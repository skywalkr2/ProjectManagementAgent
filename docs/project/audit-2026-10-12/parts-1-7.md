# PM Cockpit audit: design Parts 1–7 against the code (read-only, 2026-10-12)

I audited design Parts 1–7 against `/home/user/ProjectManagementAgent` (`engine/`, `api/`, `web/src/`, `plugins/`, `tests/`, `web/e2e/`) and changed nothing. "Built" means the code and a test both exist. "Partial" means code without a test, or only part of the requirement. "Missing" means nothing implements it.

What exists: the plugin system, long text, synced folder, stages, AI accounts, follow-ups, setup and the Add-ons screen are largely in place and tested.

What is absent: every v1 concept tied to channels, publishing, scope, facts, routing, glossary, lessons, RAID and governor. The Today home screen contradicts the current design.

Paths below are relative to the repository root. Test names are written `file::test_name` and drop the `test_` prefix: tests in `tests/`, Vitest in `web/src/**`, Playwright in `web/e2e/`.

---

## PART 1 – Product

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 1.1 | AI drafts, human approves everything outward | Partial | Copy plus Mark sent only (`engine/followups.py:94-150`) | No outbound path (no channel or publisher) exists to gate |
| 1.2 | Assistant display name is configurable | Built | `engine/config/schema.py:140`; Ask.test "dialog is named for the assistant" | |
| 1.2 | Model's name never shown | Built | `engine/applier.py:283-287`; test_pipeline::model_names_never_reach_text_people_see | |
| 1.2 | Contacts get paste-ready messages, or channel sends after approval | Partial | test_followups_backup_eval::a_message_has_greeting_questions_actions_and_closing | Channel send missing |
| 1.3.1 | Watch sources on a schedule, plus hand-ins (notes, emails, screenshots, files) | Partial | `engine/watch.py`; test_watch; HandIn.test | Screenshots and files are never read (no extractors, no vision) |
| 1.3.2 | Rules triage first; auto-closed items findable with reason; can be pulled back | Built | `engine/triage.py`; test_watch::triage_rules_close_changes_with_a_reason, a_closed_change_can_be_taken_a_closer_look_at | |
| 1.3.3 | Inputs batched into packets for dispatch | Partial | `engine/packet.py`, `engine/dispatcher.py` | One request at a time; no batches |
| 1.3.4 | AI writes a changeset of typed ops only | Built | `engine/ops.py`; test_pipeline::parse_repairs_fences_prose_and_trailing_commas | |
| 1.3.5 | Invariants then lints, names to ids, one transaction, ledger, undo | Built | `engine/applier.py:109,497,1132`; test_pipeline::undo_skips_a_group_someone_changed_since | |
| 1.3.5 | Behaviour-changing ops never auto-apply from an input | Built | `engine/applier.py:289-292`; test_plugins::system_tier_is_held_until_confirmation | |
| 1.3.5 | Invalid changeset goes back to the AI once | Built | `dispatch.fix_rounds`; test_pipeline::the_fix_round_can_correct_the_answer | |
| 1.3.6 | Review with Looks good / Send back / Undo | Built | `api/routes.py:1085-1114`; test_routes::looks_good_then_reopen, send_back_queues_a_new_request | |
| 1.3.7 | Send out: drafts per channel, diff or preview, approve exact content | Missing | `web/src/App.tsx:154-162` (empty placeholder) | No Draft record, channel, renderer or publisher |
| 1.3.8 | Follow-ups by person, copy, mark sent, aging, pasted reply goes to the AI | Built | test_routes::a_reply_is_handed_in_against_its_question_and_closes_it; FollowUps.test | "or sent as one message" via a channel is missing |
| 1.4 | Mailboxes, calendars and feeds are plugins | Partial | `engine/connectors/mailbox.py`, `calendar.py`, `feed.py` are in core | Contradiction (see list 1) |
| 1.4 | Fake connector | Built | `engine/connectors/__init__.py:242-266`; test_today_dashboard (connector "fake") | Reads items from settings, not fixture files |
| 1.4 | Fake channel | Missing | | |
| 1.4 | Local-folder connector | Built | `engine/connectors/__init__.py:202-241`; test_watch::the_first_read_only_notes_what_is_there | |
| 1.4 | Paste-in and upload | Partial | `/handin`, `/files`; test_files::upload_and_download_through_the_api | Uploads are never read by the assistant |
| 1.4 | Clipboard channel | Partial | Copy in FollowUps, Ask and Feedback | Not a channel |
| 1.4 | Stub AI adapter | Built | `engine/ai/adapters/stub.py`; used across tests | |
| 1.5 | Playbooks the PM can switch off entry by entry | Partial | `engine/playbook/guidance/notes.md` only | No entry ids, no `playbooks.yaml` |
| 1.5 | Ask the assistant anything | Built | `api/ask_routes.py`; test_ask | |
| 1.6 | No autonomous sending | Built (nothing sends) | | |
| 1.6 | Never changes its own code; requests become reports | Partial | `report.draft` (test_ask::something_the_app_cant_do_becomes_a_report_to_send) | Pack install writes code into the app's environment (list 1) |
| 1.6 | Storage behind a repository layer | Partial | `engine/storage/store.py` | No backend interface |
| 1.6 | One writer per workspace | Built | `engine/storage/lease.py`; test_lease | |

## PART 2 – Architecture

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 2.1 | Core knows no org, domain or service | Partial | test_scans::the_repository_passes | Mail, calendar and feed connectors sit in core |
| 2.1 | Extension only via `engine.plugin_api`; core never imports plugins | Built | test_scans::core_must_not_import_plugins_and_plugins_only_the_api; test_plugins::boundary_rejects_import_of_engine_internals | |
| 2.1 | Workspace: DB, config and readable export in its own git repo | Partial | `engine/workspace.py:111-125`; test_cli::init_from_a_fixture_loads_records_and_commits | Export to `data/` only via `cockpit export` |
| 2.1 | AI adapters are a kind of plugin | Missing | Hard-coded `ADAPTERS` in `engine/ai/adapters/__init__.py:19-23` | No registrar point |
| 2.2 | Repo layout: `engine/plugin_api`, `ai/adapters`, `selfcheck`, `api`, `web` | Built | | |
| 2.2 | `plugins/fake`, `publishing/`, `workplace-pm/` | Missing | Only `plugins/kit`, `plugins/example` | Packs moved to own repos by decision |
| 2.2 | `workspaces/demo-a`, `demo-b` | Built | test_config::fixture_workspaces_load; selfcheck | |
| 2.2 | `deploy/container` and `deploy/<target>` | Missing | `deploy/` holds only `install.sh`, `install.ps1`, a catalog example | |
| 2.2 | Workspace folders: config, data, sources, prompts, plugins, outbox, evals, `docs/decisions.md` | Partial | `engine/workspace.py:101-110` | No `outbox/`; no workspace `docs/decisions.md` |
| 2.2 | Path from `--workspace` or `COCKPIT_WORKSPACE`; init on first run | Partial | `engine/workspace.py:20,68`; test_cli::missing_workspace_has_a_clear_message | Needs explicit `cockpit init`, not first run |
| 2.2 | `.gitignore` admits only the demos under `workspaces/` | Built | `.gitignore` | |
| 2.3 | Config file per concern (routing, facts, scope, triage, schedule, render, status, calendar, auth, code_owners, playbooks, raid, audiences) | Partial | Only 11 files exist (`engine/config/schema.py:969-981`) | All listed files missing |
| 2.4 | Python, uv, FastAPI, Pydantic v2, pytest, ruff; JSON Schema from models | Built | `engine/ops.py:528` `schema_for` | |
| 2.4 | React+TS, Vite, Vitest, Playwright; TanStack Query + SSE; generated client; React Aria; CSS variables | Built | `web/package.json`; `web/src/lib/live.ts` (live.test.tsx) | |
| 2.4 | UI gets panel definitions from the API | Built | `/panels`; Panel.test | |
| 2.4 | Plugins found by entry point and by folders | Built | test_plugins::private_and_installed_discovery | |
| 2.4 | Postgres later; object storage for sources | Missing | | `sources_store` absent |
| 2.4 | One container image; any base path without rebuild | Partial | test_api::nothing_is_served_outside_the_base_path; Playwright "nested" project | No container; hosted mode refused (`engine/cli.py:321-323`) |

