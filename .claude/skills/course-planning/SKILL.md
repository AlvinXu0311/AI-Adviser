---
name: course-planning
description: Build a term-by-term course plan that gets a WPI Business School graduate student from their current transcript to graduation, respecting remaining requirements, prerequisites, and when courses are offered. Use when a student asks what to take next semester, how to plan their remaining terms, how to finish by a target term, or how to fit a concentration/specialty into their plan.
---

# Course planning

Turns a graduation audit into a semester-by-semester plan. All requirement,
course, and prerequisite data comes from the `wpi-adviser` MCP server.

## Inputs to collect

| Input | Default if the student does not say |
|---|---|
| Program | Ask; required |
| Completed and current courses | Ask; required |
| Target graduation term | Fewest terms that fit the load below |
| Courses per term | 3 |
| Interests / preferred specialties | None; prefer required specialties first |
| Delivery preference (online, hybrid, in person) | No preference |

## Steps

1. **Audit first.** Follow the `graduation-audit` skill's steps 1–3 to resolve
   the program and run `check_degree_progress`. The plan only schedules
   courses that the audit lists as missing (plus electives the student asks for).

2. **Pick the optional specialties.** If the program needs k optional
   specialties and fewer than k are complete, choose the ones that need the
   fewest additional courses, unless the student named a preference. Say which
   ones you picked and why.

3. **Gather course facts.** For every candidate course:
   - `get_course` → credits, offering period, delivery mode.
   - `search_courses` with the code → prerequisites from the catalog text.
   Record "offering period unknown" or "prerequisites not listed" instead of guessing.

4. **Schedule.** Fill terms in order:
   - required-specialty courses before optional ones;
   - a course goes in a term only after all its prerequisites are completed
     or scheduled in an earlier term;
   - respect the offering period when the database gives one;
   - stay within the courses-per-term limit.
   If the target term cannot be met, say which constraint blocks it
   (prerequisite chain, offering period, or load) and give the earliest feasible term.

5. **Self-check the plan before answering.** Go through each scheduled course and confirm:
   - `get_course` or `search_courses` returned it (no invented courses);
   - its prerequisites appear in an earlier term or in the student's completed list;
   - it is not already completed or in progress;
   - together, the planned courses cover every missing requirement from step 1.
   Fix any violation and run the check again. In the output, mention any
   course you moved or swapped during this check.

## Output format

```
## Course plan — <full program name>

**Goal:** finish all requirements by <term> · <n> courses remaining

### <Term 1, e.g. Spring 2027>
| Course | Satisfies | Credits | Delivery | Notes |
|---|---|---|---|---|
| <CODE> — <title> | <specialty> | 3 | Online | prereq: <CODE> ✓ |

### <Term 2> ...

**Why this order:** <1–3 sentences: prerequisite chains, offering periods, specialty choice>

**Open questions:** <unknown offering periods, unlisted prerequisites, waivers to confirm>

_Sources: check_degree_progress, get_course, search_courses. Confirm registration
details with your academic adviser._
```

## Do not

- Do not schedule a course whose prerequisites you could not find without
  noting "prerequisites not listed — confirm with adviser".
- Do not assume a course runs every term.
- Do not pad the plan with electives the student did not ask for.
