# Part 6. Core engine components

Each component is generic, configured from Part 4, and has its own tests with fictional fixtures.

## 6.1 Plugin host

Discovers plugins (entry points, `plugins/`, `<workspace>/plugins/`), reads manifests, checks versions and dependencies,
validates plugin config, and calls each plugin's `register` with a registrar for every extension point (3.3). Checks that what a
plugin registers matches its manifest. Runs the event bus (3.4). Wraps every call into plugin code so an exception becomes an
automation `Problem` naming the plugin, not a crash.

## 6.2 Connectors (inputs)

The interface in 3.3. Each returns plain data; errors are typed (no-access, not-found, outage, auth). The core ships paste-in
and upload, a local-folder connector and the fake connector. Everything else (wikis, trackers, mailboxes, calendars, feeds,
social accounts) is a plugin. Files are read as text from documents and spreadsheets by a shared extractor that plugins reuse.

## 6.3 Channels (outputs)

The interface in 3.3. A channel describes its capabilities: versioned targets with a concurrency check, pulling others' edits
back, scheduled sending, length limits, media. The core ships the clipboard channel (the PM copies the approved text and pastes
it anywhere) and the fake channel. Wiki pages, email, blogs and social networks are plugins. Channels are called only by the
publisher (6.12).

## 6.4 Watchers

Run on schedule through connectors; compare against snapshots; file a `Change` per real difference with a readable diff. Rules:

- **Check connectivity first.** A refresh starts with a quick reachability check per connector; with no network it waits
  (6.14) instead of running a string of failing checks. No network is not an outage and files nothing.
- An outage (many keys failing at once with the network up) is one automation problem, not a question per key. A single item is
  asked about only after it fails on consecutive runs.
- **Our own edits are ours.** An edit or page whose author is one of `our_accounts` is recorded as `by_us` (published by the
  cockpit): it confirms a publish, it is not a new change from someone else, and lookups answer "who made this?" with "we
  did".
- A file that moved is compared by content with what's registered before it counts as new. Spreadsheets are compared by cell
  content, not bytes, so a re-save isn't a change.
- **Supersede:** when a newer version of the same item arrives while an older one is queued, fold them into one change (all
  diffs, in order) so the AI never processes them out of order.
- Watch lists stay complete: when a record cites an item key inside an already-configured source, that item is followed in
  the same step (`watch.item`, a data op). Adding a new source is a system op (6.7).

## 6.5 Triage

Applies `config/triage.yaml` rules in order before queueing, using registered matchers. Each closed item records the rule and a
readable reason, appears under "Auto-closed", and has a one-click way to send it back ("This is ours", "Take a closer look");
pulled-back items are recorded so rules can be tuned.

## 6.6 Dispatcher

- Batches queued requests (batch size, scheduled batches, immediate kinds that run within a minute of the PM handing them in,
  with a short delay so a note can follow).
