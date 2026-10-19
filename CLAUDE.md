# PM Cockpit

A generic, extensible AI-assisted cockpit for running projects: a core loop plus plugins. The design is in `docs/design/`,
one file per part; section "6.18" is in `06-engine.md`. Start at `docs/design/README.md`, which says what to read for each
kind of task. Always read Parts 1, 2 and 10.

**Direction (owner, 2026-10-16 and 2026-10-17; `docs/decisions.md`):** the product is becoming **Thimbleby**, a daily
assistant for anyone juggling work rather than a tool only for project managers (design 6.32, the daily steward). The
assistant inside it is called **Reginald** by default, and the person can rename it. The order of work is phase B (screens), phase S
(the daily steward), phase I (Windows and macOS installers, name and icons, nothing made-up shipped), then phase C (the
packs, starting with one plugin API release answering `docs/project/plugin-answers-34-48.md`). Until phase I renames
them, the code and docs still say PM Cockpit and `cockpit`.

The project plan is in `docs/project/` (charter, scope, risks); the order of work is `docs/project/roadmap-to-1.0.md`, and
anything it defers stays deferred. The design (version in `docs/design/README.md`) is the scope baseline: a change to scope
or design needs a one-line impact note in `docs/decisions.md` first. A decision isn't done until the design text says it:
the change that records it also edits the design section it affects, and `docs/design/CHANGES.md` lists it.

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
  schema and default), fact (data), standing rule (a rule record; `rules.yaml` is the starting set) or custom to one
  deployment (private plugin). Say which in your reply. Default to config or a rule.

## Plugins
- Plugins import only `engine.plugin_api`, declare what they provide and what they may reach in `plugin.yaml`, and namespace
  their identifiers as `<plugin>/<name>`.
- Plugins work together only through the core (design 3.9): shared core records, versioned interfaces they provide or use,
  events, and requests for another plugin's task kinds. Never by importing another plugin or reading its records directly.
  Every pack works alone; optional interfaces add features when both sides are enabled.
- Plugins change knowledge only through ops and the applier, and send only through the publisher after the PM approves the
  exact content.
- Bundled plugins ship config and data for both fictional workspaces. Industry packs live in their own repositories;
  this one holds the core, the define-your-own kit, its templates and the example plugin. The core is complete on its own.

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
- Lessons from switching providers (design 6.16); a quick fix must never undo these:
  - there is no silent default provider: never "just use the first account";
  - adding or changing an account smoke-tests every tier with the exact parameters, plus the lock-down test for agents;
  - an agent's program version is part of the account;
  - only checked accounts, or ones the person accepted unchecked, sit in a fallback chain;
  - `classify_error` is the only place that reads vendor text;
  - agents start with an allowlisted environment.

## Stack and commands
- Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff. Web: React + TypeScript with Vite and Vitest.
- `uv run pytest` (parallel by default; `-n0` for one test under a debugger) · `uv run ruff check .` · `uv run ruff format --check .` · `uv run python -m engine.selfcheck`
- Web: `npm --prefix web test` · `npm --prefix web run build` (generates the API types, type-checks) ·
  `npm --prefix web run e2e` (Playwright with axe, at the root and a nested base path; build first).
- After changing an API model, run `uv run python -m api.openapi`; the self-check fails while the schema is stale.
- After changing the plugin API (`engine/plugin_api`, the manifest, events, plugin settings, core records or ops), run
  `uv run python -m engine.plugin_guide`. `docs/plugin-guide.md` is generated from the code and is the plugin contract;
  give plugin authors names only from it, never ahead of the code.
- API routes return Pydantic models from `api/schemas.py`, never bare dicts, so the UI's types stay generated.
- Try it as a person would: `uv run cockpit init ~/cockpit-try` (no template) then `uv run cockpit serve -w ~/cockpit-try`.
  `uv run cockpit demo` is the sandbox on made-up data, for trying a plugin; never a starting point.
- Tests read names and ids from the fixtures instead of writing them out, so the specificity scan holds for tests too.

## Deployment and configuration
- The same code runs locally or hosted (design Part 11); every difference is a setting, never a check for a host in code.
- Anything a person might reasonably want different is a config key (design 4.0): settable in files, environment variables
  (`COCKPIT__<FILE>__<KEY>`), flags and profiles, and editable in the Settings panel. Hard-coding one is a bug.
