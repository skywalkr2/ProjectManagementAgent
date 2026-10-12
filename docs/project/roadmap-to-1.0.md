# Go-forward plan to 1.0

Rewritten on 2026-10-12 after the review (`review-2026-10-12.md`), at the owner's direction.

**The goal:** a baseline that works for a real person with no demo data, then an assistant that learns (phase L), then the
UI finished and out of the way, then
three packs running in the owner's own workspace:
- **the writing pack;**
- **a project management pack:** an AI project manager that knows what is being done, builds schedules and tracks
  action items;
- **the publishing pack.**

The owner hasn't yet seen any pack working.

**How the order was chosen:** each phase makes the next one testable by the owner. The plan holds one stream of work at
a time, and a phase ends when its exit test passes, not when its code is written.

Durations are estimates in working sessions. Dates are set when a phase starts and recorded here.

## Phase 0: the plan and the rules (done 2026-10-12)

- [x] Review: built, missing, and why small errors reached the owner (`review-2026-10-12.md`, `audit-2026-10-12/`).
- [x] This plan; the rules in `CLAUDE.md` ("How work reaches the owner"); a decision recorded.

## Phase A: a baseline that works with no demo data (about 3 sessions)

**Exit test:** on a fresh computer folder, the owner runs one install or update command. They then:
1. make a workspace with no template;
2. add an AI account;
3. sign in to Google;
4. see their recent mail and today's meetings handled by the assistant on Today;
5. hand in a note and see the result;
6. back up.

None of it takes a file edit, a second terminal command or a demo. Automated journey tests cover the same path.

A1. **Demo data off the person's path.**
- [ ] `cockpit init` with no template is the start in the README, `docs/install.md` and the setup guide.
- [ ] The fictional workspaces stay as test fixtures and as the sandbox (`cockpit demo`), named as such.
- [ ] A self-check: a fresh workspace shows no account, source or setting with a problem.
- [ ] One command, `cockpit update`: it pulls, syncs without dropping installed add-ons, installs the web tools and
  builds, then says whether a restart is needed.

A2. **The person's path, fixed where the review found it broken.**
- [ ] **Add-ons install from the screen.** Build the Install button on Add-ons, and install a pack's own libraries
  (round 35). A release names every package it needs with checksums. Install shows what will be added, refuses
  conflicts with the app's own, and Remove takes out only what that pack needed. This is what lets the writing pack
  in.
- [ ] Runs a crash left stuck are queued again on start.
- [ ] The test-only source kind is hidden from "Add a source".
- [ ] Passwords and addresses for the core mailbox and calendar sources are entered on screen and kept like an AI key.
  Today they work only through `env:` or `file:`.
- [ ] Server messages never name a settings file, a key path, `env:` or a command. About 50 of these are listed in
  the audit.
- [ ] Settings that do nothing are wired or removed: `owner_format`, the scheduled export. The near-duplicate threshold
  becomes a setting (design 4.17; the code fixes it at 0.8).
- [ ] **A refresh button on the mailbox** (owner, 2026-10-12): check "Came in" and the mail source now.
- [ ] A divergence between two computers, or a stale lease, is resolved from a screen, not with a command.

A3. **Journey tests.** These are end to end, with a fake AI service and fake mail and calendar services, and nothing
is "ready to test" until they pass:
- [ ] fresh workspace → AI account → hand-in → result on Today;
- [ ] sign in → mail and calendar read → assistant → review on Today;
- [ ] a source added on screen → read → assistant;
- [ ] an add-on installed from the screen → turned on → its screens appear;
- [ ] backup → restore;
- [ ] the acceptance scenario, steps 1–7, all checked as written (step 6 included).

## Phase L: the learning slice (about 6 sessions)

Added on 2026-10-12 after the first design's author reviewed design 1.1 (decisions, "The learning slice"). The write side
of learning is built; this phase builds the read side, so the assistant gets better at each project the more it sees.
Design 6.22.

**Exit test: the assistant doesn't repeat a corrected mistake.**
- **Automated, on every change:** a correction produces a proposal; once kept, it reaches the next similar packet, ranked as
  designed; and the run's knowledge log shows it.
- **On the owner's AI account, started by the owner:** for every fixture pair, the later input comes out right with no
  correction repeated. The day-30 workspace's changesets differ from day 1's in the ways its history justifies.

L1. **Knowledge as records.**
- [ ] Lesson, glossary entry, routing entry and style note records, each with an id, source and evidence, date, trust,
  status and an `applies_to` target. Their ops, with Undo.
