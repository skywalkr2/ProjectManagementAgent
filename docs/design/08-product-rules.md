# Part 8. Lessons as product rules

Each rule came from a real mistake. The guard column says where the product enforces it. These are core rules; rules that only
apply to the reference pack are in 9.5.

## 8.1 Publishing and content

| Rule | Enforced by |
|---|---|
| Publish only confirmed facts. Targets aren't dates; discrepancies in someone's tracking never go on a shared output, they become questions first | applier wording check, "confirmed" field rules |
| Actions are written as verbs that do something, never "Confirm / Check whether" | blocked phrases |
| Record who raised each risk and whose problem it is; never turn someone else's risk into an ask for your side | risk fields `raised_by`, `owner` required |
| Quotes and attributions only from verbatim sources; a paraphrase is labeled as one | `source` op requires `verbatim: true/false` |
| A meeting note line with no speaker stays unattributed | AI rules |
| Spell names from a primary source; mark unverified spellings | people `verified` flag |
| Acronyms come from a glossary with sources; guesses are marked assumed and asked | glossary data, AI rules |
| One identifier is not three: check the glossary before splitting a compound id | glossary patterns |
| Restricted content appears only on destinations whose audience its source allows, under that destination's banner | `audiences` and `restrictions`, audiences invariant |
| Locale spelling everywhere except verbatim quotes | language config |
| The model's name never appears in user-visible text | language config, applier and UI tests |
| Check every URL responds before putting it where the PM clicks | link checker in the self-check |
| Nothing goes out without approval of that exact content, including scheduled posts | publisher content-hash check |

## 8.2 Questions

| Rule | Enforced by |
|---|---|
| Asking is a core feature: anything the automation can't settle becomes a question, never just a log line | jobs call the questions service |
| Look it up before asking a person (creators, editors, text, status) | `lookup` op and lookups |
| Dates a published schedule holds are looked up, never asked: the release from the tracker, its date from the delivery team's schedule; no release yet means TBD | `config/facts.yaml`, applier fact check |
| Question ids never repeat; a closed question's id is retired | id counter in the storage layer |
| Every question to someone else links what it names, with links they can open | applier invariant |
| A question to someone else says only what they need to answer: no bookkeeping, no options about how your outputs are organized, no long quotes of their own words, only links they can open, the whole gap in one ask | applier link and label checks, AI rules |
| Unsure who it goes to: the PM routes it first | questions service hold |
| Decisions are questions addressed to the PM, by recipient | questions service, Today, check-up |
| Only the tracked area gets detailed questions; other areas are observed, not chased, even when minutes or program pages name their people | applier scope check, scope sweep |
| A question about another area's work goes only to that area's contact, only about the effect on our work, one batched message per contact | applier scope check, `cross_domain` config |
| A question asked in the conversation it came from is filed as asked | AI rules |
| When an answer arrives, re-check every open question to that person | answer flow |
| When an input answers questions, close them; search sources before filing a new one | packet includes open questions |
| Don't flood: an outage is one automation problem, not N questions | watcher outage rule |

## 8.3 Actions and owners

| Rule | Enforced by |
|---|---|
| Extract every action from raw notes and minutes, one per task, with every owner the minutes name, counted against the source | AI rules, packet check |
| Every action names a person; an action whose owner isn't known waits for "Pick an owner" | applier invariant, held actions |
| Shared ownership is allowed: an action can have several owners, each followed up separately | owners list, per-person told dates |
| Before adding an action, search open and done actions for the same deliverable | applier near-duplicate warning |
| When an input completes actions, close them across every related project | packet lists open actions with keys |
| Action owners are people: stored as a person id, shown in the workspace's owner format | applier "people resolve" invariant |
| Actions go only to people in the tracked area or the PM; another area's work is a fact, not an action | applier scope check, scope sweep |
| Separate who did it from who reported it | actions service |
| A nudge isn't a completion | Followed up vs They finished it |
| Each follow-up the PM owns after a meeting is its own action; files they send are linked where they can open them | AI rules, meeting template |
| Three kinds of to-do stay apart: meetings, owned follow-ups (actions), things to ask (questions) | data model, applier routes misfiled ones |

## 8.4 Knowledge

