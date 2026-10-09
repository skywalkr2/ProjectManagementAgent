# Part 2. Architecture

## 2.1 Layers

```
+------------------------------------------------------------------+
| UI (React)        shell, core panels, panels plugins declare     |
+------------------------------------------------------------------+
| API (Python)      core endpoints, plus routes plugins register   |
+------------------------------------------------------------------+
| Core engine       records, watchers, triage, dispatcher, applier,|
|  (generic)        questions, actions, names, renderer, publisher,|
|                   governor, scheduler, today, events, plugin host|
+------------------------------------------------------------------+
| Extension points  each a registry with a typed interface:        |
|                   connectors, channels, record types, ops,       |
|                   triage matchers, AI adapters, AI task kinds,   |
|                   renderers, lookups, panels, jobs, events, ...  |
+------------------------------------------------------------------+
| Plugins           bundled (generic) | installed packages |       |
|                   private plugins inside one workspace           |
+------------------------------------------------------------------+
| Workspace         cockpit.db (records, ledger, jobs)             |
|                   config/  sources/  prompts/  plugins/  outbox/ |
|                   data/ (readable export)  docs/decisions.md     |
+------------------------------------------------------------------+
```

- **Core engine:** knows about projects, records, changes, changesets, drafts, questions, actions, people and diffs as concepts.
  Knows nothing about any organization, domain or outside service.
- **Extension points:** the only way to add behavior. Each is a registry with a typed interface in `engine.plugin_api` (3.3).
- **Plugins:** register components at extension points. The core never imports a plugin by name.
- **Workspace:** one folder per deployment: a database for records and the ledger (5.0), config and a readable export in
  its own git repository, so every change has history.
- **AI providers:** any vendor's model, as a command-line agent or an API, through one provider-neutral contract (6.16). AI
  adapters are a kind of plugin; vendor and model names appear only in adapters and config.

## 2.2 Repository layout

```
engine/                 the core (Python package `engine`)
  plugin_api/           the stable, versioned interfaces plugins code against
  ai/                   the provider layer; ai/adapters/ holds the AI vendor adapters
  selfcheck/            scans and checks, run as `python -m engine.selfcheck`
api/                    HTTP API over the engine
web/                    React app: shell, core panels, panel registry
plugins/                bundled plugins, each generic for its domain
  fake/                 fixture-backed connectors and channels
  publishing/           the first pack in real use (9.6)
  workplace-pm/         the reference pack (Part 9), built on fictional data
workspaces/
  demo-a/               fictional workplace (committed fixture for the workplace pack)
  demo-b/               fictional small imprint (committed fixture for the publishing pack)
deploy/                 packaging and deployment recipes (Part 11)
  container/            the container image every hosted recipe builds on
  <target>/             one folder per hosting target; may name that host, never a user's domain
tests/
docs/
  design/               this design, one file per part (README.md is the index); CHANGES.md since the first version
  decisions.md          product-level decisions, dated
```

A workspace looks like this:

```
<workspace>/
  cockpit.db            the database: records, ledger, jobs, leases (5.0); not committed
  config/               YAML settings (Part 4); config/plugins/<plugin>.yaml for each enabled plugin
  data/                 readable JSON export of the records, committed to git; import source for fixtures
  sources/              every input's text, by content hash
  prompts/              prompt templates; files here override the defaults that the core and plugins ship
  plugins/              private plugins for this workspace only
  outbox/               changesets written by AI runs in agent mode
  evals/                private evaluation cases built from the PM's corrections (6.20); never leave the workspace
  docs/decisions.md     why this deployment behaves the way it does
```

Real workspaces live **outside this repository**, each in its own git repository; the engine takes the path from `--workspace`
or the `COCKPIT_WORKSPACE` environment variable and initializes the database and git there on first run. Only the two fictional workspaces are
committed here, as fixtures; tests copy them to a temporary folder before running so the fixtures never change. The
`.gitignore` admits nothing else under `workspaces/`.

## 2.3 Where things go (decide this for every new requirement)

