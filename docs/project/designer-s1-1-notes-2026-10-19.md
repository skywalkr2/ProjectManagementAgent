# For S1-1, from three weeks of tracking promises (the functional designer, 2026-10-19)

As received. What they change: design 6.33 ("From three weeks of running"), `docs/decisions.md` (2026-10-19), and the
roadmap's S1-1 items. Built in S1-1: `tests/test_promises.py` (points 1, 2, 4 to 8); point 3 is the chase clock on the
past-date line, built with the promise screens.

Our running version has followed promises both ways for three weeks: actions the person owes, and actions others owe them,
from meeting notes, mail and pages. These are the cases that cost us most, as the things we'd want S1-1 to get right from
the start. The first three aren't in the item as written.

1. "On hold until <trigger>" is an ending of its own. About one promise in ten of ours waits on something: "once the
   vendor confirms", "after the epic exists", "when the contract is signed". Without a hold, it reads as overdue every day,
   and the person learns to ignore the overdue line.
   - Store the trigger.
   - A held promise is out of "due" and "overdue" everywhere.
   - When an input shows the trigger happened, propose taking it off hold with a new date, as one step.
2. A promise tied to an event follows the event. "By Thursday's meeting" or "after the review" shouldn't become "no date".
   Store the event as the due. When the meeting moves, the promise moves with it, and that's a date-only move with no news
   line. Our worst miss of the month was exactly this: a meeting moved, and the two promises due at it stayed on the old
   day.
3. Undated waiting-ons need a clock too. "They'll get back to me" with no date never reaches "no news by its date", so it
   goes stale silently: the R10 failure in its simplest form. Our rule: an undated promise owed to the person gets one
   line after 14 days without news, a dated one only within 7 days of its date or when overdue, and nothing while it's
   on hold. Chasing earlier than that annoyed people in practice.
4. Relative dates read against the message, not the reading. The quiet first run reads two weeks back. "Tomorrow",
   "Friday" and "end of next week" in a mail from ten days ago resolve against that mail's own date and the sender's time
   zone. A test: the same thread read on its day and read ten days later gives the same due dates.
5. One promise per owner, and an owner is a person.
   - "Sam and I will draft it" is two promises, never one with two owners.
   - "The team will send it" has no owner yet. Keep it visible and propose a person: who said it, or the team's usual
     contact. Never a team name alone.
   - We split a merged pair three times before making this a check that refuses it.
6. The same promise from three sources is one record with three pieces of evidence. A promise is said in a meeting,
   repeated in the follow-up mail and noted by the person. Merge on owner, thing and date window, and keep every quote.
   When the sources disagree on the date, the person's own words win, otherwise the newest; the disagreement is shown,
   not resolved silently.
7. Crediting and chasing are different acts. These belong in the endings' tests:
   - The person chasing someone else's promise doesn't end it. Their "I pinged her about it" is news, not "done".
   - When the person reports someone else's promise done ("Sam sent it"), it's credited to Sam, "reported by you". It
     isn't the person's done.
   - We had both wrong before we split them.
8. People under two names. A system's display name and the name the person uses split one person's promises into two
   lists. Every promise joins its people by id, and a second spelling becomes an alias on the person, never a second
   person.
