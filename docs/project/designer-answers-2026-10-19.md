# The functional designer's answers to F1 to F14 (2026-10-19)

Answers to `designer-update-2026-10-19.md`, as received. What they change is recorded in `docs/decisions.md`
(2026-10-19), design 6.32 ("Dependability, from the designer's answers") and the roadmap's phase S and tester milestone.

The new direction suits what we've learned: our hardest lessons have all been about remembering commitments dependably,
not about writing. Short version: yes to F1 to F14, with additions on F3, F4, F6, F7, F10, F13 and F14. Three things from
our running since 10/15 bear on them, so they come first.

## From running since 10/15

- **A rule silently closed real items for a week.** A clean-up rule closed tracker changes as "not ours" because their
  project had been renamed and the watch list still held the old name. Nobody saw it until the person asked whether a new
  item would be followed. Two fixes: link records by id, never by a display name; and every silent close is counted and
  can be reviewed. That's the "memory that silently drops commitments" risk in practice, and why I'd back F3 and F4 hard.
- **An outage isn't the assistant's failure.** Over a weekend, with the computer asleep and off the network, a good change
  failed to apply, was sent back as a mistake, and the retry hit a runner that only printed its sign-in banner. Two
  "attempts" were used up, and the person got "couldn't finish" with the banner as the reason. Now an apply that fails
  for lack of network waits and runs when the network is back, and a run that did no work isn't an attempt.
- **Bringing in an existing source.** When the person started following an existing collection of 46 items, everything in
  it was reported as new. Meanwhile, items older than the 14-day window would never have been followed. Now a newly
  added source is taken in quietly: nothing is reported as new, and every open item is followed whatever its age.

## The answers

**F1.** Yes: gate on proof. A week on the owner's real mail, with thresholds set before the week starts, is the gate we
wish we'd had. Our module-count equivalent was "the check passes": every one of the misses above passed its checks. Add
one condition: the week includes at least one closed-lid night and one network drop, because that's where our worst
failures came from.

**F2.** Yes. Hold the brief, meeting prep, people memory, areas of life and capture behind the gate. Keep reminders and
replies owed in the first slice. I'd also keep "what changed since yesterday" in the first slice, even as one plain line:
it's how the person notices a miss.

**F3.** Yes, with two additions.
- Count silent closes as their own measure: anything the assistant closed or set aside without the person seeing it, out
  of all it closed. It's sampled in the same independent review. Our week-long miss lived there, and it wouldn't show as
  "missed out of present", because the item was found and then closed.
- "Wrong ending" includes a nudge treated as done: the person chasing someone else's promise doesn't fulfill it. We hit
  this early.

Keep a small replay set as well: each real miss becomes a case with its starting state, the person's action and the
expected end state.

