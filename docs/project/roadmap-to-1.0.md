# Roadmap to 1.0

The working checklist from today to the first public release. Tick items as they finish and add the date. Dates and owner
time come from `schedule.md`; what is in each horizon comes from `scope.md`; the milestones are in `docs/design/13-build-plan.md`.
"1.0" is the first public release, which is version 1 in the plan.

Last updated: 2026-10-12.

## 1. Launch slice (done)

- [x] Built, tested and pushed; CI green on the development branch (2026-10-09).

## 2a. Build on now (decided 2026-10-09; launch-slice copy is commit `49e95e7`)

- [x] People and projects screens: add, edit, rename; remove when nothing refers to them; `cockpit init --you` (2026-10-09).
- [x] Plugin host, plugin API 0.1: reviewed, fixed and merged (2026-10-10).
- [x] Stages: reviewed, fixed and merged; API only so far (2026-10-10).
- [x] Stage screens: Stages view; ready and waiting-for-go rows on Today (2026-10-10).
- [x] Cost control, engine: catalog prices, cached input, routing rules, context fit, escalation, estimates, a go above
  the configured amount, per-run limit, budgets per kind of work (2026-10-10).
- [x] Today: first-run card, assistant state (including the stand-in), Dismiss; one-box hand-in; notes under projects;
  Chasers "To send" / "Waiting on them" with Copy then Mark sent (2026-10-10).
- [x] Cost screens: the go showing the estimate; a spend line in the header (2026-10-10).
- [x] Plugin API 0.2 (decisions, 2026-10-10), see `docs/plugin-api-0.x.md`: data levels, origin and person-only values, unique fields and `find`,
  filtered `list`, `Ref` fields, validators that see the changeset, event kind filters, `record.delete`.
- [x] The define-your-own kit with starting templates; the demo runs on a template (decisions, 2026-10-10).
- [x] Guided install and setup: built screens in the package, one-step install and update, first-run wizard, settings
  screens; agent accounts; ask the assistant about the app; a user guide (2026-10-11).
- [x] **Friends' preview**: packaged install, guided setup, labeled demo, bring-your-own AI, feedback button, download
  (2026-10-11; `docs/install.md`; a tag builds the release).
- [x] Plugin API 0.3 with uploads, previews and person actions (2026-10-11); now 0.3.30, see `docs/plugin-api-0.x.md`.
- [ ] Watchers and lookups (engine and general sources in the core; product connectors as plugins). Done: the engine,
  triage and Auto-closed, folder, feed, calendar (ICS) and mailbox (IMAP) sources, the Sources screen. Waiting on the
  owner: product mail and calendar plugins with their own sign-in.
- [ ] Publishing pack in its own private repository. For the 2026-12-01 launch, a publishing template built with the
  kit is the stretch goal, alongside the manual process.
- Every feature: run on the fictional imprint end to end with desktop and phone screenshots before hand-over; the owner's
  weekly 15-minute try; friction in `ux-notes.md`.

## 2. Owner validation (now to 2026-10-30)

- [ ] Run it locally on the fictional imprint (README, "Try it").
- [ ] Add an AI key, run `cockpit ai test` (every tier answers), then `cockpit evaluate`; choose a model from the report.
- [ ] Set up the private imprint workspace and an off-device backup folder; one backup succeeds.
- [ ] A week of real launch notes and emails through it; does it save time?
- [ ] **Go / no-go on 2026-10-30** (criteria in `schedule.md`). Go: use it through the launch. No-go: parked until after.

## 3. Freeze and launch (2026-10-31 to 2026-12-01)

- [ ] Fixes only on the copy in use, nothing new.
- [ ] Launch on 2026-12-01.

## 3a. Plugin host and document features early (from 2026-10-31, separate branch, about three and a half weeks)

