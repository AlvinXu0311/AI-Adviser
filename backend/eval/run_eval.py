"""
Evaluate the adviser on the gold set (eval/gold_set.jsonl) at three levels.

1. Components  intent classification (P/R/F1), retrieval (Recall@k, MRR, nDCG, hit rate),
               tool selection and tool-argument accuracy
2. End to end  answer accuracy (exact checks against SQL-derived answers), faithfulness and
               hallucination rate (LLM judge over the tool outputs), answer relevancy,
               out-of-scope refusal rate, pass^k consistency
3. Efficiency  latency p50/p95, tokens per query, LLM calls and tool calls per task

It runs the same steps as /api/chat (intent agent, then the LangGraph adviser) in-process.

    venv/bin/python -m eval.run_eval                     # full run
    venv/bin/python -m eval.run_eval --per-category 2 --k 2 --passk-items 3   # smoke test

Results go to eval/results/<timestamp>/: metrics.json, items.jsonl and report.md.
"""
import argparse
import asyncio
import contextvars
import json
import logging
import math
import os
import re
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
load_dotenv(EVAL_DIR.parents[1] / ".env")
os.environ.setdefault("BUS_SCHOOL_DB_PATH", str(EVAL_DIR.parents[1] / "database/database_project/bus_school.db"))
# Use the repo's versioned vector index and catalog (the app's defaults are Docker paths under backend/)
os.environ.setdefault("VECTOR_INDEX_ROOT", str(EVAL_DIR.parents[1] / "database/vector_index"))
os.environ.setdefault("CATALOG_PDF_DIR", str(EVAL_DIR.parents[1] / "database/database_project"))
os.environ.setdefault("LEGACY_VECTOR_DB_PATH", str(EVAL_DIR.parents[1] / "database/vector_db_pdf"))
# Transcripts live in an in-process store with a throwaway key; the eval needs no Redis
os.environ.setdefault("CONTEXT_STORE", "memory")
if not (os.getenv("CONTEXT_ENCRYPTION_KEY") or os.getenv("APP_JWT_SECRET")):
    from cryptography.fernet import Fernet
    os.environ["CONTEXT_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.tracers.context import register_configure_hook  # noqa: E402

from app.agents import adviser_agent as adviser_module  # noqa: E402
from app.agents import tools as tools_module  # noqa: E402
from app.agents.intent_agent import IntentAgent  # noqa: E402
from app.agents.adviser_agent import get_adviser_agent  # noqa: E402
from app.agents.intent_agent import get_intent_agent  # noqa: E402
from app.llm import model_name_for  # noqa: E402
from app.services.context_manager import get_context_manager, set_current_session  # noqa: E402
from app.services.untrusted import sanitize_transcript  # noqa: E402
from app.services.program_db_service import get_program_db_service  # noqa: E402
from app.services.search_service import program_search_tool, smart_course_search_tool  # noqa: E402

logger = logging.getLogger("eval")

CONFIDENCE_THRESHOLD = 0.2  # same gate as app/api/chat.py
REFUSAL_TEXT = "I'm not sure how to help with that."
CODE_RE = re.compile(r"\b([A-Z]{2,4})\s?-?(\d{3,4})\b")
JUDGE_CONTEXT_CHARS = 14000
PREFETCH = "business_school_database (prefetch)"

# ---------------------------------------------------------------------------
# Instrumentation: per-item token usage / LLM calls, and full tool outputs
# ---------------------------------------------------------------------------


class UsageCounter(BaseCallbackHandler):
    def __init__(self):
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def on_llm_end(self, response, **kwargs):
        self.llm_calls += 1
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)


_usage_var: contextvars.ContextVar[Optional[UsageCounter]] = contextvars.ContextVar("eval_usage", default=None)
register_configure_hook(_usage_var, inheritable=True)

# Tools run in executor threads with a copy of the context, so the list object is shared
_tool_log_var: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("eval_tool_log", default=None)


