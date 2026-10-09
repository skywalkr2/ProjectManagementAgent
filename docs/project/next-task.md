# Next task: the plugin host (plugin API 0.x)

A brief for whichever coding agent picks this up. Work on a **new branch** made from `claude/tender-tesla-16a8ob`
(for example `codex/plugin-host`), so the work can be reviewed before it is merged. Follow `CLAUDE.md` / `AGENTS.md`.

## Why this, why now

The owner will use the cockpit for real only once the publishing pack exists (decisions, 2026-10-09, "Real use starts
with the publishing pack"). Every pack needs the plugin host first. This task builds the host and nothing else.

## Read first

- `docs/design/03-plugins.md`: all of it (3.1 to 3.9). This is the specification.
- `docs/design/06-engine.md` 6.1 (plugin host) and 6.7 (changesets and the applier).
- `engine/ops.py`, `engine/applier.py`, `engine/records.py`, `engine/worker.py` (the `Events` counter), `engine/selfcheck/`.

## Build

1. **`engine/plugin_api.py`**: the only module plugins import. A `Registrar` passed to each plugin's `register()` with:
   `record_type(model)`, `op(model, tier, apply)`, `op_validator(op_name, fn)`, `task_kind(...)`, `subscribe(event, fn)`.
   Re-export only what plugins need (base classes, `WriteContext`, types). Nothing else from the engine.
2. **Manifest** (`plugin.yaml`, design 3.2): a Pydantic schema; unknown keys are errors. Check `plugin_api` version range,
   `depends_on`, and that what the code registers matches `provides` exactly.
3. **Discovery and enabling**: bundled plugins in `plugins/`, private ones in `<workspace>/plugins/`, installed ones by the
   entry point group `pm_cockpit.plugins`. Only names in `config/workspace.yaml` `plugins.enabled` load.
4. **Registries wired into the core**: plugin record types work with the store, export and import (round trip tested);
   plugin ops go through the applier with their tier and validators; identifiers must be namespaced `<plugin>/<name>`.
5. **Plugin config**: `config/plugins/<plugin>.yaml`, validated against the schema the manifest names (4.12).
6. **Events** (3.4): a named event bus (keep the existing change counter for the UI). Publish at least
   `changeset.applied`, `changeset.undone`, `record.changed` (kind, id, fields, version, op), `request.queued`,
   `question.answered`. Handlers may read, queue requests and file questions; they never write records directly.
7. **Failures stay contained**: a plugin that raises on load or in a handler is disabled for that run and reported
   (a clear log line and a status entry the API can show); the core and other plugins keep running.
8. **Example plugin** `plugins/example/` (fictional, tiny): one record type, one op, one event handler, its config, and demo
   config and data in both `workspaces/demo-a` and `workspaces/demo-b`.
9. **Self-check**: validate every bundled manifest; run the suite with no plugins enabled and with the example enabled.

## Done means

- All checks pass: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`,
  `uv run python -m engine.selfcheck`, `npm --prefix web test`, `npm --prefix web run build`, `npm --prefix web run e2e`.
- New tests cover: manifest errors, version and dependency refusal, a namespacing violation refused, a plugin op applied and
  undone through the ledger, a handler receiving `record.changed`, a crashing plugin contained, export/import round trip
  with a plugin record type, and the boundary scan refusing a plugin that imports engine internals.
- `docs/design/CHANGES.md` and the roadmap updated; anything that departs from design Part 3 gets a one-line note in
  `docs/decisions.md` first.

## Out of scope

Stages, long text, the compare view, panels from plugins, the publishing pack, UI changes, hosted mode. Don't start them.
