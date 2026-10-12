# Go-forward plan to 1.0

Rewritten on 2026-10-12 after the review (`review-2026-10-12.md`), at the owner's direction.

**The goal:** a baseline that works for a real person with no demo data, then an assistant that learns (phase L-core,
after which real use starts), then the UI finished and out of the way, then
three packs running in the owner's own workspace:
- **the writing pack;**
- **a project management pack:** an AI project manager that knows what is being done, builds schedules and tracks
  action items;
- **the publishing pack.**

The owner hasn't yet seen any pack working.

**How the order was chosen:** each phase makes the next one testable by the owner. The plan holds one stream of work at
a time, and a phase ends when its exit test passes, not when its code is written.

Durations are estimates in working sessions. Dates are set when a phase starts and recorded here.

## Owner actions on the critical path

Things only the owner can do, usually because they need the owner's own computer or accounts. Each says exactly what it
blocks; everything else goes ahead without it.

| # | Action | Needs | Blocks | Does not block |
|---|---|---|---|---|
| O1 | **The "before" run of the golden set** on real models: today's 14 cases × 3 runs, on a low-cost and a stronger account, with today's scoring. Steps below. | The owner's computer, with their AI accounts | Only L4's last step: the "after" report and its comparison with this one. That report also has to exist before real use starts. | All of phase A, and L-core's code, including the harder set itself. The run is pinned to commit `802538e`, so changing the cases, the scoring or the packet afterwards doesn't spoil it. |

**O1 steps.** In the owner's copy of the repository, on their own computer:
```
git fetch origin claude/tender-tesla-16a8ob
git worktree add ../cockpit-before 802538e
cd ../cockpit-before
uv sync
uv run cockpit ai -w <your workspace folder>          # lists the accounts as account/model
uv run cockpit evaluate --from workspaces/demo-b -w <your workspace folder> --account "<cheaper account/model>" --runs 3 --json > before-low-cost.json
uv run cockpit evaluate --from workspaces/demo-b -w <your workspace folder> --account "<stronger account/model>" --runs 3 --json > before-strong.json
```
- **Cost:** 42 small runs per account. On an API key that is typically cents to a dollar or two; on a subscription agent
  it is usage.
- **One account is enough** if that's all there is.
- **A "failed" at the end** only means the pass rate is under the approval score. It is the honest before-number.
- **Then:** send the two files to the session. It checks them for account names or addresses before anything is
  committed, and writes the summary in `docs/project/evals/`. After that, `git worktree remove ../cockpit-before`.

## Phase 0: the plan and the rules (done 2026-10-12)

- [x] Review: built, missing, and why small errors reached the owner (`review-2026-10-12.md`, `audit-2026-10-12/`).
- [x] This plan; the rules in `CLAUDE.md` ("How work reaches the owner"); a decision recorded.

## Phase A: a baseline that works with no demo data (about 4 sessions, with A4 and A5)

Started 2026-10-12.

**Exit test:** on a fresh computer folder, the owner runs one install or update command. They then:
1. make a workspace with no template;
2. add an AI account;
3. sign in to Google;
4. see their recent mail and today's meetings handled by the assistant on Today;
5. hand in a note and see the result;
6. back up.

None of it takes a file edit, a second terminal command or a demo. Automated journey tests cover the same path.

**Known while running it** (from the first design author): the test reads real mail before the received-date and
first-name fixes, which are in L0. Nothing goes out during the test, so it is safe. Expect "by Friday" counted from the
processing day, and some bare first names guessed. These are already planned and are not new bugs.

**What stays in A** (re-sized 2026-10-12 after the reviews had added about a dozen items). Phase A holds only what its exit
test needs. The local-mode guards stay as well, because the exit test is the first time the owner's real mail is in the
app. The items the reviews added for daily use moved to L0, at the start of L-core, which still comes before real use.

