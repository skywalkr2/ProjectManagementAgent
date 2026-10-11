# Part 3. Plugin system

The plugin system is what makes the core a base. Build it before the first pack (Part 13) and build both packs on it, so the
first real use proves the extension points instead of bypassing them.

## 3.1 Kinds of plugins

- **Bundled plugins** (`plugins/` in this repository): generic for their domain, tested in CI against both fictional
  workspaces. A connector, channel or AI adapter may name the product or vendor it connects to, inside its own plugin only.
- **Installed plugins:** Python packages anyone publishes, found by entry point. Same manifest, same API, same rules.
- **Private plugins** (`<workspace>/plugins/`): may hold specifics of that one deployment. Never committed to this repository.
- **Packs:** any of the above that bundles record types, ops, templates, prompts, panels, Today lines, jobs and default config
  for one kind of work. A pack may depend on other plugins (its connectors and channels) and on interfaces, never on one
  vendor's connector when an interface will do.

## 3.2 Manifest

Every plugin has a `plugin.yaml`. The host reads it before importing any code, so the PM can see what a plugin does and what it
may reach before enabling it.

```yaml
name: personal-projects
version: 0.1.0
plugin_api: ">=1.0,<2"            # plugin API versions this plugin works with
description: Track side projects with goals, next steps and a weekly review.
depends_on: []                    # other plugins it cannot work without, with version ranges
interfaces:                       # how it works with other plugins, only through the core (3.9)
  defines: []                     # interfaces this plugin defines for others, e.g. [publishing/manuscript-source]
  provides: []                    # e.g. [publishing/title@1]
  uses: []                        # e.g. [{interface: publishing/title@1, optional: true}]
subscribes: []                    # core and interface events it reacts to (3.4), e.g. [stage.moved]
provides:                         # checked against what the code registers
  record_types: [personal-projects/goal]
  ops: [personal-projects/goal.add, personal-projects/goal.update]
  ai_task_kinds: [personal-projects/weekly-review]
  panels: [personal-projects/goals]
  today: [personal-projects/goals-due]
  jobs: [personal-projects/weekly-review]
  playbook: playbook/              # 3.8
config_schema: personal_projects.config:Settings
requires:
  network: []                     # hosts it may reach; empty means none
  secrets: []                     # secret names it reads (values come from env or keychain)
  data_levels: [open, internal]   # the most sensitive inputs it may see
  tools: []                       # programs it runs, e.g. [{name: java, min_version: "17", probe: "java -version",
                                  #   optional: true, features: [<plugin>/advanced-validator]}]
entry: personal_projects:register # called with a registrar from engine.plugin_api
```

Identifiers that aren't core are namespaced `<plugin>/<name>`, so two plugins never collide and every op, record or panel shows
where it came from.

## 3.3 Extension points

