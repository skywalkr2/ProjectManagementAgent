# PM Cockpit

A generic, configurable AI-assisted PM cockpit. The full design is in `docs/DESIGN.md`; read Parts 2, 3 and 8 before any change.

## The boundary (non-negotiable)
- Engine, API and UI code contain **no** specific person, team, organization, product, program, system, host, URL or page id.
  Those live in `workspaces/<name>/config/` and `workspaces/<name>/data/`. Truly custom logic is a plugin under `plugins/`.
- Code comments describe what the code does in general terms. They never quote a user, name a person or carry a date.
  Rationale goes in the workspace's `docs/decisions.md`.
- When a user states a rule, decide first: concept (engine), setting (config key with schema and default), fact (data),
  standing instruction (`rules.md`) or plugin. Say which in your reply. Default to config or rules.md.

## AI providers
- The product supports any AI vendor through `engine/ai/` (design 5.15). Vendor and model names appear only in adapters,
  `config/ai.yaml` and usage/evaluation reports; the rest of the code calls the provider layer with a `Task`.
- Prompts live in the workspace's `prompts/` templates, not in code.
- A new vendor is a new adapter plus config. If a feature seems to need a vendor-specific call outside an adapter, add a
  capability to the adapter interface instead.

## Before finishing any change
- Run the tests and `python -m engine.selfcheck`: specificity scan, pattern scan, config coverage, both fictional
  workspaces, web build.
- New config keys have a schema entry, a default, a description and demo values in both workspaces.
- No new specific in code; if the scan flags one, move it to config or data, never add it to an allowlist to pass.

## Product rules that shape every feature
- The assistant drafts; the human approves everything outward. Nothing publishes or sends without the PM.
- The AI's only write path is a changeset validated by the applier.
- One row per thing in the UI; lists, not run-on lines; labels in plain words; the model's name never shown.
- Owners are people ("Team (Full Name)"); names stored in full on every write path.
- Questions are written for their reader and link only what the reader can open; decisions are questions to the PM.
- Rules before AI; never let two versions of a change race; saves merge, never clobber; recover after sleep and outages.

## Demo data
- Only the two fictional workspaces. No real names, companies, systems or URLs anywhere in the repository.
