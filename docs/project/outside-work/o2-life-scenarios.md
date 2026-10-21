# O2: 15 scenarios for the daily steward's next features

**Why:** after promises, the daily steward grows into bills, bookings, reminders and a short morning brief. Each feature
is designed and tested against concrete situations. These are written before the features are built, in plain words,
not code.

**Read first:** `docs/project/steward-scenarios.md` (the format and the first 15 scenarios),
`docs/project/steward-guide-sections.md` (what the features are meant to do), `docs/project/steward-brief-samples.md`
and `docs/project/steward-reminder-wording.md`.

**Produce:** one file, `docs/project/steward-scenarios-2.md`, with 15 new scenarios numbered 16 to 30, in the same shape
as the existing ones: the person, what arrives (the message or calendar entry, written out in full), what the steward
should show on Today and when, and what it must **not** do. Spread them:
- 4 on bills: a due date in a statement, an amount that changed, a bill already paid automatically, a reminder that is
  not a bill (a marketing "your statement is ready").
- 4 on bookings: a confirmation, a change of time, a cancellation, a booking that clashes with something already on the
  calendar.
- 4 on reminders: something the person asked to be reminded of, a reminder that should move when its event moves, one
  that should stop because the thing is done, one for someone else ("remind Mira").
- 3 on the morning brief: a quiet day, an overloaded day, a day where the important thing is something waiting on
  someone else.

**Rules:** fictional people, companies and places only, addresses at `example.com`; mix work and personal life; say
what the steward must not do in every scenario (send anything, guess an amount, nag); the person approves anything that
goes out.

**How it is checked:** a read by the main session against design 6.32; accepted scenarios become tests when each
feature is built.