- Where anything is looked up (a page, tree, query, folder, feed, field name, schedule) is config (`watch.yaml`,
  `facts.yaml`, connector settings). Code and default prompts refer to "the configured source", never "the release page".
- Never assume the app is served at the root: every route, link, cookie and asset path comes from `server.public_url` and
  `server.base_path`.
- Hosted mode refuses to start unless the deploy checks pass (design 11.5). Never weaken a check to get a deployment running.
- Restart only when necessary, and only when the person says so: a setting that everything reads at the moment of use
  applies at once (`LIVE_KEYS` in `engine/worker.py`); any other change says a restart is needed, holds new work, and
  waits for the person to choose "Restart now". The app never restarts on its own.
- The hosted end state is an organization install with roles (design 11.8), not built in 1.0. New core code never
  assumes one person: whoever acts is a person id, and screens never hard-code "the PM".
- Hosting platform names appear only in `deploy/` and docs. No user's domain, account or secret anywhere in the repository;
  examples use `example.com`.

## How the work is split
- The main session plans, designs, writes briefs and reviews. Well-specified implementation (screens, tests, docs, config,
  features with a clear brief) goes to a lower-cost subagent; the main session reviews its diff and runs the checks before
  anything is committed.
- The main session keeps work that needs judgment: design changes, the applier, ledger, undo, trust and plugin boundaries,
  and fixing what a review finds there.
- A subagent follows its brief literally, so every brief states the expected starting state (which files, records and
  functions exist) for the subagent to check before it builds on it.
- A subagent's "this can't be done" or "this needs a new op" comes back to the main session, never straight into a design
  change or a report.
- **Quality and efficiency governance is the prime directive** (owner, 2026-10-13):
  - Coding, tests, audits and docs go to Sonnet subagents wherever a brief can say what done looks like. The main
    session keeps only judgment and review.
  - While iterating, a subagent runs only the tests for what it touched. The full suites run once, before a push.

## Usage and machine load (owner, 2026-10-18 and 19)
Usage is the owner's money, and the machine is small (a few cores): overloaded runs made tests fail at random and wasted
time. These rules hold for the main session and every subagent.
- **Spend usage on judgment, not on doing.** The main session plans, briefs, reviews and decides; code, tests, docs and
  audits go to Sonnet subagents with a brief that says what done looks like. Reviews are lean: read the diff of the risky
  parts (the applier, Undo, spending, credentials, trust and plugin boundaries), spot-check the rest, run the checks.
- **Read only what's needed.** Search before reading; read the part of a file a change needs, not whole files; keep
  command output short (tail, grep); don't re-read what's already in context; don't re-derive settled facts.
- **One brief, one subagent, one worktree from the working branch** (`git worktree add <path> -b <name> <working
  branch>`, never the default branch, whose history is a stub). A brief states the starting state to check first.
- **At most two workers at a time** (the main session plus one subagent, or two subagents while the main session only
  reviews).
- **A subagent runs only the tests for what it touched**: never the full Python suite, the full web suite or the browser
  tests. The main session runs the full suites once, just before a push, one full run at a time.
- **Batch before the full run** (owner, 2026-10-19: the full run takes too long to do per change): commit each reviewed
  item locally, and run the full suites once per batch of three or four items, then push the batch. Locally the Python
  suite runs on one version (CI runs every supported one); the browser tests run when the batch touches `web/` or `api/`.
- **The browser tests run only in that one full run**, never two runs at once. If anything else might be using the
  default ports, set `PW_PORT_OFFSET`.
- **Never stop processes by a broad pattern** (`pkill -f pytest`, `pkill -f playwright`): it kills other workers' runs.
  Stop only your own process by its id.
- **Don't poll with sleep loops**; a foreground `sleep` may return at once. Run a long job in the background and wait for
  its notification.
- **Judge a run by its exit code**, not by grepping a summary line (pytest here prints none with `-q -n auto`).
- **A failure under load is re-run once on its own** before it is called real or a flake; a test that fails only under
  load is made robust, not retried until it passes.
- **After every push, check CI's result** for that commit, not only the local run; a red CI is work before anything new.
- **Every push reports the suite times**; the main session checks `uv run pytest --durations=15` and fixes or flags any
  test that got slow.
  - Tests stay fast: no sleeps, no real network, shared fixtures over new workspaces, and the cheapest level that
    proves the behavior (a unit test before an API test, an API test before a browser test).

