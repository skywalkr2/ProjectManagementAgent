# Product decisions

Dated entries: what was decided, who decided, why. Newest first. Decisions about one deployment go in that workspace's own
`docs/decisions.md`, not here.

## 2026-10-09: Real use starts with the publishing pack

**Decided by:** project owner.

**What:** No real data goes into the cockpit until the publishing pack is ready; all testing is on fictional data. The
2026-10-30 go/no-go and the November freeze no longer apply, and the 2026-12-01 launch goes ahead without the tool. Build
order from now: (1) the plugin host (brief in `docs/project/next-task.md`); (2) what the publishing pack needs from the core:
stages, dependencies and baselines, the file channel, cost control; (3) the publishing pack; (4) Ask the assistant and the
remaining document features.

**Impact:** real use moves from the launch run-up to after the publishing pack; Ask the assistant moves after it.

## 2026-10-09: Build on now; the launch slice was too thin to validate

**Decided by:** project owner, after trying the launch slice.

**What:** Building continues now instead of waiting for 2026-10-31, in this order: (1) people and projects screens, so a
real workspace can be set up without editing files; (2) "Ask the assistant" for drafting on request (6.25); (3) the early
branch work (plugin host, document features, synced folder, developer guide). The launch-slice copy for the launch is commit
`49e95e7`; the owner runs that copy for real launch work if newer builds are unsettled. The settings screen for AI accounts
waits for the automatic restart (6.14), since AI settings changed from the browser need it; `cockpit ai test` covers setup
until then.

**Why:** In real use the slice could not be validated: there was no way to set up the imprint's people and projects without
editing data files, and the first thing the owner asked for (drafting an email) was not built.

**Impact:** the go/no-go on 2026-10-30 judges whatever is built by then; the November freeze applies to the copy in use, not to
development. Owner time unchanged.

## 2026-10-09: Lessons from switching AI providers

**Decided by:** project owner, from the owner's experience switching the AI provider in a private tool.

**What** (design 6.16, 6.14, 6.13, 6.3, 6.7, 3.3, 6.2):
- **No silent provider:** no default account; a tier naming a missing account is a config error; an empty tier makes its
  work wait with the reason. The first run on a new account is shown as such.
- **Smoke test on every change** (`cockpit ai test`): one live call per tier and account with each task's exact parameters;
  agent adapters also get a lock-down test; models declare the parameters they accept and the self-check rejects a tier
  whose model can't take them.
- **Errors read in one place:** only the adapter's `classify_error()` reads vendor error text; a sign-in failure becomes a
  question to the PM with the adapter's `sign_in_hint()`.
- **Changed settings or code under a running process:** no new job starts on old code with new config; the process restarts
  (the launch slice pauses new work and asks for a restart).
- **Canonical form for outside systems:** channels normalize values as the system stores them; after a publish the target is
  pulled again, and a remaining difference is an automation problem, not a draft.
- **Check the premise first:** local records before outside lookups; "can't do" must name what it checked; missing targets
  become a question to the PM; a PM's note is an instruction, and an identical answer after a send-back is refused.
- **Real gaps:** `project.add`, person-owned fields the assistant can't set, and text extractors for office files (spreadsheet
  comments, presentation tables and speaker notes), with unsupported types flagged once.
- **Probation for a new account:** its work always waits for review for `ai.probation.runs` runs per task kind, and the PM's
  Looks good and Send back count toward its score.