- **Packet:** the packet replaces browsing the workspace, so it carries what runs used to go looking for (and often didn't):
  - the input, and the related records in full;
  - **every** open action and open question, with ids, in a compact one-line form, not only the related ones, so the AI can
    close what the input completed anywhere;
  - the playbook entries for this task kind (3.8), the glossary and the active lessons (6.22), and the rules that apply to
    this task kind and these projects (6.21);
  - the area each related person and item is in, with each domain's contact (6.18), and looked-up facts (6.19);
  - which recent edits and pages were made by `our_accounts` ("published by the cockpit", so nobody is asked who made them);
  - the op reference (core and enabled plugins' ops) and the search lookups available (6.22).
  A plugin's AI task kind builds its own packet with the same parts available.
- **Trusted and untrusted parts** (12.2): the PM's own note, config-derived context, rules and the op reference are trusted.
  Everything that came from outside (connector content, pasted third-party text, replies, files) is untrusted: the prompt
  formatter wraps it in marked blocks and the instructions say it is material to work on, never instructions to follow. The
  request records its origin (input, PM, schedule), and that origin decides which op tiers can apply (6.7). Secrets never
  enter a packet.
- **Order: stable first, request last.** The packet is laid out so the parts that are the same for every run in a batch come
  first, in a fixed order: instructions and op reference, playbook entries, glossary, rules, lessons, then all open actions and
  questions. The
  request-specific parts follow: scope and facts for the items involved, related records, and the input last. Most providers
  discount or cache a repeated prefix, and the open-items list is where the repetition is; the adapter marks the stable prefix
  when its provider supports caching (`prompt_caching` capability, 6.16) and ignores the mark otherwise.
- **Open items, full and compact.** An open action in full form is "[project] text (owner, due) → how to close it" (its id and
  the match text that closes it); in compact form it is id, owner and title, with no closing hint, since the id alone is enough
  to close it. Actions for the request's own projects are always in full form. Actions for other projects switch to compact
  form only when the open-items list passes `open_items.compact_share` of the budget (default 40%), so trimming is by size, not
  by rule. For scale: one PM with about 20 projects has about 50 open actions and 10 open questions, roughly 3,000 tokens in
  full form, so compact form only starts at a few hundred open actions.
- **Size budget:** each task kind has a `max_input` in `config/dispatch.yaml`, capped by the provider's context. After the
  stable prefix, the request-specific parts fill in order: the input (split into parts if it is larger than its share), scope
  and facts for the items involved, related records ranked (same project, then linked, then mentioned). Open actions and
  questions, the glossary and the rules are never dropped (only compacted as above); if they alone exceed the budget, an automation problem
  tells the PM to raise it. Whatever is left out is listed in the packet ("12 older log entries omitted") and on the `Run`, so
  a thin answer can be traced to a thin packet.
- **Self-check:** validates each changeset with the applier's checks right after the run and sends failures back for one fix
  round. Recovers the request id from unreadable output and re-queues it.
- Picks the provider and model from `config/ai.yaml`, with the fallback chain on usage limits or auth failures; a request with
  no changeset after N attempts goes to the PM as "Needs you". The dispatcher only talks to the provider layer (6.16).

## 6.7 Changesets and the applier

A changeset is JSON: `summary`, optional `change` and `request` ids, and `ops[]`. Its JSON Schema is generated from the op
registry, so the AI is asked for exactly what the applier accepts. The applier holds a **registry of op types** (3.3).

### Op tiers

Every op type declares a tier. The tier, not the model's judgment, decides what may apply on its own.

| Tier | What it does | Applies automatically? |
|---|---|---|
| `data` | records knowledge: sources, notes, facts, records, actions, questions (filed, not sent), meetings, decisions | yes, after checks |
| `outbound` | creates drafts for a channel | it creates the draft; sending always needs the PM's approval of the exact content (6.12) |
| `system` | changes how the product behaves: standing rules, watched sources, scope, facts sources, any config key, plugins, code | from the PM's own note: yes, at once, with a read-back and Undo; from an input or the assistant's own initiative: **never**, the PM confirms |

A system op in a changeset whose request came from an input (an email, a page, a reply) or from the assistant's own initiative
(a scheduled review, a suggestion) is held and becomes one decision for the PM showing exactly what would change and the source
that prompted it. This is what keeps a hostile or careless input from rewriting the rules (12.2).

A system op that comes from the PM's own note applies at once, because asking for a click on a rule the PM just typed is daily
friction and the injection risk isn't there. The real risk with PM-stated rules is misreading, and misreadings came from a new
rule colliding with an existing one ("name teams, not individuals" meant for risks, applied to action owners, which another
rule says must be people) or from a correction aimed at the wrong place. So the review card carries a **read-back** that shows
effects and overlaps, not just a restatement, in four short lines next to Undo:

1. **Applies to:** the record types and fields it touches ("risk owners on project pages").
2. **Doesn't change:** the nearest neighbors the PM might assume it covers ("action owners still name a person").
3. **Overlaps with:** any existing rule or setting it narrows, widens or contradicts, linked.
4. **Right now it would change:** a dry-run count against current data ("3 open actions, 1 draft page"), expandable to the
   items. An unexpected number is the fastest sign of a misread; **zero** matches on a rule meant to fix something is flagged
   too, since the item may not be where the PM thinks it is.

How the lines are computed: every rule and setting change carries a structured target (`applies_to`: record types, fields, an
optional filter, 4.10). "Applies to" and "Right now it would change" come from that target: a config change is dry-run exactly
in a transaction that is rolled back; a prose rule counts the current records its target matches. "Overlaps with" compares the
target with every active rule's and setting's target (the same field touched, or an overlapping filter), and the AI adds any
contradiction in meaning it sees. "Doesn't change" lists the closest records or fields the target leaves out.

**A contradiction pauses.** If line 3 finds a contradiction, the op is held even though the PM typed it, and the card asks which
one wins (the new rule, the existing one, or both with a narrower target). It is the one case where "apply at once" waits.

**Core op types.**
Data: `source`, `note`, `fact`, `record.set`, `record.add`, `record.del`, `record.log`, `record.rename`, `action.add`,
`action.update`, `action.close`, `action.assign`, `decision.add`, `milestone.add`, `risk.add`, `question.add`,
`question.update`, `question.move`, `question.done`, `question.drop`, `meeting.add`, `meeting.update`, `person.add`,
`person.merge`, `dependency.add`, `dependency.update`, `issue.add`, `issue.update`, `issue.resolve`, `risk.realize` (a risk
that came true becomes an issue linked to it), `assumption.add`, `assumption.update`, `meeting.agenda`, `glossary.add`, `glossary.update`, `lesson.add`, `parked`, `inbox` (set a change's state), `lookup`,
`watch.item` (follow one more item inside an already-configured source), `doc`.
Outbound: `draft.request` (ask for a rendered draft to a channel), `handoff` (a request for another project, drafted as a
message or ticket for its owner, 4.18).
System: `milestone.rebaseline` (resets a plan's baseline dates; a plan change is the PM's call), `rule.add`, `rule.retire`, `watch.add`, `watch.remove` (new or removed sources), `config.set` (any config key,
including scope and facts), `plugin.enable`, `plugin.disable`, `dev.request` (a code change request: becomes an automation problem for the
fixer).
Plugins register more, namespaced, each with its tier.

**Rename is one op.** `record.rename` changes the record's name field; everything inside the product shows names from the
record (5.1), so it all follows. Outputs outside the product (a published page title, links on other people's pages) are
listed in the output registry: the target keeps its id, the publisher renames the page in place, and a title-only change is a
draft like any other that shows as "renamed (same page)".

**A change request becomes a code fix only when no op can do it.** `dev.request` must list the ops it considered and why none
fits; the validator checks the list against the registry and refuses the request when an existing op could do the job, sending
it back to be done as a changeset. A request about code another project owns (4.18) is refused as a `dev.request` and
redone as a `handoff`. A request that comes from the PM's correction must first say what the data shows (6.8): a fix for a
problem that isn't in the data is refused. When a fix adds a new op (in a private plugin, 6.13), the changeset that needs it waits with
the fix and is applied after Apply, once the new op is registered; the running applier would refuse it before.

### Checks: invariants and lints

Checks come in two kinds, so that fuzzy checks can't block real work and firm ones can't be switched off.

**Invariants** always refuse; `config/checks.yaml` cannot lower them:

- Schema and required fields; every id resolves to exactly one record; record versions (5.0).
- Tier rules (above).
- **People resolve:** every person or team in an owner, recipient or attendee field resolves to one id (6.11). An unknown or
  ambiguous name holds the op and files one routing decision.
- **Every action names a person.** An action may have several owners (each a person, optionally with a team); a team alone or
  a blank is refused. An action whose person isn't known yet is held, with one question to the PM ("Pick an owner"), and is
  added only once it has one.
- **Scope** (6.18): an action's owner must be in the tracked area or be the PM. An action for anyone else, or with an owner
  label that matches another domain's `owners` patterns, is refused with the reason, and the AI records the work as a fact on
  the observed item instead. A question to anyone outside the tracked area is refused unless `cross_domain.allow` is
  `impact-only`, it goes to that domain's `contact`, it is marked `impact`, and it names in `affects` the tracked record it is
  about. Questions to people inside another domain who aren't its contact are always refused.
- **Facts** (6.19): a question whose `asks_for` is a fact kind with lookup sources is refused and sent back as a `lookup`; a
  question to anyone in a kind's `no_questions_to` that asks for that kind is refused. A lookup that finds nothing records TBD.
- **Audiences:** content reaches a destination only if every source it draws on allows that destination's audience (4.1). A
  restricted source can appear on a page locked to a named group that it allows, under that page's banner, and nowhere else.
- Untrusted content never becomes a rule, a config value or a recipient on its own (12.2).
- The model's name never appears in anything a person sees.
- A question to anyone but the PM has at least one link, and only links they can open (no local files, no cockpit pages).
- Unreadable output never applies; the dispatcher retries the run (6.6).
- Every record edit that changes a published output comes with an update-log op.
- Op-specific checks (paths stay under allowed roots; files don't overwrite unless told).

**Lints** are judgment calls. Each has a severity in `config/checks.yaml` (4.17): `return` (default), `warn`, `off`, or raised
to `refuse`. `return` sends the changeset back to the AI once with the reasons; if the problem is still there, what happens next
depends on where the item goes:

- anything that will **reach another person** (a question to someone else, a draft for a channel) is **held for the PM**,
  because the PM sends questions as written and a warning on a ready-to-send item gets missed;
- anything that **stays internal** (a note, a fact, an action's notes) applies with a **warning** on its row.

- Wording on anything that reaches a shared output: blocked phrases (including "confirm / check whether" in actions), locale
  spelling, run-on separators.
- A question whose text matches a fact kind's `terms` but doesn't declare `asks_for`.
- A question that links to something the recipient may not be able to open, or carries bookkeeping in its label.
- A new action that looks like an open or done action for the same deliverable.
- A link that doesn't respond.

Every finding is recorded on the changeset with the check's name and severity, so the PM sees why something came back.

### Normalize, apply, undo

**Normalization before apply:** names in id fields resolved to ids (6.11), dates parsed to zoned values, links enriched from
item keys and known titles.

**Apply** is one transaction: check record versions, apply the ops in order, write a ledger entry per field changed (5.0),
re-render affected outputs into drafts, commit. On error the transaction rolls back and the error is recorded on the changeset.

**Undo** builds a reverse changeset from the ledger's before-values. Ops that depend on each other share a **group**, and undo
is per field across groups but all or nothing within a group:

- The applier groups the known pairs itself (an answer recorded as a fact with the question it closed; a new action with the
  notice that told its owner; a rename with the outputs it re-rendered); the AI may group others.
- A group with a conflict (a field something else has changed since) is listed and skipped, never half restored; the PM can
  keep the current values or restore the group.
- **Outbound can't be undone.** Undoing a published page edit drafts a reverting edit for approval; a sent message shows as
  "already sent", with a follow-up offered if the PM wants to correct it.

**Classification:** a changeset is "for the PM" only if it drafts an output, files a question, adds a decision or action, holds
a system op, or otherwise needs a decision. Everything else is filed quietly (still findable). The change it came from closes as
"no change needed" automatically, so the PM never clicks "Looks good" on nothing.

## 6.8 Questions service

- `ask(to, title, text, key, on_answer, links, projects, batch)`: deduplicates by `key`; holds the question and files a routing
  decision to the PM when the recipient is unsure (`to: "?"`, a first name several people share, a name nobody on file has).
- Enriches links automatically from item keys and known titles found in the text.
- **Decisions are questions addressed to the PM.** Whether something is "your decision" is decided by the recipient, never by a
  stored kind. Moving a question from the PM to someone else makes it an ordinary question.
- Answer flow: the PM types an answer or pastes the person's reply; it becomes a request carrying the question and its
  `on_answer`; the AI records the answer as a fact, updates records, closes or narrows the question, and re-checks every other
  open question to that person against the same answer.
- Feedback flow ("Respond to the assistant"): reword, reroute, drop (kept in a dropped-questions register with the reason) or
  close; every op that settles a pending request clears that question's pending flag.
- **Check a correction against the data first.** A correction ("this shouldn't be in X's list") is a claim about the data. The
  feedback task's packet carries the current state of what it names, and the run starts by stating where the item actually is.
  When the data doesn't match the correction, the answer is a question to the PM with what was found, not a change and never a
  code fix.
- Aging: "waiting Nd" after Mark sent; chase suggestions after a configured number of days; one escalation suggestion when
  `routing.escalation` says so (4.3, 6.24).

## 6.9 Actions service

- One store interface over every action store (project records, portfolio actions, plugin stores), each action with a stable key.
- **Mark done** for the PM's own; for others' actions **Followed up** (recorded internally, stays open, counts as told) and
  **They finished it** (credited to the owner, "reported by" the PM). Never credit the PM for someone else's work.
- **Reassign:** swap one person in the owners list, keeping their team ("Product (Jane Doe)" to "Product (Sam Lee)"); the
  other owners stay. Told dates, Followed up and They finished it are per person.
- **Assign:** give a held action (one waiting for "Pick an owner") its first owner, which adds it.
- Any change in who does something or when updates the action (and any matching meeting) in the same step.

## 6.10 Action notices

Actions owned by others reach them: each open action not yet communicated to an owner shows as "to send" on the action row (not
as a separate question row), the person's Copy includes it, Mark sent records it as told. Closing the action closes the notice.
A baseline date lets a new workspace treat existing actions as already communicated. Owners marked `track_only` get no notices.

## 6.11 Names and identity

People, teams and projects are referred to by id everywhere (5.1). Names are resolved once, where they come in, and rendered
wherever they are shown.

- **Resolving** (every write path: AI ops, PM forms, edits pulled back from published pages): an id passes; a full name or
  alias that matches one person becomes that id; the PM's aliases become the PM; a first name only one known person has
  becomes that person; an owner written in the workspace's `owner_format` is parsed into person and team. Anything ambiguous or
  unknown holds the op and files one routing decision ("Who is 'Sam'?", with the candidates and "Add a new person").
- **Rendering:** owners in `owner_format` ("Product (Jane Doe)"), recipients by full name, greetings by first name. Changing
  the format changes every output at the next render.
- **No sweep needed:** nothing stores a short name, so nothing needs rewriting later. Free text (notes, fact text) keeps names
  as written.
- **Merging:** when two person records turn out to be one person, `person.merge` repoints every stored id (each record type
  declares the ids it stores, 5.1) and the ledger records it.

## 6.12 Records, renderer and publisher

- Records are the source of truth; outputs are rendered from records via templates into drafts. Never hand-edit a rendered
  output.
- For channels that can pull edits back, edits made by others on a published output (in parts the team owns) are pulled into
  records before re-rendering, so a render never overwrites them. Column matching tolerates renamed headers.
- Render-time ordering from config (actions open before done, then by owner and due date; milestones by date, undated last;
  decisions newest first). Records can stay in any order.
- Roll-ups (a summary page from project pages) are renderer features configured in `config/render.yaml`; a row edited directly
  on the roll-up after its source is kept unless forced.
- **Shared masters:** some targets are also edited outside the cockpit (a shared spreadsheet, wiki columns the team owns).
  Channels declare it (`external_editors`). Before writing, the publisher checks the channel's lock status (someone has it
  open) and waits or tells the PM; outside edits are diffed against the last pulled copy and come in as changes, never
  overwritten.
- **Publisher:** dry run, then send only drafts whose exact content the PM approved (content hash), with the channel's
  concurrency check when it has one (nobody edited since the pull) and the target's own validation. Pulls skip targets with
  unsent drafts and flag any whose remote copy moved on. Scheduled drafts are approved first and sent at their time; editing a
  scheduled draft clears its approval.
- Change classification for the review list: real change, order only, layout or format only, columns changed, text the target
  doesn't show. Never show an empty "+0 −0" draft.

## 6.13 Governor and fixer

- Every few minutes: re-queue requests whose run never finished, push work waiting too long in working hours, repair changes no
  request carries, detect stale data and outages, run the scope sweep (6.18), the rules review (6.21) and the notices, commit
  the readable export (5.0) hourly.
- Problems in the automation become `Problem` records (shown as "automation problems", so "issue" keeps its project
  meaning, 6.24). "Fix it" starts a fix run (the `code-fix` tier in `config/ai.yaml`) whose change
  comes back as a **proposed fix** with a diff; it goes live only when the PM clicks Apply. Proposed fixes can't be hidden by
  "dismiss all".
- **Apply merges; it doesn't check for staleness.** Busy files change between the fix run and the click, so a whole-file "has
  it changed since?" check would make nearly every fix stale. A proposed fix keeps the original of every file it touches. Apply
  does a three-way merge (original, current, proposed) per file, with a union merge for files listed in `fixer.union_merge`
  (default: Markdown) so rows both sides appended are kept. Only a real conflict stops it, and then the fix is redone
  automatically against the current files (up to `fixer.redo_attempts`, then the problem goes to the PM with the conflict shown).
- **One place per fix:** a proposed fix shows on its problem card only, and is counted there (Today, the header, the problem list
  count it once).
- **Requests for other projects:** a request about code another project owns (4.18) never reaches the fixer; it becomes a
  `handoff` draft for that project's owner.
- **What the fixer may change:** the workspace's config, rules, prompts, templates and private plugins, applied in the
  workspace with the export committed first. A fix that needs the core or a bundled plugin is written as a patch and an issue for this
  repository, never applied to the installed engine, so deployments don't drift from the product.
- The self-check (Part 10) validates config schemas, plugin manifests, imports, the web build and the specificity guard; run it
  after any change.

## 6.14 Scheduler and offline behavior

Jobs that need the network wait while it's down and run when it returns ("Offline, waiting for the network" shown, not
failed). After sleep, the first refresh runs on wake when data is stale, after the connectivity check (6.4). A held or failed
job doesn't count as a run: a refresh that failed leaves the data marked stale, with its age, so nothing looks fresh that isn't. Plugin jobs follow the same rules. Jobs run in
the process whose `server.role` is `all` or `worker`; the scheduler lease in the jobs table (5.0) makes sure only one scheduler
runs at a time, even when a host starts more than one copy.

## 6.15 Today builder

Builds the PM's Today list from live data and from plugins' Today contributors. **Every line starts with what the PM does and
says where:** answer N decisions, review and send N drafts, look over N changes, send N questions to a person, follow up on
questions waiting N days, finish N of your overdue actions, hold N meetings this week, apply N proposed fixes. Status, progress
and things the automation handles never appear.

## 6.16 AI provider layer (any model, by configuration)

The product starts with one vendor's models and must be able to move to another (or mix several) by editing `config/ai.yaml`.
Nothing outside the adapters knows which vendor is in use.

**One provider-neutral contract.** Every call is an `AiTask`:

- input: the task kind, the packet (Markdown and JSON: the input, related records, open actions with keys, open questions, the
  rules, the op reference), attachments (images, files), and the output schema;
- output: a JSON document that validates against that schema (for most kinds, a changeset), plus usage (tokens or the vendor's
  billing unit, cost, time) and a normalized error when it fails.

The engine validates the output with the same applier checks regardless of who produced it. Task kinds are a registry: the core
registers its own, plugins add theirs (3.3).

**Two adapter modes, both behind the same interface:**

- **API mode:** the engine builds the prompt from `prompts/` templates, calls the vendor's API, and asks for structured output
  (JSON schema, or tool calls where the vendor prefers them). When the model needs a fact it doesn't have, it returns a `lookup`
  op; the engine runs the lookup and calls again with the result (a bounded loop, so the engine, not the model, touches outside
  systems).
- **Agent mode:** a command-line agent (from any vendor) runs locked down: it gets the packet as files in a scratch folder, has no access to the workspace or the
  database, writes only its changeset to `outbox/`,
  no plugins or outside tools unless configured. The adapter knows how to start it, pass the packet (a file path or stdin), pick
  the model, read its output and usage, and recognize its errors.

**Adapter interface** (each adapter is a module in `engine/ai/adapters/` or an installed plugin, registered by name):

- `capabilities()`: structured output, tool calling, vision, file access, code editing, max context, max output, streaming,
  prompt caching (whether a marked stable prefix is cached or discounted), billing unit and price per unit;
- `run(task) -> result` with output, usage and timing;
- `classify_error(exit_code, error_stream, transport_error) -> rate_limited | quota_until(date) | auth | timeout |
  invalid_output | provider_down | other`. It reads **only** the runner's own exit code, error stream and transport errors,
  never the model's output: a model writing "not logged in" in a report is text, not an auth failure. Output and error stream
  are both kept on the `Run`, so a usage limit is never hidden behind "failed before doing any work";
- `health()` for the governor.

Adding a vendor means adding an adapter and a `providers:` entry; nothing else changes.

**Routing by capability, not by name.** Each task kind declares what it needs (a code fix needs code editing and file access; a
screenshot needs vision; most need structured output and a context size). The router picks the tier's provider, checks its
capabilities, and falls through the fallback chain if it can't serve the task. A config that maps a task kind to a provider that
lacks a required capability fails the self-check.

**Prompts are workspace content, not code.** Instructions, examples and style guides live in `prompts/` templates; the core and
plugins ship defaults that the workspace can override. Default templates refer to sources through template variables filled
from config (`{{ facts.production_date.sources }}`, `{{ scope.domains }}`), never by a page title, query or field name written
into the text. Per-provider variations (one vendor prefers XML-tagged sections, another
JSON, one caches a marked prefix) are handled by the adapter's prompt formatter, not by forking the instructions; templates
keep the stable-first order of 6.6.

**Evaluation before any switch.** A golden set of fictional fixtures (including hostile inputs, 12.2) (inputs with the expected changesets and questions) scores a
provider and model on: valid output rate, correct ops, wording rules followed, questions routed right, actions extracted
completely, cost and time. `evaluate --provider <name> --model <id>` produces a report; a model is approved for a tier only after
it meets the configured score, and the PM approves the switch (a scheduled job can check prices and new models and ask the PM,
never switch on its own). Plugins can add fixtures for their own task kinds.

**Usage, limits and cost.** Every run is a `Run` record: provider, model, units and cost. Budgets per run, day and month stop new
runs and tell the PM. A usage limit pauses that provider until its reset (and the fallback takes over); it is not retried in a
loop.

**Data handling.** Each provider has `allowed_data` levels. Inputs marked restricted only go to providers allowed to see them; if
none is, the request goes to the PM instead. Secrets come from secret references (Part 12), never from config files.

**Naming.** The assistant's display name is configuration and is the only name people see; vendor and model names appear only in
`config/ai.yaml`, the adapters, the usage reports and the evaluation reports.

## 6.17 Periodic jobs (later)

- **Weekly check-up:** suggested goals (the AI replaces automatic goals with 3 to 5 real ones), meetings to hold, actions due by
  the end of the week by owner, questions to send, answers to chase, decisions waiting, what moved. Packs add sections.
- **Updates on request:** facts since a date, written in the sender's voice; learns from the edited "as sent" version (roles
  not names where the sender prefers, soft asks, commitments exactly as stated).

## 6.18 Scope

One resolver answers "whose area is this?" for any person, team, item or project: tracked, a named domain (with its contact),
observed, parked or unknown, from `config/scope.yaml` and people data. The applier, triage, routing, notices, Today, the
check-up and the UI all ask it; no other part of the product decides scope on its own.

- **Scope sweep:** on a schedule, and whenever scope config or people data changes, finds open actions, notices and questions
  whose owner or recipient is outside the tracked area and files **one** decision to the PM, grouped by domain, with bulk
  choices: drop them (kept in the dropped register with the reason "outside our area"), turn them into observed facts, or
  replace them with one impact question to the domain's contact. Nothing changes until the PM picks.
- **Cross-domain asks:** questions to a domain's contact collect into one message per contact (batch `later`), each tied to the
  tracked item it affects. When that item closes or leaves scope, its cross-domain question is dropped.
- **Moving the line:** when the PM says an item or team is ours (or isn't), the "Respond to the assistant" flow proposes the
  scope config change; the applier and the sweep take it from there.

## 6.19 Facts and lookups

Some facts have a published home. In the reference pack's setup, for example, a work item's release lives in a tracker field
and a release's production date on a schedule page; which tracker, which field and which pages are settings.
Asking a person for them wastes their time and goes stale. `config/facts.yaml` (4.16) names those kinds and where each is
looked up.

- **Resolver:** for a kind, tries its lookup steps in order (following `from` chains, e.g. item to release to date) and returns
  the value with its source and when it was read. Plugins add lookup steps through the lookup extension point (3.3).
- **Use everywhere:** records, renders and packets show the looked-up value with its source; the AI gets it in the packet and
  never needs to ask.
- **Missing:** a kind with `missing: tbd` shows "TBD" until a source has it. No question is filed; when the source fills in,
  the watcher picks it up.
- **Enforced:** the applier refuses questions for these facts (6.7), so a model that ignores the packet can't send one.

## 6.20 Quality signals

The PM's corrections are the best measure of whether the assistant is doing well, and the best source of test cases. Each one
is recorded as a `Signal` (5.1) at the moment it happens:

| Signal | Recorded when |
|---|---|
| sent back | the PM sends a changeset back, with the note |
| undone | the PM undoes a changeset or part of one |
| dropped / reworded | the PM drops or rewords a question the assistant filed |
| pulled back | the PM pulls an auto-closed change back ("This is ours") |
| draft edited | the approved content differs from the assistant's draft (the difference is kept) |
| held op declined | the PM declines a held system op or a routing guess |

- **Quality panel** (Admin tab): rates over time by task kind, provider and model (share of changesets sent back or undone,
  share of questions dropped, auto-close pull-back rate, draft edit size), with each figure linking to its examples.
- **Private evaluation cases:** the PM can turn any signal into a case in `<workspace>/evals/` (the input, what the assistant
  did, what was right). `evaluate` runs these alongside the fictional golden set, so a model or prompt change is judged on the
  PM's real work. They never leave the workspace; the product's committed fixtures stay fictional.
- **Rule suggestions:** when send-back notes repeat a point, the rules review (6.21) proposes a rule from them.

## 6.21 Standing rules review

Standing rules (`config/rules.yaml`, 4.10) are useful until there are too many, they contradict each other, or a rule is
really a setting that only the model is enforcing (the original scope failure was exactly that). A scheduled review (an AI
task kind, weekly by default) proposes, as held system ops the PM confirms:

- **Merge or retire** duplicates and rules that no longer apply; **flag conflicts** between rules, side by side.
- **Promote** a rule that names a person, team, domain, source or fact kind into the config key that enforces it (a scope
  domain, a routing rule, a fact source), and mark the rule `promoted` with the key it became.
- **Add** a rule from repeated send-back notes (6.20).

Rules carry `applies_to`, so a packet includes only the rules for its task kind and projects (6.6), and the review keeps the
active list short enough to read.

## 6.22 Glossary, lessons and search

Runs used to read reference material on demand and write to it when they learned something. The packet now carries it, and
ops record what is learned:

- **Glossary:** terms and acronyms with meaning, status (confirmed, assumed, unknown), source and split patterns for compound
  ids. Every packet includes it. `glossary.add` and `glossary.update` record new terms; an assumed or unknown term can become
  one question to whoever the routing rules say knows it.
- **Lessons:** things a run learned about how this workspace works ("minutes from this group list owners after the dash").
  `lesson.add` records them; active lessons go into packets they apply to; the rules review (6.21) can promote a lesson to a
  standing rule or retire it.
- **Search lookups:** a bounded `lookup` over the workspace, in the same loop as fact lookups (6.16): full-text search over
  sources and records ("has this been asked or answered before?"), and the previous version of a source ("what did this page
  say last time?"). Results come back in the next call, with a limit on calls per run.

## 6.23 Dependencies and baselines

A plan is a chain of things waiting on other things, and slips are measured against what was planned. Both are core concepts,
used by any pack.

- **Dependencies:** a `Dependency` says one record (a milestone, an action, a project) waits on another, with a need-by date.
  The other side may belong to another domain (6.18); then its impact question, if any, hangs off the dependency. A dependency
  is **at risk** when the other side's current date (looked up where possible, 6.19) is after the need-by date or within the
  configured margin, and **late** when the need-by date has passed. At-risk and late dependencies are Today lines.
- **Baselines:** milestones and targets keep a baseline date and a current date. Variance (current minus baseline, in working
  days from the calendar config) shows on timelines and in drafted updates ("moved from Oct 15 to Nov 2, 13 working days
  late"). Setting a new baseline is `milestone.rebaseline`, a system op: an email can move a current date, but only the PM moves
  the plan.

## 6.24 Project management support

Core support for running projects, kept light and switchable (`config/raid.yaml`, 4.20). The cockpit keeps these current from
the inputs and surfaces what needs attention; the PM decides.

- **RAID:** risks, issues (problems happening now), assumptions and dependencies (6.23), alongside decisions. A risk that comes
  true becomes an issue linked to it (`risk.realize`). An assumption has a check-by date and how it will be checked. Inputs
  that confirm or break an assumption update it; a broken assumption is a Today line.
- **Risk fields and reviews:** probability, impact, score, mitigation, trigger and review date when the workspace turns them on.
  Open risks and unverified assumptions past their review date are Today lines ("Review 3 risks on the launch").
- **Escalation:** a question unanswered past `routing.escalation.after` gets one suggested escalation to the configured
  person, drafted for the PM with the question, how long it has waited and why it matters. Dismissing it is recorded; it is
  never sent on its own and never suggested twice for the same question.
- **Communications cadence:** people with a `cadence` (a weekly update to the leader, a fortnightly note to a vendor) get a
  Today line when one is due, and the update writer (6.17) drafts it from what changed since the last one, in the channel and
  form they prefer.
- **Meeting agendas:** before a meeting, `meeting.agenda` builds one section per attendee from their open questions, their
  actions, dependencies involving them and decisions the meeting needs, drafted to the clipboard channel. Minutes pasted
  afterward close what the meeting settled (6.9).

## 6.25 Asking the assistant

Not every need deserves a built-in feature. The PM can ask the assistant anything about the workspace ("what's on the critical
path for the launch?", "which contributors haven't replied this week?", "draft a risk review") from an Ask box.

- An ask is a request of kind `ask` (4.8): its packet has the playbooks, the records the question concerns (found with search
  lookups, 6.22) and the open items, like any other run.
- The answer is a note on the request, with links to the records it used. If the answer suggests changes (a new risk, a
  reassigned action), they come as ops in a changeset under the usual tiers and checks (6.7); a draft for someone else waits for
  approval like any other.
- An ask that comes up again and again is a signal (6.20): it may deserve a Today line, a panel or a playbook entry.
