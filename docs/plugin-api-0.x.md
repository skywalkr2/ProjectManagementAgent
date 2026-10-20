# Plugin API 0.x: what changed in each version

The contract is `docs/plugin-guide.md`, generated from the code. This file only records what each version changed.

## Plugin API 0.3

Plugin API 0.x, not 1.0: expect small changes until both of the host's own add-on packs run on it unchanged. Manifests
declare `plugin_api: '>=0.3,<0.4'`; a manifest for an earlier minor version is refused (0.x minor versions may break).
0.3 adds files, programs and person actions to 0.2, and changes nothing a 0.2 plugin relies on, so moving up is the
version range alone. The complete runnable example is
`plugins/example/`. It ships settings and records in both fictional workspaces.

## What 0.3.84 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes has to change.

- **Core op `project.add`** takes an optional `status` (a value of the project-status list, with the exact words behind it
  in the evidence, or it is refused, so an unknown status stays unknown) and an optional `link` (the page the project
  came from; an add from a link nothing set up can open says "Not read" and fills nothing from it).

## What 0.3.83 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes has to change.

- **A record's history as readers see it:** `view.changes(kind, record_id)` returns the record's changes oldest first as
  `Change`s (`at`, `op`, `field`, `before`, `after`, `actor`, `version`), leaving out a change that only moves a date on an
  existing item (the same words, a new due or start date). A date move together with any other change, a first date, a
  date taken away and every new, closed or blocked item stay. The ledger keeps everything; a pack's published status page
  reads this so a date that merely slipped is not reported as news.
- **Core records:** `Action.on_hold.on` (what a hold is blocked on: the id of a person, an action or a question; a hold
  with only words has none), `Question.held_for` (a meeting, a series or a day it waits for, out of To send until then),
  and `ValueList.tones` and `ValueList.meanings` (how each value is colored and, on a status list, what it means).
- **Core ops:** `action.hold` takes an optional `on`; `list.add` takes an optional `tone` and `meaning`.

## What 0.3.82 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes has to change: a connector that calls `context.access_token(name)`
reads whichever account its source names.

