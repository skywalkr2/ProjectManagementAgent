# Part 5. Data model and storage

## 5.0 Storage model

**A database is the system of record; git keeps a readable history.** Many of the product's rules (saves merge and never
clobber, one writer at a time, ids never repeat, undo only what hasn't changed since, one scheduler at a time) are guarantees a
database gives for free and files make you rebuild by hand. So:

- **SQLite** in the workspace (`cockpit.db`) holds every record. One file, transactional, safe for concurrent readers and one
  writer, fine locally and on a persistent volume when hosted. Postgres is a later backend for multi-user (4.15).
- **Config stays YAML** in `config/`, edited by people and committed to git (Part 4).
- **Sources stay files:** every input's text is saved under `sources/` by content hash and registered in the database.
- **`data/` is a readable export and a working recovery path:** the engine writes records as JSON files under `data/` (one
  file per record type, stable ordering), long text as plain files beside them, and the ledger as append-only files under
  `data/ledger/`, and commits them, with `config/`, to the workspace's git. That gives history, diffs and a plain-text view; an
  off-site copy through a remote waits for phase E, with the care of backups (12.1). The running engine never reads it; `cockpit import` does (recovery, fixtures, moving backends).
  `cockpit export` writes it, and the worker writes and commits it on the `storage.export.every_minutes` schedule when the
  workspace has a repository (4.15). Writing it after each applied changeset batch is not built.
- **Fictional workspaces** are committed as `config/` plus `data/` JSON; tests import them into a fresh database.

**The ledger.** Every applied op is written, in the same transaction as the change itself, to an append-only ledger: changeset
id, op, record id, field, value before, value after, request, provenance (6.6), actor (assistant, PM, rule, plugin) and time.
The ledger is the history view, the audit log and the basis for undo (6.7). It is never edited.

**Long text.** Some fields hold long prose: a statement of work, a proposal, a report, long promotional copy. A record type marks such a field as
`long_text` and names its format: `plain` (units are blank-line paragraphs) or `markdown` (units are its blocks; a fenced block,
a list or a multi-paragraph footnote is one unit), both shipped by the core, or a format a plugin registers (3.3). Every
passage-level feature works in those units: paragraph anchors (6.7), authorship, the compare view's per-passage choices (7.2)
and lint anchors. Its content is stored once per version in a text store (by content hash, like sources), and the record and the
ledger hold the hash, so thirty edits of a proposal are thirty versions, not thirty copies inside the ledger. Each version keeps
**authorship by passage**, in three kinds: written by the person, drafted by the assistant, and the person's text changed by the
assistant (disclosure rules often treat drafting and editing differently), with the model run that produced the
assistant's spans. That serves review (what changed since I last read it, as a word-level diff, 7.4), disclosure rules that ask
how much of a work an AI wrote, and undo, which restores an earlier version like any other field. The export writes long text
as plain files beside the records, so it reads well in git and survives the round trip.

Each version is a `text_version` record (5.1): the record and field it belongs to, a number that is never reused, the hash of
its text (the text itself is in the workspace's `texts/` folder), its format, how it arose (`edit`, `draft`, `proposal`,
`merge` or `import`), whether it is `pending`, `accepted`, `merged` or `discarded`, the version it was made from, its
authorship by passage, and for an anchored draft its paragraph map. A plugin or the assistant never writes the field
directly: the assistant's text is always a pending draft, and the person's own edits are accepted as theirs (decisions,
2026-10-12, "Long text is versioned…" and "Drafts are prose…"). Accepting is change by change; when the current text moved on
since the version's base, the merge is three-way: changes only in the current text are kept, changes only in the proposal are
offered, and a passage both changed is the person's pick.

**Recovery.** Git history is only useful if it can be loaded back, so recovery is a tested feature, not an afterthought:

- **Round trip:** `import(export(db))` gives back the same records, ids, versions and ledger. The self-check runs it on both
  fictional workspaces, and every record or config migration is tested through it.
- **A whole backup** (*phase A*): `cockpit restore --backup <backup folder> <new folder>` makes a workspace from one dated
  backup. It checks the database before copying, never writes into a folder that has files, and never touches the
  running workspace (decisions, 2026-10-12, "Phase A's design calls").
- **Point in time** (*designed, not yet built*; roadmap, phase E): `cockpit restore --as-of <time>` imports the last export
  before that time and replays the ledger up to it. A restore is itself recorded in the ledger, so it can be undone.
- **One record** (*designed, not yet built*; roadmap, phase L-more): the Admin tab can show any record as it was at a past time (from the ledger) and
  restore just that record, as a changeset the PM sees.
- **Off the machine, on its own:** local installs keep everything on one computer, so backups to somewhere else are expected,
  not optional (4.15, 11.1). While the app runs, a background thread makes a full backup whenever one is due, including right
  after the computer wakes, and tries again after a failure; it never creates a missing target folder, so a drive that isn't
  connected can't turn into a "backup" on the local disk (decisions, 2026-10-11, "Backups run on their own…"). The database
  is copied with SQLite's online backup, with `config/`, `sources/`, `files/`, `texts/` and `plugin-data/`. A backup to a
  target outside the person's control is encrypted (`backups.encrypt`, *phase L-core*, 12.1).

