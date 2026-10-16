# Answers to designer questions 33–38

**These answer** `docs/project/designer-questions.md` at commit `a8e0ba1`. I checked them against the running build at
`9dbee51` (branch `claude/tender-tesla-16a8ob`), with the e2e demo workspace and the fixture hand-ins.

**Mockups:**
- `mockup-round-33-38.html`
- `mockup-round-33-38/r-*.png`: the proposals
- `mockup-round-33-38/now-*.png`: what the build does today

**First, the new Today is a big step.** The queue reads as the prototype intended:
- the Decide / At risk / Review / Send groups
- verbs with one primary action each
- keyboard focus starting on the first line
- the rail at the right
- the bottom bar on a phone

The answers below are refinements, not a change of direction.

---

## 33. Toasts over the navigation

**Answer: no, it doesn't pass as built. Move the toasts off the navigation rather than moving the stack when focus
arrives.**

**What I measured** (`mockup-round-33-38/now-toasts-cover-settings.png`, 1920×1080):
- After three "Looks good" clicks, the three toasts **entirely cover** Sources, Add-ons, Settings and the sidebar toggle.
  The element at the centre of the focused Settings link is the toast.
- The toasts are 216px wide, so "Filed. Marked as looked over." wraps to three lines, and the three are identical.

**The criterion:**
- WCAG 2.2 SC 2.4.11 *Focus Not Obscured (Minimum)*, level AA: "When a user interface component receives keyboard focus,
  the component is not entirely hidden due to author-created content."
- **Partial** covering passes AA. **Entire** covering fails it. This is entire.
- The Understanding document excuses content the user opened and can dismiss without moving focus (such as with
  Escape). Toasts appear as a side effect of an action rather than being opened, so don't rely on that exception.
- I couldn't reach w3.org from this session to re-quote it, so check the exact wording before citing it in the design.

**Why not "move the stack up when focus reaches a covered entry":**
- It passes the criterion, but the stack then jumps around as the person tabs.
- It still hides the entries from pointer users.
- It needs special code for every covered element.

Fixing the placement is simpler and covers everyone.

**Do this instead** (`mockup-round-33-38/r-q33.png`):
1. **Position:**
   - From 1280px: bottom left **of the content area**, starting just right of the sidebar, never over it.
   - Below 1280px: bottom centre, above the bottom bar (as built).
   - Width: 360–420px, so a toast is one line.
2. **No toast covers a control after scrolling.**
   - Keep the existing "room under the last row".
   - Also set `scroll-padding-bottom` on the scroll container to the stack's current height. A row focused by Tab or
     `j` then scrolls clear of the toasts. This is the standard technique for sticky footers under 2.4.11.
3. **Merge and cap:**
   - The same message repeated becomes one toast with a count: "Filed 3 reviews · Undo last".
   - At most 3 toasts show; older ones fold into the newest.
   - Replace the 45%-of-height cap with "3 toasts".
4. **Don't tie persistence to reduced motion.**
   - Reduced motion means "don't animate". It doesn't mean "keep messages longer".
   - Keep the `toast_seconds` setting (0 = until dismissed) and pause on hover or focus. That covers 2.2.1 *Timing
     Adjustable*.
   - Today, with reduced motion on, the stack only grows, which is what causes the covering.
5. **Keyboard:**
   - `u` already undoes the newest.
   - Add F6 (or the existing landmark order) to reach the toast region.
   - Esc dismisses the focused toast.
6. **Test** (Playwright, part of the a11y suite): with three toasts showing, Tab through every focusable element. For each,
   assert that the element at its centre is the element itself or inside it. axe does not check 2.4.11.

## 34. Nothing selected when Today opens

**Answer: open the first line.** The details pane shows the line that has keyboard focus, or the one last clicked, from
the moment Today opens.

**Why:**
- **Keyboard focus already starts on the first line** (`9dbee51`, "keyboard from the first line"). Pressing `j` moves
  focus, but the details pane still says "Pick a line to see its items here" (`now-details-empty-after-j.png`). Focus
  and details disagree, which is confusing. Inspector panes in list–detail tools follow the focused item.
- An empty pane wastes about 30% of a 1920 screen. Using the whole screen was the owner's request.
- The first line is the most urgent thing in the ranked list, so it's the right thing to show first.

**Rules:**
- **Showing is not acting:** opening a line in the pane never marks anything as seen, read or done.
- **After a line is settled,** focus and the pane move to the **next** line, not back to the top. The person keeps their
  place.
- **Remember the line** (by key) across live refreshes and returning to Today in the same session. If it is gone, take
  the line that is now in its position.
- **Empty queue:** the pane says "Nothing needs you" plus what's next ("Next check 11:30 · Print sync tomorrow 10:00").
  It never stays blank.
- **Below 1680px** nothing changes: Enter expands the line in place, as built.
- **The pane's title** is the line's subject, with "1 of 9 · j / k" in its header so the person knows where they are.

**Also, the titles.** Two lines both read **"Answer 1 decision"**. When a line holds one item, its title should be the
item itself ("Cover finish for the hardcover: matte or soft-touch?"), with the pill saying it's a decision and the
button saying "Answer". Keep "Answer 3 decisions" for lines that group several. The same goes for "Look over 1 question
Quill wrote" and "Finish 1 overdue to-do".

## 35. A to-do that waits on a question

**Answer: the full tie can wait, but give it a link that's correct now.**