- **Several accounts of one service at once:** when a sign-in names its account (`registrar.sign_in(..., account=fn)`), the
  person can sign in again ("Add another account") and the core keeps each account's tokens apart, known by the name `fn`
  returned (best the account's address: the same name again is the same account, and signing in replaces its tokens). Each
  source of the plugin gets a core setting `account`, a list of the accounts signed in; `context.access_token(name)` in its
  read returns that account's token. With one account signed in, a source needs no choice; with several it must choose.
  Signing one account out pauses only the sources reading with it. The sources a sign-in starts (`sources=`) are started for
  the account just added. A sign-in without `account` has one account, which signing in again replaces.
- **`context.account`:** the address of the account the source reads with (read-only text), for a plugin that wants to show it;
  `None` when the sign-in names no accounts, or several are signed in and the source names none. The test kit's
  `connector_context(..., account=...)` sets it.
- `account(context)` now reads the new account with the token just granted: `context.access_token(name)` inside it gives that
  token, before it is kept under its account.

## What 0.3.81 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes has to change: a Today line without a `group` works as before.

- **A Today line names its group:** `TodayLine.group` is one of `TODAY_GROUPS` (`"decide"`, `"risk"`, `"review"`,
  `"send"`), the groups of the core's own queue. The line sits among the core's lines of that kind, below them and in
  `until` order (earliest first), so a plugin can't put itself first; its second line names the plugin quietly. A line
  with no group shows under "More for today" at the end, and `cockpit pack check` warns about it (a warning, not a
  failure). A group that isn't one of the four fails the contributor like any other bad line.
- **Core record:** `Question.followed_up` (the days the person was chased about a question after it went out, oldest
  first). A chase restarts the wait for an answer and never changes `sent_at`. A plugin that reads questions sees it.

## What 0.3.80 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Advice with a connector's error:** `ConnectorError(kind, detail, advice_key=...)` may name a wording key that says
  what the person should do (an app password, a locked account); the source's problem on screen uses it instead of the
  kind's default advice. The key and its text come from the core's wording sheet.
- **Types in this guide** are written one way on every supported Python (`X | None`, `list[X]`, bare class names).

## What 0.3.79 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **A pack's own evaluation cases:** `provides.evals` names a folder of cases in the core's format beside `plugin.yaml`
  (ids `<plugin>/<name>`); a case may name `task:` (one of the plugin's task kinds) and `score:` (a scorer it lists in
  `provides.scorers`). `registrar.scorer(name, fn)` registers it; `fn(case, produced, view)` returns a list of problems in
  words, empty when the case passes. A scorer that raises fails only its case. `cockpit evaluate -w <workspace>` runs the
  enabled plugins' cases with the golden set, and the check on a switch of account runs them too.

## What 0.3.78 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Signal kind `edited`:** the person changed fields the assistant had set; the note says which, from what to what.

## What 0.3.77 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- A request paused for an account's limit names the `tier` in its `cause`.

## What 0.3.76 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Watched items:** `by_you` (the person's own work) and `credited_to` (a source's named author); `by_us` now means
  only the app's own publish.

## What 0.3.75 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes; a plugin that reads projects, people or changesets sees
more fields.

- **Core records:** `Project.roles` (a person and their part: run, design or watch); `Person.name_verified`; a change's
  view carries `made` (what it made, for its "Made:" links).
- **Core op:** `project.role` (system tier).
- **Core lints:** `watched-project`, `other-team-item`, `unverified-quote`, `unverified-name`, `unknown-link`,
  `version-number`, `summary-is-status`, `unlinked-made`.

## What 0.3.74 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Text extractors:** `registrar.extractor(name, label=, media_types=, extract=)` with `provides.extractors` registers
  a reader from a media type to text, used before the core's readers; `extract(data, name)` returns text, returns
  `None` to decline, or raises `ExtractError(reason)`.
- **Files on a connector's item:** `SourceItem.files` carries `ItemFile(name, media_type, data)`; the core reads them into
  the item's text, so a connector never parses documents.
- `view.file_text(file_id)` reads a file's text with the same readers. `ExtractError` and `ItemFile` are exported.

## What 0.3.73 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Core op:** `person.contact` (a person, a kind of contact detail, its value, evidence); it always waits for the person.
- `person.add` takes an optional `first_name`; `project.add` an optional `evidence`, and reading notes may propose it
  (it stays a system op that waits).

## What 0.3.72 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **Core op:** `action.unhold` (an action and the words saying its wait is over).
- **Core lint:** `unnamed-recipient`.
- `ref_fields` is worked out once per model class (faster; no change for callers).

## What 0.3.71 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes; a plugin that reads actions sees one more status.

- **Core ops:** `action.hold` (an action and what it waits for) and `action.drop` (an action and why it is no longer
  needed); `question.drop` may now come from the assistant with evidence, and is offered to a person action too.
- **Core records:** an action's status may be `dropped`, with `dropped_reason`; a dropped action is never done.

## What 0.3.70 changes

Manifests stay `'>=0.3,<0.4'`. **A fix of a silent change in 0.3.64:** from 0.3.64 to 0.3.69 the store saved every
record by field alias, plugin records included, and reference paths named aliased fields by their alias. A field
declared `Field(alias="with")` was stored as `with` instead of its field name, so code reading stored records by field
name stopped seeing it, with no error. From 0.3.70 a plugin's records are stored, read back and named in reference
paths by field name again, as before 0.3.64; the alias is accepted on input. Only a core model that asks for it (the
scope's `except`, through `serialize_by_alias`) is stored by alias. A record written by 0.3.64–0.3.69 keeps its
aliased keys until it is written again.

## What 0.3.69 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes; a plugin that reads these records sees more fields.

- **Core records:** a changeset gains `applied` (the knowledge ids the run said it applied, kept only when the run was
  given them), `applied_dropped` (how many it named and wasn't given), `missing` (what the run needed and no op could
  do) and `first_on_account` (the account, on the first run on one that stands in a fallback chain); the signal kind
  `answered_assistant`.
- **Answers:** a task kind's answer may carry `applied` and `missing` beside `summary`, `topic` and `ops`; both are
  optional lists of short strings.
- **Reading notes** is offered `routing.add` beside `glossary.add`, and an input's run is followed by a rules-only scan
  that proposes new terms; work that learns on its own (`learning: own`) gets neither.

## What 0.3.68 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes; a plugin that reads these records sees more fields.

- **Learning from corrections:** a core task kind `learn-correction`, queued from a correction's signal; it proposes at
  most one piece of knowledge. Rules from anyone but the person are proposals too (`rule.add` joins the knowledge adds).
- **Core records:** a question gains `matters_for` and `dropped_reason`; a rule gains `trust`, `discard_reason`, the
  origin `input` and the status `expired`; every knowledge record gains `more_evidence` (evidence merged from duplicate
  proposals); signal kinds `just_this_time` and `change_requested`.
- **Core ops:** `question.update`, `question.move`, `question.drop`, `question.mark_sent` (the person's), `mail.restore`
  and `list.merge` (system tier).
- **Core lints:** `several-questions` and `question-without-stake`.

## What 0.3.67 adds

Manifests stay `'>=0.3,<0.4'`. A plugin that changes nothing keeps working unchanged.

- **`view.knowledge(text="", *, projects=())`** in a task kind's `packet` function returns `KnowledgeParts(stable,
  per_input)`: what the workspace learned that applies to this task kind, its projects and the text the plugin names.
  Put `stable` in `PacketParts.stable` and `per_input` in `PacketParts.request`; the core logs it on the run. Lessons and
  rules aimed at `<plugin>/<name>` task kinds reach it. A scope naming a project also covers its child projects.
- **`learning: own`**: a record type's class attribute `learning = "own"`, or `registrar.task_kind(..., learning="own")`.
  The core's own learning steps (first-name resolution, fact ranking, and later input learning) don't run on that work.
- **Core records:** a rule gains `constrains` and `reviewed_at`; a run's knowledge log gains `rules_applied`,
  `rules_present`, `rules_moved` and `refused_checks`; a signal kind `narrowed`.

## What 0.3.66 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes.

- **A run's knowledge log**: the core `run` record gains an optional `knowledge` (what it was given from what was learned,
  what was left out by scope, facts left out, the size of the always-sent section, and its searches).
- **Two core lints**, `already-known` and `near-duplicate-question`, on the core's asking ops; a workspace sets their
  severity in its checks like any lint.
- A pack's own packets don't get the knowledge section yet; that is one plugin API call, coming in L2's second wave.

## What 0.3.65 adds

Manifests stay `'>=0.3,<0.4'`.

- **A source can be marked `reported`**: a note that is content the person reports, typed on a button that relays someone
  else or repeating what someone else said. A plugin that reads sources sees one more optional field; a change to how the
  product behaves from such a source waits for the person, as for any input.

## What 0.3.64 adds

Manifests stay `'>=0.3,<0.4'`. Nothing a plugin writes changes; the core gains records and ops a plugin can read.

- **What the assistant learned is core records**: `lesson`, `glossary_entry`, `routing_entry` and `style_note`, each with
  its own `text`, `evidence`, `origin` (person, input, assistant, pack, seed, import), `status` (proposed, active,
  discarded, expired, retired) and an `applies_to` scope. Their ops are `lesson.add`, `lesson.update`, `glossary.add`,
  `glossary.update`, `routing.add`, `style.add` and `knowledge.retire`, all system-tier with Undo. An add from anyone but
  the person makes a proposal, not a held change; it guides nothing until the person keeps it.
- **Standing rules are `rule` records**, seeded once from the workspace's rules file, added by `rule.add` and ended by
  `rule.retire` (system-tier, with Undo). Stage checks read the active records.
- **One scope shape** for rules and knowledge: `task_kinds`, `records`, `filter`, `projects`, `people`, `scope`
  (`workspace` or `projects`) and `except`.
- **Facts** gain `key`, `as_of` and `supersedes`.
- **Signals** gain `run` and `changeset`, and the kinds `kept`, `discarded` and `retired`.
- **A source names its `author`**: the person whose words it is. A note typed on a button that relays someone else
  (They finished it, Followed up, an answer recorded for someone) is that person's content; a change to how the
  product behaves from it waits for the person running the app.

## What 0.3.63 adds

Manifests stay `'>=0.3,<0.4'`.

- **An action can be on hold**: the core `action` record gains an optional `on_hold` (`waiting_for`, `since`), set and
  cleared by the person. An action on hold is never due, overdue or chased. A plugin that reads actions sees one more
  optional field, and should leave held actions out of anything it counts as due.
- **Two signal kinds**: `put_on_hold` and `taken_off_hold`.

## What 0.3.62 adds

Manifests stay `'>=0.3,<0.4'`.

- **A request can name the attempt that replaced it**: the core `request` record gains an optional `superseded_by` (a
  request id). When a later attempt at the same work applies, the earlier ones are done and name it; their held items
  are refused with why. A plugin that reads requests sees one more optional field; nothing a plugin writes changes.

## What 0.3.61 adds

Manifests stay `'>=0.3,<0.4'`.

- **A file kind declares the data level of what is added under it**: `registrar.file_kind(..., data_level=)` takes
  `open`, `internal` or `restricted` (none means internal), and a level the manifest's `requires.data_levels` doesn't
  list refuses the plugin, as for a record type. A file added under the kind (an upload, or a file a person action
  makes) gets that level unless the person chose another at the upload, and a run about the file goes only to accounts
  allowed it. Only the person changes the level afterwards. A file a working copy writes takes at least its record's
  level.
- **A run record may serve no request**: the core `run` record's `request` is now optional (`None` for a run that serves
  no single request, such as the core's mail sorting). A plugin that reads runs should allow it.
- **`setting.propose` names a setting code**: the core Ask op's field is `setting` (a short code from the settings list)
  instead of `key`. It is not offered to plugins' own task kinds, so no plugin is affected.

## What 0.3.60 adds

Manifests stay `'>=0.3,<0.4'`.

- **Sources and files carry their data level**: the core `source` and `file` records gain `sensitivity` (`open`,
  `internal` or `restricted`, default `internal`), which only the person changes. A run on a source or a file goes only
  to AI accounts allowed that level. A plugin that reads them sees one more field; nothing a plugin writes changes.
- **A snapshot says when its item last changed**: the core `snapshot` record gains an optional `changed_at`, filled from
  `SourceItem.changed_at`, so "Look at the last day" finds items already there. A connector that sets `changed_at`
  needs no change.
- **An audit trail**: the core record `audit_entry` (sign-ins, sign-outs, add-ons turned on or off), written by the core
  only. Plugins can read it; it never holds a token, a secret or an account name.

## What 0.3.59 adds

Manifests stay `'>=0.3,<0.4'`.

- **A person can have a first name of their own**: the core person record gains an optional `first_name`, for someone
  who goes by a name other than the first word of their full name. Messages greet them by it, and a bare first name in
  an input resolves to them by it under the same context rule as any first name. A plugin that reads people sees one
  more optional field; nothing a plugin writes changes.
- **A calendar entry record and its op**: the core record `event` (a calendar entry: title, start, optional end,
  project, source, evidence) and the data op `event.add`, which reading notes uses for a date in an input. Plugins read
  entries like other core records.

## What 0.3.58 adds

Manifests stay `'>=0.3,<0.4'`.

- **A mail item can say who else is on it**: `MessageDetails(..., participants=("Name <name@example.com>",))`: the
  people it was sent to and those copied, each as the service names them, with the address in angle brackets when it
  has one. It is optional and defaults to empty, so an add-on that doesn't set it works as before. The core uses it
  to read a bare first name in the message's text: the name means the person of that name who is the sender or one
  of the participants, so a first name that two people share resolves for the one on the message and is held for the
  PM otherwise. A person is matched by an address in their record's `how_to_reach` or by their full name, so give
  addresses where the service has them. The core's own mail folder fills it from the To and Cc headers.
- **A watched item's received date is the item's own**: for a mail item the date the assistant counts "by Friday"
  from is `MessageDetails.received`, never `SourceItem.changed_at`, which a service may move when the message is
  edited, labeled or read. An item with no `received` is dated when it was first read. Nothing changes for an add-on
  that already sets `received`.

## What 0.3.57 adds

Manifests stay `'>=0.3,<0.4'`.

- **A mail item can say it is bulk mail and carry the service's categories**: `MessageDetails(..., bulk=True,
  categories=("promotions",))`. `bulk` is true when the message has a list-unsubscribe header or a bulk or list
  precedence, false when the connector read the headers and found none, and left out when it can't tell. `categories`
  are the service's own categories or labels for the message, as read, in lower case. Both are optional, so an add-on
  that doesn't set them works as before. The core sets aside mail that is bulk, or in the promotions, social or forums
  category, with no AI run (a setting turns this off), and a person's own sender and domain rules sort the rest. A
  matcher you register gets the item's details as `change["message"]`. The core's own mail folder fills `bulk` from the
  message headers.

## What 0.3.56 adds

Manifests stay `'>=0.3,<0.4'`.

- **A connector says what it reads**: `registrar.connector(..., reads="mail")` or `reads="calendar"`, and the manifest
  says the same in `provides.connector_reads: {<connector>: mail}` (only for connectors listed in `provides.connectors`).
  The setup walkthrough offers an add-on that signs in and reads mail or a calendar as a service to connect from that
  declaration, also before the add-on is installed, since a catalog entry carries it. The registration must match the
  manifest exactly, as for every other `provides` list. A connector that says nothing is still told apart by its name
  (mail, mailbox, email, inbox; calendar), and the app logs once that it should declare what it reads. The core's own
  mail folder and calendar address declare it.

## What 0.3.55 adds

Manifests stay `'>=0.3,<0.4'`.

- **A person action's topic** (round 37, 180): `Proposal(..., topic="...")` names what it is about for its title on
  Today and What changed, as a task kind's answer can.
- **Data forms** (181, 182): the guide now says the plugin's loader must read the files with the form's schema (a key
  left out takes the schema's default), and that the list shows each file's first problem.

## What 0.3.54 adds

Manifests stay `'>=0.3,<0.4'`.

- **A sign-in starts its sources**: `registrar.sign_in(..., sources=[{"connector": ..., "label": ..., "settings":
  {...}, "every_minutes": 15}])` lists what the core starts reading as soon as the person signs in (the inbox, the
  main calendar), so signing in is the whole setup. Each is added once per sign-in, only where the workspace reads
  nothing with that connector yet; the person's later changes and removals stand. A sign-in made before its add-on
  declared sources gets them the next time the app starts. Settings are checked against the connector's at load.
- **Send back can keep the work**: the review's Send back has "Undo what the assistant did first" (on by default);
  when off, the work stays, counts as looked over, and the new run builds on it.
- Record pages and the Projects and People tables get their data from the core (names resolved, what is open, what
  happened); this changes nothing a plugin does.

## What 0.3.53 adds

Manifests stay `'>=0.3,<0.4'`.

- **Screen edits go through the applier** (round 34, 171): saving a person, an organization or a project on the
  People & projects screens is now a `record.edit` op applied as the person, so the core's checks and every running
  plugin's validators on `record.edit` see it, as they do for edits from the synced folder.
- **Document panels** (round 36, 174): `render(view, settings, project)` now gets the project's record (as
  `show_for` does), or None for the workspace. A plugin that used the id reads `project.id`.
- **Data-file forms** (round 36, 175–179):
  - `registrar.data_form(..., pattern="*/item.yaml")` covers files matching a glob with at most one folder level
    (default `*.yaml`); `single=True` makes the kind one file named by `pattern`, listed before it exists, with no
    other allowed;
  - each listed file is checked as the loader would, defaults included, and its problem shows on the list;
  - a model-level validator's refusal comes back in its own words (no empty field location);
  - a new file can start from another of its kind (`start_from` on save);
  - a save writes only the keys the file had plus those the person set, never the whole model with its defaults,
    so a left-out key (an `extends`) stays left out.
- **Changesets carry a topic**: a few words naming what the input was about, used for the item's title on Today and
  What changed. A task kind's answer may include `"topic"`; it is optional and cut at a word.

## What 0.3.52 adds

Manifests stay `'>=0.3,<0.4'`.

- **Data-file forms** (round 26, 136): `registrar.data_form(name, label=..., folder=..., schema=Model)`, listed in
  `provides.data_forms`. The `.yaml` files in `folder` of the plugin's data layers are listed with the layer each
  comes from, and edited through a form built from the schema (fields need a default and a description, as in
  `Settings`). A save writes the workspace's or a project's copy, never the shipped one, checked against the schema
  (a refusal names the field), with Undo; a new file starts from the defaults; a copy can be removed to fall back to
  the less specific one. The plugin reads the files as before, with `view.data`. Routes under `/api/data-forms`.

## What 0.3.51 adds

Manifests stay `'>=0.3,<0.4'`.

- **Document panels** (round 26, 135): `registrar.document(name, title=..., render=fn, tab=..., show_for=...)`,
  listed in `provides.panels`. `render(view, settings, project) -> str | None` returns Markdown built per call
  (`project` is the project in view, or None); the screens draw a small subset (headings, paragraphs, lists, tables,
  rules, strong, emphasis, code and links) as their own elements, never HTML. `[text](record:<kind>/<id>)` opens a
  record the plugin may read; an outside link shows its domain. `GET /api/panels/{name}/document?project=` gives the
  blocks; a panel's `view` is "document".

## What 0.3.50 adds

Manifests stay `'>=0.3,<0.4'`.

- **A suggested mapping keeps the person's values:** applying a setup step's suggestion adds the keys the person
  doesn't have; a key they have keeps its own value, nested keys included (0.3.48 replaced it; fixed).
- **`StageStatus.current_label` and `next_label`:** the stages' names as the workspace calls them.
- **Computed cells can share work:** a computed column's function taking a fourth argument gets a dict shared by every
  cell of that column in one listing, new for each listing.
- **The testing kit:** `ws.save(path)` saves a prepared workspace and `plugin_workspace(from_saved=saved)` starts a
  test from a fresh copy; `ws.registered(plugin)` shows what a plugin registered, read-only; `ws.status(plugin)` its
  state, reason and notes; a plugin that doesn't start raises `PluginDidNotStart` (`plugin`, `reason`), and
  `require_started=False` opens the workspace anyway. The kit's attributes are listed in the guide; plugin folders
  are linked in (copied where links aren't allowed).
- **Said in the guide:** Today lines with the core's actions and the `about` each needs; `done`'s third argument
  through wrappers; computed columns can't be named like fields.
- **Add-ons are turned on and off from the Add-ons screen** (`POST /api/packs/{name}/on` and `/off`, with Undo and the
  restart the person chooses).

## What 0.3.49 adds

Manifests stay `'>=0.3,<0.4'`.

- **A source never to be quoted:** a core `source` has `excerpts` ("allowed" or "never"), set by the person only
  (`record.edit`). Checks that compare drafts with sources can read it and apply a stricter limit. A source's content
  fields (its hash, kind, trust, address, when it arrived) are now fixed: no edit changes them.
- **Renaming a setting:** a plugin `Settings` field may declare `json_schema_extra={"renamed_from": "<old name>"}`
  (or a list). A settings file still using the old name reads as the new one, the plugin's status says so, and saving
  the plugin's settings on the Settings screen writes the new name. Keep the old name for one version.
- **`task_kind(..., requires_ops=(...))`:** an answer must include at least one of these ops. One without them is
  refused as a whole (every op in it), which gets the usual fix round, then a stronger tier; one still without them
  is recorded as rejected.
- **The testing kit's throwaway workspace:** `engine.plugin_api.testing.plugin_workspace(<plugin folder>,
  settings=..., root=tmp_path)` loads the plugin in a copy of the fictional demo workspace, with `apply` (as the
  person or the assistant), `ask` (a task kind with a scripted answer, through the dispatcher), `action`, `emit`,
  `move_stage`, `stage_status`, `view` and `folder`. Plugin tests that used the host's internals can move to it.
- **Publishing a pack:** a pack that ships files its source control ignores builds its wheel from the checkout.

## What 0.3.48 adds

Manifests stay `'>=0.3,<0.4'`.

- **Today lines can offer the core's own actions:** `action` may be one of `CORE_LINE_ACTIONS`: "open" the record,
  "review" what waits on it (the assistant's answer as a `changeset`, or a draft on the record), give the "go" to a
  queued `request`, "answer" a `question`, or "move-stage" (a kind with stages). A core action needs `about`; a line
  that names the wrong kind for it fails the contributor like any bad line.
- **A setup step's `done` sees more:** its third argument is now a `SetupState`, still the set of its declared
  secrets that are set, plus `state.settings` (the effective values of the settings it suggests, read from the
  files as they are now, so a hand edit counts), `state.accounts` (AI accounts per role: write, check, research) and
  `state.tool_available(name)`.
- **A suggested mapping merges:** applying a step's suggestion for a mapping setting adds its keys and keeps every key
  the person already has.
- **Panels:** `computed={"column": fn(record, view, settings)}` adds columns that aren't fields (short values, quick,
  contained); a kind with no `project` field is filtered by project through its `layout_project` reference;
  `show_for(project, view) -> bool` lists a panel only on the projects it returns True for (`GET /api/panels?project=`).
- **`view.stage_status(record)`** gives a record's place in the workspace's effective stages (`stages.yaml`, else the
  plugin's defaults): `current`, `stages` (those that apply), `next`, the next stage's `checks` and `ready`. Not
  available inside a stage check.
- **Sign-ins:** `default_redirects` lists the callback addresses the add-on's own registration allows; at any other
  address (another base path, a hosted app) the person is asked for their own, with the reason
  (`SignInView.default_unusable`). The guide now states the default pair's rules.

## What 0.3.47 adds

Manifests stay `'>=0.3,<0.4'`.

- **A sign-in can come with the add-on's own app registration:** `registrar.sign_in(..., default_client_id=...,
  default_client_secret=..., default_app_note=...)`, so people sign in without registering anything with the
  service. Ship one only for a registration the service issues to apps on a person's computer (its secret isn't
  treated as confidential, and it allows loopback addresses). `default_app_note` says what using it means.
- **People can paste their own registration** on the Sign-ins row (on their own computer), kept beside the plugin's
  other kept secrets and readable by its owner only. `own_app_steps=[line, (line, https link), ...]` lists how to
  make one, shown beside the paste boxes and the address to allow. Which is used: the workspace's references in
  `workspace.plugins.secrets`, else the pasted one, else the add-on's. Changing it starts the sign-in over; a
  pasted one can be set aside and brought back.
- **Restarts, said once:** the app never restarts on its own. A plugin's settings changing, or plugins being turned on
  or off, makes it say a restart is needed and wait for the person; registration keeps the old settings until then,
  and the plugin isn't told. The guide's "Registering" said otherwise; corrected.
- **The guide lists the action's context methods,** `context.estimate` among them.

## What 0.3.46 adds

Manifests stay `'>=0.3,<0.4'`.

- **Organizations are records:** a core record `organization` (name, aliases, notes) holds each company, client or
  supplier once. A person's `org` is now an organization's id (`RefTo("organization")`), not a name; read the
  organization for its name. A workspace whose people held names is moved over when it opens. `person.add` and
  `record.set` on a person's `org` still take a name from the assistant: it is matched to an organization by name or
  alias, or a new one is made.
- **A project's priority** is in the project screens and API, from the `project-priority` list.

## What 0.3.45 adds

Manifests stay `'>=0.3,<0.4'`.

- **`changeset.reviewed`:** an event when the person accepts the assistant's answer to a request (`outcome`
  "accepted") or sends it back with a note ("sent_back"), with the changeset `id`, the `request`, its `task`, its
  `part` and the record it was `about`. An accepted draft raises `text.accepted` as before.
- **All-or-nothing answers:** `registrar.task_kind(..., all_or_nothing=True)` applies an answer's ops together: if
  any is refused, none applies, and the changeset is recorded as refused with each op's reason.
- **References deeper:** `RefTo` is honored six levels into a record (its own fields, then nested models), checked on
  write and guarded on delete; deeper than that it is a plain id your own validator checks.
- **Pricing inside an action:** `context.estimate(task, input_tokens, output_tokens=None)` gives what one run of a
  core or own task kind would cost in USD, priced on the account it would use first, as the request's go will; None
  when there's no listed price. Sum it over the runs an action queues.

## What 0.3.44 adds

Manifests stay `'>=0.3,<0.4'`.

- **Settings forms for plugins:** the Settings screen's data (`GET /api/settings`) now includes each running plugin's
  `Settings` model as its own group, keys `plugins/<plugin>.<field>` with `plugin` set, read from
  `config/plugins/<plugin>.yaml`. The same rules as the core's settings apply: types and choices from the model,
  `json_schema_extra={"enabled_by": "<field>"}` to grey a field while its switch is off, `{"picker": "folder"}` for
  a folder chooser. A save is checked against the model (a refusal names the field), keeps the file's comments, is
  recorded with Undo, and (corrected in 0.3.47) asks for a restart like any settings change. The form itself on the screen follows
  shortly; the data and the save are in place now.

## What 0.3.43 adds

Manifests stay `'>=0.3,<0.4'`.

- **A project with its family:** `view.list(kind, project=<id>, ancestors=True)` also takes records in the projects
  above it (its parent, then the parent's parent), and `descendants=True` those in every project below it; the
  project's own come first, then nearest first. They need a project id.
- **Said in the guide:** an item's ops can't name a record a main op creates by id; they apply after the main ops in
  the same transaction, so an own op's `apply` finds it by its natural key (`writer.find`). A group stays on the
  review while it has items, choices or requests, even when all are dropped; dropping them all queues nothing. The
  core keeps no cache for validators (the view is made anew for each call): cache costly derived data by content.
  `candidates` with no project lists what the note could be about across the workspace, most likely first.

## What 0.3.42 adds

Manifests stay `'>=0.3,<0.4'`.

- **Value lists:** `registrar.value_list(name, label=..., values=[...])` (listed in `provides.value_lists`) declares a
  list of the values a field may take, shown as a dropdown. Bind a field of your own record type with
  `Annotated[str | None, InList("<plugin>/<name>")]` (or a list of them); a field may also take a core list
  (`project-status`, `project-phase`, `project-priority`, `project-group`). Binding to another plugin's list is
  refused at load.
- **The person owns a list:** `values` are a workspace's first values, given once together with any values its
  records already hold; after that the person adds, renames and retires values (core ops `list.add`,
  `list.rename`, `list.retire`, system tier, each with Undo). A rename changes every record that holds the value in
  one step. Never rely on a value staying on a list.
- **Enforced where records are written:** a value not on its list is refused for any writer (a plugin op, the
  assistant, an edit), with the list's values in the reason. A value a record already holds stays valid after it is
  retired. The assistant's packets list the values each bound field takes.
- **Core fields:** a project's `status`, `phase`, `priority` and `group` now take their values from core lists.

## What 0.3.41 adds

Manifests stay `'>=0.3,<0.4'`.

- **What an item is, for Today:** `SourceItem` takes `event=EventDetails(start, end, all_day, where, cancelled,
  repeats)` for a calendar item or `message=MessageDetails(sender, received, unread)` for a mail item (at most one).
  Times are ISO 8601 with their offset, or plain dates for all-day events; a read with an unreadable time, an end
  before its start, or both details is refused like any malformed read. The watcher keeps them on the item's
  snapshot, and Today shows the day's agenda (`GET /api/today/agenda`) and what came in (`GET /api/today/arrived`,
  leaving out what a triage rule closed). The text still carries everything the assistant reads.
- **A change in details alone** (a message opened, so `unread` turns false) updates what Today shows without handing
  the item in again.
- **Series:** an event that stands for a repeating series the connector didn't expand carries `repeats`; the agenda
  places only what it can date, so a connector whose service can list occurrences should list them.
- The core's calendar and mailbox connectors fill these.

## What 0.3.40 adds

Manifests stay `'>=0.3,<0.4'`.

- **`retry_after(headers)`** is part of the plugin API: a Retry-After header (seconds or an HTTP date) in seconds
  from now, capped at the host's longest wait, for a connector that raises `throttled` itself.
- **Testing connectors:** `Asked.path` is decoded (`Asked.raw_path` is as sent), `query` and `form` keep blank
  values, `Asked.param(name, default)` gives a parameter's first value, and `connector_context(granted={sign-in:
  scopes})` answers `context.granted`. Left out, `context.granted` stays None as before. `Reply()` with neither `json`
  nor `text` is an empty body; `Reply(json={})` is an empty JSON object.
- **Said in the guide:** `context.granted` is empty while signed out, so ask for the token first; an `account=`
  function's `ConnectorError` is quiet and anything else counts as the plugin failing; what a triage matcher's
  `before`, `now`, `added` and `removed` hold for new, changed and removed items; only `##` sections of a help file
  are read; and how a 404 and a 410 change marker differ.
- **Unchanged on purpose:** a 410 still comes back as a response (released connectors check for it), and a
  read-only plugin host for scripts is on the list for later.

## What 0.3.39 adds

Manifests stay `'>=0.3,<0.4'`.

- **Checking a pack whose plugins share a helper package:** `cockpit pack check` takes an installed plugin's name as
  well as a folder. Install the built package beside the host and run `cockpit pack check <plugin name> --entry
  catalog/pack.yaml`; the pack loads as people will install it, helper package included.
- **One entry file for several packs:** an entry file with a `packs:` list is matched to the plugin by its `id`; a
  file that lists no pack with that id fails the check.
- **A workspace link to the installed copy itself** (a development install linked with `cockpit demo --plugin`) is
  the same plugin: no "the installed one isn't used" note, so the check no longer fails on it.

## What 0.3.38 adds

Manifests stay `'>=0.3,<0.4'`.

- **Optional single references:** `Annotated[str, RefTo("kind")] | None` is now a reference (the delete check and
  name rendering see it); before, only `Annotated[str | None, RefTo("kind")]` was. References inside unions of
  models (a field holding one of several shapes) were already found, and are now tested.
- **Nested models in ops:** an op model's nested models are validated as those models, their validators included,
  wherever the op arrives (a run, an action, a handler). Recursive models make a recursive JSON schema (`$defs`
  and `$ref`), which works; keep AI-facing op schemas shallow anyway, since some providers' structured output limits
  nesting.
- **A part's label:** a request's `part` may carry `label` (up to 80 characters, such as "3 of 5"); it is kept on the
  request and comes back in `origin["part"]`, `view.part` and the `text.accepted` payload's `part`.

## What 0.3.37 adds

Manifests stay `'>=0.3,<0.4'`.

- **Publishing a pack:** a set process (the guide's "Publishing a pack" section and the catalog's PUBLISHING.md):
  release in the pack's own repository, write `catalog/pack.yaml`, run `cockpit pack check <folder> --entry
  catalog/pack.yaml`, add a Publish request to the questions file and tell the host's session. The host verifies and
  opens a pull request on the catalog; the owner merges it. A plugin repository never writes to the catalog.
- **`cockpit pack check`:** the manifest reads and fits this host, the pack loads in a throwaway demo workspace, and
  the catalog entry fits the catalog's format and matches `plugin.yaml` as written (id, version, `plugin_api`,
  `provides`, `requires`).
- **Setup steps and secrets:** a `done` taking a third argument gets the names of the plugin's declared secrets that
  are set (a frozenset, never the values).
- **Wording keys:** a plugin's wording files may set only the keys the screens read for its own things, now listed
  in the guide's Wording section (`task.`, `stages.group.`, `op.`, `setup_step.`, `welcome.skip.`); others are left
  out with a note. Connectors, sign-ins, actions, panels and triage rule kinds take their names from `label`.
- **A linked plugin imports its own package by name:** a plugin folder with an `__init__.py` is loaded under its
  package's own name (unless something else has it), so `from mypack.part import x` works linked as it does
  installed.
- **Guide notes:** `context.access_token` on a sign-in the plugin doesn't register raises `PluginMisuse`; a
  `client_secret` is sent to `token_url` with the code and every renewal, beside PKCE.

## What 0.3.36 adds

Manifests stay `'>=0.3,<0.4'`.

- **What a sign-in asks, before the person leaves:** `registrar.sign_in(..., allows=("Read your mail", ...))`, up to
  10 short lines, shown on the Sign-ins row and the sign-in's setup step.
- **The signed-in account:** `account=fn(context) -> str`, called once after signing in with a connector-like
  context (`context.web`, `context.access_token`), names the account ("Signed in as …"). A failure leaves it unnamed
  and is contained.
- **What was allowed:** `context.granted(name) -> set[str]` is the scopes the person allowed (what the service said,
  or everything asked when it doesn't say). The row names scopes asked for and not granted; a granted scope written
  with the service's resource in front of it counts for the plain name.
- **A refused renewal:** when the service refuses to renew a sign-in, it shows "Sign in again" at once, every later
  read gets `auth` without asking the service again, and the person gets one question to sign in again, closed when
  they do. A service that is down or out of reach doesn't count as a refusal.
- **Signing out withdraws access:** `revoke_url=` (HTTPS, on a declared host): signing out sends the token there
  (RFC 7009), best effort, before forgetting it.
- **The service's refusal:** the callback keeps the service's `error` code and description; the screen shows them as
  text.
- **A setup step per sign-in:** the core adds one, labeled with the sign-in and what it asks, done while signed in,
  so a plugin's own steps don't need to check.

## What 0.3.35 adds

Manifests stay `'>=0.3,<0.4'`.

- **A service's "wait":** the web client raises `ConnectorError("throttled", retry_after=seconds)` for 429, and for
  503 with a Retry-After (seconds or a date, at most a day). A connector may raise it too. The watcher records the
  read as throttled, doesn't count it toward `watch.failures_before_asking`, and doesn't read the source again before
  the wait ends.
- **The service's own error:** a `ConnectorError` the web client raises from an answer carries `status`, `headers`
  and `body` (`err.json()` parses it), so a connector can read the service's error code and raise a better kind.
  Statuses other than 401, 403, 404, 429 and 5xx come back as responses to read.
- **Removals from change-only reads:** `Poll(removed=[key, ...])` with `complete=False` hands in those keys as gone,
  like an item missing from a complete read (when the source reports removals). `checked_poll` refuses `removed` on a
  complete read, a key listed twice, and items that aren't `SourceItem`s with text.
- **A failed read keeps the last good state:** the next read starts from the state of the last read that worked, not
  from nothing.
- **Testing connectors:** `engine.plugin_api.testing` has `connector_context(service, network=, secrets=, tokens=)`,
  where `service(asked) -> Reply` answers every request, and `read(poll, settings, state, context)`, which runs a
  poll and checks it as the watcher does. Plugin tests no longer need `engine.net` or `engine.connectors`.
- **The host for a plugin's tests:** `PM_COCKPIT_WITHOUT_SCREENS=1` builds the host's wheel without the web screens,
  so `uv pip install "pm-cockpit @ git+<host repository>@<ref>"` works without npm.
- **Guide:** a Connectors section (`SourceItem`, `Poll` and `ConnectorError` fields, the web client's statuses and
  the testing helper); the sign-in callback address must be registered exactly as the Sign-ins section shows it; one
  distribution's plugins may share a helper package of their own.

## What 0.3.34 adds

Manifests stay `'>=0.3,<0.4'`.

- **A part for work that answers with ops:** a request of any task kind may name a span of a long text, `{first,
  last}` paragraph numbers (with `base`). For a kind that answers with ops, the core checks the shape and passes the
  span to the packet (`view.part`) and to validators (`origin["part"]`); it doesn't use it for the answer. Drafts keep
  their parts as before.
- **A hand-in names its project:** the person can say which project a hand-in is about (`project` on the hand-in). The
  reading is told so, and a `candidates` function taking a third argument gets that project's id (or None), so it can
  list that project's records first.
- **Keeping or dropping offered work:** each of a proposal's `requests` gets an id (`r1`, `r2`, ...) and is kept or
  dropped on the review, like an item. A request may name a proposal `group`, so setting the group sets it too. A
  request about an item is still dropped with that item.

## What 0.3.33 adds

Manifests stay `'>=0.3,<0.4'`.

- **Signing in to a service as the person:** `registrar.sign_in(name, label=, authorize_url=, token_url=, scopes=,
  client_id="client-id", client_secret=None, params=None)`, listed in `provides.sign_ins`. The flow is OAuth 2.0
  authorization code with PKCE. Both addresses are HTTPS on hosts in `requires.network`. `client_id` (and
  `client_secret`) name secrets in `requires.secrets`, which hold the app registration the person made with the
  service. The person signs in from the screens; the service sends them back to `<the app's address><base
  path>/api/sign-ins/callback`, which the registration must allow. The core keeps the tokens on this computer (never
  in settings or the export) and renews them. A connector gets a current token with `context.access_token(name)`;
  when the person has to sign in (again), it raises `ConnectorError("auth", ...)`. The plugin never sees the refresh
  token.

## What 0.3.32 adds

Manifests stay `'>=0.3,<0.4'`.

- **A packet knows its request:** `PacketContext` has `request` (the run's request id) and `part` (the part of the
  record it names, as given to `queue_request(part=)`, or None).
- **The request behind an accepted version:** the `text.accepted` payload gains `request` (the request whose run
  drafted the version, or None for the person's own edit or an import) and `part` (the part it named, or None). The
  path from a version's `run` to the run record to its request also works.
- **Work the person starts on fewer records:** `registrar.task_kind(..., start_where={...})`, in the same form as
  `where`, narrows only the runs the person starts (offered on a record's page, or started there). Requests a plugin,
  an action or a stage queues, and any request naming a `part`, check `where` alone, so a kind started only on an
  empty record can continue part by part once it has text.
- **The smallest output:** a packet's `max_output` hint is raised to at least 256 tokens. The guide now says so.

## What 0.3.31 adds

Manifests stay `'>=0.3,<0.4'`.

- **A plugin names its own kinds on screen:** `provides.wording: [wording.yaml]` lists YAML files beside the manifest,
  each a map from a wording key to its text, such as `stages.group.<plugin>/<kind>: Chapters` (the heading for a kind
  of record in Stages). Every key must name something in the plugin's namespace (contain `<plugin>/`), and text is at
  most 200 characters; other entries are left out and noted on the plugin. Each AI task kind's `label` also becomes
  its `task.<kind>` wording. The workspace's `ui.wording` overrides any of them.

## What 0.3.30 adds

Manifests stay `'>=0.3,<0.4'`.

- **Settings in validators:** a validator with a parameter named `settings` (or `**kwargs`) gets the plugin's settings
  by keyword, beside `(op, view, origin)`. A check that depends on a setting belongs in a validator: its refusal goes
  back to the run in a fix round. A refusal raised from an op's `apply` still refuses the op with no fix round.
- **The run's request in `origin`:** `origin` gains `request` (the request's id, or None outside a run) and `part`
  (the part of the record the request names, as given to `queue_request(part=)`, or None). The request's note is not
  passed: name what a run works on with `part`, not in words.
- **A limit for queued work:** an action's `Proposal.requests` is limited by `workspace.plugins.actions.max_requests`
  (default 100), no longer by `max_items`; `context.limits["max_requests"]` gives it.

## What 0.3.29 adds

Manifests stay `'>=0.3,<0.4'`.

- **Lints:** a lint taking a fourth argument gets the run's `origin`. Plugin lints check the assistant's proposals
  only, never the person's own changes. A lint the workspace switched off isn't called. `checks.yaml` `projects:
  {<project id>: {<lint>: <severity>}}` sets severities for one project's work (the project of the op, or of the
  record the run is about).
- **An action's clock:** `context.now` (aware, the workspace's time zone) and `context.today`.
- **Requests about records a proposal creates:** in `Proposal.requests`, `"about": {"op": i}` (an op of the
  proposal's own `ops`) or `{"item": "<id>"}` resolves to the record of the task kind's `on` kind that op or item
  created, when the proposal applies. A dropped item's request is dropped; so is one whose op didn't apply.
- **Interface items:** `about(view, settings, item, task)` may take the interface's task name being requested.
  `view.interface_about(item, task)` returns the (kind, id) a request would be about, or None, so a handler can check
  first. A request a handler or job queues that is refused is skipped and noted on the plugin; the rest of its work
  goes ahead.
- **Staged ops say where they came from:** ops staged with `apply_op` have origin actor "plugin" and via "handler" or
  "job".
- **Items per project:** when reading every project's items fails, the provider is read project by project, and only
  the failing projects' items are left out.
- **Notes and confidential work:** a hand-in may carry a `sensitivity` (the person says how sensitive it is), which
  only raises the run's level. A plugin op offered to notes is offered only when the note's level covers every record
  type it writes. `registrar.op(..., notes=True, candidates=fn)`: `fn(view, settings) -> [(id, name)]` lists records
  the op may name (at most 50), shown to that run.
- **Help for asks:** `provides.help: ["help/guide.md", ...]` ships help files (Markdown, one section per `##`
  heading); asks read and cite them like the user guide.
- **Setup steps suggest settings:** `registrar.setup_step(..., settings={"ai.budgets.confirm_unpriced": True})` shows
  the suggestion with Apply, saved like any settings change (checked, with Undo). A step can't suggest accounts,
  tiers, secrets, which plugins are on, or the server's settings.
- **Agent accounts:** `agent.home: fresh` gives each run an empty home folder with only `agent.home_files` copied in;
  the lockdown test then checks that nothing a run writes there reaches the next run.
- **Stated in the guide:** registration may read settings and is fixed until restart; a check in `applies_if` needn't
  also be an entry check.

## What 0.3.28 adds

Manifests stay `'>=0.3,<0.4'`.

- **Drafts over part of a text:** `context.queue_request(..., part=...)`, and `"part"` in a proposal's requests.
  - For an anchored draft, `{"first": n, "last": m}`: the run sees only paragraphs p<n>..p<m>, with the ids they have
    in the whole text, and must account for those only. The pending version is the whole text with that span
    replaced; paragraphs outside it keep their text and authorship, and the paragraph map covers the whole text.
  - For any other draft, `{"after": n}` (0 for the start, "end" for the end): the run writes only the new part, and
    the pending version is the text with it added there (new paragraphs map from nothing).
  - Add `"base": <version number>`: when the text has moved on, the run is refused ("choose the part again") rather
    than revising the wrong paragraphs. A span past the end is refused too.
  - Two pending versions over disjoint spans are reviewed as before: once one is accepted, the other's review is
    three-way against it.
- **Output size per run:** `PacketParts(..., max_output=, expected_output=)` size this run (the estimate and the
  call), unless the workspace sets those for the task kind in `ai.tasks`.
- **`where` presence tests:** `ANY` means the field has a value, `None` that it has none; on a long text field they
  ask whether the record has text in it.
- **Stated in the guide:** the core adds the text to revise after the packet's parts, as untrusted material, with ids
  in unit order over the whole text; `Removed:` comes before the `<questions>` block; `reference_only` implies
  `no_copy`; a packet function that raises StoreError stops the run with no retry, fix round or escalation;
  `register` may read `registrar.config`, and registration is fixed until the app restarts.
- Refusals from a request's `about` check use the kind's label.

## What 0.3.27 adds

Manifests stay `'>=0.3,<0.4'`.

- **Network for connectors:** `requires.network` lists the hosts a plugin's connectors may reach ("api.example.com",
  "*.example.com"). `context.web.get/post(url, ...)` reaches only those, over HTTPS (plain HTTP only on this computer),
  follows redirects only to allowed hosts, caps answers at 5 MB, and raises `ConnectorError`: offline (no connection),
  outage (timeouts, 429 and server errors), auth (401), no_access (403), not_found (404). Other statuses come back
  for the plugin to read.
