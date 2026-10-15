# Questions for the original designer

Open questions from the build, written so each can be answered on its own. Each says what the code does today and the
default the build follows if the answer is "yes, that's fine". Answered questions move to `docs/decisions.md` and
leave this list.

## Round for the UI designer, before phase B (not yet sent, 2026-10-16)

These screens were added or changed since the mockup review of 2026-10-14 and have no mockup. Each says what the screen
does today and the default phase B builds if the answer is "that's fine".

25. **AI accounts, as one place** (the owner: "a terrible UI flow"). Today: the list in Settings, "Add an account" opens
    the setup guide, a backup is set from a row's ⋯ menu, removing the working account leaves the work with none.
    Default: one section in Settings; each row says what it does (does the work, backs it up, nothing) with one next
    step; Add opens the form in place with "for the assistant's work" or "as a backup"; removing the working account
    offers its backup in the Undo toast. How should a row read, and where does the backup choice sit?
26. **"What it can do" per account** (the capability matrix). Today: a disclosure under each account row listing skills
    with pass rate, runs, age and cost per passing run, low ones marked with an icon and words. Default: keep the
    disclosure; later a grid of accounts × skills on its own Settings page with "Measure" (estimate first). Grid or
    per-account list? What does a person compare first: cost or pass rate?
27. **Questions the assistant asks after a move** (follow-on runs). Today: a decision question per tied action ("Should
    <action> move to Thursday?") to its owner or the person, and one "does the plan still hold?" to the person, each a
    normal question row. Default: they group under the moved meeting on Today ("Print sync moved to Thursday: 3 things
    to check"), one row each inside. One group line, or separate rows?
28. **Held for a look** (new hold reasons: an inference that would close something or change a date, owner or routing;
    a drop of something that reached someone). Today: the held line with its plain reason and Do it / Leave it.
    Default: the same row, with the reason first and the button worded for what it does ("Close it", "Drop it"). Fine?
29. **Where a fact came from** (person, inferred, said by someone named). Today: stored, not shown. Default: a small
    label after the fact's text ("inferred", "from Jun Park"), never colour alone; inferred facts in italics as well.
    Label wording and placement?
30. **Meetings and series**. Today: entries can belong to a series; items can name the entry or series and roll to the
    next one. Not shown. Default: a record page for a series listing its instances and the open items on the next one;
    an item's row shows "for Thursday's print sync". Is that the right place, or does the agenda belong only to the
    project management pack's screens?
31. **The rules review's "Not now"**. Today: a secondary button on the Today line, putting it off for a week. Default:
    keep it in the line's menu, not as a second button (one primary action per row). Fine?
32. **Copy tables per person** (functional designer lesson). Default: two tables (actions, questions) under each person's
    group in Follow-ups, with Copy as text and Copy as table. Any layout preference for the "Your update" column?

Questions 25 to 32 are open (above). The round of 2026-10-15 (questions 10 to 24) and the earlier ones (1 to 9) were all answered on
2026-10-15; the answers are in `docs/decisions.md` ("The functional designer's answers to the round of 2026-10-15") and
in the design sections they changed (CHANGES section 71). The rounds are kept in the history of this file.