- **Before real use:** if the words name a person ("waits on Jun Park's answer"), make the name a link to that person's
  group in Follow-ups. That is cheap, never wrong, and it saves the hunt. If no person is named, leave the words as plain
  text.
- **Don't guess by matching text** to find "the" question. A wrong link is worse than none.
- **When the tie arrives:**
  - The to-do shows "Waits on: Can proof copies ship by Nov 3? (Jun Park, sent Oct 12)", linking to the question.
  - When the question is answered, the to-do moves to the top of the rail with "Unblocked: Jun answered Oct 16".
  - That moment is the feature's real value, so plan it with the tie, not after it.

## 36. "Draft a nudge"

**Answer: one nudge per person.** It can be built **now, from a template, with no AI run**, the same way Copy builds the
first message. So "Draft a nudge" doesn't need to wait for phase P. See `mockup-round-33-38/r-q36.png`.

**Why one per person:** it matches how the first message went out (one message per person). One ping is less annoying
than three. And the person's follow-up rhythm stays per relationship, not per item.

**What it says:**

```
Hi Maya,

Following up on two things from my note on Oct 10:

1. Do we have written permission for the epigraph?
2. Agree on the back-cover copy with Ines (it was due Wed, Oct 14)

A quick yes or no, or a date, for each is plenty.

Thanks!
```

**Rules:**
- **Only what's still open and was sent at least `followup.wait_days` ago.** Items answered since are left out, and the
  list above the box shows them as "answered Oct 12, left out", so the person sees why.
- **Same numbering and wording** as the original message, so the reader can match them up. Name the original date
  once. Mention an overdue due date as a fact, never as blame.
- **Ask for the smallest useful reply:** "a quick yes or no, or a date".
- **The 2nd follow-up** (after another wait): shorter. Only the oldest item or two, plus "Is there someone else I
  should ask, or a date I can plan around?"
- **After the 2nd follow-up with no answer:** Today suggests **one** escalation ("Ask someone else about the epigraph? ·
  Pick who"). It is never sent automatically (design 8.6).
- **The same flow as every message:** edit in place, Copy, then Mark sent. That records "followed up Oct 16 (1st)".
  The waiting clock restarts, but the line keeps "first asked Oct 10".
- **Greeting and sign-off** use the same config as Copy (`greeting`, the closing line), so the voice matches.

**Until it is built,** keep "Follow up". It's honest, since it opens the waiting items.

## 37. Add-on lines on Today

**Answer: an add-on chooses one of the existing groups** (Decide, At risk, Review, Send). "More for today" is only the
fallback for a line that doesn't name one.

**Why:** the person thinks in verbs ("what do I need to decide?"), not in sources. A publishing add-on's "Approve the
post for Friday" is a Review line, and putting it below everything else hides it under a source heading. That breaks
the one ranked list.

**Rules for the plugin API:**
- **`group` is an enum** of the core groups, validated in the manifest. Add-ons can't add groups. This is the same
  budget idea as the navigation.
- **Within a group, the core ranks** by urgency and due date. An add-on can't put itself first.
- **Each add-on line names its source** quietly in the meta ("· from Publishing"), so the person knows why it's there
  and where to turn it off.
- **The fallback heading** "More for today" stays for lines without a group. It's fine wording. Log a warning in the
  plugin check so add-on authors fix it.

## 38. "N new · Show"

**Answer: yes, with three widenings.** See `mockup-round-33-38/r-q38.png`.

1. **Hold the list for pointer users too,** not only keyboard focus. Hold while the pointer is over the queue, while a
   line is expanded or shown in the details pane, or while the person is typing in a line (an answer, a note). Mouse
   users lose their place just as much.
2. **Removals hold too.** A line settled elsewhere (in Follow-ups, or by another device) stays in place, struck through
   and muted, with "Settled in Follow-ups a moment ago". It leaves when focus moves off it or the person presses Show.
   Otherwise the line under the cursor vanishes, and the next click lands on the wrong row.
3. **The pill:**
   - It sticks to the top of the queue: "2 new · Show".
   - **Shift+N** shows the waiting lines, and the shortcut sheet lists it.
   - Showing inserts the new lines in rank order and **keeps focus on the current line**. It doesn't jump to the new
     ones.
   - A polite live region announces "2 new lines" once per batch.
   - **The sidebar's Today count updates at once.** Only the list holds still.

**When nothing holds it** (no focus, no pointer, nothing open), new lines appear at once, as built.

---

## Also seen in `9dbee51`

Small issues, worth fixing with this round:

| Seen | Where | Fix |
|---|---|---|
| Two lines titled "Answer 1 decision" | Today | A single-item line's title is the item itself (§34) |
| On a phone, the header's assistant label collides with the avatar ("A" over "AL"), and the workspace name is cut to "Lant…" (`now-phone-header.png`) | Header under 640px | On phones show only the logo, the status chip and the avatar. The assistant's state lives in the status chip's popover |
| A separate "Backup" bar under the setup line repeats the header's "Backup needed", with its button mid-row instead of at the right | Today | Make it a line in **At risk** ("Back up your work · no backup has succeeded yet · [Back up now]"), or right-align the button. Either way, one place, not two |
| At 1440 the rail's to-dos wrap to 3–4 lines beside full-size "Mark done" buttons | Rail | Use a checkbox to the left of each to-do (as in `mockup-today.html`), with Undo on the toast. The title gets the width |
| Meta lines start with raw pasted text ("Text pasted in · Events: Maya will send the guest list for…") | Review lines | Use the topic from the title rule ("Your pasted notes · guest list"). Fine to leave until the title rule lands |
