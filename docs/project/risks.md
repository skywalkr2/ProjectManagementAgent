# Risks and assumptions

Reviewed at each milestone and at the go/no-go. Likelihood and impact: low, medium, high.

## Risks

| # | Risk | Likelihood | Impact | Response | Status |
|---|---|---|---|---|---|
| R1 | Building the tool takes time the launch needs | high | high | Under 5 owner hours a week; launch slice only; go/no-go on 2026-10-30; November freeze | open |
| R2 | The launch slice isn't ready or trusted in time | medium | low | The launch never depends on it; if it isn't useful by the go/no-go, it waits until after 2026-12-01 | open |
| R3 | Imprint data lost while it lives on one laptop | medium | high | Off-device backup with nag is in the launch slice; export to a private remote | open |
| R4 | Scope keeps growing (it did during design) | high | medium | Design 1.0 baseline; change control in `scope.md`; freeze in November | open |
| R5 | AI output quality or cost isn't good enough for real messages | medium | medium | Nothing goes out without approval; quality signals recorded from day one; budgets; evaluation before switching models | open |
| R6 | Hosted mode on the imprint's public domain exposes the admin area | low (deferred) | high | Not before the publishing pack is in daily use; deploy checks block an unsafe start | deferred |
| R7 | Productization beyond the owner's two uses is untested | medium | low | Accepted: the owner is the first two customers; revisit before building beyond the two packs | accepted |
| R8 | One builder; long-term upkeep | medium | medium | Small core, automated checks, decisions and design kept current | open |
| R9 | Conflict with the owner's employment | low | high | Closed: personal project on the owner's own account; no code, data or systems from work; only ideas; clean-room design and fictional data | closed |

## Assumptions

| # | Assumption | How it's checked |
|---|---|---|
| A1 | The workflow that worked for a workplace PM fits a small imprint's launch | The launch slice on real launch notes and emails before the go/no-go |
| A2 | Contributors are reachable by paste-ready messages; no integration is needed for the launch | Use during the run-up |
| A3 | One AI vendor's API is good enough for the launch slice | Acceptance scenario plus a week of real use |
| A4 | The owner's private workspace can stay local until after the launch | Charter constraint; revisit after 2026-12-01 |
