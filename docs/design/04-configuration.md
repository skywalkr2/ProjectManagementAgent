# Part 4. Configuration model

All config is YAML (rules prose in Markdown), validated against a schema at startup and by the self-check. Every key has a
default, so a new workspace runs with an almost empty config. Each file starts with a comment block explaining every key. Core
config lives in `config/`; each plugin's lives in `config/plugins/<plugin>.yaml`.

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
- **Layers, in order of precedence:** built-in defaults, then the workspace's config files, then environment variables, then
  command-line flags. Any key can be set from the environment as `COCKPIT__<FILE>__<KEY>` (for example
  `COCKPIT__SERVER__BASE_PATH=/admin`), which is how hosting platforms usually pass settings. `cockpit config show` prints the
  effective value of every key and which layer it came from.
- **Profiles:** `config/profiles/<name>.yaml` holds overrides for one environment (`local`, `hosted`); `COCKPIT_PROFILE`
  picks one. The same workspace can run on a laptop and on a host with only the profile changing.
- **Versioned, with migrations.** Every config file starts with `version:`. When the core or a plugin renames or reshapes a
  key, it ships a migration; at start the engine migrates older files, commits the before and after to git, and lists what
  changed on the Admin tab. A file newer than the running code is refused with a clear message. The self-check fails if a
  fictional workspace isn't at the current version.
- **Presets and levels.** Each key's schema marks it `basic` or `advanced`; the Settings panel shows basic keys first. Packs
  ship presets (a starting set of values for their kind of work) that a new workspace picks from, so nobody starts from a
  blank page of options.
- **Explainable.** `cockpit config explain <key>` (and the same in the Settings panel) shows the effective value, which layer
  set it, the default, the description, and every part of the product that reads it.
- **Settings in the app:** the Admin tab has a Settings panel with a form per config file, generated from the schemas, with
  each key's description and default. Saving validates, writes the file and commits it to the workspace's git, and records the
  change in the ledger as a `config.set` by the PM. Keys set by an environment variable or flag show as locked, with where they came from. Secrets
  are never shown or typed into config; the form takes a reference (`env:NAME`, `keychain:NAME`, `file:/path`).
- **Safe to change while running:** most settings apply on save. Settings that need a restart (address, port, base path,
  storage backend) say so and offer it.

## 4.1 `config/workspace.yaml`

- `assistant_name`, `assistant_description` (display only)
- `user`: the PM's full name, aliases ("me", first name), timezone
- `plugins`: `enabled` (names with optional version ranges), extra search `paths`
- `connectors`: named connector instances, each with a `type` (a registered connector) and its settings
- `channels`: named channel instances, each with a `type` (a registered channel) and its settings
- `our_accounts`: accounts the cockpit publishes and sends with, per connector or channel; edits by them are marked
  `by_us` and given to every run (6.4, 6.6)
- `owner_format`: how an owner is written and parsed, e.g. `"{full_name}"` (default) or `"{team} ({full_name})"`
- `audiences`: who can see each destination: `open`, or a named group (members by person or team id). Each channel target
  names its audience, and may name a banner shown on it (e.g. "Restricted: program leads only").
- `restrictions`: how a restricted source is recognized (a label, a folder, a sender, a marking in the text) and which
  audiences may see it. A source with no restriction allows every audience. Checked by the audiences invariant (6.7).

Approval before anything goes out is not a setting; it is always on.

## 4.2 People

People are records (5.1), not config: added by the AI with `person.add` or by the PM, edited in the app, exported to
`data/people.json`. Fields: `full_name`, `aliases`, `role`, `team`, `org`, `how_to_reach` (per channel), `why_they_matter`,
`track_only` (inside the tracked area but only observed), `non_working_calendar`, `verified` (spelling checked against a primary
source), `status`. A person's area (tracked, a domain, or unknown) comes from their team and `config/scope.yaml` (4.4). Fictional
workspaces ship people in `data/people.json`, imported at test time.

## 4.3 `config/routing.yaml`

Ordered rules that choose a recipient for a question by topic, project, owner team or kind:
`when: {topic: requirements, project_field: product_owner} then: {to: "{project.product_owner}"}`.
A rule can say `ask_user_first` (unsure: the PM routes it). Unmatched questions go to the PM as a routing decision, never to a
guess.

## 4.4 `config/scope.yaml`

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

## 4.5 `config/watch.yaml`, `config/triage.yaml`, `config/schedule.yaml`