- [ ] Rules become records, with `rules.yaml` as the starting set; stage checks read them.
- [ ] Facts gain `key` and `as_of`.

L2. **Every run reads what applies.**
- [ ] The knowledge section in the stable part of every packet: rules, matching lessons, the glossary, routing, style notes.
- [ ] Facts of the input's projects, ranked and cut at a budget, with what was left out said.
- [ ] The `search` round, at most two per run, over facts, past inputs, records and knowledge.
- [ ] The `already-known` lint on questions, outside lookups and reports.
- [ ] The knowledge log on each run.
- [ ] One plugin API call that gives a pack's packets the same section.

L3. **Every correction teaches.**
- [ ] The `learn` task on each signal, batched by default: at most one proposal, or `lesson.update` when a lesson should
  have caught it.
- [ ] Learning from inputs: new terms, "not me, ask X", rerouted questions.
- [ ] Proposals from the person's own words apply at once with Undo; the rest wait for Keep.
- [ ] Duplicates merge when proposed.
- [ ] The repeat-correction signal; the unused-entries list.
- [ ] The corrections recorded before this phase are learned from once.
- [ ] On screen: the Learned line on the correction's card and the Today line (7.18). The rest of 7.18 is laid out in
  phase B.

L4. **Proving it.**
- [ ] Fictional fixture pairs, at least one per kind: a lesson, a glossary term, a routing entry, a style note, and a fact
  that avoids an outside lookup.
- [ ] A month of fictional history for the day-30 scenario.
- [ ] Both run by `cockpit evaluate`.

## Phase B: finish the UI/UX redesign (about 4 sessions)

The design is in Part 7 (7.7, 7.12–7.14); the foundation and shell are built.

**Exit test:** the owner reviews every screen on a laptop and a phone. Checklist items C1–C46 of
`reviews/ui-ux-2026-10/` are marked Done or explained, with screenshots in `reviews/ui-ux-2026-10/after/`.

- [ ] **Today:** the ranked queue (its engine is built), the inspector from 1680px, and the rail. Held items are
  top-level. Review & copy and send back are placed as designed, and the keyboard starts on the queue.
- [ ] **Work:** What changed and Follow-ups as list | detail. Waiting to go out is a designed screen with its empty
  state.
- [ ] **Records:** the Projects table and the People table with detail panes; record pages; forms in drawers. The
  synced folder lives only in Settings.
- [ ] **Settings:** nav | form | help, save bar or autosave with Undo, "Changed · Reset", and pickers for time zone,
  language, money and dates. Appearance has the contrast warning; admin sections sit inside Settings.
- [ ] **Setup guide** as steps | step.
- [ ] **The rest:** the Stages board, the phone review mode, the hand-in drawer, Ask as a side pane on wide screens.
- [ ] **Learning on screen** (7.18): what the assistant knows and what is still unknown, on each project's page; the
  Knowledge screen under Records.
- [ ] Words and accessibility throughout: the microcopy table in the review, and axe in light and dark at four widths.

The journey tests from A3 run against the new screens as they land.

## Phase C: the packs in the owner's workspace (about 9 sessions)

**Exit test:** in the owner's own workspace:
- the writing pack takes a fictional manuscript from import to a built PDF and EPUB the owner approves;
- the project management pack holds the project's plan and builds a schedule from it, and the schedule shows what is
  late or at risk;
- the publishing pack starts a launch for the book, with its plan in the schedule, a listing sheet and prices;
- the hand-offs between the packs work, and each pack also works alone.

C1. **The writing pack, installed and reviewed.**
- [ ] It installs from Add-ons with its libraries (A2).
- [ ] Its two load notes are settled: SVG and TIFF files the workspace doesn't accept yet.
- [ ] Its open questions are answered: 170, a review accepting a group of the assistant's changes at once; 172,
  guide fixes.
- [ ] A host-side review of the pack: what it registers and reaches, its rules, and its tests run against this host.
  It is checked on 2026-10-12 to load and register on plugin API 0.3.55.
- [ ] The owner's walkthrough on a fictional book, with what to change written down.

