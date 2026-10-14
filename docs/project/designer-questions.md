# Questions for the original designer

Open questions from the build, written so each can be answered on its own. Each says what the code does today and the
default the build follows if the answer is "yes, that's fine". Answered questions move to `docs/decisions.md` and
leave this list.

## Round of 2026-10-14 (after L2 and the O2 run)

1. **A calendar entry beside every dated action.** The notes prompt asks for an `event.add` whenever the input gives a
   date for something, so an action with a due date also gets a calendar entry. That duplicates the due date already
   on the to-do list. *Default:* keep it. *Alternative:* calendar entries only for real events (meetings, launches,
   delivery windows, appointments), never for an action's own due date.

2. **Where learning is measured, now that extraction has no headroom.** On the owner's account the harder set scores
   48 of 48 once its cases were corrected (`docs/project/evals/`): every failure was an extra op the case hadn't
   allowed, never a missing or forbidden one. *Default:* L4's before/after rests on the learning pairs ("corrected once,
   right the next time") and the repeat-correction rate in real use. *Alternative:* an even harder extraction set
   (long threads, several inputs about one item, conflicting replies) as a third "before" run.

3. **Applied versus present when no check runs on a run's output.** A rule counts as applied when the run produced an
   op or field it constrains, or a correction names it. "Its check ran on the output" is wired, but today stage checks
   run only on stage moves, so that path never fires. *Default:* leave it until a check runs on output. *Alternative:*
   run rules that have a check on every run's output, so a checked rule is counted every time it holds.

4. **The weekly rules review.** A rule is flagged only after a whole review period (30 days) since it was learned or
   last kept, so Keep starts its count again. The line returns at most once a week after the person last kept,
   narrowed or retired a rule; there is no "Not now". *Default:* as built. *Alternative:* a "Not now" that also starts
   the week.

5. **Seed lessons from refusals.** A check's fuller guidance joins a kind of work's packets when at least 5% of its
   last 50 runs were refused by it, counting refusals a fix round repaired, and only once 10 runs are counted.
   *Default:* those numbers (all settings). Are they the right starting points from your running version?

6. **A series and its books.** A rule or lesson scoped to a parent project (a series) reaches its child projects (each
   book) at any depth, and an exclusion on the parent excludes the children. Facts stay with their exact project, so a
   series' facts don't reach a book's runs. *Default:* as built. *Alternative:* a parent's key facts also reach its
   children.

7. **Someone else's words in a note.** A note on any button counts as reported content when it has a speaker other
   than the person followed by a speech word (said, says, confirmed, told, wrote, asked, wants), or a quoted passage
   of three or more words. Facts from it still apply; a rule or lesson from it waits for Keep. The words are a
   setting. *Default:* those words. Any you've seen in real notes that this would miss, or wrongly catch?

8. **The four missing ops from the hand-work audit.** Checked against the code: a project's role (the scope slice
   adds it), bringing back something set aside as an op the assistant can propose, merging a list row that was never
   a real project, and marking a question as already sent by the person have no op yet. *Default:* the first comes
   with the scope slice; the other three become ops in L3 with Undo. Should any of them stay "the person does this"
   instead?

9. **The scope slice's enforcement.** On a watched project, an action or a question to someone else is sent back once
   with "record it as a fact", then held for the person, never applied. Another team's action (all owners outside the
   person's team) gets the same treatment unless its evidence shows the person owes them something. *Default:* as
   placed. *Alternative:* refuse outright, with no return round.
