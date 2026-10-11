# Visual design spec

A companion to `README.md` (the review). This file says **what the screens should look like**: colour, type,
layout and use of the screen, components, icons, motion and states. `tokens.css` holds the values, ready to drop in.
`mockup-today.html` (and the renders in `mockup/`) shows them applied to Today.

The design agent should fold this into the design as **Part 7.12 "Visual system"** and **7.13 "Layout"**. The builder
then refactors `web/src/styles.css` to it.

---

## 1. Visual direction

**Character: a calm, dense workbench.**
- The screen should feel like a well-made professional tool, in the vein of the best issue trackers and mail clients.
  The PM can work through 30 items in ten minutes without the UI shouting.
- Neutral greys carry structure. **One accent colour** marks "act here". Three status colours appear **only** where a
  state changes what the PM should do.
- Hierarchy comes from **type weight, spacing and alignment**, not from boxes, capitals or colour.
- **Every pixel earns its place.** The app fills the window at every size (§4). There are no decorative margins, no
  banners, and no footer taking a row.
- **The assistant's work looks like evidence, not chat.** Quoted sources, highlights and a quiet "voice" rule are used
  instead of chat bubbles.

**Tests for "done":**
- A screenshot of any view in greyscale still shows what to do first.
- Squinting at the screen shows 2–3 weights of mass, not 15 bordered boxes.

---

## 2. Colour

### 2.1 What's there now

The colours are measured from `web/src/styles.css`.

| Check | Light | Dark | Verdict |
|---|---|---|---|
| Body text on page | 16.1:1 | 15.3:1 | Excellent |
| Muted text on surface | 6.8:1 | 7.5:1 | Good |
| Accent on surface | 7.8:1 | 7.7:1 | Good |
| Status text on its soft fill (warn, risk, ok, accent) | 6.1–6.7:1 | 6.2–8.1:1 | Good |
| **Card surface vs page** | **1.08:1** | **1.08:1** | Cards are barely distinct from the page, so every group needs a border and shadow. This is the root of the "box everything" look |
| **Input and control borders vs surface** | **1.35:1** | **1.32:1** | **Fails WCAG 1.4.11** (non-text contrast, 3:1) for form field boundaries |
| **Disabled primary button text** (opacity 0.5) | **2.5:1** | 3.0:1 | Hard to read; the disabled state is shown by opacity alone |
| Focus ring | Same colour as primary buttons | Same | Weak on primary buttons |

Other issues:
- **One hue does four jobs.** The accent serves as primary button, selected nav, link and focus ring. So "selected",
  "clickable" and "focused" look alike.
- **Brand colour from `config/ui.yaml` is not wired in.** 7.11 promises it, and nothing reads it.
- **The amber notice is the loudest thing on screen,** even though it is the least important.
- The palette itself (cool grey with an indigo accent) is sound and accessible. **Keep its hues.** Fix the roles and
  the structure.

### 2.2 Proposed palette

The full values are in `tokens.css`. Every text pair was checked against WCAG 2.2 AA:

| Pair | Light | Dark |
|---|---|---|
| Text on canvas | 16.3:1 | 15.9:1 |
| Muted text on surface | 6.9:1 | 7.9:1 |
| Subtle text (meta) on sunken background | 4.7:1 | 5.4:1 |
| **Control border (`--border-strong`) on surface** | **3.3:1 ✓** | **3.9:1 ✓** |
| Text on accent (primary button) | 7.8:1 | 7.3:1 |
| Accent text (links) on surface | 8.8:1 | 8.8:1 |
| Warn, danger, ok on their soft fills | 5.7–6.0:1 | 6.9–8.4:1 |
| Disabled text on disabled fill | 4.7:1 | 5.4:1 |

Notes:
- **Card and page contrast stays low on purpose** (about 1.1:1). Cards are grouped by spacing and a hairline
  `--border`. That border is decorative, not a control boundary.
- Controls (inputs, selects, checkboxes, secondary buttons) use `--border-strong`.

### 2.3 Colour roles (rules)

