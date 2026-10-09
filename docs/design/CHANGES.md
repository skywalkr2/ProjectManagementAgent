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
- **Dependencies and baselines are now core** (6.23): what waits on what, need-by dates, at-risk warnings on Today, and
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
- **Core features for future packs** (sales, writing): long text stored once per version with authorship (5.0), drafts as
  prose that the person reviews (6.7), a file channel (6.3), stages for work that moves through steps (6.26), an independent
  second opinion on another account (6.16), and cost control: estimates, a go above a set amount, budgets per task kind and per
  record (6.16). In version 1, before the plugin API is frozen.
- **Plugins working together** (3.9): packs share core records (a book is one project for both the writing and publishing
  packs), offer versioned interfaces to each other, subscribe to events and can request each other's task kinds, always
  through the core. Each pack still works alone.
