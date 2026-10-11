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
social accounts) is a plugin. Files are read as text by the text extractors (3.3): the core ships extractors for documents, spreadsheets (cells and
their comments), presentations (slide text, tables and speaker notes) and PDFs, and plugins add others. Packets carry the
extracted text, so a run never asks the PM to paste what is already in a file it can read. A file type with no extractor is
flagged to the PM once, as unsupported, not request by request.

## 6.3 Channels (outputs)

The interface in 3.3. A channel describes its capabilities: versioned targets with a concurrency check, pulling others' edits
back, scheduled sending, length limits, media. The core ships the clipboard channel (the PM copies the approved text and pastes
it anywhere), the **file channel** (the approved content is written to a configured folder, in whatever format a renderer
produced: text, a document, a PDF, an ebook; with a synced folder, by default the project's `outputs/` folder, 5.0) and the fake channel. Wiki pages, email, blogs and social networks are plugins.
Channels are called only by the publisher (6.12).

**Canonical form.** A channel normalizes values the way its system stores them (a width written as `15%` that the system
keeps as `15.0%`), and every diff compares normalized forms. After a publish, the publisher pulls the target again and checks
that no difference remains. A remaining difference is an automation problem with a report (6.13), never a new draft, so a
format-only change can't sit in Waiting to go out forever or be published again and again as a no-op.

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
- **What is built.** Sources are listed in `watch.yaml`; each names a connector (the core's `folder`, or a plugin's)
  and its settings. A read lists what the source holds now; the core keeps a snapshot per item (its text in the
  sources folder by hash) and hands in a new item with its text, a changed one with a readable diff and its text now,
  and one gone from a complete listing as gone, each as an untrusted input queued for the assistant. A source's first
  read only notes what is there, so connecting a full folder doesn't flood the queue. Every read is recorded with its
  outcome; the connector's own state is kept between reads.

## 6.5 Triage

Applies `config/triage.yaml` rules in order before queueing, using registered matchers. Each closed item records the rule and a
readable reason, appears under "Auto-closed", and has a one-click way to send it back ("This is ours", "Take a closer look");
pulled-back items are recorded so rules can be tuned.

## 6.6 Dispatcher

- Batches queued requests (batch size, scheduled batches, immediate kinds that run within a minute of the PM handing them in,
  with a short delay so a note can follow). **A batch shares the stable part of the packet; each input gets its own call.**
  Several inputs in one call lower extraction accuracy and make evidence ambiguous.
- **Clean the input first** (deterministic, before any AI call): quoted earlier messages in an email thread are removed when
  they match text already saved from an earlier source, and marked "quoted" when they don't; signatures, legal disclaimers and
  tracking footers are removed by the patterns in `config/dispatch.yaml` `cleaning`. The saved source keeps the full original;
  the packet gets the cleaned text, which is always a subset of it, so evidence (6.7) still matches. This saves the most tokens
  and prevents the most duplicate actions.
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
- **Trusted and untrusted parts** (12.2): the PM's own note, config-derived context, rules, playbooks and the op reference are
  trusted. Everything that came from outside (connector content, pasted third-party text, replies, files) is untrusted, **and
  so is anything derived from it**: every record field carries the provenance of the write that set it (the ledger has it), and
  the formatter marks untrusted-derived fields, glossary meanings and proposed lessons as data wherever they appear, including
  in the stable prefix. The prompt
  formatter wraps untrusted content in marked blocks and the instructions say it is material to work on, never instructions to follow. The
  request records its origin (input, PM, schedule), and that origin decides which op tiers can apply (6.7). Secrets never
  enter a packet.
- **Order: stable first, request last.** The packet is laid out so the parts that are the same for every run in a batch come
  first, in a fixed order, in three layers: **static** (instructions, op reference for the task kind, playbook entries),
  **slow-changing** (glossary, rules, active lessons) and **per batch** (all open actions and questions). The request-specific
  parts follow: scope and facts for the items involved, related records, the date and anything else that varies, and the input
  last. Most providers discount or cache a repeated prefix, and only an identical one: so the stable part is built once at the
  start of a batch and frozen for the batch (changes applied during the batch show up in the next one), serialized in a
  deterministic order with no dates, counts or other volatile values, and the batch's calls run close together because cached
  prefixes expire after minutes. The adapter marks a cache point after each layer when its provider supports caching
  (`prompt_caching` capability, 6.16) and ignores the marks otherwise.
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

A changeset is JSON: `summary`, optional `change` and `request` ids, and `ops[]`. The applier holds a **registry of op types**
(3.3). **Each task kind lists the ops it may use** (reading notes needs about ten), and its output schema is generated from just
those, so the AI is asked for exactly what the applier accepts and no more: small, flat schemas are what cheaper models and
endpoints with weak structured-output support handle reliably. Output that isn't valid JSON first goes through a deterministic
repair (code fences, trailing commas, unbalanced brackets, a single top-level object); only if that fails is the run sent back.

**Evidence.** Ops that claim something about the world carry `evidence`: the source id and the exact words in it that justify
the op. Required on `action.add`, `action.close`, `question.done`, `fact`, `issue.resolve`, `assumption.update`,
`dependency.update`, and any `record.set` that changes a date, status or owner. When the request came from the PM's own note,
the evidence can be that note. Evidence is kept in the ledger and shown on the row ("closed because the email said: ...").

**Drafts are not claims.** Some work is writing, not extracting: a proposal, a statement of work, a status update, a blurb.
A draft has no quote to cite, so it is not held to the evidence rule; instead it is written only into a `long_text` field
(5.0) through a `text.draft` op, marked as written by the assistant, and shown as **not yet reviewed** until the person
approves it. Factual statements inside a draft that the task kind declares checkable (a date, a price, a regulation, a
research finding) still need evidence, listed beside the draft. A task kind says which it produces: ops (extraction) or a
draft.

**Person-owned fields.** A record type can mark fields that only the person sets (a project's priority or capacity): an op
from the assistant that sets one is refused as an invariant. `project.add` adds a project as a row of the portfolio (name,
parent, group, status, phase, target, notes) without anything else a pack would attach; person-owned fields stay empty
for the person to fill.

**Proposed versions and accepting them.** Two ops create a pending version of a `long_text` field: `text.draft` (written by
the assistant) and `text.propose` (the person's own work arriving from outside the cockpit: a handed-back working copy or a
plain file edited in the synced folder, 5.0). Both wait for review. `text.accept` takes the per-passage choices from the
review (accept or reject each change; with a three-way review, which side each passage comes from) and writes one new
version, keeping authorship per passage (5.0): accepted passages from a proposal count as written by the person, accepted
passages from a draft as drafted or changed by the assistant. Rejecting everything discards the pending version. Each is in
the ledger and can be undone.

**Prose output.** For a draft, the model writes plain prose, not prose packed inside JSON, which long outputs and cheaper
models get wrong. The core wraps the text into the `text.draft` op itself, and the applier checks it like any other change
(target, length limits, never-shown words, wording lints). A draft that would end mid-sentence because the model hit its output
limit is continued once, then held.

**Paragraph anchors.** A task kind that revises existing long text can ask for an anchored draft (`output: draft, anchored:
true`). The core divides the base text into the units of its format (5.0) and gives each unit an id in the packet, and the model starts each paragraph it writes with the ids it
comes from: one id for a kept or rewritten paragraph, several for a merge, the same id on two paragraphs for a split, `new` for
an added one, plus a closing list of ids it removed. A core invariant checks that every base id is accounted for, no unknown id
appears, and no atomic unit (a fenced block, a poem) was split or merged with another; plugin validators can then check the
rest of the map. The core strips the markers before storing, keeps the paragraph map
with the pending version, and the compare view (7.2) and authorship (5.0) use it.

### Op tiers

Every op type declares a tier. The tier, not the model's judgment, decides what may apply on its own.

| Tier | What it does | Applies automatically? |
|---|---|---|
| `data` | records knowledge: sources, notes, facts, records, actions, questions (filed, not sent), meetings, decisions | yes, after checks |
| `outbound` | creates drafts for a channel | it creates the draft; sending always needs the PM's approval of the exact content (6.12) |
| `system` | changes how the product behaves: standing rules, watched sources, scope, facts sources, any config key, plugins | from the PM's own note: yes, at once, with a read-back and Undo; from an input or the assistant's own initiative: **never**, the PM confirms |

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
Outbound: `draft.request` (ask for a rendered draft to a channel), `dev.request` (a report to the product's maintainers: a
problem, or a capability no op provides; drafted for the PM to approve and send, never a code change, 6.13), `handoff` (a request for another project, drafted as a
message or ticket for its owner, 4.18).
System: `milestone.rebaseline` (resets a plan's baseline dates; a plan change is the PM's call), `rule.add`, `rule.retire`, `watch.add`, `watch.remove` (new or removed sources), `config.set` (any config key,
including scope and facts), `plugin.enable`, `plugin.disable`.
Plugins register more, namespaced, each with its tier.

**Rename is one op.** `record.rename` changes the record's name field; everything inside the product shows names from the
record (5.1), so it all follows. Outputs outside the product (a published page title, links on other people's pages) are
listed in the output registry: the target keeps its id, the publisher renames the page in place, and a title-only change is a
draft like any other that shows as "renamed (same page)".

**A request becomes a report only when no op can do it.** The product never changes its own code. `dev.request` drafts a
report for the product's maintainers, and it must list the ops it considered and why none fits; the validator checks the list
against the registry and refuses the request when an existing op could do the job, sending it back to be done as a changeset. A
request about code another project owns (4.18) is refused as a `dev.request` and redone as a `handoff`. A request that comes
from the PM's correction must first say what the data shows (6.8): a report about a problem that isn't in the data is refused. A
changeset that needs an op that doesn't exist is held with its report; once an upgrade or a private plugin adds the op, the PM
can run it again.

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
- **Evidence matches:** an op that needs evidence has it, and its quoted words appear in the cited source's saved text
  (whitespace and quote marks normalized). A quote that isn't there is refused: the cheapest defence against a model that is
  confident and wrong, and against an injected instruction pointing at text that doesn't exist. (A real but wrong target, like
  closing the wrong action, is what evidence makes visible; whether the quote fits the target is the `evidence-fit` lint.)
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
- `evidence-fit`: the quoted words don't plausibly concern the target record (its title, owner and project share nothing with
  the quote). Default `return`, which holds it for the PM if the item will reach another person.

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
  report.
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

## 6.13 Governor, automation problems and reports

- Every few minutes: re-queue requests whose run never finished, push work waiting too long in working hours, repair changes no
  request carries, detect stale data and outages, run the scope sweep (6.18), the rules review (6.21) and the notices, commit
  the readable export (5.0) hourly.
- Problems in the automation become `Problem` records (shown as "automation problems", so "issue" keeps its project
  meaning, 6.24), each with what happened, when, what it affects and what the cockpit is already doing about it (retrying,
  waiting for the network, paused until a limit resets).
- **No self-modifying code.** The product never writes or applies code changes to itself or to a workspace's plugins. What
  an installation can change on its own is data and, with the PM's confirmation, config (system ops, 6.7).
- **Check the premise first.** Before concluding that a request can't be done (a report) or reaching for an outside lookup, a
  run checks the workspace's own records for its targets: records, drafts, saved research, earlier answers. Local knowledge
  comes first. A "can't do" outcome must name the records it checked; when its targets don't exist at all, the outcome is a
  question to the PM ("these aren't in your records: did you mean ...?"), never a report. A note the PM adds to a request is an
  instruction the run must act on, and an outcome identical to the previous one for the same request is refused and sent back
  once with that reason.
- **Reports, not fixes.** A problem the PM wants looked at, or a request no op can do, becomes a **report** (`dev.request`): a
  draft with what happened, the steps and records involved, the version and the relevant log lines, with workspace specifics
  left out unless the PM keeps them in. The PM reads it, approves it and sends it through `reports` (4.9): the clipboard by
  default, or a configured channel such as the maintainers' issue tracker form.
- **One place per problem:** a problem and its report show on its problem card only, and are counted there (Today, the header
  and the problem list count it once).
- **Requests for other projects:** a request about code another project owns (4.18) becomes a `handoff` draft for that
  project's owner.
- The self-check (Part 10) validates config schemas, plugin manifests, imports, the web build and the specificity guard; run it
  after any change.

## 6.14 Scheduler and offline behavior

Jobs that need the network wait while it's down and run when it returns ("Offline, waiting for the network" shown, not
failed). After sleep, the first refresh runs on wake when data is stale, after the connectivity check (6.4). A held or failed
job doesn't count as a run: a refresh that failed leaves the data marked stale, with its age, so nothing looks fresh that isn't. Plugin jobs follow the same rules. Jobs run in
the process whose `server.role` is `all` or `worker`; the scheduler lease in the jobs table (5.0) makes sure only one scheduler
runs at a time, even when a host starts more than one copy.