| Role | Token | Use | Never |
|---|---|---|---|
| Canvas | `--canvas` | Page background behind panes | Inside a card |
| Surface | `--surface` | Panes, queue, header, sidebar, inputs | — |
| Sunken | `--surface-sunk` | Quoted source, code, expanded detail, group headers | Whole sections |
| Accent | `--accent` | **The one primary action per row or region**; selected nav item (as a soft fill); links (`--accent-text`) | Decoration, headings, icons that do nothing |
| Accent soft | `--accent-soft` | Selected row, "Needs you" and "Send" pills, the current nav item | Large areas |
| Warn | `--warn` / `--warn-soft` | **Waiting for you**, held, backup needed, approaching due | Informational notices |
| Danger | `--danger` / `--danger-soft` | **At risk**, overdue, errors, destructive confirm | "Removed" diff text alone (pair it with a mark) |
| Ok | `--ok` / `--ok-soft` | Done, healthy, test passed, the setup progress bar | "Active" on every person |
| Mark | `--mark` | Evidence highlight in a source, search hits | Anything else |
| Neutral pill | `--surface-sunk` + `--text-muted` | Kinds ("Review", "Action"), counts | — |

Two more rules:
- **Status always comes with a word** (7.10). Colour reinforces the word; it never carries the meaning alone.
- **At most 3 coloured pills per screen region.** If more rows need colour, the ranking is wrong.

### 2.4 Branding from config

- `config/ui.yaml` → `ui.brand.color` sets `--brand-600`.
- The app derives the other shades at start-up: hover (about 15% darker), soft (about 8% tint over the surface), and
  dark-mode versions (lighter by about 35 in OKLCH lightness).
- If white text on the brand colour is below 4.5:1, the app switches `--text-on-accent` to near-black.
- Settings shows a warning with the measured ratio (7.10).
- `ui.brand.logo` replaces the monogram in the header.

### 2.5 Dark mode

- No pure black: the canvas is `#0e1014`. Surfaces are *lighter* than the canvas. Depth comes from lightness, not
  shadows.
- Accents are lighter and less saturated (`#8b98ff`). Text on accent becomes dark.
- Soft fills are deep tints, not translucent overlays, so text contrast is predictable.
- **Add a theme switch** (System / Light / Dark) in the user menu. The `[data-theme]` hook already exists.
- Notices in dark use a soft fill and a word, never a full amber block.

---

## 3. Typography

