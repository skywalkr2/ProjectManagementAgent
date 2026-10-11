# PM Cockpit: UI/UX review

**For:** the design agent working on `docs/design/` (Part 7 and the prototype) and the screens in `web/src/`.

**What's in this folder:**

| File | What it is |
|---|---|
| `README.md` (this file) | The review: verdict, what to keep, every finding with a fix and a test, screen-by-screen notes, design-doc changes, order of work, and the **master checklist** used to re-review the work |
| `visual-spec.md` | What it should look like: colour (measured), type, **layout that uses the whole screen**, components, icons, motion, states, data display, enforcement |
| `tokens.css` | The proposed design tokens: light and dark, contrast-checked, ready to drop in |
| `mockup-today.html` | The proposed Today, built with those tokens (open it in a browser and resize it) |
| `mockup/` | Renders of the mockup at 390, 900, 1280, 1440 and 1920, light and dark |
| `screens/` | 33 screenshots of the current build (fictional demo data) |

**What was reviewed:**
- Branch `claude/tender-tesla-16a8ob` at commit `5239897`, the most complete build.
- Against these documents:
  - the original `DESIGN.md`
  - the Design 1.0 split in `docs/design/` (Parts 1, 7 and 8)
  - `docs/design/prototypes/today.html`
  - `docs/decisions.md`
  - `docs/project/ux-notes.md`

**Method:**
- I ran the app on the fictional imprint workspace with the stand-in AI (`tests/e2e_server.py`) and handed in the
  fixture cases so the screens had real content.
- I captured every reachable view and state at these sizes, in light and dark:

  | Size | Device |
  |---|---|
  | 390×844 | Phone |
  | 900×1000 | Tablet |
  | 1280×720 | Small laptop |
  | 1440×900 | Laptop |
  | 1920×1080 | Desktop |
  | 2560×1440 | Wide desktop |

- I audited `web/src` line by line against 7.0, 7.6, 7.10 and 7.11.
- I measured the colour tokens for WCAG contrast.
- I compared everything with the Today prototype.

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

1. **The screen is badly used.**
   - Every view except Today is an 880px centered column. That leaves **39% of a 1440 screen, 54% of a 1920 screen and
     66% of a 2560 screen empty**.
   - Today does fill the width, but gives the work a quarter of it, in a small scrolling box. Empty columns take half.
   - Vertically, about 230px of banners and chrome sit above the content.
2. **The work is hard to find.** "Needs you" shows 2½ of 13 items at 1440×900. At 900px wide it is a box about 200px
   tall.
3. **Items have no names.** Rows are titled with the first line of whatever was pasted ("Hi team,", "From: Jun Park").
   Record pages are titled with ids ("PER-2") and show values like "ORG-1".
4. **Decisions are buried.** "Who is Maya?" sits five containers deep.
5. **There is no visual system.** There are 16 font sizes, 21 spacing values, 11 corner radii, about 9 button styles,
   3 segmented controls, cards nested in cards, and ALL-CAPS sentences. Control borders fail WCAG's contrast minimum
   for form fields.
6. **The navigation sprawls.** There are 8 flat tabs plus one per plugin. They wrap onto two rows, and the header jumps
   between views.

The reference prototype (`screens/16-prototype-today.png`) is the clearest statement of what the owner wanted: a short
ranked list of verbs, each with one button.

**The target:** that queue, in a full-width shell, with a context rail and a detail pane as the screen grows (§3.1, §3.18
and `visual-spec.md` §4).

See `mockup/mock-1440.png` and `mockup/mock-1920.png` for the picture.

### Scorecard

1 is poor and 5 is excellent.

| Area | Score | One line |
|---|---|---|
| Concept and trust patterns | 5 | Evidence, whose-words, undo and approval gates are best-in-class ideas |
| Use of screen space | 1 | Fixed 880px column on most views; Today wastes half its width and nests scrolls |
| Information architecture | 2 | Flat 8+N tabs; Today hides the queue; key spec surfaces missing |
| Today (home) | 2 | Work squeezed into a quarter-width scroll box; decisions buried |
| Item design (rows, records) | 2 | No meaningful titles; ids on screen; 4–5 levels of nesting; pill overload |
| Visual design and system | 2 | Sound palette and tokens, but no scale; serif and sans clash; inconsistent components |
| Forms (hand-in, record forms, settings, setup) | 2 | Inline, full-width, ungrouped; settings and setup are long config dumps |
| Mobile | 2 | One column works mechanically; priorities inverted; first screen is all chrome |
| Accessibility | 3.5 | Strong base (React Aria, live regions, axe); control-border contrast fails; focus gaps |
| Writing (microcopy) | 4 | Calm and plain; CLI commands, config paths, ids and a few vague phrases leak through |
| Dark mode | 4 | Works via tokens; no in-app toggle |

---

## 2. What to keep

The design agent must not lose these in a redesign.

1. **Evidence lines** (`screens/03-evidence-nested.png`): a quoted "Because" plus **Show source** with a highlighted
   passage, and an "outside content" tag. This is the product's trust engine. Make it *more* visible: on wide screens it
   gets a pane of its own (`mockup/mock-1920.png`).
2. **Hand-in's "Whose words are these?"** (`screens/08-hand-in.png`). It teaches the security model in plain words.
3. **Undo toasts** with `u` to undo. There is no `window.confirm` anywhere. Toasts pause on hover and focus, and stay
   when reduced motion is on.
4. **The keyboard loop** (j/k/Enter/a/s/c/e/u/n, / and ?). It is guarded while typing, configurable, has a help dialog,
   and gives a clear focus ring on rows (`screens/27-…`).
5. **One primary action plus a "•••" menu.** `RowMenu` (React Aria) is used in 14 components, and disabled menu items
   say why.
6. **The wording sheet.** It has 1,152 keys and about 99% of strings come from it. Internal terms (changeset, op, tier,
   ledger) never appear on screen.
7. **Empty states that offer the next step:** "Connect a calendar" and "Connect a mailbox".
8. **The live indicator, backup nag and Back up now.** This is the right content, though it is in the wrong form
   (§3.4).
