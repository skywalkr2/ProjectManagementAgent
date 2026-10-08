# PM Cockpit: product design for a generic, extensible build

A clean-room design, written from scratch from experience running an AI-assisted PM workflow. It contains no code, names,
company systems or data from any real deployment. All examples are fictional. The repository's `CLAUDE.md` is the short
version of this document for coding agents.

**Two rules above all others:**

1. **The core is generic.** Everything about a particular organization or person (its people, teams, programs, systems, URLs,
   routing, vocabulary, wording rules, schedules) lives in configuration and data, never in code or code comments.
2. **The core is a base, not the whole product.** It provides the loop, the safety rules and the extension points. Anything that
   belongs to one kind of work (a workplace status-page routine, a publishing calendar, a social media account) is a plugin.

**Where this design came from.** It grew out of one use: a program manager supporting a technical leader at a large
organization, with status on wiki pages and work in an issue tracker. That use is kept, fully specified, as the **reference
pack** (Part 9) and is the first thing built on the core. It shows what the core must support; it does not set the product's
edges. Other uses (publishing support, personal projects, social media) are plugins on the same core (3.7).

**How to read this document.** Part 1 says what the product is and where its edges are. Parts 2 to 4 are the architecture, the
plugin system and the configuration every change must respect. Parts 5 to 7 specify the core. Part 8 is the product rules,
Part 9 the reference pack, Part 10 the guardrails against specifics in code, Part 11 deployment (local or hosted), Part 12
security, Part 13 the build plan.

### Terms

