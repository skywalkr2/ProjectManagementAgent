# What is project-management-only in the core, for phase P

Written by the S5 audit of the core's wording. The core reads as a daily assistant for anyone juggling work: the wording
sheet, the prompts, the playbook's guidance, the user guide and the settings descriptions say "you", "the user" (in
what the assistant is sent) or "the person", never "PM" or "project manager" (`tests/test_wording.py`). What is left is
below: concepts that belong to running a project for others, which still sit in the core because the records and screens
that hold them are shared with everyone's use. Phase P moves each to the project management pack, or makes it optional
for everyone, one item at a time. Nothing here is changed by S5.

## Concepts that are PM-only by their nature

| Item | Where it is now | What phase P does with it |
| --- | --- | --- |
| **Stages and stage cards:** a project's records moving through ordered stages with entry checks and tasks that wait for a go | `engine/stages.py`, the Stages screens (`web/src/components/Stages*.tsx`), the `stage.move` op | The pack declares stages for projects; the core keeps the extension point (it is generic: any pack may declare stages). The core's own screens stop offering stages to a person who has none declared. |
| **What the person tracks:** `steward.tracks` (`dates`, `decisions`, `design`) and the scope rules that decide what a question to someone else may ask | `engine/config/schema.py` (`StewardFile.tracks`), `engine/scope.py`, the packet's "The user tracks" line | Move the setting and the design-quality track to the pack; keep "dates" and "decisions" as the core's defaults, since a person's own promises have both. |
| **Stances that mean managing people:** `manage`, `report_to` (and `watch`) decide what the assistant may draft or ask each person | `PersonStanceOp` in `engine/ops.py`, `engine/scope.py`, the stance picker | Keep `alongside` and `watch` in the core. `manage` and `report_to` stay (a person reports to someone) but their project-team wording and the drafting limits move to the pack. |
| **Project roles:** `run`, `design`, `watch` on a project | `PROJECT_ROLES` in `engine/records.py`, `project.role` | Pack. Without it every project is the person's own. |
| **Project status, phase, priority and target:** the value lists and the "at risk" signal | `engine/defaults/value_lists.yaml` (`project-status`, `project-phase`, `project-priority`), `engine/lists.py` (`projects_at_risk`), `engine/top_priorities.py` (the "At risk" rank), `ProjectKnows` | The lists and the at-risk rank move to the pack; the core keeps `priority` (it ranks the day's to-dos) as an optional list. |
| **Series and programs:** projects inside projects with a shared agenda | `engine/series.py`, `engine/agenda.py` (the agenda storing the series) | Keep projects inside projects in the core (areas need them). The series page and its agenda are the pack's. |
| **Decision follow-on:** a moved date or replaced fact asks "does the plan for it still hold?" | `engine/follow_on.py`, `engine/prompts/follow-on.md` | Pack: it assumes plans tied to dated records. The core keeps the follow-up of a person's own moved promise. |
| **Follow-ups grouped by project** and "waiting on a decision" | `engine/followups.py` (`followups.group.project` in the wording), the Follow-ups tables | Keep by person (everyone chases people); by-project grouping is the pack's view. |
| **The Monday message to whoever the person reports to** | `engine/week_plan.py`, `engine/prompts/monday-message.md` | Stays in the core: anyone may report to someone. Its project-by-project facts are the pack's to add. |
| **Status pages and reports for others:** drafts of what happened for people outside | `engine/outward.py`, the outward lints | Core keeps the lints (every draft to another person needs them); status reports as a kind of work are the pack's. |

## Words that still lean toward projects, left as they are

The core's records are organized by project, with one Personal project made at setup and areas under it (design 6.32), so
"project" remains the name of the container on the Projects screen, in filing ("Filed under a project"), in the Unfiled
line and in the lists of the packet. For a person with only a Personal project the screens never ask anything about
projects. These are structure, not the project-manager's vocabulary, and stay.

## The product name

`app.name` is "PM Cockpit" until phase I renames the product; `tests/test_wording.py` allows that name and nothing else.
