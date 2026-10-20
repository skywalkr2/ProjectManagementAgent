# What changed since the first design

This note is for the author of the first version of this design (the single `DESIGN.md` that started this repository). It
summarizes what changed, why, and where everything now lives (roadmap phases 0, A and L cited below are in
`docs/project/roadmap-done.md`), so you can review the new version without diffing 1,400 lines.

The first design's core held up: the AI writes only changesets, a deterministic applier checks and applies them, the PM approves
everything outward, rules run before AI, any AI vendor can be used through configuration, and scans keep specifics out of code.
Those are unchanged. What changed falls into three groups: the design was **productized** (a generic core that other kinds of
work plug into, deployable locally or hosted), **lessons from the running deployment** were added, and a **systems review**
changed the storage, identity and safety models underneath.

## 1. Productized: a generic core plus plugins

- **The workplace PM workflow is now a pack, not the product.** The core keeps the loop, the safety rules and a set of
  extension points (connectors, channels, record types, ops, triage matchers, AI task kinds, renderers, lookups, panels, Today
  lines, jobs). The original use (a leader, wiki status pages, programs, "Team (Full Name)" owners, risks owned by teams) moved
  into the **reference pack** (Part 9), built only through the plugin API. A second small pack (personal projects) proves the
  extension points serve other work. Publishing support and social media are planned packs (3.7). *Why:* the owner wants the
  same base for other kinds of work, and building the first use as a pack keeps workplace specifics out of the core.
- **Publishing generalized to drafts and channels.** A wiki page is one channel; email, a blog or a social post are others.
  Every outbound draft goes through the same content-hash approval; scheduled sending only for approved content (6.3, 6.12).
- **Deployable locally or hosted.** Same code; mode, address, base path (`example.com/admin`), optional hiding, sign-in
  providers and storage are settings; hosted mode refuses to start unless deploy checks pass (HTTPS, real sign-in with a
  second factor, secrets, trusted proxies, persistent storage) (Part 11).
- **Configuration first.** Anything someone might want different is a setting: layered defaults, files, environment
  variables, flags and profiles; a Settings panel generated from the schemas; config versions with migrations; presets and
  basic/advanced levels (4.0). **Every source is a setting:** no page, query, folder, field name or schedule is written into
  code or default prompts (4.0, 10.1).

## 2. Lessons from the running deployment

| Lesson | Where |
|---|---|
| **Scope is enforced, not suggested.** Other teams' items are the program's business: no actions or detailed questions for people outside the tracked area, even when minutes or program pages name them. Each other area has one contact (its program manager) who may get one batched impact question. Scope was advisory in the first design, and the inbox filled with follow-ups for people who don't answer to the PM. | 4.4, 6.7, 6.18 |
| **Dates a published schedule holds are looked up, never asked.** Release from the tracker; production date from the delivery team's schedule page; nothing found means TBD. | 4.16, 6.19 |
| **Proposed fixes merge on Apply** (three-way, union for Markdown); only a real conflict stops a fix, and then it is redone automatically. A fix shows in one place, its issue card. The screen never gives an instruction it can't carry out. | 6.13, 7.3, 7.6 |
| **Rename is one op** and keeps the page id, so the page is renamed in place. | 6.7 |
| **A code fix is the last resort:** only when no op can do it; data that needs a new op waits for the fix. | 6.7 |
| **Ids never repeat.** | 5.0, 5.2 |

## 3. Systems review: storage, identity, safety

- **A database and a ledger instead of files plus git as the store.** SQLite holds the records; every applied op is written to
  an append-only ledger in the same transaction; records carry versions; ids come from sequences; jobs and the single running
  instance use leases. `data/` is now a readable JSON export committed to git. *Why:* many storage rules in the first design
  (merge on save, one writer, ids never repeat, undo only if unchanged, one scheduler) were database guarantees rebuilt on
  files. Undo is now a reverse changeset with per-field conflicts instead of restoring file backups (5.0, 6.7).
- **Ids, not names.** Records refer to people, teams and projects by id; names are stored once and rendered (owners in the
  owner format). *Why:* stored name strings were the reason for the names normalizer on every write, the scheduled name sweep,
  and renames chasing every copy. Names are now resolved once where they come in (5.1, 6.11).
- **Op tiers and untrusted input.** Every op is `data`, `outbound` or `system`. System ops (rules, watched sources, scope,
  config, plugins, code) never apply automatically from an input; the PM confirms them. Packets mark untrusted content; the
  paste box separates "your note" from "pasted content"; lookups only reach configured sources; evaluation includes hostile
  inputs. *Why:* the first design had no prompt-injection model, and mailbox, social and hosted use make it real (6.7, 12.2).
- **Invariants and lints.** Firm checks always refuse and can't be lowered; fuzzy ones (wording, keyword-matched date questions,
  near-duplicates) send the changeset back once, then warn; severities in `config/checks.yaml` (4.17, 6.7).
- **Learning from corrections.** Send-backs, undos, dropped questions, pulled-back auto-closes and edited drafts are recorded as
  quality signals, shown as rates, and can become private evaluation cases (6.20).
- **Standing rules have a lifecycle.** `rules.md` became `config/rules.yaml` entries (id, text, what they apply to, source,
  status). A periodic review merges, retires and **promotes** rules that are really settings into config, since an advisory
  rule is how the scope failure happened (4.10, 6.21).
- **Smaller items:** packet size budgets with omissions recorded (6.6); one running instance per workspace (5.0); retention and
  forget-a-person (4.15, 12.4); honest plugin security: declared reach is enforced on what the core hands out, but in-process
  plugins aren't sandboxed (12.3).
- **Build plan:** a walking skeleton the PM uses in milestone 2 (paste-in, one AI task, about ten ops, the ledger and undo,
  clipboard, a minimal UI); only extension points the two packs use are frozen at plugin API 1.0 (3.3, 13.1).

## 4. Renamed or removed

| First design | Now |
|---|---|
| `Task` (the meeting entity) | `Meeting`; an AI call is an `AiTask` |
| `page.set`, `page.add`, `page.del`, `page.log` | `record.set`, `record.add`, `record.del`, `record.log` |
| `config/pages.yaml` | `config/render.yaml` |
| `config/rules.md` | `config/rules.yaml` |
| `data/people.json` as config | people are records; `data/people.json` is their export |
| changesets in YAML (in one place) and JSON (in another) | JSON, schema generated from the op registry |
| triage matchers `under-tree-not-mapped`, `sub-task`, `no-record-for-key` | `container-not-mapped`, `child-item`, `unknown-key`; new `other-domain` |
| `leader` in `workspace.yaml` | reference pack config (9.3) |
| names normalizer and name sweep | name resolution at the boundary (6.11) |
| file backups and whole-file undo | ledger and per-field undo |
| `watch.add` for every new key | `watch.item` (data) for items in configured sources; `watch.add` (system) for new sources |
| Part 10, a copy of `CLAUDE.md` | removed; the repository's `CLAUDE.md` is the only copy |
| `DESIGN.md` | `docs/design/`, one file per part, same section numbering |

## 5. Where each first-design section went

| First design | Now |
|---|---|
| 1.1 to 1.3 | 1.1 to 1.3 (generalized beyond workplace PM; 1.4 core vs plugins, 1.5 assistant not methodology and 1.6 non-goals are new) |
| 2.1 Layers, 2.2 Where things go | 2.1, 2.3 (2.2 repository layout and 2.4 technology are new) |
| 3.1 to 3.10 Configuration | 4.1 to 4.10 (4.0 principles and 4.11 to 4.17 are new) |
| 4 Data model | Part 5 |
| 5.1 Connectors | 6.2 (6.3 channels is new) |
| 5.2 Watchers, 5.3 Triage, 5.4 Dispatcher | 6.4, 6.5, 6.6 |
| 5.5 Changesets and the applier | 6.7 |
| 5.6 Questions, 5.7 Actions, 5.8 Notices, 5.9 Names | 6.8, 6.9, 6.10, 6.11 |
| 5.10 Records, renderer, publisher | 6.12 |
| 5.11 Governor and fixer, 5.12 Scheduler, 5.13 Today | 6.13, 6.14, 6.15 |
| 5.14 Periodic jobs, 5.15 AI provider layer | 6.17, 6.16 |
| 6.1 to 6.5 UI | 7.1, 7.3, 7.4 (now "Waiting to go out"), 7.5, 7.6 (7.2 plugin panels is new) |
| 7.1 to 7.6 Lessons | 8.1 to 8.6 (workplace-only rules moved to 9.5) |
| 8.1 to 8.4 Guardrails | 10.1 to 10.4 |
| 9 Build plan | Part 13 |
| 10 `CLAUDE.md` | repository `CLAUDE.md` |
| (new) | Part 3 plugins, 6.1 plugin host, 6.18 scope, 6.19 facts, 6.20 quality signals, 6.21 rules review, Part 9 reference pack, Part 11 deployment, Part 12 security |

## 6. Questions for you (first round)

Your experience running the first version would settle these better than more design:

1. **Agent mode and the database.** Agent-mode runs no longer read the workspace; they get the packet as files. Did your runs
   rely on browsing the workspace in ways a packet wouldn't cover?
2. **Confirming system ops.** Rules, new sources and scope changes now always need a click from the PM, even when the PM asked
   for them in "Respond to the assistant". Is that friction acceptable in daily use, or should PM-originated system ops apply
   with an undo window instead?
3. **Undo conflicts.** Undo now restores what it can and lists conflicting fields. Were there undo cases where restoring part of
   a changeset would have been wrong?
4. **Owner format and teams.** Owners are now a person id plus an optional team id. Did anything depend on owners that were
   teams only, or on more than one person per action?
5. **Lints versus refusals.** Which of your wording and question checks truly must refuse, and which would be fine as "send back
   once, then warn"?
6. **What's missing.** Any failure from running it that isn't in Part 8 or the lessons above.

## 7. After your review: how each point was handled

Thank you for the answers. Everything below is now in the design; section numbers point to where.

### Your cautions

| You said | What changed |
|---|---|
| Keep git as a working recovery path | The ledger is exported with the records. `import(export(db))` round-trips in the self-check; `cockpit restore --as-of <time>` imports the last export before then and replays the ledger; any single record can be shown and restored as of a past time (5.0). |
| Back up off the machine in local mode too | Backups to a synced folder, drive, object store or the export remote, encrypted when outside the PM's control. Local mode shows a Today line and a header mark until one has succeeded, and the header always shows the last backup's age (4.15, 7.6, 11.1). |
| Hold hosted mode and the social pack | Hosted mode, packs after the second, and social media start only once the reference pack is in daily use with steady quality signals (Part 13). |

### Your answers

| Question | What changed |
|---|---|
| 1. Agent mode and the database | The packet always carries the glossary, active lessons, applicable rules, and **every** open action and question with ids (compact, never cut by the size budget). New ops `glossary.add`, `glossary.update`, `lesson.add`. Bounded search lookups over sources and records, and a source's previous version (6.6, 6.22). |
| 2. Confirming system ops | System ops from the PM's own note apply at once, with a read-back on the card ("Here's how I read your rule: ...") and Undo. A confirm is needed only for system ops from pasted or watched content or the assistant's own initiative (6.7, 12.2). |
| 3. Undo conflicts | Ops in a changeset can share a group; the applier groups the known pairs itself (fact + the question it closed, action + its notice, rename + its outputs). Undo is per field across groups and all or nothing within one; a conflicting group is listed and skipped. Outbound can't be undone: a published edit gets a reverting draft, a sent message shows "already sent" (6.7). |
| 4. Owner format and teams | Owners are a list of person ids, each with an optional team. Team-only owners are refused. An action whose person isn't known is held as "Pick an owner" and added only once it has one. Reassign swaps one person (5.1, 6.7, 6.9). |
| 5. Lints versus refusals | Your must-refuse list is now invariants: model name, restricted content on a disallowed audience, questions to others without links or with links they can't open, actions without a person or for a team outside scope, unreadable output (retried). Your send-back list is lints. After one return, anything that will reach another person is **held for the PM**; internal items warn (4.17, 6.7). |

### What was missing

| Failure you saw | Where it's handled |
|---|---|
| Runner errors read from model output; a usage limit hidden because only stdout was kept | `classify_error` reads only exit code, error stream and transport errors; both streams kept on the `Run` (6.16, 5.1) |
| Waiting items looked stuck | Every waiting state says why and until when ("next batch at 3:00", "paused until the limit resets") (7.6, 5.1) |
| A correction taken at face value; a code fix for a problem that didn't exist | The feedback run states where the item actually is first; if the data disagrees, it asks the PM. A `dev.request` from a correction must cite the data (6.8, 6.7) |
| Open versus restricted wasn't enough | Audiences: each destination is open or a named group with an optional banner; each restriction names the audiences it allows; an invariant checks every draft (4.1, 6.7, 12.1) |
| Shared masters edited outside the tool | Channels declare `external_editors`; the publisher checks `lock_status` and waits or warns; outside edits are diffed and come in as changes (3.3, 6.12) |
| No network on wake treated as an outage, and the refresh counted as fresh | Connectivity checked first; no network files nothing; a failed refresh leaves data marked stale with its age (6.4, 6.14) |
| Runs asked who created pages the tool itself published | Edits and pages by `our_accounts` are marked `by_us` and given to every run; lookups answer "we did" (4.1, 6.4, 6.6) |
| Requests about another project's code | `config/code_owners.yaml` says who owns what; matching requests become a `handoff` draft for that owner, never a fix. Your first design had this route; the restructure had dropped it (4.18, 6.7, 6.13) |

### Still open

1. **Packet size with every open action included.** Fine for one PM's workload; a very large portfolio may need the compact form
   trimmed further (for example, actions for other projects shown as id, owner and title only). Tell us if your real counts
   suggest a limit.
2. **Read-back wording.** Should the read-back also say what the rule will *not* cover, given the over-application you saw?

## 8. Second round: the two open points

| You said | What changed |
|---|---|
| Put the stable parts first so providers can cache the prefix | Packets are laid out stable first, in a fixed order: instructions and op reference, glossary, rules, lessons, all open actions and questions; then scope, facts and related records; the input last. Adapters with a `prompt_caching` capability mark the stable prefix; others ignore the mark (6.6, 6.16). |
| Trim by size, not by rule | The request's own projects always get the full form. Other projects switch to compact form only when the open-items list passes `open_items.compact_share` of the budget (default 40%). Your counts are recorded in the design as the reference for scale (6.6, 4.9). |
| Drop the closing hint in the compact form | Compact form is id, owner and title only; the "→ how to close it" part appears only in full form (6.6). |
| Read-backs should show effects and overlaps | Four short lines next to Undo: **Applies to**, **Doesn't change**, **Overlaps with** (linked), **Right now it would change** (a dry-run count, expandable, with zero matches flagged). Rules now carry a structured target (record types, fields, filter) so the lines are computed, not just written: config changes are dry-run in a rolled-back transaction, prose rules count the records their target matches, and overlaps compare targets, with the AI adding contradictions in meaning (4.10, 6.7, 7.6). |
| A contradiction should pause even a PM-typed rule | It does: the card becomes a choice of which one wins (the new rule, the existing one, or both with a narrower target) (6.7). |

Nothing from either round is still open on our side. If anything new comes up from running it, the place for it is Part 8
(product rules, each with where it is enforced).

## 9. Since the second round: build order and baseline

For your information; nothing here needs an answer.

- **The first real use is now a small literary imprint**, not a workplace. The publishing pack moves first in the build order;
  your workplace PM design stays as the reference pack, built on fictional data, as the main proof that the core is complete
  (Part 9, Part 13).
- **Dependencies and baselines are now core** (6.23; moved to the project management pack in 1.1, see 10.2): what waits on what, need-by dates, at-risk warnings on Today, and
  variance against a baseline that only the PM can reset.
- **Design 1.0 is the scope baseline.** Further changes go through change control (`docs/project/scope.md`).
- **Playbooks** (3.8): built-in good practice for project support in the core and for each field in its pack, overridable
  entry by entry. Your lessons are the core playbook's first material.
- **Project management support** (6.24): project issues and assumptions, optional risk fields and reviews, one suggested
  escalation for long-unanswered questions, communication cadence, meeting agendas; and **asking the assistant** (6.25) for
  anything not built in. The automation `Issue` record is now `Problem`, so "issue" keeps its project meaning.
- **AI accounts** (6.16, 4.8): the PM's own accounts with any vendor, any OpenAI-compatible endpoint (including local models),
  aggregators such as OpenRouter, or command-line agents; capabilities and prices are per model, from provider catalogs.
- **No code fixer in the product.** Your fixer lessons (merge on Apply, one place per fix, last resort) shaped the design, but
  the product no longer changes its own code at all: an AI rewriting installed code is too risky for people who install it.
  Automation problems are explained on their card and can become a report the PM sends to the maintainers (6.13). Development
  happens in the repository with the developer's own tools.
- **AI review:** claims now cite exact evidence that must exist in the source; each task kind gets only its ops; one input per
  call after cleaning quoted history and signatures; lessons learned from inputs wait for the PM (your lessons log was the one
  place an injected instruction could have persisted); a deterministic evaluation picks the model; a cheap model escalates to a
  stronger one only on check failures.
- **UI review** (Part 7): Today becomes the home queue; one primary action per row; undo toasts instead of confirmations except
  for sending; edit in place before approving; evidence on every claim; keyboard shortcuts; phone layouts; first-run setup;
  accessibility to WCAG 2.2 AA; a front-end architecture with live updates and a generated API client.
- **Core features for document-heavy packs** (a future sales pack first): long text stored once per version with authorship (5.0), drafts as
  prose that the person reviews (6.7), a file channel (6.3), stages for work that moves through steps (6.26), an independent
  second opinion on another account (6.16), and cost control: estimates, a go above a set amount, budgets per task kind and per
  record (6.16). In version 1, before the plugin API is frozen.
- **Plugins working together** (3.9): packs share core records (a launch is one project for both the publishing and a social
  media pack), offer versioned interfaces to each other, subscribe to events and can request each other's task kinds, always
  through the core. Each pack still works alone.
- **Two computers through a synced folder** (5.0): the database and git stay on local disk; a synced folder holds a readable
  export by project, the lease and nothing live; diverged histories are never merged silently.
- **Synced folder details** (5.0, 9.7): projects can nest (a series and its titles) and their folders nest too; sources
  travel with their project; the cockpit ignores its own files when watching; authorship has three kinds; the publishing
  pack defines `publishing/manuscript-source@1` so any plugin that produces finished manuscripts can start a launch.
- **Working copies and review** (5.0, 6.7, 7.2): long text can be handed out as a file for the person's own tools and taken
  back for review; the person's outside work and the assistant's drafts both wait as proposed versions, accepted passage by
  passage in a two-way or three-way compare view. An op validator's refusal counts as an invariant failure (6.16).
- **Draft checks and plugin hooks** (6.7, 3.3, 3.4, 4.6, 4.12): paragraph-anchored drafts, lints computed in code and anchored
  to passages, lints on drafts counting for escalation, a project's own language, declared outside programs, a person's own
  data files for a plugin, and a `text.accepted` event.
- **Lessons from switching AI providers** (6.16, 6.14, 6.13, 6.3, 6.7): no silent default provider, a smoke test of every
  tier with exact parameters, vendor error text read only in the adapter, no new work on old code after settings change,
  canonical form and a re-pull after publishing, premise checks before "can't do", `project.add` and person-owned fields,
  office-file extractors, and probation for a new account.

## 10. Design 1.1 (2026-10-12): what changed since the 1.0 baseline, and what was dropped

For you, so you can see what happened to your design after the baseline. Design 1.0 was set on 2026-10-09. Three days
of building followed, with about sixty decisions (`docs/decisions.md`), and the design text fell behind them. On
2026-10-12 every part was brought up to date. Items that are designed but not built are now marked "designed, not yet
built" in place, not deleted. The full audit of design against code is in `docs/project/review-2026-10-12.md` and
`docs/project/audit-2026-10-12/`.

### 10.1 What the product became

- **An everyday assistant, not only a PM's tool** (1.1, 7.1). A person running their own days signs in to their mail and
  calendar and is told what to do each day. A PM gets the same home and more.
- **The core is complete on its own** (1.3, 3.7). The free version is the core plus a "define your own" kit: item
  types, fields, stages and checks set on screens and saved as a template. Industry packs, your workplace pack among
  them, are add-ons in their own repositories, found on an Add-ons screen from a public catalog the owner controls
  (3.11).
