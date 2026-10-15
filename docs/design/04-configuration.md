# Part 4. Configuration model

All config is YAML (rules prose in Markdown), validated against a schema at startup and by the self-check. Every key has a
default, so a new workspace runs with an almost empty config. Each file starts with a comment block explaining every key. Core
config lives in `config/`; each plugin's lives in `config/plugins/<plugin>.yaml`.

**What exists today.** The schemas in `engine/config/schema.py` are the truth for which files and keys are built. This part
also describes files and keys that are in the design baseline but have no schema yet; they are marked *designed, not yet
built*. A key the schema doesn't have is refused, so a typo never silently does nothing.

## 4.0 Configuration principles

The goal: a person changes how their installation looks, behaves, runs and is secured without changing code.

- **Behavior that someone might reasonably want different is a setting.** Names, labels, wording, layout, schedules,
  thresholds, routing, which plugins run, where the app is served, how people sign in and where data lives are all config.
  Hard-coding one of these is a bug.
- **Where anything is looked up is a setting.** Every page, page tree, query, folder, feed, field name and schedule the
  product reads lives in config (`watch.yaml`, `facts.yaml`, a connector's settings), named by a key. Code and default
  prompts say "the configured source for this kind of fact", never "the release page" or "the sprint field". A behavior that
  needs a new kind of source gets a config key and a lookup step, not a literal.
- **One schema per file, one source of truth.** Schemas live with the code that reads them (Pydantic models). They produce
  the validator, the defaults, the comment block in each file, the documentation and the settings forms in the app.
- **A setting lives in one place, and so does a fact** (decisions, 2026-10-11). A setting never repeats a record, and a
  record never repeats a setting. The PM's name and other names live on their person record; `workspace.user.person` holds
  only that record's id, and the time zone sits beside it. An older file that still holds the name is moved to the record
  when the workspace opens, and the keys leave the file. A plugin refers to core records by id and never copies their names
  into its own settings or records (3.5).
- **Layers, in order of precedence:** built-in defaults, then the workspace's config files, then environment variables, then
  command-line flags. Any key can be set from the environment as `COCKPIT__<FILE>__<KEY>` (for example
  `COCKPIT__SERVER__BASE_PATH=/admin`), which is how hosting platforms usually pass settings. `cockpit config show` prints the
  effective value of every key and which layer it came from.
- **Profiles** (*designed, not yet built*): `config/profiles/<name>.yaml` holds overrides for one environment (`local`,
  `hosted`); `COCKPIT_PROFILE` picks one. The same workspace can then run on a laptop and on a host with only the profile
  changing. Until then the environment layer does the job.
- **Versioned.** Every config file starts with `version:`. A file newer than the running code is refused with a clear
  message. Automatic migration of older files, which commits the before and after to git and lists what changed on the Admin
  tab, is *designed, not yet built*; the one move that exists is the PM's name to their person record, above.
- **Presets and levels.** Each key is `basic` or `advanced`; the Settings screens show basic keys first and keep the rest
  behind "More settings" (4.22). Starting templates (3.10) are the presets: a new workspace picks one, or none, so nobody
  starts from a blank page of options.
- **Explainable.** The Settings screens show each key's description, its default and which layer set it. `cockpit config
  explain <key>`, which also lists every part of the product that reads the key, is *designed, not yet built*.
- **Settings in the app:** the Settings screens (7.9) have a form per config file, generated from the schemas, with each key's
  description and default. Saving is described in 4.22. Keys set by an environment variable or flag show as locked, with
  where they came from. Secrets are never shown or typed into config; the form takes a reference (`env:NAME` or `file:/path`;
  `keychain:NAME` is *designed, not yet built*). A key pasted on a screen is kept on this computer (4.24) and config holds a
  `file:` reference to it.
- **Settings guide the person** (decisions, 2026-10-11). A setting that turns a feature on comes first in its group, and the
  settings it governs are greyed out while it is off (`enabled_by` in the schema). A folder is chosen with a folder picker
  (`picker`), a choice from a dropdown; typing a path or a value is the fallback, not the way.
- **Safe to change while running:** a setting that everything reads at the moment of use applies at once. Any other change
  says a restart is needed, holds new AI work and waits for the person to choose "Restart now". The app never restarts on its
  own (4.22, 6.14).

### The files at a glance

| File | Section | State | Proved by |
|---|---|---|---|
| `workspace.yaml` | 4.1 | built | `tests/test_config.py::test_fixture_workspaces_load` |
| `watch.yaml` (sources and triage) | 4.5 | built | `tests/test_watch.py` |
| `language.yaml` | 4.6 | built; the `languages:` map is designed | `tests/test_followups_backup_eval.py::test_a_message_has_greeting_questions_actions_and_closing` |
| `ai.yaml` | 4.8 | built; native adapters, `probation` and per-record budgets are designed | `tests/test_ai.py` |
| `dispatch.yaml` | 4.9 | built; the governor settings are designed | `tests/test_pipeline.py::test_the_fix_round_can_correct_the_answer` |
| `rules.yaml` | 4.10 | built (read by stage gates); rules reaching packets are designed | `tests/test_stages.py::test_rule_yaml_date_and_binding_validate_at_load` |
| `ui.yaml` | 4.11 | built | `tests/test_today_dashboard.py` |
| `server.yaml` | 4.13 | built for local mode; hosted-mode keys are designed | `tests/test_local_guards.py` |
| `storage.yaml` | 4.15 | built; `retention`, encryption and some `sync` keys are designed | `tests/test_first_backup.py::test_choosing_a_backup_folder_makes_the_first_backup` |
| `checks.yaml` | 4.17 | built | `tests/test_plugin_lints.py::test_the_workspace_can_soften_a_lint_to_a_warning` |
| `stages.yaml` | 4.21 | built | `tests/test_stages.py::test_order_wording_and_mode_override` |
| `plugins/<plugin>.yaml` | 4.12 | built | `tests/test_plugin_api_0349.py::test_a_renamed_setting_reads_under_its_old_name_and_is_saved_under_the_new` |
| `routing.yaml` (4.3), `scope.yaml` (4.4), `schedule.yaml` (4.5), `render.yaml` (4.7), `status.yaml` and `calendar.yaml` (4.11), `auth.yaml` (4.14), `facts.yaml` (4.16), `code_owners.yaml` (4.18), `playbooks.yaml` (4.19), `raid.yaml` (4.20) | | designed, not yet built | |

## 4.1 `config/workspace.yaml`

Built keys, with defaults:

- `name` ("Workspace") and `assistant_name` ("Assistant"): display names. The assistant's name is the only name people see.
- `user`: `person` (the PM's own person record id, e.g. `PER-1`; their name and aliases live on that record, 5.1) and
  `timezone` (an IANA name, default `UTC`). "Today" and every date shown follow the time zone.
- `owner_format`: how an owner is shown, e.g. `"{full_name}"` (default) or `"{team} ({full_name})"`; it must contain
  `{full_name}` and may contain `{team}`, and an owner with no team is shown by the full name alone. Parsing an owner written in
  the format is *designed, not yet built, not scheduled* (6.11).
- `language`: the language and variety work is written in, as a tag (default `en-US`). A project may set its own (5.1).
- `contact_kinds`: the kinds of contact detail a person record keeps and the assistant may propose from a signature
  (`person.contact`), picked from a list on screen. Default `email`, `phone`, `address`.
- `our_accounts`: the names this app uses on watched sources (its own publishes). A watched change by one of them is
  marked `by_us` (6.4, 6.5). Live.
- `user.accounts`: the person's own names on watched sources. A change by one of them is the person's own work
  (`by_you`): never news credited to others, never a question back to them. A source in `watch.yaml` may also name its
  `author` (the person, a colleague or a team, picked from lists on screen); its changes are credited to them.
- `demo`: made-up example data; every screen says so, so nobody mistakes it for real work.
- `plugins`, which holds every setting that limits or describes add-ons:
  - `enabled`: plugins enabled in this workspace, by name. Turning one on or off is done from the Add-ons screen (with
    Undo); the change needs a restart the person chooses.
  - `failures_before_off` (3): how many times in a row a plugin's Today lines, interface items, event handler or job may
    fail before it is turned off (6.1).
  - `actions`: `keep_minutes` (60), `preview_mb` (5), `max_previews` (20), `max_items` (2000), `max_requests` (100). How a
    plugin's person actions are reviewed.
  - `tools`: `timeout_seconds` (120), `max_timeout_seconds` (1800), `probe_timeout_seconds` (10), `output_kb` (512),
    `collect_file_mb` (25), `collect_total_mb` (100). Limits on outside programs; where a program is found is set per
    computer (4.24).
  - `jobs`: by job name, `enabled` (true) and `every_minutes` (unset: the plugin's default, at least 5).
  - `secrets`: by plugin and secret name, a reference (`env:NAME` or `file:/path`), never the secret.
  - `catalog` (3.11, 6.29): `enabled` (true), `shipped_feed` (true), `feeds` (more https addresses), `refresh_hours` (24),
    and `release_tokens` (by host name, a reference to a read token for a private pack's release file).

Designed, not yet built:

- `assistant_description` (display only).
- `connectors` and `channels`: named instances of a registered connector or channel with their settings. For inputs, the
  sources in `watch.yaml` (4.5) are the built form; named channels arrive with the publisher (6.12).
- `audiences` and `restrictions`: who can see each destination and how a restricted source is recognized (12.2). Checked by
  the audiences invariant (6.7).
- `plugins.paths`: extra search folders.

Approval before anything goes out is not a setting; it is always on.

## 4.2 People

People are records (5.1), not config: added by the AI with `person.add` or by the PM, edited in the app, exported to
`data/people.json`. Fields built today: `full_name`, `aliases`, `role`, `team`, `org` (the id of an organization record),
`how_to_reach` (per channel), `why_they_matter`, `track_only` (inside the tracked area but only observed) and `status`.
Designed, not yet built: communication fields (`prefers` a channel and time, `cadence` for regular updates, `influence` and
`interest`; the last three serve 6.24, which moves to the project management pack), `non_working_calendar` and `verified`
(spelling checked against a primary source). A person's area (tracked, a domain, or unknown) will come from their team and
`config/scope.yaml` (4.4). Fictional workspaces ship people in `data/people.json`, imported at test time.

## 4.3 `config/routing.yaml` (*designed, not yet built*)

Learned routing comes first: who answers what is kept as routing entries (records, 6.22, phase L), proposed when a reply says
"not me, ask X" or the person reroutes a question. The rules below are for routing a person sets up in advance; when both
match, the person's rule wins.

Ordered rules that choose a recipient for a question by topic, project, owner team or kind:
`when: {topic: requirements, project_field: product_owner} then: {to: "{project.product_owner}"}`.
A rule can say `ask_user_first` (unsure: the PM routes it). Unmatched questions go to the PM as a routing decision, never to a
guess.

`escalation`: when a question has waited a number of working days (`after`, default 5 after Mark sent), suggest one
escalation to the configured person (`to`: the area's contact, the project owner, or a named person), at most once per
question. The suggestion is a draft for the PM to approve or dismiss, never sent on its own (6.24, now provided by the
project management pack).

## 4.4 `config/scope.yaml` (*designed, not yet built*)

Scope says which area is the workspace's own and which belongs to someone else. The applier (6.7) and the scope sweep (6.18)
enforce it; it is never left to the AI's judgment. The scope resolver is part of the rest of version 1 (roadmap, phase E).

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

## 4.5 `config/watch.yaml` (sources and triage), `config/schedule.yaml`

**Watch** (built). `watch.yaml` holds what the assistant keeps reading and the rules that set some of it aside, in one file,
because triage only ever applies to watched changes and often names a source (decisions, 2026-10-11, "Triage rules live
beside the watched sources"; there is no `triage.yaml`). Keys:

- `sources`: a list. Each entry:
  - `id` (lowercase letters, digits and dashes; unique), `label` (what to call it on screen) and `enabled` (off keeps its
    history and stops reading it);
  - `connector`: what reads it. The core's are `folder`, `feed` (RSS and Atom), `calendar` (a calendar's private file
    address) and `mailbox` (a mail folder over IMAP); a plugin's are `<plugin>/<name>` (6.2);
  - `every_minutes` (60, at least 5): how often it is read while the app runs;
  - `project`: the project its changes are about, when they all are;
  - `first_run`: what the first read does. `baseline` (default): it only notes what is there, so connecting a full folder
    or mailbox doesn't flood the queue. `recent`: it also hands in what arrived, changed or happens within
    `first_run_hours` of the read (the last day's mail, today's meetings). `all`: everything there is is handed in as new;
  - `first_run_hours` (24, 1 to 336): how many hours around the first read count as recent;
  - `report_removed` (true): hand in an item that disappeared from a complete listing;
  - `data_level` (open, internal or restricted; empty): how sensitive its items are, so they go only to AI accounts allowed
    that level. Empty: the level for its kind of source (`connector_data_levels`, below), else `default_data_level`;
  - `settings`: the connector's own settings, checked against the connector's schema (a folder's path, a mail folder and
    its secret references).
- `triage`: rules, in order; the first match closes the change before the assistant reads it. Each rule has `name`, `kind`
  (a matcher), `params`, `why` (a template shown to the PM; `{reason}` is the matcher's own words) and `sources` (empty: all).
  The core's matchers are `cosmetic` (only spacing, punctuation or capitals changed), `by-us` (changed by one of
  `workspace.our_accounts`), `terms-absent` (none of the rule's terms is in what changed), `name-matches` (the item's key
  or title matches a pattern) and, for mail, `bulk-mail` (the message says it was sent to many), `service-category` (the
  mail service's category is one of the rule's `categories`) and `sender-rule` (the sender's address is one of `senders`, or
  its domain or a domain it is inside is one of `domains`; any case). A rule may add `set_aside` (`personal`, `sales` or
  `never`): a match then puts mail in the Set aside folder in that section instead of plainly closing it, and `never` keeps
  the mail with the assistant against every set-aside rule after it and the built-in sorting (6.5). Plugins register more
  (`<plugin>/<name>`). The matchers the first design listed beyond these
  (`same-edit`, `already-seen-file`, `owner-not-ours`, `other-domain`, `container-not-mapped`, `child-item`, `unknown-key`)
  are *designed, not yet built*.
- `set_aside_defaults` (true): after the `triage` list, mail that is bulk, or that the mail service files under promotions,
  social or forums, is set aside as sales mail with no AI run. It needs no rule in the file, so every workspace has it.
- `sorting` (`ai`) and `sorting_batch` (25): how mail that no rule places is sorted (6.5). `ai`: one small low-cost run per
  batch reads only the senders, subjects and service categories (never the text) and says work, personal or sales; unsure
  counts as work. `rules`: no run. A batch is at most 100 messages. The kind of work is `sort-mail`: its tier, limits and
  budget are set under `ai.tasks` and `ai.budgets.per_task` like any kind's. Both keys are live.
- `default_data_level` (internal) and `connector_data_levels` (a map from a connector's name to a level; empty): the data
  level a watched source's items carry when the source sets none. It is kept on each source record (5.1).
- `set_aside_keep_seconds` (60): how long the app keeps the copy of mail the person confirmed was rightly set aside, so
  Undo can bring it back; then its content is deleted from the app (6.5). 0 deletes at once.
- `public_mail_domains_extra` (empty list): mail domains anyone can have an address at, added to the list the app ships. No
  sorting rule is offered or saved for a whole public mail domain, only for a sender (6.5).
- `failures_before_asking` (3): failed reads in a row before the person is asked about a source; one question, not one per
  read.

Sources are also added by a sign-in (6.27): an add-on declares the inbox and the main calendar, and signing in starts them
(`first_run: recent`, the add-on's own interval). The person narrows, adds or removes sources afterwards from the Sources
screen; those edits stand. Watch settings are live: a source added, changed or removed is read on its new terms at once.

**Schedule** (*designed, not yet built*): `config/schedule.yaml` would hold jobs (core and plugin) with cron-like times,
working hours, which jobs need the network and catch-up behavior after sleep. Today each thing has its own interval key: a
source's `every_minutes`, `storage.backups.every_hours`, a plugin job's `every_minutes` (4.1), the synced folder's check
every few seconds, and the settings in 6.14.

## 4.6 `config/language.yaml`

Built keys:

- `messages`: `greeting` ("Hi {first_name},"), `actions_heading` ("Action items with you:"), `closing` ("Thanks!") and
  `date_format` (strftime codes, default `%a, %b %d`) for copied messages, and `date_time_format` (default
  `%a, %b %d, %Y, %H:%M`) for a date and time in the assistant's own text, written in the person's time zone (6.7).
- `self_words`: the words the language uses for the person themselves (default "me", "myself" and "I"); a name written as
  one of them, in any case, resolves to the person (6.11).
- `self_words`: the words the language uses for the person themselves (default "me", "myself" and "I"); a name written as
  one of them, in any case, resolves to the person (6.11).
- `blocked_phrases`: wording not allowed in actions and shared text (default "confirm", "check whether", "check if", "TBD?").
- `run_on_separators`: separators that mean several items were crammed into one line (default " / " and "; ").
- `never_shown`: words that must never appear in anything people see; model names are added to it.
- `title_skip`: regular expressions, matched at the start of a line, ignoring case, for lines an item's title never comes
  from: greetings, quoted mail headers, sign-offs. A title is taken from the first line left (7.14).
- `bare_confirmation_words` (4, 1 to 20; applies at once): a note typed on a button with fewer words than this and no link is a
  bare confirmation and is not sent to the assistant (6.5).

The language and variety of the workspace is `workspace.language` (4.1) and of a project `Project.language` (5.1). The
`languages:` map in this file, keyed by language tag (`en-GB`, `en-US`), with a spelling list, wording lints and date formats
per language, is *designed, not yet built*; until it exists, a project's language is carried to plugins (`view.language`)
and to drafting, and the core's own wording lints use this file.

## 4.7 `config/render.yaml` and templates (*designed, not yet built*)

Output types (pages, messages, posts, plugin types), their sections and column names, column widths, sort orders per section,
what counts as a cosmetic change, and how status labels render. Templates are files, not strings in code; the core and plugins
ship defaults and the workspace's `prompts/` and template folders override them.

## 4.8 `config/ai.yaml`

The whole AI setup, so changing vendor, account or model is a config edit (details in 6.16). Each provider entry is one of the
PM's own accounts: a key they pay for, a local model server, or a command-line agent signed in as them. Vendor names appear only
here, in the adapters and in usage and evaluation reports; model ids are always config, never code. The setup guide's AI step
and Settings add an account from a shipped list of kinds and services (`catalog/ai-endpoints.yaml`, data, not code): pick one,
paste a key (kept on this computer, 4.24), pick from the models the service itself reports, and test. Command-line agents are
on the same list, each with its command and locked-down flags, so the person never types a command. Accounts can be fixed
after adding (replace the key, change the models, remove). The schema is what exists today:

```yaml
version: 1
providers:                       # every AI account the workspace may use; names are the PM's choice
  low-cost:
    adapter: openai-compatible   # any endpoint that speaks the common chat format
    kind: <id from the shipped list>   # which kind of account it was made from, for showing its name
    base_url: https://api.example.com/v1
    auth: file:/path/to/workspace/.cockpit/keys/low-cost   # a reference to a secret (env:NAME or file:/path), never the secret
    models: {small: <model id>}  # short names for this account's models
    allowed_data: [open, internal]   # the most sensitive material it may see; default [open]
    content_levels: [mature]     # optional: the content levels it takes (from content_levels below); unset: every level
    timeout_seconds: 90
    json_mode: true
  router:
    adapter: openai-compatible   # an aggregator is the same adapter with its own address
    base_url: https://router.example.com/api/v1
    auth: env:ROUTER_AI_KEY
    models: {strong: <vendor/model id>}
    allowed_data: [open]         # data passes through the aggregator and the model's vendor
  local:
    adapter: openai-compatible
    base_url: http://localhost:11434/v1   # a model server on this computer
    models: {small: <model name>}
    allowed_data: [open, internal, restricted]   # never leaves the machine
  coding-agent:
    adapter: cli-agent           # any command-line agent, signed in as the PM, run locked down (6.16)
    models: {default: <model id the agent takes>}
    allowed_data: [open, internal]
    agent:
      command: [<agent program>, <its locked-down flags>, --model, "{model}"]   # also {packet}, {prompt}, {outbox}, {scratch}
      packet_via: stdin          # stdin, file ({packet}), or argument ({prompt}, refused above a size limit)
      output_via: stdout         # or outbox: the answer is a file in {outbox}
      output_json: true          # the agent prints JSON; output_fields says where the answer, usage and cost are
      output_fields: {text: result, input_tokens: usage.input_tokens, output_tokens: usage.output_tokens, cost_usd: cost}
      pass_env: []               # variables it may see besides PATH, HOME and the language settings
      key_env: <variable>        # the variable it reads its key from, when the account uses a key
      errors: {auth: ["<its not-signed-in message>"], rate_limited: [], quota: ["<its usage-limit message>"], reset: ["<its reset time: the first group is seconds or an ISO date and time>"], exit_codes: {}}
      sign_in_hint: <its login command>
      version_command: []        # how to print its version; empty: the program with --version (6.16)
      home: shared               # fresh: each run gets an empty home with only home_files copied in
      home_files: []
tiers:                           # what the work needs, mapped to provider/model; any mix of accounts
  routine: {use: low-cost/small, fallback: [local/small], escalate_to: deep}
  deep:    {use: router/strong, fallback: []}    # an empty `use` means no account yet; the work waits and says so
tasks:                           # settings per AI task kind; plugin kinds use their declared defaults
  notes: {tier: routine, temperature: 0, max_output: 4000, expected_output: 800}
  # same_account: true  on a check accepts a fresh run on the account that wrote the work (below)
roles:                           # tiers by the role a kind of work declares: write, check or research
  check: {tier: deep, same_account: false}
budgets:
  per_run_usd: 0.25              # never start a single run estimated above this
  confirm_above_usd: 0.10        # a run estimated above this asks first, with the estimate (6.16)
  confirm_unpriced: false        # also ask before a run whose cost can't be estimated (a subscription account)
  first_go: true                 # the first runs in a workspace wait for one Go with their total (7.8)
  per_day_usd: 2
  per_month_usd: 30
  warn_at: 0.8
  per_task: {}                   # caps by task kind, e.g. {notes: {per_day_usd: 1.5}}
prices: {}                       # by provider/model, for models whose catalog gives none: {input_per_million, output_per_million, cached_input_per_million}
evaluation: {runs: 3, min_score: 0.9}
catalog_refresh_hours: 24        # how old an account's model list and prices may get before they are fetched again
rate_limits: {tries: 3, max_wait_seconds: 30, pause_seconds: 600}   # when the last account says to slow down: wait and try again; with another account, move on at once; a limit with a reset time, or one that keeps coming, pauses the account (6.16)
routing:                         # rules checked in order before a call that send some requests to another tier; the first match wins
  - when: {task: notes, quoted_messages_over: 3}   # also input_chars_over and data_level
    tier: deep
content_levels:                  # kinds of material some accounts won't take, by id; none are defined by the core
  mature: Sex or graphic violence in the story.
```

- A tier may be empty (no account yet); it may never name an account or tier that doesn't exist, and the file is refused
  with the reason if it does. Defaults give two empty tiers, `routine` and `deep`, and the `notes` task. A new workspace has
  no account until the person adds one (the stand-in `stub` adapter is for fixtures and the demo only).
- **Adapters built:** `openai-compatible` (any endpoint, an aggregator or a local server), `cli-agent` and the stand-in.
  Native vendor adapters and the aggregator-specific layer in the first design are *designed, not yet built*; none is needed
  for the features above.
- **Tasks and roles.** The core's task kinds are `notes` (reading a hand-in or a watched change) and `ask` (6.25). A task kind
  declares a role; `ai.roles.<role>.tier` maps the role to a tier and `ai.tasks.<kind>` overrides any of it. `same_account`
  (on a role or a kind) lets a check run as a fresh run on the account that wrote the work, when no other account can take
  it (6.16; decisions, 2026-10-12, "Roles, and second opinions on one account").
- **Content levels** (decisions, 2026-10-12): the workspace defines its levels in `content_levels`; a project, or a plugin's
  record, is marked with the levels its material carries; routing skips accounts that don't take them all, and when none does
  the request waits and says why. An account with no list takes every level.
- **Budgets.** Defaults suit one person. `confirm_above_usd` is 0.10: below it runs start on their own; above it they wait for
  the person's go with the estimate. On a subscription there is no price, so `confirm_unpriced` makes such runs wait too. A
  project may carry its own budget, set only by the person (`Project.budget_usd`, 5.1), which covers AI work on it and
  everything inside it. Caps per record type (`per_record`) are *designed, not yet built*.
- **Designed, not yet built:** `probation` (a new account's work always waits for review for `runs` runs per task kind,
  default 20; the person may end it early once the send-back rate is below `end_below`, default 0.05, over at least
  `min_runs`, default 10; 6.16),
  `evaluation.required_before_switch`, `auth: keychain:NAME`, the aggregator's `routing` options, and task kinds other than
  `notes` and `ask` (change, answer, feedback, update, agenda) that the first design named.

A typical notes run is about 5,000 to 10,000 tokens in and about 1,000 out, which costs a fraction of a cent on a low-cost model
and a few cents on a top-tier one (prices change; the provider catalogs have the current ones). A runaway loop hits
`per_run_usd` or `per_day_usd` long before it costs real money; the PM is warned at `warn_at`.

Drafting long documents costs more: a proposal or statement of work reads its template, the account's notes and the sections
around the one being written, writes a few thousand words, and an independent review reads it again on another account. A
long document is many such runs, plus revisions. That is why packs with drafting task kinds raise `per_task` caps only for
those kinds, and every run above `confirm_above_usd` waits for the person's go with its estimate (6.16). The defaults stay low,
so nothing expensive happens unless the person chose it.

## 4.9 `config/dispatch.yaml`, `config/governor.yaml`

**Dispatch** (built): `max_input_chars` (60000; a longer input is refused with a request to split it or raise the key),
`fix_rounds` (1, up to 3: how many times a failing answer goes back to the AI), `retries` (2, up to 5: how many times a run that gave no usable answer or failed is tried again by itself before it goes to the person, 6.16, 8.6), `retry_wait_seconds` (30: the wait before the first retry, doubled for each later one), `offline_check_seconds` (60, 5 to 3600: how long work that found no network waits before it is looked at again; it uses no tries, 6.16, 8.6), `offline_line_after_minutes` (60: how long work may wait for the network before Today asks the person to check the connection; most waits clear within minutes of opening the lid, 7.7) and `cleaning` (6.6): `remove_quoted` (true),
`signature_markers` (default "-- " and "Sent from my "; a line starting with one ends the message) and `remove_patterns`
(regular expressions for disclaimers and footers).

**Designed, not yet built:** batch size, immediate-run kinds, timeouts and attempts; `max_input` per task kind (the packet size
budget, 6.6); `open_items.compact_share` (share of the budget the open-items list may use before other projects' actions
switch to compact form, default 0.4); `config/governor.yaml` with its thresholds (stuck after N minutes, stale after N hours,
outage when more than N keys fail); and `reports`: where reports to the product's maintainers go (`clipboard` by default, or a
channel and target the PM configures) (6.13). Today a drafted report is shown for the person to copy and send.

## 4.10 `config/rules.yaml` and rule records

**Rules are records** (*built, L1*; decisions, 2026-10-12 "The learning slice"). Like value lists (4.23), rules live in the
database as `rule` records (5.1), beside the other knowledge (6.22). A rule then has:
- history and Undo, like any change;
- no restart when one is added;
- a place in the workspace's data, so it travels with it;
- the same `applies_to` target as lessons, and an origin (seed, person, assistant, pack or import) and a status (proposed,
  active, discarded, retired).

`config/rules.yaml` is the starting set. When a workspace starts (and when `cockpit init` makes one), each rule in the file
that has no record yet is made an active record with the origin `seed`; running it again adds nothing, and a rule the person
retired is not made again. A rule the file itself marks retired or promoted is made as a retired record, kept as history.
The file is then left as it was and never written back. From then on the records are the truth:
stage entry checks and every other reader take the active rules from the records (`engine/rules.py::active_rules`), while
the file is still checked when the configuration loads. A rule's id in the file becomes the record's `name`, which stage
checks refer to; the record's own id is `RULE-n`. A rule is added by `rule.add` (system tier) and ended by `rule.retire`;
a retired rule's name stays taken. **Built:** `tests/test_rules_facts_signals.py::test_a_retired_seed_rule_is_not_made_again`,
`tests/test_stages.py::test_a_rule_added_by_op_is_used_by_the_stage_check_until_it_is_retired`.

Plain-language standing rules the PM states while working ("record who raised each risk"), each one an entry rather than a
line in a growing file:

```yaml
version: 1
rules:
  - id: R-12
    text: Record who raised each risk.
    applies_to:                                   # the structured target (6.7 read-back)
      task_kinds: [change, notes]                 # empty means every AI task
      records: [project.risks]                    # record types and fields it touches
      filter: {}                                  # optional narrowing (projects, owners, status)
    source: request 3381                          # where it came from
    added: 2026-10-08
    status: active                                # active, retired, promoted
    check: <id of a deterministic check>          # optional; prose alone never lets a stage move
```

Built: the file, its schema and its use by stages (the stage check reads the rule records): a rule that names a deterministic `check` can be an entry check or an
applies-if for a stage (4.21, 6.26); a prose rule never allows a move. Designed, not yet built: rules reaching the AI tasks they
apply to (6.6) and the rules review (6.21), which keeps the list short and moves rules that are really settings into config.

## 4.11 `config/ui.yaml`, `config/status.yaml`, `config/calendar.yaml`

**UI** (built). Keys, with defaults:

- `wording`: overrides for the wording sheet, by key (the keys are in `web/src/wording/en.json`). Plugins' own wording is
  overridden the same way.
- `shortcuts`: single keys by action, never firing while typing, no two the same: `next` j, `previous` k, `primary` a,
  `send_back` s, `copy` c, `edit` e, `undo` u, `hand_in` n, `help` ?, `ask` /, `next_pane` ], `previous_pane` [. The last two
  move between the panes of a screen (7.7).
- `narrow_below_px` (640): below this width the screen uses the phone layout, one pane and a bottom bar (7.13).
- `toast_seconds` (7; 0 keeps toasts until dismissed) and `feedback_to` (the address the feedback button writes to; empty uses
  the address the app was packaged with, else feedback is drafted to copy).
- `today`: `mail_hours` (24) and `mail_max` (50) for the list of what came in, `agenda_days_ahead` (1; 0 is today only).
- `followups`: when something sent to a person is due a follow-up, one rule that Today and Follow-ups both read (6.9).
  `question_after_days` (4): a question with no reply after this many days; `action_due_within_days` (7): a told action
  whose own due date is this near or past (an action on hold is never chased); `undated_after_days` (14): a told action with
  no due date and no word after this many days. They replace the old `today.nudge_after_days`, which an existing file may still
  carry and is read as `question_after_days`.
- `brand`: `color` (`#rrggbb`; the app works out shades from it and Settings warns when its contrast would fail; empty uses the
  app's indigo) and `logo` (a PNG, JPEG, WebP or SVG file name in the config folder; empty shows the workspace's initials).
