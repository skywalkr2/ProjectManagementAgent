# Questions for the original designer

Open questions from the build, written so each can be answered on its own. Each says what the code does today and the
default the build follows if the answer is "yes, that's fine". Answered questions move to `docs/decisions.md` and
leave this list.

**Answered: F1 to F14 (2026-10-19)**, yes to all with additions, in `designer-answers-2026-10-19.md`; folded into design
6.32 and the roadmap. The questions were in `designer-update-2026-10-19.md`, each saying what the app does today and the default the build follows if the answer is "yes, that's fine":
F1 gate phase S on a week of real mail; F2 hold the broader steward features behind it; F3 how "dependable" is measured;
F4 a coverage line on Today; F5 adding a missed promise; F6 older mail at first run; F7 tests for approved sending;
F8 the tester milestone's exit; F9 Today judged by the next action; F10 the risks register; F11 bundling the mail and
calendar add-on for testers; F12 what a refused form save does next; F13 old kept passwords; F14 what a go on spending covers.

## Open: F15 to F25 (2026-10-19 and 20, phases B-6 and B-7)

Each is built to its default tonight; a different answer changes the build, not the plan.

**F15. Blocked is a kind of on hold.** The roadmap asks for "Blocked, waiting on <a person, an action or a thing>".
*Today:* an action can be on hold with words saying what it waits for, and on hold is never due or chased. *Default:*
blocked is not a second state; a hold can name a person, an action or a question, the row reads "Blocked, waiting on
…" (or "Waits on: <the question>" with the UI designer's "Unblocked: <who> answered <date>"), it is never due, and
Top priorities counts the blocked ones. Should a blocked action stay due (and be chased) instead?

**F16. How Top priorities ranks.** The roadmap lists the rules (due and overdue, at risk, blocked, waiting on the
person, the project's priority) but not their order. *Today:* there is no Top priorities list. *Default:* overdue
first, then due within the follow-up window, then waiting on the person, then at risk, then blocked; ties by the
project's priority, then by date; at most one line per person, and a set number of lines in all (a setting).

**F17. What counts as "only a date move".** A record's history leaves out changes that only move a date. *Default:* a
change is only a date move when the item's text is the same and nothing but a due or start date changed; a date
move together with any other change shows in full. Should a second move within a week also be shown, as a sign the
date is slipping?

**F18. Notifications before the mail channel.** Design 7.19 offers the browser, mail to the person themselves and a
webhook. *Today:* nothing sends mail yet (phase S1b). *Default:* the browser and a webhook now; mail to themselves is
listed as "comes with mail sending" and arrives in S1b.

**F19. Handing an action to the assistant.** *Default:* the assistant drafts one thing the action needs (a message, a
list or a page) as a pending draft on the action, under the usual estimate and go; the action stays the person's, and
approving the draft doesn't close it. Should approving offer "Mark done" in the same toast?

**F20. A plain calendar entry needs no AI run** (found by the owner's first calendar file, 2026-10-20). *Today:* every
entry of a calendar file is an input the assistant reads, one run and one Review line each, even a reminder with no
one invited and no notes ("Nothing recorded" fourteen times). *Default proposed:* an entry is filed in the calendar by
rule (an `event.add` with no AI run and no Review line); the assistant reads only an invitation from someone else, an
entry with a description, or one that changed a date a promise is due at. Is there a kind of plain entry the assistant
should still read?

**F21. A date the rules can't read** (the owner's learning run, 2026-10-20). S1-1 made the rules' reading of the date
words win, and words they couldn't read gave no date. That dropped good dates the model had read from the same words.
*Built (B-7):* the rules still win when they read the words; words they can't read keep the model's date, marked for
the person to check; words that make the due a condition ("once the keys arrive", "after the workshop", "before his
leave") keep no date. *Question:* is "keep the model's date, marked to check" right, or should an unread phrase stay
dateless? And is "before" a condition word (it also drops the model's date for "before <something unreadable>")?

**F22. A reply that doesn't answer is news** (the same run). *Built (B-7):* a reply that only acknowledges, thanks,
defers or changes the subject is one `action.news` on the open action, never an ending, an answer or "nothing to
record". Agree?

**F23. Chasing someone else's promise is the one follow-up to that person** (the UI reviewer's §3.4, 2026-10-20). Today
had one "Chase <person>: <item>" line per late promise owed by someone else, beside the per-person follow-up line.
*Built (B-7):* a late promise owed by someone the person works alongside joins that person's one follow-up line and its
one message ("Follow up with Robin · 2 overdue, oldest Tue, Oct 13"); promise lines stay for the person's own and for
someone they report to (design 6.33 and 6.34 updated). Does that keep what 6.33 meant by a promise's line?

**F24. Top priorities has no buttons** (the UI reviewer's §3.4). It repeated the queue's actions. *Built (B-7):* its
ranked entries stay (F16's order), each a link to its queue line or record; the queue is the only place to act. Agree?

**F25. A new AI account may read the person's work material by default** (the UI reviewer's first-run review, F2).
With only "open" allowed by default, the assistant couldn't work on the person's own mail and notes. *Built (B-7):*
"Can the AI service read your work mail and notes? · Yes" chosen, allowing open and internal; restricted stays opt-in in
Advanced; saved accounts keep theirs. Any data-level concern with that default?

Earlier rounds: The UI designer's round 33 to 38 (2026-10-16) is answered in
`reviews/ui-ux-2026-10/answers-33-38.md`, with mockups in `reviews/ui-ux-2026-10/mockup-round-33-38/`, and goes into phase
B as a Today follow-up wave after wave 2, with the four other findings in it (phone header overlap, the Backup bar
repeating the status chip, the rail's to-dos as checkboxes, meta lines starting with raw pasted text). Answer 37 adds a
core group to a plugin's Today line: a plugin API change, announced in the guide when built. The UI designer's round 25 to 32 (2026-10-16) is answered in
`reviews/ui-ux-2026-10/answers-25-32.md`, with mockups in `reviews/ui-ux-2026-10/mockup-round-25-32/`; phase B builds to it.
 The round of 2026-10-15 (questions 10 to 24) and the earlier ones (1 to 9) were all answered on
2026-10-15; the answers are in `docs/decisions.md` ("The functional designer's answers to the round of 2026-10-15") and
in the design sections they changed (CHANGES section 71). The rounds are kept in the history of this file.
