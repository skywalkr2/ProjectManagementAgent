# PM Cockpit audit: design Parts 8–13, the project plan, and untested end-to-end paths (read-only)

I edited nothing. Repo root is `/home/user/ProjectManagementAgent`; every path below is relative to it.

**What is in the repository**
- **Bundled plugins:** only `plugins/example` and `plugins/kit`. There is no `plugins/workplace-pm` or `plugins/publishing`, and no `deploy/container` or `deploy/<target>` recipes.
- **AI adapters:** `stub`, `openai_compatible` and `cli_agent` (`engine/ai/adapters/__init__.py:19`).
- **Ops** (`engine/ops.py:438`): note, fact, record.set, record.log, action.add, action.close, question.add, question.done, person.add, stage.move, record.delete, file.add, project.add, record.edit, text.*, answer, setting.propose, list.*, report.draft.
- **Ops that are absent:** `source`, `lookup`, `glossary.add`, `lesson.add`, `risk.add`, `record.rename`, `milestone.rebaseline`, `dev.request`/`handoff`.
- **Config files** (`engine/config/schema.py:969`): workspace, server, storage, ai, dispatch, checks, language, ui, stages, rules, watch.
- **Config files that are absent:** facts, scope, auth, playbooks, code_owners, raid, calendar.
- **Tests:** 721 Python tests; Playwright has `web/e2e/acceptance.spec.ts` and `web/e2e/shell.spec.ts`.
- **CI** (`.github/workflows/ci.yml`) runs ruff, pytest, the self-check, vitest, the web build and Playwright (root and `/admin`). It never runs `COCKPIT_TEST_CORE_ONLY=1`.

---

# GOAL 1: Gap tables

## Part 8: Product rules (each "where it is enforced" claim checked against the code)

### 8.1 Publishing and content
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| Publish only confirmed facts; discrepancies become questions | applier wording check, "confirmed" field | Missing | no `confirmed` field; `confirmed_by_pm` only (`engine/applier.py:101`) | No confirmed-fact model and no publisher, so nothing to gate. |
| Actions are verbs, never "Confirm / Check whether" | blocked phrases | Built | `engine/applier.py:296-301`, `engine/config/schema.py:624`; `tests/test_pipeline.py::test_blocked_wording_warns_on_internal_items_and_holds_what_goes_to_others` | — |
| Record who raised each risk and whose it is | risk fields `raised_by`, `owner` | Missing | no Risk record in `engine/records.py` | No risk record or fields. |
| Quotes only from verbatim sources; paraphrase labeled | `source` op `verbatim` | Missing | no `source` op; no "verbatim" anywhere | No `source` op and no verbatim flag. |
| Meeting line with no speaker stays unattributed | AI rules | Missing | not in `engine/prompts/notes.md` or `engine/playbook/guidance/notes.md` | No such rule. |
| Spell names from a primary source; mark unverified | people `verified` flag | Missing | `Person` has no `verified` (`engine/records.py:202-228`) | No flag. |
| Acronyms from a glossary; guesses marked assumed | glossary data, AI rules | Missing | no glossary anywhere | No glossary. |
| One identifier is not three | glossary patterns | Missing | — | No glossary. |
| Restricted content only on destinations its audience allows | `audiences`, `restrictions`, invariant | Missing | no audiences or restrictions in code | Data levels exist for AI routing only. |
| Locale spelling except verbatim quotes | language config | Partial | `workspace.language`, `Project.language`; told to the model only in plugin packets (`engine/packet.py:253`) | Notes packet gets no language instruction; no check. |
| Model's name never in user-visible text | language config, applier and UI tests | Built | `engine/applier.py:283-287`, `engine/dispatcher.py:83`; `test_model_names_never_reach_text_people_see` | No UI-side test. |
| Check every URL responds before the PM clicks it | link checker in self-check | Missing | `engine/selfcheck/__init__.py:93-105` has no link check | No link checker. |
| Nothing goes out without approval of that exact content | publisher content-hash check | Partial | Follow-ups Copy then Mark sent (`engine/followups.py:120`) | No publisher, no content-hash approval, no channels. |

### 8.2 Questions
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| What automation can't settle becomes a question | jobs call questions service | Partial | watch failure files one question (`engine/watch.py:389`); dispatcher uses `needs_you` | Plugin job failures become plugin notes, not questions. |
| Look it up before asking | `lookup` op | Missing | no lookup op | Missing. |
| Published dates are looked up, never asked; none means TBD | `config/facts.yaml`, applier fact check | Missing | no facts config or resolver | Missing (one eval case only: `printer-proof-date`). |
| Question ids never repeat | id counter | Built | `tests/test_store.py::test_deleted_ids_are_never_reused` | — |
| A question to someone else links what it names | applier invariant | Built | `engine/applier.py:253-261`; `test_questions_to_others_need_a_link_they_can_open` | — |
| Say only what they need; links they can open; one ask | applier link and label checks, AI rules | Partial | link check plus playbook text | No label, length or bookkeeping checks. |
| Unsure who it goes to: PM routes first | questions service hold | Built | `engine/applier.py:638-650, 997`; `test_an_unknown_name_is_held_with_a_who_is_this_question` | — |
| Decisions are questions to the PM | questions service, Today, check-up | Partial | `QuestionAddOp.kind=decision`; Today "decide" group (`engine/today_queue.py:21`) | No weekly check-up. |
| Only the tracked area gets detailed questions | applier scope check, scope sweep | Missing | no scope | Missing. |
| Another area's question: one batched message per contact | scope check, `cross_domain` | Missing | — | Missing. |
| Asked in its own conversation → filed as asked | AI rules | Missing | not in prompts | Missing. |
| An answer re-checks every open question to that person | answer flow | Partial | `/questions/{qid}/reply` (`test_a_reply_is_handed_in_against_its_question_and_closes_it`); open questions are in the packet | No explicit re-check of the person's other questions. |
| An input closes questions; search sources first | packet includes open questions | Partial | `engine/packet.py:96, 394` | No source search. |
| An outage is one problem, not N | watcher outage rule | Built | `engine/watch.py:389-433`; `test_failures_ask_once_and_a_good_read_ends_the_question` | — |