## How work reaches the owner (review, 2026-10-12)
- The plan is `docs/project/roadmap-to-1.0.md`: one phase at a time, each ending on its exit test. One stream of work at
  a time; plugin question rounds are answered once a week, together.
- The fictional workspaces are test fixtures and the sandbox, never the owner's starting point. A real workspace starts
  from `cockpit init` with no template.
- Every default produces a visible result for a real person with no file editing and no extra command. A brief says
  what the person sees in their first five minutes, and what those minutes cost at most.
- A reported problem gets a failing test of the person's path first; then everything with the same cause is found and
  fixed in the same change, and the reply says what was checked.
- Nothing is "ready to test" until the journey tests pass. The message to the owner gives the exact commands and what
  they should see.
- Never mark a plan item done on a part of it: say what is left. "Built" means a named test exists and passes: a checked
  roadmap box or a "Built" row cites it (the self-check enforces this from phase L0).
- Nothing lives only in the conversation. Every commitment to the owner or a plugin builder ("I'll add X", "Y is next") is
  written in the same turn to the roadmap or to `docs/project/open-promises.md`. That list is shown to the session when it
  starts, resumes or comes back from a compaction (the hook in `.claude/settings.json`). Reconcile it before other work. A
  promise leaves only when its item is checked off with its test, or the owner withdraws it.
- Check against the code first: a design statement, a review finding or a reported problem is verified in the code before
  it is answered, designed around or fixed, and the reply says what the code does today.

## Before finishing any change
- Run the tests and the self-check: specificity, provider, pattern and boundary scans, config coverage, manifests, both
  fictional workspaces, the core with no packs enabled, root and nested base paths, deploy checks, web build.
- A change to `web/` or `api/` also runs the browser tests (`npm --prefix web run e2e`) before it is pushed: CI runs them on
  every push, and a red run notifies the owner. Push at verified points, not after every small commit.
- New config keys have a schema entry, a default, a description and demo values in both workspaces.
- No new specific in code; if a scan flags one, move it to config or data, never add it to an allowlist to pass.

## Data and safety model
- SQLite is the system of record; every applied op is written to the ledger in the same transaction; `data/` is a readable
  export that `cockpit import` loads back (and `cockpit restore --as-of`, designed, not yet built;
  `cockpit restore --backup` makes a workspace from a whole backup), and the round trip is tested
  (design 5.0). The running engine never reads `data/`. Writes state the record versions they read.
- Records refer to people, teams and projects by id; names live on their own record and are rendered (design 5.1, 6.11).
- Every op has a tier: data, outbound or system. System ops from an input or the assistant's own initiative never apply
  automatically; the PM confirms them. System ops from the PM's own note apply at once with a read-back (applies to, doesn't change,
  overlaps with, dry-run count) and Undo, unless they contradict an existing rule or setting, which waits for the PM (design
  6.7, 12.2). Untrusted content is marked in packets and never becomes a rule, recipient or source on its own.
- Packets put stable parts first (instructions, glossary, rules, lessons, open items) and the request last (design 6.6).
- Claims carry evidence: the exact words from the cited source, which must be there (design 6.7). Drafts (prose the person
  reviews) are not claims; they stay marked unreviewed until approved, and checkable facts inside them still need evidence. One input per AI call.
  Anything derived from untrusted content stays marked untrusted, and lessons from inputs wait for the PM (design 6.6, 6.22).
  Escalate to a stronger model on check failures, never on a model's self-reported confidence.
- Lints that still fail after one return are held for the PM when the item will reach another person. A wording lint on an
  item that stays internal only warns, with no return round.
- Checks are invariants (always refuse, not configurable) or lints (severity in `config/checks.yaml`). Don't make a fuzzy check
  an invariant, and never lower an invariant.
- Local mode listens only on loopback, and checks `Host` and `Origin` on every request (design 12.1).
- Keep makes the person the author of the restatement shown. Raw outside text enters a packet only as evidence marked "from
  outside", never as guidance (12.8).
- Imported lessons, a pack's guidance and seed lessons are marked by origin. Only the person's own Keep, or their own signed
  export, makes guidance active.
- Forgetting a person and retention reach knowledge records, the knowledge log and private evaluation cases; forgetting is a
  recorded redaction (5.2, 12.4).
- Notification targets get counts, not content, unless a target is allowed for the data level (7.19).