- **Secrets:** `requires.secrets` names them. `context.secret(name)` reads the workspace's reference in
  `workspace.plugins.secrets.<plugin>.<name>` (env:NAME or file:/path), else a value the plugin kept on this computer
  with `context.keep_secret(name, value)` (readable only by the user). An undeclared name is refused.
- The core ships a `feed` connector (RSS and Atom).

## What 0.3.26 adds

Manifests stay `'>=0.3,<0.4'`.

- **Triage matchers:** `registrar.triage_matcher(name, match=fn)`, listed in `provides.triage_matchers`.
  `match(change, params) -> reason | None`; `change` has source, key, title, change, author, before, now, added,
  removed and our_accounts. A workspace uses it in `watch.yaml` `triage: [{name, kind, params, why, sources}]`; the
  first rule that returns a reason closes the change before the assistant reads it, and the person sees it under
  Auto-closed with the rule and reason and can take a closer look. A failing matcher counts as no match and is
  contained. The core's matchers are `cosmetic`, `by-us`, `terms-absent` and `name-matches`.
- **Folding:** a newer change to an item whose earlier change is still waiting is handed in once, with the earlier
  change first; the older request records `folded_into`.
- `workspace.our_accounts` names the accounts that are ours; a watched change by one is marked `by_us`.