| Point | What a plugin adds | Interface (sketch) | Plugin API |
|---|---|---|---|
| Connector | an input source | `poll(state) -> changes`, `fetch(ref)`, `search(query)`, `capabilities()`; typed errors: no-access, not-found, outage, auth | 1.0 |
| Channel | an output target | `current(target)`, `diff(current, draft)`, `send(approved_draft)`, `verify(result)`, `lock_status(target)`, `capabilities()` (versioned, pull-edits, external-editors, schedule, length limits, media) | 1.0 |
| Record type | a kind of thing to track, or extra fields on a core record | a Pydantic model, its table, display labels, migrations, the ids it stores (for merges and deletes) | 1.0 |
| Op type | a changeset operation | tier (data, outbound, system), required fields, `validate`, `normalize`, record types it may write, `apply`, `describe` (one readable line) | 1.0 |
| Op validator | extra checks on an existing op, core or plugin | `validate(op, workspace) -> problems` (can refuse, never modify; a refusal counts as an invariant failure, so it must be deterministic, 6.16) | 1.0 |
| Text format | how a `long_text` format divides into units (paragraphs, fenced blocks, multi-paragraph footnotes, poems) | `units(text) -> spans`, each span with a kind and whether it is atomic (never split or merged); pure and deterministic; the spans must cover the text exactly, in order, with nothing overlapping, which the core checks | 1.0 |
| Lint | a soft check computed in code (a rate per 1,000 words against a measured profile, say) | `lint(op, workspace) -> problems`, each with a lint id, the passage it points to (a range or paragraph id) and guidance; severity from `config/checks.yaml` (4.17) with the plugin's default | 1.0 |
| Working-copy format | a file format people edit long text in with their own tools (5.0) | `hand_out(record, field, version) -> file` and `take_back(file, base_version) -> text, unmapped`: deterministic, no AI; anything it cannot map is reported, never dropped | 1.0 |
| Triage matcher | a rule kind for `config/triage.yaml` | `match(change, params) -> reason or None` | 1.0 |
| AI adapter | a kind of AI account: a vendor's native API, an aggregator, or an agent | `models()` (with the parameters each model accepts), `run()`, `classify_error()` (the only code that reads the vendor's error text), `sign_in_hint()` (how the person signs back in), `health()`, and for agents `lockdown_test()` (6.16) | 1.0 |
| Text extractor | text from a file type (documents, spreadsheets with comments, presentations with tables and speaker notes, PDFs) | `extract(file) -> text, notes`; the core ships the common office formats | 1.0 |
| AI task kind | a new kind of AI work | packet builder, output (ops, or a draft for a `long_text` field, 6.7), the ops it may use (its output schema is generated from them), required capabilities, independent review or not, typical cost, default prompt template, default tier and parameters | 1.0 |
| Renderer | how records become content for a channel | template files, optional render function | 1.0 |
| Lookup | a fact the AI can ask the engine to fetch | `lookup(query) -> result` | 1.0 |
| Stages | the steps a record type moves through | ordered stages with entry checks and what each starts (6.26), defaults for `config/stages.yaml` | 1.0 |
| Panel | a UI view | declarative view spec (7.2); bundled plugins may also ship a React component | 1.0 |
| Today contributor | lines on the Today list | `lines(workspace) -> [TodayLine]` | 1.0 |
| Job | scheduled work | name, default schedule, needs network, `run()` | 1.0 |
| Interface | a versioned contract other plugins can use: record fields to read, events, task kinds to request (3.9) | declared in the manifest; the shape is a schema checked by the host | 1.0 |
| Event handler | a reaction to a core or interface event | `subscribe(event, handler)` (3.4) | 1.0 |
| API route | extra endpoints | mounted under `<base path>/api/plugins/<plugin>/` | planned |
| Auth provider | a way to sign in | `begin(request)`, `complete(request) -> identity or refusal`, `capabilities()` (11.4) | core only |
| Storage backend | where records and sources live | the repository layer: transactions, versions, ledger, leases, export (5.0, 4.15) | core only |
| Playbook | built-in practice for its kind of work: guidance, default rules, checklists, glossary, lints, evaluation cases | a `playbook/` folder (3.8) | 1.0 |
| Check | the plugin's own self-check | `check() -> problems` | 1.0 |

**Plugin API column:** `1.0` points are the ones the two bundled packs (publishing and workplace PM, Part 9) use; they are
built, tested from a plugin and frozen at plugin API 1.0. `core only` points exist as internal registries the core uses for its
own sign-in methods and storage, opened to plugins later. `planned` points are designed here but not built until a plugin needs
them, so nothing is frozen on a guess.

A new extension point is added to the core when a plugin needs something none of these provide. It is generic, documented here,
and covered by a test that uses it from a plugin.

## 3.4 Events

The core uses an internal event bus from the start, and plugins subscribe to it through the manifest (3.2). The core
publishes events after each step: `source.saved`, `change.filed`, `change.closed`, `request.queued`,
`changeset.applied`, `changeset.undone`, `record.changed`, `draft.created`, `draft.approved`, `draft.sent`, `question.asked`,
`question.answered`, `action.added`, `action.closed`, `problem.opened`, `job.finished`, `stage.moved`, `text.accepted`.
`record.changed` carries the record kind and id, the fields changed, the new version and the op that changed it.
`text.accepted` fires when a new version of a `long_text` field is written by `text.accept` (6.7), with the record, field, new
and previous version, where it came from (assistant draft, proposed version, or a direct edit) and its authorship summary. Interfaces add their own
events (`publishing/title.date_changed`), published by the core when the providing plugin's op applies.

Handlers may read, queue requests, file questions and open automation problems. They may not write records directly; anything that changes
knowledge goes through an op and the applier.

## 3.5 Rules every plugin follows

Enforced by the plugin host, the applier, the publisher and the self-check:

- **Writes go through the applier.** A plugin changes knowledge only through ops, and an op's apply function touches only the
  paths it declared.
- **Sending goes through the publisher.** A channel's `send` is called only by the publisher, only for a draft whose content
  hash matches the PM's approval. No plugin API hands out a way to send.
- **Reach is declared.** Network hosts, secrets and data levels come from the manifest and are shown to the PM before the
  plugin is enabled. The core enforces them on what it hands out (its HTTP client, its secret store, the records and packets
  it passes), but in-process code is not sandboxed: enabling a third-party plugin means trusting its code (12.3).
- **Programs are declared.** A plugin runs outside programs only through the plugin API's `run_tool`, only for tools in
  `requires.tools`, with a timeout and no shell. The enable screen and the self-check probe each declared tool and show what is
  missing; a missing required tool keeps the plugin off, a missing optional one turns off only the features listed with it.
