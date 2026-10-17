# From project support to a daily steward: what the core needs (accepted 2026-10-17, phase S)

The owner's ask (2026-10-17): "since we are turning this into a steward think about what we need to add to the design to
really dig into that. Most of what i originally designed came out of PM support, but this core needs to be full
featured." This is a proposal for the owner to decide on; nothing here changes the design until it is accepted, item by
item, with a note in `docs/decisions.md` and the design sections edited.

## What a steward is, in one paragraph

A good steward knows what you have promised and what others have promised you, notices what needs you before you ask,
gets the next step ready, reminds you at the right moment, remembers people and details so you don't have to, and never
acts in your name without your yes. The core already does the hard parts of that for work: reading what comes in, turning
it into actions, questions and facts with evidence, follow-ups with owners, learning from every correction, and keeping
everything outward waiting for approval. What it lacks is mostly **time** (reminders, recurrence, the shape of a day),
**the person's own life** beyond projects, and **capture from anywhere**.

## What the core has today (checked in the code)

People, organizations, teams, projects (nested), actions with owners and due dates, questions, follow-ups and Copy,
facts with evidence, rules, notes, files, sources and watchers (folder, mail, calendar), calendar entries of its own,
meeting series, stages, the knowledge records and the learning loop, Ask, Today with its queue, agenda, to-dos and "came
in", backups, add-ons. There are **no reminders at a time, no repeating to-dos, no notifications beyond counts, and no
daily or weekly review** (`engine/records.py`; nothing in the engine schedules a person-facing reminder).

## Proposed core additions, most important first