Classified as concepts in the core, with two settings (`ai.probation.runs`, and the per-model parameter capabilities in the
adapter) and new evaluation data (a request naming items that don't exist).

**Impact:** in the launch slice now (about a day, done): no default account and config errors for missing ones,
`cockpit ai test` with a start-up notice when untested, pausing work when settings or code change under the server, refusing an
identical answer after a send-back, and the new evaluation case. The rest is version 1 work, listed in the roadmap's open
items; where the adapter items land depends on the open milestone 10 decision. No owner time beyond running
`cockpit ai test` after adding a key.

## 2026-10-09: Long text formats divide text into units

**Decided by:** project owner, answering a question from a plugin kept in another repository.

**What:** Each `long_text` field names its format. The core ships `plain` and `markdown`; plugins can register a text format
(3.3) whose `units(text) -> spans` says where units start and end and which are atomic. Anchors, authorship, per-passage review
and lint anchors all work in units, and a core invariant refuses a draft that splits or merges an atomic unit.

**Why:** Splitting on blank lines breaks fenced blocks, multi-paragraph footnotes and poems; every pack with structured prose
would otherwise re-check this in its own validators.

**Impact:** about half a day on the early branch, with paragraph anchors. No owner time.

## 2026-10-09: Draft checks, plugin lints, project language, tools, plugin data, text events

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Paragraph anchors** (6.7): revising tasks can ask for anchored drafts; the core checks every base paragraph is accounted
  for, strips the markers before storing and keeps the paragraph map for review and authorship.
- **Lints in code** (3.3, 4.17): a lint extension point whose problems point to passages; guidance goes back per passage and
  shows in the compare view.
- **Lints on drafts** (6.16): for a draft or proposed version, a `return` lint still failing counts as "would be held", so it
  gets the escalation re-run, then stays pending with its findings; `warn` only shows.
- **Project language** (5.1, 4.6): a project can override the workspace locale for lints, spelling, dates and drafting.
- **Declared programs** (3.2, 3.5): `requires.tools`, run only through the plugin API, probed on enable and by the
  self-check; a missing optional tool turns off only its features.
- **Plugin data files** (4.12): `<workspace>/plugin-data/<plugin>/` laid over shipped data, versioned and synced.
- **Events** (3.4): `record.changed` carries kind, id, fields, version and op; a new `text.accepted` event.

**Why:** Each is needed by any pack that drafts long text or ships its own data, not by one plugin; deciding them before the
plugin API is frozen avoids a breaking change later.

**Impact:** anchors, code lints, lints on drafts and the events add about two days to the early branch (from 2026-10-31);
project language, declared programs and plugin data files land in version 1 milestone 4. No owner time.

## 2026-10-09: Working copies, a compare view, and validators as invariants

**Decided by:** project owner, answering requests from a plugin kept in another repository.

**What:**
- **Working copies** (design 5.0): a plugin can register a working-copy format (3.3) to hand a `long_text` field out as a file
  for the person's own tools and take it back deterministically; the hand-back becomes a `text.propose` held for review,
  three-way when the base moved, never merged silently.
- **`text.propose` and `text.accept`** (6.7): the person's outside work waits for review like an assistant draft; accepting
  takes per-passage choices and writes one version with authorship per passage. Plain files edited in the synced folder use
  the same path.
- **A compare view** (7.2): two-way and three-way review of `long_text` versions that any declarative panel can use.
- **Validators:** an op validator's refusal counts as an invariant failure for the fix round and escalation (6.16), so
  validators must be deterministic; judgment calls are lints.

**Why:** Long documents are written in the tools people already use; the cockpit is where they review and approve. Without a
core path, every plugin would build its own hand-back, diff and merge.

**Impact:** about three days more on the early branch (from 2026-10-31), which now runs about three and a half weeks. No owner
time. Nothing changes in the launch slice.

## 2026-10-09: Synced folder details and the manuscript contract

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Nested projects:** `Project` gets an optional parent; a child project's folder sits inside its parent's (a series and its
  titles, a program and its projects).
- **Sources travel:** every source (original file and extracted text) goes into its project's folder in the synced folder,
  so evidence resolves on either computer; sources above a configured data level are encrypted or left out.
- **Own files:** the cockpit records the hash of every file it writes to the folder and ignores matching files when watching;
  outputs go to each project's `outputs/` folder, and an output changed outside asks "rebuild or keep", never counts as an edit.
- **Authorship in three kinds:** written by the person, drafted by the assistant, the person's text changed by the assistant.
- **`publishing/manuscript-source@1`:** fields, events, optional task kinds and the publishing pack's behavior (design 9.7).

**Why:** Handover is only safe if the folder really holds everything; disclosure rules treat drafting and editing
differently; a finished manuscript should start a launch without retyping, from any plugin.

**Impact:** about a day more on the synced folder work in the early branch; the interface lands with the publishing pack
(milestone 8). Nothing changes in the launch slice.

## 2026-10-09: Two computers through a synced folder

**Decided by:** project owner, after a review from a plugin kept in another repository.

**What:** One workspace can be handed between computers through a file-sync folder (design 5.0, 4.15 `sync`). The database
and git history stay on each computer's local disk; the synced folder holds a complete, readable export laid out one folder
per project, written atomically after every changeset; the lease lives in the folder; diverged histories are never merged
silently; outside edits come back as changes to review. Sharing one project between different workspaces is left for later.

**Why:** Long documents need to be readable outside the cockpit and work must continue on a second computer, but file-by-file
syncing corrupts live databases and git repositories. A per-project exchange between separate installs was considered and
rejected for now: ids and people are per workspace, so a project loaded into another install would collide.

**Impact:** about four days of build time, added to the early branch after the document features (from 2026-10-31). No
owner time. Nothing changes in the launch slice.

## 2026-10-09: Plugin host and document features built early, beside the freeze

**Decided by:** project owner.

**What:** From 2026-10-31, on a separate development branch, ahead of milestones 3, 5 and 7:

1. A minimal plugin host (milestone 4): plugin API 0.x, manifests, registries, plugins working together (3.9), one example
   plugin.
2. The core features for document-heavy packs (from milestone 6): long text with versions and authorship (5.0), drafts with
   prose output (6.7), stages (6.26), cost control with estimates, a go above a set amount and budgets per task kind and per
   record (6.16), the independent second opinion (6.16), and the file channel (6.3).
3. A plugin developer guide generated from the plugin API: every extension point, op, event and interface schema, so a plugin
   kept in another repository can be built against it.

The copy the owner uses for the launch stays frozen (fixes only), whatever the go/no-go outcome.

**Why:** The owner wants to build and try plugins during the launch run-up, and plugins kept in other repositories need real,
tested contracts to build against, not a spec that changes once it meets code.

**Impact:** changes the build order only; about two weeks of build time, no owner time required (trying plugins is optional
and never ahead of the launch). The plugin API stays 0.x and may change until both bundled packs run on it.

## 2026-10-09: Plugins work together through the core

**Decided by:** project owner.

**What:** Plugins cooperate in four ways, all through the core (design 3.9): shared core records (a launch is one project
that the publishing pack and a social media pack both link to), versioned interfaces a plugin provides and others use (required or
optional), event subscriptions (now a `1.0` extension point, no longer planned), and requests for another plugin's task
kinds. Plugins still never import each other. Each pack works alone; optional interfaces add features when both are enabled.
CI tests each pack alone, each pair sharing an interface, and the core with none.

**Why:** Some work spans packs (a launch and its announcements, a won deal and its delivery); without a contract between them
the PM would retype everything and the packs would grow hidden dependencies on each other's internals.

**Impact:** adds work to version 1 milestone 4 (the plugin host; a few days of build time), before the plugin API is frozen.
Nothing changes in the launch slice.

## 2026-10-09: Core features for document-heavy packs

**Decided by:** project owner, after checking the candidate packs against the core.

**What:** Six generic features join the core design, in version 1 (milestone 6), before the plugin API is frozen:

- **Long text** (5.0): prose fields stored once per version by hash, with authorship by passage, instead of full copies in the
  ledger; needed before real data exists, because changing the ledger format later is a migration.
- **Drafts and prose output** (6.7): drafting tasks produce a `text.draft` the person reviews; drafts are not claims, so they
  are not held to the evidence rule, but checkable facts inside them are.
- **File channel** (6.3): approved content saved to a configured folder, beside the clipboard.
- **Stages** (6.26, 4.21): one mechanism for work that moves through steps, replacing per-pack stage fields; the publishing
  pack's titles use it first.
- **Independent second opinion** (6.16): a review on a different account from the one that wrote the work.
- **Cost control** (6.16, 4.8): estimates before a run, a go for anything above `budgets.confirm_above_usd` (spending money is
  irreversible, so it confirms like sending does, 7.6), budgets per task kind and per record, spend shown by pack, task kind and
  record. Drafting long documents can cost the person real money; it must never happen without their choice.

**Impact:** adds work to version 1 milestone 6 (about a week of build time; no owner time beyond reading the design). Nothing
changes in the launch slice. The sales pack stays in the Later horizon.

## 2026-10-09: Sales pack recorded as a candidate

**Decided by:** project owner.

**What:** A future sales pack is recorded in design 13.3: business-to-business sales of installed services (accounts,
opportunities, proposals, SOWs, contracts, regulatory requirements as workspace data).

**Impact:** none on the launch slice or version 1; it is in the Later horizon.

## 2026-10-09: License changed to Apache-2.0

**Decided by:** project owner.

**What:** The product is licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`, SPDX `Apache-2.0`), replacing the
AGPL-3.0 chosen earlier the same day.

**Why:** The goal is that people can use it at their companies. Many companies' open-source approval processes restrict or
ban the AGPL, while Apache-2.0 is widely approved. The owner wants attribution (the copyright notice and `NOTICE` must be
kept) and patent protection (an explicit patent grant from every contributor, ending for anyone who sues over patents in the
project); Apache-2.0 gives both. Accepted trade-off: changed versions, including ones run as a service, need not be shared.

**Impact:** none on scope or schedule. Dependencies stay compatible (all are MIT, BSD, Apache-2.0, MPL-2.0 or PSF).

## 2026-10-09: License is AGPL-3.0 (superseded the same day by Apache-2.0)

**Decided by:** project owner.

**What:** The product is licensed under the GNU Affero General Public License v3.0 only (`LICENSE`, SPDX `AGPL-3.0-only`).

**Why:** The product is meant to be run hosted as well as locally. The AGPL keeps changed versions open when they are offered
to others as a network service, not only when they are distributed.

**Impact:** none on scope or schedule. Any dependency added later must be compatible with the AGPL.

## 2026-10-09: Launch slice implementation choices

**Decided by:** built to the design; open for the project owner's review.

- **Facts are their own record kind** (`FACT-n`), not notes with a flag, so they can be looked up and undone on their own.
- **Refusal is per item:** a refused item is dropped and named; the rest of the assistant's work for that input applies.
- **Inputs longer than the limit wait for the PM** instead of being split (splitting is version 1).
- **Pasted text stays local:** a workspace's `sources/` folder is not committed; backups carry it with the database.
- **One database connection per thread,** so a reader never sees another thread's unfinished write.
- **A missing key is its own error** ("the key wasn't found"), apart from a key the vendor refused.
- **"Who is this?" and "Pick an owner" are answered on the item that waits** (What changed), not repeated in Follow-ups; a
  change with an unanswered question stays under Needs attention after Looks good.
- **Mark sent can be undone,** like every other reversible action.
- **`config/ui.yaml`** holds wording overrides, shortcut keys, the one-column width and how long toasts stay.
- **The UI uses system fonts,** loads nothing from elsewhere, and its content policy allows inline styles only for two fixed
  rules of the component library, by hash. People are picked with the browser's own list control, which works best on phones.
- **`cockpit evaluate --ai-config`** scores the PM's own accounts on the fictional cases without copying real data anywhere.
- **Browser tests** run against a test server whose stand-in AI gives each case's ideal answer, so they check the UI and the
  pipeline, not a model.

**Impact:** none on scope or schedule; all within the launch slice.

## 2026-10-09: UI review changes

**Decided by:** project owner, after a UI/UX and React review.

- **A queue, not a dashboard:** Today is the home screen, with one ranked list of things to do; panels are filtered views
  (version 1; the launch slice keeps a single column with What changed and Follow-ups).
- **One primary action per row** with the rest in a menu, and a **wording sheet** so internal terms never reach the screen.
- **Undo toasts instead of confirmations** for anything reversible; only send, publish and post confirm.
- **Keyboard first and phone friendly:** review shortcuts, one column on narrow screens, phone-critical tasks first class.
- **Edit in place before approving; evidence shown on every claim;** details by expanding rows, not tooltips; new items never
  push rows around.
- **First-run setup, real settings UX and WCAG 2.2 AA** accessibility.
- **Front-end architecture:** TanStack Query with server-sent events from the event bus, a TypeScript client generated from
  OpenAPI, React Aria Components, CSS variables for theming, a string table, sanitized rendering with real link domains, strict
  content policy, Playwright with axe.

**Impact:** launch slice gains the UI foundations (about one to two days of build time, no owner time); Today as the queue,
first run, settings UX, side-by-side diffs, virtualization and phone approval flows land in version 1 (milestone 7). Delays
nothing.

## 2026-10-09: AI review changes

**Decided by:** project owner, after an AI systems review.

Launch slice (impact: about a day of build time; owner time is reading one evaluation report; delays nothing else):
- **Evidence on claims:** ops that assert something quote the exact words from a cited source; the quote must be there
  (invariant) and should fit the target (`evidence-fit` lint). Why: with records by id, the dangerous error is a real but wrong
  target; evidence exposes it, gives an audit trail and makes injection harder.
- **Per-task op lists and small schemas, plus deterministic JSON repair, and parameters per task kind.** Why: large schemas
  degrade cheaper models and weak structured-output endpoints.
- **First evaluation set in the launch slice**, deterministic scoring, several runs per case, comparing a low-cost model with a
  stronger one. Why: the model choice should rest on evidence, especially a low-cost one.
- **Provenance everywhere; lessons from inputs are proposed until the PM accepts them;** untrusted-derived glossary meanings are
  shown as data. Why: lessons and glossary entries reach every later packet, which made them a place for injected instructions
  to persist.
- **Input cleaning and one input per call.** Why: quoted history and signatures waste tokens and create duplicate actions;
  several inputs in one call lower accuracy.

Version 1:
- **Escalation on failure** to a stronger tier on deterministic signals only.
- **Three-layer cache layout** with a frozen batch prefix and no volatile values in it.
- **Reproducible runs:** packet fingerprint, versions, parameters, model as served, upstream host; `cockpit replay`; pinned
  aggregator hosts.
- **Budget defaults lowered** to $0.25 a run, $2 a day, $30 a month, warning at 80% (applies from the launch slice).

## 2026-10-09: No code fixer in the product

**Decided by:** project owner.

**What:** The AI code fixer is removed from the product entirely, in every horizon. The product never writes or applies changes
to its own code or to a workspace's plugins. Automation problems are recorded and explained; a problem the PM wants looked at,
or a request no op can do, becomes a report (`dev.request`, now an outbound op) that the PM approves and sends to the
maintainers through a configured route (clipboard by default). Requests about other projects' code remain handoffs. The
`code-fix` tier, the `fix` task kind, `fixer` config, the merge-on-Apply machinery and proposed-fix UI are gone; the "Fix it"
button becomes "Draft a report".

**Why:** The fixer was something the owner wanted for their own development, not something people installing the product should
have: an AI changing installed code can break installations in ways their owners can't diagnose. Development happens in this
repository with the developer's own tools, outside any installation. **Impact:** removes a milestone 11 feature; simplifies
the core and the security model. Supersedes the fixer parts of the earlier entries ("Fixes merge on Apply", "The fixer changes
the workspace, not the product", "A code fix is the last resort"), whose lessons still apply to any developer tool built later.

## 2026-10-09: Launch slice uses only the OpenAI-compatible adapter

**Decided by:** project owner.

**What:** The launch slice builds one AI adapter, `openai-compatible`, which works with a key from most vendors (including
low-cost ones), aggregators and local model servers. Native adapters for vendors with their own API format move to version 1
(milestone 10). **Impact:** less work before the go/no-go; any vendor is still reachable at launch, directly or through an
aggregator. Delays nothing.

## 2026-10-09: The PM's own AI accounts, any vendor or aggregator

**Decided by:** project owner.

**What:** The AI layer is built around the PM's own accounts. Provider kinds: native vendor APIs (`anthropic`, `openai`
adapters, more as plugins), any OpenAI-compatible endpoint through one generic adapter (many vendors such as xAI, inference
hosts, local model servers), aggregators (`openrouter`, with its catalog and routing options such as refusing providers that
collect data), and command-line agents signed in as the PM. Capabilities and prices are per model, from each provider's catalog
(`models()`), with config overrides. Settings has an Add account flow (keychain for the key, Test, model list, tier choice,
data level starting at `open`, evaluation). Fallbacks may cross accounts and vendors.

**Why:** People want to use the accounts they already pay for, and aggregators reach many vendors with one key; per-adapter
capabilities can't describe an aggregator's hundreds of models. **Impact:** launch slice uses `openai-compatible` plus one native
adapter on the owner's key (no extra work: one adapter was planned, and the generic one covers most vendors); the aggregator
adapter, catalog and Add account flow land in version 1 (milestone 10). Delays nothing.

## 2026-10-09: Playbooks, ask the assistant, and project management support

**Decided by:** project owner.

- **Positioning:** a project management assistant, not a PMP replacement or a methodology tool (design 1.5).
- **Playbooks** (3.8): the core ships best-practice guidance for project support and each pack for its field, as guidance
  files, default rules, checklists, glossary seeds, lints and evaluation cases. The workspace's rules override entries by id
  (`config/playbooks.yaml`). Playbooks are scanned like code and change only by release; good workspace rules can be proposed
  upstream. Impact: core playbook first version in the launch slice (it is the guidance milestone 2's notes task needs anyway,
  organized as a playbook); publishing playbook with the publishing pack in version 1. Delays nothing.
- **Ask the assistant** (6.25): ad hoc requests answered from the records with the playbooks, so one-off PMP work doesn't need
  built-in features. Impact: version 1, should.
- **Project management support** (6.24), from the PMP review, accepted into the design now because adding them after the data
  model and screens exist would cost a migration: project issues and assumptions, optional risk fields and reviews
  (`config/raid.yaml`), one suggested escalation for long-unanswered questions, communication cadence on people, meeting
  agendas per attendee. The automation `Issue` record is renamed `Problem` so "issue" keeps its project meaning. Impact:
  version 1, could (the rename is a must, being only a name). Delays nothing in the launch slice.

## 2026-10-09: Project plan, first user and design 1.0 baseline

**Decided by:** project owner, after a project management review.

- **No employer involvement.** This is a personal project on the owner's own account, generalizing ideas from a private tool
  the owner built for their own use. No code, data or systems move between them; only ideas. Recorded as risk R9, closed.
- **First real user: the owner's literary imprint**, in a private workspace, starting with its first book launch on
  2026-12-01. The publishing pack moves to first in the build order (milestone 8); the workplace pack becomes the reference
  pack on fictional data (milestone 9); the personal-projects pack drops out of the plan (it stays as an example in Part 3).
  `demo-b` becomes a fictional small imprint.
- **Launch-safe schedule:** under 5 owner hours a week; a trimmed launch slice of milestones 1 and 2 by 2026-10-30; a go/no-go
  that day; a November freeze; the launch never depends on the tool (`docs/project/schedule.md`).
- **Dependencies and baselines join the core** (6.23): a launch is a chain of lead times, and slips need a baseline to measure
  against. Impact: version 1, must; not in the launch slice. Resetting a baseline is a system op.
- **Design 1.0 is the scope baseline.** From here, changes need a one-line impact note in this log (`docs/project/scope.md`).
  The other PMP suggestions (escalation, communications plan, agendas, risk scoring, PM issues and assumptions) wait there as
  candidate changes.

## 2026-10-09: Packet layout and read-backs, second round with the first design's author

**Decided by:** project owner, on the second-round answers from the first design's author.

- **Packets: stable first, request last.** Instructions, glossary, rules, lessons and all open items come first in a fixed
  order; the input comes last. Adapters with the `prompt_caching` capability mark the stable prefix. Why: the open-items list
  is now the largest and most repeated part of most packets.
- **Open items trimmed by size, not rule.** Full form ("[project] text (owner, due) → how to close it") for the request's own
  projects; other projects switch to compact form (id, owner, title, no closing hint) only past `open_items.compact_share` of
  the budget. Why: real counts were about 50 open actions and 10 questions for one PM with about 20 projects, about 3,000
  tokens, well within budget; the closing hint roughly doubles each line and only the request's own projects need it.
- **Read-backs show effects and overlaps:** applies to, doesn't change, overlaps with, and a dry-run count against current
  data; rules carry a structured target to compute them. A contradiction with an existing rule or setting pauses even a
  PM-typed rule until the PM picks which wins. Why: the misreadings seen in practice came from rule collisions and corrections
  aimed at the wrong place, which a restated rule wouldn't reveal but a count and an overlap would.

## 2026-10-09: Changes from the first design's author

**Decided by:** project owner, on the review by the author of the first design, who ran it daily.

- **Recovery is a tested feature.** The ledger is exported with the records; `import(export(db))` round-trips in the self-check;
  `cockpit restore --as-of` and single-record restore from the ledger. Why: restoring from git history was used in practice,
  and an export that can't be loaded back is only an archive.
- **Off-device backups in local mode**, with a Today line and header mark until one succeeds and the last backup's age always
  shown. Why: the biggest open risk of the first deployment was the whole knowledge base on one laptop.
- **Breadth waits for use:** hosted mode, packs beyond the second and social media start after the reference pack is in daily
  use.
- **The packet replaces browsing:** it always carries the glossary, active lessons, applicable rules and every open action and
  question; new `glossary.add`, `glossary.update`, `lesson.add` ops; bounded search lookups over sources and records.
- **PM-stated system ops apply at once with a read-back and Undo;** only system ops from inputs or the assistant's own initiative
  wait for a confirm. Why: the risk with the PM's own rules was misreading, which a read-back catches and a confirm doesn't.
- **Undo groups:** dependent ops are restored all or nothing; outbound can't be undone (reverting drafts, "already sent").
- **Owners are a list** (shared ownership is deliberate in some programs); team-only owners are refused and an action without a
  known person is held for "Pick an owner".
- **Lint outcomes depend on destination:** after one return, anything reaching another person is held for the PM; internal items
  warn. Missing links on questions to others, restricted content on the wrong audience and unreadable output are invariants.
- **Gaps from running it:** runner errors classified only from exit code and error stream; every waiting state shows why and until
  when; corrections checked against the data first; audiences per destination instead of open versus restricted; shared masters
  with lock checks and outside edits as changes; connectivity checked before refreshing, and failed refreshes stay stale; edits by
  our own accounts marked as ours; requests about other projects' code handed off (`config/code_owners.yaml`), restoring the
  handoff route the first design had and the restructure had dropped.

## 2026-10-09: Systems review changes

**Decided by:** project owner, after a systems design review of the whole design.

- **Database and ledger instead of files plus git as the store.** SQLite is the system of record; every applied op is written
  to an append-only ledger in the same transaction; records carry versions; ids come from sequences; jobs and the single
  running instance use leases; `data/` becomes a readable JSON export committed to git. Why: half of the storage rules
  (merge-on-save, one writer, ids never repeat, undo only if unchanged, one scheduler) were database guarantees rebuilt by hand
  on files, each learned from a failure. Undo becomes a reverse changeset with field-level conflicts instead of file restores.
  Supersedes the storage part of the 2026-10-08 technology stack entry.
- **Ids, not names.** Records refer to people, teams and projects by id; names are rendered. Why: storing "Team (Full Name)"
  strings is what required a names normalizer on every write, a name sweep and a rename reference index across every copy.
- **Op tiers and untrusted input.** Every op is data, outbound or system; system ops (rules, sources, scope, config, plugins,
  code) never apply automatically from an input. Packets mark untrusted content; lookups only reach configured sources;
  evaluation includes hostile inputs. Why: the design had no prompt-injection model, and mailbox and social plugins plus hosted
  mode make that exposure real.
- **Invariants and lints.** Firm checks always refuse and can't be lowered; fuzzy checks (wording, keyword-matched date
  questions, near-duplicates) return the changeset once, then warn, with severities in `config/checks.yaml`. Why: fuzzy checks
  that refuse produce false positives that push people to switch checks off.
- **Walking skeleton first; extension points marked 1.0, core only or planned.** The build plan reaches a version the PM uses
  in milestone 2 (paste-in, one AI task, about ten ops, the ledger, clipboard, a minimal UI). Only the extension points the two
  packs use are frozen at plugin API 1.0. Why: fifteen milestones before daily use, and sixteen hooks before any plugin, freeze
  guesses.
- **Gaps closed:** quality signals from the PM's corrections and private evaluation cases (6.20); standing rules as
  `config/rules.yaml` entries with a review that merges, retires and promotes rules into config (6.21); config versions and
  migrations, presets, basic and advanced levels, `config explain` (4.0); honest plugin security (declared reach is enforced on
  what the core hands out, not a sandbox, 12.3); one running instance per workspace; packet size budgets (6.6); retention and
  forget-a-person (4.15, 12.4).
- **The design is split into one file per part** under `docs/design/`, keeping section numbers, with a reading map in its
  README. Why: at 1,400 lines every coding session paid to read most of it.

## 2026-10-08: Every source is a setting

**Decided by:** project owner.

**What:** Where anything is looked up (a page, page tree, query, folder, feed, field name or schedule) is always configuration,
never code or default prompt text. Core and bundled plugins refer to sources by config key; default prompt templates use
template variables filled from config. Packs ship source settings as templates with placeholders that the workspace fills in,
with a Today setup line until it does. The specificity scan now also reads page titles, queries, folder paths and field names
from the fictional workspaces' config, and scans default prompt templates as well as code.

**Why:** Rules like "look on the release page" are easy to write straight into code or prompts while building for one
deployment, and each one ties the product to that deployment's tools and page layout.

## 2026-10-08: Lessons from the original deployment since the first design

**Decided by:** project owner.

Each came from a failure in the original deployment.

- **Other areas, even when named in minutes or program pages.** Domains now match owner labels as they appear on pages and in
  minutes, and the applier refuses an action whose owner label matches another domain. The owner described this as
  `other_team_owners` and `program_managers` per area; in the product they are each domain's `match.owners` and `contact`.
- **Dates are looked up, not asked.** New `config/facts.yaml` and fact resolver (6.19): an item's release comes from the
  delivery tracker or the tracker item's sprint or fix version, the release's production date from the delivery team's schedule
  page, and nothing found means TBD. The applier refuses questions for those facts, and any date question to the people listed
  in `no_questions_to`. This is a separate file rather than part of `scope.yaml` (where the owner first put it) because it is
  about where facts live, not whose area something is, and other packs need the same mechanism (publication dates, for example).
  Why: people were asked for dates that a schedule page already held, and the answers went stale.
- **Fixes merge on Apply.** A proposed fix keeps the original files and Apply runs a three-way merge, with a union merge for
  Markdown; only a real conflict stops it, and then the fix is redone automatically. Why: a whole-file staleness check made
  nearly every fix on a busy file go stale. The UI never offers an instruction it can't carry out, and a fix shows and is counted
  only on its issue card.
- **Rename is one op.** `record.rename` updates every stored reference through a reference index and keeps the page id, so the
  page is renamed in place. Why: renames done as several edits missed places and broke links.
- **A code fix is the last resort.** `dev.request` must show that no existing op fits; data that needs a new op waits with its
  fix and runs after Apply. Why: requests that ops could do became code fixes, and data changes needing a new op were refused by
  the running applier.
- **Ids never repeat.** Closed ids are retired. Why: a reused question id made old references point at the wrong question.

## 2026-10-08: Scope is enforced by the applier, with named domains and one contact each

**Decided by:** project owner.

**What:** `config/scope.yaml` gains `domains` (other areas, each with match patterns and one `contact`, usually that area's
program manager), `cross_domain` (impact-only questions, to the contact only, batched) and `unclassified` (ask the PM; never
tracked by default). The applier refuses actions owned by anyone outside the tracked area and questions to anyone outside it,
except an impact question to a domain's contact that names the tracked item it affects. A scope sweep finds existing actions and
questions that break this and files one bulk decision to the PM. A new `other-domain` triage matcher closes changes that sit
entirely in another area. One scope resolver is the only place scope is decided.

**Why:** In the original deployment, scope was advisory: the AI was told what to track but nothing stopped it. Changes on shared
pages that mixed several teams' work produced action items and detailed questions for people in other areas, who don't answer to
the workspace; that work is the program level's concern. The PM's inbox filled with follow-ups that should never have existed.
Making scope a deterministic check, with one named contact per other area and only impact questions allowed, stops the failure
at the write path instead of relying on the model.

## 2026-10-08: Local and hosted deployment from the same code; configuration first

**Decided by:** project owner.

**What:** The app runs in two modes, set by configuration: local (on the PM's computer, reachable only from it) and hosted (on a
web host the PM controls, at the PM's domain, optionally under a path such as `/admin` and optionally hidden from anyone not
signed in). Hosted mode requires real sign-in (pluggable auth providers) and refuses to start unless a set of deploy checks pass.
Packaging lives in `deploy/`: one container image plus a recipe per hosting target, starting with a tunnel to a machine the PM
owns and then a container host. Every setting can come from files, environment variables, flags or profiles, and is editable in
a Settings panel generated from the config schemas.

**Why:** The owner wants to run the product locally or on a web host, behind security checks, at a configurable hidden path, and
to change an installation without changing code. Hiding a path is not security on its own, so the deploy checks make real
sign-in, HTTPS and secret handling a condition of serving. The engine needs long-running jobs, a file system and git, so hosted
targets run it as a container or a process, not as short-lived edge functions. This replaces the earlier "local only" part of the
technology stack decision.

## 2026-10-08: Design recast as a generic core with plugins

**Decided by:** project owner.

**What:** The design is now a base for expansion, not a single-purpose tool. The core keeps only the generic loop (watch,
triage, dispatch, apply, review, send out, follow up), its safety rules and a set of extension points. The original workplace
use becomes the reference pack (design Part 9), built on the plugin API like any other pack. A second, smaller pack (personal
projects) is in the build plan to prove the extension points serve a different kind of work.

**Why:** The owner wants to use the same base for other kinds of work later (publishing support, personal projects, social
media). Building the first use as a pack, from the start, keeps workplace-specific behavior out of the core.

## 2026-10-08: Outbound content goes through channels and one approval gate

**Decided by:** project owner.

**What:** Publishing wiki pages becomes one case of a general model: records render into drafts for channels (pages, messages,
email, posts), and the publisher sends only drafts whose exact content the PM approved. Scheduled sending is allowed only for
approved content. Autonomous sending is not a goal.

**Why:** Social media and publishing plugins need outbound targets other than wiki pages. Putting every target behind the same
approval gate keeps the core promise ("the AI drafts; the human approves everything outward") as the product grows.

## 2026-10-08: Technology stack

**Decided by:** project owner.

**What:** Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff; React + TypeScript with Vite and Vitest. Plugins are Python
packages found by entry point or by folder. Storage starts as files in the workspace git repository behind a repository layer.
The app runs locally for one user.

**Why:** The design already called for Python and React. Pydantic generates JSON Schema from the same models that validate config,
records, ops and manifests, so the AI's output schema and the validator can't drift apart. Entry points give installable plugins
without a custom registry. A local, single-user app keeps the security model small until multi-user is needed.

## 2026-10-08: Changesets are JSON

**Decided by:** project owner.

**What:** Changesets are JSON documents validated against a schema generated from the op registry. Human-edited config stays
YAML.

**Why:** The design called them YAML in one place and JSON in another. AI APIs return structured output as JSON, and a generated
schema gives one source of truth.

## 2026-10-08: Naming fixes

**Decided by:** project owner.

**What:** The meeting entity is `Meeting` (was `Task`); a call to the AI provider layer is an `AiTask`. Page-specific ops became
record ops (`record.set`, `record.add`, `record.del`, `record.log`). `config/pages.yaml` became `config/render.yaml`. Tracker- and
wiki-specific triage matchers got generic names (`container-not-mapped`, `child-item`, `unknown-key`).

**Why:** "Task" meant two different things. Page and wiki names don't fit outputs like messages and posts.

## 2026-10-08: Workspaces live outside the repository

**Decided by:** project owner.

**What:** Real workspaces are separate git repositories outside this one, found by `--workspace` or `COCKPIT_WORKSPACE`. Only the
two fictional workspaces are committed, as fixtures, and `.gitignore` admits nothing else under `workspaces/`. The specificity
scan accepts `--workspace` to check code against a private workspace without copying its contents into the repository.

**Why:** Keeps real names and data out of the product repository, and lets the scan catch a deployment's specifics, not only the
demo ones.

## 2026-10-08: The fixer changes the workspace, not the product

**Decided by:** project owner.

**What:** Proposed fixes may change a workspace's config, rules, prompts, templates and private plugins. A fix that needs the core
or a bundled plugin is written as a patch and an issue for this repository.

**Why:** Applying AI-written fixes to an installed engine would make each deployment drift away from the product.

## 2026-10-08: Design document moved to `docs/`

**Decided by:** project owner.

**What:** `DESIGN.md` moved to `docs/DESIGN.md`, where `CLAUDE.md` already pointed. The copy of `CLAUDE.md` that was embedded in
the design was removed; `CLAUDE.md` is the only copy.

**Why:** One copy of each document, at the path the other documents use.

## 2026-10-09: Plugin API 0.x host boundary

Implementation of the owner-requested host uses per-store registries and post-commit events; unsupported 1.0 manifest contributions (including interfaces and reach capabilities) are refused explicitly until their extension points exist, with no scope added beyond the next-task brief.