### 8.3 Actions and owners
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| Every action extracted, counted against source | AI rules, packet check | Partial | playbook `notes.md` | No count check. |
| Every action names a person; unknown owner waits for "Pick an owner" | applier invariant, held actions | Built | `engine/applier.py:1095`; `test_an_action_with_no_owner_waits_for_pick_an_owner` | — |
| Shared ownership, each followed up separately | owners list, told dates | Built | `Action.owners`, `Action.told` (`engine/records.py:316, 324`); `test_shared_actions_keep_every_owner` | — |
| Search open and done actions for duplicates | near-duplicate warning | Partial | `engine/applier.py:116, 267-270` | Checks open actions only. |
| Input completes actions across related projects | packet lists open actions | Built | `engine/packet.py:95, 381` | — |
| Owners stored as person ids, shown in owner format | "people resolve" invariant | Partial | ids built (`engine/names.py`) | `workspace.owner_format` (`engine/config/schema.py:142`) is never read anywhere. |
| Actions only to tracked area or PM | scope check | Missing | — | — |
| Separate who did it from who reported it | actions service | Missing | — | — |
| A nudge isn't a completion | Followed up vs They finished it | Built | Follow-ups "Waiting on them" with "They finished it" (`web/e2e/acceptance.spec.ts:283`) | — |
| PM's follow-ups after a meeting are their own actions | AI rules, meeting template | Missing | no meeting template | — |
| Three kinds of to-do stay apart; misfiled ones routed | data model, applier | Partial | actions and questions are separate | No meeting record; no re-routing. |

### 8.4 Knowledge
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| Everything learned written in the same step | AI rules, ops | Partial | fact, note, person ops | No rules.yaml op, no glossary or lessons. |
| Every input shows in What changed | inputs always produce a note | Built | every request becomes a changeset on What changed; `test_a_hand_in_is_processed_and_shows_in_what_changed` | — |
| Changing data re-renders outputs | renderer hooks | Partial | synced-folder generated files rebuild (`tests/test_outside.py::test_generated_files_are_written_and_rebuilt_when_edited`) | No renderer or outputs. |
| Pull others' edits before re-rendering | publisher pulls first | Missing | — | No publisher. |
| One writer; writes state versions read | transactions, versions, lease | Built | `tests/test_store.py:64,73`, `tests/test_lease.py` | — |

### 8.5 Time
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| "This week" through configured week end, one helper | calendar config | Missing | only `user.timezone` (`engine/config/schema.py:36`) | Missing. |
| Date inputs from the day received | `source` op | Partial | prompt counts from the message's date line, else today (`engine/prompts/notes.md`) | Packet uses processing date (`engine/dispatcher.py:105`), not `Source.received_at`. |
| Store zoned times; never slice timestamps | storage layer | Partial | datetime-typed fields | No aware-datetime enforcement. |
| Per-team non-working days | calendar config | Missing | — | — |