C2. **The project management pack: started** (owner, 2026-10-12). This is an AI project manager that knows what is
being done, builds schedules and tracks action items.
- [ ] Create its private repository, with a brief and a builder session like the other packs.
- [ ] The core keeps what every kind of work needs: actions with owners, questions, follow-ups, decisions, Today. The
  pack adds planning on top, through ops and the core's records:
  - [ ] **The plan:** goals, phases, deliverables and milestones.
  - [ ] **The schedule:** work items with durations and dependencies, a critical path, dates worked out from the
    dependencies, baselines, and slips against them. Only the person rebaselines.
  - [ ] **Building it with the assistant:** from a brief, notes or another pack's milestones, the assistant drafts a
    plan and a schedule. The person approves it as any change.
  - [ ] **Tracking:** what is late or at risk each day goes to Today, with the action items behind it; a weekly status
    report is drafted for the person to send.
  - [ ] **RAID:** risks, issues, assumptions and decisions, with owners and review dates.
  - [ ] **An interface other packs use** to put their milestones into the schedule (`pm/schedule@1`). The writing pack
    puts in the book's chapters and edits; the publishing pack puts in the launch plan.
- [ ] Design 6.23 (dependencies and baselines) and 6.24 (RAID, risk reviews, escalation suggestions, cadence,
  meeting agendas) move from the core into this pack. This is a design change, recorded in decisions.

C3. **The publishing pack: started.** It doesn't exist yet. Its launch plan goes into the project management pack's
schedule when both are on, and is a plain list of milestones when it is alone.
- [ ] Create its private repository, with a brief and a builder session like the other packs.
- [ ] First version, from design 9.7 and the writing pack's `docs/publishing-pack.md`:
  - the title record;
  - a launch plan from a template, with lead times;
  - contributors;
  - Today lines and panels;
  - the listing sheet per platform and the price calculator, from dated platform data;
  - the AI-disclosure answers filled from the authorship breakdown;
  - the `publishing/manuscript-source@1` hand-off.

C4. **What the packs need from the core.**
- [ ] **The publisher and the file channel.** Approved files are saved or shared after the person approves the exact
  content. Waiting to go out lists them, with a diff where it applies.
- [ ] **Fact lookups** (6.19): published dates are looked up from the configured sources, never asked.
- [ ] Anything else either pack's builder asks for, answered in one weekly round.

## Phase D: owner validation and real use

**Exit test:** the owner's own judgment, on dates the owner sets: a week of real notes, mail and pack work saved
time, nothing went out without approval, and a backup succeeded.

- [ ] The acceptance scenario run by the owner on real material.
- [ ] A week of real use; friction recorded in `ux-notes.md` and fixed in order of cost.
- [ ] Learning on real material (6.22): voice per recipient beyond the first style notes, acronyms checked on every input,
  and a fact's freshness checked before an outward draft, with disagreements between sources recorded as private
  discrepancies to ask about.

## Phase E: the rest of version 1

Order by what protects real data first, then by what the packs ask for:
- [ ] **The governor:** stale-item sweeps, outage handling, the scheduled export with its remote; restore, including a
  single record and a point in time.
- [ ] Scope resolver (6.18), the scheduled rules and lessons review with promotion (6.21), and read-backs (6.7).
  Dependencies, baselines and RAID moved to the project management pack (C2).
- [ ] Native AI adapters and reproducible runs (6.16).
- [ ] **M0, the desktop installer:** no Python, uv, Node or terminal; it updates itself.

## Publish 1.0

- [ ] Self-check against the private workspace (`cockpit selfcheck --workspace <path>`).
- [ ] A fresh repository with one starting commit, under Apache-2.0; secret scanning on.
- [ ] The README and docs match what 1.0 does.

## Not in 1.0

- Hosted mode and sign-in (Part 11).
- Social, email and newsletter channels.
- The sales pack (13.3).
- Licensed (paid) packs: the design is accepted, but whether to charge is the owner's call, after launch.

## Done before this plan

Kept for the record; details are in `docs/decisions.md` and the git history.

**Core and safety:**
- the launch slice;
- people and projects;
- the plugin host and plugin API 0.3.55 with the generated guide and the testing kit;
- stages;
- cost control;
- guided setup and the Settings forms;
- agent accounts;
- ask the assistant.

**Documents and data:**
- long text with versions and authorship;
- drafts, the compare view and working copies;
- independent second opinions;
- interfaces between plugins;
- the synced folder.

**Inputs:**
- watchers, triage and the core folder, feed, calendar and mailbox sources;
- sign-ins that start their sources;
- the Google and Microsoft mail and calendar add-on, in its own repository and listed in the catalog.

**The redesign:** its design, foundation and shell.

**Packs:** the define-your-own kit with templates.
