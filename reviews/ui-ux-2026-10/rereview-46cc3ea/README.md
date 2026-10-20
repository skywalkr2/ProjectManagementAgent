# UI/UX re-review of batch B-7 at `46cc3ea`

**For:** the main session and the owner.

**What was reviewed:**
- branch `claude/tender-tesla-16a8ob` at `46cc3ea`
- against the re-review at `c8f8e18` (`../rereview-c8f8e18/`), the first-run review (`../first-run/`), and the team's
  status file `docs/project/ui-review-status-2026-10-20.md` (C1–C53, N1–N8)

**How:** the same capture and measuring script as last round, on the same e2e demo, so the numbers compare directly.
That's 135 screens plus four more sources:
- the full `cockpit demo`, for the new examples: moved meeting, held lines, inferred fact, series, rules line
- a brand-new empty workspace, walked through setup again
- `tools/metrics.json`, the measurements
- **`gallery/index.html`, for the owner:** a page with every screen side by side, before and after, plus the new screens
  and first run

---

## 1. Verdict

**B-7 did what was asked, and the measurements prove most of it.**

| Measure | Before (`c8f8e18`) | After (`46cc3ea`) |
|---|---|---|
| Header height at 800–1279px | 88px (two rows) | **56px** (one row at every width from 800 to 2560) |
| First Today line at 1280×720 | 429px | **257px** (target 260) |
| Internal ids on record pages | PER-1, ORG-1, TEAM-1 | **none** |
| Targets under 24px on What changed | 23 | **0** |
| Targets under 24px, all views at 1440 | 7–23 per view | 0–5 per view (only 18px checkboxes left) |
| Font weight 700 | Settings and setup | **gone** |
| Tables beside the pane | words broken, a filled Details button on every row | **clean**: columns step aside, no Details button |
| Follow-up lines on Today | one per item ("Chase X: …") | **one per person** ("Follow up with X") |
| Toasts over controls during Tab | none | none |
| Copy without seeing the message | never | never |

**The new screens** match the design:
- the moved-meeting group (27)
- the inferred fact (29)
- the series page (30)
- "Not now" in the menu (31)

The held line (28) is the exception; see R2. **First run** got the guided AI step, the cloud-folder check, plain Settings
words and the empty-state guidance.

**Still to fix:**
- **Today has internal ids in titles again** ("Drop action ACT-10"). The sweep test doesn't cover Today. (R1)
- **The queue is too tall per line.** Only 4 lines fit at 1280×720 against a target of 6. (R3)
- **Held lines mix verbs.** One decision is called "Keep", "Do it anyway" and "close it?". (R2)
- **Mail on a fresh install is still a dead end** (N2, known). Its wording wasn't changed either, although that part is
  easy. (R5)

---

## 2. Status beside the team's

Only the rows where I differ are listed; I agree with the rest of the team's status file.

| Item | Team | Me | Why |
|---|---|---|---|
| C1 | Partial | **Done** | The header is one row and 56px at 800, 1024, 1100, 1280, 1300, 1440, 1920 and 2560, measured. Plugin panels nest |
| C2 | Partial | **Done** | 56px, no footer, no banner; 48px on a phone |
| C14 | Done | **Partial** | Today titles "Drop action ACT-10" and "Keep: Theo Brandt finished '…'". What changed titles are still "From: Maya Lindqvist" and "From: Jun Park" (R1, R2, R10) |
| C19 | Partial | **Not done** | "ACT-10" and "ACT-14" are in Today titles and the inspector heading, at every width (R1) |
| C48 | Partial | **Not done** | The sweep missed R1 because it doesn't cover Today. Extend it to Today, What changed and Follow-ups |
| C49 | Partial | **Done** | Checked at 1440 with the pane open: Projects and People have no broken words and no Details button (`gallery/compare/03-…`, `04-…`) |
| C47 | Partial | Partial (agree) | The first line is at 257px, under the 260 target, but **4 lines are visible, not 6** (R3) |
| N7 | Done | **Partial** | On a brand-new workspace the header says **"Missed one"** before the assistant has worked on anything (R4) |

**Totals:**
- **C1–C53:** Done 28, Partial 23, Not done 2. The team counted 26 / 27 / 0.
- **N1–N8:** Done 3, Partial 2, Not done 3. The team counted 4 / 1 / 3.

