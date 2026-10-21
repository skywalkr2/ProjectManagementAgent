# UI/UX re-review of batch B-9 at `9e9c3f0`

**What was reviewed:**
- branch `claude/tender-tesla-16a8ob` at `9e9c3f0`, against my B-8 review (`../rereview-0f37be4/`)
- with the same capture on the same three demos: the e2e demo, the full demo, and a brand-new workspace

**Files in this folder:**
- `gallery/index.html`: B-8 and B-9 side by side
- `wording-verdict.md`: my verdict on the outside wording review, which you asked for
- `tools/metrics.json`: the measurements

## 1. Verdict

**All six findings, S1 to S6, are fixed on screen, and nothing measured got worse.**

Every measured view matches B-8:
- the header is 56px
- there are no internal ids
- there are no targets under 24px
- there is no uppercase text and no sideways scrolling
- toasts never cover a control during Tab
- Send back is in view
- Copy shows the message before anything reaches the clipboard

Today at 1280×720 still shows 6 lines, with the first at 257px. The e2e demo's queue is down from 30 lines to 28, because
the duplicates are gone.

## 2. S1–S6, for the status file

Please copy these marks into `docs/project/ui-review-status-2026-10-20.md`. I only push to my own branch, so I haven't
edited it.

| Item | Status | Seen |
|---|---|---|
| S1: one decision is one Today line | **Done** | The seating-plan drop shows only under Decide; Review no longer repeats it (`gallery/compare/01-…`) |
| S2: a held line's details show only the decision | **Done** | The pane shows the question, "The words it rests on", "Where it came from", "Why it waits" and Keep it open / Close it. The label reads "Would add a to-do" (`gallery/compare/02-…`) |
| S3: every title starts in line | **Done** | The Rules title lines up with the others at 1440 and 1920 |
| S4: titles come from a short topic | **Done** | No cut-off sentences in What changed or on Today. One leftover is in R-a below |
| S5: Review in the past tense, Decide as a question | **Done** | "Quill dropped 'Settle the endpaper color'", "Quill recorded '…'" |
| S6: one way to skip the mail step | **Done** | With nothing connected, only "I'll do this later" shows (`gallery/compare/04-…`) |

**This also makes C55 Done.** That gives:
- **C1–C56:** Done 35, Partial 21, Not done 0
- **N1–N8:** Done 5, Not done 3 (N1, N2, N8)

The other two fixes in this batch:
- **"Something else" stays chosen,** and a service picked under it is chosen too. Confirmed on screen
  (`gallery/after/ai-something-else.png`).
- **"-1 days" is not fixed.** The full demo's Today shows **"Waiting -1 days"** and "waiting up to -1 days" on "Follow
  up with Theo Brandt" (`gallery/after/minus-one-days.png`). This was captured at 01:47 UTC on Oct 21, which is still
  Oct 20 in the workspace's time zone, so something sent "today" is counted as sent tomorrow. See R-0 below.

## 3. Leftovers

- **R-0 [P1]: "Waiting -1 days" after midnight UTC.**
  - **Seen:** the bug the batch said it fixed, still on screen.
  - **Cause:** the sent date and "today" are counted in different time zones. The sent stamp looks like a UTC date,
    while "today" is the workspace's.
  - **Fix:** store when an item was sent as a moment in time, and convert both dates to the workspace's time zone
    before counting days.
  - **Also clamp the count at zero,** so a clock or time-zone mismatch shows "sent today", never a negative number.
  - **Test it in the browser,** not only in unit tests: run the full demo with the clock set just after midnight UTC
    and the workspace on a time zone behind UTC.

The rest are small and block nothing:

- **R-a [P2]: a process name used as a title.** A What changed line is titled "Checking what a move changes · Approve
  the back-cover copy", which is the internal name of the follow-on run. Title it by what happened: "After 'Approve
  the back-cover copy' moved".
- **R-b [P2]: raw model names under "Something else".** Choosing a program you're signed in to (Claude Code) shows
  "AI model: sonnet / opus / haiku" (`gallery/after/ai-something-else-claude-code.png`). These are the program's own
  model names, which the product rule keeps off the person's screens. Show "Recommended / Stronger / Faster", with the
  name in the hint if the person needs it to match the program's settings.
- **R-c [P2]: the details pane repeats its title.** It heads with the question, then repeats the question as its first
  line. Drop the repeat.

## 4. The wording review

See `wording-verdict.md`. In short:

| Rename | Verdict |
|---|---|
| **Sources → Connections** | **Accept,** for the area and what's set up in it. Keep "source" where it means the original text ("Show source", "Where it came from"), and reject `op.source` |
| **Stages → Steps** | **Reject.** "Steps" already means setup steps, the numbered AI-key steps and template steps |
| **Go → Start** | **Accept** (already done in most places). Put the estimate on the button where it starts paid work |
| **Drop → Remove** | **Reject.** "Remove" already means delete; "Drop" means "no longer needed, kept in history". Add that as the menu item's second line |

Of the other rows:
- About 20 are changed.
- **Keep "hand in" wherever the suggestion says "share",** because it's the main button's verb.
- **Use "synced folder", not "shared folder"**: it's your own folder, not one shared with other people.
- **Keep "model".**
- **Keep the "Waiting: {why} · until {until}" lines,** which describe a state, not an action.
- The rest are accepted as suggested.

## 5. Next

**Fix R-0 now:** a negative number on Today is the kind of error people notice first. Carry R-a to R-c and the wording rows into the next batch with other work.

The open items are unchanged:
- N1: the one-click installer
- N2: built-in mail and calendar sign-in
- N8: three real people setting it up alone
