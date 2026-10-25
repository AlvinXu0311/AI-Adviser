"""
LangSmith Datasets & Experiments for the 127-question gold set.

    upload   create or update the dataset (one split per category, stable example ids)
    replay   turn a saved run (eval/results/<run>/items.jsonl) into an experiment: no model calls
    live     run the current agent over the dataset as a new experiment (calls Gemini; every
             example links to its full trace). The answers are also saved locally to
             eval/results/<time>-<experiment>/items.jsonl, the format deepeval_judge.py scores.

Every experiment gets the same evaluators, all deterministic and free:
    answer_correct   rule check against the SQL-derived gold answer (same rules as run_eval.py)
    tool_selection   an acceptable tool was used (expected_tools are alternatives)
    intent_gate      academic questions pass the gate, out-of-scope ones are refused
    latency_s        end-to-end seconds (from the original run when replaying)
plus a summary evaluator with answer accuracy per category. LLM-as-judge evaluators can be
added to the dataset in the LangSmith UI on top of these.

Run from backend/ with the backend venv (LANGSMITH_API_KEY in the repo .env):
    venv/bin/python -m eval.langsmith_experiments upload
    venv/bin/python -m eval.langsmith_experiments replay --run eval/results/20261015-000318
    venv/bin/python -m eval.langsmith_experiments live --split smoke       # or test, dev, v2, a category
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
load_dotenv(EVAL_DIR.parents[1] / ".env")

import langsmith  # noqa: E402
from langsmith.anonymizer import create_anonymizer  # noqa: E402

DATASET = os.getenv("LANGSMITH_DATASET", "wpi-adviser-gold")
# Stable example ids: re-uploading updates examples in place instead of duplicating them
ID_NAMESPACE = uuid.UUID("6f1f6a52-2f8e-4b52-9f0c-5d8a8f5f4b11")


def example_id(gold_id: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, gold_id))


def client() -> langsmith.Client:
    if not os.getenv("LANGSMITH_API_KEY"):
        sys.exit("LANGSMITH_API_KEY is not set in the repo .env")
    # Same redaction as the app's tracing (the gold transcripts are synthetic, but traces of the
    # live agent go through the same code paths as production)
    from app.observability import REDACTION_RULES
    return langsmith.Client(anonymizer=create_anonymizer(REDACTION_RULES))


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=EVAL_DIR).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def load_gold(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def to_example(item: Dict[str, Any]) -> Dict[str, Any]:
    inputs = {"question": item["question"], "gold_id": item["id"]}
    if item.get("transcript"):
        inputs["transcript"] = item["transcript"]
    outputs = {k: item[k] for k in ("reference", "answer", "expected_tools", "expected_arg",
                                    "expected_program", "is_academic") if k in item}
    return {"id": example_id(item["id"]), "inputs": inputs, "outputs": outputs,
            "metadata": {"gold_id": item["id"], "category": item["category"]},
            # category, dev/test holdout, v1/v2 and smoke (see build_gold_set.assign_splits)
            "split": item.get("splits") or [item["category"]]}


def upload(ls: langsmith.Client, gold: List[Dict[str, Any]]) -> None:
    if ls.has_dataset(dataset_name=DATASET):
        dataset = ls.read_dataset(dataset_name=DATASET)
    else:
        dataset = ls.create_dataset(DATASET, description=(
            "WPI Business School adviser gold set derived from bus_school.db (courses, programs, "
            "specialties, requirement counts, degree audits with synthetic transcripts) plus "
            "hand-written out-of-scope, no-transcript, clarification and prompt-injection prompts. "
            "Splits: one per category, dev/test (70/30, grouped by course/program/specialty), "
            "smoke (2 per category), v1 (original 127) and v2."))
    existing = {str(e.id) for e in ls.list_examples(dataset_id=dataset.id)}
    examples = [to_example(item) for item in gold]
    new = [e for e in examples if e["id"] not in existing]
    changed = [e for e in examples if e["id"] in existing]
    if new:
        ls.create_examples(dataset_id=dataset.id, examples=new)
    if changed:
        ls.update_examples(dataset_id=dataset.id, updates=changed)
    stale = existing - {e["id"] for e in examples}
    if stale:
        ls.delete_examples(example_ids=list(stale))
    print(f"Dataset {DATASET!r}: {len(new)} created, {len(changed)} updated, {len(stale)} removed "
          f"({len(examples)} examples) -> {dataset.url}")


# ---------------------------------------------------------------------------
# Evaluators (deterministic)
# ---------------------------------------------------------------------------

def _item(inputs: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": inputs.get("gold_id"), "question": inputs.get("question"), **reference}


def _errored(key: str, outputs: dict) -> Optional[dict]:
    """Failed runs (timeouts, exceptions) get no score, as in run_eval, with the error as comment."""
    if outputs.get("error"):
        return {"key": key, "score": None, "comment": f"run failed: {outputs['error']}"[:300]}
    return None


def answer_correct(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    from eval.run_eval import answer_correct as rule_check
    if failed := _errored("answer_correct", outputs):
        return failed
    spec_item = _item(inputs, reference_outputs)
    if not reference_outputs.get("answer") or reference_outputs["answer"].get("refuse"):
        return {"key": "answer_correct", "score": None, "comment": "out of scope (scored by intent_gate)"}
    result = rule_check(spec_item, outputs.get("response") or "")
    comment = f"missing {result['missing']}" if result.get("missing") else None
    return {"key": "answer_correct", "score": int(result["correct"]), "comment": comment}


def tool_selection(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if failed := _errored("tool_selection", outputs):
        return failed
    expected = reference_outputs.get("expected_tools") or []
    if not expected:
        return {"key": "tool_selection", "score": None}
    called = outputs.get("tools_called") or []
    hit = any(t in expected for t in called)
    return {"key": "tool_selection", "score": int(hit), "comment": f"called {called}; acceptable {expected}"}


def intent_gate(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if failed := _errored("intent_gate", outputs):
        return failed
    academic = reference_outputs.get("is_academic", True)
    passed = bool(outputs.get("passed_intent_gate"))
    ok = passed == academic
    comment = None if ok else ("refused an academic question" if academic else "answered an out-of-scope question")
    return {"key": "intent_gate", "score": int(ok), "comment": comment}


def latency(inputs: dict, outputs: dict) -> dict:
    ms = outputs.get("latency_ms")
    return {"key": "latency_s", "score": round(ms / 1000, 2) if ms is not None else None}


def accuracy_by_category(outputs: list, reference_outputs: list, inputs: list) -> List[dict]:
    """Summary: answer accuracy per category (the per-example view can't show this directly)."""
    from eval.run_eval import answer_correct as rule_check
    gold = {i["id"]: i for i in load_gold(EVAL_DIR / "gold_set.jsonl")}
    hits = defaultdict(list)
    for inp, out, ref in zip(inputs, outputs, reference_outputs):
        if not ref.get("answer") or ref["answer"].get("refuse") or (out or {}).get("error"):
            continue
        category = gold.get(inp.get("gold_id"), {}).get("category", "unknown")
        hits[category].append(rule_check(_item(inp, ref), (out or {}).get("response") or "")["correct"])
    return [{"key": f"accuracy_{cat}", "score": round(sum(v) / len(v), 3)} for cat, v in sorted(hits.items())]


EVALUATORS = [answer_correct, tool_selection, intent_gate, latency]


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def outputs_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    tools = (record.get("tools") or {}).get("called")
    if tools is None:  # live record: same convention as run_eval (prefetch counts as the DB tool)
        prefetched = any(t["tool"].endswith("(prefetch)") for t in record.get("tool_outputs") or [])
        tools = (["business_school_database"] if prefetched else []) + [c["tool"] for c in record.get("tool_calls") or []]
    return {
        "response": record.get("response") or "",
        "tools_called": tools,
        "passed_intent_gate": record.get("passed_intent_gate"),
        "error": record.get("error"),
        "latency_ms": record.get("latency_ms"),
        "llm_calls": record.get("llm_calls"),
        "input_tokens": record.get("input_tokens"),
        "output_tokens": record.get("output_tokens"),
    }


def replay(ls: langsmith.Client, run_dir: Path, name: Optional[str]) -> None:
    saved = {r["id"]: r for r in (json.loads(l) for l in (run_dir / "items.jsonl").read_text().splitlines())}
    meta_file = run_dir / "metrics.json"
    run_meta = json.loads(meta_file.read_text()).get("meta", {}) if meta_file.exists() else {}

    def target(inputs: dict) -> dict:
        record = saved.get(inputs["gold_id"])
        if record is None:
            raise KeyError(f"{inputs['gold_id']} not in {run_dir.name}")
        return outputs_from_record(record)

    # Only the examples this run answered (an older run predates newer gold items)
    examples = [e for e in ls.list_examples(dataset_name=DATASET) if e.inputs.get("gold_id") in saved]
    print(f"Replaying {len(examples)} examples answered in {run_dir.name}")
    results = langsmith.evaluate(
        target, data=examples, evaluators=EVALUATORS, summary_evaluators=[accuracy_by_category],
        experiment_prefix=name or f"replay-{run_dir.name}",
        description=f"Saved run {run_dir.name} replayed from items.jsonl (no model calls).",
        metadata={"mode": "replay", "run": run_dir.name, **{k: run_meta[k] for k in ("model", "commit") if k in run_meta}},
        max_concurrency=8, client=ls,
    )
    print(f"Experiment: {results.experiment_name}")


async def live(ls: langsmith.Client, limit: Optional[int], split: Optional[str], concurrency: int) -> None:
    from app.config import gemini_model
    from eval.run_eval import _instrument_tools, run_pipeline

    # Record tool outputs and the DB prefetch exactly as run_eval does (tool_selection depends on it)
    _instrument_tools()

    examples = list(ls.list_examples(dataset_name=DATASET, splits=[split] if split else None))
    examples.sort(key=lambda e: e.metadata.get("gold_id", ""))
    if limit:
        # Evenly spaced across the (sorted) set so a small run still covers every category
        step = max(1, len(examples) // limit)
        examples = examples[::step][:limit]

    gold = {i["id"]: i for i in load_gold(EVAL_DIR / "gold_set.jsonl")}
    records: List[Dict[str, Any]] = []

    async def target(inputs: dict) -> dict:
        item = {"id": inputs["gold_id"], "question": inputs["question"], "transcript": inputs.get("transcript")}
        record = await run_pipeline(item)
        outputs = outputs_from_record(record)
        # Same shape as run_eval's items.jsonl, so DeepEval can score this run too
        saved = {k: v for k, v in gold.get(inputs["gold_id"], {}).items() if k != "transcript"}
        records.append({**saved, **record, "tools": {"called": outputs["tools_called"]}})
        return outputs

    results = await langsmith.aevaluate(
        target, data=examples, evaluators=EVALUATORS, summary_evaluators=[accuracy_by_category],
        experiment_prefix=f"live-{git_sha()}",
        description="Current agent run over the gold set.",
        metadata={"mode": "live", "commit": git_sha(), "model": gemini_model(), "split": split, "limit": limit},
        max_concurrency=concurrency, client=ls,
    )
    print(f"Experiment: {results.experiment_name}")

    run_dir = EVAL_DIR / "results" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{results.experiment_name}"
    run_dir.mkdir(parents=True)
    with (run_dir / "items.jsonl").open("w") as f:
        for record in sorted(records, key=lambda r: r["id"]):
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    (run_dir / "metrics.json").write_text(json.dumps({"meta": {
        "experiment": results.experiment_name, "commit": git_sha(), "model": gemini_model(),
        "split": split, "items": len(records)}}, indent=2))
    print(f"Saved answers for DeepEval: {run_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("upload")
    up.add_argument("--gold", default=str(EVAL_DIR / "gold_set.jsonl"))
    rp = sub.add_parser("replay")
    rp.add_argument("--run", required=True)
    rp.add_argument("--name")
    lv = sub.add_parser("live")
    lv.add_argument("--limit", type=int)
    lv.add_argument("--split", help="one category, e.g. degree_audit")
    lv.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    ls = client()
    if args.command == "upload":
        upload(ls, load_gold(Path(args.gold)))
    elif args.command == "replay":
        replay(ls, Path(args.run).resolve(), args.name)
    else:
        asyncio.run(live(ls, args.limit, args.split, args.concurrency))
    return 0


if __name__ == "__main__":
    sys.exit(main())