## What 0.3.25 adds

Manifests stay `'>=0.3,<0.4'`.

- **Connectors:** `registrar.connector(name, label=..., settings=Model, poll=fn)`, listed in `provides.connectors`.
  `poll(settings, state, context) -> Poll(items=[SourceItem(key, title, text, author=None, changed_at=None,
  link=None)], state={...}, complete=True)`; raise `ConnectorError(kind, detail)` with kind `auth`, `no_access`,
  `not_found`, `outage` or `offline`. A workspace reads it by naming it in `watch.yaml` (`sources: [{id, connector,
  label, every_minutes, project, first_run, report_removed, settings}]`). The core keeps snapshots, compares, and
  hands in what is new, changed (with a readable diff) or gone as outside content for the assistant; the first read
  only notes what is there unless `first_run: all`. A failing read is contained like a job; the person is asked once
  after `watch.failures_before_asking` failures in a row. Connectors can't reach the network yet: that comes with
  `requires.network`.
- The core ships a `folder` connector (text files in a folder) and a `fake` one for tests.

## What 0.3.24 adds

Manifests stay `'>=0.3,<0.4'`.

- **Setup steps:** `registrar.setup_step(name, label=..., done=fn, explanation="", action=None)`, listed in
  `provides.setup_steps`. The first-run setup shows it after the core's steps; `done(view, settings) -> bool` says
  whether it is done and is contained like Today lines; `action` (one of the plugin's person actions on the
  workspace) is its button. The person can skip it and reopen it.