- `theme` (`system`, `light` or `dark`) and `density` (`comfortable` or `compact`): the workspace's defaults. Each person can
  change both for their own device from the menu under their initials; that choice stays in their browser (7.12).

These are all live (4.22).

**Designed, not yet built:** tab order, hidden or reordered panels and header quick links (the sidebar of 7.1 replaced tabs;
plugins add entries only under Work or Records); `config/status.yaml` (the status labels in use, their colors, and which count
as open, done or at risk; a project's status is today a value list, 4.23); `config/calendar.yaml` (the week end that "this
week" runs through, holidays, and per-team non-working days); `ui.notifications` (phase B, 7.19):
- `enabled` (false);
- `quiet_hours` (`{from: "20:00", to: "08:00"}`, in the person's time zone);
- `targets`, a list, each with:
  - `kind`: browser, mail or webhook;
  - `to`: the person's own mail address, or the webhook address as a secret reference;
  - for a webhook, `body`: a template of what is posted, so any chat app or push service fits without code;
  - `detail`: count or titles, default count;
  - `allowed_data`: the data levels whose titles may go to it, default open only.

## 4.12 `config/plugins/<plugin>.yaml`

Each enabled plugin's settings, validated against the schema the plugin's manifest names. Same rules as core config: every key
has a default and a description, and both fictional workspaces carry demo values. Each running plugin's settings are their own
section on the Settings screens, saved like the core's, and a change asks for a restart (registration keeps the old settings
until then). A setting a plugin renamed is read under its new name and written under it on the next save.

**A person's own data files for a plugin** (templates with their images, fonts, profiles, word lists) go in
`<workspace>/plugin-data/<plugin>/`, laid over the data the plugin ships, by the same relative path or id: the person's file
wins, and removing it brings the shipped one back. They are versioned with the workspace's config, carried by the synced
folder (5.0), checked by the plugin's `check()`, and read through the plugin API, never by path from outside the folder. A
plugin may declare a *data form* for a kind of these files: they are then edited on a screen built from the form's schema, a
save writes only the workspace's or a project's copy (never the shipped one) with only the keys the file had plus those the
person set, and it can be undone.

## 4.13 `config/server.yaml`

Built keys (local mode):

- `mode`: `local` (default) or `hosted`. Hosted mode, with its deploy checks (11.5), is *designed* and is not part of 1.0.
- `host` (default `127.0.0.1`) and `port` (default 8765): the address to listen on.
- `public_url`: the address people use, e.g. `https://example.com`. Required when hosted. Sign-ins use it to build the address
  a service sends the person back to (6.27).
- `base_path`: where the app is mounted under that address, e.g. `/admin` (default `/`). The UI, the API
  (`<base_path>/api`), cookies and every link the app makes use it; nothing in code assumes the root.
- `open_browser` (false): open the app in this computer's browser when it starts (local mode only). `cockpit serve --open`
  and `--no-open` set it for one run; `cockpit demo` opens by default.

These keys are changed in the file or with a flag, never from the Settings screens (a wrong value could stop the app from
being reached), and a change needs a restart. They are per computer: the synced folder does not carry them (5.0).

Designed, not yet built: `hide` (when hosted, how the app answers someone who isn't signed in: `login` or `not-found`),
`trusted_proxies`, `allowed_hosts`, `headers` (security headers, `robots: noindex`), `cors` (off by default), and `role` (`all`,
`web` or `worker`, for hosts that run them separately).

## 4.14 `config/auth.yaml` (*designed, not yet built*)

- `providers`: an ordered list of sign-in methods, each with a `type` (a registered auth provider, 11.4) and its settings.
  Several may be enabled; the sign-in page offers each.
- `users`: who may sign in, by identity per provider (an email address for a sign-in provider, a username for a password).
  Everyone listed has full access in the base; roles are a later feature.
- `require_second_factor`: when hosted, a password alone is refused; defaults to true.
- `session`: idle timeout, absolute lifetime, remember-device length, cookie name.
- `lockout`: failed attempts before a pause, pause length, rate limit per address.
- `recovery`: how to get back in when locked out (one-time recovery codes generated at setup; a command run on the server
  that resets a user).

Local mode has no sign-in page: the browser presents a token kept in the workspace's private folder (4.24). Signing in to a
*service* an add-on connects to is a different thing and is built (6.27).

## 4.15 `config/storage.yaml`

Built keys:

- `backend`: `sqlite` (the only one; Postgres is a later backend for multi-user, 5.0). Changed in the file only.
- `export`: `every_minutes` (60), `commit` (true: commit the export and the config to the workspace's git) and `remote` (a
  private git remote for an off-site copy). The export is written by `cockpit export`, and on the
  `every_minutes` schedule while the app runs (`engine/export_schedule.py`, tested in `tests/test_export_schedule.py`);
  config saves are committed. A workspace with no repository gets no scheduled export, and the log says so once. The push
  to `remote` is not wired: nothing is ever sent (phase E). `every_minutes` is a live key.
- `files`: `max_file_mb` (50), `max_total_mb` (2000) and `accepted_types` (media types a file may have; a file kind can narrow
  this, never widen it) (5.3).
- `sync`: hand the workspace between computers through a synced folder (5.0).
  - `folder`: a folder a file-sync service keeps in step (empty: off). Chosen with a folder picker. The workspace itself must
    not be inside it, and the self-check and start-up refuse that setup.
  - `watch_outside_edits` (true): bring back edits made to the folder's files in other programs as changes for the person to
    review; off: they are only reported.
  - `shared` (false; asked when the folder is chosen, and changeable on the folder's panel; a live setting): whether anyone else
    can change the folder. When true, outside edits arrive as content, not as the person's own words (12.8).
  - `lease_stale_after_minutes` (10): how long after the other computer was last seen the workspace can be opened here
    without it closing first.
- `backups`: full backups to somewhere off this computer, **on their own** (decisions, 2026-10-11, "Backups run on their own;
  a missing backup folder is never created"):
  - `automatic` (true): a background thread makes a backup whenever one is due, including right after the computer wakes (it
    goes by the wall clock), with nothing to click. Off: only on request ("Back up now").
  - `targets`: a list of `path` and `label`: a synced folder, an external drive or a network share. A target inside the
    workspace is refused (it is not a copy somewhere else). **A target folder that doesn't exist is refused with the reason
    and never created**, because a drive that isn't connected would otherwise get a folder on this computer's own disk, which
    looks like a backup and isn't one. Choosing the off-device folder once is part of setup (7.8); the folder is checked
    before it is saved.
  - `every_hours` (24), `keep` (14: older backups in each target are removed) and `retry_minutes` (60, at least 5: after a
    failed backup, how long before trying again).
  - A backup is a dated folder in each target: a consistent copy of the database (SQLite's online backup) plus `config/`,
    `sources/`, `files/`, `texts/` and `plugin-data/`. The result of the last try per target is kept on this computer. Until a
    backup has succeeded, a mark in the header says "No off-device backup is set up" or that the last try failed; afterwards
    it shows the age of the last one, and "overdue" past twice `every_hours` (11.1).

`backups.encrypt` (**built**, L5; `tests/test_backup_encryption.py::test_every_file_of_an_encrypted_copy_is_sealed`): an `env:` or `file:` key reference; when set, every backup copy is sealed (AES-GCM in
chunks, a key derived per backup, each chunk bound to its path and place), `cockpit restore --backup` asks for the key and
refuses a wrong one before writing anything, and the backup line says the backup is encrypted. A lost key means a backup
that can't be read, and the description says so. File names and the folder layout are not hidden.
`files.read_max_mb` (25) and `files.read_max_chars` (30000): the largest file read as text, and how much of its text a
packet carries.

Designed, not yet built: `path` (where the workspace lives; today it is the `--workspace` folder or `COCKPIT_WORKSPACE`),
`sources_store` (an object store), `sync.layout`
(`by_project` is the only layout today), `sync.sources` (include, encrypt above a data level, or exclude above one; sources and files now carry a data level, but the setting is not built, so every source is copied) and `sync.outputs_folder` (fixed as `outputs` today), and
`retention`: per source kind and restriction level, how long raw text is kept after its facts are recorded, and
`forget_person` behavior (delete or anonymize free text that names them, repoint their records to "former contact"). The
ledger keeps that a source existed and what was learned from it.

`storage.yaml` is per computer (paths, folders and targets differ between computers), so a handover does not carry it.

## 4.16 `config/facts.yaml` (*designed, not yet built*)

Kinds of fact that a published source holds, so they are looked up and never asked of a person (6.19). Fact lookups are item C4
of the roadmap.

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
- Connector field names (`release`, `sprint`, `fix_version`), watch entries and keys are all values here, not code; a
  connector reads whatever field it is told to.

## 4.17 `config/checks.yaml`

The severity of each lint (6.7) and its settings. Built keys:

```yaml
version: 1
lints:                           # severities: refuse, return, warn, off
  blocked-wording: return
  run-on-list: return
  near-duplicate-action: warn
  evidence-fit: return
projects:                        # severities for one project's work only, over the ones above
  PRJ-3: {run-on-list: off}
tuning:                          # settings of the core lints that have more than a severity
  near_duplicate_action: {similarity: 0.8}
```

Severities: `refuse`, `return` (back to the AI once; then held for the PM if the item will reach another person, or applied
with a warning if it stays internal, 6.7), `warn`, `off`. Invariants (6.7) are not listed and can't be lowered. Plugins register
their own lints with a default severity of `return`, `warn` or `off`, never `refuse`; the workspace's file overrides it per
lint like the core's own, and `projects:` per project. A lint the workspace switched off isn't called. Plugin lints check the
assistant's proposals only, never the person's own changes. Each problem names the passage it points to, its guidance goes
back with that passage in the return round, and it shows on that passage in the compare view (7.2).

**Lint settings.** A lint with more than a severity has its settings under `tuning:`, one typed entry per core lint, named as
the lint is in `lints:` with underscores for hyphens, so each setting has a plain dotted key and environment variable
(`COCKPIT__CHECKS__TUNING__NEAR_DUPLICATE_ACTION__SIMILARITY`). `lints:` stays a map of severities, so plugin lints and their
overrides are unchanged. **Built:** `near_duplicate_action.similarity`, a number from 0 to 1, default 0.8 (the first design's
0.85 does not hold). `near-duplicate-action` compares a new action's text with open and done actions and fires at or above
that similarity, and a message says which kind it matched. **Built:** `tests/test_near_duplicate.py::test_the_check_fires_at_and_above_the_configured_similarity_and_not_below` (fires at and above the setting, with two
values, and not below), `tests/test_near_duplicate.py::test_the_check_compares_with_done_actions_too` and `tests/test_near_duplicate.py::test_the_similarity_is_between_zero_and_one` (the range and the default). `near-duplicate-question` (designed, phase L) gets its
entry beside it, with `similarity` and `days` (default 14).

**Built (L3):** `several-questions` (default `return`), a question or decision whose text holds `several_questions.minimum`
(default 2, from 2 to 20) or more items of a numbered list that ask; and `question-without-stake` (default `return`), a
`question.add` to anyone but the person with no `matters_for` (6.8). `owner_suggestion.match` (default 0.5, above 0 and at
most 1) is how much of a routing entry's topic an unowned action must hold for the entry to suggest its owner (6.9). Both
workspaces show all three. `tests/test_corrections.py::test_several_questions_returns_a_question_or_decision_at_the_configured_number_and_not_below`,
`tests/test_corrections.py::test_a_question_to_someone_else_without_a_stake_is_returned_and_then_held_so_it_is_never_sent`,
`tests/test_corrections.py::test_the_suggestion_follows_the_configured_share_of_the_topic_and_skips_what_does_not_apply`.

Lints in the first design that are *designed, not yet built*: `locale-spelling`, `fact-terms-without-asks-for` and
`unreachable-link`. With the learning slice (phase L): `already-known` (default `return`), a question, outside lookup or report
whose subject a plain search of the workspace's own knowledge already answers (6.22); and `near-duplicate-question` (default
`return`), a question close to an open one, or to one answered in the last `days` (default 14), to the same person (6.8).

## 4.18 `config/code_owners.yaml` (*designed, not yet built*)

Which project owns which code or tool, so a request about something the PM uses but this product doesn't own (a dashboard that
reads the published pages, a script another team runs) goes to its owner as a handoff:

```yaml
version: 1
owners:
  - name: portfolio dashboard
    match: {terms: [dashboard, chart, tile], outputs: [summary page readers]}
    owner: Ana Ortiz                 # a person record
    handoff: {channel: team-chat, target: dashboard requests}
```

A matching request becomes a `handoff` draft (6.7), with the request, what the PM saw and links, for the PM to approve and send.
Anything that matches nothing and needs code is about this product, and becomes a report to its maintainers (6.13).

## 4.19 `config/playbooks.yaml` (*designed, not yet built*)

Which playbooks are active and how the workspace adjusts them (3.8):

```yaml
version: 1
disabled: [core/meeting-prep-checklist]      # entries switched off, by id
replaced:                                    # an entry replaced by one of the workspace's rules
  core/risk-raised-by: R-31
```

Every enabled plugin's playbook is active by default. The Settings panel lists entries by playbook with their text, so the PM
can see exactly what the assistant has been told. (A plugin cannot yet declare its own playbook: `provides.playbook` is on the
guide's "Not yet available" list.)

## 4.20 `config/raid.yaml` (*designed, not yet built; provided by the project management pack*)

RAID, risk reviews and the rest of 6.24 are now provided by the project management pack (9.10), an add-on (decisions,
2026-10-12, "A project management pack"). This file's keys therefore become that pack's settings (`config/plugins/<pack>.yaml`, 4.12), not a
core file; the design is kept here as the pack's starting point. It says which project management records and fields are in
use, so a personal workspace can stay light and a workplace one can be thorough:

```yaml
version: 1
records: [risks, issues, assumptions, dependencies, decisions]   # any can be left out
risk_fields: [probability, impact, mitigation, trigger, review_by]  # optional fields, any subset
scales:
  probability: [low, medium, high]
  impact: [low, medium, high]
  score: probability_x_impact                # or none
review:
  risks_every: 14                            # days between reviews of an open risk (Today line)
  assumptions_every: 30
```

Packs ship presets (the publishing preset keeps risks, issues and dependencies and leaves assumptions off).

## 4.21 `config/stages.yaml`

The stages of record types that move through steps (6.26). Packs ship defaults; the workspace edits, renames, adds or removes
stages and their checks. Keys: `moves` (`person` default, or `rule`: who advances records), `wording` (stage explanations by
key, overriding the defaults) and `types`, by record type; a record type may also be written at the top level of the file, as
below. Each type takes `moves` (its own override) and `stages` (leave it out to keep the pack's list, or give an empty list to
remove them). Each stage has `id` (unique within the type), `label`, `description` (what being in the stage means, in plain
words), `entry` (check or standing rule ids required to move in), `starts` (task kinds requested on entry, waiting for the
person's go) and `applies_if` (check or rule ids that must all pass for the stage to apply to a record; moves pass over a stage
that doesn't apply).

```yaml
version: 1
publishing/title:
  - {id: manuscript, label: Manuscript}
  - {id: editing, label: Editing, entry: [manuscript-received]}
  - {id: production, label: Production, entry: [edits-approved]}
  - {id: proofs, label: Proofs, entry: [interior-final, cover-final]}
  - {id: launch, label: Launch, entry: [proof-approved, launch-date-set]}
moves: person                    # who moves records between stages by default: person or rule
```

Each entry check names a rule (4.10) or a pack's check by id; labels are wording, so they can change without touching data. A
file naming a plugin that is turned off or failed to load stays in place and shows as unavailable; the workspace still starts.

## 4.22 Saving settings, live keys and restart

How a setting gets from a screen into a file, and when the running app uses it (decisions, 2026-10-11, "Settings are saved
from the screens…" and "The app restarts only when it must, and only when the person says so").

- **A form is described from the schema** (`GET /api/settings`): every key with its description, type, choices, value, default,
  the layer that set it, whether it is locked, `basic` or advanced, the key it depends on (`enabled_by`) and a picker if it
  has one. Plugins' settings come as their own groups (4.12).
- **A save names the fingerprint of the files the form was built from**, so two saves never race; if the files changed it
  says so and asks the person to look again.
- **What can't be saved from a screen:** a key locked by an environment variable or flag, and the file-only keys: all of
  `server.*` and `storage.backend`. A guided step (adding an AI account, choosing a backup folder, a sign-in starting sources)
  may set a key no form shows, by an explicit allow-list for that step.
- **The changed files are checked as a whole** (the whole config loaded with the change) before anything is written; a
  refusal names the key and why. Files are replaced atomically, keep their comments, and are committed to the workspace's git
  when `storage.export.commit` is on.
- **Each change is recorded** as a `setting_change` record (key, value before, value after, whether each was the default),
  written by the PM with op `config.set`, so it has history and can be put back.
- **Live keys apply at once.** These are taken in without a restart because everything that reads them reads the shared
  config at the moment of use (`LIVE_KEYS` in `engine/worker.py`): `ai.*` (accounts, tiers, budgets), `ui.*`,
  `workspace.user.*`, `workspace.name`, `workspace.assistant_name`, `workspace.our_accounts`, `storage.backups.*` and `watch.*`.
- **Every other key needs a restart:** `server.*`, the rest of `storage.*`, `workspace.language`, `workspace.plugins.*`
  (including turning an add-on on or off), `dispatch.*`, `checks.*`, `language.*`, `stages.*`, `rules.*` and every plugin's
  own settings. A change to the program's own code counts too. The app then says a restart is needed and why, holds new AI
  work ("Settings or code changed; restart to use them"), and waits for the person to choose **Restart now** or **Later**. It
  never restarts on its own (6.14). A copy that can't start itself again says to close and start it.

## 4.23 Value lists

Free text and duplicated data make a system that breaks quietly. A field with a known set of values (a project's status,
phase, priority and group; a plugin's categories) takes its values from a named **value list** and is shown as a dropdown
(decisions, 2026-10-11, "One source of truth, value lists instead of free text…"). **Lists are records, not config**
(`value_list`, 5.1), not a `config/lists.yaml`: adding a value then has history and Undo like any change, needs no restart,
travels with the workspace's data, and is refused by the storage layer for any writer that tries an off-list value. The core's
first values ship in `engine/defaults/value_lists.yaml`; a plugin declares its own (`registrar.value_list`). The Settings
screens have a section for Lists where the person adds, renames and retires values. 6.31 says how they behave.

## 4.24 What lives on this computer, not in config

Some state belongs to one computer or one person and is never in the config files, the export or the synced folder. It sits in
the workspace's private folder, `<workspace>/.cockpit/`, which the workspace's git ignores:

- the install token the browser presents in local mode;
- keys pasted on a screen (an AI account's key, a plugin's app registration, a secret a plugin keeps), each a file readable
  by its owner only, referred to from config as `file:`; a hosted app takes keys only from its environment (Part 12);
- the tokens of each sign-in (6.27), beside the plugin's other kept secrets;
- where each outside program is found, per plugin tool (`.cockpit/tools.yaml`); two computers can differ;
- which setup steps were skipped, the result of the last backup per target, and which sign-ins have already had their sources
  started.

Each of these small files is written whole (a temporary file replaced over the old one), so a reader never finds half of
one, and a change that reads, changes and writes one holds that file's lock, so changes made at the same moment (request
threads and the worker's threads) are applied one after the other and none is lost (`engine/state_file.py`).

What the synced folder carries instead is in 5.0.

## 4.25 Knowledge (`knowledge:` in `config/dispatch.yaml`)

*Designed, phase L* (6.22). The settings of the learning loop, with their defaults. In the schema from L2's first
commit: `glossary_all_below`, `facts_budget`, `stable_budget`, `search_rounds`, `search_results`; each run's knowledge
log is the `knowledge` field of its `Run` record:

```yaml
knowledge:
  glossary_all_below: 150      # the whole glossary goes in every packet while it has fewer terms than this
  facts_budget: 4000           # characters of ranked facts per input; the rest is counted and searchable
  stable_budget: 8000          # characters of rules, lessons and glossary sent with every run; set from the logged sizes
  search_rounds: 2             # how many times a run may ask for a search before it must answer
  search_results: 20           # results per search
  learn: on                    # on or off; corrections with the person's words are learned from at once either way when on
  learn_every_minutes: 30      # how often silent corrections (undo, edited follow-up, pulled back) are learned from
  proposals_expire_days: 14    # unreviewed proposals from inputs expire after this, counted on the next day's card
  unused_days: 60              # an active entry that matched nothing for this long is offered for retirement
  check_on_switch: true        # offer the learning fixture pairs, with their cost, when a tier's account or model changes
  refusals_to_packet: {share: 0.05, of_last: 50}   # a check refusing this often puts its full seed lesson in the packet
  discards_hold_days: 90       # a proposal close to one the person discarded this recently is not shown again
  min_corrections_per_week: 10 # a task kind's week counts in the learning rates only with at least this many corrections
```

Learning has two task kinds, so their tiers and budgets are set in `ai.yaml` like any other (4.8). `learn-correction` writes
lessons and rules and defaults to the stronger tier. Learning from inputs is part of an input's own run (reading notes), so it uses that run's tier.