| Term | Meaning |
|---|---|
| PM | The person the cockpit works for: whoever runs the projects in a workspace (a program manager, an author, anyone) |
| Workspace | One deployment: one PM's config, data, sources, prompts and private plugins, in its own git repository |
| Record | A stored thing the cockpit tracks: a project, an action, a question, or a plugin's own type (a manuscript, a post) |
| Source | An input, saved as text: a page version, a tracker item, a pasted note, an email, a file |
| Change | A detected difference in a source that may need work |
| Request | A unit of work queued for the assistant (process a change, record an answer, write an update) |
| Changeset | The assistant's only output: a structured list of typed ops, validated and applied by the applier |
| Op | One typed operation in a changeset (`record.set`, `action.add`, `question.add`, or a plugin's own) |
| Draft | Content waiting to go out through a channel: a page version, a message, a post |
| Connector | A plugin component that brings inputs in (a wiki, a tracker, a mailbox, a feed) |
| Channel | A plugin component that takes approved drafts out (a wiki page, an email, a blog, a social network) |
| Plugin | A package that registers components at the core's extension points |
| Pack | A plugin that bundles record types, ops, templates, prompts, panels and default config for one kind of work |
| AI task | One call to the AI provider layer: a task kind, a packet, an output schema (6.16) |
| Meeting | A meeting the PM sets up or runs, with attendees and notes |

---

## Part 1. The product

### 1.1 The idea

Someone running several projects (a program manager supporting a leader, an author with books in progress, a person with side
projects) spends much of the day noticing what changed, updating the places other people read, chasing people for answers and
keeping follow-ups straight. The information is spread across sources: pages, trackers, folders, mailboxes, feeds, meetings and
chats.

The cockpit does the noticing and the drafting. It watches the sources, has an AI assistant turn each change into proposed
updates, questions and action items, and gives the PM one screen to review, correct and send out.

**The AI drafts. The human approves everything that goes out.**

### 1.2 Who it's for

- **The PM (primary user):** reviews, approves, sends, publishes. Wants one screen that says what to do today.
- **Readers:** people who read what the PM publishes (a leader reading status pages, subscribers reading a newsletter). They
  shouldn't have to confirm routine updates.
- **Contacts:** people who receive questions and action items. They never use the tool; they get paste-ready messages, or
  messages sent through a channel after the PM approves them.
- **The assistant:** an AI with a configurable display name (e.g. "Archie"). The underlying model's name never appears in
  anything a person sees.

### 1.3 The core loop

1. **Watch** sources on a schedule through connectors, plus anything the PM hands in (pasted notes, emails, screenshots, files).
2. **Triage by rules first:** configurable rules close cosmetic edits, items outside the portfolio, repeats and other known
   no-op cases before the AI sees them. Every auto-closed item stays findable with its reason and can be pulled back.
3. **Package and dispatch:** remaining items are batched into packets (the change, the related records, the open actions and
   questions, the rules) and handed to the AI provider layer.
4. **The AI writes a changeset:** a structured file of typed ops. It never edits records, pages or files directly.
5. **Check and apply:** a deterministic applier validates the changeset, normalizes it, backs up what it will touch, applies it
   and logs it. Invalid changesets go back to the AI once with the reasons before any human sees them.
6. **Review:** the PM sees each change with the AI's work nested under it and one set of buttons: Looks good, Send back, Undo.
7. **Send out:** records render into drafts for channels (a page, a message, a post). Each draft waits with a readable diff or
   preview. Nothing leaves the cockpit until the PM approves that exact content.
8. **Follow up:** questions and action items grouped by person, copied or sent as one clean message, marked sent, aged until
   answered. A pasted reply goes back to the AI, which records it and acts on it.

Every step is generic. What gets watched, what records exist, what gets drafted and where it goes are supplied by plugins and
configuration.

### 1.4 What's core and what's a plugin

| Core (always present, generic) | Extensions (plugins) |
|---|---|
| The loop: watch, triage, dispatch, apply, review, send out, follow up | Where inputs come from: wikis, trackers, mailboxes, feeds, accounts (connectors) |
| Records, changesets, the applier, undo, history | Where outputs go: pages, email, blogs, social posts (channels) |
| Questions, actions, meetings, people, the names normalizer | Kinds of things to track and extra fields on core records (record types) |
| The AI provider layer: routing, fallbacks, budgets, evaluation | Domain ops, triage matchers, AI task kinds and their prompts |
| The approval gate, diffs, the publisher | Templates and renderers for pages, posts and messages |
| Scheduler, governor, issues and the fixer | UI panels, Today lines, scheduled jobs, lookups, event handlers |
| UI shell and core panels | Vendor adapters for AI models and for outside services |
| Plugin host, config schemas, self-check | Packs: bundles of the above for one kind of work |

So the whole product runs offline on demo data, the core ships with minimal built-ins: a fake connector and fake channel backed by
fixture files, a local-folder connector, paste-in and upload, a clipboard channel (copy a message to paste anywhere) and a stub AI
adapter.

### 1.5 Not goals for the base

- **Autonomous sending.** Nothing goes out without the PM approving the exact content. A scheduled post is approved content
  that the PM scheduled; the cockpit never decides on its own to send.
- **Multi-tenant hosting.** One deployment serves one workspace. It runs on the PM's own machine or on a web host the PM
  controls (Part 11), never as a shared service holding several customers' data. Storage sits behind a repository layer so a
  multi-user build can come later without rewriting the engine.
- **Real-time collaborative editing.** One writer at a time per workspace.

---

## Part 2. Architecture

### 2.1 Layers

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
| Workspace         config/  data/  sources/  prompts/  plugins/   |
|                   outbox/  docs/decisions.md                     |
+------------------------------------------------------------------+
```

- **Core engine:** knows about projects, records, changes, changesets, drafts, questions, actions, people and diffs as concepts.
  Knows nothing about any organization, domain or outside service.
- **Extension points:** the only way to add behavior. Each is a registry with a typed interface in `engine.plugin_api` (3.3).
- **Plugins:** register components at extension points. The core never imports a plugin by name.
- **Workspace:** one folder per deployment, its own git repository, so every change has history and undo is cheap.
- **AI providers:** any vendor's model, as a command-line agent or an API, through one provider-neutral contract (6.16). AI
  adapters are a kind of plugin; vendor and model names appear only in adapters and config.

### 2.2 Repository layout

```
engine/                 the core (Python package `engine`)
  plugin_api/           the stable, versioned interfaces plugins code against
  ai/                   the provider layer; ai/adapters/ holds the AI vendor adapters
  selfcheck/            scans and checks, run as `python -m engine.selfcheck`
api/                    HTTP API over the engine
web/                    React app: shell, core panels, panel registry
plugins/                bundled plugins, each generic for its domain
  fake/                 fixture-backed connectors and channels
  workplace-pm/         the reference pack (Part 9)
  personal-projects/    a small second pack that proves the extension points
workspaces/
  demo-a/               fictional workspace (committed fixture)
  demo-b/               a second, different fictional workspace
deploy/                 packaging and deployment recipes (Part 11)
  container/            the container image every hosted recipe builds on
  <target>/             one folder per hosting target; may name that host, never a user's domain
tests/
docs/
  DESIGN.md             this document
  decisions.md          product-level decisions, dated
```

A workspace looks like this:

```
<workspace>/
  config/               YAML settings (Part 4); config/plugins/<plugin>.yaml for each enabled plugin
  data/                 records; data/<plugin>/ for a plugin's own record types
  sources/              every input, saved as text
  prompts/              prompt templates; files here override the defaults that the core and plugins ship
  plugins/              private plugins for this workspace only
  outbox/               changesets written by AI runs
  docs/decisions.md     why this deployment behaves the way it does
```

Real workspaces live **outside this repository**, each in its own git repository; the engine takes the path from `--workspace`
or the `COCKPIT_WORKSPACE` environment variable and initializes git there on first run. Only the two fictional workspaces are
committed here, as fixtures; tests copy them to a temporary folder before running so the fixtures never change. The
`.gitignore` admits nothing else under `workspaces/`.

### 2.3 Where things go (decide this for every new requirement)

| The requirement is about... | It goes in... | Example |
|---|---|---|
| How a generic concept works | core code + its docstring | "the applier backs up every file before applying" |
| A new kind of input or output | a connector or channel plugin | a mailbox, a calendar feed, a blog, a social network |
| A new kind of thing to track, or fields on a core record | a record type in a plugin or pack | a manuscript with word count and submission state |
| A whole kind of work | a pack | workplace status pages; publishing support |
| Logic only one organization or person needs | a private plugin in that workspace's `plugins/` | a page layout one program insists on |
| Who someone is, their team, role, how to reach them | `data/people.json` | "Jane Doe leads delivery for the billing teams" |
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
| Where data is stored and backed up | `config/storage.yaml` | files with snapshots pushed to a private git remote |
| Packaging for a hosting platform | a recipe in `deploy/<target>/` | a container plus a reverse proxy |
| Which AI provider and model does which task | `config/ai.yaml` | "routine tasks on provider A's small model" |
| A plugin's settings | `config/plugins/<plugin>.yaml` | the reference pack's portfolio grouping label |
| Prompts and instructions the AI gets | `prompts/` templates | the changeset instructions, the update-writing style |
| Standing instructions the PM states in passing | `config/rules.md` (read by every AI run) | "don't ask the program manager to confirm program dates" |
| Why a deployment behaves a certain way | the workspace's `docs/decisions.md` | dated entry: what, who decided, why |
| Why the product is built a certain way | this repository's `docs/decisions.md` | dated entry: what, who decided, why |

If a requirement doesn't fit a row, the answer is a new config key with a schema and a default, a plugin, or a new generic
extension point. It is never an `if team == "X"` or an `if plugin == "Y"` in the core.

### 2.4 Technology choices

- **Python 3.12+** for the engine and API, managed with **uv**. **FastAPI** for the HTTP API. **Pydantic v2** models for config,
  records, ops and plugin manifests; JSON Schema is generated from the models, so the AI's output schema and the validator
  never disagree. **pytest** for tests, **ruff** for lint and format.
- **React + TypeScript**, built with **Vite**, tested with **Vitest**. The UI gets its panel definitions from the API.
- **Plugins** are Python packages. Installed ones are found by the entry-point group `pm_cockpit.plugins`; bundled and private
  ones by scanning `plugins/` and `<workspace>/plugins/`.
- **Storage** starts as JSON and YAML files in the workspace git repository, behind a repository layer; other backends
  (SQLite, Postgres, object storage for sources) plug in through the same layer (4.15).
- **Runs locally or hosted** from the same code (Part 11). One container image serves every hosted target; the UI build
  works under any base path without rebuilding.

The reasons are recorded in `docs/decisions.md`.

---

## Part 3. Plugin system

The plugin system is what makes the core a base. Build it first (Part 13, milestone 1) and build the reference pack on it, so the
first real use proves the extension points instead of bypassing them.

### 3.1 Kinds of plugins

- **Bundled plugins** (`plugins/` in this repository): generic for their domain, tested in CI against both fictional
  workspaces. A connector, channel or AI adapter may name the product or vendor it connects to, inside its own plugin only.
- **Installed plugins:** Python packages anyone publishes, found by entry point. Same manifest, same API, same rules.
- **Private plugins** (`<workspace>/plugins/`): may hold specifics of that one deployment. Never committed to this repository.
- **Packs:** any of the above that bundles record types, ops, templates, prompts, panels, Today lines, jobs and default config
  for one kind of work. A pack may depend on other plugins (its connectors and channels) and on interfaces, never on one
  vendor's connector when an interface will do.

### 3.2 Manifest

Every plugin has a `plugin.yaml`. The host reads it before importing any code, so the PM can see what a plugin does and what it
may reach before enabling it.

```yaml
name: personal-projects
version: 0.1.0
plugin_api: ">=1.0,<2"            # plugin API versions this plugin works with
description: Track side projects with goals, next steps and a weekly review.
depends_on: []                    # other plugins, with version ranges
provides:                         # checked against what the code registers
  record_types: [personal-projects/goal]
  ops: [personal-projects/goal.add, personal-projects/goal.update]
  ai_task_kinds: [personal-projects/weekly-review]
  panels: [personal-projects/goals]
  today: [personal-projects/goals-due]
  jobs: [personal-projects/weekly-review]
config_schema: personal_projects.config:Settings
requires:
  network: []                     # hosts it may reach; empty means none
  secrets: []                     # secret names it reads (values come from env or keychain)
  data_levels: [open, internal]   # the most sensitive inputs it may see
entry: personal_projects:register # called with a registrar from engine.plugin_api
```

Identifiers that aren't core are namespaced `<plugin>/<name>`, so two plugins never collide and every op, record or panel shows
where it came from.

### 3.3 Extension points

| Point | What a plugin adds | Interface (sketch) |
|---|---|---|
| Connector | an input source | `poll(state) -> changes`, `fetch(ref)`, `search(query)`, `capabilities()`; typed errors: no-access, not-found, outage, auth |
| Channel | an output target | `current(target)`, `diff(current, draft)`, `send(approved_draft)`, `verify(result)`, `capabilities()` (versioned, pull-edits, schedule, length limits, media) |
| Record type | a kind of thing to track, or extra fields on a core record | a Pydantic model, a storage folder, display labels, migrations, the references it stores to other records (for rename) |
| Op type | a changeset operation | required fields, `validate`, `normalize`, files it may touch, `apply`, `describe` (one readable line) |
| Op validator | extra checks on an existing op, core or plugin | `validate(op, workspace) -> problems` (can refuse, never modify) |
| Triage matcher | a rule kind for `config/triage.yaml` | `match(change, params) -> reason or None` |
| AI adapter | a vendor's model, as API or agent | 6.16 |
| AI task kind | a new kind of AI work | packet builder, output schema, required capabilities, default prompt template, default tier |
| Renderer | how records become content for a channel | template files, optional render function |
| Lookup | a fact the AI can ask the engine to fetch | `lookup(query) -> result` |
| Panel | a UI view | declarative view spec (7.2); bundled plugins may also ship a React component |
| Today contributor | lines on the Today list | `lines(workspace) -> [TodayLine]` |
| Job | scheduled work | name, default schedule, needs network, `run()` |
| Event handler | a reaction to a core event | `subscribe(event, handler)` (3.4) |
| API route | extra endpoints | mounted under `<base path>/api/plugins/<plugin>/` |
| Auth provider | a way to sign in | `begin(request)`, `complete(request) -> identity or refusal`, `capabilities()` (11.4) |
| Storage backend | where records, sources and snapshots live | the repository layer's interface: read, write with merge, lock, list, snapshot (4.15) |
| Check | the plugin's own self-check | `check() -> problems` |

A new extension point is added to the core when a plugin needs something none of these provide. It is generic, documented here,
and covered by a test that uses it from a plugin.

### 3.4 Events

The core publishes events after each step: `source.saved`, `change.filed`, `change.closed`, `request.queued`,
`changeset.applied`, `changeset.undone`, `record.changed`, `draft.created`, `draft.approved`, `draft.sent`, `question.asked`,
`question.answered`, `action.added`, `action.closed`, `issue.opened`, `job.finished`.

Handlers may read, queue requests, file questions and open issues. They may not write records directly; anything that changes
knowledge goes through an op and the applier.

### 3.5 Rules every plugin follows

Enforced by the plugin host, the applier, the publisher and the self-check:

- **Writes go through the applier.** A plugin changes knowledge only through ops, and an op's apply function touches only the
  paths it declared.
- **Sending goes through the publisher.** A channel's `send` is called only by the publisher, only for a draft whose content
  hash matches the PM's approval. No plugin API hands out a way to send.
- **Reach is declared.** Network hosts, secrets and data levels come from the manifest; the host's shared HTTP client and
  secret store refuse anything undeclared. Restricted inputs never reach a plugin whose `data_levels` excludes them.
- **Config is like core config.** `config/plugins/<plugin>.yaml`, with a schema, defaults and descriptions.
- **Code against the API, not the internals.** Plugins import only `engine.plugin_api`. The plugin API follows semantic
  versioning; a breaking change is a new major version.
- **Failures stay contained.** A plugin that raises becomes an `Issue`; the core and other plugins keep running. Disabling a
  plugin stops its jobs and hides its panels, and keeps its data on disk.
- **Bundled plugins ship demo config and data** for both fictional workspaces and pass the suite against both.

### 3.6 Lifecycle

- **Enable** in `config/workspace.yaml` under `plugins.enabled`. At startup the host reads manifests, checks plugin API versions
  and dependencies, validates each plugin's config, then calls `register`.
- **Upgrade:** record schema changes ship as migrations. The workspace is snapshotted to git first; a failed migration restores
  the snapshot and opens an issue.
- **Disable:** jobs stop, panels hide, records stay. Re-enabling picks up where it left off.

### 3.7 Worked examples

These show that the extension points cover the uses in view. They are not commitments; each is a pack built later.

| Use | Connectors | Channels | Record types and ops | AI task kinds | Panels and Today |
|---|---|---|---|---|---|
| Workplace PM (reference pack, Part 9) | wiki, issue tracker, release tracker, shared files | wiki pages; clipboard messages | portfolio fields, risks with owner team, milestones | weekly check-up goals, status updates | portfolio health by group, milestones to check |
| Publishing support | manuscript folder, submissions tracker, mailbox | email to editors and agents, newsletter, blog | manuscript, submission, calendar entry | query letter draft, read a submission reply | submissions by status, editorial calendar |
| Personal projects | notes folder, calendar feed | clipboard, notes file | goal, next step | weekly review | goals, this week's next steps |
| Social media | account mentions and replies | posts per network, scheduled after approval | post, campaign | draft a post, summarize replies | post queue, replies waiting |

If a planned pack needs something no extension point provides, add a generic extension point to the core. Never special-case a
pack in the core.

---

## Part 4. Configuration model

All config is YAML (rules prose in Markdown), validated against a schema at startup and by the self-check. Every key has a
default, so a new workspace runs with an almost empty config. Each file starts with a comment block explaining every key. Core
config lives in `config/`; each plugin's lives in `config/plugins/<plugin>.yaml`.

### 4.0 Configuration principles

The goal: a person changes how their installation looks, behaves, runs and is secured without changing code.

- **Behavior that someone might reasonably want different is a setting.** Names, labels, wording, layout, schedules,
  thresholds, routing, which plugins run, where the app is served, how people sign in and where data lives are all config.
  Hard-coding one of these is a bug.
- **One schema per file, one source of truth.** Schemas live with the code that reads them (Pydantic models). They produce
  the validator, the defaults, the comment block in each file, the documentation and the settings forms in the app.
- **Layers, in order of precedence:** built-in defaults, then the workspace's config files, then environment variables, then
  command-line flags. Any key can be set from the environment as `COCKPIT__<FILE>__<KEY>` (for example
  `COCKPIT__SERVER__BASE_PATH=/admin`), which is how hosting platforms usually pass settings. `cockpit config show` prints the
  effective value of every key and which layer it came from.
- **Profiles:** `config/profiles/<name>.yaml` holds overrides for one environment (`local`, `hosted`); `COCKPIT_PROFILE`
  picks one. The same workspace can run on a laptop and on a host with only the profile changing.
- **Settings in the app:** the Admin tab has a Settings panel with a form per config file, generated from the schemas, with
  each key's description and default. Saving validates, backs up, writes the file and commits it to the workspace's git, the
  same way the applier does. Keys set by an environment variable or flag show as locked, with where they came from. Secrets
  are never shown or typed into config; the form takes a reference (`env:NAME`, `keychain:NAME`, `file:/path`).
- **Safe to change while running:** most settings apply on save. Settings that need a restart (address, port, base path,
  storage backend) say so and offer it.

### 4.1 `config/workspace.yaml`

- `assistant_name`, `assistant_description` (display only)
- `user`: the PM's full name, aliases ("me", first name), timezone
- `plugins`: `enabled` (names with optional version ranges), extra search `paths`
- `connectors`: named connector instances, each with a `type` (a registered connector) and its settings
- `channels`: named channel instances, each with a `type` (a registered channel) and its settings
- `our_accounts`: accounts the cockpit sends with, per connector or channel, so lookups know "that edit was us"
- `owner_format`: how an owner is written and parsed, e.g. `"{full_name}"` (default) or `"{team} ({full_name})"`
- `restricted_sources`: how restricted inputs are marked and where they may appear

Approval before anything goes out is not a setting; it is always on.

### 4.2 `data/people.json`

People with `full_name`, `aliases`, `role`, `team` (optional), `org` (optional), `how_to_reach` (per channel),
`why_they_matter`, `track_only` (their items are observed, never chased), `non_working_calendar`, `verified` (spelling checked
against a primary source). The single source for names. A person's area (tracked, a domain, or unknown) comes from their team
and `config/scope.yaml` (4.4); `track_only` marks someone inside the tracked area whose items are still only observed.

### 4.3 `config/routing.yaml`

Ordered rules that choose a recipient for a question by topic, project, owner team or kind:
`when: {topic: requirements, project_field: product_owner} then: {to: "{project.product_owner}"}`.
A rule can say `ask_user_first` (unsure: the PM routes it). Unmatched questions go to the PM as a routing decision, never to a
guess.

### 4.4 `config/scope.yaml`

Scope says which area is the workspace's own and which belongs to someone else. The applier (6.7) and the scope sweep (6.18)
enforce it; it is never left to the AI's judgment.

- `tracked`: the workspace's own area: patterns (teams, owners, systems, item prefixes). Only people and items here get action
  items, detailed questions, follow-ups and overdue flags.
- `domains`: other areas the PM sees but doesn't run, each with `match` patterns (teams, owner labels as they appear on
  pages and in minutes, systems, item prefixes, page trees) and a `contact`: the one person who speaks for that area toward
  this workspace, usually its program manager. Items in a domain are observed: recorded as facts, never assigned, never
  chased, even when meeting minutes or program pages name people in it.
- `cross_domain`: what may be asked of another area. `allow`: `impact-only` (default) or `none`. `to`: `contact` (always; never
  individuals inside the domain). `batch`: `later` (default), so cross-domain asks collect into one message per contact.
  `max_open_per_contact`.
- `observed`: other items recorded as facts but never chased (milestones someone else runs) that aren't part of a named domain.
- `parked`: categories recorded in a parked list and otherwise ignored.
- `unclassified`: what happens to a person or item that matches nothing: `ask` (default: one routing decision to the PM to
  place them) or `observed`. Never tracked by default.
- `new_scope`: what counts as new work beyond agreed scope, and that it becomes a pending decision until the owner decides.

```yaml
tracked:
  teams: [Orders Core, Orders Platform]
domains:
  - name: Payments
    match: {teams: ["Payments*"], owners: ["Payments (*)"], prefixes: [PAY-]}
    contact: Dana Fox            # program manager who answers for Payments toward us
  - name: Storefront
    match: {teams: ["Web*", "Mobile*"], trees: [storefront roadmap]}
    contact: Ana Ortiz
cross_domain: {allow: impact-only, to: contact, batch: later}
unclassified: ask
```

### 4.5 `config/watch.yaml`, `config/triage.yaml`, `config/schedule.yaml`

- **Watch:** entries naming a connector instance and what to watch through it (a page with or without children and depth, a
  tree, people's recent edits, a query, a folder, a feed). The settings each entry accepts come from the connector's schema.
- **Triage:** rules, each with `name`, `kind` (a registered matcher), parameters, and a `why` template shown to the PM. The core
  matchers are generic: `same-edit`, `cosmetic`, `already-seen-file`, `diff-terms-absent`, `owner-not-ours`, `other-domain` (a
  change entirely inside another domain that names no tracked item: kept as a source and closed as observed),
  `container-not-mapped` (an item under a watched container that maps to no project), `child-item`, `unknown-key`. Plugins may
  register more.
- **Schedule:** jobs (core and plugin) with cron-like times, working hours, which jobs need the network, catch-up behavior
  after sleep.

### 4.6 `config/language.yaml`

Locale and spelling list, blocked phrases on shared outputs (question-style wording: "confirm", "check whether", "TBD?"),
separators that mean a run-on list, words that must never appear in user-visible text (the model's name), date formats.

### 4.7 `config/render.yaml` and templates

Output types (pages, messages, posts, plugin types), their sections and column names, column widths, sort orders per section,
what counts as a cosmetic change, and how status labels render. Templates are files, not strings in code; the core and plugins
ship defaults and the workspace's `prompts/` and template folders override them.

### 4.8 `config/ai.yaml`

The whole AI setup, so changing vendor or model is a config edit (details in 6.16):

```yaml
providers:                     # every AI the workspace may use
  primary:
    adapter: anthropic-api     # an installed AI adapter; the only place a vendor appears
    auth: env:PRIMARY_AI_KEY   # a reference to a secret, never the secret itself
    models: {small: <model id>, large: <model id>}
    allowed_data: [open, internal, restricted]
  coding-agent:
    adapter: cli-agent         # any command-line agent: start command, args, how to pass the packet, where it writes
    command: <path to the agent CLI>
    allowed_data: [open, internal]
tiers:                         # what the work needs, mapped to a provider and model
  routine:  {use: primary/small, fallback: [coding-agent]}
  deep:     {use: primary/large}
  vision:   {use: primary/large}          # screenshots and images
  code-fix: {use: coding-agent}
tasks:                         # which tier each AI task kind uses (defaults shown; plugin kinds use their declared default)
  change: routine
  notes: routine
  answer: routine
  feedback: routine
  update: deep
  fix: code-fix
budgets: {per_run_usd: 5, per_day_usd: 20, per_month_usd: 200}
evaluation: {required_before_switch: true, min_score: 0.9}
```

### 4.9 `config/dispatch.yaml`, `config/governor.yaml`

Batch size, immediate-run kinds, timeouts, attempts; governor thresholds (stuck after N minutes, stale after N hours, outage
when more than N keys fail); `fixer`: `union_merge` (file patterns merged by union on Apply, default `["*.md"]`) and
`redo_attempts` (how many times a conflicting fix is redone before it goes to the PM, default 2).

### 4.10 `config/rules.md`

Plain-language standing rules the PM states while working ("record who raised each risk"). Every AI run reads it. The cockpit's
"Respond to the assistant" flow appends to it when the PM states a rule.

### 4.11 `config/status.yaml`, `config/calendar.yaml`, `config/ui.yaml`

- **Status:** the status labels in use, their colors, and which count as open, done or at risk.
- **Calendar:** the week end that "this week" runs through, holidays, and per-team non-working days (by `non_working_calendar`).
- **UI:** tab order, hidden or reordered panels, quick links in the header, and branding: product name shown in the header
  and browser tab, logo, accent colors, light or dark theme.

### 4.12 `config/plugins/<plugin>.yaml`

Each enabled plugin's settings, validated against the schema the plugin's manifest names. Same rules as core config: every key
has a default and a description, and both fictional workspaces carry demo values.

### 4.13 `config/server.yaml`

- `mode`: `local` (default) or `hosted`. Hosted turns on the deploy checks (11.5) and refuses to start if they fail.
- `bind`: address and port to listen on (local default `127.0.0.1:8765`; hosted usually `0.0.0.0` with the port the platform
  gives).
- `public_url`: the address people use, e.g. `https://example.com`. Required when hosted.
- `base_path`: where the app is mounted under that address, e.g. `/admin` (default `/`). The UI, the API
  (`<base_path>/api`), cookies and every link the app makes use it; nothing in code assumes the root.
- `hide`: when hosted, how the app answers someone who isn't signed in: `login` (show the sign-in page) or `not-found`
  (answer 404 everywhere except a configurable sign-in path, so a passer-by can't tell the app is there).
- `trusted_proxies`: the addresses or networks of reverse proxies whose forwarded headers (client address, protocol) are
  believed. Headers from anyone else are ignored.
- `allowed_hosts`: host names the app answers to; requests for any other host are refused.
- `headers`: security headers (content security policy, HSTS, frame and referrer policy), with safe defaults that can be
  tightened; `robots: noindex` by default.
- `cors`: off by default.
- `role`: `all` (default: web server, scheduler and workers in one process), `web` or `worker`, for hosts that run them
  separately.

### 4.14 `config/auth.yaml`

- `providers`: an ordered list of sign-in methods, each with a `type` (a registered auth provider, 11.4) and its settings.
  Several may be enabled; the sign-in page offers each.
- `users`: who may sign in, by identity per provider (an email address for a sign-in provider, a username for a password).
  Everyone listed has full access in the base; roles are a later feature.
- `require_second_factor`: when hosted, a password alone is refused; defaults to true.
- `session`: idle timeout, absolute lifetime, remember-device length, cookie name.
- `lockout`: failed attempts before a pause, pause length, rate limit per address.
- `recovery`: how to get back in when locked out (one-time recovery codes generated at setup; a command run on the server
  that resets a user).

### 4.15 `config/storage.yaml`

- `backend`: `files` (default: JSON and YAML in the workspace folder) or a registered storage backend (SQLite, Postgres,
  object storage for sources). Changing backend runs an export and import, with a snapshot first.
- `path`: where the workspace lives on disk, when the backend uses one. Hosted platforms need it on a persistent volume.
- `snapshots`: how often to commit, and an optional `remote` (a private git repository) to push to after each snapshot, so a
  hosted install has an off-site copy.
- `backups`: optional export of the whole workspace on a schedule, to a folder or an object store.

### 4.16 `config/facts.yaml`

Kinds of fact that a published source holds, so they are looked up and never asked of a person (6.19).

```yaml
kinds:
  ship_release:                    # which release a work item ships in
    lookup:                        # tried in order; the first answer wins
      - {connector: delivery-tracker, field: release}
      - {connector: tracker, field: [sprint, fix_version]}
    missing: tbd                   # nothing found: show "TBD", never ask
  production_date:                 # when that release reaches production
    from: ship_release
    lookup:
      - {watch: release-schedules, key: delivery_team}   # one watched schedule page per delivery team
    missing: tbd
    terms: [date, release, ship, go-live, production]   # how a question asking for this kind reads
    no_questions_to: [release-managers, delivery-leads]  # people or groups never asked for this kind
```

- `kinds`: each with ordered `lookup` steps (a connector field, a watched source keyed by a record field, or a plugin's lookup),
  an optional `from` (a kind this one is looked up from), `missing` (`tbd` or `ask-pm`; never a question to someone else),
  `terms` and `no_questions_to`.
- Sources named in lookups are watched, so a schedule change updates every date that depends on it.

---

## Part 5. Data model and storage

Start with JSON and YAML files in the workspace git repository. The engine talks to storage through a repository layer, and
the backend is chosen in `config/storage.yaml` (4.15), so moving to SQLite, Postgres or object storage is a config change plus a
backend plugin. Plugins store records through the same layer.

### 5.1 Core entities

| Entity | Key fields |
|---|---|
| `Project` | id, name, group (portfolio grouping; its label comes from config, e.g. "Program"), status, phase, target, priority, summary, owner, links, tags, risks[] (text, raised_by, owner, status), actions[], decisions[], milestones[], players[], log[] (dated update log), facts[] (internal knowledge with source), hold flag, `ext` (fields added by plugins, keyed by plugin) |
| `Source` | id, date received, who, kind, connector instance, title, path to saved text, projects, restriction, url |
| `Change` | id, source kind, title, link, diff, detected_at (zoned), who, state (new, queued, processed, done, ignored), result, auto rule, superseded_by, covers[] |
| `Request` | id, kind (an AI task kind: change, notes, request, answer, feedback, action, update, lookup-result, or a plugin's), ref, note, state, attempts, created |
| `Changeset` | id, change_id?, request_id?, summary, ops[], status (applied, rejected, undone, proposed, discarded), errors[], files, backup, dismissed, quiet, feedback[] |
| `Draft` | id, channel instance, target, output type, content, base version, diff, content_hash, status (draft, approved, scheduled, sent, failed, superseded), approved_at, send_at, sent_at, result |
| `Question` | id, to (full name), title, text, links[], kind (question, decision, action-notice, routing), batch (now, later), projects[], asked_at, waiting days, on_answer, key (dedupe), answer_pending, feedback_pending |
| `Action` | key (stable), store, text, owner (in the workspace's owner format), due, status, notes, told{person: date}, followups[] |
| `Meeting` | title, due, attendees, before and after notes, status |
| `Person` | see 4.2 |
| `Issue` | an automation problem: summary, detail, plugin (when one raised it), status (open, fix-requested, fixing, fix-proposed, fixed, closed) |
| `Run` | one AI task run: request, task kind, provider, model, units, cost, time, outcome |

Plugins add their own record types under `data/<plugin>/` and extra fields on core records under `ext.<plugin>`. Core code never
reads a plugin's `ext` fields; the plugin's ops, renderers and panels do.

### 5.2 Storage rules (each one came from a real failure)

- Every input is saved as a text file under `sources/` and registered before anything is done with it.
- Ids and dates come from the actual date received, never from a meeting or date mentioned in the content.
- Ids never repeat. Every id (questions above all) comes from a per-workspace counter that only goes up; a closed, dropped or
  deleted record's id is retired, so a reference in a log or a sent message always means one thing.
- Times are stored with their zone and converted for display; date-only values display as that calendar day.
- Never save a copy of a file loaded earlier in a long operation: re-read, merge, write. Saves that can race (a refresh writing
  the inbox while a run marks items) merge by item, not overwrite.
- Every write that changes knowledge goes through the applier (or a core service that logs the same way), so it is validated,
  normalized, backed up and visible.
- The workspace is snapshotted to its git repository on a schedule, before every migration and before every applied fix.
  History is never rewritten.

---

## Part 6. Core engine components

Each component is generic, configured from Part 4, and has its own tests with fictional fixtures.

### 6.1 Plugin host

Discovers plugins (entry points, `plugins/`, `<workspace>/plugins/`), reads manifests, checks versions and dependencies,
validates plugin config, and calls each plugin's `register` with a registrar for every extension point (3.3). Checks that what a
plugin registers matches its manifest. Runs the event bus (3.4). Wraps every call into plugin code so an exception becomes an
`Issue` naming the plugin, not a crash.

### 6.2 Connectors (inputs)

The interface in 3.3. Each returns plain data; errors are typed (no-access, not-found, outage, auth). The core ships paste-in
and upload, a local-folder connector and the fake connector. Everything else (wikis, trackers, mailboxes, calendars, feeds,
social accounts) is a plugin. Files are read as text from documents and spreadsheets by a shared extractor that plugins reuse.

### 6.3 Channels (outputs)

The interface in 3.3. A channel describes its capabilities: versioned targets with a concurrency check, pulling others' edits
back, scheduled sending, length limits, media. The core ships the clipboard channel (the PM copies the approved text and pastes
it anywhere) and the fake channel. Wiki pages, email, blogs and social networks are plugins. Channels are called only by the
publisher (6.12).

### 6.4 Watchers

Run on schedule through connectors; compare against snapshots; file a `Change` per real difference with a readable diff. Rules:

- An outage (many keys failing at once, or connection errors) is one logged issue, not a question per key. A single item is
  asked about only after it fails on consecutive runs.
- A file that moved is compared by content with what's registered before it counts as new. Spreadsheets are compared by cell
  content, not bytes, so a re-save isn't a change.
- **Supersede:** when a newer version of the same item arrives while an older one is queued, fold them into one change (all
  diffs, in order) so the AI never processes them out of order.
- Watch lists stay complete: when a record cites an item key, that key joins the watch list in the same step.

### 6.5 Triage

Applies `config/triage.yaml` rules in order before queueing, using registered matchers. Each closed item records the rule and a
readable reason, appears under "Auto-closed", and has a one-click way to send it back ("This is ours", "Take a closer look");
pulled-back items are recorded so rules can be tuned.

### 6.6 Dispatcher

- Batches queued requests (batch size, scheduled batches, immediate kinds that run within a minute of the PM handing them in,
  with a short delay so a note can follow).
- **Packet:** for each request, the input, the related records, every open action with its exact key (so the AI can close what
  the input completed), open questions to the people involved, the area each related person and item is in with each domain's
  contact (6.18), the rules file, and the op reference (core and enabled plugins' ops). A plugin's AI task kind builds its own packet with the same parts available.
- **Self-check:** validates each changeset with the applier's checks right after the run and sends failures back for one fix
  round. Recovers the request id from unreadable output and re-queues it.
- Picks the provider and model from `config/ai.yaml`, with the fallback chain on usage limits or auth failures; a request with
  no changeset after N attempts goes to the PM as "Needs you". The dispatcher only talks to the provider layer (6.16).

### 6.7 Changesets and the applier

A changeset is JSON: `summary`, optional `change` and `request` ids, and `ops[]`. Its JSON Schema is generated from the op
registry, so the AI is asked for exactly what the applier accepts. The applier holds a **registry of op types** (3.3).

**Core op types:** `source`, `note`, `fact`, `record.set`, `record.add`, `record.del`, `record.log`, `action.add`,
`action.update`, `action.close`, `action.assign`, `decision.add`, `milestone.add`, `risk.add`, `question.add`,
`question.update`, `question.move`, `question.done`, `question.drop`, `meeting.add`, `meeting.update`, `draft.request`
(ask for a rendered draft to a channel), `parked`, `inbox` (set a change's state), `lookup`, `watch.add`, `watch.remove`,
`rule.add`, `doc`, `record.rename`, `dev.request` (a code change request: becomes an issue for the fixer). Plugins register more,
namespaced.

**Rename is one op.** `record.rename` changes a record's name everywhere it is stored: the record, its output settings (page
title), roll-up rows and links, the watch list, question labels, parked items and source tags. The core keeps a reference index
(which records, outputs and labels mention which record) so nothing is missed, and plugins register the references they store.
The output target keeps its id, so the publisher renames the page in place; a title-only change is a draft like any other and
shows as "renamed (same page)".

**A change request becomes a code fix only when no op can do it.** `dev.request` must list the ops it considered and why none
fits; the validator checks the list against the registry and refuses the request when an existing op could do the job, sending
it back to be done as a changeset. When a fix adds a new op (in a private plugin, 6.13), the changeset that needs it waits with
the fix and is applied after Apply, once the new op is registered; the running applier would refuse it before.

**Validation (all generic, all driven by config):**

- Required fields per op; known targets (record exists, action key resolves to exactly one action).
- Wording on anything that reaches a shared output: blocked phrases, the model's name, locale spelling, run-on separators.
- Every record edit that changes a published output comes with an update-log op.
- Restricted sources never cited on open outputs.
- New actions name a person as owner in the workspace's owner format (a team alone or a blank is refused; an unknown person
  means ask the PM first).
- **Scope** (6.18): an action's owner must be in the tracked area or be the PM. An action for anyone else, or with an owner
  label that matches another domain's `owners` patterns, is refused, with the reason, and the AI records the work as a fact on the observed item instead. A question to anyone outside the tracked area is
  refused unless `cross_domain.allow` is `impact-only`, it goes to that domain's `contact`, it is marked `impact`, and it names
  in `affects` the tracked project or item it is about. Questions to people inside another domain who aren't its contact are
  always refused. An op naming a person whose area is unknown is held and one routing decision goes to the PM.
- **Facts are looked up, not asked** (6.19): a question that asks for a fact kind with lookup sources (marked `asks_for`, or
  matching that kind's `terms`) is refused and sent back as a `lookup`; a question matching a kind's `terms` to anyone in its
  `no_questions_to` is always refused. A lookup that finds nothing records TBD, not a question.
- Questions carry links to what they're about; questions to anyone but the PM link only things the recipient can open (no local
  files, no cockpit pages) and contain no assistant bookkeeping in labels.
- Op-specific checks (paths stay under allowed roots; files don't overwrite unless told).

**Normalization before apply:** every person name in owners and recipients expanded to the full name (6.11).

**Apply:** back up every file the ops may touch, apply in order, re-render affected outputs, log the changeset with one readable
line per op. On error, restore the backup and record the error. **Undo** restores the backup if nothing has touched those files
since; otherwise it refuses and says why.

**Classification:** a changeset is "for the PM" only if it drafts an output, files a question, adds a decision or action, or
otherwise needs a decision. Everything else is filed quietly (still findable). The change it came from closes as "no change
needed" automatically, so the PM never clicks "Looks good" on nothing.

### 6.8 Questions service

- `ask(to, title, text, key, on_answer, links, projects, batch)`: deduplicates by `key`; holds the question and files a routing
  decision to the PM when the recipient is unsure (`to: "?"`, a first name several people share, a name nobody on file has).
- Enriches links automatically from item keys and known titles found in the text.
- **Decisions are questions addressed to the PM.** Whether something is "your decision" is decided by the recipient, never by a
  stored kind. Moving a question from the PM to someone else makes it an ordinary question.
- Answer flow: the PM types an answer or pastes the person's reply; it becomes a request carrying the question and its
  `on_answer`; the AI records the answer as a fact, updates records, closes or narrows the question, and re-checks every other
  open question to that person against the same answer.
- Feedback flow ("Respond to the assistant"): reword, reroute, drop (kept in a dropped-questions register with the reason) or
  close; every op that settles a pending request clears that question's pending flag.
- Aging: "waiting Nd" after Mark sent; chase suggestions after a configured number of days.

### 6.9 Actions service

- One store interface over every action store (project records, portfolio actions, plugin stores), each action with a stable key.
- **Mark done** for the PM's own; for others' actions **Followed up** (recorded internally, stays open, counts as told) and
  **They finished it** (credited to the owner, "reported by" the PM). Never credit the PM for someone else's work.
- **Reassign:** swap one person for another in the owner field, keeping the rest of the owner format ("Product (Jane Doe)" to
  "Product (Sam Lee)"); in a multi-owner field, only the named person's part; refuses first names it can't resolve.
- **Assign:** give a team-only or blank owner a person.
- Any change in who does something or when updates the action (and any matching meeting) in the same step.

### 6.10 Action notices

Actions owned by others reach them: each open action not yet communicated to an owner shows as "to send" on the action row (not
as a separate question row), the person's Copy includes it, Mark sent records it as told. Closing the action closes the notice.
A baseline date lets a new workspace treat existing actions as already communicated. Owners marked `track_only` get no notices.

### 6.11 Names

One normalizer used on every write path: a first name only one known person has becomes that full name; any casing of a full
name becomes the stored spelling; the PM's aliases become the PM; teams and system labels stay as written; names nobody has on
file stay as they are. Owners are parsed and written with the workspace's `owner_format`. A scheduled sweep rewrites any short
name that got stored anyway (hand edits, pulled-back edits) and files one decision to the PM listing people known only by first
name. Grouping in the UI uses the same normalizer.

### 6.12 Records, renderer and publisher

- Records are the source of truth; outputs are rendered from records via templates into drafts. Never hand-edit a rendered
  output.
- For channels that can pull edits back, edits made by others on a published output (in parts the team owns) are pulled into
  records before re-rendering, so a render never overwrites them. Column matching tolerates renamed headers.
- Render-time ordering from config (actions open before done, then by owner and due date; milestones by date, undated last;
  decisions newest first). Records can stay in any order.
- Roll-ups (a summary page from project pages) are renderer features configured in `config/render.yaml`; a row edited directly
  on the roll-up after its source is kept unless forced.
- **Publisher:** dry run, then send only drafts whose exact content the PM approved (content hash), with the channel's
  concurrency check when it has one (nobody edited since the pull) and the target's own validation. Pulls skip targets with
  unsent drafts and flag any whose remote copy moved on. Scheduled drafts are approved first and sent at their time; editing a
  scheduled draft clears its approval.
- Change classification for the review list: real change, order only, layout or format only, columns changed, text the target
  doesn't show. Never show an empty "+0 −0" draft.

### 6.13 Governor and fixer

- Every few minutes: re-queue requests whose run never finished, push work waiting too long in working hours, repair changes no
  request carries, detect stale data and outages, run the name sweep, the scope sweep (6.18) and the notices, snapshot the
  workspace hourly.
- Problems in the automation become `Issue`s. "Fix it" starts a fix run (the `code-fix` tier in `config/ai.yaml`) whose change
  comes back as a **proposed fix** with a diff; it goes live only when the PM clicks Apply. Proposed fixes can't be hidden by
  "dismiss all".
- **Apply merges; it doesn't check for staleness.** Busy files change between the fix run and the click, so a whole-file "has
  it changed since?" check would make nearly every fix stale. A proposed fix keeps the original of every file it touches. Apply
  does a three-way merge (original, current, proposed) per file, with a union merge for files listed in `fixer.union_merge`
  (default: Markdown) so rows both sides appended are kept. Only a real conflict stops it, and then the fix is redone
  automatically against the current files (up to `fixer.redo_attempts`, then the issue goes to the PM with the conflict shown).
- **One place per fix:** a proposed fix shows on its issue card only, and is counted there (Today, the header, the issue list
  count it once).
- **What the fixer may change:** the workspace's config, rules, prompts, templates and private plugins, applied in the
  workspace with a git snapshot first. A fix that needs the core or a bundled plugin is written as a patch and an issue for this
  repository, never applied to the installed engine, so deployments don't drift from the product.
- The self-check (Part 10) validates config schemas, plugin manifests, imports, the web build and the specificity guard; run it
  after any change.

### 6.14 Scheduler and offline behavior

Jobs that need the network wait while it's down and run when it returns ("Offline" shown, not failed). After sleep, the first
refresh runs on wake when data is stale. A held job doesn't count as a run. Plugin jobs follow the same rules. Jobs run in
the process whose `server.role` is `all` or `worker`; a lock in the storage layer makes sure only one scheduler runs at a time,
even when a host starts more than one copy.

### 6.15 Today builder

Builds the PM's Today list from live data and from plugins' Today contributors. **Every line starts with what the PM does and
says where:** answer N decisions, review and send N drafts, look over N changes, send N questions to a person, follow up on
questions waiting N days, finish N of your overdue actions, hold N meetings this week, apply N proposed fixes. Status, progress
and things the automation handles never appear.

### 6.16 AI provider layer (any model, by configuration)

The product starts with one vendor's models and must be able to move to another (or mix several) by editing `config/ai.yaml`.
Nothing outside the adapters knows which vendor is in use.

**One provider-neutral contract.** Every call is an `AiTask`:

- input: the task kind, the packet (Markdown and JSON: the input, related records, open actions with keys, open questions, the
  rules, the op reference), attachments (images, files), and the output schema;
- output: a JSON document that validates against that schema (for most kinds, a changeset), plus usage (tokens or the vendor's
  billing unit, cost, time) and a normalized error when it fails.

The engine validates the output with the same applier checks regardless of who produced it. Task kinds are a registry: the core
registers its own, plugins add theirs (3.3).

**Two adapter modes, both behind the same interface:**

- **API mode:** the engine builds the prompt from `prompts/` templates, calls the vendor's API, and asks for structured output
  (JSON schema, or tool calls where the vendor prefers them). When the model needs a fact it doesn't have, it returns a `lookup`
  op; the engine runs the lookup and calls again with the result (a bounded loop, so the engine, not the model, touches outside
  systems).
- **Agent mode:** a command-line agent (from any vendor) runs locked down: read-only on the workspace, writes only to `outbox/`,
  no plugins or outside tools unless configured. The adapter knows how to start it, pass the packet (a file path or stdin), pick
  the model, read its output and usage, and recognize its errors.

**Adapter interface** (each adapter is a module in `engine/ai/adapters/` or an installed plugin, registered by name):

- `capabilities()`: structured output, tool calling, vision, file access, code editing, max context, max output, streaming,
  billing unit and price per unit;
- `run(task) -> result` with output, usage and timing;
- `classify_error(raw) -> rate_limited | quota_until(date) | auth | timeout | invalid_output | provider_down | other`;
- `health()` for the governor.

Adding a vendor means adding an adapter and a `providers:` entry; nothing else changes.

**Routing by capability, not by name.** Each task kind declares what it needs (a code fix needs code editing and file access; a
screenshot needs vision; most need structured output and a context size). The router picks the tier's provider, checks its
capabilities, and falls through the fallback chain if it can't serve the task. A config that maps a task kind to a provider that
lacks a required capability fails the self-check.

**Prompts are workspace content, not code.** Instructions, examples and style guides live in `prompts/` templates; the core and
plugins ship defaults that the workspace can override. Per-provider variations (one vendor prefers XML-tagged sections, another
JSON) are handled by the adapter's prompt formatter, not by forking the instructions.

**Evaluation before any switch.** A golden set of fictional fixtures (inputs with the expected changesets and questions) scores a
provider and model on: valid output rate, correct ops, wording rules followed, questions routed right, actions extracted
completely, cost and time. `evaluate --provider <name> --model <id>` produces a report; a model is approved for a tier only after
it meets the configured score, and the PM approves the switch (a scheduled job can check prices and new models and ask the PM,
never switch on its own). Plugins can add fixtures for their own task kinds.

**Usage, limits and cost.** Every run is a `Run` record: provider, model, units and cost. Budgets per run, day and month stop new
runs and tell the PM. A usage limit pauses that provider until its reset (and the fallback takes over); it is not retried in a
loop.

**Data handling.** Each provider has `allowed_data` levels. Inputs marked restricted only go to providers allowed to see them; if
none is, the request goes to the PM instead. Secrets come from secret references (Part 12), never from config files.

**Naming.** The assistant's display name is configuration and is the only name people see; vendor and model names appear only in
`config/ai.yaml`, the adapters, the usage reports and the evaluation reports.

### 6.17 Periodic jobs (later)

- **Weekly check-up:** suggested goals (the AI replaces automatic goals with 3 to 5 real ones), meetings to hold, actions due by
  the end of the week by owner, questions to send, answers to chase, decisions waiting, what moved. Packs add sections.
- **Updates on request:** facts since a date, written in the sender's voice; learns from the edited "as sent" version (roles
  not names where the sender prefers, soft asks, commitments exactly as stated).

### 6.18 Scope

One resolver answers "whose area is this?" for any person, team, item or project: tracked, a named domain (with its contact),
observed, parked or unknown, from `config/scope.yaml` and people data. The applier, triage, routing, notices, Today, the
check-up and the UI all ask it; no other part of the product decides scope on its own.

- **Scope sweep:** on a schedule, and whenever scope config or people data changes, finds open actions, notices and questions
  whose owner or recipient is outside the tracked area and files **one** decision to the PM, grouped by domain, with bulk
  choices: drop them (kept in the dropped register with the reason "outside our area"), turn them into observed facts, or
  replace them with one impact question to the domain's contact. Nothing changes until the PM picks.
- **Cross-domain asks:** questions to a domain's contact collect into one message per contact (batch `later`), each tied to the
  tracked item it affects. When that item closes or leaves scope, its cross-domain question is dropped.
- **Moving the line:** when the PM says an item or team is ours (or isn't), the "Respond to the assistant" flow proposes the
  scope config change; the applier and the sweep take it from there.

### 6.19 Facts and lookups

Some facts have a published home: a work item's release lives in the tracker, a release's production date on a schedule page.
Asking a person for them wastes their time and goes stale. `config/facts.yaml` (4.16) names those kinds and where each is
looked up.

- **Resolver:** for a kind, tries its lookup steps in order (following `from` chains, e.g. item to release to date) and returns
  the value with its source and when it was read. Plugins add lookup steps through the lookup extension point (3.3).
- **Use everywhere:** records, renders and packets show the looked-up value with its source; the AI gets it in the packet and
  never needs to ask.
- **Missing:** a kind with `missing: tbd` shows "TBD" until a source has it. No question is filed; when the source fills in,
  the watcher picks it up.
- **Enforced:** the applier refuses questions for these facts (6.7), so a model that ignores the packet can't send one.

---

## Part 7. UI specification (React)

### 7.1 Shell and layout

- One header bar: product name and logo (from `config/ui.yaml`), date, live indicator and last check, tabs (a segmented control, vertically centered, same height
  as the buttons), a Today button with a count, configurable quick links, Refresh, a Jobs menu, Log.
- Tabs and their panels come from a **panel registry**: the core registers its panels, plugins register theirs, and
  `config/ui.yaml` may reorder or hide them. Default layout:
  - **Work tab:** Automation issues (when any), then a row with **What changed** (two columns wide) and **Waiting to go out**,
    then **Follow-ups** (two columns wide) and **My meetings**.
  - **Portfolio tab:** project health table grouped by the configured grouping; plugins add sections.
  - **Admin tab:** request an update; the assistant's queue; plugins (enabled, version, what each may reach, its issues);
    **Settings** (a form per config file, 4.0); **Security** (who is signed in, recent sign-ins and failures, deploy check
    results when hosted).
  - A tab per pack when the pack declares one.

### 7.2 Plugin panels

Plugins describe panels declaratively, so most need no front-end code and every one looks and behaves like the core:

```yaml
panel: personal-projects/goals
title: Goals
tab: work
source: {record_type: personal-projects/goal, filter: {status: open}}
view: table                                   # list, table, board, form or detail
columns: [title, project, due, status]
row_actions: [personal-projects/goal.update]  # each runs as an op through the applier
```

Row actions and forms submit ops, so plugin UI can't bypass validation, backups or the log. A bundled plugin that needs more may
ship a React component, registered at build time against the same panel interface.

### 7.3 What changed (one list for incoming changes and the assistant's work)

- One row per incoming change (source tag, linked title, state pill with a tooltip of details). The assistant's changesets for
  that change are nested inside ("What the assistant did (N)"), next to "Show the change" (word-level diff).
- One row per piece of the assistant's own work that didn't come from a change (requests, answers), tagged with the
  assistant's name. Code fixes are not here; they live on their issue card in Automation issues (6.13).
- Buttons per row: new change: Process with the assistant / Done / Ignore. Reviewed: **Looks good** (closes the change and
  files its changesets), **Send back** (required note; option "Undo it, then send"), **Undo**. Auto-closed: "This is ours" /
  "Take a closer look".
- **Automation issues** (above What changed when any are open): one card per issue; a proposed fix shows on its card with
  Apply / Discard / See the code change, always visible, sorted first.
- Filter: Needs attention, Processed, With the assistant, The assistant's own work, Done, Auto-closed, Ignored, All.
  "All looks good" for the reviewed rows shown, with a confirm.

### 7.4 Waiting to go out

- Every draft for every channel in one list, grouped by channel. "Review changes" runs the dry run.
- Per draft: checkbox, title (left-aligned, wraps beside the checkbox), tags (new, dashboard view, wording check, scheduled),
  and a plain-words count ("3 changed, 2 added, 1 removed, 1 moved").
- Each channel's output type picks its preview. Pages: word-level strike-through and highlight; a mostly rewritten line shows
  old then new in full; small unchanged bits between changes fold into the change so phrases read old-then-new; table rows show
  cells joined cleanly with empty cells as "—"; a row that only moved shows once with a moved mark; a moved row whose cells
  changed shows as one in-place change. Short posts and messages: the full text as it will appear, with the channel's limits.
- A send message is required where the channel records one; sending a subset warns if a roll-up includes unticked drafts'
  changes. Success notes fade; errors stay with the offending lines and an "Ask the assistant to reword" button.

### 7.5 Follow-ups

- **By person:** "You" first (decisions with Answer; your action items), then everyone A to Z, one section per person (names
  normalized). Only people in the tracked area and domain contacts get a section; a contact's cross-domain questions are
  grouped under the domain's name. Each person: open questions (pill: ready to send / waiting Nd / later), then "Their action items N"
  (collapsible, with "due" and "N to send" tags). Header: **Copy N** and **Mark sent**, plus **Send** when the person has a
  channel configured in `how_to_reach` (it creates a draft that waits for approval like any other).
- **Copy** builds one message: greeting with first name, questions first (numbered when several), then "Action items with you:"
  as a list with project and due date, then one closing line. No title-then-same-text repetition.
- Action rows: due pill, text, status, "to send" / "sent · Nd", and buttons: Mark sent (when unsent), Followed up, They finished
  it (Mark done for the PM's own), Reassign (name picker with full names), "Take care of this" for the PM's own.
- **By group:** actions with each project's open questions, copyable per group, per project or all. Notices don't appear as
  questions here.
- Question rows: Mark sent, Record reply, Respond to the assistant; decisions: Answer, Respond to the assistant.

### 7.6 Interaction rules

- Compact rows; details in hover tooltips on the status pill.
- No one-click destructive or closing control without a label; closing things that are hard to reopen asks for confirmation.
- Anything with more than one item renders as a list; stored text uses line breaks, and the UI renders "- " lines as nested
  bullets and "Label: url" as a named link.
- Copyable text stays clean: no approval or provenance notes inside what the PM pastes.
- One row per thing: never show the same work in two cards.
- Never answer with an instruction the screen can't carry out: every message, error and empty state either offers a button
  that does the next step or says what the app is already doing about it.
- Labels in plain words; no internal ids in anything the PM reads. Labels that name the assistant, people or groups come from
  config.

---

## Part 8. Lessons as product rules

Each rule came from a real mistake. The guard column says where the product enforces it. These are core rules; rules that only
apply to the reference pack are in 9.5.

### 8.1 Publishing and content

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
| Restricted inputs stay off open outputs and outside messages | restriction field, applier check |
| Locale spelling everywhere except verbatim quotes | language config |
| The model's name never appears in user-visible text | language config, applier and UI tests |
| Check every URL responds before putting it where the PM clicks | link checker in the self-check |
| Nothing goes out without approval of that exact content, including scheduled posts | publisher content-hash check |

### 8.2 Questions

| Rule | Enforced by |
|---|---|
| Asking is a core feature: anything the automation can't settle becomes a question, never just a log line | jobs call the questions service |
| Look it up before asking a person (creators, editors, text, status) | `lookup` op and lookups |
| Dates a published schedule holds are looked up, never asked: the release from the tracker, its date from the delivery team's schedule; no release yet means TBD | `config/facts.yaml`, applier fact check |
| Question ids never repeat; a closed question's id is retired | id counter in the storage layer |
| Every question links what it names | applier |
| A question to someone else says only what they need to answer: no bookkeeping, no options about how your outputs are organized, no long quotes of their own words, only links they can open, the whole gap in one ask | applier link and label checks, AI rules |
| Unsure who it goes to: the PM routes it first | questions service hold |
| Decisions are questions addressed to the PM, by recipient | questions service, Today, check-up |
| Only the tracked area gets detailed questions; other areas are observed, not chased, even when minutes or program pages name their people | applier scope check, scope sweep |
| A question about another area's work goes only to that area's contact, only about the effect on our work, one batched message per contact | applier scope check, `cross_domain` config |
| A question asked in the conversation it came from is filed as asked | AI rules |
| When an answer arrives, re-check every open question to that person | answer flow |
| When an input answers questions, close them; search sources before filing a new one | packet includes open questions |
| Don't flood: an outage is one issue, not N questions | watcher outage rule |

### 8.3 Actions and owners

| Rule | Enforced by |
|---|---|
| Extract every action from raw notes and minutes, one per owner and task, counted against the source | AI rules, packet check |
| Before adding an action, search open and done actions for the same deliverable | applier near-duplicate warning |
| When an input completes actions, close them across every related project | packet lists open actions with keys |
| Action owners are people, in the workspace's owner format | applier, names normalizer |
| Actions go only to people in the tracked area or the PM; another area's work is a fact, not an action | applier scope check, scope sweep |
| Separate who did it from who reported it | actions service |
| A nudge isn't a completion | Followed up vs They finished it |
| Each follow-up the PM owns after a meeting is its own action; files they send are linked where they can open them | AI rules, meeting template |
| Three kinds of to-do stay apart: meetings, owned follow-ups (actions), things to ask (questions) | data model, applier routes misfiled ones |

### 8.4 Knowledge

| Rule | Enforced by |
|---|---|
| Everything learned is written down in the same step: facts in records, people in people data, rules in rules.md, rationale in decisions.md | AI rules, applier ops for each |
| Every input shows in What changed with what was done with it | inputs always produce a note |
| Data files feed outputs: changing the data re-renders the output in the same step | renderer hooks per record type |
| Pull others' edits before re-rendering, where the channel allows it | publisher pulls first |
| One writer at a time per workspace; re-read before every write | file locks, merge-on-save |

### 8.5 Time

| Rule | Enforced by |
|---|---|
| "This week" means through the configured week end (e.g. Friday), one helper everywhere | calendar config |
| Date inputs from the day received, not the day discussed | `source` op |
| Store zoned times; never slice a timestamp string | storage layer |
| Per-team non-working days count for that team's dates | calendar config |

### 8.6 Automation robustness

| Rule | Enforced by |
|---|---|
| Rules before AI: most changes are no-ops; deterministic rules close them | triage |
| Never let two versions of one change race | supersede |
| A run that produced nothing is retried, then goes to the PM | dispatcher attempts |
| A usage limit is a pause until reset, not a failure loop | AI adapters' `classify_error` |
| Switching AI vendor or model is a config change, approved by the PM after an evaluation run | provider layer, evaluation |
| Restricted inputs only reach AI providers and plugins allowed to see them | `allowed_data`, plugin `data_levels` |
| Error output is cleaned and short; the raw output is one click away | API error shape |
| Saves merge, never clobber | storage layer |
| Recover by itself after sleep or network loss | scheduler |
| A proposed code change never goes live unseen | fixer + Apply |
| A fix applies by three-way merge, not a staleness check; only a real conflict stops it, and then it is redone | fixer |
| A change request becomes a code fix only when no op can do it; data that needs a new op waits for the fix | `dev.request` validator, fixer |
| A rename is one op that updates every place the name is stored and keeps the page | `record.rename`, reference index |
| A failing plugin is an issue, not an outage | plugin host |

---

## Part 9. Reference pack: workplace PM

The use this design came from, built as a pack (`plugins/workplace-pm/`) on the core. It is the first pack built and the main
test that the core is complete. Everything here is generic for workplace status reporting; the organization's specifics still
live in a workspace.

### 9.1 The use

A PM supports a busy leader (an architect, a director) who owns a portfolio of projects. Status lives on wiki pages, work lives
in an issue tracker, decisions happen in meetings, chats and email. The leader reads published status pages and dashboards; key
players receive questions and action items as paste-ready messages.

### 9.2 What it needs from other plugins

Connectors of kind wiki (pages and trees, history, recent edits by person), issue tracker (queries, items with changelog),
release tracker (optional) and shared files; a channel of kind wiki page (versioned, pull-edits). The pack depends on these
kinds, not on one vendor: a wiki vendor's connector and channel live in their own plugin.

### 9.3 What it registers

- **Config** (`config/plugins/workplace-pm.yaml`): `leader` (full name, account usernames on each connector, to find their recent
  work), the grouping label ("Program"), sub-groups, `publish` targets (summary page, project pages, archive) and the dashboard
  readers to keep compatible with.
- **Record fields** on `Project` (`ext.workplace-pm`): sub-program, delivery team, delivery lead, tracker keys; risks gain
  `owner_team`.
- **Renderers and templates:** the summary page (rows roll up from project pages), project pages, the archive.
- **Triage defaults:** the `container-not-mapped`, `owner-not-ours` and `child-item` rules pre-filled for page trees and
  tracker sub-tasks.
- **Fact defaults** (`config/facts.yaml`): `ship_release` (from the delivery tracker, else the tracker item's sprint or fix
  version) and `production_date` (from the delivery team's schedule page, one per delivery team); no release yet means TBD.
- **Routing defaults:** program-date questions observed, not asked; dates never asked of release or delivery people.
- **AI task kinds:** `workplace-pm/checkup-goals` and `workplace-pm/status-update` with their prompt templates.
- **Panels:** portfolio health by program, milestones to check.
- **Today lines:** dashboard drafts waiting, milestones to check this week.
- **Workspace defaults it suggests:** `owner_format: "{team} ({full_name})"`.

### 9.4 Fictional demo setup

Both fictional workspaces enable the pack with different organizations, programs, people and vocabulary, a fake wiki and a fake
tracker backed by fixtures.

### 9.5 Pack-specific rules

| Rule | Enforced by |
|---|---|
| Name teams, not individuals, as owners of risks (actions are different: actions name a person) | pack op validator on `risk.add` |
| Owners are "Team (Full Name)" | suggested `owner_format`, names normalizer |
| Don't chase program milestones run by other PMs or things the leader doesn't own | pack's default `scope.yaml` entries |
| The leader shouldn't have to confirm routine updates | routing defaults |

---

## Part 10. Guardrails against embedding specifics in code

The failure to prevent: while building for one deployment, every rule a user states ends up as a hardcoded name, team, URL or
`if` in the engine, with the user's quote as a comment. After a few weeks the "generic" code is unusable anywhere else. The
plugin system adds a second failure to prevent: the core growing special cases for one plugin.

### 10.1 The boundary

- **Core code** (`engine/`, `api/`, `web/src/`) may reference only concepts: project, record, person, team, change, source,
  question, action, draft, channel, connector, plugin, rule. Never a specific person, team, organization, product, program,
  system, host, URL or page id, and never a vendor or service name outside `engine/ai/adapters/`.
- **Bundled plugins** may name the product or vendor they connect to, inside that plugin only. They never hold an
  organization's specifics.
- **Workspaces** (config and data, outside this repository) hold every deployment specific.
- **Private plugins** (`<workspace>/plugins/`) may be specific to that deployment and never enter this repository.
- **Deploy recipes** (`deploy/<target>/`) may name their hosting platform. They never contain a user's domain, account or
  secrets; examples everywhere use `example.com`.
- **Rationale** lives in `docs/decisions.md` (product) or the workspace's `docs/decisions.md` (deployment): dated entries with
  what, who decided and why. Code comments explain what the code does in general terms; they never quote a user or carry a date.

### 10.2 Enforcement (automated, part of the test suite and the self-check)

1. **Specificity scan:** reads every name, alias, team, org, group, system name, URL host and page id from the fictional
   workspaces, and with `--workspace <path>` from a private workspace too, and fails if any appears in core code, bundled
   plugins, tests outside fixtures, or UI source. Findings from a private workspace print only file and line, never the matched
   value, so a scan log can't leak it.
2. **Provider scan:** fails if an AI vendor or model name (from the adapter registry and `config/ai.yaml`) appears anywhere
   outside `engine/ai/adapters/`, AI adapter plugins, config, fixtures and docs.
3. **Pattern scan:** fails on URLs (except in config, fixtures and docs), on comments matching dated-decision patterns ("(Name,
   10/8)", "per X", "X said"), and on capitalized multi-word names in code that aren't in the list of concept words. That list
   holds generic concept words only; a flagged name moves to config or data, it is never added to the list.
4. **Config coverage:** every config key used in code exists in the schema with a default and a description; every schema key is
   used somewhere. Same for each plugin's config.
5. **Boundary scan:** core code imports nothing from `plugins/`; plugins import only `engine.plugin_api` from the engine; no
   core code tests for a plugin's name.
6. **Two workspaces, and core alone:** the suite runs against both fictional workspaces, and once with no bundled packs enabled
   (core plus the fake connector, fake channel and clipboard), so anything that only works for one dataset or one pack fails.
7. **Manifests:** what each plugin registers matches its manifest; declared network hosts, secrets and data levels are the only
   ones it uses.
8. **UI labels:** user-visible strings that name the assistant, people or groups come from config; a test renders the UI against
   both fictional workspaces.
9. **Deployment:** hosting platform names appear only in `deploy/` and docs; every recipe's profile passes the deploy checks
   (11.5); the UI and API tests run under the root path and under a nested base path.

### 10.3 Process (for every requirement)

Before writing code, answer and state in the change description:

1. Is this a concept (core), an extension (plugin, or a new generic extension point), a setting (config), a fact (data), a
   standing instruction (rules.md) or custom to one deployment (private plugin)?
2. If config: the key name, schema, default, and the example value for both fictional workspaces.
3. The decisions.md entry (date, who, what, why), product or workspace.
4. The generic test, run against both fictional workspaces.

When a user states a rule in passing ("don't ask the program manager about program dates"), the default home is config (a scope
or routing rule) or rules.md, not code.

### 10.4 Review checklist (every change)

- No new specific in core, API, UI or bundled plugin code; the scans pass.
- New behavior has a config key with a default, is a pure concept, or is a plugin.
- No special case for a plugin in the core; a missing capability became a generic extension point.
- Rationale went to decisions.md, not a comment.
- Both fictional workspaces pass, and the core passes alone.

---

## Part 11. Deployment

The same code runs on the PM's own computer or on a web host. What differs is configuration (`config/server.yaml`,
`config/auth.yaml`, `config/storage.yaml`, a profile) and packaging (`deploy/`). Nothing in the engine, API or UI checks which
host it is on; every difference is a setting the code reads, tested both ways.

### 11.1 Modes

| | Local | Hosted |
|---|---|---|
| Where it runs | the PM's computer | a server, a container platform, or a machine behind a tunnel, reached at the PM's own domain |
| Who can reach it | only this machine (`127.0.0.1`) | anyone on the internet who gets past sign-in |
| Sign-in | an install token handed to the browser at launch; a password optional | required: at least one provider from 11.4; passwords need a second factor |
| Storage | files in the workspace folder | files on a persistent volume, or another backend; snapshots pushed to a private remote |
| Scheduler | runs while the computer is awake; catches up after sleep (6.14) | runs continuously; one scheduler at a time |
| Command-line AI agents | available if installed | only if the image includes them; capability routing falls back otherwise |
| Start-up checks | config validation | config validation and the deploy checks (11.5); start is refused if any fail |

### 11.2 Serving under a path, and hiding

The app can live at the root of its own domain or under a path on a site that serves something else: for example
`https://example.com/admin` while the public site stays at `https://example.com/`. `server.base_path` sets it. What makes that
work without code changes:

- The UI is built with relative asset paths and reads its base path and API address from a small config document the server
  returns, so one build works under any path.
- Every route, redirect, cookie path and generated link is built from `public_url` and `base_path`. Tests run the UI and API
  both at `/` and under a nested path.
- A reverse proxy in front (the host's routing rules, a tunnel, a web server) forwards only that path to the app; the rest of
  the site never reaches it.

**Hiding** (`server.hide: not-found`) makes the app answer 404 to anyone not signed in, except at the sign-in path, which can be
set to something hard to guess. It also sends `noindex`. Hiding cuts noise from scanners; it is not protection. Sign-in (11.4)
and the deploy checks (11.5) protect the app, and hosted mode never relies on hiding alone.

### 11.3 Deploying without code changes

Everything in this part is set through config files, environment variables or flags (4.0), so a hosting platform's settings
page is enough: `COCKPIT_PROFILE=hosted`, `COCKPIT__SERVER__PUBLIC_URL=https://example.com`,
`COCKPIT__SERVER__BASE_PATH=/admin`, and secrets stored as platform secrets and referenced by `env:` names.
`cockpit init --profile hosted` writes a starting profile with every key commented, and `cockpit deploy check` lists what is
missing before the first start.

### 11.4 Sign-in

Sign-in methods are auth providers, an extension point (3.3). The core ships:

- **Install token:** the default in local mode. A random token is created at install and handed to the browser when the PM
  starts the app. Not accepted as the only method in hosted mode.
- **Password with a second factor:** passwords hashed with a memory-hard algorithm (argon2id); one-time codes from an
  authenticator app; passkeys (WebAuthn) as a second factor or instead of the password. Recovery codes shown once at setup.
- **Sign-in provider (OpenID Connect):** any standard provider, configured by issuer, client id and a client secret reference;
  only identities listed in `auth.users` get in.
- **Identity-aware proxy:** for hosts that put their own access gateway in front. The app verifies the signed token the proxy
  adds (signature against the proxy's published keys, issuer, audience, expiry, all from config); it never trusts a plain
  header naming the user. Best combined with an app sign-in, so one misconfiguration doesn't open the app.

**Sessions:** secure, HTTP-only, same-site cookies scoped to the base path; idle and absolute timeouts; sign out everywhere.
Every state-changing request carries a CSRF token. Failed sign-ins are rate limited and locked out per `auth.lockout`. Every
sign-in and failure is logged and shown on the Security panel (7.1).

### 11.5 Deploy checks

`cockpit deploy check` runs these; the self-check runs them against both fictional workspaces with a hosted profile; a hosted
server runs them at start and refuses to serve if any fail.

- `public_url` is HTTPS, and requests arrive over HTTPS (directly, or from a trusted proxy that says so).
- At least one provider other than the install token is enabled; passwords require a second factor; at least one user is
  listed.
- The session signing key comes from a secret, is long enough, and isn't a default.
- Every secret reference resolves, and no secret value appears in any config file.
- `allowed_hosts` and `trusted_proxies` are set; CORS is off or limited to listed origins; security headers are on.
- Storage is persistent (the backend reports it) and the last snapshot succeeded; a snapshot remote or backup is configured, or
  the PM has explicitly accepted running without one.
- `public_url` and `base_path` agree with what the proxy forwards (checked by fetching the app's own health address through
  `public_url`).
- No enabled plugin declares a network host or data level the deployment's settings forbid.

Warnings that don't block start: command-line AI agents unavailable, budgets unset, only one sign-in method (no fallback if it
breaks).

### 11.6 Packaging and recipes

The engine needs long-running jobs, a file system and git, so it runs as a process or a container, not as short-lived edge
functions.

- **Local:** `cockpit serve --workspace <path>` starts everything and opens the browser with the install token. Optional
  start-at-login service files for each operating system.
- **Container image** (`deploy/container/`): one image with the API, the built UI and the scheduler; runs as a non-root user;
  the workspace on a mounted volume; configured only through environment variables and mounted config. Every hosted recipe
  builds on it.
- **Recipes** (`deploy/<target>/`): one folder per hosting target, with its profile, any platform config files and a
  step-by-step README, plus a test that the profile passes the deploy checks.

First recipes, in order:

1. **Tunnel to a machine the PM owns:** the app runs on the PM's computer or a small always-on box. A tunnel publishes only
   `public_url` + `base_path`, without opening ports, and the tunnel provider's access gateway sits in front (the
   identity-aware proxy provider), plus the app's own sign-in. For example: Cloudflare Tunnel, with Cloudflare Access protecting
   only the `/admin` path of a domain whose public site is served elsewhere. File storage and git stay as they are.
2. **Container host:** the image on a platform with a persistent volume (a small virtual server behind a reverse proxy, or a
   container service). Cloudflare's container service can run the image, but at the time of writing its container disks don't
   persist, so it needs a storage backend other than local files (4.15); check the platform's current limits when writing
   that recipe.

The UI build can also be served from a static host with the API elsewhere (it reads its API address from config), but that is
not a first recipe.

---

## Part 12. Security and privacy

- **Two modes, one model.** Local mode listens on `127.0.0.1` and uses the install token. Hosted mode requires real sign-in and
  passes the deploy checks before it serves (Part 11). Roles for several users are later; in the base, everyone allowed in has
  full access.
- **Secrets** come from the environment, the OS keychain or a mounted file, referenced in config as `env:NAME`,
  `keychain:NAME` or `file:/path`, never stored in config or data. Hosted platforms pass them as environment secrets. Plugins
  get only the secrets their manifest names.
- **Outbound is gated twice:** content leaves only through the publisher after approval (8.1), and network calls from plugins go
  through the host's HTTP client, limited to the hosts each manifest declares.
- **Data levels** (open, internal, restricted) follow every source into packets, AI providers and plugins (6.16, 3.5).
- **Audit:** every changeset, approval, send, settings change, sign-in and plugin enable or disable is logged in the workspace
  and kept in its git history.
- **Plugins run in-process** in the base, so enabling a third-party plugin means trusting its code; the Admin tab shows what each
  plugin may reach before it is enabled. Running untrusted plugins in a separate process is a later step.
- **Internet-facing hygiene** (hosted): dependencies pinned and scanned in CI; the container runs as a non-root user with a
  read-only file system apart from the workspace volume; uploaded files are stored as data, never executed, and served only as
  downloads.

---

## Part 13. Build plan

Each milestone ends with tests passing against both fictional workspaces, the core passing alone, and the scans green.

1. **Skeleton, guardrails and the plugin host:** repository layout (2.2), tooling (uv, ruff, pytest, Vite, Vitest), config
   schemas with defaults, config layers (defaults, files, environment, flags, profiles) and `cockpit config show`,
   `engine.plugin_api` with registries for every extension point, manifests, the event bus, the scans and the self-check, both
   fictional workspaces, the fake plugin, and `cockpit serve` in local mode with the install token and base path support.
2. **Records and rendering:** core record types and `ext` fields, templates, render-time ordering, roll-ups, drafts, the
   clipboard channel and the fake page channel.
3. **Changesets and the applier:** op registry (core and plugin ops), generated JSON Schema, validation, normalization, backup,
   apply, undo, logging, classification.
4. **Watchers, triage, supersede:** fake connectors with fixture changes; the matcher registry; the auto-closed list.
5. **Dispatcher and the AI provider layer with a stub adapter:** the `AiTask` contract, task-kind registry, adapter interface,
   capability routing, `Run` records; the stub adapter turns fixtures into changesets from templates, so everything runs with no
   AI account.
6. **UI part 1:** shell (branding from config, working under any base path), panel registry with declarative panels, What
   changed, Waiting to go out with the diff renderer, the Settings panel generated from the config schemas.
7. **Questions and actions:** services, notices, names normalizer and sweep, Follow-ups by person and by group, Reassign.
8. **Publisher:** dry run, content-hash approval, scheduled drafts, concurrency check (fake channel first).
9. **The reference pack** (Part 9) on the fictional workspaces, using only the plugin API. Anything it needs that the API lacks
   becomes a generic extension point, not a special case.
10. **A second, small pack** (personal projects) to prove the extension points serve a different kind of work.
11. **Real AI adapters and the evaluation harness:** the first vendor's API adapter and a command-line agent adapter, error
    classification, budgets, data-level routing; the golden fixture set and `evaluate`. A second vendor's adapter later needs no
    change outside its adapter and `config/ai.yaml` (a test proves it with two adapters).
12. **Governor, scheduler, offline behavior, issues and the fixer.**
13. **Hosted deployment:** auth providers (password with a second factor, passkeys, OpenID Connect, identity-aware proxy),
    sessions, CSRF, lockout, hiding, the deploy checks, the Security panel, the container image and the first two recipes.
14. **Today builder, meetings, weekly check-up, update writer.**
15. **Real connectors and channels** (one wiki, one tracker) as plugins, configured only through config.

**Plugin API 1.0** is declared when both packs run on it unchanged. Until then it is 0.x and may change.

**After the base** (each a pack, plugin or recipe, in whatever order is useful): publishing support, social media channels,
mailbox and calendar connectors, more AI vendors, more deploy recipes and storage backends, running untrusted plugins out of
process, roles for several users.

---

## Ground rules for this build

- Built from this description only. No code, files or data copied from any real deployment.
- Fictional demo data only.
- Check your employer's policy on outside projects before building, and again before selling or publishing.