- **Watch:** entries naming a connector instance and what to watch through it (a page with or without children and depth, a
  tree, people's recent edits, a query, a folder, a feed). The settings each entry accepts come from the connector's schema.
- **Triage:** rules, each with `name`, `kind` (a registered matcher), parameters, and a `why` template shown to the PM. The core
  matchers are generic: `same-edit`, `cosmetic`, `already-seen-file`, `diff-terms-absent`, `owner-not-ours`, `other-domain` (a
  change entirely inside another domain that names no tracked item: kept as a source and closed as observed),
  `container-not-mapped` (an item under a watched container that maps to no project), `child-item`, `unknown-key`. Plugins may
  register more.
- **Schedule:** jobs (core and plugin) with cron-like times, working hours, which jobs need the network, catch-up behavior
  after sleep.

## 4.6 `config/language.yaml`

Locale and spelling list, blocked phrases on shared outputs (question-style wording: "confirm", "check whether", "TBD?"),
separators that mean a run-on list, words that must never appear in user-visible text (the model's name), date formats.

## 4.7 `config/render.yaml` and templates

Output types (pages, messages, posts, plugin types), their sections and column names, column widths, sort orders per section,
what counts as a cosmetic change, and how status labels render. Templates are files, not strings in code; the core and plugins
ship defaults and the workspace's `prompts/` and template folders override them.

## 4.8 `config/ai.yaml`

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

## 4.9 `config/dispatch.yaml`, `config/governor.yaml`

Batch size, immediate-run kinds, timeouts, attempts; `max_input` per task kind (the packet size budget, 6.6); governor thresholds (stuck after N minutes, stale after N hours, outage
when more than N keys fail); `fixer`: `union_merge` (file patterns merged by union on Apply, default `["*.md"]`) and
`redo_attempts` (how many times a conflicting fix is redone before it goes to the PM, default 2).

## 4.10 `config/rules.yaml`

Plain-language standing rules the PM states while working ("record who raised each risk"), each one an entry rather than a
line in a growing file:

```yaml
version: 1
rules:
  - id: R-12
    text: Record who raised each risk.
    applies_to: {task_kinds: [change, notes]}     # empty means every AI task
    source: request 3381                          # where it came from
    added: 2026-10-08
    status: active                                # active, retired, promoted
```

Rules reach only the AI tasks they apply to (6.6). Adding one is a system op (6.7), so a rule is never added from an input
without the PM confirming it. The rules review (6.21) keeps the list short and moves rules that are really settings into
config.

## 4.11 `config/status.yaml`, `config/calendar.yaml`, `config/ui.yaml`

- **Status:** the status labels in use, their colors, and which count as open, done or at risk.
- **Calendar:** the week end that "this week" runs through, holidays, and per-team non-working days (by `non_working_calendar`).
- **UI:** tab order, hidden or reordered panels, quick links in the header, and branding: product name shown in the header
  and browser tab, logo, accent colors, light or dark theme.

## 4.12 `config/plugins/<plugin>.yaml`

Each enabled plugin's settings, validated against the schema the plugin's manifest names. Same rules as core config: every key
has a default and a description, and both fictional workspaces carry demo values.

## 4.13 `config/server.yaml`

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

## 4.14 `config/auth.yaml`

- `providers`: an ordered list of sign-in methods, each with a `type` (a registered auth provider, 11.4) and its settings.
  Several may be enabled; the sign-in page offers each.
- `users`: who may sign in, by identity per provider (an email address for a sign-in provider, a username for a password).
  Everyone listed has full access in the base; roles are a later feature.
- `require_second_factor`: when hosted, a password alone is refused; defaults to true.
- `session`: idle timeout, absolute lifetime, remember-device length, cookie name.
- `lockout`: failed attempts before a pause, pause length, rate limit per address.
- `recovery`: how to get back in when locked out (one-time recovery codes generated at setup; a command run on the server
  that resets a user).

## 4.15 `config/storage.yaml`

- `backend`: `sqlite` (default) or, later, `postgres` (5.0). Changing backend runs an export and import, with the export
  committed first.
- `path`: where the workspace lives on disk. Hosted platforms need it on a persistent volume.
- `sources_store`: `local` (default: `sources/` in the workspace) or a registered object store.
- `export`: how often the readable export is written and committed (default hourly and after each batch), and an optional
  `remote` (a private git repository) to push to, so a hosted install has an off-site copy.
- `backups`: full backups (a consistent copy of the database plus sources) on a schedule, to one or more targets **off this
  computer**: a synced folder, an external drive, an object store, or the export remote. `encrypt` with a key reference
  (`keychain:NAME`) for any target outside the PM's control. Until an off-device target is set up and has succeeded, local mode
  shows a Today line and a header mark ("No off-device backup") (11.1); the header always shows the age of the last backup.
- `retention`: per source kind and restriction level, how long raw text is kept after its facts are recorded (default: forever
  locally, 180 days hosted for mail and replies); `forget_person` behavior (delete or anonymize free text that names them,
  repoint their records to "former contact"). The ledger keeps that a source existed and what was learned from it.

## 4.16 `config/facts.yaml`

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
- Connector field names (`release`, `sprint`, `fix_version`), watch entries and keys are all values here, not code; a
  connector reads whatever field it is told to.

## 4.17 `config/checks.yaml`

The severity of each lint (6.7) and its settings:

```yaml
version: 1
lints:
  blocked-wording: {severity: return}
  locale-spelling: {severity: warn}
  run-on-list: {severity: return}
  fact-terms-without-asks-for: {severity: return}
  near-duplicate-action: {severity: warn, similarity: 0.85}
  unreachable-link: {severity: warn}
```

Severities: `refuse`, `return` (back to the AI once; then held for the PM if the item will reach another person, or applied
with a warning if it stays internal, 6.7), `warn`, `off`. Invariants (6.7) are not
listed and can't be lowered. Plugins register their own lints with defaults here.

## 4.18 `config/code_owners.yaml`

Which project owns which code or tool, so a request about something the PM uses but this product doesn't own (a dashboard that
reads the published pages, a script another team runs) goes to its owner instead of the fixer:

```yaml
version: 1
owners:
  - name: portfolio dashboard
    match: {terms: [dashboard, chart, tile], outputs: [summary page readers]}
    owner: Ana Ortiz                 # a person record
    handoff: {channel: team-chat, target: dashboard requests}
```

A matching request becomes a `handoff` draft (6.7), with the request, what the PM saw and links, for the PM to approve and send.
Anything that matches nothing and needs code goes to the fixer as before.

