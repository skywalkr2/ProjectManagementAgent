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

**On screen:** the folder is a section of Sources beside Auto-closed, one row per message (subject, sender, date, why it was
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
**More reported speech, and two that aren't** (functional designer's answers, 2026-10-15; built, roadmap L7): "mentioned", "replied", "responded",
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
  `tests/test_next_steps.py`.

`event.add` (data tier, offered to reading notes) adds a calendar entry to the app's own calendar: a title, a start (a
day, or a date-time), an optional end (the last day or moment of a range, included), the project it belongs to, and
evidence, which is required. **Calendar entries are for real events only** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7): meetings, launches, delivery
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

**Follow-on changes** (functional designer's lessons from running, 2026-10-15; roadmap L7). The links, the series and the
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
marking a meeting done starts no run (its notes come in as their own input). The meeting's agenda and its items belong to
the project management pack (6.24), which builds on these links. From the functional designer's answers (functional designer's answers, 2026-10-15; roadmap L7):
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
  `dispatch.knowledge.follow_on_match` of a replaced fact's words, at most `follow_on_max_tied`; each is shown as it is
  now with why it is tied and the people it already reached (those an action's notice told or a chase followed up, the
  person a sent question went to). It gets the knowledge section like every task kind and logs it. It may only
  `record.set` the day or words of a tied action no one was told about (applied, with Undo), `question.add` a correction
  for a person a tied item already reached (open, so it waits for the person; nothing is sent) and `note`; the applier's
  `follow-on-reach` check refuses anything else, and the packet marks every record as outside content. A request whose
  move was undone or changed again before it runs is closed without a call
  (`tests/test_follow_on.py`, listed in the roadmap's L7 item; replay `moving-an-entry-moves-the-action-tied-to-it`).
  *Not built:* the assistant's own move of an entry's day (no op changes an entry's day; the trigger fires on any change
  to the fields), the tied candidates "due before the new day and settled there" and "said to be covered there", a
  correction for an action's notice with no link to carry (it becomes a note), and a move written by a connected
  calendar's sync.
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
  PM when nobody is named. The assistant marks each question with a kind (question, decision, and the routing, impact and
  notice kinds), and the screen follows the stored kind: a question of kind `decision` shows as a decision, and one of kind
  `question` shows as a question to answer; a decision to someone else shows in the PM's follow-ups under that person.
  Keeping the kind makes the assistant's call checkable and lets a mistaken one be corrected. An option offered inside an
  answer ("there is a feature we can turn on") is a decision for whoever decides. Moving a decision to someone else
  keeps it a decision (`question.move`, below). Its Today line ("Waiting on <name>'s decision: blocks <action>") comes
  with the dependencies of the project management pack (phase P, 6.23). **Built:** `web/src/components/FollowUps.test.tsx`
  ("a question to the PM shows as a decision or as a question by its stored kind"),
  `tests/test_corrections.py::test_moving_a_decision_to_someone_else_keeps_it_a_decision_records_routed_and_undo_sends_it_back`,
  and the prompt and golden cases below.
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
- Aging: "waiting Nd" after Mark sent (built); chase suggestions by the one follow-up rule (6.9, built); one escalation suggestion when `routing.escalation` says so (4.3, 6.24; *designed, phase C2*, with the
  project management pack: no `routing` setting exists today).

**From the functional designer's answers** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7):
- **A question someone asks the person** is one item: an action owned by the person ("Reply to the shop: when the cover
  proofs ship"). When the facts hold the answer, the action carries a drafted reply, ready to copy, citing the fact and its
  source; when they don't, it carries no draft and says what's missing. Never an action and an output for one reply.
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
  **Built:** Followed up adds the day to the action's `followed_up` for that person and sets their told day to the same
  day, so the waiting count starts over; undo removes the day and puts the told day back (`tests/test_followups_backup_eval.py::test_followed_up_records_a_chase_keeps_the_action_open_and_counts_as_told`, `tests/test_followups_backup_eval.py::test_undoing_a_chase_restores_the_told_day_and_removes_the_chase`). They finished it
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
  its first owner). Taking it off hold when an input says the wait is over is *designed, phase L3b, not built*
  (`tests/test_on_hold_and_follow_ups.py::test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date`,
  `tests/test_on_hold_and_follow_ups.py::test_a_hold_needs_words_and_an_open_action_and_undoing_it_records_no_signal`,
  `tests/test_on_hold_and_follow_ups.py::test_an_action_on_hold_is_never_overdue_on_the_to_do_list_or_in_todays_queue`,
  `tests/test_on_hold_and_follow_ups.py::test_the_to_do_list_view_says_what_a_held_action_waits_for`).
- **The follow-up rule** (built). One function, `follow_up_due` in `engine/followups.py`, decides whether something sent to a
  person is due a follow-up; Today's `nudge` lines and the Follow-ups pills both read it, so they agree
  (`tests/test_on_hold_and_follow_ups.py::test_today_and_the_follow_ups_view_agree_on_what_is_due_a_follow_up_and_on_hold_leaves_both`). A question that went
  out is chased after `ui.followups.question_after_days` days with no reply (default 4). A told action is chased only when
  its own due date is within `ui.followups.action_due_within_days` days (default 7) or past, and only after it has waited as
  long as a question; an action due later is left alone, so a deadline weeks away is not nagged about. An action with no
  due date is chased after `ui.followups.undated_after_days` days with no word (default 14). An action on hold is never
  chased. A chase starts the wait again (it counts as told again, above). The Follow-ups pill reads "waiting Nd" and, once
  the rule says it is time, "waiting Nd · follow up" in the warning color, so status is never color alone. `ui.today.nudge_after_days`
  is replaced by `question_after_days`: a workspace file that still has the old key is read as the new one
  (`tests/test_on_hold_and_follow_ups.py::test_the_old_nudge_setting_is_read_as_the_question_wait`). Each branch has a test
  (`tests/test_on_hold_and_follow_ups.py::test_a_told_action_due_far_ahead_is_not_chased`, `tests/test_on_hold_and_follow_ups.py::test_a_told_action_due_soon_is_chased_once_it_has_waited`,
  `tests/test_on_hold_and_follow_ups.py::test_a_told_action_just_sent_is_not_chased_even_when_due_soon`, `tests/test_on_hold_and_follow_ups.py::test_an_overdue_told_action_is_chased`,
  `tests/test_on_hold_and_follow_ups.py::test_an_action_on_hold_is_never_chased`, `tests/test_on_hold_and_follow_ups.py::test_an_undated_told_action_is_chased_after_the_undated_wait_and_not_before`,
  `tests/test_on_hold_and_follow_ups.py::test_a_sent_question_is_chased_after_the_question_wait_and_not_before`,
  `tests/test_on_hold_and_follow_ups.py::test_the_rule_reads_every_threshold_from_the_settings`).
- **Reassign:** swap one person in the owners list, keeping their team ("Product (Jane Doe)" to "Product (Sam Lee)"); the
  other owners stay. Told dates, Followed up and They finished it are per person. *Designed, not yet built, phase B* (edit,
  close and reassign from the row). Told dates are per person today; the only way to change an owner is to edit the whole list
  on the record page.
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
scheduled*: a new workspace with imported actions shows each as to send). Owners marked `track_only` get no notices
(*designed, not yet built, not scheduled*: the flag is stored and shown, and notices do not read it).

