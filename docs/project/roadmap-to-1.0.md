# Go-forward plan to 1.0

Rewritten on 2026-10-12 after the review (`review-2026-10-12.md`), at the owner's direction.

**The goal:** Thimbleby (still called PM Cockpit in the code until phase I): a daily assistant for anyone juggling work,
which keeps track of what the person promised and what was promised to them, and gets the next step ready, with the
person approving everything outward. The path:
- **The first milestone:** the core complete, with full UI and code reviews approved, plus the installers (phases B, S and
  I).
- **The gate week** on the owner's personal mail is the first measured use of the core.
- **Real use by the owner** starts once the writing pack is complete (phase C).
- **The free core release comes first** (owner, 2026-10-20: "core Thimbleby vs paid Thimbleby+"): after phase I, the
  open core is published with its website update, and it waits for no pack and nothing the paid upgrade needs.
  Thimbleby+ (phase T) follows only if the owner goes ahead with it.
- **Packs come after the core** (the writing pack, then the project management and publishing packs). Product 1.0 ships
  on plugin API 0.x; plugin API 1.0 keeps its own test (two packs unchanged through real use), so 1.0 doesn't wait for
  every pack to be designed (decisions, 2026-10-20).
- **1.0 is published** once the owner finalizes scope.

**How the order was chosen:** each phase makes the next one testable by the owner. The plan holds one stream of work at
a time, and a phase ends when its exit test passes, not when its code is written.

Durations are estimates in working sessions. Dates are set when a phase starts and recorded here.

**This file holds only what is left.** What the roadmap finished, in the order it was done, is in
`roadmap-done.md`. Open items carry a batch tag in square brackets, such as `[S1-2]`; "The plan in batches" below
says what each batch covers, what passes at its end and how big it is. A batch is one meaningful piece of scope, with
one full test run and one push (CLAUDE.md, "Usage and machine load").

## Where things stand (2026-10-20)

- **Done** (all in `roadmap-done.md`): phase 0; phase A (2026-10-13); phase L-core's code, L0 to L7, apart from the
  owner's re-run of the failed learning cases (O3, below); phase B's waves 1 to 4 and every defect the four outside
  reviews found, each with its test; in phase S, batches S1-1 and S1-3 and S1's outage handling, coverage line, rule check
  before applying, unseen-close counting, quiet source intake and spending as a range; and, built on 2026-10-19 and 20,
  most of phase B's last screens: batches B-5, B-6a and B-6b, the UI/UX designer's re-review (the UI gate: its feedback
  is recorded in `ui-rereview-2026-10-20.md`) and seven of batch B-7's sub-items. Each open item below says what is built
  and what is left; a part is never ticked.
- **In progress:** the end of phase B. What B-7 and B-6b still lack, in short: the browser checks written on 2026-10-20
  (`web/e2e/shell.spec.ts`, `a11y.spec.ts` and `tables.spec.ts`: the first queue line's place at 1280×720, the header
  as one row, targets of at least 24px, tables beside the pane) have not been run, because the browser tests run once,
  in the full run before a push (CLAUDE.md, "Usage and machine load"); the sweep for ids, ISO dates and raw words covers
  record pages and four lists, not every view; the reviewer's further feedback; and the owner's re-run of the failed
  learning cases. The items below name the rest.
- **The order** (decided; the batches below follow it): S1 (S1-1 to S1-3) → B's waves 5 and 6 (B-5, B-6a, B-6b) built to
  S's shape → the UI/UX designer's re-review and the feedback it brings (UI gate, B-7) → the gate week → the rest of S
  (S1b, S2 to S5) → I (installers; the first milestone ends here) → C (the writing pack) → P (the other packs) → D
  (sign-off) → L-more (beside real use, after the packs) and E (the rest of version 1, ordered by what protects real data
  first) → Publish 1.0 once the owner finalizes scope.
- **The first milestone** (owner, 2026-10-19): the core complete, with full UI and code reviews approved, and the
  installers (phases B, S and I), published as the free core release (the free core's own phase I item, I-3). 1.0 is a
  moving target until the owner finalizes scope; it ships on plugin API 0.x. There is no go/no-go date: the 2026-10-30 one was
  set aside on 2026-10-09 and 2026-10-12, and stays set aside.
- **When the owner uses it:** the owner tests it after phase B and starts real use once the writing pack is complete
  (owner, 2026-10-15; confirmed 2026-10-19). Phase S's gate week is the measured trial of the core on the owner's personal
  mail (R9 rules out work mail), before testers. The owner tries the app in the evenings as it goes.
- **Owner action pending:** the owner's first run of the learning tests (O3) was made on 2026-10-20 (81% of 214, 79% harder,
  53% pairs, 30% harder pairs; one run per case, as the B-6b item below records), and its failures led to
  the fixes built in batch B-7 (design `CHANGES.md` section 126). Left: the owner re-runs the failed cases with
  `cockpit evaluate ... --case-failed <the report>` on the commit that batch pushes (steps under O3, below).
- **Open items:** 120, each in exactly one batch; 249 done items are in `roadmap-done.md`.
- **Plugin API:** 0.3.86 (the change notes are in `docs/plugin-api-0.x.md`).

## The plan in batches

One row per batch, in the order of work. A batch is one meaningful piece of scope: it ends on its exit test, with one
full test run and one push (CLAUDE.md, "Usage and machine load"). Every open item below carries its batch tag. Sizes are
rough (half a day to two days; the batches from phase C on are sized when they are reached). The phase sections below
keep each item's full text.

