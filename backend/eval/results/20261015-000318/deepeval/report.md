# DeepEval report: 20261015-000318

Judge: `groq/openai/gpt-oss-120b` (independent of the Gemini model being graded). Tool selection is deterministic and covers every gradeable item; the LLM metrics cover a stratified sample.

| Metric | Items | Mean score | Pass rate | Threshold |
|---|---:|---:|---:|---:|
| tool_selection | 102 | 0.912 | 91% | 1.0 |
| faithfulness | 12 | 0.808 | 75% | 0.8 |
| answer_relevancy | 15 | 0.796 | 73% | 0.7 |
| correctness | 15 | 0.893 | 87% | 0.6 |
| oos_refusal (deterministic) | 24 | | 100% | |

## By category

| Category | faithfulness | answer_relevancy | correctness | tool_selection |
|---|---:|---:|---:|---:|
| course_lookup | 1.0 | 0.75 | 1.0 | 0.769 |
| degree_audit | 0.867 | 0.967 | 1.0 | 1.0 |
| no_transcript |  | 1.0 | 1.0 | 1.0 |
| program_requirements | 0.824 | 0.595 | 1.0 | 1.0 |
| specialty_courses | 0.542 | 0.667 | 0.467 | 1.0 |

## Agreement with the run's Gemini judge (faithfulness)

- Items scored by both: 12
- Mean: DeepEval/Groq 0.808 vs. Gemini judge 0.973
- Pearson r: 0.293
- Agree on "every claim supported": 50%

Disagreement here is the signal to check by hand: a same-family judge may be lenient toward its own model's phrasing, and a small sample makes r noisy.

## Lowest-scoring answers

| Item | Category | Metric | Score | Judge's reason |
|---|---|---|---:|---|
| q071 | specialty_courses | answer_relevancy | 0.00 | The score is 0.00 because the response contained only apologies, a request for rephrasing, and a transcript upload request, none of which answered the question about MBA Product Management courses. |
| q071 | specialty_courses | correctness | 0.00 | The actual output provides no course codes, titles, instructors, credits, or required courses, completely missing the expected list of Product Management MBA courses, thus failing all evaluation steps. |
| q057 | specialty_courses | faithfulness | 0.00 | The score is 0.00 because every listed contradiction is ambiguous—each claim about FinTech Analytics specialties, program details, course requirements, MSIT, or transcript uploads lacks supporting information in the retr |
| q000 | course_lookup | answer_relevancy | 0.25 | The score is 0.25 because the response focused on credit value, delivery method, and offering term rather than identifying the instructor, making most of the answer irrelevant to the question. |
| q045 | program_requirements | answer_relevancy | 0.29 | The score is 0.29 because the response focused on capstone courses, optional specialties, another program's curriculum, and transfer issues rather than listing the core MSBA courses, making most of the content irrelevant |
| q057 | specialty_courses | correctness | 0.50 | The actual output includes several of the expected courses (MIS 520, MIS 587, DS 502, DS 503, DS 541, MIS 502, MIS 571) but omits OIE 559 and MIS 584, so it does not fully list all required courses. It correctly states t |
| q045 | program_requirements | faithfulness | 0.57 | The score is 0.57 because the actual output incorrectly states that all optional specialties have 3 courses, yet the context shows the Artificial Intelligence in Business specialty includes 6 courses, creating a clear co |
| q051 | program_requirements | answer_relevancy | 0.60 | The score is 0.60 because the response included several irrelevant details—capstone requirements, a specific capstone course, a team/innovation course, and optional specialty electives—that do not address the core MSIT c |
| q064 | specialty_courses | faithfulness | 0.62 | The score is 0.62 because the actual output contains contradictions: it claims a difference in course options between the MBA in Analytics and the standard MBA despite no supporting context, it incorrectly labels MKT 500 |