- **Settings from the screens:** `GET /api/settings` describes every core config key; `POST /api/settings` saves
  changes with the fingerprint the form was built from, refuses keys set by environment variables or flags, keeps the
  files' comments, records each change as a `setting_change` and restarts the app to use them. Plugins' own settings
  files are not edited here yet.
- **Asking the assistant:** a core task kind `ask` with three core ops plugins may see in changesets: `answer` (an
  `answer` record whose `cites` must quote the help material), `setting.propose` (a `setting_proposal` the person
  applies) and `report.draft` (a `report` to the maintainers the person sends). Plugins' ops are not offered to asks.

## What 0.3.23 adds

Manifests stay `'>=0.3,<0.4'`.

- **Requests about an interface item:** `context.request_from(..., item=item)` takes an `InterfaceItem` read from
  `view.interface`. The item's provider gets the work, and its `provide_interface(..., about=fn)` says which of its
  records the item stands for: `about(view, settings, item) -> record | (kind, id) | None`, given the item as `items`
  returned it (fields the definition doesn't declare included). `InterfaceItem.key` is the host's stable key for it.
- **Undeclared item fields are noted:** fields a provider's items carry that the definition doesn't declare are
  listed in the provider's notes (Settings, plugins), once.
- **A failing call is contained:** when Today lines, an `items` function, an event handler or a job raises, that call
  is skipped (that delivery of the event, those lines or items, that job run) and noted on the plugin. The plugin is
  turned off only after `workspace.plugins.failures_before_off` failures in a row from the same place (default 3); a
  call that works resets the count. An item that doesn't match the definition is left out and noted. Breaking the
  contract (a handler writing records directly, staging another plugin's or a core op) still turns the plugin off at
  once, as do failing op callbacks, validators, lints and stage checks.
- **Refusals shown on a proposal:** a preview tries the whole proposal without keeping anything. An item that would be
  refused carries its reason (`refused`) and starts dropped; anything else that would be refused is listed in the
  review's `problems`. The person changes a choice rather than the action failing. The screen holds a text choice to
  its `max_length`.
- **Room left for files:** `context.limits["room_mb"]` is what is left of `max_total_mb`. Files in one proposal are
  checked together against it.
- **A kind's label:** `record_label` on a record type is what one record is called ("chapter"); messages use it, or
  the kind id's last part.
- **Work follows its change:** ops a handler stages and requests it queues record the change whose event they answer
  (`follows` on the request), and What changed shows it on the row.
- **Stages for some records only:** a stage's `applies_if` lists check or rule ids that must all pass for it to apply
  to a record. Moves forward pass over a stage that doesn't apply, and a stage that doesn't apply can't be chosen.

## What 0.3.22 adds

Manifests stay `'>=0.3,<0.4'`.

- **Always waiting for the go:**
  - `context.queue_request(..., needs_go=True)` and `context.request_from(..., needs_go=True)` queue work that waits
    for the person's go, whatever it costs.
  - The workspace setting `ai.budgets.confirm_unpriced` makes every run whose cost can't be estimated wait too.
- **Queueing from an action:** `Proposal(..., requests=[{"task", "about", "note"}])` queues the plugin's own task
  kinds when the person applies it, each waiting for the go. They are shown on the review, and nothing is queued
  when an all-or-nothing proposal is rejected.
- **Validators know the run:** a validator's `origin` carries `task` (the run's task kind) and `about` (`{kind, id}`
  or None).
- **Placing through a reference:** `layout_project` on a record type names the reference field whose record's project
  it is placed under, when it has no project of its own.
- **Collections sort numbers as numbers.**
- **The current version:** `view.text_version(record, field)` returns it, or None.
- **`Part(..., no_copy=True)`:** material the run may describe and quote as evidence but must not copy into new text.

## What 0.3.21 adds

Manifests stay `'>=0.3,<0.4'`.

- `registrar.panel(..., new_action=None)`: a person action of the plugin's on the workspace (`on` None), shown above
  the panel's rows to add one.
- `POST /api/records/edit {kind, id, fields, read_version}` applies the person's own `record.edit` on any shown
  record, with Undo.

## What 0.3.20 adds

Manifests stay `'>=0.3,<0.4'`.

- **`registrar.op(..., notes=True)`** offers the op to the core's reading of notes, so the assistant can use it on
  what the person hands in. Give it an `EvidenceIn` field for what it claims; the core checks the quote.
- **`<plugin>/*` in a `provides` list** stands for identifiers the plugin's own settings define; any identifier in
  its namespace is accepted. It must stand alone in its list.
- **The define-your-own kit** (`plugins/kit`, design 3.10) is built on these. Workspace templates (`templates/`,
  `cockpit template list|apply|save`) set plugins up from one file.

## What 0.3.19 adds

Manifests stay `'>=0.3,<0.4'`.

- **`registrar.action(..., where={field: value})`** narrows the records an action is offered on and may run on, as for
  task kinds. Checked at load.
- **`context.apply_op(op)`** in an event handler or a job stages one of the plugin's own ops. It applies through the
  applier after the handler returns, as a changeset from the plugin the person can see and undo, treated like work
  from outside content: system ops and person-only values wait for the person. Staging a core op turns the plugin off.
- **`view.user`** is the workspace person's id, and `view.person_name(person_id=None)` their display name (yours when
  no id is given), for a byline.