9. **Demo labelling,** the feedback dialog that writes a mail draft the person sends (`screens/25-feedback.png`), and
   "Ask" with recent questions.
10. **Accessibility work already done:**
    - React Aria dialogs and menus
    - `aria-live` toasts
    - a skip link
    - a global `:focus-visible` ring
    - no clickable `div`s
    - labelled inputs
    - axe checks in Playwright
11. **Colour hues:** cool grey with an indigo accent, with text contrast of 6–16:1. Keep the hues; fix the roles
    (`visual-spec.md` §2).

---

## 3. Findings

Each finding gives what I saw, why it matters, what to do, and how to know it's done.

- **P0** threatens the core promise.
- **P1** is a structural UX debt.
- **P2** is polish and consistency.

The IDs (3.x) are referenced by the master checklist in §8.

### 3.1 [P0] Today does not answer "what do I do next?"

**Seen** (`screens/02-today-populated.png`, `05-today-tablet.png`, `17-today-start-here-hidden.png`):
- Today is four equal-ish columns: Agenda, To do, Needs you and Came in.
- "Needs you" holds all the review and decision work in about 25% of the width, inside an inner scroll box. At
  1440×900, 2½ of 13 items show. At 900px it is about 200px tall.
- Agenda and Came in are empty and take about 50%.
- Needs you embeds two whole panels, each with its own filter: What changed (3-way) and Chasers (2-way). That puts
  filters inside a column inside a page.

**Why it matters:**
- Part 1 promises "one screen that says what to do today".
- 7.0 and 7.7 call for "a queue, not a dashboard … one ranked list … nothing informational sits on Today."
- The owner later decided (`docs/decisions.md`, 2026-10-11) on a dashboard that uses the laptop width, so nothing hides
  below the fold.
- The build meets the letter of that decision and defeats its purpose: the important things are *more* hidden.

**Do:** build a **queue-first dashboard** (`mockup/`).
- **Needs you is the main pane.** It is the widest, on the left. It is a ranked list of verb lines grouped Decide /
  Review / Send and follow up:
  - "Answer 1 decision · [Answer]"
  - "Pick who 'Maya' is · [Pick]"
  - "Look over 3 actions Quill added · [All looks good]"
  - "Send 2 questions to Maya Okafor · [Review & copy]"
- **No embedded panels or filters inside it.** The full What changed and Follow-ups views live under Work.
- **The selected line's detail:**
  - ≥1680px: it shows in an **inspector pane**: the items, evidence, highlighted source, message preview or decision
    form.
  - Below that: it expands in place.
- **A context rail** holds Agenda, Your to-dos and Came in. Each panel is sized to its content. An empty panel is one
  line ("Came in · Not connected · [Connect]").
- **One scroll region,** the page. Drop the fixed-height board with per-column scroll.
- **Ranking rules** go in the spec: decisions and held items first, then at-risk and overdue, then reviews, then sends
  and follow-ups, then later.

**Done when:**
- At 1280×720 the first queue line is within 140px of the top.
- Every top-level line of a typical day (6–10) is visible with no inner scrolling.
- Empty rail panels take one line.
- `j` starts on the first queue line (§3.22).

**Design doc:** 7.7 and the 2026-10-11 decision contradict each other. Replace both with one rule ("Today is a ranked
queue with a detail pane and a context rail"), and **replace `prototypes/today.html`** with this layout. Use
`mockup-today.html` as the starting point.

### 3.2 [P0] Items have no names

**Seen** (`screens/02-today-populated.png`): review rows are titled "Hi team,", "From: Jun Park", "Events: Maya will
send the guest list for the…" and "Production check-in, Oct 8". The cause is `WhatChanged.tsx:167`:
`item.source_title || firstLine(item.note)`. Under each title, "Quill did 1 thing" does not say what it did.

**Why it matters:** a title is how people scan, remember and refer to things. With 10+ rows the list is unreadable, and
screen-reader and j/k users hear "Hi team," over and over.

**Do:** define a **title rule** in the spec and implement it in the engine.
- Titles take the form "{Kind} from {person} · {topic}", for example "Email from Theo Brandt · cover proof" or "Your note
  · launch reading".
- Build them from structured fields first (headers, sender, subject).
- Then use the changeset `summary`: ask the model for a 3–6 word topic.
- Only then fall back to the first line, with greetings stripped.
- Replace "Quill did 1 thing" with the outcome: "Filed 1 note", or "Added 3 actions · 1 waits for you".

**Done when:** no row anywhere starts with a greeting, "From:", or a truncated sentence.

### 3.3 [P0] Decisions and blockers are buried four levels deep

**Seen:**
- To answer "Who is 'Maya'?" the user goes Needs you → What changed → the review card → expand → the "Added an action ·
  Waiting for you" child card → the picker (`screens/03-evidence-nested.png`).
- The decision "Cover finish for the hardcover" is a textarea inside "You" inside Chasers inside Needs you, cut off by
  the column's scroll (`screens/01-today-first-run.png`).

**Why it matters:** "decisions are questions addressed to the PM". Held items block the assistant, so they are the
highest-value clicks in the product.

**Do:**
- Every held item becomes its own top-level Today line with its own primary action: a decision, "who is this?", "pick
  an owner", or a waiting-for-go.
- Inside the review it becomes a small "Waiting for you · on Today" note.
- **Cap nesting at two levels:** a line, and its items.

**Done when:** every decision or held item is one click from Today, and no screen has more than two levels of bordered
containers.

### 3.4 [P0] Banners and system chrome sit above the work

**Seen:**
- At 1440×900, about 380px goes before any work (`screens/01-today-first-run.png`):
  - the DEMO strip (30px)
  - a two-row header (80px)
  - an amber "assistant is a stand-in" notice (95px) that ends with a terminal command, "cockpit ai test"
  - a "Start here" card (150px)
  - and a footer row at the bottom
- Hiding Start here still leaves about 230px (`screens/17-…`).
- On a phone the **whole first screen** is chrome (`screens/06-phone-first-screen.png`).

**Why it matters:**
- Banner blindness: users learn to ignore banners within a day.
- The notice and Start here repeat each other.
- A terminal command breaks 7.6: "never answer with an instruction the screen can't carry out."

**Do:** follow `visual-spec.md` §4.2.
- A **one-row 56px header.** DEMO becomes a chip. The status row becomes one status chip with a popover.
- **No footer:** the version, feedback and the shortcuts hint move to the Help menu.
- The stand-in notice and Start here merge into **one setup line**: "Setup 5 of 6 · Next: add an AI account · [Continue
  setup]".