## PART 3 – Plugins

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 3.1 | Bundled plugins tested on both demos and with core alone | Built | selfcheck "workspace …" and "core alone …" | |
| 3.1 | Installed and private plugins | Built | test_plugin_api_033::an_editable_install_is_found_in_its_checkout | |
| 3.2 | Manifest read and checked before import | Built | test_plugins::version_checked_before_import_and_disabled_plugins_never_import, invalid_manifests_are_refused | |
| 3.2 | `depends_on` and interface keys | Built | test_plugins::dependency_versions_and_cycles | |
| 3.2 | `provides.playbook` | Missing | `engine/plugin_manifest.py:33` ("not yet available") | |
| 3.2 | Secrets from env or keychain | Partial | `engine/secrets.py:29-31` | Keychain refused |
| 3.2 | Ids namespaced `<plugin>/<name>` | Built | test_plugins::runtime_namespace_violation_refused | |
| 3.3 | Connector `poll` with typed errors | Built | test_watch::a_plugin_adds_a_connector; test_network::failures_become_connector_error_kinds | |
| 3.3 | Connector `fetch`, `search`, `capabilities` | Missing | `registrar.connector` takes `poll` only | |
| 3.3 | Channel extension point | Missing | | |
| 3.3 | Record type | Partial | test_plugin_api_02::unique_fields_and_references_are_enforced | No migrations |
| 3.3 | Op type (tier, validate, writes, apply, describe) | Built | test_plugins::plugin_op_applies_emits_and_undoes, write_scope_is_enforced_and_validator_crash_fails_closed | Outbound tier refused (test_plugin_safety::outbound_ops_wait_for_the_publisher) |
| 3.3 | Op validator | Built | test_plugin_api_02::a_validator_sees_what_earlier_ops_in_the_same_changeset_created | |
| 3.3 | Text format | Built | test_long_text::a_plugins_text_format_is_checked | |
| 3.3 | Lint | Built | test_plugin_lints | |
| 3.3 | Working-copy format | Built | test_working_copies | |
| 3.3 | Triage matcher | Built | test_watch::a_plugin_adds_a_triage_matcher_and_a_crash_counts_as_no_match | |
| 3.3 | AI adapter point (`models`, `run`, `classify_error`, `sign_in_hint`, `health`, `lockdown_test`) | Missing as a point | Core adapters only | `health()` absent everywhere |
| 3.3 | Text extractor | Missing | | No office/PDF extraction at all |
| 3.3 | AI task kind | Built | test_plugin_tasks | |
| 3.3 | Renderer | Missing | | |
| 3.3 | Lookup | Missing | | |
| 3.3 | Stages | Built | test_stages | |
| 3.3 | Panel (declarative, under Work or Records) | Built | test_today_panels_jobs::a_panel_is_described_as_data_and_lists_its_rows; Sidebar.test | |
| 3.3 | Today contributor | Built | test_today_panels_jobs::today_lines_come_from_the_plugin_with_their_one_action | |
| 3.3 | Job | Built | test_today_panels_jobs::a_job_runs_when_due_and_is_recorded | No "needs network" flag |
| 3.3 | Interface | Built | test_interfaces (14 tests) | |
| 3.3 | Event handler | Built | test_plugins::all_named_events_and_queue_command | |
| 3.3 | API route (planned) | Missing | | As designed |
| 3.3 | Auth provider (core only) | Missing | Install token only | |
| 3.3 | Storage backend | Partial | Single Store | |
| 3.3 | Playbook point | Missing | | |
| 3.3 | Plugin `check()` | Missing | | No registrar method; selfcheck never calls plugins |
| 3.4 | Event bus; subscriptions via manifest | Built | test_event_specs::published_payloads_match_their_specs | |
| 3.4 | Events `record.changed`, `request.queued`, `changeset.applied`, `changeset.undone`, `question.answered`, `stage.moved`, `text.accepted` | Built | test_event_specs | |
| 3.4 | Events `source.saved`, `change.filed`, `change.closed`, `draft.created`, `draft.approved`, `draft.sent`, `question.asked`, `action.added`, `action.closed`, `problem.opened`, `job.finished` | Missing | | |
| 3.4 | Interface events published when the provider's op applies | Built | test_interfaces::a_provider_can_raise_an_event_from_a_handler | |
| 3.4 | Handlers read, queue, file questions; never write | Partial | test_plugins::handler_cannot_smuggle_record_writes_as_commands | Cannot "open automation problems" |
| 3.5 | Writes only through the applier | Built | test_plugins::write_scope_is_enforced_and_validator_crash_fails_closed | |
| 3.5 | Sending only through the publisher | Missing | | No publisher |
| 3.5 | Reach declared, shown before enabling, enforced | Built | test_network::a_plugin_never_reaches_a_host_it_didnt_declare; Addons.test (Adds/Reaches/Keeps) | |
| 3.5 | Programs via declared tools; missing tool handling | Built | test_tools::a_missing_required_tool_keeps_the_plugin_off, the_program_is_not_given_a_shell | |
| 3.5 | Plugin config like core config | Built | test_setup::an_add_ons_settings_are_a_form_group_saved_to_its_own_file | |
| 3.5 | Failures contained; `failures_before_off` | Built | test_today_panels_jobs::a_failing_job_is_recorded_and_turns_the_plugin_off_when_it_keeps_failing | Failure becomes plugin status, not an automation Problem |
| 3.5 | Bundled plugins ship demo config for both demos | Built | `workspaces/demo-*/config/plugins/` | |
| 3.6 | Enable via `plugins.enabled`; checks before register | Built | test_plugins | |
| 3.6 | Upgrade migrations, export first, DB backup, restore on failure | Missing | | |
| 3.6 | Disable keeps records; re-enable resumes | Built | test_plugins::disabled_records_survive_and_reenable | |
| 3.7 | Worked examples | N/A | | |
| 3.8 | Core playbook | Partial | `engine/playbook/guidance/notes.md` | Only `guidance/`; no `rules.yaml`, `checklists/`, `glossary.yaml`, `lints.yaml`, `evals/` |
| 3.8 | Layers, entry ids, `playbooks.yaml` switch/replace, read-back overlap | Missing | | |
| 3.8 | Playbook in stable packet part | Partial | `engine/packet.py:93` "# Practice" | No glossary or rules follow it |
| 3.8 | Rules review proposes upstream patches | Missing | | |
| 3.9 | Shared core records | Partial | person, team, project, source, action, question, fact exist | No dependency or budget records; facts minimal |
| 3.9 | Interfaces, events, requests for another plugin's work | Built | test_plugin_api_0323::a_request_can_name_an_interface_item_and_the_provider_says_which_record; WhatChanged.test "work a plugin did in answer to a change says which change it followed" | |
| 3.9 | Optional means optional | Built | test_interfaces::an_optional_interface_with_no_provider_reads_empty | |
| 3.9 | CI runs every pack pair | Partial | Selfcheck covers alone and core-alone only | |
| 3.9 | Missing required interface fails self-check | Partial | test_interfaces::a_required_interface_with_no_provider_keeps_the_user_off | Plugin kept off, not a self-check failure |
| 3.10 | Kit built only on the plugin API | Built | `plugins/kit/__init__.py`; test_kit | |
| 3.10 | Item types, 8 field kinds, title, project | Built | test_kit::a_template_sets_up_item_types | |
| 3.10 | Stages with filled / checklist / date-passed checks; checklists | Built | test_kit::stage_checks_come_from_the_type, items_are_added_changed_and_ticked | |
| 3.10 | Assistant fills chosen fields with evidence | Built | test_kit::the_assistant_may_fill_only_the_fields_allowed_with_evidence | |
| 3.10 | Today lines; list columns and board | Built | test_kit::today_shows_what_is_due_and_what_is_missing | |
| 3.10 | Types defined on settings screens | Missing | `Config.types` is `list[TypeDef]`, which the settings form calls "other" and won't edit (`engine/settings.py:212-229`) | |
| 3.10 | Settings validated with reasons | Built | test_kit::bad_settings_keep_the_kit_off_with_the_reason | |
| 3.10 | Adding a field is immediate | Contradicted | Plugin settings are not live keys (`engine/worker.py:30-39`); restart needed | |
| 3.10 | Removed field hidden, values kept | Partial | `hidden` flag (`plugins/kit/__init__.py:50`) | Untested |
| 3.10 | Renaming a field renames it in every record | Missing | | |
| 3.10 | A type with items can't be deleted, only hidden | Partial | `hidden` exists | No deletion guard |
| 3.10 | Templates in `templates/`, applied additively | Built | test_kit::applying_a_second_template_adds_types_and_keeps_the_first; test_setup::a_template_is_listed_and_applied | |
| 3.10 | Save as template | Partial | `cockpit template save` (test_kit::a_workspace_saves_its_settings_as_a_template) | No screen or route |
| 3.11 | Add-ons screen with Installed and Available tabs | Built | Addons.test | |
| 3.11 | Listing: maker, compatibility, price | Built | test_packs | |
| 3.11 | Adds/reaches/keeps written from the manifest | Built | test_packs::the_summary_comes_from_the_manifest_not_the_description | |
| 3.11 | Same summary approved on Turn on; re-approval on update | Partial | Turn on acts at once with Undo | No approval step |
| 3.11 | AI cost priced on the person's accounts | Built | test_packs::ai_jobs_are_priced_on_the_workspaces_accounts | |
| 3.11 | Try it in the demo / Get it | Built | Addons.test "How to get it shows the install text …"; test_shipped::the_demo_tries_a_plugin_from_its_folder_or_by_name | |
| 3.11 | App never installs code into itself | Contradicted | `api/pack_routes.py:114-155`, `engine/pack_install.py` | List 1 |
| 3.11 | Feeds read on open or refresh, cached, untrusted | Built | test_packs::feeds_are_kept_and_read_again_only_when_old_or_asked; Addons.test "text from a catalog is shown as text" | |

