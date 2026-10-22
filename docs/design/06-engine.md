# Part 6. Core engine components

Each component is generic, configured from Part 4, and has its own tests with fictional fixtures.

**Status.** A section or paragraph marked *designed, not yet built* is in the design baseline and has no code yet; the
roadmap (`docs/project/roadmap-to-1.0.md`) says when it is due. Where the code and a section differ, the code and the decisions
are right and the section is a gap. Sections 6.8 to 6.11 were written for the first design. They are where most corrections happen (drops, rewords, reroutes, reassignments), so the
learning loop's signals come from them; they were audited against the code in phase L-core (L0), and what the audit found
unbuilt is marked *designed* with its phase in each of them (checked by reading).

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
(marked test-only: Add a connection doesn't offer it, and a source already set up with it still reads) (decisions, 2026-10-11, "Calendars and mail are read through open protocols in the core…"). Pasting and uploading are ways to
hand something in (6.6), not connectors. Connectors for particular products and services (wikis, trackers, a named mail or
calendar service that needs its own sign-in) are plugins (6.27).

**Structured items.** A calendar or mail item carries what it is as structured fields beside its text: an event's start, end,
place and whether it was cancelled; a message's sender, received time and whether it is unread. The watcher keeps them on the
item's snapshot, so the agenda and the list of what came in on Today need no AI call (6.15); the text still carries everything
the assistant reads.

**Calendars from .ics.** The `calendar` connector reads a published link or, in an app on the person's own computer, a file picked
from a list (a path setting, never typed; a hosted app refuses a file plainly and asks for the link). A file is read again each time
the source is read, so a change in it is a change in the source. A repeating event is one item for its series with every date in
`expand_days` (default 60) listed on it, expanded by `engine/recurrence.py`; a repeat rule the engine doesn't support shows the
first date with a note, never nothing. A time zone written as a Windows name is read through the shipped list
(`engine/defaults/windows_zones.yaml`); a zone nobody knows, or a time with none, is read in the calendar's own zone, else the
person's, with a note. Each date is kept as a calendar entry by rules (`engine/source_entries.py`; no AI, and nothing is written
to the calendar): its place, who organizes it and who is asked (each resolved to a person by address, with their answer), whether it
came as an invitation (the calendar sent it as a request, or its organizer isn't the person) and the person's own answer. A
repeating event's entries are one series. A moved date moves only its own entry, and a promise due at it follows (6.33); a date
called off, or skipped by its series, marks only its entry and gives a promise due at it one news line, its date unchanged. The
agenda lists each date once and links its entry, whose page lists the people asked.
**A plain entry needs no AI run** (the functional designer's F20, 2026-10-20; batch B-7; `engine/entry_rules.py`). An entry
with nobody else invited, no description (`EventDetails.described` is False; a connector that doesn't say counts as
described) and no change to a date a promise is due at is **plain**: the rules keep it in the calendar, with no run of the
assistant, no request and no Review line (`CalendarEntry.plain`). The assistant still reads an invitation from someone else,
an entry with a description, and one that moved a date a promise is due at (the promise still follows by rule). A plain entry
whose title's **first word is one of `language.task_verbs`** ("Pay the deposit") is offered as a to-do, one click in its
agenda row's menu: the person's own `action.add`, in the entry's words, on the entry (due on its day, moving with it), with
Undo (`POST /api/events/{id}/todo`, `AgendaItemView.todo_offer`). A plain entry whose title **names a known person** (their
full name, else a first name or alias only one person has; never the person themselves) is linked to them
(`CalendarEntry.people`); one that **names a promise's words**, on that promise's day, becomes the day the promise is due at
(`due_event`), so it moves with it; a promise on another day, or with none, is never linked. *Built:*
`tests/test_plain_calendar_entries.py` (a calendar fixture of each kind), `web/src/components/TodayRail.test.tsx`.
*Built so far (P17, B-5):*
`tests/test_ics_full.py` (the connector, a source's read, the entries, the agenda and the add-source routes),
`tests/test_calendar_mail.py`, `web/src/components/Sources.test.tsx` (the file picker),
`web/src/components/RecordPageRecords.test.tsx` (the people asked) and `web/src/components/TodayRail.test.tsx` (the link). Left: an
invitation attached to a mail, with Undo (P17 part 3).

**Reaching the network.** A plugin's connector reaches the network only through the core's client (decisions, 2026-10-11,
"Plugins reach the network only through the core's client…"): only hosts the manifest declares in `requires.network`, over
HTTPS (plain HTTP only on this computer), with redirects checked against the same list and answers capped in size. It gets the
secrets its manifest declares (references in `workspace.plugins.secrets`, or values it keeps on this computer, such as a
refreshed token), and a current sign-in token when it asks for one. Bundled plugins may not import network modules; the scan
enforces it.

Files are read as text by the text extractors (3.3; **built**, L5: `engine/extract/`, `tests/test_extractors.py`): the core ships extractors for documents, spreadsheets (cells and
their comments), presentations (slide text, tables and speaker notes) and PDFs, and plugins add others. Packets carry the
extracted text, so a run never asks the PM to paste what is already in a file it can read. A file type with no extractor is
flagged to the PM once, as unsupported, not request by request. *As built:* documents, spreadsheets and presentations are
read from their zipped XML with the standard library and PDFs with `pypdf`; a file that can't be read gives a reason,
never empty text; the text is cut at `storage.files.read_max_chars` with a mark, and a file over `read_max_mb` is named as
not read. A connector's item carries files (`ItemFile`) and the core appends each one's text to the item, inside its
outside-content block. Each core reader checks itself at startup on a generated file; a failing reader, or a real file
it couldn't read, is a Today line that clears when a later file of that kind reads. An unsupported type is one question
to the person, which they can drop, filed once per media type (not a Today line: the person has nothing to do).

## 6.3 Channels (outputs)

The interface in 3.3. A channel describes its capabilities: versioned targets with a concurrency check, pulling others' edits
back, scheduled sending, length limits, media. The core ships the clipboard channel (the PM copies the approved text and pastes
it anywhere), the **file channel** (the approved content is written to a configured folder, in whatever format a renderer
produced: text, a document, a PDF, an ebook; with a synced folder, by default the project's `outputs/` folder, 5.0) and the fake channel. Wiki pages, email, blogs and social networks are plugins. A **notification target** (7.19, phase B)
is a channel of its own kind: mail to the person themselves, or a webhook. It sends only to the person, and only the "needs
you" items, so it needs no per-message approval.
Channels are called only by the publisher (6.12). The publisher, the file channel and the clipboard channel as channels are
*designed, not yet built*; the person copies approved text from the review today. **Mail and calendar acts** (owner,
2026-10-17) are channels too: a connected account's service, through its add-on, or a plain mailbox's outgoing server,
sending, replying, forwarding, archiving, moving, labeling and marking read, and creating, moving, cancelling, accepting,
declining or proposing a time for calendar events; each act is one outbound op the person approves exactly. They and the
publisher come in phase S1b; the file channel stays in phase C4.

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
- `intake` (the default): the first read is taken in quietly (6.32): the last `first_run_days` of mail and everything else
  the source holds is handed in together, priced as one total, and left as one list to look over.
- `baseline`: the first read only notes what is there.
- `recent`: it also hands in what arrived, changed or happens within `first_run_hours` of the read (24 by default): the last
  day's mail, today's meetings. A message counts by when it was received, an event by when it starts (before or after now),
  anything else by when it changed.
- `all`: everything there is is handed in as new.
- **On request**, after a first read that only noted what was there, the person can hand in the recent items from the
  Connections screen ("Look at the last day"). The core hands in the items already read, in the same window, that haven't been
  handed in, as if the source had been set to `recent`; triage rules apply as for any change.

**Sources a sign-in starts** (6.27). Signing in to a service starts the sources its add-on declares (the inbox, the main
calendar), with `first_run: intake` (6.32), so the first read is one total, one go and one "Look over what was found"
line, not a review line for each item. *Built so far (S1-3):* `tests/test_sign_in_sources.py`.

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
proof that learning never reads it are phase L0, **built**, `tests/test_mail_sorting.py`). Mail that isn't work goes into a **Set aside** folder in the app, in two
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
before. It also carries `participants`, everyone else on the message (to and cc, each as `Name <address>` when the service gives
the address), from the add-on (plugin API 0.3.58, optional, empty by default) or, for the core's own mail folder, from the To and
Cc headers; the snapshot keeps it. It lets a first name in the text mean the person on the message (6.11).

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
3. **The assistant's sorting**, for mail the rules can't place (`watch.sorting: ai`, on by default, chosen with a switch in
   the walkthrough's Mail step, "Let the assistant sort what the rules can't"; `rules` makes no run). **Built,**
   `tests/test_mail_sorting.py`:
   - a small low-cost run sees **only the sender, the subject line and the service's category**, never the body, the thread
     or an attachment. Each message is an opaque id (`m1`, `m2`, ...) with those three things, marked as outside content,
     in a batch that comes last in the packet after the instructions and the playbook's practice (6.6);
   - it answers work, personal or sales for each id. **Unsure means work**: a message the answer leaves out, or answers with
     another word, counts as work, so nothing is hidden on a guess;
   - one run covers a batch of headers, not one per message: the mail of a read that no rule placed goes in groups of
     `watch.sorting_batch` (25), one run each, after the rules and before anything is handed in. Only new mail is sorted
     (a message that changes keeps what the assistant decided; one the person's "never" rule keeps is never sent);
   - **the answer is checked deterministically:** it must be readable and complete JSON, name no id that isn't in the batch
     and answer no id twice. A failing answer goes back once with what was wrong (`dispatch.fix_rounds`), then is tried once
     on the tier's escalation tier when that run's estimate is within the caps (6.16); after that every message in the
     batch counts as work;
   - **where items wait:** an item isn't written or handed in until its batch has its answer, so a sorted message is set
     aside from the start and never queued for the assistant. Personal and sales answers set it aside with the reason "the
     assistant sorted it as personal mail" or "... sales mail" and `by: assistant`, shown in the Set aside folder; "This is
     work" and the sorting rules from a correction work exactly as for mail a rule set aside. "Look at the last day" sorts
     the mail a first read only noted in the same way;
   - **cost is the person's choice, as for any run (6.16):** the run is the task kind `sort-mail`, role `write`, at the
     `routine` tier unless `ai.tasks.sort-mail.tier` says otherwise, with its own entry for a budget (`ai.budgets.per_task`).
     It is estimated first and goes through the per-run limit, the first go, the amount to ask above and the day, month and
     per-kind budgets. It is made for no request, so its run record has no request (`Run.request` is none). When it can't be made (no
     account for the tier, a budget used up, the first go or the go above the configured amount not given, an account
     paused or failing, a refusal) **the mail is handed in as work, never held back**, and the read says why in plain
     words. The same cause stops the handed-in requests themselves on the paths that already show it (a request needing an
     account or a budget waits for the person, an account at its limit is a paused line, the first go is its line);
   - **The first go covers it:** before the person's first go in a workspace the run isn't made, so the mail of the
     first read is handed in as work and waits with every other run. When the person gives the first go, the mail
     requests still waiting for it (or queued) whose message was never sorted go through the sorting run first, in
     the same batches and under the same limits, the go covering the checks that wait for a go. Personal and sales
     answers set the message aside (its request is closed as set aside) and only the rest run. Mail the person
     pulled back as work, mail a rule now places or keeps, and changed messages are left alone;
   - **nothing from it is learned:** a set-aside request and snapshot carry the `set_aside` mark that
     `engine.set_aside.learnable` leaves out, so no signal, fact, lesson or evaluation case comes from them (above).

**Correcting it** (all built):
- **Any item in Came in or What changed that is a mail message** has "Set aside: personal" and "Set aside: sales" in its menu.
  The message moves to the folder at once, and a request of it that hasn't started (queued, or stopped for the person) is
  closed, remembering where it was. Undo puts both back. What the person set aside by hand stays set aside if the message
  changes. Each records a `set_aside` signal (6.20; undo records none). Learning (6.22) reads requests and snapshots only through
  `engine.set_aside.learnable`, which leaves out anything marked set aside, so mail the person set aside is never taught from.
- **Any set-aside item** has "This is work", which hands it in after all (a request set aside by a rule is queued; one the
  person had set aside goes back where it was; a message that was never handed in is handed in now) and records a `pulled_back`
  signal (6.20). It shows in Today's Came in again. Undo sets it aside again.
- **Each correction offers** "Always for this sender" and "Always for this domain": a sorting rule written through the settings
  save path as the person's own change, with a read-back toast and Undo. After "This is work" they are rules to keep the
  mail; after "Set aside" they are rules to set it aside in that section. Settings under `watch.` apply at once. The domain
  rule is never offered for a **public mail domain** (the free mail services anyone has an address at): the folder's rows, the
  answer to "This is work" and "Set aside", and Confirm all carry no domain for one, however many senders share it, and the
  save that writes a domain rule refuses it in plain words, so a screen that is out of date can't write one. The core ships
  the list (`engine/defaults/public_mail_domains.yaml`, exact match, case ignored: a subdomain isn't listed by its parent) and
  `watch.public_mail_domains_extra` adds the person's own; both apply at once. A rule for the sender is still offered.
- **Confirm** (each row's menu, and "Confirm all" for a section): the person says the mail was rightly set aside. The app
  *learns* a sender rule for each distinct sender, in the message's section, in one save with one read-back ("From now on, mail
  from a@example.com is set aside as sales") and one Undo; when three or more confirmed senders share a domain, the toast
  also offers "Always for example.com" (never for a public mail domain). These are sorting rules and nothing else is learned from the mail. The app also
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

**On screen:** the folder is a section of Connections beside Auto-closed, one row per message (subject, sender, date, why it was
set aside), grouped into Personal and Sales and promotions. Today never lists set-aside mail; Came in shows a count ("6 set
aside") that opens the folder and counts what the folder lists, so a confirmed message is no longer in it. Set-aside mail is kept like other sources and follows retention (5.2).

**A note typed on a button is an input** (phase L0, **built**). Anything the person types that could change the work reaches the
assistant. A note typed with Mark done, They finished it, Followed up, the choice of an owner, an answer to a question, or
added to an action's notes is handed in by one helper (`engine.intake.note_as_input`) once the button's own change is
saved. Unless it is a bare confirmation (fewer than `language.bare_confirmation_words` words, default 4, and no link; it
stays with the change), the note is saved as a **source marked trusted** (kind `note:<button>`, never wrapped as outside
material) whose projects are the item's project and whose **author** follows the button (below), and a request of
the usual notes work is queued **about the item**, under the usual cost rules (the first go, estimates, budgets). The run's
packet puts the person's note in a `<note>` block and the item beside it as data (its text, owners, due date, project,
status, notes, who did it, the days it was chased; for a question, who it went to and its answer), so the assistant
decides whether anything changes beyond the button's own change: a fact with its link, a moved date, a reopened or closed
action, a rule proposal. **Whose words a note is follows the button** (phase L1, **built**): the source's `author` is a person
id, and the packet shows the note as `<note source="..." by="<name>">`, so the assistant knows whose words it reads. Mark
done, Reopen, the choice of an owner, an answer to a question asked of the person, and text added to an action's notes
are the **person's own words**: the author is the person running the app (`workspace.user.person`), and a system op from
the note follows the person's-own-words path of 6.7, so it applies at once, with Undo. They finished it, Followed up, and
an answer recorded for a question asked of someone else (kind `note:answered_for`) are **content the person reports**: the
author is the person it is about (the person the action waits on, or the one the question went to). The source is still
trusted, so a fact or a moved date from it applies at once with Undo, as before, but it is **reported content**: the
packet adds `reported="yes"`, and a system op from it, which today covers every rule, value list and recipient, is held
for the person with the reason that someone else reported it. **Attributed words count whatever the button** (the
original designer's L1 check-in, 2026-10-14; built): a note on the person's own button that repeats someone else ("<name>
said / says / confirmed …", or a passage in quotation marks; the words are the setting `language.reported_speech`) is
reported content too. Its source is marked `reported` and its author stays the person who typed it; facts and dates from it
apply, and a system op from it is held. Built: `tests/test_note_input.py::test_a_rule_from_someone_else_repeated_in_a_mark_done_note_waits_for_the_person`.
**More reported speech, and two that aren't** (functional designer's answers, 2026-10-15; built, roadmap L7 (see roadmap-done.md)): "mentioned", "replied", "responded",
"noted", "commented" and "pinged" join the speech words (`language.reported_speech.verbs`), and "per" and "according to"
(`lead_words`, which come before the speaker, who starts with a capital letter) mark reported speech too; a pasted chat
is reported content as a whole (lines of a time and a name, `chat_line_patterns`, at least `chat_min_lines` of them; a
screenshot of one is not read). "I told <name> …" is the person's own report of what they did, and "<name> asked me to …"
is a request to the person (an action, `request_words`), never a rule; neither counts as reported content. Built:
`tests/test_note_input.py::test_a_pasted_chat_is_reported_as_a_whole`. Knowledge proposals (lessons, glossary entries, routing
entries, style notes, rules) are system-tier ops when they are added (L1), so they wait for Keep and are never active at
once from reported content; the learning pair that proves it is added in L4. **Undo** of the button's change does not
take the input back: the words stay saved and the queued work stays; what the assistant makes of it is a changeset the
person reviews and undoes on its own. An edit of an action's notes hands in only what was added after the old text. A
refused or conflicting change hands in nothing. Every other route that takes free text is declared in one place
(`api/free_text.py`) as `to_assistant` or `local_only` with a reason, and the self-check (`engine.selfcheck.free_text`)
fails for a route whose request has free text and no declaration. **Built:** `tests/test_note_input.py::test_a_note_under_four_words_with_no_link_makes_no_request`, `tests/test_note_input.py::test_a_short_note_with_a_link_makes_a_request`, `tests/test_note_input.py::test_mark_done_with_a_note_makes_one_request_about_the_action`, `tests/test_note_input.py::test_they_finished_it_with_a_note_makes_one_request_and_the_note_survives_the_undo`, `tests/test_note_input.py::test_followed_up_with_a_note_makes_one_request_and_without_a_body_none`, `tests/test_note_input.py::test_picking_an_owner_with_a_note_makes_one_request_about_the_action`, `tests/test_note_input.py::test_adding_to_an_actions_notes_hands_in_only_what_was_added`, `tests/test_note_input.py::test_answering_a_question_in_words_makes_one_request_about_the_question`, `tests/test_note_input.py::test_a_notes_source_is_authored_and_trusted_by_the_button` (every button), `tests/test_note_input.py::test_the_packet_names_whose_words_a_note_is_and_marks_reported_content`, `tests/test_note_input.py::test_a_they_finished_it_note_saying_from_now_on_we_always_copy_the_client_on_approvals_is_never_active`, `tests/test_note_input.py::test_a_mark_done_notes_system_op_applies_at_once_with_undo`, `tests/test_note_input.py::test_a_change_to_how_the_product_behaves_from_a_reported_note_waits_for_the_person`, `tests/test_note_input.py::test_the_packet_carries_the_item_and_the_note_as_the_persons_own_words`, `tests/test_note_input.py::test_a_note_with_a_link_and_a_new_date_comes_back_as_a_fact_and_a_moved_date_the_person_can_trust`, `tests/test_free_text_check.py::test_a_route_with_free_text_that_is_neither_wired_nor_declared_fails_the_check`, `tests/test_free_text_check.py::test_the_apis_routes_with_free_text_are_all_declared`, and the golden case `workspaces/demo-b/evals/they-finished-note.yaml` (run by `tests/test_followups_backup_eval.py::test_every_case_passes_with_its_ideal_answer`). *Not built:* the note box on the screens' buttons (phase B); today the API takes the note and the screens send none.

## 6.6 Dispatcher

**As built.** The packet holds, stable parts first and the request last: the instructions, the op reference for the task kind,
the task's playbook guidance, every open action and open question in a compact form, the people, the projects, the values each
list-bound field takes (5.4), then the date and the day the input was received, the PM's note (trusted) and the cleaned input (untrusted). Input cleaning, one input
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
    whose target matches, the glossary (all of it while small), routing for the people and projects in the input or
    whose topic the input is about (it shares `knowledge.routing_match` of the topic's words, plurals and hyphens
    folded), and style notes for the recipient of an outward draft;
  - the facts of the projects the input touches, ranked (key facts, overlap with the input, newest) and cut at a budget, with
    what was left out said (6.22);
  - the area each related person and item is in, with each domain's contact (6.18), and looked-up facts (6.19);
  - which recent edits and pages were made by `our_accounts` ("published by the cockpit", so nobody is asked who made them);
  - the op reference (core and enabled plugins' ops) and how to ask for a search (6.22).
  A plugin's AI task kind builds its own packet with the same parts available.
- **Trusted and untrusted parts** (12.2): the PM's own note (including a note typed on a button, saved as a trusted source and
  shown in a `<note>` block beside the action or question it was typed on, 6.5), config-derived context, rules, playbooks and the op reference are
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
  (**built**, phase L0: `tests/test_names.py::test_the_packet_states_the_inputs_received_date_beside_todays`), and the input last. Most providers discount or cache a repeated prefix, and only an identical one: so each layer is serialized in a
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

**Text stays text.** Every field of an op that holds text is a string, and a mapping or a list that arrives where text
belongs is refused in plain words, never turned into a string: "action.text has to be text, but it arrived as a mapping of
names to values. A ': ' inside text makes it read as a mapping, so put text with ': ' in quotes." The usual cause is a
title with a colon and a space in it, read as structured data. The answer itself is JSON and is never read as YAML. A
field an op declares as text sends the whole answer back for a fix round with those words
(`tests/test_text_shape.py::test_a_declared_text_field_given_a_mapping_sends_the_whole_answer_back_with_the_same_words`);
the loosely typed ones are checked against the target record model's field type at the applier, and the op is refused
alone: `record.set`'s value (`::test_an_answer_that_sets_an_actions_text_to_a_mapping_is_refused_and_the_text_is_left_alone`),
`record.edit`'s fields, a plugin's record included (`::test_a_list_for_a_person_edit_of_a_records_text_field_is_refused`),
and `setting.propose`'s value for a text setting or a list of text
(`::test_a_suggested_setting_that_holds_text_is_refused_for_a_mapping_and_a_list_of_text_for_a_mapping_item`). Every
record write is checked the same way whoever makes it (`::test_a_record_written_with_a_mapping_in_a_text_field_is_refused_for_any_writer`),
and an organization's name is never made by turning a value into text
(`::test_an_organization_that_is_not_text_is_never_turned_into_a_name`). Golden cases: a title with a colon
(`workspaces/demo-b/evals/colon-in-title.yaml`) and one with commas (`commas-in-title.yaml`) stay one value.

**Dates and times in the assistant's own words.** An input's text often carries machine timestamps (a date-time with its
zone, as an add-on writes a meeting's time), and the assistant copies them into what it writes. Before an assistant's changeset
is kept, each such timestamp in the prose of its ops (a note's, fact's, action's or question's text, an entry's title, an
answer) is rewritten in the person's time zone (`workspace.user.timezone`) and format (`language.messages.date_time_format`).
Evidence quotes, dates a field holds (`due`, an entry's `start`) and times with no zone are left as they are. **Built:**
`tests/test_moments.py::test_a_filed_note_shows_the_time_in_the_persons_format_and_the_evidence_keeps_the_inputs_words`.

**Drafts are not claims.** Some work is writing, not extracting: a proposal, a statement of work, a status update, a blurb.
A draft has no quote to cite, so it is not held to the evidence rule; instead it is written only into a `long_text` field
(5.0) through a `text.draft` op, marked as written by the assistant, and shown as **not yet reviewed** until the person
approves it. Factual statements inside a draft that the task kind declares checkable (a date, a price, a regulation, a
research finding) still need evidence, listed beside the draft. A task kind says which it produces: ops (extraction) or a
draft.

**Person-owned fields.** A record type can mark fields that only the person sets (a project's priority or capacity): an op
from the assistant that sets one is held for the person, who releases it or leaves it (a person-only declaration with no values
means every value of the field; a project's priority is one, **built:** `tests/test_projects_series.py::test_the_assistant_never_sets_a_projects_priority_but_the_person_does`). `project.add` adds a project as a row of the portfolio (name,
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

**Handing an action over.** The person can hand an open action to the assistant from its row (7.5): one `action-work` request,
a core draft task kind (`output: draft`, the action's `work` long text, its prompt in `prompts/action-work.md` and its playbook
entry), queued as the person's own request and so estimated and held for the go above the configured amount like any run. The
answer is a pending draft on the action; nothing else about the action changes, and it stays the person's until they close
it. A second hand-over is refused while a request or a draft is waiting. Taking the draft as it is corrects nothing; keeping
part of it records a `draft_edited` signal with the text as kept, and discarding it, or rejecting every change, a `dropped`
signal, each naming the action, the changeset and the run (6.22). The run reads the knowledge that applies and writes its
knowledge log like every kind. **Built:** `tests/test_action_work.py`, `tests/test_action_work_api.py`. *Not built:* an
evaluation case for the kind: the golden set, learning pairs and replays all start from a handed-in input or the person's
correction, so a draft kind needs a harness step first.

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
friction and the injection risk isn't there. (Built: the tier decides, and a system op from anyone but the PM is held. A
note typed on a button is the PM's own words on Mark done, Reopen, the choice of an owner, an answer to a question asked
of the PM and an addition to an action's notes; it is content the PM reports, so a system op from it is held, on They
finished it, Followed up and an answer recorded for a question asked of someone else (6.5). The
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
- `action.reply`, person-only with Undo: approve the reply the assistant drafted for an action as it is, or replace it with
  the person's own words; either marks it reviewed (6.8).
- The person's corrections of a question (6.8), each person-only with Undo and each, but `question.mark_sent`, recording a
  signal (6.20): `question.update` (reword), `question.move` (ask someone else), `question.drop` (with a reason) and
  `question.mark_sent` (the person sent it themselves).
- Value lists: `list.add`, `list.rename`, `list.merge` (every record moves from one value to another and the first leaves
  the list), `list.retire` (system tier, each with Undo, 5.4).
- Mail: `mail.restore` (a set-aside message leaves the folder and is read; system tier, so the assistant may propose it and
  the person confirms; Undo sets it aside again, 6.5).
- What the assistant learned (6.22): `lesson.add`, `lesson.update`, `glossary.add`, `glossary.update`, `routing.add`,
  `style.add` and `knowledge.retire` (system tier, each with Undo). An add that is not from the person's own words is
  a proposal and applies as a record; the rest wait for the person like any system op. Reading notes is offered
  `glossary.add` only, so a term or system name an input uses that the glossary lacks is recorded with `confidence:
  unknown` (or assumed or confirmed, as the input supports) as a proposal, or active when the words are the person's own.
  **Built:** `tests/test_corrections.py::test_glossary_and_routing_proposals_are_offered_to_reading_notes_and_no_other_knowledge_op_is`,
  `tests/test_corrections.py::test_an_unknown_term_from_an_input_is_added_as_a_proposal_and_from_the_persons_own_note_as_active`.
- Project and stages: `project.add` (a system op: from the assistant it waits for the person) and `stage.move` (always waits
  for the person's confirmation).
- Asking (6.25): `answer`, `setting.propose`, `report.draft` (a report to the product's maintainers, drafted for the PM to
  approve and send, never a code change, 6.13).
Plugins register more, namespaced, each with its tier. Reading notes is offered every op except those that are the person's own
or only for actions and asks (deleting, `file.add`, `project.add`, `record.edit`, the long-text ops, the asking ops and
the knowledge ops, which belong to the work that learns).

*Designed, phase L-core (L3b): the obvious next step* (owner, 2026-10-13). When an input names something new, the
assistant offers the obvious way to record it, as one click the person confirms, and the answer is learned (6.22):
"Who is this?" offers "Add a new person" filled in from the input; a project it hasn't heard of becomes "Add a project
<name>?" with "It's part of <a project>" and "Not a project" (reading notes may then propose `project.add`, which waits
for the person); a date goes under its project as a calendar entry; an unknown organization is added with the person;
a signature's address or number is offered for the sender's record; an action gets the date the input gives; a reply
that answers an open question proposes marking it answered; a meeting invitation shows on the agenda under its
project.

How each is recorded (decided 2026-10-15; *being built, L3b*):
- **"Add a new person"** answers the routing question with a new person, filled in from the input (the name as written,
  the organization, role and address it gives) and saved as the person's own; held ops waiting on the name are released
  and a `routed` signal names the new person. An organization no record names is added in the same change.
- **A contact detail from a signature** (`person.contact`: the person, the kind of detail, the value, evidence) always
  waits for the person: a detail from outside content would otherwise become a way to reach someone (12.8).
- **A project it hasn't heard of:** reading notes may propose `project.add` (system tier, so it waits). The held item
  offers Add, "It's part of <a project>" and "Not a project". "Part of" files the held work under that project and keeps
  the words as a glossary entry naming it; "Not a project" keeps them as a glossary entry saying they aren't one. Both are
  the person's own answer, so the entries are active at once with Undo. Projects get no alias field.
- **A blocker gone:** `action.unhold` (the action, evidence) takes an action off hold, as data with Undo.
- **A reply that answers an open question** proposes `question.done` with the answer's words; **an action with a date**
  gets it as `due`; **a meeting invitation** is an `event.add` under its project; **the person's own edit** in a watched
  source they author that does what one of their open actions asks closes it (`action.close`) with Undo; **something the
  person says they sent without naming to whom** is a decision to the person ("Who did you send this to?"), never a
  guess from the nearest name. Each has a golden case. *As built* (F): `action.unhold`; a watched input from one of the
  person's own accounts carries `by_us="yes"` on its outside-content block (still untrusted); an `event.add` with no
  project takes the request's project, else the source's only one; the lint `unnamed-recipient` (default `return`)
  returns a question or action naming a recipient the input never gave when the input says something was already sent
  (`language.already_sent_phrases`). **Built:** `tests/test_obvious_steps_f.py`.
  *As built* (E): "Add a new person" is `POST /api/questions/{qid}/new-person` on a "Who is X?" question (not yet on
  "Pick an owner"), prefilled from a proposed `person.add` and the input's header addresses; `person.contact` waits for
  the person even from their own note, and its kinds are `workspace.contact_kinds`; "It's part of" and "Not a project"
  are `POST /api/changesets/{cs}/ops/{i}/part-of` and `/not-a-project`, each setting the held proposal aside, adding an
  active confirmed glossary entry (wording in `language.messages`) and recording `held_declined`. **Built:**
  `tests/test_next_steps.py`. *On screen (B-6a):* the held project's row has Add as its one primary action, and in its menu
  "It's part of <project>" once for each of up to three projects whose names share a word with the held one (one click files it
  there), "It's part of…" for the whole list, and "Not a project" (`web/src/components/NextSteps.test.tsx`). Today's held line
  has no inline offers: it opens the change.

`event.set` (data tier, offered to reading notes) moves an entry already in the calendar: a new `start`, a new `end` or
both, with the input's words as evidence (required), refused alone when the entry doesn't exist or the end would come
before the start, and undone like any change. A message that moves a real event uses it on the entry's id, never a second
entry. **Built:** `tests/test_event_set.py`, the golden case `moved-meeting-moves-its-entry`.

`event.add` (data tier, offered to reading notes) adds a calendar entry to the app's own calendar: a title, a start (a
day, or a date-time), an optional end (the last day or moment of a range, included), the project it belongs to, and
evidence, which is required. **Calendar entries are for real events only** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7 (see roadmap-done.md)): meetings, launches, delivery
windows, appointments. An action's due date lives on the action and never gets an entry of its own, and a new date for an
open action is one op, `record.set` on its due, with no fact and no history entry (a date-only move). The cases' check is
turned round with it: it fails an entry made for an action's own date. *As built until L7:* the notes prompt asks for an
entry whenever an input that isn't set aside names a date or a range for something, beside the fact or action, with the
same quoted words. Dates come only from the input, as for actions. An end before the start is refused alone; a start or end that isn't an
ISO day or date-time makes the answer unreadable and goes back for a fix. The entry is an `event` record (`EVT`, shown as
"calendar entry"; 5.1), made by the applier and removed by Undo like any create. It is never written to a calendar service
(owner, 2026-10-13). **Built:** `tests/test_calendar_entries.py` (op validation, refusals, create and undo, the golden case
`delivery-window`). The learning pair (a corrected date carries to the next similar mail) waits for L-core.

*Designed, not yet built* (the first design's list): data ops `record.add`, `record.del`, `record.rename`, `action.update`,
`action.assign`, `decision.add`, `milestone.add`, `risk.add`, `question.update`, `question.move`, `question.drop`,
`meeting.add`, `meeting.update`, `person.merge`, `dependency.add`, `dependency.update`, `issue.add`, `issue.update`,
`issue.resolve`, `risk.realize`, `assumption.add`, `assumption.update`, `meeting.agenda`, `parked`, `inbox`, `lookup`, `watch.item` and `doc`; outbound ops `draft.request`, `dev.request` and `handoff`
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
- **Outward material never names the assistant** (the owner's lesson from running, 2026-10-20; `engine/outward.py`): an op
  that writes what others read (the text of a shared item, a history line, a reporter or an author) and holds one of the
  names the assistant has gone by is refused, with the reason in plain words (`names-assistant`; never a lint, never
  configurable). The names are the current `workspace.assistant_name`, every earlier value in the settings history
  (`setting_change`) and the product's default, matched as whole words ignoring case, so renaming the assistant blocks the
  new name and the old one. A name that is also an ordinary word ("assistant") counts in free text only where it
  attributes something ("by Assistant", "Assistant, 10/8", "Assistant's judgment"), so "an executive assistant" stays
  writable; the sweep replaces a whole attribution phrase with its source, not only the name. A history line's source is the evidence, never the assistant: the page, mail or person and the
  day ("the Oct 14 sync notes"), the person for their own note, and for a call from several inputs those inputs or the
  person who approved it. The person's own action on their own screen is their own words and is not checked; the person's
  own screens may still say the assistant did something. The same rule guards the render for readers (6.12, 7.14), the
  send step (6.12) and a sweep: `outward.sweep` re-sources a project's history lines that name the assistant from the
  ledger's evidence (the row that wrote each line), keeping each line's date, as one change of the core's own that Undo
  takes back; it runs when the app starts and after every rename. **Built so far (B-7):**
  `tests/test_outward_never_names_assistant.py::test_an_op_for_what_others_read_naming_the_assistant_is_refused_with_the_reason`,
  `::test_renaming_the_assistant_blocks_the_new_name_and_the_old_one_on_what_others_read`,
  `::test_closing_someones_action_from_an_unattributed_input_writes_a_row_sourced_by_the_input`. *Not built:* a plugin's own
  record types cannot yet say which of their fields others read (the check covers the core's ops and fields); that needs a
  generic extension point.
- **A title is never an id** (the UI/UX re-review of B-7, R1, check C54; `engine/id_words.py`): an op that writes a title (a
  to-do's words, a question's, a calendar entry's, a series' or a project's name, a report's title; the same fields through
  `record.set`) holding the id of a record that exists is refused with the reason in plain words (`id-in-title`; never a lint,
  never configurable). An id is how the product refers to a record, not a word for a person: name the record by its own
  title. The person's own typing on their own screen is not checked. The labels the ops give the person (6.7, 7.14) are made in
  one place, `_label`, which names each record by its title in quotes and, with no title, by its kind in words ("the to-do");
  a plugin's op may do the same. `outward.sweep_ids` re-makes each stored label that holds an id as labels are made now; it
  runs when the app starts. A label is the app's own words; record titles are never swept, since a title may be the
  person's own words and the invariant keeps the assistant from writing an id into one. **Built:** `tests/test_titles_without_ids.py`.
- **Evidence matches:** an op that needs evidence has it, and its quoted words appear in the cited source's saved text
  (whitespace and quote marks normalized). A quote that isn't there is refused: the cheapest defence against a model that is
  confident and wrong, and against an injected instruction pointing at text that doesn't exist. (A real but wrong target, like
  closing the wrong action, is what evidence makes visible; whether the quote fits the target is the `evidence-fit` lint.)
- Every record edit that changes a published output comes with an update-log op.
- Op-specific checks (paths stay under allowed roots; files don't overwrite unless told).

**Lints** are judgment calls. Each has a severity in `config/checks.yaml` (4.17): `return` (default), `warn`, `off`, or raised
to `refuse`. `return` sends the changeset back to the AI once with the reasons when the item will **reach another person** (a question to
someone else, a draft for a channel); if the problem is still there, that item is **held for the PM**, because the PM sends
questions as written and a warning on a ready-to-send item gets missed. A **wording** lint (`blocked-wording`, `run-on-list`)
on an item that **stays internal** (an action, a note, a fact) never costs a fix round: it applies with a **warning** on its
row. Lints about correctness (`near-duplicate-action`, `evidence-fit`) keep their configured severity on every item. Lints
look only at the assistant's own words, never at quoted evidence from the input.

**A check on words reads the words** (`engine/check_text.py`): links (an address with a scheme and a query string, `mailto:`,
a mail address, `www.` and bare domains such as a dotted host with or without a path) and the person's or the input's own quoted
text are taken out first, by one helper every such check uses: the screen-text check (7.0), the wording lints (`blocked-wording`,
`run-on-list`) and the word-overlap checks (`near-duplicate-action`, `evidence-fit`). What is known where decides which quotes can
be removed. The applier knows the input, so it removes an op's evidence quote, the quotes of its cited passages and any passage
of its text in quotation marks that is in the input. A screen field holds a string only, so it can remove links and nothing
more: a field that holds the input's own words (a cited quote) is typed as plain text, not as screen text. A settings key or a
file name is not a link, so it is still caught. The `never-shown` check is a leak guard, not a check on wording, and reads the
text whole.

Built: `blocked-wording` (blocked phrases, including "confirm / check whether" in actions), `run-on-list` (run-on separators),
`near-duplicate-action` and `evidence-fit`, below, plus any lint a plugin registers (4.17).
- Wording on anything that reaches a shared output: blocked phrases, run-on separators; locale spelling (*designed*).
- A question whose text matches a fact kind's `terms` but doesn't declare `asks_for` (*designed*, with fact lookups).
- A question that links to something the recipient may not be able to open, or carries bookkeeping in its label (*designed*).
- A new action that looks like an open or done action for the same deliverable (`near-duplicate-action`; the similarity
  threshold is a setting, default 0.8, 4.17).
- A link that doesn't respond (*designed*).
- `evidence-fit`: the quoted words don't plausibly concern the target record (its title, owner and project share nothing with
  the quote). Default `return`, which holds it for the PM if the item will reach another person.

Every finding is recorded on the changeset with the check's name and severity, so the PM sees why something came back.

### Normalize, apply, undo

**Normalization before apply:** names in id fields resolved to ids (6.11), dates parsed to zoned values, links enriched from
item keys and known titles (*designed, not yet built*, 6.8); a value for a field bound to a value list is checked against the list and refused if it is not on
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
- **A retry that applies retires the attempts before it.** Attempts are linked by the request they answer: a request made by
  sending work back names the one it redoes as `previous`, never by names or titles. When a request's changeset applies
  something, every request it redoes is retired: it is done and names the later one as `superseded_by`, its waiting reason and
  cause are cleared (so its Today lines close and a try queued for it never runs), the changes it left held are refused with
  "A later try at the same request replaced this", the routing questions asked to place them are dropped, and its open setting
  proposals and report drafts are dismissed. What an earlier attempt applied stays, with Undo as before. A try again on the
  same request needs nothing more: it clears the cause and the waiting reason when it starts. **Before any costly follow-up
  starts** (a queued automatic try, a fix round, the escalation re-run) the dispatcher checks that its cause still stands: a
  request that is already applied, finished or replaced is not run, a fix round or an escalation for a request closed meanwhile is
  not asked, and a late failure or result is not written onto it. A changeset that applied nothing retires nothing.
- **Outbound can't be undone.** Undoing a published page edit drafts a reverting edit for approval; a sent message shows as
  "already sent", with a follow-up offered if the PM wants to correct it.

**Classification:** a changeset is "for the PM" only if it drafts an output, files a question, adds a decision or action, holds
a system op, or otherwise needs a decision. Everything else is filed quietly (still findable). The change it came from closes as
"no change needed" automatically, so the PM never clicks "Looks good" on nothing.

**Follow-on changes** (functional designer's lessons from running, 2026-10-15; roadmap L7 (see roadmap-done.md)). The links, the series and the
one request on a move are **built** (what is left is listed at the end of this part). When the
person moves or retitles a dated record (a calendar entry's day or time, or a new day typed in its notes), or a fact is
replaced, one save makes **one** request to the assistant listing what changed, never one per field. The request asks it
to find what is tied to the record: records that name it or its old date, open actions linked to it or due before its
new date that are to be settled there, and anything a record says will be covered there. Each is brought in line by the
usual ops, with Undo. Links are stored when they are made (a record names the calendar entry it belongs to), so finding
them doesn't rest on matching words; matching words is the fallback. **Built:** an action, a question and a fact have
optional `event` and `series` fields, set by their add ops (`action.add`, `question.add`, `fact`) and by `record.set`, which
refuses an entry that isn't an instance of the series named with it and needs the quoted words
(`tests/test_series.py::test_actions_questions_and_facts_can_name_the_entry_or_series_they_belong_to`,
`::test_an_item_naming_a_missing_entry_or_series_or_an_entry_of_another_series_is_refused`,
`::test_record_set_names_or_clears_the_entry_or_series_of_an_action_a_question_and_a_fact`). The packet lists the series and
the entries that haven't ended, with their ids, beside the open actions and questions, and says on each item what it
belongs to (`::test_the_packet_lists_the_series_and_the_entries_to_come_and_what_each_item_belongs_to`); the notes prompt says
when to name one (`::test_the_notes_prompt_says_when_to_tie_an_item_to_an_entry_or_a_series`). A date-only move writes no history entry of its own;
marking a meeting done starts no run (its notes come in as their own input). A meeting's agenda items are core records (below, **A meeting's agenda**); building and sending an agenda belongs to
the project management pack (6.24), which builds on these links. From the functional designer's answers (functional designer's answers, 2026-10-15; roadmap L7 (see roadmap-done.md)):
- **A meeting's agenda** (**built**): a calendar entry and a series each carry `agenda`, a list of items. An item links the
  action, question or note it came from (`action`, `question` or `note`, one of them, by id), and holds who put it there
  (`added_by`, a person id, none when the assistant did from what came in), when (`added_at`) and the words it is listed
  under (`text`, the record's own words unless given). The core op `agenda.add` (system tier: from an input it waits for the
  person's confirmation and their keep puts it there as theirs; from the person's own note or a screen it applies at once;
  evidence required unless the person makes it) names the meeting by `event` (a calendar entry) or `series` (the series of a
  repeating meeting named in general) and one record; it refuses a meeting or record that doesn't exist, a record that is
  already done, dropped or answered, and one already on that agenda, and it changes nothing but the agenda, so Undo takes the
  item off. The agenda is not editable by hand (`record.edit` refuses it). It shows on the meeting's page (an "Agenda"
  section, its own items and, when it is its series' next meeting, the series' after them), on the series' page (the series'
  items and then those of its next meeting) and under the meeting's row in Today's agenda
  (`tests/test_agenda.py::test_a_meetings_page_and_its_todays_row_list_its_items_and_the_series_page_lists_the_series_and_its_next_meeting`,
  `web/src/components/AgendaList.test.tsx`). Called off into a meeting: see the endings in 6.33.
  **Built:** `tests/test_agenda.py::test_agenda_add_is_a_system_op_that_needs_evidence_unless_the_person_makes_it`,
  `::test_an_agenda_item_names_one_meeting_and_one_record`,
  `::test_the_persons_note_puts_an_action_on_a_meetings_agenda_linked_and_undo_takes_it_off`,
  `::test_a_question_and_a_note_go_on_the_agenda_in_the_order_they_were_put_there_under_the_words_given`,
  `::test_from_an_input_it_waits_for_the_person_and_their_keep_puts_it_there_as_theirs`,
  `::test_what_the_agenda_refers_to_must_exist_be_open_and_not_already_there`,
  `::test_the_agenda_of_a_meeting_is_only_changed_by_the_op`.
- **A series** (**built**): an entry can be one instance of a series ("then every three days"). A series is its own record
  (`series`: title, project and `repeats`, how often in the person's words, which no date is worked out from); each instance
  is a calendar entry that names it (`event.series`), added by `event.add`, `series.add` or `series.link`, with Undo. An
  item belongs to the series and sits on its next instance (`engine/series.py`, `next_instance`: the first instance that has
  not ended before today, in the person's days); when an instance passes with the item unsettled (an action not done or
  dropped, a question not answered or dropped), it rolls to the next one, never to nowhere: with no later instance it stays
  where it is. The worker does the roll once a day (`roll_series_if_due`), and each move is a ledger entry (`series.roll`,
  by the engine) like any other change
  (`tests/test_series.py::test_next_instance_is_the_first_one_that_has_not_ended_before_today`,
  `::test_an_open_item_on_a_passed_instance_rolls_to_the_next_and_the_move_is_in_the_ledger`,
  `::test_the_roll_leaves_settled_items_future_ones_facts_and_series_with_no_later_instance`,
  `::test_the_worker_rolls_items_once_a_day_and_tells_the_screens`). Nothing makes the instances of a series: they are
  entries the person or an input adds, so the series needs no recurrence rule.
- **Who starts it:** the assistant's own move from an input ("Thursday's sync moves to Monday") starts the same run as the
  person's. The follow-on run's own changes never start another: one hop, no cascades.
- **The run** (**built**, `engine/follow_on.py`; task kind `follow-on`, prompt `follow-on.md`, playbook `follow-on`): a save
  that changes a calendar entry's `start` or `end`, moves an action's `due` from one day to another, or adds a fact that
  `supersedes` another queues one request in the same transaction (`Store.transaction`, like learning), whatever the
  number of records or fields in the save; the request's `follows` names the change, and what moved is read back from
  the change's ledger entries. An undo, the series roll, a first due day, a time that stays on its day and a save the
  follow-on run's own request made queue nothing; `dispatch.knowledge.follow_on` turns it off. The run reads the moved
  records before and after and the records tied to them, **found by code**: those that name the entry or its series,
  then open actions and questions on the same project whose words give the old day (`language.date_patterns`) or share
  `dispatch.knowledge.follow_on_match` of a replaced fact's words, then, for a moved entry, open actions on its project
  due between the old and the new day (the new day included), at most `follow_on_max_tied`; each is shown as it is now
  with why it is tied and the people it already reached (those an action's notice told or a chase followed up, the
  person a sent question went to). It gets the knowledge section like every task kind and logs it. **A decided
  action's date or wording is never changed by the run** (decisions, 2026-10-16): `record.set` is not one of its ops and
  the applier's `follow-on-reach` check refuses it. Instead, for each tied action with a date the move may affect (it
  has a due day, or its words give the old day), the run adds one `question.add`, kind `decision`, asking whether the
  date should change, with the move as context and as evidence. Code decides who is asked and shows it in the packet:
  the action's first owner; the person when the owner is the person or nobody is named; and the person, saying who to
  ask, when the owner would need a link to what it is about and the project holds none they can open (the link rule of
  6.8). Agenda items with no due day of their own are not asked about: they sit on the meeting's next instance. When the
  moved entry or replaced fact carried more than one dated action (what is tied to it includes an agenda item, a
  question, a fact, an action with notes, or several actions), one more `decision` question goes to the person, naming
  what is tied, asking whether the plan for it still holds. A drafted correction for someone a tied item already reached
  stays as it was: a `question.add` to that person (open, so it waits for the person; nothing is sent). The run may
  also `note`; the `follow-on-reach` check refuses any other question, and the packet marks every record as outside
  content. A request whose move was undone or changed again before it runs is closed without a call
  (`tests/test_follow_on.py`, listed in the roadmap's L7 item (see roadmap-done.md): `test_no_due_or_text_change_ever_applies_from_a_follow_on_run`,
  `test_an_action_due_between_the_old_and_the_new_day_is_tied_and_one_outside_it_is_not`,
  `test_an_action_due_between_the_old_and_new_day_gets_a_question_to_its_owner_that_waits_and_undoes`,
  `test_a_moved_entry_that_carried_more_than_a_dated_action_asks_the_person_whether_the_plan_holds`; replay
  `moving-an-entry-asks-about-the-actions-tied-to-it`).
  **The assistant's own move of an entry** (**built**): `event.set` changes a calendar entry's `start` and/or `end` from an
  input (data tier, evidence required, Undo; offered to reading notes, not to the follow-on run), and its save starts the
  run like the person's edit (`tests/test_event_set.py::test_the_assistants_move_from_an_input_queues_one_follow_on_request_for_the_save`).
  *Not built:* a correction for an action's notice with no link to carry (it becomes a note), and a move written by a
  connected calendar's sync (a sync writes `snapshot` records with no changeset; see the roadmap's L7 item (see roadmap-done.md)).
- **What applies at once:** changes to the person's own items and the agenda apply with Undo. Anything that already
  reached someone (a question or a notice sent that named the old date) gets a drafted correction to send, not a silent
  edit.

## 6.8 Questions service

*As built today* there is no separate questions service: a question is written by the `question.add` op (a recipient, a
title, text, links, one project and a kind), by the engine for its own problems (a sign-in that needs attention, a watched
source that fails), and by the applier for its routing decisions. Below, what the design says and the code does not yet do
is marked *designed*, with the phase.

- `ask(to, title, text, key, on_answer, links, projects, batch)` is the one entry point *(designed, not yet built, not
  scheduled)*: it deduplicates by `key` and takes several projects, a batch and what to do on an answer. Today `question.add`
  has none of `key`, `on_answer`, `batch` or several projects. What is built is the rest of the sentence: the op is held and a
  routing decision is filed to the PM when the recipient is unsure (`to: "?"`, a first name several people share, a name
  nobody on file has), and answering that decision releases it (6.11).
- Enriching links automatically from item keys and known titles found in the text is *designed, not yet built, not
  scheduled*. Today a question to anyone but the PM is refused unless it carries a link the recipient can open, and nothing
  adds links.
- **A decision goes to whoever decides** (owner, 2026-10-15, from the functional designer's lessons from running): the
  person the input or a routing entry names as deciding (an architect choosing between options a vendor offered), and the
  PM when nobody is named. A choice someone asks the person directly is not a decision question: it is a reply the
  person owes, one action (below). A reply owed with no drafted reply, from a run that never searched, is checked
  like a question by `already-known`: when a fact answers it, it goes back once to be drafted from that fact
  (*built, B-10:* `tests/test_reply_already_known.py`). The person's own request in their sent mail ("Can you send ...?")
  is not their promise: an action owned by the person from it goes back once (`own-request-not-promise`, *built, B-10:*
  `tests/test_own_request_lint.py`). The assistant marks each question with a kind (question, decision, and the routing, impact and
  notice kinds), and the screen follows the stored kind: a question of kind `decision` shows as a decision, and one of kind
  `question` shows as a question to answer; a decision to someone else shows in the PM's follow-ups under that person.
  Keeping the kind makes the assistant's call checkable and lets a mistaken one be corrected. An option offered inside an
  answer ("there is a feature we can turn on") is a decision for whoever decides. Moving a decision to someone else
  keeps it a decision (`question.move`, below). Its Today line ("Waiting on <name>'s decision: blocks <action>") comes
  with the dependencies of the project management pack (phase P, 6.23). **Built:** `web/src/components/FollowUps.test.tsx`
  ("a question to the PM shows as a decision or as a question by its stored kind"),
  `tests/test_corrections.py::test_moving_a_decision_to_someone_else_keeps_it_a_decision_records_routed_and_undo_sends_it_back`,
  and the prompt and golden cases below.
- The person's own promise in mail they sent ("I'll review it Monday") is their to-do: an answer with no action of
  theirs quoting it goes back once (`own-promise-missed`, *built*; the words are `language.own_promise_words`). A
  team's "we'll" made the sender's alone, when the words don't name the sender, goes back once to leave the owners
  empty (`team-we-one-owner`, *built*; `language.team_promise_words`).
- The date reader reads the deadline words people use every day: numeric dates in the language's order, "day after
  tomorrow", "later today", "tonight", "noon" and "midnight", "first thing <day>", "end of the month" and "of next
  month", "this weekend", "within <n> hours, days or working days", a time with a zone abbreviation, and named days
  from the language's calendar. A doubtful reading stays inexact, so it waits for "check this" (built:
  `tests/test_phrase_cases.py::test_the_rules_read_more_of_the_deadline_words_people_use_every_day`).
- Someone's promise with a date ("Riley will drive the audit by the 20th"), recorded as a fact rather than as their
  action, goes back once to be their action, including for someone not on file yet, who is proposed and asked about
  (`promise-as-fact`, *built*; `language.promise_words`, `language.promise_state_words`). A rule on the words: a
  promise word after a named person and before a date the rules read. A state ("will be away on the 20th"), a
  project the person only watches and a promise by someone on file on another team stay facts.
- Work the words leave open ("someone should find out"), given owners the words don't name, goes back once to leave
  the owners empty so the person picks one or is asked (`someone-given-owner`, *built*; `language.unassigned_words`).
  A request to the reader ("can you ask someone") and the speaker's own promise are left alone.
- Words that give an open action a new day ("my approval can wait until Oct 20"), answered only with a fact or a note,
  go back once to move the action's date (`due-move-missed`, *built*; `language.due_move_words`). Any other op quoting
  the words, such as a moved calendar entry, settles it.
- A new day on an action that is no longer open is refused: the date goes on the open action the words are about.
- The person's own action for something another person has ("return Edda's book"), owed to nobody, goes back once
  naming that person for "promised_to" (`owed-to-missing`, *built*). A bare first name only one person has counts
  here, since the answer decides.
- A fact quoting the start of something named that no project has ("we are starting the Depot Scanner Pilot"), with no
  project proposed, goes back once to propose it (`project-start-as-fact`, *built*; `language.project_start_words`). A
  name inside a project's own counts as that project.
- A question to the person about something the input says another person stated ("Jun told me it arrives on the
  10th, but the quote says the 30th") goes back once to ask whoever made the claim (`claim-asked-of-the-person`,
  *built*; `language.claim_words`).
- Mail from someone who owes an open promise, sharing one of its longer words, answered with no op on that promise,
  goes back once to say what it means for it, news that it doesn't answer it included (`owner-mail-unanswered`,
  *built*). This covers a reply that quotes no history, which `thread-promise-unanswered` can't link.
- The sender's own promise ("I'll send it Friday"), recorded as their action and owed to nobody, goes back once naming
  the people the mail went to; mail handed in with no To line was written to the person (`promise-owed-to-reader`,
  *built*). The checks that read the From line also read mail handed in with only a From line.
- Answer flow, in two kinds, as built:
  - **The PM's own answer** to a question put to them (`/answer`) is the PM's words. Learning from it applies at once
    (*designed, phase L3*, 6.22). A held op the PM's answer releases ("yes, add them" to a `project.add`) counts as the PM's own.
  - **A reply someone else sent,** pasted by the PM (`/reply`), is handed in as pasted content: untrusted, like the paste
    box's "pasted content". Only the PM's own note beside it counts as the PM's words. So "not me, ask X" in a reply becomes
    a routing proposal that waits for the person, never routing with the PM's authority (*designed, phase L3*: nothing
    proposes a reroute today, and the pasted reply has no authority already).

  A reply becomes a request carrying the question (today a note that names its id) and its `on_answer` (*designed, not yet
  built, not scheduled*); the AI records the answer as a fact and closes the question (`question.done`, built), updates
  records, narrows the question (*designed, phase L3*: it needs `question.update`), and re-checks every other open question to
  that person against the same answer (*designed, not scheduled*: the packet lists the open questions, and the reply's prompt
  does not ask for the re-check).
  The PM's own answer is recorded on the question today; queuing it the same way is *designed*.
- **Same question twice:** `near-duplicate-question` (a lint, 4.17) compares a new question with open questions and ones
  answered in the last `checks` window, since the assistant doesn't know the `key` that deduplicates (*designed, phase L2*).
- Feedback flow (send back, or the question's own menu): reword, reroute, drop (kept in a dropped-questions register with the
  reason) or close; every op that settles a pending request clears that question's pending flag (the pending flag is
  *designed, not yet built, not scheduled*). The person's own ops (L3), each applied as theirs with Undo
  (`POST /api/changesets/{id}/undo`), with the tests below:
  - `question.update` (reword the title, the text or both; `POST /api/questions/{id}/reword`) records `reworded`;
  - `question.move` (ask someone else, by id or name; `.../reroute`) records `routed`, keeps a decision a decision for the
    new person, and makes a sent question open again for the new person;
  - `question.drop` (with a reason; `.../drop`) records `dropped`; the question stays, status `dropped`, with
    `dropped_reason`, and `GET /api/questions/dropped` lists it (a question that holds an item until it is answered is
    never in the list);
  - `question.mark_sent` (the person sent it themselves, on a day or today; `.../sent`), a bookkeeping change that records
    no signal.

  A question that holds something until it is answered (who a name is, who owns an action) is answered where that item
  waits, so none of the four applies to it, and none applies to a closed one. Each signal names the question, the
  changeset that made it and that changeset's run, and is written apart from the change, so Undo puts the question back and
  records no `undone`. Moving a question to someone else does not check for a link they can open (the person chose to ask
  them); reword and drop take their words as the person's own record, not as a note for the assistant. **Built:**
  `tests/test_corrections.py::test_reword_changes_the_question_records_a_reworded_signal_naming_its_run_and_undo_restores_it`,
  `tests/test_corrections.py::test_moving_a_sent_question_makes_it_open_for_the_new_person_and_a_name_works_as_well_as_an_id`,
  `tests/test_corrections.py::test_drop_keeps_the_question_with_its_reason_records_dropped_and_undo_opens_it_again`,
  `tests/test_corrections.py::test_mark_sent_records_the_day_undo_makes_it_open_and_it_is_not_a_correction`,
  `tests/test_corrections.py::test_a_question_that_holds_something_or_is_closed_is_not_reworded_moved_or_dropped`,
  `tests/test_corrections.py::test_the_question_routes_apply_as_the_person_with_undo_and_the_dropped_view_lists_the_reason`.
  The `draft_edited` signal of an edited message names the question ids it covered (after the person) and, when they all
  came from one run, that run and its changeset: `tests/test_corrections.py::test_an_edited_message_names_the_question_ids_and_the_run_that_wrote_them`.
  Not built: the screens, the feedback task that runs on a send-back or correction, and the routing proposal from "not
  me, ask X" in a reply (the learning builders').
- **"Change this" on a row the assistant made** (action, question, decision, calendar entry as kind `event`, fact):
  `POST /api/items/{kind}/{id}/change` with a required note records one `change_requested` signal (refs: the item; the
  changeset and run that made it, when there was one) and queues the notes work about the item under the route name
  `change_requested`, so the packet carries the item as it is when the run starts. The note is read however short. The
  notes prompt tells the run to reword, re-date, put on hold, turn into another kind, split or drop as the note says, never
  to mark an action done unless the note says so, and to ask the PM when the record doesn't match the note. **Built:**
  `tests/test_corrections.py::test_change_this_records_a_signal_and_queues_a_notes_request_whose_packet_carries_the_item_as_it_is_now`,
  `tests/test_corrections.py::test_change_this_route_queues_the_request_and_names_the_signal`,
  `tests/test_corrections.py::test_change_this_on_something_a_run_made_names_its_changeset_and_run`. The row's note box is
  built with the screens (7.18).
  **Holding and dropping** (decided 2026-10-15, from the missing-op review, 6.13): the assistant has `action.hold` (the
  action and what it waits for) and `action.drop` (the action and why it is no longer needed), and may propose
  `question.drop` with a reason; each needs evidence (the input's words, or the person's note) and applies as data with
  Undo. A dropped action has status `dropped` and a `dropped_reason`: it is never done, never credited to its owner, never
  chased, and leaves Today and the to-do list. The person can drop an action from its row menu too (a reason, Undo), which
  records a `dropped` signal when the assistant made it. An op the assistant applies records no signal; only the
  person's own act is a correction. Hold and drop are refused for an action that isn't open; a held action (waiting for
  an owner) is folded, not dropped. **Built:** `tests/test_hold_drop_fold.py::test_action_hold_writes_what_the_persons_hold_writes_records_no_signal_and_undo_restores_it`,
  `tests/test_hold_drop_fold.py::test_action_drop_is_never_done_or_credited_records_no_signal_and_undo_opens_it_again`,
  `tests/test_hold_drop_fold.py::test_a_dropped_action_leaves_the_to_do_list_the_overdue_line_the_follow_ups_and_the_packets_open_list`,
  `tests/test_hold_drop_fold.py::test_the_assistants_question_drop_needs_evidence_and_records_no_signal_while_the_persons_still_does`,
  `tests/test_hold_drop_fold.py::test_reading_notes_is_offered_the_three_ops_and_a_change_this_note_for_a_hold_is_done_not_refused`.
- **Folding an unowned action into the nearest one** (6.9): the held "Pick an owner" item offers the nearest open action;
  folding declines the held `action.add` and logs its text and evidence on that action, in one change with Undo, and
  records `held_declined` with a note naming the action it went into. *As built,* the held item is an applied action with
  status `held` and an owner question: folding sets it to `dropped` with the reason, drops the owner question, and appends
  its text and quote to the target's notes (`language.messages.folded_note`, `folded_reason`). **Built:**
  `tests/test_hold_drop_fold.py::test_folding_declines_the_held_action_logs_it_on_the_target_records_held_declined_and_undo_restores_both`,
  `tests/test_hold_drop_fold.py::test_folding_is_refused_for_a_target_that_changed_is_closed_or_is_the_action_itself_or_one_that_has_an_owner`.
- **Every correction queues its learning:** a signal is written only through `learn.record`, which queues what the
  assistant learns from it in the same transaction. **Built:** `tests/test_hold_drop_fold.py::test_every_correction_the_person_makes_here_queues_what_the_assistant_learns_from_it`,
  `tests/test_hold_drop_fold.py::test_signals_are_written_only_through_the_one_place_that_queues_their_learning`.
- **No bookkeeping in item text** (B-7). Two lints on the assistant's own wording of a to-do's or a question's title, both
  default `return` and never invariants, since telling reasoning from content is fuzzy: `reasoning-in-title` fires on a
  title that holds a phrase of `language.reasoning_phrases` ("no recorded fact", "couldn't find", …; words quoted from the
  input don't count; ordinary connectives such as "because" or "so that" are not on the list, since a to-do may well say
  why), and `question-is-statement` on a question whose title doesn't end in one of `language.question_marks` (a closing
  quote or bracket may follow). As with the other wording lints, `reasoning-in-title` on a to-do the person owns only warns;
  on one someone else owns it returns once and, still failing, is held; a still-failing question to someone else is held. The message says where the reasoning belongs: in the change's summary, which the person reads as the
  assistant's own words ("Quill says"). Fixtures: the cases `question-asked-of-me-nothing-holds-it` (forbids a to-do that
  carries the reasoning) and `decision-for-pm` (expects a question title with "?"). **Built:**
  `tests/test_item_text_lints.py`, `tests/test_evaluate_harness.py` ("carries the assistant's reasoning" and "is a
  statement").
- **One question per id, and a stake for anyone else's.** The lint `several-questions` (default `return`, and for a
  question or decision to the person too) fires on a text that holds `tuning.several_questions.minimum` (2) or more items of
  a numbered list that ask. `question-without-stake` (default `return`) fires on a `question.add` to anyone but the person
  with no `matters_for`: which of the person's decisions, designs or dated items depends on the answer, by id or in words.
  Returned once, it is then held, since it reaches someone else; the prompt tells the assistant to record the point as a fact
  and say why in the change's note instead. `matters_for` is kept on the question. **Built:**
  `tests/test_corrections.py::test_several_questions_returns_a_question_or_decision_at_the_configured_number_and_not_below`,
  `tests/test_corrections.py::test_a_question_to_someone_else_without_a_stake_is_returned_and_then_held_so_it_is_never_sent`,
  `tests/test_corrections.py::test_the_stake_is_kept_on_the_question_and_both_lints_default_to_return_in_both_workspaces`.
- **Check a correction against the data first.** A correction ("this shouldn't be in X's list") is a claim about the data. The
  feedback task's packet carries the current state of what it names, and the run starts by stating where the item actually is.
  When the data doesn't match the correction, the answer is a question to the PM with what was found, not a change and never a
  report. *Designed, phase L3.* Today Send back runs the reading task again with the old note and the PM's words added, and
  nothing in the packet states the named item's current state.
- Aging: "waiting Nd" after Mark sent (built); chase suggestions by the one follow-up rule (6.9, built); **one suggested
  escalation, built in the core (B-6a, open promise P26):** after a second follow-up and the wait running its length again
  with no answer, Today's `escalate` line asks "Ask someone else about …?" with **Pick who**, once per person (the thing with
  the most follow-ups, then the longest wait), never sent, and left out of that person's follow-up line
  (`ui.followups.escalate_after_chases`, default 2, zero turns it off). Pick who asks the question of someone else
  (`question.move`) or gives the action to them (an owner edit). **Built:** `tests/test_nudge_left_out.py`. An escalation to a
  configured person by working days, `routing.escalation` (4.3, 6.24), is *designed, phase C2*, with the project management
  pack: no `routing` setting exists today. The nudge's own list also says what it left out because it was answered since (7.5).

**From the functional designer's answers** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7 (see roadmap-done.md)):
- **A question someone asks the person** is one item: an action owned by the person ("Reply to the shop: when the cover
  proofs ship"). When the facts hold the answer, the action carries a drafted reply, ready to copy, naming the fact's
  source in words, never its id (the reader can't open the app's records); when they don't, it carries no draft and says what's missing. Never an action and an output for one reply.
  *Built:* the draft is its own text on the action (`reply`, with `reply_reviewed`, false until the person approves it or
  writes their own, so it shows as a draft); `action.add` takes it, and the person's `action.reply` (person-only, Undo;
  `POST /api/actions/{id}/reply`: no text approves the draft, text replaces it) marks it reviewed. Rewording a draft the
  assistant wrote records `draft_edited` with the text as used, naming the action and the changeset and run that made it;
  approving as it is, or writing a reply where there was none, corrects nothing. The reply goes through the same
  wording and never-shown checks as the action's text. The screen shows it in phase B (answers 28 and 32).
- **Only the person changes a question's wording.** Outside content adds a note to it; a note that contradicts the
  question ("matte or gloss?" against "matte or soft-touch?") quotes both, and the question stays as the person wrote it.
- **A decision for someone else** shows in the person's follow-ups under the decider, to copy and send. It reaches Today
  only when something of the person's depends on it and is due within a week ("Waiting on <name>'s decision: blocks
  <action>, due Fri"), which needs the dependency the project management pack records (6.23).
- **A drop by the assistant** applies with Undo and shows on the review card; an item that already reached someone (a
  sent question, a notice) waits for the person's look instead, since the other side may still be waiting on it.
  **Built:** a question marked sent, and an action someone was told about or chased for, are held with a plain reason
  (check `reached-confirm`); the person's own drop and one they confirm apply
  (`tests/test_hold_drop_fold.py::test_the_assistants_drop_of_a_sent_question_waits_for_a_look_and_one_not_sent_applies`,
  `::test_the_assistants_drop_of_an_action_someone_was_told_about_or_chased_for_waits_for_a_look`).
- **Three more ops the assistant may propose,** each with Undo: bring back a set-aside item, remove or merge a list row
  that was never a project, and mark a question as already asked ("I asked them in chat").

## 6.9 Actions service

*As built today* the core has one `action` record kind with a stable id; other stores are plugins' own record types.

- One store interface over every action store (project records, portfolio actions, plugin stores), each action with a stable
  key (*designed, not yet built, not scheduled*).
- **Mark done** for the PM's own; for others' actions **Followed up** (recorded internally, stays open, counts as told) and
  **They finished it** (credited to the owner, "reported by" the PM). Never credit the PM for someone else's work.
  **Built:** every day recorded here (sent, told, followed up, held, put on hold) is the workspace's own day, never the
  UTC date, and a wait never counts below zero (batch B-10, `tests/test_followups_backup_eval.py`,
  `web/e2e/late-evening.spec.ts`). Followed up adds the day to the action's `followed_up` for that person and sets their
  told day to the same day, so the waiting count starts over; undo removes the day and puts the told day back (`tests/test_followups_backup_eval.py::test_followed_up_records_a_chase_keeps_the_action_open_and_counts_as_told`, `tests/test_followups_backup_eval.py::test_undoing_a_chase_restores_the_told_day_and_removes_the_chase`). They finished it
  closes the action with `done_by` the person it waited on and `reported_by` the PM (`tests/test_followups_backup_eval.py::test_they_finished_credits_the_owner_and_reports_it_as_the_pm`, `tests/test_routes.py::test_they_finished_it_credits_the_owner_and_records_the_pm_as_the_reporter`); `action.close` from an
  input sets `done_by` to the owners and `reported_by` to the input's sender when that is one known person (`tests/test_pipeline.py::test_closing_an_action_from_a_message_credits_its_owners_and_names_the_sender`, `tests/test_pipeline.py::test_closing_an_action_from_the_pms_own_note_is_reported_by_the_pm`,
  `tests/test_pipeline.py::test_closing_an_action_from_a_sender_nobody_knows_leaves_reported_by_empty`). The generic status route reopening an action clears both.
  Marking an action done from a row credits its owners and records the PM as the reporter
  (`tests/test_routes.py::test_marking_an_action_done_credits_its_owners_and_records_the_pm_as_the_reporter`).
  A note typed with Mark done, They finished it, Followed up or the choice of an owner is an input like any other (6.5): it is
  handed to the assistant after the change is saved, unless it is a bare confirmation, and undoing the change leaves it
  (`tests/test_note_input.py::test_they_finished_it_with_a_note_makes_one_request_and_the_note_survives_the_undo`).
  **Told again after a change:** an action's told day is per person, and when the action's text or due date differs from
  what it was at that person's told day (read from the ledger), it counts as to send again for that person: it leaves
  Waiting on them and joins their next message. Putting the value back to what they were told reverts it, and Mark sent
  settles it, even on the same day (`tests/test_followups_backup_eval.py::test_a_changed_due_date_or_text_after_telling_puts_the_action_back_to_send_for_that_person`,
  `tests/test_followups_backup_eval.py::test_a_change_before_telling_or_one_put_back_to_what_was_told_does_not_reopen_the_action`).
- **On hold** (built). An action the person is waiting on something for carries `on_hold`: what it waits for, in plain
  words, and the day it was put on hold. The person sets it with **Put on hold** (which asks what it waits for) and clears
  it with **Take off hold**, both in the action row's menu; each acts at once with Undo and records a `put_on_hold` or
  `taken_off_hold` signal (6.20), and undoing records none. An action on hold is never due or overdue anywhere: it leaves
  Today's overdue line and the to-do list's Overdue group (it sits last, under On hold), it is never chased, and the
  Follow-ups row says "On hold: what it waits for", with its old due date in the tooltip. The due date is kept for when it
  comes off hold, and the assistant's packets say it is on hold. A hold is not `held` (the status for an action waiting for
  its first owner). **Blocked** (built, phase B-6a) is a hold that names its blocker: `on_hold.on` is the id of a person, an
  action or a question, picked from a list in Put on hold (never typed) or named by the assistant's `action.hold` (which is
  refused for a blocker that doesn't exist or is the action itself). With a blocker and no words, the words are the
  blocker's name. The row reads "Blocked, waiting on <the person or the action>" or, for a question, "Waits on: <the
  question> (<who>, sent <date>)", each name linking to what it names; a hold with only words reads "On hold: …". It is
  still one state: never due or chased, and `blocked_actions` (`engine/blocked.py`) counts the open actions whose blocker
  still blocks, by project and in all, for Top priorities, which shows it under its list (7.7; B-6b). When the
  question it waits on is answered (or the action it waits on is finished or dropped), the to-do is unblocked: it is due
  again by its own date, goes to the top of the rail under Unblocked with "Unblocked: <who> answered <date>" (the UI
  designer's answer 35; the day is read from the ledger), and stays unblocked until the person takes it off hold; the
  hold is not removed for them. The tie is set by the person or by an op naming the blocker, never by matching text.
  **One rule for "is it still on hold"** (B-6b): `standing_hold` (`engine/blocked.py`) returns the hold an action still stands
  under, or none when its blocker is over, and the promise lines, the reminder lines, the replies owed, Today's overdue line, the
  walkthrough's first promises, Top priorities, This week and the assistant's packet (its open actions and the item a note was
  typed on) all ask it, as the to-do list and Follow-ups already did, so a to-do whose blocker is over is due, chased, reminded
  and shown again everywhere by its own dates, and the assistant is no longer told it is on hold. **Built:**
  `tests/test_unblocked_lines.py`.
  **The chase moves to the blocker** (the functional designer's F15, 2026-10-20; batch B-7). A blocked action is never due
  or chased itself, but the follow-up clock of what it waits on is not left stopped: a hold that waits on a **question**
  (sent) or on **another action** (someone's, already told) gives that blocker the chase, which comes due as the blocked
  action's would have (the person's own blocked action once its day is within `ui.followups.action_due_within_days` or
  past; someone else's by the follow-up rule on how long they have been told), so the question or action is chased though
  it hasn't waited the usual days (`followups.sections`: `chase_due`, `holds_up`, `holds_overdue` on each row). Top
  priorities lists the blocker with what it holds up ("It holds up 2 to-dos"), never the blocked action (7.7). A hold that
  **waits on the person themselves** (a question asked of them, an action of theirs, or themselves named) **isn't blocked**:
  it isn't counted in `blocked_actions(…, people)`, and it is the person's own to-do, listed as one (7.7). *Built:*
  `tests/test_chase_moves_to_the_blocker.py`.
  (the designer's F15: a blocked action stays not due and not chased.) **Built:**
  `tests/test_blocked_actions.py` (the blocker, its words, the count, Undo, the op, the rows, the unblocked to-do first),
  `web/src/components/OnHold.test.tsx` (the picker and the rows), `web/src/components/TodayRail.test.tsx`. Taking it off hold when an input says the wait is over is *designed, phase L3b, not built*
  (`tests/test_on_hold_and_follow_ups.py::test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date`,
  `tests/test_on_hold_and_follow_ups.py::test_a_hold_needs_words_and_an_open_action_and_undoing_it_records_no_signal`,
  `tests/test_on_hold_and_follow_ups.py::test_an_action_on_hold_is_never_overdue_on_the_to_do_list_or_in_todays_queue`,
  `tests/test_on_hold_and_follow_ups.py::test_the_to_do_list_view_says_what_a_held_action_waits_for`).
- **The follow-up rule** (built). One function, `follow_up_due` in `engine/followups.py`, decides whether something sent to a
  person is due a follow-up; Today's `nudge` lines, the Follow-ups pills and Top priorities (7.7, through the same
  `sections`) all read it, so they agree
  (`tests/test_on_hold_and_follow_ups.py::test_today_and_the_follow_ups_view_agree_on_what_is_due_a_follow_up_and_on_hold_leaves_both`,
  `tests/test_top_priorities.py::test_the_follow_up_rule_is_the_one_the_follow_ups_screen_reads`,
  `tests/test_top_priorities.py::test_today_and_top_priorities_agree_on_who_is_due_a_follow_up`). A question that went
  out is chased after `ui.followups.question_after_days` days with no reply (default 4). A told action is chased only when
  its own due date is within `ui.followups.action_due_within_days` days (default 7) or past, and only after it has waited as
  long as a question; an action due later is left alone, so a deadline weeks away is not nagged about. An action with no
  due date is chased after `ui.followups.undated_after_days` days with no word (default 14). An action on hold is never
  chased. A chase starts the wait again (it counts as told again, above); a question is chased the same way (`Question.followed_up`
  lists the days, the wait counts from the last one and `sent_at` stays when it was first asked), which is what Draft a nudge
  records (7.5). The Follow-ups pill reads "waiting Nd" and, once
  the rule says it is time, "waiting Nd · follow up" in the warning color, so status is never color alone. `ui.today.nudge_after_days`
  is replaced by `question_after_days`: a workspace file that still has the old key is read as the new one
  (`tests/test_on_hold_and_follow_ups.py::test_the_old_nudge_setting_is_read_as_the_question_wait`). Each branch has a test
  (`tests/test_on_hold_and_follow_ups.py::test_a_told_action_due_far_ahead_is_not_chased`, `tests/test_on_hold_and_follow_ups.py::test_a_told_action_due_soon_is_chased_once_it_has_waited`,
  `tests/test_on_hold_and_follow_ups.py::test_a_told_action_just_sent_is_not_chased_even_when_due_soon`, `tests/test_on_hold_and_follow_ups.py::test_an_overdue_told_action_is_chased`,
  `tests/test_on_hold_and_follow_ups.py::test_an_action_on_hold_is_never_chased`, `tests/test_on_hold_and_follow_ups.py::test_an_undated_told_action_is_chased_after_the_undated_wait_and_not_before`,
  `tests/test_on_hold_and_follow_ups.py::test_a_sent_question_is_chased_after_the_question_wait_and_not_before`,
  `tests/test_on_hold_and_follow_ups.py::test_the_rule_reads_every_threshold_from_the_settings`,
  `tests/test_top_priorities.py::test_every_number_the_list_reads_is_a_setting`). The wait before a dated action is chased (the
  question wait) is part of the rule as built; the roadmap item's wording leaves it out. *Not one rule yet:* the promise lines
  (6.33) read their own pair of numbers, `steward.chase_dated_days` and `steward.chase_undated_days`, which hold the same
  defaults (7 and 14) as `action_due_within_days` and `undated_after_days` but are separate settings.
- **Reassign:** swap one person in the owners list, keeping their team ("Product (Jane Doe)" to "Product (Sam Lee)"); the
  other owners stay. Told dates, Followed up and They finished it are per person, so the new person has not been told and
  the action is to send to them. **Built (B-6a):** "Reassign…" in a to-do's row menu on the to-dos and questions screen (7.5)
  is the person's own `record.edit` of the owners: a list of people, and on a to-do with several owners a first choice of
  whose part changes; one change with Undo, and an `edited` signal when the assistant had set the owners. A person already
  among the owners is not listed twice. `tests/test_open_items.py::test_an_owner_change_from_the_row_is_the_persons_edit_with_undo_and_a_signal`,
  `web/src/components/OpenItems.test.tsx` (one owner, a shared to-do, the team kept).
- **One place for every open to-do and question, and merging near-duplicates** (B-6a, 7.5). `engine/open_items.py` lists
  every open action with its owners, due date, project and parent project, notes, where it came from (`engine/origin.py`),
  its state (no owner, on hold, overdue, stale or open) and the open action of the same project and owners it most nearly
  repeats; and every open question with who it waits on, since when and its state. **Merge with …** keeps the one it is
  offered on and closes the other as one change (`merge_actions`: a `record.edit` of the kept one's notes and earlier due date
  and an `action.drop` of the other, applied all or nothing), so one Undo takes both back, and the drop records a
  `dropped` correction. No new op was needed. The words it adds are `language.messages.merged_note` and `merged_reason`.
  **Stale:** the person's own open to-do with no date, no reminder and no hold that nothing has changed for
  `ui.today.stale_after_days` (default 21), one Today line in Review. **Built:** `tests/test_open_items.py`.
- **Actions worded to stand on their own** (B-6a): the playbook's rule for reading notes (`engine/playbook/guidance/notes.md`)
  and a lint, `action-stands-alone` (`checks.yaml` severity, default `return`), on an `action.add` whose words lean on
  something the reader can't see: fewer than `checks.tuning.action_stands_alone.min_words` words (default 2), or a word of
  `language.unanchored_words` ("it", "that", "the above", "as discussed", …) standing where the action's object belongs
  (right after its first word and any `language.unanchored_lead_words` such as "up on", or last after one) or a phrase of
  them anywhere. The words quoted from the input count, since they are the action. Like the other wording lints it only warns
  on an action only the person reads; unlike them, an action with an owner other than the person reaches that owner in the
  messages that tell them, so there it returns once and is then held. A lint, never an invariant: what counts is a setting.
  **Built:** `tests/test_action_stands_alone.py`.
- **Assign:** give a held action (one waiting for "Pick an owner") its first owner, which adds it (built). The held item
  carries a **suggestion** from the workspace's own records, never from AI: the person an active routing entry names (one
  that isn't "doesn't answer this", whose scope covers the action's project and whose topic the action's text holds at
  least `tuning.owner_suggestion.match` of), with the entry's own words as the reason, and the nearest other open action,
  by the near-duplicate action matcher and its setting, to fold it into. It is in the owner line on Today
  (`suggestion` on the queue line) and on the held item's question (`suggestion` on `ask`); the person still picks.
  **Built:** `tests/test_corrections.py::test_an_unowned_action_is_held_with_the_owner_a_routing_entry_suggests_and_why`,
  `tests/test_corrections.py::test_the_suggestion_follows_the_configured_share_of_the_topic_and_skips_what_does_not_apply`,
  `tests/test_corrections.py::test_the_nearest_open_action_is_offered_to_fold_it_into_at_the_near_duplicate_setting`,
  `tests/test_corrections.py::test_the_owner_suggestion_is_in_todays_line_and_the_held_items_ask`. Not built: folding the
  held action into the nearest one in one step.
- Any change in who does something or when updates the action (built for the action) and any matching meeting in the same
  step (*designed, not yet built, phase C2*: the core has no meeting record; meetings come with the project management pack
  and the app's calendar, 6.7).

## 6.10 Action notices

*As built today* nothing is stored as a notice, and no question is made for one. Actions owned by others reach them: each open
action not yet communicated to an owner shows as "to send" on the action row (not as a separate question row), the person's
Copy includes it, Mark sent records it as told. Closing the action closes the notice.
A baseline date lets a new workspace treat existing actions as already communicated (*designed, not yet built, not
scheduled*: a new workspace with imported actions shows each as to send). Owners marked `track_only` get no notices (*built*
with the stance, 6.34: a `track_only` person counts as someone the person only watches, and nothing is drafted or sent to
them: `tests/test_stance.py::test_the_default_stance_is_a_setting_and_track_only_counts_as_watch`,
`tests/test_stance.py::test_someone_watched_or_reported_to_is_never_sent_their_actions`).

## 6.11 Names and identity

People, teams and projects are referred to by id everywhere (5.1). Names are resolved once, where they come in, and rendered
wherever they are shown.

- **Resolving** (every write path: AI ops, PM forms, edits pulled back from published pages; the last is *designed, phase C4*,
  with the publisher): an id passes; a full name or
  alias that matches one person becomes that id; the PM's aliases become the PM; a bare first name (one that no one has set as an
  alias) becomes a person **only when that person is in the input's context**, and only if exactly one person of that first
  name is; a first name with an initial or surname fragment ("Ada L.") becomes the one person that fragment fits, and when it
  fits no one the op is held and the people who share the first name are offered, however many of them are in the thread;
  a name written with an address ("tess@example.com", "Tess (tess@example.com)") is the one person the address belongs to,
  and an address nobody has leaves the name beside it to decide; a person the answer names in full (or by id) whom the
  input names only by a name more than one person has (a first name inside someone else's full name doesn't count) is
  held for "who is it" with those people offered, because the input's words decide who is meant, not the answer's
  choice (batch B-10: `tests/test_names.py`, the golden case `shared-first-name-named-in-full`);
  an owner written in the workspace's `owner_format` is parsed into person and team (*designed, not yet built, not
  scheduled*; the format is used for showing owners, below).
  **Names resolve on two fields only:** the owners of an action and a question's recipient, the two that hold a name
  written in an input. Every other field that refers to a record or a value is picked from a list (7.0), so there is no name to
  resolve there. The words that mean the person themselves ("me", "myself", "I" by default) are the setting
  `language.self_words`, not words in code (4.6). **Built:** `tests/test_names.py::test_the_words_that_mean_the_person_come_from_the_language_setting`.
  Anything ambiguous or unknown holds the op and files one routing decision per name per input ("Who is 'Sam'?", with the
  candidates; names compare ignoring case and surrounding space). Every op of that input that waits on the name hangs on
  that one question, and answering it applies them all. **Built**: `tests/test_pipeline.py::test_one_unknown_name_in_two_ops_gets_one_question_and_one_answer_releases_both`,
  `tests/test_pipeline.py::test_a_second_unknown_name_in_both_ops_is_asked_once_after_the_first_answer` and the golden case
  `unknown-person-twice`. "Add a new person" is *designed*, L3b. The answer is a correction of the routing guess, so it
  records a `routed` signal (6.20) with the person chosen; keeping the name as an alias is *designed*, L3.
- **The input's context** (**built**, phase L0): the PM; the sender and the others on the message (a watched message's saved
  `participants`, and the From, To and Cc lines at the head of the input's own text, which also covers a pasted message); and
  the people of the project the input is about (the project the person chose at hand-in or the watched source's project: its
  owner and the owners of its actions). A person is matched by an address in their record's `how_to_reach`, else by a full name
  or an alias that is theirs alone. Outside content can therefore say who is in a thread, which only decides between people the
  workspace already knows. The same context is rebuilt when a held op is released, so a name is read the same way both times.
  Tests: `tests/test_names.py` (the resolving rules with and without context, the context of a hand-in and of a watched
  message) and the golden cases `first-name-in-thread`, `different-initial-held`, `shared-first-name` and `unknown-person`.
- **Rendering:** owners in `owner_format` ("Product (Jane Doe)"; the to-dos and questions screen shows them so too,
  `tests/test_open_items.py::test_an_owner_shows_with_their_team_as_the_workspace_writes_owners`), recipients by full name, greetings by first name. Changing
  the format changes every output at the next render. The format takes `{full_name}` (required) and `{team}`; an owner with
  no team is shown by the full name alone, and the team is the one on the action's owner entry, else the person's own. It
  applies where the app shows an action's owners (a record's page and the review of a change), not in the packet the
  assistant reads, because names are not yet parsed back from the format. A greeting uses the person's `first_name` when the
  record has one (the person edits it in the app), else the first word of the full name. **Built:**
  `tests/test_names.py::test_an_owner_is_written_in_the_owner_format_with_the_team_on_the_entry_else_the_persons_own`,
  `tests/test_names.py::test_the_record_page_writes_owners_in_the_owner_format`,
  `tests/test_record_page.py::test_the_owner_format_applies_to_the_owners_on_the_review_screen_and_the_record_page`,
  `tests/test_names.py::test_a_greeting_uses_the_first_name_on_the_record_else_the_first_word_of_the_full_name`,
  `tests/test_routes.py::test_a_first_name_set_on_the_person_is_what_the_copied_message_greets_them_by`.
