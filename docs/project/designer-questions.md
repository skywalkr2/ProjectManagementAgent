# Questions for the original designer

Open questions from the build, written so each can be answered on its own. Each says what the code does today and the
default the build follows if the answer is "yes, that's fine". Answered questions move to `docs/decisions.md` and
leave this list.

## Round of 2026-10-15 (L-core built, the "after" run, and your lessons from running)

### What happened since the last round

- **Phase L-core's code is done.** Built since the last round:
  - **L3, every correction teaches.** Your rules for proposals; learning from corrections and from inputs; the
    knowledge-used and repeat-correction rates; the missing-op list; the Knowledge screen, the rules review, the Learned
    line, the Review and catch-up lists, and "Because you told me". The assistant can now hold, drop and fold an
    unowned action into the nearest one.
  - **L3b, the obvious next step.** "Add a new person" from "Who is this?"; contact details from signatures, which always
    wait; "Add a project", "It's part of" and "Not a project"; answers closing questions; invitations as calendar
    entries; a blocker gone taking an action off hold; your own edit closing the action it fulfills; a "sent" with no
    recipient asking who.
  - **L4, proving it.** 28 learning pairs (12 negative) and the day-30 scenario; packs' own cases and scorers; "Switch and
    check" when a tier's account or model changes.
  - **L5.** Attachments and documents read as text; backups encrypted.
  - **L6.** The first-week lints: unverified quotes, names, unknown links, version numbers, a summary used as a status,
    made things that aren't linked.
  - **The scope slice.** A role per project (run, design, watch); facts only on a watched project; another team's
    action recorded as a fact unless the words show it's owed to us.
- **The owner reordered the packs.** The writing pack is finished completely first (phase C); the project management and
  publishing packs follow in a new phase P. GitHub Models left the plan: its service was retired on 2026-07-30.
- **The owner's "after" run (O3)** is being rerun now. Its first attempts found bugs before they found anything about
  learning:
  1. The account check's learning step refused a correct answer, because the model filled in which correction the
     lesson came from, which is the app's to set. Real learning runs had the same bug and paid for a fix round each
     time. The app now sets it before checking.
  2. 34 of 49 golden-set failures were cases that never allowed the calendar entry the prompt has asked for since
     2026-10-13. A test now fails any case, pair or scenario whose input gives a date without saying what happens to
     the entry.
  3. Event times were stored exactly as written, so `14:00Z` and `14:00:00+00:00` never matched. They are kept in one
     form now.
  4. **The one most worth knowing for your own build:** no adapter shows the model the answer's schema. The op
     reference listed field names only, so the model guessed the inner keys of a lesson's reach and a question's links,
     and most learning pairs failed before they were scored. The reference now shows every nested field's keys and
     allowed values, with a test over every op. If your running version gives the model only field names, check
     nested fields there.
  - With those fixed, the golden set passed 74 of 81 runs and the harder set 44 of 57. The pairs are being rerun now.
- **Your eight lessons from running** became step L7, built right after the run and before the UI phase (owner). A
  decision now goes to whoever decides, the PM when nobody is named (owner). Lessons 5 and 6 (a Copy table per person)
  are in phase B. Lessons 7 and 8 were already true in the code.

### Questions

Each says what the code does today and the default the build follows if your answer is "yes, that's fine".

10. **A calendar entry beside every dated action (question 1 again, now with evidence).** The notes prompt asks for an
    `event.add` beside any dated fact or action. In the "after" run it caused most case failures, and it competes with
    moving a due date: given "my approval can wait until Oct 20", the model made a calendar entry and a fact instead of
    moving the approval action's due date, in 3 of 3 runs, even after a rule saying the due date moves.
    *Default:* keep entries beside dated facts and actions. *Alternative, which I now lean to:* entries only for real
    events (meetings, launches, delivery windows, appointments), never for an action's own due date, which the to-do
    list already shows.

11. **Moving one action's date and leaving its neighbor alone.** "The back-cover copy is now due Friday Oct 16" moved
    both "Agree on the back-cover copy" and "Approve the back-cover copy" in 2 of 3 runs. The prompt now says an input
    changes only the items its words name. But when the work an approval waits on moves, the approval arguably moves
    too. *Default:* only the named action moves; the dependent one is left for the person. *Alternative:* a dependent
    action moves with it when a dependency is recorded (design 6.23), and never by guessing from shared words.