- **Config is like core config.** `config/plugins/<plugin>.yaml`, with a schema, defaults and descriptions.
- **Plugins meet only through the core** (3.9): interfaces, events and shared core records. A plugin never imports another
  plugin, reads its tables or calls its code.
- **Code against the API, not the internals.** Plugins import only `engine.plugin_api`. The plugin API follows semantic
  versioning; a breaking change is a new major version.
- **Failures stay contained.** A plugin that raises becomes an automation `Problem`; the core and other plugins keep running. Disabling a
  plugin stops its jobs and hides its panels, and keeps its data on disk.
- **Bundled plugins ship demo config and data** for both fictional workspaces and pass the suite against both.

## 3.6 Lifecycle

- **Enable** in `config/workspace.yaml` under `plugins.enabled`. At startup the host reads manifests, checks plugin API versions
  and dependencies, validates each plugin's config, then calls `register`.
- **Upgrade:** record schema and config changes ship as migrations (4.0). The export is committed first and the database is
  backed up; a failed migration restores the backup and opens an automation problem.
- **Disable:** jobs stop, panels hide, records stay. Re-enabling picks up where it left off.

## 3.7 Worked examples

These show that the extension points cover the uses in view. They are not commitments; each is a pack built later.

| Use | Connectors | Channels | Record types and ops | AI task kinds | Panels and Today |
|---|---|---|---|---|---|
| Workplace PM (reference pack, Part 9) | wiki, issue tracker, release tracker, shared files | wiki pages; clipboard messages | portfolio fields, risks with owner team, milestones | weekly check-up goals, status updates | portfolio health by group, milestones to check |
| Publishing support | manuscript folder, submissions tracker, mailbox | email to editors and agents, newsletter, blog | manuscript, submission, calendar entry | query letter draft, read a submission reply | submissions by status, editorial calendar |
| Personal projects | notes folder, calendar feed | clipboard, notes file | goal, next step | weekly review | goals, this week's next steps |
| Social media | account mentions and replies | posts per network, scheduled after approval | post, campaign | draft a post, summarize replies | post queue, replies waiting |

If a planned pack needs something no extension point provides, add a generic extension point to the core. Never special-case a
pack in the core.


## 3.8 Playbooks

A playbook is the built-in know-how for one kind of work: what good looks like, written down so every run uses it. The core
ships one for **project support** in general; every pack ships one for its field (the publishing pack for bringing a title to
launch, 9.7). The PM's own rules (`config/rules.yaml`) sit on top of both.

**What a playbook holds** (`<plugin>/playbook/`, or `engine/playbook/` for the core):

| Part | What it is | Example (core) |
|---|---|---|
| `guidance/` | practice notes for the AI, one file per task kind or topic | how to pull every action out of minutes; how to write a question its reader can answer in one reply |
| `rules.yaml` | default standing rules, same format as the workspace's (4.10), each with an id | "record who raised each risk" |
| `checklists/` | templates the PM can start from | a weekly review; a meeting prep list |
| `glossary.yaml` | seed terms for the field | (publishing) galley, ARC, ISBN, print proof |
| `lints.yaml` | soft checks for the field, with default severities (6.7) | an action phrased as "confirm" or "check whether" |
| `evals/` | fictional cases showing the practice applied | minutes with six actions, two of them shared |

**Layers:** core playbook, then pack playbooks, then the workspace's rules. Later layers win. Each entry has an id, so the PM can
switch one off or replace it (`config/playbooks.yaml`, 4.19). A read-back (6.7) shows when a new rule overlaps a playbook entry,
just as it does for other rules.

**Where it goes in a run:** the entries that apply to a task kind go into the stable part of the packet (6.6), after the
instructions and before the glossary and rules, so they are cached with it.

**How playbooks stay generic and get better:**

- Playbook text is scanned like code and prompt templates (10.2): no names, organizations, sources or vendor names, except a
  vendor's own plugin describing its own product.
- Playbooks are versioned with their plugin and changed by releases, never edited in a workspace.
- When the rules review (6.21) sees a workspace rule that would help anyone in the field, it can propose it upstream as a patch
  and an issue for this repository, the same route as other reports to the maintainers (6.13). Lessons from real use become better defaults.

**Prompts and playbooks are different.** Prompt templates (`prompts/`) say how a task is done mechanically: the packet layout,
the output schema, how to use ops. Playbooks say what good practice is. A new pack usually needs a playbook and no new prompts.

## 3.9 Plugins working together

Packs are more useful together: a social media pack can announce a launch the publishing pack runs; a deal won in the sales
pack becomes a project to deliver. Plugins never import or call each other, so they meet only through the core, in four ways:

1. **Shared core records.** People, teams, projects, sources, actions, questions, facts, stages and budgets are core records
   every plugin sees (within its declared data levels). Plugin records link to them by id. A launch is one core `Project`;
   the publishing pack's title and the social pack's posts both link to it, so either can find the other's records without
   knowing their shape, and the PM sees one project with both packs' panels.
2. **Interfaces.** A plugin may provide a named, versioned interface (`publishing/title@1`): the fields of its records other
   plugins may read, the events it raises, and the task kinds others may request. The shape is a schema the host checks, so a
   provider can change its internals freely and must bump the version to change the contract. A plugin that uses an interface
   declares it, as required or optional; the host shows this to the PM before enabling, and gives the using plugin a
   read-only view of exactly those fields, never the provider's records. An interface can also be defined by the plugin that
   uses it, for others to provide: the publishing pack defines `publishing/manuscript-source@1`, so a folder connector or any
   installed or private plugin that produces finished manuscripts can start a launch.
3. **Events.** A plugin subscribes to core events and to the events of interfaces it uses (3.4). A handler may read, queue a
   request and file a question to the PM; it never writes another plugin's records. Any change goes through an op and the
   applier, as a changeset the PM sees when it comes from another plugin.
4. **Requests for another plugin's work.** A plugin may queue a request for a task kind another plugin's interface offers
   (the publishing pack's "short blurb in the imprint's voice"). It runs as that plugin's task, under its playbook, with the
   normal cost estimate and go (6.16) and the normal review.

**Optional means optional.** Each pack works alone. When both sides of an optional interface are enabled, extra actions
appear; when one is disabled, they disappear and nothing breaks. Records stay linked by id and come back on re-enabling.

**Publishing and social media, for example.** The publishing pack provides `publishing/title@1`: the title, contributors
(person ids), formats, launch date, approved cover and blurb, and the launch milestones. A social media pack uses it
optionally:

- When a title gets a launch date, "Plan the launch posts?" appears on Today. Planning creates posts linked to the same
  project, scheduled relative to the launch date, as drafts the PM approves.
- When the launch date moves, `publishing/title.date_changed` marks every post scheduled from it as a change to look over,
  instead of leaving them on the old dates.
- The social pack requests blurb variants from the publishing pack's task kinds, so the copy matches the approved blurb and is
  reviewed like any draft.

**Tested together.** CI runs every bundled pack alone, every pair that shares an interface, and the core with no packs, on
both fictional workspaces. An interface version that a user declares but no enabled plugin provides is a self-check failure
when required and a quiet absence when optional.

## 3.10 The define-your-own kit

The free version is the core plus a kit for defining one's own kind of work on screens, with no code (decisions,
2026-10-10). The kit is a bundled plugin, `kit`, built only on the plugin API, so it proves the API and needs nothing
special from the core.

**What a person defines** (kept in the kit's settings, `config/plugins/kit.yaml`, edited on settings screens, saved and
shared as one template file):

- **Item types**, such as a "deliverable", a "submission" or a "client request". Each has a name, a plural, an id
  prefix, and **fields** of the kinds text, long text, date, number, yes/no, choice (with its options), person (a person's
  id) and link. One text field is the title. An item may belong to a project.
- **Stages** for an item type, with a plain description each and entry checks chosen from a short list (a field is
  filled, a checklist is complete, a date has passed). They become the type's default stages (6.26).
- **Checklists** per stage: lines the person ticks.
- **What the assistant may fill**: the fields reading notes may set from inputs, always with evidence (6.7). The others
  only the person sets.
- **What Today shows**: items due within a number of days, items waiting at a stage, items missing a field.
- **The list screen** for each type: which fields are its columns, how it is grouped.

**How it works.**
- At start-up the kit plugin reads its settings and registers, for each item type:
  - a record type `kit/<type>`, with its layout in the synced folder (`<plural>/<title>`);
  - ops `kit/<type>.add`, `kit/<type>.set` and `kit/<type>.tick`;
  - its stages and stage checks;
  - a panel;
  - Today lines;
  - for the fields the assistant may fill, an op reading notes may use (a plugin op can be offered to reading notes),
    with evidence required.
- Settings are validated like every config file: a field kind the kit doesn't know, a choice without options, two
  types with one prefix, or a stage check naming a field the type lacks is refused with the reason.
- **Changing a type keeps the data.** Adding a field or an option is immediate. A field removed from the type is hidden,
  and its values stay in the records and the readable folder until the person deletes them. A field renamed in the
  settings is one change that renames it in every record. An item type with items can't be deleted, only hidden.

**Templates.** A template is the kit's settings plus a name and a description. Starting templates ship with the core in
`templates/`. A template is applied in the first-run wizard or later from settings; applying one to a workspace that
already has types adds the new ones and leaves the existing ones as they are. "Save as template" writes the current
settings to a file to share. The fictional demo workspaces run on templates.