- **Inputs come in on their own** (6.4, 6.5). Watched sources (a folder, a feed, a calendar file address, a mailbox over
  IMAP) hand in each difference as an ordinary untrusted input. Services that need their own sign-in (the two big mail
  and calendar services) are add-ons. The core provides the sign-in (OAuth with PKCE through the service's own page),
  and signing in is the whole setup: the inbox and main calendar start reading at once.
- **Guided setup and Settings on screen** (4.0, 7.8). A first-run guide covers where the workspace lives, who you are,
  the AI account, a template, backups and a first hand-in. Settings forms are generated from the schemas. Saves never
  race and are committed to the workspace's git. AI accounts are picked from a list of services, or of command-line
  agents run locked down (6.16).
- **One source of truth and value lists** (5.1). Every fact lives once and is referred to by id. Fields with a known set
  of values take them from lists the person can extend, with Undo.
- **Ask the assistant** (6.25). Answers about the app come only from the shipped user guide, the settings and the
  records, with the passage quoted and checked like evidence. A settings change it suggests is a proposal the person
  applies.
- **Document work** (5.0, 6.7, 6.26). Built for the writing and publishing packs, and useful to any pack:
  - long text with versions and authorship by passage;
  - drafts reviewed change by change in a two-way or three-way compare view;
  - working copies edited in the person's own tools and taken back for review;
  - a synced folder so one workspace moves between two computers;
  - stages;
  - second opinions on another account;
  - cost estimates and budgets.
- **Plugins work together only through the core** (3.9): shared records, versioned interfaces, events and requests.
  The plugin API is at 0.3.55. Its developer guide is generated from the code, and that guide is the contract.
- **The UI was redesigned** (Part 7). The shell is full-width with a sidebar. Today is a ranked queue with a detail pane
  and a context rail (agenda, to-dos, what came in). A visual system with tokens and a style guide replaces the earlier
  screens. Record pages and settings follow set layouts, and item titles follow a rule ("{kind} from {person} · {topic}").

### 10.2 Dropped, deferred or changed from your design

Please look at this table first. Each row is something you designed or asked for that is now different. "Not built"
means the design still holds and the work is scheduled; the phase letters refer to `docs/project/roadmap-to-1.0.md`.

| Your design (or 1.0) | Now | Why |
|---|---|---|
| **Scope enforced by the applier** (6.18): only the tracked area gets actions and detailed questions; one impact question per other area | Designed, not built (phase E) | The first real use is a writer's own work, where nothing is outside scope. It matters again when a workplace pack exists. |
| **Facts a schedule holds are looked up, never asked** (6.19) | Designed, not built (phase C4) | Waits for the first pack with a published schedule to read. |
| **The publisher and channels** (6.3, 6.12): the wiki page channel, content-hash approval, Waiting to go out, `external_editors` and lock checks | Not built. The file channel comes first (phase C4); social, email and newsletter channels are not in 1.0 | Copy and Mark sent covers follow-ups today. The first outbound need is saving approved files. |
| **Read-backs for system ops from the PM's note** (6.7, your second round): Applies to, Doesn't change, Overlaps with, dry-run count | Not built (phase E). System ops from the PM apply with Undo but no read-back | Rules and their structured targets aren't built yet, so there is nothing to compute the lines from. |
| **Glossary and proposed lessons in every packet** (6.22, your first round, question 1) | Not built; moved to phase L after your review (section 11). Packets carry the open actions and questions, people, projects and value lists, stable parts first | Lessons were a launch-slice item and were missed. The review of 2026-10-12 lists this. |
| **Restore as of a time, and restore one record** (5.0, your caution on git as recovery) | Not built. One record moved to phase L after your follow-up (section 12); a point in time stays in phase E. Export and import round-trip and are tested; backups run to folders on their own | Comes with the governor. |
| **Encrypted off-machine backups** (4.15) | Encryption moved to phase L (section 12). Partly built today: backups go to the folders the person picks (a synced folder works); there is no encryption and no object store yet | As above. |
| **Audiences and the restricted-content invariant** (4.1, 6.7, 12.1) | Not built. The other invariants on your must-refuse list are in place: model name never shown, links a recipient can open, actions need a person, evidence quotes must exist | Needs the publisher. |
| **Code owners and hand-off drafts** (4.18, 6.13) | Not built | Needs requests about other projects, which come with the workplace pack. |
| **The governor** (6.14): stale-item sweeps, outage handling, scheduled export with its remote | Not built (phase E). Crashed runs are queued again on start, and held for the person when found stuck twice (built, phase A2) | Deferred behind the person's path working. |
| **The app restarts itself to use new settings** (6.14, in 1.0) | Changed: settings read at the moment of use apply at once, anything else says a restart is needed and waits for the person's "Restart now" | The owner's rule: restart only when needed and only when told. |
| **Today as one ranked column** (7.3) | Changed: a ranked queue with a detail pane and a context rail. Engine and API built; the screen is phase B | A laptop screen was two-thirds empty. |
| **Dependencies, baselines, RAID, risk reviews, escalation, cadence, agendas** (6.23, 6.24, added in 1.0 from your lessons) | Moved out of the core into a project management pack (phase C2), not yet started | Schedules belong to a kind of work. The owner wants an AI project manager that builds schedules and tracks action items as a pack of its own. |
| **The workplace reference pack bundled** (Part 9.1–9.5) | A private add-on in its own repository, not started. The core proves itself through the define-your-own kit and the example plugin | The core must be complete with no pack; industry depth is sold separately. |
| **The publishing pack bundled** (9.6–9.7) | An add-on in its own repository, not started (phase C3). A writing pack is being built by its own builder | Same decision. |
| **"The app never installs code into itself"** (3.11, in 1.0) | Changed: one-click install from the Add-ons screen, with checksums. The server side is built; the button is not (phase A) | Installing from a terminal was a pain for the people the owner shares it with. |
| **Approving what a pack adds, reaches and keeps when it is turned on, and again on update** (3.6, 3.11) | Designed, not built. Turn on acts at once, and the Add-ons listing shows the summary beforehand | Comes with the Install button (phase A). |
| **Screenshots, office files and PDFs read as inputs** (1.3, 6.6) | Office files and PDFs moved to phase L (section 12); screenshots need a model that reads images. Not built today: no text extractors and no image reading yet. Pasted text, text files and watched sources are read | No pack has needed it yet. |
| **The desktop installer** (decided 2026-10-11 as the first item after launch) | Phase E of the roadmap, after the packs | The later plan puts the packs in the owner's hands first. |
| **Hosted mode** (Part 11) | After 1.0. Base paths and public addresses are kept working, since a local install uses them too | One person on their own computer first. |
| **Triage rules in `triage.yaml`** (4.5) | A `triage:` list in `watch.yaml`, beside the sources they name | Fewer files. |
| **A first read hands in nothing** (6.4, the baseline) | A setting: baseline, recent (the last day, the default for a sign-in) or all | A baseline meant a person who just signed in saw nothing at all. |
| **A rename is one op that updates every reference** (6.7, your lesson) | Holds for value lists. There is no general `record.rename` op yet; records refer to each other by id, so a name changes in one place | Ids made most renames unnecessary. |
| **The go/no-go on 2026-10-30 and the November freeze** | Set aside. The roadmap now runs in phases, each ending on a test the owner runs | Too many streams ran at once and errors reached the owner (`review-2026-10-12.md`). |
| **The code fixer** | Removed (section 9 above). Problems become a report the PM sends to the maintainers | An AI rewriting installed code is too risky for people who install it. |

### 10.3 Your earlier answers: kept and built

These hold in the code as you asked:
- owners as a list of person ids with an optional team, and "Pick an owner" for unknown people;
- your must-refuse list as invariants and your send-back list as lints, held for the PM after one return when the item
  reaches someone else;
- undo per op group with per-field conflicts;
- runner errors classified from the exit code and error stream only;
- every waiting state saying why and until when;
- no network files nothing;
- our own accounts' edits marked as ours;
- packets stable parts first;
- evidence on every claim;
- one input per AI call.

### 10.4 What we'd like from you

1. **Anything in 10.2 you think is more urgent than its phase.** Scope (6.18) and fact lookups (6.19) came from your
   running deployment. Both are scheduled after the packs.
2. **Anything you designed that this summary doesn't mention.** That is the case we are most worried about.

## 11. Your review of 1.1: the learning loop (2026-10-12)

Thank you. You said the soul of the first version was that the assistant got smarter about each project the more it saw,
and that 1.1 had built the write side of that loop and deferred the read side. You were right.

### Your questions, answered from the code

| You asked | The answer |
|---|---|
| Where do a project's accumulated facts go in the packet, how many fit, and is there a ranking? | Nowhere yet. Facts are records with text, project, source, evidence and trust, but the packet carries only the op reference, the task's guidance, value lists, every open action and question, people and projects. There is no ranking and no size limit on the open items. |
| Is there any path from a send-back or an edited-then-sent draft to something the next run reads? | No. A send-back's note reaches the re-run of that one item. Every correction is recorded as a signal, and an edited follow-up keeps the text actually sent, but no later run reads any of it. |
| Are lessons records with ids, or text? | Neither: lessons and the glossary did not exist. Rules had the shape you describe (id, text, a structured target, source, date, status) but lived in a settings file that only stage checks read. |

### What changed

The owner put your learning slice next, after the baseline and before the UI: **phase L** of the roadmap, with your exit
test, "the assistant doesn't repeat a corrected mistake". Section 6.22 is rewritten from your slice:
- the four knowledge record types beside facts and rules;
- the knowledge section in your order;
- facts ranked, cut at a budget, with what was left out counted;
- the knowledge log on each run;
- one learning proposal per correction, with `lesson.update` when a guard failed;
- learning from inputs;
- the repeat-correction signal;
- consolidation into the rules review;
- your fixture pairs and the day-30 scenario.

Your sizing (about 85 lessons, 80 terms, 25 people with routing, 70 facts on the busiest records) fits: everything but the facts
stays in the stable part of the packet.

| You proposed | What we did differently, and why |
|---|---|
| A bounded `search` the run can use | A search **round**: the run asks, the engine searches and runs the task again with the results, at most twice. Live tool calls don't work on every kind of account the person may use, and command-line agents are among them. |
| Enforce searching before a lookup, a question or a code request | A lint, `already-known`: a question, lookup or report that a plain search already answers is sent back once with the match. Matching is fuzzy, so it can't be an invariant. |
| Rules beside the new records | Rules **become** records, as value lists did: history and Undo, no restart, and they travel with the workspace. The settings file stays as the starting set. |
| Promote a lesson to a rule, a setting or an invariant | A rule with a deterministic check, a setting, or a lint the product already has. A guard that needs new code becomes a report to the maintainers, because the product no longer changes its own code (your fixer lessons, section 9). The lesson keeps the why. |
| Run the fixture pairs on every model change | They run on the person's own AI accounts when the person starts them, because each run costs money. The plumbing (the correction reaches the next similar packet, ranked, logged) is tested on every change at no cost. |
| A small learn task on every signal | Its own task kind, on the low-cost tier, with a budget, batched every 30 minutes by default. Corrections recorded before phase L are learned from once when it arrives. |

On screen (7.18), there are four places:
- a proposal is one line on the correction's own card ("Learned: … · Keep · Edit · Discard");
- a Today line gathers the pending ones;
- each project's page shows what the assistant knows and what is still unknown, each unknown with its routed question;
- a Knowledge screen lists every entry.

The Learned line comes with phase L; the rest is laid out with the redesigned screens in phase B.

The fuller ideas from your first note come later, when real material has accumulated. They are phase D, the owner's real use:
- voice per recipient beyond the first style notes;
- acronyms as a daily habit;
- checking a fact's freshness before an outward draft, with disagreements recorded as private discrepancies.

Scope (6.18) and looking up before asking from outside sources (6.19) wait for a workplace pack, as you suggested.

## 12. Your follow-up on section 11 (2026-10-12)

All eight points are in, as you proposed except where noted below. Phase L grows from about 6 to about 8.5 sessions.

| You said | What changed |
|---|---|
| 1. Learn at the moment of correction when the person is there | A correction where the person wrote something (a send-back note, an answer to the assistant's question, a rule stated in Ask) is learned from at once. The Learned line appears on that card within seconds. Silent corrections are batched every 30 minutes (6.22, 7.18). We have no separate "Respond to the assistant" action; its equivalents here are the send-back note and the answer to a question the assistant asked. |
| 2. Don't let the cheapest model write the guards | Two task kinds. `learn-correction` writes lessons, lesson updates and rules on the stronger tier. `learn-input` proposes terms, routing and facts on the input's own tier. Anything after a repeat correction always uses the stronger tier (6.22, 4.25). |
| 3. Run the fixture pairs on a model or account switch | The switch's primary action is "Switch and check (about $X)", with "Switch without checking" in its menu. This is part of probation (6.16). A failed pair shows on Today with Switch back. We kept it an offer, not automatic, because spending is the person's choice; but it is offered at the switch, which is the moment you named. |
| 4. Fact date and source in the packet; acronyms with inputs | Each fact in the packet reads "as of <date>, from <source>". Before each input's run, a rules-only scan lists the terms missing from the glossary, and the run proposes them, with one short question when a term blocks understanding (6.22). |
| 5. Keep the proposal queue from flooding | Proposals from inputs come as one card a day ("The assistant learned 7 things today"), merged before they are shown. Unreviewed ones expire after 14 days, with the count shown on the next card. Proposals from corrections stay on their own card and never expire (6.22, 7.18). |
| 6. Learn from Ask | A rule or fact stated in Ask becomes a proposal beside the answer. It applies at once as the person's own words, with the read-back and Undo (6.25). |
| 7. Text extractors; encrypted backup and restoring one record | The owner moved both into phase L. The core's extractors (documents, spreadsheets, presentations, PDFs) and the extractor extension point. Encryption for backups that leave the person's control. Showing and restoring one record as it was. Screenshots need a model that reads images, so that is a capability of the account rather than an extractor. Point-in-time restore stays in phase E. |
| 8. Knowledge travels | Every knowledge record is in the export and import. "Take my lessons" (Settings, and `cockpit knowledge export`) carries the active lessons, the rules and the glossary terms not tied to a project into another workspace, as the person's own, with Undo. Routing and style notes stay behind with the facts, because they name that workspace's people. |

## 13. Close-out of the first round (2026-10-12)

| You said | What changed |
|---|---|
| 1. A fallback is a switch too | Only accounts that passed the learning check, or that the person accepted unchecked, may sit in a fallback chain; settings ask when an unchecked one is added. The first run on a fallback account carries "First run on <account>" on its cards (6.16). |
| 2. Direct edits are corrections | A new signal, `edited`: the person changes a field the assistant set (a fact, an owner, a due date, a project, a question's wording before sending). The ledger shows who set each field, so it needs no AI. It is a silent correction, learned from in the 30-minute batch (6.20, 6.22). |
| 3. Prove it on real use early | The owner chose to start real use at the end of phase L, beside the UI and pack work. Both numbers are designed and reviewed weekly for the first month. The repeat-correction rate should fall. The knowledge-used rate should rise: each changeset lists the knowledge ids it applied, checked against what the run was given. A loop that isn't closing is fixed before more pack work. Phase D's sign-off adds the falling rate (6.20, roadmap). |

## 14. Your review of Part 8 (2026-10-12)

| You said | What changed |
|---|---|
| Part 8 should be data, not prose | Its rules become the core playbook's seed lessons in phase L: records shipped with the product, in packets like the person's own, pointed at by fixtures, with the person's rules winning by id. The page is generated from them, and the self-check fails when it is stale. Seed lessons guarded by an invariant or code stay out of packets, as the record of why; instruction and lint ones go in. |
| Say what kind of guard each is; test the soft ones | Each guard is tagged invariant, lint, code or instruction. Every instruction-only rule gets a fixture case, which a model switch reruns, and counts as partly enforced until it has one. |
| Split 8.7 | Its process rows (journey tests before "ready to test", a failing test first, never marking a plan item done on a part) moved to 10.5. |
| Fifteen rules from the running deployment | All are rows in 8.8, each with its guard kind and an honest state. Two are partly built today: pasted inputs are stored by content hash, and the smoke test covers every tier on request. |
| "Targets aren't dates" | Now: a target is a date, a quarter or TBD, never a sentence; the detail goes in the notes. |
| Date from the day received | Now says "not the day processed", and the fix (the received date in the packet header) is in phase A. |
| Follow-up: lessons guarded by an invariant still need a line in the op reference, and frequent refusals should bring the lesson into the packet | Both adopted (Part 8, guard kinds). Every invariant puts a one-line constraint in the reference of the ops it constrains, and the self-check fails when one is missing; some of these lines already exist in the core ops' descriptions. Each run records its refusals by check. A check refusing more than 5% of a task kind's last 50 runs (a setting) brings its full seed lesson into that task kind's packets automatically, until the rate drops. The quality panel shows both. |
| Enforce first for the first real use | Phase A: received date, usage limits resuming at reset, empty or failed runs retried. Phase L, before real use starts at its end: the knowledge rules, verbatim versus paraphrase, attribution, names from a primary source, and links checked. Scope, schedule lookups and dependencies wait for the packs. |

## 15. Your review of Part 6 (2026-10-12)

Each point was checked against the code first. Four were already right in the code and wrong only in the design text (1, 2, 11 and `project.add`);
the rest are new.

| You said | What we found, and what changed |
|---|---|
| 1. The frozen batch prefix hides earlier work in the batch; per-input knowledge breaks the cache | The code builds each packet when its request runs, so it doesn't freeze; the design text did. 6.6 now says so. The knowledge section is split as you suggested: rules, task-kind lessons and a small glossary in the stable part, the rest per input. 6.21 now agrees with 6.22: every active rule goes in. `near-duplicate-question` is a new lint (phase L). |
| 2. Answers mix trusted and untrusted words | The code already separates them: `/answer` takes the PM's own words, and `/reply` hands in someone else's reply as pasted content. 6.8 described one flow and now describes both. Learning from a reply waits for the person, so "not me, ask X" never becomes routing on its own. |
| 3. Facts need supersession | `fact.supersedes`, proposed by the input's run when a new fact covers the same subject; superseded facts leave the packet and stay searchable (phase L). |
| 4. Ask has no knowledge section | It gets the section, with the same citation check (phase L). |
| 5. Remember discards | Discards are kept with their reason, and near-matches aren't shown again for 90 days, a setting (phase L). |
| 6. A direct edit isn't always a correction | The `learn-correction` packet carries the inputs received after the original run on the same records, and defaults to "nothing to generalize" unless the edit contradicts the evidence the run had (phase L). |
| 7. A first name alone is risky | True of the code today: any unique first name resolves. It now resolves only in context (same project, or a participant in the thread), and a different initial or surname fragment is held. Fixed in phase A, since it affects real mail now. |
| 8. "Restart needed" can silently stop the assistant | Held work becomes the first Decide line ("Restart to run 7 waiting requests"), and an account paused until its reset becomes a Risk line with the time (phase A). |
| 9. Today lacks the learning lines | New kinds: `learned`, `learned_daily` and `learned_backlog` under Review; `switch_failed` under Risk; probation work marked under Review (phase L). |
| 10. An agent's version is part of the account | Recorded on each run; a change is treated like a switch (smoke test, then "first run on"); the adapter turns off auto-update where the program allows, from the agents catalog (phase L). |
| 11. Exit 0 with no outbox is a failure | Already a failure in the code (`invalid_output`); nothing is marked done. It becomes its own outcome, `no_output`, counted toward the empty-run rule (phase A). |
| 12. The backlog will arrive all at once | One catch-up list, not individual cards (phase L). |
| 13. Audit 6.8 to 6.11 before phase L | Scheduled as the last item of phase A. |
| Both dates in the packet | Today's date and the input's received date (phase A). |
| `project.add` from the person's own "yes" | Already so in the code: a held op the PM's answer releases is applied as the PM, trusted and confirmed by them. 6.8 now says it. |
| Ending probation early | From the quality panel, once the send-back rate is below a set level over a minimum number of runs. |

## 16. Your review of the roadmap and Part 13 (2026-10-12)

| You said | What changed |
|---|---|
| 1. Start real use after phase A | The owner chose your fallback: real use starts after **L-core**. Your argument for an earlier start is recorded, and the first week of real use serves as the baseline. |
| 2. Split phase L | Done. **L-core** holds the loop, extractors, backup encryption and the writer's first-week rules. It also keeps a few small items you had put in L-more, because real use starts right after it: invariant constraint lines, refusal counts, the catch-up list, fallback-chain checks, and the failed-switch line. **L-more** comes after the packs: Ask's knowledge and learning from Ask, Take my lessons, Part 8 as seed lessons, agent versions, early probation, the unused list, and single-record restore. The exit test applies to L-core. |
| 3. More pairs, and negative ones | 15 to 20 pairs, about a third negative. Your sixteen generic cases are written into the roadmap (L4) as the list to build from. |
| 4. Write the day-30 expectations first | Expected differences are listed before the run and scored like the golden set. The month mixes every case with ordinary noise. |
| 5. Journey tests for silent stops and waking | Added to phase A: limit then resume, exit 0 with no answer, restart as the first Decide line, empty run retried, and the computer sleeping through a batch and waking. |
| 6. Phase C's exit test should include learning | It now requires a correction in a pack's own work to produce a proposal, and a later similar input in that pack to come out right. |
| Volume for the weekly review | A task kind's week counts only with at least 10 corrections (a setting); the first week is the baseline. |
| Drift between 13.4 and the roadmap | 13.4 now lists only the phases and points to the roadmap for contents, sizes and exit tests. Milestone 2's read-backs and glossary are marked as moved. The cache line no longer says the batch prefix is frozen. |
| The governor and a readable export | Phase A now wires the scheduled export rather than removing the setting. Backups copy the database, which isn't readable on its own, so you were right that they didn't cover this. |

## 17. Your review of the golden set (2026-10-12)

Checked against the harness (`engine/evaluate.py`) first.

| You said | What we found, and what changed |
|---|---|
| 1. Pin the date and freeze the clock | The harness already freezes one clock for every case (a Friday, 2026-10-09), so `relative-due-date` is stable. But no case carries its own received date, and the packet gives the processing date. Each case gets `received:`; the clock freezes there, and the packet header carries it. This is the test for phase A's fix. |
| 2. Penalize extra ops | True: only missing ops and a few named forbids are scored. `exact: true` becomes the default (nothing beyond the expected ops except notes and sources), and cases relax it where more is acceptable. |
| 3. Make the workspace busy | True: every case runs on the small fictional workspace. Half the cases will run against a fixture with 30 to 50 open items and near-namesakes. |
| 4. Starting state in `quoted-thread` | Cases gain `given:` records. `quoted-thread` splits into "the action exists, so update its date" and "it doesn't, so add it". |
| 5. Future-proof the hostile cases | `forbid: {tier: system}` and `forbid: {names: <person>}`, so ops that don't exist yet are caught when they arrive. |
| The new cases | All of them. The three that test phase A's fixes (a first name in the thread, "Maya R." held, an unknown person) are written in phase A as the failing tests for those fixes. The rest come with the harder set in L-core. |
| Follow-up: run it now, before the scoring changes, as a before-number; fix milestone 2 | Both. A "before" run of today's set on a low-cost and a stronger account is owner action O1 in the roadmap. It's pinned to today's commit, so the harder set can be built meanwhile, and it only has to exist before the "after" report it's compared with. It runs on the owner's accounts, since the keys live on their computer; the reports go in `docs/project/evals/`. Milestone 2 (13.1) now says the cases and pipeline are built and no real model has been scored yet. |
| The latest `evaluate` report | There isn't one. The set has only been run with the stand-in, which replays each case's scripted answer, as a check of the cases and the pipeline. No real model has been scored on it. Since the scoring as it stands would flatter a low-cost model, the first real report is made after these changes, on the owner's accounts (pass rate per case per model, three runs each), before real use starts. You'll get it then. |

## 18. Your review of Part 7 (2026-10-12)

Checked against the screens and their wording first.

| You said | What we found, and what changed |
|---|---|
| 1. Show which knowledge shaped each output | Adopted for phase L-core: the evidence line shows "Because you told me: …", linked to the entry, and the entry's menu has **This doesn't apply here** (narrow or retire). |
| 2. Set a lesson's reach when keeping it | **Keep for: this project ▾** on the Learned line, defaulting to the narrowest target the correction supports (phase L-core). |
| 3. Silent corrections need a Today line | Right: 7.18 contradicted 6.15. Proposals from silent corrections get one Review line; ones made while the person was there stay on their cards. |
| 4. Follow-ups is missing "Followed up" | True of the screen: Waiting on them offers only They finished it and Record reply, and recording a chase is designed (6.9) but not built. **Followed up** becomes the primary for actions past the nudge threshold, keeping the action open. Phase A, because today the only button closes the action. |
| 5. A "later" batch | Questions already carry `batch` (now or later), but the screen doesn't use it. Follow-ups gets **Later**, per person and collapsed; with meetings, "Hold for <meeting>" (phase B). |
| 6. "This week" at every width | A collapsed Today section, and what the inspector shows when nothing is selected; in the rail from 2560px (phase B). |
| 7. Notifications for "needs you" only | 7.19: opt-in, the Decide group's items only, one line leading with the action, quiet hours (phase B). One limit: a phone gets them only when it can reach the app, which for a local install means the same network; anywhere else waits for hosted mode. |
| 8. Knowledge rows show use | "Used 12 times · last 2 days ago" or "Never used", from the knowledge log (phase B). |
| Follow-up: notifications don't need hosted mode | Right. A notification target is a channel: the browser, mail to the person themselves, or a webhook (a chat app's incoming messages, a push-service topic). It's configured once and checked with "Send me a test", so the phone gets "needs you" anywhere from day one. Two guards. It sends only to the person, which is why it needs no per-message approval. And because a push service or chat app is a third party, it carries a count by default; titles go only to targets allowed for the data level, and restricted items never. |
| The status chip | The restart and pause lines stay on Today even when the chip shows them. |
| Format-only drafts | 7.4 now says they never appear in Waiting to go out. |
| The Add-ons introduction | It does still say "the app never installs anything itself". It is fixed with the Install button in phase A. |

## 19. Your review of Part 12 (2026-10-12)

Checked against the code first.

| You said | What we found, and what changed |
|---|---|
| 1. What Keep does to a proposal from content | Your rule, as written (12.8, 6.22). The kept entry is the assistant's restatement plus its target, shown in full; Keep (or an edit at Keep) makes the person its author, so it becomes guidance. The raw source enters packets only as evidence marked "from outside". |
| 2. Imported lessons are someone else's words | A lessons file loads as proposed, on one review list, with its origin kept. Only the person's own export, signed with their workspace's key, loads as active (phase L-more). |
| 3. A pack's guidance | Shown before turning the pack on, beside what it reaches and keeps; marked by origin in the knowledge log. Precedence: invariants, then the person's rules and lessons, then pack guidance. |
| 4. Origin and Host checks in local mode | Partly built: the session cookie is already `SameSite=Strict`, and the app sends no CORS headers. There is no Host or Origin check, so a DNS-rebinding page could read answers. Both are added in phase A. |
| 5. Never open the local install to the network | True of the code today: `server.host` takes any address in local mode. Local mode will refuse a non-loopback address and say that reaching it from another device needs hosted mode's rules (phase A). Notifications go outward through a channel (7.19), so nothing needs inbound access. |
| 6. Forget-a-person must reach knowledge and evaluations | 12.4 now lists routing entries, style notes, quoting facts and lessons, the knowledge log and private evaluation cases; retention applies to `evals/`. |
| 7. The readable export holds raw inputs | Phase A wires the export to the workspace's own git only. The remote is not offered until phase E gives it the care of backups: the screen says so, a private remote or encryption, restricted sources left out unless the person opts in. |
| 8. A minimal environment for agents | Already built: an agent sees only PATH, HOME, the language settings and the variables its account lists. The dummy-variable check in the lockdown test is added (phase L-more). |
| 9. A shared synced folder | True of the code: outside edits are recorded as the person's own. A `shared` setting, asked when the folder is chosen, makes them content when the folder is shared (phase A). |
| 10. "Keep all" fatigue | Bulk Keep only for glossary terms and facts with evidence; routing, rules and lessons one at a time, with the source beside them. |
| Hostile cases for phase L's roads | Added to the fixture list (L4): a planted lesson, a routing change, a glossary meaning that changes an instruction, an injected import. |
| Log plugin on/off and sign-ins now | Settings saves are already recorded; sign-ins and turning plugins on or off are recorded from phase A. |

## 20. Phase A re-sized (2026-10-12)

Sections 15 to 19 had added about a dozen items to phase A (from about 3 to 5.5 sessions). Its exit test is unchanged.
Phase A now holds only what that test needs, plus the local-mode guards (Host, Origin, loopback only), because the test is
the first time the owner's real mail is in the app.

The rest moved to **L0**, the start of L-core, which still comes before real use:
- the silent-stop fixes and their journey tests, and waking from sleep;
- the received date;
- first names in context, with their golden-set cases;
- the near-duplicate threshold;
- Followed up;
- the audit records;
- the shared-folder setting;
- the 6.8 to 6.11 audit.

Phase A is now about 3.5 sessions and L-core about 11; the total is unchanged. Afterwards, four of A's original items
also moved to where each is first needed:
- a pack's own libraries to C1;
- mailbox passwords on screen to B;
- the two-computer divergence screen and the scheduled export to L0.

Phase A is now about 2.5 sessions.

## 21. Your review of the workplace pack (2026-10-12)

All twelve points are now a new section, **9.5a**, after 9.1 to 9.5, so the existing numbers stay. Each names the core part
it builds on: routing entries for the roles, fact kinds with owners for the two kinds of dates, value lists for the status
rubric, person-owned fields for priority and capacity, scope for the lens, the `ship_release` fact default, and pull-edits
and audiences for pages a group edits. The baseline flow is the pack's own task kind, `workplace-pm/baseline`. The preview
through the dashboard's reader is a reader-preview hook beside the renderer extension point (3.3).

Your practical suggestion is taken as you put it. The repository already has a fictional workplace workspace (`demo-a`,
with 3 projects and 6 actions). In phase L-core it grows into the busy portfolio:
- about 20 projects and 50 open actions;
- near-namesakes;
- three roles;
- a fake dashboard reader.

It is the golden set's busy fixture first, and the pack's demo later.

## 22. Your review of Part 5 (2026-10-12)

Checked against the record definitions in the code: every field gap you named is real.

| You said | What changed |
|---|---|
| A1. Forget-a-person can't work with an append-only ledger and git that's never rewritten | Your option (b), recorded redaction (5.2). `person.forget` replaces the person's values everywhere, including the ledger's before-and-after values, with a marker, and records that it did. The export's git repository stays local until phase E's remote rules exist, and is rebuilt from the database on forget, the one rewrite allowed. A remote is replaced the same way. Backups made before the forget hold the old data until they age out; the screen says when, and offers to delete them at once. Crypto-shredding was set aside because every read and write of a person's values would go through it, for a rare operation. Retention redacts quotes the same way, except evidence kept on purpose. |
| Follow-up: forget across two computers, and undo | Checked: the two computers' histories are compared line by line (`engine/handover.py`), so a redacted line would read as a divergence. The forget is its own ledger entry; the comparison applies every forget in either history to both before comparing; the loading computer replays it on its own database. Undo restores the marker, never the value, and lists those fields as "forgotten, not restored". Each has a test (5.2, phase E). |
| B2. Discarded, expired and retired | Three states: `discarded` (with `discard_reason`; it suppresses near-matches for 90 days), `expired` (counted; it suppresses nothing) and `retired`. |
| B3. Fields the Keep rule depends on | Every knowledge record has `origin` (correction, input, ask, import, pack, seed), its own `text` (the restatement) kept apart from the evidence quote, and `kept_by` and `kept_at`. Seed lessons have `guard_kind` and `fixture_ids`. |
| B4. Priority isn't person-only | Right: only `budget_usd` and `content_levels` were. `project.priority` is now person-only: the assistant's `record.set` of it is held for the person. **Built:** `tests/test_projects_series.py::test_the_assistant_never_sets_a_projects_priority_but_the_person_does`. Capacity is a workplace pack field, not core. |
| B5. Actions can't record who did the work | Right: the code has only `told`. Actions gain `followed_up` (a chase, separate from a notice), `done_by` and `reported_by`, with Followed up in L0. Now in the code; 5.1, 6.9 and 7.5 cite the tests. |
| B6. Sources have no data level | Right: the level lives on the request (`sensitivity`, which only raises the record type's level) and isn't kept on the source. Sources and files gain `data_level` (phase L0); audience restrictions stay designed. |
| B7. Out-of-date text | All five fixed: no off-site claim (the remote is phase E); "before every migration and every add-on install or update"; the scheduler lease marked designed; backup encryption; the shared-folder rule beside `text.propose`. |
| C8. Values need a meaning | Each value has a tone, and a status value a meaning, read by the ranking, the at-risk lines and colors, never the label (phase B). |
| C9. Retention breaks evidence | Evidence quotes are kept with their ops. The source shows "removed by retention on <date>" with the quotes visible, and `excerpts: never` is respected. |
| C10. Smaller gaps | `question.held_for` (phase B), `signal.run` and `signal.changeset` (L-core), `person.verified` (L-core). |

## 23. Your review of the repository's CLAUDE.md (2026-10-12)

All five points, and the two lines on subagents, are in the file.

| You said | What changed |
|---|---|
| 1. Separate rules in force from rules only designed | A new section, "Not built yet: don't call it or assume it", sits right before the product rules. One line each, with its phase: the scope resolver, fact lookups, read-backs and the rules review, the publisher and channels, `record.rename`, the governor, knowledge in packets, and the L0 fixes. A line is removed in the change that builds it. |
| 2. Rules that keep the learning loop whole | Under the learning rule: every AI task kind gets the knowledge section and writes its knowledge log (a self-check failure from L-core); every way to change, undo, reject or redo the assistant's work records a signal; a wrong behavior gets a fixture, not only a code test. |
| 3. The lessons from switching providers | Added to "AI providers", with "a quick fix must never undo these". |
| 4. Section 19's safety rules | Added to "Data and safety model": loopback with Host and Origin checks; Keep authors the restatement; origin marking and what makes guidance active; forgetting and retention reaching knowledge and evaluations; notification counts. |
| 5. Missing product rules | Added: no silent stops; Today only what the person does, verb first; a nudge isn't completion; canonical values and no remaining difference after a publish; evaluation cases with received dates, starting records and `exact` by default. |
| Subagents and wrong premises | Every brief states the expected starting state, for the subagent to check. A subagent's "can't be done" or "needs a new op" comes back to the main session, never straight into a design change or a report. |

## 24. Your review of the project review (2026-10-12)

| You said | What changed |
|---|---|
| 1. Nothing catches the next lost promise | Done, and running in this repository now. Every commitment is written in the same turn to the roadmap or to `docs/project/open-promises.md`, which starts with five open items. A project hook (`.claude/settings.json`) prints the list, with "compare the conversation with this list and write down what's missing", when a session starts, resumes or comes back from a compaction, and reminds it before one. A promise leaves only with its test, or when the owner withdraws it. The rule is in `CLAUDE.md`. |
| 2. "Done" checked mechanically | A "Built" row or a checked roadmap box cites its test, and the self-check fails when a cited test doesn't exist (phase L0; the "built claims" step, 10.5). The fifth claimed-done item you found (milestone 2's evaluation run) is added to the review. |
| 3. The wording rule at the response boundary | In tests and dev mode, the API's response serializer refuses user-facing text with `.yaml`, `env:`, a dotted key path or a command, so the journey tests fail on the first leak, runtime messages included (phase A2, beside rewriting the known strings). |
| 4. A ceiling as well as a floor | The first-five-minutes brief says what those minutes cost at most (`CLAUDE.md`), and the first run after setup shows its estimate even below the confirm amount (design 7.8, phase A2). |
| Section 4 is superseded | Marked so, pointing to the roadmap. |
| Section 5 should be checked off | Each row has a state: eight fixed in the design text, and one (the near-duplicate threshold) fixed in the text with the code setting built afterwards (`tuning.near_duplicate_action.similarity`, 4.17). |

## 25. Phase A starts: what the code showed (2026-10-12)

Each phase A item was checked in the code before it was designed. Three gaps were worse than the plan said.

| Item | What the code does today | What phase A builds |
|---|---|---|
| Crashed runs | A run left `running` by a crash is never picked up again | Queued again on start; held for the person if found stuck twice (6.13). **Built (A2):** interruptions are counted from the request's ledger, since `attempts` also counts a person's Try again (`tests/test_requeue.py`) |
| Test source | "A stand-in source for tests" is offered under Add a source | Connectors can be marked test-only and aren't offered. **Built (A2):** `tests/test_watch.py::test_the_test_only_kind_is_not_offered_but_a_source_set_up_with_it_still_reads_and_shows` |
| Check now | The source's Read now and the schedule can read one source at the same moment; Came in has no refresh | A lock per source, and Check now on Came in (7.15). **Built (A2):** `tests/test_watch.py::test_a_source_already_being_read_is_not_read_twice` and `tests/test_today_dashboard.py::test_check_now_reads_every_source_and_one_that_fails_never_stops_the_rest` |
| Backups | Nothing restores one | `cockpit restore --backup` makes a workspace from one dated backup (5.0). **Built (A1):** `tests/test_update_restore.py::test_a_restored_backup_has_the_same_records_and_ledger_and_opens_as_a_workspace` |
| First run's cost | No notion of a first run | The first runs wait for one Go with their total (7.8, `ai.budgets.first_go`). **Built (A2):** `tests/test_first_go.py` |
| Local guards | No `Host` or `Origin` check; any listening address | The allowed hosts and origins, and loopback only in local mode (12.1). **Built (A2):** `tests/test_local_guards.py` |
| Install | The route existed; the screen had no button | Install, Update now and Remove (3.11). Only updating a running pack holds work until the restart. **Built (A2):** `tests/test_pack_install.py` |
| Acceptance scenario, step 7 | The header chip said "Backup needed" until a backup succeeded and then only "Live", with the age in the popover; Today never mentioned a backup | A backup line on Today while a backup needs attention, and the age on the chip itself (7.1, 7.7). **Built (A3):** `BackupLine.test.tsx` and `StatusMenu.test.tsx` |
| Personal and sales mail | Nothing tells it apart; it reaches the assistant like work mail | A Set aside folder: the person's rules, the mail's own category and bulk headers, then a header-only sorting run; it never reaches the assistant or learning (6.5, L0) |
| Sales and social mail set aside by rules | Every mail item reached the assistant, one AI run each, and the service's tabs can't be relied on | Mail items carry `bulk` and `categories` (plugin API 0.3.57); the core sets aside bulk, promotions, social and forums mail as sales mail with no AI run, built in and turned off by one setting (`watch.set_aside_defaults`), after the person's own sender and domain rules (`sender-rule`; `set_aside: never` keeps mail). A Set aside folder in Sources, Came in's "N set aside", one-click "Set aside: personal"/"sales" and "This is work", each offering "Always for this sender/domain"; Confirm learns a sender rule and deletes the message's content from the app after the undo time, keeping a marker (6.5; A5, **Built**: `tests/test_set_aside.py`, `src/components/SetAside.test.tsx`, J2 in `web/e2e/journeys-mail.spec.ts`). The header-only sorting run and the learning proof stay in L0 |
| Onboarding | A setup guide reached from a line on Today; mail and calendar last, add-ons installed elsewhere, a restart per step | A new-start walkthrough that opens by itself: You, AI account, Mail and calendar (install, one restart, sign in), Backups, People, Done on the first-Go line; and a getting-started page (7.8, A4) |
| Mail and calendar services | The walkthrough told a mail or calendar connector from a word list in its name | A connector declares what it reads, in its registration and in the manifest, so an add-on in a catalog is offered too; the word list stays only for a connector that does not declare it (3.2, 3.3, 7.8; plugin API 0.3.56) |
| Wording | Checked only in the screens' own wording file | Screen text typed in the API models and checked when it leaves, in tests and development. **Built (A2):** the audit's 47 strings and every further leak the tests found rewritten; a secret field's input hint is the one exemption until phase B (`tests/test_screen_text.py`, `web/src/wording/wording.test.ts`) |
| Agent errors | A Claude Code account failed its test with "other: the agent stopped with exit code 1": the agent puts its reason on its output, which wasn't read, and it couldn't see the user name its keychain sign-in is kept under | The user name and temporary folder reach the agent; `agent.errors.report_on_output` reads a failed run's output as its error report; a failed test reads in plain words (6.16). **Built:** `tests/test_cli_agent.py` |
| Focus rings | A row's ring was drawn 4px inside rows with no side padding, over their text, and showed after a click | Keyboard focus only, inside the padding or outside the row (7.10). **Built:** the focus ring test in `web/e2e/acceptance.spec.ts` |
| A question handed in | "how does this application work?" in the hand-in box failed as notes, and the failure named internal terms | The person's own note that is a question becomes an ask; an unreadable answer says so in plain words (6.25). **Built:** `tests/test_pipeline.py` |
| The walkthrough's return | It opened by itself every visit until Finish later or the last button, so an optional step brought it back | Every visit only while You or an AI account is missing; otherwise only the first visit; a sign-in returns to the screen it started from (7.8). **Built:** `tests/test_walkthrough.py`, `src/components/SignIns.test.tsx` |
| The app's own add-ons | The example and the kit were listed in setup as the person's add-ons to turn on | Not in setup; on the Add-ons screen only once on, or in a sandbox (7.8). **Built:** `tests/test_walkthrough.py` |
| Labels and answers | 16 core ops had no label ("op.answer" showed); an answer showed its first 150 characters | Every core op has a label; an answer shows whole (7.4). **Built:** `tests/test_wording.py` |
| The app's own calendar | The agenda showed only connected calendars; a dated item was only a fact | A core calendar; a dated item becomes an entry beside its fact (1, 6.7, 7.7; the PM pack builds on it). **Built:** the `event` record and `event.add`, the agenda showing the entries after the connected events on each day they cover, marked "From your notes"; `tests/test_calendar_entries.py`, `web/src/components/TodayRail.test.tsx`, the golden case `delivery-window`. The learning pair waits for L-core (L4) |

## 26. Phase L0: first names in context and the received date (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A bare first name | Any first name one person had resolved to that person, with no context | Resolves only for a person in the input's context (6.11): the PM, the sender and the others on the message, the project's people. Built: `tests/test_names.py` |
| "Maya R." | Unknown, with no candidates | A first name with a fragment that fits no one is held with the people who share the first name |
| Who is on a message | A mail item carried a sender only | `participants` on a mail item (plugin API 0.3.58, optional); the core's mail folder fills it from To and Cc |
| The received date | The source was dated when the app read it, and the packet gave the processing date | The source is dated by the item's own received time, and the packet states the day the input was received, in the workspace's time zone |
| Golden cases | One frozen clock for every case | Every case has `received:` and the clock freezes there; three new cases for these fixes |

## 27. Phase L0: the audit's fixes to names and questions (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| "Who is X?" | One question per held op, even for one name | One per name per input; answering it applies every op waiting on it (6.11). Built: `tests/test_pipeline.py::test_one_unknown_name_in_two_ops_gets_one_question_and_one_answer_releases_both` |
| The answer | Recorded nothing | A `routed` signal with the person chosen (6.20). Built: `tests/test_pipeline.py::test_saying_who_a_name_is_and_picking_an_owner_each_record_a_routed_signal` |
| Undoing the person's own release | Recorded `undone` against the assistant | Records nothing. Built: `tests/test_pipeline.py::test_undoing_a_release_records_no_undone_signal_but_undoing_the_assistants_work_does` |

## 28. Phase L0: 6.8 to 6.11 say what is built and what is designed (2026-10-13)

Sections 6.8 to 6.11 were compared with the code. No behavior changed; their text now says, for each rule the code doesn't
yet follow, that it is *designed*, with its phase.

| Item | What the section said | What it says now |
|---|---|---|
| Question `key`, `on_answer`, `batch`, link enrichment, the pending flag, the re-check of other open questions | Present tense | Designed, not yet built, not scheduled |
| Reword, reroute, drop, move a question; "not me, ask X"; narrowing; the feedback run from the named item's state; learning from the PM's own answer | Present tense | Designed, phase L3 (one sub-item added to L3) |
| `near-duplicate-question` | Phase L | Phase L2 |
| `owner_format` in rendering | Present tense | Designed, phase L0 (Followed up, `done_by` and `reported_by` were built in the same phase, section 6.9) |
| Reassign | Present tense | Designed, phase B |
| Meeting sync; escalation suggestion | Present tense | Designed, phase C2 (project management pack) |
| Edits pulled back from published pages | Present tense | Designed, phase C4 |
| One store interface over every action store; the notice baseline date; `track_only` notices; `owner_format` parsing; `person.merge` | Present tense | Designed, not yet built, not scheduled |
| 6.7, links enriched before apply | Present tense | Designed, not yet built |

## 29. Phase L0: set-aside corrections, learning and the synced folder (2026-10-13)

| Item | Before | Now |
|---|---|---|
| Signal kinds (5.1, 6.20) | "Set aside" corrections recorded nothing | A `set_aside` kind, recorded when mail is set aside by hand; putting it back records none |
| Learning and set-aside mail (6.5) | Stated, not guarded | `engine.set_aside.learnable` is the one place learning reads requests and snapshots; it leaves out set-aside ones. The learning pair waits for L4 |
| Synced-folder comparison (5.2) | A confirmed set-aside's deletion rewrote earlier ledger entries on one computer, which read as a divergence on the other | Each deletion found in either history is applied to both before comparing |

## 30. Phase L0: where the code and the design differed, decided (2026-10-13)

| Item | Before | Now |
|---|---|---|
| A question's kind (6.8) | The design said whether something is a decision is decided by the recipient, never by a stored kind; Follow-ups showed every question to the PM as a decision | The assistant marks the kind and the screen follows it: a question to the PM of kind `decision` shows as a decision, `question` as a question to answer. Built: `web/src/components/FollowUps.test.tsx` ("a question to the PM shows as a decision or as a question by its stored kind") |
| "me", "myself", "I" (6.11) | English words in code | The setting `language.self_words` (4.6), default those three. Built: `tests/test_names.py::test_the_words_that_mean_the_person_come_from_the_language_setting` |
| A greeting's first name (6.11, 5.1) | The first word of the full name | The person record's optional `first_name`, else the first word; the person form has the field. Built: `tests/test_names.py::test_a_greeting_uses_the_first_name_on_the_record_else_the_first_word_of_the_full_name` |
| `owner_format` (4.1, 6.11) | In the schema, read nowhere | Read where the app shows an action's owners; checked when set (must hold `{full_name}`; `{team}` optional). Parsing an owner written in it stays designed, not scheduled. Built: `tests/test_names.py::test_an_owner_is_written_in_the_owner_format_with_the_team_on_the_entry_else_the_persons_own` |
| An action changed after it was told (6.9) | Stayed "told" | Counts as to send again for that person. Built: `tests/test_followups_backup_eval.py::test_a_changed_due_date_or_text_after_telling_puts_the_action_back_to_send_for_that_person` |
| Names resolve on which fields (6.11) | Unsaid | Two: an action's owners and a question's recipient; every other field is picked from a list |

## 31. Phase L0: no silent stops (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A usage limit | A quota or a long request to wait stopped the request for the person, and nothing resumed it | The account is paused until the reset (kept on disk, so it holds across a restart); the waiting requests say "Waiting for <account>'s limit to reset at <time>" and run again by themselves then (6.16, 8.6). Built: `tests/test_silent_stops.py::test_waiting_requests_resume_by_themselves_at_the_reset_without_anyone_pressing_anything` |
| An empty or failed run | The request stopped for the person at once, and Try again was by hand | Retried by itself `dispatch.retries` times (2) with a wait that doubles from `dispatch.retry_wait_seconds` (30), then it comes to the person saying how many times it was tried and why (8.6). Built: `tests/test_silent_stops.py::test_an_empty_answer_is_retried_with_a_growing_wait_then_goes_to_the_person_with_why` |
| An agent that exits 0 with no answer | Empty output was an answer that failed to parse, a missing answer file was `invalid_output` | Its own outcome, `no_output`, retried like the above (6.16). Built: `tests/test_silent_stops.py::test_a_program_that_exits_cleanly_with_nothing_on_its_output_is_no_output_never_an_empty_answer` |
| A reset time from an agent | Not read | `errors.reset` patterns (seconds, or an ISO date and time) give an agent's reset time from its error stream (6.16) |
| Held work and paused accounts on Today | Only the header's restart chip and each request's own waiting text | Queue lines `restart` (first Decide line, with the count) and `paused` (Risk, with the time and the count waiting) (6.15). Built: `tests/test_silent_stops.py::test_held_work_is_the_first_decide_line_with_its_count_and_nothing_restarts`. The Today screen draws both lines at the top of Today (Restart now; AI accounts): `web/src/shell/HeldLines.test.tsx::Restart now calls the restart route, and only the click does`; the full ranked queue is phase B |
| Waking after sleep | No test covered it; a source showed the time of its last try as its last read, and Today said "Checked" at the time of a try that found no network | A read missed in sleep runs once on waking; a try that finds no network files nothing and is not counted as a read; a source's `read_at` is when it last actually read, and the screens show that (8.6). Built: `tests/test_journeys.py::test_j11_a_scheduled_read_missed_in_sleep_runs_once_on_waking_and_a_lost_network_files_nothing`, `web/src/lib/sources.test.ts`. Left: a lost connection to an AI account is still counted as a failing service (roadmap, L0) |
| The scheduled readable export | The setting `storage.export.every_minutes` was read by nothing; only `cockpit export` wrote the readable copy | The worker writes the export and commits it to the workspace's own git every `every_minutes` (60) while the app runs, catching up at once after sleep; a workspace with no git gets none and the log says so once; nothing is ever pushed, and `remote` stays unused until phase E (4.15, 5.0, 12.1). Built: `tests/test_export_schedule.py::test_the_scheduled_export_is_committed_on_the_interval_and_never_pushed` |

## 32. Phase L0: a wording lint on an internal item warns without a fix round (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A `return` wording lint (blocked wording, run-on list) on an item that stays internal | Sent the whole changeset back to the assistant, so a blocked word in an action cost a second request (and a third on the stronger tier) | Applies with a warning on the row; only an item that reaches another person gets the fix round and is held if it still fails (6.7). Lints about correctness (near-duplicate, evidence fit) keep their configured severity. Lints read only the assistant's own words, never the quoted evidence. Built: `tests/test_pipeline.py::test_a_blocked_word_in_an_internal_items_own_words_warns_without_a_second_request`, `tests/test_pipeline.py::test_a_blocked_word_in_the_quoted_evidence_costs_one_request_and_no_warning`, `tests/test_near_duplicate.py::test_a_near_duplicate_on_an_internal_item_still_returns` |
| Why an add-on didn't load | A manifest or plugin-settings failure showed the validator's own text (field paths, error types, a link); a few registration messages named manifest fields or a settings file | Said as where and what in plain words; the wording check also catches `interfaces.*`, `depends_on` and `config_schema` (7.0, 7.1). Built: `tests/test_plugin_messages.py` |
| How Ask names a setting | Each settings line in Ask's material ended with the setting's key, which an answer could quote onto the screen | Each line names the setting by its screen name and a setting code (`s-` and six characters of a hash of the key, longer for keys that would match); `setting.propose` takes `setting` (the code) instead of `key` and the applier resolves it against the settings shown, refusing an unknown code in plain words; the proposal keeps the resolved key, and the answer, its quotes and the proposal's reason are typed as screen text so the wording check sees them (6.25). Built: `tests/test_ask.py::test_a_setting_handle_is_short_and_stays_the_same`, `test_the_material_names_settings_by_a_code_and_never_by_a_key`, `test_a_handle_resolves_among_the_current_settings_and_an_unknown_one_is_refused`, `test_handles_that_collide_get_longer_so_each_names_one_setting`, `test_an_answer_rests_on_quoted_words_and_suggests_a_setting` (a proposal naming a code applies through the settings save), `test_a_suggestion_naming_an_unknown_setting_code_is_refused`, `test_an_answer_that_cites_a_settings_line_shows_no_settings_key` |

## 33. Phase L0: input levels, folders in the last day, local timestamps (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| Data level of sources and files | Only a request carried it (`sensitivity`); a source read later had none | `source` and `file` carry `sensitivity` (their data level). A hand-in's choice, an upload's choice, or a watched source's setting (else its kind's in `watch.connector_data_levels`, else `watch.default_data_level`) sets it; a run's level is the highest of its record type, its request and its source (4.x, 5.1, 6.16). Built: `tests/test_data_levels.py` |
| "Look at the last day" for a folder | Folder items carried no time, so nothing was handed in | The folder connector gives each file's modified time; the snapshot keeps it as `changed_at` (5.1) and the recent hand-in reads it. Built: `tests/test_watch_recent.py` |
| Machine timestamps in filed notes | The add-on's item text carries a date-time with its zone; the assistant copied it into the note | Timestamps with a zone in the prose of an assistant's ops are rewritten in the person's time zone and `language.messages.date_time_format` before they are kept (6.7). Built: `tests/test_moments.py` |

## 34. Phase L0: the synced folder settled from a screen, the audit trail, the shared folder (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| Diverged copies | `cockpit serve` refused to start; the choice was `cockpit sync keep` | The app starts on this computer's copy and writes nothing to the folder and does not take its lease. Today has a line (Choose which copy to keep) that opens a page showing both sides (changes, latest, computer) and the two choices with what each does. A choice is only noted; the next start carries it out through `keep` before the database is opened, so its lease check holds (5.0, 7.7). Built: `tests/test_handover_screen.py::test_a_choice_is_carried_out_at_the_next_start_and_the_other_side_is_saved`, `::test_a_choice_still_meets_the_leases_check_when_it_is_carried_out`, `::test_a_held_worker_writes_nothing_and_leaves_the_lease_alone`, `::test_today_has_a_line_and_the_page_shows_both_sides`; `web/src/components/Handover.test.tsx`, `web/src/shell/HeldLines.test.tsx` |
| Another computer has the workspace | A running copy stopped writing and said so only in the Setup panel | The same Today line (Close this copy) and the page say who, since when and the wait. Built: `tests/test_handover_screen.py::test_a_copy_that_lost_the_workspace_to_the_other_computer_says_so` |
| The audit trail | Settings changes were recorded; sign-ins, sign-outs and turning add-ons on or off were not (12.1) | Each is an `audit_entry` record, written in the same transaction as the change where there is one; never a token, a secret or the account's name. No screen lists them yet (the Admin tab is phase E); they are in the ledger and the export. Built: `tests/test_audit.py` |
| A shared synced folder | Outside edits always counted as the person's own | `storage.sync.shared` (false), asked when the folder is chosen and changeable on the folder's panel (a live setting). From a shared folder an outside edit is filed as an outside input, its changeset and every write are untrusted, and its notes say it may be someone else's change; the person's review is unchanged (5.0, 12.8). Built: `tests/test_shared_folder.py` |

## 35. Phase L0: no domain rule for a public mail domain (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| "Always for this domain" for a personal address | Offered for any sender's domain, so one click could set aside or keep every contact at a free mail service | A shipped list of public mail domains (`engine/defaults/public_mail_domains.yaml`) plus `watch.public_mail_domains_extra` (empty by default, live). For a public domain the Set aside rows, "This is work", "Set aside" and Confirm all carry no domain, so only the sender rule is offered; the sorting-rule save refuses a public domain in plain words. A match is exact (case ignored), not by parent domain (4.x, 6.5). Built: `tests/test_set_aside.py::test_a_public_mail_domain_is_the_shipped_list_plus_the_persons_own_and_matches_exactly`, `test_a_set_aside_row_and_this_is_work_offer_no_domain_for_a_public_domain`, `test_confirm_all_offers_no_domain_for_three_senders_on_a_public_domain_but_does_for_a_company`, `test_a_domain_rule_for_a_public_domain_is_refused_in_plain_words_and_nothing_is_saved`; `src/components/SetAside.test.tsx` |

## 36. Copy puts formatted text and plain text on the clipboard together (2026-10-13)

| Item | Before | Now |
|---|---|---|
| What Copy puts on the clipboard | Plain text only; the work version the owner uses opens a generated page with its own copy button | The message as previewed, in two versions at once (formatted for mail and documents, plain for chat); Copy as plain text in the menu; built by the app with every piece of text escaped, never a separate page (7.5). Decided, not built (roadmap phase B) |

## 37. Phase L0: what the browser-test failures left (2026-10-13)

| Item | Before | Now |
|---|---|---|
| An add-on's install note after the restart it asked for (3.11) | The note and its Restart now stayed on the row after the restart, saying one was still needed | The note goes once the app has come back from a restart (the app's start differs from the one it was made on); a restart still to come keeps it. The packs list is read again at that point |
| Small state files in the workspace's private folder (4.24) | Several were written in place and some were read, changed and written by more than one thread | Every one is written whole through one helper; the ones with a read-change-write hold a per-file lock (sign-ins' started sources, the install id and token made once, the model catalog copy). The backup, connection-test and export results read as "nothing kept" when unreadable instead of failing |
| Came in's "N set aside" (6.5) | Counted items the person had confirmed, which have left the folder it opens, so the count and the folder disagreed | Counts what the folder lists |

