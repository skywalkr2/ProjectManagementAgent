# Part 2. Architecture

## 2.1 Layers

```
+------------------------------------------------------------------+
| UI (React)        shell, Today, core screens, panels plugins     |
|                   declare                                        |
+------------------------------------------------------------------+
| API (Python)      core endpoints; the UI's types come from them  |
+------------------------------------------------------------------+
| Core engine       records, watchers, triage, dispatcher, applier,|
|  (generic)        questions, actions, names, today, scheduler,   |
|                   events, sign-ins, plugin host                  |
+------------------------------------------------------------------+
| Extension points  each a registry with a typed interface:        |
|                   record types, ops, validators, lints, stages,  |
|                   task kinds, person actions, file kinds, text   |
|                   and working-copy formats, connectors, sign-ins,|
|                   panels, Today lines, jobs, interfaces, events  |
+------------------------------------------------------------------+
| Plugins           bundled (the kit, an example) | add-ons        |
|                   installed from the Add-ons screen | private    |
|                   plugins inside one workspace                   |
+------------------------------------------------------------------+
| Workspace         cockpit.db (records, ledger, jobs)             |
|                   config/  sources/  prompts/  plugins/          |
|                   plugin-data/  data/ (readable export)          |
+------------------------------------------------------------------+
```

The renderer and the publisher (6.3) are part of the design and not yet built.

- **Core engine:** knows about projects, records, changes, changesets, drafts, questions, actions, people and diffs as concepts.
  Knows nothing about any organization, domain or outside service.
- **Extension points:** the only way to add behavior. Each is a registry with a typed interface in `engine.plugin_api` (3.3).
- **Plugins:** register components at extension points. The core never imports a plugin by name.
- **Workspace:** one folder per deployment: a database for records and the ledger (5.0), config and a readable export in
  its own git repository, so every change has history.
- **AI providers:** any vendor's model, as a command-line agent or an API, through one provider-neutral contract (6.16). The
  adapters are a registry inside the core (`engine/ai/adapters/`); a new vendor is a new adapter plus config. Opening adapters
  to plugins is not yet done (3.3). Vendor and model names appear only in adapters and config.

## 2.2 Repository layout

```
engine/                 the core (Python package `engine`)
  plugin_api/           the versioned interfaces plugins code against, and testing.py, the kit for plugin tests (3.13)
  ai/                   the provider layer; ai/adapters/ holds the AI vendor adapters
  connectors/           the open-protocol sources: folder, feed, calendar (ICS), mailbox (IMAP), and a fake one
  storage/              the database, ledger, export and import, the lease
  playbook/             the core playbook (3.8)
  guide/                the user guide that asking the assistant reads (6.25)
  defaults/             values the core ships, such as its value lists
  selfcheck/            scans and checks, run as `python -m engine.selfcheck`
api/                    HTTP API over the engine
web/                    React app
  src/shell/            the sidebar, header, bottom bar and setup line
  src/ui/               shared components: buttons, rows, panels, drawers, pills
  src/theme/            design tokens (CSS variables) and the rules that check their use
  src/components/       the screens, in the shell
  src/wording/          the wording sheet: every sentence a screen shows
  e2e/                  Playwright tests with axe
plugins/                bundled plugins (the core's own, not packs)
  kit/                  the define-your-own kit (3.10)
  example/              a complete, runnable example plugin for plugin authors
templates/              starting templates for the kit
catalog/                data the app ships: AI services by name, facts about this build
workspaces/
  demo-a/               fictional workplace: a test fixture and the sandbox, never a person's starting point
  demo-b/               fictional small imprint: a test fixture and the sandbox, never a person's starting point
deploy/                 install and update scripts, and an example catalog feed; hosting recipes (Part 11) come with them
tests/
reviews/                outside reviews kept for reference, such as the UI and UX review
docs/
  design/               this design, one file per part (README.md is the index); CHANGES.md lists what changed
  decisions.md          product-level decisions, dated
  plugin-guide.md       the plugin contract, generated from the code (3.13)
  plugin-api-0.x.md     what each plugin API version changed
  plugin-kickoff-template.md  the brief every plugin repository starts from (3.15)
  project/              charter, scope, risks, the roadmap and its reviews
```

Packs are not in this repository. They live in their own repositories and install from the Add-ons screen (1.8, 3.11). The
package built from this repository carries the starting templates, the AI service list, the built screens and the two
fictional workspaces in `engine/_shipped/`, copied there by the build, so a person who installs it needs no checkout and no
Node.