- Replace every CLI or config instruction with a button that does it.

**Done when:**
- Chrome above content is 56px or less, plus the setup line while setup is unfinished.
- No user-facing string contains `cockpit …`, a `.yaml` name, a config key path or `env:`. There are 9+ today; see
  §3.17.

### 3.5 [P1] The navigation is flat, long, and grows with every plugin

**Seen:**
- The nav is Today, Stages, Files, Sources, Pieces, People & projects, Settings and Add-ons: 7 fixed items plus one per
  plugin panel (`Header.tsx:63-93`), all in one segmented control.
- It wraps onto **two rows** on non-Today views at 1440 and on 1920 (`screens/09-…`, `30-…`).
- On a phone it is a sideways strip clipped mid-word.
- The setup guide is not in it.
- Nav items are `<button>`s, not links: they can't be opened in a new tab, and there are no real URLs.

**Why it matters:**
- The spec's model (Today / Work / Portfolio / Admin) grouped by *job*.
- A segmented control is the wrong pattern for more than about 5 options.
- An unbounded plugin list will break the header.

**Do:** use a **left sidebar** (`visual-spec.md` §4.2, `mockup/`):

| Section | Contains |
|---|---|
| Today | With its count |
| **Work** | What changed, Follow-ups, Waiting to go out, Stages, and plugin work panels nested here |
| **Records** | Projects, People, Files, and plugin record panels nested here |
| Bottom group | Sources, Add-ons, Settings |

- The sidebar collapses to a 64px icon rail at 1024–1279px, and on request.
- On phone, it becomes a bottom bar: Today · Work · **+** · Ask · More.
- Use real links (`<a href="#work/stages">`).
- Put a **nav budget** in the spec: plugins add entries only *under* Work or Records.

**Done when:**
- The header never wraps.
- Adding three plugins changes only the sidebar sub-lists.
- Every view has a link that can be bookmarked and opened in a new tab.

### 3.6 [P1] The layout jumps between views

**Seen:**
- Today is full-bleed. Other views are an 880px centered column.
- So the header itself moves: the brand jumps from x≈16 to x≈280 at 1440, and to x≈520 at 1920. The nav wraps. The
  actions shift.
- Compare `02-…` with `09-…`.

**Do:**
- One shell: header and sidebar fixed in place.
- Every view fills the content area with its own pane pattern (`visual-spec.md` §4.4).

**Done when:** switching any two views changes nothing outside the content area.

### 3.7 [P1] The outward approval surface is missing

**Seen:**
- There is no "Waiting to go out" view (7.4): no drafts, no word-level diff, no Approve.
- There is no Portfolio health view (7.1).
- The header has no Log, Jobs, Today count or date.
- The only outward content so far is copied messages.

**Why it matters:** "The AI drafts. The human approves everything that goes out" is the headline promise, and
approving a diff is the product's most distinctive screen.