## 38. Phase L0: a lost network waits, without using up tries (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A call that can't connect | `provider_down`, the same as a service that is failing: a request run just after waking with no network was tried three times in about a minute and a half, then came to the person | A new error kind `offline`: no connection could be made at all (the OpenAI-compatible adapter: a connect error, which covers a name that didn't resolve). Any answer from the service, a 5xx included, and any other break stay `provider_down`. A refused connection to an account whose address is on this computer is `provider_down` (a stopped local server is no lost network). The command-line agent adapter is unchanged (none of its errors says plainly that no connection was made) (6.16). Built: `tests/test_ai.py::test_a_timeout_no_connection_at_all_and_a_broken_exchange_are_their_own_kinds`, `::test_a_service_that_answers_with_a_failure_is_down_not_offline` |
| Accounts in a chain | A connection failure was `provider_down` and fell through to the next account | The router still tries the next account on `offline`; when every account that isn't paused is offline the call ends in `NetworkOffline` (6.16). Built: `tests/test_ai.py::test_the_next_account_is_tried_when_one_has_no_connection`, `::test_every_account_without_a_connection_is_the_network_being_offline`, `::test_one_account_without_a_connection_and_another_refusing_the_key_is_not_the_network` |
| The request | Counted a try, waited 30 then 60 seconds, then stopped for the person | Stays queued, says "Waiting for the network since <time>. Checking again at <time>.", cause `offline` with `since` and `until`, `retries` unchanged, looked at again after `dispatch.offline_check_seconds` (60) by the worker, never in a loop, never brought to the person for being offline; only the first miss of a wait is a run record (8.6). Built: `tests/test_silent_stops.py::test_a_lost_network_waits_without_counting_a_try_and_runs_when_the_network_is_back`, `::test_a_lost_network_never_reaches_the_person_however_long_it_lasts`, `::test_a_service_that_is_down_still_counts_its_tries`, `tests/test_journeys.py::test_j12_a_request_run_with_no_network_waits_for_it_and_runs_once_when_it_is_back` |
| Today | Nothing said the work was waiting for the network | One risk line, however many requests wait, once the oldest has waited `dispatch.offline_line_after_minutes` (15): check the network connection, with the count and since when; gone when the work runs again (7.7). The queue route now reads the worker's clock. Built: `tests/test_silent_stops.py::test_a_lost_network_is_one_today_line_after_the_configured_minutes_and_goes_when_it_is_back`, `web/src/shell/HeldLines.test.tsx` |
| Settings | n/a | `dispatch.offline_check_seconds` and `dispatch.offline_line_after_minutes`, with descriptions and demo values in both workspaces (4.9) |

