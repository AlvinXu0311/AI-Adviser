"""
Score a saved evaluation run with DeepEval, using a free judge from a different model family.

The run harness (run_eval.py) answers the gold questions with our Gemini agent and saves every
response with its tool calls and tool outputs to items.jsonl. This script re-scores those saved
answers; it never calls our agent, so it costs nothing on the Gemini side and is repeatable.

Tool use is scored as tool_selection: an answer passes if it called any of the item's expected
tools. The gold set lists acceptable alternatives (e.g. program_search or business_school_database),
so DeepEval's ToolCorrectnessMetric, which requires all of them, would under-score correct runs.

Judge: Groq's free tier, default openai/gpt-oss-120b (independent of the Gemini model being graded,
which avoids self-preference bias). The free tier caps tokens per minute and requests per day, so:
  - deterministic metrics (tool selection, out-of-scope refusal) run on every item, for free;
  - LLM metrics (faithfulness, answer relevancy, correctness vs. the reference answer) run on a
    stratified sample (--per-category);
  - requests are throttled to the per-minute limits, 429s are retried after Retry-After, and when
    the daily quota runs out the script saves progress and exits; rerunning resumes from the cache.

Usage (separate venv, see eval/requirements.txt; GROQ_API_KEY from the repo .env):
    .venv-eval/bin/python -m eval.deepeval_judge --run eval/results/<run-dir> [--per-category 3]
    .venv-eval/bin/python -m eval.deepeval_judge --run ... --report-only     # rebuild the report
"""
import argparse
import json
import os
import re
import statistics
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "NO")

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402
from openai import OpenAI, RateLimitError  # noqa: E402

