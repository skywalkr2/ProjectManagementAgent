# Product decisions

Dated entries: what was decided, who decided, why. Newest first. Decisions about one deployment go in that workspace's own
`docs/decisions.md`, not here.

## 2026-10-17: Repeating events are expanded by `engine/recurrence.py`, on `python-dateutil`

- **Decided (main session):** the core expands iCalendar repeat rules with a pure function in `engine/recurrence.py`
  (drafted with an outside assistant at the owner's request, reviewed against RFC 5545 and revised once), built on
  `python-dateutil`'s rule engine, now a dependency. It covers daily to yearly rules with interval, count, until,
  weekday ordinals, month days, set positions, skipped and extra dates, moved and cancelled occurrences, all-day and
  floating events, and daylight saving time (a missing hour moves forward; an ambiguous one takes the first).
- **Also (2026-10-17): Windows time zone names.** `engine/windows_zones.py` turns a calendar's time zone name (an Outlook
  "Eastern Standard Time", a quoted or prefixed name, or an IANA name) into its IANA name, from CLDR 48.2's default
  territory mapping in `engine/defaults/windows_zones.yaml` (Unicode-3.0 licensed; checked against the source file's
  published fingerprint and all 139 entries when added). `tzdata` becomes a dependency so time zones work on Windows,
  which ships no IANA database.
