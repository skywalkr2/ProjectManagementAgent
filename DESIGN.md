# PM Cockpit: product design for a generic, configurable build

A clean-room design, written from scratch from experience running an AI-assisted PM workflow. It contains no code, names,
company systems or data from any real deployment. All examples are fictional. Give this whole document to the coding agent;
Part 10 is the `CLAUDE.md` for the new repository.

**The one rule above all others:** the engine is generic. Everything about a particular organization (its people, teams,
programs, systems, URLs, routing, vocabulary, wording rules, schedules) lives in configuration and data, never in code or code
comments. Part 8 says how that is enforced.

---

## Part 1. The product

### 1.1 The idea

A program manager (PM) supports a busy leader (an architect, a director) who owns a portfolio of projects. Status lives on wiki
pages, work lives in an issue tracker, decisions happen in meetings, chats and email. The PM spends the day noticing what changed,
updating status pages, chasing people for answers and keeping action items straight.

The cockpit does the noticing and the drafting. It watches the sources, has an AI assistant turn each change into proposed page
updates, questions and action items, and gives the PM one screen to review, correct and publish.

**The AI drafts. The human approves everything that goes out.**

### 1.2 Who it's for

- **The PM (primary user):** reviews, approves, sends, publishes. Wants one screen that says what to do today.
- **The leader:** reads the published pages and dashboards. Shouldn't have to confirm routine updates.
- **Key players:** people who receive questions and action items. They never use the tool; they get paste-ready messages.
- **The assistant:** an AI with a configurable display name (e.g. "Archie"). The underlying model's name never appears in
  anything a person sees.

### 1.3 The core loop

1. **Watch** sources on a schedule: wiki pages and page trees, issue-tracker queries, release trackers, a shared file folder,
   and anything the PM hands in (pasted notes, emails, screenshots, files).
2. **Triage by rules first:** configurable rules close cosmetic edits, pages outside the portfolio, repeats and other known
   no-op cases before the AI sees them. Every auto-closed item stays findable with its reason and can be pulled back.
3. **Package and dispatch:** remaining items are batched into packets (the change, the related records, the open actions and
   questions, the rules) and handed to the AI runner.
4. **The AI writes a changeset:** a structured file of typed operations. It never edits records, pages or files directly.
5. **Check and apply:** a deterministic applier validates the changeset, normalizes it, backs up what it will touch, applies it
   and logs it. Invalid changesets go back to the AI once with the reasons before any human sees them.
6. **Review:** the PM sees each change with the AI's work nested under it and one set of buttons: Looks good, Send back, Undo.
7. **Publish:** page drafts wait with a readable word-level diff. Nothing reaches a shared page until the PM approves that
   exact diff.
8. **Follow up:** questions and action items grouped by person, copied as one clean message, marked sent, aged until answered.
   A pasted reply goes back to the AI, which records it and acts on it.

---

## Part 2. Architecture

### 2.1 Layers

```
+---------------------------------------------------------------+
| UI (React)            generic components, labels from config  |
+---------------------------------------------------------------+
| API (Python)          generic endpoints over the engine        |
+---------------------------------------------------------------+
| Engine (generic)      watchers, triage, dispatcher, applier,   |
|                       questions, actions, names, renderer,     |
|                       publisher, governor, scheduler, today    |
+-------------------+-------------------+-----------------------+
| Connectors        | AI providers      | Plugins               |
| wiki, tracker,    | any vendor, agent | optional custom page  |
| files, chat (in)  | or API, by config | generators, op types  |
+-------------------+-------------------+-----------------------+
| Workspace         config/  (YAML: who, what, rules, schedule)  |
|                   data/    (records, people, questions, ...)   |
|                   sources/ (every input, saved as text)        |
|                   docs/decisions.md (why things are the way    |
|                   they are)                                    |
+---------------------------------------------------------------+
```

- **Engine:** knows about projects, changes, changesets, questions, actions, people, pages and diffs as concepts. Knows nothing
  about any organization.
- **Workspace:** one folder per deployment (one PM supporting one leader). Config, data, sources and the decisions log. A git
  repository, so every change has history and undo is cheap.
- **Connectors:** small adapters behind interfaces. A fake connector backed by fixture files ships with the product, so the
  whole system runs offline on demo data.
- **AI providers:** any vendor's model, as a command-line agent or an API, through one provider-neutral contract (5.15).
  Which provider and model does which task is configuration; the engine never names a vendor or model.
- **Plugins:** the escape hatch for logic that truly is specific (a special page type a program needs). A plugin lives in the
  workspace or a separate package, registers through a documented interface, and is never imported by name from the engine.

### 2.2 Where things go (decide this for every new requirement)

