**Status: done and merged (2026-10-10).** Kept as a record of the brief. No task is handed out now.

# Next task: stages (design 6.26, config 4.21)

Read first: design 6.26, 4.21, 3.3 (extension points), 3.9, 6.7 (op tiers,
who confirms), 4.0 and 4.10, docs/design/README.md. Then engine/ops,
the applier, records, config/schema.py, plugin_api.py, the worker, and the
example plugin.

## Build
1. Config: `config/stages.yaml` in engine/config/schema.py. Per record type,
   an ordered list of stages {id, label (wording), entry: [check ids],
   starts: [task kinds]}; top-level `moves: person|rule` with a per-type
   override. Schema entries, defaults, descriptions, and demo values in
   both fictional workspaces. Validate: record type exists (core or
   plugin-registered), stage ids unique, check ids resolve, task kinds exist.
   Bad config fails at load with a plain message.
2. Plugin API: Registrar.stage_check(id, fn) so plugins register entry
   checks (namespaced <plugin>/<name>); plugins may ship default stages for
   their own record types. Rules (4.10) can also be entry checks.
   Checks are code and rules only, never AI.
3. Stage is data on the record. Op `stage.move` {record, to} with the
   version read. It refuses when an entry check fails and says which checks
   and why. It goes through the applier and ledger, and Undo works.
   The assistant may PROPOSE a move but never make one: a stage.move from
   an AI changeset is always held for the person to confirm.
4. `moves: rule`: the worker moves a record when all entry checks pass,
   recorded in the ledger with a rule as the source.
5. On entry, each `starts` task kind is queued as a request that waits for
   the person's go (estimates and budgets come later with cost control;
   leave a clear hook for them).
6. Event `stage.moved` on the event bus, after commit only.
7. API (Pydantic models in api/schemas.py, then `uv run python -m
   api.openapi`): a record's current stage and each next-stage check
   (pass/fail + reason); move; list records ready to move on (for a later
   Today line). No UI in this task; add wording keys only if the API
   returns user-facing text.
8. Stage history is a query over the ledger; expose it in the record API.
9. Example plugin: give its record type stages with one registered check,
   with demo config in both workspaces.

## Tests (at least)
Config validation errors; move passes/refuses with reasons; undo; AI
proposal is held; rule mode moves automatically; starts are queued and
wait; event fires only after commit; export/import round trip keeps
stages and history; core with no plugins enabled still passes; workspace
override renames or removes a pack's stage.

## Done
All checks in CLAUDE.md pass (pytest, ruff, format, selfcheck, web
test/build/e2e). Commit message lists steps done/unfinished and any check
you couldn't run and why.

## Out of scope
Dependencies and baselines (6.23), cost control, file channel, any UI,
the publishing pack. Note scope or design questions in your final message
instead of deciding them.

## Check cadence
After each step, run only the tests for what changed plus Ruff. Run the
full checklist (all pytest, selfcheck, web test/build/e2e) once at the end,
and again only if something fails. Push to codex/stages only.
