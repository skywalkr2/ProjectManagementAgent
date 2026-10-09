# PM Cockpit

A generic, extensible AI-assisted cockpit for running projects: a core loop plus plugins. The design is in `docs/design/`,
one file per part; section "6.18" is in `06-engine.md`. Start at `docs/design/README.md`, which says what to read for each
kind of task. Always read Parts 1, 2 and 10.

The project plan is in `docs/project/` (charter, scope, risks, schedule). Design 1.0 is the scope baseline: a change to scope
or design needs a one-line impact note in `docs/decisions.md` first, and during a freeze only fixes are accepted. Build in the
order of `docs/project/schedule.md`; anything it defers stays deferred.

## The boundary (non-negotiable)
- Core code (`engine/`, `api/`, `web/src/`) contains **no** specific person, team, organization, product, program, system,
  host, URL or page id, and no vendor or service name outside `engine/ai/adapters/`.
- Deployment specifics live in that deployment's workspace (`config/`, `data/`), outside this repository. Only the fictional
  `workspaces/demo-a/` and `workspaces/demo-b/` are committed.
- The core is a base. Anything that belongs to one kind of work is a plugin under `plugins/` (a pack when it bundles a whole use).
  A plugin may name the product it connects to; logic for one organization is a private plugin in that workspace's `plugins/`.
- If a plugin needs something no extension point provides, add a generic extension point to the core. Never special-case a
  plugin in the core; the core never imports from `plugins/`.
- Code comments describe what the code does in general terms. They never quote a user, name a person or carry a date.
  Rationale goes in `docs/decisions.md` (product) or the workspace's `docs/decisions.md` (deployment).
- When a user states a rule, decide first: concept (core), extension (plugin or new extension point), setting (config key with
  schema and default), fact (data), standing instruction (`rules.yaml`) or custom to one deployment (private plugin). Say which in
  your reply. Default to config or `rules.yaml`.

## Plugins
- Plugins import only `engine.plugin_api`, declare what they provide and what they may reach in `plugin.yaml`, and namespace
  their identifiers as `<plugin>/<name>`.
- Plugins change knowledge only through ops and the applier, and send only through the publisher after the PM approves the
  exact content.
- Bundled plugins ship config and data for both fictional workspaces.

## AI providers
- The product supports any AI vendor through `engine/ai/` (design 6.16). Vendor and model names appear only in adapters,
  `config/ai.yaml` and usage/evaluation reports; the rest of the code calls the provider layer with an `AiTask`.
- Prompts live in `prompts/` templates (defaults shipped by the core and plugins, overridden by the workspace), not in code.
- Good practice for a kind of work lives in playbooks (design 3.8): the core's for project support, each pack's for its field.
  Not in code, not in prompt templates (those say how a task is done mechanically). The workspace's rules override playbook
  entries by id. This is an assistant for the person running projects, not a methodology tool: build in what happens every
  day; leave the rest to "ask the assistant" (design 6.25).
- The PM brings their own accounts: native vendor APIs, any OpenAI-compatible endpoint (many vendors, local servers),
  aggregators such as OpenRouter, command-line agents. Capabilities and prices are per model, from the adapter's `models()`;
  never hard-code a model id or assume a capability from a vendor's name.
- A new vendor is a new adapter plus config. If a feature seems to need a vendor-specific call outside an adapter, add a
  capability to the adapter interface instead.

## Stack and commands
- Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff. Web: React + TypeScript with Vite and Vitest.
- `uv run pytest` · `uv run ruff check .` · `uv run python -m engine.selfcheck` · `npm --prefix web test` ·
  `npm --prefix web run build`
- These exist from build milestone 1 (design 13.1). Until then, say which checks you could not run.

## Deployment and configuration
- The same code runs locally or hosted (design Part 11); every difference is a setting, never a check for a host in code.
- Anything a person might reasonably want different is a config key (design 4.0): settable in files, environment variables
  (`COCKPIT__<FILE>__<KEY>`), flags and profiles, and editable in the Settings panel. Hard-coding one is a bug.
- Where anything is looked up (a page, tree, query, folder, feed, field name, schedule) is config (`watch.yaml`,
  `facts.yaml`, connector settings). Code and default prompts refer to "the configured source", never "the release page".
- Never assume the app is served at the root: every route, link, cookie and asset path comes from `server.public_url` and
  `server.base_path`.
- Hosted mode refuses to start unless the deploy checks pass (design 11.5). Never weaken a check to get a deployment running.
- Hosting platform names appear only in `deploy/` and docs. No user's domain, account or secret anywhere in the repository;
  examples use `example.com`.

## Before finishing any change
- Run the tests and the self-check: specificity, provider, pattern and boundary scans, config coverage, manifests, both
  fictional workspaces, the core with no packs enabled, root and nested base paths, deploy checks, web build.
- New config keys have a schema entry, a default, a description and demo values in both workspaces.
- No new specific in code; if a scan flags one, move it to config or data, never add it to an allowlist to pass.

## Data and safety model
- SQLite is the system of record; every applied op is written to the ledger in the same transaction; `data/` is a readable
  export that `cockpit import` and `cockpit restore` load back, and the round trip is tested (design 5.0). The running engine
  never reads `data/`. Writes state the record versions they read.
- Records refer to people, teams and projects by id; names live on their own record and are rendered (design 5.1, 6.11).
- Every op has a tier: data, outbound or system. System ops from an input or the assistant's own initiative never apply
  automatically; the PM confirms them. System ops from the PM's own note apply at once with a read-back (applies to, doesn't change,
  overlaps with, dry-run count) and Undo, unless they contradict an existing rule or setting, which waits for the PM (design
  6.7, 12.2). Untrusted content is marked in packets and never becomes a rule, recipient or source on its own.
- Packets put stable parts first (instructions, glossary, rules, lessons, open items) and the request last (design 6.6).
- Lints that still fail after one return are held for the PM when the item will reach another person, and only warn when it
  stays internal.
- Checks are invariants (always refuse, not configurable) or lints (severity in `config/checks.yaml`). Don't make a fuzzy check
  an invariant, and never lower an invariant.

## Product rules that shape every feature
- The assistant drafts; the human approves everything outward. Nothing publishes, sends or posts without the PM approving
  that exact content.
- The AI's only write path is a changeset validated by the applier.
- One row per thing in the UI; lists, not run-on lines; labels in plain words; the model's name never shown.
- Every action names at least one person: owners are a list of person ids (optional team each), shown in the owner format.
  An action without a known owner is held for "Pick an owner".
- Every waiting state shows why and until when. Runner errors are classified from the runner's exit code and error stream,
  never from model output. A correction is checked against the data before anything changes.
- Questions are written for their reader and link only what the reader can open; decisions are questions to the PM.
- Scope is enforced, not suggested (design 6.18): only the tracked area gets actions and detailed questions. Other areas are
  observed; at most one impact question goes to that area's contact. Scope decisions come from the scope resolver only.
- Facts a configured source holds (releases, schedule dates) are looked up, never asked (design 6.19); none found means TBD.
- Ids never repeat. A rename is one op that updates every reference. The product never changes its own code: a request no op can do becomes a
  report the PM sends to the maintainers (design 6.13). Developing the product happens in this repository, outside any install.
- Rules before AI; never let two versions of a change race; saves merge, never clobber; recover after sleep and outages.

## Demo data
- Only the two fictional workspaces. No real names, companies, systems or URLs anywhere in the repository.