## PART 4 – Configuration

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 4 | YAML validated; every key defaulted; comment block per file | Built | test_cli::init_without_a_template_writes_commented_defaults; test_config::default_files_are_valid_yaml_and_load_as_defaults | |
| 4.0 | Anything a person might want different is a setting | Partial | | Hard-coded: near-duplicate threshold 0.8 (`engine/applier.py:268`), BASIC key list (`engine/settings.py:32-49`), security headers (`api/app.py:57-64`) |
| 4.0 | Layers default < file < env < flag; `COCKPIT__FILE__KEY` | Built | test_config::layers_in_order_file_env_flag, env_reaches_nested_keys_and_parses_values | |
| 4.0 | `cockpit config show` with source layer | Built | test_cli::config_show_explains_each_value | |
| 4.0 | Profiles (`config/profiles`, `COCKPIT_PROFILE`) | Missing | | |
| 4.0 | Version per file; newer file refused | Built | test_config::newer_file_version_is_refused | |
| 4.0 | Migrations: commit before/after, list on Admin | Partial | `engine/migrate.py` (test_config::the_pms_name_moves_from_the_settings_to_their_person_record) | No framework, commits or Admin list |
| 4.0 | basic/advanced marked in the schema; pack presets | Partial | Hard-coded BASIC set | No presets |
| 4.0 | `config explain` / "what reads this" | Missing | | |
| 4.0 | Settings panel saves, validates, commits, records in ledger | Partial | `engine/settings.py:235-316`; test_setup::a_save_writes_the_file_records_the_change_and_never_races | Recorded as a `setting_change` record, not a `config.set` op; dict and list-of-object keys not editable |
| 4.0 | Env/flag-set keys locked with source | Built | test_setup::a_bad_value_or_a_locked_key_writes_nothing | |
| 4.0 | Secret references `env:` / `keychain:` / `file:` | Partial | | Keychain unsupported |
| 4.0 | Live keys apply on save; others ask for restart | Built | test_setup::live_settings_are_taken_in_at_once_and_a_mixed_change_waits | |
| 4.1 | `assistant_name` | Built | | |
| 4.1 | `assistant_description` | Missing | | |
| 4.1 | `user` (name and aliases on the person record; timezone) | Built | test_config::the_pms_name_moves_from_the_settings_to_their_person_record | |
| 4.1 | `plugins.enabled` with version ranges; extra search paths | Partial | | No ranges, no paths |
| 4.1 | Named connector instances | Partial | Watch sources name a type plus settings | |
| 4.1 | `channels` | Missing | | |
| 4.1 | `our_accounts` | Partial | test_watch::changes_by_our_own_accounts_and_scratch_files_are_closed | Not given to packets |
| 4.1 | `owner_format` | Partial | Defined at `engine/config/schema.py:142` | Never read anywhere (list 1) |
| 4.1 | `audiences`, `restrictions` | Missing | | |
| 4.2 | People are records, edited in app, exported | Built | test_routes::people_can_be_added_renamed_and_removed_when_unused | |
| 4.2 | People fields `prefers`, `cadence`, `influence`, `interest`, `non_working_calendar`, `verified`, `area` | Missing | | |
| 4.2 | `track_only` | Partial | Field only | Not used to suppress notices |
| 4.3 | `routing.yaml` and `escalation` | Missing | | Unknown names do become "who is this?" decisions |
| 4.4 | `scope.yaml` | Missing | | |
| 4.5 | Watch entries name a connector and its settings | Built | test_watch; Sources.test | |
| 4.5 | Triage rules (name, kind, params, why) | Built | `TriageRule` in `watch.yaml` (`schema.py:937`) | |
| 4.5 | Core matchers listed in 4.5 | Partial | Core has cosmetic, by-us, terms-absent, name-matches (`engine/triage.py:63-66`) | The 4.5 list conflicts with 6.5's |
| 4.5 | `schedule.yaml` (cron, working hours, catch-up) | Missing | | Only `every_minutes` |
| 4.6 | Blocked phrases, run-on separators, never-shown words | Built | test_pipeline::blocked_wording_warns_on_internal_items_and_holds_what_goes_to_others | |
| 4.6 | Locale spelling list, `languages:` map, per-project lints | Missing | | |
| 4.6 | Date formats | Partial | `messages.date_format` only | |
| 4.7 | `render.yaml` and templates | Missing | | |
| 4.8 | Providers (adapter, auth ref, models, allowed_data, base_url, agent) | Built | test_ai; test_cli_agent | |
| 4.8 | Native vendor adapters; aggregator with routing options | Missing | | |
| 4.8 | Tiers with use / fallback / escalate_to | Built | test_ai::a_rate_limit_falls_through_to_the_next_account_and_both_runs_are_kept; test_pipeline::the_stronger_tier_can_fix_what_the_routine_tier_got_wrong | |
| 4.8 | Tasks per kind | Built | test_plugin_tasks::the_workspace_overrides_a_task_kinds_defaults_field_by_field | Default table lists only `notes` |
| 4.8 | Roles (check, same_account) | Built | test_second_opinions | |
| 4.8 | Budgets (run, day, month, warn_at, confirm, per_task) | Built | test_pipeline::a_run_estimated_above_the_amount_to_confirm_waits_for_the_go, a_kind_of_work_stops_at_its_own_daily_budget | `confirm_above_usd` default 0.10 vs design 0.25 |
| 4.8 | `budgets.per_record` | Partial | `project.budget_usd` (test_projects_series::a_budget_covers_the_project_and_everything_inside_it) | No per-type defaults |
| 4.8 | `prices` overrides | Built | test_ai::cached_input_is_priced_at_the_cached_rate | |
| 4.8 | `evaluation.required_before_switch` | Missing | | |
| 4.8 | `probation` | Missing | | |
| 4.9 | Batch size, immediate kinds, timeouts, attempts | Missing | | |
| 4.9 | Cleaning patterns | Built | test_pipeline::quoted_history_already_on_file_is_removed_before_the_ai_sees_it | |
| 4.9 | `max_input` per task kind | Partial | One global `max_input_chars` | |
| 4.9 | `open_items.compact_share`; `governor.yaml` | Missing | | |
| 4.9 | `reports` destination | Partial | `ui.feedback_to` | |
| 4.10 | `rules.yaml` schema | Built | test_stages::rule_yaml_date_and_binding_validate_at_load | |
| 4.10 | Rules reach the AI tasks they apply to | Missing | Used only as stage gates (`engine/stages.py:17`) | |
| 4.10 | `rule.add` as a system op | Missing | | |
| 4.11 | `status.yaml` | Missing | Value lists instead (no colours or open/done) | |
| 4.11 | `calendar.yaml` | Missing | | |
| 4.11 | `ui.yaml` tab order, hidden panels, quick links | Missing | | |
| 4.11 | `ui.yaml` brand, logo, theme | Built | test_brand; theme.test | |
| 4.12 | Plugin settings validated against manifest schema | Built | test_plugins::bad_config_and_load_crash_do_not_stop_core | |
| 4.12 | `plugin-data` overlay | Built | test_plugin_data::the_most_specific_layer_wins | |
| 4.12 | Overlay checked by plugin `check()` | Missing | | |
| 4.13 | `mode` | Partial | | Hosted refused outright |
| 4.13 | host/port, `public_url`, `base_path` | Built | test_api | |
| 4.13 | `hide`, `trusted_proxies`, `allowed_hosts`, `cors`, `role`, `robots` | Missing | | |
| 4.13 | Configurable `headers` | Partial | Fixed in code (`api/app.py:57-64`) | |
| 4.14 | `auth.yaml` | Missing | Install token only (test_api::link_token_sets_a_cookie_scoped_to_the_base_path_and_strips_itself) | |
| 4.15 | `backend` | Built | | |
| 4.15 | `path`, `sources_store` | Missing | | |
| 4.15 | `export.every_minutes`, `export.remote` | Missing in effect | Defined but never read | Export only runs via CLI |
| 4.15 | `sync.folder`, `watch_outside_edits`, `lease_stale_after_minutes` | Built | test_handover; test_outside | |
| 4.15 | `sync.layout`, sources encrypt/exclude, `outputs_folder` | Missing | | |
| 4.15 | Workspace inside the synced folder refused | Built | test_sync::the_app_refuses_to_start_with_the_workspace_inside_the_folder | |
| 4.15 | Backups off-device, scheduled | Built | test_followups_backup_eval::scheduled_backups_run_when_due_and_retry_after_a_wait, a_target_inside_the_workspace_is_refused | |
| 4.15 | Backup `encrypt` | Missing | | |
| 4.15 | Backup nag and age shown | Built | test_followups_backup_eval::no_target_means_a_nag; Playwright step 7 | |
| 4.15 | `retention`, `forget_person` | Missing | | |
| 4.16 | `facts.yaml` | Missing | | |
| 4.17 | `checks.yaml` severities | Built | test_plugin_lints::the_workspace_can_soften_a_lint_to_a_warning | |
| 4.17 | Default lints | Partial | | `locale-spelling`, `fact-terms-without-asks-for`, `unreachable-link` missing; `run-on-list`, `near-duplicate-action`, `evidence-fit` exist untested; similarity not configurable |
| 4.17 | Plugin lints with passage and guidance | Built | test_plugin_lints::a_return_lint_sends_its_passage_and_guidance_back_for_a_fix | |
| 4.18 | `code_owners.yaml` | Missing | | |
| 4.19 | `playbooks.yaml` | Missing | | |
| 4.20 | `raid.yaml` | Missing | | |
| 4.21 | `stages.yaml` | Built | test_stages::workspace_replaces_or_removes_plugin_stages, order_wording_and_mode_override | |

