# Part 6. Core engine components

Each component is generic, configured from Part 4, and has its own tests with fictional fixtures.

## 6.1 Plugin host

Discovers plugins (entry points, `plugins/`, `<workspace>/plugins/`), reads manifests, checks versions and dependencies,
validates plugin config, and calls each plugin's `register` with a registrar for every extension point (3.3). Checks that what a
plugin registers matches its manifest. Runs the event bus (3.4). Wraps every call into plugin code so an exception becomes an
`Issue` naming the plugin, not a crash.

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

- An outage (many keys failing at once, or connection errors) is one logged issue, not a question per key. A single item is
  asked about only after it fails on consecutive runs.
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
- **Packet:** for each request, the input, the related records, every open action with its id (so the AI can close what the
  input completed), open questions to the people involved, the area each related person and item is in with each domain's
  contact (6.18), looked-up facts (6.19), the rules that apply to this task kind and these projects (6.21), and the op
  reference (core and enabled plugins' ops). A plugin's AI task kind builds its own packet with the same parts available.
- **Trusted and untrusted parts** (12.2): the PM's own note, config-derived context, rules and the op reference are trusted.
  Everything that came from outside (connector content, pasted third-party text, replies, files) is untrusted: the prompt
  formatter wraps it in marked blocks and the instructions say it is material to work on, never instructions to follow. The
  request records its origin (input, PM, schedule), and that origin decides which op tiers can apply (6.7). Secrets never
  enter a packet.
- **Size budget:** each task kind has a `max_input` in `config/dispatch.yaml`, capped by the provider's context. The packet
  fills in order: instructions and op reference; the input (split into parts if it is larger than its share); open actions
  and questions for the projects and people involved; scope and facts for the items involved; related records ranked (same
  project, then linked, then mentioned); applicable rules. Whatever is left out is listed in the packet ("12 older log entries
  omitted") and on the `Run`, so a thin answer can be traced to a thin packet.
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
| `system` | changes how the product behaves: standing rules, watched sources, scope, facts sources, any config key, plugins, code | **never from an input**; from the PM, shown as a proposed change the PM confirms |

A system op in a changeset whose request came from an input (an email, a page, a reply) is held and becomes one decision for
the PM showing exactly what would change and the source that prompted it. This is what keeps a hostile or careless input from
rewriting the rules (12.2).

**Core op types.**
Data: `source`, `note`, `fact`, `record.set`, `record.add`, `record.del`, `record.log`, `record.rename`, `action.add`,
`action.update`, `action.close`, `action.assign`, `decision.add`, `milestone.add`, `risk.add`, `question.add`,
`question.update`, `question.move`, `question.done`, `question.drop`, `meeting.add`, `meeting.update`, `person.add`,
`person.merge`, `parked`, `inbox` (set a change's state), `lookup`, `watch.item` (follow one more item inside an
already-configured source), `doc`.
Outbound: `draft.request` (ask for a rendered draft to a channel).
System: `rule.add`, `rule.retire`, `watch.add`, `watch.remove` (new or removed sources), `config.set` (any config key,
including scope and facts), `plugin.enable`, `plugin.disable`, `dev.request` (a code change request: becomes an issue for the
fixer).
Plugins register more, namespaced, each with its tier.

**Rename is one op.** `record.rename` changes the record's name field; everything inside the product shows names from the
record (5.1), so it all follows. Outputs outside the product (a published page title, links on other people's pages) are
listed in the output registry: the target keeps its id, the publisher renames the page in place, and a title-only change is a
draft like any other that shows as "renamed (same page)".

**A change request becomes a code fix only when no op can do it.** `dev.request` must list the ops it considered and why none
fits; the validator checks the list against the registry and refuses the request when an existing op could do the job, sending
it back to be done as a changeset. When a fix adds a new op (in a private plugin, 6.13), the changeset that needs it waits with
the fix and is applied after Apply, once the new op is registered; the running applier would refuse it before.

### Checks: invariants and lints

Checks come in two kinds, so that fuzzy checks can't block real work and firm ones can't be switched off.

**Invariants** always refuse; `config/checks.yaml` cannot lower them:

- Schema and required fields; every id resolves to exactly one record; record versions (5.0).
- Tier rules (above).
- **People resolve:** every person or team in an owner, recipient or attendee field resolves to one id (6.11). An unknown or
  ambiguous name holds the op and files one routing decision; a team alone or a blank as an action owner is refused.
- **Scope** (6.18): an action's owner must be in the tracked area or be the PM. An action for anyone else, or with an owner
  label that matches another domain's `owners` patterns, is refused with the reason, and the AI records the work as a fact on
  the observed item instead. A question to anyone outside the tracked area is refused unless `cross_domain.allow` is
  `impact-only`, it goes to that domain's `contact`, it is marked `impact`, and it names in `affects` the tracked record it is
  about. Questions to people inside another domain who aren't its contact are always refused.
- **Facts** (6.19): a question whose `asks_for` is a fact kind with lookup sources is refused and sent back as a `lookup`; a
  question to anyone in a kind's `no_questions_to` that asks for that kind is refused. A lookup that finds nothing records TBD.
- Restricted sources never cited on open outputs; untrusted content never becomes a rule, a config value or a recipient on its
  own (12.2).
- The model's name never appears in anything a person sees.
- Questions to anyone but the PM never link local files or cockpit pages.
- Every record edit that changes a published output comes with an update-log op.
- Op-specific checks (paths stay under allowed roots; files don't overwrite unless told).

**Lints** are judgment calls. Each has a severity in `config/checks.yaml` (4.17): `return` (default: back to the AI once with
the reasons, then to the PM with a warning on the row), `warn`, `off`, or raised to `refuse`.

- Wording on anything that reaches a shared output: blocked phrases, locale spelling, run-on separators.
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

**Undo** builds a reverse changeset from the ledger's before-values and applies it field by field. A field something else has
changed since is a conflict, not a reason to refuse everything: the undo restores the rest and lists the conflicting fields for
the PM (keep the current value or restore the old one).

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
- Aging: "waiting Nd" after Mark sent; chase suggestions after a configured number of days.

## 6.9 Actions service

- One store interface over every action store (project records, portfolio actions, plugin stores), each action with a stable key.
- **Mark done** for the PM's own; for others' actions **Followed up** (recorded internally, stays open, counts as told) and
  **They finished it** (credited to the owner, "reported by" the PM). Never credit the PM for someone else's work.
- **Reassign:** swap the owner's person id, keeping the team ("Product (Jane Doe)" to
  "Product (Sam Lee)"); in a multi-owner field, only the named person's part; refuses first names it can't resolve.
- **Assign:** give a team-only or blank owner a person.
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
- Problems in the automation become `Issue`s. "Fix it" starts a fix run (the `code-fix` tier in `config/ai.yaml`) whose change
  comes back as a **proposed fix** with a diff; it goes live only when the PM clicks Apply. Proposed fixes can't be hidden by
  "dismiss all".
- **Apply merges; it doesn't check for staleness.** Busy files change between the fix run and the click, so a whole-file "has
  it changed since?" check would make nearly every fix stale. A proposed fix keeps the original of every file it touches. Apply
  does a three-way merge (original, current, proposed) per file, with a union merge for files listed in `fixer.union_merge`
  (default: Markdown) so rows both sides appended are kept. Only a real conflict stops it, and then the fix is redone
  automatically against the current files (up to `fixer.redo_attempts`, then the issue goes to the PM with the conflict shown).
- **One place per fix:** a proposed fix shows on its issue card only, and is counted there (Today, the header, the issue list
  count it once).
- **What the fixer may change:** the workspace's config, rules, prompts, templates and private plugins, applied in the
  workspace with the export committed first. A fix that needs the core or a bundled plugin is written as a patch and an issue for this
  repository, never applied to the installed engine, so deployments don't drift from the product.
- The self-check (Part 10) validates config schemas, plugin manifests, imports, the web build and the specificity guard; run it
  after any change.

## 6.14 Scheduler and offline behavior

Jobs that need the network wait while it's down and run when it returns ("Offline" shown, not failed). After sleep, the first
refresh runs on wake when data is stale. A held job doesn't count as a run. Plugin jobs follow the same rules. Jobs run in
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
  billing unit and price per unit;
- `run(task) -> result` with output, usage and timing;
- `classify_error(raw) -> rate_limited | quota_until(date) | auth | timeout | invalid_output | provider_down | other`;
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
JSON) are handled by the adapter's prompt formatter, not by forking the instructions.

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
