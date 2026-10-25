"""
Offline, versioned vector index builds: validation gates activation, serving hot-swaps versions.

Uses the real catalog PDFs and Chroma, with a deterministic bag-of-words embedder so the
tests need no API key or model download.
"""
import hashlib
import json
import os
import re
import threading

import pytest

from app.services import pdf_vector_service, vector_index

DIM = 256
# The catalog PDFs live in the repo's database/ (mounted at /app/database in Docker)
REPO_PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "database", "database_project")


def bow_embed(text: str):
    vec = [0.0] * DIM
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@pytest.fixture
def index_root(tmp_path, monkeypatch):
    root = str(tmp_path / "vector_index")
    monkeypatch.setattr(vector_index, "INDEX_ROOT", root)
    monkeypatch.setattr(vector_index, "VERSIONS_DIR", os.path.join(root, "versions"))
    monkeypatch.setattr(vector_index, "CURRENT_FILE", os.path.join(root, "CURRENT"))
    monkeypatch.setattr(vector_index, "LOCK_FILE", os.path.join(root, ".build.lock"))
    monkeypatch.setattr(vector_index, "LEGACY_CHROMA_PATH", str(tmp_path / "no-legacy"))
    monkeypatch.setattr(vector_index, "PDF_SOURCE_DIR", os.path.abspath(REPO_PDF_DIR))

    def fake_init(self, provider="fake", allow_fallback=True, model=None):
        self.embedding_type, self.embedding_model, self.embedding_dims = "fake", model or "bow", DIM

    monkeypatch.setattr(pdf_vector_service._PdfPipeline, "_init_embeddings", fake_init)
    monkeypatch.setattr(pdf_vector_service._PdfPipeline, "_embed_texts", lambda self, texts: [bow_embed(t) for t in texts])
    monkeypatch.setattr(pdf_vector_service._PdfPipeline, "_embed_query", lambda self, q: bow_embed(q))
    return root


@pytest.mark.unit
class TestBuild:
    def test_build_validates_and_activates(self, index_root):
        manifest = vector_index.build()
        version, path, active_manifest = vector_index.active_index()
        assert version == manifest["version"] and active_manifest["total_chunks"] == manifest["total_chunks"]
        assert set(manifest["chunks_per_file"]) == set(pdf_vector_service.PDF_FILES)
        assert manifest["validation"]["probe_hits"] >= manifest["validation"]["probes"] - 1
        assert len(manifest["sources_sha256"]) == len(pdf_vector_service.PDF_FILES)

    def test_failed_validation_leaves_active_index_untouched(self, index_root, monkeypatch):
        first = vector_index.build()["version"]
        # Broken embeddings: every vector identical, so retrieval can't find anything specific
        monkeypatch.setattr(pdf_vector_service._PdfPipeline, "_embed_texts", lambda self, texts: [[1.0] * DIM for _ in texts])
        with pytest.raises(vector_index.IndexBuildError):
            vector_index.build()
        assert vector_index.active_index()[0] == first
        assert [v["version"] for v in vector_index.list_versions()] == [first]  # failed dir removed

    def test_missing_catalog_pdf_rejected(self, index_root, monkeypatch):
        monkeypatch.setattr(vector_index, "PDF_FILES", pdf_vector_service.PDF_FILES + ["missing.pdf"])
        with pytest.raises(vector_index.IndexBuildError, match="missing"):
            vector_index.build()
        assert vector_index.active_index()[0] is None

    def test_concurrent_builds_are_refused(self, index_root):
        with vector_index._build_lock():
            with pytest.raises(vector_index.BuildInProgress):
                vector_index.build()

    def test_no_activate_builds_without_switching(self, index_root):
        manifest = vector_index.build(activate_after=False)
        assert vector_index.active_index()[0] is None
        vector_index.activate(manifest["version"])
        assert vector_index.active_index()[0] == manifest["version"]