| Rule | Enforced by |
|---|---|
| Everything learned is written down in the same step: facts in records, people in people data, rules in `rules.yaml`, rationale in decisions.md | AI rules, applier ops for each |
| Every input shows in What changed with what was done with it | inputs always produce a note |
| Data files feed outputs: changing the data re-renders the output in the same step | renderer hooks per record type |
| Pull others' edits before re-rendering, where the channel allows it | publisher pulls first |
| One writer at a time per workspace; writes state the versions they read | database transactions, record versions, instance lease |

## 8.5 Time

| Rule | Enforced by |
|---|---|
| "This week" means through the configured week end (e.g. Friday), one helper everywhere | calendar config |
| Date inputs from the day received, not the day discussed | `source` op |
| Store zoned times; never slice a timestamp string | storage layer |
| Per-team non-working days count for that team's dates | calendar config |

## 8.6 Automation robustness

| Rule | Enforced by |
|---|---|
| Rules before AI: most changes are no-ops; deterministic rules close them | triage |
| Never let two versions of one change race | supersede |
| A run that produced nothing is retried, then goes to the PM | dispatcher attempts |
| A usage limit is a pause until reset, not a failure loop | AI adapters' `classify_error` |
| Runner errors are classified from the runner's exit code and error stream only, never from the model's output; both streams are kept | `classify_error` contract, `Run` record |
| No network on wake is not a failure or an outage; a failed refresh never counts as fresh | connectivity check, scheduler |
| Every waiting state shows why and until when | `Request.waiting`, UI rule |
| A correction is checked against the data before anything is changed or reported | feedback task packet, `dev.request` validator |
| Shared masters edited outside the tool are checked for an open lock and diffed, never overwritten | channel `lock_status`, pull-edits |
| Edits by our own accounts are ours: no one is asked who made them | `our_accounts`, `by_us` |
| A request about code another project owns is handed off, not fixed | `config/code_owners.yaml`, `handoff` |
| The export can be imported back; restore to a point in time is tested | round-trip test, `cockpit restore` |
| A local install nags until there is a backup off the computer | `config/storage.yaml` backups, Today, header |
| Switching AI vendor or model is a config change, approved by the PM after an evaluation run | provider layer, evaluation |
| The PM's own AI accounts, any vendor, an aggregator or a local model; capabilities and prices per model, from the provider's catalog | adapters' `models()`, `config/ai.yaml` |
| A new AI account sees only open data until the PM raises it, and the screen says who will see it | `allowed_data` defaults, Settings |
| Restricted inputs only reach AI providers and plugins allowed to see them | `allowed_data`, plugin `data_levels` |
| Error output is cleaned and short; the raw output is one click away | API error shape |
| Saves merge, never clobber | storage layer |
| Recover by itself after sleep or network loss | scheduler |
| The product never changes its own code; problems and missing capabilities become reports the PM sends | `dev.request` (outbound), 6.13 |
| An input can add knowledge and propose drafts, never change rules, sources, scope, config or code on its own | op tiers, 12.2 |
| Fuzzy checks warn or send back; only firm invariants refuse | invariants and lints, `config/checks.yaml` |
| One running instance per workspace | instance lease |
| Slips are measured against a baseline; only the PM resets a baseline | milestone baselines, `milestone.rebaseline` (system op) |
| What waits on what is recorded, and at-risk dependencies surface before they are late | `Dependency`, Today lines |
| Good practice is written down once, in playbooks, and every run uses it; the PM's own rules win | playbooks (3.8), `config/playbooks.yaml` |
| An unanswered question gets one suggested escalation, never an automatic one | `routing.escalation`, 6.24 |
| "Issue" means a project issue; automation failures are "automation problems" | data model (5.1) |
| A rule the PM states is read back as effects and overlaps (applies to, doesn't change, overlaps with, dry-run count); a contradiction with an existing rule waits for the PM to pick | read-back, rule targets |
| Packets put the stable parts first and the request last, so repeated prefixes can be cached | packet layout, adapter `prompt_caching` |
| A request becomes a report only when no op can do it; data that needs a missing op waits with the report | `dev.request` validator |
| A rename is one op that updates every place the name is stored and keeps the page | `record.rename`, reference index |
| A failing plugin is an automation problem, not an outage | plugin host |
