# UI/UX re-review at `c8f8e18`

**For:** the main session (batch B-6b) and the design agent.
**Reviewed:** `claude/tender-tesla-16a8ob` at `c8f8e18`, against the original review (`../README.md`, checklist C1–C46),
`../visual-spec.md`, the answers to questions 25–38, and the team's own status file
`docs/project/ui-review-status-2026-10-20.md`.

**How it was checked:**
- **The demo.** I built the commit and ran it on the fictional imprint workspace (`tests/e2e_server.py`), with six
  fixture cases handed in.
- **The capture.** I captured 130 screens: every view at 390, 1440 and 1920 wide, Today and four key views at 800,
  1024, 1100, 1280 and 2560, and dark at 390 and 1440.
- **The measurements.** These are things the team's tests don't measure: where the first queue line sits, ids and raw
  values on every screen, "Loading…", text glyphs, uppercase, bordered nesting depth, target sizes, font sizes and
  weights, horizontal scroll, inner scroll boxes, toast cover during Tab on Today, the Send back button's position, and
  whether Copy fills the clipboard.
- **The files.**
  - `tools/capture-and-measure.mjs` is the script and `tools/metrics.json` its output.
  - `screens/` holds 19 of the shots.
  - I did not re-run the team's own test suites; the main session reports CI green on `c8f8e18`.

---

## 1. Verdict

**This is a different product from the one I first reviewed, and a much better one.** The shell, the queue-first
Today, the inspector, the tables, the drawers, Settings and the setup stepper are all in. The measurements back up most
of the self-report:

- **The header** is 56px from 1280 up, and the agreed two rows (88px) from 1024 to 1279.
- **Content fills the window beside the sidebar on every view.** At 1440 it spans 256–1416px (about 98%); at 1920,
  256–1896px. There is no horizontal scroll at any width tested.
- **Clean text:** zero "Loading…", zero text glyphs and zero uppercase labels on any measured view.
- **Bordered nesting** is at most 2 on every view except the setup stepper (3).
- **Toasts:** none covers a control during Tab on Today. Repeats merge ("Filed 3 reviews · Undo last"), and the stack
  sits right of the sidebar.
- **The inspector** opens on the first line and follows `j`.
- **Copy** on a closed card no longer touches the clipboard. **Send back** is fully in view, with "Undo what it did
  first".
- **The essence is intact:** evidence, whose-words, undo, the keyboard loop and the plain words.

**My count for C1–C46: Done 23, Partial 21, Not done 2.** The team counted Done 23, Partial 23, Not done 0. The two
Not done:
- **C9:** the first queue line sits 429px down at 1280×720, and only 3 lines show.
- **C19:** internal ids and raw values are still on record pages.

**The six things to fix next,** all in §3:
1. **The first queue line sits 429px down.** Three full-width bars (Setup, Backup, This week) stack above the queue.
2. **Record pages still show internal ids and raw values** (PER-1, ORG-1, TEAM-1, "active", 2026-12-01), plus help
   text under every value and empty " · ·" separators.
3. **Tables break words mid-word** whenever the detail pane opens ("Statu/s", "Aver/y Lane"). Each row also has a
   filled "Details" button.
4. **"Top priorities" on the rail repeats the queue's follow-up lines,** with four more primaries. The queue itself
   still has one "Chase" line per item instead of one nudge per person.
5. **Assistant bookkeeping leaks into item titles:** a to-do ending "…: no recorded fact gives its date", a note titled
   "Noted.", a question that is a statement, and the source label "from Jun Park, in From: Jun Park".
6. **What changed opens every row fully,** with "Change" links under each field: 3,200px for 7 items.

### Scorecard, then and now

1 is poor and 5 is excellent.

