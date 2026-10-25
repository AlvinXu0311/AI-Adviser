"""
LangSmith tracing: redaction, trace nesting, and opaque tracing of document handlers.

Runs are captured at the HTTP layer of a real langsmith.Client, i.e. after the anonymizer,
exactly as they would leave the process.
"""
import asyncio
import json
from unittest.mock import Mock

import langsmith
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langsmith.anonymizer import create_anonymizer

from app import observability
from app.observability import REDACTION_RULES, chat_turn_trace, traced_opaque


@pytest.fixture
def captured(monkeypatch):
    """Enable tracing with a client whose HTTP calls are recorded instead of sent."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    client = langsmith.Client(api_key="test-key", api_url="http://langsmith.invalid",
                              auto_batch_tracing=False, anonymizer=create_anonymizer(REDACTION_RULES))
    posted = []

    def fake_request(method, url, *args, **kwargs):
        body = kwargs.get("data")
        if body:
            posted.append((method, url, json.loads(body)))
        return Mock(status_code=200, ok=True, raise_for_status=lambda: None)

    client.session.request = fake_request
    monkeypatch.setattr(observability, "get_client", lambda: client)
    previous = langsmith.run_trees._CLIENT
    langsmith.configure(client=client)
    yield posted
    langsmith.configure(client=previous)


def _runs(posted):
    """Merge create (POST) and update (PATCH) payloads per run id."""
    runs = {}
    for _method, _url, body in posted:
        runs.setdefault(body.get("id") or _url.rsplit("/", 1)[-1], {}).update(body)
    return list(runs.values())


@pytest.mark.unit
class TestRedaction:
    @pytest.mark.parametrize("text,leaked", [
        ("Contact jane.roe@wpi.edu about MIS 571", "jane.roe@wpi.edu"),
        ("- Student ID: 900000001\n- GPA: 3.6", "900000001"),
        ("Student ID A00123456 enrolled", "A00123456"),
        ("- Name: Jane Roe\n- GPA: 3.62", "Jane Roe"),
        ('{"student_name": "Jane Roe", "gpa": 3.6}', "Jane Roe"),
        ("Student: Test Student   Program: MSIT", "Test Student"),
    ])
    def test_pii_masked(self, text, leaked):
        redacted = create_anonymizer(REDACTION_RULES)({"text": text})["text"]
        assert leaked not in redacted

    def test_course_facts_survive(self):
        text = "MIS 571 Database Applications Development, 3 credits, GPA 3.62"
        assert create_anonymizer(REDACTION_RULES)({"t": text})["t"] == text

    def test_user_hash_is_stable_and_not_the_email(self):
        assert observability.user_hash("a@wpi.edu") == observability.user_hash("a@wpi.edu")
        assert "a@wpi.edu" not in observability.user_hash("a@wpi.edu")


@pytest.mark.unit
class TestChatTurnTrace:
    def test_disabled_is_a_no_op(self, monkeypatch):
        monkeypatch.setenv("LANGSMITH_TRACING", "false")
        with chat_turn_trace("s" * 32, "u@wpi.edu", {"message": "hi"}) as run:
            assert run is None

    def test_llm_call_in_thread_nests_under_turn_and_is_redacted(self, captured):
        model = FakeListChatModel(responses=["Your GPA is 3.62."])

        async def turn():
            with chat_turn_trace("sess" * 8, "jane.roe@wpi.edu", {"message": "hi, I'm jane.roe@wpi.edu"}) as run:
                # Same path the intent agent uses: a blocking LangChain call in a worker thread
                await asyncio.to_thread(model.invoke, "- Name: Jane Roe\n- Student ID: 900000001\nWhat is my GPA?")
                run.end(outputs={"response": "ok"})
                return run

        root = asyncio.run(turn())
        runs = _runs(captured)
        by_name = {r.get("name"): r for r in runs}

        assert "chat_turn" in by_name and "FakeListChatModel" in by_name
        child = by_name["FakeListChatModel"]
        assert child["trace_id"] == str(root.trace_id)
        assert child["parent_run_id"] == str(root.id)

        wire = json.dumps(captured)
        for secret in ("jane.roe@wpi.edu", "Jane Roe", "900000001"):
            assert secret not in wire
        # Metadata identifies the thread and a pseudonymous user, not the email
        metadata = by_name["chat_turn"]["extra"]["metadata"]
        assert metadata["session_id"] == "sess" * 8
        assert metadata["user"] == observability.user_hash("jane.roe@wpi.edu")


@pytest.mark.unit
class TestOpaqueTracing:
    def test_only_shapes_are_recorded(self, captured):
        @traced_opaque("transcript_ocr",
                       describe_inputs=lambda i: {"pdf_base64_chars": len(i["pdf_base64"])},
                       describe_outputs=lambda text: {"text_chars": len(text)})
        def ocr(pdf_base64: str) -> str:
            return "Student: Jane Roe, MIS 571 A"

        assert ocr("JVBERi0xLjQ=") == "Student: Jane Roe, MIS 571 A"
        langsmith.run_trees.get_cached_client().flush()

        runs = _runs(captured)
        run = next(r for r in runs if r.get("name") == "transcript_ocr")
        assert run["inputs"] == {"pdf_base64_chars": 12}
        assert run["outputs"] == {"text_chars": 28}
        assert "MIS 571" not in json.dumps(captured)


@pytest.mark.unit
def test_agent_input_omits_student_name_and_id():
    """The model never sees name/ID, so they can't surface in answers, reasoning or traces."""
    from app.agents.adviser_agent import AdviserAgent
    from app.services.context_manager import StudentContext

    context = StudentContext()
    context.update_from_transcript({"student_name": "Jane Roe", "student_id": "900000001", "gpa": 3.6,
                                    "degree_program": "MSIT", "courses": [{"course_code": "MIS 571"}]})
    text = AdviserAgent._format_agent_input(object.__new__(AdviserAgent), "What do I need?", context)
    assert "Jane Roe" not in text and "900000001" not in text
    assert "GPA: 3.6" in text and "Program: MSIT" in text