**Settings and code that change under a running process.** Before each job the process checks whether its config files or
its own code changed since it started (file hashes, the schema version of each config file, the installed version). Config
that changed is validated and reloaded; config that fails validation pauses the work with the reason shown. Code that changed,
or a config schema newer than the running code, stops new jobs: the process finishes the current one and restarts itself
(locally it re-executes; hosted, it exits for its supervisor to start the new code). Until it has restarted, waiting work
says "Settings or code changed; restarting before the next run". Old code never quietly runs new config.

## 6.15 Today builder

Builds the PM's Today list, the home screen (7.7), from live data and from plugins' Today contributors. **Every line starts with
what the PM does and says where:** answer N decisions, review and send N drafts, look over N changes, send N questions to a
person, follow up on questions waiting N days, finish N of your overdue actions, hold N meetings this week, look at N automation
problems, move N items to their next stage (6.26), approve N runs that need a go because of their cost (6.16). Status, progress
and things the automation handles never appear.

## 6.16 AI provider layer (any model, by configuration)

The PM brings their own AI accounts: a personal key with a model vendor, an aggregator that reaches many vendors with one key,
a model running on their own computer, or a command-line agent signed in as them. The product can use one or mix several, and
moving between them is an edit to `config/ai.yaml` (4.8). Nothing outside the adapters knows which vendor is in use.

