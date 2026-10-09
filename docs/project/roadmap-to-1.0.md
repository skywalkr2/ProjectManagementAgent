# Roadmap to 1.0

The working checklist from today to the first public release. Tick items as they finish and add the date. Dates and owner
time come from `schedule.md`; what is in each horizon comes from `scope.md`; the milestones are in `docs/design/13-build-plan.md`.
"1.0" is the first public release, which is version 1 in the plan.

Last updated: 2026-10-09.

## 1. Launch slice (done)

- [x] Built, tested and pushed; CI green on the development branch (2026-10-09).

## 2. Owner validation (now to 2026-10-30)

- [ ] Run it locally on the fictional imprint (README, "Try it").
- [ ] Add an AI key and run `cockpit evaluate`; choose a model from the report.
- [ ] Set up the private imprint workspace and an off-device backup folder; one backup succeeds.
- [ ] A week of real launch notes and emails through it; does it save time?
- [ ] **Go / no-go on 2026-10-30** (criteria in `schedule.md`). Go: use it through the launch. No-go: parked until after.

## 3. Freeze and launch (2026-10-31 to 2026-12-01)

- [ ] Fixes only on the copy in use, nothing new.
- [ ] Launch on 2026-12-01.

## 3a. Plugin host and document features early (from 2026-10-31, separate branch, about two weeks)

- [ ] Minimal plugin host: plugin API 0.x, manifests, registries, plugins working together (3.9), one example plugin.
- [ ] Long text with versions and authorship (5.0).
- [ ] Drafts with prose output (6.7).
- [ ] Stages (6.26).
- [ ] Cost control: estimates, a go above a set amount, budgets per task kind and per record (6.16).
- [ ] Independent second opinion (6.16).
- [ ] File channel (6.3).
- [ ] Plugin developer guide generated from the plugin API, for plugins kept in other repositories.
- [ ] A sandbox workspace for trying plugins, apart from the launch workspace.

## 4. Retrospective (by 2026-12-11)

- [ ] What helped and what got in the way; lessons into design Part 8.
- [ ] Re-plan version 1 from what the launch slice actually took.

## 5. Version 1 build (from 2026-12-14)

- [ ] **M1–2: rest of the core.** The parts the launch slice trimmed (13.1).
- [ ] **M3: scope and facts.** Scope resolver; facts looked up from configured sources, never asked (6.18, 6.19).
- [ ] **M4: plugin host.** Finish what 3a started: the remaining `1.0` extension points and moving built-ins behind them.
- [ ] **M5: watchers and triage.** Inputs arrive on their own instead of being pasted.
- [ ] **M6: records, rendering and the publisher.** Drafts, Waiting to go out with diffs, the publisher; the document
  features come from 3a.
- [ ] **M7: UI shell and settings.** Today as the home queue, first-run setup, the Settings panel, installable web app (Part 7).
- [ ] **M8: publishing pack** in daily use (9.6 to 9.9).
- [ ] **M9: workplace pack** on fictional data (9.1 to 9.5).
- [ ] **Plugin API 1.0** declared: both packs run on it unchanged.

## 6. Publish 1.0

- [ ] Self-check against the private workspace (`cockpit selfcheck --workspace <path>`).
- [ ] Publish as a fresh repository with one starting commit (no development history), under AGPL-3.0.
- [ ] Turn on secret scanning.
- [ ] README and docs match what 1.0 does.

## Not in 1.0

Hosted mode and sign-in (Part 11), social, email and newsletter channels, the sales pack (13.3).

## Open items

- [ ] **Milestone 10 overlap.** `scope.md` puts version 1 at milestones 1 to 9, but lists some milestone 10 items as version 1
  musts: escalation on failure, budgets, native adapters. Cost control (M6) needs budgets. Decide which milestone 10 items
  move into version 1 and update `scope.md` and the build plan to match.
