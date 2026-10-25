# DeepEval report: 20261025-174643-live-46c0634-1e4ef7dd

Judge: `groq/openai/gpt-oss-120b` (independent of the Gemini model being graded). Tool selection is deterministic and covers every gradeable item; the LLM metrics cover a stratified sample.

| Metric | Items | Mean score | Pass rate | Threshold |
|---|---:|---:|---:|---:|
| tool_selection | 278 | 0.885 | 88% | 1.0 |
| faithfulness | 6 | 1.0 | 100% | 0.8 |
| answer_relevancy | 9 | 0.699 | 56% | 0.7 |
| correctness | 9 | 0.967 | 100% | 0.6 |
| oos_refusal (deterministic) | 39 | | 100% | |

## By category

| Category | faithfulness | answer_relevancy | correctness | tool_selection |
|---|---:|---:|---:|---:|
| clarification |  | 0.976 | 0.9 |  |
| course_details | 1.0 | 0.411 | 1.0 | 1.0 |
| course_lookup | 1.0 | 0.711 | 1.0 | 0.821 |
| degree_audit |  |  |  | 1.0 |
| instructor_lookup |  |  |  | 0.4 |
| no_transcript |  |  |  | 1.0 |
| paraphrase |  |  |  | 0.7 |
| program_requirements |  |  |  | 1.0 |
| prompt_injection |  |  |  | 1.0 |
| requirement_counts |  |  |  | 1.0 |
| specialty_courses |  |  |  | 1.0 |

## Lowest-scoring answers

| Item | Category | Metric | Score | Judge's reason |
|---|---|---|---:|---|
| q192 | course_details | answer_relevancy | 0.33 | The score is 0.33 because the response focused on location, instructor, credits, and term details, none of which answer whether OBC 505 is online, in‑person, or hybrid, limiting its relevance. |
| q000 | course_lookup | answer_relevancy | 0.33 | The score is 0.33 because the response focused on course code, credits, delivery format, and schedule rather than naming the instructor, making most of the output irrelevant to the question. |
| q179 | course_details | answer_relevancy | 0.40 | The score is 0.40 because the response included unrelated details about instructor info, credit count, and delivery mode, none of which answer when MIS 571 is offered. |
| q166 | course_details | answer_relevancy | 0.50 | The score is 0.50 because the response focused on credit amount, lecture format, and the instructor—none of which answer whether BUS 500 is online, in‑person, or hybrid—so half the answer was irrelevant, preventing a hig |