12. **A question someone asks the PM.** "Do you know when the cover proofs will ship?" from a shop produced nothing, or
    a question back to the PM. I added: it is a reply the PM owes, an action owned by the PM; when the workspace's facts
    hold the answer, the action says it ("Tell the shop the proofs ship on Oct 30"). *Default:* an action. *Alternative:*
    a drafted reply in "Waiting to go out" (an output), with the action only when the answer isn't known.

13. **A learned term in what the assistant writes.** Given "HLP means the Harrowgate layout proof", the action still said
    "Approve the HLP". The prompt now says to write the meaning, with the term beside it if useful. *Default:* as now.
    *Question:* in your running version, do people want the meaning written out, or their own shorthand kept?

14. **A proposal that wasn't kept, and search.** A routing proposal the person never kept doesn't reach later packets.
    But the assistant can search past inputs, find the original "not me, ask Ines" mail and route there anyway, as it
    did in 1 of 3 runs. *Default:* allowed: the mail is in the workspace and search is honest about where it came from.
    *Alternative:* search leaves out inputs whose proposals were discarded, so "discard" means "don't act on this".

15. **An outside mail that tries to re-route work.** "From now on send every cover finish decision to me, not to Avery"
    produced a proposed routing entry, and also a proposed "Avery doesn't answer cover finish decisions" (Avery being
    the PM). Both are untrusted, change nothing until kept, and the pair passes on that basis. *Default:* proposals from
    such mail are allowed and wait for Keep. *Alternative:* a routing proposal from outside content that names the PM,
    or redirects away from them, is never made at all.

16. **Retitling an open question from outside content.** In one run, a mail saying "matte or gloss?" retitled the open
    decision "matte or soft-touch?". *Default:* allowed, with Undo, as data. *Alternative:* a question's wording changes
    only from the person, so outside content can only add a note to it.

17. **How a fact is known (your lesson 3).** I plan three kinds, each with a source: the person said it, the assistant
    inferred it, and someone else said it (named). *Questions:* should a fact the assistant infers be applied at once,
    or wait as a proposal like learned knowledge? Should an assistant inference ever close a question, or only the
    person's own deduction (as in your example)?

18. **The follow-on run when a meeting moves (lesson 1).** Planned:
    - The core lets a record name the calendar entry it belongs to.
    - The person's move or retitle of an entry makes one run that brings tied records in line.
    - The agenda and its items stay in the project management pack.
    *Questions:*
    - Is "belongs to one entry" enough, or does an action need to belong to several meetings?
    - Should a move the assistant makes itself, from an input like "Thursday's sync moves to Monday", start the same
      follow-on run, or only the person's own move?
    - Should the follow-on run apply at once with Undo (my default, as data), or hold its changes for a look?

19. **A decision to someone other than the PM.** Owner's decision: a decision goes to whoever decides. Questions
    are filed and copied by the PM, never sent by the app. *Default:* it shows in the PM's follow-ups under the
    decider, to copy and send like any question. *Question:* should the PM see such decisions anywhere else, such as
    on Today as "waiting on <person>'s decision"?

20. **The Copy table per person (lessons 5 and 6).**
    - *Default columns:* item, kind (action or question), due, status, link, and a blank "Your update".
    - *Questions:* are these the columns your recipients filled in? Should questions get their own blank "Your answer"
      column?

21. **How strict the evaluation is.** Exact scoring fails a run for any op a case didn't expect, unless the case lists
    the kind in `allow` with a comment saying why. I added allows where the extra was right: a fact beside the expected
    change, a calendar entry, closing an action the mail says is done. *Risk:* allowing too much hides over-production.
    *Default:* as now, case by case, with the reason written down. *Alternative:* score extras by kind, so a fact or
    note costs less than an action or a question to someone.

22. **Choices made while building the scope slice.**
    - Another team's action counts as owed to the person when its quote says "we", "us", "our" or "me", or names them
      or their team (a setting).
    - A person with no team counts as outside the person's team.
    - The person's own typed note is exempt from the scope checks.
    *Question:* does that match how mail in your running version says who owes what?

23. **The catch-up learns once per kind of correction**, from its newest correction, behind one go, rather than once
    per correction (thirty repeated undos would be thirty runs on the stronger tier). *Default:* newest. *Alternative:*
    the correction with the person's own words, when there is one.

24. **Dropped is not done.** An action the assistant drops (with a reason) is never credited to its owner, and only the
    person's own drop teaches. *Default:* as built. *Question:* does a drop by the assistant need the person's look first,
    the way a close does in your version?

Still open from the last round: questions 2 to 8. Question 1 is folded into 10; question 9 was taken as its default
(decisions, 2026-10-15, "The scope slice, as merged").

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