## 39. Phase L0: the assistant's header-only mail sorting (2026-10-13)

| Item | Before | Now |
|---|---|---|
| Mail the rules can't place | Handed in to the assistant as work, newsletters and personal mail included | With `watch.sorting: ai` (the default), one run per `watch.sorting_batch` (25) of headers (sender, subject, the service's categories; never the body) answers work, personal or sales; a missing or unknown answer is work; a failing check goes back once, then escalates once, then everything is work. Personal and sales set the mail aside with the reason "the assistant sorted it as personal mail" (or sales), before anything is queued; "This is work", the sorting rules and Confirm work as for mail a rule set aside (6.5). Built: `tests/test_mail_sorting.py::test_thirty_unsorted_messages_with_a_batch_of_25_make_two_runs_and_the_packet_holds_no_body`, `::test_personal_and_sales_are_set_aside_with_the_reason_and_the_rest_is_handed_in_as_work`, `::test_the_check_reads_answers_by_id_and_refuses_unknown_and_repeated_ids`, `::test_an_answer_that_keeps_failing_is_tried_once_on_the_stronger_tier_then_everything_is_work`, `::test_sorting_rules_makes_no_run` |
| When the run can't be made | (no run existed) | No account for the tier, a per-kind budget used up, no first go, or an estimate above the amount to ask about: the mail is handed in as work and the read's note says why; the same cause shows on the handed-in requests by the paths that already exist. Built: `tests/test_mail_sorting.py::test_when_the_run_cant_be_made_the_mail_is_handed_in_as_work_and_the_reason_is_given`, `::test_a_batch_that_cant_run_stops_the_rest_of_the_read_instead_of_trying_each` |
| The first go | Before the first go the run wasn't made, so the first read's mail all went in as work and the go would have run every newsletter | The go sorts first: mail requests waiting for it that were never sorted go through the sorting run (covered by the go), personal and sales are closed as set aside, only the rest run. `Run.request` is now optional (none for a run that serves no request, such as sorting). Built: `tests/test_mail_sorting.py::test_the_first_go_sorts_the_mail_handed_in_before_it_sets_aside_the_newsletter_and_runs_only_the_work`, `::test_the_first_go_leaves_alone_mail_the_person_pulled_back_as_work` |
| Exit check: set-aside mail teaches nothing | Proved for mail a rule or the person set aside | Also for mail the assistant sorted: no request, signal or knowledge; "This is work" hands it in and records `pulled_back`; the learning pair (a sender sorted wrongly, corrected, the next message from that sender kept) is a test, since no learning-pair fixture format exists yet. Built: `tests/test_mail_sorting.py::test_mail_the_assistant_set_aside_gives_no_request_signal_or_knowledge_and_this_is_work_hands_it_in`, `::test_learning_pair_a_sender_the_assistant_got_wrong_is_kept_next_time` |
| The walkthrough's Mail step | A hint that set-aside mail "can be turned off", with no control | A switch, "Let the assistant sort what the rules can't", on by default, saved as a live setting with a read-back and Undo. Built: `web/src/components/Walkthrough.test.tsx` ("the assistant's sorting of what the rules can't place is on by default and one switch turns it off") |

## 40. Phase L0: a start takes over from a stopped copy on this computer (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| The instance lease's holder | A random id | `<process id>-<random>`; an id with no process id is unknown (5.0) |
| A start that finds a lease not yet expired | Refused every time, for up to a minute, and told the person to run `cockpit takeover` | Takes the lease at once and logs one line when it was written on this computer by a process that is no longer running; refuses a running process, another computer and an id with no process id as before. Where the platform has no safe check (Windows) the answer is unknown and the lease is refused (5.0). Built: `tests/test_lease.py::test_a_lease_left_by_a_stopped_copy_on_this_computer_is_taken_without_force`, `::test_a_lease_whose_process_is_running_is_refused_and_says_it_is_open_here`, `::test_a_lease_from_another_computer_is_refused_and_names_it`, `::test_a_holder_id_without_a_process_is_refused_as_before`, `::test_a_new_lease_names_this_process_in_its_holder_id` |
| The refusal | "Already open on <host>, close it there, or run the command once that copy has stopped" | Says where: "It is already open in another window on this computer. Close it there." or on the other computer by its name; the command is named only where this computer can't tell the copy has stopped |

## 41. Phase L0: a file kind's default data level (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A file kind's level (3.3, 5.3) | A file kind had no level: every upload arrived as internal, so an unpublished document uploaded to be imported could be sent to an account allowed only internal material | `registrar.file_kind(..., data_level=)` (`open`, `internal` or `restricted`; none is internal). A level the manifest's `requires.data_levels` doesn't list refuses the add-on, as for a record type. A file added under the kind takes its level; a file a person action makes takes it too. Plugin API 0.3.61. Built: `tests/test_file_kind_levels.py::test_a_restricted_kinds_file_is_restricted_with_no_choice_and_the_persons_lower_choice_is_kept`, `::test_a_manifest_that_doesnt_list_the_level_is_refused_in_plain_words`, `::test_a_file_kinds_level_must_be_one_of_the_three`, `::test_a_file_a_person_action_makes_takes_the_kinds_level` |
| The upload's choice (5.3) | `POST /files` defaulted `data_level` to internal, so "no choice" and "internal" were the same | `data_level` is optional: left out, the file takes its kind's level; given, the person's choice stands, lower or higher. The upload screen has no level picker and sends none, so a screen upload takes its kind's level. Built: `tests/test_file_kind_levels.py::test_an_upload_with_no_choice_takes_the_kinds_level_and_an_explicit_choice_stands` |
| A run about a file (6.16, 5.1) | The level kept on a file or a source counted only through a request's own `source`; a run about the file itself was at its record type's level, internal | A run about a file or a source is also at the level kept on it, so it goes only to an account allowed that level. Built: `tests/test_file_kind_levels.py::test_a_run_on_a_restricted_file_goes_only_to_an_account_allowed_restricted` |
| Working copies (5.0, 5.3) | The file a working copy wrote (hand-out, take-back) was a plain internal attachment, whatever the record it was made from | It takes the highest of its record type's level and the level kept on the record itself, so a copy of a restricted record is restricted and a run on it goes only to an account allowed that. Built: `tests/test_file_kind_levels.py::test_a_working_copy_of_a_restricted_record_is_restricted_and_a_run_on_it_needs_such_an_account` |
| Changing a file's level afterwards (5.1) | Person-only, by the record's declaration | Unchanged; confirmed: a pack's ops cannot write core records. Built: `tests/test_file_kind_levels.py::test_a_pack_cannot_change_a_files_level_afterwards` |