def _instrument_tools():
    for tool in tools_module.get_all_tools():
        original = tool.func

        def wrapped(*args, _original=original, _name=tool.name, **kwargs):
            output = _original(*args, **kwargs)
            log = _tool_log_var.get()
            if log is not None:
                log.append({"tool": _name, "args": kwargs or list(args), "output": str(output)})
            return output

        tool.func = wrapped

    # The adviser prefetches a database summary into the prompt for program/course questions;
    # it is retrieved context too, so log it like a tool call
    original_prefetch = adviser_module.business_school_db_tool

    def prefetch(query):
        output = original_prefetch(query)
        log = _tool_log_var.get()
        if log is not None and output and output.strip():
            log.append({"tool": PREFETCH, "args": {"query": query}, "output": str(output)})
        return output

    adviser_module.business_school_db_tool = prefetch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def norm_code(code: str) -> str:
    return re.sub(r"[\s-]", "", code.upper())


def codes_in(text: str) -> List[str]:
    """Course codes in order of first appearance."""
    seen = []
    for prefix, number in CODE_RE.findall(text or ""):
        code = prefix + number
        if code not in seen:
            seen.append(code)
    return seen


def pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def rnd(value, digits=3):
    return round(value, digits) if isinstance(value, (int, float)) else value


def resolve_program(arg: str) -> Optional[str]:
    result = get_program_db_service().compare_student_progress(arg, [])
    return result.get("program_name")


# ---------------------------------------------------------------------------
# 1. Retrieval (search layer on the raw question)
# ---------------------------------------------------------------------------


def eval_retrieval(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gold = [norm_code(c) for c in item.get("retrieval_codes", [])]
    if not gold:
        return None
    tool = smart_course_search_tool if item["category"] == "course_lookup" else program_search_tool
    started = time.perf_counter()
    output = tool(item["question"])
    ranked = codes_in(output)
    gold_set = set(gold)

    def recall_at(k):
        return len(gold_set & set(ranked[:k])) / len(gold_set)

    first_hit = next((i for i, c in enumerate(ranked) if c in gold_set), None)
    dcg = sum(1 / math.log2(i + 2) for i, c in enumerate(ranked[:5]) if c in gold_set)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(gold_set), 5)))
    return {
        "tool": tool.__name__,
        "ranked_codes": ranked[:15],
        "recall@5": recall_at(5),
        "recall@10": recall_at(10),
        "context_recall": recall_at(len(ranked)),
        "hit@5": float(first_hit is not None and first_hit < 5),
        "mrr": 1 / (first_hit + 1) if first_hit is not None else 0.0,
        "ndcg@5": dcg / idcg if idcg else 0.0,
        "latency_ms": (time.perf_counter() - started) * 1000,
    }


# ---------------------------------------------------------------------------
# 2. Pipeline run (intent → adviser), mirroring app/api/chat.py
# ---------------------------------------------------------------------------


async def run_pipeline(item: Dict[str, Any]) -> Dict[str, Any]:
    session_id = f"eval-{item['id']}-{uuid.uuid4().hex[:6]}"
    set_current_session(session_id)
    context = None
    if item.get("transcript"):
        # Same intake as /api/extract-transcript: only validated fields reach the agent
        manager = get_context_manager()
        manager.set_student_context(session_id, sanitize_transcript(item["transcript"]))
        context = manager.get_student_context(session_id)

    usage = UsageCounter()
    tool_log: list = []
    _usage_var.set(usage)
    _tool_log_var.set(tool_log)

    record: Dict[str, Any] = {"tool_calls": [], "error": None}
    started = time.perf_counter()
    try:
        # Fresh intent agent per item: its chain runs in an executor thread, which drops the
        # callback context, so usage is attached through the call config instead
        intent_agent = IntentAgent()
        intent_agent._invoke_chain = lambda message, ctx="": intent_agent.chain.invoke(
            {"question": message, "context": ctx}, config={"callbacks": [usage]})
        intent = await intent_agent.classify(item["question"], [])
        record["intent_ms"] = (time.perf_counter() - started) * 1000
        record["intent"] = intent.model_dump()
        passed = intent.is_academic and intent.confidence >= CONFIDENCE_THRESHOLD
        record["passed_intent_gate"] = passed

        if not passed:
            record["response"] = REFUSAL_TEXT
        else:
            calls = []

            async def sink(event):
                if event["type"] == "agent_action":
                    calls.append({"tool": event["tool"], "input": event["input"]})

            agent_started = time.perf_counter()
            result = await get_adviser_agent().answer_query(
                query=item["question"], context=context, session_id=session_id, on_event=sink,
            )
            record["agent_ms"] = (time.perf_counter() - agent_started) * 1000
            record["response"] = result["response"]
            record["tool_calls"] = calls
    except Exception as exc:  # recorded per item, never aborts the run
        logger.exception("Item %s failed", item["id"])
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["response"] = ""
    finally:
        _usage_var.set(None)
        _tool_log_var.set(None)
        get_context_manager().clear_student_context(session_id)

    record["latency_ms"] = (time.perf_counter() - started) * 1000
    record["llm_calls"] = usage.llm_calls
    record["input_tokens"] = usage.input_tokens
    record["output_tokens"] = usage.output_tokens
    record["tool_outputs"] = tool_log
    return record


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def answer_correct(item: Dict[str, Any], response: str) -> Optional[Dict[str, Any]]:
    """Exact check against the SQL-derived answer. None for out-of-scope items (scored as refusal).

    `none_of` (prompt-injection items) lists strings that must not appear; it fails an answer that
    otherwise passes."""
    spec = item["answer"]
    if spec.get("refuse"):
        return None
    result = _positive_check(item, spec, response or "")
    forbidden = [s for s in spec.get("none_of", []) if s.lower() in (response or "").lower()]
    if forbidden:
        result = {**result, "correct": False, "forbidden": forbidden}
    return result


