# Plugin API 0.x: what changed in each version

The contract is `docs/plugin-guide.md`, generated from the code. This file only records what each version changed.

## Plugin API 0.3

Plugin API 0.x, not 1.0: expect small changes until both of the host's own add-on packs run on it unchanged. Manifests
declare `plugin_api: '>=0.3,<0.4'`; a manifest for an earlier minor version is refused (0.x minor versions may break).
0.3 adds files, programs and person actions to 0.2, and changes nothing a 0.2 plugin relies on, so moving up is the
version range alone. The complete runnable example is
`plugins/example/`. It ships settings and records in both fictional workspaces.

## What 0.3.13 adds

Manifests stay `'>=0.3,<0.4'`.

- Roles: `task_kind(..., role="write" | "check" | "research")`, default `"write"`. The workspace maps roles to tiers in
  `ai.roles.<role>.tier`. Which tier a kind uses: `ai.tasks.<kind>.tier` if set, then its role's tier, then the
  plugin's default, then `routine`.
- Independent second opinions: a `"check"` run never uses an account whose AI runs wrote the record it is about. That
  covers its accepted, merged and pending text versions, and changes AI runs applied to the record; other checks don't
  count.
  - **The same account:** a person with one account can accept it with `ai.roles.check.same_account: true` (or
    `ai.tasks.<kind>.same_account`). Other accounts are still tried first. A check then runs as a fresh run that sees
    only its packet.
  - **No account left:** the check waits for the person and says why.
  - **The record:** each run records `independence` (`other_account` or `same_account`; none for other roles).
  - **The person's pick:** an account the person picks for the request (`use`) stands.

## What 0.3.12 adds

Manifests stay `'>=0.3,<0.4'`.

- Who started a run: a task kind's `packet` function now gets a `PacketContext` as its view, a read view with
  `origin` ("pm", "input" or "schedule"). Only a note from the person ("pm") is shown to the run as their words; a note
  from an outside input is now untrusted like a scheduled one, and so is the run's changeset.
- `task_kind(..., where={field: value})` narrows which records of kind `on` the work is offered on and may start on.
  A value may be a tuple of values. `GET /api/task-kinds?kind=&id=` lists only the work offered on that record;
  starting it on another is refused, and so is a run whose record no longer matches.
- `task_kind(..., output="draft", questions=N)`: the draft may end with up to N questions for the person in a
  `<questions>` block. The core takes the block off the text and keeps the questions on the version
  (`TextVersion.questions`, also on `text.draft`); more than N gets a fix round. The text-version views show
  `questions` and `unmapped`.
- Person actions: a rerun given a choice it no longer offers drops it, rather than failing. A value it no longer
  offers falls back to the value the action reports in its `Choice`.

## What 0.3.11 adds

Manifests stay `'>=0.3,<0.4'`.

- Working-copy formats: `registrar.working_copy(name, label=, extension=, media_type=, hand_out=, take_back=,
  text_formats=())`, listed in `provides.working_copies`. `hand_out(text, context) -> bytes` makes a file from a long
  text field's current version; `take_back(data, base_text, context) -> TakeBack(text, unmapped)` reads a returned
  file, given the text of the version it was made from. The context (`WorkingCopyContext`) is a read view with the
  plugin's `config`, the `record`, the `field` and the `version` handed out. Both are deterministic, with no AI.
- The core reads every file back as it hands it out and refuses to hand out one that wouldn't come back as the same
  text. A file returned unchanged proposes nothing. A changed one becomes a pending `text.propose` version made from
  the handed-out version (three-way review when the text moved on), with `unmapped` kept on the version
  (`TextVersion.unmapped`, also on the `text.propose` op).
- Each copy is a `working_copy` record (the format, the version handed out, the file, its hash, `out`, `returned` or
  `dropped`, and the proposal it became). Routes: `GET /api/working-copies/formats?kind=&field=`,
  `GET /api/working-copies?kind=&id=`, `POST /api/working-copies`, `POST /api/working-copies/<id>/return` (the file's
  bytes as the body, `name` as a query parameter) and `POST /api/working-copies/<id>/drop`.
- A format that raises is turned off with the reason, like any plugin callback.

## What 0.3.10 adds

Manifests stay `'>=0.3,<0.4'`.

