# What changed since the first design

This note is for the author of the first version of this design (the single `DESIGN.md` that started this repository). It
summarizes what changed, why, and where everything now lives, so you can review the new version without diffing 1,400 lines.

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
| 2. Don't let the cheapest model write the guards | Two task kinds. `learn.correction` writes lessons, lesson updates and rules on the stronger tier. `learn.input` proposes terms, routing and facts on the input's own tier. Anything after a repeat correction always uses the stronger tier (6.22, 4.25). |
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
| 6. A direct edit isn't always a correction | The `learn.correction` packet carries the inputs received after the original run on the same records, and defaults to "nothing to generalize" unless the edit contradicts the evidence the run had (phase L). |
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
| B4. Priority isn't person-only | Right: only `budget_usd` and `content_levels` were. `project.priority` is now person-only (phase L0). Capacity is a workplace pack field, not core. |
| B5. Actions can't record who did the work | Right: the code has only `told`. Actions gain `followed_up` (a chase, separate from a notice), `done_by` and `reported_by`, with Followed up in L0. |
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
| 2. "Done" checked mechanically | A "Built" row or a checked roadmap box cites its test, and the self-check fails when a cited test doesn't exist (phase L0). The fifth claimed-done item you found (milestone 2's evaluation run) is added to the review. |
| 3. The wording rule at the response boundary | In tests and dev mode, the API's response serializer refuses user-facing text with `.yaml`, `env:`, a dotted key path or a command, so the journey tests fail on the first leak, runtime messages included (phase A2, beside rewriting the known strings). |
| 4. A ceiling as well as a floor | The first-five-minutes brief says what those minutes cost at most (`CLAUDE.md`), and the first run after setup shows its estimate even below the confirm amount (design 7.8, phase A2). |
| Section 4 is superseded | Marked so, pointing to the roadmap. |
| Section 5 should be checked off | Each row has a state: eight fixed in the design text, and one (the near-duplicate threshold) fixed in the text with the code setting still open in L0. |

## 25. Phase A starts: what the code showed (2026-10-12)

Each phase A item was checked in the code before it was designed. Three gaps were worse than the plan said.

| Item | What the code does today | What phase A builds |
|---|---|---|
| Crashed runs | A run left `running` by a crash is never picked up again | Queued again on start; held for the person if found stuck twice (6.13). **Built (A2):** interruptions are counted from the request's ledger, since `attempts` also counts a person's Try again |
| Test source | "A stand-in source for tests" is offered under Add a source | Connectors can be marked test-only and aren't offered. **Built (A2)** |
| Check now | The source's Read now and the schedule can read one source at the same moment; Came in has no refresh | A lock per source, and Check now on Came in (7.15). **Built (A2)** |
| Backups | Nothing restores one | `cockpit restore --backup` makes a workspace from one dated backup (5.0). **Built (A1)** |
| First run's cost | No notion of a first run | The first runs wait for one Go with their total (7.8, `ai.budgets.first_go`). **Built (A2)** |
| Local guards | No `Host` or `Origin` check; any listening address | The allowed hosts and origins, and loopback only in local mode (12.1). **Built (A2)** |
| Install | The route existed; the screen had no button | Install, Update now and Remove (3.11). Only updating a running pack holds work until the restart. **Built (A2)** |
| Acceptance scenario, step 7 | The header chip said "Backup needed" until a backup succeeded and then only "Live", with the age in the popover; Today never mentioned a backup | A backup line on Today while a backup needs attention, and the age on the chip itself (7.1, 7.7). **Built (A3)** |
| Personal and sales mail | Nothing tells it apart; it reaches the assistant like work mail | A Set aside folder: the person's rules, the mail's own category and bulk headers, then a header-only sorting run; it never reaches the assistant or learning (6.5, L0) |
| Onboarding | A setup guide reached from a line on Today; mail and calendar last, add-ons installed elsewhere, a restart per step | A new-start walkthrough that opens by itself: You, AI account, Mail and calendar (install, one restart, sign in), Backups, People, Done on the first-Go line; and a getting-started page (7.8, A4) |
| Mail and calendar services | The walkthrough told a mail or calendar connector from a word list in its name | A connector declares what it reads, in its registration and in the manifest, so an add-on in a catalog is offered too; the word list stays only for a connector that does not declare it (3.2, 3.3, 7.8; plugin API 0.3.56) |
| Wording | Checked only in the screens' own wording file | Screen text typed in the API models and checked when it leaves, in tests and development. **Built (A2):** the audit's 47 strings and every further leak the tests found rewritten; a secret field's input hint is the one exemption until phase B |

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