def _positive_check(item: Dict[str, Any], spec: Dict[str, Any], text: str) -> Dict[str, Any]:
    lower = text.lower()
    if "codes" in spec:
        gold = {norm_code(c) for c in spec["codes"]}
        found = gold & set(codes_in(text.upper()))
        recall = len(found) / len(gold)
        return {"correct": recall == 1.0, "code_recall": recall,
                "missing": sorted(gold - found)}
    if "any_of" in spec:
        return {"correct": any(s.lower() in lower for s in spec["any_of"])}
    if "all_of" in spec:
        return {"correct": all(s.lower() in lower for s in spec["all_of"])}
    if "regex" in spec:
        return {"correct": re.search(spec["regex"], text, re.IGNORECASE) is not None}
    raise ValueError(f"Unknown answer spec for {item['id']}: {spec}")


def tool_scores(item: Dict[str, Any], record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    expected = item.get("expected_tools") or []
    if not expected or not record.get("passed_intent_gate"):
        return None
    agent_called = [c["tool"] for c in record["tool_calls"]]
    prefetched = any(t["tool"] == PREFETCH for t in record.get("tool_outputs", []))
    # The automatic prefetch is a business_school_database call made before the agent's first turn
    called = (["business_school_database"] if prefetched else []) + agent_called
    selected = any(t in expected for t in called)
    agent_selected = any(t in expected for t in agent_called)
    first_ok = bool(called) and called[0] in expected

    arg_ok = None
    relevant = [c for c in record["tool_calls"] if c["tool"] in expected]
    if relevant and (item.get("expected_arg") or item.get("expected_program")):
        arg_ok = False
        for call in relevant:
            try:
                args = json.loads(call["input"])
            except json.JSONDecodeError:
                args = {"raw": call["input"]}
            value = " ".join(str(v) for v in args.values())
            if item.get("expected_arg"):
                target = item["expected_arg"]
                if (CODE_RE.fullmatch(target) and norm_code(target) in {norm_code(c) for c in codes_in(value.upper())}) \
                        or target.lower() in value.lower():
                    arg_ok = True
            elif resolve_program(value) == item["expected_program"]:
                arg_ok = True
    return {"called": called, "prefetched": prefetched, "selected": selected, "agent_selected": agent_selected,
            "first_call_correct": first_ok, "arg_correct": arg_ok}


JUDGE_PROMPT = """You are grading an academic-advising assistant for WPI Business School.

QUESTION:
{question}

RETRIEVED CONTEXT (everything the assistant's tools returned):
{context}

ASSISTANT ANSWER:
{answer}

Tasks:
1. Break the answer into its factual claims about courses, programs, requirements, instructors, credits,
   or the student's record. Ignore greetings, offers to help and generic advice.
2. For each claim decide if the retrieved context supports it.
3. Rate how well the answer addresses the question (relevancy) from 1 (off-topic) to 5 (fully on point).

Reply with JSON only:
{{"claims": [{{"claim": "...", "supported": true}}], "relevancy": 1-5}}"""

REFUSAL_JUDGE_PROMPT = """A university academic-advising assistant received this message, which is outside its scope:
"{question}"

It replied:
"{answer}"

Did the assistant decline or redirect to academic topics instead of actually doing the off-topic task?
Reply with JSON only: {{"declined": true}} or {{"declined": false}}"""


class Judge:
    def __init__(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        from app.config import gemini_model

        self.model_name = os.getenv("EVAL_JUDGE_MODEL", gemini_model())
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name, temperature=0, thinking_level="low",
            max_output_tokens=4096, api_key=os.getenv("GOOGLE_API_KEY"),
        )

    async def _json(self, prompt: str) -> Dict[str, Any]:
        from app.agents.intent_agent import IntentAgent

        for attempt in range(3):
            try:
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                text = IntentAgent._extract_text(response).strip()
                text = text.strip("`").removeprefix("json").strip()
                start, end = text.find("{"), text.rfind("}")
                return json.loads(text[start:end + 1])
            except Exception as exc:
                if attempt == 2:
                    return {"error": str(exc)}
                await asyncio.sleep(2 * (attempt + 1))
        return {}

    async def grounding(self, item, record) -> Dict[str, Any]:
        context = "\n\n".join(f"[{t['tool']}({json.dumps(t['args'])})]\n{t['output']}" for t in record["tool_outputs"])
        if not context:
            context = "(no tools were called)"
        data = await self._json(JUDGE_PROMPT.format(
            question=item["question"], context=context[:JUDGE_CONTEXT_CHARS], answer=record["response"]))
        if "error" in data:
            return {"judge_error": data["error"]}
        claims = data.get("claims") or []
        supported = sum(1 for c in claims if c.get("supported"))
        return {
            "claims": len(claims),
            "unsupported_claims": [c.get("claim") for c in claims if not c.get("supported")],
            "faithfulness": supported / len(claims) if claims else 1.0,
            "relevancy": data.get("relevancy"),
        }

    async def declined(self, item, record) -> Optional[bool]:
        data = await self._json(REFUSAL_JUDGE_PROMPT.format(question=item["question"], answer=record["response"]))
        return data.get("declined")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def binary_prf(pairs: List[tuple]) -> Dict[str, Any]:
    """pairs of (gold, predicted) booleans; positive class = True."""
    tp = sum(1 for g, p in pairs if g and p)
    fp = sum(1 for g, p in pairs if not g and p)
    fn = sum(1 for g, p in pairs if g and not p)
    tn = sum(1 for g, p in pairs if not g and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def aggregate(items, records, retrieval, passk) -> Dict[str, Any]:
    by_id = {i["id"]: i for i in items}
    ok = [r for r in records if not r["error"]]

    # Intent
    pairs = [(by_id[r["id"]]["is_academic"], r["passed_intent_gate"]) for r in ok]
    academic_prf = binary_prf(pairs)
    oos_prf = binary_prf([(not g, not p) for g, p in pairs])
    intent = {
        "accuracy": sum(1 for g, p in pairs if g == p) / len(pairs) if pairs else None,
        "academic_class": academic_prf,
        "out_of_scope_class": oos_prf,
        "macro_f1": (academic_prf["f1"] + oos_prf["f1"]) / 2,
        "n": len(pairs),
    }

    # Retrieval
    retr = {}
    groups = defaultdict(list)
    for item_id, r in retrieval.items():
        groups["all"].append(r)
        groups[by_id[item_id]["category"]].append(r)
    for name, rows in groups.items():
        retr[name] = {m: mean(x[m] for x in rows) for m in ("recall@5", "recall@10", "context_recall", "hit@5", "mrr", "ndcg@5")}
        retr[name]["n"] = len(rows)

    # Tools
    tool_rows = [r["tools"] for r in ok if r.get("tools")]
    arg_rows = [t["arg_correct"] for t in tool_rows if t["arg_correct"] is not None]
    tools = {
        "selection_accuracy": mean(float(t["selected"]) for t in tool_rows),
        "agent_only_selection_accuracy": mean(float(t["agent_selected"]) for t in tool_rows),
        "first_call_accuracy": mean(float(t["first_call_correct"]) for t in tool_rows),
        "argument_accuracy": mean(float(a) for a in arg_rows),
        "n": len(tool_rows), "n_args": len(arg_rows),
        "by_category": {},
    }
    for cat in sorted({by_id[r["id"]]["category"] for r in ok if r.get("tools")}):
        rows = [r["tools"] for r in ok if r.get("tools") and by_id[r["id"]]["category"] == cat]
        args = [t["arg_correct"] for t in rows if t["arg_correct"] is not None]
        tools["by_category"][cat] = {"selection_accuracy": mean(float(t["selected"]) for t in rows),
                                     "agent_only_selection_accuracy": mean(float(t["agent_selected"]) for t in rows),
                                     "argument_accuracy": mean(float(a) for a in args), "n": len(rows)}

    # Answers
    scored = [r for r in ok if r.get("answer_check")]
    answers = {"accuracy": mean(float(r["answer_check"]["correct"]) for r in scored), "n": len(scored), "by_category": {}}
    for cat in sorted({by_id[r["id"]]["category"] for r in scored}):
        rows = [r for r in scored if by_id[r["id"]]["category"] == cat]
        entry = {"accuracy": mean(float(r["answer_check"]["correct"]) for r in rows), "n": len(rows)}
        recalls = [r["answer_check"].get("code_recall") for r in rows if "code_recall" in r["answer_check"]]
        if recalls:
            entry["code_recall"] = mean(recalls)
        answers["by_category"][cat] = entry

    grounded = [r["grounding"] for r in ok if r.get("grounding") and "faithfulness" in r["grounding"]]
    grounding = {
        "faithfulness": mean(g["faithfulness"] for g in grounded),
        "hallucination_rate": mean(float(bool(g["unsupported_claims"])) for g in grounded),
        "unsupported_claim_rate": (sum(len(g["unsupported_claims"]) for g in grounded)
                                   / max(1, sum(g["claims"] for g in grounded))),
        "answer_relevancy_1to5": mean(g["relevancy"] for g in grounded if isinstance(g.get("relevancy"), (int, float))),
        "n": len(grounded),
    }

    oos = [r for r in ok if by_id[r["id"]]["category"] == "out_of_scope"]
    refusal = {
        "refusal_rate": mean(float(r["refused"]) for r in oos if r.get("refused") is not None),
        "refused_at_intent_gate": mean(float(not r["passed_intent_gate"]) for r in oos),
        "n": len(oos),
        # Academic questions wrongly turned away by the intent gate
        "false_refusal_rate": mean(float(not r["passed_intent_gate"]) for r in ok if by_id[r["id"]]["is_academic"]),
    }

    # Efficiency
    lat = [r["latency_ms"] for r in ok]
    agent_lat = [r["latency_ms"] for r in ok if r.get("agent_ms") is not None]
    efficiency = {
        "latency_ms": {"avg": mean(lat), "p50": pct(lat, 0.5), "p95": pct(lat, 0.95), "max": max(lat) if lat else None},
        "latency_ms_answered_by_agent": {"avg": mean(agent_lat), "p50": pct(agent_lat, 0.5), "p95": pct(agent_lat, 0.95)},
        "intent_latency_ms": {"p50": pct([r["intent_ms"] for r in ok if r.get("intent_ms")], 0.5),
                              "p95": pct([r["intent_ms"] for r in ok if r.get("intent_ms")], 0.95)},
        "input_tokens_per_query": mean(r["input_tokens"] for r in ok),
        "output_tokens_per_query": mean(r["output_tokens"] for r in ok),
        "llm_calls_per_query": mean(r["llm_calls"] for r in ok),
        "tool_calls_per_agent_task": mean(len(r["tool_calls"]) for r in ok if r.get("agent_ms") is not None),
        "max_tool_calls": max((len(r["tool_calls"]) for r in ok), default=0),
    }
    price_in, price_out = os.getenv("PRICE_PER_MTOK_IN"), os.getenv("PRICE_PER_MTOK_OUT")
    if price_in and price_out:
        efficiency["usd_per_query"] = (efficiency["input_tokens_per_query"] * float(price_in)
                                       + efficiency["output_tokens_per_query"] * float(price_out)) / 1e6

    return {
        "intent": intent, "retrieval": retr, "tools": tools, "answers": answers,
        "grounding": grounding, "refusal": refusal, "consistency": passk, "efficiency": efficiency,
        "errors": len(records) - len(ok),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def f(value, kind="pct"):
    if value is None:
        return "–"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "ms":
        return f"{value / 1000:.2f} s"
    if kind == "num":
        return f"{value:.2f}"
    return str(value)


def write_report(path: Path, meta, m):
    i, t, a, g, rf, c, e = (m["intent"], m["tools"], m["answers"], m["grounding"],
                            m["refusal"], m["consistency"], m["efficiency"])
    lines = [
        "# Adviser evaluation report", "",
        f"- Run: {meta['started']} · {meta['n_items']} gold items · errors: {m['errors']}",
        f"- Adviser model: `{meta['adviser_model']}` · intent model: `{meta['intent_model']}` · judge: `{meta['judge_model']}`",
        f"- Gold set: `{meta['gold_set']}` (answers derived from SQLite; see eval/build_gold_set.py)", "",
        "## Headline", "",
        "| Metric | Value |", "|---|---|",
        f"| Intent macro-F1 | {f(i['macro_f1'], 'num')} |",
        f"| Retrieval Recall@5 | {f(m['retrieval'].get('all', {}).get('recall@5'))} |",
        f"| Tool-selection accuracy | {f(t['selection_accuracy'])} |",
        f"| Tool-argument accuracy | {f(t['argument_accuracy'])} |",
        f"| Answer accuracy (exact, SQL gold) | {f(a['accuracy'])} |",
        f"| Faithfulness (LLM judge) | {f(g['faithfulness'])} |",
        f"| Hallucination rate (answers with ≥1 unsupported claim) | {f(g['hallucination_rate'])} |",
        f"| Out-of-scope refusal rate | {f(rf['refusal_rate'])} |",
        f"| pass^{c.get('k', '-')} | {f(c.get('pass^k'))} |",
        f"| Latency p50 / p95 | {f(e['latency_ms']['p50'], 'ms')} / {f(e['latency_ms']['p95'], 'ms')} |", "",
        "## 1. Components", "",
        "### Intent classification", "",
        f"Accuracy {f(i['accuracy'])} on {i['n']} items · macro-F1 {f(i['macro_f1'], 'num')}", "",
        "| Class | Precision | Recall | F1 |", "|---|---|---|---|",
        f"| academic | {f(i['academic_class']['precision'])} | {f(i['academic_class']['recall'])} | {f(i['academic_class']['f1'], 'num')} |",
        f"| out of scope | {f(i['out_of_scope_class']['precision'])} | {f(i['out_of_scope_class']['recall'])} | {f(i['out_of_scope_class']['f1'], 'num')} |", "",
        "### Retrieval (search layer, raw question as query)", "",
        "| Slice | n | Recall@5 | Recall@10 | Context recall | Hit@5 | MRR | nDCG@5 |", "|---|---|---|---|---|---|---|---|",
    ]
    for name, r in m["retrieval"].items():
        lines.append(f"| {name} | {r['n']} | {f(r['recall@5'])} | {f(r['recall@10'])} | {f(r['context_recall'])} | "
                     f"{f(r['hit@5'])} | {f(r['mrr'], 'num')} | {f(r['ndcg@5'], 'num')} |")
    lines += ["", "### Tool calling", "",
              f"Selection {f(t['selection_accuracy'])} (n={t['n']}) · agent's own calls only {f(t['agent_only_selection_accuracy'])} · "
              f"first call correct {f(t['first_call_accuracy'])} · arguments {f(t['argument_accuracy'])} (n={t['n_args']})", "",
              "Selection counts the automatic database prefetch as a `business_school_database` call; "
              "\"agent only\" counts just the tools the model chose.", "",
              "| Category | n | Selection | Agent only | Arguments |", "|---|---|---|---|---|"]
    for cat, r in t["by_category"].items():
        lines.append(f"| {cat} | {r['n']} | {f(r['selection_accuracy'])} | {f(r['agent_only_selection_accuracy'])} | "
                     f"{f(r['argument_accuracy'])} |")
    lines += ["", "## 2. End to end", "",
              "| Category | n | Answer accuracy | Course-code recall |", "|---|---|---|---|"]
    for cat, r in a["by_category"].items():
        lines.append(f"| {cat} | {r['n']} | {f(r['accuracy'])} | {f(r.get('code_recall'))} |")
    lines += [f"| **all** | {a['n']} | **{f(a['accuracy'])}** | |", "",
              f"- Faithfulness {f(g['faithfulness'])} · unsupported-claim rate {f(g['unsupported_claim_rate'])} · "
              f"hallucination rate {f(g['hallucination_rate'])} · answer relevancy {f(g['answer_relevancy_1to5'], 'num')}/5 (n={g['n']})",
              f"- Out-of-scope: refusal rate {f(rf['refusal_rate'])} (n={rf['n']}), {f(rf['refused_at_intent_gate'])} stopped at the intent gate; "
              f"academic questions wrongly refused: {f(rf['false_refusal_rate'])}",
              f"- Consistency: pass^{c.get('k')} {f(c.get('pass^k'))}, pass@{c.get('k')} {f(c.get('pass@k'))} on {c.get('n', 0)} items "
              f"(an item passes^k only if all k runs are correct)", "",
              "## 3. Efficiency", "",
              "| Metric | Value |", "|---|---|",
              f"| End-to-end latency avg / p50 / p95 / max | {f(e['latency_ms']['avg'], 'ms')} / {f(e['latency_ms']['p50'], 'ms')} / "
              f"{f(e['latency_ms']['p95'], 'ms')} / {f(e['latency_ms']['max'], 'ms')} |",
              f"| Latency when the adviser answers (p50 / p95) | {f(e['latency_ms_answered_by_agent']['p50'], 'ms')} / "
              f"{f(e['latency_ms_answered_by_agent']['p95'], 'ms')} |",
              f"| Intent step p50 / p95 | {f(e['intent_latency_ms']['p50'], 'ms')} / {f(e['intent_latency_ms']['p95'], 'ms')} |",
              f"| Tokens per query (in / out) | {e['input_tokens_per_query']:.0f} / {e['output_tokens_per_query']:.0f} |",
              f"| LLM calls per query | {f(e['llm_calls_per_query'], 'num')} |",
              f"| Tool calls per adviser task (max) | {f(e['tool_calls_per_agent_task'], 'num')} ({e['max_tool_calls']}) |"]
    if "usd_per_query" in e:
        lines.append(f"| Cost per query | ${e['usd_per_query']:.5f} |")
    lines += ["", "## Notes", "",
              "- Latency is measured in-process (intent agent + LangGraph adviser), without Redis, nginx or SSE overhead, "
              f"with {meta['concurrency']} questions in flight at a time.",
              "- Faithfulness and relevancy are judged by the same model family that answers, which tends to be lenient.",
              "- Retrieval is scored on the raw question passed to the search tool; the agent itself may rewrite the query.",
              "- Failed items are listed in items.jsonl with `answer_check.correct = false`."]
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(EVAL_DIR / "gold_set.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--split", default=None, help="only items in this split (dev, test, smoke, v1, v2, or a category)")
    parser.add_argument("--per-category", type=int, default=None, help="take the first N items of each category")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--k", type=int, default=3, help="runs per item for pass^k")
    parser.add_argument("--passk-items", type=int, default=20)
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.setLevel(logging.INFO)

    items = [json.loads(line) for line in open(args.gold)]
    if args.split:  # e.g. dev, test, smoke, v2 or a category
        items = [i for i in items if args.split in (i.get("splits") or [i["category"]])]
    if args.per_category:
        taken = defaultdict(int)
        picked = []
        for item in items:
            if taken[item["category"]] < args.per_category:
                taken[item["category"]] += 1
                picked.append(item)
        items = picked
    if args.limit:
        items = items[:args.limit]
    started = datetime.now()
    out_dir = EVAL_DIR / "results" / started.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    _instrument_tools()
    get_intent_agent()
    get_adviser_agent()  # build the graph once, after the tools are instrumented
    judge = None if args.no_judge else Judge()

    # Retrieval (fast, sync, sequential)
    logger.info("Retrieval on %d items", sum(1 for i in items if i.get("retrieval_codes")))
    retrieval = {}
    for item in items:
        r = eval_retrieval(item)
        if r:
            retrieval[item["id"]] = r

    sem = asyncio.Semaphore(args.concurrency)
    done = 0

    async def run_one(item):
        nonlocal done
        async with sem:
            # Fresh context per item: contextvars set inside must not leak between items
            record = await asyncio.create_task(run_pipeline(item), context=contextvars.copy_context())
            record["id"] = item["id"]
            if not record["error"]:
                record["answer_check"] = answer_correct(item, record["response"])
                record["tools"] = tool_scores(item, record)
                if judge:
                    if item["category"] == "out_of_scope":
                        record["refused"] = (True if not record["passed_intent_gate"]
                                             else await judge.declined(item, record))
                    elif record["passed_intent_gate"]:
                        record["grounding"] = await judge.grounding(item, record)
                elif item["category"] == "out_of_scope":
                    record["refused"] = not record["passed_intent_gate"]
            done += 1
            status = "ERR" if record["error"] else ("ok" if (record.get("answer_check") or {}).get("correct") or record.get("refused") else "x")
            logger.info("[%d/%d] %s %-22s %5.1fs %s", done, len(items), item["id"], item["category"],
                        record["latency_ms"] / 1000, status)
            return record

    records = await asyncio.gather(*(run_one(item) for item in items))

    # pass^k: re-run a stratified subset of academic items k-1 more times
    passk = {"k": args.k}
    if args.k > 1:
        academic = [i for i in items if i["is_academic"] and i["category"] != "no_transcript"]
        by_cat = defaultdict(list)
        for i in academic:
            by_cat[i["category"]].append(i)
        subset = []
        while len(subset) < min(args.passk_items, len(academic)):
            for cat in sorted(by_cat):
                if by_cat[cat] and len(subset) < args.passk_items:
                    subset.append(by_cat[cat].pop(0))
        first = {r["id"]: r for r in records}
        runs = defaultdict(list)
        for item in subset:
            runs[item["id"]].append(bool((first[item["id"]].get("answer_check") or {}).get("correct")))
        logger.info("pass^%d: %d items × %d extra runs", args.k, len(subset), args.k - 1)

        async def rerun(item):
            async with sem:
                rec = await asyncio.create_task(run_pipeline(item), context=contextvars.copy_context())
                check = answer_correct(item, rec["response"]) if not rec["error"] else None
                runs[item["id"]].append(bool(check and check["correct"]))

        await asyncio.gather(*(rerun(item) for item in subset for _ in range(args.k - 1)))
        passk.update({
            "n": len(subset),
            "pass^k": mean(float(all(v)) for v in runs.values()),
            "pass@k": mean(float(any(v)) for v in runs.values()),
            "pass@1": mean(float(v[0]) for v in runs.values()),
            "runs": dict(runs),
        })

    metrics = aggregate(items, records, retrieval, passk)
    meta = {
        "started": started.isoformat(timespec="seconds"), "n_items": len(items), "gold_set": args.gold,
        "adviser_model": model_name_for("adviser"), "intent_model": model_name_for("intent"),
        "judge_model": judge.model_name if judge else None, "concurrency": args.concurrency,
        "wall_clock_s": round((datetime.now() - started).total_seconds()),
    }

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        return rnd(obj, 4) if isinstance(obj, float) else obj

    (out_dir / "metrics.json").write_text(json.dumps(clean({"meta": meta, **metrics}), indent=2, ensure_ascii=False))
    with (out_dir / "items.jsonl").open("w") as fh:
        by_id = {i["id"]: i for i in items}
        for r in records:
            row = {**by_id[r["id"]], **r, "retrieval": retrieval.get(r["id"])}
            row.pop("transcript", None)
            for t in row.get("tool_outputs", []):
                t["output"] = t["output"][:2000]
            fh.write(json.dumps(clean(row), ensure_ascii=False) + "\n")
    write_report(out_dir / "report.md", meta, metrics)
    print(f"\nResults written to {out_dir}")
    print((out_dir / "report.md").read_text())


if __name__ == "__main__":
    asyncio.run(main())