**Kinds of provider, and the adapters that serve them:**

| Kind | What it is | Adapter |
|---|---|---|
| Native API | a vendor's own API, with its own features (structured output, caching, files) | one per vendor where its API differs: `anthropic`, `openai`, more as plugins |
| OpenAI-compatible API | any endpoint that speaks the widely used chat-completions format: many vendors offer one (xAI, for example), as do inference hosts and local model servers | one generic `openai-compatible` adapter, configured with `base_url`, key and model ids |
| Aggregator | one account and key for many vendors' models, with its own model catalog, prices and routing options (OpenRouter, for example) | `openrouter`, a thin layer over `openai-compatible` that reads the catalog and passes routing options |
| Local model | a model server on the PM's computer | `openai-compatible` with a local `base_url`; data never leaves the machine |
| Command-line agent | a vendor's coding agent run as a program, signed in with the PM's own login | `cli-agent` (agent mode, below) |

A new vendor that speaks the common format needs only a `providers:` entry. A native adapter is added when a vendor's own API
offers something the common format doesn't, and it is an adapter plugin, not a core change. Some vendors' agents can sign in
with the person's subscription instead of a paid key; whether that use is allowed is the vendor's terms, and the PM's call.

**Capabilities and prices are per model, not per adapter.** Through an aggregator, one account reaches models with very
different abilities and prices. So each adapter has `models()`: the models the account can use, each with its capabilities
(structured output, tool calling, vision, context and output size, prompt caching) and price, read from the provider's own
catalog where it publishes one, otherwise from the adapter's defaults and `prices:` in config. A model the catalog doesn't
describe is treated as having no optional capabilities until the PM says otherwise or an evaluation shows them. New models show
up through the catalog, with no code change.