- [x] Plugin host: plugin API 0.x, manifests, registries, plugins working together through interfaces (3.9), one example plugin (2026-10-12).
- [x] Long text with versions and authorship (5.0) (2026-10-11).
- [x] Drafts with prose output; proposed versions and accepting them per passage (6.7) (2026-10-11).
- [ ] Compare view for long text, two-way and three-way (7.2). Routes done (2026-10-11); the screen is in the UX pass.
- [x] Long text formats (`plain`, `markdown`, plugin-registered) dividing text into units; paragraph-anchored drafts; lints computed in code, anchored to passages; lints on drafts count for escalation (6.7, 3.3, 6.16) (2026-10-11).
- [x] Events: `record.changed`, `text.accepted`, and interface events (3.4) (2026-10-12).
- [x] Working copies: hand out for the person's own tools, take back, review (5.0, 3.3) (2026-10-11; screens in the UX pass).
- [x] Stages (6.26) (2026-10-10).
- [x] Cost control: estimates, a go above a set amount, budgets per task kind and per project (6.16) (2026-10-11).
- [x] Independent second opinion, with roles and same-account checks (6.16) (2026-10-12).
- [ ] File channel (6.3). Files, uploads and outputs exist (2026-10-12); the publisher's channel waits for M6.
- [x] Two computers through a synced folder: readable layout by project, lease in the folder, no silent merges, outside edits back for review (5.0) (2026-10-12).
- [x] Plugin developer guide generated from the plugin API, for plugins kept in other repositories (2026-10-11).
- [ ] A sandbox workspace for trying plugins, apart from the launch workspace.

## 4. Retrospective (by 2026-12-11)

- [ ] What helped and what got in the way; lessons into design Part 8.
- [ ] Re-plan version 1 from what the launch slice actually took.

## 5. Version 1 build (from 2026-12-14)

- [ ] **M1–2: rest of the core.** The parts the launch slice trimmed (13.1).
- [ ] **M3: scope and facts.** Scope resolver; facts looked up from configured sources, never asked (6.18, 6.19).
- [ ] **M4: plugin host.** Finish what 3a started: the remaining `1.0` extension points and moving built-ins behind them;
  project language (5.1), declared programs (`requires.tools`), plugin data files (4.12).
- [ ] **M5: watchers and triage.** Inputs arrive on their own instead of being pasted.
- [ ] **M6: records, rendering and the publisher.** Drafts, Waiting to go out with diffs, the publisher; the document
  features come from 3a.
- [ ] **M7: UI shell and settings.** Today as the home queue, first-run setup, the Settings panel, installable web app (Part 7).
- [ ] **M8: publishing pack** in daily use (9.6 to 9.9).
- [ ] **M9: workplace pack** on fictional data (9.1 to 9.5).
- [ ] **Plugin API 1.0** declared: both packs run on it unchanged.

## 6. Publish 1.0

- [ ] Self-check against the private workspace (`cockpit selfcheck --workspace <path>`).
- [ ] Publish as a fresh repository with one starting commit (no development history), under Apache-2.0.
- [ ] Turn on secret scanning.
- [ ] README and docs match what 1.0 does.

## Not in 1.0

Hosted mode and sign-in (Part 11), social, email and newsletter channels, the sales pack (13.3).

## Open items

- [ ] **Provider lessons in version 1** (decisions, "Lessons from switching AI providers"): per-model parameter
  capabilities, agent lock-down test, `sign_in_hint`, automatic restart, first-run notice, probation, canonical form for
  channels, premise checks, `project.add`, person-owned fields, office-file extractors.

- [ ] **Milestone 10 overlap.** `scope.md` puts version 1 at milestones 1 to 9, but lists some milestone 10 items as version 1
  musts: escalation on failure, budgets, native adapters. Cost control (M6) needs budgets. Decide which milestone 10 items
  move into version 1 and update `scope.md` and the build plan to match.

- [ ] **Plugin-supplied labels.** Plugin task kinds and record kinds get their on-screen names from each workspace's
  `ui.yaml` today (`task.<kind>`, `stages.group.<kind>`). A pack should ship its own wording for its kinds.