| Area | First review | Now | Why |
|---|---|---|---|
| Concept and trust patterns | 5 | 5 | Kept intact |
| Use of screen space | 1 | 4 | Full width, panes by width; held back by the stacked bars on Today and tables squeezed by their panes |
| Information architecture | 2 | 4 | Sidebar, real links, Work and Saved items groups, Settings sections |
| Today | 2 | 3.5 | The queue, inspector and rail work; the first line is too low; the rail duplicates the queue |
| Items and records | 2 | 3 | Titles mostly right; ids on record pages; bookkeeping in titles |
| Visual system | 2 | 4 | Tokens, scales and components enforced by stylelint; a few stragglers |
| Forms | 2 | 3.5 | Drawers, autosave Settings, stepper; What changed's inline editing is heavy |
| Mobile | 2 | 3.5 | Bottom bar, clean header, one column; the page is about 5,500px |
| Accessibility | 3.5 | 4 | Focus, toasts, axe in four sizes and two themes; target sizes under 24px on row menus |
| Writing | 4 | 4 | Plain words; a few new leaks (above) |
| Dark mode | 4 | 4.5 | Toggle in the user menu; holds up |

---

## 2. Checklist C1–C46: my status beside the team's

Rows where we agree just cite the evidence. **Bold** rows are where I differ, with the reason.

| Item | Team | Me | Evidence and notes |
|---|---|---|---|
| **C1** | Partial | **Done** | The sidebar groups and nesting are right; the header never wraps. The two-row header at 1024–1279 is an accepted deviation (`screens/05-…`) |
| C2 | Partial | Partial | 56px at ≥1280, 48px on phone, no footer, no banner strip. **New:** at 1280 the header truncates ("Lan…" at 1024, "Assis… last task 3:3…" at 1280), and it gained a "Your pages" text link and a bare ⚠ icon (§3.7) |
| C3 | Done | Done | Measured: header height and main left edge identical on every view (except the full-screen setup stepper, which is fine) |
| C4 | Done | Done | Measured: content 256–1416 at 1440, 256–1896 at 1920, 256–2536 at 2560; no margin over 24px |
| C5 | Partial | Partial | Today's inspector and the People/Projects panes, as reported |
| C6 | Done | Done | — |
| **C7** | Partial | **Done** | Measured at 390×844: bottom bar, no sideways scroll, Needs you before the rail, first queue line at 431px (above the fold) |
| C8 | Done | Done | Ranked, grouped, one primary per line. But 21 lines, of which 5 are per-item "Chase" lines (§3.4) |
| **C9** | Partial | **Not done** | Measured at 1280×720: first queue line **at 429px, 3 lines visible**. Three full-width bars sit above the queue (§3.1). The 140px target in the first review was too tight, since it didn't allow for the page title and the queue header. See the revised target in §3.1 |
| C10 | Done | Done | Decision and "Identify 'Maya'" are top-level lines |
| **C11** | Done | **Partial** | The rail now leads with **Top priorities**, which repeats queue lines with 4 primaries. Agenda carries an inline add-event form, so it is not one line when empty. "This week" is a bar above the queue below 2560 and a rail panel at 2560 (§3.1, §3.4, §3.12) |
| C12 | Done | Done | One row with progress and Continue setup |
| C13 | Partial | Partial | As reported |
| **C14** | Done | **Partial** | Mostly right ("Cover finish for the hardcover: matte or soft-touch?"). Exceptions: a line titled **"Noted."**; a to-do titled **"…paperback edition: no recorded fact gives its date"**; a question titled with a statement, "Corner Lamp Books can host either." (§3.5) |
| C15 | Partial | Done | Measured: maximum bordered depth 2 on every view; the setup stepper is 3 (acceptable in a full-screen flow) |
| C16 | Partial | Partial | Also: People/Projects rows carry a filled **Details** button plus "•••", although the name link and the row already open the pane (§3.3) |
| C17 | Done | Done | Measured: zero uppercase anywhere |
| C18 | Partial | Partial | Help text still under every value; Details still in schema order ("Aliases" first) (§3.2) |
| **C19** | Partial | **Not done** | Measured: **"PER-1"** (project owner), **"ORG-1", "TEAM-1"** (person), raw **"active"**, ISO **"2026-12-01"** on record pages, and **"due: 2026-10-19"** in What changed (§3.2) |
| C20 | Done | Done | Measured: the first press on a closed card leaves the clipboard untouched; the Message / Table switch is there |
| **C21** | Partial | **Done** | Measured: the Send back button at y = 786 of 900, fully in view; "Undo what it did first" ticked |
| C22 | Partial | Partial | 640px drawer, focus returns. The textarea is about 80 characters wide (target 72). "Whose words" is still radios, not a segmented control |
| C23 | Partial | Partial | As reported |
| C24 | Partial | Partial | Disabled **Send back**, **Answer**, **Hand in** and setup **Save** show no reason |
| C25 | Partial | Partial | Merge and cap verified on screen |
| C26 | Done | Done | — |
| **C27** | Done | **Partial** | Tables and board exist, but the **tables break words when the pane is open** (§3.3) |
| C28 | Done | Done | Section nav, form and help; Changed · Reset (`screens/14-…`) |
| C29 | Partial | Partial | Setup's spending fields are typed "(USD)" |
| C30 | Done | Done | Summary line, role pill and state line. The compare wording needs fixing (§3.10) |
| C31 | Done | Done | Stepper with done steps marked. It lacks a primary **Continue** (§3.11) |
| C32 | Done | Done | — |
| **C33** | Done | **Partial** | Measured: weight **700** appears on Settings → AI and in setup. At most 5 sizes per view (fine) |
| C34 | Done | Done | — |
| C35 | Partial | Partial | As reported |
| C36 | Partial | Partial | No glyphs in the main views measured; the leftovers are as the team lists |
| C37 | Partial | Partial | Measured: row **"•••" buttons are 20×30px** on every list (under 24 wide); inline "Change", "Reset" and "Where it came from" links are 22px tall; checkboxes are 18px (§3.8) |
| C38 | Done | Done | — |
| C39 | Partial | Partial | As reported |
| C40 | Done | Done | — |
| C41 | Partial | Partial | No "Loading…" was visible after load on any measured view |
| C42 | Done | Done | — |
| C43 | Partial | Partial | As reported |
| C44 | Done | Done | — |
| C45 | Partial | Partial | Also "From outside · not instructions" repeats in every review line's meta (§3.15) |
| C46 | Done | Done | The prototype still shows the old "Answer 1 decision" example line, as the team noted |

