# Brief: the review before installers

**When:**
- after the core AI training work and the everyday steward work
- **before** the installer work (N1) starts

**Who asked:** the owner, 2026-10-21.

**What to review:** the whole product as a **personal and small-business tool**, used by a **normal person with no IT
background**. This is not a check of PM-office features. The question is whether someone can set this up for their own
life, and optionally their business, without help.

## The setup the owner wants

The first run should read as one simple story, in this order:

1. **Start:** "Here's what this is and what you'll need." That means a short list:
   - an AI account (with what it costs)
   - your mail and calendar (optional)
   - a place for backups
   - about 15 minutes
2. **What you need to do:** the steps ahead, with progress, each one skippable.
3. **Your personal side:**
   - **define the people in your life:** family, friends, the people you deal with (doctor, landlord, school,
     contractors)
   - and your personal areas: home, health, money, family events
4. **Optional: "Do you have a business you want to track?"** A clear yes or no.
   - **If yes, define the business:** its name, then its **programs, projects and people** (customers, suppliers,
     staff), and the business's own mail or calendar if it has separate ones.
   - **If no,** nothing about businesses, programs or projects appears anywhere until they choose to add one later in
     Settings.
5. **Done:** what was set up, what was skipped, and the first thing to do on Today.

## How to run the review

- **A fresh install, never the demo,** on the build current at the time.
- **Two walkthroughs, each by a persona with no IT background:**
  - **A: personal only.** Someone managing their household, family logistics and appointments. Says **no** to the
    business question.
  - **B: personal plus a small business.** A sole trader or a small shop owner with a few customers, a supplier and
    one helper, plus their personal life. Says **yes**, and sets up the business with one program and two projects.
- For each, **hand in a real-feeling personal email and a business email**, and see where each one lands.
- **Screenshots of every step** for the owner, in a gallery like the earlier rounds, with A and B side by side.

## What to check

| Area | Pass when |
|---|---|
| **The opening** | The first screen says what the app does for *you*, what you'll need, and about how long it takes, in plain words, with no PM jargon ("portfolio", "stakeholder", "RAID", "program" before the business question) |
| **The personal side** | Adding people is natural: name, how they relate to you ("my sister", "our dentist") and how to reach them. No organizations, teams, roles or "track only" on the personal path |
| **The business question** | Asked once, as a plain yes or no, with one line on what changes if you say yes. Easy to say "not now" and add later from Settings |
| **The business setup** | Business name, then its programs and projects and people, in that order. Each can be skipped or added in bulk (paste a list). The words fit a small business (customers, suppliers, jobs, orders), not only an office PM |
| **Keeping the two apart** | Personal and business items never mix by accident. Today, Follow-ups and the records show which side an item belongs to, and can filter by it. A personal email doesn't land in a business project, and the other way round. The assistant asks when it isn't sure which side something is |
| **Privacy** | Personal material (health, family, money) is clearly private. The AI-account permission says plainly what it will read on each side |
| **Today for a personal user** | With no business, Today still reads naturally: personal to-dos, appointments, replies owed. Nothing implies a work setting ("program", "stakeholder", "status page") |
| **Wording** | One plain word for each idea across both sides, checked against the wording verdict (`rereview-9e9c3f0/wording-verdict.md`) |
| **Earlier first-run checks** | N3–N7 still hold, and the N8 test with real people is planned with both personas |

## What to hand back

- **A review folder:** findings ranked, with a fix and a test for each, plus a gallery of both walkthroughs.
- **A short verdict for the owner:** could persona A and persona B each set it up alone, yes or no, and what stops them
  if not.
- **Proposed checklist items** for the personal and business setup (P1…), added to the master checklist.

## The plan as agreed, and what to check against it

The main session's plan is in its roadmap (I-0, pushed as `2961aa6`, `b2e9449` and `71f2722`):

- **The order:** Welcome → You (no workspace name) → AI account → Mail and calendar → Your promises (the first result) →
  the people in your life (optional, suggested from mail) → "Do you have a business you want to track?" (optional) →
  Backups → Done.
- **Everyone gets a Personal project by default.** Business-only users can ignore it.
- **The new steps follow the same UI rules as before:**
  - all wording from the wording sheet
  - the cursor in each step's first field
  - lists for known values
  - one main action per step
  - no sideways scrolling
  - WCAG 2.2 AA in light and dark
  - browser tests at every width

**My five adjustments,** sent to the main session on 2026-10-22. Check each one:

1. **The business yes or no, and the business name, are asked early,** in the first step, so the first-result step
   files business mail correctly. The details (projects, people, programs) come after the first result.
2. **No "project" wording for personal-only users.**
   - The sidebar shows "Personal" instead of "Projects".
   - With a business, it shows "Personal" plus the business name, and "projects" appears only inside the business.
   - Personal sub-areas (home, health, money, family) are optional and suggested, never a form.
3. **Small-business words in the business step:** the business name; "What do you work on?" (jobs, clients or projects,
   using the Client work template's words); and its people as customers, suppliers or staff. "Programs" is only an
   optional way to group projects.
4. **The people step asks how someone relates to you** ("my sister", "our dentist"): no organizations, teams or roles on
   the personal side. With mail skipped, offer "paste a list" or type names, never an empty form.
5. **The two sides stay apart from day one.**
   - Every item belongs to Personal or the business.
   - Today and Follow-ups have an "All / Personal / [business]" filter.
   - The assistant asks when it isn't sure which side something belongs to.

**Also check:**
- With mail skipped, "Your promises" becomes "Hand something in to see what it does".
- Welcome isn't counted as a step; progress starts at "You: 1 of 7".

## Added by the owner, 2026-10-23: the scope of the next review

The next time the main session asks for a review, it covers **everything**, not only the changes:

1. **Walk the whole product as a complete beginner.** Someone who has never used software like this, reads every word
   literally, and gives up when something doesn't make sense.
   - Start from install and first run, then every screen and every button a beginner would press, in the order they'd
     meet them.
   - The owner's concern: **the screens are badly done and don't flow.** So judge the flow, not only each screen:
     - Does each screen make the next step obvious?
     - Does anything dead-end?
     - Does the person ever have to go looking for where something is?
     - Does the same thing appear in two places, or with two names?
   - Write down every point where the beginner would stop, guess or give up. That list is the main output.
2. **Light mode (black on white): the owner says it looks bad.** Review light mode as its own design, not as the
   inverse of dark:
   - contrast and hierarchy
   - too many borders or boxes, and flat or washed-out areas
   - the accent colour against white
   - pills and tints
   - how dense the text is

   Propose concrete token changes with before-and-after screenshots.
3. **Every setting, especially "More settings".** For each setting, decide:
   - **keep** where it is
   - **move** it (to Advanced, to the screen where it's used, or into a guided step)
   - **automate** it (the app decides; there's no setting)
   - **remove** it (it shouldn't exist for any user)

   Send the main session a clear list of **what should not be there at all**, with a one-line reason each. Group it
   for a beginner: the settings someone actually needs should fit on one short page.

What to hand back, as before:
- a review folder with a screenshot gallery, for the owner to see
- ranked findings
- the settings list
- a short verdict in plain words