- **`record.set` can set a project's `owner`**, a person id. Evidence for `record.set` fields is required only for
  changes that aren't the person's own.
- **`Preview(..., alt="")`** describes an image for people who can't see it; the caption is used when it's empty.

## What 0.3.18 adds

Manifests stay `'>=0.3,<0.4'`. `provides.panels`, `provides.today` and `provides.jobs` are now available.

- **Today lines:** `registrar.today(name, lines=fn)`, where `fn(view, settings) -> list[TodayLine(id, text, about,
  action, why, until)]` is called whenever Today is shown.
  - A line's `action` is one of the plugin's person actions or task kinds.
  - `GET /api/plugin-today` lists them, each saying whether its action is a person action or AI work.
- **Panels:** `registrar.panel(name, title=, kind=, columns=, view="table", filter={}, primary_action=None,
  row_actions=(), tab="work")` is a screen described as data (design 7.2).
  - **Checked at load:** the columns and filter must be fields of the kind, and the actions must be the plugin's own
    actions or task kinds on that kind.
  - **Routes:** `GET /api/panels` and `GET /api/panels/<name>/rows?project=`.
- **Jobs:** `registrar.job(name, every_minutes=, run=fn)`, where `fn(context)` gets an `EventContext`. It reads,
  queues requests, files questions and raises interface events.
  - **When:** it runs while the app runs, when due. `workspace.plugins.jobs.<name>` turns it off or changes how often.
  - **Records:** each run is a `job_run` record. A job that raises is recorded as failed and turns the plugin off.
  - **Route:** `GET /api/jobs`.

