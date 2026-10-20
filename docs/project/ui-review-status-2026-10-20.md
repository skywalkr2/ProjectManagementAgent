# UI/UX review checklist C1–C57 and N1–N8: status against the code

First written on 2026-10-20 before batch B-7 (C1–C46, from the code and tests in `web/src`, `web/e2e`, `api` and
`engine`); re-marked the same day after B-7 against the code, with C47–C53 (from the re-review at `c8f8e18`,
`reviews/ui-ux-2026-10/rereview-c8f8e18/README.md` §5) and N1–N8 (from the first-run review,
`reviews/ui-ux-2026-10/first-run/README.md`) added. The code decided each row; the docs only pointed to where to look.
"Done" means a named test or browser check shows it and the test passes. Anything less is "Partial", with what is
missing.

**Re-marked after the re-review at `0f37be4` and batch B-9 (2026-10-20).** The reviewer's marks at `0f37be4`
(`reviews/ui-ux-2026-10/rereview-0f37be4/README.md` §2) are in: C19, C47, C48 and C52 are Done (no id on any measured
view, six lines at 1280×720, no target under 24px); C54 and C56 are Done; C55 was Partial; C14 stayed Partial (S4); N3 and
N7 are Done as decided under F25, and N1, N2 and N8 are Not done. The reviewer's own count of C1–C53 was Done 32, Partial
21; this file counts its own rows against the code, and they are below. Then B-9's builds are marked, each with its tests:
S4 (C14), S2 (C55), and S1 as the new check C57 (the reviewer's S3, S5 and S6 have no check of their own: S3 is in the
pill-column row of 7.14, S5 and S6 in design 7.6 and 7.8, each with a test, see `docs/design/CHANGES.md` section 138).
The Python tests and the Vitest tests of B-9 ran and pass; the browser checks B-9 added (`today-capacity.spec.ts`,
`work-access.spec.ts`) are written, not run, and the measurement of S3 was made on the demo's build with a one-off script
(see below), not with the suite.