**Totals: Done 23, Partial 21, Not done 2** (the team: 23 / 23 / 0).

### The five bugs I flagged last round

All five are fixed and verified:
- toasts over the navigation
- the empty details pane
- "Answer 1 decision"
- the phone header
- the cramped to-dos (now checkboxes; one long title still wraps to 4 lines at 1440, which is acceptable)

### Questions 25–38

| # | Status | Notes |
|---|---|---|
| 25 AI accounts | Built ✓ | Summary line, role pill, state line, capability line |
| 26 Compare | Built, wording | Empty state is wrong when an account exists but nothing is measured (§3.10) |
| 27 Moved meeting group | **Not seen** | The wording exists; the demo has no moved meeting |
| 28 Held lines with verbs | **Not seen** | "Close it", "Keep it open" and "Drop it" exist in the wording; no held inference in the demo |
| 29 Where a fact came from | Built, bug | "from Jun Park, in From: Jun Park, Tue, Oct 20". The old raw source title leaks into the label (§3.5) |
| 30 Series page | **Not seen** | `SeriesPage.tsx` exists; the demo has no series |
| 31 Not now in the menu | **Not seen** | No rules line in the demo |
| 32 Copy tables | Built ✓ | Message / Table switch, preview before copy |
| 33 Toasts | Built ✓ | Verified |
| 34 Inspector follows the line | Built ✓ | Verified |
| 35 To-do waits on a question | Not checked | — |
| 36 Nudge per person | **Conflict** | `NudgeLeftOut` exists, but Today shows 5 per-item "Chase X: item" lines, plus per-person cards in Top priorities (§3.4) |
| 37 Add-on lines in core groups | Not seen | No add-on lines in the demo |
| 38 N new · Show | Not checked live | The team's tests cover it |