**One family, the system UI font.** Drop the serif display stack (Iowan Old Style, Palatino, Georgia). It renders
differently on every OS, reads as a fallback at small sizes, and clashes with a dense sans UI. If a brand wants a
display face, allow it only for the page title, through `--font-display`.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--text-2xl` | 28/34 | 600 | Reserved (an empty Today greeting) |
| `--text-xl` | 22/28 | 600 | Page title ("Today", "People") — one per view |
| `--text-lg` | 18/24 | 600 | Pane and section titles, dialog titles |
| `--text-md` | 15/22 | 400 / 600 | Body, row titles (600), form values |
| `--text-sm` | 14/20 | 400 / 500 / 600 | Row meta, buttons, labels, nav |
| `--text-xs` | 12/16 | 500 / 600 | Pills, group headers, captions, timestamps |

Rules:
- **That is 6 sizes and 3 weights (400, 500, 600).** The build has 16 sizes and 6 weights. 700 and 800 go.
- **Sentence case everywhere.** No `text-transform: uppercase` on any label longer than one word. Group headers
  ("Decide", "Review") are 12/600 in sentence case in `--text-subtle`.
- **Tabular numbers** (`font-variant-numeric: tabular-nums`) for times, dates, counts and money.
- **Line length:** paragraphs, messages, pasted sources and assistant text max out at `--measure` (72ch) *inside their
  pane*. That limits the text block, not the layout.
- **Labels sit above fields** at 14/600. Hints go *below* the field at 12/400 in `--text-subtle`. Never put a bold
  parenthetical inside the label, as in "Role (for example: Editor…)".
- Truncate titles at 2 lines, with an ellipsis and the full text on expand. Never truncate names.

---

## 4. Layout: use the whole screen

**The principle: the app fills the window at every width.** As the window grows, the app **adds panes**: navigation,
queue or list, detail and context. It does not pad a fixed column with empty margins.
- Only running prose is limited, by `--measure`, inside its pane.
- Nothing scrolls inside a fixed-height box except a pane designed to (the sidebar, an inspector).

### 4.1 What the build does now

Measured from the screenshots:

| Width | Today | Every other view |
|---|---|---|
| 1440 | 4 equal columns. The work column is about 25%, scrolls inside itself, and shows 2½ of 13 items. Two empty columns take about 50% | Content is 880px centered: **39% of the width is empty** |
| 1920 | The same, stretched | 880px centered: **54% empty** (`screens/29-1920-today.png`, `30-1920-people-54pct-empty.png`, `31-1920-settings.png`) |
| 2560 | Agenda column 500px wide and empty; "Mark done" 350px from its text (`screens/32-2560-today.png`) | 880px centered: **66% empty** |
| Vertical, 1440×900 | About 230px of chrome: the DEMO strip, a 2-row header, the stand-in banner, and a footer row | The same, without the banner |

### 4.2 The shell

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ ▣ Workspace  Demo   [⌕ Ask Quill or search…  /]        ● Live · Backup  [+ Hand in] ? (AL) │ 56px header
├────────────┬──────────────────────────────────────────────────────────────────┤
│ ⌂ Today  8 │                                                                  │
│ Work       │                                                                  │
│  What chg 4│                    CONTENT AREA (fills the window)                 │
│  Follow-up │                    panes per view, see 4.4                        │
│  Waiting…  │                                                                  │
│  Stages    │                                                                  │
│ Records    │                                                                  │
│  Projects  │                                                                  │
│  People    │                                                                  │
│  Files     │                                                                  │
│ ─────────  │                                                                  │
│  Sources   │                                                                  │
│  Add-ons   │                                                                  │
│  Settings  │                                                                  │
└────────────┴──────────────────────────────────────────────────────────────────┘
   232px sidebar (64px icon rail at 1024–1279; hidden on phone → bottom bar)
```

- **The left sidebar replaces the top segmented control.**
  - It scales to plugin panels, which nest under Work or Records.
  - It shows counts.
  - It frees the header.
  - It uses the side margin that wide screens have to spare.
  - The person can collapse it to icons.