**F4.** Yes. It's the right fix for our weekend. Two details:
- "Couldn't read" and "read, nothing new" are different words and never share a color.
- A source that has failed for longer than its usual gap becomes an item for the person ("work mail hasn't been read since
  yesterday 6 PM: sign in again?"), not only a header note.

**F5.** Yes. Make it reachable from anywhere the person is already looking, including the evening wrap-up ("anything I
missed today?"). Our misses arrived as chat ("did it handle X?"), so "Missed one" should also accept a plain sentence with
no source attached.

**F6.** Yes to 14 days, the "not looked at" line and the costed longer look-back. Two additions from our "existing source"
lesson:
- First run is quiet: no burst of "new" for old mail. It shows one summary line ("found 12 open promises in the last 14
  days") and a list to review.
- A promise found in old mail that is still open is followed from then on, like any other. Age decides only whether it's
  raised as news, not whether it's tracked.

**F7.** Yes, all six, plus two.
- A closed lid or lost network mid-send: on resume the result is checked with the service before anything is retried, so
  it never sends twice and never shows "sent" from an uncertain state.
- An approval doesn't survive a restart that changed the draft's inputs: the recipients' addresses re-resolved, or a
  template updated.

Agree that plugins stay trusted code.

**F8.** Yes. Add one number: how many items each tester brought back through "Missed one" (F5) per week. It should fall
from week one to week two. If it doesn't, the assistant isn't learning.

**F9.** Yes. Our rule is that Today holds only actions, each starting with the verb and the place. Add one test case: a day
where the right top line is "nothing needs you, and here is what was read" (F4). It proves the empty state is honest.

**F10.** Yes, a full rewrite, and the three risks are right. Add three from running:
- The computer asleep or off the network reads as failure and burns retries.
- Renames detach links: records joined by display names drift apart silently.
- Rules that close things without the person seeing them: say what's counted and where it can be reviewed.

**F11.** Yes. Offer it during setup with Skip; connecting an account is what starts reading. Keep the core testable
without it.

**F12.** Yes. Also show the person which untouched fields changed underneath them ("refreshed: daily budget is now $2,
changed elsewhere at 9:14"), so a second Save is an informed one.

**F13.** Yes to 30 days and removal with the source. One condition: a kept secret is never removed while an Undo still
points at it. Either the Undo expires first or the removal waits.

**F14.** Yes: a range for the whole request, a stop at the upper figure, and another go beyond it. Two additions:
- Retries caused by an outage don't count against the request's figure. No network isn't the request's cost, and that's
  when our pointless re-runs happened.
- Show what was actually spent next to the estimate on the finished item, so the person learns whether the ranges are
  honest.

## Checked against the plan as of this morning

The roadmap's phase S, the tester milestone and the overnight fixes read well, and R10 is exactly the right risk. Eight
things to fold in:

1. **The documents disagree on when real use starts.** "Where things stand" (still dated 10/15) says real use starts after
   the writing pack (phase C). Phase D says it starts at the end of L-core. Phase S ends with the owner's own week. With F1,
   that week is the first real use. Say so in all three places, and say it runs on the owner's personal mail: R9 rules out
   work mail, and the week shouldn't be the first time anyone notices that.
2. **The charter, the risks and the 1.0 definition still describe the earlier product.** The charter's purpose, first user
   and success measures are still about the imprint's launch. Publish 1.0 waits for "the writing pack and the project
   management pack run unchanged through phase D", yet testers arrive at phase I, long before C and P. Decide whether 1.0
   is the steward plus a stable plugin API, with the packs as 1.x. F10 only covers the risks.
3. **Phase B lays out Today before phase S changes it.** The coverage line, promises, "Missed one" and the brief all land
   on Today in S. Either build B's remaining Today waves to S's shape, or move S1 ahead of the rest of B, so Today isn't
   designed twice. Also, the owner holding all feedback until B is finished makes for a long silent stretch: our most
   useful lessons came in the first days of use, not at the end of a phase.
4. **Three items in phase E a daily assistant needs earlier.**
   - Outage handling: an assistant on a laptop sleeps every night. Waiting for the network, and not counting a cut-off
     run as a failure, belongs in S (our weekend lesson above). O3's own run stopped when the computer slept.
   - A rule's check runs before the change applies: today it runs after and only counts. That's fine for notes, but not
     once S1b can send, because a sent mail can't be undone. Our validator refuses before applying, and that's where most
     of our guards live.
   - The Monday briefing is in both S2 and E. Pick one.
5. **Testers' work mail.** Colleagues and people from a public post will connect the mailbox they live in, which is often
   their employer's. Employers' rules on copying work mail into a personal tool, and into outside AI accounts, are a real
   risk for the tester group and for the product's name. Add it to the register. The tester invitation should say personal
   mail, or work mail only with the employer's OK. Phase D's "administrator approval required" Microsoft screen is that
   wall, met in the product.
6. **The thresholds are still open (R10), and the independent list needs an owner.** The owner has under five hours a
   week. The cheapest independent list is the owner writing down each promise they notice themselves during the week,
   before looking at the assistant's list. Then compare. To set the thresholds, measure two days first and set them from
   what's seen, before the counted week starts, rather than picking numbers cold.
7. **Say that sending waits for the gate.** F1 holds the later sub-phases, which includes S1b, but F2's list doesn't name
   it, and S1b is the riskiest part of S. One line in both places.
8. **Re-estimate S1 on its own.** "About 6 sessions" covers five sub-phases. It also covers connecting fifteen rule
   modules, 120 examples, 25 threads and 20 learning pairs. With F2 taken, S1 and the gate week are the plan; a number for
   that alone makes the tester milestone's timing honest.