## 42. Phase L0: the original designer's review (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A lost network and an account's pause (6.16, 8.6) | `offline` was already never a pause (only a usage limit is); nothing proved it, and nothing lifted a pause when the account answered | Proved for every path that pauses or marks an account. A call that answers lifts any pause on its account, a usage-limit pause included; so does an answered connection test. Built: `tests/test_silent_stops.py::test_a_lost_network_pauses_no_account_however_often_it_is_found_and_whichever_account_is_cut_off`, `::test_a_successful_run_clears_a_pause_on_its_account_even_one_set_while_it_was_running`, `::test_a_connection_test_that_is_answered_lifts_the_pause_on_its_account_and_a_failed_one_does_not` |
| A lost network and "failing" (6.16) | A connection test that found no network failed the assistant's state (the chip said it could not use its account), and a later run that found no network hid a refused key | A test that only found no network is inconclusive: not kept, the last real result stands (never tested: "untested", not "failing"). Runs that found no network are left out when the latest run is read for a refused key. Built: `tests/test_silent_stops.py::test_a_lost_network_never_makes_the_assistant_failing_or_hides_a_real_failure`, `::test_a_connection_test_that_finds_no_network_is_not_kept_and_leaves_the_last_result_standing` |
| The header's status (7.1) | Said nothing about work waiting for the network | The chip says "Waiting for the network" while any request waits (after a lost live connection, before a restart or a backup); the popover gives the count and since when. `GET /api/status` gains `network_wait`. Built: `web/src/shell/status.test.ts`, `web/src/shell/StatusMenu.test.tsx`, `tests/test_journeys.py::test_j12_a_request_run_with_no_network_waits_for_it_and_runs_once_when_it_is_back` |
| `dispatch.offline_line_after_minutes` (4.9) | 15 | 60 (schema default and description; both demo workspaces) |
| Text where text belongs (6.7) | A declared text field given a mapping failed the whole answer with the validator's words; the loosely typed fields (`record.set`'s value, `record.edit`'s fields, `setting.propose`'s value) were checked only by the model's own message; an organization's name was made by turning a value into text | Every such refusal says "has to be text ... put text with ': ' in quotes". Declared fields send the answer back for a fix round with those words; loosely typed ones are refused alone at the applier against the record model's (or the setting's) type; every record write gets the same words from the store; an organization name that isn't text is refused, never turned into one. Two golden cases (a colon in a title, commas in a title). Built: `tests/test_text_shape.py` (eight tests), `workspaces/demo-b/evals/colon-in-title.yaml`, `commas-in-title.yaml` |
| The first go's estimate (7.8) | Counted only the items handed in | Includes the sorting run the go also makes for mail handed in unsorted: the Today line and the screen's line add its price (one more run on the plan's allowance when it has none). `GET /api/runs/first-go` gives the sorting runs, price and unpriced count. Built: `tests/test_mail_sorting.py::test_the_first_go_estimate_includes_the_sorting_run_so_the_person_approves_the_whole_spend`, `web/src/components/FirstGoRow.test.tsx` |

## 43. Phase L0: every note the person types reaches the assistant (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| A note on Mark done, They finished it, Followed up, the choice of an owner (6.5, 6.9) | The routes took no note: nothing the person wrote with the button was kept or read | Each takes an optional `note`; after the change is saved, `engine.intake.note_as_input` hands it in unless it is a bare confirmation. Built: `tests/test_note_input.py::test_mark_done_with_a_note_makes_one_request_about_the_action`, `::test_they_finished_it_with_a_note_makes_one_request_and_the_note_survives_the_undo`, `::test_followed_up_with_a_note_makes_one_request_and_without_a_body_none`, `::test_picking_an_owner_with_a_note_makes_one_request_about_the_action` |
| An answer to a question, text added to an action's notes (6.5) | Saved on the record only; the assistant never read it | Handed in the same way; an edit of notes hands in only what was added after the old text, and a refused edit hands in nothing. Built: `tests/test_note_input.py::test_answering_a_question_in_words_makes_one_request_about_the_question`, `::test_adding_to_an_actions_notes_hands_in_only_what_was_added` |
| The bare confirmation (4.6) | n/a | Fewer than `language.bare_confirmation_words` (4, applies at once) words and no link: kept with the change, no request. Built: `tests/test_note_input.py::test_a_note_under_four_words_with_no_link_makes_no_request`, `::test_a_short_note_with_a_link_makes_a_request`, `::test_the_word_count_comes_from_the_setting` |
| The saved note (5.1, 6.6) | n/a | A source of kind `note:<button>`, trust `trusted`, with the item's project; the request is the usual notes work with `about` set to the item. The dispatcher honors a source's own trust (a request whose source is the person's own words is not outside content), and the packet shows the note in a `<note>` block and the item as data beside it. Built: `tests/test_note_input.py::test_a_note_is_saved_as_the_persons_own_words_with_the_item_as_its_context`, `::test_the_packet_carries_the_item_and_the_note_as_the_persons_own_words` |
| What comes back (6.5) | n/a | A note with a link and a new date becomes a fact citing the saved note and a moved date, applied as the person's own note. Built: `tests/test_note_input.py::test_a_note_with_a_link_and_a_new_date_comes_back_as_a_fact_and_a_moved_date_the_person_can_trust`; golden case `workspaces/demo-b/evals/they-finished-note.yaml` (the evaluation harness takes `typed_on` for a note typed on a button and `source: trusted` as an expectation) |
| Every other route that takes free text (6.5) | Undeclared | Declared in one place (`api/free_text.py`) as `to_assistant` or `local_only` with a reason; `engine.selfcheck.free_text` fails when a route's request has free text (by the rule in its docstring) and no declaration. Built: `tests/test_free_text_check.py::test_a_route_with_free_text_that_is_neither_wired_nor_declared_fails_the_check`, `::test_declaring_each_route_clears_the_check`, `::test_a_declaration_needs_a_known_kind_and_a_reason_and_a_route_that_takes_free_text`, `::test_the_apis_routes_with_free_text_are_all_declared` |
| Settings (4.6) | n/a | `language.bare_confirmation_words`, live, with a description and demo values in both workspaces |
| Screens | n/a | The note box on the buttons is built in 46 |

## 44. Phase L0: wording checks skip links, and a retry that applies retires the attempts before it (2026-10-13)

| Item | What the code did | What it does now |
|---|---|---|
| Checks on words (6.7, 7.0) | The screen-text check read a whole string, so a link with a dotted domain or a query string was matched as a settings key or file name; the applier's wording lints read links and quoted text as the assistant's words; the word-overlap checks counted words inside links | One helper (`engine/check_text.py`) takes out links (scheme addresses, `mailto:`, mail addresses, `www.` and bare domains) and, where the place knows them, the input's quoted text, before the screen-text check, `blocked-wording`, `run-on-list`, `near-duplicate-action` and `evidence-fit` read the words. The applier removes an op's evidence quote, its cited passages and passages in quotation marks that are in the input. A screen field removes links only; a cited quote, which is the input's own words, is typed as plain text. A settings key or file name is still caught. Built: `tests/test_check_text.py` |
| A try again on the same request (6.7) | Already cleared the cause and the waiting reason when it started and left review as its only line | Unchanged; now covered. Built: `tests/test_attempts_retire.py::test_a_try_again_on_the_same_request_that_applies_leaves_no_line_or_cause_for_the_failed_try` |
| A request redone after it was sent back (6.7) | The earlier request's held changes and the questions asked to place them stayed on Today after the new one applied, and could be applied later | When the new request's changeset applies something, the requests it redoes (by `previous`) are done and carry `superseded_by`; their held changes are refused with a reason, their routing questions dropped, their open setting proposals and report drafts dismissed; what they applied stays. A changeset that applied nothing retires nothing. New optional field `request.superseded_by`. Built: `tests/test_attempts_retire.py::test_a_sent_back_attempt_with_a_held_item_is_retired_when_the_next_one_applies`, `::test_a_stopped_attempt_and_its_cause_close_when_a_later_attempt_applies`, `::test_an_attempt_that_kept_its_applied_work_keeps_it_when_the_next_one_applies`, `::test_the_attempts_open_proposals_are_discarded`, `::test_an_attempt_that_applied_nothing_retires_nothing` |
| A follow-up whose cause is gone (6.7, 6.16) | `process` ran any request it was given, a fix round or the escalation re-run went ahead whatever had happened to the request, and a late failure wrote a stop onto it | `process` runs only a request that is still open (not applied, finished or replaced); a fix round and the escalation re-run check the request first and are not asked for one that is closed or replaced; nothing of such a run is written, and a stop is not written onto a closed request. Built: `tests/test_attempts_retire.py::test_a_queued_automatic_try_for_a_request_that_has_since_applied_does_not_run`, `::test_a_request_that_is_not_waiting_in_line_is_not_run`, `::test_a_fix_round_for_a_request_retired_meanwhile_does_not_run`, `::test_a_retired_request_is_not_stopped_again_by_a_late_failure` |

## 45. The hosted end state: an organization install with roles (2026-10-13)

| Item | Before | Now |
|---|---|---|
| Who uses a hosted install | One person, signing in to their own workspace (Part 11) | The end state is an organization install: members from the People list, roles per person and per project, views per role, packs declaring which roles their parts are for, approvals by role, the person behind each change in the ledger (11.8). Not built in 1.0; new core code never assumes one person (checked by reading: design 11.8, CLAUDE.md) |

## 46. Ready for real use: the note box and where it came from (2026-10-14)

| Item | What the code did | What it does now |
|---|---|---|
| A note on the action buttons (6.5, 7.5) | The routes took a note (43) but the screens sent none | The row's menu on Mark done (Follow-ups and Today's to-do list), They finished it, Followed up and the pick of an owner has Add a note: a short box, cursor in it, Enter sends, Escape closes, the note goes with the same act on the same route; with no note the request is as before. The toast says the assistant will read the note when the server queued work from it, and that work shows in What changed at once. Built: `web/src/components/NoteBox.test.tsx` (Mark done, They finished it, Followed up and the pick of an owner: the note is sent with the act, no note sends none, the cursor starts in the box, Enter sends, Escape closes, a refused act keeps the note), `web/src/components/TodayRail.test.tsx` ("a to-do's menu adds a note to Mark done") |
| Where it came from (7.5) | A record page showed the input's id; Follow-ups and Today showed nothing of an item's origin | `origin` on a Follow-ups action and question, Today's to-do line, a record page's open items and the record view of an action or a question, computed by `engine/origin.py`: the page when its input has an openable address (shown with its real domain), else the input's saved text, else the change that created it with its request, else none. Screens show one **Where it came from** link; a change opens in What changed (the list opens the row once loaded when the person comes from another screen). New view field `origin` (`Origin`); `GET /api/record` carries it for an action or a question. Built: `tests/test_origin.py` (API: the page, the saved text, the change and its request, no origin; Today's to-do and a record page's open items), `web/src/components/Origin.test.tsx` (a Follow-ups row), `web/src/components/RecordPage.test.tsx` (a record page), `web/src/components/WhatChanged.test.tsx` ("a change asked for before this screen opened is opened once its list has loaded") |
| Knowledge records (6.22, 7.18) | n/a | *Not built:* their link comes with L1, when they exist |

## 47. Ready for real use: the header shows the assistant is alive (2026-10-14)

| Item | Before | Now |
|---|---|---|
| The assistant's line in the header (7.1) | The status chip said the worst state in a word; whether the assistant was running at all, when it last ran and what waited for it were not in the header | A line beside the chip, always there: "Assistant ✓ last run 9:42" in the person's zone and time format, "no runs yet" before the first run. Amber with a warning icon for waiting for the network, a restart to finish, a paused account or no AI account yet; red with a cross icon when the account can't be used or the last run failed. Words and icon say it, never color alone. Its popover lists today's runs per account (count, failed), the requests waiting (count, oldest since) and each tier's fallback order by the accounts' own names. Built: `web/src/shell/AssistantLine.test.tsx`, `web/src/shell/status.test.ts`, `web/src/shell/Header.test.tsx` |
| `GET /api/status` (6.15, 7.1) | Backup, AI state, spend, request counts, network wait, restart | Adds `assistant`: `last_run_at`, `last_run_failed`, `runs_today` (account, count, failed), `queued`, `oldest_queued_since`, `chains` (tier, accounts) and `paused` (account, until). Times are on the person's own clock. Only today's runs and the newest twenty are read (new store lookups `since` and `latest`); a call that found no network is in no count and is never the last run; a failed run on an account that is now paused is a pause, not a failure. Built: `tests/test_assistant_status.py` |
| Header layout (7.1) | One 56px row at every width | One row from 1280px up; below it (not on a phone) the status chip and the assistant's line take a second 32px row, so the header is 88px and the first row keeps its room. The shell's `--header-h` follows it. Phone stays 48px |

## 48. Ready for real use: on hold isn't due, and one follow-up rule (2026-10-14)

| Item | Before | Now |
|---|---|---|
| An action waiting on something | No way to say so: it kept its due date, showed as overdue and was chased | An action carries `on_hold` (what it waits for, since when), set and cleared by the person from the row's menu with Undo, each recording a signal; it is never due, overdue or chased, and shows "On hold: ..." with its old due date in the tooltip (5.1, 6.9, 6.20; `tests/test_on_hold_and_follow_ups.py::test_an_action_on_hold_is_never_overdue_on_the_to_do_list_or_in_todays_queue`) |
| When something sent is chased | One setting, `ui.today.nudge_after_days` (3), for questions and actions alike | One function, `follow_up_due`, used by Today's lines and the Follow-ups pills: a question after 4 days; a told action only when its own due date is within 7 days or past; an undated one after 14 days; never on hold. Settings `ui.followups.question_after_days`, `action_due_within_days` and `undated_after_days`; the old key is read as the first (4.11, 6.9; `tests/test_on_hold_and_follow_ups.py::test_today_and_the_follow_ups_view_agree_on_what_is_due_a_follow_up_and_on_hold_leaves_both`) |
| Follow-ups pill | "sent <date> (N days)" in the line | "waiting Nd", and "waiting Nd · follow up" in the warning color once the rule says it is time |

## 49. L1: knowledge as records (2026-10-14)

| Item | Before | Now |
|---|---|---|
| Knowledge records (5.1, 6.22) | Only facts were kept; lessons, glossary entries, routing entries and style notes were designed | Four core records, `lesson`, `glossary_entry`, `routing_entry` and `style_note`, sharing `text` (the restatement), `evidence` (quote, source, request, signal, changeset), `origin` (person, input, assistant, pack, seed, import), `pack`, `trust`, `learned_at`, `status` (proposed, active, discarded, expired, retired), `discard_reason`, `kept_by`, `kept_at` and `applies_to`. Provenance fields never change after the entry is made. They are in the export and import like any record. Built: `tests/test_knowledge_records.py::test_the_four_kinds_are_core_records_with_their_own_fields_and_one_shape`, `tests/test_knowledge_records.py::test_a_record_that_contradicts_itself_does_not_validate`, `tests/test_knowledge_records.py::test_every_kind_of_knowledge_is_in_the_export_and_loads_back` |
| Scopes with exclusions (6.22) | A rule's target was task kinds, records and a filter | One shape, `Scope`, for rules and knowledge: those three plus `projects`, `people`, `scope` (workspace or projects) and `except`. A workspace-wide entry names the projects it does not apply to, with no copy per project. Rules' own config still reads only the first three until rules become records. Built: `tests/test_knowledge_records.py::test_everywhere_except_a_project_round_trips_through_the_record_the_api_and_the_export` |
| Ops (6.7) | None for learning | `lesson.add`, `lesson.update`, `glossary.add`, `glossary.update`, `routing.add`, `style.add`, `knowledge.retire`, all system tier with Undo. From the person's own words an add is active at once; from anything else it is added as a proposal and not held, because it changes nothing until kept; an update or a retire from anyone else is held like any system op. Not offered when reading notes or to a plugin's action. Built: `tests/test_knowledge_records.py::test_a_lesson_from_the_persons_own_words_is_active_at_once_and_from_an_input_it_is_proposed`, `tests/test_knowledge_records.py::test_changing_or_retiring_an_active_entry_from_anyone_but_the_person_waits_for_them`, `tests/test_knowledge_records.py::test_undo_of_each_op_takes_the_change_back` |
| Keep, Discard, Retire (6.22, 12.8) | n/a | `POST /api/knowledge/{id}/keep`, `/discard` and `/retire`: each acts at once with Undo and records a `kept`, `discarded` or `retired` signal (new signal kinds, 6.20). Keep makes the person the author, with any wording or target they changed. Built: `tests/test_knowledge_records.py::test_keep_with_an_edited_text_makes_it_active_and_the_person_its_author`, `tests/test_knowledge_records.py::test_discard_keeps_the_proposal_with_its_reason_and_undo_brings_it_back`, `tests/test_knowledge_records.py::test_retire_ends_an_active_entry_and_undo_makes_it_active_again` |
| Provenance (7.5) | Item 46's link covered actions, questions and decisions | `GET /api/knowledge` (filters `kind`, `status`) carries `origin` for each entry, from `engine/origin.py`: the page, else the saved text of the input its evidence cites, else the change and request that made it. No screen yet (L3). Built: `tests/test_knowledge_records.py::test_the_origin_of_an_entry_is_the_page_else_the_saved_text_else_the_change_and_its_request` |
| Still to come | | Nothing reads these records into a packet (L2), no task kind proposes them (L3), no screen lists them (7.18), proposals never expire and duplicates are not merged (L3), facts' `key`, `as_of` and `supersedes` and rules as records are other L1 items |

## 50. L1: rules as records, facts with key and as_of, signals that name what they correct (2026-10-14)

| Item | Before | Now |
|---|---|---|
| Standing rules (4.10, 5.1) | Entries in `rules.yaml`, read by stage checks and load-time validation | A `rule` record (id `RULE-n`; `name`, text, applies_to (the same `Scope` shape as knowledge, with `except`), check, origin, status, source, evidence, learned_at, kept_by, kept_at), added by `rule.add` and ended by `rule.retire`, both system ops with Undo. `rules.yaml` is the starting set: each rule with no record yet becomes an active record with the origin `seed` when the workspace starts or is created, once (a retired one is not made again, and the file is never written back). Stage checks and the plugin host read the active records through `engine/rules.py`. A rule from the assistant waits for the person like any system op, then carries them as `kept_by`. Built: `tests/test_rules_facts_signals.py` (seeding, retire, op, export round trip), `tests/test_stages.py::test_a_rule_added_by_op_is_used_by_the_stage_check_until_it_is_retired` |
| Facts (5.1, 6.22) | text, project, source, evidence, trust | Also `key`, `as_of` (the day the input was received, or the request's day for a typed note, unless the input names another) and `supersedes`. What replaced a fact is computed from the newer fact, not written onto the older one, so Undo of the newer fact needs no second write; a fact is replaced once, and a replacement of nothing or of a replaced fact is refused. Built: `tests/test_rules_facts_signals.py` (as_of, supersedes, refusals, export round trip) |
| Signals (5.1, 6.20) | kind, refs, note, at | Also `changeset` and `run`: send back, undo and a routed answer set both; the run is the changeset's own. A hold, a mail item set aside by hand, an automatic close pulled back and an edited follow-up message have no run, so both stay empty. Built: `tests/test_rules_facts_signals.py` (each recording path) |

## 51. L1: a note's author follows the button (2026-10-14)

| Item | What the code did | What it does now |
|---|---|---|
| A note typed on a button (6.5) | Every typed note was a trusted source of the person's own words, with no author; a system op from any of them was held | The source records its `author` (a new optional person id on `source`; the plugin guide is regenerated). Mark done, Reopen, the choice of an owner, an answer to a question asked of the person and an addition to an action's notes are the person's own words, authored by the person running the app. They finished it, Followed up and an answer recorded for a question asked of someone else are content the person reports, authored by the person it is about (the person the action waits on, or the one the question went to). Built: `tests/test_note_input.py::test_a_notes_source_is_authored_and_trusted_by_the_button` (every button) |
| Tier of a system op from a typed note (6.7) | Held for every typed note | Applies at once with Undo from the person's own words (Mark done, Reopen, the choice of an owner, an answer to the person, notes added); held, with the reason that someone else reported it, from reported content. Facts and dates from either apply as before. Only the person's-own-words buttons change: the loosening. Built: `tests/test_note_input.py::test_a_mark_done_notes_system_op_applies_at_once_with_undo`, `::test_a_change_to_how_the_product_behaves_from_a_reported_note_waits_for_the_person` |
| A standing rule stated in reported content (6.7, 12.8) | Held, as any system op | Unchanged in effect and now by design. No knowledge ops (lessons, glossary, routing, style, rules) exist yet, so the rule covers the system tier: when they are built they are system-tier and wait for Keep. The learning pair proper is built in L4. Built (its seed): `tests/test_note_input.py::test_a_they_finished_it_note_saying_from_now_on_we_always_copy_the_client_on_approvals_is_never_active` |
| The packet (6.6) | `<note source="...">` | `<note source="..." by="<name>">`, and `reported="yes"` on reported content; the notes prompt says what that means. Built: `tests/test_note_input.py::test_the_packet_names_whose_words_a_note_is_and_marks_reported_content` |
| Answering a question (6.5) | One route, `note:answered` | A question asked of someone other than the person is recorded as `note:answered_for`, authored by whom it was asked. Built in the same tests |

## 52. The original designer's L1 check-in and the answers for L2 (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Notes (6.5, 5.1) | A note's author follows the button; only the three relaying buttons are reported content | A note on any button that repeats someone else ("<name> said …", or a quoted passage; setting `language.reported_speech`) is reported content too: the source is marked `reported`, its author stays the person who typed it, and a system op from it is held. Built: `tests/test_note_input.py` (recognition, the held rule from a Mark done note) |
| Facts (5.1) | A typed note's fact takes the request's day | The day the note's text names wins (the code already took the op's `as_of` first; the op's description now says so). Built: `tests/test_rules_facts_signals.py::test_a_fact_from_a_typed_note_that_names_an_earlier_day_takes_that_day` |
| Rules (6.22) | `rule.retire` recorded no signal | Retiring a rule goes through the same route and records the same `retired` signal as any other knowledge. Built: `tests/test_knowledge_records.py::test_retiring_a_standing_rule_records_the_same_signal_as_any_other_knowledge` |
| The packet (6.22) | Every active rule in the always-sent part | Only workspace-wide rules there; narrower ones per input, filtered by scope when the packet is built, with the left-out rules logged. A size budget, measured per run from L2's first commit, moves rules narrowest first, and a stage-checked rule sends its one-line form. *Designed, phase L2* |
| Rule review (6.22) | A rule that hasn't applied in 30 days is flagged | A rule says what it `constrains`; the log counts applied (an op or field it constrains, its check ran, or a correction names it) apart from present; the weekly review offers Keep, Narrow and Retire, never for check-enforced rules. *Designed, phase L2* |
| Search (6.22) | The instructions say to search before an outside lookup | Local first is enforced: an outside lookup from a run that hasn't searched is sent back; `already-known` runs before every question op. *Designed, phase L2* |
| Rules from inputs (6.22) | Held as a decision on Today | From L3, proposals on the Learned line; the person's own words still apply at once. *Designed, phase L3* |
| Plan | The harder golden set in L4 | Moved ahead as L1b, with its "before" run (O2) pinned ahead of L2; one account in the chain is a decision before real use |

## 53. L2, first wave: the knowledge section, the knowledge log, search and the asking lints (2026-10-14)

| Where | Before | Now |
|---|---|---|
| The packet (6.6, 6.22) | No knowledge in packets | The stable part holds workspace-wide active rules (a stage-checked rule as one line), task-kind lessons and the glossary while small; the per-input part holds narrower rules and lessons, routing, used glossary terms and the input's projects' facts, dated, sourced, ranked and cut at `knowledge.facts_budget`. Scope is filtered at build; untrusted entries show as data. Built: `tests/test_knowledge_section.py` |
| The run (5.1, 6.22) | No knowledge log | `Run.knowledge`: given, left out by scope, facts left out, the stable section's size, and searches. Built: `tests/test_knowledge_section.py::test_a_processed_requests_run_records_the_knowledge_it_was_given` |
| Search (6.22) | Designed | A run may answer with a search; the engine searches facts, past inputs, records and knowledge, at most `knowledge.search_rounds` times. Built: `tests/test_search.py` |
| Lints (4.17) | Designed | `already-known` (return) on asking ops from a run that didn't search; `near-duplicate-question` (warn) against the same person's questions within 14 days. Built: `tests/test_search.py` |

## 54. L2, second wave: rule counts and review, invariant lines, refusals, the plugin call and learning: own (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Rules (5.1, 6.22) | No record of what a rule governs | `constrains` (op kinds or fields), `reviewed_at`; each run logs `rules_applied`, `rules_present`, `rules_moved`; a weekly review in the queue and its routes (Keep, Narrow with a `narrowed` signal, Retire). Built: `tests/test_rule_review.py` |
| Invariants (6.7) | Only in code | A one-line constraint per invariant in the op reference, and a self-check that each has one. Built: `tests/test_invariants.py` |
| Refusals (6.22) | Not counted | Counted per check (fix rounds included); a frequent one brings its seed lesson, after `min_runs`. Built: `tests/test_refusals.py` |
| Plugins (3.x, 6.22) | A pack's packet got no knowledge | `view.knowledge(...)` and `learning: own`. Built: `tests/test_plugin_learning.py` |
| Scope (6.22) | Exact projects | A scope naming a project covers its children. Built: `tests/test_plugin_learning.py::test_a_scope_naming_a_parent_project_covers_its_children_at_any_depth_for_projects_and_except` |

## 55. L3, the rules for proposals: rules as proposals, just this time, one line for what was learned, the catch-up list (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Rules (6.22) | `rule.add` from the assistant or an input was a held decision on Today | It is added as a `proposed` rule, kept or discarded like the other kinds; the person's own words still apply at once with Undo. `rule` gains the statuses `expired`, `trust`, `discard_reason` and `more_evidence`, and the origin `input`. The decisions already held move once to the catch-up list. Built: `tests/test_proposals.py::test_a_rule_from_an_input_is_a_proposal_and_from_the_persons_note_is_active_with_undo`, `tests/test_proposals.py::test_held_rule_decisions_move_once_to_the_catch_up_list_and_running_twice_moves_them_once` |
| Keep (6.22, 12.8) | Kept an entry active and the person its author; an entry from content stayed `untrusted`, so it was shown to runs as data forever | Keep also makes the content trusted, because the person kept the restatement and its target as their own words; the source stays beside it as evidence. Undo puts both back. Built: `tests/test_proposals.py::test_keeping_a_rule_proposal_makes_the_restatement_theirs_and_the_source_stays_outside_evidence` |
| Duplicates and discards (6.22) | None | A proposal that repeats an active or proposed entry (same kind, same normalized wording or term, overlapping target) merges into it and links its evidence (`more_evidence`); one close to something the person discarded in the last `knowledge.discards_hold_days` (default 90) is kept as discarded with the reason "Close to one you discarded" and not shown. Built: `tests/test_proposals.py::test_a_duplicate_merges_into_the_entry_it_repeats_and_links_the_evidence`, `tests/test_proposals.py::test_a_proposal_close_to_a_recent_discard_is_not_shown_and_an_old_discard_is_forgotten` |
| Just this time (7.18, 6.20) | Designed only | `POST /api/knowledge/{id}/just-this-time` records a `just_this_time` signal and discards the proposal with that reason; the same correction proposed again is shown with how many times it was said before. Built: `tests/test_proposals.py::test_just_this_time_records_its_signal_discards_and_the_repeat_is_marked` |
| Today (7.18) | A line for the weekly rule review only | One Review line for everything learned (`learned`: proposals from inputs and from corrections, tagged by origin, with how many from inputs expired since the person last looked), and the catch-up line (`catch_up`). Proposals from inputs expire after `knowledge.proposals_expire_days` (default 14) in a daily sweep; those from corrections never do. Built: `tests/test_proposals.py::test_the_line_counts_both_origins_and_how_many_expired_since_the_person_last_looked`, `tests/test_proposals.py::test_the_sweep_expires_input_proposals_after_the_days_and_never_correction_ones` |
| Catch-up (6.22) | Designed only | Once, at startup, the corrections recorded before this phase that no entry was learned from are grouped by kind and the most repeated `knowledge.catch_up_max` (default 20) kept; the rest expire with their number shown. The learning runs for the chosen kinds are the learning step's. Built: `tests/test_proposals.py::test_the_catch_up_list_caps_and_ranks_the_corrections_from_before_and_is_made_once` |

## 56. L3, correcting what the assistant made: questions, "Change this" and the missing ops (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Questions (6.8) | A question could only be sent back with its whole changeset | `question.update`, `question.move`, `question.drop` and `question.mark_sent`: the person's own ops with Undo; the first three record `reworded`, `routed` and `dropped` naming the question, its changeset and run; dropped questions are kept with their reason (`GET /api/questions/dropped`). Built: `tests/test_corrections.py` |
| Signals (6.20) | `draft_edited` named only the person; no signal for a note on a row | `draft_edited` names the question ids and the run that wrote them; new kind `change_requested` |
| "Change this" (6.8, 7.7) | Only questions had a way to answer the assistant | `POST /api/items/{kind}/{id}/change` for an action, question, decision, calendar entry or fact: a signal, and the notes work with the item as it is now; the notes prompt says what a change may be |
| Missing ops (6.13) | Hand fixes with no op | `mail.restore`, `list.merge` (system tier) and `question.mark_sent`, each with a check and Undo |
| Lints (4.17, 6.8) | Several questions in one text, and a question to someone else with no stake, went through | `several-questions` and `question-without-stake` (default `return`); `matters_for` on `question.add` and on the question; settings `several_questions.minimum` and `owner_suggestion.match` |
| Pick an owner (6.9) | The held item offered every person | It carries the owner a routing entry suggests, with its words as the reason, and the nearest open action to fold it into |
| Notes (6.22) | Reading notes was offered no knowledge op | `glossary.add`, so an unknown term can be recorded as unknown (a proposal unless the words are the person's) |

## 57. L3, second wave: learning from inputs, the measures and checked fallback accounts (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Learning from inputs (6.22) | Designed as a `learn-input` task kind, with the scan's terms named in the packet | Part of reading notes: `routing.add` and `glossary.add` are offered, the notes prompt says when to propose terms, routing and superseding facts; a rules-only scan after the answer applies proposes each new term as unknown (`language.new_term_patterns`, `new_term_ignore`, `knowledge.new_terms_per_input`). Built: `tests/test_learn_input.py` |
| Signals (6.20) | An answer to the assistant was not a signal | `answered_assistant`, learned from at once; "Change this" is learned from at once too |
| Measures (6.20) | Designed | `applied`, `applied_dropped` and `missing` on the changeset; the knowledge-used rate, the repeat-correction rate (weekly, gated by `knowledge.min_corrections_per_week`) and the missing-op list in `GET /api/quality`. Built: `tests/test_quality.py` |
| Fallback chains (6.16) | Designed | The settings save refuses an unchecked account newly added to a chain unless `accepted_unchecked`; the account check adds a learning round-trip; the first run on a fallback account sets `first_on_account`. Built: `tests/test_quality.py` |
| Restart (6.14) | A save landing while the worker checked could read as a restart | The worker judges from the files its take-in read. Built: `tests/test_provider_safety.py::test_a_live_change_saved_while_the_worker_checks_never_asks_for_a_restart` |

## 58. L3, third wave, part A: the Knowledge screen, the rules review, use counts and accounts that can't stand in (2026-10-14)

| Where | Before | Now |
|---|---|---|
| Use on every row (7.18) | Designed only | Each entry and rule carries `used`, `given` and `last_used` from the runs' knowledge logs, shown as "Used 12 times · last 2 days ago" or "Never used". Built: `tests/test_knowledge_screen.py::test_use_counts_runs_that_applied_an_entry_runs_that_were_given_it_and_when_it_was_last_used` |
| Knowledge screen (7.18) | Designed only | Records > Knowledge: every entry and rule by kind, filtered Proposed, Active, Unused or Retired, with where it came from, what it reaches and its use; Keep or Narrow as the row's action, the rest in its menu, each with an undo toast. `GET /api/knowledge/rules` lists the rules. Edit is on proposals only. Built: `web/src/components/Knowledge.test.tsx`, `tests/test_knowledge_screen.py::test_the_rules_list_has_each_rule_with_its_reach_what_it_constrains_where_it_came_from_and_its_use` |
| Rules review (6.22, 7.18) | The line and routes, no screen | The line opens a screen of the flagged rules with their counts, the size against its budget, the rules moved, and Keep, Narrow and Retire. Built: `web/src/components/RuleReview.test.tsx` |
| Fallback chains (6.16) | A hand-edited chain was not flagged | A Today line per account in a chain that is unchecked for that tier and not accepted, or whose last check failed; its action runs the test for that tier. Built: `tests/test_knowledge_screen.py::test_an_unchecked_account_in_a_hand_edited_chain_has_a_line_until_its_check_passes`, `tests/test_knowledge_screen.py::test_a_failed_check_has_a_line_that_says_so_even_for_an_accepted_account_and_goes_when_it_passes` |
## 59. L3, third wave B: learning on the card and on Today (2026-10-14)

| Where | Before | Now |
|---|---|---|
| The Learned line (7.18) | Designed only | One line under a correction's card (a send-back, a routed or answered question, "Change this"): "Learned: ... · Keep for ▾ · Keep · Just this time · Edit · Discard", with Learning from this... while the run is queued or running, and Undo in place of Keep for the person's own words. Keep for is a pick list from the narrowest reach. The words it came from sit beside it, marked "From outside" when they came from content. Built: `web/src/components/Learned.test.tsx`, `tests/test_learned_lines.py` |
| Today (7.18) | The queue had `learned` and `catch_up` lines no screen drew | One Review line and the catch-up line, each opening its list (a row per thing, tagged by where it came from, with how many expired); Keep all only for glossary terms that carry their words. Built: `web/src/components/LearnedToday.test.tsx` |
| "Change this" and the question menu (6.8, 7.18) | Routes only | "Change this" in the menu of an action, question, decision, calendar entry of the app's own and a fact (on its page); a question's menu has Reword, Ask someone else, Drop and Already sent. Built: `web/src/components/ChangeThis.test.tsx`, `web/src/components/TodayRail.test.tsx` |
| Which knowledge shaped this (6.20, 7.18) | `applied` and `first_on_account` kept, not shown | The changes view carries both; the card shows "Because you told me: ..." linked to the entry, with This doesn't apply here (leave a project out, or retire; at once with Undo), and "First run on ..." for a stand-in account. Built: `web/src/components/WhatChangedLearning.test.tsx`, `tests/test_learned_lines.py::test_the_changes_view_carries_what_a_run_applied_and_the_account_it_first_ran_on` |

## 60. L3 finish: the assistant holds and drops, folding an unowned action, every correction teaches (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Ops (6.8) | "Change this" asked for a hold or a drop the assistant couldn't make | `action.hold`, `action.drop` (status `dropped`, `dropped_reason`), and the assistant's `question.drop`, each with evidence and Undo; only the person's own drop records `dropped`. Built: `tests/test_hold_drop_fold.py` |
| Pick an owner (6.9) | The nearest action was offered but couldn't be used | Fold: `POST /api/changesets/{cs_id}/ops/{index}/fold`, one change with Undo, `held_declined` |
| Signals (6.20) | Question corrections never queued learning | Every signal is written through `learn.record`, which queues learning |
| Screens (7.18) | No Drop on an action | Drop with a reason and Undo on action rows; "Add to …" on the held item |

## 61. L3 done: catch-up runs behind one go, unchecked backups skipped, the send-back packet, reach in words (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Catch-up (6.22) | The list was made but nothing learned from it | One learning run per kind, queued once, waiting for one go: the `catch_up_go` Today line and `POST /api/knowledge/catch-up/go`. Built: `tests/test_catch_up_learning.py` |
| Fallback (6.16) | The router still tried an unchecked backup | Skipped at the moment of use; the person's own pick never is |
| Send-back (6.8) | The redo's packet didn't show the items as they are now | Each touched record as it is now, marked taken back, kept or not applied |
| Learned line (7.18) | Reach as a pick list only | The reach in words beside it, exclusions by name |

## 62. L3b: the obvious next step from what came in (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Names (6.9) | "Who is X?" picked only an existing person | "Add a new person", prefilled from the input, with an unknown organization made once |
| Contact details (6.7, 12.8) | No way to keep a signature's details | `person.contact`, always waiting for the person; `workspace.contact_kinds` |
| Projects (6.7) | Reading notes couldn't propose a project | `project.add` waits as a system op; "It's part of" and "Not a project" kept as glossary entries |
| Holds (6.8) | No op to take an action off hold | `action.unhold` |
| Recipients (6.8) | A recipient could be guessed | The lint `unnamed-recipient` and `language.already_sent_phrases` |
| Packets (6.6) | An edit by the person's own account wasn't marked | `by_us="yes"` on its outside-content block |
| Calendar (6.7) | An entry had a project only if the assistant named one | It takes the request's or the source's project |
| Evaluation (6.16) | No way to expect a held op, a project or a watched item | `held: <op>`, `project`, `watched` in a case; seven new golden cases. Built: `tests/test_next_steps.py`, `tests/test_obvious_steps_f.py` |

## 63. L5: reading attachments and documents, and encrypted backups (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Files (6.2) | Only text files were read; attachments were names | Documents, spreadsheets, presentations and PDFs read as text, attachments included, each reader checked at startup; an unsupported type asked about once |
| Extension points (3.3) | No text extractor | `registrar.extractor`, `ItemFile` on a connector's item, `view.file_text` |
| Backups (4.15, 12.1) | Not encrypted | `storage.backups.encrypt` seals every copy; restore asks for the key. Built: `tests/test_extractors.py`, `tests/test_backup_encryption.py` |

## 64. L6 and the first-week lints (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Rules (8.8) | Designed | `unverified-quote` (questions only), `unverified-name`, `unknown-link`, `version-number`, `summary-is-status`, `unlinked-made`; `Person.name_verified`. Built: `tests/test_first_week_lints.py` |
| Change cards (7.7) | What a change made was inside its details | "Made:" links on the row (`made` on the change view) |
| Uploads (6.2) | A file sent with no type was refused as binary | Its name gives the type; a text type only when the bytes are text. Built: `tests/test_files.py::test_a_file_sent_with_no_type_or_a_generic_one_takes_the_type_its_name_gives` |

## 65. The scope slice (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Projects (6.18, 5.1) | No role per person | `Project.roles` (run, design, watch), `project.role`, a pick on the project page |
| Checks (6.7) | Nothing enforced scope | `watched-project` and `other-team-item`, returned once then held; the person's own note exempt. Built: `tests/test_scope_slice.py` |
| Packets (6.6) | Projects without the person's part | The part shown when it isn't "run" |

## 66. L3b done, and a watched source names its author (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Projects (6.7) | Add only created the project | Add files the input's unfiled work under it, with Undo |
| Watched sources (6.10, 4.1) | The person's edits and the app's publishes were both `by_us` | `workspace.user.accounts` and a source's `author`; the packet marks `author="you"` or the credited name, and `by_us` only for the app |
| Journeys | No journey for the next-step buttons | J7 presses each one and checks Undo |

## 67. One account is the usual case; expiring keys; failed calls (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Routing (6.16) | A paused routine tier only waited | Today asks before using another tier's account until the reset (`ai.borrow_other_tier`). Built: `tests/test_borrow_other_tier.py` |
| Keys (6.16, 4.8) | No end date | `credential_expires` on an account, the service-given end of a sign-in, and a Today line `ai.credential_warn_days` before, naming every place the key is used. Built: `tests/test_credential_expiry.py` |
| Screens (7.x) | A failed read could show as empty | Today's cards, a source's row, Check now and the add-ons list say what failed and what to do |

## 68. L4, part 1: learning pairs, the day-30 scenario, and the four gaps they found (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Proving it (6.22) | No pairs | 28 pairs (12 negative) and the day-30 scenario; `cockpit evaluate --pairs`. Built: `tests/test_pairs.py` |
| Signals (6.20) | `edited` was never recorded | The person's edit of a field the assistant set records it |
| Glossary (6.22) | A learned meaning merged into "not known yet"; "part of" seen only under its project | The meaning replaces the unknown proposal; the entry is workspace-wide |
| Routing (6.22) | Only by person, team or project | Also by the input's topic. Built: `tests/test_knowledge_section.py::test_a_routing_entry_reaches_an_input_about_its_topic_whoever_the_input_names` |

## 69. L4, part 2: packs' own cases and scorers, and Switch and check (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Extension points (3.3) | No pack cases or scorers | `provides.evals`, `provides.scorers`, `registrar.scorer`. Built: `tests/test_pack_evals.py` |
| Switching (6.16, 6.22) | A switch was unchecked | "Switch and check (about $X)" on the accounts screen runs the golden set, pack cases and learning pairs; a failure is the Today line `switch_failed` with Switch back. Built: `tests/test_switch_check.py` |

## 120. To-dos and questions cleaned up end to end, the nudge's left-out list and the escalation line (2026-10-20)

| Where | Before | Now |
|---|---|---|
| One place for every open to-do and question (7.5, 6.9; roadmap B-6a "cleaned up end to end") | Open items were in Follow-ups by person (to send, later, waiting) and on a record's page; nothing listed them all, with a project and person filter | A Work screen, To-dos and questions (`#work/open`, `GET /api/open-items`): each to-do with its owners (`owner_format`, with the team), due date, project and the project that holds it, where it came from, a pill only for Overdue, Stale, On hold or No owner, and its notes on hover; each question with who it waits on and since when. Filter by project, person and state, each a list built from what is open. Edit…, Reassign… (one owner of several at a time, the team kept), Mark done, Add a note, Put on hold, Change this and Drop from the row, each at once with Undo and its signal (the owner and words edit records `edited`, Drop `dropped`). Built: `tests/test_open_items.py`, `web/src/components/OpenItems.test.tsx` |
| Duplicates offered for merging (6.9, 7.5) | The near-duplicate lint found them as the assistant added them; nothing offered them later | **Merge with "<other>"** on a to-do row that nearly repeats another of the same project and owners (the lint's own similarity setting): this one stays, the other is closed, its words and notes go in the kept one's notes, the earlier date is kept; one change of existing ops (`record.edit` and `action.drop`, applied all or nothing: `apply_as_person(all_or_nothing=True)`), one Undo, a `dropped` signal. No new op. Built: `tests/test_open_items.py` |
| Stale to-dos on Today (6.15, 6.9) | Overdue and no-owner to-dos were lines; one the person never touched and never dated was not | `ui.today.stale_after_days` (21; 0 is off): the person's own open to-do with no date, reminder or hold that nothing has changed for that long is a Review line, "Keep or drop 3 to-dos nobody has touched lately", whose button opens the screen on the Stale state. `Store.last_changes` gives each record's latest ledger time. Built: `tests/test_open_items.py::test_todays_queue_has_one_line_for_the_stale_to_dos` |
| A note on every action button (7.5, 6.5) | Mark done, They finished it, Followed up and the owner pick had the box; a promise's line and a reminder's Done on Today did not | The same "Add a note" box is on a promise's line (Followed up and Done together) and on a reminder's Done, and on the new screen's Mark done. Built: `web/src/components/NoteBoxEverywhere.test.tsx` |
| Actions worded to stand on their own (6.9, 4.17, the playbook) | `blocked-wording` and `run-on-list` only | A playbook rule in the notes guidance and the lint `action-stands-alone` (default `return`; `checks.tuning.action_stands_alone.min_words`, `language.unanchored_words` and `unanchored_lead_words`): an action that says "send it" or "follow up on that" is returned once; for an action only the person reads it warns, for one with another owner it is then held. A lint, never an invariant. Built: `tests/test_action_stands_alone.py` |
| The nudge's left-out list (7.5, P26; the UI designer's answer 36) | Not built | What went in the same first message and was answered or done since is listed above the box ("Answered Oct 12, left out", "Done Oct 13, left out"), so the shorter message is explained (`Nudge.left_out`; a dropped item is not listed). Built: `tests/test_nudge_left_out.py`, `web/src/components/NudgeLeftOut.test.tsx` |
| One suggested escalation (6.8, 7.5, P26; answer 36) | Not built (only the pack's `routing.escalation` was designed) | After a second follow-up and the wait running again with no answer, one Today line per person, "Ask someone else about "<the thing>"?", with **Pick who**: a list of people that asks the question of them instead or gives the action to them; never sent. `ui.followups.escalate_after_chases` (2; 0 is off). The pack's `routing.escalation` to a configured person is unchanged. Built: `tests/test_nudge_left_out.py`, `web/src/components/TodayEscalate.test.tsx` |
| L0's audit of 6.8 to 6.11 (`docs/project/audit-2026-10-12/`) | Rows for escalation, reassign, track_only, owner_format, the near-duplicate similarity and who did a thing against who reported it were Missing | Checked against the code: built since the audit (with tests) are the question feedback flow, Followed up, who did a thing against who reported it, the near-duplicate check over done actions and its similarity setting, `owner_format` rendering, `track_only` getting no notices, and now Reassign and the escalation line. Still not built: a question's `key` and link enrichment, re-checking a person's other questions on an answer, a correction checked against the data first, the baseline date, parsing an owner back from `owner_format`, `person.merge` and the single store interface; 6.8, 6.9, 6.10 and 6.11 say so |

## 118. Blocked actions, Later, values that carry meaning, and a date move isn't news (2026-10-20)

| Where | Before | Now |
|---|---|---|
| A hold names its blocker (6.9, 5.0; decisions 2026-10-19; the designer's F15) | A hold had only words, and a to-do that waited on a question could not be tied to it | One state, not two: `on_hold.on` is the id of a person, an action or a question, picked from a list in Put on hold (never typed) or named by the assistant's `action.hold` (refused for a blocker that doesn't exist or is the action itself). The row reads "Blocked, waiting on <name or the action's text>" or "Waits on: <question> (<who>, sent <date>)", each name a link; a hold with only words stays "On hold: …". A blocked action is still never due or chased. `blocked_actions` counts the ones whose blocker still blocks, by project and in all, for Top priorities (B-6b; nothing on screen yet). When the question is answered or the action finished the to-do is unblocked: due again by its own date, first on the rail with "Unblocked: <who> answered <date>" (day read from the ledger), until the person takes it off hold. Undo restores the old hold with its blocker. Built: `tests/test_blocked_actions.py`, `web/src/components/OnHold.test.tsx`, `web/src/components/TodayRail.test.tsx` |
| Follow-ups' Later (7.5, 5.0) | The filter and `question.held_for` were designed, not built | `Question.held_for` (a calendar entry, a series or a day, with the day it was held): the question sits in Later, out of To send, the message and the Today send line, until the meeting's day (a moved meeting moves it; a series is its first instance on or after the day it was held) or the day, and is then to send as any other. "Hold for later…" in the card's menu (which question, and a meeting or a day) and "Send now" in Later, both at once with Undo; holding for the next weekly note is not built. `GET /api/followups` carries `later` per person; `POST /api/questions/{id}/held-for`. Built: `tests/test_followups_later.py`, `web/src/components/FollowUps.test.tsx` |
| Values carry meaning (5.4) | A list's values were words; "completed" compared a status's label with a setting | Each value has a tone (ok, warn, danger, neutral) and, on a status list, a meaning (not started, open, at risk, blocked, done); the ranking, the at-risk lines, the colors and "completed" read the meaning. The core ships tones for every list and meanings for the project status list, both demo workspaces ship that list with them, and a list made before this reads the shipped ones by wording (a value it doesn't ship is neutral with no meaning). Adding a value asks for its meaning and look with a suggestion made from its wording (`GET /api/list-suggestion`); `list.add` takes `tone` and `meaning`, rename carries them, merge drops them. The projects view carries each status's tone, meaning and rank. Changing them on a value already on the list is not built. Built: `tests/test_list_meanings.py`, `web/src/components/ValueLists.test.tsx`, `web/src/components/Projects.test.tsx` |
| A date move isn't news (7.14; the designer's F17) | A record's activity listed every change, a date that only slipped included | A change that only moves a date on an existing item (the same words, a new due or start date, nothing else changed in that change) is left out of the history shown to readers; a first date, a date taken away, a date moved with any other change, and every new, closed or blocked item stay; the ledger keeps everything (`engine/history.py`). Plugin API 0.3.83: `view.changes(kind, record_id)` gives a pack's published page the same filtered history. Built: `tests/test_date_moves_are_not_news.py` |
| Plugin API (3.3) | 0.3.81 | 0.3.82: `view.changes`, `Change`, `OnHold.on`, `Question.held_for`, `ValueList.tones` and `meanings`, `action.hold` `on`, `list.add` `tone` and `meaning`; `docs/plugin-guide.md` is regenerated and `docs/plugin-api-0.x.md` has the note |

## 117. What the assistant knows about a project, overlaps, the fact label and "usually with" (2026-10-20)

| Where | Before | Now |
|---|---|---|
| A project's page (7.18, 7.14) | Activity and details only; nothing said what the assistant knew of the project | A section "What the assistant knows" under the activity: the project's sources (inputs grouped by a watched source or the way they arrived, with how many and the last), its facts with who they rest on and when (key ones first, nothing a newer fact replaces, a parent project's fact only when it says it reaches the projects inside), the glossary terms used there marked confirmed, assumed or not known yet, who answers what, and what is still unknown (the project's blank fields and unknown terms, each with the open question that uses the term, or "Nobody has been asked."). `GET /api/projects/{id}/knows`. Built: `tests/test_project_knows.py`, `web/src/components/ProjectKnows.test.tsx`, `web/src/components/RecordPageRecords.test.tsx` |
| The Learned line (7.18) | A proposal showed no relation to entries that already say the same | A proposal that says what another active or proposed entry says over an overlapping target (the rule that merges duplicates, `proposals.duplicate_of`) shows "Overlaps with: <that entry> · kept or waiting", linked to it; `ProposalView.overlaps_with`. Built: `tests/test_learned_lines.py`, `web/src/components/Learned.test.tsx` |
| A fact's source label (7.14, answer 29) | Only on the fact's own page | The same label, the dashed "Inferred" tag and Confirm it on each fact row of a project's knowledge section; the label is marked as never copied and can't be selected. Facts have no row on the Knowledge screen or in Today's inspector, so those two places have nothing to show yet. Built: `web/src/components/ProjectKnows.test.tsx` |
| A series page (7.14, answer 30) | The details had no "usually with" | The people on more than `ui.series.usually_with_share` (0.5) of the meetings whose guest lists are known, once at least `usually_with_min_meetings` (2) are known, at most `usually_with_max` (6); calendar entries' attendees resolved to people, the person themselves, a declined answer and a called-off meeting left out. Built: `tests/test_series_page.py`, `web/src/components/SeriesPage.test.tsx` |
| Settings (4.0) | | `ui.series` with the three keys above, a description and default each, and demo values in both workspaces |

## 116. Several accounts of one service at once (2026-10-20)

| Where | Before | Now |
|---|---|---|
| Sign-ins (6.27) | One set of tokens per sign-in, so a second Sign in replaced the first account | One set of tokens per account, each known by the address the add-on names it with (`sign-in-<name>--<key>.json`, 0600). The old single file is the first account and is moved to its own file on first read (or stays as one unnamed account when it never named itself). The same address twice is one account |
| Sign-ins row (7.9) | One account line and one Sign out | Each account by its address with its own Sign out, and "Add another account" (the same flow, the new account kept beside the others). Signing one account out forgets only its tokens and withdraws only its access |
| Sources (4.5, 6.2) | A source of a signing-in add-on read the one account | A core setting `account` on each source, a list of the accounts signed in: the only one by default, required to choose with several. Sources made before a second account keep the first account; the sources a sign-in starts are started for the account it just added, once per account |
| Plugin API (0.3.82) | `context.access_token(name)` gave the sign-in's one token | It gives the token of the source's own account, so connectors change nothing; `context.account` is its address; the test kit's `connector_context(account=...)` sets it. Signing an account out makes only its sources wait, with the existing "sign in again" line naming it |

## 115. Add-on keys and the backup key typed on the screen (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Settings and Add-ons (4.0, 7.9) | An add-on's own secrets (`workspace.plugins.secrets`) and the backup key (`storage.backups.encrypt`) were references to name by hand | Each secret an add-on declares is a password box in its Settings section and on its Add-ons row ("Kept on this computer", Replace, "Read from …"), kept in the private keys folder (0700, file 0600) with only the `file:` reference written; `GET /api/addon-secrets`, `POST /api/addons/{plugin}/secrets/{secret}`. Built: `tests/test_typed_secrets.py`, `web/src/components/KeptSecrets.test.tsx` |
| Backup key (4.15, 7.9) | A reference box | A password box with a plain warning that a lost key means unreadable backups, and "Make one for me" (a strong key made with the standard library, kept like a typed one, shown once in that one answer and never logged or written elsewhere); `GET/POST /api/backup-key`. A replaced key stays on disk beside the new one. A hosted app refuses a typed or made key and takes where it is kept. Built: `tests/test_typed_secrets.py::test_make_one_for_me_keeps_a_strong_key_and_shows_it_once_in_that_answer_only` |
| Mailbox and calendar sources (6.2, 4.0) | Covered by the source form (P16) but the calendar's private link had no test of its own | The mailbox password and the calendar's link (a typed link and a file on this computer are exclusive) are shown by test to be kept 0600, written only as references, and absent from the settings, the database (ledger included) and every answer. Built: `tests/test_typed_secrets.py::test_the_mailbox_password_and_the_calendars_private_address_are_typed_kept_and_never_written_elsewhere`, `tests/test_typed_secrets.py::test_a_calendar_takes_a_typed_address_or_a_file_on_this_computer_not_both` |
| Undo (4.22) | The general save took no add-on secret key | `workspace.plugins.secrets.` is accepted by the general save, so Undo of a typed add-on key works. Not built: cleaning up kept secrets nothing refers to (wave 6) |

## 114. Calendars from .ics, full featured (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Calendar source (6.2) | A private link only; a repeating event was one item whose later dates the agenda couldn't place; times with an unknown zone were read as UTC | A link or a file picked on this computer (a hosted app refuses a file plainly), read again on each read; `expand_days` (default 60) lists every date of a repeating event, and a rule the engine can't follow shows the first date with a note. Windows time zone names go through the shipped list; an unknown zone or none is read in the calendar's zone, else the person's, with a note. Built: `tests/test_ics_full.py` |
| Calendar entries (5.1, 6.32) | Only the person's and the assistant's own entries | A calendar source's dates are kept as entries by rules, with place, organizer, attendees (resolved to people by address, each with their answer), the invitation mark and the person's own answer; a repeating event's entries are one series. A moved date moves its entry and the promise due at it, a called-off or skipped date marks only its entry and tells that promise once. Built: `tests/test_ics_full.py` |
| Plugin API surface (3.3) | `EventDetails` carried a start, end, place, cancelled and repeats | Adds `occurrences`, `organizer`, `attendees`, `method`, `notes` and `entries` (and `EventOccurrence`, `EventPerson`); no version change, `docs/plugin-guide.md` regenerated |
| Source form (7.8) | A path setting could pick a folder | It can pick a file too (`picker: file`, with the endings it lists): `GET /api/setup/folders?files=.ics`. Built: `web/src/components/Sources.test.tsx` |
| Entry page and agenda (7.14, 7.1) | An entry's page showed its fields; an agenda row of a read event had no page | The entry's page lists who is asked with their answers and who invited; an agenda row of a kept date links to it. Built: `web/src/components/RecordPageRecords.test.tsx`, `web/src/components/TodayRail.test.tsx` |

## 113. The gate week's instruments and the Quality screen (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Measures (6.32) | Only the quality view's API had figures, and no screen showed any | `GET /api/quality` adds the window's first and last dates and, each as a count with its denominator for each day and for the window, silent closes out of all closes, wrong endings out of endings made (declined, undone, or a nudge recorded as done that the person reopened, found from the records), the person's own missed out of present, and the number of replay files. Built: `tests/test_gate_measures.py` |
| Missed out of present (6.32, 5.1) | Named, with nowhere to enter it | A core record `promise_count`, one for each person and day, entered on the Quality screen and never computed: `PUT /api/quality/counts/{day}` saves or corrects it and returns what the day held, `POST /api/quality/counts/{day}/undo` takes that back. It goes through export and import. `docs/plugin-guide.md` is regenerated. Built: `tests/test_gate_measures.py` |
| Quality screen (7.1, 7.9) | Not built | `#quality`, a link in Settings' list of sections: a section for each measure with its number out of its denominator and a list by day, the entry form (a date defaulting to today, two numbers, Save with an Undo toast), a plain empty state for each section, and the older measures in the same style. Not on Today. Built: `web/src/components/Quality.test.tsx` |
| The replay set (6.32) | Its last run was to be shown if recorded | Only the count is shown: the capability matrix keeps one day for every set of cases together, so it can't say when the replays alone last ran |

## 112. Which sign-in an agent runs as (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Agent accounts (6.16) | The check recorded nothing about whose sign-in an agent used | An adapter capability `identity()` reads it from the program by the account's `agent.identity_command` (with `identity_field`, or `identity_line` and `identity_pattern`), or says it can't tell and why; other adapters return none. The check records it beside the account's other results and Settings shows "Runs as <account>" or "Can't tell which sign-in it uses". Built: `tests/test_agent_identity.py`, `web/src/components/AiAccounts.test.tsx` |
| A change of sign-in (6.16, 7.7) | | A later check, or a run whose last reading is older than `agent.identity_recheck_seconds`, that reads a different account makes the Today line `identity` (`state` changed) with Keep (`POST /api/ai/accounts/{name}/identity/keep`) and Sign in again. Until answered the account takes open material only; other work waits queued with the cause `identity` and "until you answer", and goes after Keep. Built: `tests/test_agent_identity.py`, `web/src/shell/HeldLines.test.tsx` |
| A level that doesn't fit (6.16) | | The account setting `identity_level` (a list of data levels) holds work above those levels the same way, with an `identity` line (`state` level) naming the levels and how many requests wait. Built: `tests/test_agent_identity.py` |
| Settings (4.0), requests (5.1) | | `agent.identity_command`, `identity_field`, `identity_line`, `identity_pattern`, `identity_timeout_seconds`, `identity_recheck_seconds` and the account's `identity_level`, with demo values in both fictional workspaces; the first preset (a signed-in command-line app) carries its own status command. `StopCause` gains the kind `identity` (so `docs/plugin-guide.md` is regenerated) |

## 111. Work the assistant releases on its own keeps the person's hours (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Lines added on their own (6.35) | A line the assistant or a rule added showed at once, whatever the hour | One whose cause came in outside working hours, or inside quiet hours, is held until the next moment inside working hours and outside quiet hours; the cause is the input's own received time (else when its record was made). Decisions, questions, held items, runs waiting for a go, refusals, reviews, replies owed, learned proposals, unfiled items and the since-yesterday line are held; reminders, anything from the person's own note, their setup, stops and lines with no moment of arrival are not. Built: `tests/test_release_hours.py` |
| What waited (6.35, 7.7) | | Arrives together: the lines keep their places and one new `away` line, `While you were away: N things arrived`, sits at the top of the first group any of them is in, with no choices, and goes with that day. Built: `tests/test_release_hours.py`, `web/src/components/TodayAway.test.tsx` |
| A reminder the person set (6.32, 6.35) | Working hours moved a reminder set outside them to the next working start | It comes at the time chosen; only quiet hours hold it (`tests/test_reminder_lines.py`, `tests/test_release_hours.py`). The settings' descriptions say so |
| Notifications (6.32) | | Unchanged by rule: the browser notifies only for reminders, which are never held, and a held line is not in the queue, so it never notifies (`web/src/components/TodayAway.test.tsx`) |
| Settings (4.0) | | `steward.hold_outside_hours` (on by default, live, off in both fictional workspaces so the sandbox shows lines at any hour) |

## 110. Sign-in sources taken in quietly, and a first success in five minutes (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Sources a sign-in starts (6.27, 6.32) | They read the last day's mail and today's meetings with `first_run: recent`, one review line for each item | They use `first_run: intake`: the first read is one total, one go and one "Look over what was found" line for each source. Built: `tests/test_sign_in_sources.py`; journeys J2 and J6 expect it |
| The walkthrough's screens (7.8) | You, Your AI account, Mail and calendar, Backups, People, Done | "Your promises" is a screen of its own right after Mail and calendar, before Backups and People, with no setup step of its own (`WALKTHROUGH_STEPS`); the screen the person is on is kept as for any other. Built: `tests/test_first_promises.py`, `web/src/components/FirstPromises.test.tsx` |
| A first result (7.8, 6.32) | The walkthrough ended with nothing read; the first result was on Today after the first go | Once a mailbox is read and an AI account is chosen, "Your promises" offers "Look back over the last 14 days of your own mail" (the source's `first_run_days`) with its estimate and one Start, which is the go of every intake the sign-in brought, the workspace's first go included (`GET /api/setup/first-promises`, `POST /api/setup/first-promises/go`). After it, up to `ui.walkthrough.first_promises` (5) open promises are listed with who owes each to whom, its day and the words it came from, and one follow-up is ready to copy through the Follow-ups screen's own copy (`POST /api/followups/{person}/mark-sent` keeps the copy). With none found the screen says so and offers "Missed one". Built: `tests/test_first_promises.py`, `web/src/components/FirstPromises.test.tsx` |
| Settings (4.0) | | `ui.walkthrough.first_promises` (5), in `ui.yaml`, shown in Settings under You |

## 109. What a draft to someone else carries, first part (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Drafts to others (6.35) | Only openable links were checked | The `bookkeeping` lint (record ids, `language.internal_terms`) and the `long-quote` lint (`checks.tuning.long_quote.max_words`) on questions to someone else and drafted replies. Built: `tests/test_reader_checks.py` |

## 108. Learning from the sent version (2026-10-19)

| Where | Before | Now |
|---|---|---|
| What was copied (5.0, 6.35) | Nothing kept the text the person copied, or when | A `copy` record (COPY) keeps it exactly as copied: who it was for, when, and the question and action ids it covered. A follow-up marked as sent keeps one (taking the mark back forgets it); copying a drafted reply keeps one (`POST /api/replies/{id}/copied`, called by Copy reply even for a reviewed draft); copying the same message again moves the same copy forward. It is exported and imported like other records. Built: `tests/test_sent_version.py` |
| Matching the sent message (6.35) | A sent message only ended a reply owed it answered | In the same pass after a read that ends replies owed, each sent message not yet matched takes, by rules alone, the newest copy for the same recipient that was copied before it and no more than `steward.sent_match.window_days` (7) earlier and is at least `steward.sent_match.similarity` (0.6) alike (the applier's word-overlap measure); one message to one copy. Built: `tests/test_sent_version.py` |
| A style signal (6.22, 6.35) | An edit made in the app was the only `draft_edited` | A matched pair whose texts differ records `draft_edited` with the sent text, naming the person, the questions and actions covered and the copy; the same text records nothing. The learning loop proposes a style note by its usual path. Learning pair `sent-version-roles` uses a new correction kind `sent_version`. Built: `tests/test_sent_version.py`, `tests/test_pairs.py` |
| Copied but not found sent (6.35) | No line | After `steward.sent_match.ask_after_days` (2) with no match, one Today line, "Did your message to <name> go out?", only while a sent folder is being read: *Yes, another way* settles the copy, *Not sent* puts its questions back as unsent (settling it), *Still to send* asks again after the same number of days; each with Undo (`POST /api/copies/{id}/settle` and `unsettle`). Built: `tests/test_sent_version.py`, `web/src/components/TodaySentCheck.test.tsx` |
| Settings (4.0) | | `steward.sent_match.window_days`, `similarity` and `ask_after_days`, in `steward.yaml` with the other steward settings (the design had named them `drafts.sent_match.*`); plain labels in Settings |

## 107. Missed one (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Missed one (6.32) | Nothing let the person say in a plain sentence what the assistant missed | `POST /api/missed` takes a sentence, records a `missed` signal for the person (new optional `person` field on the signal) and hands the words in as their own note marked "The person says the assistant missed this", so the run adds the action, promise or reply owed it names with the words as evidence. A "Missed one" button in the header on every screen (in More on a phone) and in the empty states of Today and What changed since yesterday opens a small form with the cursor in its one field; sending says "Thanks: I'll add it." Built: `tests/test_missed_one.py`, `web/src/components/MissedOne.test.tsx` |
| Learning (6.22) | Each kind of correction taught at once or in a batch | `missed` joins the ones that teach at once, with the person's sentence as their words; no run is named, so it is outside the repeat-correction rate |
| Measures (6.20, 6.32) | The quality view had three measures | `GET /api/quality` adds `missed`: "Missed one" for each person and week with the week's dates, a week with none as zero. The Quality screen is not built, so no screen shows it yet |

## 106. A stance for each person: the person's choice, the chase line, a proposal from a correction (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Choosing a stance (6.34) | `stance` was a field with no screen; `steward.tracks` showed read-only | The person's page has a list "Who they are to you" (*I manage them*, *I work alongside them*, *I report to them*, *I only watch them*, and *Use my default (<its words>)*, which says what a person marked track-only counts as). A choice saves at once as the person's own `record.edit` with an undo toast. Settings gives `steward.default_stance` and `steward.tracks` plain labels, and a list drawn from a fixed set of values (`tracks`) is ticked, never typed. Built: `web/src/components/StancePicker.test.tsx`, `web/src/components/Settings.test.tsx`, `tests/test_stance_lines.py` |
| The chase line by stance (6.33) | Every waiting-on read "Chase <name>: ..." with Followed up first | `promises.late(...)` gives each entry the owner's stance (none for the person's own and for a reply owed). *Manage* and *alongside* are unchanged. *Report to* reads "Waiting on <name>: <words>, due <day>" with New date first and Done and Drop in the menu, no Followed up; the follow-up (nudge) line leaves such an action out too. *Only watch* has no line, and no follow-up line either, but the action still counts as covered, so no other line picks it up. Built: `tests/test_stance_lines.py`, `web/src/components/TodayPromises.test.tsx` |
| A correction proposes a stance (6.22, 6.34) | A "not my job" correction could only become a lesson | New op `person.stance` (the person, one of the four stances, evidence), system tier, offered to `learn-correction` (`LEARN_OPS`): it is held for the person's Keep like any system op from the assistant, never applied on its own, and a held line says "Change who <name> is to you: you report to them". The prompt says to propose it instead of a lesson when the person rejects asking someone at all. A refusal for no such person or for the person themselves is a `targets` check, and `invariants.yaml` names the op under `targets` and `evidence`. Learning pairs now score and keep a proposed stance (`stance-report-to`, `stance-watch`, `stance-alongside`, and the negative `stance-manage`). Built: `tests/test_stance_lines.py`, `tests/test_pairs.py` |

## 105. What changed since yesterday (2026-10-19)

| Where | Before | Now |
|---|---|---|
| What changed since yesterday (6.32, 6.35) | Closes the person hadn't seen were listed on Sources; everything else the assistant did was found by opening each change on What changed | One list of what the assistant or a rule did since the start of the previous day (the person's time zone) or since they last opened it, newest first, one entry for each record: the act, the record's words, the reason with the quote and who said it, seen or not, and the op to undo. The person's own changes and held items are not in it. The Today line `Look over what changed since yesterday` (risk group, below promises) counts what is unseen in plain words and goes when the list is opened; the "Since yesterday" screen has Open on each row and Undo in its menu. The last look is a new core record `look`, one for each person, only moving forward; a change the engine makes by its own rules records `by_rule`. Built: `tests/test_since_yesterday.py`, `web/src/components/SinceYesterday.test.tsx`, `web/src/components/TodaySince.test.tsx` |

## 104. Replies owed, and how they end (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Replies owed (6.32, 6.35) | The prompt added an action with a drafted reply for each message that asked the person something; nothing marked it as a reply, and the rules in `engine/replies_owed.py` were called by nothing | `action.add` takes `reply_owed`; the action stores `reply_owed`, `replies_to` and `asker`; the rules refuse a reply owed to automatic mail, mail the person sent or a message that says none is needed (`reply-not-owed`); one Today line each in "Send and follow up", oldest message first, `Reply to {name}: {subject}`, with the draft under it marked as a draft; Copy reply first (it approves the draft), then No reply needed, Answered another way and Edit in the menu. Built: `tests/test_reply_lines.py`, `web/src/components/TodayReplies.test.tsx` |
| Learning (6.22) | A dropped action was one `dropped` signal | Dropping a reply owed is the `no_reply_needed` signal, which the learning loop reads and the repeat-correction rate counts |
| Endings (6.33, 6.35) | A reply owed ended only by the model or by the person's tick | A message the person sent on the same conversation to the asker after the ask closes it at once, as their own act with the sent words as evidence, by rules when the sent folder's mail is taken in; Answered another way closes it for the person, with their words as the evidence when given; an answer by someone else is the model's `action.close` held for Keep, naming who answered (prompt, open list, golden case `reply-owed-answered-by-another-recipient`). `action.close` takes no evidence from the person's own act, like the other endings |
| Settings (4.0) | None | `steward.reply_thread_days` (14): how far apart two messages with the same subject and a person in common may be to count as one conversation, until the mail details carry thread headers; demo values in both fictional workspaces |
| Not yet | | Learning a style from the sent version, drafting rules for messages to others, sending (S1b) |

## 103. A sender's limit travels with the content (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Audience (6.35) | A source had no limit, so a draft could carry a message marked "internal only" to anyone | A marking in a message's new text (`language.limit_markings`, demo values in both fictional workspaces) gives its source an `audience`: the people it went to and came from, with the marking and its sentence. The invariant `audience` refuses a question, a reroute or a drafted reply to anyone outside the audience of a source it draws on, naming who the message is limited to. Built: `tests/test_audience.py` |
| Ops (6.7) | None | `source.limit` (data tier, evidence): the assistant narrows an audience to a group the message names, never widens; `source.widen` (person-only): add people or remove the limit, recorded with `widened_by`, with Undo |
| Screens (7.14) | The saved text of an input showed only its title and date | A limited source says "Limited to: <names>" with the sentence that limits it, and Widen (pick a person from the list, or Remove the limit) with an Undo toast. Built: `web/src/components/SourceLimit.test.tsx` |
| Not yet | | Records made from a limited source carrying the limit themselves; leaving a limited source out of a packet (no task drafts to a recipient named in its request today) |

## 102. A rejected ask is dropped (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Corrections (6.22) | A note rejecting a question could come back as the same ask in other words | The `rejected-ask` lint holds a new question to the same person when the note holds one of `language.rejecting_words`; the prompt says to drop with the note's words. Built: `tests/test_rejected_ask.py` |

## 101. The stance gate (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Stance (6.34) | Designed as a value list with `people.default_stance` | Four fixed meanings on the person (`stance`), worded on screen; `steward.default_stance` and `steward.tracks`; `asks_about` on `question.add`; the `stance` lint held after one return; the people list in packets says who each person is to the person. Built: `tests/test_stance.py` |
## 100. Reminders at a time, in the app (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Reminders (6.32) | Rules only (`engine/reminders.py`), called by nothing | An action's `remind_at`, set or snoozed by the person with Undo and no learning signal; a Today line `{task} · due now`, a late line for one that came due unseen, one "Saved during quiet hours" line for those that waited, each with Done and a Snooze menu showing the time each choice moves to. Built: `tests/test_reminder_lines.py`, `web/src/components/TodayReminders.test.tsx` |
| Settings (4.0, 6.32) | None for working or quiet hours | `steward.reminders.*`: working hours and days, quiet hours, how missed ones arrive, Later today and This evening, how late counts as late; picked from lists, live, refused in plain words when working hours end before they start |
| Notifications (6.32) | None | A browser notification for a reminder line that appears while the app is open, asked for only from a button in Settings |
| Not yet | | The reminder in the person's own calendar or by mail (S1b); desktop notifications from the tray (phase I) |

## 99. The designer's review of 6.33 and 6.35 (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Drafts to others (6.35) | A lint: one gap per message | One message per person per batch, asks numbered inside it, each with its own id; everything one gap needs is one ask |
| Dates (6.33) | Anything tied to an event stayed "no date" | Tied to a known calendar entry is due at it; tied to an event with no entry stays "no date" with its words kept |
| One promise from several sources (6.33) | A restatement with a date outside the window became a second promise | It is an `action.move` on the open promise, held for Keep with both quotes |
| No news by its date (6.33, 6.34) | "Chase" for every waiting-on | By stance: Chase and a draft for manage and alongside, "Waiting on" for report to, no line for only watch |

## 98. Drafts to other people, replies owed, and the week (2026-10-19, designed)

| Where | Before | Now |
|---|---|---|
| Sent version (6.35, new) | The style pair waited for L-more | A sent message matched to its draft ends the reply owed and is a style signal; a copied draft not found sent is asked about once |
| Drafts to others (6.35) | Only the question rules (6.8) | Lints: no bookkeeping, openable links, one gap per message, short quotes, never singling a person out |
| Replies owed (6.35) | Sent or "No reply needed" | Also *Answered another way*, and answered by someone else on the thread (held for Keep) |
| Audience (6.35) | A source had no limit | A sender's limit is the source's audience; a draft outside it is refused, and its packet leaves the source out |
| What changed (6.35) | One line | Each line says what the assistant did; unseen closes are one step away |
| Hours (6.35) | Quiet hours for notifications | Everything the assistant releases on its own waits for working hours |
| Monday briefing (6.32, 6.35) | The week's promises, deadlines, clashes, decisions | A copy-ready message up the line first, then the week, then three to five confirmed goals; nothing from Today repeated |

## 97. Stance, agent identity, dropped asks and adding from a link (2026-10-19, designed)

| Where | Before | Now |
|---|---|---|
| Stance (6.34, new) | A role per project only; nothing said who a person is to the person | A stance per person gates what may be drafted or asked them; "alongside" by default; what the person tracks is a setting; corrections propose a stance |
| Agent identity (6.16) | The account check proved a tier runs | It also reports which sign-in an agent runs as; a change or a level mismatch is a Today line |
| Corrections (6.22) | A rejecting correction could become a reworded ask | It drops the question with the person's reason; "check X first" checks X |
| Adding from a link (6.19) | Not said | The link is read first; an unknown status stays unknown; an unread link is said plainly |

## 96. Promises on screen (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Why a promise exists (6.33, 7.7) | An action showed its text, owners and day; the exact words, whom it was promised to, the words its day came from and how it was known were on the record only | `GET /api/promises/{id}` and the why block on the record's page, on Today's inspector and on the What changed row: the words, who owes it (owner format) and to whom, the day with its words and "Check this date", where it came from, "Said" or "Worked out", then what was heard since, newest first, a delivered part credited to the owners. Each of owner, promised to, day and how it is known is a list or date picker to correct (`POST /api/promises/{id}/correct`, the person's own `record.edit` with Undo; `promised_to` and `basis` now count as edits the assistant learns from). Built: `tests/test_promise_routes.py`, `web/src/components/PromiseWhy.test.tsx` |
| A held ending (7.6, 7.7) | "Close 'X'?" with Close it and Keep it open | For `action.close`, `drop`, `move` and `part` read from an input: one line "Keep: Ana finished 'Send the floor plan'" with the quoted words and who said it under it; Keep is the button, Not yet and Change are in the menu. Built: `tests/test_promise_lines.py`, `web/src/components/TodayPromises.test.tsx` |
| A promise with nothing heard (6.33, 7.7) | The person's own overdue to-dos were one counted line; chasing others was the follow-up line for what the person had sent | One `promise` line each, carrying every one of these and no other line: the person's own promises past their day (Done first; New date, Drop in the menu), a promise owed by someone else with its day within `steward.chase_dated_days` (7) or past, or with no day and nothing heard for `steward.chase_undated_days` (14) (Followed up first; New date, Done, Drop). News since its day, an ending waiting for Keep, a hold and a recent chase leave no line. Plain own to-dos stay on the overdue line; the follow-up line keeps questions and what no promise line carries. Built: `tests/test_promise_lines.py`, `web/src/components/TodayPromises.test.tsx` |
| The sent folder (6.33, 7.15) | A mailbox was one folder | A mailbox's row offers its sent folder as a second source: the server's own list (`GET /api/watch/{source}/folders`), the folder it marks as sent already picked, one button (`POST /api/watch/{source}/sent-folder`); the person is its author; taken in quietly like any new source. Built: `tests/test_sent_folder.py`, `web/src/components/Sources.test.tsx` |
| Settings (4.0) | n/a | New file `steward.yaml`: `chase_undated_days`, `chase_dated_days`; demo values in both fictional workspaces |

## 95. The gate week freezes what it measures (2026-10-19)

| Where | Before | Now |
|---|---|---|
| The gate week's measures (6.32) | Thresholds were set from the two measured days, with nothing said about testers or about changes during the counted week | Testers are held to the gate week's thresholds for missed out of present, silent closes and wrong endings; volume-dependent counts are reported, not gated; "Missed one" falling from week one to week two is the testers' own measure. During the counted week Today, the promise lines, the prompts and the model choices are frozen: fixes go on a list and land after it, except one that loses a promise or closes one wrongly, which is fixed at once and noted in the week's log |

## 94. Promises are actions (2026-10-19, designed)

| Where | Before | Now |
|---|---|---|
| Promises (6.33) | Named in 6.32, no shape | Actions gain `promised_to`, `basis`, `said_by`, `due_words`, `due_check` and `news`; dates read by rules first; endings `action.close`, `action.move`, `action.drop`, `action.part`, `action.news`; an ending from an input waits for the person; a promise past its date with no news is a line with its choices; every promise shows why |

## 93. A new source taken in quietly (2026-10-19)

| Where | Before | Now |
|---|---|---|
| A source's first read (6.4, 6.32, 4.5) | `baseline` (the default) noted what was there and handed in nothing, so an existing collection's open items were never followed; `recent` handed in the last day one by one | `intake` is the default: the first read notes everything, then hands in the mail of the last `first_run_days` (14) and every item of any other kind of source, each request marked with its source; nothing is reported as new, every open item found is followed whatever its age, and the other first runs work as before. Built: `tests/test_source_intake.py` |
| What the intake costs (6.16, 6.32) | n/a | Priced as one total (the requests and the sorting of its mail); below `ai.budgets.confirm_above_usd` it starts by itself (the first-go rule still applies on top); unpriced or above it, one Today line per source, "Take in Inbox: 12 items from the last 14 days", and one Go (`POST /api/watch/{source}/intake/go`). Built: `tests/test_source_intake.py`, `tests/test_source_intake_routes.py`, `web/src/shell/HeldLines.test.tsx` |
| What it found (7.7, 6.32) | n/a | Its results have no line of their own on Today until the list is opened; once all its work is finished, one line "Look over what was found in Inbox: 4 items" counts what was done and held, opens What changed narrowed to that source's intake and marks it seen (`POST /api/watch/{source}/intake/seen`, with Undo). Built: `tests/test_source_intake.py`, `tests/test_source_intake_routes.py`, `web/src/components/Today.test.tsx`, `web/src/components/WhatChanged.test.tsx` |
| How far back it looked (6.32, 7.7) | Older mail was silently not read | The first `watch_run` keeps `looked_back_to`; the coverage line says "Not looked at before Oct 5" with "Look further back": pick 30, 90 or 365 more days from a list, see the count and cost, confirm (`GET`/`POST /api/watch/{source}/look-back`); the older mail the connector already returned is taken in the same way and the date moves; a source that holds no mail that far back says "Only mail from <date> is available to read". Built: `tests/test_source_intake.py`, `tests/test_source_intake_routes.py`, `web/src/components/LookBack.test.tsx` |
| Settings (4.5, 4.9) | n/a | `watch.sources[].first_run: intake` (new default) and `first_run_days` (14); `watch.look_back_choices` ([30, 90, 365]); demo values in both fictional workspaces. Records: `request.intake`, `request.intake_seen`, `watch_run.looked_back_to` |


## 92. No close goes unseen, and records join by id (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Closes nobody saw (6.32) | A rule's close, mail set aside by a rule or the sorting, and the assistant's own drops and closes were each findable in a different place (or nowhere, for the assistant's), and none was counted | One list of closes the person neither made nor saw (what, when, which rule or run, why), `GET /api/silent-closes`, shown on Sources under "Closed without you seeing"; "Looks right" marks a rule's or the assistant's close as seen (`POST /api/silent-closes/seen`); set-aside mail is reviewed in its folder. `closes.measure` gives silent closes out of all closes in the quality window, with the counts for each kind, for the Quality screen. Built: `tests/test_silent_closes.py`, `web/src/components/Sources.test.tsx` |
| A rule or watch list that names a project or person (6.32, 4.x) | A triage rule could only hold names as free terms, so a renamed project made `terms-absent` close every change; a source's project and a rule's or lesson's reference filter were stored as typed | `triage[].projects` and `triage[].people` hold ids and the matchers read the current names; a name typed for a source's project, a triage rule, a connector setting marked `RefTo` or a rule's or lesson's reference filter is resolved to the id when saved, or refused in words; names already stored are joined once at start. A triage matcher now also gets `names` among its parameters. Built: `tests/test_join_by_id.py` |
| Settings (4.9) | n/a | `watch.triage[].projects` and `.people`, with descriptions; `dispatch.knowledge.quality_window_days` also bounds the closes figure |

## 91. A request's spending as a range (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Spending on a request (6.16, 6.32) | Each call was held to the amount needing a go, so fix rounds, searches and the stronger model together could pass it | One range for the whole request; all its calls together held to the amount (without a go) or what the go covered; reaching it stops for another go; outage runs free; the finished item shows the cost beside the range. Built: `tests/test_pipeline.py`, `web/src/components/WhatChanged.test.tsx` |

## 90. A rule's check runs before the change applies (2026-10-19)

| Where | Before | Now |
|---|---|---|
| A rule's check on an output (6.22) | Ran after the change was written and only counted the rule as applied | Runs in the applier's trial apply on what each op would write; a failure goes back to the assistant once, then holds the op for the person (an outward act is refused); the write checks again; the person's own or confirmed changes aren't stopped. Built: `tests/test_rule_check_before_apply.py` |

## 89. Coverage on Today (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Today's heading and empty queue (7.7, 6.32) | "Nothing needs you" whatever the sources did | A coverage line (what was read, when, and each source that couldn't be read, since when); an empty Today says "Nothing needs you · Read 3 sources, last at 7:40 AM", and "Nothing found that needs you" with the unread sources named when any couldn't be read. "Couldn't read" and "read, nothing new" differ in words and style. Built: `web/src/components/Coverage.test.tsx`, `web/src/components/Today.test.tsx` |
| A source that stays unread (6.4, 6.32) | A question after `failures_before_asking` failures, and a note on the rail's cards | Also, past `watch.unread_gap_factor` (2) times the source's own interval, one risk line `source_unread` that starts with what to do and stands in for that question; no-network tries never count. Built: `tests/test_watch.py`, `web/src/shell/HeldLines.test.tsx` |
## 88. A run that did no work is not an attempt (2026-10-19)

| Item | What the code did | What it does now |
|---|---|---|
| A command-line agent that failed with nothing on its error stream | `other`: retried and counted, and shown as "couldn't finish" with its banner as the reason | `no_work`: no attempt, no retry used, no fix round, never shown with the banner; waits and runs again, and after `dispatch.no_work_tries` comes to the person in plain words (6.16, 6.32). `errors.no_work` patterns and the `no_work` exit code let an account name its banner. Built: `tests/test_cli_agent.py::test_a_run_that_only_printed_a_banner_did_no_work_whatever_the_banner_says`, `tests/test_silent_stops.py::test_a_run_that_did_no_work_is_no_attempt_no_retry_no_fix_round_and_never_quotes_its_banner` |
| A call the computer's sleep cut off | `timeout` or `provider_down`: a retry was counted | `no_work` when the wall clock ran ahead of the time awake by more than `dispatch.sleep_gap_seconds`. Built: `tests/test_silent_stops.py::test_a_call_the_computer_sleeping_cut_off_did_no_work_and_a_slow_one_did_not` |
| The run record | Nothing said whether it did any work | `no_work`; left out of the day's counts, of "failing" and of spending |
| A network loss in the middle of a request | The look counted an attempt; a loss on the stronger tier's re-run ended on the first answer's problems; a loss while a cut-off draft was continued stopped the request with "couldn't be continued" | No attempt used, the request waits and starts afresh with every fix round. Built: `tests/test_silent_stops.py::test_a_network_lost_in_a_fix_round_waits_for_it_and_the_outage_uses_nothing_up`, `::test_a_network_lost_on_the_stronger_tier_waits_instead_of_ending_on_the_first_answer`, `tests/test_drafts.py::test_a_continuation_that_finds_no_network_waits_for_it_and_files_nothing_yet` |
| Settings | n/a | `dispatch.no_work_tries`, `dispatch.sleep_gap_seconds`, `ai.providers.<account>.agent.errors.no_work`, with descriptions and demo values (4.9) |

## 87. Which model does what, on the Settings screen (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Choosing the model for each kind of work (7.9, 6.16) | `ai.tasks.<kind>.tier` was only editable in `ai.yaml` | The AI section lists every kind of work (the core's and each running add-on's) with a list of the tiers to pick from, shown by their plain names and the account that does the work. A change is saved as made with Undo; "Changed · Reset" puts a kind back to the tier its role or its own default gives. The save is the general settings save: a map entry's setting is opened to the screens by `json_schema_extra={"screen_edit": True}` (`opened_to_screens`, `engine/settings.py`), so no other setting of the map opens with it. `ai.` keys are read at the moment of use, so a change applies to the next piece of work with no restart |
| A failed answer's second try (7.9, 6.16) | `ai.tiers.<tier>.escalate_to` was only editable in `ai.yaml` | One list per tier: Don't try again, or Try once more with another tier. Don't is a reset. The screen says it happens only when the app's own checks find a problem, never because the model says it isn't sure. Changing it no longer lifts the pauses on the accounts: only a change of an account, of a tier's accounts, of a kind's tier or of the routing rules does (`changes_who_takes_work`, `engine/worker.py`) |
| Routing rules (7.9, 6.16) | `ai.routing` was only editable in `ai.yaml` | Rows of kind of work (or any), longer than N characters, more than N quoted earlier messages, data level (or any) and the tier, added, removed and moved from a row's menu; the first match wins, and the screen says so. A list of objects is saved whole, validated against the schema. A rule with no condition would send everything, so a new rule waits unsaved until it has one |
| Spending (6.16, 7.9) | Not said where the stronger model is chosen | One line from `engine/dispatcher.py`: work sent to a stronger model first waits for the person's go above `ai.budgets.confirm_above_usd`; a second try on it happens only within that amount or the amount the person agreed to; nothing above `ai.budgets.per_run_usd` starts |
| Measurements feed the choice (6.16) | The capability matrix was shown on its own grid and decided nothing | Beside each kind of work, per model in use: "passes N of M", the cost of a passing run, and out of date or not measured where that is true (never a pass). `engine/ai/suggest.py` suggests the cheapest tier whose model passed every skill the kind needs (all measured, none out of date, none under `ai.skills.min_score`), keeping the tier in use on a tie, and says why when there is none; "Use this" saves it as any change. A rule is suggested, with "Add this rule", where the model in use is under the minimum on a skill and another tier passes it (a skill may name the request facts it is at risk on, `route_when` in `skills.yaml`). Nothing is applied by itself. Which skills a kind needs comes from the cases that run it: the core's cases, learning pairs, scenarios and replays run the note-reading kind, a plugin's case the kind it names, and a kind no case runs shows "no tests cover it". Built: `tests/test_ai_routing_settings.py`, `tests/test_ai_suggest.py`, `web/src/components/AiRouting.test.tsx` |
## 86. Phase B wave 4: the records screens (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Projects and People (7.13) | Both navigation entries opened one screen holding people, organizations, projects, the synced folder and the scheduled work, each a list with its form inline in the row | Two screens. Each is a table with a detail pane beside it from 1024px (a drawer below), columns that drop out as the window narrows and stack on a phone, and the name as the link to the record's page. Organizations are on People; the synced folder and the scheduled work are in Settings under Backups and sync. Built: `web/src/components/Projects.test.tsx`, `People.test.tsx`, `SyncPanel.test.tsx`, `JobsPanel.test.tsx`, `Settings.test.tsx`, `web/e2e/layout.spec.ts` |
| Forms for one record (7.14) | Inline inside a list row | A drawer for a person, a project and an organization, the cursor in the first field, a primary that says what is missing, a second drawer over the first when a form needs another record. Built: the tests above |
| Record page (7.14) | The record's own fields, as a list | Activity beside details: what is open with the record, **Completed** (finished work credited to who did it, with who said it was done), what happened to it. A person's page names the person, never their id. Built: `web/src/components/RecordPageRecords.test.tsx`, `tests/test_record_page.py` |
| Completed (7.13, 7.14) | A finished project looked like any other | `workspace.project.completed_status` (default `Done`, picked from the project status list) puts a project under **Completed** at the end of the table with its group kept; nothing is removed. Built: `tests/test_record_page.py::test_a_project_with_the_configured_done_status_is_marked_completed`, `web/src/components/Projects.test.tsx` |
| Open promise P13 (7.14) | "Who is this?" had an "Add a new person" button; no other person list could add a person | Every person list ends with **Add a person…**: the form opens in a drawer over the screen and the new person is the one picked. Built: `web/src/components/NextSteps.test.tsx`, `Projects.test.tsx` |
| Open promise P14 (7.14, 7.7) | Notes filed under no project were a group on the project list; actions, questions and facts with none were nowhere | **Unfiled** above the Projects table: every item the assistant filed with no project, **File under…** (a project list ending with "Add a project…"), several at once, one Undo, each filing a correction. A question's project is its `projects` list and a note's is `project`; both now record an `edited` signal (a question's was named `project`, so it never did). One Today line while there is any, never a zero. Built: `tests/test_unfiled.py`, `web/src/components/Unfiled.test.tsx`, `TodayRecords.test.tsx` |
| Held lines (7.6; answer 28) | "Review a waiting change" with one button, "Decide" | The action as a question with the reason and the words it rests on, and two answers that name the result ("Close it" and "Keep it open"). The other answer leaves it as it was and records `held_declined`; Undo takes it back. `POST /api/changesets/{id}/ops/{index}/decline` and `undecline`. Built: `tests/test_held_ask.py`, `web/src/components/TodayRecords.test.tsx`. Not built: "Drop it and draft the note" |
| After a move (7.7; answer 27) | Each question a follow-on run asked was its own line | One "Moved" line under the move with how many things to check, who was asked besides, and one row inside for each; a group of one is a normal row with its context; a second move leaves one group. Built: `tests/test_move_groups.py`. Not built: the per-row buttons the answer draws |
| A fact's source (7.14; answer 29) | A fact's record page listed its fields | The label that is the "Where it came from" link, the dashed Inferred tag (a pill variant) and Confirm it (the person's own `record.edit` of `basis`, the one change to it that is allowed). Built: `web/src/components/RecordPageRecords.test.tsx`, `tests/test_record_page.py`. Not built: the label on Knowledge and in the inspector |
| A series page (7.14; answer 30) | A series was a record with its fields; an item rolled forward out of sight | The next meeting's open items by person (the person last), where each rolled from, past meetings as one line each, the details beside; "for Thursday's print sync" on an item's row; "Print sync · 3 open" on the agenda rail. Built: `tests/test_series_page.py`, `web/src/components/SeriesPage.test.tsx`, `TodayRail.test.tsx`. The agenda stays the project management pack's |
## 85. The functional designer's answers to F1 to F14 (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Phase S (6.32) | Every steward feature in about six sessions | A first slice, then a gate week on the owner's own mail before the rest; sending (S1b) waits for the gate |
| Dependability (6.32) | Measures named, no rules for outages, renames or quiet intake | Records join by id; silent closes counted; an outage is not a failure; a new source is taken in quietly; coverage words; "Missed one" anywhere |
| Measures (6.20, 6.32) | Found and kept, false alerts, review time | Missed out of present, wrong out of proposed, wrong endings (a nudge isn't done), silent closes, Missed-one per week, a replay set |
| Sending (6.12, 6.32) | Exact content approved | Plus stale approvals, never twice, check with the service after a cut-off, uncertain shown as uncertain |
| Spending (6.16) | A go covers one call's estimate | A range for the whole request; outage retries free; actual spend shown |

All *not yet built*: the roadmap's phase S and tester milestone carry them.

## 84. The Settings rework and the screen wording review (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Settings layout (7.9) | One long screen: a form for each group, the rest behind "More settings", AI accounts, Lists and add-on files appended below | Sections down the side, each with its own address (`#settings/ai`, `backups`, `today`, `appearance`, `lists`, `files`, `advanced`, `addon/<name>`): You and the workspace, AI accounts, Sources (a link), Backups and sync, Today, Appearance, Lists, Add-on files, Advanced, then one for each add-on. Search sits above the list. "More settings" works within a section; Advanced is by topic, each topic closed until opened |
| Saving (7.9) | A Save button for each group, grey until something changed; only the live keys were meant to save at once | Every change is saved as it is made, with an Undo toast: choices and switches when they change, text and numbers when the cursor leaves or on Enter, lists on leaving. No Save button. Each save uses the fingerprint the screen last knew (the loaded one, then each save's answer), so saves in a row never race and Undo after later saves still works; a change made elsewhere is refused with "This was changed since you opened it" under that field and the typed value kept. A setting that needs a restart still waits for Restart now |
| Help (7.9) | The description and "Default: x" under every field, and "Back to default" under changed ones | Help beside each setting (from 640px of form; under it on a phone), and "Changed · Reset" beside the label of a setting that differs from its default; Reset has Undo |
| Settings, not built from the 7.9 text | A help pane that follows the focused field with "what reads this", two columns of fields, a save bar for settings that don't apply at once, separate admin sections | Not built: the help is beside each field, each field is one row, every change saves as made, and the admin settings are topics under Advanced |
| Appearance (7.9) | Theme, density and the brand were behind "More settings" | They are shown first in Appearance (`BASIC` in `engine/settings.py`) |
| Screen wording | `docs/project/wording-review-2026-10.md` was a table of proposals | Its triage is applied: 545 of the 734 rows are changed (to-do, calendar event, Add-ons, "AI service", abbreviations spelled out with their singular, plain words for internal terms, action-first buttons), 80 zero-count rows needed no new words, and 109 are not applied (the triage's own rejections, the style guide's own terms, the services' own "app registration", words the Settings rework replaced). "Go" is "Start" and "Waiting for you to start it" (the triage's answer to the rejected "Approve"); the working copy's words are "Open a working copy" and "Bring back your edits" |
| Counts (7.7, 7.1) | Some lines could say "0 items", "Notes (0)", "0 people", "0 changes", "0 tasks", "Found X with 0 models" or "2 new, 0 changed, 0 gone" | A count of zero is never said: a Today line that counts things and holds none is not shown, a panel with nothing has no badge, a filter with nothing is only its name, a read's counts leave out the zeros, and a server found with no models says so. Tests are beside each screen |
| Server wording | "Waiting for your go", "Waiting for the network", "No off-device backup is set up", "Dropped an action" and a few more were written by the server | They follow the sheet: "Waiting for you to start it", "Waiting for an internet connection", "No backup on another device is set up", "Dropped a to-do" |

## 83. The UI designer's answers 33 to 38 (2026-10-19)

| Where | Before | Now |
|---|---|---|
| Toasts (7.6) | Bottom left over the navigation column, 216px wide, capped at 45% of the height, kept longer with reduced motion | Bottom left of the content area, just right of the navigation (bottom center below 1280px), one line each (360 to 420px), at most three, a repeated message merged with a count, scroll padding for a focused row, F6 and Esc. Built: `web/src/lib/toasts.test.tsx`, `web/e2e/shell.spec.ts` |
| The inspector (7.7) | Empty until a line was clicked | Shows the line that has the cursor from the moment Today opens, headed by the line's subject and "1 of 9 · j / k"; remembers the line; "Nothing needs you" and the next check when empty. Built: `web/src/components/Today.test.tsx` |
| Line titles (7.7) | "Answer 1 decision" | A line that holds one item is titled by the item (`QueueLineView.subject`); several keep the count. Built: `tests/test_today_queue.py`, `web/src/components/Today.test.tsx` |
| To-do that waits on a person (7.7) | Words only | The person's name is a link to their group in Follow-ups when it matches one known full name. Built: `web/src/components/OnHold.test.tsx` |
| Draft a nudge (7.5) | "Follow up" opened the waiting items | One drafted message per person from a template, Copy then Mark sent, a shorter second one; questions record chases (`Question.followed_up`). Built: `tests/test_nudge.py`, `web/src/components/FollowUps.test.tsx` |
| Add-on lines on Today (7.7, 3.3) | All under "More for today" | `TodayLine.group` names one of the core's groups (plugin API 0.3.81); the fallback stays for lines with none, and the pack check warns. Built: `tests/test_plugin_api_0381.py` |
| "N new · Show" (7.7) | Held only while the cursor is in the queue | Held for the pointer, an open line and typing too; removals held as struck-through lines; a sticky pill; `Shift+N`; announced once; the sidebar count at once. Built: `web/src/components/Today.test.tsx` |
| Phone header (7.1) | The assistant's label beside the avatar | Only the logo, the status chip and the avatar; the assistant's state is in the chip's popover. Built: `web/src/shell/Header.test.tsx` |
| Rail to-dos (7.7) | A "Mark done" button in each row | A checkbox before the words, with Undo on the toast. Built: `web/src/components/TodayRail.test.tsx` |

## 82. Languages from a list, secrets typed on the screen, and add-ons from the screen (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Language (4.22, 7.0) | A box for a language tag, in Settings and on a project | A list of language tags shown by name in the browser's language, only languages the app reads notes in (English varieties today), labeled "How the assistant spells and writes"; a project's list starts with "Same as <the language it inherits>". A value set outside the list is added to it. Built: `tests/test_setup.py::test_the_language_setting_is_a_list_of_language_tags_that_names_its_list`, `web/src/components/Settings.test.tsx`, `web/src/components/Setup.test.tsx` |
| Secrets (4.0, 4.24, 7.0) | A password or private address was `env:NAME` or `file:/path`, set up somewhere else | A password box on a local app, kept in the private keys folder; "Where it is kept instead" is the second choice; "Kept on this computer" with Replace; a hosted app refuses it. Built: `tests/test_typed_secrets.py`, `web/src/components/Sources.test.tsx` |
| Add-ons (3.11, 6.29) | With no catalog the screen said so, and a private release needed a command line | An address field in place, adding and removing catalogs, and a read token asked for in place when a release can't be read. Built: `tests/test_catalog_screen.py`, `web/src/components/Addons.test.tsx` |
| Publishing a pack (3.14) | The guide named the entry's `release` only by its field | Step 1 and 2 say to attach the built wheel to the tagged release and give its address and SHA-256 (the release asset's API address for a private repository) |

## 81. Today as a queue, an inspector and a rail (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Today (7.7) | Four columns, with the full What changed, Follow-ups and plugin lists inside "Needs you" and the held lines above them | One ranked queue (a row for each line the engine ranks, the held lines among them), the selected line's items in an inspector from 1680px and under the line below that, and a rail of Agenda, Your to-dos and Came in. The count in the heading and beside Today in the menu is the number of lines. Built: `web/src/components/Today.test.tsx`, `web/src/components/TodayRail.test.tsx` |
| New lines (7.7) | "N new · Show" for any new line | Only while the cursor is inside the queue; elsewhere a new line joins the list at once. Built: `web/src/components/Today.test.tsx` |
| Toasts (7.6) | Bottom center | From 1280px at the bottom left over the navigation column, with room left under the last row; below that, bottom center above the bottom bar. Built: `web/e2e/shell.spec.ts` |
| Review cards (7.6) | One "Change this" for the card's send-back only | Each applied item has its own "Change this" in its menu. Built: `web/src/components/WhatChanged.test.tsx` |

## 80. A drafted reply on the action, and Measure's estimate and request (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Actions (5.1, 6.8) | A question someone asked the person was an action whose text was the reply | The reply is the action's own `reply` text with `reply_reviewed` (a draft until the person approves it or writes their own); new person-only op `action.reply` and `POST /api/actions/{id}/reply`; rewording a draft records `draft_edited`. Built: `tests/test_action_reply.py`, golden cases `question-asked-of-me-facts-hold-it` and `question-asked-of-me-nothing-holds-it` (`reply_has`, `no_reply`) |
| Capability matrix (6.16) | Only an evaluation run or a switch check filled it | `POST /api/ai/skills/{account}/estimate` and `.../measure` (refused above the confirm amount without `confirmed`, background, kept across a restart); a case may say its `data_level` and an account measures only what it may see. Built: `tests/test_measure_account.py`. Not built: the Measure screen and the proof with each adapter kind's own fake service (phase B) |

## 79. The assistant moves a calendar entry from an input (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Calendar entries (6.7) | No op the assistant may use changed an entry's day or time; only the person's edit started the follow-on run | `event.set` (data tier, evidence required, Undo) changes an entry's `start` and/or `end`, is offered to reading notes, and its save starts the follow-on run. Built: `tests/test_event_set.py`, golden case `moved-meeting-moves-its-entry`. A move a connected calendar's sync writes still starts nothing (a sync writes `snapshot` records with no changeset) |

## 78. A follow-on run asks; it never changes an action's date (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Follow-on runs (6.7) | The run moved the day or words of a tied action nobody was told about, with Undo | The run never changes an action's day or words (`record.set` is not one of its ops; the `follow-on-reach` check refuses it). For each tied action with a date the move may affect (on the entry, citing the old day, or due between the old and the new day, the new day included) it asks one `decision` question: the action's owner, or the person when the owner is the person or none, or when the project holds no link the owner could open (then the question says who to ask). When the moved entry or replaced fact carried more than one dated action (an agenda item, a question, a fact, an action with notes, or several actions), one `decision` question asks the person whether the plan still holds. Who is asked and which plans are asked about are decided by code and shown in the packet. Built: `tests/test_follow_on.py::test_no_due_or_text_change_ever_applies_from_a_follow_on_run`, `::test_an_action_due_between_the_old_and_the_new_day_is_tied_and_one_outside_it_is_not`, `::test_an_action_due_between_the_old_and_new_day_gets_a_question_to_its_owner_that_waits_and_undoes`, `::test_a_moved_entry_that_carried_more_than_a_dated_action_asks_the_person_whether_the_plan_holds` |

## 77. Records name the entry or series they belong to (2026-10-16)

| Where | Before | Now |
|---|---|---|
| Calendar (5.1, 6.7) | An entry stood alone; an action, question or fact couldn't name one | A `series` record (title, project, `repeats` in the person's words); an entry names its series (`event.series`); an action, a question and a fact name the entry or series they belong to. New ops `series.add` and `series.link`; `record.set` takes `event` and `series`. Built: `tests/test_series.py` |
| Follow-on changes (6.7) | An item on a series had no instance to sit on | It sits on the series' next instance and the worker rolls an open action or question to the next one once a day, each move a ledger entry. The packet lists the series and entries to come with their ids; the notes prompt says when to name one. Built after: the one request on a move (below). Not built: the agenda (the project management pack's) |
| Follow-on runs (6.7) | Nothing followed a moved date or a replaced fact | One request per save, queued in its transaction, for a moved entry day, an action's moved due day or a replaced fact; the run reads what is tied (found by code), moves the person's own actions with Undo, drafts a correction for anyone already reached, and starts no other run. New task kind `follow-on`, keys `dispatch.knowledge.follow_on`, `follow_on_max_tied`, `follow_on_match` and `language.date_patterns`, check `follow-on-reach`. Not built: the assistant's own move of an entry, two of the roadmap's candidates, a link for a correction about an action's notice |

## 76. How a fact is known, "Not now", the floor, the catch-up's words and series facts (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Facts (6.19) | A fact carried its source and trust only | Also `basis` (person, inferred or said, with `said_by`). An inference applies marked as one; a close, a changed date or owner, or a routing that rests only on it is held for one click (`inference-confirm`). Reading notes is offered `question.mark_sent`, which applies only from the person's own note. Built: `test_fact_basis.py`. Not built: outbound filtering (phase C4), the mark on screen, the change note saying who made each part |
| Rules review (6.21, 6.22) | The line left only when the person kept, narrowed or retired a rule | "Not now" also starts its week: the `not_now` signal. Built: `test_rule_review.py`, `HeldLines.test.tsx` |
| Refusals (6.22) | A check's guidance came in only at a share of at least `min_runs` runs | Also at `knowledge.refusals_to_packet.floor` (3) refusals by one check within `floor_days` (7). Built: `test_refusals.py` |
| Catch-up (6.22) | A kind was learned from through its newest correction | Through the newest that holds the person's own words, else the newest. Built: `test_catch_up_learning.py` |
| Facts (6.22) | Facts went only with their exact project | A fact marked `reaches_children` also goes with the projects inside its own. Built: `test_knowledge_section.py` |

## 75. Three checks the designer's answers asked for, and two tests (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Drops (6.8) | Every drop by the assistant applied | A drop of a question marked sent, or of an action someone was told about or chased for, is held for the person's look with a plain reason; the person's own drop and one they confirm apply. Built: `test_hold_drop_fold.py` |
| Discarded proposals (6.22) | Search returned an input unflagged; routing could be proposed again | Search flags an input whose proposal the person discarded; the invariant `discarded-routing` refuses a routing that matches a discarded routing proposal unless it rests on the person's own words. Built: `test_proposals.py` |
| Retiring attempts (6.7) | The late answer of a retired attempt was untested | A test of the whole sequence. Built: `test_attempts_retire.py` |
| Capability matrix (6.16) | The switch check's runs were not tested | A test that it adds them. Built: `test_switch_check.py` |

## 74. A capability matrix (2026-10-15)

| Where | Before | Now |
|---|---|---|
| AI accounts (6.16) | Capabilities are stated features from a catalog | Also skills measured per model for every kind of account (native, OpenAI-compatible, aggregator, command-line agent): a skills list packs extend, a matrix with staleness and cost per passing run, a grid in Settings, routing to the cheapest model that measures well enough, and a Today line to decide. Built (step 1): the skills list, `skills:` on every case, the matrix with staleness, `GET /api/ai/skills`, "What it can do" in Settings (`tests/test_capability_matrix.py`, `AiAccounts.test.tsx`); not yet built: "Measure", the export, C0 step 2 |

## 73. What the pairs on the backup model found (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Reach (6.22) | `task_kinds` and `records` took any words | Only kinds of work and record types there are, listed in the op reference. Built: `test_knowledge_records.py`, `test_op_reference.py` |
| Routing in the packet (6.6) | Every word of the topic in the input, exactly | Most of the topic's words (`knowledge.routing_match`), plurals and hyphens folded. Built: `test_knowledge_section.py` |
| One piece of learning (6.22) | "Not a project" and "It's part of" kept an entry and also queued a learning run | The answer's entry is the learning; no run is queued. Built: `test_next_steps.py` |
| The learning packet (6.22) | The kind of work corrected wasn't said | It is said, and an entry naming kinds of work must include it. Built: `test_learn_correction.py` |

## 72. Backups and adding accounts from Settings (2026-10-15)

| Where | Before | Now |
|---|---|---|
| AI accounts (7.16) | A backup account was only the raw tier setting; Settings had no way to add an account | "Use as backup" checks the account for each kind of work and adds it to their backups with Undo; "Add an account" in Settings opens the guide's AI step. Built: `AiAccounts.test.tsx`, `tests/test_setup.py` |
| AI accounts (7.16) | "Add an account" opens the setup guide | It adds the account in place in Settings, with the AI choices only (owner). Not built: phase B |

## 71. The functional designer's answers to the round of 2026-10-15

| Where | Before | Now |
|---|---|---|
| Calendar entries (6.7) | An entry beside any dated fact or action | Real events only; an action's date is a `record.set` on its due |
| Questions (6.8) | A question to the PM became an action; anyone's content could retitle a question | One action with a drafted reply; only the person rewords, outside content adds a note |
| Decisions and drops (6.8) | Decisions to the PM; every drop applied | Whoever decides; a drop of something already sent waits for a look; three more ops the assistant may propose |
| Follow-on runs (6.7) | One entry | A series, rolling items; the assistant's moves start it; one hop; what was sent gets a drafted correction |
| Facts (6.19) | An inference not described | An inference only feeds the record and never closes anything; it proposes the close |
| Learning (6.6, 6.21, 6.22) | — | Terms by audience; outside mail never re-routes; discarded proposals flagged in search; catch-up from the person's words; series facts; "Not now"; a refusal floor; checks on every output; more reported-speech words |
| Scope (6.18) | "we/us/our" counted as owed | Requests addressed to the person count; a person with no team is asked about once |
| Evaluation (6.16) | Any extra fails | Extras weighed by reach and tracked over time; replayed misses as a third set |
| Follow-ups (7.5) | One message | Two copy tables (actions, questions) |
| Plan | L7 about 1.5 sessions; go/no-go in the charter | L7 about 4 sessions, before phase B; the go/no-go stays set aside; the owner tests after phase B and uses it after phase C |

All *not yet built*: L7, phase B and phase P.

## 70. The functional designer's lessons from running (2026-10-15)

| Where | Before | Now |
|---|---|---|
| Decisions (6.8, 5.1) | A decision is a question to the PM | A decision goes to whoever decides, the PM when nobody is named; an option inside an answer is a decision for them (owner). Built in L7; moving one keeps it a decision |
| Follow-ups (6.19) | A follow-up went to whoever the input named | A follow-up goes to whoever made the claim or owns the thing; when neither is clear it is a question to the person about who to ask, never someone known from a passing mention. Built in L7 |
| Follow-on changes (6.7) | None | Moving or retitling a dated record, or replacing a fact, makes one request that brings tied records in line; records can name the calendar entry they belong to. Built in L7; the agenda is the project management pack's |
| Facts (6.19) | Source and trust only | Each fact says who it rests on: the person, the assistant's inference or someone named; a correction replaces the fact it contradicts. Built in L7 |
| Evaluation (6.16) | Cases start from an input | Replay cases start from the person's own action and score the end state. Built in L7 |
| Follow-ups (phase B) | One message to copy per person | A Copy table per person (tab-separated and HTML, with a reply column), from the same data, with no AI run |

## 71. The UI designer's answers 25, 26, 31 and 32, built (2026-10-16)

| Where | Before | Now |
|---|---|---|
| AI accounts (7.16) | A list of rows by id with a Test button each; Add opened the setup guide | One place in Settings: a line saying who does the work and who stands in, rows with a role pill, the person's own name, a state line and one next step, "What is it for?" in an add drawer and in each row's menu; removing the main account says what happens. A provider has an optional `label` (`ai.providers.<name>.label`), and the settings' ids are never shown |
| What each model can do (6.16, 7.16) | A disclosure under each row | A grid of kinds of work by account and model on its own page, pass rate first, the cheapest passing cell marked, Measure with its estimate; one line on each row |
| Rules review (7.6) | "Not now" a button beside the answer | "Not now" in the line's menu with what it does; the 7.6 rule: a second answer is a visible button, a postponement is in the menu |
| Follow-ups (7.5) | One message per person | A Message / Table switch; the table is shown before it is copied; Copy as table (HTML) and Copy for a spreadsheet (tab-separated) |
| Today | None | A held line when work has no AI account; the backup line's button is at the row's end |

## Plugin host, API 0.1 (2026-10-09)

The first host implements the next-task brief: per-workspace registries, strict manifests and version/dependency checks,
bundled/private/installed discovery, schema-validated plugin settings, record and op registration, deterministic validators,
task kinds, and named events after commit. The existing UI change counter remains separate.

Plugins import `engine.plugin_api` (the existing package), and register exactly what their manifest declares. Op callbacks
receive a writer limited to their model's declared record kinds/fields; writes retain versions, provenance and the ledger.
Handlers receive read-only core/own-record access and staged commands for requests or questions to the PM. A failing callback
is disabled for the run; an op failure rolls back its writes through a savepoint. Runtime dependency failures disable their
consumers. Status is exposed by the authenticated `/api/plugins` endpoint; no UI panels were added.

Exports use `data/<plugin>/<kind>.json` for plugin records. Import refuses unknown record kinds instead of dropping data,
and emits no events while restoring history. Disabling a plugin retains its data; enabling it again restores typed access.
Both fictional workspaces include the example plugin's settings and records. Self-check verifies both with and without
plugins, validates every bundled manifest against registration, and compares nested exports byte for byte.

The later 1.0 extension points and reach capabilities (interfaces, panels, jobs, network, secrets and tools) are explicitly
refused by this host, not silently ignored. The contract and current limitations are in `docs/plugin-api-0.x.md`.

- **Page width (7.0):** never wider than the window, with no sideways page scroll at any width (owner, 2026-10-16). To be built with a browser test of every main screen at several widths (open promise P19).

- **The daily steward (6.32, new):** the core is a daily assistant for anyone, with time (reminders, repeating to-dos, briefs), promises both ways, replies owed, meeting prep, people memory, dates in documents, areas of life, capture from anywhere, suggestions and talking to the assistant; planned as phase S before the installers (owner, 2026-10-17).
- **The daily steward, after review (6.32):** promises and how they resolve come first; attention budget, capacity check, missed-while-asleep reminders and outcome measures added (2026-10-17).
- **Mail and calendar management (6.32, 6.3, 6.12):** approved acts on mail and calendar in 1.0 through the publisher, brought forward to phase S1b; reminders through the person's own calendar or mail; no third-party push (owner, 2026-10-17).
- **The evening wrap-up's and Monday briefing's shape (6.32):** their sections in a fixed order, under the morning brief's line rules (2026-10-18).
- **The morning brief's shape (6.32):** three sections in a fixed order, plain fact lines, at-risk lines that say when, yes lines that start with what the person does, empty sections left out and a quiet day as one line (2026-10-17).
