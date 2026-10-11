# PM Cockpit: UI/UX review

**For:** the design agent working on `docs/design/` (Part 7 and the prototype) and the screens in `web/src/`.
**Reviewed:** branch `claude/tender-tesla-16a8ob` at commit `5239897` (the most complete build), against the original
`DESIGN.md`, the Design 1.0 split in `docs/design/` (Parts 1, 7, 8), `docs/design/prototypes/today.html`,
`docs/decisions.md` and `docs/project/ux-notes.md`.
**Method:**
- I ran the app on the fictional imprint workspace with the stand-in AI (`tests/e2e_server.py`) and handed in four of the
  fixture cases so the screens had real content.
- I captured every view at 1440×900, 1280×720, 900×1000 and 390×844, in light and dark (`screens/`).
- I audited `web/src` line by line against 7.0, 7.6, 7.10 and 7.11.
- I compared both against the Today prototype.
- All data shown is the fictional demo data.

---

## 1. Verdict

The essence is here, and some of it is excellent. These patterns are better than most shipping AI products and should
be kept:

- **"Whose words are these?"** on hand-in.
- **"Because: '…'" evidence lines** with the source passage highlighted.
- **Undo toasts instead of "are you sure?"**
- **Copy, then Mark sent.**
- **The j/k/a/s/c/u keyboard loop.**
- **Plain words almost everywhere.**

The problem is not the ideas. It is how they are arranged. The product promises *"one screen that says what to do
today."* The build delivers a screen where:

- **the work is hard to find.** The column that holds it ("Needs you") gets a quarter of the width and its own scroll
  box. Empty informational columns take half the screen.
- **items have no names.** Rows are titled with the first line of whatever was pasted ("Hi team,", "From: Jun Park").
- **decisions are buried.** "Who is Maya?" sits four containers deep.
- **setup and system chrome come first.** About 40% of a laptop screen, and the whole first phone screen, is spent on
  banners and setup cards before any work.
- **there is no visual system.** There are 16 font sizes, 21 spacing values, 11 corner radii, about 9 button styles,
  3 segmented controls, cards nested in cards, and ALL-CAPS labels for whole sentences.
- **the navigation sprawls.** There are 8 flat tabs plus one per plugin, mixing daily work, records, plumbing and admin.
  The header changes width and position between views.

The reference prototype (`screens/16-prototype-today.png`) is the clearest statement of what the owner wanted: a short
ranked list of verbs ("Answer 1 decision", "Look over 4 things the assistant did"), each with one button. **The fastest
route to "best practice" is to make the built Today feel like that prototype, while honoring the owner's later decision
to use the full laptop width** (see 3.1).

### Scorecard

1 is poor and 5 is excellent.

| Area | Score | One line |
|---|---|---|
| Concept and trust patterns | 5 | Evidence, whose-words, undo and approval gates are best-in-class ideas |
| Information architecture | 2 | Flat 8+N tabs; Today hides the queue; key spec surfaces missing |
| Today (home) | 2 | Dashboard with the work squeezed into one quarter, nested scrolls, decisions buried |
| Item design (rows) | 2 | No meaningful titles; 4–5 levels of nesting; pill overload |
| Visual design and system | 2 | Clean palette and tokens, but no scale; serif and sans clash; inconsistent components |
| Forms (hand-in, settings, setup) | 2 | Settings and setup are long config dumps; hand-in is good in content, weak in form |
| Mobile | 2 | One column works mechanically; priorities inverted; first screen is all chrome |
| Accessibility | 4 | React Aria menus and dialogs, live regions, focus ring, axe in end-to-end tests; a few gaps |
| Writing (microcopy) | 4 | Calm and plain; a few CLI commands, config paths and vague phrases leak through |
| Dark mode | 4 | Works via tokens; there is no in-app toggle |

---

## 2. What to keep

The design agent must not lose these in a redesign.

1. **Evidence lines** (`screens/03-evidence-nested.png`): a quoted "Because" plus **Show source** with a highlighted
   passage, and an "outside content" tag. This is the product's trust engine. Make it *more* visible, not less.
2. **Hand-in's "Whose words are these?"** (`screens/08-hand-in.png`). It teaches the security model in plain words.
3. **Undo toasts** with `u` to undo. There is no `window.confirm` anywhere. Toasts pause on hover and focus, and stay
   when reduced motion is on.
4. **The keyboard loop** (j/k/Enter/a/s/c/e/u/n, / and ?). It is guarded while typing, configurable, and the help dialog
   lists it.