**Adding an account** (Settings, AI): pick the kind; for an OpenAI-compatible endpoint, pick from known endpoints (a list the
adapters ship as data) or enter an address; paste the key, which goes to the keychain while config keeps only the reference;
**Test** checks the key and lists the models with their capabilities and prices; choose which models fill which tiers; set
`allowed_data` (new accounts start at `open`, and the screen says who will see the data: the vendor, and for an aggregator the
aggregator too); run the evaluation (below) before a model is approved for a tier.

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

- `models()`: the models this account can use, each with `capabilities()` (structured output, tool calling, vision, file
  access, code editing, max context, max output, streaming, prompt caching: whether a marked stable prefix is cached or
  discounted) and price per billing unit, from the provider's catalog where it has one;
- `run(task) -> result` with output, usage and timing;
- `classify_error(exit_code, error_stream, transport_error) -> rate_limited | quota_until(date) | auth | timeout |
  invalid_output | provider_down | other`. It reads **only** the runner's own exit code, error stream and transport errors,
  never the model's output: a model writing "not logged in" in a report is text, not an auth failure. Output and error stream
  are both kept on the `Run`, so a usage limit is never hidden behind "failed before doing any work";
- `health()` for the governor.

Adding a vendor that speaks the common format means adding a `providers:` entry; one with its own API means adding an adapter
plugin and an entry. Nothing else changes.