---

## 3. The six choices the team made differently

| # | Choice | Verdict |
|---|---|---|
| 1 | Top priorities are links, not buttons | **Accept.** It reads as context now, and the queue is the one place to act. Shorten the wording (R11) |
| 2 | Reasoning in a title is a lint that sends the item back once | **Accept.** Fuzzy checks shouldn't refuse. R1 is different: an id in a title is exact, so it can be a hard rule |
| 3 | The header is one row at every width | **Accept, and better than my two-row compromise.** Verified at 800–2560 |
| 4 | The pane lays over the table when its columns don't fit | **Accept.** Verified; nothing is squeezed |
| 5 | F25: an explicit yes per AI account, with its identity shown, and no default | **Accept, on two conditions:** the yes appears in the AI step itself, right after the key check passes, and Continue can't skip it silently. If someone skips it, Today's empty state says "Let <account> read your work mail and notes · [Allow]". I couldn't see the yes without a working key; please add a stand-in account to the e2e fixture so it can be screenshotted |
| 6 | Below 1440px the status chip shows only its word | **Accept.** It has its accessible name and the popover |

**Known open: an opened to-do shows owner and due twice.** I didn't hit it in my captures. Leave it on your list.

---

## 4. Findings

Each finding links to its screenshot in `gallery/`.

### R1 [P0] Internal ids in Today titles (C19, C48)

**Seen** (`gallery/new/demo-drop-inspector-1920.png`):
- Today lines titled **"Drop action ACT-10"** and **"Drop action ACT-14"**.
- The inspector heading repeats the id.
- Under it, the note's text is used as a title: "Mark 'Settle the endpaper color' closed; the Print sync will cover it."

**Do:**
- Title the line by the item: **"Drop 'Settle the endpaper color'?"**
- Use the note's words in "Your note", not as a title.
- **Make "no id in a title" an applier invariant.** It's exact, so it can refuse rather than warn.
- **Extend the sweep (C48)** to Today, What changed and Follow-ups.

### R2 [P1] Held lines: one decision, three verbs (answer 28)

**Seen** (`gallery/new/demo-held-inspector-1920.png`):
- The title is "**Keep:** Theo Brandt finished 'Send two spine options'".
- The button says **Keep**.
- The inspector says "**Do it anyway**" and "This rests on something worked out, not something anyone said: **close it?**"
- So does "Keep" mean keep the to-do open, or keep Quill's change? It reads both ways.
- The meta line runs to 3–4 rows: quote · said by · email from · item · Outside · who was told.

**Do** (as answer 28 described):
- **Title the action as a question:** "Close 'Send two spine options'?"
- **Use two visible buttons that name the result:** **Close it** · **Keep it open**. Use the same two words in the
  inspector.
- **Keep the drop the same way:** "Drop 'Confirm the seating plan'?" with **Drop it and draft the note** · **Keep it**.
- **Cut the meta to one line:** the quote and who said it. The source, the "Outside" tag and who was told go in the
  inspector. "Maya Okafor, Ines Duarte were told on Sat, Oct 10" is the reason the drop is held, so it leads the
  inspector.

### R3 [P1] The queue is too tall per line (C47)

**Seen:**
- At 1280×720 the first line is at 257px, but only **4 lines** fit (target 6), because the decision and held lines
  wrap to 3–5 rows (`gallery/compare/01-today-1280.png`).
- The e2e demo now has 30 lines; the full demo has 20.

**Do:**
- **On Today, meta is one line, ellipsized:** the most useful part, such as the quote or who. Everything else is in
  the inspector, or appears when the line expands.
- **Collapse the "Outside" tag into the pill column.** It's the same signal on every review line.
- **Recheck C47** with the measurement in `shell.spec.ts`.

### R4 [P1] Two first-run slips (N7)

**Seen** (`gallery/first-run-after/6-today-first.png`):
- **The header shows "Missed one"** on a brand-new workspace, before the assistant has worked on anything. N7 said
  "Missed one" only appears after it has.
- **The header still says "Workspace"** after the person named it "My projects" in setup. It updates only after a
  reload.

**Do:**
- Hide the header's "Missed one" until the first changeset exists.
- Refresh the setup query when the name is saved, so the header updates.

