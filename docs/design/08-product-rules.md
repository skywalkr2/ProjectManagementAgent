# Part 8. Lessons as product rules

Each rule came from a real mistake. The guard column says where the product enforces it. These are core rules; rules that only
apply to the reference pack are in 9.5.

**State of enforcement (the audit of 2026-10-12).** A rule stays a rule when its guard is not built. "(not yet enforced)"
means nothing in the code does what the guard column says; "(partly enforced: ...)" says what exists. An unmarked guard has
code and a test. Version 1 builds the missing guards in the order of the roadmap (13.4); dependencies, baselines, risks and
escalation move to the project management pack (9.10).

**These rules become data** (*designed, phase L-more*; decisions, 2026-10-12 "Product rules are the core playbook's seed
lessons"). After phase L, lessons are records with ids, targets and status (6.22). The rules on this page become the core
playbook's **seed lessons**: records shipped with the product, carried in packets like the person's own lessons, and pointed
at by fixtures. This page is then generated from them, as the plugin guide is generated from the code. So:
- a product rule and a learned lesson are the same kind of thing;
- the person's own lessons and rules layer on top, and theirs win by id (3.8);
- the test "doesn't repeat a corrected mistake" covers the shipped rules too.

**Guard kinds** (*designed, phase L*). Each rule's guard has one kind:
- **invariant:** the applier always refuses;
- **lint:** returned once, then held or warned (4.17);
- **code:** built into how the engine works;
- **instruction:** text the model is given, and nothing else.

An instruction is the weakest guard: the original scope failure was an advisory rule that read as if it were enforced. So:
- every instruction-only rule has at least one fixture case in the evaluation, which a model switch reruns (6.22);
- a rule whose only guard is an instruction counts as partly enforced until that case exists.

The generated page shows the kind beside each guard. Seed lessons whose guard is an instruction or a lint go into the packets
they apply to. Those guarded by an invariant or code still give the model their constraint, but only as one line:
- **In the op reference.** Each one adds a line to the reference of the ops it constrains ("every action names a person",
  "a question to someone else carries a link they can open"). Otherwise runs keep producing changesets the applier refuses,
  and each refusal costs a retry. The self-check fails when an invariant has no such line. Some of these lines exist today
  in the core ops' own descriptions.
- **Refusals counted per check.** Each run records its refusals by check name. When one check refuses more than
  `knowledge.refusals_to_packet` of a task kind's recent runs (default 5% of the last 50), its full seed lesson joins that
  task kind's packets automatically. It leaves again once the rate drops. The quality panel lists refusals per check and
  which lessons were added this way (6.20).

## 8.1 Publishing and content

| Rule | Enforced by |
|---|---|
| Publish only confirmed facts. A target is a date, a quarter or TBD, never a sentence, and the detail goes in the notes; discrepancies in someone's tracking never go on a shared output, they become questions first | applier wording check, "confirmed" field rules (not yet enforced): no confirmed-fact model and no publisher yet |
| Actions are written as verbs that do something, never "Confirm / Check whether" | blocked phrases |
| Record who raised each risk and whose problem it is; never turn someone else's risk into an ask for your side | risk fields `raised_by`, `owner` required (not yet enforced): risk records belong to the project management pack (9.10) |
| Quotes and attributions only from verbatim sources; a paraphrase is labeled as one | `source` op requires `verbatim: true/false` (not yet enforced): no `source` op or verbatim flag |
| A meeting note line with no speaker stays unattributed | AI rules (not yet enforced) |
| Spell names from a primary source; mark unverified spellings | people `verified` flag (not yet enforced): people have no `verified` flag |
| Acronyms come from a glossary with sources; guesses are marked assumed and asked | glossary data, AI rules (not yet enforced): no glossary yet |
| One identifier is not three: check the glossary before splitting a compound id | glossary patterns (not yet enforced): no glossary yet |
| Restricted content appears only on destinations whose audience its source allows, under that destination's banner | `audiences` and `restrictions`, audiences invariant (not yet enforced): data levels route AI work today; audiences and restrictions are not built |
| Locale spelling everywhere except verbatim quotes | language config (partly enforced: the project's language reaches plugin packets; the core's notes packet carries no language instruction and nothing checks it) |
| The model's name never appears in user-visible text | language config, applier and UI tests |
| Check every URL responds before putting it where the PM clicks | link checker in the self-check (not yet enforced): the self-check has no link checker |
| Nothing goes out without approval of that exact content, including scheduled posts | publisher content-hash check (partly enforced: Follow-ups copy, then Mark sent; the publisher, channels and the content-hash check are not built) |

## 8.2 Questions

| Rule | Enforced by |
|---|---|
| Asking is a core feature: anything the automation can't settle becomes a question, never just a log line | jobs call the questions service (partly enforced: a failing watched source files one question; a failing plugin job becomes a plugin note, not a question) |
| Look it up before asking a person (creators, editors, text, status) | `lookup` op and lookups (not yet enforced): no `lookup` op yet |
| Dates a published schedule holds are looked up, never asked: the release from the tracker, its date from the delivery team's schedule; no release yet means TBD | `config/facts.yaml`, applier fact check (not yet enforced): no facts config or resolver yet |
| Question ids never repeat; a closed question's id is retired | id counter in the storage layer |
| Every question to someone else links what it names, with links they can open | applier invariant |
| A question to someone else says only what they need to answer: no bookkeeping, no options about how your outputs are organized, no long quotes of their own words, only links they can open, the whole gap in one ask | applier link and label checks, AI rules (partly enforced: the link check is built; label, length and bookkeeping checks are not) |
| Unsure who it goes to: the PM routes it first | questions service hold |
| Decisions are questions addressed to the PM, by recipient | questions service, Today, check-up (partly enforced: no weekly check-up yet) |
| Only the tracked area gets detailed questions; other areas are observed, not chased, even when minutes or program pages name their people | applier scope check, scope sweep (not yet enforced): no scope resolver yet |
| A question about another area's work goes only to that area's contact, only about the effect on our work, one batched message per contact | applier scope check, `cross_domain` config (not yet enforced): no scope resolver yet |
| A question asked in the conversation it came from is filed as asked | AI rules (not yet enforced) |
| When an answer arrives, re-check every open question to that person | answer flow (partly enforced: open questions are in the packet; the person's other questions are not re-checked on their own) |
| When an input answers questions, close them; search sources before filing a new one | packet includes open questions (partly enforced: open questions are in the packet; sources are not searched first) |
| Don't flood: an outage is one automation problem, not N questions | watcher outage rule |

## 8.3 Actions and owners

| Rule | Enforced by |
|---|---|
| Extract every action from raw notes and minutes, one per task, with every owner the minutes name, counted against the source | AI rules, packet check (partly enforced: the playbook says so; nothing counts the actions against the source) |
| Every action names a person; an action whose owner isn't known waits for "Pick an owner" | applier invariant, held actions |
| Shared ownership is allowed: an action can have several owners, each followed up separately | owners list, per-person told dates |
| Before adding an action, search open and done actions for the same deliverable | applier near-duplicate warning (open and done actions; **built:** `tests/test_near_duplicate.py::test_the_check_compares_with_done_actions_too`) |
| When an input completes actions, close them across every related project | packet lists open actions with keys |
| Action owners are people: stored as a person id, shown in the workspace's owner format | applier "people resolve" invariant (ids are stored; where the app shows an action's owners it writes them in `workspace.owner_format`, 6.11) |
| Actions go only to people in the tracked area or the PM; another area's work is a fact, not an action | applier scope check, scope sweep (not yet enforced): no scope resolver yet |
| Separate who did it from who reported it | actions service (not yet enforced) |
| A nudge isn't a completion | Followed up vs They finished it |
| Each follow-up the PM owns after a meeting is its own action; files they send are linked where they can open them | AI rules, meeting template (not yet enforced): no meeting record or template yet |
| Three kinds of to-do stay apart: meetings, owned follow-ups (actions), things to ask (questions) | data model, applier routes misfiled ones (partly enforced: actions and questions are separate; there is no meeting record and no re-routing of misfiled ones) |

## 8.4 Knowledge

| Rule | Enforced by |
|---|---|
| Everything learned is written down in the same step: facts, rules, lessons, glossary entries, routing and style notes as records with ids, people in people data, rationale in decisions.md | AI rules, applier ops for each (partly enforced: facts, notes and people have ops; the rest come in phase L, 6.22) |
| **The assistant doesn't repeat a corrected mistake.** Every correction proposes one piece of learning, and every later run reads the knowledge that applies to it | the learn task on every signal, the knowledge section of the packet, the repeat-correction signal, and the fixture pairs and day-30 scenario in the evaluation (6.22; not yet enforced: phase L, whose exit test this is) |
| Search what is already known before asking a person, looking outside or reporting to the maintainers | the `search` round and the `already-known` lint (6.22, 4.17; not yet enforced: phase L) |
| Every input shows in What changed with what was done with it | inputs always produce a note |
| Data files feed outputs: changing the data re-renders the output in the same step | renderer hooks per record type (partly enforced: the synced folder's generated files rebuild; renderers and outputs are not built) |
| Pull others' edits before re-rendering, where the channel allows it | publisher pulls first (not yet enforced): no publisher yet |
| One writer at a time per workspace; writes state the versions they read | database transactions, record versions, instance lease |

## 8.5 Time

| Rule | Enforced by |
|---|---|
| "This week" means through the configured week end (e.g. Friday), one helper everywhere | calendar config (not yet enforced): no calendar config yet |
| Date inputs from the day received, not the day processed: "by Friday" in a message received on Monday means that week's Friday | the packet header carries the input's received date, the source item's own received time (enforced: `tests/test_names.py::test_the_packet_states_the_inputs_received_date_beside_todays`, `test_a_watched_items_received_date_is_its_own_received_time_not_when_it_changed_or_was_read`) |
| Store zoned times; never slice a timestamp string | storage layer (partly enforced: nothing requires timezone-aware values) |
| Per-team non-working days count for that team's dates | calendar config (not yet enforced): no calendar config yet |

## 8.6 Automation robustness

| Rule | Enforced by |
|---|---|
| Rules before AI: most changes are no-ops; deterministic rules close them | triage |
| Never let two versions of one change race | supersede |
| A run that produced nothing is retried, then goes to the PM | dispatcher attempts (partly enforced: fix rounds exist; an empty or failed run is retried by hand) |
| A usage limit is a pause until reset, not a failure loop | AI adapters' `classify_error` (partly enforced: rate-limit waits resume; a quota or budget pause does not resume by itself at reset) |
| Runner errors are classified from the runner's exit code and error stream only, never from the model's output; both streams are kept | `classify_error` contract, `Run` record |
| No network on wake is not a failure or an outage; a failed refresh never counts as fresh | connectivity check, scheduler |
| Every waiting state shows why and until when | `Request.waiting`, UI rule |
| A correction is checked against the data before anything is changed or reported | feedback task packet, `dev.request` validator (partly enforced: Send back is built; the data check is not) |
| Shared masters edited outside the tool are checked for an open lock and diffed, never overwritten | channel `lock_status`, pull-edits (not yet enforced): no publisher or shared masters yet |
| Edits by our own accounts are ours: no one is asked who made them | `our_accounts`, `by_us` |
| A request about code another project owns is handed off, not fixed | `config/code_owners.yaml`, `handoff` (not yet enforced): no `config/code_owners.yaml` or handoff yet |
| The export can be imported back; restore to a point in time is tested | round-trip test, `cockpit restore` (partly enforced: the round trip is tested on the fixtures, and a whole backup restores with `cockpit restore --backup`; restoring to a point in time isn't built) |
| A local install nags until there is a backup off the computer | `config/storage.yaml` backups, Today, header |
| Switching AI vendor or model is a config change, approved by the PM after an evaluation run | provider layer, evaluation (partly enforced: `cockpit evaluate` exists; no approval step is tied to a report) |
| The PM's own AI accounts, any vendor, an aggregator or a local model; capabilities and prices per model, from the provider's catalog | adapters' `models()`, `config/ai.yaml` (partly enforced: the OpenAI-compatible and command-line agent adapters list models; no native adapters yet) |
| A new AI account sees only open data until the PM raises it, and the screen says who will see it | `allowed_data` defaults, Settings |
| Restricted inputs only reach AI providers and plugins allowed to see them | `allowed_data`, plugin `data_levels` |
| Error output is cleaned and short; the raw output is one click away | API error shape (partly enforced: errors are short; the raw output is not one click away) |
| Saves merge, never clobber | storage layer |
| Recover by itself after sleep or network loss | scheduler (partly enforced: the worker loops recover; no test covers catching up after sleep) |
| The product never changes its own code; problems and missing capabilities become reports the PM sends | `dev.request` (outbound), 6.13 |
| An input can add knowledge and propose drafts, never change rules, sources, scope, config or code on its own | op tiers, 12.2 |
| Fuzzy checks warn or send back; only firm invariants refuse | invariants and lints, `config/checks.yaml` |
| One running instance per workspace | instance lease |
| Every claim cites the exact words that justify it, and the words must be in the source | `evidence`, evidence invariant, `evidence-fit` lint |
| One input per AI call; email threads are cleaned of quoted history and signatures first | dispatcher, `cleaning` |
| Anything learned from untrusted content stays marked untrusted; lessons from inputs wait for the PM | provenance, proposed lessons (partly enforced: records carry trust; lessons do not exist yet) |
| A cheap model's failed answer is retried once on a stronger model before the PM sees it, on check results, never on self-reported confidence | `escalate_to` |
| Model choices are made on evidence: a deterministic evaluation, several runs per case | evaluation |
| Slips are measured against a baseline; only the PM resets a baseline | milestone baselines, `milestone.rebaseline` (system op) (not yet enforced): moved to the project management pack (9.10) |
| What waits on what is recorded, and at-risk dependencies surface before they are late | `Dependency`, Today lines (not yet enforced): moved to the project management pack (9.10) |
| Good practice is written down once, in playbooks, and every run uses it; the PM's own rules win | playbooks (3.8), `config/playbooks.yaml` (partly enforced: the core playbook for notes exists; there is no `config/playbooks.yaml` to override entries by id) |
| An unanswered question gets one suggested escalation, never an automatic one | `routing.escalation`, 6.24 (not yet enforced): moved to the project management pack (9.10) |
| "Issue" means a project issue; automation failures are "automation problems" | data model (5.1) (partly enforced: failures spread over questions, `needs_you` and plugin notes; there is no Problem record) |
| A rule the PM states is read back as effects and overlaps (applies to, doesn't change, overlaps with, dry-run count); a contradiction with an existing rule waits for the PM to pick | read-back, rule targets (not yet enforced): there is no read-back yet |
| Packets put the stable parts first and the request last, so repeated prefixes can be cached | packet layout, adapter `prompt_caching` (partly enforced: the layout is built; adapters have no `prompt_caching` capability yet) |
| A request becomes a report only when no op can do it; data that needs a missing op waits with the report | `dev.request` validator (partly enforced: `report.draft` exists; data waiting with the report does not) |
| A rename is one op that updates every place the name is stored and keeps the page | `record.rename`, reference index (partly enforced: ids and the reference index exist; there is no `record.rename` op) |
| A failing plugin is an automation problem, not an outage | plugin host |

## 8.7 Rules from the review of 2026-10-12

The review asked why small errors kept reaching the owner. Each rule below answers one cause (decisions, 2026-10-12 "The
go-forward plan"; `CLAUDE.md`, "How work reaches the owner").

| Rule | Enforced by |
|---|---|
| Every default produces a visible result for a real person, with no file editing and no second command | the brief, the journey tests and the fresh-workspace check (10.5; planned) |
| A real workspace starts from `cockpit init` with no template; the fictional workspaces are test fixtures and the sandbox, never a starting point | docs, the setup guide, the fresh-workspace check (10.5; planned) |
| Nothing goes out without the PM approving that exact content. This stays whatever else changes | publisher content-hash check (not yet enforced, see 8.1); until then, copy and Mark sent are the only way out |
| Signing in is the whole setup for a mail or calendar account: the sources the add-on declares start at once and read the inbox and main calendar, and the person narrows afterwards | `sign_in(..., sources=...)`, `engine/sign_in_sources.py` |
| A real AI account does the assistant's work as soon as it is added; an unused account offers "Use for the assistant's work" | account add flow (7.16) |
| The app restarts only when it must and only when the person says so; a setting everything reads at the moment of use applies at once | `LIVE_KEYS` in the worker, the Restart now ask |
| No file name, config key path, `env:` reference or command line reaches the screen on the default path, including text built by the server | wording sheet tests for the screens; the server-side string scan (10.5; planned) |

The review's rules for how the product is built (journey tests before "ready to test", a failing test first, never marking a
plan item done on a part) don't reach a person's workspace, so they are in 10.5, not here.

## 8.8 Rules added from the first design author's review of Part 8

Rules from the running deployment that were in the change notes or Part 6 but not on this list (decisions, 2026-10-12). Since
this list is what gets enforced and tested, each is a row. The guard kind is in brackets.

| Rule | Enforced by |
|---|---|
| Unknown stays blank or TBD, never a placeholder. Some fields are filled only from one named person's input (a priority, say), and the gap becomes a question to that person | [invariant] person-owned fields in the applier (partly enforced: plugins have person-only values, 0.2; a core project's priority is person-only; other core fields have no owner yet) |
| Out-of-scope items are parked with the reason, never dropped, and can be brought back on request | [code] a parked state and the scope sweep (not yet enforced: scope, 6.18, is phase E) |
| If the area's expert says it isn't theirs and doesn't know whose, stop: park it, don't reroute it around the organization | [code] routing entries and the question flow (not yet enforced: routing entries come in phase L) |
| Values written to an outside system are in its canonical form; after a publish, re-pull and check that no difference remains | [code] the publisher and connector normalizers (not yet enforced: no publisher) |
| Adding or changing an AI account smoke-tests every tier with the exact parameters, plus the lock-down for agents; no silent default provider | [code] provider onboarding and the self-check (partly enforced: the smoke test runs every tier on request and the lock-down per agent account; it is not yet run on every change) |
| A fallback is a switch: only checked accounts sit in a fallback chain, and the first run on one is marked | [code] the provider layer (not yet enforced: phase L, 6.16) |
| Every file type a watched source can hold has an extractor, or is flagged once as unsupported; the person is never asked to paste a file's text | [code] extractors and the packet builder (not yet enforced: phase L, 6.2) |
| Inputs are recognized by content, not file name: a moved or renamed file is matched to what is already registered before it is read again | [code] content hash and triage (partly enforced: pasted sources are stored by content hash; a moved file in a watched folder is not yet matched) |
| Today shows only things the person does, each starting with the verb and saying where; status and progress never sit on Today | [code] the Today line contract (partly enforced: the queue's lines are things to do; the verb-first wording is not checked) |
| The person sees only what needs them: a changeset with nothing to approve, decide or answer closes itself, with a way to pull it back | [code] the applier and the auto-closed list (partly enforced: watched changes are auto-closed by triage rules; a changeset with nothing to review does not yet close itself) |
| Text the person copies to send stays clean: no provenance, internal ids or approval notes inside the copyable part | [lint] a copy-block lint in the renderer (partly enforced: follow-up messages carry none; nothing checks it) |
| Anything with more than one item is a list, one item per line, never joined with separators | [lint] `run-on-list` |
| Neutral wording about other people's work in shared outputs ("moved", not "slipped"); teams, not individuals, own risks | [lint] wording lint (partly enforced: `blocked-wording` takes a configured word list; no neutral-wording list ships) |
| Learning proposals never flood the home screen: proposals from inputs come as one daily card, merged, expiring with a count | [code] 6.22, 7.18 (not yet enforced: phase L) |
| A direct edit of something the assistant set is a correction | [code] the `edited` signal (not yet enforced: phase L, 6.20) |

**What is enforced first, for the first real use.** The first real use is a writer's own work plus mail and calendar, so the
rules that bite first are not the workplace ones:
- **Phase L0, the start of L-core, before real use:** dates from the day received (8.5, built); a usage limit resuming by itself at its reset (8.6); an empty or failed run
  retried automatically, then sent to the person (8.6). Without the last two, the assistant stops silently on the first quota
  day and the person thinks it's broken.
- **Phase L, before real use starts:**
  - the knowledge rules (8.4);
  - verbatim versus paraphrase, and unattributed lines (8.1);
  - names spelled from a primary source (8.1);
  - every link checked before it is shown (8.1).

Scope, schedule lookups and dependencies wait for the workplace and project management packs.

