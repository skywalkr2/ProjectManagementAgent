# Go-forward plan to 1.0

Rewritten on 2026-10-12 after the review (`review-2026-10-12.md`), at the owner's direction.

**The goal:** Thimbleby (still called PM Cockpit in the code until phase I): a daily assistant for anyone juggling work,
which keeps track of what the person promised and what was promised to them, and gets the next step ready, with the
person approving everything outward. The path:
- **The first milestone:** the core complete, with full UI and code reviews approved, plus the installers (phases B, S and
  I).
- **The gate week** on the owner's personal mail is the first measured use of the core.
- **Real use by the owner** starts once the writing pack is complete (phase C).
- **Packs come after the core** (the writing pack, then the project management and publishing packs), and every pack is
  designed before plugin API 1.0, so the API holds the base any pack could need.
- **1.0 is published** once the owner finalizes scope.

**How the order was chosen:** each phase makes the next one testable by the owner. The plan holds one stream of work at
a time, and a phase ends when its exit test passes, not when its code is written.

Durations are estimates in working sessions. Dates are set when a phase starts and recorded here.

**This file holds only what is left.** What the roadmap finished, in the order it was done, is in
`roadmap-done.md`. Open items carry a batch tag in square brackets, such as `[S1-2]`; "The plan in batches" below
says what each batch covers, what passes at its end and how big it is. A batch is one meaningful piece of scope, with
one full test run and one push (CLAUDE.md, "Usage and machine load").

## Where things stand (2026-10-19)

- **Done** (all in `roadmap-done.md`): phase 0; phase A (2026-10-13); phase L-core's code, L0 to L7, apart from the
  owner's "after" run (O3, below); phase B's waves 1 to 4 and every defect the four outside reviews found, each with its
  test; and in phase S, S1's outage handling, coverage line, rule check before applying, unseen-close counting, quiet
  source intake and spending as a range.
- **In progress:** phase S1, batch S1-1 (the promises core). Built: promise records and ops, dates read by rules first,
  endings from an input held for the person's Keep. Left: see the batch.
- **The order** (decided; the batches below follow it): S1 (S1-1 to S1-3) → B's waves 5 and 6 (B-5, B-6a, B-6b) built to
  S's shape → the UI/UX designer's re-review and the feedback it brings (UI gate, B-7) → the gate week → the rest of S
  (S1b, S2 to S5) → I (installers; the first milestone ends here) → C (the writing pack) → P (the other packs) → D
  (sign-off) → L-more (beside real use, after the packs) and E (the rest of version 1, ordered by what protects real data
  first) → Publish 1.0 once the owner finalizes scope.
- **The first milestone** (owner, 2026-10-19): the core complete, with full UI and code reviews approved, and the
  installers (phases B, S and I). 1.0 is a moving target until the owner finalizes scope: every plugin pack is designed
  before plugin API 1.0, so the API holds the base any pack could need. There is no go/no-go date: the 2026-10-30 one was
  set aside on 2026-10-09 and 2026-10-12, and stays set aside.
- **When the owner uses it:** the owner tests it after phase B and starts real use once the writing pack is complete
  (owner, 2026-10-15; confirmed 2026-10-19). Phase S's gate week is the measured trial of the core on the owner's personal
  mail (R9 rules out work mail), before testers. The owner tries the app in the evenings as it goes.
- **Owner action pending:** one run of the learning tests (O3), at the end of batch S1-1, on the commit that batch
  pushes.
- **Open items:** 149, each in exactly one batch; 205 done items are in `roadmap-done.md`.
- **Plugin API:** 0.3.81 (see the table below).

## The plan in batches

One row per batch, in the order of work. A batch is one meaningful piece of scope: it ends on its exit test, with one
full test run and one push (CLAUDE.md, "Usage and machine load"). Every open item below carries its batch tag. Sizes are
rough (half a day to two days; the batches from phase C on are sized when they are reached). The phase sections below
keep each item's full text.

