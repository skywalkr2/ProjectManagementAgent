# Answers to designer questions 25–32

**These answer** `docs/project/designer-questions.md` at commit `11b186f`, on branch `claude/tender-tesla-16a8ob`.
**Mockups:**
- `mockup-round-25-32.html`: open it in a browser.
- `mockup-round-25-32/`: renders of each section, plus 27/28/31 in dark.

These use the tokens and patterns from `visual-spec.md`, so phase B can build them with the same components.

**One rule behind 28 and 31, worth adding to 7.6.** Whether a second choice gets a visible button depends on what it is:
- **An answer stays visible.** "Keep it open" is one of two answers to the line's question, so it is a button.
- **A postponement goes in the menu.** "Not now" answers nothing; it moves the line, so it goes in "•••".

So a held line may show two buttons: the primary answer and the other answer. Every other row keeps one.

---

## 25. AI accounts, as one place

**Answer: the default, with a summary line on top and the role said in words on every row.** See
`mockup-round-25-32/r-q25.png`.

**The section header:** "AI accounts · 3", then **Compare what they can do** (§26) and **Add an account** (primary).

**A summary line under the header** answers the question people actually have:
- "**Main account** does Quill's work → if it can't answer, **Second account** stands in."
- Under it, one quiet line: "Every kind of work has a backup", or "Harder work has no backup · [Add one]".
- Today, the person has to work this out by reading every row.

**How a row reads.** The anatomy matches every other list:
- **Role pill**, always in words:

  | Pill | Tone |
  |---|---|
  | **Does the work** | need (accent) |
  | **Backup** | neutral |
  | **Not used** | warn, only when something is wrong with it; otherwise neutral |

- **Name:** the person's own name for the account ("Main account"). The default is "{Service} account". Never the
  config id: today the demo shows "stub".
- **Meta line:** kind and service · what it covers ("Pay as you go · Example AI · everyday and harder work"). A backup
  says what it stands in for ("stands in for everyday work").
- **State line,** with a dot and words, the worst state winning:

  | State | Example |
  |---|---|
  | Ready | "Ready · answered 2 h ago · $1.20 today" |
  | Checked | "Checked for every kind of work · Oct 14" |
  | Missing key | "Key not found on this computer" |
  | Paused | "Paused until 2:20 PM (usage limit)" |
  | Check failed | "Check failed for harder work · [See why]" |
  | Key ending | "Key stops working on Nov 30" |

- **One next step,** decided by the state:

  | State | Button |
  |---|---|
  | No key | **Add its key** |
  | Untested | **Test** |
  | Check failed | **See why** |
  | Paused | none; the state line says until when |
  | Ready | **Test** (secondary) |

- **The menu holds everything else:**
  - Test
  - **Make this the main account** (with "Switch and check (about $x)")
  - **Use as backup** / **Stop using as backup**
  - Change models
  - Replace key
  - Key end date
  - Remove
- **Order:** the working account, then backups, then the rest. Broken ones go last within each group (as built).

**Where the backup choice sits:** in two places, the same words in each.
1. **In the add form,** as the question "What is it for?", with three choices, each explaining what will happen:

   | Choice | Explanation shown |
   |---|---|
   | Quill's work | "It becomes the main account. Main account becomes its backup." The current main account is kept as backup by default, so a switch never leaves the work with nothing |
   | A backup | "Stands in when Main account can't answer. Checked for each kind of work first (about $0.02)." |
   | Nothing yet | "Kept here to test or compare." |

   The button carries the cost: **Add and check (about $0.02)**.
2. **In the row's menu** ("Use as backup", "Make this the main account"), with the same check and the cost shown first.

Two more rules:
- **The add form opens in place,** as a drawer from the right (spec §4.4, forms). It does not go to the setup guide. The
  guide reuses the same form.
- **Removing.**
  - Removing the main account when a backup exists: act at once, with the toast "Removed Main account. Second account
    now does Quill's work. · Undo".
  - With no backup: the menu item says so before the click ("Remove · Quill will have no account for its work"). The
    toast says "Removed Main account. Quill has no account for its work. · Undo", and a held line appears on Today:
    "Quill has no AI account · [Add one]".

