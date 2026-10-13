# Part 6. Core engine components

Each component is generic, configured from Part 4, and has its own tests with fictional fixtures.

**Status.** A section or paragraph marked *designed, not yet built* is in the design baseline and has no code yet; the
roadmap (`docs/project/roadmap-to-1.0.md`) says when it is due. Where the code and a section differ, the code and the decisions
are right and the section is a gap. Sections 6.8 to 6.11 were written for the first design and have not been compared with
the code line by line since. They are where most corrections happen (drops, rewords, reroutes, reassignments), so the
learning loop's signals come from them; they are audited against the code first in phase L-core (L0), before the learning loop is built on them.

## 6.1 Plugin host

Discovers plugins (entry points, `plugins/`, `<workspace>/plugins/`), reads manifests, checks versions and dependencies,
validates plugin config, and calls each plugin's `register` with a registrar for every extension point (3.3). Checks that what a
plugin registers matches its manifest, all or nothing. Runs the event bus (3.4). Wraps every call into plugin code so an
exception is noted on the plugin and never crashes the core.

**Failure containment (as built).** Calls come in two kinds (decisions, 2026-10-11, "Plugin API 0.3.23…").
- A call that only reads or reacts (a Today line, an interface item, an event handler, a job) is contained one call at a time:
  the call is skipped and a note is kept on the plugin's status, and the plugin is turned off only after
  `workspace.plugins.failures_before_off` failures in a row there (default 3, 4.1).
- A plugin that breaks its contract (it reaches outside what its manifest declares) or fails inside a write (an op, a
  validator, a lint, a stage check) is turned off at once, with the reason on its status.
- A turned-off plugin no longer blocks core ops with its validators; its jobs stop and its screens are hidden, and its data
  stays on disk. Stage settings that name it stay in place and show as unavailable; the workspace still starts.
- A person action's preview tries the whole proposal without keeping anything, so an item that would be refused shows why and
  starts dropped, and other refusals are listed, instead of the action failing as a whole.
- Turning an add-on on or off (from the Add-ons screen, with Undo) and changing a plugin's settings need a restart the person
  chooses; registration keeps the old settings until then (4.22). Reporting these failures as automation `Problem` records with
  a report to the maintainers waits for the governor (6.13).

**Plugin screens the core draws.** A plugin declares lists (panels), read-only documents (a Markdown subset turned into plain
blocks, never raw HTML), forms for its data files (4.12) and Today lines; the core reads the rows through the plugin API and
draws them, so no plugin ships front-end code (7.2). The core also draws a record's own page and the counts beside its row in
a table (6.30).

## 6.2 Connectors (inputs)

