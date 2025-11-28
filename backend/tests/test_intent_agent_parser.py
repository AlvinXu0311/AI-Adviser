import pytest

from app.agents.intent_agent import IntentAgent


def test_fallback_parse_full_payload():
    raw = (
        '{"intent":"user asking about their personal transcript data","confidence":0.82,'
        '"is_academic":true,"requires_transcript":true,'
        '"reasoning":"User wants to know about their own info"}'
    )
    parsed = IntentAgent._fallback_parse(raw)
    assert parsed["intent"] == "user asking about their personal transcript data"
    assert pytest.approx(parsed["confidence"], rel=1e-6) == 0.82
    assert parsed["is_academic"] is True
    assert parsed["requires_transcript"] is True


def test_fallback_parse_missing_fields_defaults():
    raw = '{"intent":"program query"}'
    parsed = IntentAgent._fallback_parse(raw)
    assert parsed["intent"] == "program query"
    assert parsed["confidence"] == 0.5
    assert parsed["is_academic"] is True
    assert parsed["requires_transcript"] is False


def test_fallback_parse_code_block():
    raw = """
```json
{
    "intent": "course requirements question"
}
```
"""
    parsed = IntentAgent._fallback_parse(raw)
    assert parsed["intent"] == "course requirements question"
    assert parsed["confidence"] == 0.5
    assert parsed["is_academic"] is True
    assert parsed["requires_transcript"] is False
