# UI/UX re-review of batch B-8 at `0f37be4`

**For:** the main session and the owner.

**What was reviewed:** branch `claude/tender-tesla-16a8ob` at `0f37be4`, against my B-7 review
(`../rereview-46cc3ea/`), with the same capture and measurements on the same demos.

**What was captured:**
- the e2e demo (135 screens)
- the e2e demo with `--standin-account`, for F25
- the full `cockpit demo`
- a brand-new workspace, through first-run setup

**For the owner:** `gallery/index.html` puts B-7 and B-8 side by side for every screen.

## 1. Verdict

**B-8 closes everything from the last review.** Measured:

| Measure | B-7 (`46cc3ea`) | B-8 (`0f37be4`) |
|---|---|---|
| Internal ids on any screen, at any width | ACT-10 and ACT-14 on Today | **none** |
| Targets under 24px, on every view at every width | 0–5 per view (checkboxes) | **0** |
| Today lines visible at 1280×720 | 4 | **6** (first line at 257px) |
| Today lines visible at 1440 and 1920 | 7 and 8 | **9 and 12** |
| Held-line wording | "Keep" / "Do it anyway" / "close it?" | **"Close 'Send two spine options'?" · Keep it open / Close it** |
| Header, toasts, Copy, Send back | pass | still pass |

**Every finding from the last review is fixed and confirmed on screen:**

| Finding | What's on screen now |
|---|---|
| R1 | Titles name items, never ids |
| R2 | Held lines ask one question with two answers |
| R3 | Today meta is one line |
| R4 | No premature "Missed one"; the workspace name updates at once |
| R5 | The mail step is one sentence with one button |
| R6 | Done is a compact list |
| R7 | The series panel puts labels above values, with no duplicate item |
| R8 | The rules line has the "Rules" pill and a semibold title |
| R9 | Every checkbox and radio is a 24px target |
| R10 | What changed titles follow the title rule |
| R11 | Top priorities read "name · 1 overdue · …" |

**F25 is on screen for the first time:** "Let Second stand-in read your work mail and notes · Allow"
(`gallery/new-after/access-today-1440.png`).

**One structural problem is left (S1):** the same decision appears twice in the queue. It's under Decide as a held
line, and again under Review inside its change. The details pane shows the same overlap (S2).

## 2. Status

The team's status file `docs/project/ui-review-status-2026-10-20.md` **still shows the B-7 marks**, so please update it
for B-8. Here is my count.

**C1–C53: Done 32, Partial 21, Not done 0.**

What changed since my B-7 count (28 / 23 / 2):
- **C19 and C48 are now Done:** no id on any measured view.
- **C47 is now Done:** 6 lines fit at 1280×720.
- **C52 is now Done:** no target under 24px anywhere.
- **C14 stays Partial,** because of S4.

**C54–C56: Done 2, Partial 1.**
- C54 (no id in a title): Done.
- C56 (Today meta is one line): Done.
- C55 (held lines asked as a question with two answers): Partial. The line is right; the details pane still shows the
  parent review's "Looks good" and says "Closed a to-do" (S2).

**N1–N8: Done 5, Partial 0, Not done 3.**
- N3 is Done as decided under F25.
- N7 is Done.
- Still Not done:
  - N1, the installer
  - N2, built-in mail and calendar sign-in
  - N8, the test with real people

## 3. Your two calls

1. **Tighter row padding on Today: accept.** The rows still read clearly, and the sixth line fits.
2. **Lines about stopped work wrap to two lines: accept.** "Why, and until when" is the point of those lines, and they
   have no details pane to hold the rest.

## 4. Findings

### S1 [P1] One decision, two queue lines (one row per thing)

**Seen** (`gallery/after/1920-today.png`):
- "Drop 'Confirm the seating plan for the launch reading'?" is under **Decide**, with Keep it / Drop it.
- "Drop 'Confirm the seating plan for the launch reading'" is under **Review**, with All looks good.
- Likewise, "Close 'Send two spine options'?" (Decide) sits inside "Look over 2 things Quill did · Email from Theo
  Brandt · Send two spine options · 1 waits for you" (Review).
- The new titles make the duplication obvious: two lines and two buttons for one thing.
- A person could press All looks good and believe the drop is settled.

**Do:** the held op leaves its change's review.
- The review line counts it ("1 waits for you, under Decide") and links to it.
- **Approving the review never approves a held op.**
- If the change holds nothing but the held op, the review line doesn't appear at all.

**Proposed check:** C57. No item appears on two Today lines.

### S2 [P1] The held line's details pane mixes in the parent review

**Seen** (`gallery/compare/02-held-line.png`, right):
- The pane for "Close 'Send two spine options'?" opens on the whole change: "Email from Theo Brandt · Send two spine
  options", with **Looks good** at the top.
- Further down is a card labelled "**Closed** a to-do" with Keep it open / Close it, but nothing has been closed yet.

**Do:**
- The pane shows only the held decision: the question, the quote and who said it, where it came from, why it's held
  ("This rests on something worked out, not something anyone said"), and the same two answers.
- Hold labels use the conditional: "Would close a to-do", "Would drop a to-do".

### S3 [P2] Titles out of line on the Access and Rules lines

**Seen** (`gallery/new-after/access-today-1440.png`): the Access line's title starts about 70px left of the other
titles, and so does the Rules line's. Their pill column is narrower.

**Do:** give the pill column the same fixed width on every row.

### S4 [P2] Some titles fall back to a cut-off first sentence (C14)

**Seen:**
- In What changed: "Email from Maya Lindqvist · We can host the reading at 6 pm…" and "Your pasted notes · Jacket
  update: the approval of the back-cover copy…".
- "Work Quill started" is used as a title.

**Do:**
- Ask the model for a topic of 3–6 words, and use the first sentence only as a last resort.
- "Work Quill started" should say what the work was.

### S5 [P2] Drops under review read as commands

**Seen:** "Drop 'Settle the endpaper color'" with **All looks good**. The title is an order, but the review is about
something Quill already did.

**Do:** under Review, past tense ("Quill dropped 'Settle the endpaper color'"). Under Decide, a question ("Drop …?").

### S6 [P2] The mail step offers two ways to skip

**Seen** (`gallery/first-run-after/3-mail.png`): with nothing connected, both **I'll do this later** and **Continue**
are shown, and they do the same thing.

**Do:** while nothing is connected, show only "I'll do this later". Continue appears once something is connected.

## 5. Next

1. **S1 and S2:** one row per thing, with an honest details pane.
2. **S3–S6:** small fixes.
3. **Unchanged from earlier reviews, still the largest items:**
   - N1, the one-click installer
   - N2, built-in mail and calendar sign-in
   - N8, three real people setting it up alone