- **Also (2026-10-17): a reply's own words.** `engine/reply_split.py` separates an email body's new text from its quoted
  history (">" quoting, "On ... wrote:", Outlook and other mail programs' header blocks, forwarding markers) and its
  signature, keeping anything uncertain as new text; drafted with an outside assistant and widened here to header blocks
  that use Date instead of Sent in any order.
- **Also (2026-10-17): writing calendar events.** `engine/ics_write.py` writes one event as an iCalendar file (escaping,
  75-octet folding that never splits a character, a time zone definition covering the event's years, reminders as
  alarms, organizer and attendees, method and sequence), for reminders placed in the person's own calendar and
  calendar acts after a yes (phase S); drafted with an outside assistant, checked by parsing its output back with the
  `icalendar` package.
- **Also (2026-10-17): due phrases by rules.** `engine/due_phrases.py` reads a due phrase against the message's received
  time and zone, with the workweek, locale and end-of-day time as inputs; its conventions (a bare weekday is the next
  one, "next Friday" is the following week's but marked uncertain, close of business is the configured time) are
  product behavior shown to the person as a note beside the proposed date. Drafted with an outside assistant in two
  rounds; short forms (EOD, COB, Fri), a weekday with a date, and far-ahead year-less dates marked uncertain added here.
- **Also (2026-10-17): answering invitations.** `engine/itip.py` reads one invitation, update, cancellation or reply
  (RFC 5546), prepares the person's answer (accept, decline, maybe, with an optional note) without sending it, and picks
  the newer of two versions by sequence, then time stamp. It doesn't check who sent the message: before a cancellation
  or update changes a calendar entry, the caller checks that the sender is the organizer, and an answer goes out only
  through the publisher after the person's yes (phase S1b). Windows zone names resolve without an embedded definition;
  an unknown zone is refused, never read as floating. Drafted with an outside assistant; `icalendar` is now a runtime
  dependency.
- **Also (2026-10-17): promise threads and the launcher's core.** 25 fictional threads with how each promise ends
  (done, partial, a new date, cancelled, a non-answer, a condition met) join the 120 single examples as phase S
  evaluation material; drafted with an outside assistant, one inline reply corrected to quote what was really said.
  Checking them found that the reply splitter missed a "<name> wrote:" line, now history when quoted lines follow it.
  The tray launcher's core (`engine/launcher.py`) is in the repository for phase I and not yet started by anything; its
  wording, title and the address it opens come from the caller, and `pystray` and Pillow are imported only when it runs.
- **Also (2026-10-17): free time by rules.** `engine/free_slots.py` computes free time from every calendar's entries,
  the person's working hours and days, a buffer and a minimum length, with each day's total free minutes, for the
  capacity check and for proposing a new time. Drafted with an outside assistant; changed here so an all-day entry
  follows its show-as like a timed one (a day out of office is not free time; holidays marked free still don't block).
  The caller maps each source's own show-as words to busy, tentative, free and out of office.
- **Also (2026-10-17): conversations by rules.** `engine/mail_threads.py` strips reply and forward prefixes and outside
  tags from a subject (in several languages, keeping ticket numbers) and picks a message's conversation: a known
  message in its reply headers, then the first reference, then the same subject with a shared correspondent within
  a number of days, and a new conversation when more than one would match. The caller leaves the person's own
  addresses out of the participants, or every message they're on would overlap. Drafted with an outside assistant;
  a known parent now wins when the references were trimmed.
- **Also (2026-10-17): automatic mail by its headers.** `engine/automatic_mail.py` tells an automatic reply, a
  delivery report, generated mail (a receipt, a notification), list and bulk mail from a person's message, from the
  headers and an anchored subject phrase only, never the body, with the deciding header as evidence. None of them
  counts as an answer to a promise. Drafted with an outside assistant; here the mail programs' own header names and
  the subject phrases moved to `engine/defaults/automatic_mail.yaml`, and generated mail became its own kind instead
  of an automatic reply.
- **Also (2026-10-17): bookings from a confirmation's structured data.** `engine/bookings.py` reads the reservation
  data that confirmation mails embed (flights, stays, events, restaurants, rental cars, trains) into bookings, keeping
  partial ones with each missing or unclear field reported, never inferring a time zone or reading the prose. Its
  text comes from outside, so a booking stays untrusted until the person keeps the calendar entry. Drafted with an
  outside assistant; here deeply nested markup, which crashed it, is reported instead, and structured data is built
  only for reservation types, which keeps hostile markup from slowing it down.
- **Also (2026-10-17): bill dates by rules.** `engine/bill_dates.py` lists a bill's due dates in a window from a rule
  (a day of the month, the last day, the nth weekday, every N weeks, yearly), moved to the previous or next business
  day around weekends and the holidays the person gives, with reminder dates before each; no amounts, accounts or
  payments. Separate from the repeat engine because calendar repeat rules skip a 31st in short months instead of
  moving it to the last day and know nothing of business days. Drafted with an outside assistant; a bill moved
  forward from just before the window, onto its first day, was dropped and is now kept (found by checking that two
  halves of a window give the same dates as the whole).
- **Also (2026-10-17): where the installed app keeps its data, and not roaming on Windows.** `engine/app_dirs.py`
  computes the data, logs, add-ons and cache folders for macOS (Application Support, Logs, Caches), Windows and Linux
  (the XDG folders), never inside the app's own install folder. Changed from the phase I plan: on Windows the data
  goes to local AppData, not roaming, because a company may redirect the roaming folder to a network share or copy
  it at sign-out, and SQLite's own documentation warns that a database on a network share can be corrupted; two
  computers already share a workspace through its synced folder. **Impact:** phase I's data-folder item (roadmap)
  now says local AppData. Drafted with an outside assistant.
- **Also (2026-10-17): learning pairs for promises, as material first.** Twenty mistakes and corrections about finding
  promises (sarcasm, quoted history, "we", conditions, proposals, promises made on someone's behalf, forwards,
  signatures, hopes, suggestions, vague dates, two promises in one line, offers, negation, completion, partial
  delivery, non-answers, corrected dates, cancellations, "it" from the thread) are kept as material until promise
  records and ops exist, then converted to harness pairs. Drafted with an outside assistant; an unowned "we" promise
  is held for Pick an owner, as every action names a person.
- **Also (2026-10-17): the morning brief's shape.** Three sections in a fixed order (changed overnight, at risk today,
  needs your yes); changed and at-risk lines state one fact plainly, at-risk lines say when it bites, and only the yes
  lines start with what the person does, naming the thing rather than "Approve a draft". Empty sections are left out
  and a quiet day is one line, following the rule that no line counts zero things. Ten samples drafted with an outside
  assistant were rewritten to this: the brief asked for a verb at the start of every line, which put filler ("Note
  that…", "Enjoy the quiet") in front of news. **Impact:** design 6.32 gains the brief's shape.
- **Also (2026-10-17): a mail server's sign-in refusal, read by rules.** `engine/connectors/imap_refusal.py` reads the
  standard IMAP response codes first, then known phrases from `engine/defaults/imap_refusals.yaml` (service names in
  data only), shortens any web address to its domain, and gives a kind with an advice key. The odd text in the owner's
  screenshot is Python's way of printing the server's bytes (`str(err)` gives `b'…'`); the mailbox reader is to pass
  the bytes themselves when it is wired in (open promise P19), and the classifier also reads that printed form back. Drafted with an outside assistant; here a plain
  authentication failure became its own kind (check the user name and password, or make an app password) instead of
  "unknown", and the phrases moved to a YAML data file.
- **Also (2026-10-17): the screen wording review and its triage.** An outside review of all 2,308 screen wording
  entries is kept with the main session's triage (`docs/project/wording-review-2026-10.md`) and applied in phase B
  wave 3. Kept: shorter text, one name per thing ("to-do", "calendar event", "Add-ons"), spelled-out abbreviations,
  plain words for internal terms, and a check of 110 counts so that zero never renders. Rejected: "Approve" for
  starting paid AI work (approval stays the yes on exact outward content), new names for the data levels, "work" for
  workspace, "person responsible" for owner, and "Download" for working copies.
- **Also (2026-10-17): when a reminder fires, by rules.** `engine/reminders.py` plans a reminder's delivery from its
  occurrences and what was already delivered: an on-time one waits for working hours and the end of quiet hours (which
  may cross midnight), a missed one fires at once marked late, each or as one summary, and planning never marks
  anything delivered. Snooze choices: in an hour (60 real minutes across a clock change), later today, this evening,
  tomorrow morning, next week, or a picked time. Drafted with an outside assistant; here a zone whose clocks change at
  midnight no longer makes every plan "unknown", and "tomorrow morning" on a Friday is Saturday morning rather than
  refused, since the steward covers the person's own life too.
- **Also (2026-10-17): the attention budget, by rules.** `engine/attention.py` decides for each suggestion whether it is
  shown now, saved for the digest (quiet hours, or past the day's cap, the most important going first) or held back
  (below the importance threshold, or dismissed and unchanged), each with a reason. Below the threshold is held back,
  not put in the digest: the threshold is what's worth the person's attention at all. A dismissal lasts until the
  suggestion's change key differs. Drafted with an outside assistant; here dismissals are kept per kind and subject,
  since one per kind let dismissing a second suggestion bring back the first unchanged.
- **Also (2026-10-17): the capacity check, by rules.** `engine/capacity.py` adds up the day's to-do estimates against
  the free minutes and, when they don't fit, proposes whole to-dos to move, each with a plain reason; it never moves
  a fixed to-do and never changes anything itself. Order: to-dos due today or overdue last, then lowest priority, not
  promised, no due date and latest due first. Drafted with an outside assistant; here due-today and overdue to-dos
  went from first-by-priority to last, and a small move a later, larger one made unnecessary is dropped.
- **Also (2026-10-17): calendar clashes, by rules.** `engine/clashes.py` finds every pair of events that overlap
  (busy and out of office blocking, tentative ones listed apart, free never) and, given a travel allowance, pairs at
  two different stated places with too short a gap. Drafted with an outside assistant; here a web link as the
  location is an online meeting needing no travel, a pair with no location is listed for review without making the
  whole report unknown (most events have none), the comparison stops once later events start past the allowance,
  and show-as spellings are read as the free-time finder reads them.
- **Also (2026-10-18): engine helpers return data, never on-screen sentences.** Following the rule that no on-screen
  text is written in code, a helper whose result reaches a screen returns kinds, codes and values, and the screen words
  them from the wording sheet. `engine/invitation_changes.py` (what changed between two versions of an invitation,
  drafted with an outside assistant as English sentences) returns `Change(kind, values)`, with an all-day end's last
  day and a repeated-hour flag included so the screen needs no calendar rules; the capacity check's moves now carry
  `promised`, `due` and `due_state` and its reason is a code. The free-text reasons left in the reminder, clash,
  booking and sign-in modules are diagnostics for logs and tests; a screen that shows them reads their codes
  (`reason_code`, `advice_key`, `kind`), or a code is added first.
- **Also (2026-10-18): replies owed, by rules first.** `engine/replies_owed.py` says owed, not owed or unknown for a
  message, with the exact questions as evidence: only for a person's mail with you in To, a direct question in the new
  text, past the wait, and no later message from you. Unknown (several recipients and no name, FYI with a question, a
  later reply in prose) is where the AI step reads the thread. Drafted with an outside assistant; each answer gained a
  `code` for the screen.
- **Also (2026-10-18): dates in documents, by rules.** `engine/document_dates.py` finds renewal, expiry, cancel-by,
  valid-until, warranty-end, payment-due, check-in and appointment dates next to their label, with the exact words as
  evidence; it never infers a missing year or the numeric order beyond the locale, leaves relative wording ("30 days
  after purchase") uncalculated with its anchor named, and marks a date uncertain under correction or conditional
  wording. Drafted with an outside assistant and taken as written.
- **Also (2026-10-18): repeat phrases, and the 31st in short months.** `engine/repeat_phrases.py` reads "every other
  Tuesday", "the first Monday of each month", "weekdays", "every 3 months on the 15th" and "yearly on March 3" into a
  repeat rule, and returns a supported rule as a shape (kind and values) for the screen. A day past the 28th means that
  day or the month's last day when shorter, written as the standard `BYMONTHDAY=28,...,N;BYSETPOS=-1`, because the
  plain rule skips months without that day and a repeating to-do would vanish; February 29 falls on the 28th the same
  way, matching bill dates. Drafted with an outside assistant, whose describe step returned English sentences.
- **Also (2026-10-18): facts from signatures, by rules.** `engine/signature_facts.py` reads phone numbers (labeled or
  international only), labeled job titles and organizations, a few standalone role lines, and websites as their
  domain, each with its exact line as evidence; it stops at a legal notice and never takes a title from a name. A
  signature is outside text, so these facts stay untrusted until the person keeps them (people memory, phase S3).
  Drafted with an outside assistant and taken as written.
- **Also (2026-10-18): the person's writing voice, counted.** `engine/voice_profile.py` turns the new text of the
  person's sent mail into a small profile for drafting packets (usual greetings and sign-offs with their shares,
  median length, how often they use contractions, exclamations and questions, and a formality score with the markers
  behind it), keeping no message text or names. It measures; it never instructs: a packet quotes it as observed
  style. Drafted with an outside assistant and taken as written.
- **Also (2026-10-18): a reminder mailed to oneself.** `engine/reminder_mail.py` builds (never sends) the reminder
  mail phase S sends to the person's own address: plain text, an optional calendar file, a Message-ID from a token
  the caller keeps, and `Auto-Submitted: auto-generated`, so the mailbox reader classifies it as generated mail and
  never acts on its own reminder (tested against `engine/automatic_mail.py`). It goes out only through the publisher
  after the person's yes. Drafted with an outside assistant and taken as written.
- **Also (2026-10-18): checking for a new version.** `engine/release_check.py` picks the newest release in the release
  feed newer than the installed version (version order from `packaging`, prereleases only when asked), refusing an
  entry without a SHA-256, with a bad date, or with a download address that isn't HTTPS; conflicting entries for the
  newest version raise instead of picking one. For phase I's "A new version is ready". Drafted with an outside
  assistant; here plain HTTP downloads were refused, since the file and its checksum could both be swapped.
- **Impact:** open promise P17's repeat expansion has its engine (`tests/test_recurrence.py`); the calendar reader uses
  it in phase B wave 5, where a rule part it doesn't support shows the first occurrence with a note instead of
  dropping the event.

## 2026-10-17: Mail and calendar management after the person's yes; reminders through the person's own calendar; the first audience

- **Decided (owner):** (1) "if we can have the app actually able to do mail/calendar management (not just read only)
  lets do it": in 1.0 the assistant replies, forwards, sends, archives, moves, labels and marks read, and creates,
  moves, cancels, accepts and declines calendar events, each only after the person's yes on that exact act, carried out
  by the publisher (brought forward from phase C4 to phase S1b) with a visible status and the ledger. (2) "whatever we
  can do to make it full featured ... but not phone pushes unless it was an installed ios or apk": reminders reach a
  sleeping person through an event with an alarm in their own calendar or a mail to themselves; missed reminders show on
  waking; no third-party push service; a companion iOS and Android app is planned after 1.0. (3) "yes agreed": the
  first audience is independent professionals juggling clients and personal life; testers are the owner's colleagues
  and people answering a LinkedIn post.
- **Why:** copying every reply is the biggest friction left; exact-content approval, recipient checks and a visible
  status keep the trust that read-only gave.
- **Impact:** phase S grows by a wave (S1b, the publisher, mail and calendar acts); the Google and Microsoft add-ons ask
  for send and modify access, which reverses their read-only rule (their builder is told; the change is theirs); a plain
  mailbox sends through its outgoing server; a subscribed calendar link stays read-only. Design 6.3, 6.12 and 6.32 say
  so. CLAUDE.md's "not built yet" line for the publisher now points to phase S1b.

## 2026-10-17: The installers are built with PyInstaller (folder mode) and Inno Setup

- **Decided (main session, from the owner's research report on packaging, checked against the code):** phase I builds
  the app with PyInstaller in folder mode; macOS ships a signed, notarized `.app` in a `.dmg`, built per architecture;
  Windows ships a per-person Inno Setup installer. Briefcase and Nuitka were weighed: Briefcase brings its own project
  layout, and Nuitka's compiling doesn't help an app that mostly waits on the network. Updates start as a "new version
  is ready" link to the signed download.
- **Signing:** unsigned to start (owner: "i will just use unsigned to start"); testers open the app once through the
  system's "Open Anyway" or "Run anyway", shown in the release notes. Signing (about $219 a year for Apple plus
  Azure's basic signing) is added later without other changes.
- **Open, decided at the start of phase I with a trial:** how add-ons with compiled parts load once the app is signed
  (the library-validation entitlement, or a separate worker); unsigned builds load them as they are.
- **Impact:** add-ons move from the app's own package folder to one in the person's app-data place; the rest of the
  app is unchanged.

## 2026-10-17: The product is called Thimbleby; the assistant inside it is Reginald

- **Decided (owner: "okay i checked Thimbleby and we can go with that"):** the product's name is **Thimbleby**. The
  assistant's default name stays **Reginald**, which the person can rename. This replaces the earlier entry that made
  Reginald the product name.
- **Why:** the first clearance check found "Reginald" already used by two AI assistants in the same field and a Windows
  productivity app, with the .app domain held; "Morrowby" and "Daywarden" also collided (several AI products named Morrow,
  one with approval before sending). A made-up name is the easiest to own, and a character's name inside the app carries
  far less risk than a product name.
- **Impact:** phase I puts Thimbleby on screen, in the installers and in the docs from one place, and draws the icons for
  it; the default assistant name becomes Reginald. Internal names change, if at all, in phase C's plugin API release.
  Domains and an official trademark search are confirmed before the installers ship.

## 2026-10-17: The core becomes a daily steward (phase S), before the installers

- **Decided (owner: "this core needs to be full featured"; then "i agree with everything you wrote so definetely want to
  work on these before we do the full ci/cd setup with the installers"):** the twelve additions of
  `docs/project/steward-proposal.md` become phase S, after phase B and before phase I: reminders, repeating to-dos, the
  morning brief and evening wrap-up, promises both ways, replies owed, meeting prep, people memory, dates in documents,
  areas of life, capture from anywhere, gentle suggestions, and talking to Reginald; the core is audited for PM-only
  wording. Bills are reminders only, with no bank connection (owner).
- **Defaults until the owner says otherwise:** mail and calendar stay read-only for 1.0; no phone push in 1.0; areas live
  inside one workspace.
- **Impact:** about five sessions before phase I; design 6.32 describes the steward; phase B's Monday briefing moves to S1.

## 2026-10-17: The product is called Reginald, and so is the assistant until the person renames it

- **Decided (owner: "We can call it Reginald and just let the user change the name (already coded) but we can just default
  it so its called reginald like the name of the app"):** the product's name is Reginald, marketed as a daily assistant for
  anyone juggling work rather than a tool for project managers. The assistant's default name (`workspace.assistant_name`,
  today "Assistant") becomes Reginald, and the person can still rename it.
- **Why:** after Jeeves (Reginald Jeeves), who sees what's needed, handles it quietly and leaves the decision to his employer:
  the app notices, drafts, and the person approves.
- **Impact:** done in phase I: the name on screen, in the installers and in the docs comes from one place (the wording
  sheet's `app.name` and the build's product facts); the default assistant name changes with a demo value in both
  workspaces left as their own; the icons are drawn for it. Internal names (the package, the `cockpit` command, the add-on
  entry point group, the `COCKPIT__` prefix) change, if at all, in phase C's plugin API release. Availability (app stores,
  domains, trademarks) is checked before the installers ship.

## 2026-10-16: Installers for Windows and macOS, built by CI, are a phase of their own after phase B

- **Decided (owner: "I really want to be able to create windows and mac distributions so that I can send them to people for
  testing ... installed in the appropriate places, and default the storage to the place where windows/mac typically store
  application data"):** a new phase I after phase B and before phase C's plugin API release: a tag builds a macOS disk image
  and a Windows installer with their own Python and the built screens; the app installs where each system expects, keeps its
  data in the system's app-data place (a setting, never the app's own folder, kept on uninstall), starts the local server and
  opens the browser, and installs add-ons beside the app. Signing is the owner's open decision (it costs money); until then
  the builds are unsigned and say how to open them.
- **Impact:** adds about two sessions before phase C; phase B's launcher item moves into it; design Part 11 (local mode)
  gains the installed app's folders when the phase starts.

## 2026-10-16: The language setting lists only languages the app can read notes in, and says it is how the assistant writes

- **Decided (owner: "the language lets you select literally all languages which indicates to a user that the screens would
  shift to those languages"; chose the English varieties):** the setting is "How the assistant spells and writes", with a
  note that the screens stay in English, and its list holds only varieties of languages the app reads notes in (its word
  lists in the language settings: confirmations, reported speech, date phrases), so today the varieties of English. Another
  language joins the list when its word lists exist; a setting for the screens' language appears only when a translated
  wording sheet exists.
- **Why:** the setting only steers the assistant's drafts (spelling, punctuation, dates); the screens have one wording sheet
  and notes are read with English word lists, so a list of every language promised two things the app doesn't do.
- **Impact:** `engine/defaults/languages.yaml` lists English varieties; a value set earlier outside the list still shows
  (the list adds it). Design 4.22 and 7.0 say so.

## 2026-10-16: A password typed on the screen is kept in the private keys folder; a catalog's address and a read token are added on the Add-ons screen

- **Decided (main session, from the owner's words: "the language setting should be a dropdown", "in imap setup we need to be
  able to take a password and not require the user to have set it somewhere else", "they still require manual command line
  installs instead of through the screen. the screen lists zero available plugins"; phase B; open promises P15 and P16):**
  (1) The language setting and a project's own language are lists of language tags (the core's shipped
  `engine/defaults/languages.yaml`), shown by name in the browser's language and stored as the tag; a value already set that
  isn't on a named list is added to it, so no list shows a wrong value. (2) A setting whose value is a secret reference is
  marked `secret` in its description. A source's add and change routes take pasted values apart from the settings
  (`secrets`, by dotted field name); on a local app each is kept as a file in `<workspace>/.cockpit/keys/` (the folder 0700,
  the file 0600) named `source-<source id>-<field>` and the source's settings hold only its `file:` reference; a hosted app
  refuses a pasted value (the existing "keys can't be pasted" answer). A value is never written to `watch.yaml`, the ledger,
  a log or an answer; the source list says only where each secret is read from. "Where it is kept instead" (an environment
  variable or a file of the person's own) stays the second choice. (3) With no catalog listed, Add-ons offers an address
  field, saved into `workspace.plugins.catalog.feeds` (https only) and read at once; the catalog list can add another and take
  away one the person added. All of `workspace.plugins.catalog.*` is read when the screen uses it, so it is now a live key.
  An install the release host refuses for want of a token (401, 403, 404, or a token that can't be read) answers with the
  header `X-Cockpit-Needs: read-token`, and the row asks for the token in place; a typed token is kept like any other
  typed secret (`release-token-<host>`) and its reference written to `release_tokens` for the host of that entry's
  release, which the server takes from the entry, never from the request. The plugin guide's "Publishing a pack" now says to
  attach the built wheel to the tagged release and give its address and SHA-256 in `release`, with the release asset's API
  address for a private repository.
- **Why:** a person setting up a mailbox or a private add-on had to leave the screen to set an environment variable or write
  a file, and a build with no shipped catalog listed nothing. Pasted AI keys were already kept this way; the same rule now
  covers every secret reference, with the same local-only limit. The token goes only to its release host, as before.
- **Impact:** design 3.11, 3.14, 4.0, 4.22, 4.24, 6.29 and 7.0 (edited), `docs/design/CHANGES.md`, the plugin guide
  (regenerated). API: `secret` and `choices` on setting items, `secrets` on the source add and change routes, `secrets` on
  the source list, `POST /api/packs/catalogs`, `/api/packs/catalogs/remove` and `/api/packs/{id}/token`, `address`,
  `removable` and `release_host` on the Add-ons view. No new config key; no change to scope or to the plugin API. Not
  built: typing an add-on's own secrets (`workspace.plugins.secrets`) and the backup key on the screen (still a reference
  box in Settings).

## 2026-10-16: AI accounts as one place, the comparison grid, "Not now" in the menu and the copy tables are built

- **Decided (main session, from the UI designer's answers 25, 26, 31 and 32; phase B):** an AI account carries an optional
  `label`, the name the person gave it, kept apart from its id in the settings and left out of the connection check's
  fingerprint, so renaming never un-checks an account. Removing the account that does the work hands that work to the
  backup that stands in for all of it, said in the toast with Undo; with none it leaves the work with no account and Today
  says so. The one it replaces stays a backup when it passes its own check (the existing guard that only checked accounts
  stand in a fallback chain is unchanged: every route that adds a backup checks first). A backup that gains a harder model
  can move its harder-work backup there, checked first. "Not now" on the rules review is undone by marking its signal taken
  back, so the line is due again at once. A follow-up's table shows an action's project pages as its links.
- **Why:** the designer's answers say each of these, and the owner asked for one place for accounts with Undo on every
  change; a label keeps ids out of the screens without changing what the connection check covers.
- **Impact:** design 7.5, 7.6 and 7.16 (edited), `docs/design/CHANGES.md`. One new config key (`ai.providers.<name>.label`,
  with its description; shown in both fictional workspaces). New reads on `GET /api/ai/accounts` (label, state, check cost),
  `GET /api/ai/check-size`, and `take_over`, `label` and `stop_backup` on the account routes; no change to scope or to the
  plugin API.

## 2026-10-16: Today's queue, inspector and rail are built; three readings of the design are fixed

- **Decided (main session, for review; phase B wave 1):** (1) "New items arriving while the PM works wait behind a 'N new
  · Show' pill" is read as: while the cursor is inside the queue. When it is not, a line that arrives joins the list at
  once, since nothing can move under a cursor that is elsewhere. (2) The plugin Today lines name no group (the line
  registration has none), so they follow the queue's own lines under "More for today" until the registration takes one.
  (3) The toasts' column is the navigation column, so with the navigation folded to icons a toast keeps a readable
  width (`--toast-w-rail`) at the bottom left instead of being as narrow as the icons.
- **Why:** each is the least surprising reading that does not move a row under the person's cursor or hide a line the
  engine ranked.
- **Impact:** design 7.6 and 7.7 (the sentences are edited), `docs/design/CHANGES.md`. One new design token. No new
  setting, no API change, no change to scope.

## 2026-10-16: A drafted reply is its own text on the action, changed only through `action.reply`

- **Decided (main session, from the functional designer's answer, for review):** the reply to a question someone asks the
  person is `reply` on the action, with `reply_reviewed` false until the person approves it or writes their own. The
  action's text says what to do. The person approves or rewords it with a new person-only op, `action.reply` (Undo; the
  route is `POST /api/actions/{id}/reply`); rewording a draft the assistant wrote records `draft_edited`, and approving
  as it is records nothing. The assistant's `action.add` takes `reply`, only when a recorded fact holds the answer; the
  golden case with no such fact expects no reply.
- **Why:** a reply folded into the action's text could not be copied, edited or marked reviewed on its own, and a draft
  must stay marked unreviewed until the person approves it.
- **Impact:** design 5.1 (two optional fields on `action`), 6.7 (the op), 6.8; the plugin guide is regenerated (a core
  record and an op changed). No new setting. No change to scope.

## 2026-10-16: Measure counts only the cases an account may see, and asks first above the confirm amount

- **Decided (main session, for review):** a case, pair or scenario may say its `data_level` (default `internal`, the level
  a handed-in note has; none of the shipped ones says another). Measuring an account prices and runs only those no more
  private than the account's most private allowed level, and the report keeps naming every case so the set measured
  does not change. `POST /api/ai/skills/{account}/measure` is refused above `ai.budgets.confirm_above_usd` unless
  `confirmed: true` is sent (and with no estimate when `confirm_unpriced` is on), and one asked for is kept in the
  private folder so a restart finishes it.
- **Why:** a case run on an account that may not see its material would fail on the router's refusal and count against
  the model; spending is the person's choice.
- **Impact:** design 6.16 (Measuring). A new optional key on cases and pairs, no new setting. The Measure screen and the
  proof with each adapter kind's own fake service stay phase B.

## 2026-10-16: A calendar sync reaches the follow-on run through reading; asking for a team waits for the scope resolver

- **Found:** a connected calendar's sync writes its changes as inputs (snapshots), not as calendar entries, and the
  scope check that would need a person's team is a pure check with no place to ask.
- **Decided (main session):** no separate sync trigger: reading the synced change moves the app's entry with
  `event.set`, and that save starts the follow-on run like any move. "Which team is <name> on?" moves to phase E with
  the scope resolver, which is where a team is needed and where asking has a home.
- **Impact:** the L7 item is closed; a phase E item; the "Who owes what" item keeps its words part as built.

## 2026-10-16: A decided action's date is never changed automatically; a moved plan is checked with the person

- **Decided (owner):** "No it should not automatically move - the model should ask the appropriate party if it should
  change dates. typically we dont change action items after they are decided - and especially not utomatically." And:
  "If the model sees the discussion is > than a action item with due date this is a good reason to ask the user to
  validate the plan."
- **What it means:** a follow-on run never changes an action's due date or wording. For each tied action whose date the
  move affects (linked, citing the old day, or due between the old and new day), it asks the right person whether the
  date should change: the action's owner, or whoever decides, the person when nobody is named (design 6.8). When the
  moved meeting or replaced fact carried more than a dated action (a topic said to be covered there, a plan, a set of
  items), it asks the person to confirm the plan still holds. Agenda items with no due date of their own still sit on
  the meeting's next instance (placement, not a date change). Drafted corrections for what already reached someone stay.
- **Kind:** a standing rule of the core's (design 6.7, the follow-on run), not a setting.
- **Impact:** the follow-on run's `record.set` on actions is removed; questions replace it; the "two candidate kinds"
  open point is closed by this rule; L7.

## 2026-10-16: The follow-on run's open points

- **Decided (main session, from design 6.7 "the assistant's own move from an input starts it too"):** an `event.set`
  op lets the assistant move an entry's start or end from an input (data tier, evidence required, Undo), which starts
  the follow-on run like the person's edit; a move a connected calendar's sync writes starts one too, since a real
  meeting moved. A drafted correction keeps the rule that a question to someone carries a link they can open; with
  none, the run leaves a note for the person instead.
- **Settled by the owner (next entry above):** the two candidate kinds the design named are not moved; the run asks
  about them instead.
- **Impact:** two L7 items (below the follow-on item); design 6.7 unchanged in substance.

## 2026-10-16: The follow-on run (phase L7)

- **Decided (main session, for review):** one request per save, queued in the save's own transaction like learning, for a
  moved entry day, an action's moved due day or a replaced fact; the tied records are found by code and the run may only
  change the day or words of an action nobody was told about, draft a correction for someone already reached, or note.
- **Impact:** four new config keys, `dispatch.knowledge.follow_on`,
  `follow_on_max_tied`, `follow_on_match` and `language.date_patterns`, one task kind `follow-on` and one refusal check,
  all inside L7's follow-on item (design 6.7, 4.25; CHANGES section 77); no scope moves. Open for the owner: an op that
  moves a calendar entry (so the assistant's own move starts the run), and whether a correction about an action's
  notice is exempt from the link a question to someone else needs.


## 2026-10-16: A series is a record of its own, and its instances are the entries that name it (phase L7)

- **Decided (main session, for review):** a series holds a title, a project and `repeats`, the person's words for how
  often; nothing works out dates from it. Each instance is a calendar entry that names the series, so the series needs no
  recurrence rule. An item on a series sits on the first instance that has not ended before today; the worker moves an
  open action or question to the next one once a day, and a fact never moves. With no later instance the item stays put.
- **Why:** the design says an entry can be one instance of a series and an item rolls to the next one; it names no
  recurrence fields. Generating instances is a calendar service's or a pack's business, and a rule here would be a second
  source of dates beside the entries.
- **Impact:** design 5.1 (`series`, and `event`/`series` on action, question, fact, `event.series`), 6.7 and CHANGES
  section 77. New ops `series.add` and `series.link` (data tier, with Undo); `record.set` takes `event` and `series` on an
  action, a question and a fact. No new setting. The agenda that uses it stays the project management pack's.

## 2026-10-16: A rule's check that fails on an output changes nothing yet

- **Decided (main session):** a rule's check now runs on every output its scope covers and counts as applied whether it
  holds or fails (design 6.22). A failure doesn't hold or refuse the output yet.
- **Why:** turning failures into a return and a hold needs the check to run before the change applies, the same path
  lints take; that belongs with the rest of version 1, not with L7's counting.
- **Impact:** a phase E item; design 6.22 and the L7 item say so.

## 2026-10-16: What "three ops the assistant may propose" means in the code

- **Found:** bringing back a set-aside item (`mail.restore`) and merging or retiring a list value (`list.merge`,
  `list.retire`) were already proposals the assistant may make. Removing a project record is `record.delete`, the
  person's own act by design.
- **Decided (main session):** a project record stays the person's to remove; "Not a project" already handles one the
  assistant only proposed. Marking a question as already asked applies when the person's own note says they asked;
  outside content can't, so the `person-only` invariant is narrowed for the person's own words only, never loosened for
  anything else.
- **Impact:** design 6.8 unchanged in substance; the roadmap item is closed with its test.

## 2026-10-16: The capability matrix stays out of backups

- **Decided (main session):** the matrix stays in the workspace's private folder beside the connection checks, and like
  them is not part of a backup; a restored workspace starts it empty until Measure or an evaluation fills it.
- **Why:** it measures the accounts on one computer, the private folder is never backed up (Part 7), and re-measuring
  costs little next to carrying one private file through backups.
- **Impact:** design 6.16 says so; the step-1 leftovers are only Measure and the per-kind fake services.

## 2026-10-15: A capability matrix: which model can do which work, measured

- **Decided (owner):** "when we defined limits we need to start building capability matrixes so we know based on a
  certain model type we will need a deeper model for certain activities."
- **Where it goes:** a concept in the core (design 6.16 "What a model can do, measured"), with data (the skills each
  case and pair proves, a shipped list packs extend), a setting (`ai.skills.min_score`) and per-workspace measurements.
  Not vendor-specific: it is measured per model and program version, never assumed from a name.
- **Why:** the backup model's pairs showed it reads and stores knowledge but often doesn't use it (a term, routing),
  while the stronger account did; today that lives only in a report read by hand.
- **Widened (owner):** "this capability needs to be very full featured. not just in claude but all the others": every
  kind of account the product supports, measured the same way; skills packs extend; staleness; cost per passing run;
  evidence from real corrections; routing across accounts to the cheapest model that measures well enough; a Today
  line to decide, never a silent switch (design 6.16).
- **Impact:** step 1 (measured and shown, every adapter kind) joins L7, about 1.5 sessions, so L7 is about 5.5;
  step 2 (routing, task kinds' skills in the plugin API, real-use evidence, the Today line) opens phase C as C0, about
  1.5 sessions, because the writing pack is where model choice per kind of work matters most.

## 2026-10-15: The failing pairs again, after the fix wave

- **Found:** imprint 19 of 45 (from 5), workplace 7 of 24 (from 1); seven pairs now pass every run. The report's `kept`
  line showed lessons from a correction of reading notes limited to `ask` or `sort-mail` work: the learning packet never
  said which kind of work was corrected, so the model guessed from the words, and the lesson never reached the next
  input.
- **Decided (main session):** the learning packet says which kind of work was corrected, and a learning answer whose
  entry names kinds of work without that one goes back once with the reason; the prompt says to leave `task_kinds`
  empty unless the lesson holds for some kinds of work and not others. Three pairs were still stricter than the design
  and are corrected with comments.
- **The rest is the backup model's limit:** it was given the term, the routing entry or the lesson and didn't use it.
  Recorded in `docs/project/evals/README.md`; it is the evidence for keeping the stronger account for everyday work and
  this one as its backup, and it is measured again on the stronger account when its quota resets (O3's last step).
- **Impact:** design 6.22 ("Every correction proposes one piece of learning") says what the packet states and the
  check; O3 is closed on the backup model, with the main account's pairs owed when its quota resets.

## 2026-10-15: What the pairs on the backup model found

- **Found (O3, both pair sets on the low-cost backup model, `2bcff12`):** imprint 23 of 63, workplace 9 of 30. Read case
  by case against the code:
  - **Kept knowledge that never reached the later run** (`given` empty after a kept proposal). Two causes in the code:
    a reach (`applies_to`) takes any words as task kinds and record types, so a lesson naming a kind of work that
    doesn't exist applies nowhere, silently; and a routing entry reaches an input only when every word of its topic
    appears there exactly, so "the advance-copy reviewer list" misses "Which reviewers are getting advance copies?"
    unless the model also scoped it to the project. The ideal answers pass only because they scope it.
  - **Two pieces of learning from one correction:** "Not a project" and "It's part of" keep the person's own glossary
    entry and also queued a learning run, which proposed a broader lesson. (The learning answer's own limit of one op
    holds; the second piece came from the run itself.)
  - **Pairs stricter than the design:** a fact of what the mail states beside the expected op, and lesson wording
    checks ("complet", "already open") where the model said "finished" or "open questions".
  - **The model's own misses**, kept as the evaluation's signal: a missing owner (held for "Pick an owner", as it
    should be), no action where one was due, a routing proposal too broad, routing learned as a fact.
- **Decided (main session, under the owner's rule that each failing pair becomes a fix with its test before real
  use):**
  - a reach names only kinds of work and record types that exist, refused otherwise with the list, and the op
    reference shows the choices;
  - a routing entry reaches an input whose words share most of its topic, matched on word stems;
  - a correction whose answer already recorded its learning queues no learning run;
  - the pair report says what was kept, its text and reach, so a failure to reach shows why;
  - the pairs allow a fact of what the mail states where the golden cases do, and check a lesson by meaning-bearing
    stems with alternatives, each with a comment.
- **Impact:** a short fix wave before L7's own work (roadmap, L7); then the owner runs only the failing pairs again on
  the same account. Design 6.6 and 6.22 say how routing and a reach are matched.

## 2026-10-15: The op reference shows the "op" field every op carries

- **Found (owner's account check of a low-cost backup model):** the learning round-trip failed with "op 0 has no "op"
  field". Only the notes prompt said that each op names itself in an `"op"` field; the learning, reply, ask and check
  prompts and the op reference never did, so a model that didn't guess the shape failed the check, and in real runs
  needed a fix round.
- **Decided:** the op reference opens with the shape, with an example from its own list, so every task kind (core and
  plugin) shows it; the check's prompt shows it in its example. Test: `tests/test_op_reference.py`.
- **Impact:** the two pair sets of O3 run at this commit; the reference's first line changed once for every packet.

## 2026-10-15: Adding an AI account from Settings stays in Settings

- **Decided (owner):** "Add an account" in Settings opens only the AI account form, in place; it never sends the person
  back into the setup guide. The guide is for a first start.
- **Why:** the person came to change one thing; the guide's other steps are noise there.
- **Impact:** design 7.16 says so; built in phase B (roadmap, Settings). Until then the button opens the guide's AI step.

## 2026-10-15: The "after" run's last report: a spent plan, and pair checks on wording

**Decided by:** the technical PM, reading the owner's reports at `b136c7d`. **What:** the golden set passed 73 of 81 and
the harder set 55 of 57. The account's monthly quota ran out during the learning pairs, and two things in the app made
that look like 42 failures:
- **The quota message wasn't read.** The command-line agent presets give no error patterns, so "You have exceeded your
  monthly quota" was an unknown failure that the app retried. The agent adapter now reads common usage-limit and
  rate-limit wording after an account's own patterns.
- **The evaluators kept calling.** Both evaluators now stop at a spent plan: the runs after it are marked not run and
  never called, and the report is still written.
- **Pair checks on wording.** Pairs that checked the later packet for a lesson's exact words, which the model writes, now
  check that a lesson reaches the packet (the "# Lessons" heading), and match a lesson's own text by a stem. The two
  routing pairs allow the reply action the notes prompt asks for, and `routing-only-proposed` checks only that the
  unkept routing never sends the question to the one it named.
- Rescored that way, 32 of the 51 pair runs that reached the model passed. The 19 real misses are listed in
  `docs/project/evals/README.md`; several are L7's to fix.

**Why:** a report must say "not run" when the account refused, and a pair must test learning, not phrasing. **Impact:**
`engine/ai/adapters/cli_agent.py`, `engine/evaluate.py`, `engine/pairs.py`, eleven pair files; roadmap O3 stays open
until both pair sets run once the quota resets. No change to scope.

## 2026-10-15: The functional designer's answers to the round of 2026-10-15, and the owner's timing

**Decided by:** the functional designer (answers 2 to 24), the owner (timing), the technical PM (placement). **What:** every
open designer question is answered:
- **Concepts (core), L7:**
  - calendar entries only for real events, an action's date a `record.set` on its due (10);
  - only the named action moves (11);
  - a question asked of the person is one action carrying a drafted reply (12);
  - terms by audience (13);
  - discarded means don't act on it, flagged in search and checked (14);
  - outside mail never re-routes work, becoming a fact and a decision (15);
  - only the person rewords a question (16);
  - an inference feeds the record and only proposes closes (17);
  - the follow-on run with series, one hop and drafted corrections for what was sent (18);
  - decisions under the decider in follow-ups (19);
  - extras weighed by reach and tracked (21);
  - a drop of something sent waits (24);
  - replayed misses as a third set (2);
  - checks on every output (3);
  - series facts (6);
  - three ops the assistant may propose (8).
- **Settings, L7:**
  - owed words become requests addressed to the person, and a person with no team is asked about once (22);
  - more reported-speech words, with two exceptions (7);
  - a refusal floor of 3 a week (5);
  - "Not now" on the rules line (4);
  - the catch-up learns from the person's words first (23).
- **Screen, phase B:** two copy tables per person (20).
- **Project management pack, phase P:** the dependent move, the "approval before the work" flag and the "waiting on a
  decision" Today line (11, 19), which need its dependencies (6.23); the agenda storing the series (18).
- **The owner on timing:** the 2026-10-30 go/no-go stays set aside. The owner tests the tool after phase B and starts
  real use once the writing pack is complete. So L7 is built whole before phase B, with no split.

**Impact:** L7 grows from about 1.5 to about 4 sessions. Design 6.6, 6.7, 6.8, 6.16, 6.18, 6.19, 6.21, 6.22 and 7.5;
CHANGES section 71; the charter and schedule say the go/no-go stays set aside. Scope grows by L7's additions; nothing
else moves.

## 2026-10-15: The functional designer's lessons from running, and where each goes

**Decided by:** the owner (when, and the decision rule), the technical PM (the rest). **What:** eight lessons, checked
against the code: (1) a moved meeting brings what's tied to it in line: a core follow-on run per save, with records able
to name the calendar entry they belong to; the agenda and its links stay in the project management pack (design 6.24);
(2) replay cases that start from the person's own action; (3) each fact says who it rests on; (4) a contradicting answer
replaces the fact, a follow-up goes to whoever made the claim or owns the thing, and **a decision goes to whoever decides,
the PM when nobody is named** (owner; this replaces "decisions are questions to the PM"); (5, 6) a Copy table per person
in Follow-ups, from the same data and with no AI run (phase B); (7, 8) already built (the exclusive write lock, retiring
superseded attempts, Undo skipping what changed since), with a test to pin the superseded sequence; the history-row
exemption goes to the publisher (C4). Classified as core concepts (1-4), a screen feature (5, 6) and existing behavior
(7, 8); none is a setting or a standing rule. **Impact:** new roadmap step L7 (about 1.5 sessions), built after the
owner's "after" run and before phase B (owner); one phase B item; one C4 and one P item; design 5.1, 6.7, 6.8, 6.16,
6.19; CHANGES section 70; CLAUDE.md's product rule on decisions. Scope grows by L7; nothing else moves.

## 2026-10-15: What the owner's "after" run found, and how each finding was handled

**Decided by:** the technical PM, reading the owner's "after" run (O3) of the golden set. **What:** 32 of 81 runs
passed as first scored. Every failure was classified from what the run produced:
- **Cases out of date (34 runs):** since 2026-10-13 the notes prompt asks for a calendar entry beside anything an input
  dates, but the golden set's cases never allowed one, so a model that followed the prompt failed. Eleven golden cases
  and one harder-set case now allow `event.add`, and four allow a `fact` beside what they expect (a schedule row, the
  other lines of a check-in, the friendly line of a hostile mail, the body of a signed mail). A test fails any case whose
  input gives a date and that neither expects, allows nor forbids a calendar entry, so a prompt rule can't silently
  outdate the cases again. `colon-in-title` checks that a title stays whole, so it is met by a fact or an action that
  holds the whole title (an expected op may now name several kinds).
- **An app bug (likely `invitation-event`, 3 runs):** a calendar entry's times were stored exactly as written, so the
  same moment written `14:00Z` and `14:00:00+00:00` never matched. Times are now kept in one form on the record and the
  op (`canonical_time`), and the scorer compares times as times. Run summaries now show an entry's start and project.
- **Real misses (12 runs):** the assistant answered a moved date with a calendar entry instead of changing the action's
  due date (`they-finished-note`, 3 of 3), moved or closed a second action about the same thing (`date-change` 3 of 3,
  `own-edit-closes-action` 1 of 3), and once each named an owner for a shared first name and filed a date as a held
  action. The notes prompt now says how a new date for an open action is recorded (`record.set` on its due, the entry
  beside it) and that an input changes only the items its words name. The two single runs are left as variance.
- **The rerun at `c6d467c`** passed 74 of 81 golden runs and 44 of 57 harder ones, but most learning pairs failed
  before scoring: the assistant wrote a lesson's reach as `{"project": …}` or `{"id": …}` and links as titles. No
  adapter shows a model the answer's schema, so the op reference's field names were all it had of a nested shape. The
  reference now gives every nested field its keys, the values a choice allows, the kind of id a reference holds, and
  lists and mappings as such; a test checks every core op names each key its nested fields accept.
- **The rerun's harder set and pairs** (read from the reports): the calendar-entry correction now covers every pair's
  scored stage and the day-30 scenario, and the check that guards it reads "the 20th" and "tomorrow" as dates. Pairs
  whose expectation was wrong were corrected, each with a comment: `set-aside` (the later mail agrees the copy, which
  closes that action), `discarded` (the later mail answers the open cover-finish question, so it closes it),
  `injection-by-routing` (the PM's cover-finish decision is already open, so the later mail must only never reach the
  sender, and a proposal that the PM doesn't answer it waits for Keep like the other), `injected-import` (reworded to
  work no open action resembles) and `nudge-is-not-the-work` (the owner's own new day moves the due date). The notes
  prompt now says a vague time is not a new day, that a question asked of the PM is a reply they owe, answered from
  what the workspace holds, and that a known term is written out in what the assistant writes.
**Why:** the comparison with O1 and O2 must measure the assistant, not cases that lag the prompt; each correction is
shown beside the raw number. **Impact:** `engine/evaluate.py`, `engine/records.py`, `engine/ops.py`, the notes prompt,
17 cases; roadmap O3 (a short rerun of the four affected cases at the fix commit). No change to scope.

## 2026-10-15: The check on a switch runs the learning pairs too

**Decided by:** the technical PM, merging L4's second part. **What:** "Switch and check" runs the golden set, the person's
enabled packs' cases and the learning pairs as one report, passing at `ai.evaluation.min_score`; the estimate counts each
pair as about three calls at the cases' average price (a stated approximation, shown as "about"); the check is offered on
the AI accounts screen, not on a raw edit in the generic settings form. **Impact:** design 3.3, 6.16, 6.22; roadmap L4
(its build items done); plugin API 0.3.79. No change to scope.

## 2026-10-15: What L4's learning pairs found, and how each was fixed

**Decided by:** the technical PM, merging L4's first part. **What:** 28 pairs (12 negative) instead of 15 to 20, since the
roadmap lists that many cases; the pairs found four gaps in the loop, each fixed with a test: (1) a glossary proposal
that knows a term's meaning replaces a still-proposed "not known yet" entry for it instead of merging into it (an
unknown the person already kept stays, with the meaning proposed beside it); (2) "It's part of <project>" keeps a
workspace-wide glossary entry, since the name turns up in inputs not yet filed under the project; (3) a routing entry
goes with an input about its topic, not only one naming its person or team; (4) the `edited` signal existed in the
learning code but not in the record, so the person's direct edits never taught: it is now recorded for the fields the
assistant set, with the ledger saying who set them. The style pair and loading a shared lessons file move to L-more.
**Impact:** design 6.20, 6.22; roadmap L3, L4, L-more; plugin API 0.3.78. No change to scope.

## 2026-10-15: GitHub Models leaves the plan

**Decided by:** the owner. **What:** the service was added as a free second account before 1.0; its own documentation,
checked on 2026-10-15, says it was retired on 2026-07-30, so the item is removed. A second account remains possible
through any service that speaks the common format, an aggregator or a local model server. **Impact:** roadmap "Ready for
real use". No change to scope.

## 2026-10-15: The scope slice, as merged

**Decided by:** the technical PM, merging the scope slice. **What:** (1) the person's own typed note is exempt from
`watched-project` and `other-team-item`: their own words decide what they track, and the checks read what came in;
(2) the notes packet's project list says the person's part when it isn't "run", so the first answer on a watched project
needn't be returned; (3) an action owned by another team counts as owed to the person when its quote names them or
their team or says "we", "us", "our" or "me" (`language.owed_words`), so six golden cases were reworded to say who the
work is for ("send us two spine options"), which is what real mail usually says; (4) a person with no team counts as
outside the person's team. **Impact:** design 6.18; roadmap "Ready for real use" (scope slice done); designer question 9
is answered as its default. No change to scope.

## 2026-10-15: The quote check is for what the assistant asks of people, not long text

**Decided by:** the technical PM, merging L6. **What:** `unverified-quote` checks questions only; quotation marks in long
text are often the work itself (a story's dialogue), so a draft is never returned for them. The link check still covers
drafts. `summary_max_lines` lives under `workspace.project`. **Impact:** design 8.8; roadmap L6. No change to scope.

## 2026-10-15: The writing pack is finished before any other pack starts

**Decided by:** the owner (asked directly after the writing pack's builder passed it on). **What:** phase C is now the
writing pack alone, with what it needs from the core (C1, C4), and its own exit test; the project management and
publishing packs (C2, C3) and the hand-offs between packs move to a new phase P after it, before the owner's sign-off
(D). Both packs stay in 1.0. **Impact:** roadmap phases C and P; the plugin API table. No change to scope.

## 2026-10-15: L5, what the extractors and backup encryption use

**Decided by:** the technical PM, before building L5 (the owner: finish the L phases, then the UI). **What:** documents,
spreadsheets and presentations are read with the standard library (they are zipped XML); PDFs with one pure-Python
library (`pypdf`), so nothing outside Python is installed. Each extractor checks itself at startup on a small fixture and
a failure is a Today line. Backups are encrypted with the `cryptography` library when `storage.backups.encrypt` names a
key reference (`env:` or `file:`): every backup copy is then encrypted, restoring asks for the key, and the setting's
description and the backup screen say that a lost key means a backup that can't be read. **Impact:** design 4.15, 6.2,
12.1; roadmap L5; two dependencies. No change to scope.

## 2026-10-15: L3b, how each obvious next step is recorded

**Decided by:** the technical PM, before building L3b. **What:** "Add a new person" answers the routing question with a
person the person saves as their own, adding an unknown organization in the same change; a contact detail from a
signature is a new op, `person.contact`, that always waits for the person (outside content never becomes a way to reach
someone on its own); reading notes may propose `project.add`, which waits as a system op, and "It's part of" or "Not a
project" are kept as glossary entries rather than a new alias field on projects; `action.unhold` takes an action off hold
when an input says its blocker is gone; the rest (answered questions, dates, invitations, the person's own edit, the
unnamed recipient) use existing ops through the notes prompt, each with a golden case. **Impact:** design 6.7, 6.9, 5.1;
roadmap L3b. No change to scope.

## 2026-10-15: The catch-up learns once per kind, behind one go; hold is not a correction

**Decided by:** the technical PM, merging L3's last part. **What:** (1) the catch-up list queues one learning run per kind
of correction, from its newest correction that can still be learned from, not one per correction: thirty repeated undos
would otherwise be thirty runs on the stronger tier; (2) the runs wait together for one go, one Today line with the count
and total, since no general batch go existed; (3) the list holds only the kinds learning reads, so putting an action on
or off hold, the person's own planning, never waits there; (4) the router skips a backup account that isn't checked at the
moment of use, never the person's own pick for the tier, and an unchecked backup is no longer offered in a data-level
stop's account list. **Impact:** design 6.16, 6.22, 7.18; roadmap L3 (done). No change to scope.

## 2026-10-15: The assistant can hold and drop; an unowned action can be folded into the nearest one

**Decided by:** the technical PM, closing L3. **What:** "Change this" told the assistant to put on hold or drop, but it
had no op for either. Added: `action.hold` and `action.drop` (a new action status `dropped` with its reason), and the
assistant may propose `question.drop`; each needs evidence and applies as data with Undo, and only the person's own act
records a correction signal. A dropped action is never done or credited (product rule: finished work is credited to its
owner, so a drop must not look like a close). Folding a held unowned action into the nearest open one is one change
with Undo. Also moved: the learning pairs and the switch check to L4, a project's "what the assistant knows" and
"Overlaps with" to phase B. **Impact:** design 6.8, 6.9, 5.1 (action status); roadmap L3, L4, B. No change to scope.
**Found while merging:** the person's question corrections (reword, drop, reroute) wrote their signals without
queueing learning, so they never taught. Every signal is now written through one function that queues its learning,
and a test keeps it the only writer.

## 2026-10-14: L3, third wave B: learning on the card and on Today, the choices made while building

**Decided by:** the technical PM, reviewing and merging the builder's choices. **What:**
- **One route answers "what was learned from this card's correction":** `GET /api/knowledge/learned` gives a line for each
  correction that has something to show (still being learned, a proposal to keep, or the person's own words kept at once,
  with the change that undoes them). A card finds its lines by the change a correction was about, or by the records it
  names. `ProposalView` also names that change (`from_changeset`), and `ChangeItem` names the change a send-back redid
  (`redoes`) so the new card shows the line while the old one has left the list.
- **The reach list is made from the proposal's own target:** the target as proposed (narrowest, the default), the same
  kind of work on every project, any kind of work on the same projects, and everywhere; people and record targets stay.
- **"This doesn't apply here" leaves one project out of an entry or retires it,** both at once with Undo; the project is
  picked from a list. A fact and an entry already retired have no such menu.
- **Today's Review list shows every proposal waiting,** including those from corrections the person was there for,
  because the Today line counts them; a proposal acted on at its card leaves both.
- **The items in a person's card stay without buttons** (design 7.5), so the question menu (reword, ask someone else, drop,
  already sent) is on a question that has its own row (the decision and the waiting rows) and on its record page, where
  its status is known and "Already sent" is offered only while it is open.
- **Keep all** covers glossary terms that carry the words they came from; a fact is never a proposal.
- **"Because you told me" links** a rule or fact to its own page, and any other learned entry to the Knowledge screen
  (those kinds have no record page).

**Why:** The screens needed the signal-to-proposal link answered on the server, and the person should never type a reach.

**Impact:** design 7.18 and CHANGES section 59. API: one new route, new fields on the proposal, changeset and change views.
No change to scope.

## 2026-10-14: L3, third wave, part A: choices made while building the Knowledge screen

**Decided by:** the builder, for the technical PM to review. **What:**
- **Use is counted per run,** not per citation: a run counts once for an entry whether its log lists it as applied or one or
  more of its changesets cite it. Rules count by the log's own `rules_applied`, so the review and the screen agree.
- **Unused means active and never applied.** A proposal's use is shown too ("Never used"), so every row says it.
- **A failed check shows even for an account the person accepted unchecked.** Accepting waives the need for a check, not
  the news that one failed; the line's action tests again. The failed parameters of a test are kept beside the passed
  ones, so "failed" is told from "never checked for this work".
- **Edit is offered on a proposal only,** as Keep with the person's own wording. An active entry's wording has no op or
  signal kind of its own, so editing it waits for the design to add them.
- **The account line and the rules line are rows in the held-lines strip above Today's board,** where the other lines for
  work that needs a look live; the board's own Review line for what was learned is wave 3's other half.
*Kind:* concepts (core). *Impact:* none on scope; design text updated in 6.16 and 7.18.

## 2026-10-14: A plugin's records keep the stored shape they had; storing by alias is the core model's choice

**Decided by:** the technical PM, on a plugin builder's report. **What:** knowledge records (0.3.64) made the store save
every record by field alias, so a plugin field declared with an alias silently changed its stored key, and readers by
field name lost it. The store now saves by field name, as before, and only a core model whose config sets
`serialize_by_alias` (the scope's `except`, a Python keyword) is stored by alias; reference paths follow the same rule.
A change to the stored shape of a plugin's records is a breaking change: it waits for the next minor version and is
announced a round ahead, never made inside 0.3. **Impact:** plugin API 0.3.70; the plugin guide states how aliased fields
are stored. No change to scope.
## 2026-10-14: L3, second wave: learning from inputs, the measures, and accounts a fallback may use

**Decided by:** the technical PM, reviewing and merging L3's second wave. **What:**
- **Learning from inputs is part of reading notes,** not its own task kind: one input per AI call, so the run that
  reads an input proposes its terms, routing and superseding facts, guided by the notes prompt's learning rules.
- **The new-term scan runs after the answer applies,** rules only, and proposes each new term as unknown. Its entries
  have Discard, not Undo.
- **A question rerouted by hand teaches through its `routed` signal,** learned from at once, not a routing proposal of
  its own.
- **Answering the assistant teaches at once** (`answered_assistant`), and so does "Change this" (`change_requested`);
  a bare confirmation or an answer about someone else records nothing.
- **What a run applied and what it lacked** are kept on its changeset (`applied`, `missing`), not as new records. An id
  the run wasn't given is dropped and counted. The two rates and the weekly missing-op list are computed, not stored.
- **A repeat needs a target:** an entry with no target applies to everything, so no correction can be said to repeat it.
  Matching is by record type, not field.
- **A fallback chain is guarded where the person adds to it** (the settings save), with a plain refusal that names no
  internal key. A hand-edited chain is not yet flagged.
- **The account check makes one learning call per account,** so a stand-in or locked-down agent must answer it too.
- **A setting saved while the worker checks for changes** no longer reads as a restart: the worker judges a restart
  from the files its take-in read.

**Impact:** design 6.16, 6.20, 6.22, 4.25; roadmap L3; plugin API 0.3.69. No change to scope.

## 2026-10-14: Learning from corrections (L3a): choices made while building and merging

**Decided by:** the technical PM, reviewing and merging L3's first wave. **What:** (1) the learning task kinds are named
`learn-correction` and `learn-input` (a dot made their per-task settings path ambiguous); (2) a send-back and a picked
owner are learned from at once, silent corrections in a batch every `knowledge.learn_every_minutes`, through ordinary
requests with their estimate and go; (3) a learning run proposes at most one thing, and a second op refuses the answer;
(4) a rule from learning is a proposal like any other (L3p's rule-status change wins over L3a's earlier hold), and
`lesson.update` from learning is held; (5) netting reaches the one undo that withdraws a correction today (taking back
Mark sent); (6) a report to the maintainers whose words match `language.rule_report_phrases` is refused and turned into
a rule proposal, a phrase list by design; (7) learning runs show in What changed as task rows for now, to be labeled
with the screens. **Impact:** design 6.22, roadmap L3; no change to scope.

## 2026-10-14: The rules for proposals, built (phase L3p)

**Decision:** The original designer's rules for proposals are built as designed (6.22, 7.18, 12.8): a rule is a proposal like the
other kinds, duplicates merge, a close discard is not shown, "just this time" is a signal and a repeat is marked, one Today line
holds everything learned, proposals from inputs expire in a daily sweep, and the corrections recorded before are chosen once
into a catch-up list. Four choices the builder made, for review: (1) a `rule` record gains the status `expired`, the origin
`input`, `trust`, `discard_reason` and `more_evidence`, the same as the four kinds, and every knowledge record gains
`more_evidence` (the evidence of the proposals merged into it); (2) Keep also makes an entry's `trust` trusted, because the person
kept its restatement and target as their own words (before, a kept entry from content stayed data in packets for good); (3) the
catch-up list's state (when it was made, the chosen kinds, how many were left out, the rules moved) is a small file in the
workspace's private folder, so it is made once per computer, because a record kind for it would be a design change; (4) a
proposal "came from a correction" when it cites a signal or was written by a learning run on a correction, else from an input.

**Decided by:** the technical PM's brief, from the original designer's answers; choices (1) to (4) are the builder's.

**Why:** The brief needs somewhere to link merged evidence, to expire and discard rules, and to remember the one-time list; and
Keep's promise (12.8) is that the person's own words become guidance.

**Impact:** Design 6.22, 6.20, 7.18, 12.8 and CHANGES section 55. New settings `knowledge.discards_hold_days` (90),
`knowledge.discard_similarity` (0.8), `knowledge.proposals_expire_days` (14) and `knowledge.catch_up_max` (20), with demo values in
both workspaces. API: `GET /api/knowledge/proposals`, `GET /api/knowledge/catch-up`, `POST /api/knowledge/{id}/just-this-time`; the
Today queue gains the kinds `learned` and `catch_up`; keep and discard take a rule id. The plugin guide is regenerated (core
records changed). No change to scope.

## 2026-10-14: L3, correcting what the assistant made: the choices made while building

**Decided by:** the builder, for the technical PM's review. **What:** (1) The corrections of a question are ops
(`question.update`, `question.move`, `question.drop`, `question.mark_sent`), person-only, applied as the person's with
Undo like `record.edit`, never offered to the assistant. The signal is written in the same transaction but apart from
the change, so Undo leaves it in place and records no `undone`; learning nets it out later (L3). (2) Moving a question
does not require a link the new person can open: the person chose to ask them, and the invariant is about what the
assistant files. (3) Reword and drop take the person's words as their own record, so those two routes are declared
local-only in `api/free_text.py`; "Change this" is the one that goes to the assistant. (4) "Change this" accepts the kinds
`action`, `question`, `decision`, `event` (a calendar entry) and `fact`; `decision` and `question` are the same record
kind. Its note is always read, however short. (5) `mail.restore` writes its hand-in as the op, so Undo takes the handed-in
request back. (6) The owner suggestion is read from routing entries and open actions at the moment the screen is built,
by the same word-overlap matcher as the near-duplicate lint, and only offers; two settings (`several_questions.minimum`,
`owner_suggestion.match`). (7) `matters_for` and `dropped_reason` are kept on the question record. *Kind:* concepts
(core), settings and a record field. **Why:** the designer's lessons from running named these hand fixes; each choice
above was the narrowest one that keeps Undo and the signals truthful. **Impact:** design 4.17, 6.7, 6.8, 6.9, 6.13, 6.20,
7.7 and CHANGES 56; plugin guide and OpenAPI regenerated; new lints default to `return`. No change to scope. Open: the
assistant has no op to put an action on hold or drop an item, so a "Change this" note asking for either gets an answer
that says so (6.13's missing-op list); whether to add them is for the technical PM.

## 2026-10-14: The harder set's "before" run: the cases were wrong, not the assistant

**Decided by:** the technical PM, reading the owner's O2 report. **What:** 30 of 48 runs passed at `feb6b3f`; all 18
failures were extra ops in six cases, none missing or forbidden. Each extra was right: a calendar entry beside a dated
action, which the notes prompt asks for; a fact worth keeping; an owned commitment. The harness gains `allow` (op kinds
that are right but optional in a case, never counted as extra), the six cases list theirs, and the same outputs rescore
48 of 48. **Why:** exact scoring is meant to catch over-production, not to penalize what the product asks for.
**Impact:** on the owner's account the extraction sets have no headroom, so L4's comparison rests on the learning pairs
and the repeat-correction rate, as planned; `engine/evaluate.py`, six case files, the evals README. No change to scope.
Open for the owner and the original designer: whether every dated action should also get a calendar entry, as the
notes prompt asks today (it duplicates the to-do list's due date).

## 2026-10-14: The original designer's afternoon lessons, placed after checking the code

**Decided by:** the technical PM. **Checked against the code first:** (3) ids are never reused: each kind keeps a
high-water sequence saved with the data and carried through export and import (`engine/storage/store.py`,
`engine/storage/export.py`), proven by `tests/test_store.py::test_deleted_ids_are_never_reused` and
`test_explicit_ids_reserve_the_sequence`; nothing to change. (6) one shape per field: core records and ops are typed
models validated on every write and on import, so a field has one declared shape; a plugin's own data files are the
plugin's to validate. (7) watched changes already carry their author and `by_us` from `workspace.our_accounts`, but a
local file has no author, so a source needs one in its settings. **Placed:** (1) "Made:" links and the `unlinked-made`
lint, (5) summary as status, (7) a source's author: before real use; (2) one question per id, (4) the unowned action held
with a suggestion, and offering glossary ops to notes runs: L3; closing an action the person's own edit fulfills: L3b.
*Kinds:* concepts and lints with settings. **Impact:** roadmap; design text when each is built; no change to scope.

## 2026-10-14: The end-state goal: replace consulting teams; idea validation first; one person, then teams

**Decided by:** the owner. **What:** the end state aims to make business consulting teams unnecessary, so the packs
must cover what clients pay consultants for (playbooks, evidence, alignment, accountability, results shown); an idea
validation step comes before business analysis; the rollout is one person with one idea in the real world first, then
full-time teams through the hosted organization install (11.8). *Kind:* product direction, packs; no core change now.
**Impact:** the charter's "End state"; no change to 1.0's scope.

## 2026-10-14: The end state beyond 1.0: a delivery chain of packs

**Decided by:** the owner. **What:** the core stays everyday project support; packs extend it; a full set of packs
carries a business requirement through business analysis, project management and technical design, development in
sprints with built-in testing and demos, test cases and user acceptance, to a facilitated deployment (charter, "End
state"). *Kind:* product direction; packs, not core. **Why:** the owner's statement of where the product goes.
**Impact:** the charter and the roadmap's "Not in 1.0"; no change to 1.0's scope. **Answered by the owner the same day:**
planning and tracking belong to the project management pack; building is staged: first a build pack the person takes to
a coding agent ("build it"), then read-only connectors that give the PM the whole development process in one place, and
in the end the cockpit driving the building, which needs its own safety design first.

## 2026-10-14: L2's second wave: choices made while building

**Decided by:** the technical PM, reviewing the builders' work. **What:** (1) a scope that names a project covers its
child projects at any depth, for `projects` and `except`; facts stay per exact project. (2) Refusals are counted
including those a fix round repaired, and no seed lesson enters before `knowledge.refusals_to_packet.min_runs` (10) runs
are counted. (3) A rule is flagged for review only after a whole review period since it was learned or kept, so Keep
starts the count again; the weekly line's clock is the person's last Keep, Narrow or Retire. (4) "Its check ran on the
output" is wired but waits for a check that runs on a run's output; today stage checks run on moves. (5) The review's
screen comes with L3's Knowledge screen; the engine, line and routes are built now. *Kind:* concepts (core) and two
settings. **Why:** a series' rules must reach its books; fix-round refusals are the case seed lessons exist for; without
the period, Keep would reset nothing. **Impact:** design 6.22, CHANGES 54, plugin API 0.3.67; no change to scope.

## 2026-10-14: The Today mockup's review: "Just this time", one learned line, and row rules

**Decided by:** the original designer's review of the Today mockup, placed by the technical PM. **What:** the Learned
line gains "Just this time" (signal kept, no proposal, counts toward a repeat), and a lesson is about what was corrected;
the two Today review lines for learned things merge into one, each entry tagged by its origin; every row has a project
tag; each item of a review card has its own "Change this"; a card is titled by what it holds; an overdue follow-up's menu
has Followed up and They finished it; a to-do says what it waits on; the counts agree; a line offering another account
names it. Followed up stays in the menu rather than beside Draft a nudge, because a row has one primary action and the
rest in its menu (owner's UI rule). **Why:** each was a point where the screen said something the person couldn't act on
or misread. **Impact:** design 7.7 and 7.18; roadmap L3 and phase B; no change to scope.

## 2026-10-14: A slice of scope moves before real use

**Decided by:** the original designer, agreed by the owner. **What:** the person's role on each project (run, design,
watch) with its "I'm running X now" proposal; facts only on a watched project, enforced by the applier; and another
team's item is a fact unless the input says the person owes them something. The rest of the scope resolver (6.18) stays
in phase E. *Kind:* concept (core), with the role values as a list a pack can extend. **Why:** the running version needed
scope on day two (115 changes closed as not the person's in two weeks; 9 of 100 lessons were scope mistakes), and
week-one "that's not ours" corrections would swamp the repeat-correction numbers the first month is judged on.
**Impact:** design 6.18; a "Ready for real use" item with its journey test; a core record change (a project's roles)
when built; no change to scope.

## 2026-10-14: The original designer's lessons from running (nine), placed

**Decided by:** the technical PM, placing the original designer's lessons of 2026-10-14; checked against the code first.
**Where each goes:** (1) the person's role on each project decides scope: a concept, with the scope resolver (6.18,
phase E) and a learning pair in L4; (2) the missing-op list: a concept (6.13, L3), with the code check of the six hand
fixes in the roadmap; (3) a question says why it matters: a concept (`matters_for`, L3), the row's source link already
built; (4) "Change this" on every assistant-made row: L3, with its signal; (5) date moves left out of reader history and
(6) a Completed group: phase B and the publisher (C4); (7) a failed call never shown as empty, and credential expiry
reminders: concept plus a setting, before real use; (8) extractor self-test at startup: L5; (9) no tool version numbers
in messages: a lint with its patterns as a setting, before real use. **Core or pack (owner's question):** all nine are
everyday project support, so the mechanisms are core; the parts that belong to one kind of work go to packs: the
published portfolio page's Completed group and reader history (the project management pack, through the publisher), the
role values beyond run, design and watch (a pack extends the list), and a wiki's page-version patterns (that connector's
pack). **Why:** most failures were something the assistant
had no op for or something the person couldn't see. **Impact:** design 6.13 and 6.18; roadmap items in L3, L4, L5, E, B
and "Ready for real use"; no change to scope.

## 2026-10-14: GitHub Models becomes an API option before 1.0; a Copilot SDK adapter waits for its stable release

**Decided by:** the owner, after reviewing outside advice on how the app reaches AI accounts. **What:** GitHub's model
service, which is OpenAI-compatible with a free rate-limited tier, is offered as an account choice before 1.0, through
the existing OpenAI-compatible adapter (settings, no new adapter), once its limits are checked against real packets. An
adapter for the Copilot SDK is a future enhancement, after it leaves technical preview; the command-line adapter stays
the default for people whose only account is Copilot. Agent SDKs and tool protocols that give the model files and tools
are not used: the assistant only proposes changesets. *Kind:* extension (config for an existing adapter), and a future
adapter. **Why:** most people have one account; a free second one makes the one-account wait rarer without spending.
**Impact:** a Ready-for-real-use item and a "Not in 1.0" line in the roadmap; no change to scope or design.

## 2026-10-14: One AI account is the usual case; borrowing another tier's account asks first

**Decided by:** the owner, answering the original designer's L1 check-in. **What:** most people will have one AI account,
so the product plans for it: a usage limit means the work waits for the reset, said on Today with the time (built). With
two accounts, when the low-cost routine account runs out, the person is asked whether to use the higher-cost one until
the routine one is restored; never switched silently. *Concept (core) with a setting:* `ai.borrow_other_tier` (ask,
never; default ask). **Why:** spending more is the person's choice (design 6.16), and a one-account setup must not look
broken. **Impact:** design 6.16; a Ready-for-real-use item with its journey test; no change to scope.

## 2026-10-14: The original designer's L1 check-in and answers for L2

**Decided by:** the original designer (check-in and answers), placed by the technical PM. **What**, each with its kind:
- *Concept (core), with a setting:* a note on any button that repeats someone else's words is reported content; the words
  are `language.reported_speech` (speech words, the person's own speakers, the shortest quoted passage).
- *Concept:* a typed note's fact takes the day its text names (already so in the code; now tested and said in the op).
- *Concept:* retiring a rule records the same `retired` signal as any other knowledge.
- *Plan:* the harder golden set moves ahead of L2 (L1b), and its "before" run (O2) is pinned to the commit that adds it;
  one account in the chain becomes an explicit owner decision before real use.
- *Concepts for L2:* a rule's `constrains`; applied versus present, both checked without the model; the weekly review
  with Narrow; the always-sent section's budget order and one-line form for stage-checked rules; scope filtered at
  packet build; local-first search and `already-known` before every question op; the section's size in every run's log.
- *Concept for L3:* rules from anyone but the person become proposals; held rule decisions move to the catch-up list once.

**Why:** a rule the person types on someone else's behalf is still someone else's rule; L2 changes packets, so the
"before" has to be pinned first; a broad rule can never be flagged if relevance alone counts as applied. **Impact:**
design 5.1, 6.5 and 6.22, CHANGES 52; a core record change (`source.reported`, plugin API 0.3.65); a new setting with demo
values in both workspaces; no change to scope.

## 2026-10-14: Rules are records with the knowledge scope; facts and signals gain what L2 and L3 read

**Decided by:** the technical PM, merging L1's three parts. **What:** a standing rule is a `rule` record seeded once
from the rules file and changed only by `rule.add` and `rule.retire` (system tier, with Undo); stage checks read the active
records. Its `applies_to` is the same `Scope` as the four kinds of knowledge (with `projects`, `people`, `scope` and
`except`), so one shape covers everything that guides a run. `rule.retire` stays its own op beside `knowledge.retire`: a
rule has a name other settings refer to and a check, and its retire is never a proposal. Facts gain `key`, `as_of` and
`supersedes` (what replaced a fact is computed from the newer one, so Undo needs no second write); signals gain `run` and
`changeset`. A knowledge add from a note on the person's own button is the person's words and is active at once; from a
button that relays someone else it is a proposal. **Why:** two scope shapes would have to be reconciled by every reader
in L2. **Impact:** design 4.10, 5.1, 6.20, 6.22 and CHANGES 50; plugin API 0.3.64; no change to scope.

## 2026-10-14: How L1 reads whose words a typed note is

**Decided by:** the technical PM, on the original designer's sign-off of 2026-10-13; details placed by the builder.
**What:** the source of a note typed on a button records its author. Mark done, Reopen, the choice of an owner, an answer
to a question asked of the person and text added to an action's notes are the person's own words; a system op from them
applies at once with Undo (a loosening for these buttons only). They finished it, Followed up and an answer recorded for a
question asked of someone else are content the person reports, authored by the person they are about; a system op from
them is held, and a knowledge add from them is a proposal that waits for Keep. **Why:** the person's own typing is not
an injection risk, but a pasted reply is someone else's words. **Impact:** design 6.5, 6.7, 5.1 and CHANGES 51; a core
record change (`source.author`, plugin guide regenerated). Left open: a person who pastes someone else's reply into a
Mark done note is treated as the author of it.

## 2026-10-14: Knowledge records (L1): a proposal applies as a record, and the person's own act makes it active

**Decided by:** the technical PM's brief for L1; recorded with the build. **What:** lessons, glossary entries, routing
entries and style notes are core records with one shared base and one `applies_to` shape (a rule's target plus
`projects`, `people`, `scope` and `except`). Their `origin` is person, input, assistant, pack, seed or import (replacing
the first design's "correction, input, ask, import, pack or seed": an ask or a correction is the person's own words or the
assistant's generalization, and the record says which). The seven ops (`lesson.add`, `lesson.update`, `glossary.add`,
`glossary.update`, `routing.add`, `style.add`, `knowledge.retire`) are system tier, but an add that is not from the
person's own words applies as a **proposal** instead of being held, because a proposed entry changes nothing until the
person keeps it; an update or a retire from anyone else is held as any system op is. Keep and Discard are the person's own
`record.edit` of the entry's state fields, so they need no further op and undo like any edit; each records a `kept` or
`discarded` signal, as Retire records `retired`. The ops are offered to neither reading notes nor a plugin's action until
the work that learns (L3) offers them. **Why:** a held proposal would pile up on Today as system decisions, while a
record the person keeps or discards is the same safety with one step fewer; and the status, never the op's tier, is what
keeps untrusted content out of packets. **Impact:** design 5.1, 6.7, 6.20, 6.22, 7.5, 12.7 and CHANGES 49; the plugin
guide is regenerated (four record types, seven core ops, three signal kinds; plugin API 0.3.64); the API gains
`GET /api/knowledge` and three person routes.

## 2026-10-14: An action can be on hold (`on_hold`), and one rule decides follow-ups

**Decided by:** the technical PM, on the original designer's lessons. **What:** an action gains an optional `on_hold`
(`waiting_for`, plain text, and `since`), set and cleared only by the person ("Put on hold", "Take off hold" in the row's
menu, each acting at once with Undo and recording a `put_on_hold` or `taken_off_hold` signal). It is a field, not a new
status: `held` already means waiting for an owner, and the action keeps its due date for when it comes off hold. An action
on hold is never due, overdue or chased, in Today, Follow-ups and the packets. One function decides whether something sent
is due a follow-up: a question after 4 days; a told action only when its own due date is within 7 days or past (and it
has waited as long as a question); an undated one after 14 days; never on hold. The three thresholds are settings
(`ui.followups`) and replace `ui.today.nudge_after_days`, which is read as the question wait in an old file. Taking an
action off hold when an input says the wait is over stays with L3b. **Why:** a day of real use showed held actions
nagging, and deadlines weeks away being chased as if due. **Impact:** a core record change (the plugin guide is
regenerated; plugin API note to follow), two new signal kinds, three settings in both demo workspaces, designs 5.1, 4.11,
6.9, 6.20 and CHANGES 48.

## 2026-10-13: L0 signed off; what the original designer settled for L-core

**Decided by:** the original designer (L0 review, relayed by the owner); placed by the technical PM. **What:** L0 is
signed off and P13 closes. L-core's exit gains "Ready for real use": the note box on action buttons, the header's alive
line, on hold isn't due, the follow-up rule and the working source link, built at the end of L-core with phase B keeping
only their layout. Before L1: a note's author follows the button (They finished it, Followed up and an answer for someone
else are content the person reports, authored by the owner or sender; facts apply, rules and lessons wait for Keep),
knowledge proposals are writable on every account a chain can hold (tested in the switch check), knowledge keeps its
provenance link, and scopes take exclusions (`applies_to: workspace` with `except`). L2 budgets the stable prefix and
flags rules unused for 30 days; the catch-up list is capped at 20; the learner states the class and its test. The O1
"before" run is best done while L1 is built. **Why:** real use starts when L-core passes, and these are what the first
week needs. **Impact:** L-core grows by these items; phase B's scope shrinks to layout for the five; L1 starts only when
the owner says so.

## 2026-10-13: The original designer's lessons from running, placed in the plan

**Decided by:** the original designer (lessons from running the work version, relayed by the owner); placed by the
technical PM. **What:** L0 gains three items (every place the person types text reaches the assistant; wording checks
skip links; a retry that applies retires the attempts before it); L3 gains "a correction that will apply again is
knowledge, never a code request"; L3b gains "don't guess who something was sent to"; phase B gains the source link's
targets, on hold isn't due, and a header that always shows the assistant is alive (two rows, tested at 1,000 px); the
project management pack gains bulk extracts before item-by-item calls; C4 gains the rules for writing into a shared
file. The lost-network rules and one line per person were already placed. **Why:** each was found in a day's real use.
**Impact:** L0 grows by three items before it closes; the rest is in its phase.

## 2026-10-13: The hosted end state is an organization install with roles

**Decided by:** project owner ("an organization level install - like publisher where approved users from the people list
would have access to certain roles & responsibilities ... we won't build this now, but that overall organization wide
architecture needs to be part of the end state hosted setup"). **What:** design 11.8 describes it: members are people
on the People list, roles set what each sees and does (per person and per project), each role has its own views, packs
declare which roles their parts are for, the ledger records the person behind each change, approvals belong to roles.
**Why:** a publisher with many writers, editors and staff is the product's natural end state. **Impact:** nothing built
in 1.0; from now on new core code never assumes a single person (CLAUDE.md), and plugin API additions are designed with
roles in mind.

## 2026-10-13: The first go's estimate includes the sorting run

**Decided by:** the technical PM. **What:** the first go's estimate is the items handed in plus the sorting run the go
also makes for unsorted mail, so the person approves the whole spend. **Why:** the go starts that run too. **Impact:**
design 7.8; the Today line and the screen's line; `GET /api/runs/first-go`.

## 2026-10-13: The original designer's review of L0 and the work version's screens

**Decided by:** the original designer, on review; accepted by the technical PM. **What:** a lost network never pauses an
account or counts toward one failing, a successful run clears its account's pause, the header shows the offline state,
and the Today line waits an hour by default; every text field in an op must be text, refused when it arrives as a
mapping or a list; one follow-up rule for Top priorities, Today and the Follow-ups pills (an action notice is chased
only when its action is due within 7 days or overdue, never on hold, an undated one after 14 days; a plain question
after 4 days); Top priorities writes one line per person; the action-items item gains a source link, notes from any
action button, project tags and stand-alone wording. **Why:** each was found in real use of the work version.
**Impact:** two L0 items (the network follow-up, text where text belongs); phase B's Top priorities and action items;
the follow-up rule's numbers are settings. Design 6.9 and 8.6 change when each is built.

## 2026-10-13: The plugin API has its own road to 1.0 in the plan

**Decided by:** project owner ("the API updates ... are important to define timeline plan on"). **What:** the roadmap
gains a table of what the plugin API gains in each phase, the version each lands in, whether it breaks anything, and the
freeze (0.9 in phase D) and 1.0 (at Publish 1.0, once the writing and project management packs run unchanged through
phase D). **Why:** the pack builders plan their work against it. **Impact:** roadmap only; the versioning rule in
`docs/plugin-api-0.x.md` is unchanged.

## 2026-10-13: Copy puts formatted text and plain text on the clipboard; no generated page to copy from

**Decided by:** the technical PM, on the owner's request to decide as a UI/UX question (the work version opens a
generated page with a copy button). **What:** Copy writes the previewed message to the clipboard as both formatted text
and plain text in one step; the place it is pasted chooses. No separate page or file. Copy as plain text is in the menu.
**Why:** the preview the person reviewed is exactly what they paste, with one fewer window and no files piling up; it
works the same hosted, local and on a phone; the formatting is built by the app from escaped text, so nothing the
assistant writes becomes markup (design 7.0, never render raw HTML); chat apps that mangle formatting get clean plain
text. **Impact:** design 7.5; the roadmap's phase B item; the existing Copy and Mark sent flow is unchanged otherwise.

## 2026-10-13: What the work version's screens add to phase B and the project management pack

**Decided by:** project owner (sent screens of the version they use at work; open promise P11). **What:** phase B gains
follow-ups by person or project, handing an action to the assistant, projects grouped
under their parent with stage, target and last update, links to the person's own pages, a meeting added in one line, a
pasted screenshot in the hand-in and a check against raw data on screen; Top priorities is shaped from the screens. The
project management pack (C2) gains a project update on request and health per project. **Why:** these are what the
owner uses every day. Not taken: the work version's "fix ready" offer, which changes that tool's own code; this product
never changes its own code (design 6.13; owner, 2026-10-13). **Impact:** roadmap phase B and C2 only; no design section changes until each is built.

## 2026-10-14: A business analysis pack and a systems architect pack are planned

**Decided by:** project owner ("two more obvious plugins ... Business Analysis and Systems Architect ... they can be used
to submit change requests to you for system improvements").

**What:** Two packs in the plan (roadmap C3c), each in its own private repository. They draft the outputs of those roles
from inputs and work with the other packs through interfaces. Change requests for this product go through the core's
`report.draft`, which the person reviews and sends to the maintainers; the product still never changes its own code
(design 6.13).

**Why:** Both roles' outputs are what most kinds of work need beside a project plan, and well-formed change requests
make improving the product faster.

**Impact:** The roadmap gains C3c. No change to the core's scope; `report.draft` already exists.

## 2026-10-13: Ask names a setting by a short handle, never its key (phase L0)

**Decided by:** the technical PM (main session, on review). **What:** Ask's material names each setting by its screen name
and a stable short handle made from its key; `setting.propose` names the handle, and the applier resolves it against the
current settings list. **Why:** an answer cites the material word for word, so a key in the material can reach the screen;
a handle is unambiguous where screen names can repeat across groups and add-ons, and scrubbing keys out of quotes would
break the citation check. **Impact:** design 6.25; `engine/help.py`, `engine/ops.py` and the applier (roadmap L0, the
wording item; built). The op's field changed from `key` to `setting`, which is in the generated plugin guide.

## 2026-10-13: A wording lint on an item that stays internal warns, with no fix round (phase L0)

**Decided by:** the roadmap's L0 item "A blocked word costs a second AI request", from the mail journey. **What:** wording
lints read only the assistant's own words, never the quoted evidence. A `return` wording lint (blocked wording, run-on
list) on an item that stays internal (anything but a question to someone other than the PM) is applied as `warn`; only items that reach
another person get the fix round and, if it still fails, are held. **Why:** a fix round doubles the cost of a mail for a
warning nobody needed to wait for. Near-duplicate actions and evidence fit are about correctness, not style, so they keep
their configured severity on every item (the technical PM, on review). **Impact:** design 6.7 (lints); `engine/applier.py`; no setting, no API change.

## 2026-10-13: Where the code and the design differed, decided (phase L0)

**Decided by:** the technical PM (roadmap, phase L0). **What:** a question's stored kind stays and the screen follows it
(design 6.8 corrected); "me", "myself" and "I" are the setting `language.self_words`; a greeting uses the person's optional
`first_name`, else the first word of the full name; `owner_format` is read where the app shows an action's owners (an owner
with no team is shown by the full name alone; parsing it back stays unscheduled); an action whose text or due date changed
after a person was told counts as to send again for that person; names resolve only on an action's owners and a question's
recipient (6.11 corrected). **Impact:** design 4.1, 4.6, 5.1, 6.8, 6.9, 6.11, 8, 10; one additive person field (plugin guide
regenerated, plugin API version not changed); one new setting with demo values in both workspaces.

## 2026-10-13: Design 6.8 to 6.11 say what is built and what is designed (phase L0)

**Decided by:** the audit of 6.8 to 6.11 against the code, as the roadmap's L0 item asks. **What:** the sections keep their
content; each rule the code doesn't follow is marked *designed*, with its phase, and corrections to questions (reword,
reroute, drop, the feedback run, `draft_edited` tied to its run) are an L3 item. Where the code does something different from
the text, the text is unchanged until the owner decides which is right. **Impact:** design 6.7 (one phrase), 6.8 to 6.11 and
Part 6's status note; the roadmap's L0 and L3; no code, no setting.

## 2026-10-13: One "who is this?" per name, a signal for the answer, and no signal for undoing the person's own release (phase L0)

**Decided by:** the design (6.8, 6.11, 6.20) is built as the audit of 6.8 to 6.11 found it should be.

**What:**
- Ops of one input that wait on the same unresolved name (compared ignoring case and surrounding space) share one question;
  answering it applies every one of them. At most one open question per name per input.
- Answering "Who is X?" or "Pick an owner" records a `routed` signal (a new kind: the person said who a name or an owner
  is), with the changeset, the question and the person chosen.
- Undoing an op the person released or ran themselves records no `undone` signal; undoing the assistant's work still does.

**Why:** several questions for one name tired the person and inflated the counts; the best correction the person makes was
thrown away; and undoing their own decision is not a correction of the assistant.

**Impact:** design 5.1 (signal kinds), 6.8, 6.11, 6.20; one additive signal kind; no new setting; keeping the chosen name as
an alias stays with L3.

## 2026-10-13: Review earned per kind of change; the PM pack's charter and minutes; a sales pack waiting on requirements

**Decided by:** project owner ("the human approver is there for most everything, but over time the AI should learn what
can be auto AI approved"; the PM pack generates "project schedules, charters, ... moms"; a sales support pack "waiting
on functional requirements").

**What:**
- **Review earned per kind of change** (phase L-more):
  - A kind of change the person has passed unedited enough times in a row stops needing a look. It stays in What
    changed with Undo.
  - One correction takes the kind back to review.
  - It's based on the person's record, never a model's confidence.
  - It's never for anything outbound, system ops or a new or probation account: those rules are invariants.
- The project management pack drafts charters and minutes of meetings (C2).
- A sales support pack is planned once its user's requirements arrive (C3b); nothing before that.

**Why:** Reviewing everything forever doesn't scale. Earning less review from the person's own record keeps the rule
that the human approves what matters, while routine work stops costing them clicks.

**Impact:**
- Design 6.22 and 7.18 when built.
- One setting (`ai.earned_review.runs`).
- The roadmap: L-more, C2, C3b.

## 2026-10-13: Top priorities, the Monday briefing, and blocked actions

**Decided by:** project owner ("go ahead and add, because in the original version of this that I use at work, it has
monday briefings as well as a constantly updated top priority items"), after the design was compared with an outside
list of core features. The comparison found two gaps: actions can't be blocked, and nothing is sent to the person.

**What:**
- Top priorities on Today, ranked by rules, always current (phase B).
- The Monday briefing, built by rules in the app, with an optional AI summary (phase B). Sending it is phase E, under
  7.19's rule on content in notifications.
- An action can be blocked, waiting on something. Unblocking from an input is L3b; dependencies stay in the project
  management pack.
- The owner's picture of the work version shapes both before they are built (open promise P11).

**Why:** Both are what the owner relies on at work every day. A blocked action is everyday state, not methodology.

**Impact:** The roadmap: phase B, L3b and phase E. Design 7.7 when designed from the picture. A weekday setting and an
optional task kind when built.
## 2026-10-13: First names in context, and the received date, are built as designed (phase L0)

**Decided by:** the design (6.11, as changed by the review of 2026-10-12) is built as written; the choices it left open,
marked below as "builder's choice", are for the owner to confirm or overrule.

**What:**
- A bare first name resolves only for a person in the input's context: the PM, the sender and the others on the message,
  and the people of the input's project. The others on a message (builder's choice) come from the add-on (`participants`, plugin API 0.3.58) or
  the From, To and Cc lines at the head of the input's own text, so a pasted message works the same as a read one.
- A name with an initial or surname fragment resolves only to a person it fits; otherwise it is held with the people who
  share the first name, even when one of them is in the thread.
- An alias a person or the PM set still resolves as before. Two people who share an alias are told apart by the context
  (builder's choice).
- A watched mail's received date is its own received time. Every golden case carries `received:` and the clock freezes there.

**Why:** a unique first name used to resolve with no context, so a stranger with a common first name was taken for a
colleague.

**Impact:** design 6.6, 6.11, Part 5 (source, snapshot), 8.5 and the golden-set section of 6.16; plugin API 0.3.58
(optional `participants`); no new setting.

## 2026-10-13: Phase A done; the obvious next step from what came in is planned

**Decided by:** project owner ("I think we can mark A done"; "when the AI asks who someone is it should allow you to
add a new person, if it reads something that looks like a project that it hasn't heard about it should ask if it
should add a new project, if it sees dates it should create dates/milestones under that project, etc. Basically
standard obvious things. Doesn't need to be right now, but needs to be part of the plan").

**What:**
- Phase A is done, on the owner's own run of its exit test.
- **The obvious next step from what came in** is planned as L3b in L-core, with its buttons in phase B:
  - "Who is this?" offers "Add a new person".
  - A project it hasn't heard of becomes "Add a project <name>?", with "It's part of" and "Not a project".
  - Dates go under their project (calendar entries; milestones with the project management pack).
  - The rest of the obvious set: organizations, signature details, due dates, answered questions, invitations.
- Reading notes will be offered `project.add` (still a system op that waits for the person). That reverses the rule
  that only actions and plugin work start projects.

**Why:** Today the assistant asks questions the person has to work around: "who is this?" offers only existing people,
and an unknown project leaves work filed with no project.

**Impact:**
- Design 6.7 (`project.add` from notes; the obvious-next-step list).
- The roadmap gains L3b and a phase B item.
- No new setting.

## 2026-10-13: The walkthrough, the app's own add-ons, answers on screen, and dated items in the calendar

**Decided by:** project owner ("if a person doesnt want to add other people at the beginning they shouldn't keep
getting the wizard"; "no you need the wizard opened everytime if the user never setup their user info"; "i dont want to
see these fake plugins"; "When a dated item comes in and is not filtered out it should create a calendar entry").

**What:**
- **When the walkthrough opens by itself:**
  - On every visit while you haven't named yourself or no AI account is chosen for any kind of work, whatever was
    pressed before. The assistant can't work without them. An account that fails its test is said on Today, not by
    reopening the walkthrough (the built-in stand-in counts as chosen).
  - Otherwise only on a workspace's first visit. Mail, backups and people wait on Today's setup line.
  - A sign-in returns to the screen it was started from, so leaving for the service's page no longer depends on the
    walkthrough reopening.
- **Headings show no focus ring.** A heading takes focus when a screen opens or changes, for screen readers. It isn't
  something to press, so the ring only looked like a stray outline.
- **The add-ons that come with the app** (its own `plugins` folder: the example and the define-your-own kit) are
  never listed in setup as add-ons to turn on. The Add-ons screen shows them only once turned on, or in a sandbox
  workspace. Offering the kit where it's wanted is phase B.
- **What the assistant did is always in words.** Every core op has a label on the wording sheet (16 had none, so
  "op.answer" showed). An answer shows whole, not its 150-character label.
- **The app keeps its own calendar, and a dated item becomes an entry in it** (owner: "the calendar (internal) is an
  important part of the whole project cockpit and especially when we do the PM plugin").
  - The calendar is a core concept, not a view of the connected calendars. Its entries come from what came in, from the
    person, and from plugins (the PM pack's milestones and meetings build on it).
  - A dated item that isn't set aside becomes an entry (`event.add`) beside the fact, and shows on the agenda.
  - Nothing is ever written to the calendar service.
  - Phase L0 for the entries from what came in; the PM pack (phase C) uses the same records.

**Why:** The walkthrough kept returning for an optional step. Sample add-ons read as the person's own. Internal names
and cut-off answers showed on screen. A delivery window was only a fact, not on the agenda, and the design didn't say
otherwise.

**Impact:**
- Design 1 (the app's own calendar), 7.8 (when the walkthrough opens), 7.10 (headings), 6.7 and 7.7 (`event.add`,
  agenda).
- The roadmap gains the calendar entry (L0) and the kit's place (phase B).
- No new setting.

## 2026-10-13: Running from a checkout makes `cockpit` work in any folder

**Decided by:** project owner's report (`cockpit update` gave "command not found", then `uv run cockpit` in the workspace
folder couldn't find the app; "testing has just made a mess").

**What:** When `cockpit` runs from a source checkout on macOS or Linux, it links `cockpit` in uv's command folder (by
uv's own rules, usually `~/.local/bin`) to the checkout's own command, and says so once. An installed copy, or a link to
another checkout that still exists, is never replaced; a link to a removed checkout is. Windows is left for the
launcher (phase B).

**Why:** One command to start only helps when the command is found. From a checkout it worked only as `uv run cockpit`,
and only inside the checkout's folder, which a person can't be expected to remember.

**Impact:** The CLI, the README and the getting-started page. No setting.

## 2026-10-13: Three fixes from the exit test: an agent's own error, focus rings, a question handed in

**Decided by:** project owner's report ("claude code CLI isnt working, several places in the code put an outline around
things that clips into elements and i asked the AI a question and got a JSON error"; the question ran on the Copilot
account).

**What:**
- **An agent's own error is read and shown.**
  - What the code did: the Claude Code agent ran with only PATH, HOME and the language settings. It exits 1 and prints
    its reason in the JSON on its output, with nothing (or only a code) on its error stream. So the test said only "other:
    the agent stopped with exit code 1".
  - What changes:
    - The agent also sees the user name (`USER`, `LOGNAME`, `USERNAME`), which a system keychain files its sign-in
      under, and the user's `TMPDIR`.
    - An agent account can say it reports its errors on its output (`agent.errors.report_on_output`). Then, for a failed
      run only, that output is read as its error report, before the error stream. The Claude Code preset says so and
      lists its sign-in, plan-limit and rate-limit wording.
    - A failed test reads in plain words (what it means, the agent's own words, what to do), never an internal kind.
- **Focus rings never sit on text.** A row shows its ring only for keyboard focus, not after a click or when the
  screen moves focus. The ring is drawn inside the row's padding, or outside a row with none. A row title's button gets
  its ring outside, with room.
- **A question handed in as a note goes to Ask.** When the person's own note, with nothing pasted, is a question to the
  assistant, the notes run answers `"ask": true` with no ops. The same request then becomes an ask and is answered from
  the guide and the records. Pasted or outside material never does this. An answer that still isn't in the form asked
  for after the second round now says so in plain words, and the second round tells the assistant which op lacks its
  name.

**Why:** All three left the person stuck with words they can't act on, or with a screen that looked broken.

**Impact:**
- Design 6.16 (agent accounts), 6.25 (asking) and 7.10 (focus ring).
- One new agent setting, with a default (off) and a description.
- The notes prompt gains one line. No new op.

## 2026-10-13: One command to start: `cockpit` on its own

**Decided by:** project owner ("I will never remember all these command lines").

**What:** `cockpit` with nothing after it (also `cockpit start`) starts the person's workspace and opens it in the
browser. It uses the workspace named by `COCKPIT_WORKSPACE`, else the one started last on this computer (remembered in
the person's home folder), else a `Cockpit` folder in their home folder, made the first time, where the walkthrough
starts. It never writes into a folder that holds other files. `cockpit update` stays the one way to update a checkout.
`init` and `serve` remain for anyone who wants a workspace elsewhere.

**Why:** The exit test asked for one install or update command and no second command. Starting needed two commands and
a folder name to remember.

**Impact:** The CLI, the README, `docs/install.md`, `docs/getting-started.md` and the install scripts. No setting
changes. A launcher icon for people who never open a terminal is phase B.

## 2026-10-12: Pick, don't type; and a new workspace's defaults count as not chosen

**Decided by:** project owner ("nearly everything should have dropdowns, and time zone is a prime candidate"; "the name
field especially looks rough").

**What:**
- **Pick, don't type.** A field with a known set of values is a list to pick from. Settings name their list with
  `choices`; the time zone is the first, from the computer's own time zone list, in Settings and in the walkthrough.
  The rest of the screens are audited in phase B.
- **Found while checking the screenshot:**
  - **The cause:** the walkthrough offered the person's own time zone only while the setting was still at its default.
    `cockpit init` writes every default into the new workspace's files, so the step showed "UTC", and saving it would
    have put every date in UTC. The "Workspace" name had the same cause.
  - **The fix:** a value still equal to its built-in default now counts as not chosen, wherever it is kept. Your own
    name comes first, the workspace name is optional (a placeholder, not the word "Workspace"), and the step is done
    once you've named yourself.

**Impact:** Design 7.0. CLAUDE.md's UI rules. Phase B gains "Lists, not typing" and "The walkthrough's look".

## 2026-10-12: Personal and sales mail is set aside, and never feeds the assistant or its learning

**Decided by:** project owner ("recognize personal / sales emails and move them to a folder that won't impact
learning"), designed by the project lead after checking the code.

**What the code does today:**
- Triage rules close a change before the assistant sees it, under Auto-closed, with "Take a closer look".
- A mail item carries only its sender, received time and unread mark.
- Nothing knows personal or sales mail.
- Learning, from L-core on, has no rule to stay off it.

**What changes** (design 6.5, "Setting aside personal and sales mail"):
- **A Set aside folder in the app,** with Personal and Sales and promotions. The mailbox itself is never changed: the
  add-ons stay read-only.
- **Sorting order:**
  - the person's own sender and domain rules first;
  - then what the mail says about itself: the service's category, bulk headers, a personal contact;
  - then, for mail still unplaced, a low-cost sorting run that sees only sender, subject and category, never the body.
    Unsure means work.
- **Kept out entirely:** set-aside mail never reaches the assistant, and nothing learned comes from it.
- **Corrections tune sorting only,** with one-click "always for this sender or domain" rules.

**Why:** Personal mail is private and sales mail is noise. Learning from either would teach the assistant the wrong
things, and the first week of real use is the learning baseline.

**Impact:**
- Roadmap L0, before learning reads anything. Later the same day, the rules part (bulk and category matchers, the
  folder, one-click rules) moved to phase A5: the owner is getting social updates and sales mail processed now, and
  `category:primary` matched nothing in the owner's Gmail (its tabs exist only with the Default inbox type).
- Design 6.5, 6.20 and 7.4.
- A new setting, `watch.sorting` (ai or rules).
- New core matchers.
- Mail items gain `categories` and `bulk` (plugin API).
- The mail add-on's builder is told in the weekly batch.

## 2026-10-12: A new-start walkthrough: install to first result in one guided path

**Decided by:** project owner ("a new start user onboarding … easy install and setup"), designed by the project lead after
checking the code.

**What:** The setup guide exists, with seven steps plus each add-on's steps and sign-ins. It falls short in four ways:
- it doesn't open by itself;
- mail and calendar come last, and only for an add-on already installed;
- each step that needs a restart asks separately;
- no page covers the path from the install command.

The guide becomes a walkthrough (design 7.8):
- it opens by itself on a new workspace;
- its steps are You, AI account (with what it may see and spend), Mail and calendar (install, one restart, sign in),
  Backups, People (optional) and Done;
- it resumes after a restart and ends on Today's first-Go line;
- the template and other add-ons become optional extras;
- `docs/getting-started.md` covers the same path from the install command.

**Why:** The owner's goal is an easy install and setup. Phase A's exit test is exactly this path, so the walkthrough is
what the owner will run.

**Impact:**
- Design 7.8 is rewritten.
- Roadmap A4 is added before the exit test, about one session.
- A journey that goes only through the walkthrough becomes the automated exit test.
- No new op or setting. Setup state gains the walkthrough's current step.

## 2026-10-12: What the first journeys found on the person's path, and what changes before the exit test

**Decided by:** project lead, from the phase A journey tests on a workspace made by `cockpit init` and started by
`cockpit serve`.

**What:** The journeys ran the owner's exit-test path with a fake AI service. Four things stop or mislead a new person:
- **A new account may see only open material, but notes and mail are internal.**
  - The rule stays: a new account sees only open data until the person raises it (product rules, 8).
  - The dead end goes. The add-account screen says plainly that the person's notes, mail and meetings are internal, so
    the assistant can work on them only once Internal is ticked.
  - A run stopped because no account may see its material offers "Let <account> see internal material" as its one
    action, and runs again once the person chooses it.
- **Handing in before saying who you are spent money and then failed.** Without a person set for the workspace, a run
  now waits before any AI call, with "Say who you are first" and the setup step as its action.
- **Check now said "Nothing new" when a folder file had just been handed in.** Came in lists mail only; Check now's
  count now covers everything any source handed in.
- **A folder's first read hands nothing in.** That is kept (a folder may hold years of files), and the add-source form
  says so, pointing to "Look at the last day".

Also fixed: a setting given on the command line (`--port`) made any later change to a live setting wait for a restart.

**Why:** These are the joins unit tests miss: each piece worked, and the path didn't.

**Impact:** Design 6.16. No new setting or op. Phase A gains these fixes before its exit test. The account's suggested
name (the catalog id) and a key being required for a custom address are phase B screen work.

## 2026-10-12: The acceptance scenario's step 7 is built as written: a Today line and the age on the header chip

**Decided by:** project lead, while making the browser test check every step of the scenario as written.

**What:** The scenario says that with no off-device backup, Today and the header say so, and after one succeeds the header
shows its age. The code did less: Today never mentioned a backup, and the chip said only "Live" once one had succeeded
(the age was in its popover). Design 4.15 and the decision of 2026-10-09 ("a Today line and header mark until one
succeeds and the last backup's age always shown") already asked for both. Now:
- **Today** shows one row under the setup line while no backup is set up, none has succeeded, the last failed or the last is
  overdue, saying what to do first, with its button, and nothing once a backup is current.
- **The chip** keeps the backup's age beside its word ("Live · Backed up 3 h ago"); a phone shows the word only.

The same pass found two places where the scenario's wording and the design differ, and the design stands: Follow-ups is
two steps (Copy, then Mark sent, decisions 2026-10-10 "two steps"), so "Mark sent records it" is right and Copy alone
records nothing; and no screen lists facts yet (7.18's per-project knowledge is phase L-core), so step 5's "the fact is
gone" is checked on the record route the project page will read.

**Why:** A step that the product doesn't do can't pass "checked as written", and the nag that a backup is missing was
only in a chip that is easy to miss.

**Impact:** Design 7.1 and 7.7 and the wording sheet; no API, op or setting change.

## 2026-10-12: Phase A's design calls, after checking each item against the code

**Decided by:** project lead, at the start of phase A.

**What:** The code was checked item by item first. What it does today, and what phase A builds:
- **A crashed run stays stuck forever today:** the worker takes only queued requests, and nothing looks at ones left
  running. On start, each is queued again. One found stuck a second time waits for the person ("Stopped twice when the
  app closed during it"), so a request that crashes the app can't loop.
- **The test-only source kind is offered to people today.** A connector gains a test-only mark, and "Add a source" leaves
  such kinds out. Sources already set up keep working.
- **The mailbox refresh:** a "Check now" button on Came in reads every enabled source at once and shows what arrived. A
  source is never read twice at the same moment. Today the source's "Read now" and the schedule can overlap; a lock per
  source now prevents that.
- **The Install button:** the install route exists; the screen has no button. Install appears on a listed add-on whose
  release this app can install. Remove appears in the menu of one the app installed, once it is off. A new install
  offers Restart now, as turning one on does. Only updating an add-on that is running holds new work until then, so
  old and new files never mix; installing or removing one that isn't running changes nothing the app uses.
- **The first run's cost is one Go:** until the person's first go in a workspace, AI runs wait. Today then shows one
  line: how many items, and the total estimate. One Go starts them all; after that the usual confirm amount applies. A
  new setting, `ai.budgets.first_go` (on), turns this off. Only showing the estimate after the money is spent wouldn't
  let the person expect the cost.
- **Local mode's guards:** the allowed `Host` is the configured address, `localhost`, `127.0.0.1` or `[::1]`, each with
  the configured port; in hosted mode it is the public address. A state-changing request is refused when its `Origin`
  is another site, or when the browser marks it cross-site. A request with no `Origin` (not from a browser) still
  needs the token. Local mode refuses to start on a non-loopback address.
- **The wording check:** text fields the screen shows are typed as screen text in the API's models. In tests and in
  development, sending one that names a settings file, a secret reference, a real settings key, a manifest field or a
  command is refused, and so is an error message that does. Terminal output may name commands; the screen may not.
- **`cockpit update`:**
  - **in a git checkout:** a fast-forward pull, `uv sync --inexact` so installed add-ons stay, then the web tools and
    the build. It ends by saying what changed and that a running app shows Restart now. It refuses when there are
    local changes.
  - **in a packaged install:** it names the install step instead.
- **A whole backup can be restored:** a backup that can't be loaded back isn't one, and the phase A journey "backup →
  restore" had nothing to call. `cockpit restore --backup <backup folder> <new folder>` makes a workspace from one
  dated backup:
  - it checks the database first;
  - it never writes into a folder that has files;
  - it never touches the running workspace.

  Restoring to a point in time (phase E) and one record (L-more) stay where they are.
- **A fresh workspace is checked:** the self-check makes one with no template and verifies that no account, source,
  setting or data file shows a problem.

**Why:** Each was verified in the code before it was designed around. Three gaps were worse than the plan said: a stuck
run never recovers, the test source is offered, and backups had no restore.

**Impact:**
- **Design:** 5.0 (whole-backup restore), 6.13 (re-queue on start), 7.8 (the first Go), 4.x (`ai.budgets.first_go`), and
  12.1 (the allowed hosts and origins).
- **Roadmap:** A1 gains the restore. Scope grows by one small command.

## 2026-10-12: What the add-ons already built, against what the core will add

**Decided by:** project lead, after a read-only survey of both add-on repositories against the core's plan.

**What:** Very little plugin code becomes redundant. The survey mostly found what the core must add so packs fit:
- **`learning: own` for pack material.** A novel's facts are fiction and its invented names aren't acronyms, so the core's
  input learning, new-term scan, first-name resolution and fact ranking stay off it. One correction yields either a pack
  record or a core lesson, never both.
- **Pack evaluation.** Packs bring their own cases in the core's format and register only domain scorers. The generic ones
  are the core's exact matching.
- **Connector items that carry files,** so mail attachments go to the core's extractors.
- **A default data level per connector,** and the received date from an item's received time, not its last-changed time.

The writing pack is told not to build the generic scorers, web search or its research list, and to wait for the knowledge
section in the guide. The mail add-on has nothing redundant.

**Why:** The core's learning loop would otherwise learn fiction as fact, propose a glossary entry for every invented name,
and propose a second lesson for a correction the pack already recorded.

**Impact:**
- Design 6.22 and 3.3 are updated, and roadmap L0, L-core L2, L4 and L5 gain items.
- Two notes go to the builders: the writing pack now, as a heads-up; the mail add-on in the weekly batch.

## 2026-10-12: Four more items leave phase A, each to where it is first needed

**Decided by:** project lead, at the owner's request ("use your best judgement").

**What:**
- A pack's own libraries move to C1, where the writing pack needs them. They are answered with plugin question 183.
- Mailbox and calendar passwords on screen move to B. The owner signs in to a named service, so these are for people
  using the core's own mail and calendar sources.
- The screen for a divergence between two computers moves to L0, because real use may span two computers.
- The scheduled export moves to L0, because knowledge starts accumulating there.

**Why:** None is needed for phase A's exit test.

**Impact:** Phase A is about 2.5 sessions and L-core about 11.5.

## 2026-10-12: Nothing lives only in the conversation; "Built" cites a test; wording checked at the response boundary; the first run shows its cost

**Decided by:** the first design's author proposed (review of the project review); project lead adopted it and set up the
hook.

**What:**
- **Commitments are written down in the same turn,** to the roadmap or `docs/project/open-promises.md`. A project hook in
  `.claude/settings.json` shows the list when a session starts, resumes or comes back from a compaction, and reminds the
  session before one.
- **"Built" cites a test.** A "Built" row or a checked roadmap box cites its test, and the self-check fails on one that
  doesn't exist (L0).
- **Wording at the boundary.** The screen-wording rule is enforced at the API's response serializer in tests and dev mode
  (A2).
- **The first run after setup shows its estimate,** even below the confirm amount (A2).
- **The project review is corrected.** Its recommended order is marked superseded by the roadmap, and its design-text
  list is checked off.

**Why:** The review's remedies reduced the load but caught no lost promise; this session itself had been compacted. Four
items were claimed done and weren't, and a fifth was found later. A static scan misses messages built at runtime. And the
new defaults spend money on their own, on day one.

**Impact:**
- `CLAUDE.md`, `review-2026-10-12.md`, design 7.8 and 10.5, and the roadmap (A2, L0) are updated.
- New: `docs/project/open-promises.md` and `.claude/settings.json` with `.claude/hooks/open-promises.sh`.

## 2026-10-12: The data model review: forgetting by recorded redaction, distinct knowledge states, missing fields

**Decided by:** the first design's author proposed (review of Part 5); project lead checked the record definitions in the
code and chose between his two options for forgetting.

**What:**
- **Forgetting is a recorded redaction** (option b). A `person.forget` op replaces the person's values everywhere, the
  ledger's before-and-after values included, with a marker, and records that it did. The export's local git repository
  is rebuilt from the database, the one rewrite allowed. A remote (phase E) is replaced the same way. Older backups hold
  the old data until they age out, which the screen says.
- **Crypto-shredding was set aside:** it would put every read and write of a person's values through encryption, for a
  rare operation.
- **Evidence survives retention:** quotes are kept with their ops.
- **Knowledge records gain** `origin`, their own `text` apart from the evidence, `kept_by` and `kept_at`, and the
  distinct states `discarded` (with a reason; it suppresses), `expired` (counted; it doesn't suppress) and `retired`. Seed
  lessons gain `guard_kind` and `fixture_ids`.
- **Other fields:**
  - `project.priority` is person-only;
  - actions gain `followed_up`, `done_by` and `reported_by`;
  - sources and files gain `data_level` (today it lives only on the request);
  - signals gain `run` and `changeset`;
  - questions gain `held_for`;
  - `person.verified` comes in L-core.
- **Value-list values** gain a tone, and status values a meaning.
- **Stale text in Part 5 is corrected:** the off-site claim, "applied fix", the scheduler lease, backup encryption, shared
  folders.

**Why:** Each was a contradiction with an agreed rule, or a field another part depends on. Without a forget rule, three
statements in the design couldn't all be true.

**Impact:**
- Design 5.0, 5.1, 5.2, 5.4, 7.18 and 12.4 are updated.
- Roadmap: L0, L-core, B and E gain items, inside their estimates.

## 2026-10-12: The workplace pack review: what the running use needed, and its demo built early as the busy fixture

**Decided by:** the first design's author proposed (review of 9.1 to 9.5); project lead adopted it.

**What:** A new design section, 9.5a, records the twelve things the running workplace use needed:
- roles, as routing templates;
- two kinds of dates by owner, with private discrepancies;
- a status rubric as data;
- leader-owned fields and the baseline state;
- the project page sections, with key players and why they matter;
- the first-week baseline flow, as its own task kind;
- key-player exploration;
- a preview through the dashboard's own reader;
- the weekly check-up's rules;
- the domain lens;
- release over sprint;
- pages a group edits.

The fictional workplace workspace (`demo-a`) grows into a busy portfolio in L-core, as the golden set's busy fixture, and
later becomes the pack's demo. A reader-preview hook is noted beside the renderer extension point.

**Why:** 9.1 to 9.5 were too thin to be the proof that the core is complete. Most of what made the running version work
moved into the core; what's left is what only a workplace PM needs. The busy fixture costs nothing extra this way, and makes
the evaluation honest sooner.

**Impact:** Design 9.5a (new) and 3.3 are updated; roadmap L4 names the fixture. The pack itself stays off the roadmap to
1.0.

## 2026-10-12: Phase A re-sized to its exit test; the reviews' daily-use items move to L0

**Decided by:** project lead, asked to re-size phase A with its exit test unchanged.

**What:** Phase A keeps only what its exit test needs. The local-mode guards stay too, because the exit test is the first
time the owner's real mail is in the app. These items move to L0, the start of L-core, which still comes before real use:
- the silent-stop fixes and their journey tests;
- waking from sleep;
- the received date;
- first names in context, and their golden-set cases;
- the near-duplicate threshold;
- Followed up;
- the audit records for sign-ins and plugins;
- the shared-folder setting;
- the 6.8 to 6.11 audit.

**Why:** The reviews of sections 15 to 19 added about a dozen items to phase A, growing it from about 3 to 5.5 sessions.
Most protect daily use, which starts after L-core, not the exit test.

**Impact:** Phase A is about 3.5 sessions, and L-core about 11 with L0 (about 2). The total is unchanged. Design references
to "phase A" for the moved items now say L0.

## 2026-10-12: The security review: learning's new roads to trusted guidance, and local mode against other web pages

**Decided by:** the first design's author proposed (review of Part 12); project lead checked the code and placed the work.

**What:**
- **Keep authors the wording.** Keep makes the person the author of the assistant's restatement shown at Keep. The raw
  source text enters packets only as evidence marked "from outside".
- **Bulk Keep is limited** to glossary terms and facts with evidence. Routing, rules and lessons are kept one at a time.
- **Imported lessons load as proposed,** unless they are the person's own signed export.
- **A pack's guidance** is shown before it is turned on and marked by origin. Precedence: invariants, then the person's
  rules, then pack guidance.
- **Local mode:**
  - refuses a foreign `Host` and state-changing requests from a foreign `Origin` (the cookie is already strict, and there
    are no CORS headers);
  - refuses to start on a non-loopback address.
- **A shared synced folder's edits are content** (`storage.sync.shared`).
- **Audit:** sign-ins and turning plugins on or off are recorded from phase A.
- **The export remote** waits for phase E, with the care of backups.
- **Forget and export a person** reach knowledge records and private evaluation cases.
- **New hostile fixture cases:** a planted lesson, routing, a glossary meaning, and an injected import.

**Why:** Once the assistant learns, guidance in a packet is the most valuable thing to poison. The local-mode gaps are
reachable today by any page open in the same browser.

**Impact:**
- Design 12.1, 12.4, the new 12.8, 6.22, 7.18, 4.15 and 3.6 are updated.
- Phase A gains the local-mode guards, the audit records and the shared-folder setting (about half a session, so about
  5.5).
- L-core and L-more gain items within their estimates.

## 2026-10-12: The UI review: learning made visible, Followed up, Later, This week everywhere, notifications

**Decided by:** the first design's author proposed (review of Part 7); project lead checked the screens and wording and
placed the work.

**What:**
- **Learning made visible** (phase L-core, because the loop isn't trusted without it):
  - the knowledge an output applied is shown on its evidence line, with "This doesn't apply here" to narrow or retire it;
  - "Keep for: this project ▾" on the Learned line, defaulting to the narrowest target;
  - a Review line for proposals from silent corrections.
- **Use counts** on knowledge rows (phase B).
- **"Followed up"** on Waiting on them (phase A). It is designed in 6.9 but missing from the screen, where the only button
  closes the action.
- **Follow-ups' Later group** for questions held for a meeting or a weekly note; the question's `batch` field already
  exists (phase B).
- **This week at every width** (phase B).
- **Opt-in notifications** for the Decide group only, with quiet hours (phase B). Update after the author's follow-up: a
  notification target is a channel (the browser, mail to the person themselves, or a webhook for a chat app or push topic),
  tested with "Send me a test", so a phone gets them anywhere from day one, with no hosted mode. Targets send only to the
  person and carry a count by default; titles go only to targets allowed for the data level.
- **Small fixes:**
  - format-only differences never appear in Waiting to go out;
  - restart and pause lines stay on Today even when the status chip shows them;
  - the Add-ons introduction is fixed with the Install button.

**Why:** Showing which lesson shaped an output, and letting the person narrow it there, is the fastest cure for
over-application, the running version's worst learning failure. Without "Followed up", chasing someone closes their action.

**Impact:**
- Design 7.4, 7.5, 7.7, 7.18 and the new 7.19, plus 4.11, are updated.
- Roadmap: A, L-core and B gain items, inside their estimates except L-core's screen work (about half a session).

## 2026-10-12: The golden set is made harder before it chooses a model

**Decided by:** the first design's author proposed (review of the golden set); project lead checked the harness and placed
the work.

**What:**
- **Every case gets `received:`.** The harness already freezes one clock for all cases; this tests the phase A
  received-date fix.
- **`exact: true` by default.** No ops beyond the expected ones, except notes and sources.
- **`given:` starting records.** `quoted-thread` is split in two.
- **A busy workspace.** Half the cases run against 30 to 50 open items with near-namesakes.
- **Forbids that last.** Hostile cases forbid every system-tier op and any op naming the injected person.
- **About 16 new single-input cases** from failures the running version had. The cases for phase A's fixes (received date,
  first names in context, an unknown person) are written in phase A as their failing tests; the rest come in L-core.
- **A real-model report.** Pass rate per case and model, three runs each, made on the owner's accounts before real use
  starts.

**Why:** The model choice is made on this set. As scored today, a low-cost model can look as good as a strong one, because
extra ops aren't penalized and the workspace has almost no wrong candidates. Over-extraction was the running version's most
frequent real failure.

**Impact:**
- Design 6.16 is updated.
- Roadmap: phase A gains its cases; phase L-core's L4 gains the harder set and the report, adding about 1 session.
- No evaluation report on a real model exists yet. Only the stand-in runs the set, in the self-check.

## 2026-10-12: The plan review: L split into L-core and L-more, real use after L-core, stronger proof

**Decided by:** the first design's author proposed (review of the roadmap and Part 13). Project owner chose when real use
starts (after L-core; he had suggested after phase A) and placed L-more after the packs. Project lead adopted the rest.

**What:**
- **Phase L splits.**
  - **L-core:** the loop itself, extractors, backup encryption and the writer's first-week rules. It ends on "the assistant
    doesn't repeat a corrected mistake", and the owner's real use starts then.
  - **L-more,** after the packs: Ask's knowledge and learning from Ask, Take my lessons, Part 8 as seed lessons, agent
    versions, early probation, the unused list and single-record restore.
- **Proof.** 15 to 20 fixture pairs, about a third negative (over-application, another project, the world changed, a
  discard, injection), from the author's generic cases. The day-30 scenario's expected differences are written before it
  runs, scored like the golden set, and the history mixes the cases with ordinary noise.
- **The weekly review.** The first week of real use is the baseline. A task kind's week counts only with at least 10
  corrections.
- **Phase A.** Journey tests for each silent stop and for waking from sleep. The scheduled export is wired, not removed, so
  a readable copy is written as knowledge accumulates.
- **Phase C** also proves that packs learn.
- **13.4** no longer repeats the roadmap's contents, so the two can't drift; milestone 2's stale lines are marked as moved.

**Why:**
- Phase L had grown to about 11.5 sessions, and much of it isn't needed for the loop to work.
- Five pairs can pass by luck, and a loop that over-learns does harm: the author's worst learning failure was a rule for
  risks applied to action owners.
- Waking from sleep was where most "it just stopped" reports came from.
- Without a learning test in phase C, the core could learn while the packs don't.

**Impact:**
- `roadmap-to-1.0.md` is restructured. Sizes: A about 5 sessions, L-core about 8, L-more about 4. The packs start about
  3 sessions sooner than in the previous plan.
- Design 13.1, 13.4, 6.22, 6.16, 6.25, 5.0, 7.18, Part 8 and 4.25 are updated.

## 2026-10-12: The engine review: no frozen batch prefix, trusted answers only, facts that replace facts, no silent stops

**Decided by:** the first design's author proposed (review of Part 6); project lead checked each point against the code and
placed the work.

**What:**
- **The batch prefix is not frozen.** Each packet is built from the current state, as the code already does, so an input
  sees what earlier inputs in the batch created. The knowledge section splits so the cached prefix holds:
  - stable: all rules, lessons targeted at the task kind, and a small glossary;
  - per input: everything else.
  A `near-duplicate-question` lint is added.
- **Only the PM's own answer counts as the PM's words.** A pasted reply is content; the code already hands it in as pasted
  content. A held op the PM's answer releases counts as the PM's own.
- **Facts carry `supersedes`;** superseded facts leave the packet. Ask gets the knowledge section. Discarded proposals are
  remembered and not shown again for 90 days.
- **Direct edits.** Learning from one sees the inputs that came after the original run, and defaults to "nothing to
  generalize". The learning backlog arrives as one catch-up list.
- **First names.** A bare first name resolves only in context (same project, or a participant in the thread); the code
  resolves any unique first name today.
- **No silent stops.**
  - Held work shows as the first Decide line ("Restart to run N waiting requests").
  - A paused account shows as a Risk line.
  - An agent that exits 0 with no answer is `no_output`, retried.
- **Agent versions.** An agent's program version is part of the account: recorded on each run, a change treated like a
  switch, and auto-update turned off where possible.
- **Probation** can be ended early.
- **Audit.** Design 6.8 to 6.11 is audited against the code at the end of phase A.

**Why:** Each point is a way the engine would fail in daily use. Some were seen in the first version: a question filed twice
in one batch, a pasted reply gaining the PM's authority, a moved date read as current, a wrong person from a shared first
name, an assistant that stopped without anyone noticing.

**Impact:**
- Design 6.6, 6.8, 6.11, 6.14, 6.15, 6.16, 6.21, 6.22, 6.25, 4.8, 4.17, 4.25 and 5.1 are updated.
- Phase A grows to about 4.5 sessions and phase L to about 11.5.

## 2026-10-12: Product rules are the core playbook's seed lessons, with guard kinds; the first-use rules come first

**Decided by:** the first design's author proposed (review of Part 8); project lead adopted it and placed the work (the
owner had already put real use at the end of phase L, so the rules that bite in its first week land before then).

**What:**
- **Rules as data.** Part 8's rules become the core playbook's seed lessons: lesson records shipped with the product, in
  packets like the person's own, and pointed at by fixtures. Part 8 is generated from them.
- **Guard kinds.** Each guard is tagged invariant, lint, code or instruction. An instruction-only rule needs a fixture case,
  and counts as partly enforced until it has one.
- **8.7 split.** Its process rows move to 10.5.
- **New rules.** Fifteen rules from the running deployment become rows in 8.8.
- **Two wording fixes.** A target is a date, a quarter or TBD, never a sentence. Dates count from the day received.
- **Order.**
  - Phase A gains the silent-stop fixes: the received date in the packet header, a usage limit resuming at its reset, and
    an empty or failed run retried automatically.
  - Phase L gains the conversion, plus the writer's first-week rules: verbatim versus paraphrase, attribution, names from a
    primary source, and links checked before they are shown.

**Why:** Part 8 and 6.22 described two stores of the same knowledge. An advisory rule that reads as enforced was the
original scope failure. The first real use is a writer's own work plus mail and calendar, so those rules bite first.

**Update (same day, the author's follow-up):**
- **Constraint lines.** Seed lessons guarded by an invariant or code still put a one-line constraint in the reference of the
  ops they constrain. The self-check fails when an invariant has none.
- **Refusals per check.** Refusals are counted per check on each run. A check that refuses more than 5% of a task kind's
  last 50 runs brings its full seed lesson into that task kind's packets until the rate drops.

**Impact:**
- Design Part 8 (intro, 8.1, 8.5, 8.7 and a new 8.8) and 10.5 are updated.
- Phase A grows to about 3.5 sessions and phase L to about 10, so the packs start about one more week later.

## 2026-10-12: Fallbacks are switches, direct edits are corrections, and real use starts after phase L

**Decided by:** the first design's author proposed; project lead adopted points 1 and 2 and the two numbers; project owner
chose when real use starts.

**What:**
- **Fallbacks are switches.** Only accounts that passed the learning check, or that the person accepted unchecked, may sit
  in a fallback chain. The first run on a fallback account is tagged on its cards.
- **Direct edits are corrections.** A person's own edit of a field the assistant set is an `edited` signal, learned from in
  the 30-minute batch. The ledger shows who set each field.
- **Two numbers.**
  - The repeat-correction rate, which should fall.
  - The knowledge-used rate, which should rise: changesets list the knowledge ids they applied (`applied`), checked against
    the run's knowledge log.
- **Real use early.** The owner's daily use starts at the end of phase L and runs beside phases B and C. The two numbers are
  reviewed weekly for the first month, and a loop that isn't closing is fixed before more pack work. Phase D becomes the
  sign-off once the packs are in.

**Why:** A fallback is a model change nobody chose at that moment; in the first version, two batches ran on the wrong provider
unnoticed. A direct edit is often the clearest correction, with no note. Fixtures prove the plumbing, and only real material
shows the loop working.

**Impact:**
- Design 6.16, 6.20, 6.22 and 5.1 are updated.
- Roadmap: phase L gains three items (in its size estimate); real use moves from phase D to the end of L; phase D's exit
  test adds the falling rate.

## 2026-10-12: Learning-slice refinements: learn while the person is there, stronger guards, and protect what is learned

**Decided by:** the first design's author proposed; project lead adopted points 1 to 6 and 8; project owner placed point 7
in phase L.

**What:**
1. **When learning runs.** A correction where the person wrote something (a send-back note, an answer to the assistant, a
   rule stated in Ask) is learned from at once, and the Learned line appears on that card. Silent corrections are batched.
2. **Which tier writes it.** Lessons, lesson updates and rules come from `learn-correction` on the stronger tier, and so does
   anything after a repeat correction. Terms, routing and facts proposed from inputs use the input's own tier.
3. **Checking on a switch.** A switch of a tier's account or model offers the learning fixture pairs with their cost
   ("Switch and check"), as part of probation. A failed check shows on Today with Switch back.
4. **Brought forward.** Facts in the packet carry their date and source, and a rules-only scan finds terms missing from the
   glossary before each input's run.
5. **No flooding.** Proposals from inputs come as one card a day, merged first, and expire after 14 days with the count
   shown. Proposals from corrections keep their own card.
6. **Learning from Ask.** Rules and facts stated in Ask become proposals that apply at once, with Undo.
7. **Placed in phase L by the owner.** Text extractors for documents, spreadsheets, presentations and PDFs; encryption for
   backups that leave the person's control; showing and restoring one record as it was.
8. **Knowledge travels.** It is in the export like every record. "Take my lessons" carries lessons, rules and general
   glossary terms to another workspace; facts, routing and style notes stay behind.

**Why:** Learning written down in the same turn as the correction sticks; half an hour later it is a chore. A bad lesson is
in every later packet, so the guards get the stronger model. A model switch is when learning can be lost silently. An
assistant can't learn from attachments it can't read, and once it learns, the knowledge is what can't be rebuilt. A flooded
review queue gets discarded wholesale, which kills the loop quietly.

**Impact:**
- Design 6.22, 6.2, 6.16, 6.25, 4.15, 4.25, 5.0, 3.3 and 7.18 are updated.
- Phase L grows from about 6 to about 8.5 sessions, so the packs start about one more week later.
- `scope.md`: extractors, encrypted backups and restoring one record become version-1 musts in phase L.
- Phase E keeps point-in-time restore.

## 2026-10-12: The learning slice: the assistant gets better at each project, and is built next after the baseline

**Decided by:** project owner (the placement: after phase A, before the UI); proposed by the first design's author in his
review of design 1.1; project lead (the adjustments below).

**What:** A new roadmap phase L, between A (baseline) and B (UI), builds the read side of learning (design 6.22):
- **knowledge records:** lessons, glossary entries, routing entries and style notes, each with an id, source and evidence,
  date, trust, status and an `applies_to` target; rules become records too;
- **the knowledge section** in every packet, with the project's facts ranked and cut at a budget;
- **a search round** before asking anyone, and the `already-known` lint;
- **a knowledge log** on each run;
- **one learning proposal** from every correction and from inputs;
- **the repeat-correction signal;**
- **fixture pairs and a day-30 scenario** in the evaluation.

Exit test: the assistant doesn't repeat a corrected mistake.

**Adjustments to the author's proposal:**
- **Search is a round the engine runs** and feeds back, not a live tool call, so it works on every kind of account.
- **"Search before asking" is a lint,** because matching is fuzzy.
- **Rules become records,** like value lists: history, Undo, no restart, and they travel with the workspace's data.
  `rules.yaml` stays as the starting set.
- **A lesson whose guard needs new code** becomes a report to the maintainers, since the product never changes its own code.
- **The model-behavior evaluations** run on the person's own accounts, when they start them. The plumbing is tested on
  every change.
- **Learning runs** have their own task kind on the low-cost tier, with a budget, and are batched by default.

**Why:** The write side of learning is built (sources, facts with evidence, corrections recorded as signals), but no later
run reads what was learned. The assistant would be as smart on day 100 as on day 1, and a person would feel that within two
weeks. A test workspace with fictional data never shows it, because nothing accumulates. In the first version, this loop was
what made the assistant worth using.

**Impact:**
- Design 6.22 is rewritten; 1.7, 4.3, 4.10, 4.17, 5.1, 6.6, 6.19, 6.20, 6.21, 7.17 and Part 8 are updated; 4.25 and 7.18 are
  added.
- `roadmap-to-1.0.md` gains phase L (about 6 sessions), and the packs start about two weeks later.
- `scope.md`: the learning loop becomes a version-1 must.
- `CLAUDE.md`: standing rules are rule records.
- Plugin API: one call for a pack's packets to include the knowledge section.

## 2026-10-12: A project management pack: an AI project manager that builds schedules and tracks the work

**Decided by:** project owner ("an AI project manager will know what we are doing, build schedules, track action items").

**What:** A new private pack, built in phase C before the publishing pack.
- **The core keeps** what every kind of work needs: actions, questions, follow-ups, decisions and Today.
- **The pack adds** planning:
  - the plan (goals, phases, deliverables, milestones);
  - the schedule (durations, dependencies, critical path, baselines and slips; only the person rebaselines);
  - plans and schedules drafted by the assistant for the person to approve;
  - daily at-risk lines on Today and a weekly status report to send;
  - RAID;
  - an interface (`pm/schedule@1`) through which the writing and publishing packs put their milestones into one
    schedule.

  Each pack still works alone.
- **This is distinct from the workplace pack** (design Part 9.1–9.5), which is about wiki pages and trackers at a
  workplace.

**Why:** the owner's plan is to run the book and the launch with an AI project manager. Schedules and their follow-up
belong to that kind of work rather than to every use of the core.

**Impact:** design 6.23 (dependencies and baselines) and 6.24 (RAID and its reviews) move from the core to this pack;
`scope.md` lists them as an add-on rather than a core must. Phase C of the roadmap grows by about three sessions. The
publishing pack's launch plan uses the pack's schedule when both are on.

## 2026-10-12: The go-forward plan: a working baseline, then the UI, then the packs

**Decided by:** project owner ("we need the baseline done and working so we can get the publishing and writing packs
working"; the UI/UX finalization near the top; the demo data "just makes things confusing").

**What:** The roadmap is rewritten as phases, each ending on an exit test the owner can run:
- **A:** a baseline that works with no demo data.
- **B:** the UI/UX redesign finished.
- **C:** the writing pack installed and reviewed, the publishing pack started and built, and what both need from the
  core (the publisher, the file channel, fact lookups).
- **D:** owner validation and real use.
- **E:** the rest of version 1.

The fictional workspaces leave the person's path. CLAUDE.md gains the rules from the review (one stream at a time,
defaults that produce a result, journey tests before "ready to test", fixing the cause and its siblings).

**Why:** the review of 2026-10-12. Small errors reached the owner because the try-it path ran on test fixtures, safe
defaults together produced nothing, no test followed the person's journey, and too many streams ran at once. The
owner has seen neither pack working: the writing pack loads on the current host but can't be installed from the
screen (it needs its own libraries), and the publishing pack was never started.

**Impact:** `docs/project/roadmap-to-1.0.md` replaced. The 2026-10-30 go/no-go and the November freeze in
`schedule.md` no longer hold; phase D's dates are set by the owner. Feature work on version-1 extras waits for phases A
to C.

## 2026-10-12: Signing in is the whole setup for mail and calendar

**Decided by:** project owner ("it needs to just set up properly; the user shouldn't have to jump through hoops").

**What:** A sign-in starts the sources its add-on declares (the inbox, the main calendar) as soon as the person signs
in, once, and only where nothing reads with that connector yet. An add-on's mail source with nothing chosen reads the
inbox. The person narrows what is read later; their changes and removals stand.

**Why:** After signing in, nothing showed up: the mail source waited for a label to be chosen and no calendar source
existed.

**Impact:** Plugin API 0.3.54 (`sign_in(..., sources=...)`); the mail and calendar add-ons declare their defaults and
read the inbox when nothing is chosen. Sign-ins made earlier get their sources at the next start.

## 2026-10-11: The UI redesign: a full-width shell, Today as a ranked queue with a detail pane and a context rail

**Decided by:** project owner (handed over the UI/UX review in `reviews/ui-ux-2026-10/` to be carried out in full).

**What:**
- **Today** is a ranked queue (Needs you) in the widest pane, an inspector for the selected line from 1680px, and a
  context rail (Agenda, Your to-dos, Came in) sized to its content. This replaces both the single-column queue of the
  first design and the four equal columns of "Today as a dashboard" (below): the dashboard's goal (nothing hidden below
  the fold on a laptop) stands; the queue gets the width and the informational panels stay visible in the rail. Held
  items and decisions are always top-level lines.
- **The shell:** a left sidebar (Today; Work; Records; then Sources, Add-ons, Settings) with real links, a one-row 56px
  header with a status chip, no footer and no banners; a bottom bar on phones. Plugins add sidebar entries only under
  Work or Records (the navigation budget).
- **The screen is used in full:** panes are added as the window grows (7.13); only prose is limited to 72ch.
- **A visual system** (7.12) from the review's tokens, with shared components, a style guide, stylelint and screen-space
  checks; settings as nav | form | help; record pages as activity | details; forms in drawers; the title rule (7.14).
- New settings: `ui.brand.color`, `ui.brand.logo`, `ui.theme` and `ui.density`.

**Why:** the review measured 39–66% of wide screens left empty, about 230px of chrome above the work, the queue in a
quarter-width scroll box, decisions four levels deep, rows titled "Hi team,", ids on record pages and no visual system.

**Impact:** Design 7.0, 7.1, 7.3, 7.5, 7.7–7.11 rewritten and 7.12–7.14 added; `prototypes/today.html` replaced; 3.3
and 10.2 note the navigation budget and the new checks. The web client is rebuilt in the review's order (foundation,
shell, Today, records, settings, then Waiting to go out, the Stages board and the phone review mode). The engine gains the
title rule. No change to the ops, the API's meaning or the plugin API; a panel's `tab` maps to the sidebar group.
Deviations from the review are listed in the hand-off and below as they arise.

## 2026-10-11: One-click install for add-ons comes before the freeze

**Decided by:** project owner (the package-file step "is a pain"; move the add-on part of M0 forward).

**What:** The Add-ons screen gets an Install button. The catalog entry says where the pack's release file is and its
checksum; the app downloads it, checks the checksum, installs it beside itself, and offers Turn on (with the usual
restart ask). A private pack's release host takes a read token the person gives once, kept as a secret reference.
Update and Remove work the same way. Only packs of pure Python whose needs the app already has are installed this way.
The rest of the desktop installer stays in M0 after launch.

**Why:** Installing an add-on meant downloading a build artifact and running a command in a terminal.

**Impact:** the packs catalog format gains `release` (address and checksum) and the catalog repository follows; a new
setting for release hosts' read tokens; `POST /api/packs/{id}/install`, `/remove`; the roadmap's M0 loses the add-on
part. Built before 2026-10-30; no change to the launch scope otherwise.

## 2026-10-11: People install with no manual setup: a desktop installer, first thing after launch

**Decided by:** project owner (a desktop installer, "right after launch"; asked that a deployment needing no manual
setup be in the plan).

**What:** Version 1 starts with M0: signed installers for macOS and Windows that carry everything the app needs, run
it in the background, open the setup guide on first run and update themselves; add-ons install with one click from
the Add-ons screen. A hosted website stays after 1.0. The freeze before the 2026-12-01 launch stays fixes only.

**Why:** Installing today needs a terminal, uv and an install script, and installing an add-on means a command too;
people the owner shares it with should only download and double-click.

**Impact:** `docs/project/roadmap-to-1.0.md` (M0 in section 5); design Part 11 gains the desktop install and updates
when M0 is designed; the packs catalog format gains where a pack's release is and how it is checked. Costs for the
owner: signing certificates and release hosting. No change to the launch scope.

## 2026-10-11: Signing in needs no app registration from the person

**Decided by:** project owner (both ways: the add-on's own registration by default, and the person's own pasted on
screen; registering with a service "shouldn't be cumbersome").

**What:** A sign-in can come with the add-on's own app registration, so the person only signs in. A person who wants
their own pastes it on the Sign-ins row, beside a numbered list of steps with links that the add-on supplies; no
settings file or environment variable to edit. The workspace's references still win, and a hosted app uses them. A
pasted registration can be set aside and brought back.

**Why:** Services offer no way to script making an app registration for a personal account, so asking every person
to make one in a developer console was the hardest step of setting up an add-on.

**Impact:** `registrar.sign_in(default_client_id, default_client_secret, default_app_note, own_app_steps)`;
`POST /api/sign-ins/{name}/app`, `.../app/set-aside`, `.../app/bring-back`; `SignInView.app`, `app_note`,
`can_paste`, `needs_secret`, `set_aside`, `own_app_steps`. Plugin API 0.3.47. No change to scope.

## 2026-10-11: Command-line agents are chosen from a list, and accounts can be fixed after adding

**Decided by:** project owner ("we should have built in Anthropic CLI and Copilot CLI options … as there is no reason why
we need the user to set this up by hand"; an account saved by mistake "you can never fix").

**What:** The Add account screen offers the common command-line agents by name (`catalog/ai-endpoints.yaml`), each with
its command, the program's own options that keep its tools off, how it takes the packet and where its answer is. The
screen says whether the program is installed and how to sign in; the person never types a command. An agent that only
takes the packet on its command line gets it as an argument, refused above a size limit. Added accounts are listed with
Replace key, Change models and Remove (with Undo). The template step counts as done when the workspace already has a
starting template's item types, and each template lists what it adds before it is applied.

**Why:** Typing an agent's locked-down command by hand is error-prone, a mistaken account blocked adding it again, and
the template step gave no way to know what it would do.

**Impact:** `catalog/ai-endpoints.yaml` (data, not code); `agent.packet_via: argument` and `{prompt}`; `GET /ai/accounts`,
`POST /ai/accounts/{name}`, `POST /ai/accounts/{name}/remove`; `EndpointView.program`, `installed`, `model_examples`,
`model_optional`; `TemplateView.adds` and `set_up`. No change to scope.

## 2026-10-11: The app restarts only when it must, and only when the person says so

**Decided by:** project owner ("only restart when it's necessary and then warn the user before that happens").

**What:** Settings that everything reads at the moment of use apply at once, with no restart: AI accounts, tiers and
budgets, who the person is, the workspace's and assistant's names, the screens' wording and shortcuts, and the
accounts counted as ours. When saved settings (or the app's code) change in a way that needs a restart, the app says
so, holds new AI work, and waits: the person chooses "Restart now" or "Later". The app never restarts on its own. A
copy that can't start itself again says to close and start it.

**Why:** Adding an AI account restarted the app mid-setup, and the restart itself could fail (the web server raised
the stop signal again after shutting down, ending the process). A restart nobody asked for loses the person's place.

**Impact:** `engine/worker.py` (`LIVE_KEYS`, `apply_live`, `request_restart`); `POST /api/restart`;
`SettingsSaved.needs_restart` and `TemplateApplied.needs_restart` replace `restarts`; `status.can_restart`; the
settings screens ask before restarting. The serve command stops the server without a signal.

## 2026-10-11: Publishing a pack is a set process the owner approves

**Decided by:** project owner (a set process; plugin sessions never publish to the catalog); project lead (the steps).

**What:** A plugin repository releases in its own repository, keeps its entry in `catalog/pack.yaml`, runs `cockpit
pack check` (the manifest fits this host, the pack loads in a demo workspace, the entry matches `plugin.yaml` as
written), and adds a Publish request to its questions file. The host's session verifies the release itself and opens
a pull request on the catalog; the owner merges it, and only then is the pack listed. The steps are in the generated
developer guide ("Publishing a pack"), the catalog's PUBLISHING.md and `docs/plugin-kickoff-template.md`, which every
new plugin repository's kickoff brief is built from.

**Why:** The catalog is public and lists only what the owner chooses; a checked, repeatable path keeps entries honest
about what a pack reaches and keeps.

**Impact:** `engine/pack_check.py` and `cockpit pack check`; plugin API 0.3.37 notes; the catalog's main branch takes
changes by pull request only.

## 2026-10-11: The core is an everyday assistant, with Today as a dashboard

**Decided by:** project owner.

**What:** The core serves anyone running their own days, not only project managers: a solo person sets it up and lets
it read their mail and calendar and tell them what to do each day; a PM gets the same home and more. Today becomes a
dashboard that uses the screen: on a laptop, several columns visible without scrolling (today's agenda, what to do
today, what needs a reply or a decision, what changed since last time), each column scrolling on its own with a way to
see everything; fewer columns on smaller screens, one on a phone. Calendar events and mail messages that sources read
carry structured fields (start, end, place, people, sender) so the agenda and the inbox show them without an AI call.

**Why:** The same daily needs sit under every kind of work; a one-column list wastes a laptop screen and hides things
below the fold.

**Impact:** Design Part 7 (Today) and 6.4 (watched items carry structure); a Today redesign; `SourceItem` gains
optional event and message fields in a plugin API version; the scope's audience widens beyond project managers.

## 2026-10-11: One source of truth, value lists instead of free text, and settings that guide

**Decided by:** project owner.

**What:**
- **One source of truth for all data.** Every fact lives in exactly one place; everything else refers to it by id.
  The PM's name and aliases live on their person record only; `workspace.user` keeps the person's id and the
  settings that are about the workspace (time zone). A setting never repeats a record, and a record never repeats a
  setting. The rule binds plugins: a plugin refers to core records by id (`RefTo`) and never copies their names or
  fields into its own records, and the host checks what it can (design 3.5, 5.1).
- **Value lists.** A field with a known set of values (a project's status, phase and priority, a person's role and
  organization, a plugin's categories) takes its values from a named list, shown as a dropdown. Lists are settings
  (`config/lists.yaml`), with defaults from the core and from plugins, changed by the person; a value not on its list
  is refused, and adding one is a deliberate act ("Add to the list"), with Undo. Free text is kept for what is truly
  prose: notes, descriptions, summaries, the text of a question.
- **Settings guide the person.** A setting that turns a feature on comes first in its group, and the settings it
  governs are greyed out while it is off. A folder is chosen with a folder picker, a file with a file picker, a
  choice from a dropdown; typing a path or a value is the fallback, not the way.
- **AI setup for anyone.** Setup offers a list of AI services by name (a shipped data file; still no service names in
  code): pick one, paste a key (kept on this computer by the app), pick from the models the service offers, with
  suggested models for everyday and harder work, and test. Local models and command-line agents are on the same list.

**Why:** Free text and duplicated data make a system that breaks quietly; guided settings prevent mistakes instead
of explaining them.

**Impact:** Design 3.5, 4.0, 5.1 and 7 (settings). `workspace.user.full_name` and `aliases` move to the person
record. New `config/lists.yaml`, list-backed fields in core records and a plugin declaration for lists. Settings
metadata for order, dependencies and pickers. Named services in `catalog/ai-endpoints.yaml`; this answers the open
question "May catalogs list public AI services and addresses?" (yes, in data). Plugin API: lists and the one-source
rule join the contract.

**Update (same day):** the shipped list names services, their addresses and where to make a key, but no model ids:
those go stale within months. The screen lists the models the service itself reports (`POST /api/ai/models`, with a
key that isn't kept) and the person picks one for everyday work and, optionally, one for harder work. Suggesting
models waits until it can rest on what a service publishes (prices, context size) rather than on names.

**Update (same day):** value lists are kept as records (`value_list`), not in `config/lists.yaml`: adding a value
then has history and Undo like any change and needs no restart, the lists travel with the workspace's data, and the
storage layer refuses an off-list value from any writer. The core's first values ship in
`engine/defaults/value_lists.yaml`; plugins declare theirs (plugin API 0.3.42). First fields bound: a project's
status, phase, priority and group. A person's role and organization are not lists yet: an organization is better as
its own record (one source of truth), and that comes with the people screens.

## 2026-10-11: Every plugin repository has its own autonomous builder, with a written brief and a question channel

**Decided by:** project owner.

**What:** A plugin kept in its own repository is built by its own autonomous session, not from this one, so its
feedback on the plugin API is independent. Whenever this project suggests a new plugin repository, it also gives the
owner a kickoff brief: what is built there and in what order, the rules it follows, the contract (the generated
plugin guide), what the owner sets up, and how the two sessions talk. Questions to the host come in numbered rounds
in that repository's `docs/host-questions.md`, written generically, announced by a short session message; the host
answers by building a plugin API version and messaging back. A friction log records where the guide was unclear or
needed a workaround. Neither session writes to the other's repository.

**Why:** Clean feedback from builders who don't share this session's assumptions.

**Impact:** Applies to the mail and calendar plugins now, and every plugin repository after.

## 2026-10-11: Packs are found on an Add-ons screen, from catalog feeds, with costs priced on the person's accounts

**Decided by:** project owner (direction, maintainers' packs only in the default catalog, prices shown, the catalog as
a public index file the owner controls); project lead (design 3.11).

**What:** An Add-ons screen with Installed and Available. A listing shows what a pack does, what it adds, reaches and
keeps (written by the core from the pack's manifest), what its typical AI jobs cost on the person's own accounts, its
price and how to try it in the demo. The app never installs code into itself and never handles payment. Feeds are
read only when the person looks; the release build ships the maintainers' feed address; the repository holds none.

**Why:** People should be able to find out what packs exist, what they do, what they can touch and what they cost,
before installing anything, without ads or tracking.

**Impact:** Design 3.11; a `workspace.plugins.catalog` setting; `/api/packs` routes; the Add-ons screen. First
release: the catalog, the generated summary, the cost estimate, demo and install instructions. Later: updates with
re-approval, licence keys, Ask knowing the catalog, signed feeds, install from the screen.

## 2026-10-11: Mail and calendar from named services are plugins in a private repository; the core signs in

**Decided by:** project owner (plugins, in a new private repository); project lead (the sign-in in the core).

**What:** Mail and calendar from the two named services are plugins kept in their own private repository, which may
name the services and carry their sign-in addresses. The core gains a generic sign-in any plugin can declare
(`registrar.sign_in`, plugin API 0.3.33): OAuth 2.0 authorization code with PKCE through the service's own page, the
answer taken at the app's own callback route, tokens kept on this computer beside the plugin's other kept secrets and
renewed by the core, and `context.access_token(name)` for the plugin's connectors. The app registration (client id)
is the person's, set as a plugin secret.

**Why:** The open protocols cover most mail and calendars today; the services' own sign-in and richer APIs need code
that names them, which this repository keeps out.

**Impact:** Answers the open question in "Calendars and mail are read through open protocols". New routes under
`/api/sign-ins` and a Settings section for them. The plugins wait for the private repository.

## 2026-10-11: The package carries its screens, templates and demos; a demo says it is one

**Decided by:** project lead, under the owner's friends' preview milestone.

**What:** The wheel carries the starting templates, the AI endpoint catalog, the built web screens and the two fictional
demo workspaces in `engine/_shipped/` (a build hook copies them; a checkout reads them in place, through
`engine.shipped`). Building a wheel without the web screens stops with how to build them. `cockpit demo [folder]` makes
a demo workspace once (`--fresh` starts over, and refuses a folder holding a workspace that isn't a demo) and serves it,
opening the browser. New settings: `workspace.demo` (the screens label made-up data) and `server.open_browser` (with
`--open` and `--no-open`). Install and update are one script around `uv tool install --force`; a tag builds the package,
checks that it installs and starts the demo, and attaches it to a release with the scripts and `docs/install.md`.

The stand-in AI, with nothing scripting it, reads a hand-in by plain rules (`engine/ai/adapters/stand_in.py`): "<Name>
will …" is an action for that name, "we still need …" an action waiting for an owner, "Decided: …" a fact, each citing
its line; the rest is one note. It answers a question by quoting the first guide passage chosen for it. The demo's
screens say it is a demo (`workspace.demo`), and a feedback button drafts an email to `ui.feedback_to`, else to the
address a release build ships in `catalog/product.yaml` (empty in the repository); the app sends nothing itself.

**Why:** Friends get a download, not the repository: no Node, no checkout, one command to try it.

**Impact:** Roadmap "Friends' preview" (packaged install done; labeled demo screens and feedback button next). No change
to scope.

## 2026-10-11: Calendars and mail are read through open protocols in the core; product sign-ins wait for the owner

**Decided by:** project lead, pending the owner's answer below.

**What:** The core reads a calendar through its private calendar-file address and a mail folder over IMAP with an app
password. Both are protocol-level connectors that name no service, so they belong in the core. The address and the
password are secret references. Mail is read without marking anything as read. Calendar events in the configured
window are followed, so a moved meeting or a new invitation is handed in.

**Open question for the owner:** the to-do was mail and calendar for two named services. Their own sign-in (needed
when a service doesn't offer app passwords) and their richer APIs belong in plugins that name the service. This
repository's rules say it holds the core, the kit, its templates and the example plugin, and that real service
addresses don't appear anywhere in it. Should those plugins live in their own repository (like the industry packs),
and may they carry the services' public sign-in addresses?

**Why:** Most of the value (meetings, invitations, project mail) comes through the open protocols, which work today
without any decision about naming services.

**Impact:** Two more core connectors, demo sources (off) in both workspaces, a user-guide section. No change to scope.

## 2026-10-11: Plugins reach the network only through the core's client, to declared hosts

**Decided by:** project lead, following design 3.2 (what a plugin may reach) and 12.

**What:** `requires.network` and `requires.secrets` are now in use. A plugin's connector gets a web client that reaches
only its declared hosts, over HTTPS, with redirects checked against the same list and a size cap, and its declared
secrets: references in the workspace's settings, or values it keeps on this computer itself (a refreshed sign-in
token). Bundled plugins still may not import network modules; the scan enforces it. The core's feed connector reads
RSS and Atom and refuses documents that declare their own entities.

**Why:** Mail and calendar connectors need the network and a token; the person must be able to see exactly where an
add-on can reach before enabling it, and a compromised feed must not be able to make the app read other hosts.

**Impact:** Plugin API 0.3.27, `workspace.plugins.secrets` (demo values), a disabled demo feed source. Sign-in flows
for accounts come with the mail and calendar plugins. No change to scope.

## 2026-10-11: Triage rules live beside the watched sources

**Decided by:** project lead.

**What:** Triage rules are a `triage:` list in `watch.yaml`, not a separate `triage.yaml`, because they only ever apply to
watched changes and often name a source. A closed change is still kept as a source and a done request with the rule
and reason, listed as Auto-closed; Take a closer look queues it and records a `pulled_back` signal. A newer change to
an item whose earlier change hasn't been read yet folds the earlier one in, so the assistant reads them once, in order.
`our_accounts` is in `workspace.yaml` (design 4.1).

**Why:** Fewer files for the person to find, and one place that says what is read and what is set aside.

**Impact:** Design 4.5 and 6.5 read `watch.yaml` for triage. Plugin API 0.3.26 adds triage matchers. No change to scope.

## 2026-10-11: Watchers hand in differences as ordinary inputs; the first read is a baseline

**Decided by:** project lead, following design 6.4 and the decision on watchers and lookups (2026-10-10).

**What:** A watched source's read returns what it holds now; the core compares with snapshots and turns each
difference into a source record and a queued request, exactly like a pasted input but untrusted and marked with where
it came from. The first read of a source records a baseline instead of handing in everything (configurable). Removed
items are reported unless the source turns that off. No network files nothing; repeated failures file one question,
and a good read drops it. Connectors are an extension point (plugin API 0.3.25); the core ships a folder connector.

**Why:** One path for every input keeps evidence, trust and review the same whatever the source. A baseline avoids a
flood of work and cost on day one.

**Impact:** New config file `watch.yaml` (demo values with an inbox folder in both workspaces), records `snapshot` and
`watch_run`, `source.watched`, routes `/api/watch`. Triage and supersede come next, then a feed connector and network
access for plugins. No change to scope.

## 2026-10-11: Asking the assistant answers from quoted material only

**Decided by:** project lead, following the decision on asking about the app (2026-10-10).

**What:** An ask is a core `ask` request. Its packet holds the user guide sections that match the question, the
settings (no key locations), what the install can do and the records. The answer is an op whose cites are checked
against that material like evidence. Suggested settings are proposals the person applies through the same settings
save (fingerprint, validation, Undo). Requests the product can't meet become report drafts the person sends. The user
guide ships in `engine/guide/guide.md` and is the only source for how the app works.

**Why:** An assistant that explains the app must not invent buttons or settings. Quoting checked words gives the
same guarantee as evidence on claims, and proposals keep the person in charge of every change.

**Impact:** New core ops `answer`, `setting.propose` and `report.draft`; records `answer`, `setting_proposal` and
`report`; routes `/api/ask`, `/api/asks`, `/api/setting-proposals/*` and `/api/reports/*`. The Ask screen comes with
the next screens step. No change to scope.

## 2026-10-11: Settings are saved from the screens, and the app restarts itself to use them

**Superseded in part** by "The app restarts only when it must, and only when the person says so" (same day): the app
no longer restarts itself.

**Decided by:** project lead, following design 4.0, 6.14 and 7.8.

**What:**
- The Settings forms are described from the config schemas. A save names the fingerprint of the files the form came
  from, so two saves never race. Keys set by an environment variable or flag are locked, and the server's own keys and
  the storage backend are changed only in their files. The changed files are checked as a whole before anything is
  written, written keeping their comments, committed to the workspace's git, and recorded as `setting_change`
  records.
- Instead of reloading settings inside a running process, the app restarts itself between requests when its config or
  code changed (locally it re-executes). Old code never runs new settings, and nothing is half-reloaded.
- The first run has the design's steps plus a template step and plugins' own steps. Skips are kept per computer.
- A key pasted on the Add account screen is kept in the workspace's private folder (readable only by the user) and
  referred to as `file:`; a hosted app takes keys only from its environment.
- Kinds of AI account come from `catalog/ai-endpoints.yaml`. It lists only kinds that name no service for now.

**Open question for the owner:** may the catalog list public AI services by name and address (the repository rule
says no real URLs anywhere)? Until answered, people type the address of any service that isn't a local server.

**Impact:** New `setting_change` record type, plugin API 0.3.24 (`setup_step`), new routes under `/api/settings`,
`/api/setup`, `/api/templates` and `/api/ai`. No change to scope.

## 2026-10-11: Plugin API 0.3.23: contained failures, refusals shown before applying, stages that apply to some records

**Decided by:** project lead, from a plugin author's questions.

**What:**
- Today lines, interface items, event handlers and jobs are contained per call: a failure skips that call and is noted on
  the plugin; the plugin turns off after `workspace.plugins.failures_before_off` failures in a row there (default 3).
  Contract breaches and failures inside writes still turn it off at once.
- A person action's preview tries the whole proposal without keeping anything: an item that would be refused shows why
  and starts dropped, and other refusals are listed, so the person changes a choice instead of the action failing.
- A request can name an interface item; the provider's `about` function says which of its records the item stands for.
  Undeclared item fields are noted on the provider.
- `limits.room_mb`, `record_label` for messages, `follows` on work a handler does after a change, and `applies_if` on a
  stage.

**Why:** One failing read turned a whole plugin off, and an action failed outright on one refused part; a user of an
interface had to know the provider's ids; a stage that only some records need blocked the others.

**Impact:** New settings `workspace.plugins.failures_before_off` and a stage's `applies_if` (schema, defaults, demo
values). Tests that expected one failure to turn a plugin off now expect the configured count. No change to scope.

## 2026-10-11: Agent accounts are a command run locked down, described entirely in settings

**Decided by:** project lead, following design 6.16 (agent mode).

**What:** A `cli-agent` adapter runs any command-line agent as a program. The account's `agent:` settings say how to
start it (`command`, with `{model}`, `{packet}`, `{outbox}` and `{scratch}` placeholders, locked-down flags included),
how the packet goes in (`stdin` or a file), where the answer comes out (its output or a file in the outbox), where usage
and cost are in its JSON output, which environment variables it may see (`pass_env`, `key_env`), how to read its exit
codes and error stream (`errors`), and what to tell the person when it isn't signed in (`sign_in_hint`). Each run gets a
fresh folder in the system's temporary space, outside the workspace, and only PATH, HOME and the language settings
besides the listed variables. A cost the agent reports is used as the run's cost. The smoke test runs
`lockdown_test()` once per agent account: writing to its outbox must work; writing elsewhere and starting a shell must
not.

**Why:** Agents differ in flags, output shapes and error text from vendor to vendor and release to release; settings keep
every one of those out of the code, and the lockdown test catches flags that don't hold.

**Impact:** New `agent` settings under each provider in `ai.yaml` (schema, defaults, descriptions, demo accounts in both
workspaces). `AiError` gains a `hint`, shown in the waiting reason for a sign-in failure; `AiResult` gains `cost_usd`.
The lockdown is only as strong as the agent's own flags; the core can't sandbox a program by itself on every system, so
the test is the check. No change to scope.

## 2026-10-10: The core is complete on its own; the free version is "define your own"; industry packs are add-ons

**Decided by:** project owner.

**What:**
- **The core alone is a complete product.** A person installs it, is guided through setup, and runs their work with it.
  No screen ever depends on a pack.
- **The free version is the core plus a "define your own" kit**, not an industry pack: item types with fields (text,
  date, person, choice, link, number), stages with plain descriptions and entry checks, checklists, which fields the
  assistant may fill from inputs (with evidence), and what Today shows. All of it is set on screens, kept in workspace
  settings, and saved and shared as one template file. Starting templates ship with the core; the fictional demo
  workspace runs on one.
- **Industry packs are add-ons on the plugin API**, in their own repositories. The publishing pack moves to a private
  repository (to be sold later if the owner chooses); the workplace pack and its product connectors become a private
  add-on too. This repository keeps the core, the kit, templates and the example plugin.
- **Guided install and setup:** the web screens ship built inside the package (no Node needed to run it); install and
  update are one step; a first run in the browser walks through where the workspace lives, who you are, the AI account
  (with a connection test and plain errors), a starting template, backups and a first hand-in. Settings screens cover
  everything the files hold.
- **Agent accounts** (a vendor's command-line agent run with the person's own login, as corporate installs need) come
  before the friends' preview, so people can use subscriptions they already have.
- **Watchers and lookups** (6.19, milestone 5): the watcher engine, scheduling and general sources (a folder, a feed) are
  core; connectors for particular products are plugins.
- **Ask the assistant about the app** (extends 6.25): answers come only from the user guide, the workspace's settings
  (never secrets), what the install can do, and the person's records, with the passage shown. A question that needs a
  settings change becomes a proposed change the person confirms, with Undo; one the product can't do becomes a report
  to the maintainers (6.13).
- **A friends' preview** is a milestone: packaged install, guided setup, a clearly labeled demo with the stand-in,
  bring-your-own AI, a feedback button that drafts an email, and a download rather than repository access.

**Why:** The owner wants a free product anyone can set up and use for their own kind of work, with industry depth sold
separately, and to put it in friends' hands for feedback.

**Impact:** Supersedes "two reference packs bundled in version 1" in `scope.md` and design Part 9 / 13 (the packs still
prove the plugin API, from their own repositories). Order: plugin API 0.2, the kit, guided install and setup with agent
accounts and Ask the assistant, the friends' preview, watchers and connectors, then the publishing pack. The
publishing pack is no longer the path for the 2026-12-01 launch; a publishing template built with the kit is.

## 2026-10-10: Follow-ups: two steps, copy then Mark sent

**Decided by:** project owner.

**What:** Copy only puts the message on the clipboard. After a copy, the card's primary action becomes Mark sent, which
records the box's text as sent with an Undo toast; the card's menu always offers Mark sent too. This supersedes the part of
the earlier entry "Follow-ups: Copy marks sent" that made Copy record the message as sent.

**Why:** Copying is not sending; the person sends from their own email or chat and marks it sent when it has gone.

**Impact:** Design 7.5 and the wording sheet; no API, op or scope change. The sent view is unchanged.

## 2026-10-10: Dismiss a hand-in that stopped; Today suggests moves only for items already in a stage

**Decided by:** project owner (from trying the app); Claude wrote it up.

**What:** A hand-in stuck in "Needs you" or "Stopped" can be dismissed from its row menu (it keeps "Try again" as its action).
It goes to Done with a "Dismissed" label, stops counting as needing attention, and Undo puts it back as it was. A stage task
waiting for a go keeps its Go and cannot be dismissed. Today's "ready to move on" rows leave out items not yet in a stage;
Stages still offers the first stage for them.

**Why:** The only action on a failed hand-in was to try again, so an old one stayed forever. Suggesting the first stage on
Today for every item that was never started buried the real work.

**Impact:** Two optional fields on a request (`dismissed`, `dismissed_from`), two routes, one wording set. No scope change.

## 2026-10-10: Independence for second opinions is a setting per task kind

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** `tasks.<kind>.independence` in `ai.yaml`: `vendor`, `account` (default) or `isolated_run`. With `isolated_run`, a
check may use the same account in a separate run that carries only its own packet: never the writing run's history or
session, and on an agent account only after the lock-down test. A different model on the same account is preferred
when configured. The review says plainly which kind of independence was used, without naming the model.

**Why:** Many people have one subscription for everything; requiring a second account would put second opinions out of
their reach, while a separate packet-only run still removes the writing run's context.

**Impact:** Design 6.16 (independent second opinion) when built.

## 2026-10-12: Drafts are prose, anchored when they revise, and reviewed change by change

**Decided by:** Claude (design 6.7 as built); the owner can override.

**What:** A draft task kind's model writes plain prose; the core wraps it as a pending version, continues it once if
cut off, and runs lints on it. A revision can be anchored: the model marks each paragraph with the base units it came
from, a core invariant checks the map accounts for every unit and keeps atomic units whole, and the map decides
authorship. The person reviews pending versions through routes that give the regions to decide (three-way when the
text moved on) and accept, discard or edit.

**Why:** Long prose inside JSON is where cheaper models fail; anchors make "what changed and who wrote it" exact
instead of guessed.

**Impact:** Plugin API 0.3.9. The review and compare screens come with the UX work.

## 2026-10-12: Long text is versioned, reviewed change by change, and the assistant's text is always a draft

**Decided by:** Claude (design 5.0, 6.7 as built), the owner can override.

**What:** Long text fields keep every version (stored once by hash) with authorship by passage in three kinds. A
plugin writes them only with `writer.set_text`: from the person's own action the text is accepted and theirs; from
anyone else it is a pending draft. Accepting a pending version is change by change; when the current text moved on
since the version's base (a working copy handed back late), the merge is three-way: changes only in the current text
are kept, changes only in the proposal are offered, and a passage both changed is the person's pick. The export writes
texts as plain files beside the records.

**Why:** The assistant's prose must never become a book's text unreviewed, and a writer's own edits made elsewhere must
never silently undo what was accepted in the meantime.

**Impact:** Plugin API 0.3.6. Drafts as task output, anchored drafts and the compare routes come next.

## 2026-10-12: Plugins add lints; lints never refuse by default

**Decided by:** Claude (design), from the plugin's needs; the owner can override.

**What:** A plugin registers soft checks on the assistant's proposals. Each finding names the passage and how to fix
it; on "return" both go back to the assistant for its fix round. The plugin sets a default severity of return, warn or
off, never refuse; the workspace's `checks.yaml` overrides it per lint like the core's own.

**Why:** Voice and style rules are judgments: they belong with lints the person can tune, not with invariants.

**Impact:** Plugin API 0.3.5. Lints on long text and drafts come with long text.

## 2026-10-12: Projects inside projects, a language per project, and a budget per project

**Decided by:** Claude (design), from the plugin's needs; the owner can override.

**What:** A project may belong to another (`parent`; a series holds its books), never to itself or one of its own
parts. Language is a workspace setting (`workspace.language`, a tag such as en-US) a project may override, inherited
down through parents. `project.add` starts a project as a system op (the assistant's proposals wait for the person;
reading notes doesn't offer it). A project may carry a budget, set only by the person, covering AI work on it and
everything inside it; a run that would pass it waits with what is spent.

**Why:** A book series is a parent with child books; spelling, punctuation and dates follow the book's variety; and a
writer needs to see and cap what each book costs.

**Impact:** Plugin API 0.3.4. New fields on Project (`parent`, `language`, `budget_usd`), setting
`workspace.language`, op `project.add`. The project screens show and edit them in the UX pass.

## 2026-10-12: Content levels route work away from accounts that would refuse it

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** The workspace defines its content levels in `ai.content_levels` (ids and what each covers; the core names
none). Each account may list the levels it takes (`providers.<name>.content_levels`); an account without a list takes
every level, so nothing changes for people who never use them. A project carries `content_levels`, and a plugin record
type may name a field holding them; only the person sets either. A run carries the levels of its record and that
record's project, and routing skips accounts that don't take them all; if none does, the request waits with that reason.

**Why:** Refusals cost time and money and are predictable from the material; routing around them is cheaper than
handling them after the fact.

**Impact:** New settings `ai.content_levels` and `providers.<name>.content_levels`; `Project.content_levels`;
`Record.content_levels_field`. Marking an account after a refusal from the review comes with the review screens.

## 2026-10-12: A refusal is its own outcome, and the person decides what happens next

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** An adapter reports a refusal only from the provider's own signal: a content-filter stop, a refusal field in
the answer, or a content-policy code in an error body. Never from the answer's words. The run is recorded as refused,
with its cost and the provider's reason. A refused request is never retried, sent to the next account or escalated; it
waits for the person with the reason and the cost, and the person may send it to another account allowed to see the
material (`Request.use`). Accounts are offered by their names in the AI settings, never by model.

**Why:** Fiction, medicine, security and law touch material one account refuses and another accepts; which account sees
the text and what it costs stay the person's choice.

**Impact:** Run outcome `refused`; `Request.use`; `GET /api/requests/<id>/accounts` and `use` on retry. Content levels,
which route around refusals before they happen, come next.

## 2026-10-12: Plugin API 0.3.22: work that always asks first, and queueing from an action

**Decided by:** Claude (design), from plugin questions 73-79; the owner can override.

**What:**
- Plugin requests can always wait for the person's go.
- A new setting, `ai.budgets.confirm_unpriced`, makes runs whose cost can't be estimated wait too.
- An action's proposal can queue the plugin's own work, each item waiting for the go.
- Validators see the run's task and record.
- Records can be placed in the synced folder through a reference.
- Collections sort numbers as numbers.
- Plugins can read a field's current version directly.
- "Don't copy" is separate from "don't cite".

**Why:**
- On a subscription there is no price, so "ask above an amount" never asks. Spending stays the person's choice only
  if some work always asks.

**Impact:** New setting `ai.budgets.confirm_unpriced`. The action review shows the work a proposal will queue.

## 2026-10-12: How the define-your-own kit is built

**Decided by:** Claude (design), from the owner's decision of 2026-10-10; the owner can override.

**What:**
- The kit is a bundled plugin, `kit`, built only on the plugin API. It reads item types from its settings and
  registers record types, ops, stages, a panel and Today lines for each. Its settings are the plugin's own
  (`config/plugins/kit.yaml`), so the core config doesn't change.
- A plugin op can be offered to reading notes, a generic extension point, so the assistant can fill the fields a person
  allows, with evidence.
- Templates are the kit's settings with a name and a description, shipped in `templates/`.
- A manifest may declare `<plugin>/*` in a `provides` list for identifiers its own settings define.
- Changing a type keeps the data: a removed field is hidden, not deleted, and a renamed field is renamed in every
  record.

**Why:**
- Building the kit on the plugin API proves the API and keeps the core free of any one kind of work.
- Item types are settings a person edits, so they live in config with a schema and validation, like every other
  setting.

**Impact:** Design 3.10 (new). Settings screens for the kit come with guided setup.

## 2026-10-12: Plugin API 0.3.19, and evidence only for claims

**Decided by:** Claude (design), from plugin questions 69-72; the owner can override.

**What:**
- Plugin API 0.3.19.
  - Actions can be narrowed with `where`.
  - Event handlers and jobs can stage the plugin's own ops through the applier, as a changeset treated like work from
    outside content.
  - Plugins can read the workspace person's name.
  - Previews carry alt text.
  - `record.set` can set a project's owner.
- Evidence for `record.set` fields is now required only when the change isn't the person's own.

**Why:**
- A deterministic check needs somewhere to record what it checked, and going through the applier keeps the ledger,
  validators, tiers and Undo.
- Evidence exists so claims taken from inputs can be checked. A change the person makes on screen or approves in an
  action is not a claim.

**Impact:**
- Design 6.7's evidence rule now reads "claims from inputs".
- Screens show the alt text on previews.

## 2026-10-12: Plugin Today lines, panels and jobs

**Decided by:** Claude (design), building design 3.x and 7.2; the owner can override.

**What:**
- Plugin API 0.3.18.
- **Today lines:** a function returning lines, each with one action that is the plugin's own action or task kind.
- **Panels:** declarative specs (kind, filter, columns, view, actions), checked at load. Rows are read through the
  core.
- **Jobs:**
  - A run function on a schedule. It may do what an event handler may, never write records or call AI itself.
  - It runs while the app runs, configurable per job, with a `job_run` record for each run.

**Why:**
- Plugins need a place on the home screen and their own lists without front-end code.
- Regular work, such as a weekly review, shouldn't need the person to start it.

**Impact:**
- New core record `job_run`.
- New setting `workspace.plugins.jobs`.
- The screens that show plugin Today lines and panels come with the UX pass. Until then the routes are there for
  them.

## 2026-10-12: Plugin API 0.3.17: interface refinements and person-action needs

**Decided by:** Claude (design), from plugin questions 62-68; the owner can override.

**What:**
- Interface items can be computed for one project.
- Providers can raise interface events from event handlers.
- A packet part can carry a data level that raises the run's.
- `project.add` can move existing projects inside the new one.
- Person actions get free-text choices, all-or-nothing proposals and the limits they work within.
- Named interface calls with arguments were not added. Items cover the cases asked for so far.

**Why:**
- Content from another plugin can be more sensitive than the record a run is about. Routing has to see that, or
  restricted text could reach an account not allowed it.
- An import whose ops only make sense together must not apply halfway.

**Impact:**
- Changeset status `rejected` is now also used for an all-or-nothing proposal that was refused.
- Choice views carry `text` and `max_length` for the review screen.

## 2026-10-12: Interfaces between plugins

**Decided by:** Claude (design), building design 3.9; the owner can override.

**What:**
- Plugin API 0.3.16. A plugin defines a versioned interface (an item model, events, task kinds). Others provide it
  (an items function, events raised from ops, their own task kinds mapped to the interface's) or use it.
- Users read checked copies of the items, never the provider's records, filtered by their own data levels. They get
  the events and can request a provider's task kinds through the interface.
- Required uses keep a plugin off until something provides them. Optional ones read empty.
- The manifest gains `interfaces.defines`.

**Why:**
- Packs must work together without importing each other or reading each other's tables, and each must work alone.
- Checking items against the definition at read time puts a provider's mistake on the provider.

**Impact:**
- Design 3.9.
- The "uses" notice before enabling a plugin comes with the UX pass.
- A self-check case for required interfaces in the fictional workspaces comes with the first bundled pair.

## 2026-10-12: Outside edits, collections and generated files in the synced folder

**Decided by:** Claude (design), building design 5.0 and from plugin questions 59-61; the owner can override.

**What:**
- Plugin API 0.3.15. Files changed outside come back as proposals: long text pending, field edits and deletes held. A
  new core op, `record.edit`, carries the person's field changes to any record.
- Collections put many small records in one YAML file.
- Layouts can use a referenced record's field.
- Plugins can declare generated read-only files.
- Sources, outputs and working copies get readable copies, and file bytes travel in the machine copy.
- The machine copy now carries file and source bytes, which fixes handover for workspaces with files.
- Encrypting or leaving out sources above a data level waits until sources and files carry a data level. Until then
  every source is copied.

**Why:**
- Writers edit in their own tools. Outside edits must reach the record without ever changing it silently.
- Many tiny files make a folder unreadable.
- Records like a chapter's bible entry are named after another record.

**Impact:**
- Design 5.0.
- New setting `storage.sync.watch_outside_edits`.
- Core op `record.edit` is person only and never offered to note reading.
- The review screens for held edits exist; a screen listing outside edits comes with the UX pass.

## 2026-10-12: Handing a workspace between computers

**Decided by:** Claude (design), building design 5.0; the owner can override.

**What:**
- The folder's lease says which install holds the workspace. Opening compares the two ledgers entry by entry:
  - the same: nothing to do;
  - the folder continues this computer's history: back up and load the folder;
  - this computer continues the folder's: write the folder;
  - neither continues the other: refuse, until the person runs `cockpit sync keep --here` or `--folder`.
- Loads read only manifest-listed files that match their hashes.
- Storage and server settings stay per computer.
- A running install stops writing once another holds the lease.

**Why:**
- Comparing whole ledgers can't mistake two different histories of the same length for one.
- Hash-checked loads keep a half-synced folder or a sync service's conflict copy from ever being read.
- Paths and ports differ between computers.

**Impact:**
- Design 5.0.
- New setting `storage.sync.lease_stale_after_minutes`.
- New commands `cockpit sync keep` and `cockpit init --sync`.
- `cockpit serve` checks the folder before opening.
- Plugin code isn't copied between computers: a plugin missing on the other computer stops the load with the reason.

## 2026-10-12: The synced folder holds a readable layout and a machine copy

**Decided by:** Claude (design), building design 5.0; the owner can override.

**What:**
- Plugin API 0.3.14. Each record type declares a `layout` path template. The core writes those records as Markdown
  (front matter and the current long text) or YAML, with every long-text version in `.versions/`.
- Beside the readable files, the folder holds a machine copy in `.cockpit/`: the plain export, config and plugin data.
  Loading the folder reads the machine copy, never the readable files.
- Files the cockpit wrote are tracked by hash. A file whose content changed outside is never overwritten or removed.
- This first part writes the folder. The lease, handover, outside edits coming back for review, `working/`, `outputs/`
  and sources come next.

**Why:**
- Loading from readable files would make every outside edit a load-time merge. A machine copy loads exactly, and the
  readable files stay a view whose edits come back as proposals.
- Writing the whole export at once (not per changeset) keeps the folder consistent even when a write is missed.

**Impact:**
- Design 5.0.
- New setting `storage.sync.folder`.
- Core record types person, team, action, question, fact and note have layouts.
- `cockpit import` accepts a synced folder.

## 2026-10-12: Roles, and second opinions on one account

**Decided by:** Claude (design), from plugin questions; the owner can override.

**What:**
- Plugin API 0.3.13. Every task kind has a role: write, check or research. The workspace maps roles to tiers.
- A check never runs on an account whose AI runs wrote the record it checks.
- A person can accept the same account for checks. The check is then a fresh run that sees only its packet, and the
  run records that it came from the same account.
- This replaces the design's `independent: true` per task.

**Why:**
- Many people have one subscription. Without this, a check would either wait forever or quietly reuse the writer's
  account.
- Marking which kind of independence each check had keeps the choice visible.

**Impact:**
- Design 4.8 and 6.16.
- New settings `ai.roles` and `ai.tasks.<kind>.same_account`; `Run.independence`.
- The review screen shows a check's independence in the UX pass.

## 2026-10-12: Plugin API 0.3.12: who started a run, where work starts, questions from drafts

**Decided by:** Claude (design), from plugin questions; the owner can override.

**What:**
- A packet function sees who started the run. Only a note from the person counts as their words; a note from an
  outside input is now untrusted, like a scheduled one.
- A task kind can narrow the records it is offered on by field values.
- A draft may end with a few questions for the person, kept beside the version instead of inside the text.
- A person action rerun drops a choice it no longer offers.
- Temporary names for records created earlier in the same answer were not added. One op that creates both records
  covers the need. Handles would break when one op is held or refused and the other applies.

**Why:**
- Treating an outside input's note as the person's words was a trust gap.
- Work offered where it can only fail is noise.
- Questions inside a draft's prose get accepted as text by mistake.

**Impact:**
- New `TextVersion.questions` and `text.draft.questions`.
- `GET /api/task-kinds` takes `id`.
- Rerun the evaluation for the core's note-reading prompt only if inputs start carrying notes (none do today).

## 2026-10-11: Working copies: long text edited in the person's own tools

**Decided by:** Claude (design), building the plugin API; the owner can override.

**What:** Plugin API 0.3.11. A plugin may provide a working-copy format that turns a long text field into a file for
another program and reads it back, both deterministically. The core keeps the file through the file channel, records
each copy with the version and hash it went out with, and files a returned file as a pending proposal made from that
version, so accepting it is the ordinary review, three-way when the text moved on. What the format couldn't read back
is kept on the proposal, never dropped. A format must read its own untouched file back to the same text; the core
checks this at every hand-out and refuses when it fails. Watching the working folder for edits waits for the synced
folder.

**Why:** People write in their own tools; the record stays the source, a file is only a copy, and nothing in a
returned file changes the text without the person's review.

**Impact:** New core record `working_copy`; `TextVersion.unmapped` and `text.propose.unmapped`; five routes under
`/api/working-copies`. The screens to hand out and bring back come with the UX pass.

## 2026-10-11: Backups run on their own; a missing backup folder is never created

**Decided by:** project owner (nobody should have to click backup); Claude (how).

**What:** While the app runs, a background thread makes a backup whenever one is due (`storage.backups.every_hours`),
including right after the computer wakes, and tries again after `retry_minutes` when one fails. `automatic: false`
leaves only backups on request. A target folder that doesn't exist is refused with the reason, never created. Choosing
the off-device folder once stays part of setup, and the header keeps saying when none is set or the last one failed.

**Why:** Backups that depend on remembering to click don't happen. Creating a missing folder would put the "backup" on
this computer's own disk when a drive isn't connected, which looks like a backup and isn't one.

**Impact:** Design 4.15 already called for scheduled backups; this builds them. New settings `automatic` and
`retry_minutes` under `storage.backups`.

## 2026-10-11: The plugin developer guide is generated from the code and is the contract

**Decided by:** project owner (the guide before the rest of the API); Claude (how it is made).

**What:** `docs/plugin-guide.md` is written by `uv run python -m engine.plugin_guide` from docstrings, field
descriptions, `#:` comments and the host's own tables (manifest, events and their payloads, plugin settings, core
records and ops). The self-check fails when it is out of date, and tests check it covers the public API and that real
event payloads match it. Plugin authors get names only from it, never ahead of the code. `docs/plugin-api-0.x.md`
keeps only what changed per version. Core records and ops now carry a description on every field; the op descriptions
also reach the assistant in its task schemas.

**Why:** Names given ahead of the code drifted from what was built. A generated guide can't, and it grows with each
API step, so plugins integrate what exists instead of waiting for the whole API.

**Impact:** Prompts carry the fuller op descriptions; rerun the evaluation on the routine model to confirm results hold.

## 2026-10-11: Long reviews: groups, and items kept or dropped without a rerun

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** Plugin API 0.3.1. A proposal may group its choices and items under headings. Items are judgment calls the
person keeps or drops without the action running again; only kept items' ops apply, each item's ops together. Ticks
carry over a rerun to items that came back unchanged. The changeset records which items were kept and dropped. Field
names are announced only from the code and the contract document.

**Why:** A book-length file gives hundreds of judgment calls; rerunning the action for each tick would be slow and run
programs needlessly, and one long list is unreadable.

**Impact:** New setting `workspace.plugins.actions.max_items`. The review screen shows items in a later UI pass; until
then the review lists every op that applies with the ticks as they are, so nothing applies unseen.

## 2026-10-11: Person actions apply what the person reviewed, as the person

**Decided by:** Claude (design), building plugin API 0.3; the owner can override.

**What:** A plugin's person action returns one proposal (ops, files it made, previews, named choices, notes). The host
keeps it under a token for a while; flipping a choice runs the action again; applying takes exactly the kept proposal,
once, and refuses if the target changed since. It applies as the person (actor `pm`, confirmed), so person-only values
and system ops apply without a second go. Files are added by a core `file.add` op in the same changeset, so Undo takes
them back with everything else; Undo now goes newest first, so an op that refers to an earlier one's record is undone
before it. Actions can't propose ops that need evidence. Previews are pictures or plain text only. The routes are under
`/plugin-actions`, since an "action" in the core is a to-do.

**Why:** The person must approve exact content, never a recomputation of it; and an action's result must come back as
a whole with one Undo.

**Impact:** Plugin API 0.3.0. New core op `file.add` (offered only to actions), `Changeset.action`, settings under
`workspace.plugins.actions`. Manifests move to `'>=0.3,<0.4'`.

## 2026-10-11: How run_tool finds, checks and runs programs

**Decided by:** Claude (design), building plugin API 0.3; the owner can override.

**What:** Where a program is found is set per computer in `.cockpit/tools.yaml` (a path, or a command with its own
environment), falling back to the PATH; it is never synced, so two computers can differ. Each declared tool is probed
when its plugin loads: a missing or too-old required tool keeps the plugin off with the reason; a missing optional one
shows on the plugin's status and `tools.available()` says no. A probe starts with the tool's name. A run happens in a
fresh temporary folder, without a shell, with a minimal environment (PATH, locale, and HOME and temp pointed at the
folder), a timeout the plugin may lower but not raise, and capped output that says when it was cut. Limits are
`workspace.plugins.tools`. Every run is a `tool_run` record. Plugins get tools only in person actions, never in event
handlers, stage checks or validators, which must stay quick and deterministic.

**Why:** Programs differ by computer; a long or hanging program must never stall the engine, and a run must not see
the person's environment or files beyond what it was given.

**Impact:** Plugin API 0.3. New core record `tool_run`; new settings under `workspace.plugins.tools`.

## 2026-10-10: Plugin API 0.2.1: the core keeps its own rules everywhere it applies them

**Decided by:** Claude (design), from trying plugin API 0.2; the owner can override.

**What:** References inside lists are enforced like single ones. Undo skips and reports a group that would break a
unique group or leave a dangling reference. A stale `record.delete` is refused, not raised, and every op applies in its
own savepoint. Event `kinds` filters are checked at load (only on events that carry a kind, naming core or own kinds),
with one handler per event. Lookups refuse unknown fields and list values; `project=None` means "no project" and `ANY`
means no filter; matching is exact and case-sensitive. An op may label itself with `describe()`. Validators may take
`origin` as a keyword. A plugin's ops always act as the assistant, so person-only values wait for the person's release
until person actions (0.3) run as the person. Reaching outside the declared scope still disables the plugin.

**Why:** Each rule the core declares should hold on every path that writes, or a plugin can't rely on it; a typo should
fail at load, not read as silence.

**Impact:** Plugin API 0.2.1, compatible with `'>=0.2,<0.3'` manifests. `docs/plugin-api-0.x.md` updated.

## 2026-10-10: run_tool returns files the program wrote

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** `run_tool` (plugin API 0.3) takes `collect` patterns and returns matching files from the program's working
folder as bytes, with per-file and total size caps (config defaults a call may lower, never raise); files over a cap are
listed as omitted, never cut short silently. Only regular files inside the folder match (no `..`, absolute paths or links
out); the folder is deleted afterwards; returned files are untrusted material; each run is recorded.

**Why:** Some programs report through files they write (a converter's log, a rendered page), not their output stream.

**Impact:** Part of `run_tool` in plugin API 0.3.

## 2026-10-10: Plugin API 0.3 comes with the file channel

**Decided by:** Claude (design), from a second round of plugin questions; the owner can override.

**What:** Plugin API 0.3, with the file channel and before the publishing pack, adds: uploads in the UI to the
workspace's plugin data or a project, with metadata a plugin declares per file kind, and a `file.added` event; previews
(images a plugin renders in code) on review items and questions, shown and never saved or sent; person actions
(`registrar.action`), deterministic work the person starts on a record or file that returns one proposal for one review,
with named choices the person flips and the plugin recomputes before anything applies. Later: a `web_search` adapter
capability whose fetched pages are saved as sources for evidence; strict isolation of agent-mode runs (fresh session,
empty folder with only the packet, no memory files), required before an account does independent checks; subscription
accounts counted as usage against their allowance, pausing and resuming at the reset; tool paths and probes per
computer; in 1.0, sending a built file is an export to a chosen folder or a hand-off to the person's mail app, recorded
against the file's version.

**Why:** The publishing pack needs uploads, previews and person actions itself (cover files, page proofs, importing a
manuscript), so they belong in the API it is built on.

**Impact:** Roadmap 2a: "Plugin API 0.3 with the file channel" replaces "file channel".

## 2026-10-10: Tolerate harmless answer shapes; wait out rate limits on the last account

**Decided by:** Claude (design detail), from the owner's first evaluation run on a low-cost model; the owner can override.

**What:** Evidence written as a bare string, or with extra keys beside the quote, is read as the quote; the quote is still
checked word for word against the input. When the last account in line says to slow down, the call waits and tries
again (`ai.rate_limits`: tries, longest wait); with another account available, it moves on at once. Evaluation reports
calls the account refused as "not run" and leaves them out of the score. `cockpit evaluate -w <workspace>` uses that
workspace's cases and AI setup, and `init` copies a template's cases.

**Why:** The run threw away two nearly right answers over their shape and scored four rate-limited calls as failures,
which said nothing about the model.

**Impact:** New config key `ai.rate_limits` (schema, default, description, demo values). No change to what is checked.

## 2026-10-10: Hand-in is one box with a choice of whose words are in it

**Decided by:** project owner (from trying the app); Claude wrote it up.

**What:** The two-box hand-in becomes one box and a required choice, "Whose words are these?". "Someone else's" (the default)
sends the box as pasted content, with an optional line saying what to do with it as the note. "Mine" sends the box as the
note. The API and the trust model are unchanged: other people's words always arrive as pasted (untrusted) content. Alongside:
filed notes can be found under their project, the assistant's state shows on Today with the provider's own reason, and a new
workspace shows a "Start here" card.

**Impact:** Design 7.6 (hand-in wording) and 7.8 (first run) only; no change to scope, the API or the trust rules.

**Why:** A pasted email in the first box was read as instructions with no material to work on. One box with an explicit,
defaulted choice removes the way to get that wrong without weakening it.

## 2026-10-10: Plugin API 0.2 comes before the publishing pack

**Decided by:** Claude (design), from questions raised while building a plugin against 0.1; the owner can override.

**What:** Plugin API 0.2 adds: a data level per record type (up to `restricted`, honored by packets); the change's origin
passed to validators, and person-only field values that hold an op for the person when anything else sets them; unique
fields and `find`; filtered `list` by project and field values; `Ref` fields to core and own records (checked, rewritten
on rename and merge, used for export placement); validators that see the changeset's own transaction; kind filters on
`record.changed` subscriptions; a core `record.delete` op with undo. `ext` on core records is reserved and may be
removed; plugins keep their own linked records. Later, with their features: conversational tasks (6.25), per-task packet
inclusion and reference-only records (prompt bundles), generated read-only files and front-matter layouts (synced
folder), per-project plugin settings.

**Why:** The bundled publishing pack needs most of these itself (references to projects, filtered reads, person-only
values), so building them first keeps the pack on the public API instead of special cases.

**Impact:** Roadmap 2a gains "Plugin API 0.2" before the publishing pack. `Project.parent` and `Project.language` (5.1)
land with long text, also before the pack.

## 2026-10-10: Plugin host and stages reviewed; the rules they follow

**Decided by:** Claude (design detail, from a review of the plugin host and stages work); the owner can override any of it.

**What:** The plugin host (plugin API 0.1) and stages are merged after review, with these rules:
- A plugin op writes only the plugin's own record types. Core records change only through core ops, so evidence, owner and
  tier rules always apply. `outbound` plugin ops are refused until the publisher is part of the API.
- An ordinary refusal inside a plugin op (a stale version, an invalid value) refuses that op; reaching outside the
  plugin's declared scope disables it. A disabled plugin's validators no longer block core ops.
- Notes on scheduled work (plugin requests, stage tasks) reach the assistant as untrusted data, never as the PM's words.
- Stage config naming a plugin that is turned off or failed to load stays in place and shows as unavailable; the workspace
  still starts.
- A stage move goes one stage forward, after that stage's entry checks pass, or back to any earlier stage without checks.
  An item not yet in a stage may start at any stage whose checks pass, so work under way can be brought in where it is.
- Rule-driven moves need an entry check on every stage after the first, and leave an item alone after the person moved it
  back or undid a move.
- A stage task is never queued twice for the same item and stage; moving on before the go closes it, and Undo reopens it.
  Requests that plugins queue in response to a stage move also wait for the go.
- A workspace stage entry without `stages` keeps the pack's list; every stage has a label; record types may not define
  their own `stage` field.

**Also recorded here (from the host work):** registries are per store; events publish after commit only; manifest
contributions without an extension point yet are refused; standing rules may name a deterministic `check`, and prose
rules never allow a move (a general executable rule language stays an open question).

**Why:** The review found paths where a plugin could bypass core checks, where one failing plugin stopped the workspace or
blocked core work, where rules undid the person's Undo, and where skipped stages skipped their checks.

**Impact:** `docs/plugin-api-0.x.md` describes the contract. Plugin settings layered from environment, flags and profiles
are a later change.

## 2026-10-10: The publishing pack is a stretch goal for the 2026-12-01 launch; UX is checked as we go

**Decided by:** project owner.

**What:**
- The owner's manual launch process continues. If the publishing pack is usable by about 2026-11-01, the last weeks of
  the launch can run through it alongside the manual process; if not, nothing is lost. Supersedes "the launch goes ahead
  without the tool" in the entry below.
- Build order: cost control, then the file channel, then dependencies and baselines, then the publishing pack.
- No feature is done without its screen. Before handing a feature over, Claude runs it on the fictional imprint, end to end,
  with desktop and phone screenshots checked against Part 7. The owner tries it weekly for about 15 minutes; friction goes in
  `docs/project/ux-notes.md`. Before November, Today becomes the real home, with plain empty states and a first-run guide.
- From outside reviews, adopted: a one-tap reason on Send back and Undo (wrong fact, wrong person, wrong tone, missing
  context, duplicate), feeding evaluation cases; a permission diff before a plugin is enabled or upgraded; a read-only "why
  did this happen?" trace per run (after the publishing pack). Into cost control: cached input tokens recorded and priced
  separately, cache markers as an adapter capability, and choosing a tier whose context window fits before sending.
- Not adopted: ranking Today with an AI model (Today's order stays rules), showing model names, keeping workflow state or
  keys in the browser.

**Why:** The owner's main concern once the core holds is the experience of using it; the earlier UX fixes came from a few
minutes of real use.

**Impact:** Roadmap section 2a; design 6.16 and 7 get the adopted items when each is built.

## 2026-10-09: Real use starts with the publishing pack

**Decided by:** project owner.

**What:** No real data goes into the cockpit until the publishing pack is ready; all testing is on fictional data. The
2026-10-30 go/no-go and the November freeze no longer apply, and the 2026-12-01 launch goes ahead without the tool. Build
order from now: (1) the plugin host (brief in `docs/project/next-task.md`); (2) what the publishing pack needs from the core:
stages, dependencies and baselines, the file channel, cost control; (3) the publishing pack; (4) Ask the assistant and the
remaining document features.

**Impact:** real use moves from the launch run-up to after the publishing pack; Ask the assistant moves after it.

## 2026-10-09: Build on now; the launch slice was too thin to validate

**Decided by:** project owner, after trying the launch slice.

**What:** Building continues now instead of waiting for 2026-10-31, in this order: (1) people and projects screens, so a
real workspace can be set up without editing files; (2) "Ask the assistant" for drafting on request (6.25); (3) the early
branch work (plugin host, document features, synced folder, developer guide). The launch-slice copy for the launch is commit
`49e95e7`; the owner runs that copy for real launch work if newer builds are unsettled. The settings screen for AI accounts
waits for the automatic restart (6.14), since AI settings changed from the browser need it; `cockpit ai test` covers setup
until then.

**Why:** In real use the slice could not be validated: there was no way to set up the imprint's people and projects without
editing data files, and the first thing the owner asked for (drafting an email) was not built.

**Impact:** the go/no-go on 2026-10-30 judges whatever is built by then; the November freeze applies to the copy in use, not to
development. Owner time unchanged.

## 2026-10-09: Lessons from switching AI providers

**Decided by:** project owner, from the owner's experience switching the AI provider in a private tool.

**What** (design 6.16, 6.14, 6.13, 6.3, 6.7, 3.3, 6.2):
- **No silent provider:** no default account; a tier naming a missing account is a config error; an empty tier makes its
  work wait with the reason. The first run on a new account is shown as such.
- **Smoke test on every change** (`cockpit ai test`): one live call per tier and account with each task's exact parameters;
  agent adapters also get a lock-down test; models declare the parameters they accept and the self-check rejects a tier
  whose model can't take them.
- **Errors read in one place:** only the adapter's `classify_error()` reads vendor error text; a sign-in failure becomes a
  question to the PM with the adapter's `sign_in_hint()`.
- **Changed settings or code under a running process:** no new job starts on old code with new config; the process restarts
  (the launch slice pauses new work and asks for a restart).
- **Canonical form for outside systems:** channels normalize values as the system stores them; after a publish the target is
  pulled again, and a remaining difference is an automation problem, not a draft.
- **Check the premise first:** local records before outside lookups; "can't do" must name what it checked; missing targets
  become a question to the PM; a PM's note is an instruction, and an identical answer after a send-back is refused.
- **Real gaps:** `project.add`, person-owned fields the assistant can't set, and text extractors for office files (spreadsheet
  comments, presentation tables and speaker notes), with unsupported types flagged once.
- **Probation for a new account:** its work always waits for review for `ai.probation.runs` runs per task kind, and the PM's
  Looks good and Send back count toward its score.

Classified as concepts in the core, with two settings (`ai.probation.runs`, and the per-model parameter capabilities in the
adapter) and new evaluation data (a request naming items that don't exist).

**Impact:** in the launch slice now (about a day, done): no default account and config errors for missing ones,
`cockpit ai test` with a start-up notice when untested, pausing work when settings or code change under the server, refusing an
identical answer after a send-back, and the new evaluation case. The rest is version 1 work, listed in the roadmap's open
items; where the adapter items land depends on the open milestone 10 decision. No owner time beyond running
`cockpit ai test` after adding a key.

## 2026-10-09: Long text formats divide text into units

**Decided by:** project owner, answering a question from a plugin kept in another repository.

**What:** Each `long_text` field names its format. The core ships `plain` and `markdown`; plugins can register a text format
(3.3) whose `units(text) -> spans` says where units start and end and which are atomic. Anchors, authorship, per-passage review
and lint anchors all work in units, and a core invariant refuses a draft that splits or merges an atomic unit.

**Why:** Splitting on blank lines breaks fenced blocks, multi-paragraph footnotes and poems; every pack with structured prose
would otherwise re-check this in its own validators.

**Impact:** about half a day on the early branch, with paragraph anchors. No owner time.

## 2026-10-09: Draft checks, plugin lints, project language, tools, plugin data, text events

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Paragraph anchors** (6.7): revising tasks can ask for anchored drafts; the core checks every base paragraph is accounted
  for, strips the markers before storing and keeps the paragraph map for review and authorship.
- **Lints in code** (3.3, 4.17): a lint extension point whose problems point to passages; guidance goes back per passage and
  shows in the compare view.
- **Lints on drafts** (6.16): for a draft or proposed version, a `return` lint still failing counts as "would be held", so it
  gets the escalation re-run, then stays pending with its findings; `warn` only shows.
- **Project language** (5.1, 4.6): a project can override the workspace locale for lints, spelling, dates and drafting.
- **Declared programs** (3.2, 3.5): `requires.tools`, run only through the plugin API, probed on enable and by the
  self-check; a missing optional tool turns off only its features.
- **Plugin data files** (4.12): `<workspace>/plugin-data/<plugin>/` laid over shipped data, versioned and synced.
- **Events** (3.4): `record.changed` carries kind, id, fields, version and op; a new `text.accepted` event.

**Why:** Each is needed by any pack that drafts long text or ships its own data, not by one plugin; deciding them before the
plugin API is frozen avoids a breaking change later.

**Impact:** anchors, code lints, lints on drafts and the events add about two days to the early branch (from 2026-10-31);
project language, declared programs and plugin data files land in version 1 milestone 4. No owner time.

## 2026-10-09: Working copies, a compare view, and validators as invariants

**Decided by:** project owner, answering requests from a plugin kept in another repository.

**What:**
- **Working copies** (design 5.0): a plugin can register a working-copy format (3.3) to hand a `long_text` field out as a file
  for the person's own tools and take it back deterministically; the hand-back becomes a `text.propose` held for review,
  three-way when the base moved, never merged silently.
- **`text.propose` and `text.accept`** (6.7): the person's outside work waits for review like an assistant draft; accepting
  takes per-passage choices and writes one version with authorship per passage. Plain files edited in the synced folder use
  the same path.
- **A compare view** (7.2): two-way and three-way review of `long_text` versions that any declarative panel can use.
- **Validators:** an op validator's refusal counts as an invariant failure for the fix round and escalation (6.16), so
  validators must be deterministic; judgment calls are lints.

**Why:** Long documents are written in the tools people already use; the cockpit is where they review and approve. Without a
core path, every plugin would build its own hand-back, diff and merge.

**Impact:** about three days more on the early branch (from 2026-10-31), which now runs about three and a half weeks. No owner
time. Nothing changes in the launch slice.

## 2026-10-09: Synced folder details and the manuscript contract

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Nested projects:** `Project` gets an optional parent; a child project's folder sits inside its parent's (a series and its
  titles, a program and its projects).
- **Sources travel:** every source (original file and extracted text) goes into its project's folder in the synced folder,
  so evidence resolves on either computer; sources above a configured data level are encrypted or left out.
- **Own files:** the cockpit records the hash of every file it writes to the folder and ignores matching files when watching;
  outputs go to each project's `outputs/` folder, and an output changed outside asks "rebuild or keep", never counts as an edit.
- **Authorship in three kinds:** written by the person, drafted by the assistant, the person's text changed by the assistant.
- **`publishing/manuscript-source@1`:** fields, events, optional task kinds and the publishing pack's behavior (design 9.7).

**Why:** Handover is only safe if the folder really holds everything; disclosure rules treat drafting and editing
differently; a finished manuscript should start a launch without retyping, from any plugin.

**Impact:** about a day more on the synced folder work in the early branch; the interface lands with the publishing pack
(milestone 8). Nothing changes in the launch slice.

## 2026-10-09: Two computers through a synced folder

**Decided by:** project owner, after a review from a plugin kept in another repository.

**What:** One workspace can be handed between computers through a file-sync folder (design 5.0, 4.15 `sync`). The database
and git history stay on each computer's local disk; the synced folder holds a complete, readable export laid out one folder
per project, written atomically after every changeset; the lease lives in the folder; diverged histories are never merged
silently; outside edits come back as changes to review. Sharing one project between different workspaces is left for later.

**Why:** Long documents need to be readable outside the cockpit and work must continue on a second computer, but file-by-file
syncing corrupts live databases and git repositories. A per-project exchange between separate installs was considered and
rejected for now: ids and people are per workspace, so a project loaded into another install would collide.

**Impact:** about four days of build time, added to the early branch after the document features (from 2026-10-31). No
owner time. Nothing changes in the launch slice.

## 2026-10-09: Plugin host and document features built early, beside the freeze

**Decided by:** project owner.

**What:** From 2026-10-31, on a separate development branch, ahead of milestones 3, 5 and 7:

1. A minimal plugin host (milestone 4): plugin API 0.x, manifests, registries, plugins working together (3.9), one example
   plugin.
2. The core features for document-heavy packs (from milestone 6): long text with versions and authorship (5.0), drafts with
   prose output (6.7), stages (6.26), cost control with estimates, a go above a set amount and budgets per task kind and per
   record (6.16), the independent second opinion (6.16), and the file channel (6.3).
3. A plugin developer guide generated from the plugin API: every extension point, op, event and interface schema, so a plugin
   kept in another repository can be built against it.

The copy the owner uses for the launch stays frozen (fixes only), whatever the go/no-go outcome.

**Why:** The owner wants to build and try plugins during the launch run-up, and plugins kept in other repositories need real,
tested contracts to build against, not a spec that changes once it meets code.

**Impact:** changes the build order only; about two weeks of build time, no owner time required (trying plugins is optional
and never ahead of the launch). The plugin API stays 0.x and may change until both bundled packs run on it.

## 2026-10-09: Plugins work together through the core

**Decided by:** project owner.

**What:** Plugins cooperate in four ways, all through the core (design 3.9): shared core records (a launch is one project
that the publishing pack and a social media pack both link to), versioned interfaces a plugin provides and others use (required or
optional), event subscriptions (now a `1.0` extension point, no longer planned), and requests for another plugin's task
kinds. Plugins still never import each other. Each pack works alone; optional interfaces add features when both are enabled.
CI tests each pack alone, each pair sharing an interface, and the core with none.

**Why:** Some work spans packs (a launch and its announcements, a won deal and its delivery); without a contract between them
the PM would retype everything and the packs would grow hidden dependencies on each other's internals.

**Impact:** adds work to version 1 milestone 4 (the plugin host; a few days of build time), before the plugin API is frozen.
Nothing changes in the launch slice.

## 2026-10-09: Core features for document-heavy packs

**Decided by:** project owner, after checking the candidate packs against the core.

**What:** Six generic features join the core design, in version 1 (milestone 6), before the plugin API is frozen:

- **Long text** (5.0): prose fields stored once per version by hash, with authorship by passage, instead of full copies in the
  ledger; needed before real data exists, because changing the ledger format later is a migration.
- **Drafts and prose output** (6.7): drafting tasks produce a `text.draft` the person reviews; drafts are not claims, so they
  are not held to the evidence rule, but checkable facts inside them are.
- **File channel** (6.3): approved content saved to a configured folder, beside the clipboard.
- **Stages** (6.26, 4.21): one mechanism for work that moves through steps, replacing per-pack stage fields; the publishing
  pack's titles use it first.
- **Independent second opinion** (6.16): a review on a different account from the one that wrote the work.
- **Cost control** (6.16, 4.8): estimates before a run, a go for anything above `budgets.confirm_above_usd` (spending money is
  irreversible, so it confirms like sending does, 7.6), budgets per task kind and per record, spend shown by pack, task kind and
  record. Drafting long documents can cost the person real money; it must never happen without their choice.

**Impact:** adds work to version 1 milestone 6 (about a week of build time; no owner time beyond reading the design). Nothing
changes in the launch slice. The sales pack stays in the Later horizon.

## 2026-10-09: Sales pack recorded as a candidate

**Decided by:** project owner.

**What:** A future sales pack is recorded in design 13.3: business-to-business sales of installed services (accounts,
opportunities, proposals, SOWs, contracts, regulatory requirements as workspace data).

**Impact:** none on the launch slice or version 1; it is in the Later horizon.

## 2026-10-09: License changed to Apache-2.0

**Decided by:** project owner.

**What:** The product is licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`, SPDX `Apache-2.0`), replacing the
AGPL-3.0 chosen earlier the same day.

**Why:** The goal is that people can use it at their companies. Many companies' open-source approval processes restrict or
ban the AGPL, while Apache-2.0 is widely approved. The owner wants attribution (the copyright notice and `NOTICE` must be
kept) and patent protection (an explicit patent grant from every contributor, ending for anyone who sues over patents in the
project); Apache-2.0 gives both. Accepted trade-off: changed versions, including ones run as a service, need not be shared.

**Impact:** none on scope or schedule. Dependencies stay compatible (all are MIT, BSD, Apache-2.0, MPL-2.0 or PSF).

## 2026-10-09: License is AGPL-3.0 (superseded the same day by Apache-2.0)

**Decided by:** project owner.

**What:** The product is licensed under the GNU Affero General Public License v3.0 only (`LICENSE`, SPDX `AGPL-3.0-only`).

**Why:** The product is meant to be run hosted as well as locally. The AGPL keeps changed versions open when they are offered
to others as a network service, not only when they are distributed.

**Impact:** none on scope or schedule. Any dependency added later must be compatible with the AGPL.

## 2026-10-09: Launch slice implementation choices

**Decided by:** built to the design; open for the project owner's review.

- **Facts are their own record kind** (`FACT-n`), not notes with a flag, so they can be looked up and undone on their own.
- **Refusal is per item:** a refused item is dropped and named; the rest of the assistant's work for that input applies.
- **Inputs longer than the limit wait for the PM** instead of being split (splitting is version 1).
- **Pasted text stays local:** a workspace's `sources/` folder is not committed; backups carry it with the database.
- **One database connection per thread,** so a reader never sees another thread's unfinished write.
- **A missing key is its own error** ("the key wasn't found"), apart from a key the vendor refused.
- **"Who is this?" and "Pick an owner" are answered on the item that waits** (What changed), not repeated in Follow-ups; a
  change with an unanswered question stays under Needs attention after Looks good.
- **Mark sent can be undone,** like every other reversible action.
- **`config/ui.yaml`** holds wording overrides, shortcut keys, the one-column width and how long toasts stay.
- **The UI uses system fonts,** loads nothing from elsewhere, and its content policy allows inline styles only for two fixed
  rules of the component library, by hash. People are picked with the browser's own list control, which works best on phones.
- **`cockpit evaluate --ai-config`** scores the PM's own accounts on the fictional cases without copying real data anywhere.
- **Browser tests** run against a test server whose stand-in AI gives each case's ideal answer, so they check the UI and the
  pipeline, not a model.

**Impact:** none on scope or schedule; all within the launch slice.

## 2026-10-09: UI review changes

**Decided by:** project owner, after a UI/UX and React review.

- **A queue, not a dashboard:** Today is the home screen, with one ranked list of things to do; panels are filtered views
  (version 1; the launch slice keeps a single column with What changed and Follow-ups).
- **One primary action per row** with the rest in a menu, and a **wording sheet** so internal terms never reach the screen.
- **Undo toasts instead of confirmations** for anything reversible; only send, publish and post confirm.
- **Keyboard first and phone friendly:** review shortcuts, one column on narrow screens, phone-critical tasks first class.
- **Edit in place before approving; evidence shown on every claim;** details by expanding rows, not tooltips; new items never
  push rows around.
- **First-run setup, real settings UX and WCAG 2.2 AA** accessibility.
- **Front-end architecture:** TanStack Query with server-sent events from the event bus, a TypeScript client generated from
  OpenAPI, React Aria Components, CSS variables for theming, a string table, sanitized rendering with real link domains, strict
  content policy, Playwright with axe.

**Impact:** launch slice gains the UI foundations (about one to two days of build time, no owner time); Today as the queue,
first run, settings UX, side-by-side diffs, virtualization and phone approval flows land in version 1 (milestone 7). Delays
nothing.

## 2026-10-09: AI review changes

**Decided by:** project owner, after an AI systems review.

Launch slice (impact: about a day of build time; owner time is reading one evaluation report; delays nothing else):
- **Evidence on claims:** ops that assert something quote the exact words from a cited source; the quote must be there
  (invariant) and should fit the target (`evidence-fit` lint). Why: with records by id, the dangerous error is a real but wrong
  target; evidence exposes it, gives an audit trail and makes injection harder.
- **Per-task op lists and small schemas, plus deterministic JSON repair, and parameters per task kind.** Why: large schemas
  degrade cheaper models and weak structured-output endpoints.
- **First evaluation set in the launch slice**, deterministic scoring, several runs per case, comparing a low-cost model with a
  stronger one. Why: the model choice should rest on evidence, especially a low-cost one.
- **Provenance everywhere; lessons from inputs are proposed until the PM accepts them;** untrusted-derived glossary meanings are
  shown as data. Why: lessons and glossary entries reach every later packet, which made them a place for injected instructions
  to persist.
- **Input cleaning and one input per call.** Why: quoted history and signatures waste tokens and create duplicate actions;
  several inputs in one call lower accuracy.

Version 1:
- **Escalation on failure** to a stronger tier on deterministic signals only.
- **Three-layer cache layout** with a frozen batch prefix and no volatile values in it.
- **Reproducible runs:** packet fingerprint, versions, parameters, model as served, upstream host; `cockpit replay`; pinned
  aggregator hosts.
- **Budget defaults lowered** to $0.25 a run, $2 a day, $30 a month, warning at 80% (applies from the launch slice).

## 2026-10-09: No code fixer in the product

**Decided by:** project owner.

**What:** The AI code fixer is removed from the product entirely, in every horizon. The product never writes or applies changes
to its own code or to a workspace's plugins. Automation problems are recorded and explained; a problem the PM wants looked at,
or a request no op can do, becomes a report (`dev.request`, now an outbound op) that the PM approves and sends to the
maintainers through a configured route (clipboard by default). Requests about other projects' code remain handoffs. The
`code-fix` tier, the `fix` task kind, `fixer` config, the merge-on-Apply machinery and proposed-fix UI are gone; the "Fix it"
button becomes "Draft a report".

**Why:** The fixer was something the owner wanted for their own development, not something people installing the product should
have: an AI changing installed code can break installations in ways their owners can't diagnose. Development happens in this
repository with the developer's own tools, outside any installation. **Impact:** removes a milestone 11 feature; simplifies
the core and the security model. Supersedes the fixer parts of the earlier entries ("Fixes merge on Apply", "The fixer changes
the workspace, not the product", "A code fix is the last resort"), whose lessons still apply to any developer tool built later.

## 2026-10-09: Launch slice uses only the OpenAI-compatible adapter

**Decided by:** project owner.

**What:** The launch slice builds one AI adapter, `openai-compatible`, which works with a key from most vendors (including
low-cost ones), aggregators and local model servers. Native adapters for vendors with their own API format move to version 1
(milestone 10). **Impact:** less work before the go/no-go; any vendor is still reachable at launch, directly or through an
aggregator. Delays nothing.

## 2026-10-09: The PM's own AI accounts, any vendor or aggregator

**Decided by:** project owner.

**What:** The AI layer is built around the PM's own accounts. Provider kinds: native vendor APIs (`anthropic`, `openai`
adapters, more as plugins), any OpenAI-compatible endpoint through one generic adapter (many vendors such as xAI, inference
hosts, local model servers), aggregators (`openrouter`, with its catalog and routing options such as refusing providers that
collect data), and command-line agents signed in as the PM. Capabilities and prices are per model, from each provider's catalog
(`models()`), with config overrides. Settings has an Add account flow (keychain for the key, Test, model list, tier choice,
data level starting at `open`, evaluation). Fallbacks may cross accounts and vendors.

**Why:** People want to use the accounts they already pay for, and aggregators reach many vendors with one key; per-adapter
capabilities can't describe an aggregator's hundreds of models. **Impact:** launch slice uses `openai-compatible` plus one native
adapter on the owner's key (no extra work: one adapter was planned, and the generic one covers most vendors); the aggregator
adapter, catalog and Add account flow land in version 1 (milestone 10). Delays nothing.

## 2026-10-09: Playbooks, ask the assistant, and project management support

**Decided by:** project owner.

- **Positioning:** a project management assistant, not a PMP replacement or a methodology tool (design 1.5).
- **Playbooks** (3.8): the core ships best-practice guidance for project support and each pack for its field, as guidance
  files, default rules, checklists, glossary seeds, lints and evaluation cases. The workspace's rules override entries by id
  (`config/playbooks.yaml`). Playbooks are scanned like code and change only by release; good workspace rules can be proposed
  upstream. Impact: core playbook first version in the launch slice (it is the guidance milestone 2's notes task needs anyway,
  organized as a playbook); publishing playbook with the publishing pack in version 1. Delays nothing.
- **Ask the assistant** (6.25): ad hoc requests answered from the records with the playbooks, so one-off PMP work doesn't need
  built-in features. Impact: version 1, should.
- **Project management support** (6.24), from the PMP review, accepted into the design now because adding them after the data
  model and screens exist would cost a migration: project issues and assumptions, optional risk fields and reviews
  (`config/raid.yaml`), one suggested escalation for long-unanswered questions, communication cadence on people, meeting
  agendas per attendee. The automation `Issue` record is renamed `Problem` so "issue" keeps its project meaning. Impact:
  version 1, could (the rename is a must, being only a name). Delays nothing in the launch slice.

## 2026-10-09: Project plan, first user and design 1.0 baseline

**Decided by:** project owner, after a project management review.

- **No employer involvement.** This is a personal project on the owner's own account, generalizing ideas from a private tool
  the owner built for their own use. No code, data or systems move between them; only ideas. Recorded as risk R9, closed.
- **First real user: the owner's literary imprint**, in a private workspace, starting with its first book launch on
  2026-12-01. The publishing pack moves to first in the build order (milestone 8); the workplace pack becomes the reference
  pack on fictional data (milestone 9); the personal-projects pack drops out of the plan (it stays as an example in Part 3).
  `demo-b` becomes a fictional small imprint.
- **Launch-safe schedule:** under 5 owner hours a week; a trimmed launch slice of milestones 1 and 2 by 2026-10-30; a go/no-go
  that day; a November freeze; the launch never depends on the tool (`docs/project/schedule.md`).
- **Dependencies and baselines join the core** (6.23): a launch is a chain of lead times, and slips need a baseline to measure
  against. Impact: version 1, must; not in the launch slice. Resetting a baseline is a system op.
- **Design 1.0 is the scope baseline.** From here, changes need a one-line impact note in this log (`docs/project/scope.md`).
  The other PMP suggestions (escalation, communications plan, agendas, risk scoring, PM issues and assumptions) wait there as
  candidate changes.

## 2026-10-09: Packet layout and read-backs, second round with the first design's author

**Decided by:** project owner, on the second-round answers from the first design's author.

- **Packets: stable first, request last.** Instructions, glossary, rules, lessons and all open items come first in a fixed
  order; the input comes last. Adapters with the `prompt_caching` capability mark the stable prefix. Why: the open-items list
  is now the largest and most repeated part of most packets.
- **Open items trimmed by size, not rule.** Full form ("[project] text (owner, due) → how to close it") for the request's own
  projects; other projects switch to compact form (id, owner, title, no closing hint) only past `open_items.compact_share` of
  the budget. Why: real counts were about 50 open actions and 10 questions for one PM with about 20 projects, about 3,000
  tokens, well within budget; the closing hint roughly doubles each line and only the request's own projects need it.
- **Read-backs show effects and overlaps:** applies to, doesn't change, overlaps with, and a dry-run count against current
  data; rules carry a structured target to compute them. A contradiction with an existing rule or setting pauses even a
  PM-typed rule until the PM picks which wins. Why: the misreadings seen in practice came from rule collisions and corrections
  aimed at the wrong place, which a restated rule wouldn't reveal but a count and an overlap would.

## 2026-10-09: Changes from the first design's author

**Decided by:** project owner, on the review by the author of the first design, who ran it daily.

- **Recovery is a tested feature.** The ledger is exported with the records; `import(export(db))` round-trips in the self-check;
  `cockpit restore --as-of` and single-record restore from the ledger. Why: restoring from git history was used in practice,
  and an export that can't be loaded back is only an archive.
- **Off-device backups in local mode**, with a Today line and header mark until one succeeds and the last backup's age always
  shown. Why: the biggest open risk of the first deployment was the whole knowledge base on one laptop.
- **Breadth waits for use:** hosted mode, packs beyond the second and social media start after the reference pack is in daily
  use.
- **The packet replaces browsing:** it always carries the glossary, active lessons, applicable rules and every open action and
  question; new `glossary.add`, `glossary.update`, `lesson.add` ops; bounded search lookups over sources and records.
- **PM-stated system ops apply at once with a read-back and Undo;** only system ops from inputs or the assistant's own initiative
  wait for a confirm. Why: the risk with the PM's own rules was misreading, which a read-back catches and a confirm doesn't.
- **Undo groups:** dependent ops are restored all or nothing; outbound can't be undone (reverting drafts, "already sent").
- **Owners are a list** (shared ownership is deliberate in some programs); team-only owners are refused and an action without a
  known person is held for "Pick an owner".
- **Lint outcomes depend on destination:** after one return, anything reaching another person is held for the PM; internal items
  warn. Missing links on questions to others, restricted content on the wrong audience and unreadable output are invariants.
- **Gaps from running it:** runner errors classified only from exit code and error stream; every waiting state shows why and until
  when; corrections checked against the data first; audiences per destination instead of open versus restricted; shared masters
  with lock checks and outside edits as changes; connectivity checked before refreshing, and failed refreshes stay stale; edits by
  our own accounts marked as ours; requests about other projects' code handed off (`config/code_owners.yaml`), restoring the
  handoff route the first design had and the restructure had dropped.

## 2026-10-09: Systems review changes

**Decided by:** project owner, after a systems design review of the whole design.

- **Database and ledger instead of files plus git as the store.** SQLite is the system of record; every applied op is written
  to an append-only ledger in the same transaction; records carry versions; ids come from sequences; jobs and the single
  running instance use leases; `data/` becomes a readable JSON export committed to git. Why: half of the storage rules
  (merge-on-save, one writer, ids never repeat, undo only if unchanged, one scheduler) were database guarantees rebuilt by hand
  on files, each learned from a failure. Undo becomes a reverse changeset with field-level conflicts instead of file restores.
  Supersedes the storage part of the 2026-10-08 technology stack entry.
- **Ids, not names.** Records refer to people, teams and projects by id; names are rendered. Why: storing "Team (Full Name)"
  strings is what required a names normalizer on every write, a name sweep and a rename reference index across every copy.
- **Op tiers and untrusted input.** Every op is data, outbound or system; system ops (rules, sources, scope, config, plugins,
  code) never apply automatically from an input. Packets mark untrusted content; lookups only reach configured sources;
  evaluation includes hostile inputs. Why: the design had no prompt-injection model, and mailbox and social plugins plus hosted
  mode make that exposure real.
- **Invariants and lints.** Firm checks always refuse and can't be lowered; fuzzy checks (wording, keyword-matched date
  questions, near-duplicates) return the changeset once, then warn, with severities in `config/checks.yaml`. Why: fuzzy checks
  that refuse produce false positives that push people to switch checks off.
- **Walking skeleton first; extension points marked 1.0, core only or planned.** The build plan reaches a version the PM uses
  in milestone 2 (paste-in, one AI task, about ten ops, the ledger, clipboard, a minimal UI). Only the extension points the two
  packs use are frozen at plugin API 1.0. Why: fifteen milestones before daily use, and sixteen hooks before any plugin, freeze
  guesses.
- **Gaps closed:** quality signals from the PM's corrections and private evaluation cases (6.20); standing rules as
  `config/rules.yaml` entries with a review that merges, retires and promotes rules into config (6.21); config versions and
  migrations, presets, basic and advanced levels, `config explain` (4.0); honest plugin security (declared reach is enforced on
  what the core hands out, not a sandbox, 12.3); one running instance per workspace; packet size budgets (6.6); retention and
  forget-a-person (4.15, 12.4).
- **The design is split into one file per part** under `docs/design/`, keeping section numbers, with a reading map in its
  README. Why: at 1,400 lines every coding session paid to read most of it.

## 2026-10-08: Every source is a setting

**Decided by:** project owner.

**What:** Where anything is looked up (a page, page tree, query, folder, feed, field name or schedule) is always configuration,
never code or default prompt text. Core and bundled plugins refer to sources by config key; default prompt templates use
template variables filled from config. Packs ship source settings as templates with placeholders that the workspace fills in,
with a Today setup line until it does. The specificity scan now also reads page titles, queries, folder paths and field names
from the fictional workspaces' config, and scans default prompt templates as well as code.

**Why:** Rules like "look on the release page" are easy to write straight into code or prompts while building for one
deployment, and each one ties the product to that deployment's tools and page layout.

## 2026-10-08: Lessons from the original deployment since the first design

**Decided by:** project owner.

Each came from a failure in the original deployment.

- **Other areas, even when named in minutes or program pages.** Domains now match owner labels as they appear on pages and in
  minutes, and the applier refuses an action whose owner label matches another domain. The owner described this as
  `other_team_owners` and `program_managers` per area; in the product they are each domain's `match.owners` and `contact`.
- **Dates are looked up, not asked.** New `config/facts.yaml` and fact resolver (6.19): an item's release comes from the
  delivery tracker or the tracker item's sprint or fix version, the release's production date from the delivery team's schedule
  page, and nothing found means TBD. The applier refuses questions for those facts, and any date question to the people listed
  in `no_questions_to`. This is a separate file rather than part of `scope.yaml` (where the owner first put it) because it is
  about where facts live, not whose area something is, and other packs need the same mechanism (publication dates, for example).
  Why: people were asked for dates that a schedule page already held, and the answers went stale.
- **Fixes merge on Apply.** A proposed fix keeps the original files and Apply runs a three-way merge, with a union merge for
  Markdown; only a real conflict stops it, and then the fix is redone automatically. Why: a whole-file staleness check made
  nearly every fix on a busy file go stale. The UI never offers an instruction it can't carry out, and a fix shows and is counted
  only on its issue card.
- **Rename is one op.** `record.rename` updates every stored reference through a reference index and keeps the page id, so the
  page is renamed in place. Why: renames done as several edits missed places and broke links.
- **A code fix is the last resort.** `dev.request` must show that no existing op fits; data that needs a new op waits with its
  fix and runs after Apply. Why: requests that ops could do became code fixes, and data changes needing a new op were refused by
  the running applier.
- **Ids never repeat.** Closed ids are retired. Why: a reused question id made old references point at the wrong question.

## 2026-10-08: Scope is enforced by the applier, with named domains and one contact each

**Decided by:** project owner.

**What:** `config/scope.yaml` gains `domains` (other areas, each with match patterns and one `contact`, usually that area's
program manager), `cross_domain` (impact-only questions, to the contact only, batched) and `unclassified` (ask the PM; never
tracked by default). The applier refuses actions owned by anyone outside the tracked area and questions to anyone outside it,
except an impact question to a domain's contact that names the tracked item it affects. A scope sweep finds existing actions and
questions that break this and files one bulk decision to the PM. A new `other-domain` triage matcher closes changes that sit
entirely in another area. One scope resolver is the only place scope is decided.

**Why:** In the original deployment, scope was advisory: the AI was told what to track but nothing stopped it. Changes on shared
pages that mixed several teams' work produced action items and detailed questions for people in other areas, who don't answer to
the workspace; that work is the program level's concern. The PM's inbox filled with follow-ups that should never have existed.
Making scope a deterministic check, with one named contact per other area and only impact questions allowed, stops the failure
at the write path instead of relying on the model.

## 2026-10-08: Local and hosted deployment from the same code; configuration first

**Decided by:** project owner.

**What:** The app runs in two modes, set by configuration: local (on the PM's computer, reachable only from it) and hosted (on a
web host the PM controls, at the PM's domain, optionally under a path such as `/admin` and optionally hidden from anyone not
signed in). Hosted mode requires real sign-in (pluggable auth providers) and refuses to start unless a set of deploy checks pass.
Packaging lives in `deploy/`: one container image plus a recipe per hosting target, starting with a tunnel to a machine the PM
owns and then a container host. Every setting can come from files, environment variables, flags or profiles, and is editable in
a Settings panel generated from the config schemas.

**Why:** The owner wants to run the product locally or on a web host, behind security checks, at a configurable hidden path, and
to change an installation without changing code. Hiding a path is not security on its own, so the deploy checks make real
sign-in, HTTPS and secret handling a condition of serving. The engine needs long-running jobs, a file system and git, so hosted
targets run it as a container or a process, not as short-lived edge functions. This replaces the earlier "local only" part of the
technology stack decision.

## 2026-10-08: Design recast as a generic core with plugins

**Decided by:** project owner.

**What:** The design is now a base for expansion, not a single-purpose tool. The core keeps only the generic loop (watch,
triage, dispatch, apply, review, send out, follow up), its safety rules and a set of extension points. The original workplace
use becomes the reference pack (design Part 9), built on the plugin API like any other pack. A second, smaller pack (personal
projects) is in the build plan to prove the extension points serve a different kind of work.

**Why:** The owner wants to use the same base for other kinds of work later (publishing support, personal projects, social
media). Building the first use as a pack, from the start, keeps workplace-specific behavior out of the core.

## 2026-10-08: Outbound content goes through channels and one approval gate

**Decided by:** project owner.

**What:** Publishing wiki pages becomes one case of a general model: records render into drafts for channels (pages, messages,
email, posts), and the publisher sends only drafts whose exact content the PM approved. Scheduled sending is allowed only for
approved content. Autonomous sending is not a goal.

**Why:** Social media and publishing plugins need outbound targets other than wiki pages. Putting every target behind the same
approval gate keeps the core promise ("the AI drafts; the human approves everything outward") as the product grows.

## 2026-10-08: Technology stack

**Decided by:** project owner.

**What:** Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff; React + TypeScript with Vite and Vitest. Plugins are Python
packages found by entry point or by folder. Storage starts as files in the workspace git repository behind a repository layer.
The app runs locally for one user.

**Why:** The design already called for Python and React. Pydantic generates JSON Schema from the same models that validate config,
records, ops and manifests, so the AI's output schema and the validator can't drift apart. Entry points give installable plugins
without a custom registry. A local, single-user app keeps the security model small until multi-user is needed.

## 2026-10-08: Changesets are JSON

**Decided by:** project owner.

**What:** Changesets are JSON documents validated against a schema generated from the op registry. Human-edited config stays
YAML.

**Why:** The design called them YAML in one place and JSON in another. AI APIs return structured output as JSON, and a generated
schema gives one source of truth.

## 2026-10-08: Naming fixes

**Decided by:** project owner.

**What:** The meeting entity is `Meeting` (was `Task`); a call to the AI provider layer is an `AiTask`. Page-specific ops became
record ops (`record.set`, `record.add`, `record.del`, `record.log`). `config/pages.yaml` became `config/render.yaml`. Tracker- and
wiki-specific triage matchers got generic names (`container-not-mapped`, `child-item`, `unknown-key`).

**Why:** "Task" meant two different things. Page and wiki names don't fit outputs like messages and posts.

## 2026-10-08: Workspaces live outside the repository

**Decided by:** project owner.

**What:** Real workspaces are separate git repositories outside this one, found by `--workspace` or `COCKPIT_WORKSPACE`. Only the
two fictional workspaces are committed, as fixtures, and `.gitignore` admits nothing else under `workspaces/`. The specificity
scan accepts `--workspace` to check code against a private workspace without copying its contents into the repository.

**Why:** Keeps real names and data out of the product repository, and lets the scan catch a deployment's specifics, not only the
demo ones.

## 2026-10-08: The fixer changes the workspace, not the product

**Decided by:** project owner.

**What:** Proposed fixes may change a workspace's config, rules, prompts, templates and private plugins. A fix that needs the core
or a bundled plugin is written as a patch and an issue for this repository.

**Why:** Applying AI-written fixes to an installed engine would make each deployment drift away from the product.

## 2026-10-08: Design document moved to `docs/`

**Decided by:** project owner.

**What:** `DESIGN.md` moved to `docs/DESIGN.md`, where `CLAUDE.md` already pointed. The copy of `CLAUDE.md` that was embedded in
the design was removed; `CLAUDE.md` is the only copy.

**Why:** One copy of each document, at the path the other documents use.

## 2026-10-10: Follow-ups: Copy marks sent, and sent items have their own view

**Decided by:** project owner.

**What:** Copy records the message as sent at once, with an Undo toast; there is no separate Mark sent step. Follow-ups has a
filter, "To send" (default) and "Waiting on them". A person's card under To send lists only what is still to send, with the
message and Copy. Items already sent or told appear only under Waiting on them, grouped by person, one line each ("sent
<date> (N days)") with their own step (They finished it, Record reply). The PM's own decisions stay under To send.

**Why:** Items already sent sat among items still to send and looked unsent; a second click after Copy was easy to forget.

**Impact:** Design 7.5 and the wording sheet. Each question in the follow-ups response carries its sent date. No change to
scope or to the ops.

## 2026-10-13: A project's priority is held for the person, not refused

**Decided by:** project owner (the phase L0 item in the roadmap); wording by the builder.

**What:** `project.priority` is person-only (design 5.1, 6.7). The assistant's `record.set` of it is held and shown as
waiting for the person, like a plugin's person-only value; releasing it applies it. A person-only declaration with no
values means every value of the field. The person's own change (a screen edit, or a person action) applies at once.

**Why:** Design 6.7 said the assistant's op was refused as an invariant, while the code's person-only mechanism holds the
op, so the proposal isn't lost. A priority has an open set of values, so the declaration cannot list them.

**Impact:** Design 5.1, 6.7 and the product-rules table in Part 8 say so. Plugin guide wording for `person_only`
regenerated. No change to scope.

## 2026-10-13: Lint settings live under `tuning:`, and the near-duplicate check includes done actions

**Decided by:** project owner (through the coordinating session); the builder found that the earlier code skipped done
actions only by the name of a variable, with no comment, test or decision behind it.

**What:** `config/checks.yaml` gains `tuning:`, one typed entry per core lint, keyed by the lint's name with underscores.
The first is `near_duplicate_action.similarity` (0 to 1, default 0.8). `lints:` and the plugin contract are unchanged.
`near-duplicate-action` compares with open and done actions, as design 4.17 says.

**Why:** A setting "under the lint" would have changed `lints:` from a map of severities, which plugin lints and their
overrides rely on. A sibling key keeps that contract and gives later lints (such as `near-duplicate-question`) a place
for their settings.

**Impact:** Design 4.17, 6.7 and Part 8 say so. No change to scope.

## 2026-10-13: Set-aside corrections are signals, learning skips set-aside mail, and a deletion compares as matching

**Decided by:** project owner (the phase L0 item "After A5"); wording by the builder.

**What:** A new signal kind `set_aside` is recorded when the person sets mail aside by hand (refs: the requests it closed,
else the snapshot; note: the section). Learning reads requests and snapshots only through `engine.set_aside.learnable`,
which leaves out anything marked set aside. The synced folder's history comparison applies each confirmed set-aside's
deletion to both histories before comparing, so the redacted earlier values match their originals.

**Why:** Set-aside corrections were the one correction left unmeasured, mail the person said is not work must never teach the
assistant, and a deletion on one computer read as a divergence on the other.

**Impact:** Design 5.1 (signal kinds), 5.2 (the comparison), 6.5 and 6.20 say so; plugin guide regenerated. The learning pair
for set-aside mail waits for L4, which defines the fixture format. No change to scope.


## 2026-10-13: A usage limit pauses its account; an empty or failed run is retried by itself

**Decided by:** project owner (the phase L0 item "No silent stops" in the roadmap); wording and settings by the builder.

**What:** A quota that comes with a reset time, or a request to slow down that asks for longer than the router will wait or
keeps coming, pauses that account until the reset (kept in the workspace's private folder). Requests that need only paused
accounts stay queued, say whose limit resets when, and the worker runs them again by itself at the reset. An empty or
unreadable answer, a timeout, an outage, another failure and the new `no_output` outcome (an agent that finishes without
an answer) are retried by themselves: `dispatch.retries` (2) times, the wait starting at `dispatch.retry_wait_seconds` (30)
and doubling; then the request comes to the person with why. A limit with no reset time is not a pause. An agent's reset
time is read from its error stream by the account's `errors.reset` patterns. Held work and paused accounts are queue lines
(`restart`, first in Decide; `paused`, in Risk).

**Why:** Without these the assistant stops without a word on the first quota day, and the person thinks it is broken.

**Impact:** Design 4.9, 5.1, 6.15, 6.16 and Part 8. New settings `dispatch.retries`, `dispatch.retry_wait_seconds`,
`ai.rate_limits.pause_seconds` and the agent `errors.reset`, with demo values. `Request` gains `retries` and the causes
`paused` and `retry`. No change to scope.

## 2026-10-13: Diverged copies are settled from a screen; sign-ins and add-on changes are audited; a shared folder's edits are untrusted

**Decided by:** project owner (the phase L0 items); the way it is built by the builder.

**What:**
- *Settling from a screen.* When this computer and the synced folder have diverged, the app no longer refuses to start. It
  starts on this computer's own copy and holds the synced folder: nothing is written to it, its lease is not taken, and
  closing does not release it. Today shows a line (Choose which copy to keep) that opens a page with both sides in plain words
  and the two choices the command offered, each with what it does. A choice is only noted in the workspace's private folder;
  the next start carries it out through `keep` before the database is opened (so the check that the other computer has not
  opened the workspace still holds, replacing the database never happens under a running app, and any refusal drops the
  choice). Until then the person can take the choice back. The restart is the person's click.
- A running copy that lost the workspace to another computer gets the same line (Close this copy) and a page that says who,
  since when and how long until it can be opened here; there is nothing to choose.
- *Not done: the instance lease.* A copy that stopped without closing leaves the app's own lease held for up to a minute, and
  `cockpit takeover --force` takes it at once. A screen cannot settle that one: the app that would show it cannot run
  without the lease. It stays a command; the message says it.
- *The audit trail.* A new core record `audit_entry` (kind: sign_in, sign_out, plugin_on, plugin_off; subject; label; detail;
  when). Turning an add-on on or off is recorded by the settings save itself (so the guided routes, the screen's Undo and the
  general save all write it, in the same transaction as the `setting_change`); applying a template records the add-ons it
  turned on; a sign-in, a sign-out and a changed app registration that forgets a sign-in are recorded by the sign-in routes.
  Starting a sign-in, a refused one and signing out twice record nothing. No screen lists them until the Admin tab (phase E);
  the records are in the ledger and the export.
- *A shared folder.* `storage.sync.shared` (false). The folder step asks it (no default answer) and the folder's panel shows
  and changes it; it is a live setting. When true, edits found in the folder and working copies taken back from it are filed
  as an outside input (request origin `input`, changeset and ledger trust `untrusted`) with notes that say so; field edits
  and deletes are held and long text is a pending version, as before, and the person's release is their own decision.
- Authorship of an accepted passage from a shared folder is still the person's, since the review is theirs; a fourth kind of
  author is a plugin API question and is not part of this.

**Why:** The roadmap's phase L0 items: a screen instead of a command, an audit trail that starts before anyone needs it, and
an outside edit that does not count as the person's own words when others share the folder.

**Impact:** Design 5.0, 4.15, 7.7, 12.1, 12.7 and 12.8; the plugin guide (a new core record). New setting
`storage.sync.shared` with demo values. `GET/POST/DELETE /api/sync/handover`; the queue gains the `handover` line. No change
to scope.

## 2026-10-13: The restart and paused-account lines are drawn on Today

**Decision:** Today draws the two stop lines the queue already serves, at the top before the columns, one row each with one
primary action: Restart now for held work, and AI accounts for a paused account (wording "Pick another account, or wait: ...").
`GET /api/today/queue` gives a line's reset time on the person's own clock (their time zone).

**Why:** The rule is that a stop is a Today line, not only a chip; the engine built the lines but the screen showed none.

**Impact:** Design 6.15, 7.7 and 8.6 text, and the wording sheet. No new setting; no change to scope. The full ranked queue
stays in phase B.

## 2026-10-13: Input levels, folders in the last day, and local timestamps (phase L0)

**Decision:** The data level of an input is kept on its record: `source` and `file` carry `sensitivity` (named so because
`data_level` is a record type's own level on the base record). Its value comes from the hand-in's or upload's choice or the
watched source's setting, else its kind's (`watch.connector_data_levels`), else `watch.default_data_level`; only the person
changes it; a run is at the highest of its record type, its request and its source. The folder connector gives a file's
modified time as the item's `changed_at`, which the snapshot keeps for "Look at the last day". Machine timestamps with a
zone in an assistant's prose are rewritten in the person's time zone and `language.messages.date_time_format` before they
are kept; they came from the add-on's item text, copied by the assistant, not from anything the core adds.

**Why:** A source read later had no level; a folder item had no time; a note showed a time the person doesn't read.

**Impact:** Design 4.x (watch keys, `date_time_format`), 5.1 (source, file, snapshot), 6.7, 7.x. New settings
`watch.default_data_level`, `watch.connector_data_levels`, a source's `data_level` and `language.messages.date_time_format`,
with demo values. `sync.sources` stays unbuilt. No change to scope.

## 2026-10-13: No set-aside rule for a whole public mail domain (phase L0)

**Decision:** "Always for this domain" is never offered, and a domain rule is never saved, for a public mail domain (the free
mail services anyone has an address at). Only the sender rule is offered there. The core ships the list as data
(`engine/defaults/public_mail_domains.yaml`) and `watch.public_mail_domains_extra` adds the person's own; the effective list is
both, read at the moment of use. A domain matches only when listed exactly (case ignored): a subdomain of a listed domain is
not public, because an organization can run its own mail on one, and the regional and older names of a service are listed on
their own. A Set aside row, the answers to "This is work" and "Set aside", and Confirm all carry no domain for a public
domain; the sorting-rule save refuses one in plain words so a stale screen can't write it.

**Decided by:** the original designer, on review; accepted by the technical PM.

**Why:** One sender's correction on a personal address would otherwise hide or keep every contact at that service.

**Impact:** Design 4.x (a new `watch` key), 6.5 (the correction offers) and CHANGES section 35. New setting
`watch.public_mail_domains_extra` with demo values in both workspaces. `domain` on the Set aside row and on the set-aside
answer can now be empty. No change to scope.

## 2026-10-13: A lost network waits for the network and uses up no tries (phase L0)

**Decision:** A call to an AI account that could make no connection at all (the name did not resolve, or the connection
could not be opened) is a new error kind, `offline`, never `provider_down`. Any answer from the service, a 5xx included, and
any other break in the exchange stay `provider_down`; only the adapter decides it, from the kind of transport failure. The
router may still try the next account in the chain. When every account that isn't paused is offline, the request stays
queued with "Waiting for the network since <time>. Checking again at <time>.", the cause `offline` (`since`, `until`), and
`retries` unchanged, so being offline never uses up the tries a failing service gets and never brings the request to the
person. The worker looks again after `dispatch.offline_check_seconds` (60), never in a tight loop. Once a request has waited
longer than `dispatch.offline_line_after_minutes` (15), Today's queue has one line however many wait, asking the person to
check the network connection, with how many wait and since when; it goes when the work runs again. The command-line agent
adapter is unchanged: none of its errors says plainly that no connection could be made. A refused connection to an account whose
address is on this computer (localhost, a loopback address) is `provider_down`, since a stopped local server is not a lost
network. Only the first offline miss of a wait is recorded as a run; later looks record none until the request runs or the
wait ends another way.

**Decided by:** the technical PM.

**Why:** Design 8.6 says no network on waking is not a failure. A request run just after waking was tried three times in
about ninety seconds and then came to the person, who could do nothing about it, while the scheduled reads already waited
for the network without fuss.

**Impact:** Design 6.16 (error kinds, the wait), 8.6, 5.1 (request cause, run error kind), 4.9 (two `dispatch` keys), 7.7 (a
Today line) and CHANGES section 38. New settings `dispatch.offline_check_seconds` and `dispatch.offline_line_after_minutes`
with demo values in both workspaces. No change to scope.

## 2026-10-13: A start takes over from a copy on this computer that is no longer running (phase L0)

**Decision:** The instance lease's holder id begins with the process id (`<pid>-<random>`); ids without a process id (older
leases, any other writer) are unknown. A start that finds an unexpired lease takes it at once, without `cockpit takeover`,
when the lease was written on this computer (same host name), its holder names a process, and that process is no longer
running (a signal-0 check: no such process is "not running", a permission refusal is "running"; where the platform offers
no safe check, such as Windows, the answer is "unknown", so the lease is refused as before). Otherwise it is refused as
before. The refusal says in plain words where the workspace is open: "It is already open in another window on this
computer. Close it there." or on another computer by its name; the command is named only for a copy that has stopped but
this computer can't tell (another computer, or no process id). `cockpit takeover` and `--force` are unchanged. One log line
records a start taking over. A reused process id counts as running, so the safe side is a refusal that waits out the
heartbeat.

**Decided by:** the technical PM.

**Why:** The app that would show a start-up screen can't run without the lease, so the stale-lease item could not be a
screen. The common case, a copy that crashed or was killed on the same computer, can be settled without any person action
because the computer can see the process is gone; only the cases it can't see keep the command.

**Impact:** Design 5.0 (one running instance, the lease paragraph in the handover screen item) and CHANGES section 40. No new
setting, no change to scope. Roadmap L0: the instance-lease sub-item is built.

## 2026-10-13: The assistant's header-only mail sorting (phase L0)

**Decision:** Mail the rules can't place is sorted by the core task kind `sort-mail`, one run per `watch.sorting_batch`
(25) of headers, when `watch.sorting` is `ai` (the default). Choices the design left open:
- **Role and tier:** role `write`, tier `routine`. `check` would put the run on another account than the one that wrote
  some work, but there is no work, and the demo workspaces map `check` to the strong tier; `research` gathers from
  sources. `write` leaves the tier to `ai.tasks.sort-mail.tier`, else the default low-cost tier. A workspace that maps the
  `write` role to a strong tier also sorts there, unless it sets the kind's own tier.
- **Where items wait:** a new mail item is written and handed in only after its batch is answered, so a message is set
  aside from the start and never queued for the assistant. Only new mail is sorted; a changed message keeps what was
  decided about it (set aside by the assistant stays set aside, work stays work). Mail a `never` rule keeps is not sent to
  the run. "Look at the last day" sorts what a first read only noted.
- **When it can't run:** no account, a budget used up, no first go, an estimate above the amount to ask about, an account
  paused or failing, or an answer that fails its checks after the escalation: the mail is handed in as work, and the
  read's note says why. A run never waits for a go, because the mail waits for it. Before the first go in a workspace the
  run isn't made (it would spend before the person's first go), so the first read's mail goes in as work. The first go
  then sorts it first: the mail requests waiting for the go that were never sorted go through the run (the go covers
  it), personal and sales ones are closed as set aside and only the rest run. Mail the person pulled back as work is
  left alone.
- **No request:** `Run.request` is optional; a run that serves no request, such as sorting, has none.
- **Learning pair:** no learning-pair fixture format exists, so the pair is a test (`tests/test_mail_sorting.py`).

**Decided by:** the technical PM's brief; the choices above were made by the builder and reviewed by the technical PM, who
changed one: a system op (a rule, a value list, a recipient) from a typed note waits for the person, as from any input,
because the note may carry someone else's reply (`tests/test_note_input.py::test_a_change_to_how_the_product_behaves_from_a_typed_note_waits_for_the_person`).

**Why:** Newsletters and personal mail the rules miss should land in Set aside within a read, at a fraction of a cent, and
a guess must never hide mail.

**Impact:** Design 6.5, 4.x and CHANGES section 39. New settings `watch.sorting` and `watch.sorting_batch` (live), demo
values in both workspaces, the `sort-mail` prompt and playbook practice. No change to scope.

## 2026-10-13: A file kind declares the data level of what is added under it (phase L0)

**Decision:** `registrar.file_kind(...)` takes an optional `data_level` (`open`, `internal` or `restricted`; none means
internal). A level the manifest's `requires.data_levels` doesn't list refuses the add-on, in the same words as for a record
type. A file added under the kind takes that level unless the person chose one at the upload: the upload's `data_level`
is now optional (it was `internal` when left out), and the upload screen has no level picker, so it never sends one and
every screen upload takes its kind's level. The person's explicit choice, higher or lower, stands. A file a person action
makes (`file.add`) takes its kind's level. Only the person changes `sensitivity` afterwards (it was already person-only,
and a pack's ops cannot write core records). A run about a file or a source now counts the level kept on it, which the
0.3.60 text promised and the code did not do for a run named on the file itself. A file a working copy writes (hand-out or take-back) takes the highest of its record type's level and the level kept
on the record, so it is never less sensitive than what it was made from. Files read into a source by a connector
are unchanged: a source's level is its own setting, else its connector's, else the default (4.x), already a declared level.

**Decided by:** the technical PM, on the writing pack builder's question 192.

**Why:** An unpublished document uploaded to be imported is confidential by nature, yet it arrived as internal, so a run on
it could go to an account allowed only internal material. The kind knows what its files are; the person can still lower
one, because they own the material.

**Impact:** Design 3.3 (file kind), 5.3 (files), 5.1 (the `file` record) and CHANGES section 41. Plugin API 0.3.61. No new
settings. No change to scope.

## 2026-10-13: Wording checks skip links, and a retry that applies retires the attempts before it (phase L0)

**Decision:** Every check on words reads the words: one helper takes out links and the input's own quoted text first
(the screen-text check, `blocked-wording`, `run-on-list`, `near-duplicate-action`, `evidence-fit`). The applier knows the
input, so it removes an op's evidence, its cited passages and quoted passages that are in the input; a screen field holds a
string only, so it removes links and nothing more, and a field that holds the input's own words is plain text. The
`never-shown` check stays whole, as it guards against a leak. Separately, attempts are linked by the request they answer
(`previous`): when a request's changeset applies something, the requests it redoes are retired (`request.superseded_by`
names the later one; held changes refused with a reason, routing questions dropped, open proposals and reports dismissed;
what was applied stays), and every costly follow-up (a queued try, a fix round, the escalation) first checks its request is
still queued or running and not replaced.

**Decided by:** the owner's plan item from the original designer's lessons; the field and the wording of the reason were
the builder's choice, for review.

**Why:** A link or a quoted sentence is not the product's wording, so a check on wording refused text it should not.
A request redone after a refusal left the old one's held items and questions on Today after the new one applied, and a
try queued for a request that had since applied would have run and cost money.

**Impact:** Design 6.7, 5.1 (the `request` record, one optional field), 10 (the screen check) and CHANGES section 44. The
plugin guide is regenerated (a core record changed). No new setting. No change to scope.

## 2026-10-13: A note on a button is the person's own words, handed in after the change (phase L0)

**Decision:** A note typed with Mark done, They finished it, Followed up, the choice of an owner, an answer, or added to an
action's notes is saved as a source marked `trusted` (kind `note:<button>`, the item's project) and queued as the usual notes
work with the item as its `about`, unless it is a bare confirmation (fewer than `language.bare_confirmation_words`, 4,
words and no link). The dispatcher now takes a request's trust from its source: outside content stays untrusted; a source
that is the person's own words does not make the run untrusted. Undo of the button's change leaves the note and its request.
Each route that takes free text is declared `to_assistant` or `local_only` in `api/free_text.py`, and the self-check fails
for an undeclared one. "Reassign" has no route yet (phase B); the built form of giving an action an owner, picking one for a
held action, takes the note. A question has no notes field; its written answer is the note.

**Decided by:** the technical PM's brief; the choices above were made by the builder and are for review.

**Why:** A reply typed into a button was saved to the action's history and read by nothing; the same loss recurred for a
link, a new due date and a standing rule. The note is the person's, so the changes it leads to are the person's own note's
(system ops apply with the usual read-back once built, and a rule that contradicts one waits). The risk to review: a
teammate's reply pasted into the note box is outside content typed as if it were the person's own; the hand-in box is
where pasted material belongs (it stays untrusted there).

**Impact:** Design 6.5, 6.6, 6.9, 4.6 and CHANGES section 43. New setting `language.bare_confirmation_words` (live) with demo
values in both workspaces. API: optional `note` on the action status, They finished it, Followed up and pick-owner
routes; `request` on their responses. No change to scope.