The interface in 3.3. Each returns plain data; errors are typed, and decided from status codes and the service's own error
codes, never by guessing at message text: `auth` (sign in again), `no_access`, `not_found`, `outage` (the service is failing),
`offline` (no network here, which is never an outage and files nothing) and `throttled` (the service said to wait: the read is
recorded but doesn't count as a failure, and the source isn't read again before the wait ends; a connector honors the
service's retry-after answer and never loops).

**What the core ships.** Connectors that speak an open protocol and name no service: `folder` (text files in a folder),
`feed` (RSS and Atom; a document that declares its own entities is refused), `calendar` (the events of a calendar published
as a calendar file, which most services offer as a private address; events in the configured window are followed, so a moved
meeting, a new invitation or a cancellation is handed in) and `mailbox` (a mail folder over IMAP with TLS, using an app
password kept as a secret reference; messages are fetched without marking anything as read), and a `fake` one for tests
(marked test-only: Add a source doesn't offer it, and a source already set up with it still reads) (decisions, 2026-10-11, "Calendars and mail are read through open protocols in the core…"). Pasting and uploading are ways to
hand something in (6.6), not connectors. Connectors for particular products and services (wikis, trackers, a named mail or
calendar service that needs its own sign-in) are plugins (6.27).

**Structured items.** A calendar or mail item carries what it is as structured fields beside its text: an event's start, end,
place and whether it was cancelled; a message's sender, received time and whether it is unread. The watcher keeps them on the
item's snapshot, so the agenda and the list of what came in on Today need no AI call (6.15); the text still carries everything
the assistant reads.

**Reaching the network.** A plugin's connector reaches the network only through the core's client (decisions, 2026-10-11,
"Plugins reach the network only through the core's client…"): only hosts the manifest declares in `requires.network`, over
HTTPS (plain HTTP only on this computer), with redirects checked against the same list and answers capped in size. It gets the
secrets its manifest declares (references in `workspace.plugins.secrets`, or values it keeps on this computer, such as a
refreshed token), and a current sign-in token when it asks for one. Bundled plugins may not import network modules; the scan
enforces it.

Files are read as text by the text extractors (3.3; *designed, not yet built*, roadmap phase L, 6.22): the core ships extractors for documents, spreadsheets (cells and
their comments), presentations (slide text, tables and speaker notes) and PDFs, and plugins add others. Packets carry the
extracted text, so a run never asks the PM to paste what is already in a file it can read. A file type with no extractor is
flagged to the PM once, as unsupported, not request by request.

## 6.3 Channels (outputs)

The interface in 3.3. A channel describes its capabilities: versioned targets with a concurrency check, pulling others' edits
back, scheduled sending, length limits, media. The core ships the clipboard channel (the PM copies the approved text and pastes
it anywhere), the **file channel** (the approved content is written to a configured folder, in whatever format a renderer
produced: text, a document, a PDF, an ebook; with a synced folder, by default the project's `outputs/` folder, 5.0) and the fake channel. Wiki pages, email, blogs and social networks are plugins. A **notification target** (7.19, phase B)
is a channel of its own kind: mail to the person themselves, or a webhook. It sends only to the person, and only the "needs
you" items, so it needs no per-message approval.
Channels are called only by the publisher (6.12). The publisher, the file channel and the clipboard channel as channels are
*designed, not yet built* (roadmap, phase C4); the person copies approved text from the review today.

**Canonical form.** A channel normalizes values the way its system stores them (a width written as `15%` that the system
keeps as `15.0%`), and every diff compares normalized forms. After a publish, the publisher pulls the target again and checks
that no difference remains. A remaining difference is an automation problem with a report (6.13), never a new draft, so a
format-only change can't sit in Waiting to go out forever or be published again and again as a no-op.

## 6.4 Watchers

Run on schedule through connectors; compare against snapshots; hand in a readable difference for each real one, as an ordinary
input that is untrusted and marked with where it came from (decisions, 2026-10-11, "Watchers hand in differences as ordinary
inputs; the first read is a baseline"). One path for every input keeps evidence, trust and review the same whatever the
source. Rules:

- **No network is not an outage.** A connector that cannot reach the network reports `offline`: the read is recorded as such,
  nothing is filed and the source is tried again on its schedule (6.14), instead of a string of failing reads being counted as
  failures. (A quick reachability check before a whole round of refreshes is *designed*.)
- **Failures ask once.** A source that fails `watch.failures_before_asking` reads in a row (default 3) files one question to
  the person, not one per read, and a read that works again closes it. A throttled read does not count. An outage across many
  keys at once, as one automation problem, waits for the governor (6.13).
- **Our own edits are ours.** An edit or page whose author is one of `our_accounts` is recorded as `by_us` (published by the
  cockpit): it confirms a publish, it is not a new change from someone else, and lookups answer "who made this?" with "we
  did".
- A file that moved is compared by content with what's registered before it counts as new. Spreadsheets are compared by cell
  content, not bytes, so a re-save isn't a change.
- **Supersede:** when a newer version of the same item arrives while an older one is queued, fold them into one request (all
  diffs, in order) so the AI never processes them out of order. The older request is closed with `folded_into`.
- Watch lists stay complete: when a record cites an item key inside an already-configured source, that item is followed in
  the same step (`watch.item`, a data op, *designed, not yet built*). Adding a new source is a system op (6.7).

**What is built.** Sources are listed in `watch.yaml` (4.5); each names a connector (the core's, or a plugin's) and its
settings. A read lists what the source holds now. The core keeps a snapshot per item (its text in the sources folder by hash,
with the structured fields of 6.2) and compares:
- a **new** item is handed in with its text, a **changed** one with a readable diff and its text now, and one **gone** from a
  complete listing as gone (a connector that cannot list everything may name the keys that were removed; a source can turn
  reporting removals off with `report_removed`);
- each is saved as an untrusted `source` and queued as a `request` for the assistant (5.5), unless a triage rule closes it
  first (6.5);
- a change only in what an item is (a message was opened, so `unread` turned false) updates what Today shows and hands in
  nothing;
- the connector's own state is kept between reads, and a read starts from the last read that worked;
- every read is recorded as a `watch_run` with its outcome (`ok`, `baseline`, `failed`, `offline`, `throttled`), and any
  source can be read at once from its row ("Read now").

**First reads** (`first_run`, 4.5). What a source does on its first read is a setting, so connecting a full folder or
mailbox neither floods the queue nor runs up cost on day one:
- `baseline` (the default): the first read only notes what is there.
- `recent`: it also hands in what arrived, changed or happens within `first_run_hours` of the read (24 by default): the last
  day's mail, today's meetings. A message counts by when it was received, an event by when it starts (before or after now),
  anything else by when it changed.
- `all`: everything there is is handed in as new.
- **On request**, after a first read that only noted what was there, the person can hand in the recent items from the
  Sources screen ("Look at the last day"). The core hands in the items already read, in the same window, that haven't been
  handed in, as if the source had been set to `recent`; triage rules apply as for any change.

**Sources a sign-in starts** (6.27). Signing in to a service starts the sources its add-on declares (the inbox, the main
calendar), with `first_run: recent`, so the first thing the person sees is their recent mail and today's meetings handled by
the assistant.

## 6.5 Triage

Applies triage rules in order before queueing, using registered matchers. The rules live in `watch.yaml`, beside the sources
they apply to (4.5; decisions, 2026-10-11, "Triage rules live beside the watched sources"); the core's matchers are `cosmetic`,
`by-us`, `terms-absent`, `name-matches`, and for mail `bulk-mail`, `service-category` and `sender-rule`, and plugins register
more (a matcher gets the mail item's details as `change["message"]`). A matcher is deterministic,
never calls AI, and returns a reason in plain words or nothing; the first rule that matches closes the change. Each closed item
records the rule and a readable reason, is kept as a source and a request that is already done, appears under "Auto-closed",
and has a one-click way to send it back ("Take a closer look" queues it and records a `pulled_back` signal, so rules can be
tuned, 6.20). A closed mail item is left out of Today's list of what came in, and counted. A matcher that fails counts as no
match and is contained like any plugin call (6.1).

**Setting aside personal and sales mail** (owner, 2026-10-12; the rules part is phase A5, **built**, `tests/test_set_aside.py`; the sorting run and the
proof that learning never reads it are phase L0). Mail that isn't work goes into a **Set aside** folder in the app, in two
sections: *Personal*, and *Sales and promotions*. The person's mailbox is never changed; the add-ons read only. Set-aside mail
never reaches the assistant and never feeds learning:
- **No knowledge from it:** no signal, fact, glossary term, lesson or evaluation case comes from it, and the repeat-correction
  and knowledge-used rates leave it out (6.20, 6.22). **As built,** a set-aside change is kept the way a closed one is, as a
  source and a request that is already done (never queued, so no AI run), marked `set_aside`; it is left out of What changed,
  and the mail item's snapshot carries the mark, which is what the folder and Today read. L0 must keep learning from reading
  any request or snapshot with that mark.
- **Its words never go to an AI account.**
- **What remains is sorting:** the person's own choices about sorting.

A mail item carries, besides its sender, received time and unread mark, `bulk` (the message has a list-unsubscribe header or a
bulk or list precedence; the core's mail folder reads it from the headers) and `categories` (the service's own, as read, in
lower case). Both come from the add-on (plugin API 0.3.57) and default to unknown, so an add-on that doesn't set them works as
before.

It is sorted in this order, first match wins:
1. **The person's own rules**, in the `triage:` list (4.5). A rule with `set_aside: personal` or `sales` sets mail aside in that
   section instead of plainly closing it; `set_aside: never` keeps mail with the assistant against every set-aside rule after it
   and against the built-in sorting. The app keeps one rule of its own per choice (a `sender-rule` with the senders and domains
   listed), so the list stays short: "never" goes first in the list, a set-aside rule right after the last "never", and a sender
   moves out of the other choices when the person changes their mind. A `sender-rule` matches the sender's address (read from
   the message's sender, else its author, else the text's From line) or its domain, and a domain matches its subdomains, in any
   case.
2. **What the mail says about itself, built in:** after the list, and with no setting to edit, the core sets aside as sales mail
   mail that is `bulk` (the `bulk-mail` matcher) and mail whose `categories` include promotions, social or forums (the
   `service-category` matcher). One setting, `watch.set_aside_defaults` (on), turns this off. It applies to every workspace,
   whenever it was made, because it isn't a rule written into the file. *Why not in the file:* a default written into a new
   workspace's list would never reach a workspace made before, and the person edits nothing to be helped.
   The sender in the person's contacts who isn't one of the workspace's people (`personal-contact`) is *designed, not yet
   built* (L0).
3. **The assistant's sorting**, for mail the rules can't place (`watch.sorting: ai`, on by default, chosen in the
   walkthrough's Mail step) is *designed, not yet built* (L0):
   - a small low-cost run sees **only the sender, the subject line and the service's category**, never the body;
   - it answers work, personal or sales;
   - unsure means work, so nothing is hidden on a guess;
   - one run covers a batch of headers, not one per message.

**Correcting it** (all built):
- **Any item in Came in or What changed that is a mail message** has "Set aside: personal" and "Set aside: sales" in its menu.
  The message moves to the folder at once, and a request of it that hasn't started (queued, or stopped for the person) is
  closed, remembering where it was. Undo puts both back. What the person set aside by hand stays set aside if the message
  changes.
- **Any set-aside item** has "This is work", which hands it in after all (a request set aside by a rule is queued; one the
  person had set aside goes back where it was; a message that was never handed in is handed in now) and records a `pulled_back`
  signal (6.20). It shows in Today's Came in again. Undo sets it aside again.
- **Each correction offers** "Always for this sender" and "Always for this domain": a sorting rule written through the settings
  save path as the person's own change, with a read-back toast and Undo. After "This is work" they are rules to keep the
  mail; after "Set aside" they are rules to set it aside in that section. Settings under `watch.` apply at once.
- **Confirm** (each row's menu, and "Confirm all" for a section): the person says the mail was rightly set aside. The app
  *learns* a sender rule for each distinct sender, in the message's section, in one save with one read-back ("From now on, mail
  from a@example.com is set aside as sales") and one Undo; when three or more confirmed senders share a domain, the toast
  also offers "Always for example.com". These are sorting rules and nothing else is learned from the mail. The app also
  *deletes the message from itself*: after `watch.set_aside_keep_seconds` (60) it removes the snapshot's subject, sender name,
  link and saved text, the saved source record's title and text, any saved text file that nothing else holds, and the earlier
  values of those fields in the ledger (the entries stay, with who made them and when, and a write that removes the content is
  recorded like any other). What stays is a marker: the source, the message key, the sender address, the date, the section and
  the rule, so the next read finds the message and never hands it in again. The folder says how many were deleted. Until the
  time passes the copy is simply held and Undo ("unconfirm") brings the message back; after it, Undo refuses and says so (it
  doesn't copy anything for the undo, it delays the deletion). The mailbox keeps the original. Not touched: what the assistant
  already made from the message before it was set aside (its changeset and the records that came from it), and earlier backups
  and the export's git history, which hold the old text until they age out.

Sorting corrections tune sorting only. They never become content lessons.

**On screen:** the folder is a section of Sources beside Auto-closed, one row per message (subject, sender, date, why it was
set aside), grouped into Personal and Sales and promotions. Today never lists set-aside mail; Came in shows a count ("6 set
aside") that opens the folder. Set-aside mail is kept like other sources and follows retention (5.2).

## 6.6 Dispatcher

**As built.** The packet holds, stable parts first and the request last: the instructions, the op reference for the task kind,
the task's playbook guidance, every open action and open question in a compact form, the people, the projects, the values each
list-bound field takes (5.4), then the date, the PM's note (trusted) and the cleaned input (untrusted). Input cleaning, one input
per call, the fix round, the fallback chain and the escalation tier are built. **No knowledge reaches the packet yet:** facts,
rules, lessons, the glossary, routing and style notes arrive with the learning slice (6.22, phase L), and scope and looked-up
facts with 6.18 and 6.19.

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
  - the playbook entries for this task kind (3.8), then the knowledge section (6.22): every active rule, the active lessons
    whose target matches, the glossary (all of it while small), routing for the people and projects in the input, and style
    notes for the recipient of an outward draft;
  - the facts of the projects the input touches, ranked (key facts, overlap with the input, newest) and cut at a budget, with
    what was left out said (6.22);
  - the area each related person and item is in, with each domain's contact (6.18), and looked-up facts (6.19);
  - which recent edits and pages were made by `our_accounts` ("published by the cockpit", so nobody is asked who made them);
  - the op reference (core and enabled plugins' ops) and how to ask for a search (6.22).
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
  **slow-changing** (every active rule, the lessons targeted at the task kind, the whole glossary while it is small) and
  **current** (all open actions and questions). The request-specific
  parts follow: the knowledge that depends on the input (lessons targeted at its projects or people, routing, the glossary
  terms it uses, style notes, ranked facts; 6.22), scope, related records, today's date **and the input's received date**
  (phase L0, before real use), and the input last. Most providers discount or cache a repeated prefix, and only an identical one: so each layer is serialized in a
  deterministic order with no dates, counts or other volatile values, and the batch's calls run close together because cached
  prefixes expire after minutes. **The prefix is not frozen for a batch** (*changed after the first design author's review*):
  each request's packet is built from the current state, so input 2 sees the action or question input 1 just created or
  closed. Only the layer that changed loses its cache. That is usually the open items, the last stable layer, so the
  static and knowledge layers stay cached. Two inputs about the same thing (two edits of one file, a mail and its follow-up)
  then don't each file the same question. The code already builds each packet when its request runs. The adapter marks a cache point after each layer when its provider supports caching
  (`prompt_caching` capability, 6.16) and ignores the marks otherwise.
- **Open items, full and compact** (*designed, not yet built*; `open_items.compact_share`, 4.9). An open action in full form is "[project] text (owner, due) → how to close it" (its id and
  the match text that closes it); in compact form it is id, owner and title, with no closing hint, since the id alone is enough
  to close it. Actions for the request's own projects are always in full form. Actions for other projects switch to compact
  form only when the open-items list passes `open_items.compact_share` of the budget (default 40%), so trimming is by size, not
  by rule. For scale: one PM with about 20 projects has about 50 open actions and 10 open questions, roughly 3,000 tokens in
  full form, so compact form only starts at a few hundred open actions.
- **Size budget** (today one key, `dispatch.max_input_chars`, and an input longer than it is refused with a request to split it;
  a `max_input` per task kind, capped by the provider's context, is *designed*, 4.9). After the
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
the op. Required on `action.add`, `action.close`, `question.done`, `fact`, and any `record.set` that changes a date, status,
owners, target or owner (and, in the project management pack, on its RAID and dependency updates). When the request came from
the PM's own note, the evidence can be that note. Evidence exists so claims taken from inputs can be checked: a change the
person makes on screen, or approves in a plugin's action, is not a claim and carries none (decisions, 2026-10-12, "Plugin API
0.3.19, and evidence only for claims"). Evidence written as a bare string, or with extra keys beside the quote, is read as the
quote; the quote is still checked word for word. Evidence is kept in the ledger and shown on the row ("closed because the
email said: ...").

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
friction and the injection risk isn't there. (Built: the tier decides, and a system op from anyone but the PM is held. The
read-back below, the contradiction pause and the `applies_to` targets are *designed, not yet built*: review of 2026-10-12.) The real risk with PM-stated rules is misreading, and misreadings came from a new
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

**Core op types.** The ops built today (`docs/plugin-guide.md`, "Core ops", is generated from the code and lists every
field):
- Data: `action.add`, `action.close`, `question.add`, `question.done`, `fact`, `note`, `person.add`, `record.set` (project
  status, phase, target, priority, summary, parent, language and owner; action text, due and notes; question title and text;
  person role, organization and why they matter), `record.log`.
- The person's own: `record.edit` (any field of any record, including an edit made to a file in the synced folder, which waits
  for the person's review there), `record.delete` (with Undo), `file.add` (made only by plugin actions, with the file's
  bytes), and the long-text ops `text.draft` (the assistant's text, always a pending draft), `text.propose` (the person's own
  work arriving from outside), `text.accept`, `text.discard` and `text.edit`.
- Value lists: `list.add`, `list.rename`, `list.retire` (system tier, each with Undo, 5.4).
- Project and stages: `project.add` (a system op: from the assistant it waits for the person) and `stage.move` (always waits
  for the person's confirmation).
- Asking (6.25): `answer`, `setting.propose`, `report.draft` (a report to the product's maintainers, drafted for the PM to
  approve and send, never a code change, 6.13).
Plugins register more, namespaced, each with its tier. Reading notes is offered every op except those that are the person's own
or only for actions and asks (deleting, `file.add`, `project.add`, `record.edit`, the long-text ops, and the asking ops).

*Designed, phase L-core (L3b): the obvious next step* (owner, 2026-10-13). When an input names something new, the
assistant offers the obvious way to record it, as one click the person confirms, and the answer is learned (6.22):
"Who is this?" offers "Add a new person" filled in from the input; a project it hasn't heard of becomes "Add a project
<name>?" with "It's part of <a project>" and "Not a project" (reading notes may then propose `project.add`, which waits
for the person); a date goes under its project as a calendar entry; an unknown organization is added with the person;
a signature's address or number is offered for the sender's record; an action gets the date the input gives; a reply
that answers an open question proposes marking it answered; a meeting invitation shows on the agenda under its
project.

*Designed, phase L0:* `event.add`, a calendar entry in the app's own calendar (a date or a date range, a title, the
project it belongs to, and evidence), recorded when an input that isn't set aside names a date for something (a delivery
window, a deadline, an appointment), beside the fact. It is never written to a calendar service (owner, 2026-10-13).

*Designed, not yet built* (the first design's list): data ops `record.add`, `record.del`, `record.rename`, `action.update`,
`action.assign`, `decision.add`, `milestone.add`, `risk.add`, `question.update`, `question.move`, `question.drop`,
`meeting.add`, `meeting.update`, `person.merge`, `dependency.add`, `dependency.update`, `issue.add`, `issue.update`,
`issue.resolve`, `risk.realize`, `assumption.add`, `assumption.update`, `meeting.agenda`, `glossary.add`, `glossary.update`,
`lesson.add`, `parked`, `inbox`, `lookup`, `watch.item` and `doc`; outbound ops `draft.request`, `dev.request` and `handoff`
(4.18); and system ops `milestone.rebaseline`, `rule.add`, `rule.retire`, `watch.add`, `watch.remove`, `config.set`,
`plugin.enable` and `plugin.disable`. The dependency, milestone, risk, issue, assumption and meeting ops move to the project
management pack with 6.23 and 6.24. Today a rule, a watched source, a plugin or a setting is changed from a screen (4.22) or
proposed by the assistant as `setting.propose`.

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
- **Scope** (6.18; *designed, not yet built*, it waits for the scope resolver, roadmap phase E): an action's owner must be in the tracked area or be the PM. An action for anyone else, or with an owner
  label that matches another domain's `owners` patterns, is refused with the reason, and the AI records the work as a fact on
  the observed item instead. A question to anyone outside the tracked area is refused unless `cross_domain.allow` is
  `impact-only`, it goes to that domain's `contact`, it is marked `impact`, and it names in `affects` the tracked record it is
  about. Questions to people inside another domain who aren't its contact are always refused.
- **Facts** (6.19; *designed, not yet built*, roadmap C4): a question whose `asks_for` is a fact kind with lookup sources is refused and sent back as a `lookup`; a
  question to anyone in a kind's `no_questions_to` that asks for that kind is refused. A lookup that finds nothing records TBD.
- **Audiences** (*designed, not yet built*, with the publisher): content reaches a destination only if every source it draws on allows that destination's audience (4.1). A
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

Built: `blocked-wording` (blocked phrases, including "confirm / check whether" in actions), `run-on-list` (run-on separators),
`near-duplicate-action` and `evidence-fit`, below, plus any lint a plugin registers (4.17).
- Wording on anything that reaches a shared output: blocked phrases, run-on separators; locale spelling (*designed*).
- A question whose text matches a fact kind's `terms` but doesn't declare `asks_for` (*designed*, with fact lookups).
- A question that links to something the recipient may not be able to open, or carries bookkeeping in its label (*designed*).
- A new action that looks like an open or done action for the same deliverable (`near-duplicate-action`; the similarity
  threshold is fixed at 0.8 in the code today and is to become a setting, 4.17).
- A link that doesn't respond (*designed*).
- `evidence-fit`: the quoted words don't plausibly concern the target record (its title, owner and project share nothing with
  the quote). Default `return`, which holds it for the PM if the item will reach another person.

Every finding is recorded on the changeset with the check's name and severity, so the PM sees why something came back.

### Normalize, apply, undo

**Normalization before apply:** names in id fields resolved to ids (6.11), dates parsed to zoned values, links enriched from
item keys and known titles; a value for a field bound to a value list is checked against the list and refused if it is not on
it (5.4).

**Apply** is one transaction: check record versions, apply the ops in order, write a ledger entry per field changed (5.0),
re-render affected outputs into drafts, commit. On error the transaction rolls back and the error is recorded on the changeset.

**Undo** builds a reverse changeset from the ledger's before-values. Ops that depend on each other share a **group**, and undo
is per field across groups but all or nothing within a group:

- The applier groups the known pairs itself (an answer recorded as a fact with the question it closed; a new action with the
  notice that told its owner; a rename with the outputs it re-rendered); the AI may group others.
- A group with a conflict (a field something else has changed since) is listed and skipped, never half restored; the PM can
  keep the current values or restore the group.
- Undo goes newest first, so an op that refers to an earlier one's record is undone before it; an undo that would break a
  unique field group or leave a dangling reference is skipped and reported, never half done.
- **Send back** queues the work again with the person's note and, by default, first undoes what the assistant did; the person
  may keep it instead, and the old work then counts as looked over and the new run builds on it.
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
- Answer flow, in two kinds, as built:
  - **The PM's own answer** to a question put to them (`/answer`) is the PM's words. Learning from it applies at once
    (6.22). A held op the PM's answer releases ("yes, add them" to a `project.add`) counts as the PM's own.
  - **A reply someone else sent,** pasted by the PM (`/reply`), is handed in as pasted content: untrusted, like the paste
    box's "pasted content". Only the PM's own note beside it counts as the PM's words. So "not me, ask X" in a reply becomes
    a routing proposal that waits for the person, never routing with the PM's authority.

  A reply becomes a request carrying the question and its `on_answer`; the AI records the answer as a fact, updates
  records, closes or narrows the question, and re-checks every other open question to that person against the same answer.
  The PM's own answer is recorded on the question today; queuing it the same way is *designed*.
- **Same question twice:** `near-duplicate-question` (a lint, 4.17) compares a new question with open questions and ones
  answered in the last `checks` window, since the assistant doesn't know the `key` that deduplicates (*designed, phase L*).
- Feedback flow (send back, or the question's own menu): reword, reroute, drop (kept in a dropped-questions register with the reason) or
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
  alias that matches one person becomes that id; the PM's aliases become the PM; a bare first name only one known person has
  becomes that person **only when the input's context matches** (the person is on the same project, or is a participant in
  the thread); anything with a different initial or surname fragment is held (*changed after the first design author's
  review; the code today resolves any unique first name, fixed in phase L0, before real use*); an owner written in the workspace's `owner_format` is parsed into person and team. Anything ambiguous or
  unknown holds the op and files one routing decision ("Who is 'Sam'?", with the candidates and "Add a new person").
- **Rendering:** owners in `owner_format` ("Product (Jane Doe)"), recipients by full name, greetings by first name. Changing
  the format changes every output at the next render.
- **No sweep needed:** nothing stores a short name, so nothing needs rewriting later. Free text (notes, fact text) keeps names
  as written.
- **Merging:** when two person records turn out to be one person, `person.merge` repoints every stored id (each record type
  declares the ids it stores, 5.1) and the ledger records it.

## 6.12 Records, renderer and publisher

*Designed, not yet built* (roadmap, phase C4: the publisher and the file channel, with Waiting to go out). The product's rules
for it, that nothing goes out without the PM approving that exact content, already bind every path that sends.

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

- **Built (roadmap A2): runs a stop left unfinished.** When the worker starts, every request left running goes back in the
  queue with the note "The app closed while this ran; it runs again now." and raises `request.queued`. One found running
  after it was already put back once goes to needs you instead ("Stopped twice when the app closed during it"), its
  approval untouched, so Try again and Dismiss apply and a request that stops the app can't loop. The number of
  interruptions is counted from the request's own history (the ledger), not from `attempts`, which also counts a
  person's Try again. Built: `tests/test_requeue.py`.
- *Designed, not yet built* (roadmap, phase E): every few minutes, re-queue requests whose run never finished (the same
  rule, while the app runs), push work waiting too long in working hours, repair
  changes no request carries, detect stale data and outages, run the scope sweep (6.18), the rules review (6.21) and the
  notices, and commit the readable export (5.0) hourly.
- *Designed, not yet built:* problems in the automation become `Problem` records (shown as "automation problems", so "issue" keeps its project
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
  default, or a configured channel such as the maintainers' issue tracker form. Built today: `report.draft`, from an ask
  (6.25), which the person copies and sends; `dev.request`, `reports` and the validator that lists the ops considered are
  *designed*.
- **One place per problem:** a problem and its report show on its problem card only, and are counted there (Today, the header
  and the problem list count it once).
- **Requests for other projects:** a request about code another project owns (4.18) becomes a `handoff` draft for that
  project's owner.
- The self-check (Part 10) validates config schemas, plugin manifests, imports, the web build and the specificity guard; run it
  after any change.

## 6.14 Scheduler, offline behavior and restart

Jobs that need the network wait while it's down and run when it returns ("Offline, waiting for the network" shown, not
failed). After sleep, the first refresh runs on wake when data is stale, after the connectivity check (6.4). A held or failed
job doesn't count as a run: a refresh that failed leaves the data marked stale, with its age, so nothing looks fresh that isn't.
Plugin jobs follow the same rules.

**What runs while the app runs (as built).** The process that holds the instance lease (5.0) runs four loops, each on its own
thread so a slow one never holds up another:
- the **worker** takes queued requests one at a time and moves stage-ready records on;
- the **backup** loop makes a full backup whenever one is due and retries after a failure (4.15); it goes by the wall clock, so
  a computer waking from sleep catches up at once;
- the **synced folder** loop writes the folder after any change and renews this install's lease, and brings outside edits
  back for review (5.0), checking every few seconds;
- the **jobs** loop, once a minute, runs the plugin jobs that are due (at the interval each job declares or
  `workspace.plugins.jobs` sets) and reads the watched sources that are due (`every_minutes`, 6.4).
A scheduler lease in the jobs table, and `server.role` (`all`, `web` or `worker`) so a host can run them separately, are
*designed, not yet built* (hosted mode, Part 11, is not part of 1.0).

**Settings and code that change under a running process, and the restart** (decisions, 2026-10-11, "The app restarts only
when it must, and only when the person says so"). The worker notices when its config files or its own code changed since it
started (a hash of the config files; the newest modification time of the program's source). Then:
- If every changed key is **live** (4.22: AI accounts, tiers and budgets, who the person is, the names, the screens' wording
  and shortcuts, the accounts counted as ours, backups, the watched sources), the changed files are validated and taken in
  at once, and open screens are told. A file that does not validate changes nothing and is logged.
- If any changed key is not live, or the code changed, the settings in use stay as they were, no new job starts, queued AI work
  is held ("Settings or code changed since the cockpit started; restart it to use them"), and the screens say a restart is
  needed and for which settings. The person chooses **Restart now** or **Later**. **The app never restarts on its own.**
  Old code never quietly runs new settings; nothing is half-reloaded. **Held work is never a silent stop** (*phase L0, before real use*): the
  first Decide line on Today says "Restart to run 7 waiting requests", with the count, for someone who opens the laptop and
  never looks at the header.
- **Restart now** (`POST /api/restart`) restarts between requests, at once if none is running; locally the process re-executes
  itself. A copy that can't start itself again (it was not started by `cockpit serve`) says to close it and start it. The
  serve command stops its web server without a signal, so the restart cannot end the process by raising the stop signal
  again.

## 6.15 Today builder

Builds the PM's Today, the home screen (7.7), from live data and from plugins' Today contributors. Nothing in it calls AI or
reaches a service; it reads records only, and the order is computed by the engine, never by the screen. **Every line starts
with what the PM does and says where:** answer N decisions, review and send N drafts, look over N changes, send N questions to a
person, follow up on questions waiting N days, finish N of your overdue actions, move N items to their next stage (6.26),
approve N runs that need a go because of their cost (6.16). Status, progress and things the automation handles never appear.

**The ranked queue (as built).** `engine/today_queue.py` returns one list (`GET /api/today/queue`) in four groups, in this
order, each line with a kind:

| Group | Lines (kind) |
|---|---|
| **Decide** | work held until a restart (`restart`, "Restart to run 7 waiting requests", always first; *phase L0, before real use*); a decision or a question put to the PM (`decision`, `question`); a name the assistant couldn't place (`who_is`, "Pick who 'Maya' is"); an action with no owner (`owner`, "Pick an owner"); an item the applier held for the PM's yes (`held`); a run waiting for the PM's go because of its cost (`go`); a run the provider refused, waiting for the PM to choose what happens next (`refused`) |
| **Risk** | work that failed (`failed`); an AI account paused until its limit resets, with the time and the count waiting (`paused`, *phase L0, before real use*); a learning check that failed after a switch, with Switch back (`switch_failed`, *phase L*); the PM's own overdue to-dos, as one line (`overdue`) |
| **Review** | the assistant's work waiting for a look (`review`), with what it did counted by kind (actions added or closed, questions, notes, recorded, people, projects, drafts, held, refused); learning proposals from corrections waiting for Keep (`learned`), the daily card of learning from inputs (`learned_daily`) and the catch-up list (`learned_backlog`), all *phase L*; a new or probation account's work, marked as such (*phase L*) |
| **Send** | messages to send, one line per person (`send`); a person who hasn't answered in `ui.today.nudge_after_days` days (`nudge`: questions sent and actions told, 4.11) |

Within a group, a kind has a fixed place (decisions first, then who-is, owner, held, go, refused, questions), then the line that
has waited longest, or is due first, comes first; a nudge goes by its longest wait. **Held items and decisions are always
top-level lines**, never only inside a review. A line has a key that stays the same while the thing it stands for waits, the
count it covers, the record ids it covers (actions, questions), the title of the input it is about, whether the input was
untrusted, and why it waits, in the engine's own words (7.6). Plugin Today lines and stage lines ("ready to move on", 6.26)
are added by the screen into their groups; a plugin line carries one action, its own or one of the core's (open, review, go,
answer, move to the next stage). Lines the first design listed for meetings to hold this week and for automation problems are
*designed, not yet built* (with the governor, 6.13); at-risk dependencies and risk reviews are lines the project management
pack adds (6.23, 6.24).

**The rail's feeds** are separate calls over the same records: the **agenda** (`/today/agenda`: events from watched calendars
on today and `ui.today.agenda_days_ahead` days after, in the person's time zone, all-day events first), **your to-dos**
(`/today/todo`: the PM's own open actions, overdue first) and **came in** (`/today/arrived`: mail received within
`ui.today.mail_hours`, newest first, at most `mail_max`, leaving out what a triage rule closed and saying how many). They read
the structured fields of watched items (6.2), so no AI call stands between a message arriving and the person seeing it.

**Item titles** follow the title rule (7.14) and are built by `engine/titles.py`, never by the screen: "{kind} from {person} ·
{topic}". Each part comes from structured fields first, then from the assistant's short topic, and only then from the text:
- the **kind** is `email`, `calendar`, `change` (another watched item), `note` (the person's own words), `pasted` or `task`
  (work the app started, such as a stage's task);
- the **person** is a known person's id when the sender names exactly one, else the sender as written with address parts
  removed; it comes from a watched item's author, or from the `From:` line a pasted message starts with;
- the **topic** is a watched item's subject (with "Re:" and "Fwd:" removed), or a pasted message's `Subject:`; else the
  **changeset's `topic`**, the few words the assistant gives for what the input was about (kept to one line, cut at a word,
  at most 60 characters; for a plugin's person action, the proposal's topic); and only then the first meaningful line of the
  text, with greetings, quoted headers and sign-offs skipped (`language.title_skip`, 4.6), cut at eight words.
A title never starts with a greeting or "From:". The same title is on Today, What changed and the review.

## 6.16 AI provider layer (any model, by configuration)

The PM brings their own AI accounts: a personal key with a model vendor, an aggregator that reaches many vendors with one key,
a model running on their own computer, or a command-line agent signed in as them. The product can use one or mix several, and
moving between them is an edit to `config/ai.yaml` (4.8). Nothing outside the adapters knows which vendor is in use. Adapters
built today: `openai-compatible` (any endpoint, an aggregator, a local server), `cli-agent` and the stand-in; native vendor
adapters are *designed, not yet built*.

**Kinds of provider, and the adapters that serve them:**

| Kind | What it is | Adapter |
|---|---|---|
| Native API | a vendor's own API, with its own features (structured output, caching, files) | one per vendor where its API differs: `anthropic`, `openai`, more as plugins (*designed, not yet built*) |
| OpenAI-compatible API | any endpoint that speaks the widely used chat-completions format: many vendors offer one (xAI, for example), as do inference hosts and local model servers | one generic `openai-compatible` adapter, configured with `base_url`, key and model ids |
| Aggregator | one account and key for many vendors' models, with its own model catalog, prices and routing options (OpenRouter, for example) | `openrouter`, a thin layer over `openai-compatible` that reads the catalog and passes routing options (*designed, not yet built*; today an aggregator is an `openai-compatible` account) |
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

**Adding an account** (Settings, AI): pick the kind, by name, from a list the app ships as data (`catalog/ai-endpoints.yaml`:
services, local servers and the common command-line agents, each agent with its command, the program's own options that keep
its tools off, how it takes the packet and where its answer is; the screen says whether the program is installed and how to sign
in, and the person never types a command); paste the key, which is kept on this computer while config keeps only a reference
(the keychain is *designed, not yet built*, 12.1); **Test** checks the key and lists the models with their capabilities and prices; choose which models fill which tiers; set
`allowed_data` (new accounts start at `open`, and the screen says who will see the data: the vendor, and for an aggregator the
aggregator too; it also says that notes, mail and meetings are internal, so the assistant can work on them only once
Internal is ticked, and a run stopped because no account may see its material offers "Let <account> see internal
material" as its action, the person's own one-click raise, phase A); run the evaluation (below) before a model is approved for a tier.

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
  never the model's output: a model writing "not logged in" in a report is text, not an auth failure. An agent that prints
  its errors on its output instead (its account sets `agent.errors.report_on_output`) has that output read as its error
  report, and only for a run that exited with an error. An agent sees the user name and temporary folder as well as PATH,
  HOME and the language settings, since a system keychain keeps its sign-in under the user name. Output and error stream
  are both kept on the `Run`, so a usage limit is never hidden behind "failed before doing any work";
- `health()` for the governor.

Adding a vendor that speaks the common format means adding a `providers:` entry; one with its own API means adding an adapter
plugin and an entry. Nothing else changes.

**Routing by capability, not by name.** Each task kind declares what it needs (a screenshot needs vision; most need structured output and a context size). The router picks the tier's provider and model,
checks that model's capabilities and the request's data level against `allowed_data`, and falls through the fallback chain if
it can't serve the task. Fallbacks can cross accounts and vendors (a usage limit on one account moves the work to the next).
A fallback is a switch nobody chose at that moment, so (*designed, phase L*, 6.22):
- **Who may be in the chain:** only an account that passed the learning check, or that the person accepted unchecked.
  Settings ask when an unchecked account is added to a chain.
- **The first run on a fallback account** tags its cards "First run on <account label>", so its output gets a closer look.
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

**Exit 0 with no answer is a failure** (*phase L0, before real use*). Some agents exit 0 after printing a limit or sign-in message to their
output, with no changeset. That is its own outcome, `no_output`, never "done": it is retried, then counts toward the
empty-run rule (8.6). Today an agent that should answer in its outbox and doesn't is already `invalid_output`, so nothing is
marked done. The separate outcome lets the empty-run rule and the quality panel count it apart from a malformed answer.

**Probation for a new account** (*designed, not yet built*; the learning check with a switch is phase L, 6.22). A switch of a
tier's account or model offers to run the learning fixture pairs first, with their cost estimate. **A command-line agent's
program version is part of the account** (*phase L-more*): agents update themselves, and a new version can change flags, defaults or error
output under a passing smoke test. So each `Run` records the agent's version; a version change is treated like an account
change (smoke test, then "first run on <account>"); and the adapter turns off the program's own auto-update where the
program allows it, by settings in the agents catalog (data, not code). **The person can end probation early** (*phase L-more*) from the
quality panel once the account's send-back rate is below `ai.probation.end_below` over at least `ai.probation.min_runs`
runs, because 20 reviewed runs per task kind is a lot of cards when mail arrives on its own. A newly approved account's changesets carry a "new account" tag and always wait for review
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

**How a case is scored** (*the harness as built, then the first design author's review of the golden set; designed, phase
L-core*). Today every case runs with the clock frozen at one moment, on a fresh copy of the fictional workspace. A case
lists the ops it expects and, optionally, ops it forbids. The review found the set too easy in ways that would let a
low-cost model look as good as a strong one, so each case gains:
- **`received:`,** the date and time the input arrived. The harness freezes the clock there and puts it in the packet header
  (the received-date fix in L0), so a relative date ("by Tuesday") is tested against the input's own date.
- **`exact: true` by default:** no applied ops beyond the expected ones, except `note` and `source`. A case relaxes it when
  more is acceptable. Over-extraction was the running version's most frequent real failure: duplicate actions, actions for
  people outside the area, notes nobody needed.
- **`given:`,** the records the case starts from, so a case can say "the action already exists" and expect a date update
  instead of a second action.
- **A busy workspace:** at least half the cases run against a fixture with 30 to 50 open actions and questions, including
  near-namesakes ("send spine options", "send corrected spine file", "agree spine with the printer"). Choosing the right id
  is then part of the test, as in real packets.
- **Forbids that last:**
  - `forbid: {tier: system}` refuses any system-tier op (rules, settings, and from phase L any knowledge entry that applies
    without Keep), so a hostile case catches ops that don't exist yet;
  - `forbid: {names: <person>}` refuses any op that names an injected person, not only a new person record.

**Reproducible runs.** Every `Run` keeps a fingerprint of exactly what was sent (the packet, stored once and referenced by
hash; sources by id), the prompt template and playbook versions, the parameters, the model id exactly as the provider reported
serving it, and for an aggregator the upstream host that served it. Aggregators can route one model id to different hosts and
builds, so `routing` (4.8) can pin preferred hosts, and the quality panel can compare by host. `cockpit replay <run>` re-runs a
packet on any model, and any run can become an evaluation case. (*Designed, not yet built*: what a `Run` keeps today is the
provider, the model as reported, the tier, tokens, cost, outcome and error; the packet fingerprint, `replay` and upstream-host
routing are not built.)

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

**Refusals, content levels and waiting out limits (as built).**
- A **refusal** is its own outcome. An adapter reports one only from the provider's own signal (a content-filter stop, a
  refusal field in the answer, a content-policy code in an error body), never from the answer's words. The run is recorded as
  `refused`, with its cost and the provider's reason, and the request is never retried, sent to another account or escalated:
  it waits for the person with the reason and the cost, and the person may send it to another account allowed to see the
  material (`Request.use`). Accounts are offered by their names, never by model (decisions, 2026-10-12, "A refusal is its own
  outcome…").
- **Content levels** route work away from accounts that would refuse it before it is sent. The workspace defines its levels
  (`ai.content_levels`), a project or a plugin record carries the ones its material has (only the person sets them), an account
  may list the levels it takes, and a run goes only to accounts that take all of its record's and its project's levels; if none
  does, the request waits and says why (decisions, 2026-10-12, "Content levels route work away…").
- **Rate limits.** When the last account in line says to slow down, the call waits and tries again (`ai.rate_limits`: tries
  and longest wait); with another account available it moves on at once. Calls an account refused for rate reasons are
  reported as "not run" in evaluations and left out of the score.
- **Waiting for a go.** Anything above `budgets.confirm_above_usd` asks first; `budgets.confirm_unpriced` makes runs whose cost
  can't be estimated (a subscription) ask too, so spending stays the person's choice even where "ask above an amount" never
  asks; plugin work can be declared to always wait for the go.

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

*Designed, not yet built* (roadmap, phase E). One resolver answers "whose area is this?" for any person, team, item or project: tracked, a named domain (with its contact),
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

*Designed, not yet built* (roadmap, phase C4). Before any outside lookup, a run searches what the workspace already knows
(6.22, phase L). Some facts have a published home. In the reference pack's setup, for example, a work item's release lives in a tracker field
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
is recorded as a `signal` record (5.1) at the moment it happens (the recording is built; the quality panel, private evaluation
cases from signals and rule suggestions are *designed, not yet built*):

| Signal | Recorded when |
|---|---|
| sent back | the PM sends a changeset back, with the note |
| undone | the PM undoes a changeset or part of one |
| dropped / reworded | the PM drops or rewords a question the assistant filed |
| pulled back | the PM pulls an auto-closed change back ("This is ours") |
| draft edited | the approved content differs from the assistant's draft (the difference is kept) |
| held op declined | the PM declines a held system op or a routing guess |
| edited | the person changes a field the assistant set (a fact, an owner, a due date, an item's project, a question's wording before it is sent). The ledger shows who set each field, so this needs no AI. A silent correction, learned from in the batch (*designed, phase L*) |
| repeat correction | any of the above, on a run whose knowledge log (6.22) shows it was given an active lesson or rule whose target matched the corrected item (*designed, phase L*) |

The repeat-correction rate, not the raw correction rate, says whether the assistant is learning; the quality panel shows it
next to the others, week by week. Refusals are counted per check too, and a check that refuses often brings its seed
lesson into the packet (Part 8, guard kinds). Beside the repeat-correction rate, the **knowledge-used rate**: the share of runs whose changeset says which
lessons, rules or facts it applied (`applied`, a list of knowledge ids). Each id is checked against the knowledge the run was
given, so it is a checked citation, not the model's say-so. If the first rate doesn't fall, the loop isn't closing; if the
second stays near zero, the knowledge isn't reaching the runs that need it. Each signal also starts the learning step (6.22): rates measure the assistant, and proposals teach it.

- **Quality panel** (Admin tab): rates over time by task kind, provider and model (share of changesets sent back or undone,
  share of questions dropped, auto-close pull-back rate, draft edit size), with each figure linking to its examples.
- **Private evaluation cases:** the PM can turn any signal into a case in `<workspace>/evals/` (the input, what the assistant
  did, what was right). `evaluate` runs these alongside the fictional golden set, so a model or prompt change is judged on the
  PM's real work. They never leave the workspace; the product's committed fixtures stay fictional.
- **Learning proposals:** each correction proposes at most one lesson, rule, fact, glossary entry, routing entry or style
  note, on the correction's own card (6.22). This replaces suggesting rules only when send-back notes repeat.

## 6.21 Standing rules review

*Designed, not yet built.* Merging duplicates as they are proposed and listing unused entries come with the learning slice
(phase L, 6.22); the scheduled review is phase E. It covers lessons as well as rules. Standing rules (records, 4.10) are useful until there are too many, they contradict each other, or a rule is
really a setting that only the model is enforcing (the original scope failure was exactly that). A scheduled review (an AI
task kind, weekly by default) proposes, as held system ops the PM confirms:

- **Merge or retire** duplicates and rules that no longer apply; **flag conflicts** between rules, side by side.
- **Promote** a rule that names a person, team, domain, source or fact kind into the config key that enforces it (a scope
  domain, a routing rule, a fact source), and mark the rule `promoted` with the key it became.
- **Promote a lesson** whose guard is mechanical into a rule with a deterministic check, a setting or a lint the product has; a
  guard that needs new code becomes a report to the maintainers (6.13). The lesson stays as the record of why.
- **Retire** lessons and other knowledge that matched nothing for `knowledge.unused_days`.

Rules carry `applies_to`, but every packet includes every active rule (6.22): they are few, and most failures were a rule
the run never saw. The review keeps the active list short enough for that.

## 6.22 Knowledge and the learning loop

*Designed, not yet built* (roadmap: the loop in phase L-core, next after phase A, after which real use starts; Ask's
knowledge, Take my lessons, agent versions, early probation, the unused list and single-record restore in phase L-more,
after the packs; decisions, 2026-10-12 "The learning slice" and "The plan review"). This is what
makes the assistant better at each project the more it sees. It has four parts:
- knowledge is kept as records;
- every run reads the knowledge that applies to it;
- every correction proposes one piece of learning;
- tests prove a corrected mistake is not repeated.

The write side is built: sources with provenance, facts with evidence, ids instead of names, and the corrections recorded as
signals (6.20). This section is the read side.

**Knowledge records.** Six kinds:
- **Fact** (built), plus `key` (the facts that matter most, always shown first) and `as_of`.
- **Rule** (4.10), now a record.
- **Lesson:** what went wrong, why, and the guard. Created from a correction and linked to the signal it came from.
- **Glossary entry:** a term or acronym, its meaning, project or global, and a confidence (confirmed, assumed or unknown). It
  may also carry patterns for splitting compound ids.
- **Routing entry:** a topic, area, project or kind of question → the person who answers it. Negatives too: "doesn't answer
  this", or "never ask them about that; look it up at <source>".
- **Style note:** an audience or recipient → an observation ("replaces names with roles", "cuts delivery claims"). Its evidence
  is the difference between the assistant's draft and what was actually sent.

Every entry has:
- an id;
- a source and its evidence (the request, signal or input it came from, and the words);
- the date it was learned;
- a trust level from its source;
- a status: proposed, active or retired;
- the same structured target that rules have (`applies_to`: task kinds, record types and fields, projects, people, and a
  filter).

Ids matter: a fixture, a rule promotion and a later correction can each point at the exact lesson. Entries change only
through ops (`lesson.add` and `lesson.update`, `glossary.add` and `glossary.update`, `routing.add`, `style.add`, `rule.add`,
`fact`, and `retire` for any kind), so every change is in the ledger with Undo.

**The knowledge section of every packet** is split so the cached prefix stays the same from input to input (6.6):
- **In the stable part,** after the playbook and before the open items:
  1. every active rule (they are few, and most failures were a rule the run never saw);
  2. active lessons targeted at the task kind;
  3. the whole glossary while it is small (under `knowledge.glossary_all_below`).
- **In the per-input part,** because it depends on the input:
  1. lessons targeted at the input's projects or people;
  2. routing entries for the people and projects in the input;
  3. the glossary terms the input uses, once the glossary is too large to send whole;
  4. style notes for the recipient, when the task drafts something that goes out;
  5. the **facts**, below.

The facts are those of the projects the input touches, each with its date and source ("as of
2026-09-14, from the weekly call notes"). A run can then see that a fact is old, not only that it ranks low. They are ranked:
key facts first, then by overlap with the input's terms and ids, then newest first. The list is cut at `knowledge.facts_budget`, and what was left out
is said ("42 more facts on this project; search for them").

**A newer fact replaces an older one.** Ranking alone would still put "ships in release A" beside "moved to release B", and
the run can pick the wrong one. A scope or a date that moves twice in a week is the most common churn. So:
- a `fact` has an optional `supersedes` (the id of the fact it replaces);
- the input's run proposes it when a new fact covers the same subject as an existing one (same project and field, or a high
  overlap of words);
- a superseded fact leaves the packet but stays findable by search, with what replaced it.

The full freshness check (6.19) waits for phase D.

Only active entries go in, never proposed or retired ones. An entry is presented as guidance only when its source is trusted.
Otherwise it is shown as data with its source, as 6.6 does for anything derived from untrusted content. **Keep makes a
proposal from content trusted, in the person's words** (12.8): the kept entry is the assistant's restatement plus its target,
shown in full at Keep, so Keep makes the person its author. The raw source text never enters a packet as guidance, only as
linked evidence marked "from outside". **Order of precedence:** invariants, then the person's own rules and lessons, then a
pack's guidance, which is marked by origin.

**Plugins and the learning loop** (*designed, phase L-core*; from a survey of the add-ons built so far). A pack may hold
material that is not workspace knowledge. A novel's facts are fiction, and its invented names are not acronyms. So:
- a record type or task kind can declare **`learning: own`**. The core's learning from inputs, the new-term scan,
  first-name resolution against People, and fact ranking into workspace facts then don't run on it. The pack keeps its
  own plan records (a series bible, a kill list, book rules), which stay the plugin's;
- a pack can still **publish** entries into core knowledge through ops (real-world research facts, say), and they are
  marked by origin like any pack guidance (12.8);
- when a person corrects a pack's work, the core proposes a lesson targeted at that pack's task kinds, unless the pack
  claims the correction with its own record. One correction never yields both a pack record and a core lesson.

A pack's own task kinds get the same section through one plugin API call. So a writing pack's runs see the person's lessons and
glossary, and a pack's own knowledge (a series bible) can be offered the same way later.

**Search before asking.** A run that needs more than its packet holds asks for it with a `search` request: words, ids, a
project, which kinds (facts, past inputs, records, knowledge). It is not a live tool call, so it works on every kind of AI
account, command-line agents included. The engine runs the search, deterministically and bounded (`knowledge.search_results`),
and runs the task again with the results, at most `knowledge.search_rounds` times (default 2). The instructions say to search
the workspace's own knowledge before an outside lookup (6.19), a question to a person, or a report to the maintainers.

It is also checked where it can be. A `question.add`, an outside lookup or a `report.draft` whose subject a plain search
already answers gets the lint `already-known` (4.17), which sends it back once with the match. It is a lint, not an invariant,
because matching is fuzzy.

**The knowledge log.** Each `Run` records:
- which knowledge entries it was given, by id;
- how many facts were left out;
- what it searched for and what came back.

A bad result can then be traced to knowledge that was missing (not in the packet) or ignored (in the packet, and the answer
went against it). The repeat-correction signal (6.20) is computed from this log.

**Every correction proposes one piece of learning.** When a signal is recorded (sent back, undone, dropped, reworded, pulled
back, draft edited, held op declined, or the person's answer to a question the assistant asked them), a small `learn` task runs. Its packet holds:
- the item;
- the assistant's original output;
- the correction: the note, what was undone, or the text as edited or sent;
- the knowledge entries the original run was given;
- the active lessons and rules.

It returns **at most one** proposal op, or "nothing to generalize":
- a new lesson, rule, fact, glossary entry, routing entry or style note;
- or `lesson.update`, when an existing lesson should have caught it but didn't. A repeat means the guard was wrong, and fixing
  it beats adding a second one.

The proposal shows on the correction's own card as one line: "Learned: … · Keep · Edit · Discard" (7.18). It stays there
until the person decides, and never expires.

How a proposal applies follows the tier rule (6.7, 12.2):
- **From the person's own words** (their send-back note, their answer to the assistant's question): it applies at once,
  with the read-back and Undo.
- **From the assistant's own generalization, or from content:** it waits for Keep. Learning proposed from untrusted content
  never applies without the person.

Before a proposal is shown, it is compared with the active entries of its kind by target and wording, so duplicates merge
instead of piling up. This is the same overlap check as rules (6.7), shown as "Overlaps with …".

**What the person discarded is remembered.** A discarded proposal is kept, with the reason if the person gave one. A new
proposal that nearly matches a discard from the last `knowledge.discards_hold_days` (default 90) is not shown again. Otherwise
the same glossary guess or routing entry comes back from every input that mentions it, and the daily card repeats itself.

**When it runs.**
- **At once, when the person wrote something.** That covers a send-back note, an answer to the assistant's question, or a
  rule stated in Ask. The person is looking at the card right then, and the Learned line should appear while they still
  remember why. Writing the learning down in the same turn as the correction is the habit that makes it stick.
- **Batched,** every `knowledge.learn_every_minutes` (default 30), for silent corrections: an undo, an edited follow-up, a
  pulled-back auto-close, a dropped question, or the person's own direct edit of something the assistant set (6.20). A direct
  edit is often the clearest correction there is.

**A direct edit isn't always a correction.** Sometimes the world changed, not the assistant: a later mail moved a due date,
or work was handed over. Learning from that gives wrong lessons ("the assistant gets due dates wrong"). So:
- the `learn.correction` packet carries every input received after the original run that touches the same records;
- it answers "nothing to generalize" unless the edit contradicts the evidence the run had at the time.

**Which tier writes it.** A bad lesson is worse than none, because it is in every later packet. So there are two task kinds:
- **`learn.correction`:** lessons, `lesson.update` and rules from corrections, on the stronger tier. These are rare and
  high-value.
- **`learn.input`:** glossary entries, routing and facts proposed from inputs. These come out of the input's own run, on its
  tier, which is usually the low-cost one.

Anything proposed after a repeat correction (a guard that already failed once) always runs on the stronger tier. Both kinds
follow cost control (6.16), each with its own budget. Corrections recorded before this was built are learned from once,
when it arrives, into **one catch-up list** ("Learned from earlier corrections: 23 to review"), not into dozens of correction
cards on day one.

**Learning from inputs too.** Before the run, a rules-only step (no AI) lists the terms in the input that look like
acronyms or project terms and are not in the glossary, and the packet names them. The run that processes an input may then
propose:
- glossary entries for new acronyms or terms. An assumed or unknown one that blocks understanding can carry one short question
  to whoever routing says knows it.
- routing entries when the input shows who answers what ("not me, ask X" in a reply). A question the person reroutes by hand
  proposes one as well.
- facts, as it already does.

Since these come from content, they wait for the person.

**Keeping the proposals from flooding.** With mail and calendar read on their own, an everyday assistant proposes a lot. If
Today fills with "Learned" lines, people discard everything and the loop dies quietly. So:
- **Proposals from inputs** are gathered into one review card per day ("The assistant learned 7 things today"), merged with
  each other and with active entries before they are shown.
- **Unreviewed proposals from inputs** expire after `knowledge.proposals_expire_days` (default 14). The count shows on the
  next day's card ("4 expired unreviewed"), never silently.
- **Proposals from corrections** always stay on the correction's own card and never expire.

**Learning from what is said in Ask.** When the person states a rule or a fact while asking the assistant something ("from
now on…", "she's the one who decides that"), the answer proposes it like any correction (6.25). These are the person's own
words, so it applies at once, with the read-back and Undo. In practice, many standing rules come from exactly this kind of
aside.

**Knowledge travels.** Every knowledge record is in the export and import like any record (5.0). A person can also take their
lessons to another workspace (*phase L-more*). **Take my lessons** (Settings, and `cockpit knowledge export`) writes one file holding:
- the active lessons;
- the rules;
- the glossary entries that are not tied to a project.

Loading a file the person exported from their own workspace (signed with that workspace's key) adds the entries as the
person's own, active, with Undo. Any other file loads as proposed, on one review list, with its origin kept (12.8). Facts, routing and style notes stay
behind, because they name that workspace's projects and people. A pack's playbook is the published form of the same idea;
this is the private one.

**Style from what was actually sent.** When the person sends their own version of a draft (today: the text pasted at Mark sent;
later: an approved draft edited before publishing), the difference from the draft is kept as a `draft edited` signal. The learn
task turns a pattern in it into a style note for that recipient or audience. The next draft for them starts from it.

**Consolidation.** Lessons join the standing rules review (6.21). Merging duplicates comes in phase L-core, and the
unused list in phase L-more:
- merging duplicates when a proposal is made (above);
- a list of active entries that matched nothing for `knowledge.unused_days` (default 60), offered for retirement.

The scheduled review comes in phase E. It promotes a lesson whose guard is mechanical into a rule with a deterministic check, a
setting, or a lint the product already has. A guard that needs new code becomes a report to the maintainers (6.13), because the
product never changes its own code. The lesson stays as the record of why.

**Proving it** (the phase L exit test, then real use):
- **Automated, with no AI cost (the plumbing):** a correction produces the proposal, the proposal reaches the next similar
  packet, ranked as designed, and the run's knowledge log shows it. Run on every change.
- **On the person's own AI accounts (the behavior), in `cockpit evaluate`, and with every switch of a tier's account or
  model:** pairs of fictional fixtures, at least one per kind
  (a lesson, a glossary term, a routing entry, a style note, and a fact that avoids an outside lookup). Each pair is:
  - (a) an input, the wrong output, the correction and the expected proposal;
  - (b) a later, similar input that must come out right with no correction repeated.

  Plus one **day 1 versus day 30** scenario: the same input against an empty workspace and against one with a month of
  fictional history. The expected changesets must differ in the ways the history justifies.

  They cost money, so the person starts them, but they are offered at the moment that matters. A switch of a tier's
  account or model shows "Switch and check (about $X)" as its primary action, and "Switch without checking" in its menu. The
  check is part of the new account's probation (6.16). A pair that fails flags the switch on Today, with Switch back. A
  provider switch is exactly when learning can be lost silently. A fallback is a switch too (6.16).
- **On real use, from the end of phase L:** fixtures prove the plumbing, but the loop shows only as real material
  accumulates. The owner's daily use starts as soon as phase L is done, while the UI and packs are built. Through the first
  month, two numbers are watched weekly: the repeat-correction rate, which should fall, and the knowledge-used rate, which
  should rise (6.20).

**Reading what arrives.** An assistant can't learn from what it can't read, and for an everyday user most facts arrive in
mail attachments. So the text extractors (6.2) come with this slice. Reading a screenshot needs an account whose model reads
images, which is a capability of the account (6.16), not an extractor.

**Protecting it.** Once the assistant learns, the knowledge is the most valuable part of the workspace and the part that can't
be rebuilt. Losing a month of lessons is losing the product. So this slice also brings:
- encryption for backups that leave the person's control (4.15);
- showing and restoring one record as it was at a past time (5.0).

Both land before the owner's real use (phase D).

The knowledge records are in 5.1, the packet layout in 6.6, the signal in 6.20, the settings in 4.25, and the screens in
7.18.

## 6.23 Dependencies and baselines

**Provided by the project management pack (9.10).** Dependencies and baselines now belong to the project management pack, an add-on,
not to the core (decisions, 2026-10-12, "A project management pack: an AI project manager that builds schedules and tracks the
work"). The core keeps actions, questions, follow-ups, decisions and Today. The pack adds the plan, the schedule with
durations, dependencies, a critical path, baselines and slips (only the person rebaselines), plans and schedules the assistant
drafts for the person to approve, and an interface (`pm/schedule@1`) through which the writing and publishing packs put their
milestones into one schedule; each pack still works alone. The design below is kept as the pack's starting point; the
`Dependency` record and the `milestone.rebaseline` op are the pack's, and nothing here is built in the core.

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

**Provided by the project management pack (9.10).** RAID, risk reviews, escalation suggestions, communications cadence and meeting
agendas are provided by the project management pack, an add-on (decisions, 2026-10-12, "A project management pack…"), with its
settings in the pack's own file (4.20). The core keeps actions, questions, follow-ups, decisions and Today; a question
unanswered for a while is a nudge on Today today (6.15). The design below is kept as the pack's starting point and is not built
in the core.

Support for running projects, kept light and switchable (`config/raid.yaml`, 4.20). The cockpit keeps these current from
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
path for the launch?", "which contributors haven't replied this week?", "draft a risk review") or about the app ("how do I
change how often mail is read?") from an Ask box. The ask answers **from quoted material only** (decisions, 2026-10-10, "The
core is complete on its own…", and 2026-10-11, "Asking the assistant answers from quoted material only").

- **An ask is a core request of kind `ask`** (4.8), started from the Ask box (`POST /api/ask`) with the PM's question as its
  note, so it is trusted as the PM's own words. The worker processes it like any request, on the tier `ai.tasks.ask` or the
  `write` role gives it.
- **Ask has the knowledge section** (*designed, phase L-more*, 6.22). "Who decides this?", "what does this acronym mean here?"
  and "what did we agree about X?" are exactly what the glossary, routing, rules and facts answer. So the ask packet carries
  the knowledge section like any other. The citation check is the same: an answer citing a knowledge entry quotes it.
  Otherwise Ask would be the one place the assistant is as smart on day 100 as on day 1.
- **What the person says in Ask is learned** (*designed, phase L-more*, 6.22). A rule or fact stated in a question ("from now on…",
  "she's the one who decides that") becomes a proposal beside the answer. It applies at once, as the person's own words, with
  the read-back and Undo.
- **Its packet holds only what an answer may quote:**
  - the sections of the **user guide** that share the most words with the question (up to four; a section's title counts
    double; the overview when nothing matches), plus the help files add-ons ship (`provides.help`). The guide
    (`engine/guide/guide.md`) is the only source for how the app works;
  - the **settings**, one line each: key, current value, default, whether the person can change it, is locked or is changed in
    a file, and what it does. Nothing says where a key comes from, and keys that name a credential are left out;
  - **what this install can do:** each add-on's kinds of AI work, actions, screens, setup steps and item types, or why it is
    off;
  - the **records** the question concerns and the open items, like any other run. Text in records came from inputs and is
    material, never instructions.
- **The answer is an `answer` op** (an `answer` record). Its `cites` are the exact words the answer rests on, and each must
  appear in that material (whitespace and quote marks aside), the same check as evidence (6.7). A made-up button, setting or
  feature can't be cited, so it is refused; when the material doesn't answer, the answer says so and cites the closest words.
  Links back to the records it used are shown beside it.
- **A setting the person can change** comes as a `setting.propose` op (a `setting_proposal`): the key, the new value and why.
  Nothing changes until the person applies it, with one click, through the same settings save as any change (the files'
  fingerprint, validation, the record of the change, 4.22), so it can be undone. A locked key, or one changed only in a file, is
  never proposed; the answer says where it is changed instead.
- **Something the product can't do** comes as a `report.draft` op (a `report`) to the maintainers, written without names from
  the records, which the person reviews and sends themselves (6.13). The product never changes its own code.
- **Changes** the question asks for (a new action, a decision, a note) come as ops in a changeset under the usual tiers and
  checks (6.7), with the ops reading notes uses; a draft for someone else waits for approval like any other. Plugins' ops are
  not offered to asks.
- **A question handed in as a note becomes an ask.** When the person's own note, with nothing pasted, is a question to the
  assistant, the notes run answers `"ask": true` with no ops, and the same request becomes an ask. Only a trusted request
  with no source qualifies; pasted or outside material never turns into an ask.
- With no account set up, the stand-in answers by quoting the first guide passage chosen for the question (7.8).
- An ask that comes up again and again is a signal (6.20): it may deserve a Today line, a panel or a playbook entry.

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

## 6.27 Sign-ins to services

Some services (a mailbox, a calendar) let a person in only through their own sign-in page. The core runs that for plugins, so no
plugin handles a password or a refresh token (decisions, 2026-10-11, "Mail and calendar from named services are plugins in a
private repository; the core signs in"). The mechanism is generic: an add-on declares a sign-in (`registrar.sign_in`, listed in
`provides.sign_ins`) and the core does the rest. Core code names no service.

- **What an add-on declares:** the addresses of the service's sign-in page and token endpoint (HTTPS, on hosts in
  `requires.network`), the scopes it asks for, what the person is asked to allow in plain words (shown before they leave the
  app), the names of its declared secrets that hold the app registration, a way to name the signed-in account, an address where
  signing out withdraws access, optionally its own app registration (below), and the sources to start (below).
- **The flow** is OAuth 2.0 authorization code with PKCE, the flow for apps on a person's computer. The person starts it from the
  Sign-ins row, or from the setup step the core adds for each sign-in. The core makes a one-time `state` and a PKCE verifier,
  kept in memory for ten minutes, and gives the screen the service's page. The service sends the person back to
  `<server.public_url, else http://host:port><base_path>/api/sign-ins/callback`, built from settings (4.13), so it works under a
  nested base path; the app registration must allow exactly that address (the Sign-ins row shows it).
- **The callback is served without the app's cookie.** The person arrives from the service's page, and a browser may leave a
  strict cookie off such a navigation. It is safe because the route does nothing without a `state` this app issued, unexpired
  and unused, which PKCE ties to the verifier. It answers with a page that takes the person back into the app from the app's
  own address, where the cookie is sent. When the service refuses, its error code and description are kept and shown as text,
  never as markup.
- **Tokens stay on this computer**, in the workspace's private folder beside the plugin's other kept secrets, readable by their
  owner only (4.24); never in a settings file, the export or the synced folder. The plugin never sees the refresh token. Its
  connector asks the core for a current access token (`context.access_token(name)`); the core renews it when it is about to run
  out. A sign-in that can't be renewed reads as an `auth` failure, so the person is asked to sign in again. When the service
  refuses a renewal, the row says "Sign in again" at once and later reads get `auth` without asking the service again; a
  service that is down or out of reach is not a refusal and the sign-in stands. Signing out withdraws the access at the service
  when it offers a way (RFC 7009, best effort) and forgets the tokens. The row shows the scopes asked for that the service did
  not grant.
- **Whose app registration is used**, in this order (decisions, 2026-10-11, "Signing in needs no app registration from the
  person"; the id and its secret always come from the same place):
  1. **the workspace's**: references in `workspace.plugins.secrets` (4.1). A hosted app uses these;
  2. **the person's own**, pasted on the Sign-ins row beside a numbered list of steps with links that the add-on supplies. It is
     kept on this computer (local mode only), changing it starts the sign-in over (the service ties tokens to the
     registration), and it can be set aside and brought back. No settings file or environment variable to edit;
  3. **the add-on's own default**, so the person only signs in. An add-on ships one only for a registration the service issues
     to apps on a person's computer, and says what using it means. It allows certain callback addresses (loopback addresses
     match on any port); at any other address (another base path, a hosted app) the person is asked for their own, with the
     reason.
- **Signing in is the whole setup** (decisions, 2026-10-12). The add-on lists the sources its sign-in starts (the inbox, the
  main calendar), each with its connector, label, settings and interval. As soon as the person signs in, the core adds them to
  `watch.sources` (4.5) **once per sign-in, and only where the workspace reads nothing with that connector yet**, with
  `first_run: recent` (6.4). A mail source with nothing chosen reads the inbox, so nothing has to be chosen first. The person
  narrows, adds or removes sources afterwards, and their changes and removals stand. Which sign-ins have had their sources
  started is kept on this computer; a sign-in made before its add-on declared any gets them at the next start.
- **"Not reading".** If the person later removed the sources, the Sign-ins row says what it is not reading and offers **Start
  reading**, which adds them again with one click.

## 6.28 Live updates

The app tells open screens when something changed, so they refresh without the person asking (`GET /api/events`, a stream of
server-sent events). A change counter is bumped after any write the app makes, whether from a screen, the worker, a source
read, a backup or a restart request. Each `changed` event carries the new version and **the record kinds written since the
previous event**, read from the ledger: `{"version": 12, "kinds": ["person", "request"]}`. A screen then refreshes only the
queries those kinds affect. A change that wrote no records (a setting, a source's status) names none, and the screen refreshes
everything; a bare number from an older server reads the same way. A keep-alive line is sent every 15 seconds, and the stream
ends when the app closes.

## 6.29 Add-ons: catalog feeds and one-click install

(3.11 describes the screen; this is the engine.)

- **Feeds.** A feed is one index file (YAML or JSON, at most 2 MB, at most 200 entries) at an https address. The engine reads
  the maintainers' feed shipped with the build, unless `workspace.plugins.catalog.shipped_feed` is off, and the workspace's
  own `feeds`; and only when the person opens Available (when the kept copy is older than `refresh_hours`) or presses Refresh.
  The copy is kept in the workspace's private folder for offline use, and a feed that can't be read falls back to it, with the
  reason. Everything in a feed is untrusted: text stays text, links are https only, and nothing in it becomes a rule, a
  setting or an instruction. An entry that doesn't fit the format is left out with a note; the rest of the feed still shows.
- **An entry** has an id, name, one-line summary, publisher, whether the maintainers made it, when it was updated, its version,
  the `plugin_api` range it works with (checked against the running version), a price as the publisher states it, a homepage,
  how to get it, whether it can be tried in the demo, its typical AI jobs, its manifest's `provides` and `requires` copied
  exactly, and, to be installable here, a **`release`**: an https address of a release file and its SHA-256 checksum.
- **What it adds, reaches and keeps** is written by the core from the manifest (never from the pack's own description): counts
  and names of item types, screens, Today lines, kinds of AI work, actions, setup steps and sources it adds; the sign-ins,
  hosts, programs and secrets it reaches; and the most private data level it uses. **What its AI work costs here** is each
  typical job priced on the person's own accounts for its role (the price when the model's prices are known, else only the
  size of the work, or "no account is set up for this work").
- **Install** (decisions, 2026-10-11, "One-click install for add-ons comes before the freeze"; local mode only; a hosted app's
  add-ons come with its deployment): `POST /api/packs/{id}/install` downloads the release file from the entry's address
  (https, at most 50 MB), checks it against the entry's checksum **before touching anything**, and installs it beside the app.
  A private pack's release host takes a read token the person gives once, kept as a secret reference
  (`workspace.plugins.catalog.release_tokens`, by host name); it is sent only to that host and never on a redirect to another.
  Only a wheel of pure Python whose needs the app already has (each requirement present at an allowed version) is installed
  this way; anything else is refused with what to do instead. Installing a pack's own libraries is planned (roadmap, A2).
  Paths outside the install place are refused. An earlier install of the same pack is replaced only if it was installed from
  here (the install marks its metadata).
- **Update** is the same call. **Remove** (`POST /api/packs/{id}/uninstall`) takes away only the files an install from here
  recorded, and only once the pack is turned off; its records and settings stay.
- **Installing never turns a pack on.** Turn on is a separate step (`POST /api/packs/{name}/on`, with Undo), and the app uses
  the pack after the restart the person chooses (6.14). The app never handles payment.

## 6.30 Record pages and table counts

The core draws a page for any record it holds, its own types and a plugin's, and the counts beside each row of the Projects and
People tables (7.14). `engine/record_page.py` only reads; nothing calls AI. For a record it gives:
- its **name**, taken from the record (full name, name, title or text), never its id;
- its **details**: the fields its type declares, in the order it declares them, leaving out empty values, long text, aliases and
  the core's own `id`, `stage` and `ext`; each with a type the screen uses to show it (date, number, yes or no, choice, list,
  map or text), and every reference resolved to the referred record's name and a link;
- what is **still open with it**: for a person, the open actions they own and the open questions to them; for a project, those
  in the project; for an organization, those of its people;
- what **happened to it**, newest first: the ledger's entries for it and for what is open with it, one entry per record and
  change (not per field written), whether the assistant or the person did it, at most the latest 60.
For the tables, `counts` gives per person the open items with them and when they were last contacted (the latest day an action
was told or a question sent), and per project its open actions, open questions and when it last changed.

## 6.31 Value lists

(5.4 says what a list is and 4.23 why it is not config; this is how the engine keeps them.)
- **Created when a workspace opens.** For every list the core ships (`engine/defaults/value_lists.yaml`) and every list a
  running plugin declares, a workspace that lacks it gets a `value_list` record with the first values plus any value its
  records already hold, so nothing that was valid becomes invalid. After that the list is the person's.
- **Changed only by its three ops** (`list.add`, `list.rename`, `list.retire`), each a system op with Undo and each in the
  ledger. A rename writes the list first and then every record that holds the value, in the same transaction.
- **Enforced where records are written,** not on a screen: the storage layer refuses an off-list value from any writer, naming
  the list's values, and lets a record keep a value that was retired after it was set.
- **Seen by the assistant:** a packet lists the values each list-bound field takes (6.6), so a proposal names a real value.
  Adding a value is a deliberate act ("Add to the list"), never a side effect of writing a new value; the assistant may only
  propose it, as a system op that waits for the person.