| The requirement is about... | It goes in... | Example |
|---|---|---|
| How a generic concept works | core code + its docstring | "the applier backs up every file before applying" |
| A new kind of input or output | a connector or channel plugin | a mailbox, a calendar feed, a blog, a social network |
| A new kind of thing to track, or fields on a core record | a record type in a plugin or pack | a manuscript with word count and submission state |
| A whole kind of work | a pack | workplace status pages; publishing support |
| Logic only one organization or person needs | a private plugin in that workspace's `plugins/` | a page layout one program insists on |
| Who someone is, their team, role, how to reach them | people records (exported to `data/people.json`) | "Jane Doe leads delivery for the billing teams" |
| Who answers which kind of question | `config/routing.yaml` | "requirements questions go to the project's product owner" |
| Where a kind of fact is looked up instead of asked | `config/facts.yaml` | "an item's release comes from the tracker; its date from the schedule page" |
| What the portfolio tracks vs only observes | `config/scope.yaml` | "only items owned by these teams get follow-ups" |
| Which sources to watch, through which connector | `config/watch.yaml` | a page id, a tracker query, a folder path, a feed |
| Which changes close without the AI | `config/triage.yaml` | "diff only touches rows of other owners" |
| When jobs run | `config/schedule.yaml` | "batches at 9, 11, 1, 3, 5 on weekdays" |
| Words and spellings, the assistant's name, locale | `config/language.yaml` | blocked phrases on shared pages, US spelling |
| Output layout: sections, columns, sort orders | `config/render.yaml` + templates | "Action Items: Project, Notes, Owner, Due, Status" |
| Status labels and their colors | `config/status.yaml` | "At Risk" maps to amber |
| Calendar meaning ("this week", non-working days) | `config/calendar.yaml` | week ends Friday; a team's holidays |
| Tab order, hidden panels, quick links, branding | `config/ui.yaml` | hide the Portfolio tab in a personal workspace |
| Where and how the app runs: mode, address, base path | `config/server.yaml` | hosted at `https://example.com/admin` |
| How people sign in | `config/auth.yaml` | password with a one-time code, or a sign-in provider |
| Where data is stored and backed up, and for how long | `config/storage.yaml` | export pushed to a private git remote; raw emails kept 90 days |
| Who may see each destination, and which sources are restricted to whom | `config/workspace.yaml` `audiences`, `restrictions` | a page locked to program leads may carry restricted notes |
| Which project owns code or tools the PM uses but this product doesn't | `config/code_owners.yaml` | dashboard requests are handed to its owner |
| Good practice for a kind of work (how to do it well) | a playbook in the core or the pack (3.8) | how to write a follow-up; launch lead times |
| Which playbook entries are on, off or replaced | `config/playbooks.yaml` | switch off the meeting prep checklist |
| Which project management records and risk fields are used | `config/raid.yaml` | a personal workspace without assumptions |
| How strict each check is | `config/checks.yaml` | blocked wording sends a changeset back instead of refusing it |
| Packaging for a hosting platform | a recipe in `deploy/<target>/` | a container plus a reverse proxy |
| Which AI provider and model does which task | `config/ai.yaml` | "routine tasks on provider A's small model" |
| A plugin's settings | `config/plugins/<plugin>.yaml` | the reference pack's portfolio grouping label |
| Prompts and instructions the AI gets | `prompts/` templates | the changeset instructions, the update-writing style |
| Standing instructions the PM states in passing | `config/rules.yaml` (read by the AI runs they apply to) | "don't ask the program manager to confirm program dates" |
| Why a deployment behaves a certain way | the workspace's `docs/decisions.md` | dated entry: what, who decided, why |
| Why the product is built a certain way | this repository's `docs/decisions.md` | dated entry: what, who decided, why |

If a requirement doesn't fit a row, the answer is a new config key with a schema and a default, a plugin, or a new generic
extension point. It is never an `if team == "X"` or an `if plugin == "Y"` in the core.

## 2.4 Technology choices

- **Python 3.12+** for the engine and API, managed with **uv**. **FastAPI** for the HTTP API. **Pydantic v2** models for config,
  records, ops and plugin manifests; JSON Schema is generated from the models, so the AI's output schema and the validator
  never disagree. **pytest** for tests, **ruff** for lint and format.
- **React + TypeScript**, built with **Vite**, tested with **Vitest**. The UI gets its panel definitions from the API.
- **Plugins** are Python packages. Installed ones are found by the entry-point group `pm_cockpit.plugins`; bundled and private
  ones by scanning `plugins/` and `<workspace>/plugins/`.
- **Storage:** SQLite as the system of record, with a ledger and a readable JSON export committed to git (5.0), behind a
  repository layer; Postgres later for multi-user, object storage optional for sources (4.15).
- **Runs locally or hosted** from the same code (Part 11). One container image serves every hosted target; the UI build
  works under any base path without rebuilding.

The reasons are recorded in `docs/decisions.md`.