**Do:**
- Reserve Work → Waiting to go out now. Give it an empty state ("Nothing waiting to go out. Drafts appear here for your
  approval").
- Design it as list + full-width diff (`visual-spec.md` §4.4, §5.11).
- Design Projects as the portfolio table (§4.4).
- Include both in the next prototype pass, even if they are built later.

### 3.8 [P1] Copy can put text on the clipboard that the user has not seen

**Seen:**
- On a collapsed person card, **Copy 2** writes the message to the clipboard straight away
  (`FollowUps.tsx:265`, `screens/04-…`).
- The card then offers **Mark sent**, which is right.

**Why it matters:** 7.5 says "Copy shows the message it will copy, editable in place." Pasting unseen text to a
colleague is the outward risk the product exists to prevent.

**Do:**
- The primary on a collapsed card is **Review & copy**, which opens the message (inline, or in the inspector) with
  **Copy** under it.
- `c` on a collapsed row does the same.

**Done when:** text never reaches the clipboard unless that message is on screen at that moment.

### 3.9 [P1] Visual hierarchy: too many boxes, pills and capitals

**Seen** (`screens/02`, `03`, `11`):
- **Five levels of bordered containers.**
- **ALL-CAPS sentences:** "FILED A NOTE UNDER THE SALT ORCHARD LAUNCH", "QUILL SAYS".
- **Pills on everything:**
  - "ACTIVE" on every person
  - "WINTER LIST" (a group) styled like a status
  - "NOT DONE YET", "NOT STARTED", "REVIEW" and "WAITING FOR YOU" all look alike
- **Four filled primaries** on People & projects.
- On Organizations rows, "•••" sits next to the name.

**Why it matters:**
- When everything is boxed, nothing stands out.
- Capitals slow reading.
- Ubiquitous pills train people to ignore the one that matters.

**Do:** follow `visual-spec.md` §1, §2.3, §3 and §5.2–5.5.
- Dividers instead of cards inside panes; panels only at the top level.
- Sentence case.
- Pills only for exceptions, with four tones.
- One primary per region.
- Fixed row anatomy: pill column, title, meta, primary, then menu at the right edge.

**Done when:**
- At most two levels of borders anywhere.
- No uppercase label over one word.
- Pills on fewer than a third of the rows in any list.

### 3.10 [P1] Settings is a config file with a form around it

**Seen:**
- **Basic:** one 5,446px page with six **Save** buttons (`screens/12-…`).
- Every field shows "Default: x" plus **Back to default**, even when the value equals the default.
- **Raw values:** "America/New_York", "en-US", "0.25".
- **AI accounts listed by internal id** ("stub", "low-cost", "router", "coding-agent"), with environment variable names.
- **More settings:** **131 fields** on one page. Template syntax shows in labels: 'How an action owner is written, e.g.
  "{team} ({full_name})"' (`screens/26-…`).
- Value lists take about 40% of the page.
- "Synced folder" also appears on People & projects.
- At 1920 the form column uses 46% of the width (`screens/31-…`).

**Do:** follow `visual-spec.md` §4.4 (Settings).
- **Section nav | form | help pane.**
- Fields in two columns where related.
- **Autosave** with an undo toast, or one sticky save bar. Never six Save buttons.
- "Changed · Reset" only when a value differs from its default. Defaults and descriptions go in the help pane.
- Pickers for time zone, language, money and dates.
- **AI accounts** with display names and a status chip (Ready / Key missing / Untested). Environment details go behind
  "Details".
- **Advanced settings** grouped by topic, with search, never one list of 131. Template fields get a **live preview**
  ("Production (Maya Okafor)") instead of showing their syntax.
- Lists get their own section. Synced folder lives in one place.

**Done when:**
- Any setting is two clicks away, with no unrelated scrolling.
- No raw environment variable, IANA id, locale tag or `{placeholder}` shows by default.

### 3.11 [P1] The setup guide is a long page, not a guide

**Seen** (`screens/13-…`):
- Seven steps, all expanded, on about 3,500px.
- Finished steps keep their full forms.
- 12 provider cards plus an internal accounts list.

**Do:**
- **Steps checklist | the open step** (`visual-spec.md` §4.4).
- Done steps collapse to "✓ Workspace: Lantern House · Edit".
- In the AI step:
  - lead with a recommendation
  - group the providers (pay as you go / an app you're signed in to / free tier)
  - hide internal accounts until one is added
- The progress count matches the setup line on Today.

### 3.12 [P1] Hand-in: good content, weak form

**Seen** (`screens/08-…`):
- It opens inline and pushes Today down.
- The textarea is about 1,370px wide.
- Four questions are asked every time. Sensitivity is "The usual".
- The disabled **Hand in** button is low-contrast lavender, with no reason given.
- Focus isn't returned to the trigger on close.

**Do:**
- **Desktop:** a right-hand drawer (`--detail-w`, about 600px) with the textarea at `--measure`.
- **Phone:** a full-screen sheet from **+**.
- "Whose words" as a segmented control.
- Sensitivity and project as chips showing their current values in an Options row.
- A hint under the disabled button: "Paste or type something to hand in".
- After submit, a toast with **Open** that selects the new line.

**Done when:** a hand-in takes at most 3 interactions, with lines of at most 72 characters.

### 3.13 [P1] Phone: the right parts in the wrong order

**Seen** (`screens/06`, `07`):
- The first screen is chrome.
- The nav strip is clipped.
- Needs you comes after empty Agenda and To do.
- The page is 4,400px.
- Full-width "Looks good" buttons sit next to a tiny "•••".

**Do:**
- A bottom bar.
- Needs you first. Empty rail panels collapse or hide.
- Primary actions full-width only inside an open item.
- A one-item-at-a-time **review mode**: Looks good, Send back, Next (`mockup/mock-phone.png`).

**Done when:** at 390×844 the first queue line is above the fold, and a review needs no sideways scrolling or menu.

### 3.14 [P1] Dead ends and unexplained disabled controls

**Seen:**
- In Sources, **Read now** is disabled on Off sources, with no **Turn on** (`screens/10-…`).
- Files shows "New piece".
- Add-ons says "This copy of the app doesn't list a catalog" with no next step (`screens/14-…`).
- Empty states point to "watch.yaml" and "storage.backups.targets".
- Disabled buttons fade to 50% opacity with no reason given (Hand in, Save, Use this person, Answer).

**Do:**
- Every disabled control **says why**, or is replaced by the action that enables it.
- Every empty state has one button, or says what the app is doing about it (7.6).
- Disabled controls use the style in `visual-spec.md` §5.1, not opacity.

### 3.15 [P2] There is no design system underneath

**Seen** (`web/src/styles.css`, 476 lines):
- 16 font sizes and 6 weights.
- 21 spacing values and 11 radii.
- About 9 button families, 3 segmented controls and 3 empty-state styles.
- 13 copies of the display-heading rule.
- Tokens are not filled from `config/ui.yaml`.
- No CSS modules.
- A serif display stack that renders differently on each OS.
- **Contrast failures:**
  - control borders at **1.35:1**, which fails WCAG 1.4.11 at 3:1
  - disabled primary text at **2.5:1**
  - a focus ring the same colour as primary buttons

**Do:** adopt `visual-spec.md` and `tokens.css` in full:
- the palette and roles
- the type and spacing scales
- the shared components
- branding from config, with a contrast guard
- stylelint enforcement
- a style-guide view with screenshot tests

### 3.16 [P2] Accessibility gaps

- **Control boundaries:** input and select borders at 1.35:1 fail 1.4.11. Use `--border-strong`.
- **Focus on view change:** changing view doesn't move focus to the new heading. Focus the `h1`, or announce
  "{View} page".
- **Hand-in focus:** hand-in doesn't return focus to its trigger.
- **Errors:** error toasts share the polite region and the 7-second timer, and have no retry (`lib/act.ts:31-35`).
  Errors should stay inline with **Try again**, and background errors should use `role="alert"` and stay.
- **j/k gaps:** j/k skips Agenda and Came in rows, and starts in To do (§3.22).
- **Loading:** 29 places say "Loading…" and there is one skeleton. Use shared skeleton rows with `aria-busy`.
- **Colour alone:** past agenda rows differ only by colour. Add a "Done" or "Past" word or icon.
- **Live updates:** `lib/live.ts` invalidates *every* query on every event, which risks "nothing moves under the PM".
  Invalidate by event kind, and hold new items behind "N new · Show".

### 3.17 [P2] Microcopy

| Now | Problem | Suggested |
|---|---|---|
| "Add an account in your AI settings, then run the connection test: cockpit ai test" | Terminal command in the UI | "Add an AI account · [Continue setup]" |
| "Quill did 1 thing" | Says nothing | "Filed 1 note" / "Added 3 actions · 1 waits for you" |
| "Review the next project note is ready for Ready for review · [Move to Ready for review]" (`screens/28-…`) | Repeats itself; generated from labels | "Ready to move: Review the next project note → Ready for review · [Move]" |
| "Not started · Ready for Captured · [Move to Captured]" (Stages) | Machine-like | A board (§4.4), or "New · [Start]" |
| "Type a title for the new piece." as a dialog heading; "What it will change: It won't change anything."; button "Apply" (`screens/24-…`) | An instruction as a title; a read-back that contradicts creating something; a generic verb | Title "New piece"; drop the read-back for a plain create; button "Create piece" |
| "What should Quill change? (required; everything it did here is undone first)" | Hidden consequence in a parenthesis; 7.3 offers "Undo it, then send" as an *option* | Label "What should Quill do differently?" and a checkbox "Undo what it did first" (on by default) |
| "How sensitive is this? — The usual" | Vague | "Who may see this? — Normal / Confidential / Private" |
| "Packs add a whole kind of work…" | Internal term | "Add-ons add a kind of work, such as publishing or social posts" |
| "Untrusted: made by a program" / "outside content" | Two phrasings for one idea | "From outside · not instructions" |
| "Chasers" vs the spec's "Follow-ups" | Two names | "Follow-ups" everywhere |
| "Needs you" / "Waiting for you" / "Your answer" / "You" | Four variants | "Needs you" for the queue; "Waiting for you" for held items |
| "Workspace" (13 strings), "env:NAME", "tokens", "Client ID" | Admin jargon on the main path | Behind Advanced or Details |
| "?" as a button | Ambiguous | A Help icon with a label |

### 3.18 [P0] The screen is badly used: the app should fill the window at every size

The owner's standing request is that the design use the screen to its full extent.

**Seen:**
- **Horizontal.** Every non-Today view (People & projects, Settings, Sources, Stages, Files, Pieces, Add-ons, record
  pages, setup) is centered at 880px:

  | Window width | Left empty |
  |---|---|
  | 1440 | 39% |
  | 1920 | 54% (`screens/30-1920-people-54pct-empty.png`, `31-1920-settings.png`) |
  | 2560 | 66% (`screens/33-2560-people.png`) |

- **Today.** At 2560, Today fills the width but spends it on empty columns: Agenda is 500px wide with one button, and
  "Mark done" sits 350px from its text (`screens/32-2560-today.png`).
- **Vertical.** About 230px of chrome: the DEMO strip, a 2-row header, the notice and the footer.
- **Wrong containers.** Lists of people and projects use tall cards (about 72px each, 7 people fill a laptop screen)
  where a table would show 20 rows with more information.
- **Forms don't fit their content.** Single-line fields stretch to 850px (`screens/22-…`). The project form is
  13 full-width fields in a column, expanded inline inside the list (`screens/23-…`).

**Why it matters:**
- The PM works on a laptop or a big monitor all day. Empty margins mean more scrolling, fewer things compared at once,
  and more clicks to reach detail.
- Professional tools (mail clients, trackers, CRMs) add panes as the window grows, so a wide screen shows *more
  context*, not more margin.

**Do:** follow `visual-spec.md` §4. In short:
- **A full-width shell.** Left sidebar, one-row header, no banners, no footer.
- **Panes by width:**
  - phone: one pane
  - tablet: one pane plus a drawer
  - laptop: two panes
  - desktop: two panes, with two-column forms
  - wide: three panes
  - ultra: three panes plus an extra context pane
- **Patterns per view:**
  - Today: queue | inspector | rail
  - Work lists: list | detail
  - Stages: board
  - Projects, People, Files and Sources: table | detail
  - Settings: nav | form | help
  - Record: activity | details
  - Setup: steps | step
- **Limit line length** for prose (72ch) inside panes, not the layout.
- **Tables for records,** with sortable, resizable columns that hide by priority as the width shrinks. A density
  setting (comfortable 56px rows, compact 44px).
- **Forms in drawers,** with fields sized to their content and two columns when wide.

**Done when** (add these to the end-to-end suite):
- At 1440×900 and 1920×1080, every view's content covers at least 90% of the width beside the sidebar, and no view has a
  horizontal margin over 48px outside its panes.
- People shows at least 15 people at 1440×900 without scrolling.
- At 1920, Today shows the inspector, and at least 8 queue lines without scrolling.
- Chrome above content is 56px or less.

### 3.19 [P1] Record pages show ids, raw values and help text instead of the record

**Seen:**
- **Person page** (`screens/21-record-person-ids.png`):
  - the heading is "**PER-2**"
  - fields are in alphabetical order: Aliases first, Full name second
  - values are "ORG-1", "TEAM-1" and "active"
  - a schema description sits under every value ("The id of the organization they work for; its name lives on that
    record")
- **Project page** (`screens/20-…`): Owner "PER-1", Target "2026-12-01".
- **Neither page** shows the record's actions, questions, notes, decisions or history.

**Why it matters:**
- This breaks the core rule "no internal ids in anything the PM reads".
- A record page is where a PM goes to answer "what's going on with X?", and this page can't answer it.

**Do:**
- The title is the record's name.
- Details in a meaningful order (name, role, organization, how to reach), with resolved names and formatted dates.
- No help text on view; it belongs in the edit form.
- Two columns: **activity** (timeline, open actions and questions, notes, decisions) and **details**.
- Edit opens the drawer form.

**Done when:** no id or raw enum value appears on any record page, and a person's page lists everything open with them.

### 3.20 [P1] Forms: inline, full width, ungrouped

**Seen:**
- **Add a person** opens inline above the list, with 850px-wide fields for a name (`screens/22-…`).
- **Edit project** expands *inside the list row*, pushing Organizations and Projects down. It is 13 full-width fields:
  Name, Target date, Status, Phase, Priority, Group, Owner, "Inside", Language, Budget, Summary (`screens/23-…`).
- Labels carry bold parenthetical hints: "Role (for example: Editor, Printer contact)".
- "Inside: None" is unclear.
- "Language (inherited; type one to set its own)" with an "en-US" placeholder.
- The primary is disabled until valid, with no reason.

**Do:** follow `visual-spec.md` §4.4 (forms) and §5.6.
- A drawer form.
- Fields sized to their content, two columns when wide, and grouped: Basics / Schedule / People / Advanced.
- Hints below the field.
- Pickers for dates, people and language.
- Plain labels ("Part of" instead of "Inside").
- Inline validation messages instead of a silently disabled button.

### 3.21 [P1] Send back: the submit button is out of sight, and undo is forced

**Seen** (`screens/18-send-back.png`):
- "Send back with a note" opens a textarea at the bottom of the narrow Needs you column. Its submit button lands below
  the column's scroll edge.
- The label says everything is undone first ("required; everything it did here is undone first"). The spec (7.3) offers
  "Undo it, then send" as an *option*.

**Do:**
- Send back opens in the inspector, or a small anchored dialog, with the note, a checkbox "Undo what Quill did first"
  (on by default), and **Send back** visible without scrolling.
- `s` opens it with the note focused.

### 3.22 [P2] The keyboard loop starts in the wrong place

**Seen:**
- The first `j` from page load focuses the second To-do item, not the first Needs-you line
  (`screens/27-keyboard-j-starts-in-todo.png`).
- Agenda and Came in rows are skipped (no `data-row`).

**Do:**
- j/k walks the **queue** in rank order first.
- `]` and `[` (or `g` then `r`) jump to the rail panels.
- Document this in the shortcut sheet.

### 3.23 [P2] Toasts stack and repeat

**Seen:** "Copied" and "Marked as sent to Ines Duarte · Undo" stack as two dark bars over the content
(`screens/19-…`).

**Do:** one toast that updates in place ("Copied" becomes "Marked as sent · Undo"). Keep toasts clear of the primary
action column. On phone, put them above the bottom bar.

### 3.24 [P2] Offline and live state

**Seen:** with the browser set offline for 6 seconds, the header still read "Live · updated 11:18 PM"
(`screens/28-…`). This may be detection latency rather than a bug.

**Do:**
- **Specify:** the status chip shows "Offline · reconnecting" within 5 seconds.
- Actions that need the server say "Will run when back online".
- Add an end-to-end test that sets the browser offline.

---

## 4. Screen-by-screen notes

- **Header** (all screens): see §3.4 and §3.5. Ask should be a search-style field with its `/` hint (as in the
  prototype), not a button.
- **Today:** see §3.1–3.4 and §3.18.
  - **To do** is the best-made part of the current board: grouped by when, one button per row, readable meta. Keep its
    feel in the rail.
  - Use checkboxes for your own to-dos (`mockup/`). That's faster than a "Mark done" button, and it has an undo toast.
- **What changed:**
  - The 3-way filter belongs on the full page.
  - "QUILL SAYS" becomes the voice line in `visual-spec.md` §5.10.
  - "Show source" opens the source in the inspector on wide screens.
- **Follow-ups (Chasers):**
  - Person cards ("Ines Duarte · 2 to send · [Copy 2]") are excellent. Keep them and fix §3.8.
  - Waiting on them (`screens/19-…`): "They finished it" is a quiet text button. Make it a secondary button and show
    "sent today" as a pill tone.
- **Stages:** two sections of one card each. Make it a board (§4.4). Fix the generated wording (§3.17).
- **People & projects:** split into **Projects** (the portfolio table) and **People** (a table with an organizations
  filter). Move Edit into the row's detail pane. Remove "Active" pills. Remove "Synced folder" from this page.
- **Record pages:** see §3.19.
- **Files / Pieces:** fine empty states. "New piece" belongs only on Pieces, under Work. The New piece dialog copy is in
  §3.17.
- **Sources:** good descriptions. Use a table with **Turn on** (§3.14). Auto-closed belongs here, which is right.
- **Settings, More settings, setup guide:** see §3.10 and §3.11.
- **Add-ons:**
  - It uses a fourth segmented style (an underline). Use the shared component.
  - The empty catalog needs a next step: "Install from a file…".
- **Ask dialog:** clean, and "Recent questions" is good. On wide screens, open it as a right-hand pane so answers with
  lists have room and the work stays visible.
- **Feedback dialog** (`screens/25-…`): good intent. The message preview repeats the text box above it. Show one editable
  message with the version lines appended, and keep "This app sends nothing".
- **Keyboard help:** group the keys (Move / Act / Open). Add `]`/`[` for panes.
- **Dark mode:** solid. Tone the amber notice down (it goes away with §3.4 anyway). Add a theme toggle.

---

## 5. Gaps between the design and the build

| Spec | Says | Build | Action |
|---|---|---|---|
| 7.0 / 7.7 | Today is one ranked queue; nothing informational | 4-column dashboard (owner decision 2026-10-11) | Queue-first dashboard (§3.1); reconcile in the doc |
| 7.1 | Tabs: Today / Work / Portfolio / Admin | 8 flat tabs plus plugins | Sidebar (§3.5) |
| 7.1 | Header collapses to a menu on narrow screens | Clipped sideways strip | Icon rail and bottom bar |
| 7.1 | Date, Today count, Refresh, Jobs, Log, quick links | Missing | Date and count in the Today heading; jobs, log and refresh in the status popover; quick links in the sidebar |
| 7.1 | Portfolio health table | Missing | Projects table (§4.4) |
| 7.3 | Send back with the *option* "Undo it, then send" | Always undoes; submit hidden | §3.21 |
| 7.4 | Waiting to go out, with diffs and Approve | Missing | Reserve it and design it (§3.7) |
| 7.5 | Copy shows the editable message first | Blind copy from a collapsed card | §3.8 |
| 7.6 | Skeleton rows, not spinners | 1 skeleton, 29 "Loading…" | Shared skeleton |
| 7.6 | Never an instruction the screen can't carry out | 9+ CLI or config strings | Buttons |
| 7.6 / Part 1 | No internal ids on screen | Record pages show PER-, ORG-, TEAM- ids and raw enums | §3.19 |
| 7.9 | Settings grouped, basic first, advanced behind a toggle, inline help | One long page; 131 advanced fields; 6 Save buttons | §3.10 |
| 7.10 | AA contrast in both themes | Control borders 1.35:1 | `tokens.css` |
| 7.10 | Brand colours from config, with a contrast warning | Not wired | `visual-spec.md` §2.4 |
| 7.11 | CSS modules, routing, events invalidate affected queries | Global CSS, hash routing, invalidate-all | Components with CSS modules; invalidate by kind |
| — (new) | Use the whole screen | Fixed 880px column | §3.18, `visual-spec.md` §4 |

---

## 6. Changes to make to the design documents

1. **Rewrite 7.7** as "Today: a ranked queue with a detail pane and a context rail". Fold in the 2026-10-11 decision
   and define the ranking. Held items and decisions are always top-level. **Replace the prototype** with one based on
   `mockup-today.html`.
2. **Add 7.12 "Visual system"** from `visual-spec.md` §1–3 and §5–8, with `tokens.css` as the source of values.
3. **Add 7.13 "Layout and screen use"** from `visual-spec.md` §4: the shell, breakpoints, pane patterns per view and
   density. The rule is that the app fills the window and adds panes as it grows.
4. **Add "Row anatomy" and "Title rule"** (§3.2, `visual-spec.md` §5.3), with at most two levels of nesting.
5. **Add a navigation budget** to 7.1 and the plugin part: a sidebar, with plugins only under Work or Records.
6. **Add a mobile section:** the bottom bar, Needs-you first, one-item review mode.
7. **Rewrite 7.1's header list:** brand, Demo chip, Ask field, status chip, Hand in, Help, user menu. No footer.
8. **Add a Settings IA to 7.9:** nav | form | help, autosave with undo, "Changed · Reset", pickers, live previews for
   templates, and advanced settings grouped.
9. **Add record page and form patterns:** activity | details, drawers, field sizing.
10. **Pick one word each** for Follow-ups/Chasers, Needs you/Waiting for you, and outside content/untrusted.
11. **Add the screen-space, contrast and style-lint checks** to 10.x (guardrails) and 7.11 (tests).

---

## 7. Suggested order of work

1. **Foundation (about 1 week):** `tokens.css`, the type and spacing scales, the shared components (§5 of the spec), the
   style-guide view, stylelint, and screenshot and axe tests.
2. **Shell (3–4 days):** sidebar, one-row header with the status chip, no footer or banners, links for views, bottom bar
   on phone (§3.4–3.6).
3. **Today (about 1 week):** queue | inspector | rail, the title rule, held items at the top level, Review & copy, the
   send-back placement, the keyboard order, and the prototype update (§3.1–3.3, 3.8, 3.21, 3.22).
4. **Records and lists (about 1 week):** table + detail for Projects, People, Files and Sources; record pages; drawer
   forms (§3.18–3.20).
5. **Settings and setup (about 1 week):** §3.10 and §3.11.
6. **Then:** Waiting to go out with the diff, the Stages board, and the phone review mode (§3.7, §3.13).
7. **Throughout:** microcopy (§3.17) and the accessibility fixes (§3.16).

---

## 8. Master checklist

This list is what the re-review will check. Each item cites its finding.

**Shell and screen use**
- [ ] C1. Left sidebar navigation with Today / Work / Records / Sources, Add-ons and Settings. Plugin panels nest; the
  header never wraps. (3.5)
- [ ] C2. One-row header of 56px or less, with a Demo chip, Ask field, status chip, Hand in, Help and user menu. No
  footer. No banners. (3.4)
- [ ] C3. The header and sidebar don't move between views. (3.6)
- [ ] C4. At 1440 and 1920, content covers at least 90% of the width beside the sidebar on every view. No margin over
  48px outside panes. (3.18)
- [ ] C5. Panes are added by width as in `visual-spec.md` §4.3 (inspector at ≥1680 on Today; detail panes on lists).
  (3.18)
- [ ] C6. Real links for views, which can be bookmarked and opened in a new tab. (3.5)
- [ ] C7. Phone: bottom bar, Needs you first, no sideways scroll, first queue line above the fold. (3.13)

**Today**
- [ ] C8. Queue-first: a ranked list of verb lines grouped Decide / Review / Send, one primary each, no nested panels
  or filters. (3.1)
- [ ] C9. The first queue line is within 140px of the top at 1280×720; a typical day is visible without inner scrolling.
  (3.1)
- [ ] C10. Every decision and held item is a top-level line, one click away. (3.3)
- [ ] C11. Rail: Agenda, Your to-dos, Came in, sized to content; an empty panel is one line. (3.1)
- [ ] C12. The setup line is a single row with progress; no CLI text. (3.4)
- [ ] C13. j/k starts at the first queue line; panes can be reached by keyboard. (3.22)

**Items and records**
- [ ] C14. Title rule: no row title starts with a greeting, "From:", or a cut-off sentence; outcomes instead of
  "Quill did 1 thing". (3.2)
- [ ] C15. At most two levels of bordered containers anywhere. (3.3, 3.9)
- [ ] C16. Fixed row anatomy; the menu at the right edge on every row. (3.9)
- [ ] C17. Pills only for exceptions, with four tones; sentence case; no uppercase sentences. (3.9)
- [ ] C18. Record pages: the name as title, resolved names, formatted dates, no help text, activity | details. (3.19)
- [ ] C19. No internal id or raw enum value on any screen. (3.19)

**Actions and flows**
- [ ] C20. Copy never puts unseen text on the clipboard; "Review & copy". (3.8)
- [ ] C21. Send back is fully visible, with an optional "Undo what Quill did first". (3.21)
- [ ] C22. Hand-in is a drawer (sheet on phone), at most 3 interactions, textarea at 72ch or less, focus returned.
  (3.12)
- [ ] C23. Forms in drawers, fields sized to content, two columns when wide, grouped, hints below fields, inline
  validation. (3.20)
- [ ] C24. Every disabled control says why or offers the enabling action; every empty state has a button. (3.14)
- [ ] C25. Toasts merge and update; errors stay inline with Try again. (3.23, 3.16)
- [ ] C26. Waiting to go out exists, at least as a designed screen with an empty state. (3.7)
- [ ] C27. Projects is a portfolio table; People is a table with a detail pane; Stages is a board. (3.18, §4)

**Settings and setup**
- [ ] C28. Settings is nav | form | help, with autosave plus undo (or one save bar) and "Changed · Reset" only when
  changed. (3.10)
- [ ] C29. Pickers for time zone, language, money and dates; no raw env vars, IANA ids, locale tags or `{placeholders}`
  by default. (3.10)
- [ ] C30. AI accounts with display names and status chips. (3.10)
- [ ] C31. Setup guide as a stepper with collapsed done steps and a matching progress count. (3.11)

**Visual system**
- [ ] C32. `tokens.css` adopted; colour roles as in `visual-spec.md` §2.3; brand colour from config with a contrast
  guard. (3.15)
- [ ] C33. Six type sizes and three weights; one UI family; tabular numbers. (3.15)
- [ ] C34. 4-point spacing and three radii; stylelint enforces the scales and bans raw hex, uppercase and
  opacity-disabled. (3.15)
- [ ] C35. One component each for Button, Pill, Row, Panel, SegmentedControl, EmptyState, LoadFailed, Skeleton, Drawer
  and StatusChip. (3.15)
- [ ] C36. Line icons replace the text glyphs; nav shows icon and label. (`visual-spec.md` §6)
- [ ] C37. Density setting; touch targets of at least 44px on coarse pointers. (`visual-spec.md` §4.5)
- [ ] C38. Theme toggle (System / Light / Dark). (`visual-spec.md` §2.5)

**Accessibility and robustness**
- [ ] C39. Control borders at least 3:1; double focus ring; axe passes in light and dark at 390, 1024, 1440 and 1920.
  (3.16)
- [ ] C40. Focus moves to the heading on view change; focus returns from drawers and dialogs. (3.16)
- [ ] C41. Skeleton rows with `aria-busy` instead of "Loading…". (3.16)
- [ ] C42. Live updates invalidate by kind; new items wait behind "N new · Show". (3.16)
- [ ] C43. Offline shows within 5 seconds; queued actions say so. (3.24)

**Words**
- [ ] C44. No `cockpit …`, `.yaml`, config paths or `env:` on the default path. (3.4, 3.17)
- [ ] C45. The §3.17 table applied; one word each for Follow-ups, Needs you and outside content. (3.17)

**Design documents**
- [ ] C46. 7.7 rewritten and the prototype replaced; 7.12 Visual system and 7.13 Layout added; the other §6 items done.

---

## 9. Coverage

**Reviewed (screens in `screens/`):**

| Area | Screens and states reviewed |
|---|---|
| Today | First run; populated; Start here hidden; expanded review; show source; row menu; send back; filters |
| Follow-ups | To send; after Copy; Mark sent with Undo; Waiting on them |
| Other views | Stages (before and after a move); Files; Pieces with the New piece dialog; Sources; People & projects; add person; edit project |
| Record pages | Project; person |
| Settings | Basic; more settings; search |
| Setup and add-ons | Setup guide; Add-ons |
| Dialogs | Ask; keyboard help; Feedback |
| Hand-in | Desktop and phone |
| States | Offline; dark mode |

Every one of those was checked at 1440. Today was also checked at 1280, 900, 390, 1920 and 2560, and in dark. Lists,
Settings and People were also checked at 1920 and 2560.

**Not reviewable in this build** (the design should still cover them, using this system):
- **Waiting to go out and the diff review:** not built.
- **The compare view for long text and working copies:** these exist (`TextReview.tsx`, `WorkingCopies.tsx`) but no
  demo data reaches them.
- **File action review** (`ActionReview.tsx`).
- **Sign-ins for an add-on.**
- **The restart notice.**
- **An Ask answer from a real AI account.**
- **Error states with the server down.**
- **A day with 30 or more items**, which needs virtualized lists and the "N new · Show" pill.

## Screens

| File | What it shows |
|---|---|
| `01-today-first-run.png` | First screen: banners, Start here, four columns, decision cut off |
| `02-today-populated.png` | After hand-ins: "Hi team," titles, Needs you squeezed |
| `03-evidence-nested.png` | Evidence and highlight (keep), and "Who is Maya?" five levels deep |
| `04-chasers-after-copy.png` | Blind Copy from a collapsed card, then Mark sent |
| `05-today-tablet.png` | 900px: Needs you is a box about 200px tall |
| `06-phone-first-screen.png` | Phone: the first screen is all chrome; nav clipped |
| `07-phone-full-page.png` | Phone full page (about 4,400px) |
| `08-hand-in.png` | Hand-in inline at full width |
| `09-stages-header-shift.png` | Centered layout; nav wraps to two rows |
| `10-sources.png` | Disabled "Read now" with no "Turn on" |
| `11-people-projects.png` | "ACTIVE" pills, four primaries, misplaced Synced folder |
| `12-settings-full-page.png` | Settings: one long page, six Save buttons |
| `13-setup-guide.png` | Setup: all steps expanded |
| `14-add-ons.png` | Add-ons dead end; fourth segmented style |
| `15-dark.png` | Dark theme |
| `16-prototype-today.png` | The reference prototype: the ranked verb queue |
| `17-today-start-here-hidden.png` | Steady state: still about 230px of chrome |
| `18-send-back.png` | Send back: submit hidden below the column edge; forced undo |
| `19-waiting-on-them-toasts.png` | Waiting on them; two stacked toasts |
| `20-record-project.png` | Project page: Owner "PER-1", raw date, help text as content |
| `21-record-person-ids.png` | Person page titled "PER-2"; ORG-1, TEAM-1, "active" |
| `22-add-person-form.png` | Inline add form with 850px fields |
| `23-edit-project-inline.png` | 13-field edit form expanded inside the list |
| `24-new-piece-dialog.png` | "Apply" / "It won't change anything" for a create |
| `25-feedback.png` | Feedback mail draft (keep; trim the duplicate preview) |
| `26-more-settings-131.png` | 131 settings, template syntax in labels |
| `27-keyboard-j-starts-in-todo.png` | The first `j` lands in To do, not Needs you |
| `28-offline-still-live-stage-wording.png` | Offline test still says Live; "ready for Ready for review" |
| `29-1920-today.png`, `32-2560-today.png` | Today on wide screens: empty columns stretched |
| `30-1920-people-54pct-empty.png`, `31-1920-settings.png`, `33-2560-people.png` | 880px column on wide screens: 54–66% empty |
| `../mockup/mock-*.png` | The proposed Today at 390, 900, 1280, 1440 and 1920, light and dark |
