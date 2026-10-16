# Questions for the original designer

Open questions from the build, written so each can be answered on its own. Each says what the code does today and the
default the build follows if the answer is "yes, that's fine". Answered questions move to `docs/decisions.md` and
leave this list.

## Round for the UI designer, from building Today (not yet sent, 2026-10-16)

Found while building the new Today (commit `9dbee51`). Each says what the screen does now and the default if the answer
is "that's fine".

33. **Toasts over the navigation.** From 1280px, toasts sit at the bottom left over the navigation and can cover Sources,
    Add-ons and Settings; the stack is capped at 45% of the window height, and with reduced motion toasts stay until
    dismissed. Is a toast over focusable navigation acceptable under WCAG 2.2 "Focus Not Obscured"? Default: keep the
    position, and move the stack up when keyboard focus reaches a covered entry.
34. **Nothing selected when Today opens.** The inspector (from 1680px) starts empty until a line is picked. Default:
    keep it empty, with a short line saying "Pick a line to see its details". Or should the first line open?
35. **A to-do that waits on a question.** The to-do says what it waits on, but there is no link to the question
    (nothing in the data ties them yet). Default: the words only, and the link comes with that tie. Is a link needed
    before real use?
36. **"Draft a nudge".** The design names it as the primary of an overdue follow-up, but nothing writes nudge messages
    yet; today the primary is "Follow up", which opens the waiting items. Default: keep "Follow up" until drafting
    nudges is built (phase P). What should a drafted nudge say, and to whom: one per person, or one per item?
37. **Add-on lines on Today.** Lines from add-ons name no group, so they follow the queue under "More for today".
    Default: keep that heading. Or should an add-on choose one of Decide, At risk, Review or Send?
38. **"N new · Show".** New lines that arrive while the keyboard is in the queue wait behind this pill, so the list
    doesn't jump; otherwise they appear at once. Fine?

Questions 33 to 38 are open (above). The UI designer's round 25 to 32 (2026-10-16) is answered in
`reviews/ui-ux-2026-10/answers-25-32.md`, with mockups in `reviews/ui-ux-2026-10/mockup-round-25-32/`; phase B builds to it.
 The round of 2026-10-15 (questions 10 to 24) and the earlier ones (1 to 9) were all answered on
2026-10-15; the answers are in `docs/decisions.md` ("The functional designer's answers to the round of 2026-10-15") and
in the design sections they changed (CHANGES section 71). The rounds are kept in the history of this file.