1. **S1-1 Promises core (built; the owner's learning run O3 is its last step)** (0 open items; size: about a day)
    - *Covers:* *Promises both ways* (phase S, S1; built so far: promise ops, rules-first dates, endings held for Keep, see that item's "Built so far"; left: prompts and playbook, the sent folder as a source, golden cases and harness pairs); *How a promise resolves* (S1; left: the line for a promise past its date with its choices); *Every promise shows why* (S1).
    - *Exit:* the twenty learning pairs run as harness pairs and pass; a fictional thread gives promises both ways with endings held for Keep; and the owner's one learning-test run (O3) on this batch's push.

2. **S1-2 What the person owes and misses** (2 open items; size: about two and a half days)
    - *Covers:* *Replies owed* (S1); *Reminders at a time* (moved here from S2, since the gate's first slice names reminders; S2 keeps a one-line pointer); *What changed since yesterday* (a new item in S1, from the designer's F2: the gate text names the line and no item stood for it); *"Missed one"* (S1).
    - *Also covers* (the designer's lessons, 2026-10-19): *A stance per person* (the field, its default and the gate on drafts and questions, design 6.34), and *A rejected ask is dropped, not reworded* (6.22), each with learning pairs.
    - *Also covers* (the designer's notes for later batches, 2026-10-19; design 6.35): *Learning from the sent version* (the style pair, moved here from L-more), *What a draft to someone else carries*, *A sender's distribution limit travels with the content*, and the extra endings of a reply owed (in *Replies owed*) and the assistant's own voice in *What changed since yesterday*.
    - *Exit:* a journey test for each; the stance gate holds a design question drafted to someone the person works alongside; a draft to someone outside a restricted message's group draws only on the open one; the style pair passes; the new learning pairs pass.

3. **S1-3 Ready for the gate week (built; the gate week is next)** (0 open items; size: about a day and a quarter)
    - *Covers:* *Sign-in sources taken in quietly* (S1, designer's F6: sources a sign-in adds use the quiet intake, and journeys J2 and J6 are rewritten for one total, one go and one "Look over what was found" line; a new item in S1); *A first success in five minutes* (S1); *The gate week's instruments* (S1).
    - *Also covers* (the designer's lessons, 2026-10-19): *Which sign-in an agent runs as* (design 6.16), so the gate week runs on a known account; and (the designer's notes for later batches) *Work the assistant releases on its own keeps the person's hours* (design 6.35).
    - *Exit:* the owner can start the two measured days; journeys J2 and J6 pass with one total, one go and one "Look over what was found" line.

4. **B-5 Sources and accounts** (1 open item, plus the numbered wave 5 entry; size: about one to two days)
    - *Covers:* *Wave 5* with P17 (.ics calendars, full featured) and P18 (several accounts of one service); the items that belong with it: *Passwords, keys and private addresses typed on the screen* (P16), *Add-ons install from the screen* (P15), *Mailbox and calendar passwords and addresses entered on screen* (all in phase B, built to S's shape).
    - *Exit:* the tests each item names pass; the owner adds an .ics link and file and a second account of one service, and types a password and a key on screen, with no file edit.

5. **B-6a The rest of B: records, Settings and forms** (3 open items, plus the numbered wave 6 entry; size: about one to two days)
    - *Covers:* from *Wave 6* (phase B): the designer's F12 and F13 and P26 (in the wave 6 entry), *Lists, not typing*, *The cursor starts where you type*, *Value-list values carry meaning*, *Follow-ups' Later*, *An action can be blocked*, *The obvious next steps on screen*; and the open items that fit this area: *A project's "what the assistant knows"*, *"Overlaps with …"*, *The Quality screen*, *Where a fact came from* (29), *A series page* (30), *A date move isn't news*, *Settings*, *Learning on screen*, *Action items and open questions, cleaned up*, *The app's own kit*, *Found by the phase A journeys*.
    - *Also covers* (the designer's lessons, 2026-10-19): *An unknown status stays unknown, and an add from a link says when nothing could read it* (design 6.19).
    - *Exit:* the tests each item names pass, and the browser test of every main screen at several widths shows no sideways scroll; the owner works through their own open items on a laptop and a phone.

6. **B-6b The rest of B: Today and the shell** (12 open items; built on 2026-10-20 apart from what each item says is left; size: about one to two days)
    - *Covers:* from *Wave 6* (phase B): *The Today rows as the mockup review set them*, *This week at every width*, *Notifications for "needs you" only*, *The walkthrough's look*, *An unnamed assistant reads as one*, *The header shows the assistant is alive*, *Words and accessibility throughout*; and the open items that fit this area: *After a move* (27), *Held for a look* (28), *Work*, *Setup guide*, *The rest* (Stages board, phone review mode, hand-in drawer, Ask as a side pane), *Review after the first Go*, *When something is due a follow-up*, *Top priorities, always current*, *Copy puts the formatted message and its plain text on the clipboard together*, *What the work version's screens show*.
    - *Exit:* phase B's exit test: the owner reviews every screen on a laptop and a phone; checklist items C1 to C53 and N1 to N8 are marked Done or explained (`docs/project/ui-review-status-2026-10-20.md`), with screenshots; the journey tests run against the new screens.

7. **UI gate: the UI/UX designer's re-review (done 2026-10-20: its feedback is recorded in `ui-rereview-2026-10-20.md`)** (0 open items)
    - *Covers:* *The UI/UX designer's re-review* (phase B, last group): once B-6b is pushed, the main session messages the session titled "UI/UX design review" with the commit to review and the list of UI changes since its last review (`docs/design/CHANGES.md`); it builds and reviews the screens itself. The ping carries what the reviewer asked for (2026-10-20): the branch and commit, the main session's own Done / Partial / Not done table for C1–C46 (each row citing its test, audited against the code by a subagent first), its bug list re-checked, and every place the build chose differently from the review, with why.
    - *Exit:* its feedback is received and recorded in one file in `docs/project/`.

8. **B-7 UI/UX feedback** (1 open item, with seven of its thirteen sub-items checked off; size: about two days)
    - *Covers:* *Build the UI/UX designer's accepted feedback* (phase B, last group): the whole re-review of 2026-10-20 (`docs/project/ui-rereview-2026-10-20.md`), its demo data, and the owner's learning-run fixes from B-6b, in four briefs: records and item text (§3.2, §3.5) beside the learning fixes, then Today (§3.1, §3.4, §3.12, §3.14, §3.15) beside the rest of the P2s and tables (§3.3, §3.6–§3.11, §3.13), then the demo data.
    - *Exit:* each accepted item has its test, and the owner sees the changed screens.
    - *Then* (owner, 2026-10-20): once B-7 is pushed and green, the UI/UX reviewer gets the next round, and the paid 1.0
      plan on `claude/paid-1-0-plan` (`docs/project/business-model.md`, its P25) is merged into this branch and folded
      into the roadmap as P25 says.

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

16. **I-1 Installers, name and icons** (16 open items; size: about two sessions, the old estimate for all of phase I)
    - *Covers:* every installer item of phase I: the CI build from a tag, install places, app-data places, opening the app, add-ons beside the app, updates, signing, *A name and icons*, *Nothing made-up ships*, *How it is built*, *Add-ons in an installed app*, the system vault, the *Exit test*; and *A launcher for people who never open a terminal* (phase B, moved here).
    - *Exit:* phase I's exit test on a clean Mac and a clean Windows machine: download, install, open, finish the walkthrough to the first result, quit, reopen with the data still there, update, uninstall with the data kept.

17. **I-2 The tester milestone and the website** (5 open items; size: about half a day, then the owner's decisions)
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

25. **L-more The rest of learning (refined when reached)** (11 open items; size: about 4 sessions, as the phase states)
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
| O3 | **First run made 2026-10-20 (the results and the fixes are under "Found by the owner's first real use", B-6b); left: the owner re-runs the failed cases with `--case-failed` after batch B-7.** **One run of the learning tests, at the end of batch S1-1:** the golden set, the harder set, the existing learning pairs and the twenty promise pairs, on the owner's account, 3 runs per case, on the commit that S1-1 pushes. Compared case by case with O1 and O2. It costs the owner's AI allowance once, and it gives the gate week a clean "before". Steps below. | The owner's computer, with the account used for O1 and O2 | The gate week's start, and real use: the comparison has to exist before either starts. | Phase B, which goes ahead meanwhile. |

| M5 | **Before the free core release:** make the working repository private and publish the open core from it as a fresh public repository at each release; first, a session lists what in `docs/project/` and the design is the owner's own business, and the owner decides what the public core carries (`business-model.md`) | The owner's GitHub account | The free core release (I-3) | Everything before phase I |
| M6 | **Before the free core release:** the website's pages for it: download, privacy policy, terms (open promise P24; I-2) | The website's session | The free core release (I-3) | Everything before phase I |
| M0 | **Before anything is sold:** read the intellectual-property and outside-business clauses of every employment or contractor agreement, or a short consult; R9 is reopened until then | The owner's agreements | Phase T (Thimbleby+) | The free core release |
| M1 | Ask Google whether a local app sending mail to the person's own AI account is in scope of the yearly assessment (CASA), and what its user-data policy requires for AI processing; get an assessor's quote | A Google account for the app | Phase T's one-click Gmail sign-in, and the price | The free core: it connects Gmail through the person's own registration |
| M2 | Microsoft publisher verification for the add-on's registration | The website and its privacy policy | Phase T's one-click Outlook sign-in | The free core |
| M3 | Signing: Apple's developer programme and Windows signing (about $219 a year) | Payment | Selling (phase T) | The free core and testers ("unsigned to start", 2026-10-17) |
| M4 | A payment service that is the merchant of record, issuing the licences | M0 | Phase T's licence | The free core |

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

**Where phase B stands (2026-10-20).** Waves 1 to 4 are built, and so is every defect the outside reviews found
(roadmap-done.md, "Phase B"). Waves 5 and 6 (batches B-5, B-6a and B-6b) were built on 2026-10-19 and 20 apart from the
items below, each of which says what is built and what is left; the UI/UX designer's re-review is done and recorded (UI
gate), and batch B-7 builds its feedback, the first-run review's and the functional designer's answers F15 to F25: seven
of its thirteen sub-items are built and checked off, and the rest wait on browser checks that are written and not yet
run, a sweep over more views, the reviewer's next look and the owner's re-run of the failed learning cases. The owner
holds feedback until phase B is done and then tests it all at once ("im going to wait on any other feedback until we
get all the updates done"); the message then gives the update commands and a walkthrough.

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
uncertain remote results, revoked sign-ins, hostile content redirecting an act); (decided 2026-10-20: the
installers ship the mail and calendar add-ons ready to sign in, see the I-1 item); and the owner's target of sharing installers with a small invited
group on 2026-10-20, which the plan's order (B, S, then I) and the integrity items above don't yet support.

**The waves left** (waves 1 to 4 are in roadmap-done.md):

3. [B-5] **Wave 5, sources and accounts:** open promise P17 (.ics calendars, full featured: a pasted link, a file on disk,
   invitations as calendar entries, repeating events expanded, Outlook time zones, attendees) and P18 (several accounts
   of one service at once, each source picking its account; a plugin API change told to the mail add-on's builder).
   P16's leftovers too: an add-on's own secrets and the backup key typed on the screen.
   *P17 built (B-5):* a link or a file on this computer, repeats expanded, invitations, Outlook zones, attendees, a
   changed or cancelled date on its own entry, a promise due at it following and listed in Since yesterday
   (`tests/test_ics_full.py`). Left of P17: an invitation attached to a mail, and a hosted app's upload instead of a file.
   *P18 built (B-5):* tokens kept per account, the old single file migrated, each source reading as its account (a
   list on its form), signing one account out pausing only its sources, sources a new account starts reading as it,
   `context.account` (plugin API 0.3.82) (`tests/test_sign_in_accounts.py`, `web/src/components/SignIns.test.tsx`,
   `web/src/components/Sources.test.tsx`). Left of P18: the note to the mail add-on's builder (drafted at the end of
   `plugin-answers-34-48.md`, sent with the weekly plugin round), a renewal warning for an account other than the
   first, and the "not reading" line and setup step per account. *P16's leftovers built:* see the checked P16 item.
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
`reviews/ui-ux-2026-10/` are marked Done or explained, with screenshots in `reviews/ui-ux-2026-10/after/`. The re-review
added C47–C53 and the first-run review N1–N8 (`reviews/ui-ux-2026-10/rereview-c8f8e18/README.md` §5,
`reviews/ui-ux-2026-10/first-run/README.md`); the build's status for all of them is in
`docs/project/ui-review-status-2026-10-20.md`.

From L3 (design 7.18):

From the UI designer's answers to questions 25 to 32 (2026-10-16; `reviews/ui-ux-2026-10/answers-25-32.md`, mockups in
`reviews/ui-ux-2026-10/mockup-round-25-32/`; each answer has its layout, exact wording, edge cases and the test for done):
- [ ] [B-6b] **28 Held for a look**: the action as a question, reason and evidence first, the primary button names the result,
  the other answer a visible button.
  *Built (wave 4):* `tests/test_held_ask.py`, `TodayRecords.test.tsx`. Left: "Drop it and draft the note", which waits for the publisher (S1b).

From the original designer's lessons of 2026-10-14:
- [ ] [B-6b] **Work:** What changed and Follow-ups as list | detail, with a "to send" marker on each action row (from L0).
  Sources shows on a source's row when its mail couldn't be sorted and why (from L0). Waiting to go out is a designed screen with its empty
  state.
  *Built (B-6b):* the "To send" marker on an open action's row in What changed and in To-dos and questions
  (`tests/test_to_send_marker.py`, `web/src/components/OpenItems.test.tsx`, `web/src/components/WhatChanged.test.tsx`); a
  source's row saying why some of its mail wasn't sorted (`tests/test_mail_sorting.py`,
  `web/src/components/Sources.test.tsx`); Waiting to go out as a designed empty state
  (`web/src/components/WaitingToGoOut.test.tsx`). *Left:* What changed and Follow-ups as list | detail: their rows
  still open in place, and only Projects and People use the shared detail pane (design 7.17).
- [ ] [B-6a] **Settings:** nav | form | help, save bar or autosave with Undo, "Changed · Reset", and pickers for time zone,
  language, money and dates. Appearance has the contrast warning; admin sections sit inside Settings.
  *Built (wave 3):* nav, saved as made with Undo, "Changed · Reset", help beside the field, `Settings.test.tsx`, `shell.spec.ts`. Left: the contrast warning in Appearance and the pickers for money and dates, to check and finish in wave 6.
  *Built (B-6a):* the contrast warning in Appearance and the date-format list (`web/src/lib/theme.test.ts`,
  `web/src/components/Settings.test.tsx`). *Left:* a money list needs a currency setting, which doesn't exist yet.
- [ ] [B-6b] **The header shows the assistant is alive** (the original designer's lessons from running, 2026-10-13): one short line, always ("The assistant ✓ last run 9:42", the
  account's own label, never a model's name), with today's runs per account, what's queued and the fallback order in its
  tooltip; amber or red when something is wrong. The held-work and paused lines cover the bad case; this covers "is it
  alive?". The header is two rows when it needs them (title, views and primary buttons on top; status and the person's
  links small below), tested at about 1,000 px wide. (The line and the two-row header below 1280px are built under "Ready
  for real use"; what is left here is the final layout and a browser check of the header at about 1,000 px wide.)
  *Changed (B-7, `docs/decisions.md`, 2026-10-20):* the header is one row at every width; below 1440px the assistant's
  state is a section of the status chip's popover.
  *Built (B-6b, B-7):* the final layout, one row with the alive line beside the status chip from 1440px and in the chip's
  popover below it (`web/src/shell/Header.test.tsx`: "the assistant's alive line is in the header beside the status
  chip", "below 1440px the assistant's state moves into the status chip's popover, as on the phone, and the line beside
  the chip is gone"). *Left:* the browser check of the header at 1000, 1100 and 1200px (`web/e2e/shell.spec.ts`: "the
  header is one row, with every control inside the window"), written on 2026-10-20 and not run.
- [ ] [B-6b] **The rest:** the Stages board, the phone review mode, the hand-in drawer, Ask as a side pane on wide screens.
  *Built (B-6b):* the stages board (`web/src/components/StagesBoard.test.tsx`, `tests/test_stage_cards.py`), the hand-in as a
  drawer and Ask as a pane from 1440px (`web/src/components/AskPane.test.tsx`), and the phone's review mode on What
  changed (`web/src/components/WhatChanged.test.tsx`: "review mode on a phone"). *Left:* the review mode on the other Work
  lists, which comes with them becoming list | detail (the "Work" item above).
- [ ] [B-6b] **Review after the first Go** (found by journey J2): What changed shows "5 new · Show" with Needs attention
  empty while Needs you counts 5, and only one review opens by default, so an owner question can sit closed. The
  Today redesign makes the first results one clear list. After Remove, the add-on's row vanishes along with its note.
  *Built (B-6b):* the first results as one list, every open question open (`web/src/components/WhatChanged.test.tsx`).
  *Left:* the removed add-on's row and note going together (after Remove the row stays and says "<name> is removed.
  Restart to finish." (`web/src/components/Addons.test.tsx`); whether the row also goes from the list was not checked
  in a browser).
- [ ] [I-1] **A launcher for people who never open a terminal** (owner, 2026-10-13): moved to phase I, where the macOS and
  Windows installers give the app icon and Start menu entry.
  The UI/UX reviewer's first-run review (2026-10-20, F1, `reviews/ui-ux-2026-10/first-run/`) sets the bar N1: a person who
  has never used a terminal installs and opens the app from a downloaded file, before any non-technical tester.
- [ ] [I-1] **Mail and calendar connect with a sign-in on a fresh install** (the first-run review's F3 and N2): Gmail or
  Microsoft 365 connects with a sign-in, with no add-on screen, restart or server setting on the person's path; "Other
  email" fills the server from the address; server, port and secret settings under Advanced in plain words; the
  unverified-app warning explained where it appears. *Decided (owner, 2026-10-20: "anything that makes a non technical
  user life easier"), narrowed the same day (core first):* the installer ships the mail and calendar add-ons installed
  and turned on, **ready to set up**: their tiles are on the setup step from the first start, and they connect through a
  registration the person makes with plain numbered steps (Gmail's set to "In production"), or for other mail an app
  password over IMAP. Gmail's app passwords aren't counted on (password sign-in ended for Workspace accounts; personal
  Gmail unconfirmed, `business-model-delta-gmail-later.md`): the owner's live check says whether the steps may offer
  them second, so the Gmail steps are written as the app's best walkthrough, a screenshot per step. One-click sign-in through the add-on's own registration is Thimbleby+ (phase T), since it needs Google's yearly
  assessment. To be built as a generic feature (nothing of it exists in the code yet: no bundling step or setting): the release build
  bundles the add-on packages a repository variable lists (as the catalog and feedback addresses are filled in), installs them with the app
  and turns them on in a new workspace with no restart; this repository names none of them. The add-ons stay in their
  own repository and release there.
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
  *Built (B-6a):* To-dos and questions under Work, with filters, edit, reassign, merge, hold and drop from the row with
  Undo; stale and no-owner lines on Today; a note box on every action button; the action-stands-alone lint
  (`tests/test_open_items.py`, `tests/test_action_stands_alone.py`, `web/src/components/OpenItems.test.tsx`,
  `web/src/components/NoteBoxEverywhere.test.tsx`). *Left:* notes on hover and the parent project tag on Follow-ups and
  Today rows, Reassign on Waiting-on-them rows, and the owner's exit check on a laptop and a phone.
- [ ] [B-6b] **Top priorities, always current** (owner, 2026-10-13: the version used at work has "a constantly updated top
  priority items" list). A short ranked list on Today across every project, rebuilt as records change and ranked by
  rules (due and overdue, at risk, blocked, waiting on the person, the project's priority), never by an AI call. Shaped
  by the owner's screens of the work version (open promise P11, received 2026-10-13): one row per thing with a date chip
  (red when due), a verb first, **one line per person** ("<person>: send 1 question, follow up on 3 waiting up to 5
  days", with the items in the line's tooltip; the original designer's review: two lines per person made seven lines
  where five said it all), "Review and publish 3 drafts", who suggested it and why on the second line ("The assistant suggests · no answer
  yet"), and the row's actions (Mark done, Reassign, Hand to the assistant). Dated entries whose day has passed and
  that aren't marked done are lines ("passed, not marked done"), and the next two weeks' entries are listed after.
  *Built (B-6b):* the ranked list, one line per person, passed dated to-dos and the next days (`tests/test_top_priorities.py`,
  `web/src/components/TopPriorities.test.tsx`).
  *Changed (B-7, decisions 2026-10-20: the re-review's §3.4 and the designer's F16 and F24):* Top priorities is context
  with no buttons and no menu; each entry's words link to its queue line or its record, so "Mark done", "Reassign" and
  "Hand to the assistant" on its rows are not built, by decision (the queue is the place to act). The order is overdue,
  waiting on the person, due within the window, at risk, and a blocked to-do appears as the question or action that
  holds it up (`tests/test_top_priorities.py`, `tests/test_chase_moves_to_the_blocker.py`,
  `web/src/components/TopPriorities.test.tsx`: "an entry has no buttons and no menu, only its words as a link").
  *Left:* the second line's "who suggested it" ("The assistant suggests · no answer yet"), which is not built (design
  7.7 says so).
- [ ] [B-6b] **Copy puts the formatted message and its plain text on the clipboard together** (owner, 2026-10-13: the work
  version opens a generated page with a copy button; decided on review, design 7.5): the preview on screen is what is
  pasted, mail and documents get the formatting, chat gets clean plain text, and the menu has Copy as plain text. Every
  Copy in the app uses it (questions, follow-ups, the briefing, reports). A browser test pastes both versions and checks
  the formatted one escapes every piece of text.
  *Built (B-6b):* one helper, `web/src/lib/copy.ts`, used by every place the app copies (the preview is what is pasted,
  formatted and plain together, "Copy as plain text" in the menu, every piece of text escaped, a refused copy selects the
  text) (`web/src/lib/copy.test.ts`, `web/src/components/FollowUps.test.tsx`). *Left:* the browser test that pastes both
  versions (`web/e2e/acceptance.spec.ts`, 3d) is written and has not been run.
- [ ] [S2] **The Monday briefing, in the app** (owner, 2026-10-13: the work version has "monday briefings"). *Moved to phase
  S1 (2026-10-17), as the weekly form of the morning brief; the description below stands.* On the first
  open of the week (the day is a setting), a briefing in this order (the designer's notes, 2026-10-19; design 6.35):
  a copy-ready message to whoever the person reports to (stance *I report to them*, 6.34; a draft under the draft
  rules, with its estimate); "this week" through the last working day: promises due by owner with overdue first,
  questions to send, answers to chase, decisions waiting, built from the records by rules; and three to five goals the
  person confirms, kept for the week. Nothing already on Today is repeated. Sending it to the person is phase E.
- [ ] [B-6b] **What the work version's screens show** (owner's screens, 2026-10-13; the screens hold real names, so only
  what they do is written here). *Built (B-6b), checked off in `roadmap-done.md`:* Follow-ups by person, or by project;
  Projects at a glance; links to the person's own pages; a meeting added in one line; never raw data on screen. Two
  sub-items are open:
  - [ ] **Hand an action to the assistant** from its row (beside Mark done and Reassign): the assistant drafts the work
    (a message, a list, a page) as a pending draft for the person, under the usual estimate and approval. The action
    stays the person's until they close it.
    *Built (B-6b, B-7):* the core draft task kind `action-work`, estimated, held for the go and filed as a pending draft,
    from the row's menu in To-dos and questions and in Follow-ups; the action stays the person's; keeping part or
    discarding the draft records a signal; a Copy beside the draft keeps it as copied and the action stays open
    (`tests/test_action_work.py`, `tests/test_action_work_api.py`, `tests/test_approved_draft_is_not_done.py`,
    `web/src/components/HandToAssistant.test.tsx`). *Left:* an evaluation case for the task kind (no harness step starts
    from a handed-over action).
  - [ ] **The hand-in takes a pasted screenshot** as well as text and files. Check first what the drawer does today.
    *Built:* the check of what it does today: a pasted picture is told plainly it can't be read yet, and the box keeps
    its words (`web/src/components/HandIn.test.tsx`). *Left:* reading a picture.
- [ ] [B-6b] **The walkthrough's look** (owner, 2026-10-12: "this looks rough"):
  - fields sized to what they hold, not the full page width;
  - one clear primary button per screen ("Save and continue"), with Skip as a quiet link;
  - the step list without "Not done yet" on every row;
  - the current step marked as "you are here", not styled like a focused button (owner: it read as focus). The
    cursor already starts in the screen's first field (`Walkthrough.test.tsx`);
  - the page using its width.

  It goes through the redesign's components and screenshots like every other screen.
  *Built (B-6b, B-7):* the step list without "Not done yet" (only done and skipped are marked), "You are here" on the
  current step with a bar and no fill, one primary on every screen (Continue; "Save and continue" on You) with "I'll do
  this later" or Skip beside it, and the cursor in the first field (`web/src/components/Walkthrough.test.tsx`, "the
  look"). *Left:* the fields sized to what they hold and the page using its width, which only a browser shows
  (`web/e2e/panes.spec.ts`, "the walkthrough's look": it passed in the browser run at `ec37749` and has not been run since
  B-7 changed the step's buttons).
- [ ] [B-6a] **Follow-ups' Later** (7.5): questions held for a meeting or the weekly note (`question.held_for`), kept out of To
  send.
  *Built (B-6a):* held for a meeting, a series or a day, out of To send until then, "Send now" in its menu
  (`tests/test_followups_later.py`, `web/src/components/FollowUps.test.tsx`). *Left:* holding a question for the weekly
  note.
- [ ] [B-6b] **Notifications for "needs you" only** (7.19): opt-in, the Decide group's items, quiet hours. The targets are
  notification channels the phone already receives anywhere: the browser, mail to the person themselves, or a webhook
  (chat app or push topic). Each is checked with "Send me a test" and sends only to the person, a count by default.
  *Built (B-6b):* opt-in and off by default (`ui.notifications`); one notice, a count and never what an item is about, when
  an item enters Today's Decide group that the person has not been told about; quiet hours that hold it; a failed note
  tried again with the reason in Settings; the browser's own notification and a webhook (the person's own address kept
  as a secret reference), each with "Send me a test" (`tests/test_notifications.py`,
  `web/src/components/Notifications.test.tsx`). *Left:* mail to the person themselves (it comes with mail sending,
  S1b-2; Settings lists it as coming), and titles for an allowed data level (`detail`, `allowed_data`).
- [ ] [B-6b] Words and accessibility throughout: the microcopy table in the review, and axe in light and dark at four widths.
  *Built (B-6b, B-7):* the rows of the microcopy table that remained (a change's line says what was done, Send back asks what
  to do differently, "Who may see this?", one marker for outside material, Add-ons' sentence)
  (`web/src/components/WhatChanged.test.tsx`, `web/src/components/ActionReview.test.tsx`,
  `web/src/components/HandIn.test.tsx`); the wording check reaching the setup path's labels from schemas, connectors and
  add-on manifests (`tests/test_setup_path_words.py`); axe in light and dark at 390, 1024, 1440 and 1920 for every main
  screen, the board, the hand-in drawer, Ask and the review mode, run and passed at `ec37749`
  (`web/e2e/a11y.spec.ts`, `web/e2e/panes.spec.ts`). *Left:* axe over what B-7 changed: `a11y.spec.ts` gained checks on
  2026-10-20 and has not been run since.
- [ ] [B-6b] **Found by the owner's first real use (2026-10-20):**
  - adding a second AI account closes its form once saved; the account's row shows its checks as they run ("Checking for
    harder work…") and the outcome, and an account whose sign-in can't be told apart says so with "Use it anyway"
    (the screenshot: "Adding…" held for minutes while the checks ran);
    *Built (B-6b):* `web/src/components/AccountChecks.test.tsx`, `web/src/components/WelcomeAiDrawer.test.tsx`;
  - a plain calendar entry is filed by rule with no AI run and no Review line, if the designer agrees (question F20);
    *Built (B-7):* the designer agreed (F20) and nobody else invited, no description and no promise's date makes an entry
    plain (`tests/test_plain_calendar_entries.py`);
  - the two follow-up settings (`steward.chase_*_days` and `ui.followups.*_days`) become one, with the impact noted;
    *Left:* both families still exist: the promise lines read `steward.chase_*_days`, and Top priorities, Today's nudge
    lines and the Follow-ups pills read `ui.followups.*_days` (design 6.9 lists them as not one rule yet);
  - the toast-at-390px and the Today-cursor browser tests are made robust under load (each failed once under load and
    passed alone);
    *Built:* both tests are rewritten (`web/e2e/shell.spec.ts`). *Left:* they have not been run since.
  - **date words the rules can't read** (the owner's learning run, 2026-10-20: 6 of 11 misses): `engine/due_phrases.py`
    reads "the 25th", "by the 30th", "due Oct 22" and their kin, and words it still can't read keep the model's own
    date marked to check instead of dropping it; the case `quoted-thread-action-exists` expects the move held for Keep
    that the designer's correction set (2026-10-19), not a direct date change;
    *Built (B-7):* `tests/test_due_phrases.py`, `tests/test_promises.py`, `tests/test_learning_run_b7.py`;
  - **the rest of the owner's learning run (2026-10-20; 81% of 214, 79% harder, 53% pairs, 30% harder pairs; one run
    per case). About 7 cases that passed in O2 now fail: a regression from S1-1 (date words override the date and an
    unread phrase drops it; one promise per owner splits a shared task, which older cases still expect as one):** a
    condition ("once the keys arrive", "after the workshop") goes in the promise's due words (8 misses); a reply that
    doesn't answer is `action.news` (7 misses); the date reader takes a leading "on" or "due" and ordinals (about 8);
    then the owner re-runs the failed cases with `--case-failed`. Built in batch B-7 (owner, 2026-10-20: "include the
    ai fixes").
    *Built (B-7):* a condition keeps its words as the due words with no date
    (`tests/test_promises.py::test_a_condition_keeps_its_words_and_has_no_date_even_when_the_model_gave_one`), a reply
    that doesn't answer is news and never an ending, and the date reader takes a leading "on" or "due" and ordinals
    (`tests/test_learning_run_b7.py`, `tests/test_due_phrases.py`). *Left:* the owner's re-run of the failed cases with
    `--case-failed` on the commit that batch B-7 pushes, which is this item's acceptance; and the split of a shared
    task into one promise per owner, which no recorded fix covers (check it on that re-run);
  - `cockpit evaluate` waits for the network as the app's own runs do (a lost network uses up no try and fails no case),
    and the pair harness's practice copies never hold the main account as an unchecked backup (fixed:
    `tests/test_catch_up_learning.py::test_the_main_account_listed_again_as_its_own_backup_is_never_held_as_an_unchecked_backup`);
    *Built (B-7):* the wait (`tests/test_evaluate_network.py`).

The journey tests from A3 run against the new screens as they land.

From the owner (2026-10-19), after phase B's screens and before the gate week:
- [ ] [B-7] **Build the UI/UX designer's accepted feedback** (owner, 2026-10-19): the feedback the owner accepts from that
  re-review is built before the gate week, each item with its test. *Received 2026-10-20 and accepted in full*
  (`docs/project/ui-rereview-2026-10-20.md`; the review's sections are cited as §3.x; choices in `docs/decisions.md`,
  2026-10-20). Each sub-item is done when its test passes. *Built (2026-10-20), checked off in `roadmap-done.md`:* no
  bookkeeping in item text; one row per thing; demo data for answers 27 to 31; first run for a person with no IT
  background; the functional designer's answers to F15 to F25; "Mark this closed" isn't "done"; outward material never
  names the assistant. What is left:
  - **Record pages and every view say names, dates and words** (§3.2, C19, C48): references resolved to names, dates
    formatted, enums as labels, no help text on view, details ordered (name, role, organization, how to reach, the
    rest), meta joined only from non-empty parts, activity worded "Quill changed the due date of …" with field labels,
    links by title with the domain as a hint; a sweep test over every view and record kind that fails on an id, an ISO
    date, an empty separator or a raw enum value.
    *Built:* references as names, dates formatted, choices as labels, no help text while viewing, details ordered, meta
    joined from the parts that exist, activity worded with the assistant's name and the field's label, links by title with
    the domain beside it (`web/src/components/RecordPageNames.test.tsx`, `web/src/components/RecordPageRecords.test.tsx`,
    `web/src/components/OpenItems.test.tsx`, `web/src/components/WhatChanged.test.tsx`, `tests/test_record_page.py`);
    the sweep over every kind of record's page and the People, Projects, open to-dos and Unfiled lists
    (`web/src/components/RecordSweep.test.tsx`). *Left:* the sweep over the other views (Today, What changed,
    Follow-ups, Sources, Settings and the rest): it covers record pages and four lists, not "every view".
  - **Today's first screen** (§3.1, C47): the backup reminder is an At risk line plus the status chip, This week is a
    rail panel at every width, and at 1280×720 with setup unfinished the first queue line is at most 260px down with at
    least six lines visible (at most 200px with setup done), checked in `shell.spec.ts`.
    *Built:* the backup reminder as one At risk queue line beside the status chip, with no bar
    (`tests/test_follow_up_lines.py`, `web/src/components/TodayFirstScreen.test.tsx`); This week as a rail panel at every
    width (`web/src/components/Today.test.tsx`, `web/src/components/TodayFirstScreen.test.tsx`). *Left:* the browser
    check that the first queue line is at most 260px down with six lines visible at 1280×720 (200px with setup done)
    (`web/e2e/shell.spec.ts`): written on 2026-10-20, not run.
  - **Tables beside the detail pane** (§3.3, C49): no break inside a word, columns by priority, the pane overlaying the
    table when even those don't fit, no per-row Details button, the People organization filter sized to its content
    and its Organizations list as a table.
    *Built:* no break inside a word (headers on one line, a long value ending in an ellipsis with its whole value as its
    title), columns by priority beside the pane, the pane overlaying the table when they don't fit, no per-row Details
    button, the People organization filter sized to its content, Organizations as a table, a row or its name opening the
    pane (`web/src/components/TablesBesidePane.test.tsx`). *Left:* the browser check at 1440px that no header or cell
    breaks inside a word (`web/e2e/tables.spec.ts`): written, not run.
  - **The P2 findings** (§3.6 to §3.15, C52): What changed opens the first item and edits in the meta line; the header
    below 1440px puts the assistant's state in the status chip's popover and "Your pages" in the person's menu, and the
    ⚠ gets a label or joins the chip; no visible interactive element under 24×24 (checked in `a11y.spec.ts`); only the
    weight tokens (a stylelint rule); the compare page and account row say "Not measured yet"; setup's primary is
    Continue, Skip a secondary button, amounts in currency fields; "Add to agenda" opens the drawer; the inspector
    header on one line, Send back at 72ch with its reason, the hand-in's "Whose words" as a segmented control; the
    phone's rail panels one line each below the queue; review lines tagged "Outside" with the full phrase as its name.
    *Built:* What changed opening the first item and editing in the meta line (`web/src/components/WhatChangedFold.test.tsx`);
    the one-row header, the assistant's state in the status chip's popover below 1440px, "Your pages" in the person's menu
    and Missed one with its words (`web/src/shell/Header.test.tsx`, `web/src/shell/HeaderLinks.test.tsx`); targets of at
    least 24px (`web/src/theme/targets.test.ts`); only the weight tokens (`web/src/theme/stylelint-rules.test.ts`); "Not
    measured yet" and "Nothing measured yet" (`web/src/components/AiCompare.test.tsx`); setup's Continue as the primary,
    Skip a secondary and amounts as money fields (`web/src/components/Walkthrough.test.tsx`); "Add to agenda" opening the
    drawer and an empty Agenda as one line (`web/src/components/TodayRail.test.tsx`); the inspector header on one line,
    Send back at 72ch with its reason and "Whose words" as a segmented control (`web/src/components/SmallPoints.test.tsx`);
    the phone's rail panels one line each and review lines tagged "Outside" (`web/src/components/TodayFirstScreen.test.tsx`).
    *Left:* the browser checks written on 2026-10-20 and not run: no visible interactive element under 24×24
    (`web/e2e/a11y.spec.ts`) and the header as one row at 1000, 1100 and 1200px (`web/e2e/shell.spec.ts`).
  - **The reviewer's further feedback** (owner, 2026-10-20: "provide the UI/UX agent the next batch when you can because
    it already has more feedback"): received (`reviews/ui-ux-2026-10/first-run/`; built in "First run for a person with no
    IT background", checked off in `roadmap-done.md`). *Left:* when B-7 is pushed and green, the reviewer gets the commit,
    the status for C1–C53 and N1–N8 (`docs/project/ui-review-status-2026-10-20.md`) and every place the build chose
    differently.
  - **The learning-run fixes** (owner, 2026-10-20: built in this batch): the B-6b items "date words the rules can't
    read" and "the rest of the owner's learning run", then the owner re-runs the failed cases with `--case-failed`.
    *Built:* the fixes, each with its test (see "Found by the owner's first real use", B-6b). *Left:* the owner's re-run
    of the failed cases, which is this sub-item's acceptance, and its result.

- [ ] [B-8] **Build the UI/UX designer's review of batch B-7** (received 2026-10-20 at `46cc3ea`,
  `reviews/ui-ux-2026-10/rereview-46cc3ea/README.md`; the owner's standing answer, 2026-10-20: "give them what they
  want"). B-7's six deliberate differences were accepted; F25's yes is accepted on two conditions, which are built here.
  Each sub-item is done when its test passes:
  - R1: no record id in any title the person reads (Today, its inspector, What changed, Follow-ups): a line is titled by
    its item ("Drop 'Settle the endpaper color'?"); an id in a title is refused as an invariant, and the sweep reaches
    those screens (check C54). **Built (wave 1):** `tests/test_titles_without_ids.py` (labels by title, the kind in words
    when there is none, a held and a review line, the invariant, the sweep of an old label and of a stored title with Undo),
    `web/src/components/TodayRecords.test.tsx` ("no line of Today shows an id"), `web/e2e/shell.spec.ts` ("no Today line,
    inspector heading or What changed title holds an internal id": written, not run). *Left:* the web sweep
    (`RecordSweep.test.tsx`) does not yet draw What changed and Follow-ups from data (C48);
  - R2: a held line is asked as a question ("Close 'Send two spine options'?") with the same two result buttons in the
    line and the inspector ("Close it", "Keep it open"); its meta keeps the quote and who said it, the rest moves to the
    inspector (check C55). **Built (wave 1):** `web/src/components/TodayRecords.test.tsx` (every ask on the line, no
    "Keep:" or second question), `web/src/components/TodayPromises.test.tsx` (the endings read from an input, Close it and
    Keep it open with Undo), `web/src/components/WhatChanged.test.tsx` ("a held drop on the change's card has the line's two
    buttons, and who was told leads it"), `tests/test_held_ask.py`;
  - R3: every Today line's meta is one line, cut with an ellipsis, and "Outside" folds into the pill column, so six lines
    fit at 1280×720 (checks C47, C56). **Built (wave 1):** `web/src/ui/Row.test.tsx`,
    `web/src/components/TodayRecords.test.tsx` ("Outside in the pill column, meta one line"), `web/e2e/shell.spec.ts` (six
    lines in full at 1280×720 with the demo's longest held and moved lines, each meta one line: written, not run; the
    same lines measured in a browser by hand put the sixth line's bottom at 679px of 720). *Left:* the stopped-work lines
    (`HeldLines`) still wrap their second line, because it says why and until when and has no inspector to hold the rest;
  - R4: on a new workspace the header has no "Missed one" until there is something it could have missed, and the
    workspace's new name shows without a reload. **Built (wave 1):** `web/src/shell/Header.test.tsx` ("a new workspace
    offers no Missed one until something has been read or handed in"), `web/src/App.test.tsx` ("a new name for the
    workspace shows in the header at once");
  - R5: the mail step on a fresh install says one sentence, with one button and one way out. **Built (wave 1):**
    `web/src/components/Walkthrough.test.tsx` ("with no service listed and nothing read the step is one sentence and one
    button");
  - F25's conditions: the yes is asked in the AI step right after the key check passes, and Continue can't skip it
    silently; when it was skipped, Today says "Let <account> read your work mail and notes" with Allow; the browser
    tests' fixture has a stand-in account so the yes can be captured. **Built (wave 2):** `tests/test_work_access.py` (the
    line for an account the person said Not now about, none for one never asked or one that may read internal material,
    Allow with its read-back and Undo, a higher level kept, the guide records Not now), `web/src/components/WelcomeAi.test.tsx`
    ("Allow lets the account read open and internal material; Not now leaves it at open material only", with `work_data`),
    `web/src/shell/HeldLines.test.tsx` (the line and "Allow gives the yes … and Undo puts the answer back"). The step
    already asked the yes after the check and kept Continue disabled until it was answered
    (`web/src/components/WelcomeAi.test.tsx`: "the question names the account and its sign-in…"). *Left:* the browser check
    `web/e2e/work-access.spec.ts` and the server's `--standin-account` are written, not run;
  - R6–R11: the Done step's empty cards; the series page's side panel (labels above values, an item not listed in both
    Agenda and Next); the rules line's weight and pill; 24px hit areas for checkboxes; no "From: <person>" titles in What
    changed; shorter Top priorities wording. **Built (wave 2):** R6 `web/src/components/Walkthrough.test.tsx` ("each step
    is one compact row…"); R7 `web/src/components/SeriesPage.test.tsx` ("an item listed under Agenda is not listed again
    under Next…", "a person whose only items are on the agenda…") and `web/src/theme/targets.test.ts` ("a side panel puts
    each label above its value…"); R8 `web/src/shell/HeldLines.test.tsx` (the pill "Rules"; the weight is a stylesheet rule,
    not measured); R9 `web/src/theme/targets.test.ts` ("a checkbox or radio is a 24px control itself…"); R10
    `web/src/components/WhatChanged.test.tsx` ("a change from an email is titled by Today's rule…"); R11
    `web/src/components/TopPriorities.test.tsx` ("a person's row reads name · 1 overdue · 1 waiting 10 days…"). *Left:* the
    browser checks added for R6, R9 (a11y.spec.ts measures the element now) and R10 are written, not run; no layout was
    measured in a browser for R6, R7 and R9 (none is available here), so the CSS follows the review's numbers and the
    stylesheet tests;
  - CI's python-later job (the tests with the clock 40 days ahead) finishes: on `46cc3ea` it ran past 30 minutes with
    every other job green and was cancelled, as the same run hung locally at 94% with three workers and passed with two.
    The job now has a time limit and prints the stack of any test past five minutes; the hanging test is found and fixed,
    and the job passes on the batch's commit. *Found and fixed (2026-10-20):* the hang was faketime's, not a test's
    (`tests/test_events.py::test_wait_returns_when_the_counter_moves` waited for a deadline faketime had moved 40 days
    out), and keeping its timing clock real broke short sleeps instead (33 failures at `0f37be4`), so the job moves the
    date inside each test process with the time-machine test library (`TEST_CLOCK_DAYS_AHEAD`, `tests/conftest.py`):
    the whole suite passes 40 days on locally with three workers, and the job passed on CI at `9e9c3f0` (4.5 minutes,
    run 39527996195).

- [x] [B-9] **Build the UI/UX designer's review of batch B-8** (received 2026-10-20 at `0f37be4`,
  `reviews/ui-ux-2026-10/rereview-0f37be4/README.md`; R1 to R11 confirmed fixed on screen, and both of the session's
  judgment calls accepted; the owner's standing answer: "give them what they want"). Each sub-item is done when its
  test passes:
  - S1: one decision is one Today line: a held op leaves its change's review line; the review line says how many wait
    under Decide; a change holding only held ops shows no review line; approving a review never settles a held op
    (true in the code today: `looks_good` only marks the change reviewed; a test pins it) (check C57: no item on two
    Today lines). **Built (B-9):** `tests/test_one_decision_one_line.py` (the held op leaves the review line, the line's
    `deciding` keys, a change with only held ops has no review line, `looks_good` never settles a held op, no op on two
    lines), `tests/test_source_intake.py`, `web/src/components/TodayOneDecision.test.tsx` ("the decision stays a question
    under Decide, and the review line beside it says it waits there", "Go to what waits opens the held line's details");
    the browser check "one decision is one line…" in `web/e2e/today-capacity.spec.ts` is written, not run;
  - S2: a held line's details show only the held decision (the question, the quote and who said it, the source, why it
    waits, the two answers); a held op's label is conditional ("Would close a to-do"). **Built (B-9):**
    `web/src/components/TodayOneDecision.test.tsx` ("a held line opens on only its decision…", "a held op the engine
    doesn't shape as a question opens as its own row…", "a held op's label on its change's card says what it would do…"),
    `web/src/wording/wording.test.ts` ("every op that says what was done has a conditional twin…");
  - S3: the pill column has one fixed width on every row, so every title starts in line. **Built (B-9):**
    `web/src/components/TodayOneDecision.test.tsx` ("the lines that stop or ask for something use the queue's columns…");
    measured at 1440px on the demo's build: every line's title starts at x = 413, where the Access line started at 344 and
    the Rules line at 333 (the browser checks in `web/e2e/today-capacity.spec.ts` and `web/e2e/work-access.spec.ts` are
    written, not run);
  - S4: What changed and Today topics come from a short topic, never a cut-off first sentence; "Work <assistant>
    started" says what the work was. **Built (B-9):** `tests/test_item_titles.py` ("a short topic beats a first line that
    would be cut off", "with no topic and a first line too long to show whole the topic is empty", "work the app
    started…"), `web/src/lib/queue-words.test.ts`;
  - S5: under Review a change the assistant made reads in the past tense ("<assistant> dropped …"); under Decide, a
    question. **Built (B-9):** `tests/test_one_decision_one_line.py` ("a review line for one thing says what was done and
    to what"), `web/src/components/TodayOneDecision.test.tsx` ("a review line says what the assistant did in the past
    tense…"), `web/src/wording/wording.test.ts` ("a review title for one thing the assistant did is in the past tense…");
  - S6: with nothing connected, the mail step shows only "I'll do this later"; Continue appears once something is
    connected. **Built (B-9):** `web/src/components/Walkthrough.test.tsx` ("the mail step with nothing connected has one way
    on…", "the mail step has Continue once something is connected…");
  - `docs/project/ui-review-status-2026-10-20.md` carries the reviewer's marks at `0f37be4` and then B-9's. **Built (B-9):**
    the file (a documentation item, so no test). The three browser checks passed in the full runs and on CI at
    `e4d9fd7` (run 39545093376, every job green), and the reviewer marked S1 to S6 Done on screen at `9e9c3f0`
    (`reviews/ui-ux-2026-10/rereview-9e9c3f0/README.md`) and R-0 to R-c at `149890e` (its `followup-149890e/`).

- [ ] [B-10] **The owner's re-run of the failed AI cases** (2026-10-21, at `9e9c3f0`, one account, 3 runs per case:
  the golden set's 41 failing cases at 39% of runs passing, 10 cases passing every run). Each sub-item is done when its
  cases pass on the owner's next re-run and a stub or unit test pins the rule:
  - a promise with a condition keeps its date words apart from the condition, and the condition in its text (019, 020,
    021, 054, 055, 056, 064, t10, t12, t25-m2): the task's prompt and guidance. **Built** (instructions; a model
    behavior, so done when the owner's next re-run passes these cases): `tests/test_learning_run_b7.py`
    "a_condition_with_a_date_keeps_the_date…" pins the wording, and `promised_to` is required whenever the input shows who;
  - the scorer compares due words as the date rules read them, past "on" and "by" (013, 027, 112). **Built:**
    `tests/test_evaluate_harness.py` "due_words_are_compared_as_the_date_rules_read_them" and the pinned
    "a_promise_is_matched_on_who_it_is_owed_to…";
  - a first name two people share is held for "who is it" even when the answer names one of them in full, when the
    full name isn't in the input (shared-first-name). **Built:** the golden case `shared-first-name-named-in-full`;
  - a person the answer writes as an address, or a name with the address beside it, is the person the address belongs
    to (the learning pairs 07 and 20 held "tess@example.com" and "Tess (tess@example.com)" as unknown). **Built:**
    `tests/test_names.py` "a_person_written_with_their_address…", "an_address_nobody_has…";
  - a reply in a promise's thread that the answer leaves without any op goes back once for what it said (105, 110,
    114, 120, t21). *Open, a design question first:* an action keeps no record of the words it came from, so which
    open promise a pasted reply belongs to can only be guessed from overlapping text, and a wrong guess spends a paid
    return round. *Decided (F30):* the thread is the conversation the rules join, and pasted text joins a promise's
    thread by rule when its quoted history holds that promise's evidence quote; done when a stub case shows a pasted
    reply that quotes the promise's sentence linked to it by rule, and an empty answer to it sent back once. **Built:**
    `tests/test_thread_promise_lint.py::test_through_a_hand_in_an_empty_answer_is_sent_back_once` and
    `::test_news_from_a_reply_that_quotes_the_promise_is_about_it_whatever_its_own_words` (the lint
    `thread-promise-unanswered`). *Left:* the five cases pass only when the reply quotes the promise, so they are
    checked again on the owner's re-run; watched mail joined by conversation alone is not built;
  - a lesson as narrow as the person's words (F31): a named person or project, a role or plural group, or "always",
    "every", "never"; the reach stated in words; a correction never left without a lesson; done when the pairs
    `over-application`, `other-project` and `another-teams-rows-naming-ours` pass on the owner's next re-run, with a
    unit test of the breadth rule. *The instructions are written* (the learning prompt and its playbook; the Learned
    line already states the reach and picks it), with
    `test_a_lessons_breadth_is_read_from_the_persons_words_and_a_mistake_always_teaches_the_narrow_one`; *left:* the
    three pairs on the owner's re-run;
  - who a promise is owed to (F32): three stub cases, Cc (owed to the To recipients, the person watches), a named third
    party, and "we'll" from the sender's team. **Built:** the golden cases `promise-owed-cc-team`,
    `promise-owed-named-third-party` and `promise-owed-we-team`, the instruction in the notes prompt and playbook
    (`test_a_promise_is_owed_to_whoever_it_is_said_to`), and a forbid that names who a promise must not be owed to
    (`test_forbid_can_name_who_a_promise_must_not_be_owed_to`);
  - a self-check that fails while a decision entry from 2026-10-21 on names no change-log section that exists. **Built:**
    `engine/selfcheck/decisions.py`, `tests/test_selfcheck_decisions.py`;
  - the rest, case by case, through the prompt or a stronger tier (`docs/decisions.md` 2026-10-21, "Four evaluation
    cases follow the reply-owed rule"):
    - cases brought to the reply-owed rule: `decision-for-pm`, `thread-t18-m2-called-off` and
      `follow-up-with-no-clear-owner-asks-who` (stub cases pass);
    - instructions that contradicted a check: a reply's source in words, never an id
      (`question-asked-of-me-facts-hold-it`, `tests/test_obvious_steps_f.py`), and shared work as one action
      (`production-checkin`, `test_the_prompt_says_who_owns_shared_work_and_where_a_direct_choice_and_a_disputed_claim_go`);
    - rules: **Built:** a reply owed with no draft when a fact answers it (`tests/test_reply_already_known.py`), the
      person's own request (`promise-078-send-bram-agenda`, `tests/test_own_request_lint.py`), a signature phone
      (`signature-phone`, `tests/test_signature_contact.py`);
    - instructions only, a model behavior: the disputed claim (`follow-up-goes-to-who-made-the-claim`) and the colon
      (`colon-in-title`);
    - checked on a low-cost model (CLAUDE.md, "Check an AI fix on a low-cost model"): 14 of the 15 golden cases above
      pass on it, `decision-for-pm` only on the stronger tier; of the learning pairs, 11, 12, 15, 16, look-it-up and
      over-application pass (look-it-up and over-application after their expectations were brought to the reply-owed
      rule and loosened from one exact phrase), 20 passes on the stronger tier, and a lesson may now name only the
      projects its correction touches (`tests/test_learn_correction.py`); the reply owed also asks whoever the routing
      names (`test_a_reply_owed_with_no_recorded_answer_also_asks_whoever_the_routing_names`);
    - *left:* `stance-manage` (a design change from someone the person manages gets no "why" question on either tier: an
      instruction gap), `another-teams-rows-naming-ours` (the impact question missed on both), pair 03 (kept as a
      glossary term, not a lesson), `other-project` (a routing entry where a lesson was wanted), pair 19 (no lesson
      proposed), and thread-t14, whose answers are in the owner's `rerun.json`, not yet seen. All of these are done only
      when the owner's next re-run passes them.
  - from the learning pairs' re-run (69 runs at 32%): a lesson kept with a reach that misses the later run (pair 19,
    reach `follow-on` or `action-work`, the later run `notes`) and three firsts that propose no lesson at all (15, 16,
    20): whether the reach the model picks should be widened or checked against the correction's own task kind;
    `promised_to` left out of a promise made to the person in a message to them (pairs 11 and 12); "we" still owned by
    the writer (03); routing, the kept term and the fact lookup given but not followed (routing, day-30, look-it-up,
    stance-manage);
  - from the harder set (12 runs at 58%): `new-person-with-organization` and `project-no-record` (a project named in
    the input with no record is not held for adding).
  - from the harder learning pairs (21 runs at 62%): a correction turned into a lesson or routing entry broader than
    the correction (`over-application`: a reviewer for the load-test plan became "every plan review"; and
    `another-teams-rows-naming-ours`, the kept lesson over-applied), and no lesson for a correction about another project
    (`other-project`). With the pairs above, one piece of work on how a lesson is proposed and scoped.
- [ ] [B-11c] **Every kind of AI account works properly** (owner, 2026-10-21: "Most people will not use API and will
  probably just use subscription but I want them all to work properly"; after S1-4a): (1) an audit of every catalog
  entry against its own documentation, command-line programs first (the options each command accepts, how it takes an
  effort, its temperature and output rules), each finding fixed as data or an adapter capability, never a vendor check
  in code; (2) a native adapter for the recommended service's own messages interface, with effort, prompt caching and
  refusal handling. Done when each catalog entry's settings are confirmed against its documentation with a named test
  per finding, and the native adapter passes the smoke test's exact parameters and the lock-down rules in a named test.
  (3) **Failures captured in detail for feedback** (owner, 2026-10-21: "We should have something in the program that
  captures failures in detail so the user can send them in the feedback"): every failed AI call, account check,
  connector read and server error keeps what a maintainer needs (when, the task kind, the account's service and
  program version, the request's exact parameters, the status code, the error kind and the service's own error text),
  and never the packet, mail or any of the person's content; keys, tokens and addresses are masked. Send feedback offers
  "Add the last problems" (on by default when there were any in the last days, a setting), shown in full in the email
  before it leaves, as today. Done when a named test shows a failed call's report holds the parameters and the error and
  no packet text, secret or address.
- [ ] [B-11] **A recommended setup per AI service, out of the box, measured to stay current** (split, owner
  2026-10-21, so the steward starts the next day: **B-11a** first, the three tiers, the presets, effort as an adapter
  capability, the fallback by price and setup loading it all with no question; **B-11b** later, beside I-0, the Settings
  screen with the tiers and their cost per day, and "Measure"). **B-11a built:** `engine/ai/presets.py`,
  `tests/test_tier_presets.py` (presets for the two services whose families are certain; effort reaches a service only
  through its confirmed `effort_param` or `effort_option`, none set yet). *Left for B-11b:* the Settings screen,
  "Measure", the model picker's role words (two examples now share "stronger"), effort in the pre-save account check,
  and confirming each service's effort parameter. *Found while confirming it (2026-10-21):* the recommended service is
  reached through its chat-format compatibility endpoint, which per its own documentation ignores `reasoning_effort`,
  supports no prompt caching, is "not considered a long-term or production-ready solution", and refuses any
  temperature below 1 on current models; **fixed:** `send_temperature` (off for that entry,
  `test_the_recommended_service_is_sent_no_temperature`). *Proposed:* a native adapter for that service's own
  messages interface, for effort, prompt caching and refusal handling (owner to decide) (owner, 2026-10-21;
  design 6.16; placed before phase S because it decides what testers spend; the owner may move it): three tiers
  (everyday, stronger, hardest); a preset per catalog entry naming a model family and an effort per tier; effort as a
  per-model adapter capability; tiers filled by price where no preset matches, marked not checked; a measured
  recommendation from a few evaluation cases on request, comparing model and effort pairs by measured cost per passing
  answer (a low-cost model at high effort against a stronger one at low effort); setup loads the preset with no
  question, and Settings shows the three tiers with a cost per day, changes them and measures. Done when a new account of each preset service gets its tiers filled with no choice made,
  a service with no preset gets them by price, and a measurement test picks the cheapest passing model, each with a
  named test.

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

**From the outside design review (2026-10-21, `docs/project/reviews/steward-design-review-2026-10.md`; checked against
the code by the main session),** for S1 before the gate week:
- [ ] [S1-4] **Two sides from day one** (the UI/UX reviewer, 2026-10-21, design 6.32; first in phase S, because the
  steward's first read of mail files into them): the business as a top-level project named by a setting, every item on
  Personal or the business, filing by its people first, one batched "Which side?" question for what neither its people
  nor its words place (never asked of a person with no business), the "All / Personal / <business>" filter on Today and
  Follow-ups, and a relation field for people on the personal side. Done when a fictional week of mail for a person with
  a business files each item to its side with at most one question, and a person with no business is asked nothing,
  each with a named test.
  *S1-4a, the data, built:* the settings `workspace.project.personal` and `workspace.project.business`, the Personal
  project made by `cockpit init`, `POST /api/setup/business`, `Person.side` and `Person.relation`, filing by people in
  the applier's restatements, and the one batched Today line
  (`tests/test_sides.py::test_a_week_of_mail_for_a_person_with_a_business_is_filed_by_people_and_asks_which_side_once`,
  `::test_the_same_week_for_a_person_with_no_business_files_everything_and_asks_nothing`). Left: S1-4b, the "All /
  Personal / <business>" filter on Today and Follow-ups; filing by an item's words (only its people decide today).
- [ ] [S1-3] The first run's coverage: before Start, which account, folders and dates will be read; after it, which
  were read; and a missing sent folder said plainly on the first promise list, so an incomplete first result never
  looks complete.
- [ ] [S1-3] A date marked "check this" is never a firm deadline: no reminder, at-risk line or overdue from it until the
  person confirms it.
- [ ] [S1-3] The deadline words people use every day are read by the rules, so fewer dates wait for "check this"
  (the outside helper's 80 phrases, `tests/fixtures/phrases/due-phrases-01.yaml`, 42 read as a person means them at
  `1ec95d2` and none read wrongly; `tests/test_phrase_cases.py` holds the rules to them): numeric dates in the
  language's order ("11/6"), "day after tomorrow", "later today", "tonight", "noon" and "midnight", "first thing
  <day>", "end of the month" and "end of next month", "this weekend", "within <n> hours or days", a time with a zone
  abbreviation ("5pm ET", zone abbreviations as language data), and holidays as dated data per locale ("by
  Thanksgiving"), never in code. Each one read is a case in that file passing; a doubtful reading stays inexact.
- [ ] [S1-3] A late reminder says "overdue · due <time>" unless the app knows it was closed or asleep (today's
  `queue.reminder.late` says "while this computer was asleep" without knowing).
- [ ] [S1-3] The brief's all-clear names any source not read since the last brief, so a stale mailbox never reads as a
  quiet day.
- [ ] [S1-3] `docs/project/steward-proposal.md`'s stale statements (phase order, the Monday briefing's phase, reminders on
  any dated thing, approved writes as an open question) are corrected to the roadmap.

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

S1b. **Acting for you, after your yes** (owner, 2026-10-17: "if we can have the app actually able to do mail/calendar
management (not just read only) lets do it"):
- [ ] [S1b-1] **The publisher, brought forward from phase C4:** every outward act is shown as its exact content and target
  (recipients, the calendar and the time), approved by the person, then carried out with a visible status (sent, failed
  with why, undone where the service allows) and written to the ledger. Recipient checks: a new or outside recipient,
  or one taken from untrusted text, is called out before the yes. It calls `outward.check_outgoing` on every draft before
  the yes, so nothing that still names the assistant goes out (design 6.12; the function is built and tested in B-7,
  `tests/test_outward_never_names_assistant.py`, and nothing calls it yet).
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
  The repeats people say that the grammar declines today (the outside helper's 60 phrases,
  `tests/fixtures/phrases/repeat-phrases-01.yaml`, 31 agreeing at `1ec95d2`, every other one declined, none read
  wrongly): wording variants of supported repeats ("weekly on Wednesday", "every two weeks on Thursday", "every other
  week on Monday", "the first Saturday each month", "on the 1st", "annually"); several days of the week ("Mondays and
  Thursdays", "weekdays except Friday"); several days of the month ("the 1st and 15th", "the second and fourth
  Tuesday"); the last day, weekday or a given day of the month; a yearly weekday ("the last Friday in November"); and
  February 29 falling on the 28th. Each needs a shape and its wording to say it back; unclear ones ("biweekly",
  "quarterly") stay declined and asked.
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
  **Personal, decided** (owner, 2026-10-20; design 6.32 "Personal life"): setup makes one Personal project; areas (no end
  date) and personal projects (with an end) under it, proposed by the assistant once several items share a theme and
  confirmed by the person; a move teaches the next filing; privacy per area through content levels; Personal left out
  of work reports. First five minutes: one Personal project and no questions until a pattern shows.
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

- [ ] [I-0a] **Before any installer work: every kind of AI account hardened** (owner, 2026-10-21: "I want this hardened
  across the board before we get to the installer"): B-11c done (each catalog entry confirmed against its own
  documentation with a named test per finding, and the native adapter in), subscription programs first.
- [ ] [I-0] **Before any installer work: setup and the everyday screens reviewed as a normal non-IT person** (owner,
  2026-10-21, passed to the UI/UX reviewer). The reviewer walks setup and the daily screens as a personal and business
  tool, not a project manager's. Setup is reshaped to match design 7 ("Setup for a person, with a business optional", in the UI/UX
  reviewer's order of 2026-10-21: the business question in step 1, Welcome not counted, a hand-in when mail is skipped,
  people by relation, small-business words, Personal in place of Projects):
  what this is and what to do first; the personal side (the people in one's life, personal business); then the optional
  "Do you have a business you want to track?" (its name, programs, projects, people). The new flow is built under the
  UI rules already in force (design Part 7 and CLAUDE.md's UI rules: the wording sheet, the cursor in the first field,
  lists to pick from, one primary action, Continue and Skip as the walkthrough has them, no sideways scroll at any
  width, WCAG 2.2 AA in light and dark, and the browser tests at every width). Done when the reviewer's findings
  are answered and a journey test walks both paths (personal only; personal and a business) with no work terms on the
  personal-only path.
  Inputs, reviewed against design 7 and the wording sheet (2026-10-21): `docs/project/setup-inputs/` holds the setup
  wording (`wording.yaml`), the relations list for the Personal side (`relations.yaml`, a setting's default) and the
  common Personal areas offered as unticked boxes (`areas.yaml`, a setting's default; phase S4 proposes areas from a
  pattern). A job or a business is the second side, the person's choice in step 1, with `workspace.project.work_kind`
  picking its words (decisions 2026-10-21, "A job or a business can be the second side").

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
- [ ] [I-2] **Three people set it up alone** (the first-run review's N8): three people who match the persona each complete
  setup alone ("set it up and see what it does with one of your emails") in under 20 minutes, watched without help;
  every stop or question becomes a finding. The exit test of the tester milestone.
- [ ] [I-2] **The release build fills in its catalog and feedback addresses** from repository variables, as the package build
  already does, so a tester's Add-ons lists packs with nothing to type.
- [ ] [I-1] **Signed so the systems let it open** (owner, 2026-10-21: decided, not before 1.0: "we can clearly state
  it's currently unsigned on the webpage. When we get more users I'll look at that again", paid for by Thimbleby Plus;
  1.0 ships unsigned, and the item below says how). Without signing, macOS refuses
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
  release notes and the download page show both, with pictures, and the download page says plainly, before the
  button, that the app is not yet signed, what the warning means and that signing comes later; each download's SHA-256
  checksum is shown beside it so a person can check the file is the one released. Unsigned builds don't enforce library validation, so
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

- [ ] [I-3] **The free core release** (owner, 2026-10-20: "get to Thimbleby core faster and push and update the website";
  `docs/project/business-model.md`): after phase I's exit test, the open core is published under Apache-2.0 from a fresh
  public repository (owner action M5), with CONTRIBUTING (ideas welcome, no pull requests), SECURITY (how to report a
  problem privately) and a trademark note (Apache-2.0 doesn't license the name); the website shows the release (M6,
  I-2). A journey test: a free install connects an Outlook.com mailbox through a pasted registration, on the fake
  sign-in service the tests use; and the owner's live check of the same on a real Outlook.com and a real Gmail account
  (registration "In production"), which confirms the add-on's steps. Nothing in it waits for phase T.

## Phase T: Thimbleby+ (after the free core release, and only if the owner goes ahead)

The paid upgrade in `docs/project/business-model.md` (decisions, 2026-10-20): one yearly licence for one-click Gmail and
Outlook and every pack. It is conditional (owner, 2026-10-20: "a 'maybe' Thimbleby+"; "I don't want to be beholden to
this yearly Google assessment"), so nothing in the core depends on it. Owner actions M0 to M4 come first, M0 before
anything else. Each item ends with its named test. **Proposed, awaiting the functional designer's review**
(`docs/project/business-model-delta-gmail-later.md`): Plus launches with one-click Outlook and every pack, and Gmail's
one-click sign-in (with Google's yearly assessment, M1b) waits for a trigger; a tester registration the owner keeps in
Google's Testing status (M7) serves testers and founding members. The items below take it once it is accepted.

- [ ] [T-6] **Testers and the weekly sign-in** (functional designer, F27 and F29, 2026-10-21): a Today line the day
  before a known sign-in expiry ("<service> needs signing in again tomorrow"); mail unread while a sign-in lapsed shown
  as a coverage gap and counted apart from missed promises in the independent-list comparison; one question about it in
  the two-week check-in form; a dated list of everyone added to and removed from the tester registration, kept before
  anyone is added; and one of phase I's three testers on the free own-registration path.
- [ ] [T-7] **No dead end without mail** (F28): with no mail connected, the setup guide and the coverage line point to
  the mail add-on's steps, naming no service.

- [ ] [T-1] **The Plus licence, checked offline:** a licence file signed by the owner's key, kept in the workspace's
  private folder and checked with the public key the app ships with; no call home. Generic in the core: a catalog entry,
  a plugin manifest or a sign-in's own registration can name an entitlement (`plus`), and the core checks it without
  knowing what it unlocks (design 3.11).
- [ ] [T-2] **The add-on's own registration needs the entitlement:** the core uses a sign-in's shipped registration only
  while its entitlement is held; otherwise the Sign-ins row offers the person's own registration with the add-on's steps.
  Test: a lapsed licence keeps packs at their version, stops the one-click sign-in with the Sign-ins row's offer and a
  Today line, and a renewed licence brings it back.
- [ ] [T-3] **Downloads gated by the licence:** a small download address checks the licence and returns a short-lived
  link; Add-ons' Install sends the licence instead of a release host's read token (P15). Free add-ons download with no
  licence.
- [ ] [T-4] **Suggest something:** *Send feedback* and `report.draft` become one flow the person approves word for word;
  the assistant offers it when it hits something it can't do; release notes say what came from suggestions.
- [ ] [T-5] **The template gallery, as untrusted content** (after the paid 1.0 if time is short): templates shown in full
  before they are added, marked by origin, "from outside" in packets. Test: a gallery template whose help text tries to
  change routing changes nothing and reaches packets marked "from outside".

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

1.0 is a moving target until the owner finalizes scope (owner, 2026-10-19). It ships on plugin API 0.x; plugin API 1.0
keeps its own test, two packs unchanged through real use (decisions, 2026-10-20). The items below are the release
mechanics.

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
- A price per pack, or a marketplace: one Plus licence covers every pack instead (decisions, 2026-10-20; `business-model.md`, whose items the batches take under open promise P25).
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

