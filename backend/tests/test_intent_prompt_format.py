import re

from app.agents.intent_agent import INTENT_PROMPT


def test_intent_prompt_escapes_braces():
    prompt = INTENT_PROMPT
    # Ensure literal JSON braces remain escaped for ChatPromptTemplate.
    assert "{{" in prompt and "}}" in prompt
    single_brace = re.search(r"(?<!{){(?![{])", prompt)
    assert single_brace is None, "prompt contains single brace that LangChain would treat as a variable"
