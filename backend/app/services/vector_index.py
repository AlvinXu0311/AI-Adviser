"""
Offline, versioned builds of the PDF vector index.

Layout under database/vector_index/:
    versions/<version>/     one complete Chroma index per build
        manifest.json       written last; a version without it is incomplete and never served
    CURRENT                 name of the active version (replaced atomically)
    .build.lock             held while building, so the CLI and the admin API never build at once

A build never touches the active version: it writes a new directory, validates it (every PDF
produced chunks, chunk count matches, sampled course codes come back from their own titles),
and only then flips CURRENT. Serving processes pick the change up on their next search.
Older versions are kept (VECTOR_INDEX_KEEP, default 3) so a bad catalog can be rolled back
with `activate`.

CLI (from backend/, or `docker compose exec backend ...`):
    python -m app.services.vector_index build [--no-activate]
    python -m app.services.vector_index list
    python -m app.services.vector_index activate <version>
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

import chromadb

from .pdf_vector_service import (
    COLLECTION_NAME,
    INDEX_ROOT,
    LEGACY_CHROMA_PATH,
    PDF_FILES,
    PDF_SOURCE_DIR,
    _PdfPipeline,
)

logger = logging.getLogger(__name__)

VERSIONS_DIR = os.path.join(INDEX_ROOT, "versions")
CURRENT_FILE = os.path.join(INDEX_ROOT, "CURRENT")
LOCK_FILE = os.path.join(INDEX_ROOT, ".build.lock")
MANIFEST = "manifest.json"
EMBED_BATCH = 50
PROBES = 5
# UTC build time (sorts chronologically) plus a short random suffix so two builds in one second differ
VERSION_RE = re.compile(r"^\d{8}T\d{6}Z(?:-[0-9a-f]{4})?$")


class IndexBuildError(RuntimeError):
    """The new index failed validation; the active version is unchanged."""


class BuildInProgress(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Reading the active version (used by serving processes)
# ---------------------------------------------------------------------------

def _read_manifest(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(path, MANIFEST)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def active_index() -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """(version, path, manifest) to serve: CURRENT if valid, else the legacy index, else nothing."""
    try:
        with open(CURRENT_FILE) as f:
            version = f.read().strip()
    except OSError:
        version = ""
    if version:
        path = os.path.join(VERSIONS_DIR, version)
        manifest = _read_manifest(path)
        if manifest is not None:
            return version, path, manifest
        logger.error("CURRENT points to %s, which has no manifest; ignoring it", version)
    if os.path.isdir(LEGACY_CHROMA_PATH) and os.listdir(LEGACY_CHROMA_PATH):
        return "legacy", LEGACY_CHROMA_PATH, {}
    return None, None, {}


def list_versions() -> List[Dict[str, Any]]:
    current = active_index()[0]
    versions = []
    for name in sorted(os.listdir(VERSIONS_DIR)) if os.path.isdir(VERSIONS_DIR) else []:
        manifest = _read_manifest(os.path.join(VERSIONS_DIR, name))
        versions.append({
            "version": name,
            "complete": manifest is not None,
            "active": name == current,
            "built_at": (manifest or {}).get("built_at"),
            "chunks": (manifest or {}).get("total_chunks"),
            "embedding_type": (manifest or {}).get("embedding_type"),
        })
    return versions


def activate(version: str) -> None:
    """Point CURRENT at a complete version (atomic rename, so readers never see a partial file)."""
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Not a version name: {version!r}")
    path = os.path.join(VERSIONS_DIR, version)
    if _read_manifest(path) is None:
        raise ValueError(f"{version} is not a complete index version")
    os.makedirs(INDEX_ROOT, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=INDEX_ROOT, prefix=".CURRENT.")
    with os.fdopen(fd, "w") as f:
        f.write(version + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CURRENT_FILE)
    logger.info("Activated vector index %s", version)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _build_lock() -> Iterator[None]:
    os.makedirs(INDEX_ROOT, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BuildInProgress("Another vector index build is already running")
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _sources_digest() -> Dict[str, str]:
    digests = {}
    for name in PDF_FILES:
        path = os.path.join(PDF_SOURCE_DIR, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                digests[name] = hashlib.sha256(f.read()).hexdigest()
    return digests


class IndexBuilder(_PdfPipeline):
    """Builds one new index version from the catalog PDFs."""

    def __init__(self):
        self._init_embeddings()

    def collect_chunks(self) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        chunks, per_file = [], {}
        for pdf_name in PDF_FILES:
            path = os.path.join(PDF_SOURCE_DIR, pdf_name)
            if not os.path.exists(path):
                raise IndexBuildError(f"Catalog PDF missing: {pdf_name}")
            text = self._extract_text_from_pdf(path)
            file_chunks = self._chunk_text(text, pdf_name) if text else []
            if not file_chunks:
                raise IndexBuildError(f"No text could be indexed from {pdf_name}")
            per_file[pdf_name] = len(file_chunks)
            chunks.extend(file_chunks)
        return chunks, per_file

    def write(self, path: str, chunks: List[Dict[str, Any]]) -> chromadb.Collection:
        client = chromadb.PersistentClient(path=path)
        collection = client.create_collection(COLLECTION_NAME, metadata={"description": "WPI Academic PDF Documents"})
        documents = [c["text"] for c in chunks]
        embeddings: List[List[float]] = []
        for i in range(0, len(documents), EMBED_BATCH):
            embeddings.extend(self._embed_texts(documents[i:i + EMBED_BATCH]))
        metadatas = []
        for c in chunks:
            meta = {"source": c["source"], "chunk_index": c["chunk_index"]}
            for key in ("course_code", "course_title", "chunk_type"):
                if key in c:
                    meta[key] = c[key]
            metadatas.append(meta)
        collection.add(ids=[c["id"] for c in chunks], embeddings=embeddings,
                       documents=documents, metadatas=metadatas)
        return collection

    def validate(self, collection: chromadb.Collection, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if collection.count() != len(chunks):
            raise IndexBuildError(f"Index has {collection.count()} chunks, expected {len(chunks)}")
        # Retrieval sanity: a course's own title must find that course among the top results
        courses = [c for c in chunks if c.get("course_code") and c.get("course_title")]
        step = max(1, len(courses) // PROBES)
        probes = courses[::step][:PROBES]
        hits = 0
        for c in probes:
            result = collection.query(query_embeddings=[self._embed_query(c["course_title"])], n_results=10,
                                      include=["metadatas"])
            if c["course_code"] in {m.get("course_code") for m in result["metadatas"][0]}:
                hits += 1
        if probes and hits < len(probes) - 1:
            raise IndexBuildError(f"Retrieval check failed: {hits}/{len(probes)} sampled courses found")
        return {"probes": len(probes), "probe_hits": hits}


def build(activate_after: bool = True) -> Dict[str, Any]:
    """Build, validate and (by default) activate a new version. Raises without touching CURRENT on failure."""
    with _build_lock():
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(2).hex()
        path = os.path.join(VERSIONS_DIR, version)
        os.makedirs(path)
        try:
            builder = IndexBuilder()
            chunks, per_file = builder.collect_chunks()
            collection = builder.write(path, chunks)
            checks = builder.validate(collection, chunks)
            manifest = {
                "version": version,
                "built_at": datetime.now(timezone.utc).isoformat(),
                "embedding_type": builder.embedding_type,
                "embedding_model": builder.embedding_model,
                "embedding_dims": builder.embedding_dims,
                "total_chunks": len(chunks),
                "chunks_per_file": per_file,
                "sources_sha256": _sources_digest(),
                "validation": checks,
            }
            # The manifest marks the version complete, so it is written last
            with open(os.path.join(path, MANIFEST), "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise
        if activate_after:
            activate(version)
            prune()
        logger.info("Built vector index %s (%d chunks)", version, len(chunks))
        return manifest


def prune(keep: Optional[int] = None) -> List[str]:
    """Delete the oldest complete versions beyond `keep`, plus leftovers of failed builds. Never the active one."""
    keep = keep or int(os.getenv("VECTOR_INDEX_KEEP", "3"))
    current = active_index()[0]
    versions = list_versions()
    complete = [v["version"] for v in versions if v["complete"]]
    doomed = [v["version"] for v in versions if not v["complete"]] + complete[:-keep]
    removed = []
    for name in doomed:
        if name != current:
            shutil.rmtree(os.path.join(VERSIONS_DIR, name), ignore_errors=True)
            removed.append(name)
    return removed


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.services.vector_index")
    sub = parser.add_subparsers(dest="command", required=True)
    build_cmd = sub.add_parser("build", help="build and validate a new index version")
    build_cmd.add_argument("--no-activate", action="store_true", help="build and validate only")
    sub.add_parser("list", help="list index versions")
    activate_cmd = sub.add_parser("activate", help="serve an existing version (rollback)")
    activate_cmd.add_argument("version")
    args = parser.parse_args(argv)

    if args.command == "build":
        manifest = build(activate_after=not args.no_activate)
        print(json.dumps(manifest, indent=2))
    elif args.command == "list":
        print(json.dumps(list_versions(), indent=2))
    else:
        activate(args.version)
        print(f"Active: {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