**Done when:**
- The summary line is right for every combination of main and backup accounts.
- Every row shows a role pill and a state line in words.
- No config id is visible.
- Add never leaves Settings.

## 26. "What it can do" per account

**Answer: both, at different depths.**
- **A grid across accounts** on its own page answers the question that matters: "for this kind of work, which account
  should I use?"
- **Each account row** keeps a one-line summary that links to the grid.
- **Pass rate first, then cost per right answer** among those that pass.

See `mockup-round-25-32/r-q26.png`.

**Why pass rate first:** a cheap answer that's wrong costs the person a correction, which is the most expensive thing in
the product. Cost only means something among accounts that clear `ai.skills.min_score`. So the grid answers in that
order:
1. Does it pass?
2. Of those that pass, which is cheapest?

**The grid** (Settings → AI accounts → **Compare what they can do**, full width):
- **Rows:** kinds of work (skills), in the order the person meets them. Plain names: "Pull actions from meeting notes",
  "Route a question to who decides", "Use a known term", "Write an update in your voice".
- **Columns:** account · model ("Main account · everyday", "Main account · harder"), with the main account first.
- **Each cell:**
  - **Pass rate,** large: "94%".
  - **Under it, small:** cost per right answer, runs, and age ("$0.03 · 18 runs · 2 days ago").
  - **Below the minimum:** "⚠ 56%" in danger colour, with "Below 80%". Words and icon, never colour alone.
  - **Old** (past the staleness setting): the age says "(old)" and the value counts as unknown.
  - **Not measured:** "— Not measured" with **Measure (about $0.12)**.
  - **The cheapest passing cell** in each row: an ok tint with "✓ Cheapest that passes", or "✓ Only one that passes".
    This is the cell step 2's routing will choose, so the person sees the choice before it is automatic.
- **Header:** what the numbers mean ("right answers · cost per right answer · minimum 80%") and **Measure again (about
  $x)** with the estimate first.
- **On each account row,** one line: "Good at 9 of 12 kinds of work · 1 below the minimum · 2 not measured · See all".
  The current disclosure becomes this line. It is shorter, and the detail lives in one place.

**Done when:** a person can say which account to use for each kind of work in one look, without reading numbers that
don't matter (the cost of failing models).

## 27. Questions the assistant asks after a move

**Answer: one group line under the move, expanded in place, with one row inside per thing to check.** See
`mockup-round-25-32/r-q27.png`.

**Why:** the person has one thing to think about (the meeting moved), and three separate rows would make them rebuild
that context three times. Grouping also keeps the queue's "one line per thing" rule honest: the *thing* is the move.

**The group line** goes in the Decide group:
- **Pill:** "Moved" (warn).
- **Title:** "Print sync moved to Thu, Oct 22 · 2 things to check". Use the meeting's own name and the new date. If the
  move was to an earlier date, say "moved earlier to …", because earlier moves are the risky ones.
- **Meta:** who or what moved it ("From Sam Rivera's calendar change", "From your edit") · and **what went to other
  people** ("1 question also went to Theo Brandt (in Follow-ups)").
- **Inside the group, one row each, each with its own buttons:**

  | Row | Buttons |
  |---|---|
  | "Should 'Send the interior file to the printer' move to Thu, Oct 22?" with the reason ("Yours · due Tue, Oct 20, the day before the old print sync") | **Move it to Oct 22** (primary) · **Keep Oct 20**. Both are answers, so both are visible (see the rule at the top) |
  | "Does the plan still hold?" with what was checked ("Proof approval (Nov 3) still comes after the new date · nothing else is tied to it") | **It holds** · **Needs a change…** (opens a note to Quill) |

- **The group line's menu:** "Open the meeting", "Undo the move's follow-on run".