**Ask:** add demo data to the e2e fixture for a moved meeting, a held inference, an inferred fact, a series and a rules
line, so 27–31 can be reviewed on screen. Five of the eight screens from those rounds can't be seen in the demo today.

---

## 3. Findings

### 3.1 [P1] Today: three bars above the queue push the work down (C9, C11)

**Seen** (`screens/01-today-1280.png`): **Setup 3 of 5**, then a **Backup** bar, then a collapsed **This week** bar, each
full width. The queue starts at 347px and its first line at **429px**. At 1280×720 only 3 lines show.

**Do:**
- **Backup:** fold it into the status chip, which already says "Backup needed", and make it an **At risk** queue line
  ("Back up your work · no backup has worked yet · [Back up now]"). One place, not two.
- **This week:** a rail panel at every width. It already is one at 2560.
- **Setup:** keep the setup line. It hides itself once setup is done.

**Revised target** (replaces C9's 140px):
- at 1280×720 with setup unfinished: **first queue line ≤ 260px, at least 6 lines visible**
- with setup done: **≤ 200px**

Add these to `shell.spec.ts`.

### 3.2 [P1] Record pages: ids, raw values, help text and empty separators (C18, C19)

**Seen** (`screens/09-person-record-ids.png`, `10-project-record.png`):
- **Person page:** Org "ORG-1", Team "TEAM-1", Status "active", "Name verified: No", with its schema description
  ("True when the name's spelling came from the person…; false when…"). Fields are in schema order, Aliases first.
- **Project page:** Owner "PER-1", Target "2026-12-01". Links show the raw address broken over three lines.
- **Open items** end in empty separators: "Sam Rivera · due Fri, Oct 16 · ·", "Avery Lane · ·", or a lone "·".
- **Activity lines** end in field keys: "· Work", "· To", "· Why they matter", "· Target".
- **Activity says "The assistant"** where the rest of the app says Quill.

**Do:**
- Resolve every reference to its name: person, organization, team.
- Format dates ("Tue, Dec 1").
- Map enums to labels ("Active").
- Drop the help text on view.
- Order details: name, role, organization, how to reach, then the rest.
- Join meta parts only when they're non-empty.
- Activity reads "Quill changed the due date of **Send two spine options**", using the field's label, never its key.
- Links show their title, with the domain as a hint.

**Test:** a sweep test (Playwright or Vitest) that renders every record kind and fails on `/\b[A-Z]{2,5}-\d+\b/`, on
`\d{4}-\d{2}-\d{2}`, on `· ·` and on schema enum values.

### 3.3 [P1] Tables break words when the detail pane opens (C27, C16)

**Seen** (`screens/07-projects-table-words-broken.png`, `08-people-table-pane.png`): with the pane open at 1440, the
table gets about 715px.
- **Projects** squeezes 9 columns: "Statu/s", "Stag/e", "Targ/et", "Last/upda/ted", "Wint/er List", "Aver/y Lane".
- **People** breaks "Organizati/on", "coordinato/r", and "maya.okaf/or@examp/le.org".
- **Every row** has a filled **Details** button and a "•••", although the name link and a row click already open the
  pane.

**Do:**
- **Never break inside a word:** `overflow-wrap: normal; word-break: normal`, with headers on one line. Long emails and
  addresses get an ellipsis, with the full value in the pane.
- **Columns get a priority.** When the pane opens, keep Name, Status, Target, Owner and Open items; hide the rest behind
  the column picker. When even those don't fit, the pane overlays the table rather than squeezing it.
- **Remove the per-row Details button.** A row click, Enter on a focused row, or the name link opens the pane. The menu
  keeps the rest. That also removes 7–9 filled primaries per table.
- **The People organization filter** is a full-width select: size it to its content. The Organizations list below is
  still the old card style; make it a table or a filter.

### 3.4 [P1] One row per thing: "Top priorities" repeats the queue, and follow-ups are per item (C11, answer 36)

**Seen** (`screens/02-today-1920.png`):
- **The queue's Send group** has "Send 2 to-dos to Sam Rivera" and so on, then **five "Chase <person>: <item>, due …"
  lines, one per item.**
- **The rail's new Top priorities panel** shows "Sam Rivera: 2 overdue · [Review & copy]" for the same people, with 4
  more filled primaries.
- **The total is 21 lines,** and the same person can appear in three places.

**Do:**
- **One follow-up line per person** in the queue: "Follow up with Sam Rivera · 2 overdue, oldest Tue, Oct 13 · [Draft a
  nudge]". It opens the one-per-person nudge from answer 36, which `NudgeLeftOut` already supports. That cuts five lines
  to three in the demo.