### 8.6 Automation robustness
| Rule | Claimed enforcement | State | Evidence | What is absent |
|---|---|---|---|---|
| Rules before AI | triage | Built | `engine/triage.py`; `tests/test_watch.py:273, 292` | — |
| Never let two versions race | supersede | Built | `test_a_newer_change_folds_in_the_older_one_still_waiting` | — |
| A run that produced nothing retried, then to PM | dispatcher attempts | Partial | fix rounds (`engine/dispatcher.py:337`) | No automatic retry of an empty or failed run; retry is manual. |
| Usage limit is a pause until reset | `classify_error` | Partial | rate-limit waits (`engine/ai/router.py:243`); budgets say "Paused until tomorrow" | Quota or budget doesn't resume by itself at reset. |
| Runner errors from exit code and stream only; both kept | `classify_error`, `Run` | Built | `test_error_kind_comes_from_the_call_never_from_the_model_text`, `test_cli_agent.py:126` | Stdout is not kept on `Run`. |
| No network on wake isn't a failure | connectivity, scheduler | Built | `tests/test_watch.py::test_no_network_is_not_a_failure` | — |
| Every waiting state says why and until when | `Request.waiting` | Built | `Request.waiting` in `engine/records.py`; `engine/dispatcher.py:102-170` | — |
| A correction is checked against data first | feedback packet, `dev.request` validator | Partial | send-back plus REPEATED refusal (`engine/dispatcher.py:413`) | No data check. |
| Shared masters: lock check and diff | `lock_status`, pull-edits | Missing | — | — |
| Edits by our accounts are ours | `our_accounts`, `by_us` | Built | `test_changes_by_our_own_accounts_and_scratch_files_are_closed` | — |
| Code another project owns is handed off | `code_owners.yaml`, `handoff` | Missing | — | — |
| Export imports back; point-in-time restore tested | round-trip test, `cockpit restore` | Partial | `tests/test_export.py` | No `cockpit restore` in `engine/cli.py`. |
| Local install nags until off-computer backup | storage backups, Today, header | Built | `tests/test_followups_backup_eval.py:96`; e2e `acceptance.spec.ts:115` | — |
| Switching vendor/model is config approved after an evaluation | provider layer, evaluation | Partial | `cockpit evaluate` | No approval gate tied to an evaluation. |
| PM's own accounts, any vendor; capabilities and prices per model | adapters' `models()`, ai.yaml | Partial | `catalog()` in `openai_compatible` and `cli_agent`; `tests/test_ai.py:213` | No native adapters. |
| New account sees only open data; screen says who sees it | `allowed_data` defaults | Built | `engine/config/schema.py:369`; `welcome.ai.data.*` wording | — |
| Restricted inputs only reach allowed providers and plugins | `allowed_data`, `data_levels` | Built | `tests/test_ai.py:146`, `tests/test_interfaces.py:158` | — |
| Error output short; raw one click away | API error shape | Partial | `web/src/lib/problem.ts` | No raw-output reveal. |
| Saves merge, never clobber | storage layer | Built | `test_a_stale_write_to_other_fields_merges` | — |
| Recover after sleep or network loss | scheduler | Partial | worker loops (`engine/worker.py:358-386`) | No catch-up-after-sleep test. |
| Product never changes its own code | `dev.request`, 6.13 | Built | `report.draft` (`engine/ops.py:397`); `test_something_the_app_cant_do_becomes_a_report_to_send` | — |
| An input can't change rules, sources, scope, config or code | op tiers | Built | `engine/applier.py:289-292`, `engine/ops.py:469` | — |
| Fuzzy checks warn; only invariants refuse | invariants, `checks.yaml` | Built | `engine/config/schema.py:589-604`; `test_a_lint_can_never_default_to_refusing` | — |
| One running instance | lease | Built | `tests/test_lease.py` | — |
| Every claim cites exact words | evidence invariant, `evidence-fit` | Built | `engine/applier.py:179-213`; `test_a_quote_that_isnt_in_the_input_goes_back_once_then_is_refused` | — |
| One input per call; threads cleaned | dispatcher, cleaning | Built | `engine/cleaning.py`; `test_quoted_history_already_on_file_is_removed_before_the_ai_sees_it` | — |
| Untrusted stays untrusted; lessons wait | provenance, proposed lessons | Partial | `trust` on Fact, Note, Source, File | No lessons. |
| Cheap model's failure retried once on stronger, on check results | `escalate_to` | Built | `engine/dispatcher.py:196-222`; `test_the_stronger_tier_can_fix_what_the_routine_tier_got_wrong` | — |
| Model choices on deterministic evaluation, several runs | evaluation | Built | `engine/evaluate.py`; `evaluation.runs` | — |
| Slips against baseline; only PM rebaselines | baselines, `milestone.rebaseline` | Missing | — | — |
| Dependencies recorded; at-risk ones surface | `Dependency`, Today | Missing | — | — |
| Good practice in playbooks; PM's rules win | playbooks, `config/playbooks.yaml` | Partial | `engine/playbook/guidance/notes.md` | No override-by-id file. |
| Unanswered question gets one suggested escalation | `routing.escalation` | Missing | — | — |
| "Issue" = project issue; failures = "automation problems" | data model | Partial | no Issue record | No Problem record either; failures spread over questions, `needs_you` and plugin notes. |
| PM-stated rule read back (effects, overlaps, dry run) | read-back | Missing | `rules.yaml` only used for stage moves | — |
| Stable parts first for caching | packet layout, `prompt_caching` | Partial | `engine/packet.py:1-6, 88-125`; cached-token pricing | No adapter `prompt_caching` capability. |
| Request becomes a report only when no op can do it | `dev.request` validator | Partial | `report.draft` | No data waiting with the report. |
| A rename is one op updating every place | `record.rename`, reference index | Partial | ids plus `REFERENCES`; `test_a_person_in_use_cannot_be_removed_and_a_rename_shows_everywhere` | No `record.rename` op. |
| A failing plugin is an automation problem, not an outage | plugin host | Built | `engine/plugin_host.py:1051`; `tests/test_today_panels_jobs.py:215` | — |

## Part 9: Reference and publishing packs

| Section or requirement | State | Evidence | What is absent |
|---|---|---|---|
| 9.1 The use (workplace PM) | Missing | no `plugins/workplace-pm` | Pack is a private add-on by decision (2026-10-10); Part 9 still says "bundled". |
| 9.2 Needs wiki, tracker and release connector kinds, wiki channel | Missing | — | No wiki, tracker or channel kinds. |
| 9.3 Config, `ext` fields, renderers, triage defaults, fact defaults, routing defaults, task kinds, panels, Today lines, owner format | Missing | — | Core has the extension points (`ext`, panels, Today lines, triage matchers); the pack doesn't exist. |
| 9.4 Both fictional workspaces enable the pack | Missing | `workspaces/*/config/workspace.yaml` enable `[example, kit]` only | — |
| 9.5 Pack rules (teams own risks, owner format, scope defaults, routing) | Missing | — | — |
| 9.6 Publishing: the use | Missing | not in repo | Lives in its own private repository. |
| 9.7 Title record, launch-plan template, plan-from-template, scope/fact defaults, task kinds, `publishing/manuscript-source@1`, Today lines, panels, clipboard, playbook, RAID preset | Missing | interface mechanism exists in core (`tests/test_interfaces.py`) | Pack, interface definition and playbook absent; no publishing kit template (`templates/` has only `client-work`, `content-calendar`). |
| 9.8 Not in the first version | n/a | — | — |
| 9.9 `demo-b`: one title, launch plan, contributors, fixture emails | Partial | demo-b has people, projects and 14 eval cases (`workspaces/demo-b/evals`) | No title record or launch plan; demo-b kit config is a content calendar. |

## Part 10: Guardrails

