# Part 1. The product

## 1.1 The idea

Someone running several projects (a program manager supporting a leader, an author with books in progress, a person with side
projects) spends much of the day noticing what changed, updating the places other people read, chasing people for answers and
keeping follow-ups straight. The information is spread across sources: pages, trackers, folders, mailboxes, calendars, feeds,
meetings and chats.

The cockpit does the noticing and the drafting. It watches the sources, has an AI assistant turn each change into proposed
updates, questions and action items, and gives the PM one screen to review, correct and send out.

The same daily needs sit under every kind of work, so the cockpit also serves a person who is only running their own days
(1.7).

**The AI drafts. The human approves everything that goes out.**

## 1.2 Who it's for

- **The PM (primary user):** whoever runs the work in a workspace: a program manager, an author, or anyone with a busy week.
  Reviews, approves, sends, publishes. Wants one screen that says what to do today.
- **Readers:** people who read what the PM publishes (a leader reading status pages, subscribers reading a newsletter). They
  shouldn't have to confirm routine updates.
- **Contacts:** people who receive questions and action items. They never use the tool; they get paste-ready messages to send
  from their own tools, or, once channels exist (1.4), messages sent after the PM approves them.
- **The assistant:** an AI with a configurable display name (e.g. "Archie"). The underlying model's name never appears in
  anything a person sees.

## 1.3 The core loop

1. **Watch** sources on a schedule through connectors, plus anything the PM hands in (pasted notes, emails, screenshots, files).
2. **Triage by rules first:** configurable rules close cosmetic edits, items outside the portfolio, repeats and other known
   no-op cases before the AI sees them. Every auto-closed item stays findable with its reason and can be pulled back.
3. **Package and dispatch:** remaining items are batched into packets (the change, the related records, the open actions and
   questions, the rules) and handed to the AI provider layer.
4. **The AI writes a changeset:** a structured file of typed ops. It never edits records, pages or files directly.
5. **Check and apply:** a deterministic applier checks the changeset (hard invariants, then softer lints), resolves names to
   ids, and applies it in one transaction, recording every field it changed in a ledger so any of it can be undone. Ops that
   would change the product's own behavior never apply automatically from an input. Invalid changesets go back to the AI once with the reasons before any human sees them.
6. **Review:** the PM sees each change with the AI's work nested under it and one set of buttons: Looks good, Send back, Undo.
7. **Send out:** records render into drafts for outputs (a page, a message, a post). Each draft waits with a readable diff or
   preview. Nothing leaves the cockpit until the PM approves that exact content. Built so far: Copy for messages. The
   publisher, channels and the Waiting to go out screen are designed and not yet built.
8. **Follow up:** questions and action items grouped by person. Copy puts one clean message on the clipboard; Mark sent
   records that it has gone, once the PM has sent it from their own tools. Items are aged until answered. A pasted reply goes
   back to the AI, which records it and acts on it.

Every step is generic. What gets watched, what records exist, what gets drafted and where it goes are supplied by plugins and
configuration.

## 1.4 What's core and what's a plugin

| Core (always present, generic) | Extensions (plugins and add-ons) |
|---|---|
| The loop: watch, triage, dispatch, apply, review, send out, follow up | Sources for particular products and services (connectors), and sign-ins to them |
| Records, changesets, the applier, undo, history | Where approved output goes: pages, email, blogs, social posts (channels; not yet built) |
| Questions, actions, meetings, people and ids, the ledger and undo | Kinds of things to track (record types), with their stages, checks and lints |
| Sources that speak open protocols: a folder, a feed, a calendar by its address, a mailbox over IMAP | Mail and calendar from named services, signed in as the person |
| The AI provider layer: routing, fallbacks, budgets, evaluation, and its adapters (any vendor, any OpenAI-compatible address, command-line agents) | Domain ops, triage matchers, AI task kinds and their prompts |
| The approval gate, diffs, the publisher (not yet built) | Person actions, file kinds, text formats and working-copy formats for documents |
| Scheduler, governor, automation problems and reports | UI panels, Today lines, scheduled jobs, event handlers |
| UI shell, Today and the core screens, guided setup, the Add-ons screen | Packs: bundles of the above for one kind of work, found on the Add-ons screen (1.8) |
| Plugin host, config schemas, self-check | The define-your-own kit is a bundled plugin that needs nothing special from the core (3.10) |

The core is complete on its own (1.8). To run with no outside account it ships a few built-ins: a fake connector (items from
settings), a folder connector, paste-in and upload, Copy to the clipboard, and a stand-in AI adapter that reads a hand-in by
plain rules and says it is a stand-in.

## 1.5 An assistant, not a methodology

The cockpit assists the person running projects; it doesn't replace their judgment or impose a methodology. It knows good
practice and applies it where it helps: in the core, how to support projects well (clear follow-ups, questions written for
their reader, decisions recorded); in each pack, how its kind of work is done well. That knowledge lives in **playbooks**
(3.8), which the PM can switch off entry by entry or override with their own rules.

Anything a playbook doesn't build in, the PM can still ask for: "what's waiting on me this week?", "draft a risk review for
the launch". The assistant answers from the records with the same playbooks in hand (6.25). Built-in features are for what
happens every day; everything else is a question away.

## 1.6 Not goals for the base