- **No sweep needed:** nothing stores a short name, so nothing needs rewriting later. Free text (notes, fact text) keeps names
  as written.
- **Merging:** when two person records turn out to be one person, `person.merge` repoints every stored id (each record type
  declares the ids it stores, 5.1) and the ledger records it. *Designed, not yet built, not scheduled* (6.7 lists the op).
  Today a person that other records still refer to can't be removed, and the person is marked as left instead.

## 6.12 Records, renderer and publisher

*Built in part (S1b-1: the act, the publisher and the screens; the file channel is phase C4, mail and calendar channels S1b-2).* The product's rules
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
- **The outward act (phase S1b, designed 2026-10-22; change log 177; built in part, S1b-1a, change log 180: see "Built so far" below).** Everything the app does outside the
  workspace on the person's behalf (a message sent, a reply, an event created or answered, a file written for someone) is
  one **act**, a core record (`act`): its channel, its target (the recipients as person ids with the address each resolves
  to, or the calendar and time, or the folder), its content in named parts, and its status. Its states:
  `draft` (made by the assistant, a plugin or the person) → `approved` (the person's yes on this exact act) → `sending` →
  `sent`, or `failed` (with why), or `uncertain` (the service's answer was lost); `stale` when anything the yes covered
  changed; `withdrawn` when the person takes it back; `undone` where the channel can undo. Every change of state is an op
  through the applier, so each is in the ledger.
  - **The yes covers a fingerprint.** Approving records a hash of the content, the target as resolved (each recipient's
    address, not only their id), the channel and the template version the content was rendered from. The publisher
    recomputes it at send time; any difference, including an address that re-resolved or a template updated since,
    makes the act `stale`, and it needs a new yes. Editing the act clears the yes.
  - **Only the person approves.** Act ops are outbound tier: never applied automatically, never by a rule, never from an
    input; `act.approve` comes only from the person's own click on that act. The assistant and plugins may only draft.
  - **Recipients are called out.** Before the yes, the act shows each recipient who is new (never written to before),
    outside the workspace's people, or taken from untrusted text, and the yes acknowledges each by name. An assistant-drafted
    act may only address the workspace's known people and the people in the thread it answers; any other address comes from
    untrusted text and is called out. Content from outside that tries to add a recipient to an act, or to add an act, is
    refused (an invariant).
  - **Never twice, never "sent" when unsure.** Before calling the channel, the act moves to `sending` with an attempt key
    in the same transaction; the channel sends with that key. A clear answer makes it `sent` (with the service's id) or
    `failed`. A timeout, a lost connection or a closed lid leaves it `sending`; on the next start, or the next try, the
    publisher first asks the channel what happened to that key. Sent: `sent`. Not there: back to `approved`, so it can go
    when the person says (never on its own after a restart). A channel that can't say: `uncertain`, and Today asks the
    person to look ("Check the Sent folder for the message to Ana"), with **It was sent** and **Send it again**.
  - **A withdrawn sign-in stops it plainly:** the act is `failed` with "Sign in to <account> again", and the sign-in's Today
    line says so; nothing retries in a loop.
  - **The name check:** `outward.check_outgoing` runs on every part before the yes is offered and again at send.
  - **Channels** are an extension point (plugin API): a channel declares what it can do (`send`, `status` by attempt key,
    `undo`, the target kinds it takes) and is called only by the publisher. The core ships `copy` (the person copies the
    approved text; Mark sent makes it `sent`, as Copy works today) and `fake` (for tests). Mail and calendar acts are the
    mail add-on's channels (S1b-2).
  - **Mail and calendar acts (S1b-2; designed 2026-10-22).** One act is one thing done outside, on one account, after
    one yes. The act says what it does (`action`) on what (`about`), and which of the person's accounts carries it.
    - **What an act can do.** A `message` act: `send` (a new message), `reply`, `reply_all` or `forward`, the last three
      naming the saved message they answer (`in_reply_to`); the service's own id of that message is read from the saved
      input when the act is sent, and is part of the fingerprint. A `mailbox` act (a new target kind, no recipients and no
      content): `archive`, `move` (to a folder), `label` (with a label) or `mark_read`, on one saved message or an approved
      list of them (`about`: the inputs' ids); the detail shows each message's sender, subject and date. A `calendar` act:
      `create` (an event or a hold: calendar, start, end, title, and an alarm before the start when asked), `move` or
      `cancel` (an event the person organizes, named by its calendar entry), or `answer` (accept, tentative, decline, or
      propose a new time, to an invitation named by its calendar entry). An answer goes to the organizer, so the organizer
      is its recipient and is called out like any other; `engine/itip.py` prepares the reply. The act's list line and
      detail name the event or the message (the invitation's own title: "Answer to <event>").
    - **Which account carries it.** An act names the account (`account`: the sign-in or mailbox connector it goes
      through) and the channel that account's kind provides. A reply, a mailbox act or an answer defaults to the account
      the message or invitation came in on; a new message to the account the person picked last. Changing the account
      clears the yes.
    - **Acting is the person's switch, per account, off by default.** Reading needs only read access; acting needs more
      (send, change messages, write events). Each account has **Let {assistant} act after your yes** in Settings; turning
      it on asks the service for the wider access through the account's own sign-in page (a sign-in declares its
      `acting_scopes` beside its reading ones), and turning it off gives the access back where the service allows. An
      account that can't act still gets drafts, carried out by Copy. Nothing about this switch is ever proposed by a rule
      or an input; it is a setting only the person changes.
    - **Channels declare what they can do.** `registrar.channel(...)` takes `actions`, by target kind
      (`{"message": ["send", "reply", ...], "mailbox": [...], "calendar": [...]}`), and the account kinds it serves. A
      draft whose action the account's channel doesn't declare is refused at the draft, with the reason in plain words.
      `OutgoingAct` carries `action`, `about` (each item's service id and, for a calendar entry, its UID and sequence)
      and the event fields (`start`, `end`, `title`, `alarm`, `answer`, `proposed`).
    - **Undo where the channel can.** A `mailbox` act and a `calendar` `create` can be taken back (moved back, the label
      removed, marked unread, the event deleted); a sent message, a move or cancel others were told of, and an answer
      can't. `act.undo` is the person's op on a `sent` act whose channel declares `undo`; the publisher calls the channel
      and records `undone` (or `failed` with the reason). The undo toast after the send offers it while the act is the
      last thing done; Waiting to go out's sent list offers it after.
    - **A plain mailbox acts through its own servers (the core's `mailbox` channel).** Sending goes through the
      account's outgoing server (SMTP with TLS, port 465 or STARTTLS on 587; host, port and the same password reference
      as the mailbox, each a setting with a default from the incoming host). The Message-ID is made from the attempt key,
      so `status` asks the Sent folder for that Message-ID over IMAP: found is `sent`; not found is `unknown`, never
      "not sent", because a server may not keep a copy (so nothing is sent twice). After sending, the channel saves a copy
      to the Sent folder unless the setting says the server does it. Archive, move, label (an IMAP keyword) and mark read
      go over IMAP, by Message-ID. An answer to an invitation goes as mail to the organizer with the iTIP reply attached,
      which is how a plain mailbox answers. Creating, moving or cancelling events needs a calendar service: a subscribed
      calendar link is read-only, so those acts are offered only on an account whose add-on declares them.
    - **A reminder that reaches a sleeping person** (owner, 2026-10-17, 2026-10-20 and 2026-10-22). A reminder can reach
      the person while the app is closed in four ways, one choice in Settings (Where reminders reach you when the app
      isn't open): *Nowhere* (only Today, the default); *In the app's calendar*, an entry on the app's own calendar with
      its alarm at the reminder time, which is local data and so no act, with no account, yes or channel; *In my calendar*
      on a signed-in calendar account that can act (its channel declares `calendar: create`), an event with an alarm on
      that account's own calendar; and *To my mail* on a mailbox account that can act, a message to the person's own
      address. The last two are acts like any other, drafted by the engine from the core's reminder template, addressed
      only to the person, for the one reminder time (`reminder` and `reminder_at` on the act), so a reminder time never
      gets a second act. The person approves each one, or gives a **standing yes for reminders**: the choice itself, with
      the exact reminder shown first, on one account and in one form. Core code names no calendar service: it says "a
      signed-in calendar account". *Ask me each time* keeps the two outward forms as drafts in Waiting to go out.
      - **The template** is a data file the core ships (`engine/defaults/reminder_template.yaml`) with its version the
        hash of its text; the workspace's own `templates/reminder.yaml` replaces it and changes the version. Two forms:
        the to-do's words, and the plain form ("A reminder from {app}", with the time) used when the to-do's data level
        is above what the account may hold (`steward.reminders.allowed_data`, 7.19: the most sensitive to-do whose words
        may go; the level of a to-do is the highest of internal and the saved input it came from).
      - **What the engine does** (`engine/reminder_acts.py`, in the worker's pass): for each open to-do, not on hold,
        whose reminder time lies within `steward.reminders.look_ahead_hours` (24) of now it drafts the one act
        (`made_by: reminders`, tier outbound; the applier lets only this actor draft a reminder act, and only exactly the
        reminder the template renders, to the person's own address or the account's own calendar, on the account the
        person chose: invariant `act-reminder`). A snooze or a cleared reminder, and a to-do that is done, dropped or put
        on hold, withdraws an act that has not gone out (the publisher's own `act.reminder_withdrawn`, recorded as such
        and never undone from the ledger). For the app's own calendar the same pass makes, moves and removes the entry
        (the engine's own `reminder.entry` op, a data-tier write with Undo; a to-do never has two).
      - **The standing yes** is a record (`standing_yes`: account, channel, form `calendar` or `mail`, the person's own
        address for a mail, the template name and version, given at, ended at) that only the person's `standing_yes.give`
        and `standing_yes.end` make or end (person-only: refused from the assistant, an input, a rule, an add-on and the
        engine's own reminders; an add-on's person action can't propose them). While one stands, the engine's approval
        (`act.approve` with `by_standing`) is allowed only when the invariant `act-approval` finds **every** one of
        these: the act is a reminder act the engine made; its channel and account are the yes's; a mail goes to exactly
        one recipient, the person's own address as the yes recorded it, with no other recipient, and an event is `create`
        on the account's own calendar with no attendee, at the reminder time with its alarm at that time; its template
        name and version equal the yes's and the version in force; its parts are exactly the template rendered for that
        to-do; it draws on no saved message; and the to-do's reminder time is still the one it was drafted for. Anything
        else is refused as before. A change of the template's version, the account's acting switch, the person's own
        address (for a mail), who the person is, or the account's channel makes it stale: it stops approving, and Today
        says "Look again at reminders in your calendar" (or "mail") with what changed. The ledger records each approval
        as the person's, and the act's `approved.standing_yes` names the yes. No rule, input, assistant or add-on can
        make, widen or renew one.
      - **Sending:** the engine's pass hands an act its standing yes approved to the publisher, which recomputes the
        fingerprint first, as for any act. A reminder mail carries the time in its words and goes once the look-ahead
        reaches it. A plain mailbox sends the mail through its own servers; it offers no calendar form (a subscribed
        calendar link is read-only), so *In my calendar* is listed only for accounts whose channel declares it.
      - The reminder's words follow the notification rule (7.19): above the allowed level the event's title and the mail
        say only "A reminder from {app}" with the time, and the content stays in the app.
    - **The invariants** stay: only the person approves (now: their click on the act, or their standing yes when the act
      matches it exactly, `act-approval`); nothing from outside adds an act or a recipient; a mailbox act never deletes a
      message (there is no delete action, only archive).
  - **Where the person sees it:** Waiting to go out (7.4) lists acts by state, each with its exact content and target,
    the callouts and one primary (Approve and send; a send confirms, 7.1); Today has one line per act that is `failed`,
    `uncertain` or `stale`, starting with the verb.
  - **The named tests (designer, F7, 2026-10-19):** the exact approved content and recipients go out; a yes goes stale when
    the draft, a recipient's address or the template changes; a timeout, retry or restart never sends twice; an uncertain
    answer shows as uncertain, never as sent; a withdrawn sign-in stops the act plainly; outside content that tries to
    change a recipient or add an act is refused; a closed lid or lost network mid-send is checked with the service before
    any retry; a yes doesn't survive a restart that changed the act's inputs.
  - **Built so far (S1b-1a, change log 180: the engine, the API and the plugin API 0.3.87; the screens, S1b-1b, below).**
    - **The record and the ops:** `act` (`engine/records.py`) with its states, `engine/acts.py` and the outbound-tier ops
      `act.draft`, `act.edit`, `act.approve`, `act.withdraw`, the person's two answers `act.confirm_sent` ("It was sent")
      and `act.resend` ("Send it again"), and the publisher's `act.sending`, `act.sent`, `act.failed`, `act.uncertain`,
      `act.stale` and `act.reopen` (an attempt the service never saw is `approved` again). An assistant's `act.draft`
      waits for the person (held, never applied on its own); an add-on's person action may propose only `act.draft`.
      The invariants `act-approval`, `act-publisher-only`, `act-from-outside` and `act-recipient` are in
      `engine/defaults/invariants.yaml`; the audience limit (6.35) applies to an act's recipients through the existing
      `audience` invariant, at the draft, the edit and the yes. Undo takes back the person's own ops and never what the
      publisher recorded. Where the template's version now comes from is the channel's (`template_version`).
      `tests/test_publisher.py::test_only_the_person_approves_and_an_outbound_op_is_never_applied_automatically`,
      `tests/test_publisher.py::test_an_act_may_not_address_someone_outside_the_limit_of_what_it_draws_on`.
    - **The yes and the callouts:** `tests/test_publisher.py::test_a_recipient_called_out_must_be_acknowledged_by_name`,
      `tests/test_publisher.py::test_the_name_check_refuses_a_part_that_names_the_assistant` (before the yes and again at
      send).
    - **The publisher** (`engine/publisher.py`; `Worker.settle_acts` runs `resume` at start): the eight named tests are
      `tests/test_publisher.py::test_the_exact_approved_content_and_recipients_go_out`,
      `::test_a_yes_goes_stale_when_the_draft_a_recipients_address_or_the_template_changes`,
      `::test_a_timeout_retry_or_restart_never_sends_twice`,
      `::test_an_uncertain_answer_shows_as_uncertain_never_as_sent`,
      `::test_a_withdrawn_sign_in_stops_the_act_plainly`,
      `::test_outside_content_that_tries_to_change_a_recipient_or_add_an_act_is_refused`,
      `::test_a_closed_lid_or_lost_network_mid_send_is_checked_with_the_service_before_any_retry` and
      `::test_a_yes_does_not_survive_a_restart_that_changed_the_acts_inputs`.
    - **Channels:** `registrar.channel` and `provides.channels` (plugin API 0.3.87), the core's `copy` (`tests/test_publisher.py::test_the_copy_channel_goes_sent_only_by_the_persons_mark_sent`) and
      `FakeChannel` for tests (`tests/test_publisher.py::test_a_plugins_channel_is_registered_by_name_and_the_core_ships_copy`).
    - **The records survive export and import:** `tests/test_publisher.py::test_an_acts_records_survive_export_and_import`.
    - **The API** (`api/act_routes.py`): `GET /api/acts`, `GET /api/acts/{id}`, `POST /api/acts/{id}/approve`, `/withdraw`,
      `/send` and `/settle`: `tests/test_publisher.py::test_the_api_lists_reads_approves_and_sends_an_act_after_the_yes`,
      `::test_the_api_withdraws_an_act_and_takes_the_persons_answers_for_one_it_cannot_confirm`.
    - **Built (S1b-1b, change log 182): the screens.** Waiting to go out lists the acts that wait (draft, approved,
      sending, stale, failed, uncertain) as list | detail: one line each ("Message to Ana Example") with its state as a word
      and an icon and its one button, the detail with every part as plain text, each recipient by name with the address as
      it resolves now, a box to acknowledge each recipient called out by name, and **Approve and send**, which confirms
      ("Send this message to Ana Example now?") and then says yes on the fingerprint shown and sends. A `copy` act has Copy
      (the yes, then the exact text on the clipboard) and Mark sent instead. An act that went stale says what changed and
      offers Look again before the yes is offered; Take it back is in the menu with Undo. Today has one line for each act
      that is `failed` (the channel's own words for a withdrawn sign-in, else "Look at the message to Ana, which didn't
      go out: <reason>"), `uncertain` (**It was sent** with Undo; **Send it again**, which confirms, in the menu) or `stale`
      ("Look again at the message to Ana: <what changed>"); failed and unsure ones are in At risk, a stale one in Decide;
      each opens the act in Waiting to go out. The lines are read from the acts list by the screen (like the stage rows),
      not ranked by the engine's queue. `web/src/components/WaitingToGoOut.test.tsx`, `web/src/components/TodayActs.test.tsx`;
      the browser test `web/e2e/outgoing.spec.ts`.
    - **Built (S1b-2a, change log 185: the engine, the API and the plugin API 0.3.88).**
      - **Actions, `about`, the account:** `ActTargetIn` takes `action` (a message with none is a send), `about`, `label`
        and the event fields, and the kind `mailbox` (no recipients, no content; an event act's content is its fields).
        `reply`, `reply_all` and `forward` name `in_reply_to`; a mailbox act names its messages; `move`, `cancel` and
        `answer` name one calendar entry; a proposal names both times; an answer's recipient is the organizer. The
        fingerprint adds `about` (each item's service id as it resolves now: a saved message's watched key, a calendar
        entry's key as its UID) and `account` only when the act uses them, so an older yes still holds.
        `tests/test_act_actions.py::test_a_message_action_that_answers_a_saved_message_names_it`,
        `::test_a_mailbox_act_needs_its_messages_and_what_its_action_needs`, `::test_a_mailbox_act_has_no_content_and_no_recipients`,
        `::test_a_calendar_act_names_what_its_action_needs`,
        `::test_an_act_made_before_actions_were_named_still_works_and_keeps_its_yes`,
        `::test_the_yes_goes_stale_when_an_items_service_id_or_the_account_changes`,
        `::test_a_changed_calendar_entry_or_event_field_makes_the_yes_stale_at_send`,
        `::test_an_answers_recipient_is_the_organizer_and_is_called_out`,
        `::test_the_account_defaults_to_where_the_message_came_in_and_a_new_message_to_the_one_picked_last`,
        `::test_editing_the_account_clears_the_yes_and_can_bring_the_channel_back`.
      - **Acting is the person's switch:** `watch.acting`; off sends the draft to Copy and the publisher refuses a channel
        call for it; no ask can name the setting. `::test_a_draft_for_an_account_that_is_not_switched_on_is_carried_out_by_copy`,
        `::test_switching_acting_off_after_the_yes_stops_the_channel_being_called`,
        `::test_acting_is_the_persons_switch_a_setting_proposal_from_the_assistant_or_an_input_is_refused`,
        `::test_a_sign_in_declares_the_scopes_acting_adds`.
      - **Channels declare actions and accounts:** `::test_a_draft_whose_action_its_channel_does_not_declare_is_refused_with_a_reason`,
        `::test_a_plugin_declares_actions_and_accounts_when_it_registers_a_channel`,
        `::test_the_channel_is_handed_what_the_act_is_about_with_the_service_ids_as_they_resolve_now`.
      - **Undo of a sent act:** `act.undo` (the person's), the publisher's `act.undone` and `act.undo_failed`, and
        `POST /api/acts/{id}/undo`; only a mailbox act and a created event; a refusal or no answer leaves the act sent
        with the reason. `::test_undo_of_a_sent_mailbox_act_calls_the_channel_once_and_records_undone`,
        `::test_a_created_event_can_be_taken_back_but_a_move_a_cancel_and_an_answer_cannot`,
        `::test_a_sent_message_cannot_be_taken_back`, `::test_a_refused_or_unanswered_undo_leaves_the_act_sent_with_the_reason`,
        `::test_only_the_person_asks_to_take_an_act_back_and_a_channel_without_undo_cannot`.
      - **The act view:** `::test_the_api_shows_what_an_act_does_and_takes_back_a_sent_mailbox_act`,
        `::test_an_account_not_switched_on_says_why_copy_carries_it_and_the_settings_offer_the_switch`.
    - **Built (S1b-2b, change log 187: the core `mailbox` channel, `engine/channels_mailbox.py`).** Registered as the core
      channel `mailbox`, serving `mailbox:<source id>` accounts, with `message`: send, reply, reply_all, forward;
      `mailbox`: archive, move, label, mark_read; `calendar`: answer. Settings on the mailbox source: `from_address`
      (the user name when that is an address), `smtp_host` (the incoming host with a leading `imap.` made `smtp.`),
      `smtp_port` (465 secure from the start, any other number made secure after connecting, never plain),
      `sent_folder` (else the server's `\Sent` folder, else Sent), `server_keeps_sent` (off: a copy is saved after the
      send, and a copy that can't be saved changes nothing about the answer), `archive_folder` (else the server's
      `\Archive` folder, else Archive is refused with a plain reason), and the existing `timeout_seconds`. One connection
      to each server per act, no retry: a try-later is `outage`. A reply, reply all or forward is about the saved message it
      answers (`about_refs`), so the channel is handed its service id and the fingerprint covers it.
      - **Sending:** the Message-ID is `<attempt key@sender's domain>`, so a key always makes the same one; a reply has
        In-Reply-To and References; a forward quotes the saved text as plain text. Every recipient must be accepted before
        the message is handed over. 2xx is sent; 535 and friends are `auth` naming the mailbox; 5xx `refused`; 4xx
        `outage`; an unreachable server `offline`; a connection lost while the message goes over is no clear answer.
        `::test_a_send_hands_the_exact_parts_and_recipients_with_a_message_id_made_from_the_key`,
        `::test_the_same_key_gives_the_same_message_id_and_another_key_another`,
        `::test_the_outgoing_server_settings_have_defaults_from_the_incoming_host`,
        `::test_port_587_connects_and_then_makes_the_connection_secure`,
        `::test_a_reply_carries_in_reply_to_and_references_from_the_originals_service_id`,
        `::test_a_forward_quotes_the_saved_text_as_plain_text_and_is_no_reply`,
        `::test_a_copy_is_saved_in_the_sent_folder_the_server_marks_unless_the_server_keeps_its_own`,
        `::test_a_copy_that_cannot_be_saved_does_not_change_the_answer`,
        `::test_a_message_with_nowhere_to_come_from_or_go_is_refused_before_any_connection`,
        `::test_a_refused_sign_in_is_auth_and_names_the_account`,
        `::test_a_5xx_refusal_is_refused_naming_the_address_and_nothing_is_handed_over`,
        `::test_a_try_later_is_an_outage_and_is_never_retried`,
        `::test_a_server_that_cannot_be_reached_is_offline_and_one_that_hangs_up_before_data_is_an_outage`,
        `::test_a_connection_lost_while_the_message_goes_over_is_no_clear_answer_and_saves_no_copy`,
        `::test_a_server_that_does_not_offer_a_secure_connection_is_never_used_without_one`
        (all in `tests/test_mailbox_channel.py`).
      - **Status:** the sent folders of the mailboxes acting is on for are searched, read-only, for the Message-ID of the
        key: found is `sent`, anything else `unknown`, never "not sent". `::test_status_finds_the_message_id_in_the_sent_folder_and_otherwise_cannot_say`,
        `::test_status_looks_only_in_mailboxes_acting_is_on_for_and_a_failure_is_unknown`.
      - **Mailbox acts:** over IMAP, each message found by `SEARCH HEADER Message-ID` in the source's folder (all must
        be there before any change), then `MOVE` (or, with UIDPLUS, `COPY`, `\Deleted` and `UID EXPUNGE` of that one
        message; a server with neither is refused), `STORE +FLAGS` a keyword for label or `\Seen` for mark read. A
        missing message is refused ("moved or deleted"); nothing is ever deleted. Undo moves back, removes the keyword
        or `\Seen`. `::test_archive_moves_the_message_found_by_its_message_id_to_the_archive_folder`,
        `::test_archive_with_no_archive_folder_is_refused_with_a_plain_reason`,
        `::test_move_label_and_mark_read_use_move_and_store_by_message_id`,
        `::test_a_server_without_move_copies_then_flags_and_expunges_only_that_message`,
        `::test_a_message_that_is_not_there_is_refused_and_nothing_changes`,
        `::test_a_folder_that_does_not_exist_is_refused`,
        `::test_a_mailbox_act_never_deletes_and_a_refused_sign_in_is_auth`,
        `::test_undo_moves_a_message_back_to_its_folder_and_takes_the_label_and_the_read_mark_off`,
        `::test_undo_says_so_when_the_message_was_moved_again_and_never_takes_back_a_sent_message`.
      - **Answering an invitation:** mail to the organizer with `reply_ics` attached as `text/calendar; method=REPLY`
        through the same send path; a proposed new time is refused (a plain mailbox can't). `::test_an_answer_goes_as_mail_to_the_organizer_with_the_itip_reply_attached`,
        `::test_each_answer_has_its_own_status_and_a_new_time_cannot_be_proposed_by_mail`.
      - **Through the publisher with the stand-in servers:** `::test_the_core_registers_the_mailbox_channel_for_mailbox_accounts_with_its_actions`,
        `::test_an_approved_message_goes_out_through_the_publisher_and_is_sent_with_its_message_id`,
        `::test_a_reply_through_the_publisher_is_handed_the_saved_messages_own_id`,
        `::test_a_lost_answer_is_settled_by_asking_the_sent_folder_and_never_sent_twice`,
        `::test_a_lost_answer_with_no_copy_to_find_is_uncertain_not_reopened`,
        `::test_an_archive_goes_through_the_publisher_and_undo_puts_it_back`,
        `::test_an_invitation_answer_goes_through_the_publisher_as_mail`.
    - **Built (S1b-2c, change log 189: reminders that reach a sleeping person and the standing yes).** The reminder
      template, `engine/reminder_acts.py`, `engine/reminder_entries.py`, `engine/standing_yes.py`, the `standing_yes`
      record, the ops `standing_yes.give`, `standing_yes.end`, `act.reminder_withdrawn` and `reminder.entry`, the
      invariant `act-reminder` and the standing-yes branch of `act-approval`, `GET /api/reminders/where`,
      `POST /api/reminders/yes`, `POST /api/reminders/yes/end`, and Settings (`ReminderWhere`) with Today's stale line.
      - **The standing yes approves exactly a matching reminder act, and each refusal is its own test:**
        `tests/test_standing_yes.py::test_a_standing_yes_approves_a_matching_reminder_act`,
        `::test_it_refuses_an_act_with_a_second_recipient`, `::test_it_refuses_an_act_to_a_recipient_who_is_not_the_person`,
        `::test_it_refuses_an_act_to_the_persons_name_at_another_address`, `::test_it_refuses_an_act_on_a_different_account`,
        `::test_it_refuses_an_act_on_a_different_channel`, `::test_it_refuses_an_event_on_another_calendar_or_with_another_alarm`,
        `::test_it_refuses_an_act_made_from_a_different_template_version`,
        `::test_it_refuses_an_act_whose_words_were_edited_away_from_the_rendered_template`,
        `::test_it_refuses_an_act_that_is_not_a_reminder`, `::test_it_refuses_an_act_from_the_assistant_dressed_as_a_reminder`,
        `::test_it_refuses_an_act_from_an_add_on_dressed_as_a_reminder`,
        `::test_only_the_engines_reminders_draft_a_reminder_act`,
        `::test_nothing_but_the_engines_reminders_approves_under_a_standing_yes`,
        `::test_a_click_on_an_act_never_carries_a_standing_yes_and_a_click_alone_still_approves`.
      - **Giving and ending it is the person's alone, and it goes stale:**
        `::test_giving_and_ending_a_standing_yes_are_refused_from_anything_but_the_person`,
        `::test_the_engines_reminders_are_refused_giving_or_ending_one`,
        `::test_giving_one_is_refused_for_a_template_that_changed_an_account_that_cannot_act_and_a_second`,
        `::test_an_ended_standing_yes_approves_nothing_and_undo_brings_it_back`,
        `::test_it_goes_stale_when_the_templates_version_changes`,
        `::test_it_goes_stale_when_the_persons_own_address_changes`,
        `::test_it_goes_stale_when_acting_is_turned_off_for_the_account`,
        `::test_the_ledger_records_the_approval_as_the_persons_and_names_the_standing_yes`.
      - **The reminders:** `tests/test_reminder_acts.py::test_a_due_reminder_drafts_one_act_to_the_person_and_never_a_second`,
        `::test_the_plain_form_is_used_above_the_level_the_account_may_hold`,
        `::test_a_snooze_withdraws_a_reminder_act_that_has_not_gone_out`,
        `::test_a_done_to_do_withdraws_a_reminder_act_that_has_not_gone_out`,
        `::test_ask_me_each_time_leaves_the_reminder_as_a_draft_in_waiting_to_go_out`,
        `::test_with_a_standing_yes_a_reminder_goes_out_through_the_publisher_and_only_that_one`,
        `::test_a_reminder_mail_goes_out_through_a_plain_mailbox_to_the_persons_own_address`,
        `::test_a_reminder_in_the_apps_calendar_is_an_entry_with_an_alarm_and_no_act`,
        `::test_a_snooze_moves_the_same_entry_and_a_done_to_do_removes_it_with_undo`.
      - **The screens:** `web/src/components/ReminderWhere.test.tsx`.
    - **Built (S1b-2d, change log 190: the screens for mail and calendar acts).**
      - **The person drafts an act:** `POST /api/acts` takes `kind`, `action`, `about`, `in_reply_to`, `recipients`,
        `parts`, `folder`, `label`, `answer` and the proposed times, and an `account` (left out: the one the message or
        invitation came in on, as the engine chooses it). The channel is the one that serves the account and declares the
        action; with acting off for the account Copy carries it and the view says why (`copied_because`); a draft the
        channel can't carry (a plain mailbox proposing a time, an action the channel doesn't declare) is refused with the
        reason. A reply or reply all with no `recipients` goes to the message's sender (reply all: everyone else on its To
        and Cc lines but the person's own addresses; `engine/reply_recipients.py`). `GET /api/acts/options` says what can be
        done about a saved message, a calendar entry or a reply owed: the account it came in on, whether acting is on,
        the actions and answers the account's channel does, why proposing isn't offered where it isn't, and the mail
        source whose folders `Move to` lists; `GET /api/acts/free-slots` gives the free times to propose
        (`engine/propose_times.py` over `engine/free_slots.py`: the working week of `steward.reminders`, every calendar
        entry blocking except one declined or called off, each slot as long as the invitation, the first at the next
        round time; `watch.propose_days`, `propose_slots` and `propose_round_minutes`); `GET /api/acts/accounts` lists
        the accounts with the person's switch.
      - **On screen:** a saved message's page has Reply, with Reply to everyone, Forward, Archive, Move to (a pick list of
        the mailbox's folders), Label and Mark as read in its menu; the reply-owed line's primary is Send reply where its
        account can act (the drafted reply goes as an act to approve; Copy reply moves into the menu), Copy reply as
        before where it can't; a calendar entry that came as an invitation has Accept, with Maybe, Decline and Propose a
        time in its menu (the free times of the working week or a typed start and end; not offered, with the reason, on
        a plain mailbox). Each drafts the act and opens it in Waiting to go out. Settings has **Let {assistant} act after
        your yes** for each account (a signed-in account starts its sign-in with `acting=true` first, a mailbox saves;
        off saves at once with Undo), and a mailbox's sent and archive folders are pick lists of its folders.
        Reminders' Undo after a standing yes brings back the earlier choice and account.
      - **Tests:** `tests/test_act_draft_api.py`, `web/src/components/ActsOnRecords.test.tsx`,
        `web/src/components/TodayReplySend.test.tsx`, `web/src/components/OutgoingActs.test.tsx`,
        `web/src/components/ActingAccounts.test.tsx`, `web/src/components/Sources.test.tsx` ("a mailbox's folders"),
        `web/src/components/ReminderWhere.test.tsx` ("Undo after giving the yes ..."); the browser test
        `web/e2e/acts-journey.spec.ts` (written, not yet run).
    - **Not built (S1b-2):** the add-ons' channels; asking the service to drop the wider access when acting is turned off;
      an invitation line on Today (an invitation is answered from its calendar entry); acting on several selected
      messages at once (the API takes a list in `about`, but no list of saved messages lets the person select any);
      Move to for a signed-in account (the API has no folder list for one); before-and-after text for a stale act (an act
      keeps only the hashes of what the yes covered); the engine's queue ranking the act lines; the follow-up message
      moving onto acts (Copy still works as it did); and calling `outward.check_outgoing` for the first export a person
      hands to someone else.
- Change classification for the review list: real change, order only, layout or format only, columns changed, text the target
  doesn't show. Never show an empty "+0 −0" draft.
- **The send step refuses the assistant's name** (the owner's lesson from running, 2026-10-20; `engine/outward.py`): content
  going to someone else is refused while it still holds a name the assistant has gone by (6.7), saying where ("the message
  to Ana"). Today that is Copy: the follow-up message and the drafted follow-up are not offered (`FollowupSection.withheld`,
  `NudgeView.withheld`, with the reason in `language.messages.withheld_name`, and Copy is disabled), and marking one sent
  with text that holds a name is refused (409). **The publisher must call `outward.check_outgoing` on every draft before
  it sends or publishes anything**, with a label for each part; the act publisher does (at the yes, at Mark sent for a copied act and again at
  send), and the older publish targets above are still not built. The readable export (`data/`, the synced folder, backups) is the person's own complete record and is not
  outward; the first export a person hands to someone else (for example their lessons) must call the same function.
  **Built so far (B-7):** `tests/test_outward_never_names_assistant.py::test_the_send_step_refuses_what_still_names_the_assistant_and_says_where`,
  `web/src/components/FollowUps.test.tsx` ("a message that still names the assistant shows why it is held back and cannot be copied").

## 6.13 Governor, automation problems and reports

**The missing-op list** (*designed, phase L3*; the original designer's lessons from running, 2026-10-14). A run that
says no op can do what it needed ("no op writes the people list"), and every edit the person makes by hand to fix the
assistant's work where an op would have done, go on one weekly list on Quality. Each entry becomes an op with its check and
Undo, or an explicit "the person does this" decision recorded in `docs/decisions.md`. The product never adds the op
itself (the report to the maintainers below). **Built (L3):** three of the first audit's hand fixes are ops now:
`mail.restore` (bring back a set-aside message; system tier), `list.merge` (merge one value of a list into another;
system tier) and `question.mark_sent` (the person sent it themselves; person-only), each with its check and Undo.
`tests/test_corrections.py::test_mail_restore_proposed_by_the_assistant_waits_then_brings_the_message_back_and_undo_sets_it_aside`,
`tests/test_corrections.py::test_mail_restore_hands_in_a_message_that_was_never_handed_in_and_undo_takes_that_back`,
`tests/test_corrections.py::test_list_merge_moves_every_record_to_the_other_value_and_undo_puts_both_back`,
`tests/test_corrections.py::test_list_merge_has_a_check_and_waits_for_the_person_when_the_assistant_proposes_it`,
`tests/test_corrections.py::test_mark_sent_records_the_day_undo_makes_it_open_and_it_is_not_a_correction`. Not built: a
project's role, putting an action on hold or dropping any item as an op the assistant may use, and the weekly list on
Quality.

- **Built (roadmap A2, see roadmap-done.md): runs a stop left unfinished.** When the worker starts, every request left running goes back in the
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
  Old code never quietly runs new settings; nothing is half-reloaded. **Held work is never a silent stop** (built:
  `tests/test_silent_stops.py::test_held_work_is_the_first_decide_line_with_its_count_and_nothing_restarts`,
  `tests/test_journeys.py::test_j9_work_held_for_a_restart_is_the_first_line_on_today_and_runs_after_the_restart_i_choose`): the
  first Decide line on Today (kind `restart`) says "Restart to run 7 waiting requests", with the count, for someone who opens the
  laptop and never looks at the header. It only asks: the restart starts when the person chooses Restart now.
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
| **Decide** | work held until a restart (`restart`, "Restart to run 7 waiting requests", always first; built, `tests/test_silent_stops.py::test_the_restart_line_comes_before_the_first_go_and_before_decisions`); a decision or a question put to the PM (`decision`, `question`); a name the assistant couldn't place (`who_is`, "Pick who 'Maya' is"); an action with no owner (`owner`, "Pick an owner"); an item the applier held for the PM's yes (`held`, shaped as a question with two answers when it rests on an inference or drops something that reached someone, `engine/held_ask.py`, 7.6); the questions a follow-on run asked about one move, as one group (`moved`, `engine/move_groups.py`, 7.7; a group of one stays a `decision` or `question` carrying `after_move`); a run waiting for the PM's go because of its cost (`go`); a run the provider refused, waiting for the PM to choose what happens next (`refused`) |
| **Risk** | work that failed (`failed`); an AI account paused until its limit resets, with the time and the count waiting (`paused`, built, `tests/test_silent_stops.py::test_a_paused_account_is_a_risk_line_with_the_time_and_the_count_waiting`); work that has waited for the network longer than `dispatch.offline_line_after_minutes`, one line with the count and since when (`offline`, built, `tests/test_silent_stops.py::test_a_lost_network_is_one_today_line_after_the_configured_minutes_and_goes_when_it_is_back`); a learning check that failed after a switch, with Switch back (`switch_failed`, *phase L*); the PM's own overdue to-dos, as one line, leaving out any on hold (`overdue`); no backup that works: none set up, none yet, the last one failed or the last one overdue, with the one button that mends it (`backup`, "Back up your work", 7.7; the header chip says it too; batch B-7, `tests/test_follow_up_lines.py`) |
| **Review** | the person's own open to-dos with no date that nothing has changed for `ui.today.stale_after_days`, one line (`stale`, 6.9; its action opens To-dos and questions on the stale ones); the assistant's work waiting for a look (`review`), with what it did counted by kind (actions added or closed, questions, notes, recorded, people, projects, drafts, held, refused); what the assistant filed under no project, one line with the count while there is any (`unfiled`, `engine/unfiled.py`, 7.14); learning proposals from corrections waiting for Keep (`learned`), the daily card of learning from inputs (`learned_daily`) and the catch-up list (`learned_backlog`), all *phase L*; a new or probation account's work, marked as such (*phase L*) |
| **Send** | messages to send, one line per person (`send`); one line per person who is due a follow-up (`nudge`: questions sent, actions told by the rule in 6.9, and the promises they owe that 6.33 says are late with nothing heard, with how many are overdue and the oldest date, 4.11; a promise owed by someone the person reports to keeps its own `promise` line); the one thing a person still hasn't answered after `ui.followups.escalate_after_chases` follow-ups, as a suggestion to ask someone else (`escalate`, 6.8; never sent; the same thing is not also in the person's nudge line) |

Within a group, a kind has a fixed place (decisions first, then who-is, owner, held, go, refused, questions), then the line that
has waited longest, or is due first, comes first; a nudge goes by its longest wait. A review or overdue line that covers exactly
one thing carries its words as `subject`, which the screen uses as the line's title (7.7). **Held items and decisions are always
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
  text, with greetings, quoted headers and sign-offs skipped (`language.title_skip`, 4.6), and never cut: a line of more
  than eight words is not used.
  **Built (B-7, changed in B-9):** a topic from the assistant with fewer than `language.title_min_words` words (3) gives way
  to the input's first meaningful line only when that line fits whole; otherwise a short topic of two words or more stays
  (a bare "Noted." is one word and never titles an item), and with nothing usable the topic is empty and the screen says
  so (`title_for(min_words=…)`; `tests/test_item_titles.py`). Work the app started (no source, not the person's own note)
  carries its task kind and what it is about (`Title.task`, `Title.subject`, `engine/titles.py` `subject_of`).
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

**What a model can do, measured: the capability matrix** (owner, 2026-10-15: "very full featured … not just in claude
but all the others"; step 1 (the skills list, the matrix, staleness and the grid in Settings) is built, apart from
"Measure" and the export, which the roadmap lists; step 2 (using it) is *designed, not yet built*; roadmap L7 (see roadmap-done.md) step 1,
C0 step 2). Capabilities above are features a catalog
states. Whether a model *does* a kind of work well is measured, the same way for every account the product supports:
native vendor APIs, OpenAI-compatible endpoints (local servers included), aggregators and command-line agents. Nothing is
assumed from a vendor's or model's name, and no vendor or model name appears outside adapters, `config/ai.yaml` and
evaluation reports.
- **Skills.** A skill is one thing a run can get right or wrong: using a term, following routing, using a lesson, dates,
  owners, not repeating a question, evidence, structured answers, refusing injected instructions, and so on. The core
  ships the list as data; a pack adds its own (drafting in a voice, checking a manuscript's continuity). Every golden
  case, learning pair and pack case names the skills it proves (`skills:`); the self-check fails a case without one, or
  one that names a skill not on the list, in the fictional workspaces and the bundled packs. A case anywhere that
  names an unknown skill doesn't load; a pack's own case with no `skills:` still runs and adds nothing to the matrix.
  *Built:* `engine/defaults/skills.yaml`, `engine/skills.py` (`merge` is where a pack's skills will be added).
- **The matrix.** Each evaluation run adds to it: model (the account's model id as its tier was set up, and a
  command-line agent's program version) × skill → passes, runs, the last date, and the cost of a passing run (price ×
  tokens, from the run's usage; a run on two accounts counts for both, its cost divided). It is kept in the workspace's
  private folder (`ai-skills.json`, `engine/ai/matrix.py`), beside the connection checks, and never sent anywhere. Like
  them it is not part of a backup: it measures the accounts on this computer, and a restored workspace starts it empty
  until Measure or an evaluation fills it again (decisions, 2026-10-16). A measurement goes stale when the program version changes, after `ai.skills.stale_days`, or when
  the cases that measured it change (a hash of the case ids that name the skill, kept for the golden cases and for the
  pairs of each fictional workspace); a changed model id is a different row, so it starts unmeasured. Stale is shown and
  counts as unknown for routing, and the next run recorded over a stale entry starts it again rather than mixing in
  the old runs.
- **Measuring.** `cockpit evaluate` and the switch check (6.22) fill it; Settings offers "Measure" per account with its
  estimate first (spending is the person's choice, 6.16), and only on cases for the data levels the account is allowed.
  *Built (API; the screen is phase B):* `POST /api/ai/skills/{account}/estimate` says what measuring would run and cost
  (the account's models, or the one named, on the golden cases, the plugins' cases and the learning pairs, each
  `ai.evaluation.runs` times, priced as the switch check prices its cases); `POST /api/ai/skills/{account}/measure` is
  refused above `ai.budgets.confirm_above_usd` (or with no price, when `confirm_unpriced` is on) unless `confirmed` is
  sent, then runs on a thread of its own and fills the matrix (`engine/ai/measure.py`). What was asked for is kept in the
  private folder (`ai-measures.json`) so a restart finishes it; one that was answered not at all, or couldn't finish, is
  `failed` with why in `GET /api/ai/skills`, never a result. A case, pair or scenario may say its `data_level` (default
  `internal`, the level a handed-in note has); an account runs and is priced only for those no more private than its most
  private `allowed_data`, and the report still names every case, so the set measured doesn't change.
  Real use adds evidence too: a correction of a run counts against that model for the skills the correction's kind
  touches, shown apart from the measured cases (6.20).
- **Seeing it.** Settings shows each account's models × skills, under the account's row ("What it can do", `GET
  /api/ai/skills`), in plain words: pass rate, how many runs, how old, and cost
  per passing run; skills below `ai.skills.min_score` are marked, unknown is said as unknown, never colour alone. The
  model's own name is never shown, only the account and the short model name the person chose.
- **Using it.** Each task kind, the core's and a pack's, declares the skills it needs. The router picks, among the
  accounts allowed for the data level, the cheapest model whose measured score holds for every needed skill; a task kind
  can say it needs the stronger tier regardless. When none measures well enough it takes the tier's configured model and
  says on the run which skill was unmeasured or low. Fallbacks keep their rules (only checked accounts, 6.16), and
  escalation on failed checks stays: a model's own confidence still counts for nothing.
- **Telling the person.** When the matrix shows a cheaper model is as good for some work, or the configured one is
  below the score for a skill a task kind needs, Today gets one line to decide ("Use <account> for everyday work: it
  scores the same at a third of the cost"). Nothing switches on its own.
- **Choosing from Settings** (built; the router's own pick by skill and the Today line above are still designed). Which
  model does what (7.9) puts the measurements beside each kind of work and offers, only on the person's click, the
  cheapest tier whose model passed every skill the kind needs (`engine/ai/suggest.py`): all measured, none out of date,
  none under `ai.skills.min_score`; a stale or missing result is unknown and never a pass. Which skills a kind needs
  comes from the cases that run it: the core's cases, pairs, scenarios and replays run the note-reading kind, a pack's
  case the kind it names. It also offers a routing rule where the model in use is under the minimum on a skill and
  another tier passes it.

**Adding an account** (Settings, AI): pick the kind, by name, from a list the app ships as data (`catalog/ai-endpoints.yaml`:
services, local servers and the common command-line agents, each agent with its command, the program's own options that keep
its tools off, how it takes the packet and where its answer is; the screen says whether the program is installed and how to sign
in, and the person never types a command); paste the key, which is kept on this computer while config keeps only a reference
(the keychain is *designed, not yet built*, 12.1); **Test** checks the key and lists the models with their capabilities and prices; choose which models fill which tiers; set
`allowed_data` (new accounts start at `open`, and the screen says who will see the data: the vendor, and for an aggregator the
aggregator too; it also says that notes, mail and meetings are internal, so the assistant can work on them only once
Internal is ticked, and a run stopped because no account may see its material offers "Let <account> see internal
material" as its action, the person's own one-click raise, phase A); run the evaluation (below) before a model is approved for a tier.
*The first-run step* (7.8; B-7, first-run review F2, N3, N4): the catalog marks one hosted service **recommended** and
one the **alternative**, and gives each its pages for making an account, adding credit and making a key; the rest sit
under "Something else". **The check runs when the key is pasted** (`POST /api/ai/account-check`, `engine/ai/key_check.py`):
the new account is put into a copy of the settings with every tier pointed at it and `smoke_test` runs on that copy, so every
kind of work is tried with the exact settings and an agent also gets its lock-down and sign-in checks, before anything is
saved; the pasted key is handed to the adapter and kept nowhere. The result is one reason from the failure's own kind (key
refused, no credit, can't be reached, asked to wait, not signed in), worded for the kind of account: a hosted service is told
to check its internet connection, never to "start it if it runs on this computer" (`where_of` tells an address on this
computer or network from a hosted one; `TRANSPORT_HINTS`, `LIST_PROBLEMS`). It also says which sign-in the account runs
as when it can be found (the signed-in user of an agent), and says in plain words when it can't (a key). **A new account reads
only open material until the person says so** (decision F25): the step asks once, per account, "Allow <account>, signed in
as <identity>, to read your work mail and notes?" with nothing chosen; Allow lets it read open and internal material, Not now
leaves it at open, and the three levels stay under Advanced. A drawer in Settings starts a new account at open material too.
**The yes is never skipped silently** (the UI/UX re-review of B-7, conditions on F25; B-8): it is asked in the step itself, right after
the key check passes, and Continue stays disabled with its reason ("Choose Allow or Not now above.") until it is answered. Not now is
kept with the account (`ai.providers.<name>.work_data: not_now`, sent by the step as `work_data`), and an account in that state with
no level above open has a Today line, **"Let <account> read your work mail and notes"**, with one button, Allow (`work_access`
in the queue; 7.7). Allow is `POST /api/ai/accounts/{name}/allow-work`: one settings change that adds the internal level (keeping any
higher one) and clears the answer, with the read-back and Undo every settings change has. Allow changes what the account may read, not
the assistant's work, so it records no signal; the line goes the moment the account may see the internal level, however that
came about. The browser tests' server can start with such an account (`tests/e2e_server.py --standin-account`, the `access` project) so
the line and the yes can be captured. **Built:** `tests/test_work_access.py`, `web/src/components/WelcomeAi.test.tsx` (the question, its
two answers, `work_data` sent with Not now only), `web/src/shell/HeldLines.test.tsx` (the line, Allow with Undo), `web/e2e/work-access.spec.ts` (written, not run).
*Built so far:* `tests/test_first_run_ai.py` (the catalog's recommendation and links, the open-only default, the messages by
kind of account, every tier with its exact settings, the identity), `web/src/components/WelcomeAi.test.tsx`. Until a kind of work has a result the compare page says "Nothing measured yet" with
"Measure (about $x)", and an account's row says "Not measured yet" with a Measure button, instead of "Good at 0 of 14"
(`web/src/components/AiCompare.test.tsx`, `web/src/components/AiAccounts.test.tsx`).
*Found by the first journeys (B-6a):* a new account's suggested name is the service's name ("<service> account", numbered when
taken), never its catalog id, which stays the short name in the settings until the person names the account themselves; and a
custom address (the catalog's "another service" kind) needs no key, since the service may take none: a key is asked for only
by the kinds that need one, and a service that does refuses without it in plain words. **Built:**
`web/src/components/WelcomeAi.test.tsx` (the suggested name, a custom address added with no key),
`tests/test_forms_b6a.py::test_a_custom_address_needs_no_key_because_the_service_may_take_none`.

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
  the model, read its output and usage, and recognize its errors. Where the program's docs give an option for system
  instructions from a file (`system_option`), the packet's instructions and reference go there, in place of the
  program's own, and only the request is sent as the packet.

**Adapter interface** (each adapter is a module in `engine/ai/adapters/` or an installed plugin, registered by name):

- `models()`: the models this account can use, each with `capabilities()` (structured output, tool calling, vision, file
  access, code editing, max context, max output, streaming, prompt caching: whether a marked stable prefix is cached or
  discounted) and price per billing unit, from the provider's catalog where it has one;
- `run(task) -> result` with output, usage and timing;
- `classify_error(exit_code, error_stream, transport_error) -> rate_limited | quota | auth | unsupported | timeout |
  invalid_output | no_output | provider_down | offline | other`, with `retry_after` (seconds to the reset) when the runner gave one:
  an HTTP `Retry-After`, or, for an agent, the first group of a pattern in `errors.reset` matched in the error stream. It reads **only** the runner's own exit code, error stream and transport errors,
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
A fallback is a switch nobody chose at that moment, so (6.22):
- **Who may be in the chain:** only an account that passed the check with that tier's exact parameters, its lockdown
  probes and the learning round-trip, or that the person accepted unchecked (`accepted_unchecked` on the account). The
  learning round-trip is one small call per account: a fixed correction, expecting one proposal the app's own checks
  accept, and a failure says which part failed. A result is kept per account and model with a fingerprint of the
  account's settings, so a changed account is checked again. *As built,* the settings save refuses an unchecked account
  newly added to a chain, in plain words. A hand-edited file is not refused, but every account in a chain that is neither
  checked for that tier nor accepted unchecked, or whose last check failed (accepted or not), is a Today line,
  "Check <account> before it stands in for <work>", whose Check now runs the account's test for that tier and goes when it
  passes (`engine/ai/checked.py::cannot_stand_in`). The router reads the same list at the moment of use and never falls
  through to such an account; the person's own pick for a tier is never skipped, and when skipping leaves nothing the run
  waits with the usual "no account" stop and its Today line. **Built:** `tests/test_catch_up_learning.py::test_the_router_skips_an_unchecked_or_failed_backup_and_takes_a_checked_or_accepted_one`.
  **Built:** `tests/test_quality.py::test_an_unchecked_account_is_refused_from_a_chain_until_it_passes_for_that_tier_or_the_person_accepts_it`,
  `tests/test_quality.py::test_the_learning_round_trip_fails_saying_which_part_failed`,
  `tests/test_knowledge_screen.py::test_an_unchecked_account_in_a_hand_edited_chain_has_a_line_until_its_check_passes`,
  `tests/test_knowledge_screen.py::test_a_checked_or_accepted_account_has_no_line_and_neither_has_an_account_outside_every_chain`,
  `tests/test_knowledge_screen.py::test_a_failed_check_has_a_line_that_says_so_even_for_an_accepted_account_and_goes_when_it_passes`,
  `tests/test_knowledge_screen.py::test_the_line_comes_back_when_the_account_is_changed_after_it_passed`,
  `web/src/shell/HeldLines.test.tsx::Check now runs the account's test for that work, and the line is gone once the queue no longer has it`.
- **The first run on a fallback account** is tagged on its changeset (`first_on_account`), and its cards will say "First
  run on <account label>" so its output gets a closer look (the cards are phase B's). **Built:**
  `tests/test_quality.py::test_the_first_run_on_a_fallback_account_is_tagged_on_its_changeset_and_a_later_one_is_not`.
When the common format lacks structured output for a model, the adapter asks for JSON and the applier's checks still decide.

**The recommended service has a native adapter** (`anthropic-messages`; *built, B-11c part 2a*). Its own messages interface
is used instead of its chat-format compatibility layer, which the service itself calls not ready for production, ignores
effort and has no prompt caching. The native adapter sends the instructions and then the stable part of the packet as the
system prompt with the cache marker on the stable part, so the stable prefix is cached (cache reads are priced as the
cached part of the prompt); sends a tier's effort in the interface's own setting; sends a temperature only when the
account's `send_temperature` is on; and reads only the text blocks of the answer. A stop for the output limit is a cut-off
answer and a refusal stop is the refusal outcome (never retried inside the call: the app's own fallback chain decides).
Errors are classified from the status and the error body's structured type, never its words. The catalog entry names this
adapter and the service's base address without a version path; an account saved earlier keeps the adapter its own settings
name until the person re-adds it. *B-11c part 2c:* the model list's capability tree is read per model (the effort levels it
takes, and whether it can think on its own; nothing is read that the tree doesn't state), so a tier's effort is sent only
to a model whose listed efforts include it, and the connection test says in plain words when it was left out. A model
that thinks on its own gets the provider's `thinking_room` tokens added to a task's output limit, within its own limit,
since thinking counts toward it. A tier's `thinking: off` is applied only where the model's listed capabilities accept it at
the tier's effort, and otherwise the test says why not. **Built:** `tests/test_anthropic_messages.py`.

**A recommended setup per service, out of the box, and measured to stay current** (owner, 2026-10-21; *designed, B-11*).
A person who adds an account gets every tier filled in, so routine work never lands on an expensive model by accident:
- Three tiers: everyday, stronger and hardest. Each kind of work names its tier; most work is everyday.
- Each entry in the catalog of AI services (`catalog/ai-endpoints.yaml`, data) carries its preset: for each tier, a model
  family to look for among the models the service lists for the person's key, and an effort (low, medium or high).
  The catalog names families, never exact ids, so a newer model of the same family is picked up with no change; the
  preset takes the newest of the family (by the listing's release date, else the version in the id, else the list's
  order, `engine/ai/family.py`; `tests/test_family.py`); this
  is the one place a model's name carries meaning, and it is data, never code.
- Effort is set per tier (low, medium or high) and reaches the service only through the account's own setting for it:
  `effort_param` (the request field a chat-format service takes), `effort_option` (the arguments a command-line agent
  takes) or, for a native adapter, the setting its own interface documents. Each is set in the catalog only on a service whose own documentation confirms the parameter, so an unconfirmed
  service is never sent a field it doesn't know; a tier's effort is part of what its smoke test sends. Escalating may raise the
  effort on the same model before moving to a stronger one (with B-11b's measuring).
- Presets are written only for services whose model families are certain; the rest are filled by price until
  measuring, or the person, says better. *Built (B-11a):* `engine/ai/presets.py`, `tests/test_tier_presets.py`.
- With no preset match (a local server, an aggregator, a renamed family), the tiers are filled by price from the
  service's own model list, cheapest first, and marked not checked until the smoke test confirms them.
- Measuring keeps the defaults honest as models improve: from Settings, whenever the person asks, a small set
  of evaluation cases runs on the service's cheaper models at each effort (estimated first, a few cents), and the
  pair that passes for each tier at the lowest measured cost per passing answer becomes the recommendation, which the
  person accepts or not. Cost is measured, not read from the price list, because a higher effort writes more tokens: a
  low-cost model at high effort may or may not beat a stronger one at low effort, and only the run says which. A measurement older than
  the service's newest listed model is offered again.
- **A newer model is asked about, and moved to only by the person's setting, after a check** (designer, 2026-10-22;
  owner, 2026-10-22; change log 174 and 178; *built*, `tests/test_model_watch.py`, `tests/test_family.py`): the preset
  takes the newest model of the family, and setup asks nothing (owner, 2026-10-22); a check every `ai.models.check_every_days` days (default 7) lists each account's
  models and prices and keeps, per account, one Today line. "Newer" is one rule (`engine/ai/family.py`) shared with the
  preset: only a model of the tier's own family (the family word of the catalog's preset for the service) counts, and
  it is newer by the listing's own release date when every model of the family has one, else by the version in the
  model's id compared number by number (5.5 over 4.5, 10 over 9; a long run of digits is a date stamp, not a version),
  else the list's order, which never says a model is newer, so nothing is offered on it. The line says what it would
  change in cost per day at the current use (the last `ai.models.use_days` days of runs priced at the two models'
  prices, resolved as the router does: the price in the settings over the service's listing; a maintainers' price
  list fetched weekly comes with the release feed, phase I). With
  `ai.models.follow_newest` off, the line says it and offers **Switch** (the settings' own switch with its check) and
  **Not now** (kept until a different newer model, or price, appears). With it on (the default), a newer model whose
  price is known and the same or lower in and out is checked first on a copy of the settings (the check estimated
  first, and held for the person's go above `ai.budgets.confirm_above_usd`) and only a passed check writes the
  change, through the settings save; Today then says what moved, with the cost change, **Keep it** and **Switch
  back** (the earlier model, with Undo). A model that costs more, one whose price isn't known, a check above the
  amount, and a failed check never move a tier: the line says why, with Switch and Not now. A price rise on the
  tier's current model is a line of its own with the increase and no switch. A model of another family is never
  moved to. *Built, with the move's own tests:* `tests/test_model_watch.py`.
- **Thinking off** (*built*, `tests/test_anthropic_messages.py::test_thinking_off_is_sent_only_where_the_listed_capabilities_accept_it_at_the_tiers_effort`) is sent only to a model whose listing says it supports it; it is never inferred from a hand test.
- **Estimates learn from use** (*built*, `tests/test_estimate_calibration.py`, change log 175): when an account is
  checked, one token-count request per tier's model (for an adapter that can count without running; the adapter
  interface's optional `count_tokens`) gives the ratio of real tokens to the app's own count, kept with the account and
  model in the private folder; every run's reported usage then corrects it, with no extra call (a running average over
  `ai.estimates.calibration_runs`). An adapter whose program adds its own text (`adds_overhead`, the command-line agent)
  also keeps a measured fixed overhead per request (one run used about 12,000 tokens for a two-word request), taken from
  the check's small call and added to every estimate. An account that can't count and reports nothing stays at ratio 1.
  The native adapter counts through its service's own count request: the request's model, system prompt and messages,
  and nothing that only matters for a run (`tests/test_anthropic_messages.py::test_the_count_request_sends_only_what_is_counted_and_reads_the_input_tokens`).
  *Left:* the evaluation and switch estimates, which price a practice workspace with no kept measurements.
- **A saved account moves to a native adapter only on the person's yes** (*built*, `tests/test_native_move.py`, change
  log 176): an account whose address is a catalog service that names another adapter than the account uses (the
  account is on the generic connection) gets one Today line, "Move <account> to its service's own connection", with
  **Move** and **Not now** (remembered for the account; the line never comes back unasked). Move first shows what the
  new connection signs in as, from what is known without a call: the key (its last four characters, and plainly whether
  it is another key than the account uses now), the address, and the account's name. On the yes the account check (one
  call per tier and kind of work with its exact parameters, the learning round-trip) runs on the new connection; only a
  passed check writes the change, through the settings save, with Undo; a failed check, or no network, leaves the
  account as it was and says why. What the person set on the account stays; only the adapter, the service's own address
  and settings the account never set change.
- Where it shows (owner, 2026-10-21): setup asks nothing about tiers; adding an account loads its preset silently and
  setup says only that it is ready. Settings holds the rest: the three tiers in plain words with an estimated cost per
  day, each changeable, and "Measure", which offers the measured recommendation. The model's name shows only in
  Advanced.

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
includes the adapter's `sign_in_hint()` (its own login command or page), and never reaches any other path. A service that
no longer lets a program be used with the person's kind of account (`unsupported`, matched by the account's `errors.unsupported`
patterns) is a failure of the account, not of the work: it is never retried, falls to the next account in the chain like a
refused key, shows the account as failing, and says "pick another account, or use a key instead" in place of a sign-in hint,
since signing in again does not help.

**Exit 0 with no answer is a failure** (built: `tests/test_silent_stops.py::test_a_program_that_exits_cleanly_with_nothing_on_its_output_is_no_output_never_an_empty_answer`,
`test_an_empty_answer_file_and_a_missing_one_are_both_no_output`,
`tests/test_journeys.py::test_j8_an_agent_that_exits_cleanly_with_no_answer_is_retried_then_sent_to_me_and_never_done`).
Some agents exit 0 after printing a limit or sign-in message to their
output, with no changeset. That is its own outcome, `no_output` (nothing on its output, no answer file in the outbox, or an
empty one), never "done": it is retried, then counts toward the empty-run rule (8.6). A malformed answer stays
`invalid_output`, so the empty-run rule and the quality panel count the two apart.

**Probation for a new account** (*designed, not yet built*; the learning check with a switch is phase L, 6.22). A switch of a
tier's account or model offers to run the learning fixture pairs first, with their cost estimate. **A command-line agent's
program version is part of the account** (*phase L-more*): agents update themselves, and a new version can change flags, defaults or error
output under a passing smoke test. Built so far (L1b): the adapter reads the version (`agent.version_command`, default
the program with `--version`, within `agent.version_timeout_seconds`) and the evaluation report records it
(`tests/test_cli_agent.py`, `tests/test_evaluate_harness.py::test_a_run_through_a_command_line_agent_records_its_version_and_account`).
Still *phase L-more*: each `Run` records the agent's version; a version change is treated like an account
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
L-core*). Every case runs with the clock frozen at its own received time, on a fresh copy of the fictional workspace. A case
lists the ops it expects and, optionally, ops it forbids. The review found the set too easy in ways that would let a
low-cost model look as good as a strong one, so each case gains:
- **`received:`,** the date (or date and time with an offset) the input arrived, **built** (phase L0): every case has one, a case
  without one is refused, the harness freezes the clock there and the packet header states it, so a relative date ("by
  Tuesday") is tested against the input's own date (`tests/test_names.py::test_every_golden_case_carries_its_received_date_and_the_clock_freezes_there`,
  `test_a_case_without_a_received_date_is_refused`). An expected held name can say how many decisions it files (`count`).
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
until its reset (and the fallback takes over); it is not retried in a loop. **The pause** (built:
`tests/test_silent_stops.py::test_a_usage_limit_with_a_reset_pauses_the_account_and_it_is_not_called_before_then`,
`test_the_pause_is_kept_on_disk_so_a_new_process_still_honors_it`,
`test_a_fallback_account_takes_the_work_while_the_first_is_paused`,
`test_waiting_requests_resume_by_themselves_at_the_reset_without_anyone_pressing_anything`): a quota that comes with a reset
time, a request to slow down that asks for longer than `ai.rate_limits.max_wait_seconds`, or one that keeps coming after the
tries (then for `pause_seconds`), pauses that account until the reset. The pause is kept in the workspace's private folder, so it
holds across a restart. A paused account is not called; the router uses the next account in the tier's chain when one is allowed;
**Borrowing another tier's account asks first** (*designed, before real use*; the owner, 2026-10-14): most people have one
account and simply wait for the reset, but when the routine tier's accounts are all paused and another tier's account is
free, Today asks "Use <account> for routine work until <account>'s limit resets at <time>?" with the estimate. Yes lasts
until the reset and no keeps the work waiting; `ai.borrow_other_tier` (ask, never; default ask) can turn the question off.
A fallback the person put in the tier's own chain is their choice already and is not asked about. When none is, the
request stays queued, says "Waiting for <account>'s limit to reset at <local time>" (the account's name, never
a model), and the worker leaves it alone until then and runs it again by itself at the reset, with nobody pressing anything. A
limit with no reset time is not a pause: the request waits for the person ("out of credit"). Changing the accounts or tiers lifts
the pauses, since another account may take the work
(`tests/test_silent_stops.py::test_changing_the_accounts_lets_waiting_requests_try_the_new_setup_at_once`).

**A lost network is `offline`, and it waits** (built: `tests/test_ai.py::test_a_timeout_no_connection_at_all_and_a_broken_exchange_are_their_own_kinds`,
`test_a_service_that_answers_with_a_failure_is_down_not_offline`, `test_the_next_account_is_tried_when_one_has_no_connection`,
`test_every_account_without_a_connection_is_the_network_being_offline`,
`test_one_account_without_a_connection_and_another_refusing_the_key_is_not_the_network`;
`tests/test_silent_stops.py::test_a_lost_network_waits_without_counting_a_try_and_runs_when_the_network_is_back`,
`test_a_lost_network_never_reaches_the_person_however_long_it_lasts`, `test_a_service_that_is_down_still_counts_its_tries`,
`test_a_lost_network_is_one_today_line_after_the_configured_minutes_and_goes_when_it_is_back`,
`test_another_account_in_the_chain_takes_the_work_when_one_has_no_connection`;
`tests/test_journeys.py::test_j12_a_request_run_with_no_network_waits_for_it_and_runs_once_when_it_is_back`). `offline` means
no connection could be made at all: the name did not resolve or the connection could not be opened. Any answer from the
service, a 5xx included, is still `provider_down`, and a break after the connection was made stays `provider_down`. Only
the adapter decides it, from the kind of transport failure and never from text (the OpenAI-compatible adapter: a connect
error is `offline`, except when the account's own address is on this computer (localhost or a loopback address), where a refused connection means the local server is not running and is `provider_down`, decided from the configured address (`tests/test_ai.py::test_a_refused_connection_to_this_computer_is_a_stopped_server_not_a_lost_network`); any other transport error `provider_down`; the command-line agent adapter classifies from the exit
code and error stream and none of its errors says plainly that no connection could be made, so it does not use `offline`).
The router tries the next account in the chain on `offline`, since another account may be reachable. When every account
in the chain that is not paused is `offline`, the call ends in `NetworkOffline` and the request waits: it stays queued,
says "Waiting for the network since <time>. Checking again at <time>.", has the cause `offline` with `since` (kept from the
first time it found no network) and `until`, and **no try is counted** (`retries` is unchanged), so being offline never
uses up the tries a failing service gets and never brings the request to the person. The worker leaves it alone until
`until` (`dispatch.offline_check_seconds`, 60) and then tries again; it never loops. The first miss of a wait is a recorded run
with the error kind `offline`, so the history shows it; later looks of the same wait record none, until the request runs or the wait
ends another way (`tests/test_silent_stops.py::test_a_wait_for_the_network_records_its_first_miss_only_not_one_run_per_look`). Once a request has waited longer than `dispatch.offline_line_after_minutes` (60), Today's queue has one
risk line, however many requests wait, to check the network connection, with how many wait and since when; it goes when the
requests run again (7.7). **Being offline is never held against an account.** It pauses none (only a usage limit
does); it counts toward none being failing (a connection test that finds no network is inconclusive: its result isn't
kept and the last real result stands, and runs that found no network are left out when the latest run is read for a
refused key); and an answered run or connection test lifts any pause on its account, a usage-limit pause included,
since an answer shows the limit has lifted
(`tests/test_silent_stops.py::test_a_lost_network_pauses_no_account_however_often_it_is_found_and_whichever_account_is_cut_off`,
`::test_a_lost_network_never_makes_the_assistant_failing_or_hides_a_real_failure`,
`::test_a_connection_test_that_finds_no_network_is_not_kept_and_leaves_the_last_result_standing`,
`::test_a_successful_run_clears_a_pause_on_its_account_even_one_set_while_it_was_running`,
`::test_a_connection_test_that_is_answered_lifts_the_pause_on_its_account_and_a_failed_one_does_not`). While any request
waits for the network the header's status says "Waiting for the network" (after a lost live connection, before a
restart or a backup), and its popover gives the count and since when (`network_wait` of the status;
`web/src/shell/StatusMenu.test.tsx`, `web/src/shell/status.test.ts`, `tests/test_journeys.py::test_j12_a_request_run_with_no_network_waits_for_it_and_runs_once_when_it_is_back`).
**`cockpit evaluate` waits the same way** (`process_through_outage` in the dispatcher, which `evaluate`, `--pairs` and
`--replays` all use): a case, pair stage or replay stage that finds no network leaves its request in the wait above, with
no try used, so it fails nothing and is not counted as not run; the run prints "waiting for the network (no try is
used); looking again in 60s", pauses until the request's own check time and runs it again, and prints "the network is
back; going on". It never gives up by itself; the person stops it. *Built so far (batch B-7):* `tests/test_evaluate_network.py`
(a provider that goes offline and returns, for the dispatcher call, a case, a pair and a replay, with the pause injected,
no sleep).
**A run that did no work is not an attempt.** Besides `offline`, the error kind `no_work` is a run that ran and did
nothing: a command-line agent that failed with nothing on its error stream (only a banner or a sign-in prompt on its
output), whose error stream matches the account's `errors.no_work` patterns or whose exit code the account maps to
`no_work`, or that a signal ended; or a call that failed with a timeout or a break in the exchange while the computer was
asleep (the wall clock ran ahead of the time awake by more than `dispatch.sleep_gap_seconds`, 30). It is classified from
the exit code, the error stream and the clocks, never from the answer (an error stream with other words is still
`other`; a known sign-in or usage-limit pattern still wins). The router tries the next account on it. The request is no
attempt (`attempts` and `retries` stay as they were), nothing is sent back as a mistake and no fix round is used, the run
record has `no_work` true and no cost, and runs like it are left out of the day's counts and of whether an account is
failing. The request waits as a `retry` with `idle` counting the runs in a row, the wait doubling from
`dispatch.retry_wait_seconds`; after `dispatch.no_work_tries` (5) in a row it comes to the person saying how many times the
program started and did no work, and never quoting the banner (`tests/test_silent_stops.py::test_a_run_that_did_no_work_is_no_attempt_no_retry_no_fix_round_and_never_quotes_its_banner`,
`::test_runs_that_keep_doing_no_work_come_to_the_person_in_plain_words_after_the_configured_number`,
`::test_a_call_the_computer_sleeping_cut_off_did_no_work_and_a_slow_one_did_not`,
`tests/test_cli_agent.py::test_a_run_that_only_printed_a_banner_did_no_work_whatever_the_banner_says`). A network lost or a
run that did no work in the middle of a request's work (a fix round, a search call, the stronger tier's re-run, a draft's
continuation) is the same wait: the request goes back in line with no attempt used, the interrupted round's answer is not
filed or shown as a failure, and the next look starts afresh with every fix round still to use
(`tests/test_silent_stops.py::test_a_network_lost_in_a_fix_round_waits_for_it_and_the_outage_uses_nothing_up`,
`::test_a_network_lost_on_the_stronger_tier_waits_instead_of_ending_on_the_first_answer`,
`tests/test_drafts.py::test_a_continuation_that_finds_no_network_waits_for_it_and_files_nothing_yet`). No apply step reaches
the network (ops only write records, settings, rules and text), so there is no apply to wait for the network.

Notes and messages cost little; drafting work
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
- **A request's spending as a range** (designer F14; built in S1, `engine/dispatcher.py` `request_range`, `_Budget`): each
  dispatch estimates the whole request, low (one call on its tier) and high (every fix round and search round on that tier,
  and the same on the stronger tier when it may take over; a stronger tier with no price adds nothing). The go asks on the
  low figure as before and shows both ("About $0.04, at most $0.40."). All of a request's calls together are held to one
  amount: without a go, `budgets.confirm_above_usd`; with a go, what it had spent before plus the high figure, fixed at the
  first dispatch after the go so a retry doesn't widen it. A call the rest of that amount can't cover isn't made: the
  request stops with what it spent and waits for another go, which covers a fresh amount. Runs an outage cut off (no
  network, or a run that did no work) don't count. The finished item shows what it cost beside the range. A call whose
  provider reports no token counts has no known cost and counts nothing, as in the usage reports.

**Data handling.** Each provider has `allowed_data` levels. Inputs marked restricted only go to providers allowed to see them; if
none is, the request goes to the PM instead. Secrets come from secret references (Part 12), never from config files.

**Naming.** The assistant's display name is configuration and is the only name people see; vendor and model names appear only in
`config/ai.yaml`, the adapters, the usage reports and the evaluation reports.

**Replaying the real event** (functional designer's lessons from running, 2026-10-15; built, roadmap L7 (see roadmap-done.md)). Every
real miss becomes a replayable case: the starting records, the person's action through the same entry point the screen
uses (an edit, a move, a button), and the expected end state, scored on the records as they end up as well as on the ops.
Replays run in a throwaway copy, never the person's workspace, since Undo rightly refuses to roll back a record that has
changed since. Replayed misses are a third set beside the golden and harder sets. *As built* (`engine/replays.py`, which
documents the file format): a replay is a file in a workspace's `replays/` folder with its `skills:`, starting records,
setup inputs with fixed answers, the person's `action` (the same keys and the same code as a pair's correction,
`engine/pairs.py`), and the end state it expects: records that must be there (with exact counts), records that must not,
and signals the action must have recorded. A learning run the action queues is the account's (the stand-in answers from
`ideal`). `cockpit evaluate --replays` runs the set and adds it to the capability matrix as its own set. The shipped
replays are one per real miss: "Not a project" and "It's part of" each keep the person's own entry and queue no learning
run, a moved decision stays a decision, a question marked as already asked is filed as sent, and a calendar entry sent
back is undone with the work queued again. **Built:** `tests/test_replays.py`.

**Extras are weighed and tracked** (functional designer's answers, 2026-10-15; built, roadmap L7 (see roadmap-done.md)). Missing and forbidden ops stay exact. An op a case didn't expect is weighed
by its reach: a fact is free (a note is never counted); any other extra that stays inside the workspace (an action, a calendar entry, a question to the person, an extra
knowledge entry from a learning stage) costs 0.5; anything that reaches another person (a question to someone else, an
op of the outbound tier) fails the run. A run passes when nothing is missing or forbidden, no extra reaches another person
and the extras together cost no more than `ai.evaluation.extra_allowance` (default 1.0). An op kind a case lists in
`allow` weighs nothing. Each run carries its extras and their weight (`extra_weight`), shown in the report text and kept
in the report's JSON, so a case's `allow` list can't hide a trend. *Not built:* a view of the weight across saved reports.
Built: `tests/test_evaluate_harness.py::test_the_weighed_extras_must_stay_within_the_allowance`.

**Which sign-in an agent runs as** (designer's lessons, 2026-10-19; roadmap S1-3). A command-line agent that was never
signed in on its own can borrow another tool's stored sign-in, so runs go through an account nobody chose, with its own
allowance and its own data settings. The account check therefore reports the identity each agent runs as, read from the
tool itself (its own sign-in status command or log, through an adapter capability, so no vendor name leaves the
adapter), and Settings shows it beside the account. A change of identity between runs is a Today line ("The agent now
runs as <other account>: keep it or sign in again?"), and so is an identity that doesn't fit the data level of the work
it reads (a personal account on a work area). Until the person answers, runs that would reach a level the new identity
isn't allowed wait, as any run does with no allowed account. A tool that can't report who it runs as says so on the
account, never a guess. The same leak in the other direction is risk R14.

How it is built: an agent account's settings name the command (`agent.identity_command`) and where the account is in its
answer (`identity_field` for JSON, or `identity_line` with an optional `identity_pattern`); the adapter's `identity()`
runs it with the same allowlisted environment as a run and returns the account and how it was read, or "can't tell" with
the reason (no command set, a failing command, an answer without the account). Other adapters have no identity. The check
records the first reading in the workspace's private folder; a later check, or a run whose last reading is older than
`agent.identity_recheck_seconds`, that reads a different account keeps the recorded one and makes the Today line (Keep
records the new one, Sign in again opens the accounts screen, and a reading that is the recorded account again clears
it). While the line waits, the account takes open material only; work above that waits in line with its reason and "until
you answer", and goes after Keep. `identity_level` on the account names the levels the sign-in may see; work above them
waits the same way, with a line naming the levels and how much waits. An unreadable identity changes nothing recorded.
*Built so far (S1-3):* `tests/test_agent_identity.py`, `web/src/shell/HeldLines.test.tsx` (the Today line),
`web/src/components/AiAccounts.test.tsx` (Runs as, Can't tell). *Not built:* an account that borrows work for another tier
(6.16, borrowing) still reads only the account's allowed levels, not its identity's.

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
- **The person's role on each project decides what is tracked** (*designed, phase E*; the original designer's lessons from
  running, 2026-10-14). A project carries each person's role on it: they **run** it, they **design** for it, or they only
  **watch** it (per person id, so an organization install, 11.8, works the same). The resolver reads that role, not a
  global list: on a project the person runs, another team's blocking defect is a risk and an action, not a parked note. "I'm
  running X now" or "they want me to PM X" in any input or note proposes the role change as a system op the person
  confirms, and it takes effect that day. A learning pair proves it (roadmap L4, see roadmap-done.md). **A slice comes before real use** (the
  original designer, 2026-10-14; the rest stays in phase E): the role and its proposal; on a project the person only
  watches, facts only (no actions, no questions to other people), enforced by the applier from the role; and another
  team's item on any project is a fact unless the input says the person owes them something. *As built (the slice,
  2026-10-15):* `Project.roles` and `project.role` (system tier; a project with no role for the person is one they run);
  the lints `watched-project` and `other-team-item` (default `return`; returned once, then held and never applied even
  when the item reaches no one); "the person owes it" when the quote names the person or their team or holds a word in
  `language.owed_words`; the person's own note is exempt from both; the packet's project list says the person's part
  when it isn't "run". **Built:** `tests/test_scope_slice.py`. **Who owes what, revised** (functional designer's answers, 2026-10-15; the words are built, roadmap L7 (see roadmap-done.md)): "we", "us"
and "our" are usually the sender's own team committing to something, which is not owed to the person; what is owed is a
request addressed to them ("you", "your team", "please send", in `language.owed_words`, or their name or their team's
followed by a request word, `language.request_words`). Built: `tests/test_scope_slice.py::test_a_quote_that_addresses_the_person_is_one_the_person_owes`.
*Not built:* a person with no team still counts as outside, and is to be asked about once ("Which team is <name>
on?") rather than guessed; today nothing is asked.

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

**How a fact is known** (functional designer's lessons from running, 2026-10-15; roadmap L7 (see roadmap-done.md), *partly built*). Every fact
says who it rests on, with its source: the person said it, the assistant inferred it, or someone else said it (named).
The person's own deduction is recorded as their inference, and a question it settles closes with that as the reason.
When the person says they asked someone directly, the question is filed as already asked, so the reply has a place to
land. What the assistant writes about a change says who made each part of it: the person's edits are never described as
the assistant's, nor the other way round. **An inference only feeds the record** (functional designer's answers,
2026-10-15): it applies at once, marked inferred, but never goes on anything others see and never changes a date, an
owner or a routing on its own. It never closes a question or an action either: it proposes the close ("this looks
answered by <source>: close?"), which one click confirms. The person's own deduction closes it, recorded as theirs.

*As built:* a fact record has `basis` (`person`, `inferred` or `said`, empty on a fact recorded before this) and
`said_by` (the person's id when someone named said it). The `fact` op takes `basis` (`inferred` or `said`, with
`said_by`) and leaves it out when the input's origin says it: the person's own note is `person`, and content from
outside is `said` by its sender (nobody named when the input doesn't give one known person). The applier holds, with
a plain reason and `inference-confirm` as the check, an `action.close`, a `question.done`, a `record.set` of a due date,
target, owner or owners, and a `routing.add` that rests only on an inference: an op rests on a fact of the same changeset
when the words it quotes and the fact's quoted words overlap, and only on an inference when every fact it shares words
with is inferred. Releasing the hold is the person's one click; the person's own acts and a confirmed op are never held.
"I asked them to confirm" in the person's own note files the question as already asked: `question.mark_sent` is offered to
reading notes and applies only when the input is the person's own note. **Built:**
`tests/test_fact_basis.py::test_a_fact_from_the_persons_note_rests_on_the_person_and_one_from_outside_on_its_sender`,
`::test_the_model_can_mark_a_fact_inferred_or_name_who_said_it`,
`::test_a_close_that_rests_only_on_an_inference_is_held_with_a_plain_reason_and_one_click_closes_it`,
`::test_a_close_that_rests_on_something_said_or_on_the_persons_own_note_applies_at_once`,
`::test_a_date_an_owner_or_a_routing_resting_only_on_an_inference_is_held`,
`::test_a_note_saying_the_person_already_asked_files_the_question_as_asked`,
`::test_the_notes_prompt_says_when_a_fact_is_inferred_and_when_to_mark_a_question_asked`.
*Not built:* keeping an inference off anything others see (the outbound filtering lands with the publisher, phase C4);
the mark on screen; the person's deduction recorded as theirs with its reason on the closed question; and the change
note saying who made each part.

**A correction, not a second fact.** An answer that contradicts a recorded fact replaces it (`supersedes`, which quotes
the old fact), and the records that repeated the old fact are asked about by a follow-on run, which never edits them (6.7). A follow-up
question goes to whoever made the claim or owns the thing it is about; when neither is clear, it is a question to the
person about who to ask, never a guess from a passing mention. **Built:** the prompt rule and the golden cases
`follow-up-goes-to-who-made-the-claim` and `follow-up-with-no-clear-owner-asks-who`
(`tests/test_obvious_steps_f.py::test_the_prompt_says_a_follow_up_goes_to_the_claims_maker_or_owner_and_otherwise_asks_who`).

**Adding a record from a link** (designer's lessons, 2026-10-19; roadmap B-6a, C4). "Track this as a project, from
<link>" reads the link before anything is added, through whatever configured source can read it: its status, what
shipped and its dates, each as a fact with its evidence. Something the source says is finished isn't new work: it is
added with those facts, and the person is asked whether to mark it complete. A status nobody stated stays unknown,
never "not started": status is an evidence field, so a status with no words behind it is refused, by `record.set` and by
`project.add` (its `status` takes the words that state it as evidence, from the assistant; the person's own screens need none,
and a status the value list lacks is refused). When no source can read the link, the add says so ("Not read: nothing set up
can open this link", `language.messages.link_not_read`) instead of filling the record from the link's text alone:
`project.add`'s `link` is kept as a link on the project labeled so, the held row shows the same line (`OpMeta.note`), and a
source that reads addresses on the link's host (`engine/projects.py::source_for_link`) makes it an ordinary link. **Built:**
`tests/test_forms_b6a.py` (a status with no words, a quote not in the input, a stated status that waits and is kept, no status
left unknown, a status the list lacks, a link nothing can open, a link a source reads, the held row's note),
`web/src/components/NextSteps.test.tsx`. The full lookup of a system of record is phase C4's fact lookups.

## 6.20 Quality signals

The PM's corrections are the best measure of whether the assistant is doing well, and the best source of test cases. Each one
is recorded as a `signal` record (5.1) at the moment it happens (the recording is built; the quality panel, private evaluation
cases from signals and rule suggestions are *designed, not yet built*). Each signal names the **changeset** it corrects and the
**run** that made it, when there was one (L1: a send back, an undo and a routed answer set both; the run is the changeset's own).
A correction of something no run made leaves both empty: putting an action on hold or taking it off, a mail item set aside by
hand, an automatic close pulled back, and an edited follow-up message (a draft the rules build). **Built:**
`tests/test_rules_facts_signals.py::test_sending_back_and_undoing_name_the_changeset_and_its_run`,
`tests/test_rules_facts_signals.py::test_saying_who_a_name_is_names_the_changeset_and_its_run`,
`tests/test_rules_facts_signals.py::test_a_correction_of_something_no_run_made_leaves_run_and_changeset_empty`:

| Signal | Recorded when |
|---|---|
| sent back | the PM sends a changeset back, with the note |
| undone | the PM undoes a changeset or part of one |
| dropped / reworded | the PM drops (the note is the reason) or rewords (the note is the old and new wording) a question the assistant filed. Refs: the question; the changeset and run that made it. Undoing the correction leaves the signal and records none. **Built**: `tests/test_corrections.py::test_reword_changes_the_question_records_a_reworded_signal_naming_its_run_and_undo_restores_it`, `tests/test_corrections.py::test_drop_keeps_the_question_with_its_reason_records_dropped_and_undo_opens_it_again` |
| change requested | the person asks for a change to something the assistant made, with a note on its row ("Change this": an action, question, decision, calendar entry or fact). Refs: the item; the changeset and run that made it, when there was one; the note is the person's words. The note also goes to the assistant as the person's own input about the item. **Built**: `tests/test_corrections.py::test_change_this_records_a_signal_and_queues_a_notes_request_whose_packet_carries_the_item_as_it_is_now` |
| pulled back | the PM pulls an auto-closed change back ("This is ours") |
| set aside | the person sets a mail item aside by hand ("Set aside: personal" or "Set aside: sales", 6.5). Refs: the requests closed by it, or the snapshot when none was waiting; the note is the section, and says when a sorting rule was offered for the sender. Undoing it records no signal, and learning never reads anything marked set aside (6.5). **Built**: `tests/test_set_aside.py::test_set_aside_by_hand_records_a_set_aside_signal_and_putting_it_back_records_none` |
| draft edited | the approved content differs from the assistant's draft (the difference is kept). Refs: the person the message was for, then the ids of the questions it covered; when those all came from one run, that run and its changeset (otherwise both are empty). **Built**: `tests/test_corrections.py::test_an_edited_message_names_the_question_ids_and_the_run_that_wrote_them`, `tests/test_corrections.py::test_an_edited_message_over_questions_from_different_runs_or_none_leaves_the_run_empty` |
| held op declined | the PM declines a held system op or a routing guess, or answers a held line's question with the other answer ("Keep it open", 7.6). Refs: the changeset and the record the op was about. Undoing the decline nets the signal out. **Built:** `tests/test_held_ask.py` |
| routed | the person said who a name or an owner is, answering "Who is X?" or "Pick an owner" (refs: the changeset, the question, the person chosen; the note is the name as written), or asked someone else about a question (`question.move`; refs as above; the note says from whom to whom; undoing it leaves the signal). Undoing the person's own release of a held op records no signal: it is their decision, not the assistant's work. **Built**: `tests/test_pipeline.py::test_saying_who_a_name_is_and_picking_an_owner_each_record_a_routed_signal`, `tests/test_pipeline.py::test_undoing_a_release_records_no_undone_signal_but_undoing_the_assistants_work_does` |
| put on hold / taken off hold | the person puts an action on hold or takes it off (refs: the action; the note is what it waits for). Undoing either records no signal. **Built**: `tests/test_on_hold_and_follow_ups.py::test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date`, `tests/test_on_hold_and_follow_ups.py::test_a_hold_needs_words_and_an_open_action_and_undoing_it_records_no_signal` |
| just this time | the person says a proposed piece of learning is right for this case but is not a pattern (7.18). Refs: the entry; no note. The entry is discarded with that as its reason and nothing replaces it; a repeat of the same correction is shown with how many times this was said. Undoing records no signal. **Built**: `tests/test_proposals.py::test_just_this_time_records_its_signal_discards_and_the_repeat_is_marked` |
| not now | the person says "Not now" to the rules review line (6.22). Refs: the rules flagged then (none when only rules moved out of the always-sent part); no note, run or changeset. Not a correction: it starts the line's week and nothing learns from it. Undoing records no signal. **Built**: `tests/test_rule_review.py::test_not_now_route_records_a_signal_names_the_flagged_rules_and_changes_no_rule` |
| kept / discarded / retired | the person keeps or discards a proposed piece of what the assistant learned, or retires an active one (6.22). Refs: the entry; no note (a discard's reason stays on the entry). Undoing records no signal. **Built**: `tests/test_knowledge_records.py::test_keep_with_an_edited_text_makes_it_active_and_the_person_its_author`, `tests/test_knowledge_records.py::test_discard_keeps_the_proposal_with_its_reason_and_undo_brings_it_back`, `tests/test_knowledge_records.py::test_retire_ends_an_active_entry_and_undo_makes_it_active_again` |
| edited | the person changes a field the assistant set (a fact, an owner, a due date, an item's project, a question's wording before it is sent). The ledger shows who set each field, so this needs no AI. A silent correction, learned from in the batch. *As built:* an edit through `record.edit` or `record.set` of an action's text, due, owners or project, a question's title, text, recipient, stake or project, a fact's key, value, date or project, or a calendar entry's title, dates or project, or a note's project, whose previous value the assistant set, records one `edited` signal per record naming the change and run that set it; a record another signal of the same change already names is left alone. A question's project is its `projects` list (the field was named `project`, which a question doesn't have, so filing a question under a project recorded nothing; fixed with the Unfiled group, 7.14). **Built**: `tests/test_hold_drop_fold.py::test_the_persons_edit_of_what_the_assistant_set_is_an_edited_correction_that_queues_learning` |
| answered the assistant | the person writes an answer to a question the assistant asked them. Refs: the question; its changeset and run. Learned from at once. A bare confirmation, or an answer about someone else, records none. **Built**: `tests/test_learn_input.py::test_an_answer_to_the_assistants_question_records_a_signal_and_queues_learning_at_once` |
| repeat correction | any of the above except a drop (work no longer needed says nothing about the assistant; drops, misses and declined changes are counted apart, below), on a run whose knowledge log (6.22) shows it was given an active lesson or rule whose target matched the corrected item: its task kind, record type, filter and project (with ancestors). Not a record: computed from the signals and the log. Corrections the person took back, corrections of something no run made, and Keep, Discard, Retire, Narrow and "Just this time" don't count; an entry with no target never counts as repeated. **Built**: `tests/test_quality.py::test_a_correction_repeats_only_when_the_run_was_given_knowledge_whose_target_matched_the_corrected_item` |

The repeat-correction rate, not the raw correction rate, says whether the assistant is learning; the quality panel shows it
next to the others, week by week. Refusals are counted per check too, and a check that refuses often brings its seed
lesson into the packet (Part 8, guard kinds). Beside the repeat-correction rate, the **knowledge-used rate**: the share of runs whose changeset says which
lessons, rules or facts it applied (`applied`, a list of knowledge ids). Each id is checked against the knowledge the run was
given, so it is a checked citation, not the model's say-so. If the first rate doesn't fall, the loop isn't closing; if the
second stays near zero, the knowledge isn't reaching the runs that need it. *As built,* `GET /api/quality` reports both
per task kind over `knowledge.quality_window_days` (28), the repeat-correction rate per week only for weeks with at least
`knowledge.min_corrections_per_week` (10) corrections, and the weekly missing-op list from each changeset's `missing`
(6.13); only the run that produced a changeset counts. The screen is phase B's. **Built:** `tests/test_quality.py`. Missed, declined and dropped are also reported each on its own (`apart`, window and weeks), so a week of drops never reads as a week of misses: **built:** `tests/test_quality.py::test_the_quality_route_gives_missed_declined_and_dropped_apart`. Each signal also starts the learning step (6.22): rates measure the assistant, and proposals teach it.

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

*Partly built: the records, their ops and Keep, Discard and Retire (phase L1) are built; packets that read them (L2) are built; the rules for proposals (L3p: rules as proposals, duplicates, near-discards, "just this time", expiry, the one Today line and the catch-up list) are built; learning from corrections (the `learn` task kinds) and the screens are designed, not yet built* (roadmap: the loop in phase L-core, next after phase A, after which real use starts; Ask's
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
- **Fact** (built), plus `key` (the facts that matter most, always shown first), `as_of` and `supersedes` (L1, built; below).
- **Rule** (4.10), now a record (L1, built): `rule.add` and `rule.retire`, system ops with Undo, and the rules file as the
  starting set. Retiring one records the same `retired` signal as any other knowledge (built). *From L3* (the original
  designer, 2026-10-14), a rule from the assistant, an input or reported content is a proposal kept or discarded on the
  Learned line like the other kinds, and Keep shows the restatement the person agrees to; a rule in the person's own
  words still applies at once with Undo. The held rule decisions on Today move to the catch-up list once, when L3 starts.
  **Built in L3p:** `rule.add` is one of the ops that add as a proposal (`KNOWLEDGE_ADD_OPS`), a `rule` record has the
  statuses `proposed`, `active`, `discarded`, `expired` and `retired`, the origin `input`, `trust`, `discard_reason` and
  `more_evidence` like the other kinds, and `engine/catch_up.py` moves the held decisions once. Built:
  `tests/test_proposals.py::test_a_rule_from_an_input_is_a_proposal_and_from_the_persons_note_is_active_with_undo`,
  `tests/test_proposals.py::test_held_rule_decisions_move_once_to_the_catch_up_list_and_running_twice_moves_them_once`.
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
- a status: proposed, active, discarded, expired or retired (distinct states, 5.1);
- the same structured target that rules have (`applies_to`: task kinds, record types and fields, projects, people, and a
  filter).

Ids matter: a fixture, a rule promotion and a later correction can each point at the exact lesson. Entries change only
through ops (`lesson.add` and `lesson.update`, `glossary.add` and `glossary.update`, `routing.add`, `style.add`, `rule.add`,
`fact`, and `retire` for any kind), so every change is in the ledger with Undo.

**Built in L1** (`tests/test_knowledge_records.py`): the four kinds below as core records, their ops and the person's acts on them. Nothing reads
them into a packet yet (L2), and no task kind proposes them yet (L3). The facts' `key`, `as_of` and `supersedes` and
rules as records are separate L1 items, not built here.
- **The records** `lesson` (LES), `glossary_entry` (GLOSS), `routing_entry` (ROUTE) and `style_note` (STYLE) share one
  base (`KnowledgeRecord`, `engine/records.py`): `text` (the restatement, in plain words), `evidence` (`quote`, `source`,
  `request`, `signal`, `changeset`, kept apart from the text), `origin` (`person`: the person's own words; `input`:
  proposed from content; `assistant`: its own generalization; `pack`, with `pack` naming it; `seed`; `import`), `trust`,
  `learned_at`, `status` (proposed, active, discarded, expired, retired), `discard_reason`, `kept_by`, `kept_at` and
  `applies_to`. An active entry always says who kept it and when. Their level is internal, as a fact's, and `origin`,
  `pack`, `trust`, `learned_at` and `evidence` never change after the entry is made, even by the person's own edit.
  Own fields: a lesson's `guard` and `signal`; a glossary entry's `term`, `meaning`, `confidence`, `project` and
  `id_patterns`; a routing entry's `topic`, `person` or `team`, `negative` and `look_up`; a style note's `audience` and
  `observation`. Built: `test_the_four_kinds_are_core_records_with_their_own_fields_and_one_shape`,
  `test_a_record_that_contradicts_itself_does_not_validate`.
- **Scopes with exclusions.** `applies_to` is the shape rules use (`task_kinds`, `records`, `filter`) plus `projects`,
  `people`, `scope` and `except`. `scope` is `workspace` (everywhere, less the projects in `except`: a rule that holds
  everywhere but one program needs no copy on every other project) or `projects` (only those listed; naming projects
  without a scope means this). It is stored and shown with the key `except`. `task_kinds` and `records` name only kinds
  of work and record types the workspace has (plugins' included; a record target may be `type.field`): anything else is
  refused with the list, and the op reference lists them, since a reach naming something that doesn't exist would apply
  nowhere, silently. Built: `test_a_reach_names_only_kinds_of_work_and_record_types_there_are_and_says_which_there_are`,
  `test_naming_projects_makes_the_scope_those_projects_and_except_is_its_own_key`,
  `test_everywhere_except_a_project_round_trips_through_the_record_the_api_and_the_export`.
- **The ops** `lesson.add`, `lesson.update`, `glossary.add`, `glossary.update`, `routing.add`, `style.add` and
  `knowledge.retire` (any kind, named by its id), all system tier, each with Undo. What an add does follows who it
  comes from: from the person's own words (the rule for system ops, above) the entry is **active at once**, with the
  person as `kept_by` and `origin` `person`; from anything else it is added as a **proposal** (`proposed`, with
  `origin` `input` for content, including a note typed on an item's button, or `assistant` for the assistant's own
  initiative) and is *not held*: it is a record the person can Keep, and it changes nothing until kept. An update or a
  retire is held like any system op unless it comes from the person. An update changes a proposed or an active entry, a
  retire only an active one, and what an op names (projects, people, the signal) must exist. Built:
  `test_each_add_and_update_op_makes_and_changes_its_record`,
  `test_an_update_names_something_and_only_changes_what_is_proposed_or_active`,
  `test_a_lesson_from_the_persons_own_words_is_active_at_once_and_from_an_input_it_is_proposed`,
  `test_changing_or_retiring_an_active_entry_from_anyone_but_the_person_waits_for_them`,
  `test_the_evidence_is_kept_apart_from_the_wording_and_names_where_it_came_from`,
  `test_what_an_op_names_must_exist_and_the_scope_must_hold_together`,
  `test_undo_of_each_op_takes_the_change_back`. Reading notes and a plugin's actions are not offered these ops
  (`test_the_learning_ops_are_neither_offered_when_reading_notes_nor_to_a_plugins_action`); the work that learns
  will be (L3).
- **Keep, Discard and Retire** (`POST /api/knowledge/{id}/keep`, `/discard` and `/retire`, each stating the version
  read). Each acts at once with Undo (the change it makes), records a `kept`, `discarded` or `retired` signal (6.20; undoing
  records none) and refuses an entry in the wrong state. Keep makes a proposal active with the person as `kept_by`; the
  wording or target the person changed in the same call is their own wording (12.8). Discard keeps the proposal with the
  reason if one is given. Keep and Discard are the person's own `record.edit` of the entry's fields, so they apply as
  theirs and undo like any edit. Built: `test_keep_with_an_edited_text_makes_it_active_and_the_person_its_author`,
  `test_only_a_proposal_can_be_kept_and_where_an_entry_came_from_cannot_be_edited`,
  `test_discard_keeps_the_proposal_with_its_reason_and_undo_brings_it_back`,
  `test_retire_ends_an_active_entry_and_undo_makes_it_active_again`, `test_keeping_needs_the_person_to_be_known`.
- **Provenance.** `GET /api/knowledge` (filters `kind` and `status`) lists entries newest first with `origin`, the same
  "where it came from" link as an action's (`engine/origin.py`: the page, else the saved text of the input the evidence
  cites, else the change and request that made the entry). The record's own `origin` is the view's `learned_from`. No
  screen shows it yet (7.18, L3). Built: `test_the_list_filters_by_kind_and_status_and_carries_each_entrys_own_fields`,
  `test_the_origin_of_an_entry_is_the_page_else_the_saved_text_else_the_change_and_its_request`.
- **Export and import.** Every kind is written and loaded back like any record (5.0). Built:
  `test_every_kind_of_knowledge_is_in_the_export_and_loads_back`.
- **Not built, left for later phases:** the Learned line and the review screens (L3, 7.18), `promoted` for a lesson, and a
  pack's or a seed's entries (L-more). Duplicate merging, the discard hold and the `expired` sweep are built in L3p (below);
  the knowledge section of packets and its log are built in L2.

**The knowledge section of every packet** is split so the cached prefix stays the same from input to input (6.6):
- **In the stable part,** after the playbook and before the open items:
  1. every active rule that applies to the whole workspace (they are few, and most failures were a rule the run never
     saw); a rule narrowed to some projects or task kinds goes in the per-input part, so scope is filtered when the
     packet is built and never left to the model: an excluded project's rules (`except`) are not in its packets at all,
     and the knowledge log says which were left out (built in L2, `engine/knowledge_section.py`; the original designer,
     2026-10-14);
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
- a `fact` has an optional `supersedes` (the id of the fact it replaces; built in L1, and fixed once the fact is made). The
  older fact is never edited. What replaced it is computed from the newer fact (`engine/facts.py::superseded_by`), so undoing
  the newer fact brings the older one back with no second write to undo, and the two can never disagree. A fact can be replaced
  once: a replacement that names a fact already replaced, or one that doesn't exist, is refused with the reason;
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

A pack's own task kinds get the same section through one plugin API call (built in L2: `view.knowledge(text,
projects=...)` returns `KnowledgeParts(stable, per_input)`, placed by the pack and logged on its run like a core packet's;
`learning: own` is declared on a record type or a task kind, and `engine/learning.py::learns_on` tells each learning step
whether to run). **A scope that names a project covers its child projects** at any depth, for `projects` and `except`
alike (built in L2); facts stay per exact project. So a writing pack's runs see the person's lessons and
glossary, and a pack's own knowledge (a series bible) can be offered the same way later.

**The always-sent section has a size budget** (built in L2 except the weekly line; the original designer, 2026-10-14). Its size is in
the knowledge log on every run from the first L2 commit, so the budget's default comes from real numbers. Over the budget,
rules leave it narrowest first: those scoped to one project or one task kind before those scoped to several, and
workspace-wide rules in the person's own words last. A rule a stage check enforces sends only its one-line form there and
its full text in the per-input part for the runs it covers, since the check does the enforcing. Nothing is dropped
silently: "Review your standing rules" shows at most once a week, with the section's size and the count of rules moved.

**What a rule constrains, and whether it applied** (built in L2, `engine/rule_use.py`, `engine/rule_review.py`; the
screen for the review is L3's; the original designer, 2026-10-14). A rule is flagged only after a whole review period
since it was learned or last kept, so Keep starts the count again; the line's weekly clock is the last time the person
kept, narrowed or retired a rule. **"Not now"** on the line also starts its week (functional designer's answers, 2026-10-15), so the person never has
to decide something to make it go away. *As built:* `POST /api/knowledge/rules/review/not-now` records a `not_now` signal
(refs: the rules flagged then; no run or changeset; it is not a correction and learning never reads it), and the line's
clock counts it like a Keep, Narrow or Retire. **Built:**
`tests/test_rule_review.py::test_not_now_starts_the_lines_week_without_deciding_anything_even_when_only_rules_moved`,
`::test_not_now_route_records_a_signal_names_the_flagged_rules_and_changes_no_rule`,
`web/src/shell/HeldLines.test.tsx`: "Not now on the rules review puts it off for its week and the line goes". A rule
says what it constrains (`constrains`): the op kinds or fields it is about ("questions to someone", "an action's owner",
"a due date"), or the check that enforces it. For each run in its scope the knowledge log records it as **applied** when
the run produced an op or field it constrains, or its check ran on that output (passing or refusing), or a correction
names it; otherwise as **present**. Both are checked without asking the model; the model's own "I applied rule X" may show
as a hint on the evidence line and is never counted. A rule present but not applied for `knowledge.rule_review_days` (30)
is offered for review on the weekly card, most-present first, with Keep (resets the clock), Narrow and Retire. A rule
enforced by a code check or an invariant is never flagged: the check holds it whether or not anything triggers.
**Checks on every output** (functional designer's answers, 2026-10-15; built, roadmap L7 (see roadmap-done.md)): a rule with a check runs it on every run's output in its scope, not only
on stage moves, so a checked rule counts as applied each time. *As built* (`engine/rule_use.py::record_applied`, `engine/stages.py::output_check_ran`): once a
run's changeset is applied, each active rule the run was given that names a code check has the check run on every record the changeset's applied ops wrote
(as the records are then) that the rule's scope covers (`task_kinds` names the run's kind of work or is empty, `records` and `filter` take in the record, the
same test a stage entry uses), and the rule is counted as applied on the run's knowledge log whether the check held or not (6.22: "passing or refusing"). A
rule whose scope covers nothing the output wrote stays present. **Before the change applies** (phase S1, 2026-10-19;
`engine/rule_use.py::failing_rules`, `engine/applier.py`): the applier's trial apply runs every active rule's check on
what each op would write, as it would be written (earlier ops of the same changeset applied), when the rule's scope covers
the record and the run's kind of work. A failing check goes back to the assistant once with the rule's words and the
check's reason; if the answer still fails, the op is held for the person whoever the item reaches, with the same words
as its reason, and an outward act is refused. The write itself checks again, so nothing that breaks a rule is kept even
if records changed in between. A change the person makes or confirms (a person action, a release from hold) is theirs
to make and isn't stopped by their own rule. A rule whose check stopped an op counts as applied on the run. A check that
is missing or turned off fails, as a stage entry check does. **Built:** `tests/test_rule_output_checks.py`,
`tests/test_rule_check_before_apply.py`.

**Search before asking.** A run that needs more than its packet holds asks for it with a `search` request: words, ids, a
project, which kinds (facts, past inputs, records, knowledge). It is not a live tool call, so it works on every kind of AI
account, command-line agents included. The engine runs the search, deterministically and bounded (`knowledge.search_results`),
and runs the task again with the results, at most `knowledge.search_rounds` times (default 2). The instructions say to search
the workspace's own knowledge before an outside lookup (6.19), a question to a person, or a report to the maintainers.
**Local first** (built in L2, `engine/search.py`; the original designer, 2026-10-14): the search round runs over records, facts and
past inputs before any outside lookup is proposed, and an outside lookup from a run that hasn't searched is sent back to
search first, so no run looks outside for items that never existed.

It is also checked where it can be. A `question.add` to anyone (the person included), an outside lookup or a `report.draft` whose subject a plain search
already answers gets the lint `already-known` (4.17), which sends it back once with the match. It is a lint, not an invariant,
because matching is fuzzy. The plain check reads facts and active knowledge; the run's own search also reaches past
inputs and records. A search answer is its own shape (`search`: words, ids, project, kinds); a search uses no fix round
and no try, is estimated and recorded like any call, and results from an outside input make the work untrusted (built:
`tests/test_search.py`).

**Seed lessons and refusals** (built in L2). Each invariant has a one-line constraint printed under the ops it
constrains in the op reference, and a seed lesson (`engine/defaults/invariants.yaml`); the self-check fails for an
invariant without a line. Refusals are counted per check over a task kind's last runs, including those a fix round
repaired (logged on the run as `refused_checks`); a check whose share reaches `knowledge.refusals_to_packet.share`, once at
least `min_runs` runs are counted, brings its seed lesson into the stable part, marked as the product's own guidance.
**A floor for rare work** (functional designer's answers, 2026-10-15): the same check refusing a kind of work's runs
`knowledge.refusals_to_packet.floor` times (3) within `floor_days` days (7) brings its guidance in whatever the share and
however few runs are counted, since a rare kind of work never reaches the minimum runs quickly. A check counts once per
run. **Built:** `tests/test_refusals.py::test_the_same_check_refusing_the_floor_times_in_its_days_brings_its_lesson_whatever_the_share`,
`::test_the_floor_counts_runs_of_the_same_check_within_its_days_only`,
`::test_a_check_counts_once_per_run_for_the_floor_and_the_floor_is_a_setting`,
`::test_a_packet_carries_the_floored_lesson_and_logs_it`.

**From the functional designer's answers** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7 (see roadmap-done.md)):
- **Terms by audience.** On the person's own list the assistant keeps their shorthand with the meaning beside it the
  first time ("Approve the HLP (Harrowgate layout proof)"); in anything that goes to others, the meaning comes first and
  the term only if the reader uses it. A term nobody has defined stays unknown, never guessed.
- **Outside mail never re-routes work.** Content from outside never proposes routing work away from the person, and never
  proposes that the person doesn't answer something. A mail asking to take over a kind of decision becomes a fact
  ("<sender> asked that cover finish decisions go to them") and one decision to the person ("<sender> asks to take cover
  finish decisions. Keep them with you, or change?"). A sender's own "not me, ask <name>" is still proposed as routing.
- **Discarded means don't act on it.** Search still returns an input whose proposal was discarded, flagged ("routing
  proposal discarded on <day>"), and a check refuses routing that matches a discarded proposal unless the person's own
  words support it. **Built:** only a discard the person made counts (not "just this time", not one held back as close
  to an earlier discard); a routing matches when it names the same person or team, says the same (who does, or doesn't,
  answer) and its topic shares at least `knowledge.routing_match` of the discarded topic's words; the invariant is
  `discarded-routing` (`tests/test_proposals.py::test_search_flags_an_input_whose_proposal_was_discarded_but_not_one_kept_or_set_aside`,
  `::test_a_routing_that_matches_a_discarded_proposal_is_refused_unless_it_rests_on_the_persons_words`).
- **The catch-up learns from the person's words** when a kind's corrections hold some, else from the newest.
  **Built:** a correction holds the person's words when its kind's note is theirs (`catch_up.THEIR_WORDS`: a send-back,
  a change requested, an answer, a reworded question, a message as they used it) and the note isn't empty
  (`tests/test_catch_up_learning.py::test_a_kind_is_learned_from_through_the_newest_correction_that_holds_the_persons_own_words`).
- **A fact for a whole series.** A fact on a parent project can be marked as applying to its children, and then reaches
  their runs; other facts stay with their exact project. **Built:** the fact's `reaches_children` (the `fact` op sets it,
  and it needs the project); a run for a project at any depth below gets the marked facts of the projects above it in
  its facts section (`tests/test_knowledge_section.py::test_a_series_fact_marked_to_reach_its_children_goes_into_their_packets_and_no_other_fact_of_a_parent_does`,
  `tests/test_fact_basis.py::test_a_fact_marked_to_reach_the_projects_inside_its_own_is_kept_so_and_needs_its_project`).

**The knowledge log.** Each `Run` records:
- which knowledge entries it was given, by id, and for each rule whether it was applied or only present (above);
- the size of the always-sent section, and the rules left out by scope;
- how many facts were left out;
- what it searched for and what came back.

A bad result can then be traced to knowledge that was missing (not in the packet) or ignored (in the packet, and the answer
went against it). The repeat-correction signal (6.20) is computed from this log.

**A lesson's projects are the correction's own** (*built, B-10:* `tests/test_learn_correction.py`
"a_lesson_kept_for_a_project_the_correction_never_touched…", "a_lesson_may_reach_a_project_the_persons_own_words_name"):
a learning entry limited to projects may name only those the corrected work belongs to (the project it was handed in to,
its source's, its ops' and its records') or one the person's words name; any other goes back once. A check on a low-cost
model found lessons about work filed nowhere kept for an unrelated project, so they never reached the next run.

**Every correction proposes one piece of learning, as narrow as the person's words** (F31, *designed, B-10*): a named
person or project gives that one, a role or a plural group gives that role, and only "always", "every" or "never" gives
general; the proposal states its reach in words ("for reviews on <project>"), which the person widens or narrows with one
click, and a correction that would propose nothing proposes the narrow one. When a signal is recorded (sent back, undone, dropped, reworded, pulled
back, draft edited, held op declined, or the person's answer to a question the assistant asked them), a small `learn` task runs, unless the person's own answer already recorded what it teaches ("Not a project" and "It's part of" keep their glossary entry, which the correction names as `learned`). Its packet holds:
- the item, and which kind of work was corrected (an entry that names kinds of work must include it, or it goes back
  once with that reason; built: `test_a_lesson_naming_kinds_of_work_must_include_the_one_corrected_and_the_packet_says_which_it_was`);
- the assistant's original output;
- the correction: the note, what was undone, or the text as edited or sent;
- the knowledge entries the original run was given;
- the active lessons and rules.

It returns **at most one** proposal op, "nothing to generalize", or one question to the person:
- a new lesson, rule, fact, glossary entry, routing entry or style note;
- or `lesson.update`, when an existing lesson should have caught it but didn't. A repeat means the guard was wrong, and fixing
  it beats adding a second one;
- or, when it can't tell what the correction means (what was wrong, or what to do instead), one question to the person
  saying what it understood and what it needs to know. The person's answer is a correction learned from at once, and
  learning from that answer asks nothing more (`learning-question`, *built*:
  `tests/test_learn_correction.py::test_an_unclear_correction_asks_the_person_one_question_and_never_anyone_else`).
- A correction that says the assistant missed something (the person said so, or sent back an answer that recorded
  nothing) is never "nothing to generalize": an answer with no op goes back once (`miss-left-unlearned`, *built*).
- The packet says what each kind of correction means: a declined change was the wrong change, and its note is the
  change's own label, not the person's words; a drop asks why, from the note or the input.
- **Missed, declined and dropped are three signals, never one** (designer, 2026-10-22; change log 174, 176; *built*):
  *missed* means the assistant failed to find something, and teaches extraction or asks; *declined* means not the
  person's, or not a promise, and teaches relevance or routing; *dropped* means no longer needed, and teaches nothing
  unless the person's own words give a reason that generalizes (a drop with no note is not learned from at all). The
  Quality measures (6.20) count the three apart, so a week of drops never reads as a week of misses, and a drop never
  counts as a correction of the assistant. *As built:* the packet and the prompt say what each teaches; a `dropped`
  signal with no note queues no learning (the draft set aside records none); `GET /api/quality` reports `apart`, the
  three counted apart for the window and each week; `dropped` is not in the correction count or the repeat-correction
  rate (`tests/test_learn_correction.py::test_a_drop_with_no_reason_is_not_queued_for_learning_and_one_with_a_reason_is`,
  `tests/test_quality.py::test_missed_declined_and_dropped_are_counted_apart_for_each_week_and_never_added_together`).
  When no run made the
  corrected work, the packet says so and a lesson names no kind of work (built:
  `tests/test_learn_correction.py::test_a_lesson_from_a_correction_no_run_made_names_no_kind_of_work`).

The proposal shows on the correction's own card as one line: "Learned: … · Keep · Edit · Discard" (7.18). It stays there
until the person decides, and never expires. `GET /api/knowledge/learned` gives each correction's line: still being
learned (with the waiting request's words), a proposal (which also names the change it was learned from, `from_changeset`),
or the person's own words already kept, with the change to undo. A card finds its lines by the change the correction was
about or by the records it names.

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

**Proposal rules, as built in L3p** (`engine/proposals.py`, `engine/knowledge.py`, `engine/rules.py`). They apply to the four
kinds and to standing rules, and to a proposal only: what the person says in their own words is active at once.
- **A duplicate merges.** A proposal with the same kind, the same normalized wording (a glossary entry's term, a routing
  entry's topic and who it names, a style note's audience and observation, a lesson's or rule's text) and a target that
  overlaps an active or proposed entry's (task kinds, people and projects each share something) is not made again: it links
  its evidence to that entry (`more_evidence`) and the op's outcome names the entry. An active entry is kept before a proposed one.
- **A near-discard is not shown.** A proposal whose words are alike enough (`knowledge.discard_similarity`, default 0.8, the
  share of words in common) to an entry the person discarded in the last `knowledge.discards_hold_days`, over an overlapping
  target, is made as `discarded` with the reason "Close to one you discarded", so nothing shows. The hold counts only
  the person's own discards (the `discarded` signal), never one made this way, and not one set aside with "just this time".
- **A pasted reply is content.** A note typed on a button that relays someone else is content the person reports, so its
  proposals are proposals (the same test as for any op from a note).
- **Just this time.** `POST /api/knowledge/{id}/just-this-time` on a proposal records a `just_this_time` signal (no `discarded`
  signal), discards it with the reason "Just this time", and acts at once with Undo. Nothing is proposed in its place. The
  key it remembers is the entry's kind and normalized subject (the same wording the duplicate test uses), so the next
  proposal about the same thing is made and shown, and `just_this_time_before` on its view says how many times it was set
  aside before. Undoing puts the proposal back and it stops counting.
- **Where a proposal came from.** `came_from` is `correction` when the entry cites a correction (its evidence `signal`, a
  lesson's `signal`) or was written by a learning run on a correction, else `input`.
- **Expiry.** A daily sweep in the worker (`sweep_proposals_if_due`) sets proposals from inputs to `expired` once they have
  waited more than `knowledge.proposals_expire_days` (default 14). Proposals from corrections never expire.
- **One line for everything learned.** `GET /api/knowledge/proposals` lists the proposals waiting, oldest first, with
  `came_from`, evidence, target and `expires_at`. Today has one Review line, `learned`, counting them by origin, with `expired`:
  how many expired since the person last kept, discarded or set one aside. It leaves out the catch-up list.
- **The catch-up list.** `engine/catch_up.py::start`, run at startup, makes the list once: the corrections recorded so far
  that no entry cites, grouped by kind (the signal's kind, the task kind that made the change and the record kinds it
  touched), ranked by how often the kind repeated and then by recency, cut at `knowledge.catch_up_max` (default 20); the rest
  are counted as left out. It also moves the held rule decisions into proposals. The list's state is a small file in the
  workspace's private folder (`.cockpit/catch-up.json`), so it is made once per computer. `catch_up.waiting` gives the learning
  step the kinds still to learn from, and each leaves it once an entry cites one of its corrections.
  `GET /api/knowledge/catch-up` returns the proposals on the list with `waiting` and `left_out`, and Today has the Review line
  `catch_up`. *Until the `learn` task kinds exist, only the moved rules reach the list; the corrections wait.*
Built: `tests/test_proposals.py` (every test named in CHANGES.md section 55).

**When it runs.**
- **At once, when the person wrote something.** That covers a send-back note, an answer to the assistant's question, or a
  rule stated in Ask. The person is looking at the card right then, and the Learned line should appear while they still
  remember why. Writing the learning down in the same turn as the correction is the habit that makes it stick.
- **Batched,** every `knowledge.learn_every_minutes` (default 30), for silent corrections: an undo, an edited follow-up, a
  pulled-back auto-close, a dropped question, or the person's own direct edit of something the assistant set (6.20). A direct
  edit is often the clearest correction there is.

**A direct edit isn't always a correction.** Sometimes the world changed, not the assistant: a later mail moved a due date,
or work was handed over. Learning from that gives wrong lessons ("the assistant gets due dates wrong"). So:
- the `learn-correction` packet carries every input received after the original run that touches the same records;
- it answers "nothing to generalize" unless the edit contradicts the evidence the run had at the time.

**Which tier writes it.** A bad lesson is worse than none, because it is in every later packet. So there are two task kinds:
- **`learn-correction`:** lessons, `lesson.update` and rules from corrections, on the stronger tier. These are rare and
  high-value.
- **Learning from inputs:** glossary entries, routing and facts proposed from inputs. These come out of the input's own
  run (reading notes), on its tier, which is usually the low-cost one; there is no separate task kind (*as built*: the
  notes prompt's learning rules say when to propose each, and `learn-input` is only a name for that part of the run).

Anything proposed after a repeat correction (a guard that already failed once) always runs on the stronger tier. Both kinds
follow cost control (6.16), each with its own budget. Corrections recorded before this was built are learned from once,
when it arrives, into **one catch-up list** ("Learned from earlier corrections: 23 to review"), not into dozens of correction
cards on day one. *As built,* one learning run per kind of correction on the list (its newest correction that can still
be learned from), queued once when the app starts; the runs wait together for one go, shown as one Today line with the
count and the total (`POST /api/knowledge/catch-up/go`). Only the kinds learning reads (`learn.TEACHES`) are on the list:
putting an action on or off hold is the person's own planning, not a correction of the assistant. **Built:**
`tests/test_catch_up_learning.py::test_the_catch_up_learning_is_queued_once_for_each_kind_and_held_for_one_go_with_one_total`.

**A send-back's redo sees the items as they are now:** its packet lists each record the sent-back work touched (up to
12), as it is now, marked taken back, kept, or not applied, inside a block marked as records. **Built:**
`tests/test_catch_up_learning.py::test_a_send_backs_packet_shows_each_item_the_work_touched_as_it_is_now_and_where_it_is`.

**Learning from inputs too.** A rules-only scan (no AI) finds the terms in an input that look like acronyms or project
names (`language.new_term_patterns`, less `language.new_term_ignore`) and are not in the glossary or among the
workspace's names. *As built,* it runs after the input's answer applies, and proposes each new term as an unknown
glossary entry from the input, at most `knowledge.new_terms_per_input` (0 turns it off), never one the person discarded
recently. Its entries have Discard, not Undo. The run that processes an input may also propose:
- glossary entries for new acronyms or terms. An assumed or unknown one that blocks understanding can carry one short question
  to whoever routing says knows it.
- routing entries when the input shows who answers what ("not me, ask X" in a reply: a routing proposal, and the question
  stays open). A question the person reroutes by hand teaches through its `routed` signal (learned from at once), not a
  routing proposal of its own.
- facts, as it already does, replacing an older fact the input supersedes.
- An answer the person writes to a question the assistant asked them records `answered_assistant` and is learned from at
  once, like a send-back; a bare "yes" or an answer about someone else records none.
Work that learns on its own (`learning: own`) gets none of this.
**Built:** `tests/test_learn_input.py` (every test named in CHANGES.md section 57).

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
  provider switch is exactly when learning can be lost silently. A fallback is a switch too (6.16). *As built (L4):* the
  check runs the shipped golden set, the person's enabled packs' cases and the learning pairs on the new choice, on the
  worker, and passes at `ai.evaluation.min_score`; a check that can't finish never counts as a pass; the estimate prices
  a sample of real packets and counts each pair as about three calls; the verdict and what Switch back restores are kept
  on this computer; the Today line is `switch_failed`, with Switch back and Keep it; `dispatch.knowledge.check_on_switch`
  (default on) turns the offer off. **Built:** `tests/test_switch_check.py`, `tests/test_pairs.py`.
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

**A rejected ask is dropped, not reworded** (designer's lessons, 2026-10-19; roadmap S1-2). When the person's correction of
a question rejects the asking ("not my job", "why are we asking this?"), the correction ends as `question.drop` with
the person's words as the reason, never as a politer version of the same ask. "Check X first" means check X in that
run (the search round, 6.6) and close the question if X answers it. A reword is right only when the person objects to
the wording, not to the asking. Each such correction also proposes the learning it implies, and when it is about who
the person is to the recipient, a stance (6.34). Learning pairs cover each case.
*Built (S1-2):* the assistant can't reword a question (that is the person's own), so the politer version would be a new
question to the same person; when the "Change this" note holds one of `language.rejecting_words`, such a question is
the `rejected-ask` lint, returned once and then held, and the notes prompt says to drop with the note's words
(`tests/test_rejected_ask.py`; the learning pair `rejected-ask`, and `look-it-up` for "check first"). Left: proposing a
stance from such a correction (with the stance screens).

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
- **A setting the person can change** comes as a `setting.propose` op (a `setting_proposal`): the setting, the new value and
  why. The material names each setting by its screen name and a short **handle** made from its key (a stable hash), never the
  key itself; the op names the handle and the applier resolves it against the current settings list (an unknown handle is
  refused in plain words, and two keys whose short handles match both get longer ones), so a key never reaches an answer or
  the screen. The proposal keeps the resolved key for the settings save; the screens show the setting's screen name. Built:
  `tests/test_ask.py::test_a_setting_handle_is_short_and_stays_the_same`, `test_the_material_names_settings_by_a_code_and_never_by_a_key`, `test_a_handle_resolves_among_the_current_settings_and_an_unknown_one_is_refused`, `test_handles_that_collide_get_longer_so_each_names_one_setting`, `test_an_answer_rests_on_quoted_words_and_suggests_a_setting` (a proposal naming a code applies through the settings save), `test_a_suggestion_naming_an_unknown_setting_code_is_refused`, `test_an_answer_that_cites_a_settings_line_shows_no_settings_key`.
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
  service that is down or out of reach is not a refusal and the sign-in stands. A sign-in with a known expiry gets a
  Today line the day before ("<service> needs signing in again tomorrow"), and mail left unread while a sign-in lapsed
  is a coverage gap on the coverage line, counted apart from missed promises (F27, *designed, phase T*). With no mail
  connected, the setup guide and the coverage line point to the mail add-on's steps, naming no service (F28). Signing out withdraws the access at the service
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
     reason. A default that names an entitlement (3.11) is used only while the entitlement is held; without it the row
     says one-click sign-in needs it and offers the person's own registration with the add-on's steps, and when a held
     entitlement lapses, a Today line says the service isn't being read until the person chooses (decisions,
     2026-10-20). Not built yet.
- **Signing in is the whole setup** (decisions, 2026-10-12). The add-on lists the sources its sign-in starts (the inbox, the
  main calendar), each with its connector, label, settings and interval. As soon as the person signs in, the core adds them to
  `watch.sources` (4.5) **once per sign-in, and only where the workspace reads nothing with that connector yet**, with
  `first_run: intake` (6.32). A mail source with nothing chosen reads the inbox, so nothing has to be chosen first. The person
  narrows, adds or removes sources afterwards, and their changes and removals stand. Which sign-ins have had their sources
  started is kept on this computer; a sign-in made before its add-on declared any gets them at the next start.
- **"Not reading".** If the person later removed the sources, the Sign-ins row says what it is not reading and offers **Start
  reading**, which adds them again with one click.
- **Several accounts of one service at once** (roadmap wave 5, P18). When the add-on names the signed-in
  account (the `account` function), the sign-in row lists each account by its address with **Sign out** on each, and **Add
  another account** starts the same flow and keeps the new account beside the others. Tokens are kept per account, one file for
  each (`sign-in-<name>--<key>.json`, the key a short hash of the address, readable by its owner only); a sign-in made before
  accounts existed is read as the first account and moved to its own file on first read, or stays as one unnamed account when
  its tokens never said whose they were. The same address again is the same account: signing in replaces its tokens. A source
  of such an add-on has an `account` setting (4.5), a list of the accounts signed in: the only one when there is one, a choice
  the source form requires when there are several; when a second account is signed in, sources that named none keep the first
  account, and the sources the sign-in starts are started for the new account. The add-on's connector needs no change:
  `context.access_token(name)` gives the token of the source's own account, and `context.account` its address (plugin API
  0.3.82). Signing one account out forgets only its tokens: the sources reading with it fail as `auth` and wait with the
  existing "sign in again" line, which names the account; the other accounts' sources go on. *Built so far (B-5, P18):*
  `tests/test_sign_in_accounts.py` and the account list in `web/src/components/SignIns.test.tsx` and the account choice in
  `web/src/components/Sources.test.tsx`.

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
  `POST /api/packs/{id}/token` takes it typed (a local app keeps it with `keep_secret` and writes the `file:` reference; a
  hosted app refuses it) or as a reference, for the host of that entry's release; a refusal that a token would fix carries the
  header `X-Cockpit-Needs: read-token`, which is how the row knows to ask. `POST /api/packs/catalogs` (and `/remove`) add and
  take away a feed address, https only.
  Only a wheel of pure Python whose needs the app already has (each requirement present at an allowed version) is installed
  this way; anything else is refused with what to do instead. Installing a pack's own libraries is planned (roadmap, A2; see roadmap-done.md).
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
  map or text), and every reference resolved to the referred record's name and a link (a field that holds the id of a record
  its type doesn't declare a reference, such as a person's team or a project's owner, is resolved the same way);
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

## 6.32 The daily steward (phase S, designed)

The core is a daily assistant for anyone juggling work, not only project support: it knows what the person promised and
what was promised to them, notices what needs them, gets the next step ready, reminds them at the right moment, remembers
people and details, and never acts in their name without their yes on the exact content. On top of 6.8 to 6.15 and 6.22:
- **Time:** reminders at a time on any dated thing, with snooze; repeating to-dos on the calendar's repeat engine; a
  morning brief and an evening wrap-up, with the Monday briefing as the weekly form. The brief has three sections in
  order (changed overnight, at risk today, needs your yes): a changed or at-risk line states one fact plainly, an
  at-risk line says when it bites, a needs-your-yes line starts with what the person does and opens the exact
  content, an empty section is left out, a quiet day is one line, and no line reports status or progress (samples in
  `docs/project/steward-brief-samples.md`). The evening wrap-up has done today (credited to whoever did it), moved to
  tomorrow and still waiting on others; the Monday briefing opens with a copy-ready message to whoever the person
  reports to, then the week's promises, questions, chases and decisions, and three to five goals the person confirms,
  under the same line rules (6.35; `docs/project/steward-wrapup-samples.md`).
  **Built (S2, the brief):** `engine/brief.py` makes the three forms by rules, reading Today's own lines, what changed
  since yesterday, this week's days, the clash finder and `engine/invitation_changes.py`, and repeating none of their
  logic; nothing in it calls AI. *Morning:* **changed** is what someone else did to the person's own things since the
  evening of the last working day (`steward.brief.overnight_from`: news, a date that followed its meeting, a close a rule
  made; never the person's own acts) and what an invitation changed (new, called off, back on, moved, place, title,
  organizer; never who replied), read from the calendar entries' history; **risk** is the person's own to-dos due today
  or late (with the time of the meeting one is due at), what others owe them that is late (read from the follow-up
  lines) and today's meetings that overlap by how much; **yes** is Today's own decision, question, held, reply, send and
  follow-up lines, each opening that line, with "draft ready" where a message is already written. *Evening:* done today
  credited to whoever did it, what moved ahead today or is still open today, and what others still owe or haven't
  answered; it is quiet when nothing moved and nobody is waited on. Each section shows at most `steward.brief.max_lines`
  and says how many more. The card is at the top of Today from `steward.brief.morning_from`, gives way to the wrap-up from
  `steward.brief.evening_from` and closes for the day in that browser, which is no signal of anything. **Left:** the
  capacity line and the moves it proposes (the capacity item, S2); at-risk lines from a date inside a mail or a booking
  ("the last day to cancel"), from a meeting named only in words, and from a clash after today (only today's meetings are
  compared, with no travel time); the reminder offer. The sample mornings are cases in both workspaces
  (`workspaces/*/briefs/`, `engine/brief_cases.py`), each scored exactly with what it still lacks named (`left:`).
  `tests/test_brief.py`, `tests/test_brief_week.py`, `web/src/components/BriefCard.test.tsx`.
- **Adding a to-do yourself (phase S2; designed 2026-10-22).** Today and To-dos have **Add a to-do**: the words, when
  (typed in plain words and read by the due-date rules, said back under the field, or left without a day), who
  (the person by default, picked from the list of people), the project (picked, optional) and Repeats. No AI is
  involved: it applies at once as the person's own, with Undo, and the cursor starts in the words. The hand-in box stays
  the way to hand in something to be read. **Built (S2):** the form is a drawer opened by one quiet button in Today's
  header and by the To-dos header (its primary when nothing is open), with the cursor in the words; the day is read by
  `POST /api/todos/day` and said back, the person is the default owner, who and the project are lists, and Repeats says
  back as in the edit form; `POST /api/todos` reads the day and the repeat first (nothing is kept when either isn't
  clear or the repeat doesn't fall on the day) and applies the to-do, then its repeat, as the person's own, answering
  with both changes so the toast's Undo takes them back last first (`engine/add_todo.py`, `tests/test_add_todo.py`,
  `web/src/components/AddTodo.test.tsx`).
- **Repeating to-dos (phase S2; designed 2026-10-22).** A to-do repeats when the person says how, in their own words
  ("every other Tuesday", "the 1st and 15th"), read by the repeat grammar (`engine/repeat_phrases.py`) into a standard
  repeat rule and said back from the wording sheet, so the person sees what was understood before it is kept; a phrase
  the grammar declines is said to be unclear and nothing repeats. **Each occurrence is its own to-do**: only the next
  one exists at a time, so a list never fills with future copies. When one ends (done, dropped, or done by someone
  else), the next is made in the same change, with the same text, owners, project and notes, due on the next date of
  the rule after the one that ended and not before today; Undo of the ending takes the next one back too. One that is
  missed **stays open** (nothing a person meant to do is closed for them), and the next is made only when it ends, on
  the first rule date from that day. "Stop repeating" in the to-do's menu ends the repeat and leaves the open one as
  it is; its detail lists the earlier occurrences and how each ended. A repeat set by the person applies at once; one
  the assistant read from an input ("I send the report every Friday") is a suggestion that waits for their yes.
  **Built so far:** the grammar and its shapes (`tests/test_repeat_phrases.py`, `tests/test_phrase_cases.py`); the
  repeat on a to-do (`repeat`, `occurrence_of`, the op `action.repeat`) and the next occurrence made in the same change
  as the ending, whichever way it ends, with Undo taking both back (`tests/test_repeating_todos.py`); the words
  checked as the person types (`POST /api/repeats/check`), said back from data under the Repeats field of the edit
  form, a repeat mark on the row, Stop repeating in its menu and the earlier occurrences on the to-do's page
  (`web/src/components/RepeatingTodos.test.tsx`). A phrase that carries the to-do's own words ("water the plants every
  day") is declined, since the field holds the repeat only. The same field is on the form that adds a to-do by hand,
  and Today's to-do rows carry the repeat mark in words (`web/src/components/AddTodo.test.tsx`,
  `tests/test_add_todo.py`). **Built (S2c, change log 188):** the assistant proposes a repeat from an input's own
  words. `action.repeat` may carry only `words` (the input's exact words, as `due_words` does for a day), which the engine reads with the repeat grammar
  from the to-do's due day (else the day the input was received, on the person's own clock) into a rule, the words and a
  first day; its `id` may name a to-do added earlier in the same answer as `@<index of that op>` (counting from 0, an
  `action.add` before it), which the applier resolves to the new id when it checks (against the ops before it, as
  plugin validators see them), when it applies, and when a held one is released later (from the changeset's recorded
  outcome of that op). Words the grammar declines, or that miss the to-do's own day, refuse the repeat op alone ("the
  repeat in the input isn't clear"): the to-do still applies and nothing repeats. From anyone but the person it stays a
  suggestion that waits for their yes (`repeat-confirm`), and its held line says the repeat in words. The extraction
  prompt names the op for a to-do the input says someone repeats and never for a habit that isn't a to-do; a case that
  expects a repeat waiting for the person, or forbids one, counts it as made. Built:
  `tests/test_repeating_todos.py` (the `@` resolved at check and apply, held and released later, a to-do gone, words read
  from the due day and from the received day, unclear words, a bad `@`), the golden-set cases
  `repeat-named-from-the-same-answer` and `repeat-someone-elses-habit` in both fictional workspaces
  (`tests/test_evaluate_harness.py::test_the_repeat_cases_pass_on_their_stub_answers_and_the_repeat_stays_held`).
- **Promises and people:** promises both ways from everything that comes in, the person's own sent mail included;
  replies owed with drafts in the person's voice; prep before and capture after any meeting; people memory with evidence.
- **What arrives:** dates in documents become dated facts and proposed reminders (bills are reminders only: no bank
  connection); areas of life with their own data level and allowed accounts; capture from anywhere, voice included
  through an adapter capability.
- **Manner:** suggestions on patterns, each a line with choices recorded as signals; talking to the assistant as the way
  to ask for anything, every proposed change kept or dropped inline.
- **Promises come first** (2026-10-17): dependable memory for commitments is the reason to choose the product. A promise
  is found with its evidence and its basis (said or inferred), and its end is proposed the same way: done, date
  changed, called off, partly delivered, or answered without an answer; never closed silently.
- **Attention is budgeted:** quiet hours, a daily cap with a digest for the rest, an importance threshold, and
  dismissals that stick; the day's priorities are checked against the free time on the calendar, without automatic
  scheduling. Reminders that came due while the computer slept show at once on waking, marked late.
- **Measured:** promises found and kept, false alerts, time spent reviewing and follow-ups completed, on the Quality
  screen (6.20).
- **Acting after a yes** (owner, 2026-10-17): mail (reply, forward, send, archive, move, label, mark read) and calendar
  (create, move, cancel, accept, decline, propose a time) through the publisher (6.3, 6.12), each act shown exactly,
  approved, carried out with a visible status and written to the ledger. A reminder can reach a sleeping person as an
  event with an alarm in their own calendar or a mail to themselves.
- **Not in 1.0:** a third-party push service (a companion phone app comes after 1.0), a bank or any financial account. The details of each item are designed in its own section when its wave starts; the proposal is
  `docs/project/steward-proposal.md`.

### Personal life: one Personal project, with areas and projects under it (phase S4; decided 2026-10-20)

Personal mail and calendar entries the person wants kept track of (an appointment, a bill, a renewal) belong to no work
project, so they would otherwise sit unfiled, and "Set aside: personal" (6.5) means not tracked at all. So:
- **One Personal project, made at setup, for everyone** (owner, 2026-10-21: the default project for every person, used
  or not): an ordinary project the person can rename or remove, made with no question; a setting names which project is
  the personal one (`workspace.project.personal`). What the assistant files there is never "unfiled". A person who only
  tracks a business answers yes to setup's business question and can leave Personal empty; nothing asks them to use it.
- **Two sides from day one** (the UI/UX reviewer, 2026-10-21; *designed, S1-4*): every item belongs to Personal or to the
  second side, a business or a job as the person chose at setup (a top-level project, its projects under it; a
  setting, `workspace.project.business`, names it). Today and Follow-ups get an "All / Personal / <business>" filter (*built*; a follow-up section for
  another person stays whole while any of its items is on the chosen side, since it is one message). Filing reads the
  signals in this order (designer, 2026-10-22; change log 174; **built, B-12 batch 1:** `tests/test_filing_signals.py`,
  `tests/test_sides.py`; the first rank that decides, decides, and a rank whose signals point to both sides decides
  nothing, so the next is read): **people first**, since each person belongs to a side; then **the sender's domain**,
  when the sender is nobody known: it votes for a side when every known person with an address there is in one
  organization and that organization's people are all on one side (a public mail service, or a domain shared by people of
  two organizations, never votes); then **identifiers**: a project's `aliases` (any form the person gives: another name, a
  code, a ticket-key prefix; any alias counts, even one word); then **project names**; last, the configured **side words**
  (`workspace.project.side_words`). Words are matched as whole words in any case. A project's name counts on its own only
  when it has two or more words or is no everyday word (`language.everyday_words`, from a shipped list for the default
  language); "Launch" counts only through an alias such as "Spring launch" or a code. Words **propose, never file
  silently**: every item filed this way keeps why (`filed_by`: the signal, the word or domain that matched, the project;
  written by the applier with the op, and cleared if the assistant writes one), and what changed's line for a new action
  and the item's page say it in words when anything but its people filed it ("Filed under <project>: it names <word>", or
  "it's from <domain>") with **Move to <the other side>**, one step through the person's own change of the item's project
  with Undo; the change is the `edited` correction every change of a field the assistant set already records
  (`tests/test_filing_signals.py::test_move_changes_the_items_project_as_the_person_records_one_correction_and_undo_restores_it`).
  Only an item neither its people nor its words place is asked
  about, and those are asked together in one "Which side?" question, never one each. A person with no business is never
  asked: what the assistant can't place goes to Personal while Personal is the only top-level project (its areas and
  projects under it); a workspace that tracks other work at the top without naming a business keeps such items unfiled
  for the person to file, as before, a computer joining a synced folder makes no Personal of its own, and an answer that proposes a new project leaves its items for that project, which Add files under it. People on the personal side record how they relate to the person (a relation, "my sister"), not a role or an
  organization.
- **Areas and projects under it** (`Project.parent`): an **area** is ongoing and never finishes (health, money, home,
  family, a car, pets) and has no end date, so it is never behind; a **project** has a goal and an end (moving house, a
  renovation, a tax return) and is followed like any other. A project may sit under an area.
- **Start flat; propose on a pattern.** Setup makes only Personal. When a number of items (a setting) share a theme, the
  assistant proposes one new area or project for them ("File these 4 under a new area 'Health'?"), a `project.add`
  that waits for the person's yes as every proposed project does; never a question per item. A move from Personal to an
  area is an `edited` correction (6.20), so the next item like it is filed there. Setup offers common areas as tick
  boxes, all unticked and skippable, from a list that is a setting.
- **Privacy per area** with the project's content levels (3.3): an area such as health or money can be more private than
  the rest, and its material then reaches only the accounts allowed for that level; Personal itself follows the
  person's general setting. Personal and everything under it stay out of work reports and status pages.
- **One Today:** a bill due Friday sits beside a work deadline, tagged by its area.

### Dependability, from the designer's answers (2026-10-19)

The functional designer's answers to F1 to F14 (`docs/project/designer-answers-2026-10-19.md`), drawn from what went wrong
in running. Phase S builds them with named tests; an item says "Built" only where a test is cited.
- **Records join by id, never by a display name.** Anything that names a record to follow (a watch list, a rule, a filter)
  holds its id, so a rename never detaches it. Built (`engine/references.py`):
  - A triage rule names the projects and people it looks for by id (`projects`, `people`); the matchers read their
    current names and other names when they run, so a rename follows, and a record that is gone gives no terms, so the
    rule closes nothing. Tests: `tests/test_join_by_id.py::test_a_triage_rule_that_names_a_project_by_id_still_matches_after_the_project_is_renamed`,
    `::test_a_triage_rule_that_names_a_person_by_id_follows_the_name_they_go_by_now`,
    `::test_a_rule_that_names_a_record_that_is_gone_closes_nothing`.
  - A name typed where an id belongs is resolved to the id when the setting is saved, and refused in its own words when it
    matches nothing or more than one record; the screens keep showing the record's current name. It covers a source's
    project, the triage rules' projects and people (Settings save, the source form), a connector's settings marked
    `RefTo`, and a rule's or lesson's `filter` on a reference field (a rule from the starting file included). Tests:
    `tests/test_join_by_id.py::test_saving_a_triage_rule_that_names_a_project_or_person_by_name_stores_their_ids`,
    `::test_saving_a_rule_that_names_something_the_app_does_not_know_is_refused_and_says_which`,
    `::test_saving_a_source_with_a_project_name_stores_the_projects_id`,
    `::test_adding_a_source_through_the_api_with_a_project_name_stores_its_id_and_refuses_an_unknown_one`,
    `::test_a_connectors_settings_that_refer_to_records_are_stored_as_ids`,
    `::test_a_rule_filtering_actions_by_project_name_stores_the_id_and_covers_them_after_a_rename`,
    `::test_a_lesson_filtering_by_a_person_name_stores_the_id`,
    `::test_a_starting_rule_in_the_rules_file_that_filters_by_name_is_seeded_with_the_id`.
  - What older files and records hold by name is joined once when the app starts, and a name that matches nothing is left
    as it was, never guessed at. Test: `tests/test_join_by_id.py::test_names_already_stored_in_the_watch_settings_and_in_rules_become_ids_when_the_app_starts`.
  - Already by id, and kept so: a rule's `sources` (the source's own id, so a relabel never detaches it; `tests/test_join_by_id.py::test_a_rule_that_names_a_source_keeps_matching_when_the_source_is_relabeled`),
    a source's `author`, and a rule's or lesson's `projects` and `people`. Still by a name an outside system gives: the
    accounts the person and the workspace write under (`by-us`, `user.accounts`), which have no id of their own to join by.
- **No close goes unseen.** Every item the assistant or a rule closes or sets aside without the person seeing it is counted
  and can be reviewed ("silent closes"), and the count is one of the dependability measures. Built (`engine/closes.py`):
  - A close is one of three kinds: a triage rule's close of a watched change, mail a rule or the assistant's sorting set
    aside, and an action or question the assistant closed, dropped or answered as data (`action.close`, `action.drop`,
    `question.drop`, `question.done`). It is silent unless the person made it (their own note, screen or person action) or
    saw and approved it (confirmed the set-aside mail, marked a rule's close as seen, "Looks good" on the changeset,
    released the op from held). An undone close, or one the person took a closer look at, is no longer a close. Each says
    what, when, which rule or run, and why.
  - The list is `GET /api/silent-closes` (and `POST /api/silent-closes/seen`), shown on the Connections screen under "Closed
    without you seeing", below the Set aside folder and the rule closes. The measure, silent closes out of all closes in
    the quality window with the counts for each kind, is `closes.measure`, shown on the Quality screen (see Measures).
  - Tests: `tests/test_silent_closes.py::test_an_assistant_drop_applied_as_data_is_a_silent_close_and_is_listed_with_what_when_by_and_why`,
    `::test_the_persons_own_close_is_not_silent_but_is_counted_in_all_closes`,
    `::test_a_close_the_person_looked_over_and_approved_is_not_silent`,
    `::test_a_rule_close_is_silent_and_says_which_rule_and_why`,
    `::test_mail_a_rule_sets_aside_is_silent_until_confirmed_and_what_the_person_sets_aside_never_is`,
    `::test_the_measure_gives_silent_closes_out_of_all_closes_with_the_denominators_by_kind_and_period`,
    `::test_the_api_serves_the_count_the_list_and_the_measure_and_marking_one_seen_lowers_the_count`; the screen:
    `web/src/components/Sources.test.tsx` ("closes nobody has seen").
  - Looked at and not counted, because the person sees them as part of the work or they close no item: follow-on and
    learning runs closed when there is nothing to do, a change folded into a newer one (read once, in order), the
    questions a source's recovery or a sign-in closes, requests an attempt superseded, proposals that expired (counted on
    their own review line), and stage moves (a move forward, never a close).
  - Not built: a Today line for silent closes.
- **An outage is not a failure.** With the computer asleep or no network, work waits and runs when the network is back. A
  run that did no work (cut off, or a runner that only printed a sign-in banner) is not an attempt, is never sent back as
  a mistake, and doesn't count against the request's spending figure.
- **A newly added source is taken in quietly.** Nothing in it is reported as new: one summary line ("found 12 open promises
  in the last 14 days") and a list to review. Every open item in it is followed from then on, whatever its age; age decides
  only whether it is raised as news. This is `first_run: intake`, the default (`engine/source_intake.py`):
  - The first read notes everything the source holds. It then hands in the mail of the last `first_run_days` (14) and every
    item of any other kind of source, through the same triage and sorting as any hand-in; each request is marked with the
    source (`intake`). Older mail isn't read, and the source records the day before which it wasn't looked at
    (`looked_back_to` on its first `watch_run`); the coverage line says "Not looked at before Oct 5".
  - The whole intake is priced as one total (the requests' estimates and the sorting run for its mail). When the total is
    known and not above `ai.budgets.confirm_above_usd` it starts by itself; otherwise the requests are held and Today has one
    line for the source ("Take in Inbox: 12 items from the last 14 days", or "<n> items" for a source with no mail) with the
    total, and one Go starts them all (`POST /api/watch/{source}/intake/go`; the mail waiting for sorting is sorted first).
    The first-go rule applies on top of an intake that starts by itself. A Go is itself a go: it covers the first go, as the
    catch-up list's Go does.
  - Until the person opens the list, the requests' review lines and held lines are not on Today. Once all of them are
    finished (done, stopped or waiting for the person) there is one line, "Look over what was found in Inbox: 4 items", with
    what they did counted ("3 actions, 2 questions, 4 held for you"). It opens What changed narrowed to that source's intake
    and marks it seen (`POST /api/watch/{source}/intake/seen`, with Undo); after that, whatever still needs a look shows
    line by line. Held items stay held, and nothing applied is undone or hidden from the records screens.
  - "Look further back" on the coverage line offers a list of days (`watch.look_back_choices`: 30, 90, 365 more), shows the
    count and about what it costs before anything is read (`GET /api/watch/{source}/look-back?days=`), and takes in the older
    mail the source already returned the same quiet way, under the same go rules, moving the date back. The core can only take
    in what the connector returned: when the source holds no mail that far back the result says "Only mail from <date> is
    available to read" and the date moves only as far as that mail goes. Built: `tests/test_source_intake.py`,
    `tests/test_source_intake_routes.py`, `web/src/components/LookBack.test.tsx`, `web/src/shell/HeldLines.test.tsx`,
    `web/src/components/Today.test.tsx`, `web/src/components/WhatChanged.test.tsx`. A source a sign-in starts is taken in this way too (6.27;
    `tests/test_sign_in_sources.py`). *Not built:* a connector's own first read is bounded by its own settings (the mailbox
    connector takes its latest `first_read` messages, with no date), so the date a first read says it looked back to is the
    window the core applied, not a promise about what the connector returned.
- **The walkthrough's first result** (S1-3). Right after the mail step, once a mailbox is read and an AI account is chosen,
  the walkthrough offers the same intake as one look back: "Look back over the last 14 days of your own mail" (the source's
  `first_run_days`), the items and the one estimate shown first, and one Start for every source's intake the sign-in
  brought (the mail waiting for sorting is sorted first; the Start also covers the workspace's first go for those
  requests). The sent folder is part of it when it is read, as another source. After the Start it lists up to
  `ui.walkthrough.first_promises` (5) open promises (design 6.33's view: who owes each to whom, its day and its exact words)
  and one follow-up ready to copy, the one the Follow-ups screen composes, copied and kept by the same route (6.35); with no
  promise found it says so and offers "Missed one". Nothing is spent before the Start; with the built-in stand-in the
  figure shown is "less than a cent". **Coverage**: the screen lists what is read, one row per source: before the Start the
  account, folder and day it reads from, from the same settings the read uses (no call to a service); after it, how each
  source went, in words. A source that wasn't read is said beside it, a mail account with no sent folder gets one plain
  line and the action that adds it (promises made in mail the person sent can't be found until it is), and "none found"
  never says the mail held none while something wasn't read, so an incomplete first result never looks complete; when the
  only gap is a missing sent folder, the list says everything listed was read but not the mail the person sent, never that
  something connected wasn't read (change log 168, 173; `tests/test_first_promises.py`, `web/src/components/FirstPromises.test.tsx`). Built: `tests/test_first_promises.py`, `web/src/components/FirstPromises.test.tsx`,
  journeys J2 (nothing found) and J6 (a promise found). *Not built:* a sent folder offered by a sign-in itself (6.33), so the
  look back reads it only when the person added it.
- **Coverage on Today.** "Couldn't read" and "read, nothing new" are different words and never share a color. A source that
  has failed for longer than its usual gap becomes a line for the person ("work mail hasn't been read since yesterday
  6 PM: sign in again?"). A day whose right top line is "nothing needs you, and here is what was read" is a test case.
  Where Today would say nothing needs the person (its heading, the empty queue, the inspector's all-clear), a source that
  is on and hasn't been read successfully in `watch.stale_after_hours` (24; there is no brief yet, so the last day stands
  in for "since the last brief") is named with its own label and when it was last read ("Work mailbox hasn't been read
  since Tuesday"), and the line then says only that nothing was found, never that nothing needs the person. Built:
  `tests/test_watch.py::test_a_source_not_read_successfully_within_the_stale_hours_is_named_by_when_it_was_last_read`,
  `web/src/components/Today.test.tsx` ("a source not read lately is named where Today would say nothing needs you").
- **A date marked "check this" is never a deadline.** An action whose `due_check` is set (the rules couldn't read its date
  for certain) keeps the date for the person to see, marked "check this date" wherever its row shows it, but has no
  reminder from it, no at-risk or due-soon line, no overdue state or line, no place in "due this week", no chase by it and
  no "it was due" in a message to someone else, until the person confirms it (setting the date, which clears the doubt).
  It is chased and sorted as an undated action. Every place a due date becomes urgency reads it through
  `engine/firm_due.py`. A reminder the person set at a time of their own is theirs and stays. Built:
  `tests/test_due_check.py`, `web/src/components/TodayRail.test.tsx` and `web/src/components/OpenItems.test.tsx` (the
  marker).
- **Missed one** is reachable wherever the person is looking, the evening wrap-up included ("anything I missed today?"),
  and accepts a plain sentence with no source.
  *Built so far (S1-2):* `POST /api/missed` takes the sentence, records one `missed` signal with the person's id (the
  signal's `person` field) and the words as its note, and hands the words in as the person's own trusted note
  (`note:missed_one`, no record, no source to read); the notes packet marks it "The person says the assistant missed
  this", and the prompt tells the run to add what the words name (an action, a promise with who owes it to whom, a reply
  owed) with the words as evidence, never only a note or a fact. The control is in the header on every screen (More on a
  phone) and in the empty states of Today and What changed since yesterday; the form's cursor is in its one field, and
  sending shows "Thanks: I'll add it." with a link to the changes. `missed` is read by the learning loop at once like a
  send-back (the note is the person's words); no run is named, since the person's sentence is all that is known, so it
  is not part of the repeat-correction rate, and a lesson from it should name no kind of work unless the person's words
  do. The quality view (`GET /api/quality`) lists "Missed one" for each person and week with the week's dates, a week
  with none as zero. Built: `tests/test_missed_one.py`, `web/src/components/MissedOne.test.tsx`. The Quality screen shows it
  by week. *Not built:* the evening wrap-up's entry (phase S2).
- **Measures** (the gate week, the tester group, the Quality screen): missed out of present; wrong out of proposed; wrong
  endings, a nudge treated as done included (chasing someone else's promise doesn't fulfill it); silent closes out of all
  closes (the figure is built, `closes.measure`; the screen is not); changed dates, cancellations, partial deliveries and
  owner changes handled; review time; sources not read; and "Missed one" per person per week, which should fall from week
  one to week two. Counts with their denominators; a held-out set; and a replay set where each real miss becomes a case
  (starting state, the person's action, expected end). **The gate week's thresholds** are set from its two measured
  days; the testers are held to those numbers for missed out of present, silent closes and wrong endings (per-tester
  thresholds would move the bar to fit), counts that depend on how much mail a person gets are reported, not gated, and
  the "Missed one" trend is the one measure only the testers have. **During the counted week, what is measured is
  frozen:** Today, the promise lines, the prompts and the model choices don't change, and fixes found go on a list and land
  after it; the one exception is anything that loses a promise or closes one wrongly, fixed at once with the day noted in
  the week's log so the measures before and after can be told apart.
  *Built so far* (the gate week's instruments, `engine/gate_measures.py`): `GET /api/quality` gives each measure as a count
  with its denominator, for each day (on the person's clock) and for the window, which is the quality window's days
  ending today, with its first and last dates. **Silent closes out of all closes** is `closes.measure`, by the day each
  close was made. **Wrong endings out of endings made**: an ending is a close, drop, move, part or unhold (`ENDING_OPS`)
  in a change a run made (not one the person made on a screen), counted once it applied or the person decided about it
  (one still waiting for their Keep is not counted yet); it is wrong when the person kept things as they were
  (`decline_held`), undid it, or reopened an action a nudge had recorded as done. A nudge recorded as done is found from
  the records: an applied `action.close` whose request came from a note typed on "Followed up" (the source's kind), and
  the reopening is the action's status going back to open in the ledger afterward; an ending undone and reopened counts
  once. **Missed out of present** is the person's own entry, never computed: the record `promise_count` (one for each
  person and day, `present` and `missed`), saved or corrected by `PUT /api/quality/counts/{day}` and put back by
  `POST /api/quality/counts/{day}/undo` with what the save returned; a day that hasn't come, or more missed than
  present, is refused. "Missed one" for each person and week is as before. **The replay set** is the number of files in the
  workspace's `replays/` folder; when they last ran isn't shown, because the capability matrix records a day for every
  set of cases together and so can't say it for replays alone. The Quality screen (`#quality`, a link in Settings'
  list of sections) has one section for each measure, each a sentence with its number out of its denominator ("2 of 41
  closes weren't seen by you.") and a short list by day, never a bare percentage and never by colour; the entry form
  (a date defaulting to today, two number fields, Save with an Undo toast, the cursor in the date); an empty state in
  plain words for each section; and the older measures (knowledge used, repeated corrections, what runs couldn't do).
  It is not on Today. During the counted week the screen only shows the window's dates; nothing else about it changes.
  Tests: `tests/test_gate_measures.py::test_silent_closes_are_counted_out_of_all_closes_for_each_day_and_for_the_window`,
  `::test_an_ending_the_person_declined_or_undid_is_wrong_and_every_applied_declined_or_undone_ending_was_made`,
  `::test_a_nudge_recorded_as_done_that_the_person_reopened_is_a_wrong_ending`,
  `::test_the_daily_count_is_saved_corrected_and_undone`,
  `::test_counts_are_summed_for_the_window_as_missed_out_of_present_for_the_person_who_entered_them`,
  `::test_the_window_is_the_configured_days_ending_today_on_the_persons_own_clock`,
  `::test_the_replay_set_is_the_files_in_the_workspaces_replays_folder`,
  `::test_the_quality_route_serves_every_measure_with_its_denominator_and_the_window`,
  `::test_the_daily_count_is_entered_corrected_and_undone_through_the_api` and the export round trip
  `::test_a_window_with_no_counts_is_zero_over_zero_and_the_counts_survive_export_and_import`; the screen:
  `web/src/components/Quality.test.tsx`. *Not built:* a record of when the replays last ran.
- **Sending (S1b) is accepted only on named tests:** exact content and recipients; an approval goes stale when the draft,
  its recipients or its inputs change, a restart that re-resolved addresses or updated a template included; never twice
  after a timeout, retry or restart; after a closed lid or lost network mid-send, the result is checked with the service
  before anything is retried, and an uncertain result shows as uncertain, never as sent; a withdrawn sign-in stops plainly;
  outside content can't change a recipient or add an act. Plugins stay trusted code.
- **Spending on a request** is estimated as a range for the whole request (retries and the stronger model included), stops at
  the upper figure and waits for another go beyond it; retries caused by an outage don't count; the finished item shows
  what was actually spent beside the estimate. *Built (S1):* 6.16 "A request's spending as a range".
- **A refused form save** refreshes the fields the person didn't touch and lists what changed underneath them ("refreshed:
  daily budget is now $2, changed elsewhere at 9:14").
- **Kept secrets** that nothing refers to are removed after 30 days, and with their source or account, never while an Undo
  still points at one.

*Built so far (S1-2, reminders at a time, in the app):* an action carries an optional `remind_at` (a moment with its time
zone). The person sets it from the to-do's menu ("Remind me…", a day and time box; "Change reminder…" and "Remove
reminder" once set) or moves it with a snooze, always their own `record.edit` with Undo; it is not in the edited fields
of `engine/learn.py`, so it is never a correction of the assistant (`tests/test_reminder_lines.py`,
`web/src/components/TodayReminders.test.tsx`). The settings are `steward.reminders.*` in `steward.yaml`, picked from
lists and live (no restart): the working day's start and end and its first and last day (09:00 to 17:30, Monday to
Friday), quiet hours (21:00 to 07:00, which may cross midnight), how reminders missed while the computer slept arrive
(`each` or `summary`), how far Later today and This evening reach, and how long after its time an unshown reminder counts
as late; working hours that end before they start, and quiet hours with equal ends, are refused in plain words
(`tests/test_reminder_lines.py`). When a reminder reaches the person is decided by `engine/reminders.py` through
`engine/reminder_lines.py`: an open action that is not on hold, whose `remind_at` has come, is one Today line,
`{task} · due now`; one that came due and was not shown for the late-after time is `{task} · overdue · due {time}`, shown
at once and never dropped, and says "late: due {time}, while the app wasn't running" only when the app knows it was not
running then (a gap in the record of when it was running, below); reminders that fell in
quiet hours wait, then arrive together as "Saved during quiet hours" with `{task} · was due {day and time}`, and with
`summary` the late ones are one line too. Each line has Done first and Snooze in its menu with In 1 hour, Later today,
This evening, Tomorrow morning, Next week (each with the time it moves to, a choice with no time left today left out)
and Pick a time…. A line that appears while the app is open is also one browser notification with its words, once the
person has allowed them from the button in Settings (the browser is never asked on load). Not built yet: the reminder in
the person's own calendar or mailed to them (the publisher, S1b), and desktop notifications from the tray (phase I). A
reminder is marked late by how long ago it came due. What the line says about why is only what the app knows: while it
runs, the worker notes the moment it was last seen in the workspace's private folder (`engine/running.py`, at most every
20 seconds); when the next note is more than the late-after time and two minutes after the last, that stretch is kept as
a gap (the computer asleep or the app closed; the record cannot tell which). A late reminder, or a summary of missed ones
(all of them), is worded as asleep only when a gap covers its due time. Built:
`tests/test_reminder_lines.py::test_a_late_reminder_says_the_app_was_away_only_when_a_gap_in_its_running_covers_the_due_time`,
`::test_a_summary_of_missed_reminders_says_the_app_was_away_only_when_it_covers_every_one`,
`::test_the_running_record_keeps_a_gap_only_when_the_app_went_unnoted_longer_than_the_gap`,
`::test_the_worker_notes_when_the_app_is_running_and_not_more_often_than_it_should`,
`web/src/components/TodayReminders.test.tsx`. Working hours never move a reminder the person set; only quiet hours hold it (6.35).

## 6.33 Promises (phase S1, designed 2026-10-19)

A promise is something someone owes someone: "I'll send it Friday" is the person's own; "they'll get back to me Tuesday"
is a waiting-on. Promises are **actions**, not a new kind of record: an action already has owners, a due date, done and
dropped, who did it and who reported it, follow-ups and holds, and its evidence in the ledger. Which way a promise runs
is read from it, never stored twice: owned by the person, it is theirs to keep; owned by someone else and promised to
the person, the person is waiting on it.

**What an action gains.**
- `promised_to`: the people it was promised to, by id (the person, for a waiting-on; the other party, for the person's
  own promise). Empty for a plain to-do. A promise is owed to whoever it is said to (F32): said to the To recipients
  with the person in Cc, it is owed to them and the person only watches it; "I'll send Sam the plan" is owed to Sam;
  "we'll" from the sender's team is not owed to the person unless the words say so.
- `basis`: said (someone said it outright) or inferred (the assistant read it between the lines), as facts carry it
  (6.7), with `said_by` when the input names the speaker. Never a model's confidence.
- `due_words`: the exact words the date came from ("by Friday", "early next week"), and `due_check` when the rules'
  reading is uncertain (next Friday, a past "this Friday", a year-less date far ahead), so the person checks it.
- `news`: what was heard that doesn't end it ("replied, but didn't say when"), each entry with its date, words and
  source.

**Dates by rules first.** `action.add` and `action.move` take `due_words`; the applier reads them with
`engine/due_phrases.py` against the date the input was received, and the rules' date wins over a date the model gave.
Anything vague stays "no date". A date tied to a known calendar entry is due at it (`due_at_event`, below); one tied
to an event with no entry ("once the keys arrive") stays "no date", with the event's words kept. A due date with no
words behind it is kept as given only when the person wrote it.
*The reader and what it can't read (batch B-7).* The reader steps past a leading lead word (`language.due_lead_words`:
"by", "on", "due", "due by", "no later than") and reads an ordinal day ("the 25th", "by the 30th", "on the 3rd"; the
endings are `language.due_ordinal_suffixes`) as the next day of the month with that number, marked to check when it is
read forward into another month; "Oct 22nd" and "the 25th of November" read too. Words it can't read as a date, by
whether they are a **condition**: a condition (words with one of `language.due_condition_words`, as whole words: "once",
"after", "before", "when", "until", "as soon as", "of receiving", "soon") keeps its words in `due_words` and has **no
date**, whatever date the model gave (a condition is never turned into a date); any other unread words **keep the
model's own date, marked to check** (`due_check`), where they used to drop it. The prompt says the same: a condition's
own words go in `due_words` with no `due` ("once the keys arrive"), and `waiting_for` is in addition to them, never
instead. A promise with both a day and a condition ("If the committee approves, I'll send it on Friday") keeps the
day's words as its `due_words` and the condition in `waiting_for`, and its text says the condition, so the day is never
lost (batch B-10). A bare weekday said on that weekday ("by Friday", written on a Friday) is read forward, as every bare
weekday is, and marked to check, never firm: it may mean today or a week later (`tests/test_due_phrases.py`). The open-actions list in the packet says "promised to" for a promise, so the assistant can tell which open
action takes `action.move`. *Built so far:* `tests/test_due_phrases.py` (a test per form, the words as settings, the
conditions), `tests/test_promises.py::test_a_leading_on_or_due_and_an_ordinal_are_read_by_the_rules_and_win_over_the_models_date`,
`::test_words_the_rules_cannot_read_keep_the_models_own_date_marked_to_check`,
`::test_a_condition_keeps_its_words_and_has_no_date_even_when_the_model_gave_one`,
`::test_the_reading_follows_the_language_settings_words`, and `tests/test_learning_run_b7.py` (every case that expects a
condition, and the cases that expect no date for words that are neither).
*Conditions and "before" (the functional designer's F21, 2026-10-20; batch B-7).* A condition that **waits for something to
happen** ("once the keys arrive", "after the workshop", "until you publish it", "as soon as …", "of receiving …") puts the
promise **on hold from the start**, waiting for those words (`on_hold.waiting_for`, the day it was added), where it used to
be merely dateless; an `action.add` that also names its own `waiting_for` keeps that wording. "Before <a meeting>" is **due
at that calendar entry** (`due_event`, so it moves with it) when the words after "before" name exactly one entry that is
still ahead (a title the words hold whole; the soonest of a repeating title; a title that is part of a longer matching one
is the same meeting), and has **no date with its words kept** when they name none or several ("before his leave starts").
Condition words that only leave the date open ("soon", "eventually") stay dateless and not on hold. Which words are which is
configuration, beside `language.due_condition_words`: `language.due_hold_words` (the ones that put a promise on hold) and
`language.due_before_words` (the ones after which an entry may be named). The golden cases that expect a condition say
`on_hold: true` (`promise-017-get-back-tavish`, `-021-send-ansel-estimate`, `-033-reply-oren-after`, `-052-return-averys-samples`,
`-055-inspect-room-avery`, `-064-keep-averys-draft`, `-067-reply-avery-after`, `thread-t12-m1-promise`) or `false` for a
"before" nobody can place (`-031-make-sure-tavish`, `-060-make-sure-avery`). *Built so far:* `tests/test_condition_words_hold.py`.

**How a promise ends, each an op with its evidence:**
- done: `action.close` (credited to its owners, with who reported it, as today);
- date changed: `action.move` (new `due_words`, or a date the person gives);
- called off: `action.drop` with the reason;
- partly delivered: `action.part`: what was delivered goes into its news, credited, and the text becomes what is left,
  which stays open;
- answered without an answer: `action.news`: the waiting-on stays open and says why. A reply that doesn't answer is news,
  never "nothing to record": a message where the promise was made (its thread, or from whoever owes or is owed it) that only
  acknowledges, thanks, praises, defers, asks to wait or turns to another subject, and doesn't deliver, move, part-deliver,
  drop or close it, is one `action.news` on the open action, with no fact, no second action and no ending. The prompt
  gives the mechanics and the core playbook the practice. *Built so far (batch B-7):* the eight golden `no-answer`
  cases, each checked to fail on a close and on an empty answer: `tests/test_learning_run_b7.py::test_a_reply_that_does_not_answer_is_news_never_an_ending_and_never_nothing`.

**Done needs delivery in the words** (the owner's lesson from running, 2026-10-20: "Mark this closed" isn't "done"). The
engine, not the model, reads the exact words an ending quotes (`engine/endings.py`), by three language settings
(`language.delivery_words`, `language.called_off_words`, `language.closed_words`; 4.6):
- *delivery words alone* ("sent", "finished", "it's in", "she did it") leave `action.close` as proposed: the owners are
  credited, and who reported it;
- *call-off words alone* ("moot", "covered by", "no longer needed", "we'll get it in the discussion", "will cover") make a
  proposed close an `action.drop` with the person's words as its reason: never done, nobody credited, nothing on the
  history others read;
- *"close" or "closed" with neither* (or delivery and call-off words together) is neither: the ending is held as **one
  choice on the item**, "Done by Ana, or no longer needed?", even when the note is the person's own. Done by the owner
  closes it and credits them; No longer needed drops it with the quoted words as the reason; each applies at once with
  Undo and records an `answered_assistant` signal, so the assistant learns what that person means by "closed". The person's
  own button on a screen is never read for words;
- words that say nothing about an ending leave a done for the person's own action as it was, but a done that would
  credit someone else is held as the same one choice: crediting a person for work nobody did is the costly mistake
  (`tests/test_endings_need_delivery.py::test_a_done_that_would_credit_someone_else_with_no_word_of_delivery_asks_and_the_persons_own_does_not`).
- **Already told:** calling off an action whose owner was told or chased drafts one line to them,
  `language.messages.called_off_notice` ("No longer needed, thanks: <the action>"), as a question of kind `action-notice` in
  To send for the person to copy and send; nothing goes out by itself, Undo takes the draft away with the drop, and nothing
  is drafted to the person or to someone they only watch or report to.
- **Moved into a meeting** (**built**): a call-off whose words hold one of `language.meeting_words` ("will cover", "in the
  planning sessions", "take it up") and name a meeting the workspace knows puts the action on that meeting's agenda,
  linked to it, in the same drop. The meeting is a calendar entry still ahead whose whole title the words hold (a title that
  is part of a longer matching one is the same meeting named less fully; the soonest of several with one title; one called
  off or already passed is never named), else a series whose title they hold; none or several means none, and the
  action is only called off, its words saying where it went. The engine names it on the drop (`action.drop`'s `event` or
  `series`), read from the words the same way for a close the engine turned into a drop and for a drop the assistant
  proposed, so a check and the apply that follows agree (the day is the day the input was received). Applying the drop,
  at once from the person's own note or on their keep from an input, adds the item (`agenda.add`'s item, by the person
  when the person's own words or keep, else by the assistant), and Undo of the drop takes both back. Built:
  `tests/test_agenda.py::test_called_off_into_a_meeting_it_is_dropped_and_put_on_that_meetings_agenda_and_undo_takes_both_back`,
  `::test_a_drop_the_assistant_proposed_with_such_words_is_put_on_the_agenda_too_and_waits_with_it_from_an_input`,
  `::test_a_series_the_words_name_gets_the_item_when_no_entry_is_ahead_and_the_next_meeting_gets_it_when_one_is`,
  `::test_words_that_move_it_to_no_known_meeting_only_call_it_off`,
  `::test_a_meeting_that_passed_or_was_called_off_or_is_named_twice_is_not_the_one_meant`,
  `::test_the_same_changeset_gives_the_same_ops_for_the_check_and_the_apply`,
  `::test_the_meeting_words_have_a_description_a_default_and_demo_values_in_both_workspaces`.
- The notes prompt says a closing note proposes `action.drop` unless the words say it was delivered, and the core
  playbook carries the practice ("done needs delivery; closed isn't done"). The endings' learning pairs are
  `promise-pair-23-covered-elsewhere`, `-24-closed-asks` and `-25-she-sent-it`.

*Built so far (B-7, "Mark this closed" isn't "done"):* `tests/test_endings_need_delivery.py` (done credits the owner, call-off
words drop with no credit and nothing in the completed history, a bare "closed" holds one choice from the person's own note
too, each answer applies with Undo and records its signal, a told owner gets the drafted line, the settings),
`web/src/components/TodayPromises.test.tsx` (the choice's line and its two answers), and the three pairs through
`tests/test_pairs.py`.

*Built so far (B-7, a meeting holds agenda items):* `tests/test_agenda.py` (the op, its tier and evidence, the one meeting
and one record it names, Undo, a held item from an input and its keep, what it refuses, the agenda not editable by hand, the
meeting's page, the series' page and Today's row reading it, and a call-off into a known meeting, a series, none, one passed
or called off, or two named, with the check and the apply agreeing) and `web/src/components/AgendaList.test.tsx` (the
meeting's page, the series' page and Today's row).

**Never a silent close.** An ending (close, drop, move, part) that comes from an input or the assistant's own initiative
is held for the person: one line that asks, "Close 'Send the floor plan'?" ("Drop '…'?", "Move '…' to Oct 22?", "Mark part of
'…' as delivered?"), with the words it came from and who said them, and two buttons that name the result ("Close it" and
"Keep it open"; 7.6), with Change in the menu. One from the person's own note or a button applies at once with Undo. `action.news` changes nothing about the
promise and applies at once, shown on it. A held ending kept by the person counts as seen (6.32's silent closes).

**No news by its date.** A promise past its date with no ending and no news is on a line with its choices. For the person's
own it is a line of its own with Done, New date and Drop. For a waiting-on, it is **on the follow-up line for the person who
owes it** ("Follow up with Ana · 2 overdue, oldest Tue, Oct 13", **Draft a nudge**: one line per person however many items,
7.7), whose message lists it with the rest the follow-up rule (6.9) says is due; each item in the open line has its own
Followed up (a nudge: it stays open), They finished it, hold, Change this and Drop. A waiting-on's line follows the stance of whoever owes
it (6.34): *I manage them* and *I work alongside them* get the follow-up line and its draft; *I report to them* gets no
follow-up and no draft, only a line of its own, "Waiting on Ana: the budget answer, due Tuesday", with New date, Done and Drop; *I only watch*
gets no line at all, though the action still counts as covered, so no other line picks it up. A person with no stance has the default stance. A reply owed (6.35) is the person's own and is never gated by stance. A nudge never ends it. A waiting-on is not left to go stale: with a date it
is due a follow-up from `steward.chase_dated_days` (7) before the date, and once the date has passed; with none, after
`steward.chase_undated_days` (14) with no news since it was made or since its last news (it joins the person's follow-up line,
"no date, nothing heard for 14 days" in its row). One chased lately waits as long again. Never while it is on hold.
**News mustn't silence the chase clock** (the functional designer's F22, 2026-10-20; batch B-7). A reply that doesn't answer
is news (`action.news`, which records it as `non_answer` on the news entry; a part delivered and a call-off carry none, and
an entry written before this had none either, so it keeps the rule it had). The first non-answer since the promise's line
began restarts the clock **once**: for a dated promise the line is quiet for `steward.chase_dated_days` (7) from that
reply, for an undated one for its `chase_undated_days` (14); a **second** brings the line back at once with the news shown
("Robin replied twice without a date: ask again?"; `replies` on the line, on the promise's own line and on the person's
follow-up line). News of any other kind still ends the wait for its day. *Built so far (F22):*
`tests/test_news_does_not_silence_the_chase.py` (an overdue waiting-on with two non-answers gets its line back),
`web/src/components/TodayPromises.test.tsx`.
*Built so far (batch B-7):* the one follow-up line per person
(`promises.waiting_on` and `promises.is_follow_up` give the list `followups.sections` and Today's queue share, so the line and
the message it opens cover the same items): `tests/test_follow_up_lines.py`, `tests/test_promise_lines.py`,
`tests/test_stance_lines.py`.

**Every promise shows why:** the exact words, who owes it to whom, the date and the words it came from, where it came
from (a link to the source), and "said" or "inferred". Each of these is one click to correct, and each correction is a
signal (6.22).

**Where promises come from:** every input, the person's own sent mail and notes included. When a mailbox is connected,
its sent folder is offered as a second source, taken in quietly like any new source (6.32). A message's new text is
split from its quoted history and signature first (`engine/reply_split.py`), so a promise quoted again is never found
twice, and automatic mail never ends a promise (`engine/automatic_mail.py`). Messages join their conversation by rules
(`engine/mail_threads.py`), so a reply is read against the promises of its thread. An answer that leaves a reply in a
promise's thread without any op on that promise goes back once to say what the reply said (F30): a reply joins a
promise's thread by rule when its quoted history holds words the promise was recorded with (a quote of at least four
words, from the ledger), and otherwise is read as before. Such a reply is about that promise, so news, a new date or a
part from it fits the promise whatever its own words (the `evidence-fit` lint accepts it). *Built:* the lint
`thread-promise-unanswered`, `tests/test_thread_promise_lint.py`; joining watched mail by the conversation the rules
join (`engine/mail_threads.py`) when its history quotes none of the promise's words is not built.

**Evaluation:** the 120 single examples and 25 whole threads (`docs/project/steward-promise-*.yaml`) become golden cases,
and the twenty learning pairs become harness pairs in a workspace's `pairs/` folder.

*Built so far (S1):* the fields, rules-first dates, `action.move`, `action.part` and `action.news`, and endings from an
input held for the person (the person's own note, edit or sent mail applies at once; keeping a held close credits who
the input said reported it) (`tests/test_promises.py`). **On screen:** every promise shows why (the words, who owes it to
whom in the owner format, the day with its words and "Check this date", where it came from, "Said" or "Worked out", the
news under it, newest first, a delivered part credited to the owners), each of owner, promised to, day and basis one click
to correct from a list or date picker as the person's own edit with Undo, a signal the assistant learns from
(`tests/test_promise_routes.py`, `web/src/components/PromiseWhy.test.tsx`); a held ending reads as one line that asks,
"Close 'Send the floor plan'?", with its words and who said them under it and the two buttons that name the result, Change
in the menu (`tests/test_promise_lines.py`, `web/src/components/TodayPromises.test.tsx`); a promise needing a look is one Today
line with its choices and on no other line: the person's own past their day, and those owed by someone else from
`steward.chase_dated_days` (7) before their day or past it, or, with no day, after `steward.chase_undated_days` (14) with
nothing heard, never while on hold or with news since their day (`tests/test_promise_lines.py`); the sent folder offered
under a mailbox, the server's marked folder picked, taken in quietly (`tests/test_sent_folder.py`,
`web/src/components/Sources.test.tsx`). The prompts and playbook entries ask for promises both
ways, and the golden cases and harness pairs are in demo-b (`tests/test_followups_backup_eval.py`,
`tests/test_evaluate_harness.py`). *Not built yet:* the sent folder offered by a plugin's sign-in sources.

**From three weeks of running** (the designer's S1-1 notes, 2026-10-19, `docs/project/designer-s1-1-notes-2026-10-19.md`):
- **On hold until a trigger** is its own state: `action.hold` stores what it waits for, and a held promise is out of due
  and overdue everywhere. Taking it off hold can carry its new date (`action.unhold` with `due_words`), as one step;
  read from an input, it waits for the person's Keep like any date change. A promise that holds only once something
  happens ("once the keys arrive") is added on hold from the start (`action.add` with `waiting_for`).
- **Owed to the person, whatever the team:** a promise made to the person by someone on another team is one they wait
  on, so the other-team check (6.18) lets it through (`tests/test_scope_slice.py`).
- **Due at a meeting:** `action.add` with `due_at_event` and its `event` is due on the entry's day (`due_event`) and moves
  when the entry moves (`event.set`, or the person's own edit), as a date-only move with no news.
- **The chase clock:** a promise owed to the person gets a line only after `steward.chase_undated_days` (14) days with no
  news when it has no date, only within `steward.chase_dated_days` (7) days of its date or once past it when it has one,
  and never while on hold.
- **Dates read against the message:** a mail message's source keeps `sent_at`, with the sender's own offset, and the
  rules read its words against that day and zone, so the same thread read on its day or ten days later gives the same
  dates.
- **One promise per owner:** a promise with two owners is refused ("add one action for each person who owes it"); an
  owner that isn't a known person waits for "Pick an owner".
- **One promise from several sources:** a new promise with the same one owner, owed to the same people, in nearly the
  same words (`checks.tuning.near_duplicate_action.similarity`) and a date within
  `checks.tuning.near_duplicate_action.date_window_days` (3) of an open one is added to it quietly (`also_said`, every
  quote kept). When the dates disagree, the person's own words win, otherwise the newest, and the other date is a news
  line on the promise. **A restatement with a new date** (the same owner, people and nearly the same words, but a date
  outside the window: "I'll send it Friday", then a week later "I'll send it the Friday after") is an `action.move` on
  the open promise, never a second promise: read from an input it waits for the person's Keep, and the line shows both
  quotes.
- **Crediting and chasing:** the person's "I pinged her" is news and the promise stays open; "Sam sent it" closes it,
  credited to Sam and reported by the person.
- **Two names, one person:** a second spelling of two or more words that the person confirms in "who is this?" becomes an
  alias on that person; a bare first name never does, since it could later match the wrong person unasked.
*Built (S1-1):* `tests/test_promises.py`; the chase clock with the promise screens.

## 6.34 Stance: who each person is to the person (phase S1-2, designed 2026-10-19)

The designer's lessons from running (2026-10-19): polite, accurate questions to another team's architect were each the
wrong thing for this person to send that person ("not my job to tell the architects how to do their jobs"). Another user
might manage those architects and want exactly those questions. So who each person is to the person decides what the
assistant may draft or ask them. It is the person's own rule, kept per person, beside the role per project (6.18).

- **The stance** is a field on the person record (`stance`) with four fixed meanings, because the gate reads the
  meaning: `manage` (*I manage them*), `alongside` (*I work alongside them*), `report_to` (*I report to them*) and
  `watch` (*I only watch*; someone marked `track_only` counts as this). The words on screen come from the wording
  sheet, so personal life can use its own words for the same meanings (a client, family). A value list (6.31) can't
  hold a meaning per value, so it isn't one. A person with no stance has `steward.default_stance`, *I work alongside
  them* by default: quizzing someone you don't manage costs more than a missed question.
- **What the person tracks** is a setting, `steward.tracks` (delivery dates and decisions by default; design quality is
  an option): a person who tracks dates gets no design questions drafted, whatever the stance. A per-project override
  is not built yet.
- **The gate on drafts and questions**, checked in the applier on every question or drafted message to someone other
  than the person:
  - *manage*: anything within what the person tracks, design detail included, and chasing their dates;
  - *alongside*: follow-ups on promises made to the person, and an apparent big mistake: a contradiction with a recorded
    decision or fact, with links to both sides; nothing a standing rule already answers, and no questions about how
    they do their own work;
  - *report to*: no chasing at all; a question to them is drafted only when the person asks for it;
  - *only watch*: nothing is drafted to them.
  The question's kind (`asks_about` on `question.add`: date, decision, design, mistake or other) is the model's label,
  so the gate is a lint, `stance` (one return, then a hold for the person, like the scope checks of 6.18), and a
  "mistake" with fewer than two links to what it contradicts is returned the same way. The packet's people list says
  who each person is to the person and what the person tracks, so the model can ask only what is allowed. The
  person's own note asks whoever it says.
- **Corrections propose a stance.** A reply like "not my job" or "we are not their boss" about a question to someone
  becomes a proposed stance for that person, or for their role, which the person keeps or changes (6.22). It is
  probably the most common correction a steward gets. The proposal is the op `person.stance` (the person, one of the
  four stances, evidence), a system op the learning task may propose: it is held for the person's Keep like every
  system op from the assistant, and never applies on its own. For someone's role there is no op yet.
- **Choosing a stance.** The person's page has a list of the four meanings (and "Use my default"), saved at once as
  the person's own edit with Undo. Settings shows `steward.default_stance` as a list and `steward.tracks` as ticks.
- **Not yet:** the full scope resolver (6.18, phase E) takes the stance as one of its inputs; until then the gate above
  is the whole of it.

*Built so far (S1-2):* the field, the two settings, `asks_about`, the gate and the packet's people list
(`tests/test_stance.py`); choosing a stance on the person's page and the two settings' plain labels
(`web/src/components/StancePicker.test.tsx`); the chase line by stance, "Waiting on" for someone the person reports to
and no line for someone only watched (`tests/test_stance_lines.py`, `web/src/components/TodayPromises.test.tsx`); the
op `person.stance` held for the person's Keep, offered to the learning task; and the learning pairs for each stance
(`workspaces/demo-b/pairs/stance-*.yaml`). Left: a stance for a role rather than a person, drafted messages other than
questions, and the send line ("Send <name> their actions"), which still counts actions owed by someone only watched.

## 6.35 Drafts to other people, replies owed, and the week (phases S1-2, S1-3 and S2, designed 2026-10-19)

The designer's notes for S1-2, S1-3 and S2 from their running version
(`docs/project/designer-future-notes-2026-10-19.md`). Each point lands in the batch the designer named.

**Learning from the sent version (S1-2).** The person's sent message is the best teacher a draft gets, and it is
already in the configured sent folder.
- When the sent folder is read, a sent message is matched to the draft it came from: the same recipient, sent within
  `steward.sent_match.window_days` (a setting, 7) after the draft was copied, and text at least
  `steward.sent_match.similarity` alike (a setting, 0.6; the share of words the two have in common). A match is
  one-to-one, the newest unmatched copy first; nothing is matched by the model.
- The difference between the draft and what was sent is recorded as a style signal (6.22, the correction kind
  "edited before sending"): names replaced with roles, a promise cut, a softer opening. It becomes a proposed style
  note through the usual learning loop, never a rule on its own. This is the style pair, brought forward from L-more.
- A matched sent message ends the reply owed it answered, credited to the person, with the sent message as evidence.
- A draft the person copied that has no matching sent message after `steward.sent_match.ask_after_days` (a setting,
  2 by default) becomes one Today line: "Did your message to <name> go out?", with *Yes, another way*, *Not sent* and
  *Still to send*. A draft the person never copied asks nothing, and so does a person with no sent folder being read.

- **An approved draft isn't done** (the functional designer's F19, 2026-10-20; batch B-7). Approving or copying the draft
  the assistant made for an action (6.7, "hand an action to the assistant") **leaves the action open**: a nudge isn't
  completion. The approved text, or the one copied (`POST /api/actions/{id}/work/copied`, which also keeps a draft still
  waiting), is kept as a `copy` of kind `work`, for the first person the action was promised to, else the one whose message
  asked. It ends when **the sent version is seen in the sent folder**: the match above ends the action at once, as the
  person's own act, with the sent message's first line as the evidence (the person's own sent mail applies at once, 6.33),
  or when the person marks it done. With nothing matching sent after `steward.sent_match.ask_after_days` (2), the same
  line asks "Did your message to <name> go out?" (only while a sent folder is being read, and not once the action is
  over); answering that it went another way, or never went, settles the copy and leaves the action to the person. A draft
  for nobody known is kept but never matched or asked about. *Built:* `tests/test_approved_draft_is_not_done.py`.
*Built so far (S1-2, learning from the sent version):* each copy of a follow-up or a drafted reply is kept as a `copy`
record with the text exactly as copied; the sent folder's messages are matched to copies by rules in the pass that ends
replies owed; a differing pair records `draft_edited` with the sent text and an identical one records nothing; and the
unsent line has its three answers, each with Undo (`tests/test_sent_version.py`,
`web/src/components/TodaySentCheck.test.tsx`); the style pair is `workspaces/demo-b/pairs/sent-version-roles.yaml` (the
correction kind `sent_version`, `tests/test_pairs.py`). Left: a follow-up message to chase (`mark_followed_up`) is not
kept as a copy yet; and a copy for a sender nobody knows is kept but never matched. Style notes now reach a run's
packet as "How to write for them": those for the people the input names, and those for a kind of audience in words
(`engine/knowledge_section.py`; the pair checks the heading reaches the later draft's packet).

**What a draft to someone else carries (S1-2).** A message drafted for another person carries only what they need.
These are lints on every draft addressed to someone other than the person (severity in `config/checks.yaml`; one
return, then held for the person when the draft will reach someone, per 6.22):
- *no bookkeeping*: no record ids, internal terms, stances, scores or "the assistant noticed"; the record ids and
  `language.internal_terms` are the deterministic part (the lint `bookkeeping`);
- *only openable links*: a link the reader can't open is left out (the rule questions already follow, 6.8);
- *no long quotes back*: a quote is at most `checks.tuning.long_quote.max_words` (a setting, 25 by default); the rest
  is a link or a summary;
- *never single a person out*: a draft to several people never names one of them as the cause of a miss; a
  discrepancy in one person's work is asked of that person privately, in a draft to them alone. Naming is the model's
  label, so this one is a lint with a return, not a refusal.

*Built so far (S1-2):* the `bookkeeping` and `long-quote` lints on a question to someone else and on a drafted reply
(`tests/test_reader_checks.py`); openable links were already refused (6.8). Left: never singling a person out, which
needs drafts to several people (S1b), and its learning pair.

**One message per person per batch.** Everything one gap needs is one ask, never three messages about one gap. All the
asks to one person go out together: one message per person per batch, the asks numbered inside it, sent now or held
for a later batch. Each ask keeps its own id, so each is answered and tracked on its own. An ask made for someone who
already has a message waiting joins it instead of becoming a second draft the same day. The grouping is by rules, from
the asks' recipients. *Today:* follow-ups already compose one message per person with every waiting question numbered,
each question keeping its id (`engine/followups.py`); holding a message for a later batch is not built.

**How a reply owed ends (S1-2).** Besides a sent reply, a reply owed ends when:
- the person marks it *Answered another way* (a call, a meeting, a chat), optionally with a few words that become the
  evidence;
- *someone else on the thread answered it*: a later message on the same thread, from another recipient, that answers
  the ask. Read from an input, this ending waits for Keep like every other ending (6.33), and the line names who
  answered.
"No reply needed" stays a choice the assistant learns from (6.22).

*Built so far (S1-2, replies owed):* `action.add` takes `reply_owed`, and the applier stores `reply_owed`, `replies_to`
(the input's source) and `asker` (the person its sender is, when known) on the action; before it does, the rules in
`engine/replies_owed.py` read the message's headers and new text, and automatic mail, mail the person sent and a message
that says no reply is needed are refused (`reply-not-owed`, a refusal rather than a return: the rules are certain
there, and a message whose headers can't be read is left to the model's reading). Each open reply owed is one Today line
in "Send and follow up", oldest message first, `Reply to {name}: {subject}`, with the draft under it marked as a draft
until the person has copied, edited or written it: Copy reply (which approves it as it is) is the one button, and the
menu has No reply needed (a drop with the reason, recorded as the `no_reply_needed` signal the learning loop reads),
Answered another way (a short form with the cursor in the words; closes it as done, credited to the person, the words
as the evidence) and Edit. A message the person sent on the same conversation to the asker after the ask ends it at
once, as their own act, by rules when the sent folder's mail is taken in (`engine/reply_lines.py`, one conversation by
`engine/mail_threads.py`: the same subject and a person in common within `steward.reply_thread_days`, 14 by default,
because the mail details carry no thread headers yet); an answer from someone else is the model's `action.close` held
for Keep, whose line names who answered, and the open list a run reads marks each reply owed so it can be closed
(`tests/test_reply_lines.py`, `web/src/components/TodayReplies.test.tsx`, the golden case
`workspaces/demo-b/evals/reply-owed-answered-by-another-recipient.yaml`).

**A sender's distribution limit travels with the content (S1-2).** Some messages say who may see them: a marking
("internal only", "not for the client"), a named group, or the sender's own words.
- When a message carries a limit, the source records it as its audience: the named group, or the message's own
  recipients when no group is named. Recording a limit only narrows, so it applies at once from the input; widening it
  is the person's alone (a person-only change) and is recorded with who widened it.
- Every record that takes evidence from a limited source carries the limit (the most restrictive one wins when it has
  several). A draft is refused (an invariant: deterministic, from the evidence's sources and the draft's recipients)
  when any recipient is outside the audience of a source it draws on, and the packet for a draft to someone outside
  an audience leaves that source's content out entirely.
- Proven with a restricted and an open message in one area: a draft to someone outside the group draws only on the open
  one, and a draft to the group may draw on both.

*Built so far (S1-2, the limit on a source):* a message whose new text (not its quoted history) holds one of the
`language.limit_markings` phrases (whole words, ignoring case) gives its source an `audience`: the people on its From,
To and Cc lines, known people by id and anyone else by lowercased address, with the `marking` and the sentence it was in
(`why`); no marking, or a text with no From and To lines, means no limit. `source.limit` (data tier, evidence, only on
the input's own message) narrows the audience to a group the message names and refuses a widening; `source.widen`
(person-only) adds people or removes the limit, records `widened_by`, and Undo restores the narrower audience. The
invariant `audience` refuses a `question.add`, a rerouted `question.move`, or an `action.add` with a drafted `reply`
when a source it draws on (the input's own, the one a quote of its evidence is from, a rerouted question's own; a reply
owed does not count the message it answers) has an audience the recipient is not in; the person is never outside one.
The saved text of a limited source shows "Limited to: <names>" with the sentence and a Widen choice with Undo
(`tests/test_audience.py`, `web/src/components/SourceLimit.test.tsx`).

*Built (S1-2, what is made from a limited source):* a fact, an action or a question carries the limit of the sources its
`source` and its evidence name, the narrowest when there are several. The limit is derived from the sources when it is
read (`audience.limit_of_record`), not copied onto the record, because every reader can follow the reference and a
widening then reaches everything made from the source. The `audience` invariant also refuses a `question.add`, a
rerouted `question.move` or a drafted reply that names (by id, in its title, text, reply or "matters for") a record whose
limit the recipient is outside. Packets for a draft to a named reader leave such records out (`audience.left_out_for`):
the notes run, whose reader is the input's sender (open actions, open questions and the facts section), and the follow-on
run, whose readers are the people a tied record already reached (the tied records and the moved records). An input's own
text is never left out of its own run. Runs with no named reader are not filtered: asks and learning runs go to the
person, who is never outside a limit, and a plugin's draft names its reader in its own packet. Not yet: the drafted
follow-up message (`followups.compose`) does not check a to-do's limit against its owner, and singling a person out in a
group draft, with its learning pair, waits for drafts to several people (S1b). (`tests/test_audience.py`,
`tests/test_follow_on.py`)

**What changed since yesterday says what the assistant did (S1-2).** Each line names the act and its reason in the
assistant's own voice ("Closed the floor plan promise: the owner said it was sent"), and anything the assistant closed,
moved or merged without the person seeing it is one step from the line: the record, its evidence and its Undo.

*Built so far (S1-2, the list and its line):* `engine/since_yesterday.py` lists what the assistant or a rule did since
the start of the previous day in the person's time zone, or since they last opened the list when that is later, newest
first and one entry for each record: added, closed, moved, merged, dropped, set aside or news heard, the record's words,
the reason with the exact quote and who said it, whether the person has seen it (closes by the silent-close rule of
`engine/closes.py`, anything else once the change is looked over), and the change and op, rule's close or mail to undo.
The person's own changes, held items and ops released from held are left out. Changes the rules make say so: a reply
owed closed by the person's sent mail ("you replied on <day>", the change carries `by_rule`) and a promise whose date
followed its meeting. The last look is one small `look` record for each person that only moves forward. One Today line,
`Look over what changed since yesterday`, with the counts in plain words, sits in the risk group below promises, goes
when the list is opened (`GET /api/since-yesterday`, then `POST /api/since-yesterday/seen` with the moment it was drawn,
so a change that arrived meanwhile is not swallowed) and comes back with the next change. The "Since yesterday" screen
(from the line and from What changed) has Open on each row and Undo in its menu. Built: `tests/test_since_yesterday.py`,
`web/src/components/SinceYesterday.test.tsx`, `web/src/components/TodaySince.test.tsx`.

**Work the assistant releases on its own keeps the person's hours (S1-3).** Anything the assistant releases without
the person's act at that moment (new lines it adds to Today, a reminder it set itself, a notification, work held until
an event that comes in at night) waits for the person's working hours, and never lands in quiet hours (both are the
existing settings). A time the person chose (a reminder for 7:00) is kept as chosen. What waited arrives together, as
one group, when the hours start.

*Built so far (S1-3, hours):* a line the assistant or a rule adds on its own is held while the moment its cause came in
has no release yet: the first moment that is inside working hours and outside quiet hours (`engine/reminders.py`
`release_at`, from the `steward.reminders` settings). The cause is the input's own received time for a line made from an
input, else when the line's record was made. Held kinds: decisions, questions, who-is and owner questions, moved
meetings, held items, runs waiting for a go, refusals, reviews, replies owed, learned proposals, unfiled items and the
since-yesterday line. Never held: a reminder the person set (kept as chosen; working hours no longer move it, only quiet
hours hold it), anything made from the person's own note, the person's own setup (first go, catch-up go, intake go,
what an intake found), lines that report a stop (restart, handover, paused, borrow, offline, failed, account and
credential checks, an unread source, a missing account, a kind of file not read), and lines that have no moment of
arrival because a date passes or a count builds over days (overdue, promises, send, nudge, the rules review, the
catch-up list, a copy not found sent). What waited arrives together: the lines keep their places and one row, `While you
were away: N things arrived`, sits at the top of the first group any of them is in and goes with that day; the
browser notifies only for reminders, which are never held, so a held line never notifies. `steward.hold_outside_hours`
(on by default, live) turns holding off. Not built: work held until an event the person named (nothing holds work
until an event yet; `release_at` is the rule it will use), and Today lines that running plugins add, which are not held
(`tests/test_release_hours.py`, `web/src/components/TodayAway.test.tsx`).

**The Monday briefing (S2).** On the first open of the week (the day is a setting):
1. **A copy-ready message to whoever the person reports to**: the people whose stance is *I report to them* (6.34).
   It is a draft under the rules above (unreviewed until the person copies it), covering what was done, what moved and
   what needs them. With nobody marked, the briefing asks once who it is for.
2. **This week**, through the last working day: promises due by owner, overdue first; questions to send; answers to
   chase; decisions waiting. Built from the records by rules.
3. **Goals:** three to five for the week, proposed from what is due and open, which the person confirms, changes or
   drops. Confirmed goals are kept for the week and read by the morning brief.
Nothing already on Today is repeated in the briefing; it links to Today instead.

**Built (S2, the Monday briefing):** `GET /api/brief` makes it on the configured day (`steward.brief.weekly_day`) and offers
it beside the morning brief on the later working days of the week until the week's goals are confirmed. *This week* is the
person's promises through the last working day, what others promised them, the questions held to send, the answers to
chase and the decisions waiting, overdue first; what Today already has a line for is left out and counted ("N more things
are already on Today"). *Goals* are kept on a `week_plan` record for the person and the week, which is the person's own
words and only theirs (`PUT /api/brief/goals`: between `steward.brief.goals_min` and `goals_max`, answered with what it
replaced, which sending back is Undo); until confirmed, up to the most are proposed from the person's own open to-dos
due through the week, to confirm in one press or change. The morning brief carries the week's confirmed goals. *The
message* is the core draft kind `monday-message` on the record's `message` text: asked for with `POST /api/brief/message`,
estimated and held for the person's go like every draft, written from the week's facts under the draft rules, shown
as "Draft, not yet reviewed" and made the person's by Copy (`POST /api/brief/message/copied`); setting it aside is a
signal like any draft's. It is for the people marked "I report to them" and absent when there are none. **Left:** drafting
the message as an act the person approves (Copy only today), and asking once who it is for when nobody is marked
(the section is simply absent). `tests/test_brief.py`, `tests/test_brief_week.py`,
`web/src/components/BriefCard.test.tsx`.
