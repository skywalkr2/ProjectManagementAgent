# Risks and assumptions

Reviewed at each phase exit in `roadmap-to-1.0.md`. The go/no-go date and the November freeze were set aside (decisions, 2026-10-12; `charter.md`, `scope.md`), so no response below rests on them. Likelihood and impact: low, medium, high.

## Risks

| # | Risk | Likelihood | Impact | Response | Status |
|---|---|---|---|---|---|
| R1 | Building the tool takes time the launch needs | high | high | Under 5 owner hours a week; one phase at a time, each ending on its exit test in the roadmap, and anything the roadmap defers stays deferred; the owner's tester gate (phase I) holds back outside testers until it is met | open |
| R2 | The launch slice isn't ready or trusted in time | medium | low | The launch never depends on it (the 2026-12-01 launch goes ahead without the tool); the owner decides when real use starts, and the self-check and each phase's exit test must pass before anything is called ready to test | open |
| R3 | Imprint data lost while it lives on one laptop | medium | high | Off-device backup with nag is in the launch slice; export to a private remote | open |
| R4 | Scope keeps growing (it did during design) | high | medium | Design baseline; change control in `scope.md` (a one-line impact note in `docs/decisions.md` for every change); the roadmap's order of work and exit tests; the self-check | open |
| R5 | AI output quality or cost isn't good enough for real messages | medium | medium | Nothing goes out without approval; quality signals recorded from day one; budgets; evaluation before switching models | open |
| R6 | Hosted mode on the imprint's public domain exposes the admin area | low (deferred) | high | Not before the publishing pack is in daily use; deploy checks block an unsafe start | deferred |
| R7 | Productization beyond the owner's two uses is untested | medium | low | Accepted: the owner is the first two customers; revisit before building beyond the two packs | accepted |
| R8 | One builder; long-term upkeep | medium | medium | Small core, automated checks, decisions and design kept current | open |
| R9 | Conflict with the owner's employment | low | high | Closed: personal project on the owner's own account; no code, data or systems from work; only ideas; clean-room design and fictional data | closed |
| R10 | The assistant silently drops a commitment (a promise it missed, or one it let go stale), so a memory product is worse than paper | medium | high | The owner's tester gate (roadmap phase I): outside testers wait until the owner's thresholds for missed and false promises are set before the run. The measures the roadmap names: those thresholds measured with denominators on a held-out set, omissions found by an independent reading of a consented sample, a visible coverage line (what was read, when, and what wasn't) so "nothing needs you" never reads as "couldn't check", a cheap way for the person to add a missed promise with omissions counted, no silent close of a promise (every resolution is a proposal with its evidence), and the week of the owner's own measured use that ends phase S. Not yet in force: the thresholds are an open owner decision | open |
| R11 | The computer asleep or off the network reads as a failure and uses up retries (designer, 2026-10-19) | high | medium | Design 6.32: an outage is not a failure; work waits for the network; a run that did no work isn't an attempt and costs nothing against the request. Built in phase S1 | open |
| R12 | Renames detach links: records joined by display names drift apart silently (designer, 2026-10-19) | medium | high | Records join by id, never by a display name (design 5.1, 6.32); anything that names a record to follow holds its id | open |
| R13 | Rules close things without the person seeing them (designer, 2026-10-19) | medium | high | Every unseen close is counted and reviewable ("silent closes", design 6.32), and is one of the gate's measures | open |
| R14 | Testers connect their employer's mailbox, against their employer's rules on copying work mail into a personal tool and outside AI accounts (designer, 2026-10-19) | high | high | The tester invitation says personal mail, or work mail only with the employer's OK; the "administrator approval required" screen is explained, not worked around | open |
| R15 | A command-line agent runs under a sign-in nobody chose (borrowed from another tool), so work goes through the wrong account, its allowance and its data settings (designer, 2026-10-19) | medium | high | The account check reports who each agent runs as; a change or a level mismatch is a Today line (roadmap S1-3, design 6.16). Built, `tests/test_agent_identity.py`; still open until an owner's live check shows each program's own sign-in command answers as its preset says (only one preset carries a command, the others say "can't tell") | open |

## Assumptions

| # | Assumption | How it's checked |
|---|---|---|
| A1 | The workflow that worked for a workplace PM fits a small imprint's launch | The launch slice on real launch notes and emails, in the owner's own use (roadmap phase S's measured week) |
| A2 | Contributors are reachable by paste-ready messages; no integration is needed for the launch | Use during the run-up |
| A3 | One AI vendor's API is good enough for the launch slice | Acceptance scenario plus a week of real use |
| A4 | The owner's private workspace can stay local until after the launch | Charter constraint; revisit after 2026-12-01 |
