# Part 5. Data model and storage

## 5.0 Storage model

**A database is the system of record; git keeps a readable history.** Many of the product's rules (saves merge and never
clobber, one writer at a time, ids never repeat, undo only what hasn't changed since, one scheduler at a time) are guarantees a
database gives for free and files make you rebuild by hand. So:

- **SQLite** in the workspace (`cockpit.db`) holds every record. One file, transactional, safe for concurrent readers and one
  writer, fine locally and on a persistent volume when hosted. Postgres is a later backend for multi-user (4.15).
- **Config stays YAML** in `config/`, edited by people and committed to git (Part 4).
- **Sources stay files:** every input's text is saved under `sources/` by content hash and registered in the database.
- **`data/` is a readable export and a working recovery path:** on a schedule and after each applied changeset batch, the
  engine writes records as JSON files under `data/` (one file per record type, stable ordering) and the ledger as append-only
  files under `data/ledger/`, and commits them, with `config/`, to the workspace's git. That gives history, diffs, off-site
  backup (4.15) and a plain-text view. The running engine never reads it; `cockpit import` does (recovery, fixtures, moving
  backends).
- **Fictional workspaces** are committed as `config/` plus `data/` JSON; tests import them into a fresh database.

**The ledger.** Every applied op is written, in the same transaction as the change itself, to an append-only ledger: changeset
id, op, record id, field, value before, value after, request, provenance (6.6), actor (assistant, PM, rule, plugin) and time.
The ledger is the history view, the audit log and the basis for undo (6.7). It is never edited.

**Long text.** Some fields hold long prose: a statement of work, a proposal, a report, long promotional copy. A record type marks such a field as
`long_text`. Its content is stored once per version in a text store (by content hash, like sources), and the record and the
ledger hold the hash, so thirty edits of a proposal are thirty versions, not thirty copies inside the ledger. Each version keeps
**authorship by passage**: which spans the assistant wrote, which the person wrote or changed, and which model run produced the
assistant's spans. That serves review (what changed since I last read it, as a word-level diff, 7.4), disclosure rules that ask
how much of a work an AI wrote, and undo, which restores an earlier version like any other field. The export writes long text
as plain files beside the records, so it reads well in git and survives the round trip.

**Recovery.** Git history is only useful if it can be loaded back, so recovery is a tested feature, not an afterthought:

- **Round trip:** `import(export(db))` gives back the same records, ids, versions and ledger. The self-check runs it on both
  fictional workspaces, and every record or config migration is tested through it.
- **Point in time:** `cockpit restore --as-of <time>` imports the last export before that time and replays the ledger up to
  it. A restore is itself recorded in the ledger, so it can be undone.
- **One record:** the Admin tab can show any record as it was at a past time (from the ledger) and restore just that record,
  as a changeset the PM sees.
- **Off the machine:** local installs keep everything on one computer, so backups to somewhere else are expected, not
  optional (4.15, 11.1).

**Provenance.** Each ledger entry records whether the write came from trusted or untrusted content (12.2), so every field's
provenance is known; packets mark untrusted-derived fields as data (6.6).

**Record versions.** Every record carries a version that goes up on each write. Writes state the version they read; a write
against a newer version is merged field by field when the fields differ and refused when the same field changed, so two
writers never silently overwrite each other.

**Ids.** Ids come from per-kind sequences in the database and are never reused (`Q-1042` is always the same question, even
after it closes). Ids are shown only where the PM needs a handle (logs, the Admin tab), never in labels or outgoing messages.

**Jobs.** Scheduled and queued work lives in a jobs table with leases: a worker takes a job by writing a lease with an expiry,
so a crashed worker's job is picked up again, and only one scheduler holds the scheduler lease at a time.

**One running instance per workspace.** The engine takes an instance lease at start (instance id, host, heartbeat). A second
instance on the same workspace (the laptop and a host at once, say) refuses to start and says who holds it. `cockpit takeover`
takes the lease after the holder's heartbeat has expired, or immediately with a confirmation.

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
  naturally in any editor. The layout round-trips through `cockpit import`
  like the plain export, and the self-check tests it.
- **The lease lives in the folder too:** holder, computer, heartbeat and the last changeset written. Opening the workspace on
  the other computer while the holder's heartbeat is fresh is refused, naming the computer. Once it is released or stale, the
  opening install backs up its local database, loads the folder's newer state, and takes the lease.
- **Never a silent merge:** if both computers worked while unable to sync and their histories diverged (the folder's last
  changeset is not one the local copy has seen, and the local copy has changes the folder lacks), nothing loads. The person
  chooses which history to keep; the other is saved as a backup. Duplicate files a sync service creates on conflict are found,
  shown, and never loaded.
- **Edits made outside:** the folder is watched (the local-folder connector). A long-text file changed in another editor comes
  back as a change for the person to review, marked as edited outside the cockpit, never applied silently.