## What 0.3.17 adds

Manifests stay `'>=0.3,<0.4'`.

- **Interfaces:**
  - `items(view, settings, project)` may take the project: an id when one project's items are asked for, None for
    everything. A two-argument function still works.
  - A provider can raise interface events from an event handler with `context.emit("<name>.<event>", payload)`, for
    events that follow a core change such as a stage move.
  - `InterfaceItem.data_level`.
- **Data levels in packets:** `Part(..., data_level="restricted")`. A run goes only to accounts allowed the highest
  level among the record it is about and its parts.
- **`project.add` takes `children`:** ids of existing projects to move inside the new one, in the same op, so Undo
  takes both back. A child that would make a loop is refused.
- **Person actions:**
  - `Choice(..., text=True, max_length=200)` is a value the person types.
  - `Proposal(..., all_or_nothing=True)`: one refused op refuses every op, and the changeset is recorded as
    `rejected`.
  - `ActionContext.limits` holds max_items, max_previews, preview_mb, keep_minutes, max_file_mb, max_total_mb and
    accepted_types.
  - A `Group` has no value: setting a group sets each of its choices, and each reaches the action in `choices`.
- **Documented:**
  - the dry run that validators see;
  - that op labels are made against the records before the changeset;
  - that `text.accepted` always carries all three authorship kinds.