@pytest.mark.unit
class TestVersions:
    def _fake_version(self, root, name, complete=True):
        path = os.path.join(root, "versions", name)
        os.makedirs(path)
        if complete:
            with open(os.path.join(path, "manifest.json"), "w") as f:
                json.dump({"version": name, "total_chunks": 1, "embedding_type": "fake"}, f)

    def test_activate_rolls_back_and_rejects_bad_names(self, index_root):
        self._fake_version(index_root, "20260101T000000Z")
        self._fake_version(index_root, "20260201T000000Z")
        self._fake_version(index_root, "20260301T000000Z", complete=False)
        vector_index.activate("20260201T000000Z")
        vector_index.activate("20260101T000000Z")
        assert vector_index.active_index()[0] == "20260101T000000Z"
        with pytest.raises(ValueError):
            vector_index.activate("20260301T000000Z")  # incomplete
        with pytest.raises(ValueError):
            vector_index.activate("../../etc")

    def test_prune_keeps_newest_and_active(self, index_root):
        names = [f"2026010{i}T000000Z" for i in range(1, 6)]
        for name in names:
            self._fake_version(index_root, name)
        self._fake_version(index_root, "20260109T000000Z", complete=False)
        vector_index.activate(names[0])  # oldest is active (after a rollback)
        removed = vector_index.prune(keep=2)
        left = [v["version"] for v in vector_index.list_versions()]
        assert names[0] in left and names[-1] in left and names[-2] in left
        assert "20260109T000000Z" in removed

    def test_current_without_manifest_is_ignored(self, index_root):
        os.makedirs(index_root, exist_ok=True)
        with open(os.path.join(index_root, "CURRENT"), "w") as f:
            f.write("20260101T000000Z\n")
        assert vector_index.active_index() == (None, None, {})


@pytest.mark.unit
class TestServingHotSwap:
    @pytest.fixture
    def service(self, index_root, monkeypatch):
        monkeypatch.setattr(pdf_vector_service, "RELOAD_CHECK_SECONDS", 0)
        monkeypatch.setattr(pdf_vector_service.PDFVectorService, "_instance", None)
        monkeypatch.setattr(pdf_vector_service.PDFVectorService, "_initialized", False)
        yield pdf_vector_service.PDFVectorService
        pdf_vector_service.PDFVectorService._instance = None
        pdf_vector_service.PDFVectorService._initialized = False

    def test_serves_new_version_without_restart_and_keeps_answering(self, service, index_root):
        first = vector_index.build()["version"]
        svc = service()
        assert svc.version == first
        assert svc.search("Database Applications Development", top_k=3)

        # Searches keep succeeding while a new version is built and activated
        errors, results = [], []

        def reader():
            for _ in range(20):
                try:
                    results.append(len(svc.search("Business Intelligence", top_k=3)))
                except Exception as exc:  # pragma: no cover - the assertion reports it
                    errors.append(exc)

        thread = threading.Thread(target=reader)
        thread.start()
        second = vector_index.build()["version"]
        thread.join()
        assert not errors and all(results)

        svc.search("anything")
        assert svc.version == second and svc.get_stats()["index_version"] == second

    def test_no_index_returns_empty_instead_of_building(self, service, index_root):
        svc = service()
        assert svc.collection is None
        assert svc.search("MIS 571") == []
        assert not os.path.exists(os.path.join(index_root, "versions"))  # serving never builds

    def test_index_with_wrong_vector_size_is_refused(self, service, index_root, monkeypatch):
        """A version whose vectors don't fit the query model must not replace a working one."""
        good = vector_index.build()["version"]
        svc = service()
        assert svc.version == good

        monkeypatch.setattr(pdf_vector_service._PdfPipeline, "_embed_texts",
                            lambda self, texts: [bow_embed(t) + [0.0] * 8 for t in texts])
        monkeypatch.setattr(vector_index.IndexBuilder, "validate", lambda self, c, chunks: {})
        bad = vector_index.build()["version"]
        assert vector_index.active_index()[0] == bad

        assert svc.search("Database Applications Development", top_k=3)  # still answering
        assert svc.version == good