| The requirement is about... | It goes in... | Example |
|---|---|---|
| Who someone is, their team, role, how to reach them | `data/people.json` | "Jane Doe leads delivery for the billing teams" |
| Who answers which kind of question | `config/routing.yaml` | "delivery-date questions for projects assigned to a delivery lead go to that lead" |
| What the portfolio tracks vs only observes | `config/scope.yaml` | "only items owned by these teams get follow-ups; program milestones are observed" |
| Which pages, trees, queries, folders to watch | `config/watch.yaml` | a page id, a tracker query, a folder path |
| Which changes close without the AI | `config/triage.yaml` | "diff only touches rows of other owners" |
| When jobs run | `config/schedule.yaml` | "batches at 9, 11, 1, 3, 5 on weekdays" |
| Words and spellings, the assistant's name, locale | `config/language.yaml` | blocked phrases on shared pages, US spelling, display name |
| Page layout, sections, column names, sort orders | `config/pages.yaml` + templates | "Action Items: Project, Notes, Owner, Due, Status" |
| Status labels and their colors | `config/status.yaml` | "At Risk" maps to amber |
| Calendar meaning ("this week", holidays per team) | `config/calendar.yaml` | week ends Friday; a team's non-working days |
| Which AI provider and model does which task, fallbacks, budgets, data rules | `config/ai.yaml` | "routine tasks on provider A's small model; code fixes on provider B's coding agent" |
| Prompts and instructions the AI gets | `prompts/` templates in the workspace | the changeset instructions, the update-writing style |
| Standing instructions the PM states in passing | `config/rules.md` (read by every AI run) | "don't ask the program manager to confirm program dates" |
| Why a behavior exists | `docs/decisions.md` | dated entry: what was decided, by whom, why |
| How a concept works (generic) | engine code + its docstring | "the applier backs up every file before applying" |

If a requirement doesn't fit a row, the answer is a new config key with a schema and a default, or a plugin. It is never an
`if team == "X"` in the engine.

---

## Part 3. Configuration model

All config is YAML (rules prose in Markdown), validated against a schema at startup and by the self-check. Every key has a
default so a new workspace runs with an almost empty config. Each file starts with a comment block explaining every key.

### 3.1 `config/workspace.yaml`

- `assistant_name`, `assistant_description` (display only)
- `user`: the PM's full name, aliases ("me", first name), timezone
- `leader`: full name, account usernames on each connector (to find their recent work)
- `our_accounts`: service accounts the cockpit publishes with, so lookups know "that edit was us"
- `connectors`: which adapter per kind (wiki, tracker, files, release tracker) and their settings
- `publish`: target pages, approval required (always true), dashboard readers to keep compatible with
- `restricted_sources`: how restricted inputs are marked and where they may appear

### 3.2 `data/people.json`

People with `full_name`, `aliases`, `role`, `team`, `org`, `how_to_reach`, `why_they_matter`, `track_only` (their items are
observed, never chased), `non_working_calendar`. The single source for names.

### 3.3 `config/routing.yaml`

Ordered rules that choose a recipient for a question by topic, project, owner team or kind:
`when: {topic: delivery-date, project_assigned_to: delivery_lead} then: {to: "{project.delivery_lead}"}`.
A rule can say `ask_user_first` (unsure: the PM routes it). Unmatched questions go to the PM as a routing decision, never to a guess.

### 3.4 `config/scope.yaml`