## 6.11 Names and identity

People, teams and projects are referred to by id everywhere (5.1). Names are resolved once, where they come in, and rendered
wherever they are shown.

- **Resolving** (every write path: AI ops, PM forms, edits pulled back from published pages; the last is *designed, phase C4*,
  with the publisher): an id passes; a full name or
  alias that matches one person becomes that id; the PM's aliases become the PM; a bare first name (one that no one has set as an
  alias) becomes a person **only when that person is in the input's context**, and only if exactly one person of that first
  name is; a first name with an initial or surname fragment ("Ada L.") becomes the one person that fragment fits, and when it
  fits no one the op is held and the people who share the first name are offered, however many of them are in the thread;
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
- **Rendering:** owners in `owner_format` ("Product (Jane Doe)"), recipients by full name, greetings by first name. Changing
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
| **Decide** | work held until a restart (`restart`, "Restart to run 7 waiting requests", always first; built, `tests/test_silent_stops.py::test_the_restart_line_comes_before_the_first_go_and_before_decisions`); a decision or a question put to the PM (`decision`, `question`); a name the assistant couldn't place (`who_is`, "Pick who 'Maya' is"); an action with no owner (`owner`, "Pick an owner"); an item the applier held for the PM's yes (`held`); a run waiting for the PM's go because of its cost (`go`); a run the provider refused, waiting for the PM to choose what happens next (`refused`) |
| **Risk** | work that failed (`failed`); an AI account paused until its limit resets, with the time and the count waiting (`paused`, built, `tests/test_silent_stops.py::test_a_paused_account_is_a_risk_line_with_the_time_and_the_count_waiting`); work that has waited for the network longer than `dispatch.offline_line_after_minutes`, one line with the count and since when (`offline`, built, `tests/test_silent_stops.py::test_a_lost_network_is_one_today_line_after_the_configured_minutes_and_goes_when_it_is_back`); a learning check that failed after a switch, with Switch back (`switch_failed`, *phase L*); the PM's own overdue to-dos, as one line, leaving out any on hold (`overdue`) |
| **Review** | the assistant's work waiting for a look (`review`), with what it did counted by kind (actions added or closed, questions, notes, recorded, people, projects, drafts, held, refused); learning proposals from corrections waiting for Keep (`learned`), the daily card of learning from inputs (`learned_daily`) and the catch-up list (`learned_backlog`), all *phase L*; a new or probation account's work, marked as such (*phase L*) |
| **Send** | messages to send, one line per person (`send`); something sent to a person that is due a follow-up by the rule in 6.9 (`nudge`: questions sent and actions told, 4.11) |

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