## PART 5 – Data and storage

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 5.0 | SQLite system of record | Built | test_store | |
| 5.0 | Sources saved by hash and registered | Built | `engine/intake.py`; test_routes::a_source_shows_the_pasted_text | |
| 5.0 | `data/` export per type plus ledger, committed | Partial | `engine/storage/export.py`; test_export::export_commits_to_the_workspace_git | Not on a schedule or after batches |
| 5.0 | Ledger same-transaction with all fields | Built | `engine/storage/db.py:25-41`; test_store::every_changed_field_is_in_the_ledger_with_who_and_why, a_failed_transaction_leaves_no_record_and_no_ledger | |
| 5.0 | Long text: formats, versions, hash store, 3 authorship kinds, export | Built | test_long_text (14 tests) | |
| 5.0 | Round trip on both demos | Built | test_export::fixture_round_trips; selfcheck | |
| 5.0 | `cockpit restore --as-of` | Missing | | |
| 5.0 | Single-record restore | Missing | | |
| 5.0 | Provenance per ledger entry | Built | `ledger.trust` column | |
| 5.0 | Packets mark untrusted-derived fields | Missing | | |
| 5.0 | Record versions merge or refuse | Built | test_store::a_stale_write_to_other_fields_merges, a_stale_write_to_the_same_field_is_refused | |
| 5.0 | Ids from sequences, never reused | Built | test_store::deleted_ids_are_never_reused | |
| 5.0 | Jobs table with leases; scheduler lease | Missing | No jobs table in `db.py` | |
| 5.0 | Instance lease and `cockpit takeover` | Built | test_lease; test_cli::takeover_frees_a_workspace_left_open | |
| 5.0 | Synced folder: per-project readable copy, atomic writes, layouts, `.cockpit` machine copy, never overwrite outside edits | Built | test_sync | |
| 5.0 | Sources travel with project | Built | test_outside::sources_and_outputs_are_readable_and_their_bytes_travel | |
| 5.0 | Encrypt or exclude sources above a data level | Missing | | |
| 5.0 | Cockpit knows its own files | Built | test_outside::the_cockpits_own_bookkeeping_is_never_a_conflict_copy | |
| 5.0 | `outputs/` rebuild-or-keep | Partial | test_outside::generated_files_are_written_and_rebuilt_when_edited | |
| 5.0 | Folder lease, ledger comparison, load newer copy | Built | test_handover (9 tests) | |
| 5.0 | Only verified files load | Built | test_handover::a_folder_still_syncing_is_never_loaded | |
| 5.0 | Diverged histories never merge silently | Built (CLI only) | test_handover::diverged_histories_load_nothing_until_one_is_kept | Resolution only via `cockpit sync keep` |
| 5.0 | Outside edits come back as proposals | Built | test_outside | |
| 5.0 | Working copies | Built | test_working_copies | |
| 5.1 | Records by id; renames show everywhere | Built | test_routes::a_person_in_use_cannot_be_removed_and_a_rename_shows_everywhere | |
| 5.1 | Person | Partial | | Comms and area fields missing |
| 5.1 | Team | Partial | | No `area`, no screen or route |
| 5.1 | Project | Partial | | `risks`, `decisions`, `milestones`, `players`, `facts`, `hold` missing |
| 5.1 | Action | Partial | | `followups`, `store` missing |
| 5.1 | Question | Partial | | `affects`, `asks_for`, `on_answer`, `key`, pending flags missing |
| 5.1 | Source | Partial | | `from`, `restriction` missing |
| 5.1 | Change | Partial | Folded into request + source + snapshot | |
| 5.1 | Request | Built | | |
| 5.1 | Changeset | Partial | | `read_back`, `quiet`, `feedback` missing |
| 5.1 | Rule | Partial | Config only | |
| 5.1 | Run | Partial | | Packet hash, template/playbook versions, parameters, upstream host missing |
| 5.1 | Signal | Partial | sent_back, undone, pulled_back, draft_edited recorded | dropped, reworded, held_declined never recorded |
| 5.1 | Meeting, Issue, Assumption, Draft, Problem, Dependency, GlossaryTerm, Lesson | Missing | | |
| 5.1 | Plugin tables and `ext`; declared refs guard deletes | Built | test_plugin_api_02::delete_is_refused_while_referred_to_and_undo_brings_a_record_back; test_organizations | Merge missing |
| 5.2 | Inputs saved first; zoned times; versioned writes; applier for knowledge | Built | test_today_dashboard::details_must_be_readable_times; test_screen_edits | |
| 5.2 | Export committed before migrations and fixes | Missing | | |
| 5.2 | Retention | Missing | | |
| 5.3 | Files by SHA-256; kinds; limits; backed up | Built | test_files (6 tests); `engine/backup.py:86` includes `files` | Restore missing |
| 5.3 | Downloads keep media type; never inline HTML/SVG | Partial | `api/routes.py:863-875` | Non-images sent as octet-stream |
| 5.3 | Previews | Built | test_plugin_api_0319::a_preview_carries_alt_text | |