- `tracked`: patterns (owner teams, work-item prefixes, systems) whose items get questions, follow-ups and overdue flags
- `observed`: items recorded as facts but never chased (program milestones run by other PMs)
- `parked`: categories recorded in a parked list and otherwise ignored (UI copy reviews, other domains' internals)
- `new_scope`: what counts as new work beyond agreed scope, and that it becomes a pending decision until the owner decides

### 3.5 `config/watch.yaml`, `config/triage.yaml`, `config/schedule.yaml`

- Watch: pages (with or without children, depth), trees, people's recent edits, tracker queries and keys, folders, release data.
- Triage rules, each with `name`, `kind` (from a fixed set of generic matchers: same-edit, under-tree-not-mapped,
  diff-terms-absent, owner-not-ours, cosmetic, sub-task, already-seen-file, no-record-for-key), parameters, and a `why`
  template shown to the PM.
- Schedule: jobs with cron-like times, working hours, which jobs need the network, catch-up behavior after sleep.

### 3.6 `config/language.yaml`

Locale and spelling list, blocked phrases on shared pages (question-style wording: "confirm", "check whether", "TBD?"),
separators that mean a run-on list, words that must never appear in user-visible text (the model's name), date formats.

### 3.7 `config/pages.yaml` and templates

Page types (summary page, project page, archive, plugin pages), their sections and column names, column widths, sort orders
per section, what counts as a cosmetic change, and how status labels render. Templates are files, not strings in code.

### 3.8 `config/ai.yaml`

The whole AI setup, so changing vendor or model is a config edit (details in 5.15):

```yaml
providers:                     # every AI the workspace may use
  primary:
    adapter: anthropic-api     # an installed adapter (5.15); the only place a vendor appears
    auth: env:PRIMARY_AI_KEY   # a reference to a secret, never the secret itself
    models: {small: <model id>, large: <model id>}
    allowed_data: [open, internal, restricted]
  coding-agent:
    adapter: cli-agent         # any command-line agent: start command, args, how to pass the packet, where it writes
    command: <path to the agent CLI>
    allowed_data: [open, internal]
tiers:                         # what the work needs, mapped to a provider and model
  routine:  {use: primary/small, fallback: [coding-agent]}
  deep:     {use: primary/large}
  vision:   {use: primary/large}          # screenshots and images
  code-fix: {use: coding-agent}
tasks:                         # which tier each kind of work uses (defaults shown)
  change: routine
  notes: routine
  answer: routine
  update: deep
  checkup-goals: deep
  fix: code-fix
budgets: {per_run_usd: 5, per_day_usd: 20, per_month_usd: 200}
evaluation: {required_before_switch: true, min_score: 0.9}
```

### 3.9 `config/dispatch.yaml`, `config/governor.yaml`

Batch size, immediate-run kinds, timeouts, attempts; governor thresholds (stuck after N minutes, stale after N hours, outage
when more than N keys fail).

### 3.10 `config/rules.md`

Plain-language standing rules the PM states while working ("record who raised each risk"). Every AI run reads it. The cockpit's
"Respond to the assistant" flow appends to it when the PM states a rule.

---

## Part 4. Data model and storage

Start with JSON/YAML files in the workspace git repository; move to SQLite/Postgres for multi-user. The engine talks to storage
through a repository layer so the swap is local.

| Entity | Key fields |
|---|---|
| `Project` | id, name, program, sub-program, status, phase, target, priority, summary, delivery team, links, risks[], actions[], decisions[], milestones[], players[], log[] (dated update log), facts[] (internal knowledge with source), hold flag |
| `Source` | id, date received, who, kind, title, path to saved text, projects, restriction, url |
| `Change` | id, source kind, title, link, diff, detected_at (zoned), who, state (new, queued, processed, done, ignored), result, auto rule, superseded_by, covers[] |
| `Request` | id, kind (change, notes, request, answer, feedback, action, update, lookup-result), ref, note, state, attempts, created |
| `Changeset` | id, change_id?, request_id?, summary, ops[], status (applied, rejected, undone, proposed, discarded), errors[], files, backup, dismissed, quiet, feedback[] |
| `Question` | id, to (full name), title, text, links[], kind (question, decision, action-notice, routing), batch (now, later), projects[], asked_at, waiting days, on_answer, key (dedupe), answer_pending, feedback_pending |
| `Action` | key (stable), store, text, owner ("Team (Full Name)" or full name), due, status, notes, told{person: date}, followups[] |
| `Task` | a meeting the PM sets up or runs: title, due, attendees, before/after notes, status |
| `Person` | see 3.2 |
| `Issue` | an automation problem: summary, detail, status (open, fix-requested, fixing, fix-proposed, fixed, closed) |

**Storage rules (each one came from a real failure):**
- Every input is saved as a text file under `sources/` and registered before anything is done with it.
- Ids and dates come from the actual date received, never from a meeting or date mentioned in the content.
- Times are stored with their zone and converted for display; date-only values display as that calendar day.
- Never save a copy of a file loaded earlier in a long operation: re-read, merge, write. Saves that can race (a refresh
  writing the inbox while a run marks items) merge by item, not overwrite.
- Every write that changes knowledge goes through the applier (or an engine service that logs the same way), so it is
  validated, normalized, backed up and visible.
- The workspace is snapshotted to git on a schedule and before every code fix. History is never rewritten.

---

## Part 5. Engine components

Each component is generic, configured from Part 3, and has its own tests with fictional fixtures.

### 5.1 Connectors

Interfaces: `WikiConnector` (fetch page as text and storage format, children, history, search, publish with version check),
`TrackerConnector` (query, fetch items with changelog), `FilesConnector` (list, read text from documents and spreadsheets),
`ReleaseConnector` (optional). Each returns plain data. Errors are typed: no-access, not-found, outage, auth.

### 5.2 Watchers

Run on schedule; compare against snapshots; file a `Change` per real difference with a readable diff. Rules:
- An outage (many keys failing at once, or connection errors) is one logged issue, not a question per key. A single item is
  asked about only after it fails on consecutive runs.
- A file that moved is compared by content with what's registered before it counts as new. Spreadsheets are compared by cell
  content, not bytes, so a re-save isn't a change.
- **Supersede:** when a newer version of the same page arrives while an older one is queued, fold them into one change (all
  diffs, in order) so the AI never processes them out of order.
- Watch lists stay complete: when a record cites a tracker key, that key joins the watch list in the same step.

### 5.3 Triage

Applies `config/triage.yaml` rules in order before queueing. Each closed item records the rule and a readable reason, appears
under "Auto-closed", and has a one-click way to send it back ("This is ours", "Take a closer look"); pulled-back items are
recorded so rules can be tuned.

### 5.4 Dispatcher and AI runner contract

- Batches queued requests (batch size, scheduled batches, immediate kinds that run within a minute of the PM handing them in,
  with a short delay so a note can follow).
- **Packet:** for each request, the input, the related records, every open action with its exact key (so the AI can close what
  the input completed), open questions to the people involved, the rules file, and the op reference.
- Runs the AI in a locked-down mode: read-only on the workspace, writes only changesets to an outbox.
- **Self-check:** validates each changeset with the applier's checks right after the run and sends failures back for one fix
  round. Recovers the request id from unreadable output and re-queues it.
- Picks the provider and model for each request from `config/ai.yaml` (tier per task kind, or a flag in the PM's note), with the
  fallback chain on usage limits or auth failures; a request with no changeset after N attempts goes to the PM as "Needs you".
  The dispatcher only talks to the provider layer (5.15), never to a vendor.

### 5.5 Changesets and the applier

A changeset is YAML: `summary`, optional `change` / `request` ids, and `ops[]`. The applier holds a **registry of op types**,
each with required fields, a validator, a normalizer, the files it may touch, an apply function and a readable one-line
description. Generic op types:

`source`, `note`, `fact`, `page.set`, `page.add`, `page.del`, `page.log`, `action.add`, `action.update`, `action.close`,
`action.assign`, `decision.add`, `milestone.add`, `question.add`, `question.update`, `question.move`, `question.done`,
`question.drop`, `task.add`, `task.update`, `parked`, `inbox` (set a change's state), `lookup`, `watch.add`, `watch.remove`,
`rule.add`, `doc`, `dev.request` (a code change request: becomes an issue for the fixer, or a handoff for another project).
Plugins may register more.

**Validation (all generic, all driven by config):**
- Required fields per op; known targets (project exists, action key resolves to exactly one action).
- Wording on anything that reaches a shared page: blocked phrases, the model's name, locale spelling, run-on separators.
- Every page edit comes with an update-log op.
- Restricted sources never cited on open pages.
- New actions name a person as owner (a team alone or a blank is refused; unknown person means ask the PM first).
- Questions carry links to what they're about; questions to anyone but the PM link only things the recipient can open
  (no local files, no cockpit pages) and contain no assistant bookkeeping in labels.
- Op-specific checks (paths stay under allowed roots; files don't overwrite unless told).

**Normalization before apply:** every person name in owners and recipients expanded to the full name (5.9).

**Apply:** back up every file the ops may touch, apply in order, re-render affected pages, log the changeset with one readable
line per op. On error, restore the backup and record the error. **Undo** restores the backup if nothing has touched those files
since; otherwise it refuses and says why.

**Classification:** a changeset is "for the PM" only if it drafts a page change, files a question, adds a decision or action, or
otherwise needs a decision. Everything else is filed quietly (still findable). The change it came from closes as "no change
needed" automatically, so the PM never clicks "Looks good" on nothing.

### 5.6 Questions service

- `ask(to, title, text, key, on_answer, links, projects, batch)`: deduplicates by `key`; holds the question and files a routing
  decision to the PM when the recipient is unsure (`to: "?"`, a first name several people share, a name nobody on file has).
- Enriches links automatically from tracker keys and known page titles found in the text.
- **Decisions are questions addressed to the PM.** Whether something is "your decision" is decided by the recipient, never by a
  stored kind. Moving a question from the PM to someone else makes it an ordinary question.
- Answer flow: the PM types an answer or pastes the person's reply; it becomes a request carrying the question and its
  `on_answer`; the AI records the answer as a fact, updates records, closes or narrows the question, and re-checks every other
  open question to that person against the same answer.
- Feedback flow ("Respond to the assistant"): reword, reroute, drop (kept in a dropped-questions register with the reason) or
  close; every op that settles a pending request clears that question's pending flag.
- Aging: "waiting Nd" after Mark sent; chase suggestions after a configured number of days.

### 5.7 Actions service

- One store interface over every action store (project records, portfolio actions, plugin stores), each action with a stable key.
- **Mark done** for the PM's own; for others' actions **Followed up** (recorded internally, stays open, counts as told) and
  **They finished it** (credited to the owner, "reported by" the PM). Never credit the PM for someone else's work.
- **Reassign:** swap one person for another in the owner field, keeping the team ("Product (Jane Doe)" to "Product (Sam Lee)");
  in a multi-owner field, the person whose section it was reassigned from; refuses first names it can't resolve.
- **Assign:** give a team-only or blank owner a person.
- Any change in who does something or when updates the action (and any matching task) in the same step.

### 5.8 Action notices

Actions owned by others reach them: each open action not yet communicated to an owner shows as "to send" on the action row (not
as a separate question row), the person's Copy includes it, Mark sent records it as told. Closing the action closes the notice.
A baseline date lets a new workspace treat existing actions as already communicated. Owners marked `track_only` get no notices.

### 5.9 Names

One normalizer used on every write path: a first name only one known person has becomes that full name; any casing of a full
name becomes the stored spelling; the PM's aliases become the PM; teams and system labels stay as written; names nobody has on
file stay as they are. A scheduled sweep rewrites any short name that got stored anyway (hand edits, pulled-back page edits)
and files one decision to the PM listing people known only by first name. Grouping in the UI uses the same normalizer.

### 5.10 Records, renderer and publisher

- Records are the source of truth; pages are rendered from records via templates. Never hand-edit a rendered page.
- Edits made by others on a published page (in columns the team owns) are pulled back into records before re-rendering, so a
  render never overwrites them. Column matching tolerates renamed headers.
- Render-time ordering from config (actions open before done, then by owner and due date; milestones by date, undated last;
  decisions newest first). Records can stay in any order.
- Summary rows roll up from project pages; a row edited directly on the summary page after its project page is kept unless forced.
- Publisher: dry run, then publish only pages whose exact diff the PM approved (diff hash), with a concurrency check (nobody
  edited since the pull) and the target's own validation. Pulls skip pages with unpublished drafts and flag any whose remote
  page moved on.
- Change classification for the review list: real change, order only, layout/format only, columns changed, text the dashboard
  doesn't show. Never show an empty "+0 −0" draft.

### 5.11 Governor and fixer

- Every few minutes: re-queue requests whose run never finished, push work waiting too long in working hours, repair changes
  no request carries, detect stale data and outages, run the name sweep and the notices, snapshot the workspace hourly.
- Problems in the automation itself become `Issue`s. "Fix it" starts a fix run (the `code-fix` tier in `config/ai.yaml`, whichever
  coding agent that names) whose code change comes back as a **proposed fix**
  with a diff; it goes live only when the PM clicks Apply. Proposed fixes can't be hidden by "dismiss all".
- A self-check command validates config schemas, imports, the web build and the specificity guard (Part 8); run after any change.

### 5.12 Scheduler and offline behavior

Jobs that need the network wait while it's down and run when it returns ("Offline" shown, not failed). After sleep, the first
refresh runs on wake when data is stale. A held job doesn't count as a run.

### 5.13 Today builder

Builds the PM's Today list from live data. **Every line starts with what the PM does and says where:** answer N decisions,
review and publish N drafts, look over N changes, send N questions to a person, follow up on questions waiting N days, finish
N of your overdue actions, hold N meetings this week, apply N proposed fixes. Status, progress and things the automation handles
never appear.

### 5.14 Periodic jobs (later)

- Weekly check-up: suggested goals (the AI replaces auto goals with 3-5 real ones), meetings to hold, actions due by end of
  week by owner, questions to send, answers to chase, decisions waiting, what moved.
- Status updates on request: facts since a date, written in the sender's voice; learns from the edited "as sent" version (roles
  not names where the sender prefers, soft asks, commitments exactly as stated).

### 5.15 AI provider layer (any model, by configuration)

The product starts with one vendor's models and must be able to move to another (or mix several) by editing `config/ai.yaml`.
Nothing outside the adapters knows which vendor is in use.

**One provider-neutral contract.** Every AI task is a `Task`:
- input: the task kind, the packet (Markdown and JSON: the input, related records, open actions with keys, open questions, the
  rules, the op reference), attachments (images, files), and the output schema;
- output: a JSON document that validates against that schema (for most tasks, a changeset), plus usage (tokens or the vendor's
  billing unit, cost, time) and a normalized error when it fails.
The engine validates the output with the same applier checks regardless of who produced it.

**Two adapter modes, both behind the same interface:**
- **API mode:** the engine builds the prompt from the workspace's `prompts/` templates, calls the vendor's chat or responses API,
  and asks for structured output (JSON schema, or tool calls where the vendor prefers them). When the model needs a fact it
  doesn't have, it returns a `lookup` op; the engine runs the lookup and calls again with the result (a bounded loop, so the
  engine, not the model, touches outside systems).
- **Agent mode:** a command-line coding agent (from any vendor) runs in a locked-down mode: read-only on the workspace, writes
  only to an outbox folder, no plugins or outside tools unless configured. The adapter knows how to start it, pass the packet
  (a file path or stdin), pick the model, read its output and usage, and recognize its errors.

**Adapter interface** (each adapter is a small module in `engine/ai/adapters/` or an installed plugin, registered by name):
- `capabilities()`: structured output, tool calling, vision, file access, code editing, max context, max output, streaming,
  billing unit and price per unit;
- `run(task) -> result` with output, usage and timing;
- `classify_error(raw) -> rate_limited | quota_until(date) | auth | timeout | invalid_output | provider_down | other`;
- `health()` for the governor.
Adding a vendor means adding an adapter and a `providers:` entry; nothing else changes.

**Routing by capability, not by name.** Each task kind declares what it needs (a code fix needs code editing and file access;
a screenshot needs vision; most tasks need structured output and a context size). The router picks the tier's provider, checks
its capabilities, and falls through the fallback chain if it can't serve the task. A config that maps a task to a provider that
lacks a required capability fails the self-check.

**Prompts are workspace content, not code.** Instructions, examples and style guides live in `prompts/` templates. Per-provider
variations (one vendor prefers XML-tagged sections, another JSON) are handled by the adapter's prompt formatter, not by
forking the instructions.

**Evaluation before any switch.** A golden set of fictional fixtures (inputs with the expected changesets and questions) scores a
provider/model on: valid output rate, correct ops, wording rules followed, questions routed right, actions extracted completely,
cost and time. `evaluate --provider <name> --model <id>` produces a report; a model is approved for a tier only after it meets the
configured score, and the PM approves the switch (a scheduled job can check prices and new models and ask the PM, never switch
on its own). Approved models per tier are recorded in config.

**Usage, limits and cost.** Every run records provider, model, units and cost. Budgets per run, day and month stop new runs
and tell the PM. A usage limit pauses that provider until its reset (and the fallback takes over); it is not retried in a loop.

**Data handling.** Each provider has `allowed_data` levels. Inputs marked restricted only go to providers allowed to see them;
if none is, the request goes to the PM instead. Secrets come from the environment or the OS keychain, never from config files.

**Naming.** The assistant's display name is configuration and is the only name people see; vendor and model names appear only
in `config/ai.yaml`, the adapters, the usage reports and the evaluation reports.

---

## Part 6. UI specification (React)

### 6.1 Layout

- One header bar: product name, date, live indicator and last check, tabs (a segmented control, vertically centered, same height
  as the buttons), a Today button with a count, configurable quick links, Refresh, a Jobs menu, Log.
- **Work tab:** Automation issues (when any), then a row with **What changed** (two columns wide) and **Waiting to publish**,
  then **Follow-ups** (two columns wide) and **My meetings**.
- **Portfolio tab:** project health table grouped by program; milestones to check.
- **Admin tab:** request an update; the assistant's queue.

### 6.2 What changed (one list for incoming changes and the assistant's work)

- One row per incoming change (source tag, linked title, state pill with a tooltip of details). The assistant's changesets for
  that change are nested inside ("What the assistant did (N)"), next to "Show the change" (word-level diff).
- One row per piece of the assistant's own work that didn't come from a change (requests, answers, code fixes), tagged with the
  assistant's name.
- Buttons per row: new change: Process with the assistant / Done / Ignore. Reviewed: **Looks good** (closes the change and
  files its changesets), **Send back** (required note; option "Undo it, then send"), **Undo**. Proposed code fix: Apply /
  Discard / See the code change (always visible, sorted first). Auto-closed: "This is ours" / "Take a closer look".
- Filter: Needs attention, Processed, With the assistant, The assistant's own work, Done, Auto-closed, Ignored, All.
  "All looks good" for the reviewed rows shown, with a confirm.

### 6.3 Waiting to publish

- Before review: list of draft pages. "Review changes" runs the dry run.
- Per page: checkbox, title (left-aligned, wraps beside the checkbox), tags (new page, dashboard view, wording check), and a
  plain-words count ("3 changed, 2 added, 1 removed, 1 moved").
- Diff rendering: word-level strike-through and highlight; a mostly rewritten line shows old then new in full; small unchanged
  bits between changes fold into the change so phrases read old-then-new; table rows show cells joined cleanly with empty cells
  as "—"; a row that only moved shows once with a moved mark; a moved row whose cells changed shows as one in-place change.
- Publish message required; publishing a subset warns if the summary includes unticked pages' changes. Success notes fade;
  errors stay with the offending lines and an "Ask the assistant to reword" button.

### 6.4 Follow-ups

- **By person:** "You" first (decisions with Answer; your action items), then everyone A to Z, one section per person (names
  normalized). Each person: open questions (pill: ready to send / waiting Nd / later), then "Their action items N" (collapsible,
  with "due" and "N to send" tags). Header: **Copy N** and **Mark sent**.
- **Copy** builds one message: greeting with first name, questions first (numbered when several), then "Action items with you:"
  as a list with project and due date, then one closing line. No title-then-same-text repetition.
- Action rows: due pill, text, status, "to send" / "sent · Nd", and buttons: Mark sent (when unsent), Followed up, They finished
  it (Mark done for the PM's own), Reassign (name picker with full names), "Take care of this" for the PM's own.
- **By program:** actions with each project's open questions, copyable per program, per project or all. Notices don't appear as
  questions here.
- Question rows: Mark sent, Record reply, Respond to the assistant; decisions: Answer, Respond to the assistant.

### 6.5 Interaction rules

- Compact rows; details in hover tooltips on the status pill.
- No one-click destructive or closing control without a label; closing things that are hard to reopen asks for confirmation.
- Anything with more than one item renders as a list; stored text uses line breaks, and the UI renders "- " lines as nested
  bullets and "Label: url" as a named link.
- Copyable text stays clean: no approval or provenance notes inside what the PM pastes.
- One row per thing: never show the same work in two cards.
- Labels in plain words; no internal ids in anything the PM reads.

---

## Part 7. Lessons as product rules

Each rule came from a real mistake. The guard column says where the product enforces it.

### 7.1 Publishing and content

| Rule | Enforced by |
|---|---|
| Publish only confirmed facts. Targets aren't dates; discrepancies in someone's tracking never go on a shared page, they become questions first | applier wording check, "confirmed" field rules |
| Actions are written as verbs that do something, never "Confirm / Check whether" | blocked phrases |
| Record who raised each risk and whose problem it is; never turn another team's risk into an ask for your team | risk fields `raised_by`, `owner_team` required |
| Name teams, not individuals, as owners of risks (actions are different: actions name a person) | applier checks per section |
| Quotes and attributions only from verbatim sources; a paraphrase is labeled as one | `source` op requires `verbatim: true/false` |
| A meeting note line with no speaker stays unattributed | AI rules |
| Spell names from a primary source; mark unverified spellings | people `verified` flag |
| Acronyms come from a glossary with sources; guesses are marked assumed and asked | glossary data, AI rules |
| One identifier is not three: check the glossary before splitting a compound id | glossary patterns |
| Restricted inputs stay off open pages and outside messages | restriction field, applier check |
| Locale spelling everywhere except verbatim quotes | language config |
| The model's name never appears in user-visible text | language config, applier and UI tests |
| Check every URL responds before putting it where the PM clicks | link checker in the self-check |

### 7.2 Questions

| Rule | Enforced by |
|---|---|
| Asking is a core feature: anything the automation can't settle becomes a question, never just a log line | jobs call the questions service |
| Look it up before asking a person (creators, editors, text, status) | `lookup` op and lookups service |
| Every question links what it names | applier |
| A question to someone else says only what they need to answer: no bookkeeping, no options about how your pages are organized, no long quotes of their own words, only links they can open, the whole gap in one ask | applier link and label checks, AI rules |
| Unsure who it goes to: the PM routes it first | questions service hold |
| Decisions are questions addressed to the PM, by recipient | questions service, Today, check-up |
| Don't chase what you only observe (other PMs' program items, things the architect doesn't know) | scope config |
| A question asked in the conversation it came from is filed as asked | AI rules |
| When an answer arrives, re-check every open question to that person | answer flow |
| When an input answers questions, close them; search sources before filing a new one | packet includes open questions |
| Don't flood: an outage is one issue, not N questions | watcher outage rule |

### 7.3 Actions and owners

| Rule | Enforced by |
|---|---|
| Extract every action from raw notes and minutes, one per owner and task, counted against the source | AI rules, packet check |
| Before adding an action, search open and done actions for the same deliverable | applier near-duplicate warning |
| When an input completes actions, close them across every related project | packet lists open actions with keys |
| Owners are people: "Team (Full Name)" | applier |
| Separate who did it from who reported it | actions service |
| A nudge isn't a completion | Followed up vs They finished it |
| Each follow-up the PM owns after a meeting is its own action; files they send are linked where they can open them | AI rules, meeting template |
| Three kinds of to-do stay apart: meetings (tasks), owned follow-ups (actions), things to ask (questions) | data model, applier routes misfiled ones |

### 7.4 Knowledge

| Rule | Enforced by |
|---|---|
| Everything learned is written down in the same step: facts in records, people in people data, rules in rules.md, rationale in decisions.md | AI rules, applier ops for each |
| Every input shows in What changed with what was done with it | inputs always produce a note |
| Data files feed pages: changing the data re-renders the page in the same step | renderer hooks per data file |
| Pull others' page edits before re-rendering | publisher pulls first |
| One writer at a time per workspace; re-read before every write | file locks, merge-on-save |

### 7.5 Time

| Rule | Enforced by |
|---|---|
| "This week" means through the configured week end (e.g. Friday), one helper everywhere | calendar config |
| Date inputs from the day received, not the day discussed | `source` op |
| Store zoned times; never slice a timestamp string | storage layer |
| Per-team non-working days count for that team's dates | calendar config |

### 7.6 Automation robustness

| Rule | Enforced by |
|---|---|
| Rules before AI: most changes are no-ops; deterministic rules close them | triage |
| Never let two versions of one change race | supersede |
| A run that produced nothing is retried, then goes to the PM | dispatcher attempts |
| A usage limit is a pause until reset, not a failure loop | provider adapters `classify_error` |
| Switching AI vendor or model is a config change, approved by the PM after an evaluation run | provider layer, evaluation |
| Restricted inputs only reach AI providers allowed to see them | provider `allowed_data` |
| Error output is cleaned and short; the raw output is one click away | API error shape |
| Saves merge, never clobber | storage layer |
| Recover by itself after sleep or network loss | scheduler |
| A proposed code change never goes live unseen | fixer + Apply |

---

## Part 8. Guardrails against embedding specifics in code

The failure to prevent: while building for one deployment, every rule a user states ends up as a hardcoded name, team, URL or
`if` in the engine, with the user's quote as a comment. After a few weeks the "generic" code is unusable anywhere else.

### 8.1 The boundary

- **Engine code** (`engine/`, `api/`, `web/src/`) may reference only concepts: project, person, team, change, source, question,
  action, page, rule, connector. Never a specific person, team, organization, product, program, system, host, URL or page id.
- **Config and data** (`workspace/config/`, `workspace/data/`) hold every specific.
- **Plugins** (`plugins/<name>/`) may be specific, register through interfaces, and are never imported by name from the engine.
- **Rationale** lives in `workspace/docs/decisions.md` (dated entries: what, who decided, why). Code comments explain what the
  code does in general terms; they never quote a user or carry a date.

### 8.2 Enforcement (automated, part of the test suite and the self-check)

1. **Specificity scan:** a test reads every name, alias, team, org, program, system name, URL host and page id from the
   workspace config and data and fails if any appears in engine code, tests outside fixtures, or UI source.
2. **Provider scan:** fails if an AI vendor or model name (from `config/ai.yaml` and the adapter registry) appears anywhere
   outside `engine/ai/adapters/`, config, fixtures and docs.
3. **Pattern scan:** fails on URLs (except in config, fixtures and docs), on comments matching dated-decision patterns
   ("(Name, 10/8)", "per X", "X said"), on capitalized multi-word names in code that aren't in an allowlist of concept words.
4. **Config coverage:** every config key used in code exists in the schema with a default and a description; every schema key
   is used somewhere.
5. **Fixture-only tests:** tests use the fictional demo workspace; a second, different fictional workspace runs the same suite,
   so anything that only works for one dataset fails.
6. **UI labels:** user-visible strings that name the assistant or people come from config; a test renders the UI against both
   fictional workspaces.

### 8.3 Process (for every requirement)

Before writing code, answer and state in the change description:
1. Is this a concept (engine), a setting (config), a fact (data), a standing instruction (rules.md) or truly custom (plugin)?
2. If config: the key name, schema, default, and the example value for the demo workspace.
3. The decisions.md entry (date, who, what, why).
4. The generic test, run against both fictional workspaces.

When a user states a rule in passing ("don't ask the program manager about program dates"), the default home is config (a
scope or routing rule) or rules.md, not code.

### 8.4 Review checklist (every change)

- No new specific in engine, API or UI code; the scans pass.
- New behavior has a config key with a default, or is a pure concept.
- Rationale went to decisions.md, not a comment.
- Both fictional workspaces pass.

---

## Part 9. Build plan

Each milestone ends with tests passing against both fictional workspaces and the specificity scans green.

1. **Skeleton and guardrails first:** repo layout (`engine/`, `api/`, `web/`, `plugins/`, `workspaces/demo-a/`,
   `workspaces/demo-b/`), config schemas with defaults, the specificity and pattern scans, the self-check command, CLAUDE.md.
   Two fictional workspaces (different org, people, programs, vocabulary).
2. **Records and rendering:** project records, templates, summary roll-up, render-time ordering, the fake wiki connector.
3. **Changesets and the applier:** op registry, validation, normalization, backup, apply, undo, logging, classification.
4. **Watchers, triage, supersede:** fake connectors with fixture changes; triage rules; auto-closed list.
5. **Dispatcher and the AI provider layer with a stub adapter:** the `Task` contract, adapter interface, capability routing,
   usage records; a `stub` adapter turns fixtures into changesets from templates, so everything runs with no AI account.
6. **UI part 1:** header, What changed (merged list), Waiting to publish with the diff renderer.
7. **Questions and actions:** services, notices, names normalizer and sweep, Follow-ups by person and by program, Reassign.
8. **Publisher:** dry run, diff-hash approval, concurrency check (fake connector first).
9. **Real AI adapters and the evaluation harness:** the first vendor's API adapter and a command-line agent adapter, error
   classification, budgets, data-level routing; the golden fixture set and `evaluate`. Adding a second vendor's adapter later
   should need no change outside `engine/ai/adapters/` and `config/ai.yaml` (a test proves it with two adapters).
10. **Governor, scheduler, offline behavior, issues and the fixer.**
11. **Today builder, meetings, weekly check-up, update writer.**
12. **Real connectors** (one wiki, one tracker) behind the interfaces, configured only through config.

---

## Part 10. `CLAUDE.md` for the new repository (paste as the repo's CLAUDE.md)

> # PM Cockpit
>
> A generic, configurable AI-assisted PM cockpit. The full design is in `docs/DESIGN.md`; read Parts 2, 3 and 8 before any change.
>
> ## The boundary (non-negotiable)
> - Engine, API and UI code contain **no** specific person, team, organization, product, program, system, host, URL or page id.
>   Those live in `workspaces/<name>/config/` and `workspaces/<name>/data/`. Truly custom logic is a plugin under `plugins/`.
> - Code comments describe what the code does in general terms. They never quote a user, name a person or carry a date.
>   Rationale goes in the workspace's `docs/decisions.md`.
> - When a user states a rule, decide first: concept (engine), setting (config key with schema and default), fact (data),
>   standing instruction (`rules.md`) or plugin. Say which in your reply. Default to config or rules.md.
>
> ## AI providers
> - The product supports any AI vendor through `engine/ai/` (design 5.15). Vendor and model names appear only in adapters,
>   `config/ai.yaml` and usage/evaluation reports; the rest of the code calls the provider layer with a `Task`.
> - Prompts live in the workspace's `prompts/` templates, not in code.
> - A new vendor is a new adapter plus config. If a feature seems to need a vendor-specific call outside an adapter, add a
>   capability to the adapter interface instead.
>
> ## Before finishing any change
> - Run the tests and `python -m engine.selfcheck`: specificity scan, pattern scan, config coverage, both fictional
>   workspaces, web build.
> - New config keys have a schema entry, a default, a description and demo values in both workspaces.
> - No new specific in code; if the scan flags one, move it to config or data, never add it to an allowlist to pass.
>
> ## Product rules that shape every feature
> - The assistant drafts; the human approves everything outward. Nothing publishes or sends without the PM.
> - The AI's only write path is a changeset validated by the applier.
> - One row per thing in the UI; lists, not run-on lines; labels in plain words; the model's name never shown.
> - Owners are people ("Team (Full Name)"); names stored in full on every write path.
> - Questions are written for their reader and link only what the reader can open; decisions are questions to the PM.
> - Rules before AI; never let two versions of a change race; saves merge, never clobber; recover after sleep and outages.
>
> ## Demo data
> - Only the two fictional workspaces. No real names, companies, systems or URLs anywhere in the repository.

---

## Ground rules for this build

- Built from this description only. No code, files or data copied from any real deployment.
- Fictional demo data only.
- Check your employer's policy on outside projects before building, and again before selling or publishing.