**What a model can do, measured: the capability matrix** (owner, 2026-10-15: "very full featured … not just in claude
but all the others"; step 1 (the skills list, the matrix, staleness and the grid in Settings) is built, apart from
"Measure" and the export, which the roadmap lists; step 2 (using it) is *designed, not yet built*; roadmap L7 step 1,
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
- `classify_error(exit_code, error_stream, transport_error) -> rate_limited | quota | auth | timeout |
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

**Data handling.** Each provider has `allowed_data` levels. Inputs marked restricted only go to providers allowed to see them; if
none is, the request goes to the PM instead. Secrets come from secret references (Part 12), never from config files.

**Naming.** The assistant's display name is configuration and is the only name people see; vendor and model names appear only in
`config/ai.yaml`, the adapters, the usage reports and the evaluation reports.

**Replaying the real event** (functional designer's lessons from running, 2026-10-15; built, roadmap L7). Every
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

**Extras are weighed and tracked** (functional designer's answers, 2026-10-15; built, roadmap L7). Missing and forbidden ops stay exact. An op a case didn't expect is weighed
by its reach: a fact is free (a note is never counted); any other extra that stays inside the workspace (an action, a calendar entry, a question to the person, an extra
knowledge entry from a learning stage) costs 0.5; anything that reaches another person (a question to someone else, an
op of the outbound tier) fails the run. A run passes when nothing is missing or forbidden, no extra reaches another person
and the extras together cost no more than `ai.evaluation.extra_allowance` (default 1.0). An op kind a case lists in
`allow` weighs nothing. Each run carries its extras and their weight (`extra_weight`), shown in the report text and kept
in the report's JSON, so a case's `allow` list can't hide a trend. *Not built:* a view of the weight across saved reports.
Built: `tests/test_evaluate_harness.py::test_the_weighed_extras_must_stay_within_the_allowance`.

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
  confirms, and it takes effect that day. A learning pair proves it (roadmap L4). **A slice comes before real use** (the
  original designer, 2026-10-14; the rest stays in phase E): the role and its proposal; on a project the person only
  watches, facts only (no actions, no questions to other people), enforced by the applier from the role; and another
  team's item on any project is a fact unless the input says the person owes them something. *As built (the slice,
  2026-10-15):* `Project.roles` and `project.role` (system tier; a project with no role for the person is one they run);
  the lints `watched-project` and `other-team-item` (default `return`; returned once, then held and never applied even
  when the item reaches no one); "the person owes it" when the quote names the person or their team or holds a word in
  `language.owed_words`; the person's own note is exempt from both; the packet's project list says the person's part
  when it isn't "run". **Built:** `tests/test_scope_slice.py`. **Who owes what, revised** (functional designer's answers, 2026-10-15; the words are built, roadmap L7): "we", "us"
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

**How a fact is known** (functional designer's lessons from running, 2026-10-15; roadmap L7, *partly built*). Every fact
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
the old fact), and the records that repeated the old fact are brought in line by a follow-on run (6.7). A follow-up
question goes to whoever made the claim or owns the thing it is about; when neither is clear, it is a question to the
person about who to ask, never a guess from a passing mention. **Built:** the prompt rule and the golden cases
`follow-up-goes-to-who-made-the-claim` and `follow-up-with-no-clear-owner-asks-who`
(`tests/test_obvious_steps_f.py::test_the_prompt_says_a_follow_up_goes_to_the_claims_maker_or_owner_and_otherwise_asks_who`).

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
| held op declined | the PM declines a held system op or a routing guess |
| routed | the person said who a name or an owner is, answering "Who is X?" or "Pick an owner" (refs: the changeset, the question, the person chosen; the note is the name as written), or asked someone else about a question (`question.move`; refs as above; the note says from whom to whom; undoing it leaves the signal). Undoing the person's own release of a held op records no signal: it is their decision, not the assistant's work. **Built**: `tests/test_pipeline.py::test_saying_who_a_name_is_and_picking_an_owner_each_record_a_routed_signal`, `tests/test_pipeline.py::test_undoing_a_release_records_no_undone_signal_but_undoing_the_assistants_work_does` |
| put on hold / taken off hold | the person puts an action on hold or takes it off (refs: the action; the note is what it waits for). Undoing either records no signal. **Built**: `tests/test_on_hold_and_follow_ups.py::test_putting_an_action_on_hold_records_what_it_waits_for_and_a_signal_and_taking_it_off_keeps_the_due_date`, `tests/test_on_hold_and_follow_ups.py::test_a_hold_needs_words_and_an_open_action_and_undoing_it_records_no_signal` |
| just this time | the person says a proposed piece of learning is right for this case but is not a pattern (7.18). Refs: the entry; no note. The entry is discarded with that as its reason and nothing replaces it; a repeat of the same correction is shown with how many times this was said. Undoing records no signal. **Built**: `tests/test_proposals.py::test_just_this_time_records_its_signal_discards_and_the_repeat_is_marked` |
| not now | the person says "Not now" to the rules review line (6.22). Refs: the rules flagged then (none when only rules moved out of the always-sent part); no note, run or changeset. Not a correction: it starts the line's week and nothing learns from it. Undoing records no signal. **Built**: `tests/test_rule_review.py::test_not_now_route_records_a_signal_names_the_flagged_rules_and_changes_no_rule` |
| kept / discarded / retired | the person keeps or discards a proposed piece of what the assistant learned, or retires an active one (6.22). Refs: the entry; no note (a discard's reason stays on the entry). Undoing records no signal. **Built**: `tests/test_knowledge_records.py::test_keep_with_an_edited_text_makes_it_active_and_the_person_its_author`, `tests/test_knowledge_records.py::test_discard_keeps_the_proposal_with_its_reason_and_undo_brings_it_back`, `tests/test_knowledge_records.py::test_retire_ends_an_active_entry_and_undo_makes_it_active_again` |
| edited | the person changes a field the assistant set (a fact, an owner, a due date, an item's project, a question's wording before it is sent). The ledger shows who set each field, so this needs no AI. A silent correction, learned from in the batch. *As built:* an edit through `record.edit` or `record.set` of an action's text, due, owners or project, a question's title, text, recipient, stake or project, a fact's key, value, date or project, or a calendar entry's title, dates or project, whose previous value the assistant set, records one `edited` signal per record naming the change and run that set it; a record another signal of the same change already names is left alone. **Built**: `tests/test_hold_drop_fold.py::test_the_persons_edit_of_what_the_assistant_set_is_an_edited_correction_that_queues_learning` |
| answered the assistant | the person writes an answer to a question the assistant asked them. Refs: the question; its changeset and run. Learned from at once. A bare confirmation, or an answer about someone else, records none. **Built**: `tests/test_learn_input.py::test_an_answer_to_the_assistants_question_records_a_signal_and_queues_learning_at_once` |
| repeat correction | any of the above, on a run whose knowledge log (6.22) shows it was given an active lesson or rule whose target matched the corrected item: its task kind, record type, filter and project (with ancestors). Not a record: computed from the signals and the log. Corrections the person took back, corrections of something no run made, and Keep, Discard, Retire, Narrow and "Just this time" don't count; an entry with no target never counts as repeated. **Built**: `tests/test_quality.py::test_a_correction_repeats_only_when_the_run_was_given_knowledge_whose_target_matched_the_corrected_item` |

The repeat-correction rate, not the raw correction rate, says whether the assistant is learning; the quality panel shows it
next to the others, week by week. Refusals are counted per check too, and a check that refuses often brings its seed
lesson into the packet (Part 8, guard kinds). Beside the repeat-correction rate, the **knowledge-used rate**: the share of runs whose changeset says which
lessons, rules or facts it applied (`applied`, a list of knowledge ids). Each id is checked against the knowledge the run was
given, so it is a checked citation, not the model's say-so. If the first rate doesn't fall, the loop isn't closing; if the
second stays near zero, the knowledge isn't reaching the runs that need it. *As built,* `GET /api/quality` reports both
per task kind over `knowledge.quality_window_days` (28), the repeat-correction rate per week only for weeks with at least
`knowledge.min_corrections_per_week` (10) corrections, and the weekly missing-op list from each changeset's `missing`
(6.13); only the run that produced a changeset counts. The screen is phase B's. **Built:** `tests/test_quality.py`. Each signal also starts the learning step (6.22): rates measure the assistant, and proposals teach it.

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
**Checks on every output** (functional designer's answers, 2026-10-15; built, roadmap L7): a rule with a check runs it on every run's output in its scope, not only
on stage moves, so a checked rule counts as applied each time. *As built* (`engine/rule_use.py::record_applied`, `engine/stages.py::output_check_ran`): once a
run's changeset is applied, each active rule the run was given that names a code check has the check run on every record the changeset's applied ops wrote
(as the records are then) that the rule's scope covers (`task_kinds` names the run's kind of work or is empty, `records` and `filter` take in the record, the
same test a stage entry uses), and the rule is counted as applied on the run's knowledge log whether the check held or not (6.22: "passing or refusing"). A
rule whose scope covers nothing the output wrote stays present. A failing check changes nothing yet; it counts as applied, as the design above says (decisions, 2026-10-16). Running it
before the change applies, with one return to the assistant and then a hold for the person when the output reaches
someone, as lints do, is phase E. **Built:** `tests/test_rule_output_checks.py`.

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

**From the functional designer's answers** (functional designer's answers, 2026-10-15; *not yet built*, roadmap L7):
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

**Every correction proposes one piece of learning.** When a signal is recorded (sent back, undone, dropped, reworded, pulled
back, draft edited, held op declined, or the person's answer to a question the assistant asked them), a small `learn` task runs, unless the person's own answer already recorded what it teaches ("Not a project" and "It's part of" keep their glossary entry, which the correction names as `learned`). Its packet holds:
- the item, and which kind of work was corrected (an entry that names kinds of work must include it, or it goes back
  once with that reason; built: `test_a_lesson_naming_kinds_of_work_must_include_the_one_corrected_and_the_packet_says_which_it_was`);
- the assistant's original output;
- the correction: the note, what was undone, or the text as edited or sent;
- the knowledge entries the original run was given;
- the active lessons and rules.

It returns **at most one** proposal op, or "nothing to generalize":
- a new lesson, rule, fact, glossary entry, routing entry or style note;
- or `lesson.update`, when an existing lesson should have caught it but didn't. A repeat means the guard was wrong, and fixing
  it beats adding a second one.

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
