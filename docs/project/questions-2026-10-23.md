# Questions for the morning (2026-10-23)

Collected while building past the owner's evening (open promise P31). Each says who it is for, what it decides, what
the build does meanwhile, and whether it blocks anything. Answered questions move into `docs/decisions.md` and leave
this file.

## For the functional designer

Answered on 2026-10-22: recorded in `docs/decisions.md` ("The functional designer's answers on the 2026-10-23 questions"),
written into the design (change log 174) and planned as roadmap item B-12.

1. **"Who suggested it" in the inspector (B-12 batch 4, item 3; stopped for a definition).** The answer moved it from
   Top priorities' second line to the inspector, but nothing on a Today line or its record says who suggested the item,
   and "a line that comes from a suggestion" isn't defined: decisions and questions are always asked by the assistant,
   and only owner and escalate lines carry a suggestion today (`OwnerSuggestionView`). What exists: a question's status
   and answer, a promise's basis (said or inferred), and which change made a record (its run or the person).
   - Decides: which lines count as a suggestion, and whether "who" is the change that made the item (the assistant's run,
     a rule, or the person), which can be derived without a new field.
   - Proposed: every line about an item the assistant made from an input says "Suggested by <assistant> from <source>"
     in the inspector, with "no answer yet" while a question to the person is open; items the person made say nothing.
   - Meanwhile: nothing is shown; Top priorities stays one line.

## For the owner

0. **The gate before the rest of phase S.** The roadmap gates phase S on a week of real use: S1 (promises, reminders,
   replies owed, the coverage line, "Missed one", the quiet first run) is proven on the owner's personal mail for a
   counted week before S1b (sending and calendar acts), the brief, meeting prep, people memory, areas of life, capture
   and the conversation are built. Tonight's build stops at the gate: S1's remaining items and B-11c are built; nothing
   behind the gate is.
   - *Answered (owner, 2026-10-22):* the gate week comes once the core is built; the rest of S is built now
     (`docs/decisions.md`, "The gate week comes once the core is built").
   - Meanwhile: S1 is finished and ready for the week; B-11c's hardening continues.
   - Blocks: everything behind the gate.

1. **Why your account answers corrections with nothing (pairs 23, 24, 25, `rejected-ask`).** With the exact learning
   packets, a low-cost model proposes the right lesson for 23, 24 and 25; your account proposed nothing. The report
   keeps each run's error, which the summary lines don't show. Please run this from `~/dev/thimbleby` and paste what it
   prints:

   ```
   uv run python -c "import json,os; r=json.load(open(os.path.expanduser('~/tonight-pairs.json')))['results']; [print(x['case'], '|', x['error'], '|', x['got']) for x in r if not x['passed']]"
   ```

   - Decides: whether the fix is in the app (a failed or unreadable learning answer) or in the instructions.
   - Meanwhile: the packet now says what a decline and a drop mean, and a correction saying something was missed can no
     longer be answered with nothing (it proposes the narrow lesson or asks you).
   - Blocks: nothing else.