**Edge cases:**
- **Questions addressed to other people** (an action's owner) are not the person's to answer. They live in
  **Follow-ups** under that person, with the context "after Print sync moved", and the group only counts them in its
  meta.
- **A group with one item** shows as a normal row, with the context in its meta ("because Print sync moved to
  Thursday").
- **When every row is settled,** the group clears with one undo toast.
- **Two moves of the same meeting before the person looks:** one group, showing the latest date. Earlier rows that no
  longer apply drop out. This is the same rule as "never let two versions race".

## 28. Held for a look

**Answer: yes. The reason comes first, the primary button says exactly what it does, and the other answer is visible
too, worded as specifically.** See `mockup-round-25-32/r-q27.png` (the two "Waiting for you" rows).

**Title: the action as a question,** with the item named in quotes. For example:
- "Close 'Send two spine options'?"
- "Change the due date to Nov 5?"
- "Give 'Book a photographer' to Sam Rivera?"
- "Send 'Which bio?' to Ines Duarte instead?"
- "Drop 'Agree the trim size with the printer'?"

**Meta: the reason first, then the evidence:**
- **For an inference:** "Quill inferred it's done from Theo Brandt's email: 'both spines are in the shared folder' · not
  said outright". Use the same quote style as "Because" lines. Where it came from opens the source.
- **For a drop of something that reached someone:** the consequence, in bold: "**Sam Rivera and Theo Brandt were told on
  Oct 10**, so Quill will draft a note to them."

**Buttons are verbs naming the result:**

| Hold | Primary | Other answer |
|---|---|---|
| Close | **Close it** | **Keep it open** |
| Date | **Change it to Nov 5** | **Keep Oct 30** |
| Owner | **Give it to Sam** | **Keep Maya** |
| Routing | **Send it to Ines** | **Keep it with Maya** |
| Drop (reached someone) | **Drop it and draft the note** | **Keep it** |

- Avoid generic "Do it / Leave it": they make the person re-read the title to know what they're agreeing to.
- **After either button:** an undo toast saying what happened ("Closed 'Send two spine options' · Undo"). The drafted
  note for a drop goes to Waiting to go out and is linked in the toast.

**Pill:** "Waiting for you" (warn), the same as other held items, so the person learns one signal.

## 29. Where a fact came from

**Answer: a source label in the meta line, which *is* the "Where it came from" link.** That is one control, not a label
next to a link. An inference adds a dashed-outline **"Inferred"** tag and the words. **No italics:** italics already mean
"a quote" in Because lines and in held lines, so italic facts would read as quotations. See
`mockup-round-25-32/r-q29.png`.

**Wording** (the label is the link text):

| Rests on | Label |
|---|---|
| The person | "from you, Oct 8" |
| Someone named, in their own words | "from Jun Park's email, Oct 9" or "from Jun Park, in the production check-in notes, Oct 8" |
| Someone named, reported by another | "said by Maya Lindqvist (Corner Lamp Books), in Ines Duarte's notes, Oct 11" |
| Inferred | [≈ Inferred] "Quill inferred this from Sam Rivera's note, Oct 12" · **Confirm it** |

**Placement and rules:**
- **The meta line,** after the fact's kind ("Date · from Jun Park's email, Oct 9"), on every fact row: record pages,
  Knowledge, the inspector.
- **Not in copied or published text.** Copyable text stays clean (7.6). Inferred facts never reach a shared output
  unconfirmed (8.1). The publisher's wording check already enforces "publish only confirmed facts".
- **Confirm it** on an inferred fact turns it into "from you, today", with Undo.
- **For a screen reader,** the tag reads "Inferred by Quill, not stated".
- **The tag style** (dashed `--border-strong` outline, `≈` icon, neutral text) is reserved for inferences. Add it to the
  Pill component as an `inferred` variant.

## 30. Meetings and series

**Answer: a plain series page in the core, plus the "for Thursday's print sync" label on item rows. Building and sending
the agenda stays in the project management pack,** which adds its buttons to this page. See
`mockup-round-25-32/r-q30.png`.

**Why the core needs the page:** items already roll from one meeting to the next in the core (L7). Without a page, a
rolled item moves somewhere the person can't see, and "where did it go?" is exactly the confusion the product exists to
prevent. Listing what's open for the next meeting is record display, not agenda building.

**The series page** follows the record page pattern (spec §4.4, activity | details):
- **Header:** the series title · "Every Thursday" (the person's words, labelled "in your words", since nothing works out
  dates from it) · the project · "•••".
- **Main column:**
  - **"Next: Thu, Oct 22, 10:00 · 3 open",** grouped by person (the person last, as "You"). Rows use the standard
    anatomy. Rolled items say so: "moved from Oct 15's print sync".
  - **Past meetings,** collapsed to one line each: "Thu, Oct 15 · 3 settled · 1 moved to Oct 22". Each opens that
    instance's settled and moved items.
- **Details column:** repeats, project, usually with, and the rolling rule in plain words ("Open items roll to the next
  meeting when one passes unsettled").

**Elsewhere:**
- An item tied to a series shows **"for Thursday's print sync"** in its meta, linking to the page. Within a week, use the
  weekday ("Thursday's"); further out, the date ("Oct 29's").
- On Today's Agenda rail, an instance shows its open count ("Print sync · 3 open"), linking to the page.

**What the pack adds later:** **Build the agenda** and **Copy agenda** in the header, the per-attendee agenda sections,
and the stored agenda (decisions 18). The core page is designed so the pack only adds buttons and a section, never
replaces the page.

## 31. The rules review's "Not now"

**Answer: yes, move it to the line's menu.** It puts the line off; it doesn't answer it (see the rule at the top). See
the open menu in `mockup-round-25-32/r-q27-dark.png`.

- **The line:** pill "Rules" (neutral) · "Look over 3 rules Quill never used" · meta "Sent with every run for 30 days,
  never applied · 1,840 of 4,000 characters" · primary **Look over**.
- **The menu:** **Not now**, with its consequence under it ("Back on Today on Thu, Oct 22"), then **Open Knowledge**.
- **The toast:** "Off Today until Thu, Oct 22 · Undo".
- Use the same pattern for every "later" on Today. One rule means the person learns it once.

## 32. Copy tables per person

**Answer: preview first, "Your update" last and widest, and two copy buttons named for where the table is going.** See
`mockup-round-25-32/r-q32.png`.

**Show the table before it is copied.** This follows the rule from the review (C20: nothing reaches the clipboard
unseen). The person's group in Follow-ups gets a **Message | Table** switch. Table shows exactly what will be copied.

**Columns:**
- **Actions:** Project · Action · Due · Link · **Your update**
- **Questions:** Project · Question · First asked · Link · **Your answer**

**Layout of the fill-in column:**
- **Last** and **widest** (about 35–40% in the preview and in the HTML copy).
- **Tinted** with the soft accent in the HTML copy, header included, so the reader sees where to write.
- **No placeholder text,** so the reader has nothing to delete before typing.
- **Last because:** in a spreadsheet, people tab to the end of a row to type, and the columns they read (what, when,
  link) sit to its left in reading order.

**Rows and cells:**
- **Order:** actions by due date, overdue first, undated last. Questions by first asked, oldest first, with "Not sent
  yet" last.
- **The project is repeated on every row.** No merged cells, so the table sorts and filters in a spreadsheet.
- **Due:** "Fri, Oct 23". Overdue says it in words: "Wed, Oct 14 · overdue". In HTML it is also in danger colour, never
  colour alone.
- **First asked:** "Oct 10", or "Not sent yet".
- **Link:**
  - **HTML:** the page's name as the link text ("Book page").
  - **Spreadsheet copy:** the full address, which spreadsheets turn into links. A link label would lose the address in
    tab-separated text.
  - **No link:** "—".
  - Only links the reader can open (the existing rule).

**Copy buttons,** named for the destination rather than the format:
- **Copy as table** (primary): HTML, for mail and chat.
- **Copy for a spreadsheet:** tab-separated.
- Under them, one hint line says which is which.
- **Mark sent** sits beside them, as in the message view (Copy, then Mark sent).

**No title row or instructions inside the copied table.** Copyable text stays clean. The person adds their own line in
the message.

**Later:** when the person hands a filled-in table back, the assistant reads "Your update" and "Your answer" by column.
That is worth a test case.

---

## One more thing, not asked

**The To do column on Today has regressed at 1440×900.** It is so narrow that titles wrap one word per line ("Approve /
the back- / cover / copy"), next to a full-size **Mark done** button and a "•••" (current build, `11b186f`). Phase B
replaces this board with the queue and rail, which fixes it. If phase B is more than a few days away, a quick fix is a
`min-width` on the column, or moving the To do actions into the row's menu.
