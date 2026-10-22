# Questions for the morning (2026-10-23)

Collected while building past the owner's evening (open promise P31). Each says who it is for, what it decides, what
the build does meanwhile, and whether it blocks anything. Answered questions move into `docs/decisions.md` and leave
this file.

## For the functional designer

These were built tonight as described; each needs a yes or a change.

1. **Filing by words (S1-4).** When an item's people don't place it, its words may: the names and aliases of the
   projects on each side, plus a configured list per side (`workspace.project.side_words`). Words of one side place it;
   words of both, or none, go to the one "Which side?" question. People still win.
   - Decides: whether words should place an item at all, and whether project names alone (no list) would be enough.
2. **When a correction teaches nothing.** The owner decided an unclear correction asks the person one question. Built
   alongside: a correction saying something was missed (or sending back an answer that recorded nothing) always
   teaches or asks; a lesson from a correction no run made names no kind of work.
   - Decides: whether "missed" should also cover a decline and a drop, which the packet now explains but doesn't force.
3. **The deadline words' readings** (S1-3): "within <n> days" counts calendar days (only "working days" skips
   weekends, and holidays are never skipped); "this weekend" is Saturday and Sunday, read as a range; midnight is always
   doubtful; CST is read as US Central time by default (it is ambiguous elsewhere, and a workspace can change it).
   - Decides: whether any of these should read differently.
4. **Reminders and the app's own running record** (S1-3): a late reminder says "while the app wasn't running" only when
   the app's record of when it ran has a gap covering the due time; otherwise "overdue". The record can't tell sleep from
   closed, so the words don't claim either.
   - Decides: the wording, and whether the app should tell the two apart (the system's sleep events, in phase I).

## For the owner

0. **The gate before the rest of phase S.** The roadmap gates phase S on a week of real use: S1 (promises, reminders,
   replies owed, the coverage line, "Missed one", the quiet first run) is proven on the owner's personal mail for a
   counted week before S1b (sending and calendar acts), the brief, meeting prep, people memory, areas of life, capture
   and the conversation are built. Tonight's build stops at the gate: S1's remaining items and B-11c are built; nothing
   behind the gate is.
   - Decides: when the gate week starts, and whether anything behind the gate should be built before it (the plan says
     no).
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