A workspace looks like this:

```
<workspace>/
  cockpit.db            the database: records, ledger, jobs, leases (5.0); not committed
  config/               YAML settings (Part 4); config/plugins/<plugin>.yaml for each enabled plugin
  data/                 readable JSON export of the records, committed to git; import source for fixtures
  sources/              every input's text, by content hash
  files/  texts/        added files and every version of long text, stored once by hash
  plugin-data/          data files for plugins, layered over what a plugin ships (3.3)
  prompts/              prompt templates; files here override the defaults that the core and plugins ship
  plugins/              private plugins for this workspace only
  .cockpit/             files that stay on this computer: the install token, kept secrets, where programs are found
  outbox/  evals/  docs/   made when first used: changesets written by AI runs in agent mode; private evaluation
                        cases built from the PM's corrections (6.20), which never leave the workspace; and
                        decisions.md, why this deployment behaves the way it does
```

A workspace may also write a readable layout of its records, one folder per project, to a synced folder outside the
workspace, so two computers can share it (5.0).

Real workspaces live **outside this repository**, each in its own git repository; the engine takes the path from `--workspace`
or the `COCKPIT_WORKSPACE` environment variable. `cockpit init` makes a workspace: the database, the config files with their
defaults, and the git repository. Only the two fictional workspaces are committed here, as fixtures; tests copy them to a
temporary folder before running so the fixtures never change. The `.gitignore` admits nothing else under `workspaces/`.

## 2.3 Where things go (decide this for every new requirement)