- Data files: `provides.data` names a folder beside `plugin.yaml` with what the plugin ships. `view.data(path,
  project=None)` reads a file from the most specific layer that has it (the project's
  `plugin-data/<plugin>/projects/<id>/`, the workspace's `plugin-data/<plugin>/`, then what the plugin ships);
  `view.data_files(folder, project=None)` lists them across layers. Paths stay inside the data; the workspace's layer is
  committed with config and included in backups.
- Prompt bundles are the task kind's `packet` function: it says exactly what each run sees, part by part, with trust
  and reference-only marks. No separate declaration is needed.

## What 0.3.9 adds

Manifests stay `'>=0.3,<0.4'`.

- Anchored drafts: `task_kind(..., output="draft", anchored=True)`. The run sees the current text with an id on each
  unit (`[p3]`, atomic ones marked) and starts each paragraph it writes with the ids it came from (`[p3]`, `[p3,p4]`,
  `[new]`), ending with `Removed: ...`. A core check refuses a draft that leaves a unit unaccounted for, names an
  unknown id, or splits or merges an atomic unit, and sends the reason back for a fix round. The ids are stripped; the
  paragraph map is kept on the version (`paragraph_map`, also on the `text.draft` op for validators) and decides
  authorship: a paragraph kept word for word keeps its author, one rewritten from the person's text is
  `assistant_edit`, a new one `assistant`.
- Review routes for the screens: `GET /api/texts?kind=&id=&field=` (current text, authorship, versions),
  `GET /api/text-versions/<id>/review` (the regions to decide, three-way when the text moved on),
  `POST /api/text-versions/<id>/accept` and `/discard` (`read_version`, `choices`), and `POST /api/texts/edit`.

## What 0.3.8 changes

Manifests stay `'>=0.3,<0.4'`.

- `view.get`, `view.list` and `view.find` take the record kind positionally, so a field called `kind` can be matched.
- Only the core's `EvidenceIn` is treated as evidence; a plugin op's own field called `evidence` is left alone.
- `RefTo` is honored inside nested models (a model or a list of models), for checks on write and for delete
  protection: paths such as `relationships[].person`.
- `view.source_text(source_id)` reads a saved core source's text (untrusted material).
- Documented: refusing stage checks' reasons are shown joined with "; ".

## What 0.3.7 adds

Manifests stay `'>=0.3,<0.4'`.

- Draft task kinds: `task_kind(..., output="draft", field="<long text field>", on="<kind>")`. The model answers in
  plain prose (no JSON is asked for); the core removes one surrounding code fence, continues an answer cut off at the
  output limit once (holding it for the person if it is cut off again), and files it as a core `text.draft` op: a
  pending version, made from the field's current version, written by the assistant. Lints on the op `text.draft` run
  on it; a "return" finding gets one fix round, then the stronger tier, then the draft stays pending with its findings.

## What 0.3.6 adds

Manifests stay `'>=0.3,<0.4'`.

- Long text: mark a field `Annotated[str | None, LongText("plain" | "markdown" | "<plugin>/<format>")]`. Every version
  is a `text_version` record with its number, status (pending, accepted, merged, discarded), source and authorship by
  passage (person, assistant, assistant_edit); the text is stored once by hash. `registrar.text_format(name, units)`
  adds a format (listed in `provides.text_formats`); the core checks its units cover the text exactly.
- Writing: `writer.set_text(kind, id, field, text)` in an op (accepted and written by the person when the person runs
  it, a pending draft from anyone else); never the field directly. Core ops: `text.edit` (person only, current at
  once), `text.propose` (pending, from the person's work outside), `text.accept` (person only, change by change,
  three-way when the text moved on since the base), `text.discard` (person only). Undo restores the earlier text.
- Reading: `view.text(record, field, version=None)`, `view.text_versions(...)`, `view.authorship(...)`.
- Event `text.accepted` (filterable by the owner's kind) with version, previous, source and words per author.
- The export writes each text as `data/texts/<hash>.txt` and import loads them back; backups include them.
- The guide now documents `Part`, `PacketParts`, `LintFinding`, `LongText` and `Unit`; the self-check's network scan
  lists reaching submodules (`urllib.request`, `http.client`) so pure helpers such as `urllib.parse` pass.

## What 0.3.5 adds

Manifests stay `'>=0.3,<0.4'`.

- Lints: `registrar.lint(name, fn, ops=(...), severity="warn")`, listed in `provides.lints`.
  `fn(op, view, settings) -> list[LintFinding(message, passage, guidance)]` runs on the named core or own ops before
  they apply. "return" sends the passage and guidance back for the assistant's fix round, "warn" shows them on the
  review, "off" skips; `config/checks.yaml` overrides the default per lint. A lint can't default to refusing, and one
  that raises turns its plugin off while the work goes on.

## What 0.3.4 adds

Manifests stay `'>=0.3,<0.4'`.

- Projects inside projects: `Project.parent` (never itself or below it); `record.set` may change a project's `parent`
  and `language`. A core op `project.add` (name, summary, parent, language) starts one; it is a system op, so from the
  assistant it waits for the person, and reading notes never offers it. Actions and plugin task kinds may propose it.
- Language: the workspace's `workspace.language` (default `en-US`), a project's `language`, inherited through its
  parents. `view.language(record)` gives the tag for any record; a plugin task's run is told to write in it.
- Budgets: `Project.budget_usd`, set only by the person, covers AI work on the project, the records in it and the
  projects inside it; a run that would pass it waits for the person with what is spent.

## What 0.3.3 changes

Manifests stay `'>=0.3,<0.4'`.

- An installed plugin is found in its checkout too (editable, development installs).
- A plugin in the workspace's `plugins/` folder wins over an installed one of the same name, with a note in its
  status (`notes` in `/api/plugins`); other duplicates are still refused.
- A file kind whose accepted types the workspace narrows (some or all) loads with a note saying what it lost.
- An op's `describe` may take a read view, `describe(self, view)`, to name the records it changes.
- Undo after an undo: a field written again since counts as a conflict only while it holds something other than what
  the change being undone set.
- Documented: an op's own `group` in a proposal item wins (one Undo for several items); nested settings models and
  aliases; an op that doesn't match its model makes the whole answer or proposal unreadable, while a refused op is
  refused alone.

## What 0.3.2 adds

Manifests stay `'>=0.3,<0.4'`. Plugin task kinds can now do real work (see "Registering" in the guide):

- `task_kind(..., label=, prompt="<plugin>/<name>", playbook="<plugin>/<name>", on=, packet=, tier=, max_output=,
  expected_output=, temperature=)`: the plugin's own prompt (`prompts/<name>.md`, which the workspace overrides with
  `prompts/<plugin>/<name>.md`) and guidance (`guidance/<name>.md`); the record kind a run works on; what the run sees,
  as `PacketParts(stable, request)` of `Part(title, text, trusted, reference_only)`; and defaults the workspace's
  `ai.tasks.<kind>` overrides field by field.
- A request carries the record it is about (`Request.about`). `context.queue_request(task, note, about=)` and the
  person (`POST /api/task-kinds/<name>/start`) start work on a record; `GET /api/task-kinds?kind=` lists what can be
  started on a kind.
- A record type may set `content_levels_field` to one of its `list[str]` fields: the content levels (from the
  workspace's `ai.content_levels`) the person set on a record. Only the person sets it; an op from anyone else that
  sets it is held. Work on the record goes only to accounts that take every level on it and on its project.
- A refused run (the provider's own refusal signal) is recorded as refused and waits for the person; it is never
  retried, sent to another account or escalated.
- A run with a packet sees only its instructions, the op reference, its guidance and its parts. Untrusted parts make
  the changeset untrusted; evidence may quote any part that isn't reference-only, cited as `<kind>:<id>`.

## What 0.3.1 adds

Manifests stay `'>=0.3,<0.4'`.

- **Groups:** `Group(id, heading, explanation="")` in `Proposal.groups`. A `Choice` and an `Item` may name one with
  `group=`; a group the proposal doesn't list is refused. Setting a whole group of choices is one rerun with every value
  in `choices`.
- **Items the person keeps or drops without a rerun:** `Item(id, label, ops, group=None, kept=True)` in
  `Proposal.items`. `ops` are dicts like `Proposal.ops` (same rules, `"$file:N"` included) and apply and undo together.
  `Proposal.ops` always apply; an item's ops apply only while it is kept. Ids must be unique, and at most
  `workspace.plugins.actions.max_items` items per proposal.
- **Ticks:** the preview route takes `previous` (the review it replaces) and `kept` (`{item_id: bool}`); the person's
  ticks carry over to items that came back with the same id and the same ops, and an item that changed starts as the
  action says. `apply` takes the final `kept`. An unknown item id is refused and the review stays open.
- `Changeset.action` records `kept` and `dropped` item ids; the review's `ops` list is everything that applies with
  the ticks as they are.
- `Proposal`'s new fields come after the existing ones, so positional calls keep working.
- A `tool_run` records the program's `version` from its probe.

## What 0.3 adds

- **Files** (design 5.3). People add files in the UI; bytes are stored once by hash and described by a core `file`
  record (name, media type, size, kind, project, details, origin, replaces). `registrar.file_kind(name, details=Model,
  accept=(...), max_mb=..., label=...)` declares what a kind of file is for and the details it asks for (validated on
  add); declare it in `provides.file_kinds`. `file.added` publishes `{id, kind}` and may be filtered by file kinds.
  Views read bytes with `view.file_bytes(file_id)`, checked against the hash. Files a program or action made are
  `origin: tool` and untrusted.
- **Programs** (`requires.tools`): `{name, min_version, probe, optional, features}`. Where a program is found is set
  per computer in `<workspace>/.cockpit/tools.yaml` (`name: /path` or `name: {command: [...], env: {...}}`), else the
  PATH. Each tool is probed when the plugin loads; the probe's first word is the tool's name, and the first version
  number in its output is compared with `min_version`. A missing required tool keeps the plugin off; a missing
  optional one shows in the plugin's status, and `context.tools.available(name)` is false.
  `context.tools.run(name, args, files={path: bytes}, timeout=..., collect=[patterns], max_file_mb=...,
  max_total_mb=...)` writes the files into a fresh folder, runs the program there without a shell, with a minimal
  environment (PATH, locale; HOME and temp point at the folder), a timeout and capped output, and returns
  `ToolResult(returncode, stdout, stderr, timed_out, output_cut, files, omitted, seconds)`. `files` holds what matched
  `collect` (regular files inside the folder only); a file over a cap is listed in `omitted`, never cut short. Calls may
  lower the timeout and caps, never raise them (`workspace.plugins.tools`). The folder is deleted afterwards and every
  run is a `tool_run` record. Programs run only in person actions.
- **Person actions:** `registrar.action(name, label=..., run=fn, on=kind | None, file_kinds=(...))`, declared in
  `provides.actions`. `on` is a core or own record kind, `"file"` (optionally only some file kinds), or None for the
  whole workspace. `fn(target, context, choices) -> Proposal` is deterministic work; `context` reads core and own
  records and file bytes, has the plugin's settings and `context.tools`, and changes nothing. A `Proposal` has:
  - `summary`: one line;
  - `ops`: dicts for core ops or your own (not ops that need evidence: an action has no input to quote);
  - `files`: `NewFile(name, media_type, data, file_kind, project, meta, replaces)`, added when it applies; ops refer to
    one as `"$file:<index>"`;
  - `previews`: `Preview(name, media_type, data, caption)`, PNG, JPEG, GIF, WebP or plain text, shown and never saved;
  - `choices`: `Choice(id, label, value, options=[(value, label)], help)`; no options means on or off. Flipping one
    runs `fn` again with the person's values in `choices`;
  - `notes`: anything the person should know.

  The person reviews the proposal and applies exactly that, as themselves (actor `pm`): person-only values apply, and
  validators see `origin.via == "action"`. If the target changed since the review, nothing applies and the person runs
  the action again. A review keeps for `workspace.plugins.actions.keep_minutes` and applies once. Ops apply as any
  changeset does (each refused or held alone), and Undo takes back the whole action, its files included. An action
  that raises `StoreError` or a tool error shows its message; any other exception turns the plugin off.

## What 0.2 adds

- **Record types declare rules the core enforces** (class variables on the `Record` subclass):
  - `person_only = {"status": ("decided", "locked")}`: an op that sets one of these values from anything but the
    person (the assistant, a rule, a schedule) is **held for the person**, not refused or applied. When the person
    releases it, it applies.
  - `unique = (("project", "slug"),)`: these field groups must be unique among live records of the kind; a duplicate
    is refused.
  - `data_level = "internal"` (`open`, `internal` or `restricted`): must be listed in the manifest's
    `requires.data_levels`. Work whose packet carries such a record (a stage task today; prompt bundles later) goes only
    to AI accounts allowed that level.
  - `project: Annotated[str | None, RefTo("project")] = None`: a reference to a core or own record kind. The core
    checks the target exists on every write and refuses deleting a record still referred to. (Ids never change on
    rename. Placing records under their project in exports and the synced folder comes with the synced folder.)
- **Lookups:** `view.list(kind, project=None, **equals)` filters in the database; `view.find(kind, **equals)` returns
  the first match or `None`. Both are on validators' views, event contexts and op writers.
- **Validators see the changeset so far:** a validator's view is the changeset's own transaction, so op 2 can refer to
  a record op 1 created. Before applying (for the fix round), validators run against a dry run of the changeset that is
  rolled back. A validator may take a third argument, `origin`: `{"actor": "pm" | "assistant" | "rule", "trust":
  "trusted" | "untrusted", "via": "screen" | "note" | "input" | "task" | "rule"}`. Two-argument validators keep working.
- **Delete:** `writer.delete(kind, id, read_version=...)` deletes one of the plugin's own records (the op's `writes`
  must give `("*",)` for the kind); refused while referred to; Undo brings it back. The core op `record.delete` does
  the same for any record; it is a system op (from the assistant it waits for the person) and reading notes never
  offers it.
- **Event filters:** a `subscribes` entry may be `{event: record.changed, kinds: [<kind>, ...]}`; a plain event name
  still means every kind.
- **`ext` on core records** is reserved and may be removed before 1.0; keep your own record linked by `RefTo`.

## What 0.2.1 changes

Fixes from trying 0.2; manifests stay `'>=0.2,<0.3'`.

- **Who sets a person-only value.** Ops from tasks and events carry the assistant as their actor, so a person-only
  value is held until the person releases it; releasing is how the person decides. Person actions (0.3) apply as the
  person, so such values apply at once.
- **Labels:** an op may override `describe(self) -> str | None` to give its one-line label in review lists (held,
  applied, refused). Without it the list falls back to a `text`, `title`, `answer` or `full_name` field.
- **References inside lists:** `list[Annotated[str, RefTo("kind")]]` is enforced like a single reference: every id
  must exist, and a record still listed is not deleted.
- **Undo keeps the rules:** Undo skips and reports a group that would bring back a record whose unique values another
  live record now has, or remove a record that something outside the group now refers to.
- **A stale `record.delete`** is refused like any stale op, not raised.
- **Event filters are checked at load.** `kinds` is allowed only on events that carry a kind (`record.changed`,
  `stage.moved`, and `file.added`, whose kinds are file kinds), and may name only core kinds or the plugin's own; a
  typo or another plugin's kind refuses the plugin. Subscribe to an event once: one handler per event, routing by
  `payload["kind"]` if it handles several.
- **Lookups:** an unknown field name and a list value are refused with a plain message. `project` defaults to
  `ANY` (no filter); `project=None` asks for records in no project. Matching, in lookups and in `unique`, is exact and
  case-sensitive; store a normalized copy (a slug) when you need case-insensitive matching.
- **Validators** may take `origin` as a third positional parameter or as a keyword-only `origin`. They run more than
  once per op (in the dry run for the fix round, then in the changeset), so they must be pure and cheap. The `rule`
  origin comes from the rule worker, which today moves stages only. Validators on the core `stage.move` work like any
  other.
- **`record.changed`** carries field names, not values; read the record for values. A delete and its Undo both list
  `_deleted`. The core fields every record has (`ext`, `stage`) appear in `fields` when they change, plugin records
  included.
- **Data levels:** list every level your types use in `requires.data_levels`, the default `internal` included; the
  refusal names the type.
- **Reaching outside the declared scope** (writing a kind or field the op's `writes` doesn't give, deleting without
  `("*",)`) is a contract breach and disables the plugin, unlike an ordinary refusal: it means the plugin's code and
  manifest disagree.

## Discovery and configuration

A bundled or private plugin lives in `<plugins>/<name>/` with `plugin.yaml` and a Python package. Private plugins are in
`<workspace>/plugins/`. Installed distributions declare a `pm_cockpit.plugins` entry point named for the plugin and place
`plugin.yaml` beside their top-level package's `__init__.py`. Discovery reads the manifest without loading the entry point.
Duplicate discovery names are refused. Only names in `workspace.plugins.enabled` load; dependencies must also be enabled.

`depends_on` entries have `name` and `version` (a version range). Both plugin and API versions use standard version ranges.
Unknown keys anywhere in the manifest are errors. Contributions must match `provides` exactly, including optional
`provides.op_validators` entries identifying the core or own ops being validated. `subscribes` must match registrations.
Namespaces are `<plugin>/<name>`; record id prefixes must be uppercase and unique in the workspace.

`config_schema` names a subclass of `engine.plugin_api.Settings`. It forbids unknown keys and supplies `version: 1`.
Every setting must have a default and description. The host validates `config/plugins/<name>.yaml` before calling `register`.
Registration is staged: failures leave no partially installed contributions. Each store has its own module namespace and
registries, so one workspace cannot enable an op in another.

## Registration contract

Plugins import engine types only from `engine.plugin_api`; other plugin packages and engine internals are not APIs.

- `record_type(model)`: subclass `Record`, declaring `record_kind` and `prefix` class variables.
- `op(model, tier, apply)`: subclass `OpModel`, with a single literal `op` and a `writes` class variable mapping the plugin's
  own record kinds to field tuples. Core records change only through core ops, so their evidence, owner and tier rules
  always apply. `tier` is `data` or `system`; `outbound` is refused until the publisher is part of the API. `("*",)` permits creation of that kind; a field tuple permits updates only to those fields.
  `apply(op, writer, settings)` uses `writer.create(kind, data)` or
  `writer.update(kind, id, changes, read_version=version)`. It cannot replace the write context or access SQL through the API.
  `writer.delete(kind, id, read_version=version)` deletes one of the plugin's own records (see 0.2 above).
- `op_validator(op_name, fn)`: `fn(op, read_view, origin)` (or `fn(op, read_view)`) returns a list of refusal messages. It must be deterministic and cannot
  modify records. Validators may target core or own ops. A validator that crashes refuses the op it was checking and
  disables its plugin; later core ops carry on without it, and the plugin's own ops are refused.
- `task_kind(name, ops=..., prompt="notes", playbook="notes")`: the dispatcher uses the registered op list for parsing,
  validation, schema and reference generation. These defaults reuse the core extraction prompt/playbook. Workspace prompt
  overrides work as before. Pack-provided prompt/playbook loading is a later extension point.
- `subscribe(event, fn)`: `fn(payload, context)` reads core or own records through `get`/`list`; it can stage
  `queue_request(task, note)` or `file_question(title, text)` for the PM. Commands commit only after a successful handler.
  Requests for other plugins require the future interface mechanism and are currently refused. Plugin requests are marked
  as scheduled work: their notes reach the assistant as untrusted data, never as the PM's instructions, and system ops never
  apply automatically from them. A request queued by a `stage.moved` handler waits for the person's go, like `starts`.

## Events and failure behavior

Events publish after a successful transaction, never after rollback or while importing an export. `record.changed` carries
`kind`, `id`, `fields`, `version`, and the ledger `op` (including its changeset index). The bus also publishes
`request.queued`, `question.answered`, `changeset.applied`, `changeset.undone`, `stage.moved` and `file.added`. A causal event chain does not re-enter the
same plugin/event handler, preventing unbounded request or record-event loops. Separate committed transactions still emit
their own events. Event payloads are copied for each handler.

An ordinary refusal inside an op (a stale `read_version`, an invalid value) refuses that op only. Reaching outside the
plugin's declared scope (`PluginMisuse`), or load, validation, op or event callback exceptions, disable the offending plugin
for the run, log the reason, and appear in
the authenticated `/api/plugins` response. Required consumers are disabled too. Unrelated plugins and core work continue.
A failed op's savepoint is rolled back; its outcome is recorded as refused. Record schemas remain available for undo and
export after a runtime failure. Restarting with the plugin enabled attempts a fresh load.

The host is not a Python sandbox. Enabling a plugin trusts its code. The API exposes no network, process, secret or sending
capability (programs only through `context.tools`, see 0.3). Manifests requesting these or later extension points are refused until implemented. Version 0.2 does not yet
implement migrations, interface contracts, plugin panels or custom prompt bundles.

## Verification

`tests/test_plugins.py` covers both fictional workspaces, core-only and enabled operation, strict manifests, compatibility,
dependencies, discovery, configuration, atomic registration, namespace enforcement, dispatcher/schema integration, tier
holding and release, validators, ledger/undo, post-commit events, handler/op failures, write scope and data preservation.
The existing boundary test and a plugin-specific test reject imports of engine internals. The self-check compares complete
nested exports, validates all bundled registrations, and checks both core-only and enabled fixture imports.


For the same core suite on copied fixtures with no plugins, run
`COCKPIT_TEST_CORE_ONLY=1 uv run pytest --ignore=tests/test_plugins.py`. The plugin contract suite runs in the normal full
suite, including its explicit core-only and enabled pipeline cases. The committed fictional fixtures are never changed by
this test mode.

## Stages

A plugin declares `provides.stage_checks` (check ids) and `provides.stages`
(record types with defaults) in its manifest. Register a pure deterministic
check with `registrar.stage_check("<plugin>/<name>", fn)`. Its signature is
`fn(record: Stored, view: ReadView, config: Settings) -> StageCheckResult`;
return both a boolean and a plain reason. The view permits core and own
records only. Checks never call AI; exceptions disable the plugin and block
entry. Put check wording in plugin settings.

Use `registrar.stages(record_type, [{id, label, entry, starts}, ...], moves=None)`
for defaults on the plugin's own types. Workspace `config/stages.yaml` accepts
`types: {record_type: {moves: person, stages: [...]}}`, or the design's shorter
`record_type: [...]` form. `moves` defaults to `person`; a type may override it
with `rule`. A workspace list replaces the complete pack list; leaving `stages`
out keeps the pack's list and changes only `moves`; an empty list removes the
stages. Every stage needs a label. In rule mode every stage after the first needs
an entry check, so rules never walk a record through stages nobody checks.
Stored ids and ledger history survive label changes and removed stages; no
successor is inferred for an id that is no longer configured. Record types may
not define their own `stage` field; it belongs to the core.

Stage config that names a plugin which is not running (turned off, or failed to
load) stays in place and shows as unavailable; the workspace still starts. Names
that no running plugin or the core explains are config errors.

Rules in `config/rules.yaml` retain the metadata in design 4.10. An optional
`check` names the deterministic code check that implements a rule. Stage entry
may name the rule id. Retired, out-of-scope, and prose-only rules do not pass.
A general executable rule language remains an open design question; AI never
interprets a rule to authorize a move.

`stage.move` takes `record: {kind, id}`, `to`, and `read_version`. Every AI
proposal waits for the person, including proposals from trusted notes. A move
goes one stage forward, after that stage's entry checks pass, or back to any
earlier stage without checks. An item not yet in a stage, or in a stage config
removed, may start at any stage whose checks pass. The rule worker advances only
to the next stage, and leaves an item alone after the person moved it back or
undid a move, until the person moves it forward again. Both paths use the applier,
record exact versions, write the ledger, and support grouped Undo.

On entry, `starts` task kinds create requests with `approval: required` and
`state: needs_you`. The explicit go endpoint grants approval. Retry and direct
dispatch cannot bypass this gate. `approve_stage_request` is the integration
point for future estimates and budget authorization; request `stage_start`
metadata identifies both the task's record and originating changeset. A task is
not queued twice for the same item and stage. Moving on before the go closes the
left stage's waiting tasks in the same changeset, so Undo reopens them. Undo
removes pending tasks with the move, and refuses the group once a task changed.

The `stage.moved` event contains `kind`, `id`, `version`, `from`, `to`, and `op`.
It is published after commit, including reversals from Undo; rolled-back writes
emit nothing.

All endpoints are under the configured base path plus `/api`:

- `GET /records/{id}?kind=...`: record data, stage status, next checks, and ledger history, for kinds that have stages.
- `GET /records/{id}/stage-history?kind=...`: stage entries and reversals from the ledger.
- `GET /stages/ready`: records whose next stage checks pass.
- `POST /stages/move`: explicit person move with the op fields above (without `op`).
- `GET /stages/requests`: task requests originating from stage entries.
- `POST /requests/{id}/go`: `{"read_version": n}` approves a waiting stage task.

No stage UI is included in this increment; it comes before the publishing pack.

Plugin settings are read from `config/plugins/<name>.yaml` only. Environment, flag and profile layers for them are a later
change.