## UI rules (design Part 7)
- Today is the home; panels are filtered views. One primary action per row, the rest in its menu.
- When a screen, step or form opens, the cursor is in its first main field (owner); only a screen with no field puts it
  on its heading. Shortcut keys never fire while the cursor is in a field.
- A field with a known set of values is a list to pick from, never a box to type in (owner): time zones, people,
  projects, value lists, accounts, models, folders. A text setting names its list with `json_schema_extra={"choices": …}`.
- Reversible actions act at once with an undo toast; only send, publish, post and spending above the configured amount confirm.
- No hard-coded user-facing text: everything comes from the wording sheet and config. No internal terms on screen.
- Keyboard and phone both work; WCAG 2.2 AA; status never by color alone.
- No screen is ever wider than the window (owner): no sideways scroll bar at any window width; columns wrap, stack or
  shrink instead. A browser test checks every main screen at several widths.
- Never render raw HTML; links from untrusted content show their real domain. The API client is generated from OpenAPI.

## Not built yet: don't call it or assume it
The rules below describe the target. These parts don't exist in the code yet, so never call them, and never skip a check
because one of them "handles it". Remove a line in the change that builds it.
- The scope resolver (design 6.18; phase E): nothing enforces scope today.
- Fact lookups (6.19; phase C4): facts are only recorded, never looked up.
- Read-backs and the rules review (6.7, 6.21; phase E).
- The publisher and channels other than Copy (6.3, 6.12): mail and calendar acts in phase S1b, the file channel in C4.
- `record.rename` (6.7): ids make most renames unnecessary, but there is no general rename op.
- The governor: stale sweeps, outage handling, point-in-time restore (6.13; phase E).

## Product rules that shape every feature
- The assistant drafts; the human approves everything outward. Nothing publishes, sends or posts without the PM approving
  that exact content.
- The AI's only write path is a changeset validated by the applier.
- The assistant doesn't repeat a corrected mistake: every correction proposes one piece of learning, every run reads the
  knowledge that applies to it, and the repeat-correction rate is watched (design 6.22, 6.20). New work keeps the loop
  whole:
  - every AI task kind, core or plugin, gets the knowledge section and writes its knowledge log; from L-core, a task kind
    without them fails the self-check;
  - every way a person can change, undo, reject or redo the assistant's work records a signal; a new button that edits the
    assistant's output without one is a bug;
  - a wrong behavior of the assistant gets a fixture, not only a code test: a learning pair (the mistake and the corrected
    later case) for learning, or a golden-set case for extraction.
- One row per thing in the UI; lists, not run-on lines; labels in plain words; the model's name never shown.
- AI work that costs real money is the person's choice: estimate first, ask above the configured amount, budgets per task kind
  and per record (design 6.16).
- Every action names at least one person: owners are a list of person ids (optional team each), shown in the owner format.
  An action without a known owner is held for "Pick an owner".
- Every waiting state shows why and until when. Runner errors are classified from the runner's exit code and error stream,
  never from model output. A correction is checked against the data before anything changes.
- Questions are written for their reader and link only what the reader can open; a decision goes to whoever decides, the PM
  when nobody is named (design 6.8).
- Scope is enforced, not suggested (design 6.18): only the tracked area gets actions and detailed questions. Other areas are
  observed; at most one impact question goes to that area's contact. Scope decisions come from the scope resolver only.
- Facts a configured source holds (releases, schedule dates) are looked up, never asked (design 6.19); none found means TBD.
- Ids never repeat. A rename is one op that updates every reference. The product never changes its own code: a request no op can do becomes a
  report the PM sends to the maintainers (design 6.13). Developing the product happens in this repository, outside any install.
- Rules before AI; never let two versions of a change race; saves merge, never clobber; recover after sleep and outages.
- No silent stops: anything that stops the assistant's work (a restart waiting, a provider paused, a run that keeps failing)
  is a Today line, not only a status chip.
- Today shows only what the person does, each line starting with the verb. Status and progress never go there.
- A nudge isn't completion: "Followed up" keeps the action open, and finished work is credited to its owner, with who
  reported it.
- Values written to an outside system are in its canonical form, and a publish leaves no remaining difference.
- Evaluation cases carry their received date and starting records, and score extra ops by default. Relaxing `exact` needs
  a comment saying why.

## Demo data
- Only the two fictional workspaces. No real names, companies, systems or URLs anywhere in the repository.