from eval.deepeval_html import write_html_report  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Any OpenAI-compatible endpoint works as the judge (e.g. a local Ollama at http://127.0.0.1:11434/v1)
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", GROQ_BASE_URL)
LLM_METRICS = ("faithfulness", "answer_relevancy", "correctness")
# The right answer here is a question back to the student (which program? please upload), so there
# are no retrieved facts to be faithful to; faithfulness would only measure the judge's confusion
NO_FAITHFULNESS = {"clarification", "no_transcript"}
# Tool outputs are long; the judge sees at most this much retrieved context per answer
MAX_CONTEXT_CHARS = int(os.getenv("DEEPEVAL_MAX_CONTEXT_CHARS", "6000"))
# Longest wait we accept for a 429 before treating the quota as exhausted for today
MAX_RETRY_WAIT = float(os.getenv("GROQ_MAX_RETRY_WAIT", "90"))


def load_env() -> None:
    """GROQ_* from the repo .env (without overriding real environment variables)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip().startswith(("GROQ_", "DEEPEVAL_")):
                os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

class DailyQuotaExhausted(RuntimeError):
    pass


class GroqJudge(DeepEvalBaseLLM):
    """DeepEval model backed by Groq's OpenAI-compatible API, throttled to the free tier."""

    def __init__(self, model: str, base_url: str = GROQ_BASE_URL):
        self.model_name = model
        self.base_url = base_url
        self.rpm = int(os.getenv("GROQ_RPM", "30"))
        self.tpm = int(os.getenv("GROQ_TPM", "8000"))
        # gpt-oss models reason before answering; "low" keeps the JSON verdict within max_tokens
        self.reasoning_effort = os.getenv("GROQ_REASONING_EFFORT", "low")
        self._lock = threading.Lock()
        self._window: List[tuple] = []  # (timestamp, tokens) in the last 60 s
        self.calls = 0
        self.tokens = 0
        super().__init__(model)

    def load_model(self):
        # No key is fine for deterministic-only runs; the first real call reports it
        api_key = os.getenv("GROQ_API_KEY") if self.base_url == GROQ_BASE_URL else "local"
        return OpenAI(base_url=self.base_url, api_key=api_key, max_retries=0, timeout=300) if api_key else None

    def get_model_name(self) -> str:
        provider = "groq" if self.base_url == GROQ_BASE_URL else "openai-compatible"
        return f"{provider}/{self.model_name}"

    def supports_json_mode(self) -> bool:
        return True

    def _throttle(self, estimated_tokens: int) -> None:
        """Stay under requests-per-minute and tokens-per-minute (sliding 60 s window)."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._window = [(t, n) for t, n in self._window if now - t < 60]
                used = sum(n for _, n in self._window)
                if len(self._window) < self.rpm and used + estimated_tokens <= self.tpm:
                    self._window.append((now, estimated_tokens))
                    return
                wait = 60 - (now - self._window[0][0]) + 0.5 if self._window else 1
            time.sleep(max(wait, 0.5))

    @staticmethod
    def _retry_after(err: RateLimitError) -> float:
        header = err.response.headers.get("retry-after") if err.response is not None else None
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        # Groq also says "Please try again in 7m12.5s" in the message
        match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(err))
        if match:
            h, m, s = match.groups()
            return int(h or 0) * 3600 + int(m or 0) * 60 + float(s)
        return 30.0

    def generate(self, prompt: str, schema=None):
        if self.model is None:
            sys.exit("GROQ_API_KEY is not set (add it to the repo .env; free key at console.groq.com)")
        estimated = len(prompt) // 4 + 600  # prompt + typical verdict; 429s cover underestimates
        for attempt in range(6):
            self._throttle(estimated)
            try:
                extra = {"reasoning_effort": self.reasoning_effort} if "gpt-oss" in self.model_name else None
                response = self.model.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=2048,
                    response_format={"type": "json_object"} if schema is not None else None,
                    extra_body=extra,
                )
                break
            except RateLimitError as err:
                wait = self._retry_after(err)
                if "per day" in str(err).lower() or wait > MAX_RETRY_WAIT:
                    raise DailyQuotaExhausted(f"Groq quota exhausted (retry in {wait/60:.0f} min)") from err
                time.sleep(wait + 1)
        else:
            raise RuntimeError("Groq kept rate-limiting; giving up on this call")

        self.calls += 1
        if response.usage:
            self.tokens += response.usage.total_tokens
        text = response.choices[0].message.content or ""
        if schema is not None:
            try:
                return schema.model_validate_json(text)
            except Exception:
                return text  # DeepEval falls back to its own lenient JSON parsing
        return text

    async def a_generate(self, prompt: str, schema=None):
        import asyncio
        return await asyncio.to_thread(self.generate, prompt, schema)


# ---------------------------------------------------------------------------
# Test cases and metrics
# ---------------------------------------------------------------------------

def tool_names(item: Dict[str, Any]) -> List[str]:
    """Tools actually used, counting the automatic DB prefetch like run_eval does."""
    return list((item.get("tools") or {}).get("called") or [c["tool"] for c in item.get("tool_calls") or []])


def retrieval_context(item: Dict[str, Any]) -> List[str]:
    chunks, total = [], 0
    for out in item.get("tool_outputs") or []:
        text = f"[{out['tool']}] {out.get('output', '')}"
        if total + len(text) > MAX_CONTEXT_CHARS:
            text = text[: max(0, MAX_CONTEXT_CHARS - total)]
        if text:
            chunks.append(text)
            total += len(text)
        if total >= MAX_CONTEXT_CHARS:
            break
    return chunks


def build_test_case(item: Dict[str, Any]) -> LLMTestCase:
    return LLMTestCase(
        input=item["question"],
        actual_output=item.get("response") or "",
        expected_output=item.get("reference"),
        retrieval_context=retrieval_context(item) or None,
    )


def tool_selection(item: Dict[str, Any]) -> Dict[str, Any]:
    """1.0 if any acceptable tool was used (expected_tools are alternatives, not a checklist)."""
    called, expected = tool_names(item), item.get("expected_tools") or []
    hit = any(t in expected for t in called)
    return {"score": 1.0 if hit else 0.0, "success": hit,
            "reason": f"called {called or 'no tools'}; acceptable {expected}"}


def make_metrics(judge: GroqJudge) -> Dict[str, Any]:
    return {
        # Strict: a claim the tool outputs don't support counts against the answer, not only a
        # contradiction (DeepEval's default treats unsupported claims as faithful)
        "faithfulness": FaithfulnessMetric(model=judge, threshold=0.8, async_mode=False,
                                           truths_extraction_limit=20, penalize_ambiguous_claims=True),
        "answer_relevancy": AnswerRelevancyMetric(model=judge, threshold=0.7, async_mode=False),
        # Steps given up front, so GEval doesn't spend a call generating them
        "correctness": GEval(
            name="Correctness",
            model=judge,
            threshold=0.6,
            async_mode=False,
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT,
                               LLMTestCaseParams.EXPECTED_OUTPUT],
            evaluation_steps=[
                "List the facts in the expected output that answer the question (course codes, titles, "
                "instructors, credits, required courses, remaining requirements).",
                "Check each of those facts is stated or clearly implied in the actual output.",
                "Heavily penalize any contradiction: a wrong course code, instructor, credit count, or a "
                "course presented as required that is not.",
                "Do not penalize extra details that are correct and relevant, or a different wording.",
            ],
        ),
    }


def gradeable(item: Dict[str, Any]) -> bool:
    return item.get("is_academic") and item.get("passed_intent_gate") and not item.get("error") \
        and bool(item.get("response"))


def stratified_sample(items: List[Dict[str, Any]], per_category: int) -> List[Dict[str, Any]]:
    """Evenly spaced items from each category (deterministic, so reruns pick the same items)."""
    by_cat = defaultdict(list)
    for item in items:
        if gradeable(item):
            by_cat[item["category"]].append(item)
    sample = []
    for cat in sorted(by_cat):
        group = by_cat[cat]
        if len(group) <= per_category:
            sample.extend(group)
        else:
            step = len(group) / per_category
            sample.extend(group[int(i * step)] for i in range(per_category))
    return sample


# ---------------------------------------------------------------------------
# Scoring with a resumable cache
# ---------------------------------------------------------------------------

def load_cache(path: Path) -> Dict[tuple, Dict[str, Any]]:
    cache = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            cache[(row["id"], row["metric"])] = row
    return cache


def score(run_dir: Path, per_category: int, metrics_wanted: List[str], model: str,
          base_url: str = GROQ_BASE_URL, limit: Optional[int] = None) -> Path:
    items = [json.loads(l) for l in (run_dir / "items.jsonl").read_text().splitlines()]
    out_dir = run_dir / "deepeval"
    out_dir.mkdir(exist_ok=True)
    cache_path = out_dir / f"{model.replace('/', '_')}.jsonl"
    cache = load_cache(cache_path)
    judge = GroqJudge(model, base_url)
    metrics = make_metrics(judge)

    jobs = []
    for item in items:  # deterministic metric: every item with expected tools
        if "tool_selection" in metrics_wanted and gradeable(item) and item.get("expected_tools"):
            jobs.append((item, "tool_selection"))
    for item in stratified_sample(items, per_category):
        for name in LLM_METRICS:
            if name not in metrics_wanted:
                continue
            if name == "faithfulness" and (not item.get("tool_outputs") or item["category"] in NO_FAITHFULNESS):
                continue
            if name == "correctness" and not item.get("reference"):
                continue
            jobs.append((item, name))
    todo = [(i, m) for i, m in jobs if (i["id"], m) not in cache]
    print(f"{len(jobs)} scores planned, {len(jobs) - len(todo)} cached, {len(todo)} remaining")
    if limit is not None:  # cap LLM work this session (deterministic scores are free)
        free = [j for j in todo if j[1] == "tool_selection"]
        todo = free + [j for j in todo if j[1] != "tool_selection"][:limit]
    print(f"Running {len(todo)} with {judge.get_model_name()}")

    with cache_path.open("a") as cache_file:
        for n, (item, name) in enumerate(todo, 1):
            started = time.perf_counter()
            try:
                if name == "tool_selection":
                    result = tool_selection(item)
                else:
                    metric = metrics[name]
                    metric.measure(build_test_case(item))
                    result = {"score": metric.score, "success": metric.is_successful(), "reason": metric.reason}
                row = {"id": item["id"], "category": item["category"], "metric": name, **result,
                       "judge": "deterministic" if name == "tool_selection" else judge.get_model_name(),
                       "seconds": round(time.perf_counter() - started, 1)}
            except DailyQuotaExhausted as err:
                print(f"\n{err}. {n - 1}/{len(todo)} done this session; rerun the same command to resume.")
                break
            except Exception as err:  # a malformed judge reply shouldn't stop the batch
                row = {"id": item["id"], "category": item["category"], "metric": name, "score": None,
                       "success": None, "reason": f"judge error: {err}"[:300], "judge": judge.get_model_name()}
            cache_file.write(json.dumps(row) + "\n")
            cache_file.flush()
            if name != "tool_selection":
                print(f"  [{n}/{len(todo)}] {item['id']} {name}: {row['score']}")
    print(f"Judge usage this session: {judge.calls} calls, {judge.tokens} tokens")
    return cache_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _mean(values: List[float]) -> Optional[float]:
    return round(statistics.fmean(values), 3) if values else None


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 3 or statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return None
    return round(statistics.correlation(xs, ys), 3)


def report(run_dir: Path, model: str) -> Path:
    items = {i["id"]: i for i in (json.loads(l) for l in (run_dir / "items.jsonl").read_text().splitlines())}
    rows = [r for r in load_cache(run_dir / "deepeval" / f"{model.replace('/', '_')}.jsonl").values()
            if not (r["metric"] == "faithfulness" and r["category"] in NO_FAITHFULNESS)]
    scored = [r for r in rows if r["score"] is not None]
    summary: Dict[str, Any] = {"judge": f"groq/{model}", "run": run_dir.name, "metrics": {}}

    lines = [f"# DeepEval report: {run_dir.name}", "",
             f"Judge: `groq/{model}` (independent of the Gemini model being graded). "
             "Tool selection is deterministic and covers every gradeable item; the LLM metrics "
             "cover a stratified sample.", "",
             "| Metric | Items | Mean score | Pass rate | Threshold |", "|---|---:|---:|---:|---:|"]
    thresholds = {"faithfulness": 0.8, "answer_relevancy": 0.7, "correctness": 0.6, "tool_selection": 1.0}
    for name in ("tool_selection",) + LLM_METRICS:
        group = [r for r in scored if r["metric"] == name]
        if not group:
            continue
        mean = _mean([r["score"] for r in group])
        pass_rate = round(sum(bool(r["success"]) for r in group) / len(group), 3)
        errors = sum(1 for r in rows if r["metric"] == name and r["score"] is None)
        summary["metrics"][name] = {"n": len(group), "mean": mean, "pass_rate": pass_rate, "judge_errors": errors}
        lines.append(f"| {name} | {len(group)} | {mean} | {pass_rate:.0%} | {thresholds[name]} |")

    oos = [i for i in items.values() if not i.get("is_academic") and not i.get("error")]
    if oos:
        refused = sum(1 for i in oos if not i.get("passed_intent_gate"))
        summary["metrics"]["oos_refusal"] = {"n": len(oos), "rate": round(refused / len(oos), 3)}
        lines.append(f"| oos_refusal (deterministic) | {len(oos)} | | {refused / len(oos):.0%} | |")

    lines += ["", "## By category", "", "| Category | " + " | ".join(LLM_METRICS) + " | tool_selection |",
              "|---|" + "---:|" * (len(LLM_METRICS) + 1)]
    for cat in sorted({r["category"] for r in scored}):
        cells = [_mean([r["score"] for r in scored if r["category"] == cat and r["metric"] == m]) for m in
                 LLM_METRICS + ("tool_selection",)]
        lines.append(f"| {cat} | " + " | ".join("" if c is None else str(c) for c in cells) + " |")

    # Judge agreement with the run's own Gemini judge (faithfulness = supported-claim fraction)
    pairs = [(r["score"], items[r["id"]]["grounding"]["faithfulness"]) for r in scored
             if r["metric"] == "faithfulness" and (items[r["id"]].get("grounding") or {}).get("faithfulness") is not None]
    if pairs:
        ours, gemini = [p[0] for p in pairs], [p[1] for p in pairs]
        agree = sum((a >= 0.999) == (b >= 0.999) for a, b in pairs) / len(pairs)
        summary["judge_agreement"] = {"n": len(pairs), "deepeval_mean": _mean(ours), "gemini_judge_mean": _mean(gemini),
                                      "pearson": _pearson(ours, gemini), "fully_supported_agreement": round(agree, 3)}
        lines += ["", "## Agreement with the run's Gemini judge (faithfulness)", "",
                  f"- Items scored by both: {len(pairs)}",
                  f"- Mean: DeepEval/Groq {_mean(ours)} vs. Gemini judge {_mean(gemini)}",
                  f"- Pearson r: {_pearson(ours, gemini)}",
                  f"- Agree on \"every claim supported\": {agree:.0%}",
                  "", "Disagreement here is the signal to check by hand: a same-family judge may be lenient "
                  "toward its own model's phrasing, and a small sample makes r noisy."]

    worst = sorted((r for r in scored if r["metric"] in LLM_METRICS and not r["success"]), key=lambda r: r["score"])[:10]
    if worst:
        lines += ["", "## Lowest-scoring answers", "", "| Item | Category | Metric | Score | Judge's reason |", "|---|---|---|---:|---|"]
        for r in worst:
            reason = (r["reason"] or "").replace("|", "/").replace("\n", " ")[:220]
            lines.append(f"| {r['id']} | {r['category']} | {r['metric']} | {r['score']:.2f} | {reason} |")

    out = run_dir / "deepeval" / "report.md"
    out.write_text("\n".join(lines) + "\n")
    (run_dir / "deepeval" / "metrics.json").write_text(json.dumps(summary, indent=2))
    html_out = write_html_report(run_dir, summary, rows, items, thresholds)
    print(f"Report: {out}\nHTML:   {html_out}")
    return out


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True, help="results directory containing items.jsonl")
    parser.add_argument("--per-category", type=int, default=3, help="items per category for the LLM metrics")
    parser.add_argument("--metrics", default=",".join(("tool_selection",) + LLM_METRICS))
    parser.add_argument("--model", default=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    parser.add_argument("--base-url", default=JUDGE_BASE_URL, help="OpenAI-compatible judge endpoint")
    parser.add_argument("--limit", type=int, default=None, help="max LLM metric scores this session")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run).resolve()
    if not (run_dir / "items.jsonl").exists():
        sys.exit(f"No items.jsonl in {run_dir}")
    if not args.report_only:
        score(run_dir, args.per_category, args.metrics.split(","), args.model, args.base_url, args.limit)
    report(run_dir, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