1. **S1-1 Promises core (built; the owner's learning run O3 is its last step)** (0 open items; size: about a day)
    - *Covers:* *Promises both ways* (phase S, S1; built so far: promise ops, rules-first dates, endings held for Keep, see that item's "Built so far"; left: prompts and playbook, the sent folder as a source, golden cases and harness pairs); *How a promise resolves* (S1; left: the line for a promise past its date with its choices); *Every promise shows why* (S1).
    - *Exit:* the twenty learning pairs run as harness pairs and pass; a fictional thread gives promises both ways with endings held for Keep; and the owner's one learning-test run (O3) on this batch's push.

2. **S1-2 What the person owes and misses** (4 open items; size: about two and a half days)
    - *Covers:* *Replies owed* (S1); *Reminders at a time* (moved here from S2, since the gate's first slice names reminders; S2 keeps a one-line pointer); *What changed since yesterday* (a new item in S1, from the designer's F2: the gate text names the line and no item stood for it); *"Missed one"* (S1).
    - *Also covers* (the designer's lessons, 2026-10-19): *A stance per person* (the field, its default and the gate on drafts and questions, design 6.34), and *A rejected ask is dropped, not reworded* (6.22), each with learning pairs.
    - *Also covers* (the designer's notes for later batches, 2026-10-19; design 6.35): *Learning from the sent version* (the style pair, moved here from L-more), *What a draft to someone else carries*, *A sender's distribution limit travels with the content*, and the extra endings of a reply owed (in *Replies owed*) and the assistant's own voice in *What changed since yesterday*.
    - *Exit:* a journey test for each; the stance gate holds a design question drafted to someone the person works alongside; a draft to someone outside a restricted message's group draws only on the open one; the style pair passes; the new learning pairs pass.

3. **S1-3 Ready for the gate week** (5 open items; size: about a day and a quarter)
    - *Covers:* *Sign-in sources taken in quietly* (S1, designer's F6: sources a sign-in adds use the quiet intake, and journeys J2 and J6 are rewritten for one total, one go and one "Look over what was found" line; a new item in S1); *A first success in five minutes* (S1); *The gate week's instruments* (S1).
    - *Also covers* (the designer's lessons, 2026-10-19): *Which sign-in an agent runs as* (design 6.16), so the gate week runs on a known account; and (the designer's notes for later batches) *Work the assistant releases on its own keeps the person's hours* (design 6.35).
    - *Exit:* the owner can start the two measured days; journeys J2 and J6 pass with one total, one go and one "Look over what was found" line.

4. **B-5 Sources and accounts** (3 open items, plus the numbered wave 5 entry; size: about one to two days)
    - *Covers:* *Wave 5* with P17 (.ics calendars, full featured) and P18 (several accounts of one service); the items that belong with it: *Passwords, keys and private addresses typed on the screen* (P16), *Add-ons install from the screen* (P15), *Mailbox and calendar passwords and addresses entered on screen* (all in phase B, built to S's shape).
    - *Exit:* the tests each item names pass; the owner adds an .ics link and file and a second account of one service, and types a password and a key on screen, with no file edit.

5. **B-6a The rest of B: records, Settings and forms** (18 open items, plus the numbered wave 6 entry; size: about one to two days)
    - *Covers:* from *Wave 6* (phase B): the designer's F12 and F13 and P26 (in the wave 6 entry), *Lists, not typing*, *The cursor starts where you type*, *Value-list values carry meaning*, *Follow-ups' Later*, *An action can be blocked*, *The obvious next steps on screen*; and the open items that fit this area: *A project's "what the assistant knows"*, *"Overlaps with …"*, *The Quality screen*, *Where a fact came from* (29), *A series page* (30), *A date move isn't news*, *Settings*, *Learning on screen*, *Action items and open questions, cleaned up*, *The app's own kit*, *Found by the phase A journeys*.
    - *Also covers* (the designer's lessons, 2026-10-19): *An unknown status stays unknown, and an add from a link says when nothing could read it* (design 6.19).
    - *Exit:* the tests each item names pass, and the browser test of every main screen at several widths shows no sideways scroll; the owner works through their own open items on a laptop and a phone.

6. **B-6b The rest of B: Today and the shell** (17 open items; size: about one to two days)
    - *Covers:* from *Wave 6* (phase B): *The Today rows as the mockup review set them*, *This week at every width*, *Notifications for "needs you" only*, *The walkthrough's look*, *An unnamed assistant reads as one*, *The header shows the assistant is alive*, *Words and accessibility throughout*; and the open items that fit this area: *After a move* (27), *Held for a look* (28), *Work*, *Setup guide*, *The rest* (Stages board, phone review mode, hand-in drawer, Ask as a side pane), *Review after the first Go*, *When something is due a follow-up*, *Top priorities, always current*, *Copy puts the formatted message and its plain text on the clipboard together*, *What the work version's screens show*.
    - *Exit:* phase B's exit test: the owner reviews every screen on a laptop and a phone; checklist items C1 to C46 are marked Done or explained, with screenshots; the journey tests run against the new screens.

7. **UI gate: the UI/UX designer's re-review** (1 open item; size: waits on the reviewer)
    - *Covers:* *The UI/UX designer's re-review* (phase B, last group): once B-6b is pushed, the main session messages the session titled "UI/UX design review" with the commit to review and the list of UI changes since its last review (`docs/design/CHANGES.md`); it builds and reviews the screens itself.
    - *Exit:* its feedback is received and recorded in one file in `docs/project/`.

8. **B-7 UI/UX feedback** (1 open item; size: set when the feedback arrives)
    - *Covers:* *Build the UI/UX designer's accepted feedback* (phase B, last group): what the owner accepts from that file, built before the gate week.
    - *Exit:* each accepted item has its test, and the owner sees the changed screens.

9. **Gate week (owner)** (no items; the gate is written out in phase S; size: two measured days, then the counted week)
    - *Covers:* the owner's personal mail, at least one closed-lid night and one network drop; the owner writes down each promise they notice before looking at the assistant's list; two days are measured first and the thresholds set from what was seen, then the counted week. The testers are held to the thresholds this week sets for missed out of present, silent closes and wrong endings: those numbers come from real use, and per-tester thresholds would move the bar to fit. Counts that depend on how much mail a person gets are reported, not gated. The "Missed one" trend from week one to week two is the one measure only the testers have.
    - *Frozen:* What is measured is frozen during the counted week: Today, the promise lines, the prompts and the model choices don't change. Fixes found during the week go into `docs/project/gate-week-fixes.md` (created when the week starts) and land after it. The one exception is anything that loses a promise or closes one wrongly: it is fixed at once, and the day is noted in the week's log so the measures before and after it can be told apart.
    - *Exit:* pass or not on the owner's thresholds for the measures in design 6.32. Nothing behind the gate starts before it.

10. **S1b-1 The publisher and the guards** (2 open items; size: about a day)
    - *Covers:* *The publisher, brought forward from phase C4*; *Nothing on its own* (both in phase S, S1b); and the named S1b tests of the approval guards (designer's F7, `docs/project/designer-answers-2026-10-19.md`): a closed lid or lost network mid-send is checked with the service before any retry, an approval does not survive a restart that changed the draft's inputs, and the rest of that answer's list.
    - *Exit:* those tests pass; every outward act shows its exact content and target, nothing runs without the person's yes on that exact act, and the status and ledger line are written.

11. **S1b-2 Mail and calendar acts** (4 open items; size: about a day, with the mail add-on's builder)
    - *Covers:* *Mail*; *Calendar*; *Plugin API for acting* (all in S1b).
    - *Exit:* journey tests with fake mail and calendar services pass: an approved reply, a move or label, an invitation answer; the owner sees each act's exact content, its status and Undo where the service allows.

12. **S2 Time and attention** (6 open items; size: about a day)
    - *Covers:* *Repeating to-dos*, *What changed in an invitation*, *The morning brief* (and the evening wrap-up), *The Monday briefing, in the app* (moved here from phase B; it is the weekly form of the brief), *A capacity check on the day's priorities*, *An attention budget* (phase S, S2, and the B item for the briefing).
    - *Exit:* the engine tests each item names pass; the owner sees a brief built from a fictional day's changes, risks and yeses, and a "more than today holds" line on an overfull fictional day.

13. **S3 People and meetings** (2 open items; size: about half a day)
    - *Covers:* *Meeting prep and after-meeting capture*; *People memory* (S3).
    - *Exit:* journey tests: a fictional meeting shows its prep and files its notes; a person's line shows before a meeting and when a promised follow-up has gone quiet.

14. **S4 What arrives, and where it may go** (3 open items; size: about a day)
    - *Covers:* *Dates in documents*; *Areas of life*; *Capture from anywhere* (S4).
    - *Exit:* a fictional booking and bill become dated facts with proposed reminders; each area says which account reads it and whether anything leaves the computer; a forwarded item arrives.

15. **S5 Manner and proof** (4 open items; size: about a day)
    - *Covers:* *Gentle suggestions with choices*; *Talking to Reginald*; *The core reads as a daily assistant*; *The outcome, measured* (S5).
    - *Exit:* phase S's exit test: the Quality screen shows the outcome measures from the owner's measured week.

16. **I-1 Installers, name and icons** (15 open items; size: about two sessions, the old estimate for all of phase I)
    - *Covers:* every installer item of phase I: the CI build from a tag, install places, app-data places, opening the app, add-ons beside the app, updates, signing, *A name and icons*, *Nothing made-up ships*, *How it is built*, *Add-ons in an installed app*, the system vault, the *Exit test*; and *A launcher for people who never open a terminal* (phase B, moved here).
    - *Exit:* phase I's exit test on a clean Mac and a clean Windows machine: download, install, open, finish the walkthrough to the first result, quit, reopen with the data still there, update, uninstall with the data kept.

17. **I-2 The tester milestone and the website** (4 open items; size: about half a day, then the owner's decisions)
    - *Covers:* open promise P24: *the content brief for the website's session* and *keeping the website in step with releases* (phase I, "The website"); the tester invitation items: *the release build fills in its catalog and feedback addresses*, *Mail and calendar sign-in approval for testers and launch*; and the tester milestone paragraph at the top of phase I.
    - *Exit:* the first content brief is sent; a small invited group can install and connect mail, and the website says what to expect.

18. **Tester weeks (testers)** (no items; size: two calendar weeks)
    - *Covers:* the invited group uses the app on personal mail (or work mail with the employer's OK, risk R14) for two weeks, each tester bringing back what was missed through "Missed one". The testers are held to the thresholds the gate week set for missed out of present, silent closes and wrong endings; counts that depend on how much mail a person gets are reported, not gated.
    - *Exit:* the testers' "Missed one" counts fall from week one to week two, and the inherited thresholds hold.

19. **C0 The capability matrix, step 2 (refined when reached)** (4 open items; size: about 1.5 sessions, as C0 states)
    - *Covers:* the four items of C0 (phase C)
    - *Exit:* phase C's exit test, for the part C0 serves: work goes to the cheapest model whose measured scores hold.

20. **C1 The writing pack, installed and reviewed (refined when reached)** (6 open items; size: set when reached)
    - *Covers:* the items of C1 (phase C)
    - *Exit:* the pack installs from Add-ons with its libraries, and the owner's walkthrough on a fictional book is done.

21. **C4 What the packs need from the core (refined when reached)** (11 open items; size: set when reached)
    - *Covers:* the items of C4 (phase C): the file channel, shared-file writing, fact lookups, and the builders' question rounds
    - *Exit:* phase C's exit test: the writing pack takes a fictional manuscript from import to a built PDF and EPUB the owner approves, and a correction in the pack's own work teaches.

22. **C2 The project management pack (refined when reached)** (3 open items; size: set when reached)
    - *Covers:* the items of C2 (phase P)
    - *Exit:* phase P's exit test, for the plan, the schedule and what is late or at risk.

23. **C3 The publishing pack (refined when reached)** (4 open items; size: set when reached)
    - *Covers:* the items of C3 (phase P); C3b, the sales support pack, has no items and waits on its user's requirements
    - *Exit:* phase P's exit test, for the launch plan, listing sheet and prices and the hand-offs between packs.

24. **C3c Business analysis and systems architect packs (refined when reached)** (4 open items; size: set when reached)
    - *Covers:* the items of C3c (phase P)
    - *Exit:* each pack drafts what its role writes, works alone, and hands off through versioned interfaces.

25. **L-more The rest of learning (refined when reached)** (12 open items; size: about 4 sessions, as the phase states)
    - *Covers:* the items of phase L-more
    - *Exit:* each item's own test; it runs beside real use after the packs.

26. **D Owner validation and real use (refined when reached)** (4 open items; size: set when reached)
    - *Covers:* the items of phase D
    - *Exit:* phase D's exit test, which is the owner's own judgment on dates the owner sets.

27. **E The rest of version 1 (refined when reached)** (9 open items; size: set when reached)
    - *Covers:* the items of phase E
    - *Exit:* each item's named test, in the order phase E gives (what protects real data first).

28. **Publish 1.0** (3 open items; size: set when reached)
    - *Covers:* the three release mechanics of the section "Publish 1.0"
    - *Exit:* the private workspace's self-check passes, the fresh repository exists, and the README and docs match what 1.0 does.

## Owner actions on the critical path

Things only the owner can do, usually because they need the owner's own computer or accounts. Each says exactly what it
blocks; everything else goes ahead without it.

| # | Action | Needs | Blocks | Does not block |
|---|---|---|---|---|
| O1 | **Done 2026-10-14** (`docs/project/evals/2026-10-14-before-agent.json`: 42 of 42 passed on the owner's one account, a command-line agent). **The "before" run of the golden set** on real models: today's 14 cases × 3 runs, on a low-cost and a stronger account, with today's scoring. Steps below. | The owner's computer, with their AI accounts | Only L4's last step: the "after" report and its comparison with this one. That report also has to exist before real use starts. | All of phase A, and L-core's code, including the harder set itself. The run is pinned to commit `802538e`, so changing the cases, the scoring or the packet afterwards doesn't spoil it. |
| O2 | **Done 2026-10-14** (`docs/project/evals/2026-10-14-before-harder-agent.json`: 30 of 48 as scored at `feb6b3f`, 48 of 48 once six cases were corrected; every failure was an extra op the case hadn't allowed). **The harder set's "before" run** (the original designer's L1 check-in, 2026-10-14): the harder set (below, "L1b") on the owner's account, 3 runs per case, pinned to the commit that adds it, which is the last commit before any L2 code. The report records the agent's program version, and says plainly when every tier ran on the same account, so the run says nothing about a low-cost tier against a stronger one. Steps below, once the set lands. | The owner's computer, with their AI accounts | L4's comparison, which rests on this set. | L2's build: the run is pinned, so it can be made any time; L2 code only lands after the pinned commit. |
| O3 | **One run of the learning tests, at the end of batch S1-1:** the golden set, the harder set, the existing learning pairs and the twenty promise pairs, on the owner's account, 3 runs per case, on the commit that S1-1 pushes. Compared case by case with O1 and O2. It costs the owner's AI allowance once, and it gives the gate week a clean "before". Steps below. | The owner's computer, with the account used for O1 and O2 | The gate week's start, and real use: the comparison has to exist before either starts. | Phase B, which goes ahead meanwhile. |


**O3 steps** (on the commit that batch S1-1 pushes; the message that asks for the run names it). Earlier attempts at the
"after" run, and the fixes they led to, are in `roadmap-done.md` and `decisions.md` (2026-10-15). In the owner's copy of
the repository, on their own computer, on the workspace and account used for O2:
```
git fetch origin claude/tender-tesla-16a8ob
git worktree add ../cockpit-after FETCH_HEAD
cd ../cockpit-after
uv sync
uv run cockpit ai test -w ~/cockpit-exit
uv run cockpit evaluate --from workspaces/demo-b -w ~/cockpit-exit --account "<the account used for O2>" --runs 3 --json > ~/after.json
uv run cockpit evaluate --from workspaces/demo-a -w ~/cockpit-exit --account "<the account used for O2>" --runs 3 --json > ~/after-harder.json
uv run cockpit evaluate --pairs --from workspaces/demo-b -w ~/cockpit-exit --account "<the account used for O2>" --runs 3 --json > ~/after-pairs.json
uv run cockpit evaluate --pairs --from workspaces/demo-a -w ~/cockpit-exit --account "<the account used for O2>" --runs 3 --json > ~/after-pairs-harder.json
```
- **Check the commit:** `git log -1 --format=%h` in `../cockpit-after` must show the commit the message names.
- **First:** `ai test` should end with every tier able to run, on its main account or a backup that stands in; stop
  there if a tier can't run. Paste the lines exactly as written: a
  `<…>` placeholder or a trailing `# note` breaks the whole paste in zsh.
- **Cost:** about 430 small runs in all on the one account before the promise pairs: 81 and 60 for the two sets (27 and
  20 cases × 3), and about 280 for the pairs (30 pairs and the day-30 scenario, each about three calls, × 3); the twenty
  promise pairs add about 180. On a subscription agent it is
  usage, and a long run may pause at the plan's limit and carry on. Run the commands one at a time if you'd rather see
  each report first.
- **What it shows:** each report ends with a pass rate per case and an overall line. The first two cover O1's and O2's
  cases plus the ones added since (those have no "before" number). A pair passes only when the later input comes out
  right with the correction not repeated, and a negative pair passes only when its later input is unchanged. A pair
  that fails names what the later run was given, so a gap in learning shows which knowledge didn't reach it.
- **Saving the report:** `--out <file>` saves the report after every case, so a run that stops part way leaves what it
  finished. If the main account's allowance runs out, the pair commands run on the backup account, and the report names it.
- **Keep the computer awake:** start each command with `caffeinate -i` on a Mac. A run frozen by sleep can take many
  minutes to recover, since each call waits up to 90 seconds before giving up.
- **Then:** send the four files (in your home folder) to the session. It checks them for account names or addresses, writes the comparison
  with O1 and O2 in `docs/project/evals/`, and turns any failing pair into a fix with its test before the gate week starts.
  After that, `git worktree remove ../cockpit-after`.

## The plugin API's road to 1.0

The pack builders plan against this table (owner, 2026-10-13). The contract stays `docs/plugin-guide.md`, generated from
the code; each version's changes are in `docs/plugin-api-0.x.md`; builders hear of each change in the weekly round.
Within 0.3 every change is additive: a pack built for an earlier 0.3 version keeps working, and manifests keep
`plugin_api: '>=0.3,<0.4'`. A minor version (0.4) may break, and is announced a round ahead with what to change.

| When (phase) | What the plugin API gains | Version | Breaks anything? |
|---|---|---|---|
| B | Nothing planned: panels, Today lines and jobs keep their contract through the redesign | none | No |
| C1, then P (C2, C3) | What the packs' builders ask for, answered in the weekly round (round 39: a conversation on a record, context-sized task kinds, data-form previews, a pack's value on a request, computed-column headings); interfaces between packs (such as `pm/schedule@1`) belong to the packs | 0.3.x | No |
| C4 | The publisher and the file channel for a pack's outputs, fact lookups from configured sources, and a kind of author for edits made outside the app in a shared folder. Whether a pack's "send" changes shape is decided here; if it does, this is 0.4 | 0.3.x or 0.4 | Only if 0.4, announced a round ahead |
| D | Frozen: no new names, only fixes, anything deprecated removed | 0.9 | Removals only, listed a round ahead |
| Publish 1.0 | 1.0 once the writing pack and the project management pack run on it unchanged through phase D's week of real use | 1.0 | No |

At the estimates below, the packs can count on: the L-core additions in about 9 sessions, a stable contract for the
redesign (4 sessions), the publisher and fact lookups at the end of phase C (about 9 sessions more), and the freeze at
the start of phase D. Dates are recorded here as each phase starts.

## Phase B: finish the UI/UX redesign

The note box on action buttons, the header's "alive" line, on hold isn't due, the follow-up rule and the "where it came
from" link are built for real use at the end of L-core ("Ready for real use"); phase B gives them their final layout.

The design is in Part 7 (7.7, 7.12–7.14); the foundation and shell are built.

**Where phase B stands (2026-10-19).** Waves 1 to 4 are built, and so is every defect the outside reviews found
(roadmap-done.md, "Phase B"). Left: waves 5 and 6, built to phase S's shape after S1, then the UI/UX designer's
re-review and the feedback it brings (batches B-5, B-6a, B-6b, UI gate and B-7). The owner holds feedback until
phase B is done and then tests it all at once ("im going to wait on any other feedback until we get all the updates
done"); the message then gives the update commands and a walkthrough.

From the three outside reviews of 2026-10-18 (`docs/project/incoming/reviews-2026-10-18/`); their defects are fixed
(roadmap-done.md), and this one is for the owner to decide:

3. **Plan changes proposed, for the owner to decide** (product review): the tester cohort as a roadmap milestone with
   exit numbers; a real-mail acceptance gate at S1 (the owner's mailbox, one week, the promise workflow whole, a
   miss and false-alarm rate the owner accepts); numbers for "dependable" before S's later waves; later steward
   capabilities held behind a dependable promise workflow; the risks register rewritten for the steward product;
   a policy for older mail at first run; a named S1b test of the approval guards against hostile input; the
   walkthrough reworked for the new audience; Today judged by the next action being obvious; a visible coverage
   line (what was read, when, and what wasn't) so "nothing needs you" never looks like "couldn't check"; a cheap way
   to add a missed promise, with omissions measured.

**Owner decisions waiting (from the reviews):** the product review's plan changes above; numeric dependability
thresholds set before the acceptance run, measured with denominators and a held-out set, omissions found by an
independent reading of a consented sample; publisher acceptance tests (stale approvals, duplicates after a retry,
uncertain remote results, revoked sign-ins, hostile content redirecting an act); whether the mail and calendar
add-on ships inside the installers (an extension plus packaging: provider code stays in the add-on, connecting stays
optional, the core stays testable without it); and the owner's target of sharing installers with a small invited
group on 2026-10-20, which the plan's order (B, S, then I) and the integrity items above don't yet support.

**The waves left** (waves 1 to 4 are in roadmap-done.md):

3. [B-5] **Wave 5, sources and accounts:** open promise P17 (.ics calendars, full featured: a pasted link, a file on disk,
   invitations as calendar entries, repeating events expanded, Outlook time zones, attendees) and P18 (several accounts
   of one service at once, each source picking its account; a plugin API change told to the mail add-on's builder).
   P16's leftovers too: an add-on's own secrets and the backup key typed on the screen.
4. [B-6a, B-6b] **Wave 6, the rest:** (also the designer's F12 and F13, 2026-10-19: a refused form refreshes the untouched fields and
   lists what changed underneath; kept secrets nothing refers to are removed after 30 days or with their source, never
   while an Undo points at one; and open promise P26: a to-do tied to the question it waits on, the nudge's
   answered-and-left-out list, the suggested escalation after a second follow-up) Top priorities, the Stages board, the phone review mode, the hand-in drawer, Ask as a side pane,
   the Quality screen, a project's "what the assistant knows", the work screens as list and detail, blocked actions, Copy
   with formatting, the action and question clean-up, lists not typing everywhere, the cursor in the first field, and
   checklist C1–C46 with screenshots. (The Monday briefing moved to phase S1; the launcher moved to phase I.)

Waiting on the owner: whether a Follow-ups table's action links should go to the project's pages (built that way in wave 2);
signing for the installers (phase I).

**Exit test:** the owner reviews every screen on a laptop and a phone. Checklist items C1–C46 of
`reviews/ui-ux-2026-10/` are marked Done or explained, with screenshots in `reviews/ui-ux-2026-10/after/`.

From L3 (design 7.18):
- [ ] [B-6a] **An unknown status stays unknown** (the designer's lessons, 2026-10-19; design 6.19): `project.add` refuses a
  status with no words behind it, as `record.set` does; an add from a link says "not read" when nothing set up can open
  the link. Reading the link's system of record is C4's fact lookups.
- [ ] [B-6a] A project's "what the assistant knows" section on its page: sources and the last input, facts with source and date,
  glossary terms used there (confirmed, assumed, unknown), who answers what, and what is still unknown with its question.
- [ ] [B-6a] "Overlaps with …" on the Learned line, linking the entry a proposal would merge with.
- [ ] [B-6a] The Quality screen (6.20): the knowledge-used and repeat-correction rates and the weekly missing-op list, from
  `GET /api/quality` (built in L3).

From the UI designer's answers to questions 25 to 32 (2026-10-16; `reviews/ui-ux-2026-10/answers-25-32.md`, mockups in
`reviews/ui-ux-2026-10/mockup-round-25-32/`; each answer has its layout, exact wording, edge cases and the test for done):
- [ ] [B-6b] **27 After a move**: one group line per move in Decide, one row inside per thing to check; questions to others go to
  Follow-ups and are counted in the group's meta; a group of one is a normal row; a second move replaces the group.
  *Built (wave 4):* the group line and its rows, `tests/test_move_groups.py`. Left: the per-row answers ("Move it to Oct 22 / Keep Oct 20", "It holds / Needs a change…") and the toast when the last row is settled.
- [ ] [B-6b] **28 Held for a look**: the action as a question, reason and evidence first, the primary button names the result,
  the other answer a visible button.
  *Built (wave 4):* `tests/test_held_ask.py`, `TodayRecords.test.tsx`. Left: "Drop it and draft the note", which waits for the publisher (S1b).
- [ ] [B-6a] **29 Where a fact came from**: the source label in the meta line as the "Where it came from" link; "≈ Inferred" in a
  dashed outline with Confirm it; no italics; never in copied or published text.
  *Built (wave 4) on the fact's record page:* `RecordPageRecords.test.tsx`, `tests/test_record_page.py`. Left: the label on Knowledge and in the inspector.
- [ ] [B-6a] **30 A series page**: next meeting's open items by person, past meetings collapsed, details; item rows link "for
  Thursday's print sync"; the agenda stays the project management pack's.
  *Built (wave 4):* `tests/test_series_page.py`, `SeriesPage.test.tsx`. Left: "usually with", which needs a meeting's attendees (P17).

From the original designer's lessons of 2026-10-14:
- [ ] [B-6b] **The Today rows as the mockup review set them** (the original designer, 2026-10-14, design 7.6 and 7.7): a project
  tag before a row's title when the screen mixes projects, left out when it holds one; toasts at the bottom left from
  1280px, never over a row's controls, with room left under the last row; "Change this" on each item of a review card; a card titled by what it holds ("3 things the
  assistant did"); Followed up and They finished it in an overdue follow-up's menu; a to-do says what it waits on, linked
  to the question it depends on; the heading's count and the menu's count agree, folded lines not counted; a line that
  offers another account names it.
  *Built (B wave 1):* the project tag, on the lines that carry a project (decisions, questions and owner questions), only
  while the queue names more than one (`web/src/components/Today.test.tsx`: "a row names its project only when the screen
  holds more than one", "with one project on screen the tag is left out"); toasts at the bottom left over the navigation
  column from 1280px, and room under the last row (`web/e2e/shell.spec.ts`: "the style guide has every shared component in
  every state"; `web/e2e/acceptance.spec.ts`, scenario 4, Mark sent); "Change this" on each applied item of a review card
  (`web/src/components/WhatChanged.test.tsx`: "each item in a review card has its own Change this, which sends back that
  item and no other"); a card titled by what it holds (`Today.test.tsx`: "a review card is titled by what it holds"); the
  heading's count and the menu's count are one number (`Today.test.tsx`: "the heading says how many lines need the person,
  and the same number is the menu's"; `web/src/shell/Sidebar.test.tsx`: "counts show where they help and an empty count
  shows nothing"); a line that offers another account names it (`HeldLines.test.tsx`, the borrow line, built earlier).
  *Left:* the project tag on review and send lines (the engine's queue line carries no project for them: it needs the
  request's or the person's project on `QueueLineView`); Followed up and They finished it are in a follow-up's menu
  already, but "Draft a nudge" as the primary has no engine behind it (no nudge message is written yet), so a nudge line's
  primary opens the waiting items; a to-do that waits on something says what (the hold's own words) but is not linked to
  the question it depends on, because no record ties an action to a question (a design and ops question for the main
  session).
- [ ] [B-6a] **A date move isn't news** (lesson 5): the history shown to readers (a record's activity, a published page) leaves
  out changes that only move a date on an existing item (same text, new date); new, closed and blocked items, status,
  scope, risks and decisions stay. The ledger keeps everything. The core provides this reader filter; a pack's published
  status page uses it (C2, C4).

- [ ] [B-6b] **Work:** What changed and Follow-ups as list | detail, with a "to send" marker on each action row (from L0).
  Sources shows on a source's row when its mail couldn't be sorted and why (from L0). Waiting to go out is a designed screen with its empty
  state.
- [ ] [B-6a] **Settings:** nav | form | help, save bar or autosave with Undo, "Changed · Reset", and pickers for time zone,
  language, money and dates. Appearance has the contrast warning; admin sections sit inside Settings.
  *Built (wave 3):* nav, saved as made with Undo, "Changed · Reset", help beside the field, `Settings.test.tsx`, `shell.spec.ts`. Left: the contrast warning in Appearance and the pickers for money and dates, to check and finish in wave 6.
- [ ] [B-6b] **Setup guide** as steps | step.
- [ ] [B-6b] **The header shows the assistant is alive** (the original designer's lessons from running, 2026-10-13): one short line, always ("The assistant ✓ last run 9:42", the
  account's own label, never a model's name), with today's runs per account, what's queued and the fallback order in its
  tooltip; amber or red when something is wrong. The held-work and paused lines cover the bad case; this covers "is it
  alive?". The header is two rows when it needs them (title, views and primary buttons on top; status and the person's
  links small below), tested at about 1,000 px wide. (The line and the two-row header below 1280px are built under "Ready
  for real use"; what is left here is the final layout and a browser check of the header at about 1,000 px wide.)
- [ ] [B-6b] **The rest:** the Stages board, the phone review mode, the hand-in drawer, Ask as a side pane on wide screens.
- [ ] [B-6a] **Learning on screen** (7.18): what the assistant knows and what is still unknown, on each project's page; the
  Knowledge screen under Records; each entry's use ("Used 12 times · last 2 days ago"). Built: the Knowledge screen and
  each row's use (`web/src/components/Knowledge.test.tsx`, `tests/test_knowledge_screen.py::test_the_knowledge_list_carries_how_much_each_entry_was_used`).
  Left: the per-project section.
- [ ] [B-6b] **Review after the first Go** (found by journey J2): What changed shows "5 new · Show" with Needs attention
  empty while Needs you counts 5, and only one review opens by default, so an owner question can sit closed. The
  Today redesign makes the first results one clear list. After Remove, the add-on's row vanishes along with its note.
- [ ] [B-6a] **The cursor starts where you type** (owner, 2026-10-12; design 7.0): every screen, step, form and dialog opens
  with the cursor in its first main field. The walkthrough does already (`Walkthrough.test.tsx`); the redesign applies
  it everywhere, with a browser check per screen.
- [ ] [I-1] **A launcher for people who never open a terminal** (owner, 2026-10-13): moved to phase I, where the macOS and
  Windows installers give the app icon and Start menu entry.
- [ ] [B-6a] **Lists, not typing** (owner, 2026-10-12: "nearly everything should have dropdowns"): every field on every screen
  whose values are known is a list to pick from. Audit each free-text field and convert it, with a test per screen. The
  time zone is done (`test_the_time_zone_setting_is_a_list_of_known_time_zones`; the Settings screen and the
  walkthrough). Settings name their lists with `choices`. *Also done:* the language (owner, 2026-10-16: "the language
  setting should be a dropdown"): Settings and a project's own language are lists of language tags shown by name, and a
  value set outside a named list is added to it, so no list shows a wrong value
  (`tests/test_setup.py::test_the_language_setting_is_a_list_of_language_tags_that_names_its_list`,
  `tests/test_setup.py::test_a_choice_list_includes_the_current_value_when_it_is_not_one_of_the_list`,
  `web/src/lib/languages.test.ts`, `web/src/components/Settings.test.tsx` (a setting that picks a language),
  `web/src/components/Setup.test.tsx` (the project form's Language list: empty is "Same as …", picking saves the tag)).
- [ ] [B-5] **Passwords, keys and private addresses typed on the screen** (P16; owner, 2026-10-16: "in imap setup we need to be
  able to take a password and not require the user to have set it somewhere else"). *Built:* a setting that holds a
  secret reference is marked `secret`; a source's add and change routes take pasted values apart from the settings and a
  local app keeps each in the private keys folder (0700, the file 0600), writing only its `file:` reference; a hosted app
  refuses; the value never reaches `watch.yaml`, the ledger or an answer; a source's form shows a password box, "Where it
  is kept instead", "Kept on this computer" with Replace and "Read from …"
  (`tests/test_typed_secrets.py`, `web/src/components/Sources.test.tsx` (a secret setting typed on the screen)).
  *Left:* typing an add-on's own secrets (`workspace.plugins.secrets`) and the backup key (`storage.backups.encrypt`),
  which are still reference boxes in Settings.
- [ ] [B-5] **Add-ons install from the screen** (P15; owner, 2026-10-16: "they still require manual command line installs
  instead of through the screen. the screen lists zero available plugins"). *Built:* with no catalog listed Add-ons
  offers an address field (the cursor in it) that saves into `workspace.plugins.catalog.feeds` and reads it at once; the
  catalog list adds another and takes away one the person added; an install refused for want of a read token asks for it
  in place (typed and kept as in P16 on a local app, a reference on a hosted one), then Install can be pressed again;
  the plugin guide's "Publishing a pack" says to attach the built wheel to the tagged release and give its address and
  SHA-256 in `release` (`tests/test_catalog_screen.py`, `web/src/components/Addons.test.tsx` (adding a catalog from the
  screen, a read token for a private release)). *Left:* telling the mail add-on's builder to attach its wheel and give
  `release` in its next release (the main session), and an install tried against a real private release host by the
  owner.
- [ ] [B-6a] **Action items and open questions, cleaned up end to end** (owner, 2026-10-13: "the whole action items / open
  issues needs a lot of work"). Starts from L0's audit of design 6.8 to 6.11 against the code, so the list of what is
  wrong comes from the code, not memory. Then one place for each: every open action with its owner, due date, project
  and where it came from; every open question with who it's waiting on and since when. Filter by project, person and
  state; edit, close and reassign from the row, with Undo; duplicates offered for merging; anything stale or with no
  owner surfaced on Today. From the original designer's review (2026-10-13): "where it came from" is a link that opens
  the source, not a label (the original page if the source has one, else the input's saved text or its registered
  summary, else the change that made the item with the request behind it; provenance is already in the ledger);
  **on hold isn't due** (built for real use, L-core; B gives the layout; the original designer's lessons from running, 2026-10-13): a held action is out of due and overdue everywhere (Today, counts, reports, the weekly
  review), shows "on hold" with its old date in a tooltip and names what it waits for, and when the input that ends the
  hold arrives the assistant takes it off hold and gives it a new date in the same change (a status value's `meaning`,
  with `held` ranked below open and never due); a note box on every action button (the helper and the routes are built, L0: the screens send no note yet), so a note typed on any action button reaches the assistant; each row carries its project (and
  parent project) tag, with its notes on hover; actions are worded to stand on their own (a playbook rule and a lint
  on the assistant's wording); and the follow-up rule above (built for real use; B gives the layout). Exit check: the owner works through their own open items on a laptop and a phone.
- [ ] [B-6b] **When something is due a follow-up** (built for real use at the end of L-core; B gives the layout and Top priorities' lines; the original designer's review, 2026-10-13: counting from when a notice
  was sent made an action due in a month come up three days later). One rule, used by Top priorities, Today's lines
  and the Follow-ups pills ("red past the follow-up time"), so all three agree: a notice of an action for someone is
  chased only when its action is due within 7 days or overdue, never while it is on hold, and an undated one after 14
  days with no word; a plain question is chased after 4 days. Each number is a setting. Check what the code does today
  first (`engine/followups.py`, the nudge threshold) and test the rule at the engine.
- [ ] [B-6b] **Top priorities, always current** (owner, 2026-10-13: the version used at work has "a constantly updated top
  priority items" list). A short ranked list on Today across every project, rebuilt as records change and ranked by
  rules (due and overdue, at risk, blocked, waiting on the person, the project's priority), never by an AI call. Shaped
  by the owner's screens of the work version (open promise P11, received 2026-10-13): one row per thing with a date chip
  (red when due), a verb first, **one line per person** ("<person>: send 1 question, follow up on 3 waiting up to 5
  days", with the items in the line's tooltip; the original designer's review: two lines per person made seven lines
  where five said it all), "Review and publish 3 drafts", who suggested it and why on the second line ("The assistant suggests · no answer
  yet"), and the row's actions (Mark done, Reassign, Hand to the assistant). Dated entries whose day has passed and
  that aren't marked done are lines ("passed, not marked done"), and the next two weeks' entries are listed after.
- [ ] [B-6b] **Copy puts the formatted message and its plain text on the clipboard together** (owner, 2026-10-13: the work
  version opens a generated page with a copy button; decided on review, design 7.5): the preview on screen is what is
  pasted, mail and documents get the formatting, chat gets clean plain text, and the menu has Copy as plain text. Every
  Copy in the app uses it (questions, follow-ups, the briefing, reports). A browser test pastes both versions and checks
  the formatted one escapes every piece of text.
- [ ] [S2] **The Monday briefing, in the app** (owner, 2026-10-13: the work version has "monday briefings"). *Moved to phase
  S1 (2026-10-17), as the weekly form of the morning brief; the description below stands.* On the first
  open of the week (the day is a setting), a briefing in this order (the designer's notes, 2026-10-19; design 6.35):
  a copy-ready message to whoever the person reports to (stance *I report to them*, 6.34; a draft under the draft
  rules, with its estimate); "this week" through the last working day: promises due by owner with overdue first,
  questions to send, answers to chase, decisions waiting, built from the records by rules; and three to five goals the
  person confirms, kept for the week. Nothing already on Today is repeated. Sending it to the person is phase E.
- [ ] [B-6b] **What the work version's screens show** (owner's screens, 2026-10-13; the screens hold real names, so only
  what they do is written here):
  - [ ] **Follow-ups by person, or by project** (a switch): the person's own items first, including corrections the
    assistant is still working on, with the person's note shown under each; then each person with their open questions
    ("waiting 5d", red past the follow-up time), Record reply and Respond to the assistant on each; Copy and Mark sent
    for the person's unsent items; their action items folded under a count, with "1 to send".
  - [ ] **Hand an action to the assistant** from its row (beside Mark done and Reassign): the assistant drafts the work
    (a message, a list, a page) as a pending draft for the person, under the usual estimate and approval. The action
    stays the person's until they close it.
  - [ ] **Projects at a glance:** the Projects table grouped under their parent project, with the stage, the target
    date and when it was last updated ("5 days ago"); the health (on track, at risk, on hold) comes from the project
    management pack when it is on (C2).
  - [ ] **Links to the person's own pages** in the header: a list in Settings (name and address), each opening in a new
    tab, so the boards and pages they check daily are one click away.
  - [ ] **A meeting added in one line** (what and when) on the calendar, the assistant merging it with a duplicate.
  - [ ] **The hand-in takes a pasted screenshot** as well as text and files. Check first what the drawer does today.
  - [ ] **Never raw data on screen:** the work version shows a raw data structure in a milestone's title. Our wording
    check covers server text; add a check that no title or line holds braces or quoted keys.
- [ ] [B-6a] **An action can be blocked** (from comparing the design with an outside list of core features): "Blocked, waiting
  on <a person, an action or a thing>", shown on the row and counted in Top priorities. The assistant proposes
  unblocking when an input says the blocker is gone (L3b). Dependencies between work items stay in the project
  management pack (C2).
- [ ] [B-6a] **The obvious next steps on screen** (L3b): "Add a new person" in the who-is-this chooser, "Add a project",
  "It's part of" and "Not a project", and the other one-click offers, in the row's menu or as its primary.
  *Built:* "Add a person…" in every person picker (P13, `NextSteps.test.tsx`) and "Add a project…" when filing (P14, `Unfiled.test.tsx`). Left: "It's part of" and "Not a project" as one-click offers.
- [ ] [B-6a] **The app's own kit, offered where it's wanted** (owner, 2026-10-13: "i dont want to see these fake plugins"): the
  add-ons that come with the app (the define-your-own kit and the example) no longer show in setup or on the Add-ons
  screen while off. The kit is offered where a person asks for kinds of items of their own (Ask, the record forms),
  not as an add-on to turn on.
- [ ] [B-6b] **The walkthrough's look** (owner, 2026-10-12: "this looks rough"):
  - fields sized to what they hold, not the full page width;
  - one clear primary button per screen ("Save and continue"), with Skip as a quiet link;
  - the step list without "Not done yet" on every row;
  - the current step marked as "you are here", not styled like a focused button (owner: it read as focus). The
    cursor already starts in the screen's first field (`Walkthrough.test.tsx`);
  - the page using its width.

  It goes through the redesign's components and screenshots like every other screen.
- [ ] [B-6b] **An unnamed assistant reads as one:** with the default name, lines say "Assistant is on it". The `.unnamed`
  wording variant (built for the AI screen's heading) is used for the other `{assistant}` lines.
- [ ] [B-6a] **Found by the phase A journeys** (decisions, 2026-10-12, "What the first journeys found"): a new AI account's
  suggested name is the service's name, not its catalog id; a custom address needs no key when the service takes
  none; Follow-ups' Copy shows the message it will copy before copying, as 7.5 says (today it copies at once).
- [ ] [B-5] **Mailbox and calendar passwords and addresses entered on screen** and kept like an AI key, for the core's own
  mail and calendar sources (moved from phase A; today they work only through `env:` or `file:`). The exit test and the
  owner's real use sign in to a named service instead.
- [ ] [B-6a] **Follow-ups' Later** (7.5): questions held for a meeting or the weekly note (`question.held_for`), kept out of To
  send.
- [ ] [B-6a] **Value-list values carry meaning** (design 5.4): a tone for each value, and a meaning for status values, so a value the
  person adds still ranks and colors correctly.
- [ ] [B-6b] **This week at every width** (7.7): a collapsed Today section, and the inspector's view when nothing is selected.
- [ ] [B-6b] **Notifications for "needs you" only** (7.19): opt-in, the Decide group's items, quiet hours. The targets are
  notification channels the phone already receives anywhere: the browser, mail to the person themselves, or a webhook
  (chat app or push topic). Each is checked with "Send me a test" and sends only to the person, a count by default.
- [ ] [B-6b] Words and accessibility throughout: the microcopy table in the review, and axe in light and dark at four widths.

The journey tests from A3 run against the new screens as they land.

From the owner (2026-10-19), after phase B's screens and before the gate week:
- [ ] [UI gate] **The UI/UX designer's re-review** (owner, 2026-10-19): once B-6b is pushed, the main session messages
  the session titled "UI/UX design review" (it runs on this repository with full access and builds the screens itself, so
  no screenshots are sent) with the commit to review and the list of UI changes since its last review (from
  `docs/design/CHANGES.md`). It builds and reviews the screens and sends its feedback, which is recorded in one file in
  `docs/project/`, like the designer answers files. Done when that feedback is received and recorded.
- [ ] [B-7] **Build the UI/UX designer's accepted feedback** (owner, 2026-10-19): the feedback the owner accepts from that
  re-review is built before the gate week, each item with its test.

## Phase S: the daily steward (after phase B, before phase I)

The owner's ask (2026-10-17): "this core needs to be full featured" as a daily assistant for anyone, not only project
support; the owner accepted `docs/project/steward-proposal.md` ("i agree with everything you wrote so definetely want to
work on these before we do the full ci/cd setup with the installers"). Reordered the same day after an outside review the
owner brought (in the proposal's "Review, 2026-10-17"): **dependable memory for commitments across work and personal life
is the reason to choose Thimbleby**, so promises and how they resolve come first, before reminders and briefs. Design
6.32. Each item ends with named tests. Exit test: a week of the owner's own use, measured (S5). The starting set of
journey tests and evaluation cases is `docs/project/steward-scenarios.md` (15 fictional scenarios, reviewed 2026-10-17).

Guide sections for promises, the brief, reminders, bills, bookings and acting after a yes are drafted
(`docs/project/steward-guide-sections.md`); each moves into `engine/guide/guide.md` in the change that builds its
feature, never before, since the guide is what the assistant answers from.

**The gate (functional designer's F1 and F2, 2026-10-19; design 6.32 "Dependability").** Phase S builds a first slice,
proves it on a week of real use, and only then goes on:
- **The first slice (S1):** promises and how they end, reminders, replies owed, one plain "what changed since yesterday"
  line, the coverage line, "Missed one", the quiet first run, and outage handling brought forward from phase E (work waits
  for the network; a run that did no work isn't an attempt). A rule's check before the change applies (from phase E) is
  needed before S1b at the latest. **Estimated alone: about 4 sessions** (connecting the fifteen rule modules into intake,
  the promise records and endings, the coverage line, "Missed one", the quiet first run, outage waiting, the replay set),
  then the gate week.
- **The gate week:** the owner's personal mail (R9 rules out work mail); at least one closed-lid night and one network drop;
  the owner writes down each promise they notice before looking at the assistant's list, as the independent list; two
  days are measured first and the thresholds set from what was seen, then the counted week. Pass on the owner's
  thresholds for the measures in design 6.32. The testers are held to the thresholds this week sets for missed out of present, silent closes and wrong endings: those numbers come from real use, and per-tester thresholds would move the bar to fit. Counts that depend on how much mail a person gets are reported, not gated. The "Missed one" trend from week one to week two is the one measure only the testers have.
- **The freeze:** What is measured is frozen during the counted week: Today, the promise lines, the prompts and the model choices don't change. Fixes found during the week go into `docs/project/gate-week-fixes.md` (created when the week starts) and land after it. The one exception is anything that loses a promise or closes one wrongly: it is fixed at once, and the day is noted in the week's log so the measures before and after it can be told apart.
- **Behind the gate:** S1b (sending and calendar acts: the riskiest part, so it waits), the brief, meeting prep, people
  memory, areas of life, capture from anywhere and the conversation.

S1. **Promises, and how they end:**
- [ ] [S1-2] **Learning from the sent version** (the designer's notes, 2026-10-19; design 6.35; the style pair, moved here
  from L-more): a sent message is matched one-to-one to its draft (thread, recipients, `drafts.sent_match.similarity`);
  the difference is a style signal ("edited before sending") that proposes a style note through the learning loop; a
  copied draft not found sent after `drafts.sent_match.ask_after_days` asks once whether it went out another way. Exit:
  a learning pair proves a sent version's changes (names replaced with roles, a promise cut) carry to the next draft,
  and a journey test of the copied-but-not-sent question.
- [ ] [S1-2] **What a draft to someone else carries** (the designer's notes, 2026-10-19; design 6.35): lints on every draft
  to someone other than the person: no bookkeeping (the wording sheet's internal terms), only openable links, quotes of
  the reader's own words at most `drafts.max_quote_words`, and never singling a person out in a group draft (a
  discrepancy goes to that person alone). One message per person per batch: everything one gap needs is one ask, all
  asks to one person go out together numbered, each keeping its own id, sent now or held for a later batch (the
  designer's review, 2026-10-19). Exit: a test per lint, a test that two asks to one person on one day make one
  message with two numbered asks answered separately, and a learning pair for singling out.
  *Built so far (S1-2):* the `bookkeeping` and `long-quote` lints (`tests/test_reader_checks.py`); one message per
  person with numbered asks already existed (`engine/followups.py`). Left: holding a message for a later batch, and
  singling out (with drafts to several people, S1b) and its learning pair.
- [ ] [S1-2] **A sender's distribution limit travels with the content** (the designer's notes, 2026-10-19; design 6.35):
  a limit read from a message is recorded on the source as its audience (narrowing applies at once; widening is the
  person's alone, recorded with who widened it); records drawing on it carry the most restrictive limit; a draft to
  anyone outside an audience is refused (an invariant), and its packet leaves that source out. Exit: a restricted and
  an open message in one area; a draft outside the group draws only on the open one.
  *Built so far (S1-2):* markings read by rules into the source's audience, `source.limit` (narrow only) and
  `source.widen` (the person's), the `audience` invariant on questions, reroutes and drafted replies, and "Limited to"
  with Widen on screen (`tests/test_audience.py`, `SourceLimit.test.tsx`). Left: records made from a limited source
  carrying the limit (a fact quoted later), and a packet leaving a limited source out once a task drafts to a named
  recipient.
- [ ] [S1-2] **"Missed one"** (designer F5) wherever the person is looking, the evening wrap-up included, accepting a plain sentence.
- [ ] [S1-3] **Sign-in sources taken in quietly** (designer F6, from the intake built 2026-10-19): sources a sign-in adds use
  `first_run: intake`, and journeys J2 and J6 are rewritten for one total, one go and one "Look over what was found" line
  instead of a review line per item. *Today:* sign-in sources still read the last day (`first_run: recent`).
- [ ] [S1-3] **A first success in five minutes:** the walkthrough connects one mailbox and an AI account, looks back over the
  last two weeks of the person's own mail (estimate first), and shows a handful of real open promises with one follow-up
  ready, before any project, area, pack or extra account is asked about.
- [ ] [S1-3] **Which sign-in an agent runs as** (the designer's lessons, 2026-10-19; design 6.16): the account check reads
  the identity each command-line agent runs as from the tool itself (an adapter capability), Settings shows it beside
  the account, and a change of identity, or one that doesn't fit the work's data level, is a Today line; runs that would
  reach a level the new identity isn't allowed wait for the person. Risk R15.
- [ ] [S1-3] **Work the assistant releases on its own keeps the person's hours** (the designer's notes, 2026-10-19;
  design 6.35): new Today lines it adds, reminders it set itself, notifications and work held until an event that
  comes in at night wait for working hours and never land in quiet hours; a time the person chose is kept; what waited
  arrives as one group. Exit: a test with an input at night and a reminder the person set for early morning.
- [ ] [S1-3] **The gate week's instruments** (design 6.32 measures): silent closes, missed out of present (against the owner's
  own list), wrong endings, Missed-one per week, the replay set.

S1b. **Acting for you, after your yes** (owner, 2026-10-17: "if we can have the app actually able to do mail/calendar
management (not just read only) lets do it"):
- [ ] [S1b-1] **The publisher, brought forward from phase C4:** every outward act is shown as its exact content and target
  (recipients, the calendar and the time), approved by the person, then carried out with a visible status (sent, failed
  with why, undone where the service allows) and written to the ledger. Recipient checks: a new or outside recipient,
  or one taken from untrusted text, is called out before the yes.
- [ ] [S1b-2] **Mail:** reply, reply all, forward and send a drafted message; archive, move, label and mark read, one at a time
  or as an approved list. Through the account's own service (the Google and Microsoft add-ons ask for send and modify
  access, a change their builder makes) and, for a plain mailbox, sending through the account's outgoing server.
- [ ] [S1b-2] **Reminders that reach the person while the computer sleeps** (moved from S1-2's reminders, which needed
  the publisher for it): (owner: "whatever we can do to make it full featured ... but not
  phone pushes unless it was an installed ios or apk"): a reminder can also go into the person's own calendar as an
  event with an alarm (an approved calendar write, once per reminder or by a standing yes for reminders), so their phone
  rings without Thimbleby running; or as a reminder mail to their own address. No third-party push service. A
  companion phone app (iOS and Android) that receives the desktop's reminders is planned after 1.0 (it needs a relay
  the apps can reach).
- [ ] [S1b-2] **Calendar:** create an event or a hold, move or cancel one the person owns, and accept, decline or propose a
  new time for an invitation. Through the account's service; a subscribed calendar link stays read-only by nature.
  Reading an invitation and preparing the answer has its engine (`engine/itip.py`, `tests/test_itip.py`); sending it
  waits for the publisher.
- [ ] [S1b-2] **Plugin API for acting:** add-ons declare the acts they can carry out (a channel per account kind: send,
  reply, move, label, create or change an event) and the access they need in `requires`; the core calls them only from
  the publisher after the yes, and their sign-in asks for the wider access when the person turns acting on. Released
  with the guide, so the mail add-on's builder builds against it.
- [ ] [S1b-1] **Nothing on its own:** the assistant drafts every act; none runs without the person's yes on that exact act, and
  rules may only suggest (an outbound op is never applied automatically, design 6.7).

S2. **Time and attention:**
*Reminders at a time moved to S1 (batch S1-2), because the gate's first slice names reminders.*
- [ ] [S2] **Repeating to-dos** on the repeat engine the calendar uses (open promise P17), each occurrence its own row.
  A repeat is typed as a phrase and shown back from data (`engine/repeat_phrases.py`, `tests/test_repeat_phrases.py`):
  "the 31st" falls on a short month's last day rather than skipping it.
- [ ] [S2] **What changed in an invitation** is computed as data (`engine/invitation_changes.py`,
  `tests/test_invitation_changes.py`): moved, end changed, cancelled or restored, title, place, organizer, and who was
  added, removed or replied, each a kind with its values for the wording sheet; it feeds the brief's "changed
  overnight" lines and the invitation's page.
- [ ] [S2] **The morning brief as what changed, what is at risk and what needs your yes** (not another summary), and the
  evening wrap-up; the Monday briefing is the weekly form (moved from phase B).
  Its shape is in design 6.32, with ten samples (`docs/project/steward-brief-samples.md`) that become its evaluation cases.
- [ ] [S2] **A capacity check on the day's priorities:** an optional effort estimate on a to-do (the assistant suggests one),
  the free time left from the calendar, and "this is more than today holds" when it is, with what to move. No automatic
  scheduling.
  What to move is proposed by rules (`engine/capacity.py`, `tests/test_capacity.py`): never a fixed to-do, those due
  today or overdue last, then lowest priority, not promised and latest due first, with no move a larger one made
  unnecessary.
  Free time is computed by rules (`engine/free_slots.py`, `tests/test_free_slots.py`): every calendar merged,
  working hours and days in the person's zone across clock changes, a buffer around meetings, tentative entries
  blocking unless counted as free; it also finds the slots for "propose a new time".
  Clashes are found by rules (`engine/clashes.py`, `tests/test_clashes.py`): overlaps across every calendar,
  tentative ones apart, and too little travel time between two places, an online meeting needing none.
- [ ] [S2] **An attention budget:** quiet hours, a cap on suggestions per day (the rest wait for the digest), an importance
  threshold, and dismissals that stick and teach (a dismissed kind of suggestion comes back only when something
  changes). All settings with defaults.
  Which suggestions interrupt is decided by rules (`engine/attention.py`, `tests/test_attention.py`): held back when
  dismissed and unchanged or below the threshold, saved for the digest in quiet hours or past the day's cap, the
  most important shown first.

S3. **People and meetings:**
- [ ] [S3] **Meeting prep and after-meeting capture** for any calendar event, not only a series.
- [ ] [S3] **People memory:** last in touch, asked of and by them, what matters to them, how they like to be reached, their
  dates, all with evidence; shown before a meeting, and one line when a promised follow-up has gone quiet.

S4. **What arrives, and where it may go:**
- [ ] [S4] **Dates in documents:** deadlines, renewals, expiries, warranties and bookings become dated facts with a proposed
  reminder; travel and booking confirmations become the app's own calendar entries. Bills are reminders only: no bank
  connection, balances or cash flow (owner, 2026-10-17).
  Booking confirmations are read from the structured data the mail carries (`engine/bookings.py`,
  `tests/test_bookings.py`, fictional samples in `tests/fixtures/bookings/`): flights, stays, events, restaurants,
  rental cars and trains, with every missing or unclear field reported and nothing guessed from the prose.
  Bill dates by rules (`engine/bill_dates.py`, `tests/test_bill_dates.py`): a day of the month (the 31st becomes the
  month's last day), the last day, the nth weekday, every N weeks or yearly, moved to the previous or next business
  day around weekends and the person's holidays, each with reminders some days before.
- [ ] [S4] **Areas of life** (work, home, a side project) with their own data level and allowed AI accounts, one Today across
  them, and **the separation visible:** each area says which account reads it and whether anything leaves the
  computer, and a draft for one area never draws on another area's knowledge (the packet's reach stops at the area).
- [ ] [S4] **Capture from anywhere:** a forward-to address or watched folder, voice notes transcribed through a new adapter
  capability, the phone page's capture box; the global shortcut with phase I's menu bar and tray app.

S5. **Manner and proof:**
- [ ] [S5] **Gentle suggestions with choices** on patterns, each choice recorded as a signal, within the attention budget; the
  governor's stale sweep for the person's own items is brought forward from phase E.
- [ ] [S5] **Talking to Reginald:** the conversation on a record (plugin question 190) as the way to ask for anything, every
  proposed change kept or dropped inline.
- [ ] [S5] **The core reads as a daily assistant:** screens, prompts and help audited for project-manager wording; what is
  PM-only is listed for the PM pack (phase P).
- [ ] [S5] **The outcome, measured** on the Quality screen (6.20): open promises found that the person kept, false alerts
  (dismissed or corrected), time spent reviewing, and follow-ups completed. The exit test reads these from the owner's
  week.

Decided by the owner (2026-10-17): approved mail and calendar management in 1.0 (S1b); reminders reach a sleeping
person through their own calendar or a mail to themselves, no third-party push, a companion phone app after 1.0; the
first audience is independent professionals juggling clients and personal life, tested first by the owner's colleagues
and people answering a LinkedIn post. Areas stay inside one workspace.

## Phase I: installers for Windows and macOS (after phase S)

**The tester milestone (owner, 2026-10-18; designer's F8 and plan point 5, 2026-10-19).** Measured also by how many
items each tester brings back through "Missed one" per week, which should fall from week one to week two. The invitation
says personal mail, or work mail only with the employer's OK (risk R14). A small invited group tests the installers with the mail and calendar
add-on. Gated on: every integrity defect in phase B's first items fixed with its test; the installers built and tried
on a clean Mac and a clean Windows computer with the same journey (install, connect mail, a first result, Undo,
reopen); and the gate week passed, so its thresholds exist. The testers are held to the thresholds the gate week set for
missed out of present, silent closes and wrong endings: those numbers come from real use, and per-tester thresholds would
move the bar to fit. Counts that depend on how much mail a person gets are reported, not gated. The "Missed one" trend
from week one to week two is the one measure only the testers have. The two tester weeks are their own row in the batches
("Tester weeks").

**The owner decided (2026-10-18):** (1) every defect above is fixed before anyone outside tests the app: the tester
milestone below is gated on them; (2) testers use the mail and calendar add-on, since a test without real mail isn't
much of a test; it stays an add-on and becomes optional at 1.0, and how testers get it (inside the installers, or
offered from the catalog during setup) is designed in phase I without putting its code in this repository; (3) no
fixed date: the 2026-10-20 target is dropped and the tester group follows the gates; (4) the website is fed by this
plan (phase I, "The website").

**The website (owner, 2026-10-18).** The product's public website lives in its own repository, worked by its own
session; today it is a coming-soon page. This plan feeds it what to say, and it never says more than the app does:
- [ ] [I-2] A content brief for the website's session at each milestone that changes what's true (the tester milestone,
  each release, 1.0): what the product does today, what it doesn't yet, who it's for, how to join the testers, and
  where downloads are. Written here from the release state; sent with `send_message`; the website's repository never
  receives code or private details from this one.
- [ ] [I-2] Keeping the two in step: the release workflow publishes the facts the website shows (latest version, download
  links and their checksums, release notes) in a form the website reads, so the site is never edited by hand to
  match a release. Designed with the website's session; the domain and repository are named in that session's
  settings, not in this repository.

The owner's ask (2026-10-16): "I really want to be able to create windows and mac distributions so that I can send them
to people for testing, and they will not want to do all the command lines to build it. Can we have a CI/CD setup that
will create windows and mac installers? Those windows/mac installers should set the program to be installed in the
appropriate places, and default the storage to the place where windows/mac typically store application data." It comes
after phase S (the owner's order, 2026-10-17) and before phase C's plugin API release. Today a tag builds the Python package with install scripts
(`.github/workflows/release.yml`); a tester still needs a terminal.

- [ ] [I-1] **Built by CI from a tag:** the same `v*` tag that builds the package also builds, on macOS and Windows runners, a
  macOS disk image (`.dmg`, Apple silicon and Intel) and a Windows installer (`.exe` setup), each with its own Python,
  the built screens and the core's shipped files inside, so a tester needs no Python, Node or terminal. The release page
  lists them with their SHA-256. The suite and the self-check run on each runner before anything is attached.
- [ ] [I-1] **Installed where each system expects:** macOS drags the app to Applications; Windows installs for the person
  (no administrator rights needed) in the per-user programs folder, with a Start menu entry and an uninstaller. This
  replaces phase B's "A launcher for people who never open a terminal".
- [ ] [I-1] **The data where each system keeps app data:** the workspace, its private folder, backups' defaults and logs go to
  the system's own place: on macOS the person's Application Support folder (logs in their Logs folder), on Windows their
  local AppData folder, never the roaming one, which a company may put on a network share where a database's locks
  are unreliable (logs and cache beside the data, each in its own folder). The app's location is never written to.
  Where the folder is stays a setting (`cockpit init` and the walkthrough can pick another), and uninstalling never
  deletes the person's data. The folders are computed by `engine/app_dirs.py` (`tests/test_app_dirs.py`); nothing
  uses it until phase I.
- [ ] [I-1] **Opening the app starts it:** the app starts the local server on loopback, opens the person's browser at it, and
  shows a menu bar (macOS) or tray (Windows) item with Open, Restart (only when one is waiting, per the restart rule) and
  Quit. A second launch opens the running one instead of starting another. The first launch lands in the walkthrough on
  a new workspace in the default folder (`cockpit init` with no template).
  The launcher's core is built (`engine/launcher.py`, `tests/test_launcher.py`): the per-folder lock, the readiness
  wait, the tray loop on the main thread and one server thread. Left: start it from the app with the configured
  base path and the install token, the menu wording from the wording sheet, the brand icon, `pystray` and Pillow in
  the desktop build only, one restart path shared with `cockpit serve` (which restarts by starting itself again),
  and the manual check on Windows and macOS.
  Draft build files (PyInstaller for macOS and Windows, a per-user Inno Setup installer, a tag workflow with
  checksums) are in `deploy/desktop/`, not switched on; `deploy/desktop/DRAFT.md` lists what to verify and fix first.
  The icon set ("Reginald's bow": SVG masters, the macOS iconset and .icns, the Windows .ico, one-color menu bar and
  tray icons in black and white, and the favicon) is in `docs/design/brand/icons/`; `export_icons.py` rebuilds the
  exports from the renders, checked to reproduce them pixel for pixel.
- [ ] [I-1] **Add-ons install beside the app, not inside it:** an installed app's own folder is read-only (and signed), so
  Install on Add-ons puts add-ons in a per-person add-ons folder in the app-data place, which the app reads at start.
- [ ] [I-1] **Updates:** the app checks the release feed it was built with (a build variable, empty in the repository) and
  shows "A new version is ready" with what changed; the person downloads and installs it themselves; their data stays.
- [ ] [I-2] **The release build fills in its catalog and feedback addresses** from repository variables, as the package build
  already does, so a tester's Add-ons lists packs with nothing to type.
- [ ] [I-1] **Signed so the systems let it open** (the owner's decision, open: costs money): without signing, macOS refuses
  to open a downloaded app until the person allows it in Privacy & Security, and Windows SmartScreen warns before it
  runs. Signing needs an Apple Developer account (yearly fee) with notarization for macOS, and a code-signing
  certificate or signing service for Windows; the secrets live only in the repository's CI secrets. Until the owner
  decides, the builds are unsigned and the release notes say how to open them.
- [ ] [I-1] **A name and icons** (owner, 2026-10-16: "I also want to make sure we add proper icons and a good name. is PM
  Cockpit really a good name ... it should be marketed more as a daily assistant type thing versus only for PMs"): the
  product's name is **Thimbleby** (owner, 2026-10-17), and the assistant's default name is **Reginald**, which the
  person can still change; it is checked for clashes (app stores, trademarks, domains) before the installers ship. *First check
  (2026-10-17, the owner's research report, kept on their computer): two AI assistants already use the name in the same
  field (one with email integrations, one a reminder "butler"), a Windows productivity app has the exact name, the
  .app domain is held, and an official trademark search is still owed. "Morrowby" and "Daywarden" collided too; the owner chose
  Thimbleby after their own check; thimbleby.app was free on 2026-10-17 (the owner's check).* The name shown on
  screen, in the installers and in the docs comes from one place; internal names (the package, the command, the add-on
  entry point, the environment prefix) change, if at all, in phase C's plugin API release, so add-on builders adapt
  once. Icons: the app icon for macOS and Windows at every size, a one-color menu bar and tray icon, and the browser tab
  icon, from the designer. *Direction chosen 2026-10-17: "Reginald's bow", a cream thimble with a deep red bow tie and a
  gold rim on a deep red tile (concept: `docs/design/brand/icon-concept-reginalds-bow.webp`, an image-generator sketch,
  not a final file). The final set is redrawn as vector art: one consistent bow size and position at every size, the
  macOS tile on Apple's icon grid with its margin, no extra border on the dark version, dimples only at 512 and above,
  the bare silhouette with a white bow notch at 16, filled shapes for the menu bar and tray, a Windows .ico (16, 24,
  32, 48, 256) and the browser tab icon.*
- [ ] [I-1] **Nothing made-up ships** (owner, 2026-10-16: "I want it to come with all the capabilities but without all the
  nonsense demo setups that just make things confusing. The user can addon during setup"): the installed app has no
  sandbox command, no fictional workspaces and no example add-on; the first launch is the walkthrough on an empty
  workspace, and add-ons are offered in its add-ons step from the catalog. The fictional workspaces stay in the
  repository as test fixtures only.
- [ ] [I-1] **How it is built (research, 2026-10-17, checked against the code):** PyInstaller in its folder mode (not one
  file, which unpacks on every start) for the app; on macOS an `.app` signed with the hardened runtime, notarized and
  stapled, inside a `.dmg`, built separately on Apple silicon and Intel runners (pinned, not "latest"); on Windows an
  Inno Setup installer for the person only (`PrivilegesRequired=lowest`, under their local programs folder), with both
  the program and the installer signed. Python 3.12 on native runners; no Node or browser engine in the download (the
  screens are prebuilt and open in the person's own browser). The launcher: the menu bar or tray loop on the main
  thread, one server in the background (no reload, one worker), a readiness check before the browser opens, one
  instance only, and Quit stops everything. The local API already requires the install token besides loopback and the
  Host and Origin checks (`api/app.py`), which an app holding mail access needs. Updates start as "a new version is
  ready" opening the signed download; Sparkle (macOS) and WinSparkle (Windows) are the later step.
- [ ] [I-1] **Add-ons in an installed app (decide at the start of phase I, with a trial):** today Install unpacks a wheel into
  the app's own package folder (`engine/pack_install.py` `target()`), which a frozen, signed app can't take. The plan:
  an add-ons folder in the person's app-data place, put on the import path at start, filled with exactly the wheels a
  release lists (round 35's design: every wheel with its checksum, never from an index). Pure-Python wheels work that
  way. Wheels with compiled parts (a pack's XML or typesetting library) also need, on macOS, either the
  `disable-library-validation` entitlement (allowed for notarized apps; it lets the app load code not signed by its
  own team, so add-ons stay limited to checksummed catalog releases) or a separate Python worker for add-ons. The trial
  installs the writing pack's own wheels into a built app on both systems and picks one.
- [ ] [I-1] **Signing: unsigned to start** (owner, 2026-10-17: "i will just use unsigned to start"). The macOS build is
  only ad-hoc signed (Apple silicon needs that much, and PyInstaller does it), so a tester opens it once through
  System Settings, Privacy & Security, "Open Anyway"; on Windows, SmartScreen's "More info", then "Run anyway". The
  release notes and the download page show both, with pictures. Unsigned builds don't enforce library validation, so
  compiled add-ons load without the entitlement for now; the trial above still decides the signed setup. Signing is
  added later without other changes. **Costs when it is (prices advertised 2026-10-17, before tax):** Apple Developer Program $99 a
  year (signing and notarization for direct downloads); Windows: Azure Artifact Signing Basic $9.99 a month with 5,000
  signatures (individuals eligible in the US and Canada, identity checked; signs from GitHub without a long-lived
  secret), or a standard certificate from about $129 a year plus a signing service or hardware token. About $219 a
  year for Apple plus Azure Basic. No signing removes SmartScreen's warning at once; reputation builds over downloads.
- [ ] [I-2] **Mail and calendar sign-in approval for testers and launch** (research the owner brought, 2026-10-17; the
  services' published rules, to be confirmed with them):
  - *Google:* the full feature set needs `gmail.modify` and `calendar.events` (plus `calendar.calendarlist.readonly`
    to pick calendars); Gmail reading is already a "restricted" permission, so a read-only test changes nothing. An
    app in Google's Testing mode allows up to 100 listed testers, shows an unverified warning, and its sign-ins expire
    after 7 days (testers reconnect weekly; the app's "sign in again" line covers it). Public use needs Google's
    verification: a verified domain (thimbleby.app), a homepage and privacy policy, a reason for each permission, a
    demonstration video. Sending mail content to a cloud AI service likely counts as processing outside the computer,
    which brings Google's yearly independent security assessment (priced by the assessing lab; ask for a written quote;
    a local model keeps the content on the computer). Start verification as soon as the acting features (S1b) can be
    shown.
  - *Microsoft:* `Mail.ReadWrite`, `Mail.Send` and `Calendars.ReadWrite` (with `offline_access` and `openid`); no
    published tester cap; personal Outlook accounts consent themselves; companies' consent rules often need an
    administrator's approval even for a verified publisher. Publisher verification is free but needs a verified
    organization in Microsoft's partner program.
  - *Both:* a public desktop client with the system browser, the authorization code flow and PKCE, no secret embedded
    in the app; and Thimbleby's own approval of every exact act stays, since a granted permission allows more than the
    person approved. For the first test: Google in Testing mode for under 100 people (others on Microsoft or a plain
    mailbox), a guide for company administrators, and the warning and weekly reconnection explained to testers.
- [ ] [I-1] **Passwords, keys and sign-in tokens in the system's own vault** (found writing the privacy policy, 2026-10-17):
  today they are files in the workspace's private folder, readable only by the person's account; the installed app
  keeps them in the macOS Keychain and Windows Credential Manager instead, with the files as the fallback where no vault
  exists. The privacy policy draft (`docs/design/brand/privacy-policy.md`) is updated to match when it lands.
- [ ] [I-1] **Exit test:** on a clean Mac and a clean Windows machine, download from the release page, install, open, finish
  the walkthrough to the first result, quit, reopen with the data still there, update to the next version, uninstall
  with the data kept. Journey tests cover what CI can (launch, the server answering, the data folder), and the owner
  checks the rest by hand on both systems.

## Phase C: the writing pack in the owner's workspace

Re-sequenced on 2026-10-15 (the owner: the writing pack is finished completely before any other pack starts). Phase C is
the writing pack and what it needs from the core; the project management and publishing packs and the hand-offs between
packs are phase P, after it.

**Exit test:** in the owner's own workspace:
- the writing pack takes a fictional manuscript from import to a built PDF and EPUB the owner approves, working alone;
- **the pack learns too:** a correction in the pack's own work produces a proposal, and a later similar input comes out
  right. This proves the plugin API call in L2 carries the knowledge to packs.

C0. **The capability matrix, step 2: work goes to a model that can do it** (owner, 2026-10-15; design 6.16; about 1.5
sessions; first in phase C because the writing pack is the first use where model choice per kind of work matters most):
- [ ] [C0] task kinds, the core's and a pack's, declare the skills they need (plugin API: `task_kind(skills=...)` and `skills:`
  on a pack's cases), and the guide says so once it is built;
- [ ] [C0] the router picks the cheapest allowed model whose measured scores hold for every needed skill, across accounts,
  within the data level and the fallback rules; unknown or stale counts as not measured, and the run says which skill
  decided;
- [ ] [C0] corrections in real use count against the model for the skills they touch, shown apart from measured cases;
- [ ] [C0] Today's one line when the matrix shows a cheaper model is as good, or the configured one is low for a needed
  skill; nothing switches on its own.

C1. **The writing pack, installed and reviewed.**
- [ ] [C1] **A pack's own libraries install from the screen** (round 35, moved from phase A): a release names every package it
  needs with checksums. Install shows what will be added, refuses conflicts with the app's own, and Remove takes out only
  what that pack needed. Answered with plugin question 183 (file types a pack needs).
- [ ] [C1] It installs from Add-ons with its libraries.
- [ ] [C1] Its two load notes are settled: SVG and TIFF files the workspace doesn't accept yet.
- [ ] [C1] Its open questions are answered: 170, a review accepting a group of the assistant's changes at once; 172,
  guide fixes.
- [ ] [C1] A host-side review of the pack: what it registers and reaches, its rules, and its tests run against this host.
  It is checked on 2026-10-12 to load and register on plugin API 0.3.55.
- [ ] [C1] The owner's walkthrough on a fictional book, with what to change written down.

C4. **What the packs need from the core.**
- [ ] [C4] **The publisher and the file channel** (the publisher itself moves to phase S1b for mail and calendar; this item
  keeps the file channel). Approved files are saved or shared after the person approves the exact
  content. Waiting to go out lists them, with a diff where it applies. A page whose changes are logged as history rows
  logs each change, except the removal of a stray history row, which needs no row of its own (the functional designer's
  lesson 8, 2026-10-15).
- [ ] [C4] **Writing into a shared file someone else uses** (the original designer's lessons from running, 2026-10-13): write only the target cells or parts and copy every other
  part byte for byte, with a test that validations, conditional formats and formulas survive; "is it open?" checks for a
  process holding the file, not only a lock file (autosave on a synced cloud file leaves none); when it is open, hold the
  change and retry on a timer, then after writing wait for the sync to settle, re-read, and rewrite once if it was
  overwritten; after a few tries, go to the person once. Text written into someone else's table stays short and
  scannable (a key, a status word, a few words), explanations go in the assistant's own notes, and a cell where nothing
  was found stays blank.
- [ ] [C4] **Fact lookups** (6.19): published dates are looked up from the configured sources, never asked. Includes
  "add from <link>" reading the link's system of record first: its status, what shipped and its dates, and a finished
  item added with its facts and a question whether to mark it complete (the designer's lessons, 2026-10-19).
- [ ] [C4] Anything else either pack's builder asks for, answered in one weekly round.
- [ ] [C4] **Rounds 34 to 48 and 52, answered 2026-10-16** in `docs/project/plugin-answers-34-48.md` (sent to the builder, who
  confirmed and will adapt once): built together as phase C's first plugin API release, the dependency install in C1, and
  the conversation on a record (190) right after it. The owner keeps phase B first (2026-10-16: "Keep B first").
- [ ] [C4] **Round 39 from the writing pack's builder** (received 2026-10-13; answered in the weekly round, after L0):
  - 190, **a conversation on a record**: a thread kept on the record, opened from any screen with that record as its
    context, each message a request of a task kind the pack names, replies with citations, kept-or-dropped changes,
    queued work with its estimate, and questions answered by replying; it uses L2's bounded search. It is designed with
    Ask as a side pane (phase B) and built after L2, since it needs the search round; the design answer goes in the round.
  - 191, a task kind that declares the context it needs, so a run goes only to a model whose window fits, the estimate
    names it, and a run that fits nowhere says so before anything is sent (provider layer, 6.16).
  - 187, a preview beside a data form, run again after each save, read only, as the person.
  - 188, a small pack-defined value on a request, never shown, returned to the run.
  - 189, a computed panel column headed from the pack's wording.
- [ ] [C4] **Round 41 from the writing pack's builder** (received 2026-10-13; answered in the weekly round, after L0):
  - 193, a task kind whose `on` names several record kinds, the packet told which one it got;
  - 194, `$new:<n>` in a proposal for the record an earlier op creates, resolved by the applier in order, and refused
    with the reason when the person drops op n (applier work: the main session's);
  - 195, a `show_for`-style predicate on a person action, given the view and the target, quick and deterministic.
- [ ] [C4] **Round 42 from the writing pack's builder** (received 2026-10-13; answered in the weekly round, after L0):
  - 196, a task kind's declared tier holds over its role's tier (or is marked required), `ai.tasks.<kind>.tier` still
    overriding both; with 191's declared context need;
  - 197, `RefTo(..., blocks_delete=False)` for a reference that is history, left dangling and shown as removed.
- [ ] [C4] **Round 44 from the writing pack's builder** (received 2026-10-13; answered in the weekly round): 199, a request's
  part carrying a small pack-defined address for work on a record or file that isn't long text (with 188); 200, a record
  type saying where it is written, apart from a field named `project` (or the guide naming the rule); 201, the test
  kit's `ActionResult.apply` taking the requests to keep too.
- [ ] [C4] **Round 45** (received 2026-10-13): 202 answered at once from the code (a superseded request's `state` is set to
  done in the same change that sets `superseded_by`); 203, a stable code on the core's failures for packs' tests, and
  the guide saying the wording is not the contract, answered in the weekly round.
- [ ] [C4] **Round 46** (received 2026-10-13; answered in the weekly round): 204, `where` and `start_where` reading a field
  through a reference (with 195); 205, a request in a proposal `about` an existing record an item's op changes, dropped
  with it (with 194); 206, the guide saying a request waiting for the go is `needs_you` with approval `required`.

## Phase P: the project management and publishing packs (after the writing pack)

Moved out of phase C on 2026-10-15, in the same order the owner set: started once the writing pack is complete. The
writing pack's hand-offs to these packs are built here, when the packs exist (open promise P12, round 50).

**Exit test:** in the owner's own workspace:
- the project management pack holds the project's plan and builds a schedule from it, and the schedule shows what is
  late or at risk;
- the publishing pack starts a launch for the book, with its plan in the schedule, a listing sheet and prices;
- the hand-offs between the packs work, and each pack also works alone.

C2. **The project management pack: started** (owner, 2026-10-12). This is an AI project manager that knows what is
being done, builds schedules and tracks action items.
- [ ] [C2] Create its private repository, with a brief and a builder session like the other packs.
- [ ] [C2] The core keeps what every kind of work needs: actions with owners, questions, follow-ups, decisions, Today. The
  pack adds planning on top, through ops and the core's records:
  - [ ] **The charter:** drafted from a brief or notes for the person to approve (goals, scope, stakeholders, risks).
  - [ ] **Minutes of meetings:** drafted from notes or a transcript, with the decisions and actions filed as records.
  - [ ] **The files a project manager hands around** (owner, 2026-10-13: "PPTs, excels, etc"): slide decks, spreadsheets
    (schedules, trackers, budgets) and documents, built from the records in the person's template and saved or shared
    through the core's publisher after the person approves the exact file (C4).
  - [ ] **The plan:** goals, phases, deliverables and milestones; a date the core files as a calendar entry under a project
    becomes a milestone in that project's plan (moved from L3b). From L7, entries are made only for real events
    (meetings, launches, delivery windows, appointments), never an action's own due date, so a milestone comes from
    one of those.
  - [ ] **Meeting agendas linked to actions** (the functional designer's lesson 1 and answer 18, 2026-10-15): an agenda
    item stores the action or question it covers, and the series as well as the instance, when the agenda is written,
    so moving the meeting (the core's follow-on run, L7) finds them by id; an unsettled item rolls to the series' next
    instance; an item someone said they'd raise there is added if it's missing.
  - [ ] **What dependencies make possible in the core's terms** (answers 11 and 19): a dependent action moves with the
    one it waits on, with Undo and said in the change's note; an approval due before the work it approves is flagged
    to the person; a decision that blocks one of the person's actions due within a week is a Today line ("Waiting on
    <name>'s decision"). Never from shared words.
  - [ ] **The schedule:** work items with durations and dependencies, a critical path, dates worked out from the
    dependencies, baselines, and slips against them. Only the person rebaselines.
  - [ ] **Building it with the assistant:** from a brief, notes or another pack's milestones, the assistant drafts a
    plan and a schedule. The person approves it as any change.
  - [ ] **A system of record's bulk extract before item-by-item calls** (the original designer's lessons from running, 2026-10-13): a source declares a bulk extract (a team
    dashboard's full export of epics and stories, say) and its refresh time; the assistant reads it before asking anyone
    for status, cites its timestamp, and treats an old one as old.
  - [ ] **Tracking:** what is late or at risk each day goes to Today, with the action items behind it; a weekly status
    report is drafted for the person to send.
  - [ ] **A project update on request** (owner's screens, 2026-10-13): pick a project (or a parent and everything under
    it), a start date and who it is from and to; the assistant drafts the update from everything recorded since then
    (milestones, decisions, changes, inputs) in the sender's voice, with internal notes left out, for the person to
    approve.
  - [ ] **Health per project** (on track, at risk, on hold, not started) with the person's say, shown in the core's
    Projects table and in Top priorities.
  - [ ] **RAID:** risks, issues, assumptions and decisions, with owners and review dates.
  - [ ] **On the app's own calendar** (owner, 2026-10-13): milestones, due dates and meetings are entries in the
    core's calendar (the same records as `event.add`, phase L0), so the agenda and Today show them with everything
    else that is dated.
  - [ ] **An interface other packs use** to put their milestones into the schedule (`pm/schedule@1`). The writing pack
    puts in the book's chapters and edits; the publishing pack puts in the launch plan.
- [ ] [C2] Design 6.23 (dependencies and baselines) and 6.24 (RAID, risk reviews, escalation suggestions, cadence,
  meeting agendas) move from the core into this pack. This is a design change, recorded in decisions.

C3. **The publishing pack: started.** It doesn't exist yet. Its launch plan goes into the project management pack's
schedule when both are on, and is a plain list of milestones when it is alone.
- [ ] [C3] Create its private repository, with a brief and a builder session like the other packs.
- [ ] [C3] First version, from design 9.7 and the writing pack's `docs/publishing-pack.md`:
  - the title record;
  - a launch plan from a template, with lead times;
  - contributors;
  - Today lines and panels;
  - the listing sheet per platform and the price calculator, from dated platform data;
  - the AI-disclosure answers filled from the authorship breakdown;
  - the `publishing/manuscript-source@1` hand-off.
- [ ] [C3] After the first version:
  - the hand-off's next minor version, which says where each edition's book number comes from (the writer's own, a
    platform's free one, or none);
  - for editions with the writer's own number, a registration sheet in the order of the national numbering agency's
    form, and later a standard book-metadata file per title that the writer uploads. The pack sends nothing itself, and
    the agency's current terms are checked before this is built.
- [ ] [C3] From the writing pack's author records (received 2026-10-13, read through the hand-off's next minor version, read
  only): the author on each listing sheet; an author-profile sheet per platform, ready to copy; series and backlist
  cross-promotion in the launch plan, with the also-by list kept in step; listing and price checks for backlist titles
  outside the workspace; and short review quotes the writer approved, checked against each platform's quoting rule.
  Reading profile and review pages comes later, on the core's search and fact lookups, within each site's terms;
  nothing is scraped or sent.
- Staying with the writing pack: the cover wrap specification and advance reader editions.

C3c. **A business analysis pack and a systems architect pack** (owner, 2026-10-14: "pretty much barely disguised
standard AI that would take inputs and generate outputs that those roles would typically do ... they would also fit
hand in hand with nearly every other plugin ... they can be used to submit change requests ... for system
improvements"). Each in its own private repository with a builder, like the other packs; neither is scheduled before
the project management pack's first version.
- [ ] [C3c] **Business analysis:** from notes, transcripts or a brief, drafts what a business analyst writes: requirements,
  user stories with acceptance criteria, process maps in words, gap and impact analysis, questions for stakeholders.
  Drafts are the person's to review; checkable facts in them carry evidence.
- [ ] [C3c] **Systems architect:** drafts what an architect writes: a solution outline, architecture decision records,
  interface and data descriptions, risks and trade-offs, and review notes on a design handed in.
- [ ] [C3c] **Working with the other packs** through versioned interfaces only (design 3.9): requirements and decisions to
  the project management pack's plan and RAID; a pack's own records as inputs to both.
- [ ] [C3c] **Change requests for this product:** both packs can turn a need into a well-formed request (the problem, the
  requirement, acceptance criteria, the impact) through the core's `report.draft`, which the person reviews and sends
  to the maintainers (design 6.13). The product never changes its own code; the request goes out only after the
  person approves its exact text.

C3b. **A sales support pack** (owner, 2026-10-13): for a family member's sales job. Waiting on its functional
requirements from its user; nothing is designed or scheduled before they arrive. When they do, it gets its own
private repository and builder like the other packs, and works with the project management pack through interfaces.

## Phase L-more: the rest of learning

After the packs, beside real use (owner, 2026-10-12). None of it is needed for the loop to work. Each item has its own test.
- [ ] [L-more] **The style pair** (moved from L4): *moved to S1-2 as "Learning from the sent version" (the designer's notes,
  2026-10-19); this line stays as a pointer.*
- [ ] [L-more] **Loading a shared lessons file** (moved from L4, with Take my lessons): the injected-import pair runs through the
  real loader, and an injected entry loads as proposed.
- [ ] [L-more] **Review earned per kind of change** (owner, 2026-10-13: "over time the AI should learn what can be auto AI
  approved"). Changes to the person's data already apply at once with Undo; what they approve is the review. A kind of
  change (per task kind and op, per project where it differs) that the person has passed with Looks good
  `ai.earned_review.runs` times in a row (a setting), unedited and not undone, stops needing a look: it is marked
  reviewed and stays in What changed with Undo. One edit, undo or send back takes the kind back to review. It is
  shown and reversible on the quality panel. Never for anything outbound, system ops (rules, recipients, sources) or a
  new or probation account, and never from a model's own confidence (design 6.16, 6.22). Exit check: a learning pair
  for earning and losing it, and a test that an outbound or system op never earns it.
- [ ] [L-more] Ask gets the knowledge section, with the same citation check, and a rule or fact stated in Ask becomes a proposal
  that applies at once with Undo (6.25).
- [ ] [L-more] Take my lessons: lessons, rules and general glossary terms to a file and back into another workspace. A file from
  the person's own workspace (signed with its key) loads as active; any other file loads as proposed, on one review list.
- [ ] [L-more] A pack's guidance shown before it is turned on, and marked by origin in the knowledge log (design 12.8).
- [ ] [L-more] The agent lockdown test checks that a dummy environment variable isn't visible.
- [ ] [L-more] Part 8's rules become the core playbook's seed lessons, each with a guard kind and its fixture ids. The page is
  generated from them, and the self-check fails when it is stale. A fixture case for every instruction-only rule.
- [ ] [L-more] A command-line agent's program version recorded on each run; a new version treated like an account change; the
  program's own auto-update turned off where it allows.
- [ ] [L-more] Probation ended early from the quality panel; probation work marked on Today.
- [ ] [L-more] The unused-entries list, offered for retirement.
- [ ] [L-more] Show and restore one record as it was at a past time, from the ledger.

## Phase D: owner validation and real use

The owner's real use starts once the writing pack is complete (owner, 2026-10-19); this phase is the sign-off once the
packs are in.

**Exit test:** the owner's own judgment, on dates the owner sets: a week of real notes, mail and pack work saved
time, nothing went out without approval, a backup succeeded, and the repeat-correction rate fell over the weeks of use.

- [ ] [D] The acceptance scenario run by the owner on real material.
- [ ] [D] A week of real use; friction recorded in `ux-notes.md` and fixed in order of cost.
- [ ] [D] **Microsoft mail and calendar set up as well as Google, before 1.0** (owner, 2026-10-12). The owner's exit test
  signs in to Google; a Microsoft account must work just as smoothly through the new-start walkthrough before 1.0:
  - personal and work or school accounts;
  - an organization that requires an administrator's approval, with the screen saying exactly that and what to ask
    the administrator for;
  - the service's setup checklist in the add-on's help (the app registration, its permissions, the redirect address);
  - "the service isn't set up" errors mapped to plain words;
  - a live check on a real account;
  - a journey test like J2 against a fake service that answers the way Microsoft's sign-in does, including the
    approval-required refusal.

  The core's part is the walkthrough and the sign-in flow. The add-on's builder is told in the weekly batch.
- [ ] [D] Learning on real material (6.22): voice per recipient beyond the first style notes, and a fact's freshness checked
  before an outward draft, with disagreements between sources recorded as private
  discrepancies to ask about.

## Phase E: the rest of version 1

Order by what protects real data first, then by what the packs ask for:
- [ ] [E] **What is left of L7's facts** (moved 2026-10-16): an inference never reaches anything others see (with the
  publisher of C4); the person's own deduction is recorded as theirs, with its reason on the question it closes; what
  the assistant writes about a change says who made each part.
- [ ] [E] **The capability matrix proved on every adapter kind** (moved from L7): a fake service for the native API, the
  aggregator and the command-line agent beside the existing chat-format one, each measured into the matrix and kept apart.
  *Today:* one test records tagged results for each kind.
- [ ] [E] **"Which team is <name> on?" asked once**, with the scope resolver (moved from L7, decisions 2026-10-16): when the
  resolver needs a team the person on file doesn't have, one question to the person, never repeated for them; the
  answer sets the team with Undo. *Today:* a person with no team counts as outside the tracked area.
- [ ] [E] **The governor:** (outage handling moved to phase S1, 2026-10-19) stale-item sweeps, outage handling, `sync.sources` (sources above a level encrypted or left out of the synced folder), the scheduled export with its remote; restore to a point in
  time (a single record comes in phase L).
  Outage handling includes a draft cut off at the output limit whose continuation call finds no network: today it is
  held with a note; it should wait for the network like any run.
- [ ] [E] **Retention, and export and forget a person** (design 5.2, 12.4): forgetting is a recorded redaction, with the local
  export repository rebuilt; evidence quotes survive retention. The forget travels through the synced folder: the history
  comparison treats redacted entries as matching, and the loading computer replays the forget. Undo never restores a
  forgotten value.
- [ ] [E] Scope resolver (6.18), the scheduled rules and lessons review with promotion (6.21), and read-backs (6.7).
  The resolver reads **the person's role on each project** (run, design, watch, a value list a pack can extend; per
  person id; the role itself and its two simplest rules are built before real use, "A slice of scope"), and "I'm running X now"
  in any input proposes the role change as a system op, effective that day (the original designer's lessons, 2026-10-14,
  lesson 1). Its learning pair is in L4.
  Dependencies, baselines and RAID moved to the project management pack (C2).
- [ ] [E] **The Monday briefing sent to the person** (owner, 2026-10-13; building it in the app is phase S2, this is sending it), and a morning summary if they want one: to a
  notification target, with content only where the target is allowed for the data level (7.19), counts otherwise.
- [ ] [E] Native AI adapters and reproducible runs (6.16).
- [ ] [E] **M0, the desktop installer:** no Python, uv, Node or terminal; it updates itself.

## Publish 1.0

1.0 is a moving target until the owner finalizes scope (owner, 2026-10-19): every plugin pack is designed before
plugin API 1.0, so the API holds the base any pack could need. The items below are the release mechanics.

- [ ] [Publish 1.0] Self-check against the private workspace (`cockpit selfcheck --workspace <path>`).
- [ ] [Publish 1.0] A fresh repository with one starting commit, under Apache-2.0; secret scanning on.
- [ ] [Publish 1.0] The README and docs match what 1.0 does.

## Not in 1.0

- Hosted mode and sign-in (Part 11), and its end state: an organization install where members from the People list have
  roles, their own views and approvals by role (design 11.8; owner, 2026-10-13).
- Social, email and newsletter channels.
- The sales pack (13.3).
- Which of a pack's AI work a project allows (the writing pack's question 198, after 1.0): a project, inherited from the
  workspace and its parent, names the task kinds or groups that may run, or none; the core refuses to queue the rest from
  anywhere, says why once, and hides actions and lines that lead only to disallowed work.
- Licensed (paid) packs: the design is accepted, but whether to charge is the owner's call, after launch.
- The delivery chain of the end state (charter, owner 2026-10-14): a requirement carried from business analysis through
  project management and technical design to development, testing, acceptance and deployment, with a development pack
  (sprints, built-in testing, demos), a testing and acceptance pack (internal test cases, UAT) and a deployment pack.
  Building is staged (charter): a build pack exported for a coding agent first; then read-only connectors that bring the
  development process back to the PM; driving the building from the cockpit last, with its own safety design.
  Business analysis, technical design (the systems architect pack) and project management are already planned (C2,
  C3c). What the chain needs from the core is listed there when it is designed: links that trace a requirement to its
  stories, test cases and defects across packs, and sign-offs by role (design 11.8).
- An adapter for the Copilot SDK (owner, 2026-10-14), once it is out of technical preview: it drives the same
  command-line agent through a structured channel instead of reading its printed output. It must pass the same
  lock-down test as the command-line adapter (no tools, no files), and the command-line adapter stays.