## What 0.3.16 adds

Manifests stay `'>=0.3,<0.4'`. Interfaces between plugins (design 3.9):

- **Define:** `registrar.define_interface(name, version="1.0", item=Model, events={"approved": Payload},
  task_kinds=("short-blurb",))`, listed in `interfaces.defines`. Within a major version, add only optional fields.
- **Provide:** `registrar.provide_interface("<name>@<major>", items=fn, task_kinds={"short-blurb":
  "<plugin>/<own task kind>"})`, listed in `interfaces.provides`. `items(view, settings) -> list[dict]` returns
  everything offered. Each item is checked against the definition when read and may carry `project` and
  `data_level`. Raise the interface's events from an op with `writer.emit("<name>.<event>", payload)`; the payload is
  checked against the definition, and one that doesn't match turns the provider off.
- **Use:** declare `interfaces.uses: [{interface: "<name>@<major>[.<minor>]", optional: true}]`.
  - **Reading:** `view.interface("<name>@<major>", project=...)` returns `InterfaceItem(provider, data)` copies from
    every running provider. Items above the user's data levels (`requires.data_levels`) are left out.
  - **Events:** subscribe to `<name>.<event>`.
  - **Requests:** in an event handler, `context.request_from("<name>@<major>", "<task>", note, about,
    provider=None)` queues the provider's own task kind, with the usual estimate, go and review.
- **Loading:**
  - A required interface with no running definition and provider keeps the user off, with the reason.
  - An optional one reads empty.
  - A provider whose items don't fit the definition is turned off.

## What 0.3.15 adds

Manifests stay `'>=0.3,<0.4'`.

- **Collections:** a record type with `layout_collection = True` writes every record whose `layout` renders the same
  path into one YAML file, a list of entries each with its id, sorted by `layout_sort` (the id when unset). Record
  types with long text can't be collections.
- **Paths through a reference:** a layout may use `{ref.field}` (with a format, `{chapter.order:02}`), where `ref` is a
  field holding one `RefTo` id and `field` a field of the record it refers to. Checked at load. A missing record or
  value becomes the id.
- **Generated files:** `registrar.derived_file(name, path=, depends_on=, render=)`, listed in
  `provides.derived_files`. `render(project, view, settings) -> str | None` makes a read-only file at `path` in each
  project's folder, for every project with records of a kind in `depends_on`. It runs each time the folder is
  written, so it must be pure and quick. An edit made outside is reported and overwritten; a render that raises turns
  the plugin off.
- **`record.edit`, a new core op:** the person's own change to fields of any record, core or a plugin's (not long
  text, the stage, the id or `ext`), checked against the record type, its unique groups and references. Person only.
- **Outside edits come back:** with `storage.sync.watch_outside_edits` (default true), a readable file changed in
  another program becomes a proposal. Nothing applies without the person:
  - **long text:** a pending `text.propose` made from the version written there, noted "edited outside the cockpit";
  - **fields:** a held `record.edit`;
  - **a collection:**
    - a changed entry: a held `record.edit`;
    - a removed entry: a held `record.delete`;
    - an added entry: reported, not created.
  - **a working copy in `working/`:** taken back by its format.

  Each change is handled once. Once the person has decided, the file is written again from the records.
- **More in the folder:**
  - **sources:** texts handed in, and files the person added, go in the project's `sources/`;
  - **outputs:** files the person approved from actions go in `outputs/`, the newest of each;
  - **working copies:** copies that are out go in `working/`;
  - **the machine copy** now holds the bytes of every file and source, so a handover carries them.

  A deleted source, output or working copy is reported, not written again.

## What 0.3.14 adds

Manifests stay `'>=0.3,<0.4'`.

- Layout declarations: a record type sets `layout`, a path template relative to its project's folder in the synced
  folder, without an extension, such as `"plan/chapters/{order:02}-{slug}"`.
  - **Placeholders:** `{field}` and `{field:format}` take the record's own values (and `{id}`). A missing value
    becomes the id.
  - **Checked at load:** the template must be a relative path of the record's fields, with no extension and no name
    the core keeps for itself.
  - **The files:**
    - a record with one long text field is a Markdown file: its other fields as YAML front matter, the current text
      as the body;
    - a record with none is a YAML file;
    - a record with several is a folder with `record.yaml` and a file per field.
  - **Versions:** every version of the long text goes in `.versions/<name>/` beside it (`v<N>.md`, or `.txt` for
    plain text), with `versions.yaml` listing each version's status, source, base, words per author, authorship spans,
    note, unmapped and questions.
  - **No layout:** a record type without one appears only in the folder's machine copy.
- The synced folder, first part: `storage.sync.folder`.
  - **When:** after every change, the core writes one folder per project there, a child project's inside its
    parent's. Records in no project go under `_workspace/`.
  - **The machine copy:** `.cockpit/` holds the plain export, the config and the plugin data.
  - **How:** each file is written beside its target and renamed into place, and its hash is kept in
    `.cockpit/manifest.json`. A file changed outside is never overwritten or removed. Two records that would share a
    file get the second one's id added to its name.
  - **Placement:** the workspace may not be inside the folder; start-up refuses.
  - **Loading:** `cockpit import <synced folder>` loads it into an empty workspace.
  - **Still to come:** the lease and handover, outside edits coming back for review, `working/`, `outputs/` and
    sources.

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