What ran for this re-marking (2026-10-20, on the commit that adds this file's changes to `00d7d92`): the Python tests of
every file cited below that B-7 or B-6b touched (each exits 0), and 52 Vitest files (912 tests, all pass), among them
every Vitest file cited below. The browser tests were not run (CLAUDE.md: they run once, in the full run before a push).

Cautions that apply to many rows:
- **Browser checks.** `web/e2e/a11y.spec.ts` and `web/e2e/panes.spec.ts` ran and passed in the full browser run at
  commit `ec37749` (axe in light and dark at 390, 1024, 1440 and 1920 for every main screen, the stages board with a
  card's menu open, the hand-in drawer, Ask as a pane, the phone's review mode, the walkthrough's look). Since then B-7
  changed `a11y.spec.ts`, `shell.spec.ts`, `tables.spec.ts`, `acceptance.spec.ts` and the journeys. What B-7 added to
  them (the first queue line's place at 1280×720, C47; the tables at 1440px, C49; no visible control under 24×24,
  C52; the header as one row at 800 to 1300px with no two controls overlapping) **ran and passed in the full browser
  run at `ae035b8`** (274 passed, 2 skipped, with the fallback font CI uses). The rows below were marked before that
  run; where one is Partial only for want of it, the run now supplies the evidence.
- **The status chip below 1440px** shows only its word: the backup's age is in its popover and its name, as the
  assistant's state already is. With a wider font and a long age the chip either covered Missed one or pushed the
  buttons out of the window.
- Test names are quoted from the files. Line numbers are left out because they move.

| Item | What it asks, in a few words | Status | Evidence / what is missing |
|---|---|---|---|
| C1 | Sidebar with Today / Work / Records / Sources / Add-ons / Settings; plugin panels nest; header never wraps | Partial | Sidebar and nesting: `Sidebar.test.tsx` ("the views are links, in the fixed groups, with plugin panels only under Work or Records"). B-7 made the header one row at every width (`web/src/shell/Header.test.tsx`: "below 1440px the assistant's state moves into the status chip's popover, as on the phone, and the line beside the chip is gone"). Missing: the browser check of one row at 1000, 1100 and 1200px (`shell.spec.ts`, "the header is one row…") is written, not run. |
| C2 | One-row header of 56px or less with Demo chip, Ask, status chip, Hand in, Help, user menu; no footer, no banner | Partial | `Header.test.tsx` covers every control, and from B-7 "Your pages" is the person's menu's first group (`HeaderLinks.test.tsx`). `shell.spec.ts` "every view fills the content area, under a header of at most 56px and no banner" checks 1440 and 1920 (ran at `ec37749`). Missing: the one-row check below 1280px is written, not run; no test asserts there is no footer, though none exists in `web/src`. |
| C3 | Header and sidebar don't move between views | Done | `shell.spec.ts` "the header and the sidebar do not move when the view changes" (ran at `ec37749`). |
| C4 | At 1440 and 1920 content covers 90% or more of the width beside the sidebar; no margin over 48px | Done | `shell.spec.ts` "every view fills the content area" asserts main width ≥ 90% at 1440 and 1920 on every view. The 48px margin limit is not asserted directly. |
| C5 | Panes added by width: inspector at 1680 or wider on Today, detail panes on lists | Partial | Today: `Today.test.tsx` "from 1680px the pane opens on the first line at once…". Lists: Projects and People use the list-and-detail pane, which from B-7 overlays the table when the columns don't fit (`TablesBesidePane.test.tsx`). Missing: Files, Sources, What changed and Follow-ups have no detail pane. |
| C6 | Real links for views; bookmarkable, open in a new tab | Done | `shell.spec.ts` "views are links: each entry has an address, and loading it opens the view". |
| C7 | Phone: bottom bar, Needs you first, no sideways scroll, first queue line above the fold | Partial | `BottomBar.test.tsx`; `shell.spec.ts` "on a phone the bottom bar is visible, the page does not scroll sideways…". B-7 made each rail panel under the queue one line (`TodayFirstScreen.test.tsx`: "on the phone each panel below the queue is one line that says what is in it, and a press opens it"). Missing: no test that Needs you comes first or that a queue line is above the fold at 390px (the re-review measured one at 431px). |
| C8 | Today is a ranked queue of verb lines grouped Decide / Review / Send, one primary each, no nested panels or filters | Done | `Today.test.tsx` "the queue is one ranked list in the engine's order, each line starting with a verb and offering one primary". B-7: one follow-up line per person in place of one "Chase" line per promise (`tests/test_follow_up_lines.py`). |
| C9 | First queue line within 140px of the top at 1280×720 (revised by the re-review to C47's 260px); a typical day visible without inner scrolling | Partial | B-7 removed what pushed the queue down: the backup bar is an At risk queue line and This week is a rail panel (`TodayFirstScreen.test.tsx`: "a backup that has never worked is an At risk line with the one button that mends it, and no bar above the queue", "This week is a panel of the rail at every width, never a section above the queue"). Missing: the measurement itself (`shell.spec.ts`, "Today at 1280x720 with setup …: the first queue line is at most … down and six lines show") is written, not run; the re-review measured 429px before B-7. |
| C10 | Every decision and held item is a top-level line, one click away | Done | `Today.test.tsx` "the restart and paused lines are rows of the queue…"; `HeldLines.test.tsx`; `TodayRecords.test.tsx`, `tests/test_held_ask.py`. |
| C11 | Rail: Agenda, Your to-dos, Came in, sized to content; an empty panel is one line | Done | The re-review's complaints are fixed in B-7: Top priorities has no buttons (`TodayFirstScreen.test.tsx`: "no filled button is anywhere in the rail; the one button it adds is Add to agenda"), the agenda's form is a drawer and an empty Agenda is one line (`TodayRail.test.tsx`), This week is a rail panel at every width. `TodayRail.test.tsx` "four panels in reading order…", "empty panels show no count of zero…". |
| C12 | Setup line is one row with progress, no CLI text | Done | `SetupLine.test.tsx` "it is one row: how far along, a progress bar, the next step and a button to continue"; wording check (see C44). |
| C13 | j/k starts at the first queue line; panes reachable by keyboard | Partial | `Today.test.tsx` "the cursor starts on the first line, and the arrows and Enter walk and open it". B-7 added the move key (`keys.test.tsx`). Missing: no key to move into the details pane or rail panels; F6 reaches only the toasts. |
| C14 | Title rule: no greeting, "From:" or cut-off sentence; outcomes, not "did 1 thing" | Done | `tests/test_today_queue.py` "a_pasted_message_is_titled_by_its_sender_and_subject"; `WhatChanged.test.tsx` "a change's line says what was done…". B-7 fixed the re-review's exceptions: a bare "Noted." (`tests/test_item_titles.py`) and reasoning or a statement in a title (`tests/test_item_text_lints.py`). **The re-review at `0f37be4` kept it Partial (S4):** "Email from Maya Lindqvist · We can host the reading at 6 pm…" and "Work Quill started". **B-9 built S4:** a short topic gives way only to a first line that fits whole, else a short topic of two words or more stays, else the title is the kind and who it came from (`tests/test_item_titles.py`, `web/src/lib/queue-words.test.ts`); work the app started says its kind and subject (`tests/test_item_titles.py` "work_the_app_started…", `queue-words.test.ts`). Done by those tests; the reviewer has not yet looked at it on screen. |
| C15 | At most two levels of bordered containers anywhere | Partial | Built through the `Panel` and `Row` components. Missing: no test or lint checks nesting depth (the re-review measured two on every view). |
| C16 | Fixed row anatomy; the menu at the right edge on every row | Partial | `ui/Row.test.tsx` "a row has a pill column, a title, a meta line, then the primary action and the menu". B-7 removed the filled Details button from People and Projects rows (`TablesBesidePane.test.tsx`). Missing: other rows are still hand-built (the rail's `.tb-title` rows, the Follow-ups cards). |
| C17 | Pills only for exceptions, four tones, sentence case, no uppercase | Done | `ui/Pill.test.tsx`; `stylelint-rules.test.ts` "uppercase text is refused"; `People.test.tsx` "…no Active tag on anyone". |
| C18 | Record pages: name as title, resolved names, formatted dates, no help text, activity \| details | Done | B-7 fixed what the re-review found: `RecordPageNames.test.tsx` (every reference a name, dates formatted, choices as labels, no help text while viewing, details starting with name, role, organization and how to reach), `RecordPageRecords.test.tsx` (activity worded with the assistant's name and field labels), `tests/test_record_page.py`. |
| C19 | No internal id or raw enum value on any screen | Done | Re-review at `0f37be4`: no id on any measured view. B-7's sweep (`RecordSweep.test.tsx`, "the people, projects, open to-dos and unfiled lists say names, dates and words") covers every kind of record's page and four lists; `shell.spec.ts` ("no Today line, inspector heading or What changed title holds an internal id") covers Today, its inspector and What changed. |
| C20 | Copy never puts unseen text on the clipboard; "Review & copy" | Done | `FollowUps.test.tsx` "Copy on a closed card opens the message first and copies nothing…", "when the clipboard is blocked nothing is marked and the card keeps Copy"; `copy.test.ts` (one helper, formatted and plain together, escaped); `Today.test.tsx` "Review & copy opens the message to copy…". |
| C21 | Send back fully visible, with optional "Undo what Quill did first" | Partial | `WhatChanged.test.tsx` "send back asks what to do differently, with Undo what it did first ticked, and unticking it keeps what it did". B-7 limited the box to 72ch and made the disabled button say "Write what to do differently first." (`SmallPoints.test.tsx`). Missing: no browser test that the submit button is visible (the original bug; the re-review measured it fully in view). |
| C22 | Hand-in is a drawer (sheet on phone), at most 3 interactions, textarea 72ch or less, focus returned | Partial | `panes.spec.ts` "Hand something in" passed at `ec37749`; `AskPane.test.tsx` ("opens as a drawer over the screen it was opened from…", "closing it with words in the box asks first, and Keep editing leaves them there"); "Whose words are these?" is a segmented control from B-7 (`SmallPoints.test.tsx`). Missing: the 3-interaction limit is untested and the textarea was about 80 characters wide when last measured. |
| C23 | Forms in drawers, fields sized to content, two columns when wide, grouped, hints below, inline validation | Partial | `People.test.tsx` "adding a person opens a drawer with the cursor in the name…", `Projects.test.tsx` "the project form is a drawer…". Missing: no test for two columns, grouping, or inline validation in those forms. |
| C24 | Every disabled control says why or offers the enabling action; every empty state has a button | Partial | `ui/Button.test.tsx` "a disabled button shows its reason and points to it"; `Walkthrough.test.tsx` (Continue says what is missing); `SmallPoints.test.tsx` (Send back); `ui/EmptyState.test.tsx`. Missing: no sweep over all disabled controls (the re-review found Answer, Hand in and setup Save without a reason; Save is now Continue). |
| C25 | Toasts merge and update; errors stay inline with Try again | Partial | `lib/toasts.test.tsx` "the same message pushed again is one toast with a count…", "at most three toasts show". Load failures are inline with Try again. Missing: a failed action is still an error toast with no Try again (`lib/act.ts`). |
| C26 | Waiting to go out exists, at least as a designed screen with an empty state | Done | `WaitingToGoOut.test.tsx`; `App.test.tsx` opens `#work/outgoing`. The diff review itself is not built (publisher, S1b). |
| C27 | Projects is a portfolio table; People a table with a detail pane; Stages a board | Partial | `Projects.test.tsx`, `People.test.tsx`, `StagesBoard.test.tsx`, `tests/test_stage_cards.py`; the board's browser test `panes.spec.ts` passed at `ec37749`. B-7 fixed the words broken beside the pane (`TablesBesidePane.test.tsx`). Missing: the browser check at 1440px (`tables.spec.ts`) is written, not run; only a browser shows a break inside a word. |
| C28 | Settings is nav \| form \| help, autosave plus undo, "Changed · Reset" only when changed | Done | `Settings.test.tsx` "there is no Save button: a text setting saves when the cursor leaves it… with Undo", "a changed setting says Changed with a Reset beside its label…". |
| C29 | Pickers for time zone, language, money, dates; no raw env vars, IANA ids, locale tags, `{placeholders}` | Partial | Language and date format are lists (`Settings.test.tsx`); the time zone is chosen by city with a search (`Settings.test.tsx`: "a time zone is picked by its city, with a search, and the setting still holds its id") and American/British spelling is named in words (B-7; `tests/test_setup_path_words.py` refuses an IANA id or a locale tag on the setup path). Setup's spending amounts are money fields with the currency symbol (`AiSpendLine.tsx`, `Walkthrough.test.tsx`: "Your AI account: spending is one sentence…"). Missing: there is no currency setting, so no money picker. |
| C30 | AI accounts with display names and status chips | Done | `AiAccounts.test.tsx` "every row says its role in words, its own name… its state in words, and shows no id". B-7: "Not measured yet" until a result exists (`AiCompare.test.tsx`). |
| C31 | Setup guide as a stepper, done steps collapsed, matching progress count | Done | `Walkthrough.test.tsx` (the look: "the list has no "Not done yet" on a row, marks done and skipped ones, and says which screen is open", "a screen not done yet has Continue as its one primary button…"); `SetupLine.test.tsx`. |
| C32 | `tokens.css` adopted; colour roles; brand colour from config with a contrast guard | Done | `StyleGuide.test.tsx`; `lib/theme.test.ts`; `Settings.test.tsx` "Appearance shows the measured contrast…". |
| C33 | Six type sizes, three weights, one UI family, tabular numbers | Done | Tokens define six sizes, three weights and one family. B-7 added the missing rule: `stylelint-rules.test.ts` (the rule `cockpit/weight-tokens` allows only the three weight tokens). |
| C34 | 4-point spacing, three radii; stylelint enforces scales, bans raw hex, uppercase and opacity-disabled | Done | `web/src/theme/stylelint-rules.test.ts`; `npm run build` runs `lint:css`. |
| C35 | One component each for Button, Pill, Row, Panel, SegmentedControl, EmptyState, LoadFailed, Skeleton, Drawer, StatusChip | Partial | All ten exist in `web/src/ui/` with tests; `StyleGuide.test.tsx`. Missing: old hand-made `.pill` and `.tabs` styles are still in `styles.css` and used in about ten components. |
| C36 | Line icons replace text glyphs; nav shows icon and label | Partial | `ui/Icon.test.tsx`; `Sidebar.test.tsx`. B-7 gave the warning icon its words (`Header.test.tsx`: "Missed one is a button with its words, not a bare warning icon"). Missing: text glyphs (checkmarks, crosses, arrows) remain in the source of about twenty components, among them the walkthrough, AI compare and AI accounts; the screen was not re-audited glyph by glyph. |
| C37 | Density setting; touch targets of 44px or more on coarse pointers | Partial | Density: `lib/theme.test.ts`; `Header.test.tsx` "the person's initials open the user menu, where theme and density are saved…". B-7: icon-only buttons at least 32×32 and any button at least 24×24 (`web/src/theme/targets.test.ts`). The 44px rule is in `tokens.css` under `pointer: coarse`. Missing: the browser check of every main screen (`a11y.spec.ts`, "has no visible interactive element under 24×24") is written, not run. |
| C38 | Theme toggle (System / Light / Dark) | Done | `Header.test.tsx`; `lib/theme.test.ts`; `shell.spec.ts` "the user menu's theme and density are kept for this device". |
| C39 | Control borders 3:1 or better; double focus ring; axe passes in light and dark at 390, 1024, 1440, 1920 | Partial | `tokens.css`: `--border-strong` 3.26:1 light, 3.9:1 dark; double ring. `shell.spec.ts` and `a11y.spec.ts` run axe in both themes at four widths and passed at `ec37749`; B-7 changed screens and the specs since. Missing: axe has not run over what B-7 changed; no automated check of the 3:1 border contrast. |
| C40 | Focus goes to the heading on view change; focus returns from drawers and dialogs | Done | `shell.spec.ts` "changing view moves focus to the new view's heading"; `App.test.tsx`; `ui/Drawer.test.tsx`. |
| C41 | Skeleton rows with `aria-busy` instead of "Loading…" | Partial | `ui/EmptyState.test.tsx` "skeleton rows mark their region busy…". Missing: "Loading…" text remains in nine components (`Welcome`, `NextSteps`, `WhatChanged`, `Ask`, `AddFile`, `Origin`, `DataForms`, `StageParts`, `Sources`). |
| C42 | Live updates invalidate by kind; new items wait behind "N new · Show" | Done | `lib/live.test.tsx`; `Today.test.tsx` "lines that arrive while the person is working in the queue wait behind 'N new · Show'"; `WhatChanged.test.tsx` "rows that arrive while the list shows others still wait behind N new". |
| C43 | Offline shows within 5 seconds; queued actions say so | Partial | `shell.spec.ts` "going offline shows in the status chip within five seconds, and coming back clears it". Missing: the browser does not queue actions while offline. |
| C44 | No `cockpit …`, `.yaml`, config paths or `env:` on the default path | Done | `wording/wording.test.ts`; `tests/test_screen_text.py`. B-7 (N5): the check reaches labels from config schemas, connectors and add-on manifests (`tests/test_setup_path_words.py`), and braces or quoted keys fail it too (`lib/raw-data.test.ts`). |
| C45 | The §3.17 wording table applied; one word each for Follow-ups, Needs you, outside content | Partial | The rows of the microcopy table that remained were applied in B-6b (`WhatChanged.test.tsx`, `ActionReview.test.tsx`, `HandIn.test.tsx`); B-7 uses one short "Outside" tag in the queue whose name is the full phrase "From outside · not instructions" (`TodayFirstScreen.test.tsx`: "a queue line made from outside content carries the short Outside tag, whose name is the full phrase"). Missing: nothing enforces one word for each idea; "Waiting for you" and "Needs you" both appear. |
| C46 | Design docs: 7.7 rewritten and prototype replaced; 7.12 and 7.13 added; other §6 items done | Done | `docs/design/07-ui.md` has 7.7, 7.12 Visual system, 7.13 Layout and 7.14 Items, records and forms, and B-7 edited 7.1, 7.6, 7.7, 7.9 and 7.14 as it built (each change is in `docs/design/CHANGES.md` sections 125 to 133). A documentation item, so no test applies. |
| C47 | Today at 1280×720 with setup unfinished: first queue line at most 260px, at least 6 lines visible (setup done: at most 200px) | Done | Re-review at `0f37be4`: 6 lines fit at 1280×720 (the tighter row padding was accepted). `today-capacity.spec.ts` ("Today at 1280x720 shows six lines in full…") and `shell.spec.ts` measure it. |
| C48 | A sweep test over every view and record kind finds no id, ISO date, raw enum or empty separator | Done | Re-review at `0f37be4`: no id on any measured view. `RecordSweep.test.tsx` sweeps every kind of record's page and the People, Projects, open to-dos and Unfiled lists; `shell.spec.ts` measures Today, its inspector and What changed. |
| C49 | With the detail pane open at 1440, no table header or cell breaks inside a word; rows have no filled Details button | Partial | `TablesBesidePane.test.tsx` (no break inside a word as the markup and styles it checks, columns by priority, pane overlaying the table when they don't fit, no Details button). Missing: the browser check at 1440px (`tables.spec.ts`) is written, not run. |
| C50 | Every person appears in the queue at most once per verb; the rail has no primary buttons | Done | `tests/test_follow_up_lines.py::test_each_person_is_in_the_queue_at_most_once_per_verb`; `TodayFirstScreen.test.tsx` ("Top priorities has no buttons: each entry is a link…", "no filled button is anywhere in the rail; the one button it adds is Add to agenda"). |
| C51 | The applier refuses reasoning in titles, statement-questions, and raw source titles in provenance | Done | Chosen differently for the first two (see below): lints `reasoning-in-title` and `question-is-statement` with severity `return` (`tests/test_item_text_lints.py`, `tests/test_evaluate_harness.py`); a title under three words falls back to the source's (`tests/test_item_titles.py`); provenance reads "from Jun Park's email, Oct 20", never the raw title (`tests/test_record_page.py`, `RecordPageRecords.test.tsx`). |
| C52 | No visible interactive element smaller than 24×24 | Done | Re-review at `0f37be4`: no target under 24px anywhere. `targets.test.ts` (see C37) and the browser check over every main screen (`a11y.spec.ts`). |
| C53 | The fixture shows a moved meeting, a held inference, an inferred fact, a series and a rules line | Done | `tests/test_demo_examples.py`: both fictional workspaces carry one of each, from a history made with the app's own code (the rules line reads the last 30 days of runs, so it shows until mid-November on the real clock). |
| C54 | No internal id in a title on Today, in an inspector heading or in What changed | Done | Re-review at `0f37be4`: Done. `tests/test_titles_without_ids.py`; `TodayRecords.test.tsx`, `WhatChanged.test.tsx`; `shell.spec.ts` ("no Today line, inspector heading or What changed title holds an internal id"). |
| C55 | A held line is asked as a question with two answers, and its details show only that decision | Done | Re-review at `0f37be4`: Partial (the line was right; the details pane showed the parent review's Looks good and "Closed a to-do", S2). **B-9 built S2:** `TodayOneDecision.test.tsx` ("a held line opens on only its decision…", "the answers in the details are the line's own answers…", "a held op the engine doesn't shape as a question opens as its own row…", "a held op's label on its change's card says what it would do…"), `wording.test.ts` ("every op that says what was done has a conditional twin…"). Done by those tests; the reviewer has not yet looked at it on screen. |
| C56 | Today's meta is one line | Done | Re-review at `0f37be4`: Done. `ui/Row.test.tsx`; `today-capacity.spec.ts`, `shell.spec.ts`. |
| C57 | No item appears on two Today lines | Done | New in the re-review at `0f37be4` (S1). **B-9 built it:** `tests/test_one_decision_one_line.py` ("a change holding only a held op has no review line and one decide line", "a review line leaves out the held op and says how many wait under decide", "no item is on two lines", "looks good never settles a held op"), `tests/test_source_intake.py`, `TodayOneDecision.test.tsx` ("the decision stays a question under Decide, and the review line beside it says it waits there"). The browser check on the demo ("one decision is one line…" in `today-capacity.spec.ts`) is written, not run. |
| N1 | A person who has never used a terminal installs and opens the app from a downloaded file | Not done | Phase I (roadmap I-1). `deploy/desktop` is a draft, not switched on. |
| N2 | On a fresh install, Gmail or Microsoft 365 connects with a sign-in, without an add-on screen, a restart or a server setting | Not done | Phase I (roadmap I-1). The owner decided the installer ships the mail and calendar add-ons installed and turned on (`docs/decisions.md`, 2026-10-20); nothing of it is in the code yet. Today the setup step installs and turns on an add-on with one button and one restart (`Walkthrough.test.tsx`, "a service that is not installed: one button installs it and turns it on, then one restart, then Sign in"). |
| N3 | With the default choices on the AI step, the assistant can work on the person's own mail and notes | Done | Chosen differently (F25, see below): with nothing chosen a new account reads open material only, and "Allow <account>, signed in as <identity>, to read your work mail and notes?" is one explicit yes (`tests/test_first_run_ai.py::test_a_new_account_reads_only_open_material_until_the_person_allows_more`; `WelcomeAi.test.tsx`). After that one yes the assistant can work on the person's own mail and notes. The re-review at `0f37be4` marked it Done as decided under F25. |
| N4 | The AI step has one recommended service, numbered steps that cover account, credit and key, a check on paste with specific error reasons, and one Continue | Done | `tests/test_first_run_ai.py` (one recommended service and one alternative, from data; the check on paste for every kind of work; a reason per account kind); `WelcomeAi.test.tsx` ("Recommended" on the first service only); `Walkthrough.test.tsx` (one Continue, "I'll do this later" beside it). |
| N5 | No string on the setup path contains an IANA id, a locale tag, `env:`, `file:/`, IMAP, port, TLS, token, CLI or "command"; a test enforces it | Done | `tests/test_setup_path_words.py` (wording sheet, schema labels, connector settings and add-on manifests; what must stay technical is marked `advanced`). |
| N6 | Backups offer the cloud-drive folders found on the computer, by name | Done | `tests/test_cloud_folders.py`; `Walkthrough.test.tsx` ("Backups: Back up now and continue saves the drive found and moves on"). |
| N7 | Today's first screen says what to do next for each setup state | Done | `Today.test.tsx` ("with no AI service an empty Today says to connect one, and its button goes on with setup", "with a service connected and nothing worked on yet, an empty Today says what to hand in", "Missed one appears only once the assistant has worked on something"). |
| N8 | Three people who match the persona each complete setup alone in under 20 minutes, watched | Not done | Needs the installer (N1) and the friends' preview; nothing of it has been run. |

## The five bugs the reviewer flagged

Still fixed after B-7; the re-review confirmed them on screen. What B-7 changed in them:

| Bug | Status | Evidence |
|---|---|---|
| Toasts covering the navigation | Fixed | From 1280px the stack is bottom left of the content area, right of the sidebar, 420px wide (`lib/toasts.module.css`). Maximum of 3, repeats merge into one with a count, F6 and Escape reach and dismiss them. Tests: `lib/toasts.test.tsx`; `acceptance.spec.ts` (toast starts right of the nav); `shell.spec.ts` "with three toasts showing, Tab never leaves a control under them". The Tab test runs on the style guide page, not on Today. |
| The empty details pane | Fixed | From 1680px the pane opens on the first line, follows the cursor, and says "Nothing needs you" plus what is next when empty (`Today.test.tsx`: "from 1680px the pane opens on the first line at once…", "with nothing that needs the person the pane says so…"). B-7: when no line is selected the inspector shows This week. |
| "Answer 1 decision" titles | Fixed | A line that holds one item is titled by the item (`tests/test_today_queue.py::test_a_line_that_holds_one_thing_carries_that_things_own_words_as_its_subject`; `Today.test.tsx` "a line that holds one item is titled by the item itself; a line that groups several keeps its count"). |
| Phone header overlap | Fixed | Under 640px the header holds only the logo, the status chip and the avatar (`Header.test.tsx` "on a phone only the logo, the status chip and the avatar are in the header…"). No browser test measures that the pieces do not overlap. |
| The cramped to-dos | Fixed | Each to-do in the rail has a checkbox to the left and the title takes the width (`TodayRail.test.tsx`: "marking a to-do done uses the action path and offers Undo"). No test measures the title's line count at 1440. |

**C1–C46: Done 24, Partial 22, Not done 0** (after B-7 it was Done 23, Partial 23; C19 became Done at the re-review at
`0f37be4`). C47–C53: Done 6 (C47, C48, C50, C51, C52, C53), Partial 1 (C49). **All 53: Done 30, Partial 23, Not done 0**
(before the re-review: Done 26, Partial 27). C54–C57: Done 4 (C54, C55, C56 and C57, the last two by B-9's builds).
N1–N8: Done 5 (N3 to N7), Partial 0, Not done 3 (N1, N2, N8).

What the re-review at `0f37be4` changed: C19, C47, C48 and C52 became Done (measured on screen); C14 stayed Partial for S4
and C55 was Partial for S2, and B-9 built both with tests (above). C49 stays Partial: its browser check (`tables.spec.ts`)
is written, not run.

What B-7 changed in the C1–C46 marks: C18 (record pages) became Done; C27 (tables) became Partial until the browser check
of the tables runs; C33 stayed Done with its missing rule now built; C1, C2, C9 and C19 are built further but Partial for
want of a browser measurement or a wider sweep. The re-review marked C9 and C19 Not done; its own count was Done 23,
Partial 21, Not done 2.

## Where the build chose differently from the review, and why

- **Top priorities stays, as context with no buttons** (B-7; decisions, 2026-10-20; the re-review's 3.4 and C50): each
  entry's words link to its queue line (which opens there without leaving Today) or, when the queue has none, to its
  record; the queue is the only place to act. The review offered dropping the panel or making it context; the owner's
  picture of the work version (promise P11) asked for it. So "Mark done", "Reassign" and "Hand to the assistant" on its rows
  are not built, and its second line "who suggested it" is not built either.
- **A lint that returns, never an applier refusal, for reasoning in titles and statement-questions** (B-7; C51): telling
  reasoning from content is fuzzy, and CLAUDE.md keeps fuzzy checks out of the invariants. `reasoning-in-title` and
  `question-is-statement` have severity `return`: one return to the model, then held for the person when the item reaches
  someone else, and a warning only when it stays internal. The two deterministic parts of C51 (a short title falling back
  to the source's, and the provenance label from the person and the kind of input) are built as the review asked.
- **The header is one row at every width** (B-7; the re-review's 3.7): below 1440px the assistant's state is a section of
  the status chip's popover, "Your pages" is the first group of the person's menu and the warning icon says "Missed one".
  This replaces the two rows from 1024 to 1279px (88px) the build had chosen before, so it is no longer a difference
  from the review; the browser check of it is written, not run.
- **The pane overlays a table when its columns don't fit** (B-7; the re-review's 3.3): beside the pane only the columns of
  highest priority stay (People: Name, Role, Organization, Open items; Projects: Name, Status, Target, Owner, Open
  items) and, when even those don't fit, the pane lays over the table. The review asked for the table not to be squeezed
  and left the means open.
- **The work-data question has nothing chosen** (B-7; F25, which overruled the main session's first decision): the
  first-run review's N3 asks that the default choices let the assistant work on the person's own mail and notes. The
  functional designer's answer is that a new AI account reads nothing of work until the person says yes for that
  account, once, with the account's sign-in identity shown. With nothing chosen the account reads open material only;
  "Allow" gives open and internal; the three levels sit under Advanced. N3's wording can't pass as written, by design.
- **"Blocked" is a kind of on hold**, not a separate state: a hold may name who or what it waits on (a person, a to-do or
  a question) and then reads "Blocked, waiting on …"; neither is due. From B-7 the chase moves to what holds it up (the
  blocker's question or action gets the chase clock and is the row in Top priorities), and a hold that waits on the person
  themselves is their own to-do (designer questions F15; `docs/project/designer-questions.md`).
- **Copy on a closed Follow-ups card opens the message first**, and the next press copies it, so nothing reaches the
  clipboard unseen (design 7.5). The label still reads "Copy 2", not "Review & copy" (not re-checked after B-7).
- **The cursor:** every dialog, drawer and form opens with it in the first field; a screen with no main field puts it on
  its heading; a page load itself takes no focus (kept on purpose, `App.test.tsx`).
- **Money has no picker yet:** there is no currency setting; setup's spending amounts are typed into money fields with the
  currency symbol in front.
- **List | detail for What changed and Follow-ups is not built:** their rows still open in place; the shared detail pane
  exists (Projects and People use it). Design 7.17 says so.
- **The phone's review mode is on What changed only;** the other lists get it as they become list | detail.
- **Notices go to the browser and a webhook;** mail to the person waits for mail sending (phase S1b), and the screen says
  so. Designer question F18.
- **A pasted picture in the hand-in drawer is not read yet:** it says so and keeps the box.
- **The sweep covers record pages and four lists, not every view** (C48): the other views are checked by spot checks.
- **S4 chose a short topic over a cut-off sentence, and no topic over both** (B-9; design 7.14, 6.15): the review
  asked for a topic of three to six words with the first sentence as a last resort. The prompt already asked for three to
  six words, so the fault was the fallback. Now a short topic gives way only to a first line that fits whole (at most
  eight words); with no whole line a short topic of two words or more stays; a single word ("Noted.") never does; and with
  nothing usable the topic is empty and the title is the kind and who it came from. This replaces B-7's rule that any topic under three
  words gave way to the first line cut at eight words. A bare one-word topic and a first line too long to show whole are the
  cases that now end at who they came from.
- **A held op leaves its change's review line only when it has a line under Decide** (B-9; S1): one asked of someone else
  (a question routed away) has no line for the person, so it stays counted in the review line as "waits for you", as before.
- **Where the held line's reason comes from** (B-9; S2): the stored reason, in the words of today's checks (`reason_of`),
  the same words the change's card uses, so a hold stored before the wording changed reads as one made now.
- **Work the app started is named by the wording sheet's kinds of task** (B-9; S4): the sheet names the core's kinds of
  work; a plugin's task kind reads as "the assistant's work" with its subject (a plugin's own label for a task kind is
  not on the title, which has no way to carry it).
- **The measurement of S3** (B-9): a one-off script (not the browser suite) opened the demo's own build, before (`faeeb11`)
  and after, at 1440px, and read the left edge of every Today line's words column. Before: 413 for every line except the
  Access line (343.8) and the Rules line (333). After: 413 for all twenty lines, the Access and Rules lines included.