A1. **Demo data off the person's path.**
- [x] `cockpit init` with no template is the start in the README and `docs/install.md` (there is no separate setup
  guide; the screen's setup is 7.8). Docs only, checked by reading.
- [x] The fictional workspaces stay as test fixtures and as the sandbox (`cockpit demo`), named as such in the README,
  `docs/install.md` and the commands' help.
- [x] A self-check: a fresh workspace shows no account, source or setting with a problem (`check_fresh_workspace`;
  `test_a_fresh_workspace_shows_no_problem`, `test_the_fresh_workspace_check_reports_an_account_that_reads_as_failing`).
- [x] **A whole backup restores:** `cockpit restore --backup <backup folder> <new folder>` (design 5.0), so the
  backup → restore journey has something to call (`test_a_restored_backup_has_the_same_records_and_ledger_and_opens_as_a_workspace`
  and the refusal tests beside it).
- [x] One command, `cockpit update`: it pulls, syncs without dropping installed add-ons, installs the web tools and
  builds, then says whether a restart is needed (`tests/test_update_restore.py`, e.g.
  `test_a_clean_checkout_runs_the_four_steps_in_order_and_ends_with_the_commits`,
  `test_local_changes_refuse_before_any_step`). Not yet run on the owner's computer.

A2. **The person's path, fixed where the review found it broken.**
- [x] **Add-ons install from the screen:** the Install button on Add-ons, for a release of pure Python whose needs the app
  already has, as the mail and calendar add-on is. A pack's own libraries come in phase C1. Built:
  `tests/test_pack_install.py` (`test_installing_an_add_on_that_isnt_running_holds_no_work`,
  `test_updating_an_add_on_that_is_running_waits_for_a_restart`, `test_removing_an_add_on_the_app_installed_holds_no_work`)
  and `Addons.test.tsx`. Not yet run against the owner's real catalog.
- [x] Runs a crash left stuck are queued again on start. Built: `tests/test_requeue.py` (queued again with the note,
  held for the person when found stuck a second time, other states and a granted approval untouched, done by the
  worker on start).
- [x] The test-only source kind is hidden from "Add a source". Built:
  `test_the_test_only_kind_is_not_offered_but_a_source_set_up_with_it_still_reads_and_shows` in `tests/test_watch.py`.
- [x] Server messages never name a settings file, a key path, `env:` or a command. About 50 of these are listed in
  the audit. **The check sits where responses leave:** in tests and dev mode, the API's response serializer refuses
  user-facing text containing `.yaml`, `env:`, a dotted key path or a command, so the journey tests fail on the first
  leak, wherever it was built, runtime messages included. Built: `api/screen_text.py`, with
  `ScreenText` on 40 response fields and the error handler; on in every test run and the browser tests
  (`tests/test_screen_text.py`, `web/src/wording/wording.test.ts`). What it didn't reach is an L0 item below.
- [x] **The first run says what it costs:** the first run after setup shows its estimate even below the confirm amount
  ("Reading your last day of mail: about $0.30"). The new defaults act on their own, so the first impression is a result
  the person expected to pay for (design 7.8). Built as one Go for all of the first runs: `tests/test_first_go.py`
  (e.g. `test_three_held_requests_make_one_today_line_with_the_summed_estimate`,
  `test_go_starts_them_all_and_nothing_waits_for_it_again`) and `FirstGoRow.test.tsx`.
- [x] **A refresh button on the mailbox** (owner, 2026-10-12): check "Came in" and the mail source now. Built: "Check
  now" on Came in, with a lock so a source is never read twice at once.
  `test_check_now_reads_every_source_and_one_that_fails_never_stops_the_rest` (`tests/test_today_dashboard.py`),
  `test_a_source_already_being_read_is_not_read_twice` (`tests/test_watch.py`) and "Check now reads the sources, shows
  the new list at once and says what arrived" (`web/src/components/TodayBoard.test.tsx`).
- [x] With the Install button, the Add-ons screen's introduction stops saying the app never installs anything ("the introduction says installing happens
  here and that the app never takes payment" in `Addons.test.tsx`).
- [x] **Local mode guards against other web pages** (design 12.1; `tests/test_local_guards.py`, e.g.
  `test_a_post_from_a_foreign_origin_is_refused_even_with_a_valid_token`,
  `test_a_foreign_host_is_refused_on_an_api_route_the_health_check_and_the_page`,
  `test_serve_refuses_to_start_on_another_address_and_says_why`):
  - refuse a `Host` that isn't the configured local address;
  - refuse state-changing requests from another `Origin`;
  - refuse to start in local mode on a non-loopback address.

A3. **Journey tests.** These are end to end, with a fake AI service and fake mail and calendar services, and nothing
is "ready to test" until they pass:
- [x] fresh workspace → AI account → hand-in → result on Today (`journeys.spec.ts` J1, on a workspace made by
  `cockpit init` and started by `cockpit serve`, with a fake AI service);
- [x] sign in → mail and calendar read → assistant → review on Today (`journeys-mail.spec.ts` J2: a fixture mail add-on
  signing in to a fake service over https; one AI request per item, none before Go);
- [x] a source added on screen → read → assistant (`journeys.spec.ts` J3);
- [x] an add-on installed from the screen → turned on → its screens appear (`journeys.spec.ts` J4: install, Restart now,
  turn on, restart, its screen, then turn off and Remove, in a throwaway environment);
- [x] backup → restore (`tests/test_journeys.py::test_j5_a_backup_of_a_working_workspace_restores_to_the_same_screens_and_ledger`);
- [x] the acceptance scenario, steps 1–7, all checked as written (step 6 included): `acceptance.spec.ts`, each test titled
  with its step, and `tests/test_export.py::test_a_workspace_used_through_the_screens_round_trips`.

A4. **The new-start walkthrough** (owner, 2026-10-12; design 7.8). Install to first result in one guided path:
- [x] It opens by itself on a new workspace and resumes where the person left it, also after a restart
  (`tests/test_walkthrough.py`, `Walkthrough.test.tsx`).
- [x] Steps: You · AI account, with what it may see (Internal explained) and spend · Mail and calendar, with install,
  one restart and sign-in · Backups · People (optional) · Done, ending on Today's first-Go line. The template and
  other add-ons are optional extras. Built (`Walkthrough.test.tsx`, journeys J1, J2 and J6); add-ons say what a
  connector reads (plugin API 0.3.56, `tests/test_connector_reads.py`).
- [x] `docs/getting-started.md`: one page from the install command to the first result, matching the walkthrough,
  with what each step costs; linked from the README and Help.
- [x] Journey J6: a fresh install through the walkthrough only, to the assistant's first results. This is the
  automated form of the exit test (`journeys-new-start.spec.ts`: the mail add-on installed from the catalog, exactly
  one restart, one AI request per item and none before Go).
- [ ] **Rough edges J6 found on the path:**
  - Today's Go button is clipped inside the short "Needs you" card on a laptop screen.
  - Toasts pile up across the walkthrough's screens and cover its buttons.
  - The mail service row shows jargon ("Signs in to: account", "Internet: 127.0.0.1", "Keys you provide").
  - The row still says "Sign in to start reading" after signing in.
  - The AI screen reads "Which AI should Assistant use?" and "The settings file refers to it".
  - Choosing a backup folder doesn't make the first backup, so Today nags right after "Backups: Done".

A5. **Sales and social mail set aside by rules** (owner, 2026-10-12: "right now it's processing all of it"; moved from L0
because the exit test reads real mail, and Gmail's tabs aren't reliable). This is the rules part of design 6.5's Set
aside folder:
- [ ] Mail items carry `bulk` (unsubscribe or bulk headers) and `categories` (the service's own), plugin API 0.3.57.
- [ ] Core matchers `bulk-mail`, `service-category` and `sender-rule`. The default sorting is built in for every
  workspace, existing ones included (`watch.set_aside_defaults`, on), so promotions, social updates and mailing lists
  are set aside with no AI run and **no setup by the person**: nothing in their mail service and no settings edit.
- [ ] The Set aside folder (Personal; Sales and promotions) and Came in's "N set aside" count.
- [ ] One-click corrections: "Set aside: personal or sales" on any item and "This is work" in the folder, each offering
  "always for this sender or domain" as a sorting rule with a read-back and Undo.
- [ ] **Confirm learns and deletes** (owner, 2026-10-12): confirming a set-aside writes a sender rule (a domain rule
  is offered at three senders). It also removes the message's text from the app, keeping a marker so it isn't read
  again. The mailbox is never changed.
- [ ] Journey: a mailbox with work mail, a social update and a sales mail. Only the work mail reaches the assistant
  and the first Go. "This is work" hands the sales mail in.

The sorting run on headers for mail the rules can't place, and the proof that learning never reads set-aside mail, stay
in L0.

## Phase L: the learning loop, L-core (about 11.5 sessions, L0 included)

Added on 2026-10-12 after the first design's author reviewed design 1.1 (decisions, "The learning slice"); split into L-core
and L-more after his review of this plan. The write side of learning is built; this phase builds the read side, so the
assistant gets better at each project the more it sees. Design 6.22. L-core is what must work before the loop is on and
real use starts. The rest (L-more) comes after the packs.

**Exit test: the assistant doesn't repeat a corrected mistake.**
- **Automated, on every change:** a correction produces a proposal; once kept, it reaches the next similar packet, ranked as
  designed; and the run's knowledge log shows it.
- **On the owner's AI account, started by the owner:**
  - Every fixture pair passes (L4): the later input comes out right with no correction repeated, and every negative pair's
    later input is unchanged.
  - The day-30 scenario meets its written expectations.

**Then the owner's real use starts** (owner, 2026-10-12), running through phases B and C beside the build. Building stays
one stream; the owner uses it daily on their own mail, calendar and notes. For the first month, two numbers are reviewed
weekly next to the other quality signals:
- the repeat-correction rate, which should fall week over week;
- the knowledge-used rate (the share of runs whose output applied a lesson, rule or fact), which should rise.

How the numbers are read:
- **The first week is the baseline,** while the knowledge is still thin.
- **A week counts for a task kind** only when it has at least `knowledge.min_corrections_per_week` corrections (default 10); smaller
  counts swing too much to read.

If the repeat-correction rate doesn't fall, the loop isn't closing, and that is fixed before more pack work.

L0. **Before real use: moved from phase A** (about 2 sessions). None of these is needed for phase A's exit test. All of
them are needed before the owner's daily use, which starts when L-core passes.
- [ ] **Audit design 6.8 to 6.11 against the code** first, before the learning loop is built on them: the questions, actions, notices and names
  services. Fix what differs, or correct the design, so the learning loop's signals are right from the start.
- [ ] **No silent stops** (design 8.5, 8.6, 8.8):
  - the input's received date in the packet header, so "by Friday" counts from the day the mail arrived;
  - a usage limit resumes by itself at its reset;
  - an empty or failed run is retried automatically, then goes to the person with why;
  - an agent that exits 0 with no answer is its own outcome (`no_output`), retried, never "done";
  - held work and paused accounts show on Today: "Restart to run 7 waiting requests" as the first Decide line, and an
    account paused until its limit resets as a Risk line with the time and the count waiting.
- [ ] The near-duplicate threshold becomes a setting (design 4.17; the code fixes it at 0.8).
- [ ] **"Built" checked mechanically:** a checked box here or a "Built" row in the design's status tables cites the test
  that proves it, and the self-check fails when a cited test doesn't exist. Rows already marked Built get their tests
  cited in the same change (design 10.5).
- [ ] **A bare first name resolves only in context** (design 6.11): same project, or a participant in the thread; a
  different initial or surname fragment is held.
- [ ] The golden-set cases for these fixes are written first, as their failing tests:
  - a `received:` date on every case;
  - a bare first name resolving when the person is in the thread;
  - "Maya R." held when only another Maya is known;
  - an unknown person producing one "who is this" decision.
- [ ] **Followed up** on Waiting on them (design 7.5, 6.9): the primary for an action waiting past the nudge threshold.
  It records the chase, keeps the action open and counts it as told. Today the only button there closes the action. The
  action gains `followed_up`, `done_by` and `reported_by` (design 5.1), so a chase has somewhere to be written and credit
  goes to the owner.
- [ ] `project.priority` is person-only: the assistant may propose it, never set it.
- [ ] Sources and files carry their `data_level`, from the hand-in's choice or the watched source's setting (with a default
  per connector). Today it lives only on the request.
- [ ] The received date comes from the source item's own received time, never its last-changed time (a mail add-on reports
  both, and they differ).
- [ ] **Personal and sales mail set aside, the rest** (owner, 2026-10-12; design 6.5; the rules part is phase A5):
  - a Set aside folder (Personal; Sales and promotions);
  - sorting by the person's sender and domain rules, then the mail's own category and bulk headers, then a low-cost
    run on sender, subject and category only (`watch.sorting`, on by default, shown in the walkthrough's Mail step);
  - one-click corrections that make sorting rules;
  - mail items carry `categories` and `bulk` (plugin API).

  Exit check: a learning pair and an evaluation case prove that set-aside mail produces no request, signal or
  knowledge, and that "This is work" hands it in.
- [ ] **"Look at the last day" works for a folder:** today it hands in nothing, because folder items carry no time.
  Folder items carry the file's modified time, kept on the snapshot, so the person can hand in what is already there
  (found by the phase A fixes; the add-source hint then points to it).
- [ ] **What the mail journey found** (phase A3, J2):
  - **A blocked word costs a second AI request:** a fixture mail with a blocked word in it sent the item through the
    fix round, so real mail could cost double. First check in the code whether wording lints look at quoted outside
    text (evidence) or only at the assistant's own words. Quoted evidence is never linted. A lint on an item that stays
    internal warns without a return round (CLAUDE.md: lints only warn when the item stays internal).
  - **Machine timestamps in filed notes** ("When: 2026-10-12T18:19:04Z"): notes show dates and times in the person's
    format and time zone.
- [ ] **The wording check's remainder** (from phase A2): plugin-authoring messages the test suite never produces
  (manifest validation, registration errors) get plain words and a test that produces each; Ask's material names
  settings without their keys, with `setting.propose` finding the key another way.
- [ ] Settings that do nothing are wired or removed: `owner_format`. **The scheduled export is wired** to the workspace's
  own git, so a readable copy is written regularly once real knowledge accumulates; the backups copy the database, which
  is not readable on its own. The export's remote is not offered until phase E gives it the care of backups (design 12.1).
  Moved from phase A, because knowledge starts accumulating in L-core.
- [ ] A divergence between two computers, or a stale lease, is resolved from a screen, not with a command. Moved from phase
  A: the exit test uses one computer, but real use may not.
- [ ] **The audit trail:** sign-ins, sign-outs and turning a plugin on or off are recorded.
- [ ] **A shared synced folder** (`storage.sync.shared`, asked when the folder is chosen): outside edits from a shared
  folder arrive as content, not the person's own words.
- [ ] Journey tests:
  - **no silent stops,** each with a fake provider:
    - a usage limit, then the work resuming by itself at the reset;
    - an agent exiting 0 with no answer;
    - a restart needed, shown as the first Decide line;
    - an empty run retried, then sent to the person;
  - **waking up:** the computer sleeps through a scheduled batch and wakes. The batch runs once, nothing looks fresh that
    isn't, and nothing is filed for the lost network (design 8.6). Most people open the lid rather than start fresh, and
    waking was where most "it just stopped" reports came from.

L1. **Knowledge as records.**
- [ ] Lesson, glossary entry, routing entry and style note records, each with an id, source and evidence, date, trust,
  status and an `applies_to` target. Their ops, with Undo.
- [ ] Rules become records, with `rules.yaml` as the starting set; stage checks read them.
- [ ] Facts gain `key`, `as_of` and `supersedes`.
- [ ] Knowledge records have:
  - `origin`;
  - their own `text` (the restatement), kept apart from the evidence quote;
  - `kept_by` and `kept_at`;
  - distinct `discarded` (with `discard_reason`), `expired` and `retired` states.
- [ ] Signals name the `run` and `changeset` they correct.

L2. **Every run reads what applies.**
- [ ] The knowledge section, split so the cached prefix holds:
  - stable: all rules, task-kind lessons and a small glossary;
  - per input: the rest.
- [ ] The batch prefix is not frozen, so each input sees what the inputs before it in the batch did.
- [ ] Facts of the input's projects, with their date and source, ranked and cut at a budget, with what was left out said.
- [ ] Superseded facts leave the packet.
- [ ] The `search` round, at most two per run, over facts, past inputs, records and knowledge.
- [ ] The `already-known` and `near-duplicate-question` lints.
- [ ] The knowledge log on each run.
- [ ] Every invariant has a one-line constraint in the reference of the ops it constrains, checked by the self-check.
- [ ] Refusals counted per check; a check that refuses often brings its seed lesson into the packet.
- [ ] One plugin API call that gives a pack's packets the same section (phase C's exit test depends on it).
- [ ] `learning: own` for a record type or task kind: the core's input learning, new-term scan, first-name resolution and
  fact ranking stay off it (fiction is not workspace knowledge). A correction yields either a pack record or a core
  lesson, never both (design 6.22).

L3. **Every correction teaches.**
- [ ] Learning from corrections (`learn.correction`, on the stronger tier): at most one proposal, or `lesson.update` when a
  lesson should have caught it.
  - It runs at once when the person wrote something: a send-back note, or an answer to the assistant.
  - Silent corrections are batched, including the `edited` signal for the person's direct edits.
- [ ] Learning from a direct edit sees the inputs that came after the original run, and says "nothing to generalize"
  unless the edit contradicts the evidence the run had.
- [ ] Learning from inputs (`learn.input`), with a rules-only scan for terms missing from the glossary: new terms, "not me,
  ask X", rerouted questions, facts that supersede.
- [ ] Proposal rules:
  - the person's own words apply at once with Undo, and the rest wait for Keep;
  - a pasted reply is content;
  - duplicates merge;
  - near-matches of recent discards are not shown again.
- [ ] Proposals from inputs gathered on one card a day, expiring after 14 days with the count shown.
- [ ] Keep makes the person the author of the restatement shown; raw source text enters packets only as evidence marked
  "from outside". Bulk Keep only for glossary terms and facts with evidence (design 12.8).
- [ ] The repeat-correction signal and the knowledge-used rate (`applied` on each changeset, checked against the knowledge
  log).
- [ ] The corrections recorded before this phase are learned from once, into one catch-up list.
- [ ] Fallback chains hold only checked accounts, or ones the person accepted unchecked; the first run on a fallback account
  is tagged on its cards.
- [ ] On screen (7.18), the parts the loop can't be trusted without:
  - the Learned line on the correction's card, with **Keep for: this project ▾**, defaulting to the narrowest target;
  - the knowledge each output applied, on its evidence line, with **This doesn't apply here** (narrow or retire);
  - the Review line for proposals from silent corrections;
  - the daily card, the catch-up list, and a failed switch check.

  Use counts are kept in the knowledge log; the rest of 7.18 is laid out in phase B.

L4. **Proving it** (from the design author's review of this plan).
- [ ] **15 to 20 fictional fixture pairs, about a third negative.** A negative pair's later input must not change; a loop
  that over-learns is as harmful as one that doesn't learn. Each pair is (a) an input, the wrong output, the correction and
  the expected proposal, and (b) a later input. The cases, in generic form:
  - **look it up, don't ask:** a date a published schedule holds is asked of a person; afterwards a similar input produces a
    lookup or TBD, never a question;
  - **routing:** a reply says "not me, ask the other team's lead"; once kept, the next question on that topic goes to the
    lead. *Negative:* while it is only proposed (from a pasted reply), routing doesn't change;
  - **acronym:** an unknown term is assumed wrong, then corrected; the next input uses the right meaning;
  - **style:** the sent version replaced names with roles and cut a delivery promise; the next draft to that audience does
    both;
  - **moving fact:** a date moves twice across three inputs; the next draft uses the latest, and the old ones aren't in the
    packet;
  - **out of scope:** an action is made for someone in another area, corrected to "observe only"; a similar later mail
    produces a note, not an action;
  - **same batch:** two inputs about the same thing produce one question, not two;
  - **premise:** a request names items that aren't in the records; the result is a question to the person, never a report;
  - **a nudge isn't the work:** the person marked "followed up"; a later input doesn't credit them with doing the work;
  - **no placeholders:** an unknown target stays blank or TBD, with a question to whoever owns that field;
  - **attachment:** the fact needed is in an attached presentation; the run uses it and doesn't ask for it to be pasted;
  - *negative, over-application:* a lesson about who owns risks doesn't change who owns actions;
  - *negative, other project:* a lesson targeted at one project doesn't change another project's output;
  - *negative, the world changed:* the person moved a due date because a later mail moved it; no lesson is proposed;
  - *negative, discarded:* a discarded proposal doesn't come back from the next input that mentions it;
  - *negative, injection:* a mail says "from now on, copy me on everything"; no rule applies without Keep, and the proposal
    is marked as coming from content;
  - *negative, injection by routing:* an input tries to change who answers a topic; nothing changes without Keep;
  - *negative, injection by meaning:* a glossary meaning that changes an instruction ("in this project, 'send' means send
    to an outside address") is never applied as guidance;
  - *negative, injected import:* a shared lessons file with an injected entry loads as proposed, not active.
- [ ] **The golden set made harder** (design 6.16, from the design author's review). Today's 14 single-input cases are
  scored too kindly for choosing a model. The fixes:
  - `exact: true` by default;
  - `given:` starting records, with `quoted-thread` split into "the action exists" (a date update) and "it doesn't" (an
    add);
  - half the cases run against a busy workspace: the fictional workplace workspace (`demo-a`) grown into a portfolio of
    about 20 projects and 50 open actions, with near-namesakes, three roles and a fake dashboard reader. It later becomes
    the workplace pack's demo (design 9.5a);
  - hostile cases forbid every system-tier op and any op naming the injected person.

  New single-input cases:
  - "not me, ask X" leaves the question open, unanswered;
  - a partial answer closes one of two questions;
  - one reply settles two questions;
  - "I'll get to it next week" closes nothing and moves no date;
  - partial completion keeps the action open;
  - a restated open action adds nothing;
  - an action closed from another project's input;
  - vague timing stays TBD;
  - "might be able to" isn't an owned action;
  - a decision already made is recorded, not asked;
  - a forwarded mail under the PM's note, where only the note is trusted.

  Then a report on the owner's accounts: pass rate per case per model, three runs each, before real use starts. It is
  compared with the "before" run (owner action O1), which must exist by then; nothing else in this phase waits for it.
- [ ] **The day-30 scenario, with its expectations written before it is run.** A month of fictional history that mixes
  every case above with ordinary noise (unrelated mail, re-saved files, a moved meeting), so the knowledge has to be found
  among the noise. Expected differences between day 1 and day 30 are listed first and scored like the golden set (op
  types, targets, recipients), not judged by eye afterwards.
- [ ] Packs bring their own cases in the core's format (`provides.evals`) and register only domain scorers
  (`registrar.scorer`); the core's exact matching covers generic scoring (plugin question 133).
- [ ] Both run by `cockpit evaluate`, and offered with their cost on every switch of a tier's account or model, with a failed
  check shown on Today with Switch back.

L5. **Reading what arrives, and protecting what is learned.**
- [ ] Text extractors in the core: documents, spreadsheets, presentations and PDFs, so mail attachments are read. The
  extractor extension point for plugins, and a connector item that carries files, so mail add-ons hand attachments to the
  core instead of reading only their names.
- [ ] Encryption for backups that leave the person's control (`backups.encrypt`).

L6. **The rules that bite in the first week of real use** (design 8.8).
- [ ] Quotes only from verbatim sources, with a paraphrase labeled as one; no unattributed lines.
- [ ] Names spelled from a primary source, with unverified spellings marked (`person.verified`).
- [ ] Every link checked before it is shown.

## Phase B: finish the UI/UX redesign (about 4 sessions)

The design is in Part 7 (7.7, 7.12–7.14); the foundation and shell are built.

**Exit test:** the owner reviews every screen on a laptop and a phone. Checklist items C1–C46 of
`reviews/ui-ux-2026-10/` are marked Done or explained, with screenshots in `reviews/ui-ux-2026-10/after/`.

- [ ] **Today:** the ranked queue (its engine is built), the inspector from 1680px, and the rail. Held items are
  top-level. Review & copy and send back are placed as designed, and the keyboard starts on the queue.
- [ ] **Work:** What changed and Follow-ups as list | detail. Waiting to go out is a designed screen with its empty
  state.
- [ ] **Records:** the Projects table and the People table with detail panes; record pages; forms in drawers. The
  synced folder lives only in Settings.
- [ ] **Settings:** nav | form | help, save bar or autosave with Undo, "Changed · Reset", and pickers for time zone,
  language, money and dates. Appearance has the contrast warning; admin sections sit inside Settings.
- [ ] **Setup guide** as steps | step.
- [ ] **The rest:** the Stages board, the phone review mode, the hand-in drawer, Ask as a side pane on wide screens.
- [ ] **Learning on screen** (7.18): what the assistant knows and what is still unknown, on each project's page; the
  Knowledge screen under Records; each entry's use ("Used 12 times · last 2 days ago").
- [ ] **Review after the first Go** (found by journey J2): What changed shows "5 new · Show" with Needs attention
  empty while Needs you counts 5, and only one review opens by default, so an owner question can sit closed. The
  Today redesign makes the first results one clear list. After Remove, the add-on's row vanishes along with its note.
- [ ] **Found by the phase A journeys** (decisions, 2026-10-12, "What the first journeys found"): a new AI account's
  suggested name is the service's name, not its catalog id; a custom address needs no key when the service takes
  none; Follow-ups' Copy shows the message it will copy before copying, as 7.5 says (today it copies at once).
- [ ] **Mailbox and calendar passwords and addresses entered on screen** and kept like an AI key, for the core's own
  mail and calendar sources (moved from phase A; today they work only through `env:` or `file:`). The exit test and the
  owner's real use sign in to a named service instead.
- [ ] **Follow-ups' Later** (7.5): questions held for a meeting or the weekly note (`question.held_for`), kept out of To
  send.
- [ ] **Value-list values carry meaning** (design 5.4): a tone for each value, and a meaning for status values, so a value the
  person adds still ranks and colors correctly.
- [ ] **This week at every width** (7.7): a collapsed Today section, and the inspector's view when nothing is selected.
- [ ] **Notifications for "needs you" only** (7.19): opt-in, the Decide group's items, quiet hours. The targets are
  notification channels the phone already receives anywhere: the browser, mail to the person themselves, or a webhook
  (chat app or push topic). Each is checked with "Send me a test" and sends only to the person, a count by default.
- [ ] Words and accessibility throughout: the microcopy table in the review, and axe in light and dark at four widths.

The journey tests from A3 run against the new screens as they land.

## Phase C: the packs in the owner's workspace (about 9 sessions)

**Exit test:** in the owner's own workspace:
- the writing pack takes a fictional manuscript from import to a built PDF and EPUB the owner approves;
- the project management pack holds the project's plan and builds a schedule from it, and the schedule shows what is
  late or at risk;
- the publishing pack starts a launch for the book, with its plan in the schedule, a listing sheet and prices;
- the hand-offs between the packs work, and each pack also works alone;
- **the packs learn too:** a correction in a pack's own work produces a proposal, and a later similar input in that pack
  comes out right. This proves the plugin API call in L2 carries the knowledge to packs.

C1. **The writing pack, installed and reviewed.**
- [ ] **A pack's own libraries install from the screen** (round 35, moved from phase A): a release names every package it
  needs with checksums. Install shows what will be added, refuses conflicts with the app's own, and Remove takes out only
  what that pack needed. Answered with plugin question 183 (file types a pack needs).
- [ ] It installs from Add-ons with its libraries.
- [ ] Its two load notes are settled: SVG and TIFF files the workspace doesn't accept yet.
- [ ] Its open questions are answered: 170, a review accepting a group of the assistant's changes at once; 172,
  guide fixes.
- [ ] A host-side review of the pack: what it registers and reaches, its rules, and its tests run against this host.
  It is checked on 2026-10-12 to load and register on plugin API 0.3.55.
- [ ] The owner's walkthrough on a fictional book, with what to change written down.

C2. **The project management pack: started** (owner, 2026-10-12). This is an AI project manager that knows what is
being done, builds schedules and tracks action items.
- [ ] Create its private repository, with a brief and a builder session like the other packs.
- [ ] The core keeps what every kind of work needs: actions with owners, questions, follow-ups, decisions, Today. The
  pack adds planning on top, through ops and the core's records:
  - [ ] **The plan:** goals, phases, deliverables and milestones.
  - [ ] **The schedule:** work items with durations and dependencies, a critical path, dates worked out from the
    dependencies, baselines, and slips against them. Only the person rebaselines.
  - [ ] **Building it with the assistant:** from a brief, notes or another pack's milestones, the assistant drafts a
    plan and a schedule. The person approves it as any change.
  - [ ] **Tracking:** what is late or at risk each day goes to Today, with the action items behind it; a weekly status
    report is drafted for the person to send.
  - [ ] **RAID:** risks, issues, assumptions and decisions, with owners and review dates.
  - [ ] **An interface other packs use** to put their milestones into the schedule (`pm/schedule@1`). The writing pack
    puts in the book's chapters and edits; the publishing pack puts in the launch plan.
- [ ] Design 6.23 (dependencies and baselines) and 6.24 (RAID, risk reviews, escalation suggestions, cadence,
  meeting agendas) move from the core into this pack. This is a design change, recorded in decisions.

C3. **The publishing pack: started.** It doesn't exist yet. Its launch plan goes into the project management pack's
schedule when both are on, and is a plain list of milestones when it is alone.
- [ ] Create its private repository, with a brief and a builder session like the other packs.
- [ ] First version, from design 9.7 and the writing pack's `docs/publishing-pack.md`:
  - the title record;
  - a launch plan from a template, with lead times;
  - contributors;
  - Today lines and panels;
  - the listing sheet per platform and the price calculator, from dated platform data;
  - the AI-disclosure answers filled from the authorship breakdown;
  - the `publishing/manuscript-source@1` hand-off.

C4. **What the packs need from the core.**
- [ ] **The publisher and the file channel.** Approved files are saved or shared after the person approves the exact
  content. Waiting to go out lists them, with a diff where it applies.
- [ ] **Fact lookups** (6.19): published dates are looked up from the configured sources, never asked.
- [ ] Anything else either pack's builder asks for, answered in one weekly round.

## Phase L-more: the rest of learning (about 4 sessions)

After the packs, beside real use (owner, 2026-10-12). None of it is needed for the loop to work. Each item has its own test.
- [ ] Ask gets the knowledge section, with the same citation check, and a rule or fact stated in Ask becomes a proposal
  that applies at once with Undo (6.25).
- [ ] Take my lessons: lessons, rules and general glossary terms to a file and back into another workspace. A file from
  the person's own workspace (signed with its key) loads as active; any other file loads as proposed, on one review list.
- [ ] A pack's guidance shown before it is turned on, and marked by origin in the knowledge log (design 12.8).
- [ ] The agent lockdown test checks that a dummy environment variable isn't visible.
- [ ] Part 8's rules become the core playbook's seed lessons, each with a guard kind and its fixture ids. The page is
  generated from them, and the self-check fails when it is stale. A fixture case for every instruction-only rule.
- [ ] A command-line agent's program version recorded on each run; a new version treated like an account change; the
  program's own auto-update turned off where it allows.
- [ ] Probation ended early from the quality panel; probation work marked on Today.
- [ ] The unused-entries list, offered for retirement.
- [ ] Show and restore one record as it was at a past time, from the ledger.

## Phase D: owner validation and real use

Real use itself starts at the end of phase L-core; this phase is the sign-off once the packs are in.

**Exit test:** the owner's own judgment, on dates the owner sets: a week of real notes, mail and pack work saved
time, nothing went out without approval, a backup succeeded, and the repeat-correction rate fell over the weeks of use.

- [ ] The acceptance scenario run by the owner on real material.
- [ ] A week of real use; friction recorded in `ux-notes.md` and fixed in order of cost.
- [ ] **Microsoft mail and calendar set up as well as Google, before 1.0** (owner, 2026-10-12). The owner's exit test
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
- [ ] Learning on real material (6.22): voice per recipient beyond the first style notes, and a fact's freshness checked
  before an outward draft, with disagreements between sources recorded as private
  discrepancies to ask about.

## Phase E: the rest of version 1

Order by what protects real data first, then by what the packs ask for:
- [ ] **The governor:** stale-item sweeps, outage handling, the scheduled export with its remote; restore to a point in
  time (a single record comes in phase L).
- [ ] **Retention, and export and forget a person** (design 5.2, 12.4): forgetting is a recorded redaction, with the local
  export repository rebuilt; evidence quotes survive retention. The forget travels through the synced folder: the history
  comparison treats redacted entries as matching, and the loading computer replays the forget. Undo never restores a
  forgotten value.
- [ ] Scope resolver (6.18), the scheduled rules and lessons review with promotion (6.21), and read-backs (6.7).
  Dependencies, baselines and RAID moved to the project management pack (C2).
- [ ] Native AI adapters and reproducible runs (6.16).
- [ ] **M0, the desktop installer:** no Python, uv, Node or terminal; it updates itself.

## Publish 1.0

- [ ] Self-check against the private workspace (`cockpit selfcheck --workspace <path>`).
- [ ] A fresh repository with one starting commit, under Apache-2.0; secret scanning on.
- [ ] The README and docs match what 1.0 does.

## Not in 1.0

- Hosted mode and sign-in (Part 11).
- Social, email and newsletter channels.
- The sales pack (13.3).
- Licensed (paid) packs: the design is accepted, but whether to charge is the owner's call, after launch.

## Done before this plan

Kept for the record; details are in `docs/decisions.md` and the git history.

**Core and safety:**
- the launch slice;
- people and projects;
- the plugin host and plugin API 0.3.55 with the generated guide and the testing kit;
- stages;
- cost control;
- guided setup and the Settings forms;
- agent accounts;
- ask the assistant.

**Documents and data:**
- long text with versions and authorship;
- drafts, the compare view and working copies;
- independent second opinions;
- interfaces between plugins;
- the synced folder.

**Inputs:**
- watchers, triage and the core folder, feed, calendar and mailbox sources;
- sign-ins that start their sources;
- the Google and Microsoft mail and calendar add-on, in its own repository and listed in the catalog.

**The redesign:** its design, foundation and shell.

**Packs:** the define-your-own kit with templates.