**Provenance.** Each ledger entry records whether the write came from trusted or untrusted content (12.2), so every field's
provenance is known; packets mark untrusted-derived fields as data (6.6).

**Record versions.** Every record carries a version that goes up on each write. Writes state the version they read; a write
against a newer version is merged field by field when the fields differ and refused when the same field changed, so two
writers never silently overwrite each other.

**Ids.** Ids come from per-kind sequences in the database and are never reused (`Q-1042` is always the same question, even
after it closes). Ids are shown only where the PM needs a handle (logs, the Admin tab), never in labels or outgoing messages.

**Jobs.** Scheduled and queued work lives in a jobs table with leases: a worker takes a job by writing a lease with an expiry,
so a crashed worker's job is picked up again. Only one scheduler holding the scheduler lease at a time is *designed, not
yet built* (6.14); today the instance lease keeps a second copy of the app from running at all.

**One running instance per workspace.** The engine takes an instance lease at start (instance id, host, heartbeat). A second
instance on the same workspace (the laptop and a host at once, say) refuses to start and says where it is open: in another
window on this computer, or on another computer by its name. The holder's id begins with its process id. A start takes the
lease at once, without a command, when the lease was written on this computer and that process is no longer running (one
log line says so); a lease whose process is running, one from another computer, and one whose id names no process are
refused until the heartbeat expires, and the refusal names `cockpit takeover` only as the last resort for a copy that has
stopped but this computer can't tell. `cockpit takeover` takes the lease immediately with a confirmation.

**Two computers through a synced folder.** A person who works on two computers keeps one workspace and hands it over through
a folder that a file-sync service keeps in step (4.15, `sync`). File-by-file syncing corrupts live databases and git
repositories, so neither ever lives in the synced folder:

- **Local only:** each computer keeps its own copy of the workspace (database, git history, `sources/`) on local disk. While
  an install holds the workspace, its database is the record of truth.
- **The synced folder is a complete, readable copy:** after every applied changeset the engine writes the export there, laid
  out **one folder per project** (its records, every version of its long text as plain files with authorship, its history and
  findings) plus the workspace-wide records (people, teams, config, sequences, the ledger). Each file is written beside its
  target and then renamed into place, so a half-written file never syncs. A record type (core or plugin) declares how its
  records and long text are named in the project folder (`proposal.md`, `sections/07-pricing.md`), so the folder reads
  naturally in any editor (`layout` on the record type; types without one are only in the machine copy). The folder
  also holds a machine copy in `.cockpit/` (the plain export, config and plugin data), which is what loading the folder
  reads, so it round-trips through `cockpit import` exactly; the readable files are generated from the same records, and
  edits to them come back as proposals. A file whose content no longer matches what the cockpit wrote is never
  overwritten or removed.
- **Starting sets come after an import, never before** (L1): a workspace's rules file is the starting set of its `rule`
  records (4.10). They are made when the workspace starts or is created, after any import has loaded its own records
  (an import needs an empty database), so an export's rules, with their history, come back as they were and only a rule with
  no record is made. **Built:** `tests/test_rules_facts_signals.py::test_rules_and_their_history_survive_export_and_import`.
- **Nested projects nest their folders:** a project with a parent (5.1) has its folder inside its parent's, so a series folder
  holds its titles. Moving a project to another parent moves its folder, as one op.
- **Sources travel with their project:** handover needs every source on the other computer, so each source (the original
  file as received, such as a `.docx`, and its extracted text) is written to its project's `sources/` folder, or to the
  workspace-wide one when it belongs to none. Evidence then resolves on either computer. Retention (4.15) still applies.
  Sources above a configured data level are encrypted with a key reference before they reach the folder, or left out, in
  which case the other computer shows their evidence as "kept on the other computer" (4.15 `sync`).
- **The cockpit knows its own files:** every file the cockpit writes into the folder (the export, its sources, and outputs
  such as approved PDFs and ebooks from the file channel, 6.3) has its content hash recorded at write time. The watcher ignores
  files that still match, so the cockpit's own writes are never mistaken for outside edits. Outputs go to each project's
  `outputs/` folder; if one is changed or deleted outside, it shows as "changed outside the cockpit: rebuild or keep", never as
  a content edit, because outputs are built from the records, not the other way round.
- **The lease lives in the folder too:** holder (this install's own id), computer, heartbeat and how far the folder's history
  goes (`.cockpit/lease.json`). Opening the workspace on the other computer while the holder's heartbeat is fresh is refused,
  naming the computer. Once it is released or stale, the opening install compares the two ledgers entry by entry: when the
  folder's continues this computer's, it backs up its local database, loads the folder's newer state (config and plugin data
  too; storage and server settings stay per computer), and takes the lease. A running install that finds the lease taken
  by another stops writing to the folder. A new computer is set up with `cockpit init <path> --sync <folder>`. Plugin code
  is not copied between computers: a plugin the folder's workspace uses that is missing here stops the load, with the reason.
- **Only verified files load:** a load reads only files the manifest lists, each matching its recorded hash, so a folder
  still bringing in changes is refused ("try again in a minute") rather than loaded half-synced.