- **Top priorities:** either remove it, or make it **context without actions**: no buttons, with each entry linking to
  its queue line. Show it only for things not already in the queue (cross-project risks, for example). The queue is the
  only place to act.

### 3.5 [P1] Assistant bookkeeping in item text (C14, answer 29)

**Seen:**
- **A to-do titled** "Reply to Corner Lamp Books about the paperback edition: **no recorded fact gives its date**". The
  assistant's reasoning became part of a to-do that may be sent to someone.
- **A note titled "Noted."**, as a Today line and on Projects → Unfiled.
- **A question to the PM whose text is a statement:** "Corner Lamp Books can host either."
- **A fact's source label:** "from Jun Park, **in From: Jun Park**, Tue, Oct 20".

**Do:**
- **A lint in the applier:**
  - to-do and question titles contain no reasoning clauses
  - a question's text ends in a question mark, or is rewritten as one
  - a title under three words falls back to the source title
- **Reasoning belongs in "Quill says".**
- **The provenance label** uses the person and the kind of source ("from Jun Park's email, Oct 20"), never the source's
  raw title.

The first one breaks a product rule ("questions are written for their reader… no bookkeeping"), so treat it as a P1,
not as polish.

### 3.6 [P2] What changed: every row fully open, with "Change" under every field

**Seen** (`screens/11-what-changed-expanded.png`): every change is expanded. Each to-do shows "Who owes it / Promised to
/ Due", with a separate "Change" link under each value and "Where it came from" below. Seven changes make a 3,200px page,
with 23 targets under 24px.

**Do:**
- **Open the first item only.** The rest stay one line each. The inspector pattern from Today is the long-term answer
  (list | detail).
- **Edit in the meta line:** "Theo Brandt · due Fri, Oct 16 · promised to no one". Each part is a button that opens a
  small popover. No stacked links.

### 3.7 [P2] Header crowding at 1024–1440

**Seen:**
- "Lan…" at 1024.
- "Assis… ✓ last task 3:3…" at 1280.
- A new "**Your pages**" text link and a bare **⚠** icon between the status chip and Hand in.

**Do:**
- **Below 1440:** the assistant's state goes into the status chip's popover, as on the phone. The workspace name never
  truncates before the Ask field does.
- **"Your pages":** into the user menu or the sidebar's Saved items.
- **⚠:** give it a label, or fold it into the status chip, which is the one place for "something needs attention".

### 3.8 [P2] Target sizes (C37, WCAG 2.5.8)

**Seen:**
- Row "•••" buttons are **20×30px** on every list.
- "Change", "Reset" and "Where it came from" are 22px tall.
- Checkboxes are 18px.