| The requirement is about... | It goes in... | Example |
|---|---|---|
| How a generic concept works | core code + its docstring | "the applier backs up every file before applying" |
| A source that speaks an open protocol | the core's connectors, set in `config/watch.yaml` | a folder, a feed, a calendar by its address, a mailbox over IMAP |
| A new kind of input or output | a connector (or, once built, a channel) in a plugin | a wiki, a tracker, a named mail service, a blog, a social network |
| A new kind of thing to track | a record type in a plugin or pack; the kit for one defined on screens (3.10) | a manuscript with word count and submission state |
| A kind of work a person defines with no code | the define-your-own kit's settings, saved as a template | a "client request" with fields and stages |
| A whole kind of work | a pack, an add-on in its own repository | planning and schedules; writing a book; publishing; workplace status pages |
| Logic only one organization or person needs | a private plugin in that workspace's `plugins/` | a page layout one program insists on |
| Who someone is, their team, role, how to reach them | people records (exported to `data/people.json`) | "Jane Doe leads delivery for the billing teams" |
| Who answers which kind of question | `config/routing.yaml` | "requirements questions go to the project's product owner" |
| Where a kind of fact is looked up instead of asked | `config/facts.yaml` | "an item's release comes from the tracker; its date from the schedule page" |
| What the portfolio tracks vs only observes | `config/scope.yaml` | "only items owned by these teams get follow-ups" |
| Which sources to watch, through which connector | `config/watch.yaml` | a page id, a tracker query, a folder path, a feed |
| Which changes close without the AI | the `triage:` list in `config/watch.yaml`, beside the sources it applies to | "diff only touches rows of other owners" |
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
| Which planning records and risk fields are used | the project management pack's settings (3.1, 1.8) | a personal workspace without assumptions |
| How strict each check is | `config/checks.yaml` | blocked wording sends a changeset back instead of refusing it |
| Packaging for a hosting platform | a recipe in `deploy/<target>/` | a container plus a reverse proxy |
| Which AI provider and model does which task | `config/ai.yaml` | "routine tasks on provider A's small model" |
| A plugin's settings | `config/plugins/<plugin>.yaml` | the reference pack's portfolio grouping label |
| A set of values a field takes (a status, a priority, a plugin's categories) | a value list: records, with defaults from the core and from plugins, changed by the person | a project's status values |
| What a screen calls a plugin's own kinds | the plugin's wording file; the workspace's `ui.wording` overrides it | the heading for a kind of record on Stages |
| Prompts and instructions the AI gets | `prompts/` templates | the changeset instructions, the update-writing style |
| Standing instructions the PM states in passing | `config/rules.yaml` (read by the AI runs they apply to) | "don't ask the program manager to confirm program dates" |
| Why a deployment behaves a certain way | the workspace's `docs/decisions.md` | dated entry: what, who decided, why |
| Why the product is built a certain way | this repository's `docs/decisions.md` | dated entry: what, who decided, why |

If a requirement doesn't fit a row, the answer is a new config key with a schema and a default, a plugin, or a new generic
extension point. It is never an `if team == "X"` or an `if plugin == "Y"` in the core.

## 2.4 Technology choices

- **Python 3.12+** for the engine and API, managed with **uv**, built into a package with Hatch. **FastAPI** (served by
  uvicorn) for the HTTP API; **httpx** for the core's web client. **Pydantic v2** models for config, records, ops and plugin
  manifests; JSON Schema is generated from the models, so the AI's output schema and the validator never disagree. **PyYAML**
  for config. **pytest** for tests, **ruff** for lint and format.
- **React + TypeScript**, built with **Vite**. **TanStack Query** holds server state, and server-sent events from the engine's
  event bus say which queries to refresh, so lists update without polling. **React Aria Components** give accessible menus,
  dialogs, listboxes and toasts. The API client's types are generated from the OpenAPI schema (`openapi-typescript`), so a
  changed API model fails the web build. Views are addressed by the fragment of the address (`#today`, `#work/changed`), so a
  link works under any base path.
- **Styling** is CSS modules over CSS variables: design tokens in three layers (primitives, roles, components) live in one
  file, and a **stylelint** rule set refuses a size, gap or radius that is not from the token scale (7.12). Brand color and
  theme come from config (7.11). The UI gets its panel definitions from the API.
- **Tests:** Vitest with Testing Library for the screens; **Playwright with axe** for whole journeys and accessibility, at the
  root and at a nested base path. The web build is `npm run build` (style rules, generated types, type check, bundle).
- **Plugins** are Python packages. Installed ones are found by the entry-point group `pm_cockpit.plugins`; bundled and private
  ones by scanning `plugins/` and `<workspace>/plugins/`. A plugin in the workspace's `plugins/` wins over an installed one of
  the same name, with a note on its status. Add-ons install from the Add-ons screen (3.11).
- **Storage:** SQLite as the system of record, with a ledger and a readable JSON export committed to git (5.0), behind a
  repository layer; Postgres later for multi-user, object storage optional for sources (4.15).
- **Runs locally or hosted** from the same code (Part 11). The UI build works under any base path without rebuilding.

The reasons are recorded in `docs/decisions.md`.

## 2.5 Where a person starts

The two fictional workspaces are test fixtures and the sandbox. They exist to cover every shape of every setting, which is the
opposite of a starter's job, so they are never a person's starting point (decisions, 2026-10-12).

- **A real workspace starts from `cockpit init` with no template.** It holds the config defaults and no demo records. It is
  meant to hold no example AI account and no source that shows a problem; the self-check that proves it is planned and not yet
  built. The guided first run (Part 7) takes the person from there to a first result.
- **A template is a choice, not a default.** The first run offers the kit's starting templates (3.10); applying one adds item
  types to a workspace and is never needed to get a result.
- **The sandbox is `cockpit demo`.** It makes a demo workspace of made-up data apart from real work, serves it with screens
  that say it is a demo, and is how a plugin is tried (`cockpit demo --plugin`, 3.13). A demo's stand-in AI is replaced by
  the person's own account as soon as one is added.
- **Every default produces a visible result** for a real person with no file editing and no extra command (1.7).

## 2.6 Restarts and live settings

The app restarts only when the person chooses Restart now. It never restarts on its own (decisions, 2026-10-11).

- **Live settings apply at once.** Settings that everything reads at the moment of use need no restart: AI accounts, tiers
  and budgets; who the person is, the workspace's and the assistant's names; the screens' wording and shortcuts; the accounts
  counted as ours; backup targets and timing; and the watched sources. They are the `LIVE_KEYS` in `engine/worker.py`.
- **Anything else waits.** When saved settings, an add-on turned on or off, or the app's own code change in a way that needs a
  restart, the app says so, holds new AI work, and waits. The person chooses Restart now or Later. A copy that cannot start
  itself again says to close it and start it.
- **Plugins register once per start.** A plugin's registrations are fixed until the app restarts, so a change to its settings or
  to which plugins are on shows as "On after a restart" until the person restarts (3.6).
- **Old code never runs new settings,** and nothing is half-reloaded: until the restart, the plugin keeps the settings it
  registered with.
