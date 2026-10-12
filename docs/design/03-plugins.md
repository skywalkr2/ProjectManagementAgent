# Part 3. Plugin system

The plugin system is what makes the core a base. Build it before the first pack (Part 13) and build packs on it, so real use
proves the extension points instead of bypassing them.

## 3.1 Kinds of plugins

- **Bundled plugins** (`plugins/` in this repository): the define-your-own kit (3.10) and the example plugin. They use only
  the plugin API, are tested in CI against both fictional workspaces, and ship settings and demo data for both. A connector
  may name the product or service it connects to, inside its own plugin only.
- **Installed plugins (add-ons):** Python packages anyone publishes, found by entry point. Same manifest, same API, same rules.
  Industry packs are add-ons in their own repositories; the Add-ons screen finds them and installs them (3.11).
- **Private plugins** (`<workspace>/plugins/`): may hold specifics of that one deployment. Never committed to this repository.
  A private plugin with the same name as an installed one wins, with a note on its status.
- **Packs:** any of the above that bundles record types, ops, templates, prompts, panels, Today lines, jobs and default config
  for one kind of work. A pack may depend on other plugins (its connectors) and on interfaces, never on one vendor's
  connector when an interface will do. One distribution may ship several plugins; they may share a helper package of their
  own, but no plugin imports another plugin's registered package or reads its records.

## 3.2 Manifest

Every plugin has a `plugin.yaml`. The host reads it before importing any code, so the PM can see what a plugin does and what it
may reach before enabling it. Unknown keys are errors, and what the code registers must match `provides` and `subscribes`
exactly. The manifest keys are listed in `docs/plugin-guide.md`, which is generated from the code and is the contract.

```yaml
name: personal-projects
version: 0.1.0
plugin_api: ">=0.3,<0.4"          # plugin API versions this plugin works with; 0.x minor versions may break
description: Track side projects with goals, next steps and a weekly review.
depends_on: []                    # other plugins it cannot work without: [{name, version}]
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
  data: data/                     # a folder beside plugin.yaml of files it ships; the workspace overrides them
config_schema: personal_projects.config:Settings
requires:
  network: []                     # hosts it may reach; empty means none
  secrets: []                     # secret names it reads (values come from env or keychain)
  data_levels: [open, internal]   # every data level its record types use
  tools: []                       # programs it runs, e.g. [{name: java, min_version: "17", probe: "java -version",
                                  #   optional: true, features: [<plugin>/advanced-validator]}]
entry: personal_projects:register # called with a registrar from engine.plugin_api
```