**Routing by capability, not by name.** Each task kind declares what it needs (a screenshot needs vision; most need structured output and a context size). The router picks the tier's provider and model,
checks that model's capabilities and the request's data level against `allowed_data`, and falls through the fallback chain if
it can't serve the task. Fallbacks can cross accounts and vendors (a usage limit on one account moves the work to the next).
When the common format lacks structured output for a model, the adapter asks for JSON and the applier's checks still decide.

**Escalate on failure, not on price.** Cheap models do most of the work; a tier can name `escalate_to` (another tier). When a
run's changeset still fails an invariant after its one fix round, or would be held for a lint, the request is re-run once on the
escalation tier before the PM sees it. A refusal from an op validator (3.3), core or plugin, counts as an invariant failure here, with the
validator's reasons sent in the fix round; validators must therefore be deterministic, and a check that needs judgment is a
lint with a severity instead. A draft or proposed version of long text always waits for review, so for it a `return` lint
still failing after the fix round counts as "would be held": it gets the one re-run on the escalation tier (estimated, counted,
and skipped when it would cross a cap), then stays pending with the findings shown on their passages. A `warn` lint only shows. The decision uses deterministic signals only (check failures, evidence that doesn't match,
unresolved names, a truncated packet), never the model's own confidence. Each `Run` records which tier produced the accepted
answer, so the quality panel (6.20) shows where the cheap model is enough. A config that maps a task kind to a provider that
lacks a required capability fails the self-check.

**Independent second opinion.** Every task kind has a role: `write`, `check` or `research`, and the workspace maps roles to
tiers (`ai.roles`, 4.8). A `check` is a review independent of the work under review: the router leaves out every account
whose AI runs wrote the record it is about (its text versions and the changes runs applied to it). Its findings are
suggestions the person decides on, never automatic rewrites. Packs that draft long documents use it on each one; the core
can use it to check a draft before it reaches another person. If no other account can take it, the check waits for the
person and says why, instead of quietly reviewing with the same model. A person with one account can accept the same
account for checks (`ai.roles.check.same_account`, or per kind). The check is then a fresh run that sees only its packet,
never the writing run's history, and the run records `independence` (`other_account` or `same_account`) so the review says
which kind it was.