- **Autonomous sending.** Nothing goes out without the PM approving the exact content. A scheduled post is approved content
  that the PM scheduled; the cockpit never decides on its own to send.
- **Changing its own code.** The product never writes or applies code changes to itself. A problem the automation can't solve,
  or a request no op can do, becomes a report the PM approves and sends to the maintainers (6.13). Developing the product is
  done in its repository, with whatever tools the developer chooses, outside any installation. Installing an add-on the
  person chose, from a release whose checksum matches its catalog entry, is not the product changing its own code (3.11).
- **Multi-tenant hosting.** One deployment serves one workspace. It runs on the PM's own machine or on a web host the PM
  controls (Part 11), never as a shared service holding several customers' data. Storage sits behind a repository layer so a
  multi-user build can come later without rewriting the engine.
- **Real-time collaborative editing.** One writer at a time per workspace.

## 1.7 An everyday assistant

The core serves anyone running their own days, not only project managers (decisions, 2026-10-11). A solo person sets it up,
lets it read their mail and calendar, and is told each day what to do. A PM gets the same home and more: projects, people,
follow-ups and stages.

- **Today is the home.** It answers "what do I do now?" on one screen, and every other screen is a filtered view of the same
  records (7.0). Its main pane is a ranked queue, Needs you: held items, decisions, replies, work waiting for a go. Held
  items and decisions are always top-level lines. The order comes from rules, never from an AI model. Beside it, a context
  rail shows the day's Agenda, Your to-dos and what Came in, and on a wide screen an inspector shows the selected line. The
  layout is in 7.7 (decisions, 2026-10-11, "The UI redesign").
- **Events and messages carry structure.** A source can hand in a calendar event (start, end, place, cancelled) or a mail
  message (sender, received, unread) beside its text, so the agenda and the inbox show them without an AI call. The assistant
  still reads the text.
- **Signing in is the whole setup** for mail and calendar from a named service. A sign-in starts reading the inbox and the
  main calendar at once. Nothing has to be chosen first; the person narrows, adds or removes sources afterwards, and their
  changes stand (3.12; decisions, 2026-10-12).
- **It gets better at each project the more it sees.** Who answers what, what a term means here, which facts matter, how
  the person edits drafts for each reader, and every corrected mistake are written down as they are learned, and every later
  run reads them. Without this it is an inbox processor that is as smart on day 100 as on day 1 (6.22; decisions,
  2026-10-12 "The learning slice").
- **A visible result in the first five minutes.** Every default is chosen so that a real person sees a result with no file
  editing, no extra command and no demo data. After the guided setup and one sign-in, Today shows the day's agenda and what
  came in, with the assistant's work on it. A real workspace starts from `cockpit init` with no template (2.5).

## 1.8 What ships in the core and what is an add-on

**The core is complete on its own** (decisions, 2026-10-10). A person installs it, is guided through setup and runs their
work with it. No screen depends on an add-on. The free version is the core plus the define-your-own kit (3.10): item types
with fields, stages and checklists, what the assistant may fill, and what Today shows, all set on screens, saved and shared
as one template file.

**The core ships sources that speak open protocols.** They name no service, so they belong in the core (decisions,
2026-10-11):
- a folder of text files;
- a feed (RSS or Atom);
- a calendar, read from its private calendar-file (ICS) address, with the events in a window followed so a moved meeting or
  a new invitation is handed in;
- a mailbox, read over IMAP with an app password, without marking anything as read.

A calendar address and a mailbox password are secrets, kept like an AI key. The core also ships paste-in and upload, Ask the
assistant, guided setup, backups, the Add-ons screen, the kit with its starting templates and the example plugin.

**Add-ons for named mail and calendar services.** Some services offer no app password or calendar address, or their own
interfaces read more. For these, an add-on in its own repository names the service and reads the person's mail and
calendar. The core does the sign-in, through the service's own page, as the person (3.12). The add-on supplies the reading.

**Packs** are add-ons for one kind of work. They live in their own repositories, are found on the Add-ons screen from catalog
feeds (3.11), and prove the plugin API from outside this one (decisions, 2026-10-10 and 2026-10-11). This repository holds
the core, the define-your-own kit with its templates and the example plugin. The planned packs:
- **A writing pack:** from an idea or a manuscript to a finished book.
- **A project management pack** (decisions, 2026-10-12; designed, not yet built). An AI project manager that knows what is
  being done. The core keeps what every kind of work needs: actions with owners, questions, follow-ups, decisions and
  Today. The pack adds planning on top:
  - the plan: goals, phases, deliverables and milestones;
  - the schedule: durations, dependencies, a critical path, baselines and slips against them, where only the person
    rebaselines;
  - plans and schedules the assistant drafts for the person to approve;
  - at-risk lines on Today each day, and a weekly status report to send;
  - RAID: risks, issues, assumptions and decisions, with owners and review dates;
  - an interface (`pm/schedule@1`) through which other packs put their milestones into one schedule.
  Dependencies and baselines (6.23) and RAID with its reviews (6.24) belong to this pack, not to the core.
- **A publishing pack** (designed, not yet built): bringing a title to launch. When the project management pack is on, its
  launch plan goes into that schedule; alone, it is a plain list of milestones.
- **The workplace pack:** wiki pages and trackers at a workplace, the reference pack (Part 9). It is kept outside this
  repository.

Each pack works alone. When both sides of an optional interface are on, extra features appear (3.9).