- **Never a silent merge:** if both computers worked while unable to sync and their histories diverged (the folder's last
  changeset is not one the local copy has seen, and the local copy has changes the folder lacks), nothing loads. The person
  chooses which history to keep (`cockpit sync keep --here` or `--folder`); the other is saved as a backup. Duplicate files a sync service creates on conflict are found,
  shown, and never loaded.
  - **From a screen** (*built, phase L0*): `cockpit serve` doesn't refuse. It starts on this computer's own copy and holds the
    folder: nothing is written to it, its lease isn't taken, and closing doesn't release it. A Today line (Choose which copy to
    keep, 7.7) opens a page that shows both sides in plain words (how many changes each has that the other lacks, the latest, the
    computer) and the two choices with what each does. A choice is only noted in the workspace's private folder; the next
    start carries it out through the same `keep` before the database is opened, so the check that the other computer hasn't
    opened the workspace holds, the database is never replaced under a running app, and a refused start drops the choice. Until
    then it can be taken back; the restart is the person's click. Built: `tests/test_handover_screen.py`,
    `web/src/components/Handover.test.tsx`.
  - **A copy that lost the workspace** to another computer while running gets the same line (Close this copy) and a page
    saying who, since when and how long until it can be opened here. The app's own instance lease (above) needs no screen:
    a start takes it at once from a copy on this computer that is no longer running (its process id is in the holder id);
    only a copy on another computer, or one this computer can't tell about, waits for the heartbeat to expire or for
    `cockpit takeover --force`. Built: `tests/test_lease.py`.
- **Edits made outside:** the folder is checked for changes every few seconds (`storage.sync.watch_outside_edits`). Long
  text changed in another editor comes back as a proposed version (`text.propose`, 6.7) made from the version written
  there, marked as edited outside the cockpit. It counts as the person's own work only when the folder isn't shared; when
  `storage.sync.shared` is on, outside edits (and working copies taken back from the folder) are content, reviewed like any
  other (12.8): the request is an outside input, the changeset and every write it makes are untrusted, and the notes say it
  may be someone else's change. The folder step asks the question, and the folder's panel shows and changes the answer. Built:
  `tests/test_shared_folder.py`. An accepted passage is still credited to the person, whose review it is. Changed fields come back as a `record.edit` held for the person; in a
  collection file, changed entries come back as held edits and removed ones as held deletes, while added entries are
  reported (creating a record takes its plugin's op). Nothing applies silently. Each change is handled once, and once the
  person has decided, the file is written again from the records. History, sources, outputs and generated files are never
  read back.
- **Collections and generated files:** a record type can put all its records for one path in a single YAML list
  (`layout_collection`), and a layout can use a field of a referenced record (`{chapter.order:02}`). A plugin can declare
  generated read-only files rendered from its records; an edit made to one outside is reported and it is rebuilt.

**Working copies.** People often write and edit long text in the desktop tools they already use, not in the cockpit. A plugin
that registers a working-copy format (3.3) can hand a `long_text` field out as a file in that tool's format and take it back:

- **Hand-out:** through the file channel, into the project's `working/` folder (or a configured folder without sync). The core
  records the file's hash, the record, field and long-text version it was made from, and the format's plugin.
- **Hand-back:** when the file changes (the watcher ignores it while its hash matches) or the person uploads a file as that
  working copy, the core saves it as a source of the project, runs the format's `take_back` with the base version (a job, not an
  AI task: nothing to estimate or pay for), and files the result as a `text.propose` marked "handed back from a working copy",
  with whatever could not be mapped listed beside it.
- **Review:** a word-level diff against the base version. If the field changed in the cockpit after the hand-out, the review is
  three-way (base, cockpit, handed back) with a choice per passage; nothing is ever merged silently.
- **Housekeeping:** a working copy whose base has been superseded is marked stale; one never handed back can be dropped by the
  person with no effect on the record. Retention, data levels and the synced folder apply as for any source.