5. **One primary action plus a "•••" menu.** `RowMenu` (React Aria) is used in 14 components, and its trigger is
   labelled "More actions for {item}".
6. **The wording sheet.** It has 1,152 keys and about 99% of strings come from it. Internal terms (changeset, op, tier,
   ledger) never appear on screen.
7. **Empty states that offer the next step:** "Connect a calendar" and "Connect a mailbox".
8. **The header's live indicator, backup nag and Back up now.** This is the right *content*, though it is in the wrong
   form (see 3.4).
9. **The DEMO strip:** "Everything here is made up. Nothing you do here reaches anyone."
10. **Accessibility work already done:**
    - React Aria dialogs and menus
    - `aria-live` toasts
    - a skip link
    - a global `:focus-visible` ring
    - no clickable `div`s
    - labelled inputs
    - axe checks in Playwright

---

## 3. Findings

Each finding gives what I saw, why it matters, what to do, and how to know it's done.

- **P0** threatens the core promise.
- **P1** is a structural UX debt.
- **P2** is polish and consistency.

### 3.1 [P0] Today does not answer "what do I do next?"

**Seen** (`screens/02-today-populated.png`, `05-today-tablet.png`):
- Today is four equal-ish columns: Agenda, To do, Needs you and Came in.
- "Needs you (13)" holds all the review and decision work, but gets about 25% of the width and an inner scroll box.
  Only about 2.5 of the 13 items show at 1440×900.
- At 900px (a 2×2 grid) it is a box roughly 200px tall.
- Agenda and Came in are empty, and together take about 50% of the width.
- Inside Needs you, two whole panels are embedded ("What changed" with its own 3-way filter, and "Chasers" with its own
  2-way filter). So the user meets filters inside a column inside a page.

**Why it matters:**
- Part 1 promises "one screen that says what to do today".
- 7.0 and 7.7 call for "a queue, not a dashboard … one ranked list, each line actionable where it stands … nothing
  informational sits on Today."
- The owner later decided (`docs/decisions.md`, 2026-10-11) that Today should be a dashboard using the laptop width, so
  nothing hides below the fold.
- The build satisfies the letter of that decision but defeats its purpose: the important things are now *more* hidden,
  inside a narrow scroll box.

**Do:** build a **queue-first dashboard**.
- **Needs you is the main column**, at about 55–60% of the width, on the left where the eye starts.
  - Render it as the prototype's verb lines, ranked: "Answer 1 decision · [Answer]", "Pick who 'Maya' is · [Pick]",
    "Look over 4 things Quill did · [All looks good]", "Send 3 questions to Maya Okafor · [Copy]".
  - Each line expands in place to its items.
  - **No embedded panels and no filters inside the column.** The full What changed and Chasers views with filters live
    under Work.
- **Agenda, To do and Came in form a right-hand rail**, stacked, each sized to its content.
  - An empty one collapses to a single line ("No calendar connected · Connect").
  - A long one shows the first 5 with "Show all 12".
- At most **one scroll region**: the page. Drop the per-column scroll lock. A fixed-height board with nested scrolls is
  hostile to trackpads, screen readers and print, and it hides counts.
- **Ordering rules** go in the spec: decisions and held items first, then overdue, then today's sends, then reviews, then
  everything else.

**Done when:**
- At 1280×720 every top-level line of Needs you is visible without inner scrolling for a typical day of 6–10 lines.
- The first thing read on the page is a verb with a button.
- Empty columns take one line.