| Section or requirement | State | Evidence | What is absent |
|---|---|---|---|
| 10.1 Core holds no specific names, URLs or vendors | Built (scanned) | `engine/selfcheck/scans.py` | Only partly enforced; see 10.2. |
| 10.1 Sources are config | Partial | `watch.yaml` sources | No facts, scope or lookup config. |
| 10.1 Deploy recipes name only their platform; example.com | n/a | no recipes | — |
| 10.2.1 Specificity scan | Partial | `scans.py:113-177`; `tests/test_scans.py:43-60` | Reads only workspace name/user, person, org, team and project names/aliases, and URLs in config. Not team fields, system names, page ids, queries, folder paths or connector field names from `watch.yaml` or connector settings (facts and scope don't exist). |
| 10.2.1 `--workspace` private scan prints only file and line | Built | `scans.py:175`; `test_specificity_hides_private_values` | — |
| 10.2.2 Provider scan | Built | `scans.py:180-194`; `known_vendors.yaml`; `test_provider_names_only_inside_adapters` | — |
| 10.2.3 Pattern scan: URLs and dated comments | Built | `scans.py:197-210`; `test_urls_and_dated_comments_are_caught` | — |
| 10.2.3 Capitalized multi-word names not in concept list | Missing | — | Not implemented; no concept-word list. |
| 10.2.4 Config coverage: description and default | Built | `scans.py:260-275` | — |
| 10.2.4 Every key used in code exists; every schema key used; plugin config too | Missing | — | Unused keys pass: `workspace.owner_format`, `storage.export.every_minutes`, `storage.export.remote` are never read. |
| 10.2.5 Core imports nothing from plugins; plugins import only `plugin_api`; no network or process libraries | Built | `scans.py:213-257`; `tests/test_scans.py:89,102` | — |
| 10.2.5 No core code tests for a plugin's name | Missing | — | Not scanned. |
| 10.2.6 Suite runs against both fictional workspaces | Partial | `tests/conftest.py:59` (`demo` fixture) | Many suites (routes, setup, today, e2e) use `DEMO_B` only. |
| 10.2.6 Core alone, no bundled packs | Partial | self-check "core alone" (`engine/selfcheck/__init__.py:102`); `COCKPIT_TEST_CORE_ONLY` (`tests/conftest.py:22`) | Self-check only loads and round-trips fixtures; CI never runs the suite core-only. |
| 10.2.7 Registrations match manifest; declared hosts, secrets and levels enforced | Built | `engine/selfcheck/__init__.py:157`; `test_the_manifest_must_match_what_is_registered`; `tests/test_network.py:198` | — |
| 10.2.8 Prompt templates and playbooks scanned like code | Built | `.md` under `engine/` and `plugins/` is in `CODE_SUFFIXES` (`scans.py:25-26`) | — |
| 10.2.9 UI text only from wording sheet; scan JSX for literal text | Partial | `web/src/wording/wording.test.ts:20` checks only that used keys exist | No literal-text scan. |
| 10.2.9 UI rendered against both workspaces | Missing | e2e uses demo-b only (`tests/e2e_server.py`) | — |
| 10.2.9 axe in light and dark at phone, laptop, desktop | Partial | `web/e2e/shell.spec.ts:30-64` | Only the style guide and Today; other screens axe-checked in light at one size. |
| 10.2.9 Stylelint for colors, tokens, uppercase, disabled opacity | Built | `web/.stylelintrc.json`, `web/stylelint/rules.mjs`; runs in `npm run build` | — |
| 10.2.9 Screen use: 90% width at 1440/1920, header at most 56px | Built | `web/e2e/shell.spec.ts:137-167` | — |
| 10.2.9 No default screen shows an id, raw enum, command line or config path | Partial | `acceptance.spec.ts:134` (no "cockpit"), `:292` (no ids in copied message) | Not systematic across screens. |
| 10.2.10 Hosting platform names only in `deploy/` and docs | Missing | — | No scan. |
| 10.2.10 Every recipe's profile passes deploy checks | Missing | — | No recipes, no checks. |
| 10.2.10 UI and API at root and nested base path | Built | `web/playwright.config.ts` (root and `/admin`); `tests/test_api.py:38-70` | — |
| 10.3 Process | n/a | — | — |
| 10.4 Review checklist | n/a | — | — |

## Part 11: Deployment

| Section or requirement | State | Evidence | What is absent |
|---|---|---|---|
| 11.1 Local mode on 127.0.0.1 with install token | Built | `engine/config/schema.py:168`; `api/app.py:137-160`; `tests/test_api.py` | — |
| 11.1 Hosted mode | Missing (deferred) | `engine/cli.py:321` refuses hosted | Out of 1.0 by `roadmap-to-1.0.md` "Not in 1.0". |
| 11.1 Scheduler catches up after sleep | Partial | worker loops | No test. |
| 11.1 Backups expected, nag | Built | see 8.6 | — |
| 11.2 `base_path`, relative assets, runtime config, cookie path | Built | `api/app.py:174-196, 265-272`; e2e nested | — |
| 11.2 Hiding (`server.hide`, noindex) | Missing | no key | — |
| 11.3 Env vars | Built | `test_env_reaches_nested_keys_and_parses_values` | — |
| 11.3 `COCKPIT_PROFILE`, `init --profile hosted`, `cockpit deploy check` | Missing | `engine/cli.py:74-193` | — |
| 11.4 Install token | Built | `api/app.py` | — |
| 11.4 Password + 2FA, passkeys, recovery codes, OIDC, identity-aware proxy | Missing | — | — |
| 11.4 Sessions: HttpOnly, SameSite, base-path cookie | Built | `api/app.py:148-155` | Secure flag only when hosted. |
| 11.4 Idle and absolute timeouts, sign out everywhere, CSRF tokens, lockout, sign-in log, Security panel | Missing | — | — |
| 11.5 Deploy checks (all bullets) | Missing | — | — |
| 11.6 Local serve opens browser with token | Built | `engine/cli.py:353-356` | — |
| 11.6 Start-at-login files, container image, recipes 1 and 2 | Missing | — | — |
| 11.6 (not in design) install scripts | Built | `deploy/install.sh`, `deploy/install.ps1` | Untested. |

## Part 12: Security and privacy

| Section or requirement | State | Evidence | What is absent |
|---|---|---|---|
| 12.1 Two modes, one model | Partial | local only | — |
| 12.1 Secrets `env:` and `file:` | Built | `engine/secrets.py` | — |
| 12.1 Secrets `keychain:` | Missing | `engine/secrets.py:29` raises "not supported yet" | — |
| 12.1 Plugins get only declared secrets | Built | `engine/plugin_host.py:566`; `tests/test_network.py:172` | — |
| 12.1 Outbound gated by publisher approval | Partial | copy and Mark sent only | No publisher or channels. |
| 12.1 Data levels | Built | `engine/ai/router.py`, `engine/plugin_host.py:349, 1391` | — |
| 12.1 Audiences | Missing | — | — |
| 12.1 Audit: ledger | Built | `engine/storage/store.py` | — |
| 12.1 Audit: approvals and settings | Built | Looks good and Mark sent write the ledger; settings changes write `setting_change` (`engine/settings.py:311`) | — |
| 12.1 Audit: sign-ins and plugin enable/disable | Partial | — | No separate sign-in or plugin-toggle log. |
| 12.2 Provenance and paste-box split | Built | `engine/intake.py`; `engine/packet.py:116-124`; `test_untrusted_input_is_marked_and_the_note_is_not` | — |
| 12.2 Tiers | Built | — | — |
| 12.2 Untrusted stays untrusted | Partial | — | Lessons and glossary don't exist. |
| 12.2 Evidence must exist | Built | — | — |
| 12.2 Untrusted text doesn't become structure | Built | `test_hostile_input_cannot_add_people_or_recipients_on_its_own` | — |
| 12.2 Lookups only through configured sources | n/a | — | No lookup op. |
| 12.2 Nothing sensitive in packets | Built | — | — |
| 12.2 Outbound review shows provenance and full links | Missing | — | No outbound review. |
| 12.2 Hostile golden fixtures | Partial | `hostile-standing-rule.yaml`, `hostile-admin-mode.yaml` | No cases for send requests or new watched sources. |
| 12.3 Reach shown before enabling | Built | Add-ons "Reaches" (`web/src/wording/en.json:1098-1103`) | — |
| 12.3 Reach enforced | Built | `tests/test_network.py:198` | — |
| 12.3 "Not a sandbox" wording on the Admin tab | Missing | — | No Admin tab and no such wording. |
| 12.3 Bundled plugins can't import network libraries | Built | `scans.py:251-256` | — |
| 12.3 Out-of-process plugins | Missing (planned) | — | — |
| 12.4 Retention, export a person, forget a person, shorter hosted retention | Missing | — | — |
| 12.5 Dependencies pinned | Built | `uv.lock`, exact versions in `web/package.json` | — |
| 12.5 Dependencies scanned in CI | Missing | — | — |
| 12.5 Non-root, read-only container | Missing | — | — |
| 12.5 Uploads served only as downloads | Built | `api/routes.py:863-875` | Images are served inline. |
| 12.5 No raw HTML; links show real domain | Built | no `dangerouslySetInnerHTML`; `SafeText.test.tsx`; `engine/documents.py` | — |
| 12.5 Database never served | Built | UI route serves `dist/` only (`api/app.py:220-233`) | — |
| 12.5 Strict CSP | Built | `api/app.py:56` | — |

## Part 13: Build plan, milestone by milestone

| Milestone and item | State | Evidence or what is absent |
|---|---|---|
| M1 repository layout and tooling | Built | — |
| M1 database, versions, ledger, id sequences, lease | Built | `tests/test_store.py`, `tests/test_lease.py` |
| M1 readable export and round trip | Built | `tests/test_export.py` |
| M1 point-in-time restore | Missing | no `cockpit restore` |
| M1 config schemas, versions, layers | Built | `tests/test_config.py` |
| M1 profiles | Missing | no profile loading |
| M1 `config show` | Built | — |
| M1 `config explain` | Partial | `show` prints each value's layer; no `explain` |
| M1 scans and self-check | Partial | see 10.2 gaps |
| M1 both fixtures importable | Built | — |
| M1 local serve with token and base path | Built | — |
| M2 paste-in "your note" / "pasted content" | Built | — |
| M2 core playbook, first version | Built | `engine/playbook/guidance/notes.md` |
| M2 notes task via stub and openai-compatible | Built | — |
| M2 cleaning, one input per call | Built | — |
| M2 op lists, small schemas, JSON repair, evidence | Built | `test_parse_repairs_fences_prose_and_trailing_commas` |
| M2 provenance on every write | Built | — |
| M2 first evaluation set | Built | 14 cases in demo-b, `runs: 3`; none in demo-a |
| M2 applier, about ten ops | Partial | `source` is not an op |
| M2 names to ids, owners list, held actions | Built | — |
| M2 read-backs for PM-stated rules | Missing | — |
| M2 undo with op groups | Built | — |
| M2 glossary in packet, `glossary.add`, `lesson.add` | Missing | — |
| M2 open actions and questions in packet | Built | — |
| M2 waiting states | Built | — |
| M2 clipboard channel | Partial | Copy in the UI only; no channel |
| M2 off-computer backups with nag | Built | — |
| M2 minimal UI | Built | — |
| M2 Playwright acceptance with axe | Partial | step 6 absent (see Goal 2) |
| M2 quality signals | Built | `Signal` record |
| M3 scope resolver and sweep | Missing | — |
| M3 fact resolver | Missing | — |
| M3 search lookups | Missing | — |
| M3 audiences and restrictions | Missing | — |
| M3 remaining question and action ops | Missing | — |
| M3 action notices | Missing | `action-notice` exists only as an enum value |
| M3 Reassign | Missing | no route or op |
| M3 corrections checked against data | Missing | — |
| M4 manifests, registries, fake plugin | Built | — |
| M4 interfaces, events, cross-plugin requests, two fakes | Built | `tests/test_interfaces.py` |
| M4 built-ins behind interfaces | Partial | adapters and channels not plugin-registrable |
| M5 fake connectors, matcher registry, auto-closed list | Built | `tests/test_watch.py`; `/api/auto-closed` |
| M5 extra: folder, feed, ICS, IMAP connectors | Built | — |
| M6 core record types and `ext` | Built | — |
| M6 templates, render ordering, roll-ups | Missing | — |
| M6 drafts | Built | `text.draft` |
| M6 content-hash approval, scheduled drafts | Missing | — |
| M6 concurrency check | Built | — |
| M6 shared masters, reverting drafts after undone publishes | Missing | — |
| M6 fake page channel, Waiting to go out with diff renderer | Missing | — |
| M6 long text with versions and authorship | Built | — |
| M6 drafts with prose output | Built | — |
| M6 file channel | Missing | files and uploads exist |
| M6 stages | Built | — |
| M6 independent reviews | Built | — |
| M6 cost control | Built | — |
| M7 Today as home queue | Built | — |
| M7 first-run setup | Built | — |
| M7 declarative panel registry | Built | — |
| M7 branding | Built | — |
| M7 Settings panel | Built | — |
| M7 Admin tab with Quality | Missing | — |
| M7 side-by-side diffs | Partial | long-text compare only |
| M7 virtualized lists | Missing | — |
| M7 phone approval flows | Partial | one column; no phone review mode |
| M7 installable web app | Missing | no manifest in `web/index.html` |
| M8 publishing pack | Missing here | external |
| M9 workplace pack | Missing here | external |
| M10 escalation | Built | — |
| M10 three-layer cache, frozen batch prefixes | Partial | — |
| M10 reproducible runs, `cockpit replay` | Missing | — |
| M10 native adapters | Missing | — |
| M10 aggregator adapter | Partial | catalog entry via openai-compatible; no routing options |
| M10 `models()` from catalogs | Built | — |
| M10 Add account flow | Built | — |
| M10 command-line agent adapter | Built | — |
| M10 capability routing | Partial | context fit, routing rules, content levels |
| M10 budgets | Built | — |
| M10 data-level routing | Built | — |
| M10 packet budgets | Partial | `max_input_chars` |
| M10 golden fixtures with hostile inputs | Partial | — |
| M10 `evaluate` | Built | — |
| M10 test proving a second adapter needs no other change | Missing | — |
| M11 governor | Missing | — |
| M11 scheduler | Built | — |
| M11 offline behaviour and honest staleness | Partial | — |
| M11 automation problems | Partial | — |
| M11 reports | Built | — |
| M11 error classification from runner streams | Built | — |
| M11 handoffs | Missing | — |
| M11 rules review | Missing | — |
| M12 hosted deployment (all items) | Missing | deferred |
| M13 Today builder | Partial | queue and agenda |
| M13 meetings | Missing | — |
| M13 weekly check-up | Missing | — |
| M13 update writer | Missing | — |
| M13 issues, assumptions, risk fields and reviews | Missing | — |
| M13 escalation suggestions, communications cadence, meeting agendas | Missing | — |
| M13 Ask box | Built | — |
| M14 real wiki and tracker connectors as plugins | Missing here | core ships ICS, IMAP, feed, folder |
| Plugin API 1.0 | Not declared | `PLUGIN_API_VERSION = "0.3.55"` (`engine/plugin_api/__init__.py:48`) |

---

# GOAL 2: Roadmap, schedule and scope against the code

**Ticked but not fully built**
- **One-click add-on install.** The roadmap's M0 sub-bullet says add-ons install "with one click: moved forward, built before the freeze"; decisions 2026-10-11 says "The Add-ons screen gets an Install button."
  - The API exists: `POST /api/packs/{id}/install` and `/uninstall`, `engine/pack_install.py`, `tests/test_pack_install.py:93`.
  - The UI has no Install button. `web/src/components/Addons.tsx:303-317` only shows the publisher's install text to copy.
  - `addons.intro` (`web/src/wording/en.json:1062`) still says "The app never installs anything itself."
- **2a "Plugin API 0.3 … now 0.3.30".** The code is at 0.3.55; the text is stale.
- **3a "Long text formats … lints on drafts count for escalation".** Built in the dispatcher (`engine/dispatcher.py:392`), but no test escalates on a draft lint; only the fix round is tested (`tests/test_drafts.py::test_a_return_lint_on_a_draft_gets_a_fix_round`).
- **1 "Launch slice (done)".** Slice musts still partial or missing: "proposed lessons" (must in both horizons), the clipboard channel as a channel, and Playwright running the whole acceptance scenario (step 6 is missing).
- **3a "Plugin host … interfaces … one example plugin".** Built. Built-ins are not behind registries: adapters are a fixed dict (`engine/ai/adapters/__init__.py:19`) and there are no channels.

**Built but not ticked**
- **Watchers and lookups (2a).** The core sign-in (OAuth, plugin API 0.3.33+), sign-in sources (0.3.54), `tests/test_sign_in*.py` and the Sources screen are all built. Only the product plugins are missing, and they are private. "Lookups" (lookup op, facts) are not built.
- **M4.** Project language (`Project.language`, `engine/applier.py:240`), declared programs (`requires.tools`, `engine/tools.py`) and plugin data files (`engine/plugin_host.py:1644`) are built. What remains is the extension points and moving built-ins behind them.
- **M5.** Watchers and triage are built for folder, feed, ICS and IMAP (`engine/watch.py`, `engine/triage.py`, `/api/auto-closed`).
- **M7 (mostly).** Today as home queue, first-run setup and the Settings panel are built. The installable web app, virtualized lists and the Admin/Quality tab are not.
- **Provider-lessons open item, partly.**
  - Built: agent lock-down test (`engine/ai/adapters/cli_agent.py:189`), `sign_in_hint` (`engine/config/schema.py:334`), restart on request (`engine/cli.py` `restart_self`), `project.add`, person-owned fields (`PERSON_ONLY_OPS`, `person_only`).
  - Not built: per-model parameter capabilities, probation, a first-run notice for a new account, canonical form for channels, office-file extractors.
- **Milestone 10 overlap open item.** Escalation and budgets are built and native adapters are not. No decision is recorded and `scope.md` is unchanged.
- **Scope "should" items not reflected as done in the roadmap:**
  - Settings panel generated from schemas: built (`engine/settings.py`).
  - Ask the assistant: built.
  - Private evaluation cases: built (`cockpit evaluate --workspace`, `tests/test_cli.py:200`).

**Stale or inconsistent plan items**
- **Go/no-go and freeze.** Roadmap §2–3 and `schedule.md` still list the 2026-10-30 go/no-go and the freeze. `docs/decisions.md:1106` ("Real use starts with the publishing pack") says they "no longer apply."
- **Packs placement.**
  - Design Part 9 and 13.1 still say the packs are bundled (`plugins/workplace-pm/`).
  - Decisions 2026-10-10 say packs are add-ons in their own repositories.
  - `scope.md` still marks "Publishing playbook" a version 1 must.
- **Unused config keys.** `storage.export.every_minutes` and `storage.export.remote` are in the schema, but nothing schedules the export or pushes it to a remote. `workspace.owner_format` is likewise never used.

**`scope.md` musts not built: launch slice**
- Proposed lessons (row "Input cleaning…proposed lessons"): missing.
- Clipboard channel: partial (Copy and Mark sent only; no channel or publisher gate).
- UI foundations: complete as far as checked.

**`scope.md` musts not built: version 1**

| Item | State | What is missing |
|---|---|---|
| Today as home queue, first-run setup, settings form UX, side-by-side diffs, virtualized lists, phone approval flows, installable web app | Partial | Virtualized lists, installable web app, phone review mode; Waiting-to-go-out diffs. |
| Proposed lessons | Missing | — |
| Escalation, cache layers, reproducible runs, budget defaults | Partial | Reproducible runs and replay missing; cache layers partial. |
| Scope resolver and fact lookups | Missing | — |
| Dependencies and baselines | Missing | — |
| Publishing playbook | Missing here | Planned for the pack's own repository. |
| Automation `Issue` renamed `Problem` | Partial | No Issue name, but no Problem record either. |
| Native adapters; aggregator adapter with catalog and routing options | Missing / Partial | Add account and catalog models are built. |
| File channel | Missing | — |

The version 1 musts that are built: plugin host and API 0.x, plugins working together, long text, working copies and compare, two computers, prose drafts, stages, cost control, waiting states, core playbook.

**Milestone 2 acceptance scenario (`schedule.md:45-60`)**

The automated test is `web/e2e/acceptance.spec.ts`, `test.describe.serial("acceptance scenario")`. It runs on demo-b, at the root and under `/admin`, with a stub AI that returns each case's ideal answer (`tests/e2e_server.py`). It does not cover the scenario end to end:

| Step | Test | Coverage | What is not checked |
|---|---|---|---|
| 1 | "1. meeting notes become actions with owners…" (`:223`) | One action per task, owners including the shared action, and "who is this?" are checked. | That each action is linked to the title/project. |
| 2 | "2. a vendor's date becomes a fact…" (`:250`) | One fact and no question are checked. | That the fact holds the new date and cites its source. |
| 3 | "3. an instruction inside pasted content…" (`:257`) | Note only, no person added. | That `rules.yaml` and settings are unchanged (no op could add a rule anyway). |
| 4 | "4. Follow-ups…" (`:283`) | One owner's section: copy, no ids, Mark sent, Undo. | "Each contributor has one section"; that the message includes the person's questions as well as actions. |
| 5 | "5. undoing the vendor's date removes the fact" (`:310`) | The "Undone" pill only. | That the fact is gone, and that the ledger shows both the change and the undo. No Python test asserts an undo entry in the ledger. |
| 6 | none | — | No test at all. Export → import into a fresh database → identical after the scenario is not tested; `tests/test_export.py::test_fixture_round_trips` covers pristine fixtures only. |
| 7 | "signing in, the backup nag…" (`:115`) and "7. after a backup succeeds…" (`:318`) | The header chip says "Backup needed"; after "Back up now" the status popover shows the age. | That Today says so; that the header chip itself shows the age. |

---

# GOAL 3: End-to-end paths with no automated test from start to finish

**1. Fresh `cockpit init` with no template → serve → setup guide → add a real AI account → test it → hand in a note → result on Today**
- Tested in isolation:
  - `tests/test_cli.py::test_init_without_a_template_writes_commented_defaults`, `test_a_fresh_workspace_knows_who_you_are`
  - `tests/test_setup.py::test_the_person_the_app_is_for_is_named_on_their_record` (fresh workspace)
  - Setup steps: `test_steps_say_what_is_done_and_can_be_skipped`
  - Account add with a mocked service: `test_a_service_is_picked_by_name…`, `test_a_real_account_takes_over_the_tiers_still_on_the_stand_in`
  - Account test: `test_an_account_says_whether_its_key_is_there…`
  - Hand-in on demo-b with stub or stand-in: `tests/test_routes.py`, `tests/test_stand_in.py`
  - Today queue: `tests/test_today_queue.py`
  - Web units: `WelcomeAi.test.tsx`, `Setup.test.tsx`
  - The e2e only opens the AI step's fields (`acceptance.spec.ts:158-185`).
- Untested joins:
  - Browser on a template-less workspace (the e2e always starts from demo-b).
  - Submitting the Add-account form in the browser.
  - A newly added openai-compatible account (mock transport) then used by the worker to process a hand-in.
  - The stand-in → real-account switch followed by work.
  - The Today line produced from that run.

**2. Installer → first run**
- `deploy/install.sh` and `install.ps1` are not tested.
- `release.yml` smoke-starts `cockpit demo` from the wheel and greps "Open http"; nothing exercises the setup guide afterwards.

**3. Signing in to a mail add-on → mail read → handed to the assistant → shown for review**
- Tested in isolation:
  - OAuth with PKCE, callback, token keep and renew: `tests/test_sign_in.py::test_the_person_signs_in_and_the_connector_gets_a_token`
  - Sign-in starts declared sources: `tests/test_sign_in_sources.py`, but its connector returns `Poll([], {})`
  - Sign-ins UI: `SignIns.test.tsx` (mocked)
  - Watch hand-in from a fake connector: `tests/test_watch.py::test_new_changed_and_gone_items_are_handed_in_as_outside_content`
  - Dispatch of pasted text: `tests/test_pipeline.py`
- Untested joins:
  - A token-using connector returning mail items → `watch.refresh` → request with an untrusted source → dispatcher → changeset → What changed/Today.
  - The worker loop doing this on its own.
  - No mail add-on exists in the repo.

**4. Core IMAP/ICS/feed/folder source added on the Sources screen → read by the worker → assistant → review, or agenda on Today**
- Tested in isolation:
  - Form a11y in e2e (`acceptance.spec.ts:340`)
  - Source added via API: `test_a_source_is_added_changed_and_removed_from_the_screens_without_a_restart`
  - IMAP with FakeImap and ICS: `tests/test_calendar_mail.py`
  - Worker runs due watches (fake connector, baseline only): `tests/test_watch.py:224`
  - Agenda and arrived routes from records: `tests/test_today_dashboard.py:123`
- Untested joins:
  - A watched item processed by the dispatcher into a reviewable changeset.
  - ICS read → snapshot → Today agenda in one flow.
  - Any of it in a browser.

**5. Installing an add-on from the Add-ons screen**
- Not possible from the UI: there is no Install button.
- Tested in isolation:
  - Download, checksum and token: `tests/test_pack_install.py`
  - API install with a mocked feed and download: `test_the_install_route_uses_the_catalog_entry`
  - Turn on/off with Undo: `tests/test_setup.py::test_an_installed_add_on_is_turned_on_and_off_with_undo`; `Addons.test.tsx`
  - Restart prompt: `web/src/lib/restart.test.tsx`
- Untested joins:
  - UI → install → Turn on → restart → plugin loaded and its panels/Today lines appear.
  - `restart_self` really re-executing.

**6. Backup → restore**
- Backups are tested (`tests/test_followups_backup_eval.py`, e2e "Back up now").
- There is no restore command and no test of recovering a workspace from a backup copy.

**7. Two computers through a synced folder**
- Tested in isolation: `tests/test_handover.py`, `tests/test_sync.py`, `tests/test_outside.py`.
- Untested joins:
  - `cockpit init --sync` (no test uses it).
  - Two app instances handing over the lease end to end, then serving.

**8. Settings change that needs a restart → "Restart now" → app back with the setting**
- Tested in isolation: `tests/test_setup.py:295-414`, `web/src/lib/restart.test.tsx`.
- Untested: a live process restart (`os.execv`) and the browser reconnecting.

**9. Follow-up sent → reply arrives → question closed → Waiting on them clears**
- Tested in isolation: e2e step 4 (to Mark sent); `tests/test_routes.py::test_a_reply_is_handed_in_against_its_question_and_closes_it`.
- Untested: the reply hand-in from the "Waiting on them" UI, and that row leaving.

**10. Stage move → task waits for go → run → draft → text review → accept**
- Tested in isolation:
  - e2e stage go (`acceptance.spec.ts:603`), stopping at Go
  - Drafts and long text: `tests/test_drafts.py`, `tests/test_long_text.py`
  - `TextReview.test.tsx` (mocked)
- Untested: draft review and per-passage accept in the browser, and the `text.accepted` event reaching a plugin in the same flow.

**11. Working copy handed out → edited in another program → taken back → reviewed**
- Tested in Python units (`tests/test_working_copies.py`, `tests/test_outside.py:298`) and `WorkingCopies.test.tsx`.
- Untested: no browser path.

**12. Template applied from the setup guide → kit item types → items through Stages and Today**
- Tested in isolation: `tests/test_setup.py::test_a_template_is_listed_and_applied`, `tests/test_kit.py`.
- Untested: the e2e never applies a template; the join to Stages and Today is untested.

**13. Cost-held run → Go from Today → run completes**
- Tested in isolation: `tests/test_routes.py:496-508`, `tests/test_pipeline.py:455`.
- Untested: no web or e2e test of the cost Go (e2e covers only the stage Go).

**14. Ask the assistant → suggested setting → Apply → takes effect**
- Tested in isolation: `tests/test_ask.py`, `Ask.test.tsx`.
- Untested: the e2e checks a11y only; the Apply-to-effect join in the UI is untested.

**15. `cockpit ai test` → `cockpit evaluate` → choose a model → tiers updated**
- Tested in isolation: CLI tests with stub or missing key (`tests/test_cli.py:64, 71, 176, 200`).
- Untested: choosing from the report and changing the configuration.

**16. Core alone (no packs) through the UI**
- No e2e or web test runs with plugins disabled, and CI never sets `COCKPIT_TEST_CORE_ONLY`.

**17. demo-a (the workplace fixture) through the UI**
- Untested: the e2e and most route tests use demo-b only.

**18. Product update (`install.sh` re-run or release upgrade) keeping the workspace**
- Untested.