This moves one workspace between computers. Sharing a single project with a different workspace (another person's install)
is a different problem, since ids and people are per workspace; it is left for later.

## 5.1 Core entities

Records refer to each other **by id, never by name**. Names (people, projects, groups) are stored once, on their own record,
and rendered wherever they appear: owners in the workspace's owner format, question labels from a template, page titles from
the project's name. Renaming is then one field (6.7), and there is nothing to normalize after the fact (6.11). The same rule
holds between records and settings: every fact lives in exactly one place and everything else refers to it by id; a setting
never repeats a record and a record never repeats a setting (4.0; decisions, 2026-10-11, "One source of truth…"). It binds
plugins: they refer to core records with `RefTo` and never copy their names or fields.

Every record has an id (`<prefix>-<number>`, never reused), a version that goes up on each write, and two fields the core owns:
`stage` (6.26) and `ext` (fields plugins add, keyed by plugin). `engine/records.py` is the truth for the fields below; the
generated plugin guide lists each one with its description.

### Built

| Record (id prefix) | What it is | Key fields |
|---|---|---|
| `person` (PER) | someone the workspace works with or tracks | full_name, first_name (what a greeting to them uses; empty means the first word of the full name), aliases, role, team, org (an organization id), how_to_reach (per channel), why_they_matter, track_only, status (active, left). The PM is one of them: `workspace.user.person` points at the record, which holds their name and aliases |
| `organization` (ORG) | a company, client or supplier, kept once so a rename shows everywhere | name (unique), aliases, notes. An older workspace whose people hold organization names is moved over when it opens |
| `team` (TEAM) | a group of people | name, aliases, members (person ids) |
| `project` (PRJ) | a piece of work, possibly inside another | name, group, status, phase, priority (each from a value list, 5.4), target, summary, owner (person id), links, tags, log[] (dated update lines), **parent** (a project id: a title in a series, a project in a program; never itself or one of its own parts), **language** (a tag; unset means the parent's, else `workspace.language`, 4.1), **budget_usd** (the most AI work on it and everything inside it may cost; only the person sets it), content_levels (only the person sets it). **priority** is person-only too: the assistant's `record.set` of it is held for the person (shown as waiting for them, applied when they release it), and the person's own change applies at once. **Built:** `tests/test_projects_series.py::test_the_assistant_never_sets_a_projects_priority_but_the_person_does`. Capacity is a workplace pack field (9.5a), not core |
| `action` (ACT) | something a person will do | project, text, owners[] (each a person id with an optional team id; at least one unless held), due, **remind_at** (optional: when to remind the person, with its time zone; the person's own edit or snooze, never a correction; 6.32; **built:** `tests/test_reminder_lines.py`), status (held until it has an owner, open, done), notes, **reply** (optional: the reply the assistant drafted for a question someone asked the person, ready to copy; empty when no fact holds the answer) and **reply_reviewed** (false until the person approves it or writes their own; **built:** `tests/test_action_reply.py`), **event** and **series** (the calendar entry, or the series, it belongs to; an item on a series sits on its next instance, 6.7; **built:** `tests/test_series.py::test_actions_questions_and_facts_can_name_the_entry_or_series_they_belong_to`), **on_hold** (optional: `waiting_for`, plain words for what it waits for, and `since`, the day it was put on hold; set and cleared by the person, never due or chased while set; 6.9), told{person id: date}, **followed_up**{person id: [dates]} (a chase, separate from `told`, which is a notice; 6.9, 7.5), **done_by** (person ids who did the work) and **reported_by** (the person who said it was done), so a nudge is never completion and credit goes to the owner, not to whoever reported it, source, evidence. Closing from the PM's own button records the person it waited on as `done_by` and the PM as `reported_by`; the assistant closing it from an input records the owners as `done_by` and the input's one known sender (or the PM, for the PM's own note) as `reported_by`, left empty when the sender isn't one known person; reopening clears both. **Built:** `tests/test_followups_backup_eval.py::test_followed_up_records_a_chase_keeps_the_action_open_and_counts_as_told`, `tests/test_on_hold_and_follow_ups.py::test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date`, `tests/test_followups_backup_eval.py::test_they_finished_credits_the_owner_and_reports_it_as_the_pm`, `tests/test_pipeline.py::test_closing_an_action_from_a_message_credits_its_owners_and_names_the_sender` |
| `question` (Q) | a question for a person; a decision is a question to whoever decides, the PM when nobody is named (6.8) | to, title, text, links[], kind (question, decision, action-notice, routing, impact), projects, **event** and **series** (the calendar entry, or the series, it belongs to; an item on a series sits on its next instance, 6.7; **built:** `tests/test_series.py::test_actions_questions_and_facts_can_name_the_entry_or_series_they_belong_to`), batch (now, later), *phase B:* **held_for** (a meeting or a send date, for the Later group, 7.5), status (open, sent, answered, dropped), sent_at, answer, source, options, resolves (what answering releases, e.g. a held op) |
| `fact` (FACT), `note` (NOTE) | something recorded as true with its evidence; something kept from an input that is neither a fact, action nor question. Never edited | text, project, source, evidence (facts), trust; a fact also has **event** and **series** (the calendar entry, or the series, it belongs to; an item on a series sits on its next instance, 6.7; **built:** `tests/test_series.py::test_actions_questions_and_facts_can_name_the_entry_or_series_they_belong_to`), **key** (the facts that matter most, shown first), **as_of** (the day it was true as of: its input's received day, or the request's day for a typed note, unless the input names another) and **supersedes** (the id of the fact it replaces, fixed once made). The older fact is never edited: what replaced it is computed from the newer one's `supersedes` (`engine/facts.py::superseded_by`), so undoing the newer fact brings the older back with nothing else to undo, and a fact is replaced at most once. **Built:** `tests/test_rules_facts_signals.py::test_a_newer_fact_marks_the_older_one_as_replaced_and_undo_takes_the_mark_away` |
| `rule` (RULE) | a standing instruction (4.10), a knowledge record (6.22). Added by `rule.add`, ended by `rule.retire`; both system ops with Undo. Written to `rules/{id}` in the synced folder | **name** (its own name, unique and never reused: stage checks and the rules file refer to it; the record's id is `RULE-n`), text, applies_to (the scope every knowledge record has: task kinds, record types and fields, filter, projects, people, scope and except; the rules file's `applies_to` is its first three), check (a deterministic check; none means prose), *phase L2:* **constrains** (the op kinds or fields it is about, so the knowledge log can tell applied from present, 6.22), origin (seed, person, assistant, pack, import), status (proposed, active, discarded, retired), source, evidence (when it came from an input), learned_at, kept_by (a person id), kept_at. **Built:** `tests/test_rules_facts_signals.py::test_seeding_makes_each_starting_rule_an_active_seed_record_once` |
| `lesson` (LES), `glossary_entry` (GLOSS), `routing_entry` (ROUTE), `style_note` (STYLE) | what the assistant learned (6.22): a lesson with its guard, a term and its meaning, who answers a kind of question (or who doesn't), what an audience wants or avoids. Changed only by their ops (`lesson.add`, `lesson.update`, `glossary.add`, `glossary.update`, `routing.add`, `style.add`, `knowledge.retire`), each with Undo; the person keeps, discards or retires them. Their level is internal, as a fact's. Not in the synced folder (no layout) | every kind: text (the restatement), evidence ({quote, source, request, signal, changeset}), origin (person, input, assistant, pack, seed, import), pack, trust, learned_at, status (proposed, active, discarded, expired, retired), discard_reason, kept_by, kept_at, applies_to (task_kinds, records, filter, projects, people, scope, except). Own: lesson guard, signal; glossary term, meaning, confidence (confirmed, assumed, unknown), project, id_patterns; routing topic, person or team, negative, look_up; style audience, observation. **Built:** `tests/test_knowledge_records.py` (6.22 lists the tests by part) |
| `event` (EVT), shown as "calendar entry" | something dated in the app's own calendar, never written to a calendar service. Added by `event.add` (6.7); the PM pack's milestones and meetings will build on it. Written to `calendar/{id}` in the synced folder | title, start (a day or a date-time, ISO text; a day means all-day), end (the last day or moment of a range, included), project, **series** (the series it is one instance of), source, evidence, trust. Its level is internal, as a fact's. **Built:** `tests/test_calendar_entries.py::test_a_workspace_with_an_entry_round_trips_through_the_export` |
| `series` (SER), shown as "series of calendar entries" | a meeting or check-in that repeats; each instance is a calendar entry that names it, and an item on the series sits on its next instance (6.7). Added by `series.add`; an entry joins or leaves by `series.link`. Written to `calendar/{id}` in the synced folder | title, project, **repeats** (how often, in the person's words, never used to work out dates), source, evidence, trust. **Built:** `tests/test_series.py::test_series_add_makes_the_series_links_its_entries_and_undo_unlinks_them`, `tests/test_series.py::test_a_workspace_with_a_series_and_items_on_it_round_trips_through_the_export` |
| `source` (SRC) | one input, saved as text; its content never changes | received_at (a mail's own received time; else when it was handed in or first read; never when it was last changed), kind, title, content_hash, trust (trusted, untrusted; 12.2), projects, url, **author** (the person whose words it is: for a note typed on a button, the person running the app, or the person it is reported about on the buttons that relay someone else, 6.5), **reported** (a note that is content the person reports: typed on a button that relays someone else, or repeating what someone else said, 6.5), **watched** (for an input a watcher found: the source in `watch.yaml`, the item's key, what happened to it, author, by_us), **excerpts** (`allowed` or `never`: the person allows using the source but never quoting it beyond a word or two; set by the person only). **sensitivity** (open, internal, restricted: the input's data level; the field is not called `data_level` because that name is a record type's own level; set from the hand-in's choice or the watched source's setting, else its kind's, else the default; only the person changes it; a request's level is the highest of its record type, its own `sensitivity` and its source's). *Built:* `tests/test_data_levels.py` (phase L0). Restrictions to named audiences are designed (4.1, 12.1) |
| `snapshot` (SNAP) | what a watched item looked like when last read; its text is in `sources/` by hash | source (id in `watch.yaml`), key, title, content_hash, author, seen_at, gone, link, **event** (for a calendar item: start, end, all-day, place, cancelled, repeats) or **message** (for a mail item: sender, received, unread, bulk, categories, participants), changed_at (when the item last changed or arrived, as its source said: a file's modified time for a folder, which "Look at the last day" reads), closed_by (the triage rule that closed its latest change), set_aside ({section, rule, reason}, and confirmed_at, for mail set aside as not work), deleted (the content was deleted after the person confirmed; only a marker is kept) |
| `watch_run` (WRUN) | one read of a watched source and what came of it | source, started_at, seconds, outcome (ok, baseline, failed, offline, throttled), retry_at, error_kind, error, new, changed, removed, state (what the connector keeps between reads), looked_back_to (for a first read that took the source in quietly: the day before which its mail wasn't looked at; a look further back moves it, 6.32) |
| `request` (REQ) | a unit of work for the assistant | task (an AI task kind), note (the PM's own words, trusted only when `origin` is pm), source, origin (pm, input, schedule), state (queued, running, review, done, needs_you, failed), waiting (why and until when, 7.6), approval and estimate_usd (a run that asks for the person's go), about, part, use (the account the person picked), follows, sensitivity, project, auto_closed ({rule, reason} when triage closed it), set_aside ({section, rule, reason} when triage or the person set a mail item aside; it is never queued), folded_into, **intake** (the id of the newly added source whose first read or look further back took the request in, 6.32) and **intake_seen** (the person opened the list of what it found), attempts, retries (automatic tries after a run with no usable answer, 8.6), cause (why it waits when the words are not enough: `data_level`, `no_person`; for a queued request `paused` with the account and `until`, `retry` with `until`, or `offline` with `since` and `until`, and the worker leaves such a request alone until that time), changeset, previous, **superseded_by** (the later request that redid this one and applied, which retired it, 6.7), dismissed |
| `changeset` (CS) | what the assistant proposed for one request, how it was checked and what was applied | request, summary, **topic** (a few words naming what the input was about, for the item's title, 6.15), ops[] (one outcome per op: the op, its status applied, held, refused or undone, group, the records it touched, the reason), status (applied, held, rejected, undone, partly_undone), problems, trust, reviewed, run, action (the plugin action it came from) |
| `run` (RUN) | one call to an AI provider | request, task, provider, model, tier, characters and tokens in and out, cached tokens, cost_usd, seconds, outcome (ok, invalid_output, error, **refused**), independence (other_account, same_account; for a check), error_kind (including `offline`: no connection could be made), error_detail |
| `signal` (SIG) | a correction by the PM (6.20) | kind (sent_back, undone, dropped, reworded, pulled_back, draft_edited, held_declined, routed, set_aside, put_on_hold, taken_off_hold, kept, discarded, retired; *phase L-core:* edited), refs, note, at, and **run** and **changeset**, the changeset it corrects and the run that made it, so the repeat-correction rate can read that run's knowledge log; `refs` keeps the records it is about. Both are empty for a correction of something no run made (a hold, a mail item set aside by hand, an automatic close pulled back, an edited follow-up message). **Built:** `tests/test_rules_facts_signals.py::test_sending_back_and_undoing_name_the_changeset_and_its_run` |
| `file` (FILE) | a file a person added or a program wrote (5.3) | name, media_type, size, sha256, file_kind, project, meta, origin (upload, tool), trust, replaces, added_at. **sensitivity**, as on `source`, set from the upload's `data_level` choice, else its file kind's level, else internal; a file a person action makes takes its kind's level |
| `text_version` (TXT) | one version of a long text field (5.0) | owner_kind, owner_id, field, number, sha256, format, words, source (edit, draft, proposal, merge, import), status (pending, accepted, merged, discarded), base, replaces, authorship[], paragraph_map[], unmapped, questions, run |
| `working_copy` (WC) | a long text field handed out as a file for the person's own tool, and what came back (5.0) | owner_kind, owner_id, field, format, base, file, sha256, status (out, returned, dropped), returned_file, proposal |
| `value_list` (LIST) | the values a field may take (5.4) | name, label, values, retired. *Phase B:* each value's **tone** and, for a status list, its **meaning** (5.4) |
| `answer` (ANS), `setting_proposal` (SETPROP), `report` (RPT) | what asking the assistant (6.25) produces: an answer with the words it rests on; a setting change the person applies or sets aside; a report to the maintainers the person sends | request, text and cites[] / key, value, why, status / title, text, status (draft, sent, dismissed) |
| `setting_change` (SETCHG) | one setting the person changed from a screen (4.22) | key, before, after, was_default, is_default, at |
| `audit_entry` (AUD) | a sign-in, a sign-out or turning an add-on on or off, made from the screens (12.1). Never a token, a secret or the account's name | kind (sign_in, sign_out, plugin_on, plugin_off), subject (the sign-in's or the add-on's name), label, detail, at. **Built:** `tests/test_audit.py`; no screen lists them until the Admin tab (phase E) |
| `tool_run` (TOOL), `job_run` (JOBRUN) | one run of an outside program a plugin declared; one run of a plugin's scheduled job | plugin, tool or job, outcome, seconds, the program's exit code and the end of its error stream, or the job's error |

Plugins add record types in their own tables (namespaced `<plugin>/<name>`) and fields on core records under `ext.<plugin>`.
Core code never reads a plugin's `ext` fields; the plugin's ops, renderers and panels do. A record type declares which fields
refer to other records (`RefTo`, honored up to six levels deep), so a delete or a merge (two people records that turn out to be
one person) can be checked and carried through, and a rename shows everywhere. A record type may also declare a data level, a
`layout` for the synced folder (5.0), fields only the person sets, and unique field groups.

### Designed, not yet built

These are in the design baseline and have no record type yet. Several belong to the project management pack now (decisions,
2026-10-12, "A project management pack"); the core keeps actions, questions, follow-ups, decisions and Today.

| Entity | Key fields | Note |
|---|---|---|
| `Meeting` | id, title, due, attendees (person ids), agenda (per attendee, 6.24), before and after notes, status | agendas are 6.24 |
| `Issue` | id, project id, text, raised_by, owners[], impact, status (open, resolved), opened, resolved, from_risk (when a risk came true) | RAID: the project management pack (6.24) |
| `Assumption` | id, project id, text, source id, status (unverified, confirmed, invalid), check_by, how it will be checked | RAID: the project management pack (6.24) |
| `Dependency` | id, from (the record that waits), on (the record it waits for; may be in another domain), need_by, status (on track, at risk, late, done), impact question id (6.18), notes | the project management pack (6.23) |
| risks, decisions and milestones on `Project` | risks[] (text, raised_by, owner, status and the optional fields `config/raid.yaml` turns on: probability, impact, score, mitigation, trigger, review_by), decisions[], milestones[] (each with a baseline date and a current date), players, hold flag, facts[] | the project management pack (6.23, 6.24); a project's update log and notes exist today |
| `Change` | id, source id, title, link, diff, detected_at, who, state (new, queued, processed, done, ignored), result, auto rule, superseded_by, covers[] | today an incoming difference is a `source` plus a queued `request`, with a `snapshot` for the item (5.5) |
| `Draft` | id, channel instance, target, output type, content, base version, diff, content_hash, status (draft, approved, scheduled, sent, failed, superseded), approved_at, send_at, sent_at, result | with the publisher (6.12); text drafts today are `text_version`s |
| `Rule`, the rest | the fields above are built (L1). Still designed: trust, the statuses expired and promoted, promoted_to, and an applies_to that names projects and people (with exclusions) | phase L (6.22) |
| `Problem` | an automation problem (not a project issue): id, summary, detail, plugin (when one raised it), status (open, reported, resolved, dismissed), report (the drafted report, if one was sent, 6.13) | with the governor (6.13) |

**Every knowledge record** (rule, lesson, glossary entry, routing entry, style note) also has:
- **origin:** person (the person's own words), input (proposed from content), assistant (its own generalization),
  pack, seed or import. *Built* for the four kinds above; a rule record takes the same fields when rules become records;
- **text:** the restatement, which is the entry's own wording, kept apart from the **evidence** quote, which keeps the
  source's provenance;
- **kept_by** and **kept_at:** who made it active, and when. Keep makes that person the author of the text (12.8);
- **applies_to**, the shape rules use plus `projects`, `people`, `scope` (workspace or projects) and `except` (the
  projects a workspace-wide entry does not apply to).

The states are distinct, because they mean different things:
- **discarded:** the person said no. Kept with **discard_reason**, and it suppresses near-matches for 90 days.
- **expired:** a proposal from an input that nobody reviewed in 14 days. It is counted, and suppresses nothing, because
  nobody decided.
- **retired:** it was active, and is no longer used or was narrowed out.

Seed lessons (Part 8) also carry **guard_kind** (invariant, lint, code or instruction) and **fixture_ids**.

The `fact` record gained `key`, `as_of` and `supersedes` in L1 (above).
Discarded proposals are kept with their reason. A `run` gains the agent's program version, and the outcome `no_output`
(6.16). The `run` record gains its knowledge log: the ids of
the knowledge entries it was given, how many facts were left out, and its searches with what came back (6.22). A changeset
gains `applied`, the knowledge ids it says it used, checked against that log. A `run` also records its refusals by check name
(8, guard kinds). A `signal` gains the kind `edited` (6.20).

Also designed: on `Person`, **verified** (*phase L-core*, with "names spelled from a primary source", 8.8), and later area
(derived from team and scope, 6.18), prefers, cadence, influence, interest and non_working_calendar; on `Question`, affects, asks_for (a fact kind), on_answer, key (dedupe) and the pending flags; on `Run`, the packet
size and omissions, packet hash, template and playbook versions, model as served and upstream host (6.16).

## 5.2 Storage rules (each one came from a real failure)

- Every input is saved under `sources/` and registered before anything is done with it.
- Ids and dates come from the actual date received, never from a meeting or date mentioned in the content.
- Ids never repeat; a closed, dropped or deleted record's id is retired, so a reference in a log or a sent message always means
  one thing.
- Times are stored with their zone and converted for display; date-only values display as that calendar day.
- Every write is a transaction that states the record versions it read; long operations re-read before they write. Nothing
  saves a copy loaded earlier.
- Every write that changes knowledge goes through the applier (or a core service that writes the ledger the same way), so it is
  validated, recorded and visible.
- Names live on their own record; everything else stores the id.
- The ledger is append-only and the export's git history is never rewritten, **with one exception: forgetting a person**
  (below). The export is committed on a schedule, before every migration (record or config, 4.0) and before every add-on
  install or update.
- Retention will follow `config/storage.yaml` (4.15; *designed, not yet built*): raw source text can be deleted after its
  facts are recorded; the ledger keeps that a source existed and what was learned from it. **Evidence survives
  retention:** each evidence quote is kept with its op (it is short), so the evidence check and "show the passage" still
  work. The source then shows "removed by retention on <date>" with the quotes still visible. A source marked
  `excerpts: never` keeps no more than its few words.
- **Forgetting a person, with an append-only ledger** (*designed, phase E*; decisions, 2026-10-12 "The data model
  review"). Without this rule, three statements contradict each other: the ledger is never edited and keeps every
  before-and-after value; the export with raw text is committed to git and never rewritten; and forgetting a person
  reaches everything (12.4). So forgetting is a **recorded redaction**:
  - a `person.forget` op replaces that person's values in records, knowledge, the knowledge log, private evaluation cases
    and the ledger's before-and-after values with a marker, and records that it did;
  - the export's git repository is local only until phase E's remote rules exist, and on forget it is rebuilt from the
    database as a fresh history, the one rewrite the rules allow;
  - when a remote exists (phase E), it is replaced the same way, and the screen says so;
  - backups made before the forget still hold the old data until they age out. The screen says when that will be, and the
    person can delete older backups at once;
  - **it travels through the synced folder.** The forget is its own ledger entry, after the entries it redacts. Today two
    computers' histories are compared line by line (`engine/handover.py`), so a redacted line would look like a divergence
    and block the load. So the comparison applies every forget found in either history to both before comparing: a
    redacted entry matches its original (built for a confirmed set-aside's deletion, 6.5: `engine/handover.py`
    `apply_redactions`, which finds each deleted record in either history and blanks its redacted fields in both; a forget
    adds its own entries to the same step). The computer that loads replays the forget on its own database and ledger, so
    its local copy is redacted too;
  - **undo never brings a forgotten value back.** Undoing a change that touched a forgotten person restores the marker,
    not the value (the ledger no longer has it), and the undo lists those fields as "forgotten, not restored".

  A test covers each: two computers, a forget on one, the other loading without a divergence and ending up redacted; and
  an undo after a forget.

  Crypto-shredding (a key per person, deleted on forget) was the other option. It would make every read and write of a
  person's values go through encryption, and it was set aside for a rare, recorded operation instead.
  Retention uses the same redaction for quotes in the ledger whose source text it removed, unless the quote is evidence
  kept on purpose above.

## 5.3 Files

Files people add (a cover image, a logo, a manuscript, a font) and files programs write are kept the way sources are:
**by content**, never changed in place.

- **Bytes** live in the workspace's `files/` folder under their SHA-256 hash; the same bytes are stored once. They are
  backed up with the database, config and sources, and restore brings them back.
- **A `file` record** describes each one: name, media type, size, hash, **file kind**, scope (the whole workspace, or
  one project by reference), metadata, where it came from (`upload` or a tool run), and trust. Uploads by the person are
  trusted as files but their **content** is material, never instructions; files from tool runs are untrusted.
- **File kinds** say what a file is for: the core's `attachment`, and kinds a plugin or a template declares, each with a
  metadata schema (validated on upload), accepted media types, a size cap and, when the kind's files are confidential by
  nature, a data level (a file added under it gets that level unless the person chose another at the upload; the add-on's
  manifest must list it, as for a record type). A new version of a file is a new file
  record that points to the one it replaces, so history stays.
- **Reading and showing:** downloads are served with the stored media type, `Content-Disposition: attachment` except
  for images shown in the app, and `nosniff`; HTML and SVG are never rendered inline. Plugins read bytes through the
  plugin API by file id, never by path.
- **Previews** are images a plugin renders in code for one review item or question; they are kept while the item is
  open and never sent or exported.
- **Limits** (largest file, accepted types, total per workspace) are settings with defaults (`storage.files`, 4.15).

## 5.4 Value lists

A field with a known set of values takes them from a named list instead of free text (decisions, 2026-10-11, "One source of
truth, value lists instead of free text…"). The core's lists today bind a project's `status`, `phase`, `priority` and `group`
(`project-status`, `project-phase`, `project-priority`, `project-group`); a plugin binds its own fields to lists it declares
(`<plugin>/<name>`), and may use a core list. A person's role and organization are not lists: an organization is its own record
(5.1), so a company is kept once.

- **A list is a `value_list` record**, not a config file (4.23). It has a name, a label, the `values` offered in order, and
  `retired` values: no longer offered, but records that hold one keep it and stay valid.
- **First values.** The core ships them in `engine/defaults/value_lists.yaml` and plugins declare theirs. A workspace gets each
  list the first time it opens, with those values plus any value its records already use, so nothing that was valid becomes
  invalid. After that the list belongs to the person.
- **Values carry meaning** (*phase B*; from the first design author's review). Each value has a **tone** (ok, warn,
  danger, neutral). A status list's values also have a **meaning** (not_started, open, at_risk, blocked, done). The ranking,
  the at-risk lines, a dashboard's colors and "done but not archived" read the meaning, never the label. So a person can add
  "On hold" and it still ranks and colors correctly. Adding a value asks for its meaning, with a suggestion.
- **Changing a list is an op with Undo:** `list.add` (adding a retired value offers it again), `list.rename` (changes every
  record that holds the value, in the same op) and `list.retire`. They are system-tier ops, and need no restart.
- **Enforced at the storage layer.** A value not on its list is refused for any writer (a plugin op, the assistant, an edit), with the list's values in the reason. Adding a value is a deliberate act ("Add to the list"), never a side effect
  of typing. The assistant's packets list the values each bound field takes.

## 5.5 How an input becomes records

Every input arrives the same way, whether the person pasted it or a watcher found it (6.4, 6.6):

1. The text is saved under `sources/` by content hash and a `source` record is made (untrusted for anything from outside; a
   watched item also carries where it came from).
2. A `request` is queued for the assistant, with `origin` input (or `pm`, when the person typed the note). A watched item also
   has a `snapshot`, which is what the next read is compared with, and every read is a `watch_run`.
3. The run is a `run` record; its answer is a `changeset` with a `topic`, one outcome per op, and the checks' problems. The ops
   change records through the applier (6.7), each field written to the ledger in the same transaction.
4. The person looks the changeset over (it is marked `reviewed`), sends it back (a `signal`) or undoes it.

A newer change to a watched item whose earlier change has not been read yet is folded in: the older request is closed with
`folded_into` naming the newer one, whose input holds both changes, earlier first, so the assistant reads them once, in order. A change a triage rule closed is a request that is already done,
with `auto_closed` saying which rule and why; taking a closer look queues it and records a `pulled_back` signal.
