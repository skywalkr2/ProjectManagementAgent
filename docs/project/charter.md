# Project charter

## Purpose

Build PM Cockpit: a generic, AI-assisted cockpit that watches a person's sources, drafts updates, questions and action items,
and gives them one screen to review and send. The design is in `docs/design/`.

## End state, beyond 1.0 (owner, 2026-10-14)

**The intent:** to do with this tool what used to take many people and a large budget, and to finish real delivery, not
just produce documents about it. The measure is delivered work that passed its own acceptance, not the volume of output.
The goal is to make business consulting teams unnecessary (owner, 2026-10-14). To do that, the packs must deliver what
clients pay consultants for beyond documents:
1. **Knowing what good looks like:** deep playbooks per field (design 3.8), built on by the workspace's own lessons.
2. **Evidence behind every recommendation:** interviews, data and documents cited, as facts are today.
3. **Alignment:** interview guides, workshop plans, a synthesis of what each person said, and open disagreements put to
   the owner as decisions; the client's own manager runs the room.
4. **Accountability:** every decision, approval and requirement traced to delivery and acceptance.
5. **Results shown:** delivered and accepted work, with the trail behind it.

**The rollout:** first in the real world with one person and one idea; then for full-time teams through the hosted
organization install (design 11.8, owner 2026-10-13).

1. The core handles everyday project support, as designed.
2. Packs extend it, each useful on its own.
3. A full set of packs, bought together, carries a business requirement to delivery:
   - **Idea validation** comes first, when the starting point is an idea: who it is for, the problem it solves, what must
     be true for it to work, the cheapest test of each assumption, the evidence that came back, and a go or no-go before
     money goes into building (owner, 2026-10-14).
   - **Business analysis** turns the requirement into functional requirements, reviewed with the person back and forth
     until validated.
   - Then two packs work from them: **project management** plans the delivery (schedule, plan and the outputs a project
     is tracked with), and **technical design** drafts the technical requirements, user stories and designs.
   - Business analysis and project management check the technical design against the original requirements and their
     exit criteria; once approved it goes to **development**, which plans delivery as a scrum team would, with testing
     built into each sprint and a demo to the end users at each step.
   - This repeats until delivery is confirmed by validated internal test cases and user acceptance testing, and then the
     packs facilitate the **deployment**.

Every hand-off between packs goes through the core (interfaces, requests for another pack's task kinds, stages with
entry checks), and every step's output is the person's to approve, as for everything else. That replaces today's copying
and pasting of outputs between functions by hand.

**How the work itself gets done** (owner, 2026-10-14). Planning and tracking delivery is the project management pack's.
Building is staged:
1. **A build pack to take away:** the approved design (requirements, stories with acceptance criteria, technical design,
   test cases) exported as one bundle a coding agent can be told to build from, in the team's own tools. The bundle
   carries the ids that let the work report back the same way every time (owner, 2026-10-14): every requirement, story
   and test case keeps its id; the bundle's instructions tell the builder to name those ids in branches, commits, pull
   requests and test names, and to keep a progress file in the repository (each story's state and its tests' results,
   by id) in a fixed format. Stage 2's connectors read exactly those, so the view back in the project tool is
   consistent whoever does the building.
2. **The PM sees the whole development process in one place:** read-only connectors to where the work happens (the code
   host, its checks, the issue tracker) bring progress, test results and demos back as inputs, traced to the
   requirements they serve, so the plan, the risks and acceptance update without copying anything.
3. **In the end, everything in one place:** the cockpit drives the building too, which needs its own safety design
   (separate sandboxes, permissions, review of every change, rollback) before it is built.

## Background

A personal project on the owner's own account. It generalizes ideas from a tool the owner built and runs privately for their
own use. No code, data or systems move between that tool and this project in either direction; only ideas. The design is
clean-room and all committed data is fictional.

## Sponsor, owner and first user

The owner: sponsor, product owner and first user. The **first real deployment is the owner's literary imprint**, in a private
workspace outside this repository, starting with the run-up to its first book launch on **2026-12-01**.

## Objectives and success measures

**Set aside (owner, 2026-10-09 and 2026-10-12; confirmed 2026-10-15):** there is no go/no-go date. The 2026-12-01 launch
goes ahead without the tool. The owner tests it after the UI phase (B) and starts real use once the writing pack is
complete (phase C); the order of work is `roadmap-to-1.0.md`. The original criteria are kept below for the record.

**By the go/no-go (2026-10-30), the launch slice (`schedule.md`) is useful or it waits** (set aside, above):

- The milestone 2 acceptance scenario (`schedule.md`) passes on the fictional imprint.
- A week of the owner's real launch notes and emails runs through it, and the owner judges it saved time.
- Nothing went out without approval (guaranteed by design; checked anyway).
- An off-device backup exists and has succeeded.

**For version 1 (after the launch), measured from quality signals (design 6.20):**

| Measure | Target |
|---|---|
| Changesets sent back or undone | under 10% |
| Questions the PM drops or rewords | under 15% |
| PM time on follow-ups | under 30 minutes a day |
| Questions to others answered | median within 3 working days |
| Launch-plan milestones that slip without an at-risk warning on Today at least 7 days earlier | none |
| Messages, posts or pages sent without the PM approving the exact content | none |

## Constraints

- **Owner time:** under 5 hours a week until the launch; the owner directs and reviews, the building is done for them.
- **The launch never depends on the tool.** It helps if it's ready, or it waits until after 2026-12-01.
- **Local only until after the launch:** no hosted mode, no public admin path.
- **Repository hygiene:** no real names, companies, domains or data in the repository; real data lives only in private
  workspaces.

## Stakeholders

| Who | Role | Involvement |
|---|---|---|
| Owner | Sponsor, product owner, first user (publisher) | Decides scope, reviews milestones, runs the private workspace |
| Author of the first design | Subject-matter reviewer | Reviews design changes via `docs/design/CHANGES.md` |
| The imprint's contributors (editor, designer, printer, reviewers, media) | Recipients of messages | Never use the tool; receive only what the owner approves |

## Out of scope (for now)

Hosted deployment, sign-in providers, social media and email integrations, distributor or retailer integrations, the workplace
pack in real use, multi-user. See `scope.md`.