**No silent provider.** Which account runs work is never a default. A tier naming an account that isn't in
`config/ai.yaml` is a config error: start-up and the self-check fail and name the tier. A tier with no account yet leaves its
work waiting, saying which tier needs one. The stand-in adapter runs only where a workspace configures it explicitly (fixtures, tests). Every run records its
provider and model, and the first run on an account after it was added or changed shows on the run's change as "first run
on <account>".

**Smoke test on every change.** Adding or changing an account, a model or a tier runs `cockpit ai test` before the first real
run: one small live call per configured tier, with that tier's exact parameters, so a parameter one model refuses (a reasoning
setting on an automatically routed model, say) is caught before real work fails. For agent adapters it also runs
`lockdown_test()`: writing to the agent's outbox works, writing anywhere else is refused, and starting a shell is refused.
Each model's accepted parameters come from the adapter's `models()`, and the self-check rejects a tier whose parameters its
model doesn't accept.

**Errors are read in one place.** `classify_error()` in the adapter is the only code that reads a vendor's error text or exit
output. Everything else works from its classification. A sign-in failure (`auth`) always becomes a question to the PM that
includes the adapter's `sign_in_hint()` (its own login command or page), and never reaches any other path.

**Probation for a new account.** A newly approved account's changesets carry a "new account" tag and always wait for review
(nothing closes on its own) for `ai.probation.runs` runs per task kind (default 20). The PM's Looks good and Send back on them
count toward that account's evaluation score (6.20), because a model can pass the fixtures and still follow instructions too
literally in real use.

**Prompts are workspace content, not code.** Instructions, examples and style guides live in `prompts/` templates; the core and
plugins ship defaults that the workspace can override. Default templates refer to sources through template variables filled
from config (`{{ facts.production_date.sources }}`, `{{ scope.domains }}`), never by a page title, query or field name written
into the text. Per-provider variations (one vendor prefers XML-tagged sections, another
JSON, one caches a marked prefix) are handled by the adapter's prompt formatter, not by forking the instructions; templates
keep the stable-first order of 6.6.

**Evaluation before any switch.** A golden set of fictional fixtures (inputs with the expected changesets and questions,
including hostile inputs, 12.2) scores a provider and model on: valid output rate, correct ops, evidence that matches, wording
rules followed, questions routed right, actions extracted completely, cost and time. **Scoring is deterministic**: the produced
ops are matched to the expected ones (op type, target ids, owners, dates, evidence present and matching); a model may judge
wording only, never structure. Models answer differently from run to run, so each case runs several times (`evaluation.runs`,
default 3) and the report gives a pass rate per case. The first set (10 to 20 cases from the milestone 2 acceptance scenario,
plus hostile inputs) is built with the launch slice, so the first model choice, cheap or strong, is made on evidence. `evaluate --provider <name> --model <id>` produces a report; a model is approved for a tier only after
it meets the configured score, and the PM approves the switch (a scheduled job can check prices and new models and ask the PM,
never switch on its own). Plugins can add fixtures for their own task kinds.

**Reproducible runs.** Every `Run` keeps a fingerprint of exactly what was sent (the packet, stored once and referenced by
hash; sources by id), the prompt template and playbook versions, the parameters, the model id exactly as the provider reported
serving it, and for an aggregator the upstream host that served it. Aggregators can route one model id to different hosts and
builds, so `routing` (4.8) can pin preferred hosts, and the quality panel can compare by host. `cockpit replay <run>` re-runs a
packet on any model, and any run can become an evaluation case.