## PART 6 – Engine

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 6.1 | Plugin host: discover, verify, register, wrap calls | Built | test_plugins (24 tests) | Exceptions become plugin status, not a Problem record |
| 6.2 | Connectors with typed errors; core folder and fake | Built | test_watch | |
| 6.2 | Text extractors; unsupported type flagged once | Missing | | |
| 6.3 | Clipboard / file / fake channels; canonical form; verify after publish | Missing | | |
| 6.4 | No network is not a failure | Built | test_watch::no_network_is_not_a_failure | |
| 6.4 | Reachability pre-check | Partial | | |
| 6.4 | Outage as one problem | Partial | Per-source `failures_before_asking` (test_watch::failures_ask_once_and_a_good_read_ends_the_question) | No workspace-wide outage |
| 6.4 | `by_us` | Built | test_watch::changes_by_our_own_accounts_and_scratch_files_are_closed | |
| 6.4 | Moved file / spreadsheet cell compare | Missing | | |
| 6.4 | Supersede (fold) | Built | test_watch::a_newer_change_folds_in_the_older_one_still_waiting | |
| 6.4 | `watch.item`, `watch.add` ops | Missing | | |
| 6.4 | Baseline first read; snapshots; diffs | Built | test_watch; test_watch_recent | |
| 6.5 | Triage in `watch.yaml`, core matchers, Auto-closed, Take a closer look, pull-back signal | Built | test_watch::triage_rules_close_changes_with_a_reason; `api/watch_routes.py:107-130` | No "This is ours" button |
| 6.6 | Batches with a shared frozen stable prefix | Missing | | |
| 6.6 | Clean input first | Built | test_pipeline::quoted_history_already_on_file_is_removed_before_the_ai_sees_it | |
| 6.6 | Packet contents | Partial | `engine/packet.py:88-101` | No glossary, rules, lessons, scope, facts or `our_accounts` |
| 6.6 | Trusted/untrusted marking | Built | test_pipeline::untrusted_input_is_marked_and_the_note_is_not; test_plugin_safety::a_scheduled_request_note_is_never_trusted | Derived fields not marked |
| 6.6 | Stable first, request last | Partial | | No cache layer marks |
| 6.6 | Full/compact open items with closing hints | Missing | | |
| 6.6 | Size budget with omissions listed | Partial | Too long becomes "needs you" | No splitting or omissions list |
| 6.6 | Self-check fix round | Built | test_pipeline::the_fix_round_can_correct_the_answer | |
| 6.6 | Fallback chain; "needs you" | Built | test_ai::a_missing_key_is_an_auth_failure_and_falls_through | |
| 6.7 | Op registry, per-task op list and schema, JSON repair | Built | test_pipeline::parse_repairs_fences_prose_and_trailing_commas | |
| 6.7 | Evidence required and matched | Built | test_pipeline::a_quote_that_isnt_in_the_input_goes_back_once_then_is_refused | |
| 6.7 | Drafts are not claims; prose, continuation, anchors | Built | test_drafts | Checkable facts inside drafts not enforced |
| 6.7 | Person-owned fields | Built | test_plugin_api_02::a_person_only_value_from_the_assistant_is_held_and_applies_when_released | |
| 6.7 | `project.add` | Built | test_projects_series | |
| 6.7 | `text.propose` / `text.accept` | Built | test_long_text::accepting_some_changes_writes_a_merged_version | |
| 6.7 | Tiers; system ops from input held | Built | test_plugins::system_tier_is_held_until_confirmation | |
| 6.7 | Read-back (4 lines), contradiction pause | Missing | | |
| 6.7 | Core op list | Partial | ~24 core ops exist | Missing: `source`, `record.add`/`del`/`rename`, `action.update`/`assign`, `decision.add`, `milestone.*`, `risk.*`, `question.update`/`move`/`drop`, `meeting.*`, `person.merge`, `dependency.*`, `issue.*`, `assumption.*`, `glossary.*`, `lesson.add`, `parked`, `inbox`, `lookup`, `watch.*`, `doc`, `draft.request`, `dev.request`, `handoff`, `rule.*`, `config.set`, `plugin.enable`/`disable` |
| 6.7 | `dev.request` lists considered ops; validator checks registry | Missing | `report.draft` has no such check | |
| 6.7 | Invariants: schema, ids, versions, tiers, people resolve, action has a person, untrusted never a rule or recipient, model name, question links, evidence | Built | test_pipeline::an_unknown_name_is_held_with_a_who_is_this_question, an_action_with_no_owner_waits_for_pick_an_owner, hostile_input_cannot_add_people_or_recipients_on_its_own, questions_to_others_need_a_link_they_can_open | |
| 6.7 | Invariants: scope, facts, audiences, update-log with published edits | Missing | | |
| 6.7 | Lint return / held / warn routing | Built | test_pipeline::blocked_wording_warns_on_internal_items_and_holds_what_goes_to_others | Several lints missing (see 4.17) |
| 6.7 | Link enrichment from item keys | Missing | | |
| 6.7 | Re-render outputs on apply | Missing | | |
| 6.7 | Undo by group | Built | test_pipeline::undo_skips_a_group_someone_changed_since | |
| 6.7 | Keep/Restore on undo conflict | Partial | | |
| 6.7 | Quiet classification ("for the PM" only when needed) | Missing | Every changeset goes to review | |
| 6.8 | Routing decision for an unsure recipient | Built | test_pipeline::a_first_name_two_people_share_offers_both | |
| 6.8 | Answer flow | Built | test_routes::answering_a_question | |
| 6.8 | Dedup by key; link enrichment; re-check other questions | Missing | | |
| 6.8 | Feedback flow (reword, reroute, drop); correction checked against data | Missing | | |
| 6.8 | Aging and nudges | Built | `engine/today_queue.py:239-270` | Escalation missing |
| 6.9 | Mark done (PM's own) | Built | test_routes::the_pm_marks_an_action_done_and_back | |
| 6.9 | They finished it | Built | FollowUps.test "They finished it closes the action with Undo" | |
| 6.9 | Assign a held action | Built | test_routes::a_held_action_gets_an_owner | |
| 6.9 | Followed up; Reassign; single store interface | Missing | | |
| 6.10 | Told dates via Mark sent | Built | test_followups_backup_eval::mark_sent_records_questions_and_told_dates_and_edits | |
| 6.10 | Baseline date; `track_only` exclusion | Missing | | |
| 6.11 | Resolve names (id, full name, alias, first name, me) | Built | `engine/names.py`; test_pipeline | |
| 6.11 | `owner_format` render/parse; teams; `person.merge` | Missing | | |
| 6.12 | Renderer, publisher, pull-back, shared masters, change classification | Missing | | |
| 6.13 | Governor (re-queue, stale, outage, sweeps, hourly export) | Missing | A request left in "running" after a crash is never re-queued (`engine/worker.py:224-245`) | |
| 6.13 | Problem records | Missing | | |
| 6.13 | Identical outcome after send-back refused | Built | test_provider_safety::the_same_answer_after_a_send_back_is_refused | |
| 6.13 | Reports | Partial | `report.draft` via Ask | |
| 6.13 | Handoff; check-the-premise rule | Missing | | |
| 6.14 | Offline jobs wait | Built | test_watch::no_network_is_not_a_failure | |
| 6.14 | Config/code change stops new work | Built | test_provider_safety::changed_settings_stop_new_work_until_restart | Restarts only on the person's go (list 1) |
| 6.14 | Scheduler lease; `server.role` | Missing | | |
| 6.15 | Today builder: verb lines, groups, rank | Built (engine) | `engine/today_queue.py`; test_today_queue::the_queue_ranks_decisions_first_then_reviews | UI doesn't use it; no meetings, problems or lessons lines |
| 6.16 | openai-compatible, local and cli-agent adapters | Built | test_ai; test_cli_agent; test_setup::a_model_server_on_this_computer_is_found_without_a_key | |
| 6.16 | Native and aggregator adapters | Missing | | |
| 6.16 | Per-model capabilities | Partial | `engine/ai/task.py:51-58` | Context and price only; no vision, tools or caching flags |
| 6.16 | Add account flow with Test | Built | WelcomeAi.test; AiAccounts.test; test_setup::an_ai_account_keeps_a_pasted_key_on_this_computer | No evaluation before tier approval |
| 6.16 | AiTask contract | Built | | No attachments |
| 6.16 | Lookup loop in API mode | Missing | | |
| 6.16 | Agent mode locked down | Built | test_cli_agent::the_agent_runs_in_its_own_folder_with_a_small_environment, the_lockdown_test_catches_an_agent_that_writes_anywhere | |
| 6.16 | `classify_error` from runner only | Built | test_ai::error_kind_comes_from_the_call_never_from_the_model_text | |
| 6.16 | `health()` | Missing | | |
| 6.16 | Routing by capability | Partial | Data level and context only (test_ai::accounts_only_see_data_they_are_allowed, an_account_whose_model_cant_hold_the_request_is_skipped) | Self-check doesn't validate capabilities |
| 6.16 | Escalate on failure | Built | test_pipeline::the_stronger_tier_can_fix_what_the_routine_tier_got_wrong | |
| 6.16 | Independent check | Built | test_second_opinions | |
| 6.16 | No silent provider | Built | test_provider_safety::a_tier_naming_a_missing_account_is_a_config_error | "first run on <account>" missing |
| 6.16 | Smoke test with lockdown | Built | test_provider_safety::the_smoke_test_tries_every_tier_with_each_tasks_parameters | Self-check doesn't reject unaccepted parameters |
| 6.16 | Sign-in failure includes hint | Partial | test_cli_agent::a_sign_in_failure_says_what_to_do | A waiting line, not a question to the PM |
| 6.16 | Probation | Missing | | |
| 6.16 | Prompt overrides | Built | test_plugin_tasks::the_workspace_overrides_a_plugins_prompt | No config template variables; no per-adapter formatter |
| 6.16 | Evaluation, several runs | Built | test_followups_backup_eval::every_case_passes_with_its_ideal_answer; test_cli::evaluate_runs_a_workspaces_own_cases_with_its_own_ai_setup | No approval step or scheduled checks |
| 6.16 | Reproducible runs; `cockpit replay` | Missing | | |
| 6.16 | Estimate, go, budgets, spend shown | Built | test_routes::a_run_held_for_its_cost_shows_its_estimate_and_goes_on_the_go, status_reports_what_the_assistant_has_cost_and_when_a_limit_is_near | No batch total; no usage panel |
| 6.16 | `allowed_data` | Built | | |
| 6.17 | Weekly check-up; updates on request | Missing (marked later) | | |
| 6.18 | Scope resolver, sweep, cross-domain | Missing | | |
| 6.19 | Fact resolver | Missing | | |
| 6.20 | Signals | Partial | | See 5.1 |
| 6.20 | Quality panel; private cases from signals; rule suggestions | Missing | | |
| 6.21 | Rules review | Missing | | |
| 6.22 | Glossary, lessons, search lookups | Missing | | |
| 6.23 | Dependencies, baselines | Missing | | |
| 6.24 | RAID, risk reviews, escalation, cadence, meeting agendas | Missing | | |
| 6.25 | Ask box; answer with cited words; `setting.propose`; `report.draft`; user guide sections | Built | test_ask (6 tests); Ask.test | |
| 6.25 | Ask packet with playbooks and search lookups; suggested record changes as ops; repeated asks become signals | Missing | `engine/packet.py:130-172` | |
| 6.26 | Stages: entry checks by rule, person or rule moves, AI only proposes, starts wait for go, `applies_if`, undoable `stage.move`, Today "ready to move on", history | Built | test_stages (35 tests); test_plugin_api_0323::a_stage_that_doesnt_apply_is_passed_over; Stages.test | |

## PART 7 – UI

| § | Requirement | Status | Evidence | What is absent |
|---|---|---|---|---|
| 7.0 | Today is a ranked queue first | Contradicted | `web/src/components/TodayBoard.tsx:36-45` (four-column board) | List 1 |
| 7.0 | Use the whole screen | Built | `web/e2e/shell.spec.ts:142-160` | |
| 7.0 | One primary per row; undo toasts | Built | Row.test; toasts.test | |
| 7.0 | Edit in place | Built | FollowUps.test "Copy puts the edited message …" | |
| 7.0 | Show why with highlighted source | Built | WhatChanged.test "a change shows what was done, why, and the highlighted source" | |
| 7.0 | "N new · Show" | Partial | `en.json:187` | In What changed only |
| 7.0 | Wording sheet, ui.yaml overrides, no internal terms | Built | wording.test "no internal terms reach the screen" | |
| 7.0 | No command line, file name or env ref on the default path | Partial | | List 3 and `en.json:4,6,406,660,1126` |
| 7.1 | Header pieces | Built | Header.test; StatusMenu.test; status.test | |
| 7.1 | Sidebar groups, real links, rail 1024–1279, navigation budget | Built | Sidebar.test; `web/e2e/shell.spec.ts` | |
| 7.1 | `ui.yaml` reorder/hide panels | Missing | | |
| 7.1 | Admin sections in Settings (queue, Quality, Rules, Security) | Missing | | |
| 7.1 | Phone bottom bar | Built | BottomBar.test | |
| 7.1 | Phone review mode | Missing | | |
| 7.1 | Installable web app | Missing | | |
| 7.1 | Projects view as portfolio table; project page with RAID | Missing | `web/src/App.tsx:165-168` opens the Setup screen | |
| 7.2 | Declarative table/list/board panels; spec validated; actions as ops | Built | Panel.test; test_today_panels_jobs::a_panel_must_name_real_fields_and_its_own_actions | No form/detail views |
| 7.2 | Compare view (2- and 3-way, per passage, one `text.accept`) | Built | TextReview.test; test_long_text::the_review_routes_compare_accept_and_edit | No word-level diff marks |
| 7.3 | Change rows with nested work and evidence | Built | WhatChanged.test | |
| 7.3 | "Show the change" word diff | Missing | | |
| 7.3 | Looks good, Send back (note), Undo | Built | WhatChanged.test | |
| 7.3 | Process with the assistant, This is ours, Ignore, Done | Missing | | |
| 7.3 | Problem cards | Missing | | |
| 7.3 | 8 filters and "All looks good" | Partial | Only Needs attention, Done, All (`en.json:150-152`) | |
| 7.4 | Waiting to go out (whole section) | Missing | `web/src/App.tsx:154-162` placeholder | |
| 7.5 | To send / Waiting on them filter; You first then A–Z | Built | FollowUps.test; test_followups_backup_eval::the_pm_comes_first_then_everyone_a_to_z | |
| 7.5 | Copy then Mark sent, Undo, menu Mark sent, clipboard blocked | Built | FollowUps.test; Playwright step 4 | |
| 7.5 | Message format | Built | test_followups_backup_eval | |
| 7.5 | Waiting on them: date, They finished it, Record reply | Built | FollowUps.test | |
| 7.5 | Channel Send; tracked-only cards and domain grouping; Reassign; Take care of this; By group; Respond to the assistant | Missing | | |
| 7.6 | Spend waits for a go | Built | test_routes::a_run_held_for_its_cost_can_be_dismissed_and_put_back | |
| 7.6 | Lists and links rendered | Built | SafeText.test | |
| 7.6 | Hand-in "Whose words are these?" | Built | HandIn.test; Playwright step 3 | |
| 7.6 | Waiting states say why | Built | Ask.test "each state is said in words, with why it is waiting" | |
| 7.6 | Skeletons | Built | EmptyState.test | |
| 7.6 | Held system op Confirm/Decline beside its source | Partial | Release only (`api/routes.py:1122`) | No Decline |
| 7.6 | Read-backs | Missing | | |
| 7.6 | Undo report with Keep/Restore | Partial | | |
| 7.7 | Ranked queue | Missing in UI | Engine and API built (test_today_queue) | |
| 7.7 | Inspector; This week | Missing | | |
| 7.7 | Agenda, to-dos, Came in, Connect line | Built (as columns) | TodayBoard.test; test_today_dashboard | |
| 7.7 | No panel or filter inside the queue | Contradicted | `web/src/components/TodayBoard.tsx:343-352` | |
| 7.7 | j/k over the queue | Partial | | |
| 7.7 | Heading with date, count and next check | Partial | Date only (`web/src/App.tsx:142-145`) | |
| 7.7 | Setup line | Built | SetupLine.test | |
| 7.8 | First-run steps 1–7, skippable, key in private folder, backup folder checked, plugin steps, restart rule | Built | Welcome.test; WelcomeAi.test; WelcomeBackup.test; test_setup (37 tests) | |
| 7.8 | steps \| step layout | Partial | | |
| 7.9 | Schema-generated forms | Built | Settings.test | |
| 7.9 | nav \| form \| help layout | Missing | | |
| 7.9 | Live save and save bar | Partial | Single Save with Undo | |
| 7.9 | Changed · Reset | Partial | "Back to default" | |
| 7.9 | Plain-word pickers; template previews | Missing | | |
| 7.9 | AI accounts with status chip and Test | Built | AiAccounts.test | Key location shown inline, not behind Details |
| 7.9 | Lists section | Built | Settings.test "Settings ends with a Lists section …" | |
| 7.9 | A setting lives in one place only | Contradicted | Sync folder on People screen (`web/src/components/Setup.tsx:56,671+`) and in Settings | |
| 7.9 | Appearance with contrast warning | Missing | Contrast computed in `lib/theme.ts`, no UI | |
| 7.10 | Shortcuts configurable; contrast; status not by colour; polite announcements; focus return; reduced motion | Built | keys.test; theme.test; Pill.test; toasts.test; ModalPanel.test; App.test | 3:1 borders and 44px targets untested |
| 7.11 | Relative assets, runtime config, TanStack Query + SSE, generated types, React Aria, hash routes, wording sheet | Built | test_api::the_ui_gets_a_base_for_the_configured_path_and_a_strict_policy; live.test; views.test | |
| 7.11 | Untrusted rendering and CSP | Built | SafeText.test; Playwright "nothing broke the content security policy" | |
| 7.11 | Playwright root and nested with axe; stylelint | Built | `web/playwright.config.ts`; stylelint-rules.test.ts | |
| 7.11 | Virtualized lists | Missing | | |
| 7.11 | Style-guide screenshots at all widths and themes | Partial | `web/e2e/shell.spec.ts:30` | |
| 7.11 | Screen-space checks | Partial | 90% width only | |
| 7.12 | Tokens, shared components, branding, theme/density, icons | Built | `web/src/theme/tokens.css`; `web/src/ui/*.test`; theme.test; Icon.test | |
| 7.12 | Diff component | Missing | | |
| 7.12 | Data display rules | Partial | | |
| 7.13 | List \| detail for Work views | Missing | | |
| 7.13 | Stages board | Partial | Stages.test | No drag or `m` key |
| 7.13 | Projects and People tables | Missing | | |
| 7.13 | Files and Sources table + detail | Partial | List only | |
| 7.13 | Record page activity \| details | Built | RecordPage.test; test_record_page | |
| 7.13 | Hand-in drawer | Partial | Rendered inline in main (`web/src/App.tsx:225`) | |
| 7.13 | Ask side pane on wide screens | Partial | Modal (`web/src/components/Ask.tsx:48`) | |
| 7.14 | Engine-built titles; outcome wording | Built | `engine/titles.py`; test_today_queue (title tests) | |
| 7.14 | Row anatomy | Built | Row.test | |
| 7.14 | Record page by name | Built | test_record_page | |
| 7.14 | Forms in drawers, grouped | Missing | Drawer used only in StyleGuide; forms inline in Setup | |
| 7.14 | Disabled primary says why | Built | Button.test | |

---

## FLAG 1 – Code that contradicts the design

1. **Today home screen.** Today is a four-column board (Agenda, To do, Needs you, Came in) in `web/src/components/TodayBoard.tsx:36-45`. Design 7.0/7.7 and the 2026-10-11 decision replace that with a ranked queue, an inspector and a rail. The engine queue (`engine/today_queue.py`, `GET /api/today/queue`) exists but the web never calls it.
2. **Panels inside the queue.** The Needs-you column embeds the full What changed, PluginToday and Follow-ups lists, filters included (`web/src/components/TodayBoard.tsx:343-352`). 7.7 says no panel, filter or tab inside the queue.
3. **Pack install.** `POST /api/packs/{id}/install` and `/uninstall` (`api/pack_routes.py:114-155`, `engine/pack_install.py`) install wheels into the app's own environment. 3.11 still says "the app never installs code into itself". Decision 2026-10-11 approved an Install button, so the design text is stale. The web shows only an install command to copy, so no button exists either.
4. **Core connectors.** Mailbox (IMAP), calendar and feed connectors ship in core (`engine/connectors/mailbox.py`, `calendar.py`, `feed.py`, registered at `engine/connectors/__init__.py:269-280`). 1.4/6.2 put them in plugins.
5. **Self-restart.** 6.14 says the process restarts itself on code or config change. The code holds work until the person chooses Restart now (`engine/worker.py:157-222`). That matches 7.1/7.8 and CLAUDE.md, so the design is inconsistent with itself.
6. **System ops from the PM's note.** They apply at once (`engine/applier.py:289-292`) with no read-back and no contradiction pause. 6.7 makes both conditions of "apply at once".
7. **`owner_format`.** `workspace.owner_format` (`engine/config/schema.py:142`) is never read; owners always render as full name. That is a setting with no effect.
8. **Near-duplicate threshold.** The `near-duplicate-action` similarity is hard-coded at 0.8 (`engine/applier.py:268`). 4.17 makes it a `checks.yaml` setting (0.85).
9. **Sync folder in two places.** The synced-folder setting and the scheduled-work list appear on the People/Projects screen (`web/src/components/Setup.tsx:56-57,671+`) as well as in Settings (`engine/settings.py:41`). 7.9 says a setting lives in one place only.
10. **Projects and People views.** Both open the Setup editor (`web/src/App.tsx:165-168`), not a portfolio table and a people table (7.1, 7.13).
11. **Key location shown inline.** AI account rows show where a key is read from ("key from the environment variable X", "key from the file /path") on the row itself (`engine/secrets.py:40-42` → `web/src/components/AiAccounts.tsx:93-94`). 7.9 puts this behind Details.
12. **Keychain.** `keychain:` references are refused (`engine/secrets.py:29-30`); 4.0, 4.8 and 3.2 use `keychain:NAME` as the standard secret reference.
13. **Ask material names files.** The Ask packet's settings material says "changed in <file>.yaml" (`engine/help.py:83`), so answers can cite config file names. 6.25 says the material never says where keys come from.
14. **`confirm_above_usd` default.** It defaults to 0.10 (`engine/config/schema.py:443-447`); 4.8 shows 0.25.
15. **File downloads.** Non-image files are served as `application/octet-stream` (`api/routes.py:874`). 5.3 says downloads keep the stored media type.
16. **Design self-conflict on triage.** 4.5 (`config/triage.yaml`, 9 matchers) conflicts with 6.5 (rules in `watch.yaml`, 4 matchers). The code follows 6.5.
17. **Kit edits need a restart.** Kit type changes need one; 3.10 says adding a field or option is immediate.

## FLAG 2 – Defaults that leave a real person unable to get a result without editing files or running commands

1. **Getting started needs a terminal.** Install (`deploy/install.sh`), `cockpit init`, and `cockpit serve` are all commands. `server.open_browser` defaults to false (`engine/config/schema.py:172`), so without `--open` the person must copy the token URL from the terminal. Signed-out screens say "Open the link printed by `cockpit serve`" (`api/app.py:283`).
2. **No git history of records.** `storage.export.every_minutes` and `export.remote` are never read. `data/` is written only by `cockpit export` (`engine/cli.py:434`).
3. **No restore.** There is no restore path at all: no `cockpit restore`, no single-record restore, and backups cannot be restored from a screen. `cockpit import` into an empty DB is the only route.
4. **Two-computer divergence.** Choosing which history to keep is CLI-only (`cockpit sync keep --here|--folder`, message at `engine/handover.py:227-230`).
5. **A stale instance lease.** It needs `cockpit takeover` (`engine/storage/lease.py:36-37`).
6. **Mail and calendar sources.** The core mailbox password and calendar address accept only `env:NAME` or `file:/path` (`engine/connectors/mailbox.py:36-37`, `calendar.py:23-26`). The person must set an environment variable or create a secret file by hand.
7. **Plugin secrets.** `workspace.plugins.secrets` (a dict) has no screen. It must be edited in `workspace.yaml` as `env:`/`file:` references.
8. **Kit item types (the free version's main feature).** They cannot be defined or edited on any screen: `types` is a list of objects and the form marks it non-editable (`engine/settings.py:188,212-229`). Only shipped templates or hand-editing `config/plugins/kit.yaml` work. "Save as template" is CLI-only (`cockpit template save`).
9. **Settings with no screen.** These must be hand-edited:
   - standing rules (`rules.yaml`)
   - triage rules (`watch.triage`)
   - stage definitions and wording (`stages.yaml`)
   - lint severities (`checks.yaml` lints and projects)
   - wording overrides and keyboard shortcuts (`ui.wording`, `ui.shortcuts`)
   - per-task AI settings and prices (`ai.tasks`, `ai.prices`)
   - routing rules, content levels and per-task budgets (`ai.routing`, `ai.content_levels`, `ai.budgets.per_task`)
   - tier fallbacks and escalation (`ai.tiers.*.fallback` / `escalate_to`)
   - catalog release tokens (`workspace.plugins.catalog.release_tokens`)
   - plugin job schedules (`workspace.plugins.jobs`)
10. **Error messages send the person to `ai.yaml`.** Raising `tasks.<kind>.max_output` has no screen (`engine/dispatcher.py:409,470`). `budgets.per_run_usd` is on screen but the message still says `ai.yaml` (`engine/dispatcher.py:151`). `dispatch.max_input_chars` has no screen (`engine/dispatcher.py:114`).
11. **Server settings are file/flag only** (`engine/settings.py:51`): host, port and base path.
12. **Model evaluation is CLI-only** (`cockpit evaluate`). 6.16 expects it in Settings → AI before a model is approved.
13. **Adding packs.** The Add-ons screen offers only a command to copy (`web/src/components/Addons.tsx:303-317`); the install API exists but has no button.
14. **A test-only source kind is offered to users.** "A stand-in source for tests" (core `fake` connector, `engine/connectors/__init__.py:280`) appears in Add a source (`api/setup_routes.py:286-310`), with an "items" setting the form cannot edit.
15. **Crashed runs stay stuck.** A request left in `running` after a crash is never re-queued (`engine/worker.py:224-245`), so it stays stuck with no button to recover it.
16. **Send out does nothing.** "Waiting to go out" is an empty placeholder that sends people to What changed (`web/src/App.tsx:154-162`).

## FLAG 3 – User-visible text in engine/ or api/ naming files, key paths, env vars or commands

These reach the screen as waiting lines, refusals, form descriptions, status reasons or Ask answers.

**Waiting lines and refusals**
- `engine/ai/router.py:65` – "the {tier} tier isn't set up in ai.yaml"
- `engine/ai/router.py:68` – "add one to ai.yaml and set tiers.{tier}.use"
- `engine/ai/router.py:76` – "{provider} isn't an account in ai.yaml"
- `engine/ai/router.py:94-96` – "(roles.check.same_account in ai.yaml)"
- `engine/dispatcher.py:114` – "raise dispatch.max_input_chars"
- `engine/dispatcher.py:150-151` – "raise budgets.per_run_usd in ai.yaml"
- `engine/dispatcher.py:408-409` – "Raise tasks.{kind}.max_output in ai.yaml"
- `engine/dispatcher.py:469-470` – same message, for drafts
- `engine/dispatcher.py:545` – "Check the account in ai.yaml, then try again."
- `engine/applier.py:992` – "workspace.user.person isn't set …"; reaches the screen through `engine/worker.py:237`, which also shows the raw exception text
- `engine/watch.py:87` – "there is no source {id} in watch.yaml"

**Secrets**
- `engine/secrets.py:22` – "the environment variable {name} isn't set"
- `engine/secrets.py:27` – "the secret file {path} doesn't exist"
- `engine/secrets.py:30` and `:31` – "use env:NAME or file:/path"
- `engine/secrets.py:40` and `:42` – "key from the environment variable {name}" / "key from the file {path}"; shown on AI account rows (`api/setup_routes.py:419-421`) and in the smoke test (`engine/ai/smoke.py:76,83`)
- `api/setup_routes.py:469`, `:529`, `:592` – "give env:NAME instead"
- `api/pack_routes.py:134` – wraps a `SecretError`, so it carries the env var or file text

**Settings saves**
- `engine/settings.py:355` – "{key} is set in {file}.yaml or with a flag, not here"
- `engine/settings.py:362` – "{key} is changed in {file}.yaml"
- `engine/settings.py:358,361` – dotted key paths in refusals
- `engine/config/loader.py:205` – "{name}.yaml has problems: {file.key.path}: …"; surfaced through `engine/settings.py:378-380` and `api/setup_routes.py:240,448,632`
- `engine/config/schema.py:540,545,547,550,553,557` – AI config validation messages naming `providers.*`, `tiers.*`, `routing[i]`, `tasks.*`, `roles.*`
- `engine/config/stages.py:23,28,31,34,38,60,64` – "stages.yaml: …" / "rules.yaml: …"; also used as plugin status reasons

**Add-ons screen ("why off")**
- `engine/plugin_host.py:755,781` – "requires.secrets"
- `engine/plugin_host.py:1108` – "plugin API … is outside …"
- `engine/plugin_host.py:1111` – "provides.data … beside plugin.yaml"
- `engine/plugin_host.py:1170` – "(storage.files.accepted_types)"
- `engine/plugin_host.py:1191` – "requires.tools"
- `engine/plugin_host.py:1338` – "requires.secrets"
- `engine/plugin_host.py:1393` – "requires.data_levels"

**Field descriptions shown on Settings and Sources forms**
- `engine/config/schema.py:89`, `:97` – env:NAME or file:/path
- `engine/config/schema.py:117` – ".cockpit/tools.yaml"
- `engine/config/schema.py:124` – env:NAME or file:/path
- `engine/config/schema.py:355` – env:NAME or file:/path
- `engine/config/schema.py:403` – roles.check.same_account
- `engine/config/schema.py:715` – "see web/src/wording/en.json for the keys"
- `engine/connectors/mailbox.py:37`, `engine/connectors/calendar.py:25` – env:NAME or file:/path

**Ask answers (material the AI may quote)**
- `engine/help.py:83` – "changed in {file}.yaml"; also lists dotted keys
- `engine/guide/guide.md:105` – "Each is a source in watch.yaml"

**Terminal only (engine/ text, not screen)**
- `engine/storage/lease.py:37` – `cockpit takeover`
- `engine/handover.py:229` – `cockpit sync keep --here` / `--folder`
- `engine/workspace.py:75` – `cockpit init`
- `engine/templates.py:105` – `cockpit template list`
- `engine/worker.py:23` – "restart it"
- `api/app.py:93` – "(storage.sync.folder)"
- `engine/cli.py:304`, `:322`, `:348`, `:429` – `cockpit serve`, `server.mode`, `cockpit ai test`, restart command

**Outside the engine/api scope**
- The same kind of text is in `web/src/wording/en.json:4,6,406` (`cockpit serve`), `:660,662` (env:NAME) and `:1126` (`cockpit demo --plugin`).