### R5 [P1] Mail step: the wording is unchanged on a fresh install (F3)

**Seen** (`gallery/first-run-after/3-mail.png`): still "No services listed. Connect a mail folder or private calendar
address below. Connect another service using a mail server folder or a private calendar address." It repeats itself,
and nothing is "below".

**Do:**
- Before the built-in connectors land (N2): "Mail and calendar sign-in comes with an add-on that isn't installed yet. You
  can connect a mail folder or a calendar link now · [Connect one] · or skip this and hand things in by pasting".
- One sentence, one button, one way out.

### R6 [P2] The Done step's cards are still tall and empty (F5)

**Seen** (`gallery/first-run-after/5-done.png`): the words are plainer now ("What kind of work is this?"), but each step
card is still about 130px for one line. The templates sit in a narrow column.

**Do:** use a compact list (step · status · Set up) and give the templates the full width.

### R7 [P2] The series page's details column is cramped

**Seen** (`gallery/new/demo-series-page.png`):
- Labels and values sit side by side in a 360px panel, so "every / Thursday", "The Salt / Orchard launch" and
  "· 3 of 3 / meetings" wrap.
- "Which paper stock does the hardcover use?" is listed under both Agenda and Next.

**Do:**
- In side panels, put the label **above** the value.
- List an item once: in Next, with an "on the agenda" tag.

### R8 [P2] The rules line differs from other rows

**Seen** (`gallery/new/demo-rules-menu.png`):
- Its title is regular weight; every other row title is semibold.
- Its pill says "Rules to look over", where other pills are one or two words.
- The menu is right ("Not now · Back on Today on Tue, Oct 27").

**Do:** pill "Rules", title in semibold.

### R9 [P2] Checkboxes are 18px (C52)

**Seen:** the rail's to-do checkboxes, the Unfiled select boxes and the setup radios are 18×18. They are the only
targets left under 24px.

**Do:** give each a 24px hit area by padding its label. The visible box can stay 18px.

### R10 [P2] What changed titles are still "From: <person>"

**Seen:** "From: Maya Lindqvist", "From: Jun Park" and "From: Theo Brandt" (`gallery/compare/08-what-changed.png`).
Today uses the title rule; What changed doesn't.

**Do:** use the same titles as Today, for example "Email from Jun Park · proof copies".

### R11 [P2] Top priorities wording

**Seen:** "Ines Duarte: follow up on 1 waiting 10 days, 1 overdue, 1 due soon" wraps to three lines of link text.

**Do:** "Ines Duarte · 1 overdue · 1 waiting 10 days". The link is the name only.

### Kept, and worth saying

- **The moved-meeting group** (`gallery/new/demo-moved-open.png`) is exactly answer 27: one group, with **Move it to Thu,
  Oct 22 / Keep Wed, Oct 21** and **It holds / Needs a change…**.
- **The inferred fact** (`gallery/new/demo-inferred-records-project-PRJ-1.png`): the dashed "≈ Inferred" tag, "Quill
  inferred this from Theo Brandt's email, Oct 19", and **Confirm it**.
- **The series page** (`gallery/new/demo-series-page.png`): next meeting by person, "moved from Oct 15's Print sync",
  past meetings, and "every Thursday · in your words".
- **The AI account step** (`gallery/compare/07-first-run-ai.png`): Recommended, four numbered steps, the spending
  sentence, and one Continue with its reason when disabled.
- **Settings → You:** "English spelling: American" and "Find a city".

---

## 5. Order for the next batch

1. **R1:** ids in titles, with an invariant and the sweep extended.
2. **R2 and R3:** held-line wording and one-line meta on Today. Together they bring C47 to 6 visible lines.
3. **R4 and R5:** first-run slips and the mail step's wording.
4. **R6–R11:** in any order.
5. **The F25 yes:** a stand-in account in the fixture, so the yes can be screenshotted.

**New checks:**
- [ ] C54. No Today line, inspector heading or What changed title contains an internal id. An invariant plus the sweep
  enforce it. (R1)
- [ ] C55. A held line's title is a question, and its two buttons name the result, with the same words in the
  inspector. (R2)
- [ ] C56. On Today, every line's meta is one line. (R3)
