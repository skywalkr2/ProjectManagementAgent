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
   - Note: projects have no aliases, so only their names are matched; a project with a one-word everyday name
     ("Launch") would match that word anywhere. A minimum of two words for a project name to count, or aliases on
     projects, would answer it.
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
5. **Lines that stop the assistant's work wrap to two lines** (B-8 R3). Every other Today line keeps its meta on one
   line, and the rest is in the inspector. A stopped-work line (a restart waiting, a provider paused) has no inspector,
   and its second line says why it waits and until when, which the rules require to be visible. So it wraps.
   - Choices: (a) keep the wrap, since these lines are rare and must say why and until when; (b) cut the line with an
     ellipsis and give these lines a small inspector holding the full text; (c) shorten the wording so it fits one line
     at 1280px.
   - Proposed: (a), unless the reviewer sees these lines often enough to matter.
6. **What's left of "every kind of AI account works properly"** (B-11c, part 2). Each needs a call before it's built:
   - Turning thinking off. The service's model listing has no "can turn thinking off" capability, so `thinking: off` is
     never sent. Options: leave it unsent until the listing says so, or send it to models the person checked by hand
     in the account test.
   - Picking a family's newest model. The preset relies on the order of the model list, which the service's reference
     doesn't promise (the list has no date field). Options: keep the order with a check that warns when it changes, or
     ask the person to pick once.
   - Estimates. Character counts undercount the current models by about a third. The exact count is one count request
     per model, which costs a call each time. A command-line agent also adds its own overhead to every request (one
     run counted about 12,000 tokens for a two-word request). Options: one count request when an account is checked,
     kept as a ratio; or a count before each run above a set size.
   - Moving a saved account to the native adapter, which waits for the Settings screen in B-11b. Options: move it
     silently on the next start, or ask once with a read-back.

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
