# Project charter

## Purpose

Build PM Cockpit: a generic, AI-assisted cockpit that watches a person's sources, drafts updates, questions and action items,
and gives them one screen to review and send. The design is in `docs/design/`.

## End state, beyond 1.0 (owner, 2026-10-14)

1. The core handles everyday project support, as designed.
2. Packs extend it, each useful on its own.
3. A full set of packs, bought together, carries a business requirement to delivery:
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
entry checks), and every step's output is the person's to approve, as for everything else.

## Background

A personal project on the owner's own account. It generalizes ideas from a tool the owner built and runs privately for their
own use. No code, data or systems move between that tool and this project in either direction; only ideas. The design is
clean-room and all committed data is fictional.

## Sponsor, owner and first user

The owner: sponsor, product owner and first user. The **first real deployment is the owner's literary imprint**, in a private
workspace outside this repository, starting with the run-up to its first book launch on **2026-12-01**.

## Objectives and success measures

**By the go/no-go (2026-10-30), the launch slice (`schedule.md`) is useful or it waits:**

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