This moves one workspace between computers. Sharing a single project with a different workspace (another person's install)
is a different problem, since ids and people are per workspace; it is left for later.

## 5.1 Core entities

Records refer to each other **by id, never by name**. Names (people, projects, groups) are stored once, on their own record,
and rendered wherever they appear: owners in the workspace's owner format, question labels from a template, page titles from
the project's name. Renaming is then one field (6.7), and there is nothing to normalize after the fact (6.11).

| Entity | Key fields |
|---|---|
| `Person` | id, full_name, aliases, role, team, org, area (derived from team and scope, 6.18), how_to_reach (per channel), prefers, cadence, influence, interest (6.24), why_they_matter, track_only, non_working_calendar, verified, status (active, left) |
| `Team` | id, name, aliases, members (person ids), area |
| `Project` | id, name, group (portfolio grouping; its label comes from config, e.g. "Program"), status, phase, target, priority, summary, owner (person id), links, tags, risks[] (text, raised_by, owner, status, and the optional fields `config/raid.yaml` turns on: probability, impact, score, mitigation, trigger, review_by), decisions[], milestones[] (each with a baseline date and a current date, 6.23), players (person ids), log[] (dated update log), facts[] (internal knowledge with source id), hold flag, `ext` (fields added by plugins, keyed by plugin) |
| `Action` | id (stable key), project id, store, text, owners[] (each a person id with an optional team id; at least one), due, status (held until it has an owner, open, done), notes, told{person id: date}, followups[] |
| `Question` | id, to (person id), title, text, links[], kind (question, decision, action-notice, routing, impact), affects (record ids), asks_for (fact kind or none), batch (now, later), projects (ids), asked_at, on_answer, key (dedupe), answer_pending, feedback_pending |
| `Meeting` | id, title, due, attendees (person ids), agenda (per attendee, 6.24), before and after notes, status |
| `Issue` | a project issue (a problem happening now): id, project id, text, raised_by, owners[], impact, status (open, resolved), opened, resolved, from_risk (when a risk came true) (6.24) |
| `Assumption` | id, project id, text, source id, status (unverified, confirmed, invalid), check_by, how it will be checked (6.24) |
| `Source` | id, received_at (zoned), from (person id or text), by_us (written by one of `our_accounts`), kind, connector instance, title, content hash, projects (ids), trust (trusted, untrusted; 12.2), restriction (a marking and the audiences allowed to see it, 4.1), url |
| `Change` | id, source id, title, link, diff, detected_at, who, state (new, queued, processed, done, ignored), result, auto rule, superseded_by, covers[] |
| `Request` | id, kind (an AI task kind), ref, note (the PM's own words, trusted), state, waiting (why and until when, 7.6), attempts, created, origin (input, PM, schedule) |
| `Changeset` | id, change id?, request id?, summary, ops[] (each with an optional `group`, 6.7), read_back (applies to, doesn't change, overlaps, dry-run count; 6.7), status (applied, rejected, held, undone, proposed, discarded), problems[] (invariants and lints, 6.7), dismissed, quiet, feedback[] |
| `Draft` | id, channel instance, target, output type, content, base version, diff, content_hash, status (draft, approved, scheduled, sent, failed, superseded), approved_at, send_at, sent_at, result |
| `Rule` | id, text, applies_to (task kinds, record types and fields, filter), source (request or PM), added, status (active, retired, promoted), promoted_to (config key) (4.10) |
| `Problem` | an automation problem (not a project issue): id, summary, detail, plugin (when one raised it), status (open, reported, resolved, dismissed), report (the drafted report, if one was sent, 6.13) |
| `Run` | id, request, task kind, provider, model, units, cost, time, packet size and omissions (6.6), packet hash, template and playbook versions, parameters, model as served, upstream host (aggregators), tier that produced the accepted answer, exit code, error stream (kept apart from the output), outcome (6.16) |
| `Dependency` | id, from (the record that waits), on (the record it waits for; may be in another domain), need_by, status (on track, at risk, late, done), impact question id (6.18), notes (6.23) |
| `GlossaryTerm` | id, term, aliases, meaning, status (confirmed, assumed, unknown), source id, trust (from the source), patterns (how compound ids split) (6.22) |
| `Lesson` | id, text, learned_from (request or source), applies_to, status (proposed, active, promoted to a rule, retired), trust (6.22) |
| `Signal` | id, kind (sent back, undone, dropped, reworded, pulled back, draft edited), record ids, note, time (6.20) |

Plugins add record types in their own tables (namespaced) and fields on core records under `ext.<plugin>`. Core code never reads
a plugin's `ext` fields; the plugin's ops, renderers and panels do. Each record type declares the ids it stores so a delete or a
merge (two people records that turn out to be one person) can be checked and carried through.

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
- The export and the workspace's git history are never rewritten. The export is committed on a schedule, before every
  migration (record or config, 4.0) and before every applied fix.
- Retention follows `config/storage.yaml` (4.15): raw source text can be deleted after its facts are recorded; the ledger keeps
  that a source existed and what was learned from it.