**Design doc:** 7.7 and the 2026-10-11 decision contradict each other. Replace both with one written rule ("Today is a
ranked queue with a context rail"), and **update `prototypes/today.html`** to show the two-zone layout. The prototype is
what builders follow.

### 3.2 [P0] Items have no names

**Seen** (`screens/02-today-populated.png`): review rows are titled "Hi team,", "From: Jun Park", "Events: Maya will send
the guest list for the…" and "Production check-in, Oct 8". The cause is `WhatChanged.tsx:167`:
`item.source_title || firstLine(item.note)`. Under each title, "Quill did 1 thing" does not say *what* it did.

**Why it matters:** a title is how people scan, remember and refer to items. A greeting line is not a name. With 10+ rows
the list becomes unreadable, and keyboard (j/k) users hear "Hi team," over and over.

**Do:** define a **title rule** in the spec and implement it in the engine, not the UI.
- Titles take the form "{Kind} from {person} · {topic}", for example "Email from Theo Brandt · cover proof" or "Your note
  · launch reading".
- Build them from structured fields first: headers, sender and subject.
- When those are missing, use the changeset's `summary`. The model already writes "Recorded the proof date", so ask it
  for a 3–6 word topic as well.
- Only fall back to the first line as a last resort, and then strip greetings.
- Replace "Quill did 1 thing" with the outcome: "Filed 1 note", or "Added 3 actions · 1 waits for you".

**Done when:** no row on any screen starts with a greeting, "From:", or a truncated sentence.

### 3.3 [P0] Decisions and blockers are buried four levels deep

**Seen** (`screens/03-evidence-nested.png`):
- To answer "Who is 'Maya'?" the user must open Needs you, then What changed, find the review card, expand it, find the
  "Added an action · Waiting for you" child card, and use the picker at its bottom. That is five nested containers.
- The decision "Cover finish for the hardcover" is a textarea inside the "You" card inside Chasers inside Needs you
  (`screens/01-today-first-run.png`), where it is cut off by the column's scroll.

**Why it matters:**
- The design says "Decisions are questions addressed to the PM."
- The prototype gives each one its own top line ("Answer 1 decision", "Pick an owner for 1 action").
- Held items block the assistant's work, so they are the highest-value clicks in the product.

**Do:**
- Every held item becomes its own top-level Today line with its own primary action: a decision, "who is this?", "pick an
  owner", or a waiting-for-go.
- Its place in the review card becomes a small "Waiting for you, see Today" note.
- **Cap nesting at two levels**: a line, and its items.

**Done when:** every decision or held item is reachable in one click from Today, and no screen has more than two nested
bordered containers.

### 3.4 [P0] Setup and system chrome sit above the work

**Seen:**
- At 1440×900 (`screens/01-today-first-run.png`), these take about 380px before any work appears:
  - the DEMO strip
  - a two-row header
  - an amber "assistant is a stand-in" notice, which ends with a terminal command, "cockpit ai test"
  - a "Start here" card
- On a phone (`screens/06-phone-first-screen.png`) the **whole first screen** is chrome, and the first content is an
  empty Agenda.

**Why it matters:**
- Users learn to ignore banners within a day (banner blindness).
- The stand-in notice and Start here repeat the same message ("add an AI account").
- A terminal command breaks 7.6: "never answer with an instruction the screen can't carry out."

**Do:**
- Merge the stand-in notice into Start here, and make Start here **one slim line**: "Setup · 1 of 6 left: Add an AI
  account [Continue]". Or make it a Today line ranked by importance.
- Replace every CLI instruction with a button that does it. "Test connection" already exists on the AI accounts screen.
- On a phone, the first thing below the header is the first Needs-you line.

**Done when:**
- The first work item starts within 200px of the top of the page at 1280×720.
- No user-facing string contains `cockpit …`, a `.yaml` name or a config key path. There are 9 such strings today; see
  §5.

### 3.5 [P1] The navigation is flat, long, and grows with every plugin

**Seen:**
- The header nav is Today, Stages, Files, Sources, Pieces, People & projects, Settings and Add-ons. That is 7 fixed items
  plus one per plugin panel (`Header.tsx:63-93`).
- Daily work (Today), record lists (Pieces, Files, People & projects), plumbing (Sources, Stages) and admin (Settings,
  Add-ons) share one segmented control.
- On every non-Today view at 1440px the control **wraps onto two rows** (`screens/09-stages-header-shift.png`).
- On a phone it is a sideways strip clipped mid-word ("People & p") with no scroll cue.
- The setup guide is not in the nav at all.
- Nav items are `<button>`s, not links, so they cannot be opened in a new tab and have no real URLs to share.

**Why it matters:**
- The spec's model was four tabs: Today, Work, Portfolio and Admin. That kept the top level about *jobs*, not *data
  types*.
- An unbounded plugin list will break the header.
- A segmented control is the wrong pattern for more than about 5 options.

**Do:**
- **Primary nav at most 5:**
  - **Today**
  - **Work**: What changed, Chasers (follow-ups), Waiting to go out, Stages, and plugin work panels as a sub-nav
  - **Projects**: the portfolio, people and organizations
  - **Files**
- A **gear menu** for Settings, Sources, Add-ons, Setup guide and Feedback.
- Make plugins register into Work's sub-nav, never the top level, and **put a nav budget in the spec**.
- Use real links (`<a href="#work/stages">`).
- On phone, use a bottom tab bar (Today · Work · + Hand in · Ask · More).

**Done when:**
- The header nav never wraps at 1024px or wider.
- Adding three plugins does not change the header.
- Every view has a link that can be bookmarked.

### 3.6 [P1] The layout jumps between views

**Seen:**
- Today is full-bleed. Every other view is a centered 880px column.
- So the header itself moves: the brand jumps from x≈16 to x≈280, the nav wraps, and the actions shift.
- Compare `02-today-populated.png` with `09-stages-header-shift.png`.

**Why it matters:** a shell that moves when you change tabs feels broken, and breaks the spatial memory people use to
find controls.

**Do:**
- **One app shell**: the header is always full width with fixed positions.
- Only the *content* width changes by view type: board views full width, lists and forms at about 880px.

**Done when:** switching any two views changes nothing above the content area.

### 3.7 [P1] The outward approval surface is missing

**Seen:**
- There is no "Waiting to go out" view (7.4): no drafts, no word-level diff, no Approve.
- There is no Portfolio health view (7.1).
- The header has no Log, Jobs, Today count or date.
- The only outward content today is copied messages.

**Why it matters:** "The AI drafts. The human approves everything that goes out" is the product's headline, and the
approval-of-a-diff experience is its most distinctive screen. Some of this is planned for version 1. But until it exists
the UI can't be judged on its core promise, and the IA in 3.5 needs a place reserved for it now, so it doesn't arrive as
tab number 9.

**Do:**
- Reserve Work → Waiting to go out now, with a useful empty state ("Nothing waiting to go out. Drafts appear here for
  your approval").
- Design the diff review screen next, from 7.4, as a full-page compare view (the existing text review screen is a start).

### 3.8 [P1] Copy can put text on the clipboard that the user has not seen

**Seen:**
- On a collapsed Chasers card, **Copy 2** writes the message to the clipboard straight away, without showing it. The only
  feedback is a "Copied" toast (`screens/04-chasers-after-copy.png`).
- The card then shows **Mark sent**, which was right.

**Why it matters:** 7.5 says "Copy shows the message it will copy, editable in place." Pasting text you haven't read into
an email to a colleague is exactly the outward risk the product exists to prevent.

**Do:** the first click on a collapsed card **expands it to show the message**, editable, with Copy under it. Or show it
in a popover. Copying from the keyboard (`c`) on a collapsed row should do the same.

**Done when:** text is never placed on the clipboard without the message being on screen at that moment.

### 3.9 [P1] Visual hierarchy: too many boxes, too many pills, too many capitals

**Seen** (`screens/02`, `03`, `11`):
- **Five levels of bordered containers:** column card, then section, then row card, then child card, then source card.
- **ALL-CAPS labels for sentences**, such as "FILED A NOTE UNDER THE SALT ORCHARD LAUNCH" and "ADDED AN ACTION".
- **Pills with no semantic system:**
  - every person carries an "ACTIVE" pill
  - a project's group shows as a grey "WINTER LIST" pill that reads like a status
  - "NOT DONE YET", "NOT STARTED", "REVIEW", "WAITING FOR YOU" and "YOU" all look alike
- **People & projects has four filled primary buttons** on one page.
- On the Organizations rows the "•••" sits beside the name instead of at the right edge, as it does everywhere else.

**Why it matters:**
- When everything is boxed, nothing stands out. Borders should mark *units of action*, not every grouping.
- Uppercase removes word shapes, so long caps strings are much slower to read.
- Pills on every row train people to ignore pills, including the one that matters ("Waiting for you").

**Do:**
- Inside a column or list, separate rows with **dividers**, not cards. Keep borders for top-level containers only.
- **Sentence case** for all labels. Use small caps or tracking only for one-to-two-word section eyebrows.
- **Pills only for state that changes what you should do.** Hide default states such as "Active" and show the exceptions
  ("Inactive", "Track only").
- Define **4 pill tones**, each always paired with a word:
  - neutral: info
  - accent: needs you
  - warn: waiting or at risk
  - ok: done
- **One filled primary per region.** Section "Add …" buttons become secondary.
- Right-align every row menu.

**Done when:**
- No screen shows more than two levels of borders.
- No label over 3 words is uppercase.
- A pill appears on fewer than a third of the rows in any list.

### 3.10 [P1] Settings is a config file with a form around it

**Seen** (`screens/12-settings-full-page.png`, 5,446px tall at 1440 wide):
- **One long page with no section nav**, and six separate **Save** buttons.
- Every field repeats "Default: x" plus **Back to default**, even when the value already equals the default.
- **Raw machine values** for the time zone ("America/New_York"), language ("en-US") and money ("0.25").
- **AI accounts listed by internal id** ("stub", "low-cost", "router", "coding-agent"), with "Key not found: key from the
  environment variable LOWCOST_AI_KEY".
- The same AI accounts block appears again in the setup guide.
- Value lists (status, phase and so on) take about 40% of the page.
- The "Synced folder" setting appears in Settings *and* at the bottom of People & projects.

**Why it matters:** 7.9 asks for "grouped by file and topic; basic keys first, advanced behind a toggle; search … inline
descriptions." The search exists. The rest reads as YAML rendered as HTML, and the per-section Save buttons make it easy
to lose edits.

**Do:**
- **A left section rail:** General, You, AI accounts, Spending, Backups and sync, Lists, Sign-ins, Advanced.
- **Autosave each field** with an undo toast, matching the app's undo-first rule. Or use one sticky "Save changes" bar.
  Never six Save buttons.
- Show **"Changed · Reset"** only when a value differs from its default.
- Use **pickers**: time zone (searchable, with the city name), language (named), currency inputs with a "$" prefix.
- **AI accounts** get display names ("Low-cost account", "Router") and a status chip ("Ready", "Key missing",
  "Untested").
- Put environment-variable details behind "Details". Most users will never type `env:`.
- **Lists** move to their own tab.
- **Synced folder** lives in one place.

**Done when:**
- Any setting is reachable in two clicks without scrolling past unrelated ones.
- No raw environment variable, IANA id or locale tag shows by default.

### 3.11 [P1] The setup guide is a long page, not a guide

**Seen** (`screens/13-setup-guide.png`):
- All seven steps are fully expanded on one page, about 3,500px long.
- Finished steps keep their full forms. For example, "Name the workspace" (Done) still shows three fields and a disabled
  Save.
- The AI step shows 12 provider cards plus an internal accounts list.

**Why it matters:** a first run should give a sense of progress and one clear next step. 7.8 says "a short setup, each
step skippable." Showing everything at once is a wall of work.

**Do:**
- **A stepper:** a checklist on the left ("3 of 6 done") and **one open step** on the right.
- Done steps collapse to "✓ Workspace: Lantern House · Edit".
- In the AI step:
  - lead with a recommendation ("Most people start with a pay-as-you-go account")
  - group the providers ("Pay as you go", "Use an app you're signed in to", "Free tier")
  - hide the internal accounts list until after the first account is added

**Done when:** a new user sees one step at a time, and the progress count matches Start here's.

### 3.12 [P1] Hand-in: good content, weak form

**Seen** (`screens/08-hand-in.png`):
- It opens **inline**, pushing Today down, rather than as a focused panel.
- The textarea spans about 1,370px, which is unreadable line length for pasted email.
- Four questions are asked every time: whose words, anything to do, how sensitive ("The usual"), which project.
- The disabled **Hand in** button is low-contrast lavender, with no hint why it's disabled.
- Focus isn't returned to the trigger on close.

**Do:**
- Use a **right-side drawer or centered sheet**, about 720px wide, so Today stays visible behind it.
- Keep "Whose words" as segmented buttons (two choices fit better as a toggle than as radios).
- Collapse sensitivity and project into an **"Options" row of chips** that show their current values ("Sensitivity: usual
  · Project: not sure"). The assistant can usually infer the project.
- Change the hint under the disabled button to "Paste or type something to hand in".
- After submitting, show a toast with **Open**, which jumps to the new row.

**Done when:** a paste and hand-in takes ≤3 interactions (open, paste, Enter), and the form never exceeds about 75
characters per line.

### 3.13 [P1] Phone: the right parts are there, in the wrong order

**Seen** (`screens/06`, `07`):
- On the 390px phone screen, the first screen is all chrome.
- The nav strip is clipped.
- Needs you comes after empty Agenda and To do sections.
- The full page is about 4,400px.
- "Looks good" buttons stretch full width, while "•••" stays small beside them.

**Why it matters:** 7.1 says that on a phone "review and approve or send back a draft, copy a message, answer a decision,
hand something in" are first class.

**Do:**
- Use a **bottom tab bar**: Today, Work, a large **+** for Hand in, Ask and More.
- On Today, **Needs you comes first**, and empty sections collapse to one line or are hidden.
- Primary actions are full-width only inside an open item.
- Consider a **swipe-free review mode**: one item per screen, with Looks good, Send back and Next. That is how people
  triage on a phone.

**Done when:** on a 390×844 screen the first Needs-you line is above the fold, and the user can get through a review
without scrolling sideways or opening a menu.

### 3.14 [P1] Dead ends and unexplained disabled controls

**Seen:**
- In Sources, **Read now** is disabled on three "Off" sources, with no way to turn them on from that row
  (`screens/10-sources.png`).
- Files shows a "New piece" button. Pieces belong to the content-calendar template, so the button means nothing on a
  Files page.
- Add-ons says "This copy of the app doesn't list a catalog" with no next step (`screens/14-add-ons.png`).
- Several empty states point to files: "watch.yaml" and "storage.backups.targets in the workspace config".

**Do:**
- **Every disabled control either explains itself** (a tooltip and a visible reason) **or is replaced by the action that
  enables it** ("Turn on").
- **Every empty state has a button** or says what the app is already doing about it. This is already a rule in 7.6;
  enforce it with a checklist in review.

### 3.15 [P2] There is no design system underneath

**Seen** (from `web/src/styles.css`, 476 lines, one global sheet):

| What | Count | Values or notes |
|---|---|---|
| Font sizes | 16 | 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 17, 18, 19, 20, 22, 26 and 0.92em |
| Font weights | 6 | 400–800 |
| Spacing values | 21 | 1–120px |
| Border radii | 11 | |
| Button families | about 9 | `.btn` variants, `.link-button`, `.newbar`, `.filters button`, `.tabs button`, `.tab`, `.toast button`, `.expander` and `.because button` |
| Segmented controls | 3 | near-identical: `.filters`, `.tabs` and `.tablist` |
| Empty-state styles | 3 | |
| Copies of the display-heading rule | 13 | |

Other gaps:
- Colors *are* tokenized: 32 hex values, all in `:root` with dark overrides, which is good.
- But the theme tokens are **never filled from `config/ui.yaml`** as 7.11 requires: nothing calls `setProperty`.
- There are no CSS modules.
- The display font stack (Iowan Old Style, then Palatino, then Georgia) renders differently on each OS and looks like a
  fallback at 20px column titles.

**Do:** add **Part 7.12 "Visual system"** to the design, then refactor to it.
- **Type scale:** 12 / 14 / 16 / 20 / 24 / 32, with weights 400 / 600 only.
  - Body at 15–16px.
  - Use the serif for **page titles only**, or drop it. Section and column titles use the UI sans at 600.
- **Spacing scale (4-pt):** 4, 8, 12, 16, 24, 32 and 48.
- **Radius scale:** 4 for inputs and pills, 8 for buttons, 12 for cards, plus pill.
- **Components:**
  - `Button`: primary, secondary, ghost and danger, each at sm and md
  - `SegmentedControl`
  - `Pill`, with the four tones from 3.9
  - `Row`: title, meta, state, primary and menu, in fixed positions
  - `EmptyState`: message plus action
  - `LoadFailed`: message plus Try again, replacing 12 copies
  - `SectionHeader`
- **Wire `config/ui.yaml` branding into the tokens**, and add the contrast warning 7.10 promises.
- **Optional:** a light/dark toggle (the `[data-theme]` hook already exists).

**Done when:** a lint (stylelint or a self-check) fails on any font size, spacing value or radius outside the scales.

### 3.16 [P2] Accessibility gaps

These are small; the base is strong.

- **Focus on view change:** changing view doesn't move focus to the new page heading. Screen reader users get no cue.
  Focus the `h1`, or announce "{View} page".
- **Hand-in focus:** hand-in doesn't return focus to its trigger on close.
- **Error toasts** use the same polite live region and the same 7-second timer as successes, with no **Try again**
  (`lib/act.ts:31-35`). Errors should stay until dismissed, carry a retry, and use `role="alert"`.
- **j/k gaps:** j/k skips Agenda and Came in rows (no `data-row`).
- **Loading states:** 29 places say "Loading…" and there is one skeleton. 7.6 asks for skeletons. Make `LoadingRows` a
  shared component.
- **Past agenda rows** differ only by a muted color.
- **Live updates:** `lib/live.ts` invalidates *every* query on every server event. That risks the "nothing moves under the
  PM" rule (7.0), and costs requests. Invalidate by event kind.

### 3.17 [P2] Microcopy

The writing is the strongest part of the build. To tighten it:

| Now | Problem | Suggested |
|---|---|---|
| "Add an account in your AI settings, then run the connection test: cockpit ai test" | Terminal command in the UI | "Add an AI account · [Set up]" |
| "Quill did 1 thing" | Says nothing | "Filed 1 note" / "Added 3 actions · 1 waits for you" |
| "Not started · Ready for Captured · [Move to Captured]" (Stages) | Machine-like; repeats itself | "New · [Start: Captured]", or a board view with columns |
| "How sensitive is this? — The usual" | Vague | "Who may see this? — Normal / Confidential / Private" |
| "Packs add a whole kind of work…" (Add-ons) | Internal term | "Add-ons add a kind of work, such as publishing or social posts" |
| "Untrusted: made by a program" / "outside content" | Two phrasings for one idea | Pick one: "From outside · not instructions" |
| "Needs you" vs "Waiting for you" vs "Your answer" vs "You" | Four variants | "Needs you" for the queue, "Waiting for you" for held items |
| "?" as a button | Ambiguous | "Help" or a keyboard icon with a label |
| "Workspace" (13 strings), "env:NAME", "tokens", "Client ID" | Admin jargon on the main path | Keep it behind Advanced or Details |

---

## 4. Screen-by-screen notes

- **Header** (all screens):
  - The 2-row header plus the DEMO strip is about 110px.
  - The status row (live, backup, spend, restart) should become **one status chip** that summarizes and opens a popover:
    "● Live · Backup needed".
  - Hand in and Ask are right. Ask in the prototype is a search-like field with the `/` hint, which teaches the shortcut
    better than a button.
- **Today:** see 3.1–3.4.
  - The **To do** column is the best-made part of the board: grouped by when, one button per row, readable meta.
  - **Came in** and **Agenda** empty states are good.
- **What changed (inside Needs you):**
  - The 3-way filter belongs on the full page, not on Today.
  - The "QUILL SAYS" block with a left rule is a nice pattern for the assistant's voice. Keep it, in sentence case.
- **Chasers:**
  - "Chasers" is a different word from the spec's "Follow-ups". Pick one and use it in the nav, headings and Today lines.
  - Person cards ("Ines Duarte · 2 to send · [Copy 2]") are excellent.
- **Stages:** two sections of one card each. This should be the spec's **board view**: columns per stage, with cards that
  can be dragged or moved from the keyboard.
- **People & projects:**
  - Edit + ••• on every row: put Edit in the menu, or make the row itself open the record page.
  - "ACTIVE" on every person is noise (3.9).
  - "Synced folder" doesn't belong here.
  - Projects deserve their own page: the Portfolio health table of 7.1.
- **Files / Pieces:** fine empty states, but "New piece" on Files is misplaced. Pieces should sit under Work (3.5).
- **Sources:** good descriptions ("A folder · every 30 minutes · 1 item"). Fix the disabled buttons (3.14). Auto-closed
  belongs here, which is right.
- **Settings and setup guide:** see 3.10 and 3.11.
- **Add-ons:** the Available/Installed tabs use a fourth segmented style (an underline). Use the shared component.
- **Ask dialog:** clean. "Recent questions" is a good touch. Make it wider for answers that contain lists.
- **Keyboard help:** good. List the keys in groups (Move, Act, Open).
- **Dark mode:** solid. The amber notice is heavy in dark; tone it down to the `--warn-soft` border only.

---

## 5. Gaps between the design and the build

| Spec | Says | Build | Action |
|---|---|---|---|
| 7.0 / 7.7 | Today is one ranked queue; nothing informational | 4-column dashboard (owner decision 2026-10-11) | Reconcile in the doc: queue-first dashboard (3.1) |
| 7.1 | Tabs: Today / Work / Portfolio / Admin | 8 flat tabs plus plugins | Restructure (3.5) |
| 7.1 | Header collapses to a menu on narrow screens | Clipped sideways strip | Bottom bar (3.13) |
| 7.1 | Date, Today count, Refresh, Jobs, Log, quick links | Missing | Fold into the status chip and gear menu; drop Refresh (SSE makes it redundant) |
| 7.4 | Waiting to go out, with diffs and Approve | Missing | Reserve the place now (3.7) |
| 7.5 | Copy shows the editable message first | Copy from a collapsed card is blind | 3.8 |
| 7.6 | Skeleton rows, not spinners | 1 skeleton, 29 "Loading…" | Shared skeleton |
| 7.6 | Never an instruction the screen can't carry out | 9 CLI or config-path strings | Replace with buttons |
| 7.9 | Settings grouped, basic first, advanced behind a toggle | One long page; per-section Save | 3.10 |
| 7.10 | Brand colors from config, with a contrast warning | Tokens not wired to config | 3.15 |
| 7.11 | CSS modules, React Router, events invalidate affected queries | Global CSS, hash routing, invalidate-all | Fine for now except invalidate-all (3.16) |

---

## 6. Changes to make to the design documents

1. **Rewrite 7.7** as "Today: a ranked queue with a context rail". Fold in the 2026-10-11 decision, define the ranking
   order, and state that held items and decisions are always top-level lines. **Update the prototype** to match.
2. **Add 7.12 "Visual system":** the scales and components in 3.15, the four pill tones, and the "two levels of borders"
   and "sentence case" rules.
3. **Add a "Row anatomy" section:**
   - a title rule (3.2)
   - meta line
   - state pill (exceptions only)
   - one primary action at the right
   - a "•••" menu at the far right
   - expansion in place
   - at most 2 levels of nesting
4. **Add a navigation budget** to 7.1 and 3.x (plugins): at most 5 primary destinations, with plugin panels under Work.
5. **Add a mobile section** with the bottom bar, Needs-you-first order and the one-item review mode.
6. **Shrink the 7.1 header list** to: brand, nav, Ask field, Hand in, status chip, and a help/gear menu.
7. **Add a Settings IA** to 7.9: a section rail, autosave with undo, "Changed · Reset" instead of always-on defaults,
   pickers for machine values, and advanced fields behind Details.
8. **Pick one word each** for: Follow-ups/Chasers, Needs you/Waiting for you, and outside content/untrusted.

---

## 7. Suggested order of work

1. **Quick wins (about 1–2 days):**
   - titles (3.2)
   - remove the CLI and config strings (3.4, 3.17)
   - merge the stand-in notice into a one-line Start here
   - sentence-case labels
   - hide "Active" pills
   - one shell width (3.6)
   - Copy shows the message first (3.8)
   - error toasts stay, with a retry
2. **Today redesign (about 1 week):** the queue-first dashboard (3.1, 3.3), the prototype update, and phone ordering
   (3.13).
3. **Visual system (about 1 week):** tokens and scales, the shared components, the style lint, and wiring branding to the
   tokens (3.15, 3.9).
4. **Navigation and shell (3–4 days):** five destinations plus the gear menu, links, the bottom bar, and the status chip
   (3.5).
5. **Settings and setup (about 1 week):** the section rail with autosave, and the setup stepper (3.10, 3.11).
6. **Then** Waiting to go out and the diff review (3.7), on the new system.

## 8. Acceptance checklist for the next pass

- [ ] At 1280×720 the first Needs-you line is within 200px of the top, and the top-level lines don't need inner
  scrolling.
- [ ] No row title starts with a greeting, "From:", or a cut-off sentence.
- [ ] Every decision or held item is one click from Today.
- [ ] At most two levels of bordered containers on any screen.
- [ ] The header is identical across views and never wraps at 1024px or wider; at most 5 primary nav items.
- [ ] No `cockpit …`, `.yaml`, config key path or `env:` text on the default path.
- [ ] Copy never fills the clipboard with text that isn't on screen.
- [ ] Type, spacing and radius values all come from the scales (enforced by a lint).
- [ ] Error toasts persist and offer a retry; focus moves to the heading on view change.
- [ ] On a phone, Needs you comes first and a review can be done one-handed.
- [ ] Axe checks still pass in light and dark at all four viewport sizes.

## Screens

| File | What it shows |
|---|---|
| `screens/01-today-first-run.png` | First screen: banners, Start here, four columns, decision cut off |
| `screens/02-today-populated.png` | After four hand-ins: "Hi team," titles, Needs you squeezed |
| `screens/03-evidence-nested.png` | Evidence and source highlight (keep), and "Who is Maya?" five levels deep |
| `screens/04-chasers-after-copy.png` | Copy from a collapsed card, then Mark sent |
| `screens/05-today-tablet.png` | 900px: Needs you is a box about 200px tall |
| `screens/06-phone-first-screen.png` | Phone: first screen is all chrome; nav clipped |
| `screens/07-phone-full-page.png` | Phone full page (about 4,400px) |
| `screens/08-hand-in.png` | Hand-in form inline at full width |
| `screens/09-stages-header-shift.png` | Non-Today view: centered layout, nav wraps to two rows |
| `screens/10-sources.png` | Disabled "Read now" with no way to turn the source on |
| `screens/11-people-projects.png` | "ACTIVE" pills, four primaries, misplaced Synced folder |
| `screens/12-settings-full-page.png` | Settings as one long page with six Save buttons |
| `screens/13-setup-guide.png` | Setup guide: all steps expanded, done steps as large as undone ones |
| `screens/14-add-ons.png` | Add-ons dead end; fourth segmented style |
| `screens/15-dark.png` | Dark theme |
| `screens/16-prototype-today.png` | The reference prototype: the ranked verb queue to aim for |