- **The header is one row of 56px.**
  - The DEMO strip becomes a "Demo" chip.
  - The status row becomes one status chip ("● Live · Backup needed") that opens a popover with details (last check,
    backup age, today's AI spend, restart).
  - Ask becomes a search-style field with its `/` hint.
  - Hand in becomes a "+" primary button.
  - Help and shortcuts become an icon button. The person's initials open the user menu (theme, density, sign out).
- **No footer.** The version, "Send feedback" and the shortcut hint move into the Help menu.
- **No banners above content.** System messages go to the status chip, the setup line (one row), or a Today line.
- Vertical chrome drops from about 230px to **56px**.

### 4.3 Breakpoints and what each shows

| Name | Width | Shell | Today | Lists (People, Projects, Files, Sources) | Settings |
|---|---|---|---|---|---|
| Phone | < 640 | Bottom bar: Today · Work · **+** · Ask · More. Header 48px | Queue only. The rail goes below, collapsed | Single-column rows. Detail opens as a full screen | Sections as a list; each opens as a full screen |
| Tablet | 640–1023 | Icon rail (64px) | Queue full width; rail below in 2 columns | Table with fewer columns. Detail as a drawer | Section list, then the form |
| Laptop | 1024–1439 | Icon rail, or full sidebar if pinned | **Queue + rail** | **Table + detail pane** (when a row is selected) | Section nav + form |
| Desktop | 1440–1919 | Full sidebar | Queue + rail | Table + detail pane | Section nav + form (2 field columns) + help pane |
| Wide | 1920–2559 | Full sidebar | **Queue + inspector + rail** | Table + detail pane with tabs (activity, details) | Same as desktop, wider |
| Ultra | ≥ 2560 | Full sidebar | Queue + inspector + rail. The rail adds a **This week** pane | Table + detail + related (questions, actions) | Same |

### 4.4 Pane patterns per view

**Today: queue | inspector | rail.**
- The queue (§5.4) takes `1fr`, minimum 560px. It always gets the most width.
- The **inspector** (≥1680px) shows the selected line's items, evidence and highlighted source, a message preview to
  copy, or the decision form.
- Below 1680px, the same content **expands in place** under the line.
- The **rail** holds Agenda, Your to-dos and Came in. Each panel is sized to its content. An empty panel is one line.
- See `mockup/mock-1440.png`, `mock-1920.png` and `mock-phone.png`.

**What changed, Follow-ups, Waiting to go out: list | detail.**
- These are mail-client layouts. The left list holds rows with one primary action each. The right pane holds the
  selected item in full: the source with highlights, the assistant's work with evidence, the message editor, or the
  word-level diff.
- The keyboard loop (j/k/a/s/c/e/u) works across both panes.
- **Waiting to go out** uses the full width for diffs. Below about 1600px it is inline; above, side by side.

**Stages: board.** One column per stage fills the width, with horizontal scroll only past about 6 stages. Cards show the
title, project, owner avatar and due date. Move a card by drag, keyboard (`m` then a stage key) or the menu.

**Projects (Portfolio): table + detail.**
- Columns: project, group, status (a pill, exceptions only), phase, target, owner, open actions, open questions, last
  change.
- Rows are grouped by the configured grouping. Columns can be sorted and resized.
- Selecting a row opens the record's detail pane.
- On wide screens, all columns show. On laptop, the less important ones hide behind a column picker.

**People and Organizations: table + detail.**
- Columns: name, role, organization, how to reach, open items with them, last contact.
- Rows have no "Active" pill. Inactive and track-only people are filtered or tagged.
- The detail pane shows details, open questions and actions with them, and history.

**Files, Pieces and plugin record panels:** use the same table + detail pattern, or a grid of thumbnails for files when
the person chooses it.

**Sources:** a table with name, kind, schedule, last read, items and state (with **Turn on** for an Off source). The
detail pane holds settings, the last run and the auto-closed items for that source.

**Record page (project or person)** — full page, two columns.
- **Main, `1fr`:** an activity timeline (changes, notes, decisions), then open actions and questions.
- **Side, about 360px:** details as label/value pairs (resolved names, formatted dates, no help text), plus Edit.
- The title is the record's **name**, never its id (`screens/21-record-person-ids.png` shows "PER-2").

**Settings: section nav | form | help.**
- 220px section nav.
- The form lays fields out in **two columns of `--field-max`** (560px) when there is room. Related fields such as the
  backup interval and how many to keep sit side by side.
- At ≥1440px, a help pane shows the focused field's description, its default and "what reads this", and the read-back
  after a change. This replaces the "Default: x · Back to default" pair repeated under every field.

**Setup guide: steps | step.** A checklist on the left ("4 of 6 done"). The open step on the right uses the form rules
above.

**Forms for one record** (add or edit a person, project, piece):
- Use a **drawer from the right** (`--detail-w`), so the list stays visible and the new row appears beside it.
- Lay out in 2 field columns when the drawer is at least 560px.
- Don't expand forms inline inside a list row (`screens/23-edit-project-inline.png`): that pushes the list off the
  screen.

**Hand something in:**
- Desktop: a drawer from the right, about 640px. The textarea is limited to `--measure`, and Today stays visible.
- Phone: a full-screen sheet from the **+** button.

### 4.5 Density

- **Comfortable** (default): 56px rows and 36px buttons.
- **Compact**: 44px rows and 30px buttons. Set from the user menu and remembered per device.
- On a coarse pointer, touch targets are at least 44px whatever the density.

---

## 5. Components

Each is one shared component with its own CSS. The build has about 9 button families, 3 segmented controls and
3 empty-state styles. Each of those becomes one.

### 5.1 Button

| Variant | Look | Use |
|---|---|---|
| Primary | `--accent` fill, `--text-on-accent` | **One per row or region**: the likeliest next step |
| Secondary | `--surface` with a `--border-strong` 1px border | Other visible actions (Cancel, Edit, Connect) |
| Ghost | No border, `--text-muted`; hover fill `--surface-hover` | Toolbars, "Hide", icon buttons, "•••" |
| Danger | `--danger` fill | Irreversible confirm only (publish, send, delete) |

- **Sizes:** md is 36px with 14px padding; sm is 30px with 10px padding. On touch, 44 and 40px. 14/600 text. Radius
  `--radius-md`.
- **States:**
  - hover: darker fill, or the hover surface
  - active: 1px translate or a darker fill
  - focus: the double ring from `tokens.css`
  - **disabled:** `--surface-sunk` fill with `--text-subtle` text and a border. **Not opacity.** Always paired with the
    reason (a hint under the button, or a tooltip on focus and hover).
  - loading: a spinner replaces the icon and the label stays
- **Icon + label** when an icon helps. Icon-only buttons always have `aria-label` and a tooltip.

### 5.2 Pill (status and kind)

- 22px high, 8px padding, `--radius-sm`, 12/600, **sentence case**.
- **Tones:** neutral, need (accent), warn, danger, ok (§2.3).
- **Show exceptions, not defaults.** "Active" on a person or "Not started" on every stage card is a default, so it gets
  no pill.
- A **group** ("Winter list") is not a status. Show it as plain meta text or a table column.

### 5.3 Row (list item) anatomy

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [Pill]   Title (15/600, max 2 lines)                          [Primary]   [•••]  │  ← 56px min (comfortable)
│ 128px    Meta: source · person · date · project (14/400 muted)                    │
└──────────────────────────────────────────────────────────────────────────────────┘
  ↑ status or kind column, fixed width, so titles align     ↑ actions right-aligned, same x on every row
```

- **Fixed positions:** the pill column, title, meta, primary and menu sit at the same x on every row of every list.
  The Organizations rows put "•••" next to the name instead, which must go.
- Rows are separated by **1px `--border` dividers**, not cards.
- **Selected:** an `--accent-soft` fill and a 3px inset accent bar on the left.
- **Keyboard focus:** the double ring. **Hover:** `--surface-hover`.
- **Expanded:** the content indents to the title column, on `--surface` (not a nested card). Child items are divided by
  dashed `--border` lines.
- **Maximum nesting:** a line, then its items. Evidence and source sit inside an item as a sunken block, not another
  card.

### 5.4 Queue (Today's "Needs you")

- **Groups:** Decide, Review, Send and follow up, Later. Each has a 12/600 group header on the `--canvas` tint.
- Lines are **verbs with counts**: "Answer 1 decision", "Look over 3 actions Quill added", "Send 2 questions to Maya
  Okafor".
- The pane header shows the count, "most urgent first" and keyboard hints (desktop only).
- **New items** arrive as a "2 new · Show" pill pinned at the top of the pane. Rows never shift under the cursor (7.0).
- **Clearing a line:** after its action, the line collapses (opacity and height animation, about 180ms) and an undo
  toast appears.

### 5.5 Panel (pane container)

- A `--surface` card with a 1px `--border`, `--radius-lg` and no shadow.
- The header row is 48px: title at 18/600 (or 15/600 in the rail), then count and actions at the right.
- **Only top-level panes are panels.** Nothing inside a panel is another bordered card except the sunken source block.

### 5.6 Form controls

- **Inputs, selects and textareas:**
  - 40px high (44px on touch), `--border-strong` 1px border, `--radius-md`, 15px text
  - placeholder in `--text-subtle`
  - focus: the double ring
  - error: `--danger` border, with a message below in `--danger` 12/500 prefixed with "!" or an icon
- **Width follows content:** a name field is about 360px, a number 120px, a date 180px. Fields are not stretched to
  880px (`screens/22-add-person-form.png`).
- **Select:** a custom listbox (React Aria) with search for any list over 8 items: people, time zones, projects.
  Native `<select>` is fine for short lists.
- **Time zone and language:** a searchable picker showing "New York (Eastern time) · UTC−4" and "English (United
  States)". Never a raw IANA id or locale tag.
- **Date:** a picker with typed entry, shown as "Tue, Dec 1, 2026". Never "2026-12-01" or "12/01/2026" in display.
- **Checkbox and radio:** 18px with a `--border-strong` border and the accent when checked. Two to four mutually
  exclusive choices become a **segmented control**: "Whose words: Someone else's | Mine".

### 5.7 Segmented control and tabs

- **One** segmented control: a 32px track on `--surface-sunk`, with the selected segment on `--surface` with
  `--elev-1`. Use it for 2–4 filters (To send | Waiting on them).
- **Tabs** (underline style) only for switching panes *inside a record* (Activity | Details | Files).
- Never use either as the main navigation (that is the sidebar).

### 5.8 Menu, dialog, drawer, popover

- **Menu:** `--surface`, `--elev-2`, `--radius-md`, 36px items with an optional icon, and a separator between groups.
  A destructive item goes last, in `--danger`. Disabled items show their reason (this already exists; keep it).
- **Dialog:** use only for a confirm that can't be undone (send, publish), or a short question. Max 560px, `--elev-3`,
  title at 18/600, primary at the bottom right, `--overlay` behind.
- **Drawer:** for forms and hand-in. It slides from the right (260ms ease-out, none under reduced motion), uses
  `--detail-w`, has a sticky footer with the actions, and Esc closes it with a guard against losing unsaved text.
- **Popover:** for the status chip and date pickers.

### 5.9 Toast

- Bottom center, 12px above the bottom bar on phone. Text-coloured fill (inverted), `--radius-lg`, `--elev-3`, at most
  3 stacked.
- **Success with undo:** stays for `toast_seconds` and pauses on hover and focus (this already exists; keep it).
- **Errors are not toasts:** an error stays inline at the place it happened, with **Try again**. Only a background error
  becomes a toast, and that toast stays until dismissed and uses `role="alert"`.
- Merge related toasts: "Copied" followed by "Marked as sent" becomes one toast that updates.

### 5.10 Evidence and the assistant's voice

These are the product's signature; give them a consistent, recognisable look.

- **Voice line:** a 3px `--border` left rule, 14px muted text, with the assistant's name in 600 ("**Quill:** Recorded
  the proof date."). Not "QUILL SAYS" in capitals.
- **Because:** 14px muted text, with the quote in italic `--text`, and "Source" as a link.
- **Source block:**
  - a sunken fill with `--radius-md`, limited to `--measure`
  - a 12px header line: source name, date, and an outside-content pill
  - highlighted passages use `<mark>` with `--mark` **and** an underline (not colour alone)
  - screen readers hear "highlighted: …"

### 5.11 Diff (Waiting to go out, 7.4)

- **Added:** `--ok-soft` fill, an underline, and a "+" gutter mark. The screen reader label is "added".
- **Removed:** `--danger-soft` fill, strike-through, and a "−" gutter mark. The screen reader label is "removed".
- **Moved:** a "↕ moved" pill on the row.
- Side by side at ≥1600px; inline below.

### 5.12 Empty, loading, error, offline

- **Empty:**
  - one sentence that says what will appear here, plus **one button** that makes it appear
  - in a rail panel, one line
  - in a main pane, centered in the pane with an optional 48px line icon
- **Loading:**
  - skeleton rows that match the row anatomy (3–5 rows, shimmer off under reduced motion)
  - no "Loading…" text (29 sites today)
  - `aria-busy` on the region
- **Error:** inline in the pane: "Couldn't load people. [Try again]", and the raw detail behind "Details".
- **Offline:**
  - the status chip turns warn: "Offline · reconnecting"
  - actions that need the server queue up and say so ("Will send when back online")
  - an offline indicator must appear within about 5 seconds of losing the connection. In a 6-second test with the
    browser set offline, the header still said "Live" (`screens/28-offline-still-live-stage-wording.png`); verify how fast it detects this.

### 5.13 Status chip (header)

- A 30px pill on `--surface-sunk`, with a dot and short text. **One worst state wins:**

  | State | Shows |
  |---|---|
  | All good | "● Live" |
  | Backup | "Backup needed" (warn) |
  | Offline | "Offline" (warn) |
  | Restart | "Restart to finish" (warn), with a button in the popover |
  | Spend limit near | "Spend 90% of today" (warn) |

- The popover lists all of them, each with its action.

---

## 6. Icons

- **Use a single line-icon set, bundled locally** (Lucide, ISC license, or equivalent). Inline SVG at 18px in nav and
  buttons and 16px in meta, with a 1.75–1.8 stroke and `currentColor`.
- **Replace the text glyphs** used as icons: "!", "•••", "?", "✕" and "↻". Each becomes a proper icon with an
  accessible name.
- **The nav always shows icon + label**, except the collapsed rail, which shows a tooltip on hover and focus.
- **Icons never carry meaning alone** in status. A pill always has its word.
- Suggested mapping:

  | Item | Icon |
  |---|---|
  | Today | home |
  | What changed | inbox |
  | Follow-ups | send |
  | Waiting to go out | upload |
  | Stages | layers |
  | Projects | grid |
  | People | users |
  | Files | folder |
  | Sources | rss |
  | Add-ons | puzzle |
  | Settings | gear |
  | Ask | search or chat |
  | Hand in | plus |
  | More | more-horizontal |

---

## 7. Motion

| What | How | Duration |
|---|---|---|
| Row expand and collapse | Height and opacity | `--dur-base` (180ms) |
| Line cleared after an action | Fade and collapse, then the undo toast | 180ms |
| Drawer in and out | Translate X | `--dur-slow` (260ms) |
| Toast in and out | Translate Y 8px and opacity | 180ms |
| Menu and popover | Opacity and scale from 0.98 | `--dur-fast` (120ms) |
| Hover and press | Background colour | 120ms |

- Everything goes to 0ms under `prefers-reduced-motion` (`tokens.css` does this).
- No motion for live updates. New items wait behind the "N new · Show" pill.

---

## 8. Data display

- **Never show an id** ("PER-2", "ORG-1", "TEAM-1", "PRJ-1") or a raw enum value ("active", "on_track"). Resolve them to
  names and labels everywhere: record pages, forms, meta lines and messages.
- **Dates:**
  - "Tue, Oct 13" within the year, "Oct 13, 2027" otherwise
  - relative for recent ones ("2 h ago", "yesterday"), with the full date and time on hover and focus
  - due dates add a word when it matters: "due today", "2 days overdue"
- **Times** use tabular numbers and the person's 12- or 24-hour preference.
- **Money:** "$0.25", "$2 a day", with the currency from config. Not "0.25 (USD)".
- **People:** the full name on first mention in a view, plus an avatar with initials in tables and boards. Never a bare
  first name, except in the copied message's greeting.
- **Counts** sit next to their label ("Follow-ups 3"). An empty count shows nothing, not "0", except in a header where
  the 0 is the information.
- **Help text is for forms, not for reading.** Record pages show values only; descriptions belong in the edit form and
  the Settings help pane.

---

## 9. How to build and enforce this

1. **Drop `tokens.css` in** as `web/src/theme/tokens.css`. Fill the brand primitives from `config/ui.yaml` at start-up.
2. **Make one component per pattern** in §5, each with its own CSS (CSS modules, as 7.11 already says), consuming only
   tokens.
3. **Add a living style guide view** (`#styleguide`, dev and demo only) that renders every component in every state.
4. **Add Playwright screenshot tests of the style guide and Today** in light and dark at 390, 1024, 1440 and 1920 widths,
   with axe on each. This catches visual regressions and contrast in one run.
5. **Add stylelint rules in the self-check:**
   - no raw hex outside `tokens.css`
   - `font-size`, `gap`, `padding`, `margin` and `border-radius` only from `var(--…)`
   - no `text-transform: uppercase`
   - no `opacity` on disabled controls
6. **Add a screen-space check** to the end-to-end suite:
   - at 1440×900 and 1920×1080, the main content's bounding box covers at least 90% of the window width minus the
     sidebar
   - no view has a horizontal margin over 48px outside panes
   - Today's first queue line is within 140px of the top