**Usage, limits and cost.** Every run is a `Run` record: provider, model, units and cost. A usage limit pauses that provider
until its reset (and the fallback takes over); it is not retried in a loop. Notes and messages cost little; drafting work
(proposals, statements of work, long copy, research, independent reviews) can cost the person real money, so spending is something they decide,
never something that happens to them:

- **Estimate first.** Before a run, the cost is estimated from the packet size, the expected output (from past runs of that
  task kind, or the kind's declared default before there are any) and the model's price. Anything above
  `budgets.confirm_above_usd` asks first, with the estimate ("Draft the proposal: about $0.80"). A batch (draft all twelve
  sections) shows one total and runs only on the person's go.
- **Budgets at every level.** Per run, day and month across everything; per task kind; and per record, so a deal, document or
  project can have its own cap ("this deal so far: $4.20 of $15"). Packs may also set a default per pack. Reaching a cap stops
  new runs of that scope and tells the person; it never cuts a run off halfway.
- **Escalation and reviews count.** A retry on a stronger tier and an independent review are estimated and counted like any
  run; escalation is skipped, and the item held, when it would cross a cap.
- **Spend only on what changed.** Revising a section sends that section and short summaries of the rest, not the whole document;
  stable parts go first so providers that cache prefixes charge less (6.6).
- **Visible.** Spend by pack, task kind, record, model and day is shown in the usage panel, and a record's spend on the record.
  Packs declare a typical cost per task kind, and their documentation says what a typical project costs on a low-cost and a
  strong model.

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
  one question to whoever the routing rules say knows it. A meaning that came from untrusted content is shown to the model as
  data ("reported meaning, from <source>"), never as guidance, until the PM confirms it.
- **Lessons:** things a run learned about how this workspace works ("minutes from this group list owners after the dash").
  Because lessons become guidance in every later packet, they are the obvious place for an injected instruction to persist. So
  `lesson.add` records a lesson as **proposed**; it becomes **active** only when the PM accepts it (a Today line collects them:
  "Review 3 proposed lessons"). A lesson from the PM's own note is active at once, with a read-back. Active lessons go into the
  packets they apply to; the rules review (6.21) can promote a lesson to a standing rule or retire it.
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
- **Asking about the app.** The same box answers questions about the product. The packet holds what this install can do
  (each add-on's kinds of work, actions, screens and setup steps), the settings with their values, defaults and
  descriptions (never where keys come from), the records, and the sections of the user guide that share the most words
  with the question. The answer is an `answer` op whose cited words must be in that material, so a made-up button or
  setting can't be cited. A setting the person can change comes as a `setting.propose` op, applied with one click and
  Undo; something the product can't do comes as a `report.draft` to the maintainers (6.13), written without names from
  the records, which the person reviews and sends.

## 6.26 Stages

Work that moves through steps (a title from manuscript to launch, a deal from first contact to signed, a document from
outline to approved) uses one core mechanism instead of a status field per pack. A record type declares its **stages** in order (in a
pack's defaults, editable in `config/stages.yaml`, 4.21), each with:

- **Entry checks:** what must be true to move into it (all sections reviewed, a SOW approved, the launch date set), evaluated
  by rules before any AI.
- **Who moves it:** the person (default), or a rule for steps that need no judgment. The assistant can propose a move, never
  make one.
- **What it starts:** task kinds or jobs that run on entry (draft the proposal, build the print files), each estimated and
  budgeted (6.16).
- **Whether it applies:** a stage may apply to some records only (a review that only large orders need), by checks that must
  pass for it to apply. Moves forward pass over a stage that doesn't apply to the record, and it isn't offered on it.

Moving a record is an op (`stage.move`), so it is in the ledger and can be undone. When a record's entry checks pass, Today
shows "ready to move on" for it (6.15), once it is in a stage (starting one is done from Stages); when they fail, the record shows which ones and why. Stages are data on the record,
so a title's or a deal's history of stages is a query, and dependencies and baselines (6.23) can refer to them.