**Do:** IconButton at least 32×32 (24×24 is the floor). Inline text buttons at least 24px tall. Checkbox hit area at
least 24px, by padding the label. Add a check to `a11y.spec.ts` that no visible interactive element is under 24×24.

### 3.9 [P2] Weight 700 (C33)

**Seen:** on Settings → AI and in setup.

**Do:** add a stylelint rule that allows only the weight tokens.

### 3.10 [P2] AI compare wording

**Seen** (`screens/15-ai-compare-empty.png`): "There is nothing to compare yet. Add an account first." But an account
exists; nothing has been measured. The account row reads "Good at 0 of 14 kinds of work · 14 not measured", which sounds
like failure.

**Do:**
- The compare page says "Nothing measured yet · [Measure (about $x)]".
- The row says "Not measured yet · [Measure]" until at least one skill has a result.

### 3.11 [P2] Setup stepper

**Seen** (`screens/16-setup-stepper.png`):
- No primary **Continue**. The step has a disabled **Save**, then **Back**, then a "Skip for now" link.
- The spending amounts are typed "(USD)" fields.

**Do:**
- **Continue** is the primary action. It saves and moves on.
- **Skip for now** becomes a secondary button.
- Disabled buttons say why.
- Use currency inputs with "$".

### 3.12 [P2] An inline form on the rail

**Seen:** the Agenda panel on Today carries an inline add-event form (What, Day, Time, Add), on the phone too.

**Do:** use an "Add to agenda" button that opens the drawer. An empty Agenda is one line.

### 3.13 [P2] Small layout points

- **The inspector header** "1 of 21 · j / k" wraps onto two lines. Make it `nowrap`.
- **The Send back textarea** spans about 1,130px, and its disabled submit gives no reason. Limit it to 72ch and give the
  reason.
- **The hand-in drawer's "Whose words"** is still two stacked radios. Use the segmented control.

### 3.14 [P2] The phone page is about 5,500px

**Seen** (`screens/04-today-390-full.png`): queue, then Top priorities, then This week, then Agenda with its form, then
to-dos, then Came in.

**Do:**
- Once §3.1, §3.4 and §3.12 land, collapse the rail panels below the queue to one line each ("Agenda · nothing
  today", "To-dos · 3").
- The review mode is the phone's main path.

### 3.15 [P2] "From outside · not instructions" on every review line

**Seen:** the full phrase repeats in the meta of every review line, often wrapping the line to three rows.

**Do:**
- In the queue, use a short neutral tag, "Outside", with the full phrase as its accessible name and in the inspector.
- Keep the full phrase where the content is shown (the source block).

---

## 4. Order of work

1. **§3.2 and §3.5:** ids and bookkeeping. These are product-rule breaks, and the sweep tests stop them coming back.
2. **§3.1 and §3.4:** Today's first screen, and one row per thing.
3. **§3.3:** tables with panes.
4. **§3.6–3.15:** in any order. Each is small.
5. **Demo data** for 27–31, so the next review can see them.

## 5. Checklist delta for the next pass

Add these to the master checklist, so the next re-review checks them:
- [ ] C47. Today at 1280×720 with setup unfinished: first queue line at most 260px, at least 6 lines visible (with
  setup done, at most 200px). (3.1)
- [ ] C48. A sweep test over every view and record kind finds no id, ISO date, raw enum or empty separator. (3.2)
- [ ] C49. With the detail pane open at 1440, no table header or cell breaks inside a word; rows have no filled Details
  button. (3.3)
- [ ] C50. Every person appears in the queue at most once per verb; the rail has no primary buttons. (3.4)
- [ ] C51. The applier refuses reasoning in titles, statement-questions, and raw source titles in provenance. (3.5)
- [ ] C52. No visible interactive element smaller than 24×24. (3.8)
- [ ] C53. The fixture shows a moved meeting, a held inference, an inferred fact, a series and a rules line. (§2)