`provides` also takes `stages`, `stage_checks`, `op_validators`, `file_kinds`, `actions`, `lints`, `text_formats`,
`working_copies`, `derived_files`, `setup_steps`, `data_forms`, `connectors`, `triage_matchers`, `value_lists`, `sign_ins`,
`help` and `wording` (3.3). A plugin whose own settings define identifiers (the kit's item types) lists `<plugin>/*` for them.
`provides.playbook` is not yet available (3.8).

Identifiers that aren't core are namespaced `<plugin>/<name>`, so two plugins never collide and every op, record or panel shows
where it came from.

## 3.3 Extension points

Each row gives the call a plugin makes (or the manifest key), what it adds, and the plugin API version in which it arrived
(`docs/plugin-api-0.x.md` says what each version changed). Names are those in `docs/plugin-guide.md`.

| Point | What a plugin adds | How it is declared | Plugin API |
|---|---|---|---|
| Record type | a kind of thing to track, with its own fields | `registrar.record_type(Model)`: a `Record` subclass with an id prefix and a data level. It may declare person-only values, unique field groups, references (`RefTo`), value-list fields (`InList`), long text (`LongText`), a content-levels field and a layout in the synced folder. Extra fields on a core record are not offered: a plugin keeps its own record and links it by id | 0.1; data level, person-only, unique, references 0.2; long text 0.3.6; layout 0.3.14; value lists 0.3.42 |
| Op type | a changeset operation | `registrar.op(Model, tier, apply, notes=, candidates=)`. Tier is data or system (outbound is refused until the publisher exists). It writes only the plugin's own record types, through a writer limited to the fields it declares; `describe()` gives its one readable line; `notes=True` offers it to the reading of notes, with evidence for what it claims | 0.1; notes 0.3.20 |
| Op validator | extra checks on an existing op, core or plugin | `registrar.op_validator(op, fn)`: `fn(op, view, origin)` returns refusals. It can refuse, never modify; a refusal counts as an invariant failure, so it must be deterministic and quick (6.16) | 0.1; sees the changeset so far and the origin 0.2; gets settings 0.3.30 |
| Lint | a soft check computed in code (a rate per 1,000 words against a measured profile, say) | `registrar.lint(name, fn, ops=, severity=)`: findings with a message, the passage and guidance. Severity is return, warn or off, never refuse; the workspace's `config/checks.yaml` overrides it (4.17) | 0.3.5 |
| Stages | the steps a record type moves through, with entry checks | `registrar.stages(record_type, stages)` and `registrar.stage_check(id, fn)`: pure checks, never AI; a stage may apply to some records only (`applies_if`); defaults for `config/stages.yaml` (6.26) | 0.1; `applies_if` 0.3.23 |
| AI task kind | a new kind of AI work | `registrar.task_kind(name, ...)`: the ops its answer may use, or a draft for a long text field (`output="draft"`, anchored when it revises); its own prompt and guidance; the record it works on (`on`); a packet function saying what each run sees; a role (write, check or research); tier and output size defaults | 0.1 with the core prompt; own prompts, guidance, packets and `on` 0.3.2; drafts 0.3.7; anchored 0.3.9; roles 0.3.13; `all_or_nothing` 0.3.45; `requires_ops` 0.3.49 |
| Person action | deterministic work the person starts on a record, a file or the workspace | `registrar.action(name, label=, run=, on=)`: `run(target, context, choices)` returns one proposal of ops, new files, previews, named choices and notes. The person reviews it and what they approve applies as theirs, with one Undo | 0.3 |
| File kind | what a kind of uploaded file is for | `registrar.file_kind(name, details=, accept=, max_mb=)`: the details asked for when one is added and the media types it takes. Raises `file.added` | 0.3 |
| Declared program | an outside program the plugin runs | `requires.tools` in the manifest; `context.tools.run(name, args, files, timeout, collect=)` in person actions only. Found per computer, no shell, a fresh folder, capped output (3.5) | 0.3 |
| Text format | how a long text format divides into units (paragraphs, blocks, poems) | `registrar.text_format(name, units)`: pure, deterministic spans that cover the text exactly; atomic units are never split or merged. The core ships "plain" and "markdown" | 0.3.6 |
| Working-copy format | a file format people edit long text in with their own tools (5.0) | `registrar.working_copy(name, hand_out=, take_back=)`: deterministic, no AI. What it cannot map is reported, never dropped; the core refuses a format that does not read its own untouched file back to the same text | 0.3.11 |
| Derived file | a read-only file generated from records into each project's folder | `registrar.derived_file(name, path=, depends_on=, render=)` | 0.3.15 |
| Data files and forms | files a plugin ships (templates, word lists) that the workspace and a project can override; forms to edit them | `provides.data` names the folder; `view.data(path, project=)` reads the most specific layer; `registrar.data_form(name, folder=, schema=)` adds a form checked by a schema | data 0.3.10; forms 0.3.52 |
| Connector | an input source | `registrar.connector(name, label=, settings=, poll=)`: `poll(settings, state, context)` lists what the source holds now, or only what changed; errors are auth, no_access, not_found, outage, offline or throttled. The core compares, keeps snapshots and hands in differences (6.4); the connector never writes records | 0.3.25; network 0.3.27; throttled 0.3.35 |
| Sign-in | a sign-in to a service, as the person | `registrar.sign_in(name, authorize_url=, token_url=, scopes=, sources=, ...)`: the core runs the flow and keeps the tokens; a connector asks for a current token. See 3.12 | 0.3.33; `sources` 0.3.54 |
| Triage matcher | a rule kind for the `triage:` list in `config/watch.yaml` | `registrar.triage_matcher(name, match=)`: `match(change, params)` returns a reason in plain words or None | 0.3.26 |
| Value list | the values a field may take, shown as a dropdown | `registrar.value_list(name, label=, values=)`; the person owns the list after the first values | 0.3.42 |
| Setup step | a step added to the first-run setup | `registrar.setup_step(name, label=, done=, action=, settings=)`; may suggest core settings the person applies | 0.3.24 |
| Panel | a list screen, under Work or Records in the sidebar (never a top-level entry: the navigation budget, 7.1) | `registrar.panel(name, title=, kind=, columns=, view=, ...)`: a declarative spec (7.2), with computed columns and a per-project `show_for` | 0.3.18; computed columns and `show_for` 0.3.48 |
| Document panel | a read-only page composed from many records | `registrar.document(name, title=, render=)`: `render` returns Markdown, drawn as the screens' own elements, never HTML | 0.3.51 |
| Today contributor | lines on the Today list | `registrar.today(name, lines=)`: each line has one action, the plugin's own or one of the core's | 0.3.18 |
| Job | scheduled work | `registrar.job(name, every_minutes=, run=)`: reads, queues requests, files questions, stages the plugin's own ops; never writes records or calls AI itself. The workspace changes or turns off its schedule | 0.3.18 |
| Interface | a versioned contract other plugins can use: record fields to read, events, task kinds to request (3.9) | `registrar.define_interface`, `registrar.provide_interface`, and the manifest's `interfaces`; the item shape is a schema the host checks | 0.3.16 |
| Event handler | a reaction to a core or interface event | `registrar.subscribe(event, fn)` and the manifest's `subscribes` (3.4) | 0.1 |
| Wording | what screens call the plugin's own kinds | `provides.wording`: YAML files of wording keys in the plugin's namespace; the workspace's `ui.wording` overrides | 0.3.31 |
| Help | text that asking the assistant reads and cites | `provides.help`: Markdown files, one section per `##` heading | 0.3.29 |
| Plugin settings | the plugin's own config | a `Settings` subclass named in `config_schema`, read from `config/plugins/<plugin>.yaml`, shown as a group on the Settings screen | 0.1; screen 0.3.44 |

**Not yet.** These are in earlier drafts of this design and have no registrar call. They are added when a plugin needs them,
each with a test that uses it from a plugin.

| Point | What it would add | State |
|---|---|---|
| Channel | an output target: `current`, `diff`, `send`, `verify`, `lock_status`, `capabilities` | not yet; it comes with the publisher (6.3). Until then a plugin has no way to send, and its ops may not be outbound |
| Renderer | how records become content for a channel | not yet; comes with channels. With it, a **reader preview**: a hook that shows an output as a downstream reader (a dashboard's parser) will see it, and says when nothing it shows changed (9.5a) |
| Lookup | a fact the AI can ask the engine to fetch | not yet (6.19) |
| Connector `fetch`, `search`, `capabilities` | reading one item, searching a source | not yet; a connector has `poll` only |
| Text extractor | text from a file type (documents, spreadsheets, presentations, PDFs) | not yet; the core's own extractors come in phase L (6.2, 6.22), and the extension point with them. With them, **a connector's item can carry files** (a mail's attachments), which the core reads with its extractors, so a connector never parses documents itself |
| Evaluation cases and scorers | a pack's own golden-set cases in the core's format, and deterministic scorers for what only the pack can judge | not yet (phase L-core, with the harder golden set, 6.16); the core's exact matching covers generic scoring, so a pack registers only domain scorers |
| AI adapter | a kind of AI account: `models()`, `run()`, `classify_error()`, `sign_in_hint()`, `health()`, `lockdown_test()` (6.16) | core only: the adapters are a registry inside the core |
| Playbook | a plugin's whole playbook (3.8) | not yet: `provides.playbook` turns the plugin off with the reason; a task kind's guidance is available |
| Check | the plugin's own self-check | not yet |
| API route | extra endpoints under `<base path>/api/plugins/<plugin>/` | planned |
| Auth provider, storage backend | a way to sign in; where records live | core only: internal registries |

The plugin API is 0.x. Minor versions may break, so a manifest declares `>=0.3,<0.4` and an earlier minor version is refused.
It becomes 1.0 when the packs built from their own repositories run on it unchanged. A new extension point is added to the
core when a plugin needs something none of these provide. It is generic, documented in the generated guide, and covered by a
test that uses it from a plugin.

## 3.4 Events

The core uses an internal event bus, and plugins subscribe to it through the manifest (3.2) with `registrar.subscribe`, one
handler per event. Events are published after the change behind them is committed. The core publishes these:

| Event | When | Since |
|---|---|---|
| `record.changed` | a record was created, changed, deleted or brought back by Undo; carries the kind, id, new version, the fields changed and the op | 0.1 |
| `stage.moved` | a record moved to another stage, by the person, a rule or Undo | 0.1 |
| `file.added` | a file was added; carries its id and file kind | 0.3 |
| `text.accepted` | a new version of a long text field is current (the person's edit, an accepted draft or proposal, a merge, an import); carries the record, field, new and previous version, where it came from, the request that drafted it and its authorship summary in three kinds | 0.3.6 |
| `request.queued`, `question.answered`, `changeset.applied`, `changeset.undone` | AI work was queued; a question was answered; a changeset was applied or had ops undone | 0.1 |
| `changeset.reviewed` | the person accepted the assistant's answer or sent it back with a note | 0.3.45 |

A subscription may filter by kind on `record.changed`, `stage.moved`, `file.added` (file kinds) and `text.accepted`. Interfaces
add their own events (`publishing/title.date_changed`), raised by the providing plugin from an op (`writer.emit`) or an event
handler (`context.emit`); the payload is checked against the interface's definition.

Designed and not yet published: `source.saved`, `change.filed`, `change.closed`, `draft.created`, `draft.approved`,
`draft.sent`, `question.asked`, `action.added`, `action.closed`, `problem.opened` and `job.finished`. They are added when a
plugin needs one.

Handlers and jobs may read, queue requests (their own task kinds, or another plugin's through an interface), file questions,
raise interface events, and stage the plugin's own ops. Staged ops apply through the applier after the handler returns, as a
changeset from the plugin that the person can see and undo, treated like work from outside content. They may not write
records directly or stage a core op; anything that changes knowledge goes through an op and the applier.

## 3.5 Rules every plugin follows

Enforced by the plugin host, the applier and the self-check, and by the publisher once it exists:

- **Writes go through the applier.** A plugin changes knowledge only through ops, and an op's apply function touches only the
  paths it declared. A plugin op writes only the plugin's own record types; core records change only through core ops, so
  evidence, owner and tier rules always apply.
- **One source of truth.** A plugin refers to core records by id (`RefTo`) and never copies their names or fields into its own
  records. A field with a known set of values takes it from a value list. The host checks what it can (5.1).
- **Sending goes through the publisher.** A channel's `send` is called only by the publisher, only for a draft whose content
  hash matches the PM's approval. No plugin API hands out a way to send. The publisher and channels are not yet built, so
  plugin ops of the outbound tier are refused.
- **Reach is declared.** Network hosts, secrets and data levels come from the manifest and are shown to the PM before the
  plugin is enabled. The core enforces them on what it hands out: a connector gets a web client that reaches only its declared
  hosts, over HTTPS, with redirects checked against the same list and a size cap, and its declared secrets, as references in
  the workspace's settings or values it keeps on this computer. Bundled plugins may not import network modules; the scan
  enforces it. In-process code is not sandboxed: enabling a third-party plugin means trusting its code (12.3).
- **Programs are declared.** A plugin runs outside programs only through `context.tools.run`, only for tools in
  `requires.tools`, in person actions only (never in event handlers, stage checks or validators, which must stay quick and
  deterministic), with a timeout, no shell and a minimal environment. Every run is recorded. The enable screen and the
  self-check probe each declared tool and show what is missing; a missing required tool keeps the plugin off, a missing
  optional one turns off only the features listed with it. Where a program is found is set per computer.
- **Config is like core config.** `config/plugins/<plugin>.yaml`, with a schema, defaults and descriptions, shown as a form on
  the Settings screen.
- **Plugins meet only through the core** (3.9): interfaces, events and shared core records. A plugin never imports another
  plugin, reads its tables or calls its code.
- **Code against the API, not the internals.** Plugins import only `engine.plugin_api`. Until 1.0, a minor version may break a
  plugin; the manifest's `plugin_api` range says which it works with.
- **Failures stay contained.** A plugin that raises is turned off for the run with the reason in its status; the core and other
  plugins keep running. Calls that only read or react (Today lines, interface items, event handlers, jobs) are contained one
  call at a time: the call is skipped and noted on the plugin, and the plugin is turned off only after
  `workspace.plugins.failures_before_off` failures in a row there. Breaking the contract, or failing inside a write (an op, a
  validator, a lint, a stage check), turns it off at once. Disabling a plugin stops its jobs and hides its panels, and keeps
  its data on disk.
- **Bundled plugins ship demo config and data** for both fictional workspaces and pass the suite against both.

## 3.6 Lifecycle

- **Install, update and remove** add-ons from the Add-ons screen (3.11). Installing never turns a pack on.
- **Enable** in `config/workspace.yaml` under `plugins.enabled`, or with Turn on on the Add-ons screen, which acts with Undo and
  shows "On after a restart" until the person chooses Restart now (2.6). Before turning a pack on, the screen shows the
  guidance it adds to packets (playbook entries and seed lessons) beside what it reaches and keeps (12.8). Turning a plugin on
  or off is recorded (12.1). At startup the host reads manifests, checks plugin API
  versions, dependencies and required interfaces, validates each plugin's config, then calls `register`. Registration is fixed
  until the next start.
- **Upgrade:** record schema and config changes ship as migrations (4.0). The export is committed first and the database is
  backed up; a failed migration restores the backup and opens an automation problem. Designed, not yet built.
- **Disable:** jobs stop, panels hide, records stay. Re-enabling picks up where it left off.
- **Two computers:** plugin code is not copied between computers. A synced workspace whose plugin is missing on the other
  computer stops loading with the reason (5.0).

## 3.7 Worked examples

These show that the extension points cover the uses in view. They are not commitments; each is a pack built later, in its own
repository, or a template made with the kit.

| Use | Connectors | Channels | Record types and ops | AI task kinds | Panels and Today |
|---|---|---|---|---|---|
| Workplace PM (reference pack, Part 9) | wiki, issue tracker, release tracker, shared files | wiki pages; Copy for messages | portfolio fields, risks with owner team, milestones | weekly check-up goals, status updates | portfolio health by group, milestones to check |
| Publishing support | manuscript folder, submissions tracker, mailbox | email to editors and agents, newsletter, blog | manuscript, submission, calendar entry | query letter draft, read a submission reply | submissions by status, editorial calendar |
| Project management | none; other packs put milestones in through an interface | the weekly status report, copied for now | plan, work item with dependencies, baseline, RAID entry | draft a plan and a schedule, draft a status report | at-risk lines, the schedule, RAID |
| A kind of work defined with the kit (3.10), such as client requests or a content calendar | the core's folder, feed, calendar and mailbox sources | Copy | item types with fields and stages | the core's reading of notes, filling the fields the person allows | items due, items waiting at a stage |
| Social media | account mentions and replies | posts per network, scheduled after approval | post, campaign | draft a post, summarize replies | post queue, replies waiting |

A writing pack (from an idea or a manuscript to a finished book) is built the same way, in its own repository.

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

**What is built.** The core's `guidance/` folder is built. A plugin's task kind can ship its own guidance
(`guidance/<name>.md`) and prompt, and the workspace overrides them. The rest of the playbook (the other parts above, the
layers, the entry ids and `config/playbooks.yaml`) is designed and not yet built; the manifest key `provides.playbook`
turns the plugin off with the reason until it is.

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
pack becomes a project to deliver; a writing pack and a publishing pack can put their milestones into one schedule. Plugins
never import or call each other, so they meet only through the core, in four ways:

1. **Shared core records.** People, teams, projects, sources, actions, questions, facts, stages and budgets are core records
   every plugin sees (within its declared data levels). Plugin records link to them by id. A launch is one core `Project`;
   the publishing pack's title and the social pack's posts both link to it, so either can find the other's records without
   knowing their shape, and the PM sees one project with both packs' panels. A project may sit inside another (a series holds
   its books).
2. **Interfaces.** A plugin may provide a named, versioned interface (`publishing/title@1`): the fields of its records other
   plugins may read, the events it raises, and the task kinds others may request. The shape is a schema the host checks when
   an item is read, so a provider can change its internals freely and must bump the version to change the contract. A plugin
   that uses an interface declares it, as required or optional; the host shows this to the PM before enabling, and gives the
   using plugin read-only copies of exactly those fields, filtered by the user's data levels, never the provider's records. An
   interface can also be defined by the plugin that uses it, for others to provide: the publishing pack defines
   `publishing/manuscript-source@1`, so a folder connector or any installed or private plugin that produces finished
   manuscripts can start a launch. The project management pack's `pm/schedule@1` works the same way: other packs put their
   milestones into one schedule (1.8).
3. **Events.** A plugin subscribes to core events and to the events of interfaces it uses (3.4). A handler may read, queue a
   request and file a question to the PM; it never writes another plugin's records. Any change goes through an op and the
   applier, as a changeset the PM sees when it comes from another plugin.
4. **Requests for another plugin's work.** A plugin may queue a request for a task kind another plugin's interface offers
   (the publishing pack's "short blurb in the imprint's voice"). It runs as that plugin's task, under its playbook, with the
   normal cost estimate and go (6.16) and the normal review. The request may name an item the user read through the
   interface instead of a record: the provider says which of its own records the item stands for, so the user never needs
   the provider's ids. Work a handler does in answer to an event records the change that raised it, and What changed shows
   it after that change.

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

**Tested together.** The self-check runs the core with no packs, and each bundled plugin, on both fictional workspaces. A
required interface that no enabled plugin provides keeps the using plugin off with the reason; an optional one reads empty. A
self-check case for required interfaces, and runs of every pair that shares an interface, come with the first bundled pair.

## 3.10 The define-your-own kit

The free version is the core plus a kit for defining one's own kind of work on screens, with no code (decisions,
2026-10-10). The kit is a bundled plugin, `kit`, built only on the plugin API, so it proves the API and needs nothing
special from the core.

**What a person defines** (kept in the kit's settings, `config/plugins/kit.yaml`, saved and shared as one template file):

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
- **Changing a type keeps the data.** A field removed from the type is hidden, and its values stay in the records and the
  readable folder until the person deletes them. A field renamed in the settings is one change that renames it in every
  record. An item type with items can't be deleted, only hidden. Registration is fixed until the app restarts (2.6), so a
  changed type shows after the restart the person chooses.
- **What is built.** The kit, its settings checks, templates, stages, Today lines and filling with evidence are built.
  Defining types on the Settings screens, a screen or route for "Save as template" (today it is `cockpit template save`),
  renaming a field in every record and the guard that stops deleting a type with items are designed and not yet built.

**Templates.** A template is the kit's settings plus a name and a description. Starting templates ship with the core in
`templates/`. A template is applied in the first-run wizard or later from settings; applying one to a workspace that
already has types adds the new ones and leaves the existing ones as they are, and each template lists what it adds before it
is applied. "Save as template" writes the current settings to a file to share. The fictional demo workspaces run on templates.

## 3.11 Finding packs: the Add-ons screen

People learn about packs inside the app, on one calm screen, never through ads, badges or lines on Today.

**Add-ons** has two tabs. *Installed* lists the plugins this install has, on or off, with what each adds and why one
is off. *Available* lists packs from catalog feeds. A pack's listing answers four questions before anything is
installed:

- **What it does:** its name, one line, who makes it ("Made by the app's maintainers" or "Third party"), when it was
  updated, whether it works with this version (its `plugin_api` range against the running one), and its price as the
  feed states it (free, one-time, a subscription, or "see the publisher's page").
- **What it adds, reaches and keeps:** written by the core from the pack's manifest, never from its own description:
  the item types, screens, steps on Today and AI work it adds; the services it signs in to, the hosts it reaches and
  the programs it runs on this computer; the most private data level it uses. The design has the person approve this
  summary when turning the pack on, and again when an update asks for more. Turning on now acts at once, with Undo; the
  approval step and the re-approval are not yet built.
- **What its AI work costs here:** each pack lists its typical AI jobs (a label, typical input and output size, the
  role). The core prices them with the person's own accounts, tiers and prices ("Drafting a chapter ≈ $0.04"); on a
  subscription or a local model it shows the size of the work instead of a price.
- **How to try it or get it:** "Try it in the demo" runs the pack on made-up data (`cockpit demo --plugin`), apart from real
  work. "Install" puts a pack that names a release on this computer (below). Otherwise "Get it" shows the install command
  for a free pack, or opens the publisher's page (its real domain shown) for a paid one. The app never handles payment.

**Install, update and remove from the screen** (decisions, 2026-10-11, "One-click install for add-ons comes before the
freeze"). A pack's catalog entry says where its release is and how to check it. The Install button:
- downloads the release, checks it against the entry's checksum, installs it beside the app and offers Turn on, with the
  usual restart the person chooses (2.6). An installed pack stays off until the person turns it on, and installing one leaves
  every other add-on as it was;
- needs a release that names every package the pack needs, each with a checksum, so a pack's own libraries come with it;
- shows what will be added before it installs, and refuses what conflicts with the app's own libraries;
- is matched by Update and Remove. Remove works on a pack that is turned off, takes out only what that pack needed, and leaves
  the pack's records and settings in place;
- takes a read token for a private pack's release host, given once and kept as a secret reference;
- is for a local install only. A hosted app's add-ons are installed with its deployment.

The Install button is designed. On the server, installing a single release file of pure Python whose needs the app already
has, removing it, and the read token are built. The button itself, the list of what will be added, the conflict check and a
pack's own libraries are not yet built: the screen still shows an install command to copy. Installing code the person chose,
from a checked release, is not the product changing its own code (1.6).

**Catalog feeds.** A feed is one index file at an HTTPS address: version, and per pack its id, name, summary,
publisher, first-party flag, price, latest version, `plugin_api` range, install instructions, homepage, its manifest's
`provides` and `requires`, its typical AI jobs, and its release (the address of its release file and the file's checksum).
A release build ships the maintainers' feed address (as it ships the feedback address); the repository holds none. The
maintainers' catalog is a public index file the owner controls, and lists only packs the owner has said may be listed (3.14).
A workspace can turn the catalog off or add feeds (`workspace.plugins.catalog`). A feed is read only when the person opens
*Available* or presses Refresh, with a plain request that carries nothing about them, and the copy is kept for offline use.
Everything in a feed is untrusted: text is shown as text, links show their real domain, and nothing in it becomes a rule, a
setting or an instruction.

**Licensed packs.** The design accepts that a pack may be licensed: a price in its catalog entry and a licence key kept as a
plugin secret. Whether to charge for any pack is the owner's call, after launch. No licence checking is built.

**Later:** updates with what changed and re-approval when an update asks for more; asking the assistant knows the catalog, so
a question the core can't answer but a pack can mentions the pack before a report is drafted; a signed feed and pinned
package fingerprints; team feeds for hosted installs.

## 3.12 Signing in to a service

Some services offer no app password or calendar address, so an add-on that reads them needs the person to sign in on the
service's own page. The core does the signing in once, for any plugin that declares it, so no add-on handles a password or a
token (decisions, 2026-10-11).

- **The flow.** `registrar.sign_in(...)` declares a sign-in (listed in `provides.sign_ins`). The core runs OAuth 2.0
  authorization code with PKCE through the service's page, takes the answer at its own callback route under the app's base
  path, keeps the tokens on this computer (never in settings or the export), and renews them. A connector asks for a current
  token with `context.access_token(name)`; when the person has to sign in again it raises an `auth` error, which asks them once.
  The plugin never sees the sign-in itself or the refresh token.
- **Nothing to register.** An add-on can ship its own app registration, so the person only signs in; it explains in a note what
  using it means. A person who wants their own pastes it on the Sign-ins row beside numbered steps the add-on supplies, with no
  file or variable to edit, and can set it aside and bring it back. The workspace's references win, and a hosted app uses them.
- **Said before leaving.** The row says in plain words what the sign-in asks to allow, names the account once signed in,
  and names any permission asked for and not granted. Signing out withdraws the access at the service where it can.
  A service that refuses to renew shows "Sign in again" at once. The core adds a setup step per sign-in.
- **Signing in is the whole setup** (decisions, 2026-10-12). The sign-in lists `sources=`: what the core starts reading as
  soon as the person signs in, such as the inbox and the main calendar. Each is added once per sign-in and only where nothing
  reads with that connector yet. Choose settings that read something useful with no further choice; a mail source with
  nothing chosen reads the inbox. The person narrows, adds or removes sources afterwards, and their changes and removals stand.
- **Errors and limits.** A connector's errors are auth, no_access, not_found, outage, offline and throttled, decided from the
  service's status codes and error codes, never from its message text. A throttled read waits for the service's retry-after
  answer and is not counted as a failure.

## 3.13 Testing a plugin and checking a pack

- **The guide is the contract.** `docs/plugin-guide.md` is written from the code by `uv run python -m engine.plugin_guide`
  (docstrings, field descriptions and the host's own tables for the manifest, events, settings, core records and ops). The
  self-check fails when it is out of date. Plugin authors take names only from it, never ahead of the code.
  `docs/plugin-api-0.x.md` records only what each version changed.
- **The testing kit,** `engine.plugin_api.testing`, is part of the plugin API, so a plugin's tests never reach the host's
  internals. `connector_context(service, network=, secrets=, tokens=)` and `read(poll, settings, state, context)` run a
  connector against recorded answers with no network and check its result as the watcher does. `plugin_workspace(...)` is a
  throwaway workspace with the plugins loaded, going through the same paths as the app: the applier (`apply`), the dispatcher
  with a scripted answer (`ask`), person actions (`action`), events, stage moves and the synced folder's layout, with `status`
  and `registered` to look at what a plugin did.
- **The host for a plugin's tests** installs without the web screens when `PM_COCKPIT_WITHOUT_SCREENS=1` is set, so no Node is
  needed.
- **Trying a plugin** on made-up data, apart from real work: `cockpit demo --plugin <folder or installed name>`.
- **Checking a pack:** `cockpit pack check <plugin folder or installed name> [--entry <catalog entry>]`. The manifest must read
  and fit this host; the pack must load in a throwaway demo workspace; and the catalog entry must fit the catalog's format and
  match `plugin.yaml` as written (id, version, `plugin_api`, `provides`, `requires`). A pack whose plugins share a helper
  package is checked installed. Each finding is in plain words, and the check passes only when every line does.

## 3.14 Publishing a pack

Packs are listed by a set process the owner approves (decisions, 2026-10-11). The catalog is public and lists only what the
owner chooses; a checked, repeatable path keeps entries honest about what a pack reaches and keeps. The steps are in the
generated guide ("Publishing a pack"), the catalog repository's PUBLISHING.md and `docs/plugin-kickoff-template.md`.

1. **Release in the pack's own repository:** raise the version in `plugin.yaml` and the package's metadata, say what changed,
   run its tests, tag the release, and let its own checks build the package from the tag.
2. **Write its catalog entry** in that repository, in the catalog's format (`deploy/pack-catalog.example.yaml` shows it):
   `provides` and `requires` copied exactly from `plugin.yaml`, its price, how to get it, its release, and its typical AI jobs.
3. **Check it** with `cockpit pack check` (3.13).
4. **Ask for it to be published:** add a Publish request to the repository's questions file (the pack, the version and tag, what
   changed, the check's output, and whether the owner has said it may be listed publicly) and tell the host's session. A plugin
   repository never writes to the catalog.
5. **The host verifies and proposes.** It runs the same check, the pack's tests and a run in the demo sandbox, and opens a pull
   request on the catalog saying what the pack adds, reaches and keeps, and what changed in what it asks for since its last
   listing.
6. **The owner decides.** The pack is listed only once the owner has said it may be, and the pull request is merged. The
   catalog's main branch takes changes by pull request only. Updates follow the same path.

## 3.15 How an add-on is built

Every plugin kept in its own repository has its own autonomous builder session, so its feedback on the plugin API is
independent of the session that builds the core (decisions, 2026-10-11).

- **A written brief.** Whenever this project suggests a new plugin repository, it gives the owner a kickoff brief built from
  `docs/plugin-kickoff-template.md`: what is built and in what order, the rules it follows, the contract (the generated
  guide), what the owner sets up, and how the two sessions talk.
- **A question channel.** Questions to the host come in numbered rounds in that repository's questions file, written
  generically, as features any plugin could use, because the host's public repository never names a private plugin. A short
  message announces each round. The host answers by building a plugin API version and messaging back; the builder records
  which version answered. A friction log records where the guide was unclear, wrong or missing, or needed a workaround.
- **No shared writes.** Neither session writes to the other's repository. Catalog work goes to the host, never to the owner.
- **One round a week.** Plugin question rounds are answered once a week, together, and the plan runs one stream of work at a
  time.
