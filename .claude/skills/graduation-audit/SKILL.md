---
name: graduation-audit
description: Audit a WPI Business School graduate student's courses against their program's graduation requirements and report what is complete, in progress, and still missing. Use when a student asks "how close am I to graduating", "what do I still need for my MSIT/MBA/MSBA", "have I met the core requirements", or shares a transcript and asks about degree progress.
---

# Graduation audit

Produces a requirement-by-requirement audit for one student and one program,
using the `wpi-adviser` MCP server as the only source of requirement data.

## Inputs to collect

1. **Program** — the exact program the student is enrolled in.
2. **Completed courses** — course codes the student has passed.
3. **Current courses** — course codes in progress this term (kept separate).

If the student shares a transcript, read the course codes from it. Ask for
anything missing instead of guessing.

## Steps

1. **Resolve the program.** Read the `adviser://programs` resource. "MBA" and
   "MBA in Analytics" are different programs with different requirements; if
   the student's wording could mean more than one, ask which one before going on.
   Pass the program's full name (or MSIT / MSBA / FinTech / OSCA) to the tools.

2. **Normalize course codes** to `DEPT NNN` with one space and uppercase
   department (`mis571` → `MIS 571`). Cross-listed codes such as `DS/ECE 577`
   stay as the student wrote them, but list them in the report so the student
   can confirm how they were counted.

3. **Run the audit.** Call `check_degree_progress` with `program`,
   `completed_courses`, and `current_courses`. Do not merge current courses into
   completed ones; the tool reports them separately.

4. **Check the remaining courses.** For each course the audit lists as missing,
   call `get_course` to get credits, offering period, and delivery mode. If
   `get_course` returns null, call `search_courses` once with the code; if that
   also finds nothing, say the course was not found. Do not describe it from memory.

5. **Self-check before answering.**
   - Every requirement in the report came from `check_degree_progress`, not
     from general knowledge of MBA/MS programs.
   - Every course you name is either in the student's list or was returned by a tool.
   - Required specialties and optional specialties (and how many optional ones
     the program needs) match the tool's report.
   If any check fails, fix the report or remove the claim.

## Output format

```
## Graduation audit — <full program name>

**Status:** <Complete / On track (all remaining requirements in progress) / N requirements outstanding>

| Requirement | Type | Status | Counted courses | Still needed |
|---|---|---|---|---|
| <specialty> | Required / Optional | Complete / In progress / Missing | ... | ... |

**Optional specialties:** <k> of <n required> complete.

### Remaining courses
- **<CODE> — <title>** (<credits> cr, <offering period>, <delivery>)

### Things to confirm with your adviser
- <cross-listed or unmatched courses, transfer credit, waivers, petitions>

_Sources: check_degree_progress, get_course (WPI Business School database)._
```

Keep it to the audit. Term-by-term scheduling belongs to the
`course-planning` skill; offer it at the end if the student has courses left.

## Do not

- Do not state GPA, grade, or credit-hour rules unless a tool returned them.
- Do not say the student "will graduate" on a date; report requirement status only.
- Do not treat a course as satisfying a requirement unless the audit counted it.