1. **Commitments both ways, from everything that comes in.** "I'll send it Friday" in your own sent mail or note
   becomes your to-do; "they'll get back to me by Tuesday" becomes a waiting-on with its date. Your sent folder is a
   source by default when a mailbox is connected. (Builds on actions and follow-ups; the change is reading your own
   words for promises, not only others'.)
2. **Reminders at a time, and notifications that reach you.** Any to-do, waiting-on, fact with a date or calendar entry
   can carry "remind me" (a time, or "the morning of", "an hour before"). Reminders appear as desktop notifications from
   the installed app's menu bar or tray (phase I) and as a Today line; the content shown follows the data level rules
   (counts only where content isn't allowed). Snooze is a choice on the reminder.
3. **Repeating to-dos.** "Pay the water bill on the 1st", "send the weekly update every Friday": a repeat rule on a
   to-do, using the same repeat engine the calendar needs for repeating events (open promise P17), each occurrence its
   own row that can be done, moved or skipped.
4. **The shape of the day: a morning brief and an evening wrap-up.** Morning: today's meetings with what to prepare for
   each, what is due, what you are waiting on that is late, and the three things that matter most (Top priorities).
   Evening: what got done (credited), what moved, what is left for tomorrow, one question if something looks stuck.
   The Monday briefing (phase B) is the weekly form of the same thing. Each is a page in the app and, if the person
   wants, a notification.
5. **Meeting prep and after-meeting capture for any calendar event**, not only series: before it, who is coming, what is
   open with each of them, the last notes and decisions; after it, "what came out of it?" takes a quick note that
   becomes actions, questions and facts like any other.
6. **Replies owed.** Mail and messages that ask you something and haven't been answered are their own Today group,
   oldest first, each with a drafted reply in your voice for you to edit and copy. "You haven't answered Ana in four
   days" is a line, not a guilt feed: the person can say "no reply needed", which the assistant learns.
7. **People memory.** Each person's record keeps when you were last in touch, what they asked of you and you of them,
   what they care about and how they like to be reached, and the dates that matter to them, all with evidence. Before
   you meet someone, the steward shows it; when you have gone quiet on someone you said you would follow up with, it
   says so once.
8. **Dates hiding in documents.** A letter, a contract, a receipt or a confirmation mail with a deadline, a renewal, an
   expiry, a warranty end or a booking becomes a fact with its date and, if the person keeps it, a reminder. Travel and
   booking confirmations become calendar entries of the app's own with their details.
9. **Areas of life, kept apart where they should be.** Work, home, a side project: top-level areas (projects at the top
   of the tree) with their own data level and the AI accounts each may use, so personal mail can be read only by a
   local model, say, while one Today shows everything that needs you. Filing, rules and learning stay per area.
10. **Capture from anywhere.** A global shortcut from the installed app opens a capture box over whatever you are doing;
    a forward-to address or a watched folder takes mail and files you send it; a voice note is transcribed (a new
    adapter capability, so any provider that can transcribe can do it) and handled like any note. The phone review mode
    (phase B) gains the same capture box.
11. **The steward proposes, with consent.** Patterns become one gentle line: "you've moved this three times: drop it,
    hand it on, or give it a time?"; "this is waiting on you and on Sam: shall I ask Sam first?". Each line has its
    choices and records what the person picks, so the next suggestion is better. (Builds on the governor's stale sweep,
    phase E, brought forward for the person's own items.)
12. **Talking to Reginald.** The conversation on a record (plugin question 190) becomes the core's main way to ask for
    anything: "what did I promise the landlord?", "draft a reply to Ana saying yes but next week", "move my Friday
    to-dos to Monday". Every change it proposes is a changeset the person keeps or drops inline, as everywhere else.

## Proposed for packs, not the core

The core stays a base; whole uses go in packs (CLAUDE.md, "The boundary"):
- **Project management pack** (phase P): what stays PM-specific today (status reports, stages for projects, RAID-style
  logs, the scope resolver's tracked area, schedules). An audit lists every PM-only concept in the core and moves it there,
  so the core reads as a daily assistant to anyone.
- **Life admin pack:** bills, subscriptions, renewals, warranties, household documents and their checklists. For bills,
  reminders only (owner, 2026-10-17: "I dont want to touch that here, but simple things like bill reminders is good"): a
  bill is a name, who it's paid to, its usual amount if the person wants it noted, its due day and how it repeats, found
  from the bill's mail or added by hand, with a reminder before it's due and "Paid" to mark it. No bank connection, no
  account balances and no cash-flow analysis. Even without the pack, the core's repeating to-dos, reminders and dates in
  documents (items 2, 3 and 8) already cover a bill reminder.
- **Travel pack:** itineraries from confirmations, packing and document checklists, time zone help.
- **Household pack:** shared to-dos and roles for a family, once organization installs with roles exist (design 11.8,
  after 1.0).
- The writing and publishing packs, as planned.

## Decisions for the owner

1. **Accept the twelve core additions** (or strike some), and their order.
2. **Calendar and mail stay read-only?** Today the add-ons only read. A steward would eventually propose calendar holds
   and send replies, always after your yes on the exact content (through the publisher, phase C4). Keep read-only for 1.0,
   or plan approved writes?
3. **Notifications:** desktop notifications from the installed app are proposed; should a phone get them too (a push
   service costs something and needs an account), or is the phone review page enough for 1.0?
4. **Areas of life:** separate areas with their own AI accounts in one workspace (proposed), or separate workspaces?
5. **When:** most of this is after phase B. Proposed order: reminders, repeating to-dos and the morning brief in phase B's
   last wave (they are screens on things the core nearly has); commitments both ways, replies owed, meeting prep and
   people memory as a new phase S right after phase I; dates in documents, areas, capture and voice after that, before
   phase C's packs; the PM audit with phase P.

## Review, 2026-10-17 (an outside review the owner brought), and what changed

The review's judgment: Thimbleby's strongest selling point is dependable memory for commitments across work and personal
life, and the plan should make that measurable and quick to experience. Checked against the design and the code; taken
into phase S (the roadmap has the new order):
- **Promises first** (review 1), with **how they resolve** (2): done, date changed, called off, partly delivered, or
  answered without answering; each a proposal with evidence, never a silent close.
- **Every promise shows why** (3): source sentence, owner, date and whether it was said or inferred (the `basis` facts
  carry), not a model's confidence score, which the design never trusts (checks decide, not self-reported confidence).
- **Drafted follow-ups are expected** (4) and **consent alone isn't unique** (7): the difference is promises kept across
  every source with the people around them, and the same controls for messages, calendar and learned rules.
- **A capacity check** (5) without automatic scheduling; **a five-minute first success** (8); **visible privacy between
  areas** (9); **missed-while-asleep recovery** (10, part); **the brief as changes, risks and what needs a yes** (11);
  **an attention budget** (12); **outcome measures** on the Quality screen (13, part).

Decisions the review raises, for the owner:
1. **Approved writes** (review 6): today mail and calendar are read-only and replies are copied. Sending a reply or
   placing a calendar hold after the person's yes on the exact content, with recipient checks and a visible sent/failed
   status, removes the copy-and-paste step. It needs the publisher (phase C4) and the add-ons asking for send and write
   access. Keep read-only for 1.0, or bring approved writes in?
2. **A phone when the computer sleeps** (review 10): a desktop app can't remind anyone while its computer sleeps. Options:
   (a) missed reminders shown on waking only (built in S2 either way); (b) the person's own calendar carries the alarm,
   with Thimbleby adding the reminder to it (needs approved calendar writes, decision 1); (c) a push service to the phone
   (costs something, needs an account); (d) a reminder mail to the person's own address (no new service, needs approved
   sends, decision 1).
3. **The first audience** (review 13): independent professionals juggling clients and personal life are suggested. It
   decides the walkthrough's examples, the store copy and which pack comes first after the core.

