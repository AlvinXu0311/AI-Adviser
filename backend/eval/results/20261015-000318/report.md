# Adviser evaluation report

- Run: 2026-10-15T00:03:18 · 127 gold items · errors: 1
- Adviser model: `gemini-3.8-flash` · intent model: `gemini-3.8-flash` · judge: `gemini-3.8-flash`
- Gold set: `/home/alvin/Documents/AI-Adviser/backend/eval/gold_set.jsonl` (answers derived from SQLite; see eval/build_gold_set.py)

## Headline

| Metric | Value |
|---|---|
| Intent macro-F1 | 1.00 |
| Retrieval Recall@5 | 55.2% |
| Tool-selection accuracy | 91.2% |
| Tool-argument accuracy | 100.0% |
| Answer accuracy (exact, SQL gold) | 91.2% |
| Faithfulness (LLM judge) | 96.5% |
| Hallucination rate (answers with ≥1 unsupported claim) | 15.7% |
| Out-of-scope refusal rate | 100.0% |
| pass^3 | 85.0% |
| Latency p50 / p95 | 6.24 s / 14.42 s |

## 1. Components

### Intent classification

Accuracy 100.0% on 126 items · macro-F1 1.00

| Class | Precision | Recall | F1 |
|---|---|---|---|
| academic | 100.0% | 100.0% | 1.00 |
| out of scope | 100.0% | 100.0% | 1.00 |

### Retrieval (search layer, raw question as query)

| Slice | n | Recall@5 | Recall@10 | Context recall | Hit@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|---|---|
| all | 73 | 55.2% | 64.2% | 87.1% | 65.8% | 0.52 | 0.50 |
| course_lookup | 39 | 76.9% | 76.9% | 76.9% | 76.9% | 0.71 | 0.73 |
| program_requirements | 12 | 74.3% | 79.2% | 100.0% | 91.7% | 0.53 | 0.60 |
| specialty_courses | 22 | 6.4% | 33.6% | 98.1% | 31.8% | 0.16 | 0.06 |

### Tool calling

Selection 91.2% (n=102) · agent's own calls only 55.9% · first call correct 60.8% · arguments 100.0% (n=52)

Selection counts the automatic database prefetch as a `business_school_database` call; "agent only" counts just the tools the model chose.

| Category | n | Selection | Agent only | Arguments |
|---|---|---|---|---|
| course_lookup | 39 | 76.9% | 76.9% | 100.0% |
| degree_audit | 18 | 100.0% | 100.0% | 100.0% |
| no_transcript | 5 | 100.0% | 100.0% | – |
| program_requirements | 18 | 100.0% | 22.2% | 100.0% |
| specialty_courses | 22 | 100.0% | 0.0% | – |

## 2. End to end

| Category | n | Answer accuracy | Course-code recall |
|---|---|---|---|
| course_lookup | 39 | 100.0% | 100.0% |
| degree_audit | 18 | 100.0% | 100.0% |
| no_transcript | 5 | 100.0% | – |
| program_requirements | 18 | 100.0% | 100.0% |
| specialty_courses | 22 | 59.1% | 84.9% |
| **all** | 102 | **91.2%** | |

- Faithfulness 96.5% · unsupported-claim rate 4.4% · hallucination rate 15.7% · answer relevancy 4.90/5 (n=102)
- Out-of-scope: refusal rate 100.0% (n=24), 100.0% stopped at the intent gate; academic questions wrongly refused: 0.0%
- Consistency: pass^3 85.0%, pass@3 85.0% on 20 items (an item passes^k only if all k runs are correct)

## 3. Efficiency

| Metric | Value |
|---|---|
| End-to-end latency avg / p50 / p95 / max | 7.28 s / 6.24 s / 14.42 s / 38.20 s |
| Latency when the adviser answers (p50 / p95) | 7.92 s / 14.62 s |
| Intent step p50 / p95 | 1.74 s / 2.65 s |
| Tokens per query (in / out) | 6277 / 607 |
| LLM calls per query | 2.95 |
| Tool calls per adviser task (max) | 2.35 (9) |

## Notes

- Latency is measured in-process (intent agent + LangGraph adviser), without Redis, nginx or SSE overhead, with 4 questions in flight at a time.
- Faithfulness and relevancy are judged by the same model family that answers, which tends to be lenient.
- Retrieval is scored on the raw question passed to the search tool; the agent itself may rewrite the query.
- Failed items are listed in items.jsonl with `answer_check.correct = false`.

## Findings from this run

1. **Most "hallucinations" come from one bug.** `app/api/chat.py` always passes `program_id="msit"`, and the
   adviser input ends with `Program: MSIT`. In 10 of the 16 answers flagged with an unsupported claim, the only such
   claim is "the student is in MSIT". Fixing that should bring the hallucination rate from 15.7% to roughly 6%.
2. **Specialty course lists are the weakest category** (59.1% exact, 84.9% code recall). The model shortens long
   option lists (e.g. q071 Product Management in the MBA lists 2 of 12 courses; q067 AI in Business for MSBA lists
   none of the right ones). These failures are deterministic: q057, q059 and q060 failed all 3 pass^k runs, so
   pass^3 (85%) equals pass@3. The misses are reproducible errors, not randomness.
3. **The agent leans on the database prefetch.** For program and specialty questions the model almost never calls
   `program_search` (agent-only selection 22% / 0%), because `_with_db_prefetch` already injected the program
   structure. Counting the prefetch, selection is 100% for those categories.
4. **Course lookups by "What is the course title of X?"** (9 items) were answered from the prefetch without a
   `smart_course_search` call, so they score as wrong tool selection even though all 9 answers are correct.
   The same 9 raw questions also miss in retrieval (Hit@5 0), which is why course_lookup Recall@5 is 76.9%.
5. **Retrieval ranking for specialties is poor** (Recall@5 6.4%) even though context recall is 98%:
   `program_search` returns the whole program, so the right courses are present but far from the top.
6. **One error**: q097 (out of scope) hit the 6 s intent timeout. In production that request would return an error
   instead of a refusal.
7. **Latency**: p50 6.2 s, p95 14.4 s (in-process, 4 concurrent). The long tail comes from multi-tool questions
   (up to 9 tool calls); the intent step adds about 1.7 s to every request.
