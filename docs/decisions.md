# Product decisions

Dated entries: what was decided, who decided, why. Newest first. Decisions about one deployment go in that workspace's own
`docs/decisions.md`, not here.

## 2026-10-11: Command-line agents are chosen from a list, and accounts can be fixed after adding

**Decided by:** project owner ("we should have built in Anthropic CLI and Copilot CLI options … as there is no reason why
we need the user to set this up by hand"; an account saved by mistake "you can never fix").

**What:** The Add account screen offers the common command-line agents by name (`catalog/ai-endpoints.yaml`), each with
its command, the program's own options that keep its tools off, how it takes the packet and where its answer is. The
screen says whether the program is installed and how to sign in; the person never types a command. An agent that only
takes the packet on its command line gets it as an argument, refused above a size limit. Added accounts are listed with
Replace key, Change models and Remove (with Undo). The template step counts as done when the workspace already has a
starting template's item types, and each template lists what it adds before it is applied.

**Why:** Typing an agent's locked-down command by hand is error-prone, a mistaken account blocked adding it again, and
the template step gave no way to know what it would do.

**Impact:** `catalog/ai-endpoints.yaml` (data, not code); `agent.packet_via: argument` and `{prompt}`; `GET /ai/accounts`,
`POST /ai/accounts/{name}`, `POST /ai/accounts/{name}/remove`; `EndpointView.program`, `installed`, `model_examples`,
`model_optional`; `TemplateView.adds` and `set_up`. No change to scope.

## 2026-10-11: The app restarts only when it must, and only when the person says so

**Decided by:** project owner ("only restart when it's necessary and then warn the user before that happens").

**What:** Settings that everything reads at the moment of use apply at once, with no restart: AI accounts, tiers and
budgets, who the person is, the workspace's and assistant's names, the screens' wording and shortcuts, and the
accounts counted as ours. When saved settings (or the app's code) change in a way that needs a restart, the app says
so, holds new AI work, and waits: the person chooses "Restart now" or "Later". The app never restarts on its own. A
copy that can't start itself again says to close and start it.

**Why:** Adding an AI account restarted the app mid-setup, and the restart itself could fail (the web server raised
the stop signal again after shutting down, ending the process). A restart nobody asked for loses the person's place.

**Impact:** `engine/worker.py` (`LIVE_KEYS`, `apply_live`, `request_restart`); `POST /api/restart`;
`SettingsSaved.needs_restart` and `TemplateApplied.needs_restart` replace `restarts`; `status.can_restart`; the
settings screens ask before restarting. The serve command stops the server without a signal.

## 2026-10-11: Publishing a pack is a set process the owner approves

**Decided by:** project owner (a set process; plugin sessions never publish to the catalog); project lead (the steps).

**What:** A plugin repository releases in its own repository, keeps its entry in `catalog/pack.yaml`, runs `cockpit
pack check` (the manifest fits this host, the pack loads in a demo workspace, the entry matches `plugin.yaml` as
written), and adds a Publish request to its questions file. The host's session verifies the release itself and opens
a pull request on the catalog; the owner merges it, and only then is the pack listed. The steps are in the generated
developer guide ("Publishing a pack"), the catalog's PUBLISHING.md and `docs/plugin-kickoff-template.md`, which every
new plugin repository's kickoff brief is built from.

**Why:** The catalog is public and lists only what the owner chooses; a checked, repeatable path keeps entries honest
about what a pack reaches and keeps.

**Impact:** `engine/pack_check.py` and `cockpit pack check`; plugin API 0.3.37 notes; the catalog's main branch takes
changes by pull request only.

## 2026-10-11: The core is an everyday assistant, with Today as a dashboard

**Decided by:** project owner.

**What:** The core serves anyone running their own days, not only project managers: a solo person sets it up and lets
it read their mail and calendar and tell them what to do each day; a PM gets the same home and more. Today becomes a
dashboard that uses the screen: on a laptop, several columns visible without scrolling (today's agenda, what to do
today, what needs a reply or a decision, what changed since last time), each column scrolling on its own with a way to
see everything; fewer columns on smaller screens, one on a phone. Calendar events and mail messages that sources read
carry structured fields (start, end, place, people, sender) so the agenda and the inbox show them without an AI call.

**Why:** The same daily needs sit under every kind of work; a one-column list wastes a laptop screen and hides things
below the fold.

**Impact:** Design Part 7 (Today) and 6.4 (watched items carry structure); a Today redesign; `SourceItem` gains
optional event and message fields in a plugin API version; the scope's audience widens beyond project managers.

## 2026-10-11: One source of truth, value lists instead of free text, and settings that guide

**Decided by:** project owner.

**What:**
- **One source of truth for all data.** Every fact lives in exactly one place; everything else refers to it by id.
  The PM's name and aliases live on their person record only; `workspace.user` keeps the person's id and the
  settings that are about the workspace (time zone). A setting never repeats a record, and a record never repeats a
  setting. The rule binds plugins: a plugin refers to core records by id (`RefTo`) and never copies their names or
  fields into its own records, and the host checks what it can (design 3.5, 5.1).
- **Value lists.** A field with a known set of values (a project's status, phase and priority, a person's role and
  organization, a plugin's categories) takes its values from a named list, shown as a dropdown. Lists are settings
  (`config/lists.yaml`), with defaults from the core and from plugins, changed by the person; a value not on its list
  is refused, and adding one is a deliberate act ("Add to the list"), with Undo. Free text is kept for what is truly
  prose: notes, descriptions, summaries, the text of a question.
- **Settings guide the person.** A setting that turns a feature on comes first in its group, and the settings it
  governs are greyed out while it is off. A folder is chosen with a folder picker, a file with a file picker, a
  choice from a dropdown; typing a path or a value is the fallback, not the way.
- **AI setup for anyone.** Setup offers a list of AI services by name (a shipped data file; still no service names in
  code): pick one, paste a key (kept on this computer by the app), pick from the models the service offers, with
  suggested models for everyday and harder work, and test. Local models and command-line agents are on the same list.

**Why:** Free text and duplicated data make a system that breaks quietly; guided settings prevent mistakes instead
of explaining them.

**Impact:** Design 3.5, 4.0, 5.1 and 7 (settings). `workspace.user.full_name` and `aliases` move to the person
record. New `config/lists.yaml`, list-backed fields in core records and a plugin declaration for lists. Settings
metadata for order, dependencies and pickers. Named services in `catalog/ai-endpoints.yaml`; this answers the open
question "May catalogs list public AI services and addresses?" (yes, in data). Plugin API: lists and the one-source
rule join the contract.

**Update (same day):** the shipped list names services, their addresses and where to make a key, but no model ids:
those go stale within months. The screen lists the models the service itself reports (`POST /api/ai/models`, with a
key that isn't kept) and the person picks one for everyday work and, optionally, one for harder work. Suggesting
models waits until it can rest on what a service publishes (prices, context size) rather than on names.

**Update (same day):** value lists are kept as records (`value_list`), not in `config/lists.yaml`: adding a value
then has history and Undo like any change and needs no restart, the lists travel with the workspace's data, and the
storage layer refuses an off-list value from any writer. The core's first values ship in
`engine/defaults/value_lists.yaml`; plugins declare theirs (plugin API 0.3.42). First fields bound: a project's
status, phase, priority and group. A person's role and organization are not lists yet: an organization is better as
its own record (one source of truth), and that comes with the people screens.

## 2026-10-11: Every plugin repository has its own autonomous builder, with a written brief and a question channel

**Decided by:** project owner.

**What:** A plugin kept in its own repository is built by its own autonomous session, not from this one, so its
feedback on the plugin API is independent. Whenever this project suggests a new plugin repository, it also gives the
owner a kickoff brief: what is built there and in what order, the rules it follows, the contract (the generated
plugin guide), what the owner sets up, and how the two sessions talk. Questions to the host come in numbered rounds
in that repository's `docs/host-questions.md`, written generically, announced by a short session message; the host
answers by building a plugin API version and messaging back. A friction log records where the guide was unclear or
needed a workaround. Neither session writes to the other's repository.

**Why:** Clean feedback from builders who don't share this session's assumptions.

**Impact:** Applies to the mail and calendar plugins now, and every plugin repository after.

## 2026-10-11: Packs are found on an Add-ons screen, from catalog feeds, with costs priced on the person's accounts

**Decided by:** project owner (direction, maintainers' packs only in the default catalog, prices shown, the catalog as
a public index file the owner controls); project lead (design 3.11).

**What:** An Add-ons screen with Installed and Available. A listing shows what a pack does, what it adds, reaches and
keeps (written by the core from the pack's manifest), what its typical AI jobs cost on the person's own accounts, its
price and how to try it in the demo. The app never installs code into itself and never handles payment. Feeds are
read only when the person looks; the release build ships the maintainers' feed address; the repository holds none.

**Why:** People should be able to find out what packs exist, what they do, what they can touch and what they cost,
before installing anything, without ads or tracking.

**Impact:** Design 3.11; a `workspace.plugins.catalog` setting; `/api/packs` routes; the Add-ons screen. First
release: the catalog, the generated summary, the cost estimate, demo and install instructions. Later: updates with
re-approval, licence keys, Ask knowing the catalog, signed feeds, install from the screen.

## 2026-10-11: Mail and calendar from named services are plugins in a private repository; the core signs in

**Decided by:** project owner (plugins, in a new private repository); project lead (the sign-in in the core).

**What:** Mail and calendar from the two named services are plugins kept in their own private repository, which may
name the services and carry their sign-in addresses. The core gains a generic sign-in any plugin can declare
(`registrar.sign_in`, plugin API 0.3.33): OAuth 2.0 authorization code with PKCE through the service's own page, the
answer taken at the app's own callback route, tokens kept on this computer beside the plugin's other kept secrets and
renewed by the core, and `context.access_token(name)` for the plugin's connectors. The app registration (client id)
is the person's, set as a plugin secret.

**Why:** The open protocols cover most mail and calendars today; the services' own sign-in and richer APIs need code
that names them, which this repository keeps out.

**Impact:** Answers the open question in "Calendars and mail are read through open protocols". New routes under
`/api/sign-ins` and a Settings section for them. The plugins wait for the private repository.

## 2026-10-11: The package carries its screens, templates and demos; a demo says it is one

**Decided by:** project lead, under the owner's friends' preview milestone.

**What:** The wheel carries the starting templates, the AI endpoint catalog, the built web screens and the two fictional
demo workspaces in `engine/_shipped/` (a build hook copies them; a checkout reads them in place, through
`engine.shipped`). Building a wheel without the web screens stops with how to build them. `cockpit demo [folder]` makes
a demo workspace once (`--fresh` starts over, and refuses a folder holding a workspace that isn't a demo) and serves it,
opening the browser. New settings: `workspace.demo` (the screens label made-up data) and `server.open_browser` (with
`--open` and `--no-open`). Install and update are one script around `uv tool install --force`; a tag builds the package,
checks that it installs and starts the demo, and attaches it to a release with the scripts and `docs/install.md`.

The stand-in AI, with nothing scripting it, reads a hand-in by plain rules (`engine/ai/adapters/stand_in.py`): "<Name>
will …" is an action for that name, "we still need …" an action waiting for an owner, "Decided: …" a fact, each citing
its line; the rest is one note. It answers a question by quoting the first guide passage chosen for it. The demo's
screens say it is a demo (`workspace.demo`), and a feedback button drafts an email to `ui.feedback_to`, else to the
address a release build ships in `catalog/product.yaml` (empty in the repository); the app sends nothing itself.

**Why:** Friends get a download, not the repository: no Node, no checkout, one command to try it.

**Impact:** Roadmap "Friends' preview" (packaged install done; labeled demo screens and feedback button next). No change
to scope.

## 2026-10-11: Calendars and mail are read through open protocols in the core; product sign-ins wait for the owner

**Decided by:** project lead, pending the owner's answer below.

**What:** The core reads a calendar through its private calendar-file address and a mail folder over IMAP with an app
password. Both are protocol-level connectors that name no service, so they belong in the core. The address and the
password are secret references. Mail is read without marking anything as read. Calendar events in the configured
window are followed, so a moved meeting or a new invitation is handed in.

**Open question for the owner:** the to-do was mail and calendar for two named services. Their own sign-in (needed
when a service doesn't offer app passwords) and their richer APIs belong in plugins that name the service. This
repository's rules say it holds the core, the kit, its templates and the example plugin, and that real service
addresses don't appear anywhere in it. Should those plugins live in their own repository (like the industry packs),
and may they carry the services' public sign-in addresses?

**Why:** Most of the value (meetings, invitations, project mail) comes through the open protocols, which work today
without any decision about naming services.

**Impact:** Two more core connectors, demo sources (off) in both workspaces, a user-guide section. No change to scope.

## 2026-10-11: Plugins reach the network only through the core's client, to declared hosts

**Decided by:** project lead, following design 3.2 (what a plugin may reach) and 12.

**What:** `requires.network` and `requires.secrets` are now in use. A plugin's connector gets a web client that reaches
only its declared hosts, over HTTPS, with redirects checked against the same list and a size cap, and its declared
secrets: references in the workspace's settings, or values it keeps on this computer itself (a refreshed sign-in
token). Bundled plugins still may not import network modules; the scan enforces it. The core's feed connector reads
RSS and Atom and refuses documents that declare their own entities.

**Why:** Mail and calendar connectors need the network and a token; the person must be able to see exactly where an
add-on can reach before enabling it, and a compromised feed must not be able to make the app read other hosts.

**Impact:** Plugin API 0.3.27, `workspace.plugins.secrets` (demo values), a disabled demo feed source. Sign-in flows
for accounts come with the mail and calendar plugins. No change to scope.

## 2026-10-11: Triage rules live beside the watched sources

**Decided by:** project lead.

**What:** Triage rules are a `triage:` list in `watch.yaml`, not a separate `triage.yaml`, because they only ever apply to
watched changes and often name a source. A closed change is still kept as a source and a done request with the rule
and reason, listed as Auto-closed; Take a closer look queues it and records a `pulled_back` signal. A newer change to
an item whose earlier change hasn't been read yet folds the earlier one in, so the assistant reads them once, in order.
`our_accounts` is in `workspace.yaml` (design 4.1).

**Why:** Fewer files for the person to find, and one place that says what is read and what is set aside.

**Impact:** Design 4.5 and 6.5 read `watch.yaml` for triage. Plugin API 0.3.26 adds triage matchers. No change to scope.

## 2026-10-11: Watchers hand in differences as ordinary inputs; the first read is a baseline

**Decided by:** project lead, following design 6.4 and the decision on watchers and lookups (2026-10-10).

**What:** A watched source's read returns what it holds now; the core compares with snapshots and turns each
difference into a source record and a queued request, exactly like a pasted input but untrusted and marked with where
it came from. The first read of a source records a baseline instead of handing in everything (configurable). Removed
items are reported unless the source turns that off. No network files nothing; repeated failures file one question,
and a good read drops it. Connectors are an extension point (plugin API 0.3.25); the core ships a folder connector.

**Why:** One path for every input keeps evidence, trust and review the same whatever the source. A baseline avoids a
flood of work and cost on day one.

**Impact:** New config file `watch.yaml` (demo values with an inbox folder in both workspaces), records `snapshot` and
`watch_run`, `source.watched`, routes `/api/watch`. Triage and supersede come next, then a feed connector and network
access for plugins. No change to scope.

## 2026-10-11: Asking the assistant answers from quoted material only

**Decided by:** project lead, following the decision on asking about the app (2026-10-10).

**What:** An ask is a core `ask` request. Its packet holds the user guide sections that match the question, the
settings (no key locations), what the install can do and the records. The answer is an op whose cites are checked
against that material like evidence. Suggested settings are proposals the person applies through the same settings
save (fingerprint, validation, Undo). Requests the product can't meet become report drafts the person sends. The user
guide ships in `engine/guide/guide.md` and is the only source for how the app works.

**Why:** An assistant that explains the app must not invent buttons or settings. Quoting checked words gives the
same guarantee as evidence on claims, and proposals keep the person in charge of every change.

**Impact:** New core ops `answer`, `setting.propose` and `report.draft`; records `answer`, `setting_proposal` and
`report`; routes `/api/ask`, `/api/asks`, `/api/setting-proposals/*` and `/api/reports/*`. The Ask screen comes with
the next screens step. No change to scope.

## 2026-10-11: Settings are saved from the screens, and the app restarts itself to use them

**Decided by:** project lead, following design 4.0, 6.14 and 7.8.

**What:**
- The Settings forms are described from the config schemas. A save names the fingerprint of the files the form came
  from, so two saves never race. Keys set by an environment variable or flag are locked, and the server's own keys and
  the storage backend are changed only in their files. The changed files are checked as a whole before anything is
  written, written keeping their comments, committed to the workspace's git, and recorded as `setting_change`
  records.
- Instead of reloading settings inside a running process, the app restarts itself between requests when its config or
  code changed (locally it re-executes). Old code never runs new settings, and nothing is half-reloaded.
- The first run has the design's steps plus a template step and plugins' own steps. Skips are kept per computer.
- A key pasted on the Add account screen is kept in the workspace's private folder (readable only by the user) and
  referred to as `file:`; a hosted app takes keys only from its environment.
- Kinds of AI account come from `catalog/ai-endpoints.yaml`. It lists only kinds that name no service for now.

**Open question for the owner:** may the catalog list public AI services by name and address (the repository rule
says no real URLs anywhere)? Until answered, people type the address of any service that isn't a local server.

**Impact:** New `setting_change` record type, plugin API 0.3.24 (`setup_step`), new routes under `/api/settings`,
`/api/setup`, `/api/templates` and `/api/ai`. No change to scope.

## 2026-10-11: Plugin API 0.3.23: contained failures, refusals shown before applying, stages that apply to some records

**Decided by:** project lead, from a plugin author's questions.

**What:**
- Today lines, interface items, event handlers and jobs are contained per call: a failure skips that call and is noted on
  the plugin; the plugin turns off after `workspace.plugins.failures_before_off` failures in a row there (default 3).
  Contract breaches and failures inside writes still turn it off at once.
- A person action's preview tries the whole proposal without keeping anything: an item that would be refused shows why
  and starts dropped, and other refusals are listed, so the person changes a choice instead of the action failing.
- A request can name an interface item; the provider's `about` function says which of its records the item stands for.
  Undeclared item fields are noted on the provider.
- `limits.room_mb`, `record_label` for messages, `follows` on work a handler does after a change, and `applies_if` on a
  stage.

**Why:** One failing read turned a whole plugin off, and an action failed outright on one refused part; a user of an
interface had to know the provider's ids; a stage that only some records need blocked the others.

**Impact:** New settings `workspace.plugins.failures_before_off` and a stage's `applies_if` (schema, defaults, demo
values). Tests that expected one failure to turn a plugin off now expect the configured count. No change to scope.

## 2026-10-11: Agent accounts are a command run locked down, described entirely in settings

**Decided by:** project lead, following design 6.16 (agent mode).

**What:** A `cli-agent` adapter runs any command-line agent as a program. The account's `agent:` settings say how to
start it (`command`, with `{model}`, `{packet}`, `{outbox}` and `{scratch}` placeholders, locked-down flags included),
how the packet goes in (`stdin` or a file), where the answer comes out (its output or a file in the outbox), where usage
and cost are in its JSON output, which environment variables it may see (`pass_env`, `key_env`), how to read its exit
codes and error stream (`errors`), and what to tell the person when it isn't signed in (`sign_in_hint`). Each run gets a
fresh folder in the system's temporary space, outside the workspace, and only PATH, HOME and the language settings
besides the listed variables. A cost the agent reports is used as the run's cost. The smoke test runs
`lockdown_test()` once per agent account: writing to its outbox must work; writing elsewhere and starting a shell must
not.

**Why:** Agents differ in flags, output shapes and error text from vendor to vendor and release to release; settings keep
every one of those out of the code, and the lockdown test catches flags that don't hold.

**Impact:** New `agent` settings under each provider in `ai.yaml` (schema, defaults, descriptions, demo accounts in both
workspaces). `AiError` gains a `hint`, shown in the waiting reason for a sign-in failure; `AiResult` gains `cost_usd`.
The lockdown is only as strong as the agent's own flags; the core can't sandbox a program by itself on every system, so
the test is the check. No change to scope.

## 2026-10-10: The core is complete on its own; the free version is "define your own"; industry packs are add-ons

**Decided by:** project owner.

**What:**
- **The core alone is a complete product.** A person installs it, is guided through setup, and runs their work with it.
  No screen ever depends on a pack.
- **The free version is the core plus a "define your own" kit**, not an industry pack: item types with fields (text,
  date, person, choice, link, number), stages with plain descriptions and entry checks, checklists, which fields the
  assistant may fill from inputs (with evidence), and what Today shows. All of it is set on screens, kept in workspace
  settings, and saved and shared as one template file. Starting templates ship with the core; the fictional demo
  workspace runs on one.
- **Industry packs are add-ons on the plugin API**, in their own repositories. The publishing pack moves to a private
  repository (to be sold later if the owner chooses); the workplace pack and its product connectors become a private
  add-on too. This repository keeps the core, the kit, templates and the example plugin.
- **Guided install and setup:** the web screens ship built inside the package (no Node needed to run it); install and
  update are one step; a first run in the browser walks through where the workspace lives, who you are, the AI account
  (with a connection test and plain errors), a starting template, backups and a first hand-in. Settings screens cover
  everything the files hold.
- **Agent accounts** (a vendor's command-line agent run with the person's own login, as corporate installs need) come
  before the friends' preview, so people can use subscriptions they already have.
- **Watchers and lookups** (6.19, milestone 5): the watcher engine, scheduling and general sources (a folder, a feed) are
  core; connectors for particular products are plugins.
- **Ask the assistant about the app** (extends 6.25): answers come only from the user guide, the workspace's settings
  (never secrets), what the install can do, and the person's records, with the passage shown. A question that needs a
  settings change becomes a proposed change the person confirms, with Undo; one the product can't do becomes a report
  to the maintainers (6.13).
- **A friends' preview** is a milestone: packaged install, guided setup, a clearly labeled demo with the stand-in,
  bring-your-own AI, a feedback button that drafts an email, and a download rather than repository access.

**Why:** The owner wants a free product anyone can set up and use for their own kind of work, with industry depth sold
separately, and to put it in friends' hands for feedback.

**Impact:** Supersedes "two reference packs bundled in version 1" in `scope.md` and design Part 9 / 13 (the packs still
prove the plugin API, from their own repositories). Order: plugin API 0.2, the kit, guided install and setup with agent
accounts and Ask the assistant, the friends' preview, watchers and connectors, then the publishing pack. The
publishing pack is no longer the path for the 2026-12-01 launch; a publishing template built with the kit is.

## 2026-10-10: Follow-ups: two steps, copy then Mark sent

**Decided by:** project owner.

**What:** Copy only puts the message on the clipboard. After a copy, the card's primary action becomes Mark sent, which
records the box's text as sent with an Undo toast; the card's menu always offers Mark sent too. This supersedes the part of
the earlier entry "Follow-ups: Copy marks sent" that made Copy record the message as sent.

**Why:** Copying is not sending; the person sends from their own email or chat and marks it sent when it has gone.

**Impact:** Design 7.5 and the wording sheet; no API, op or scope change. The sent view is unchanged.

## 2026-10-10: Dismiss a hand-in that stopped; Today suggests moves only for items already in a stage

**Decided by:** project owner (from trying the app); Claude wrote it up.

**What:** A hand-in stuck in "Needs you" or "Stopped" can be dismissed from its row menu (it keeps "Try again" as its action).
It goes to Done with a "Dismissed" label, stops counting as needing attention, and Undo puts it back as it was. A stage task
waiting for a go keeps its Go and cannot be dismissed. Today's "ready to move on" rows leave out items not yet in a stage;
Stages still offers the first stage for them.

**Why:** The only action on a failed hand-in was to try again, so an old one stayed forever. Suggesting the first stage on
Today for every item that was never started buried the real work.

**Impact:** Two optional fields on a request (`dismissed`, `dismissed_from`), two routes, one wording set. No scope change.

## 2026-10-10: Independence for second opinions is a setting per task kind

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** `tasks.<kind>.independence` in `ai.yaml`: `vendor`, `account` (default) or `isolated_run`. With `isolated_run`, a
check may use the same account in a separate run that carries only its own packet: never the writing run's history or
session, and on an agent account only after the lock-down test. A different model on the same account is preferred
when configured. The review says plainly which kind of independence was used, without naming the model.

**Why:** Many people have one subscription for everything; requiring a second account would put second opinions out of
their reach, while a separate packet-only run still removes the writing run's context.

**Impact:** Design 6.16 (independent second opinion) when built.

## 2026-10-12: Drafts are prose, anchored when they revise, and reviewed change by change

**Decided by:** Claude (design 6.7 as built); the owner can override.

**What:** A draft task kind's model writes plain prose; the core wraps it as a pending version, continues it once if
cut off, and runs lints on it. A revision can be anchored: the model marks each paragraph with the base units it came
from, a core invariant checks the map accounts for every unit and keeps atomic units whole, and the map decides
authorship. The person reviews pending versions through routes that give the regions to decide (three-way when the
text moved on) and accept, discard or edit.

**Why:** Long prose inside JSON is where cheaper models fail; anchors make "what changed and who wrote it" exact
instead of guessed.

**Impact:** Plugin API 0.3.9. The review and compare screens come with the UX work.

## 2026-10-12: Long text is versioned, reviewed change by change, and the assistant's text is always a draft

**Decided by:** Claude (design 5.0, 6.7 as built), the owner can override.

**What:** Long text fields keep every version (stored once by hash) with authorship by passage in three kinds. A
plugin writes them only with `writer.set_text`: from the person's own action the text is accepted and theirs; from
anyone else it is a pending draft. Accepting a pending version is change by change; when the current text moved on
since the version's base (a working copy handed back late), the merge is three-way: changes only in the current text
are kept, changes only in the proposal are offered, and a passage both changed is the person's pick. The export writes
texts as plain files beside the records.

**Why:** The assistant's prose must never become a book's text unreviewed, and a writer's own edits made elsewhere must
never silently undo what was accepted in the meantime.

**Impact:** Plugin API 0.3.6. Drafts as task output, anchored drafts and the compare routes come next.

## 2026-10-12: Plugins add lints; lints never refuse by default

**Decided by:** Claude (design), from the plugin's needs; the owner can override.

**What:** A plugin registers soft checks on the assistant's proposals. Each finding names the passage and how to fix
it; on "return" both go back to the assistant for its fix round. The plugin sets a default severity of return, warn or
off, never refuse; the workspace's `checks.yaml` overrides it per lint like the core's own.

**Why:** Voice and style rules are judgments: they belong with lints the person can tune, not with invariants.

**Impact:** Plugin API 0.3.5. Lints on long text and drafts come with long text.

## 2026-10-12: Projects inside projects, a language per project, and a budget per project

**Decided by:** Claude (design), from the plugin's needs; the owner can override.

**What:** A project may belong to another (`parent`; a series holds its books), never to itself or one of its own
parts. Language is a workspace setting (`workspace.language`, a tag such as en-US) a project may override, inherited
down through parents. `project.add` starts a project as a system op (the assistant's proposals wait for the person;
reading notes doesn't offer it). A project may carry a budget, set only by the person, covering AI work on it and
everything inside it; a run that would pass it waits with what is spent.

**Why:** A book series is a parent with child books; spelling, punctuation and dates follow the book's variety; and a
writer needs to see and cap what each book costs.

**Impact:** Plugin API 0.3.4. New fields on Project (`parent`, `language`, `budget_usd`), setting
`workspace.language`, op `project.add`. The project screens show and edit them in the UX pass.

## 2026-10-12: Content levels route work away from accounts that would refuse it

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** The workspace defines its content levels in `ai.content_levels` (ids and what each covers; the core names
none). Each account may list the levels it takes (`providers.<name>.content_levels`); an account without a list takes
every level, so nothing changes for people who never use them. A project carries `content_levels`, and a plugin record
type may name a field holding them; only the person sets either. A run carries the levels of its record and that
record's project, and routing skips accounts that don't take them all; if none does, the request waits with that reason.

**Why:** Refusals cost time and money and are predictable from the material; routing around them is cheaper than
handling them after the fact.

**Impact:** New settings `ai.content_levels` and `providers.<name>.content_levels`; `Project.content_levels`;
`Record.content_levels_field`. Marking an account after a refusal from the review comes with the review screens.

## 2026-10-12: A refusal is its own outcome, and the person decides what happens next

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** An adapter reports a refusal only from the provider's own signal: a content-filter stop, a refusal field in
the answer, or a content-policy code in an error body. Never from the answer's words. The run is recorded as refused,
with its cost and the provider's reason. A refused request is never retried, sent to the next account or escalated; it
waits for the person with the reason and the cost, and the person may send it to another account allowed to see the
material (`Request.use`). Accounts are offered by their names in the AI settings, never by model.

**Why:** Fiction, medicine, security and law touch material one account refuses and another accepts; which account sees
the text and what it costs stay the person's choice.

**Impact:** Run outcome `refused`; `Request.use`; `GET /api/requests/<id>/accounts` and `use` on retry. Content levels,
which route around refusals before they happen, come next.

## 2026-10-12: Plugin API 0.3.22: work that always asks first, and queueing from an action

**Decided by:** Claude (design), from plugin questions 73-79; the owner can override.

**What:**
- Plugin requests can always wait for the person's go.
- A new setting, `ai.budgets.confirm_unpriced`, makes runs whose cost can't be estimated wait too.
- An action's proposal can queue the plugin's own work, each item waiting for the go.
- Validators see the run's task and record.
- Records can be placed in the synced folder through a reference.
- Collections sort numbers as numbers.
- Plugins can read a field's current version directly.
- "Don't copy" is separate from "don't cite".

**Why:**
- On a subscription there is no price, so "ask above an amount" never asks. Spending stays the person's choice only
  if some work always asks.

**Impact:** New setting `ai.budgets.confirm_unpriced`. The action review shows the work a proposal will queue.

## 2026-10-12: How the define-your-own kit is built

**Decided by:** Claude (design), from the owner's decision of 2026-10-10; the owner can override.

**What:**
- The kit is a bundled plugin, `kit`, built only on the plugin API. It reads item types from its settings and
  registers record types, ops, stages, a panel and Today lines for each. Its settings are the plugin's own
  (`config/plugins/kit.yaml`), so the core config doesn't change.
- A plugin op can be offered to reading notes, a generic extension point, so the assistant can fill the fields a person
  allows, with evidence.
- Templates are the kit's settings with a name and a description, shipped in `templates/`.
- A manifest may declare `<plugin>/*` in a `provides` list for identifiers its own settings define.
- Changing a type keeps the data: a removed field is hidden, not deleted, and a renamed field is renamed in every
  record.

**Why:**
- Building the kit on the plugin API proves the API and keeps the core free of any one kind of work.
- Item types are settings a person edits, so they live in config with a schema and validation, like every other
  setting.

**Impact:** Design 3.10 (new). Settings screens for the kit come with guided setup.

## 2026-10-12: Plugin API 0.3.19, and evidence only for claims

**Decided by:** Claude (design), from plugin questions 69-72; the owner can override.

**What:**
- Plugin API 0.3.19.
  - Actions can be narrowed with `where`.
  - Event handlers and jobs can stage the plugin's own ops through the applier, as a changeset treated like work from
    outside content.
  - Plugins can read the workspace person's name.
  - Previews carry alt text.
  - `record.set` can set a project's owner.
- Evidence for `record.set` fields is now required only when the change isn't the person's own.

**Why:**
- A deterministic check needs somewhere to record what it checked, and going through the applier keeps the ledger,
  validators, tiers and Undo.
- Evidence exists so claims taken from inputs can be checked. A change the person makes on screen or approves in an
  action is not a claim.

**Impact:**
- Design 6.7's evidence rule now reads "claims from inputs".
- Screens show the alt text on previews.

## 2026-10-12: Plugin Today lines, panels and jobs

**Decided by:** Claude (design), building design 3.x and 7.2; the owner can override.

**What:**
- Plugin API 0.3.18.
- **Today lines:** a function returning lines, each with one action that is the plugin's own action or task kind.
- **Panels:** declarative specs (kind, filter, columns, view, actions), checked at load. Rows are read through the
  core.
- **Jobs:**
  - A run function on a schedule. It may do what an event handler may, never write records or call AI itself.
  - It runs while the app runs, configurable per job, with a `job_run` record for each run.

**Why:**
- Plugins need a place on the home screen and their own lists without front-end code.
- Regular work, such as a weekly review, shouldn't need the person to start it.

**Impact:**
- New core record `job_run`.
- New setting `workspace.plugins.jobs`.
- The screens that show plugin Today lines and panels come with the UX pass. Until then the routes are there for
  them.

## 2026-10-12: Plugin API 0.3.17: interface refinements and person-action needs

**Decided by:** Claude (design), from plugin questions 62-68; the owner can override.

**What:**
- Interface items can be computed for one project.
- Providers can raise interface events from event handlers.
- A packet part can carry a data level that raises the run's.
- `project.add` can move existing projects inside the new one.
- Person actions get free-text choices, all-or-nothing proposals and the limits they work within.
- Named interface calls with arguments were not added. Items cover the cases asked for so far.

**Why:**
- Content from another plugin can be more sensitive than the record a run is about. Routing has to see that, or
  restricted text could reach an account not allowed it.
- An import whose ops only make sense together must not apply halfway.

**Impact:**
- Changeset status `rejected` is now also used for an all-or-nothing proposal that was refused.
- Choice views carry `text` and `max_length` for the review screen.

## 2026-10-12: Interfaces between plugins

**Decided by:** Claude (design), building design 3.9; the owner can override.

**What:**
- Plugin API 0.3.16. A plugin defines a versioned interface (an item model, events, task kinds). Others provide it
  (an items function, events raised from ops, their own task kinds mapped to the interface's) or use it.
- Users read checked copies of the items, never the provider's records, filtered by their own data levels. They get
  the events and can request a provider's task kinds through the interface.
- Required uses keep a plugin off until something provides them. Optional ones read empty.
- The manifest gains `interfaces.defines`.

**Why:**
- Packs must work together without importing each other or reading each other's tables, and each must work alone.
- Checking items against the definition at read time puts a provider's mistake on the provider.

**Impact:**
- Design 3.9.
- The "uses" notice before enabling a plugin comes with the UX pass.
- A self-check case for required interfaces in the fictional workspaces comes with the first bundled pair.

## 2026-10-12: Outside edits, collections and generated files in the synced folder

**Decided by:** Claude (design), building design 5.0 and from plugin questions 59-61; the owner can override.

**What:**
- Plugin API 0.3.15. Files changed outside come back as proposals: long text pending, field edits and deletes held. A
  new core op, `record.edit`, carries the person's field changes to any record.
- Collections put many small records in one YAML file.
- Layouts can use a referenced record's field.
- Plugins can declare generated read-only files.
- Sources, outputs and working copies get readable copies, and file bytes travel in the machine copy.
- The machine copy now carries file and source bytes, which fixes handover for workspaces with files.
- Encrypting or leaving out sources above a data level waits until sources and files carry a data level. Until then
  every source is copied.

**Why:**
- Writers edit in their own tools. Outside edits must reach the record without ever changing it silently.
- Many tiny files make a folder unreadable.
- Records like a chapter's bible entry are named after another record.

**Impact:**
- Design 5.0.
- New setting `storage.sync.watch_outside_edits`.
- Core op `record.edit` is person only and never offered to note reading.
- The review screens for held edits exist; a screen listing outside edits comes with the UX pass.

## 2026-10-12: Handing a workspace between computers

**Decided by:** Claude (design), building design 5.0; the owner can override.

**What:**
- The folder's lease says which install holds the workspace. Opening compares the two ledgers entry by entry:
  - the same: nothing to do;
  - the folder continues this computer's history: back up and load the folder;
  - this computer continues the folder's: write the folder;
  - neither continues the other: refuse, until the person runs `cockpit sync keep --here` or `--folder`.
- Loads read only manifest-listed files that match their hashes.
- Storage and server settings stay per computer.
- A running install stops writing once another holds the lease.

**Why:**
- Comparing whole ledgers can't mistake two different histories of the same length for one.
- Hash-checked loads keep a half-synced folder or a sync service's conflict copy from ever being read.
- Paths and ports differ between computers.

**Impact:**
- Design 5.0.
- New setting `storage.sync.lease_stale_after_minutes`.
- New commands `cockpit sync keep` and `cockpit init --sync`.
- `cockpit serve` checks the folder before opening.
- Plugin code isn't copied between computers: a plugin missing on the other computer stops the load with the reason.

## 2026-10-12: The synced folder holds a readable layout and a machine copy

**Decided by:** Claude (design), building design 5.0; the owner can override.

**What:**
- Plugin API 0.3.14. Each record type declares a `layout` path template. The core writes those records as Markdown
  (front matter and the current long text) or YAML, with every long-text version in `.versions/`.
- Beside the readable files, the folder holds a machine copy in `.cockpit/`: the plain export, config and plugin data.
  Loading the folder reads the machine copy, never the readable files.
- Files the cockpit wrote are tracked by hash. A file whose content changed outside is never overwritten or removed.
- This first part writes the folder. The lease, handover, outside edits coming back for review, `working/`, `outputs/`
  and sources come next.

**Why:**
- Loading from readable files would make every outside edit a load-time merge. A machine copy loads exactly, and the
  readable files stay a view whose edits come back as proposals.
- Writing the whole export at once (not per changeset) keeps the folder consistent even when a write is missed.

**Impact:**
- Design 5.0.
- New setting `storage.sync.folder`.
- Core record types person, team, action, question, fact and note have layouts.
- `cockpit import` accepts a synced folder.

## 2026-10-12: Roles, and second opinions on one account

**Decided by:** Claude (design), from plugin questions; the owner can override.

**What:**
- Plugin API 0.3.13. Every task kind has a role: write, check or research. The workspace maps roles to tiers.
- A check never runs on an account whose AI runs wrote the record it checks.
- A person can accept the same account for checks. The check is then a fresh run that sees only its packet, and the
  run records that it came from the same account.
- This replaces the design's `independent: true` per task.

**Why:**
- Many people have one subscription. Without this, a check would either wait forever or quietly reuse the writer's
  account.
- Marking which kind of independence each check had keeps the choice visible.

**Impact:**
- Design 4.8 and 6.16.
- New settings `ai.roles` and `ai.tasks.<kind>.same_account`; `Run.independence`.
- The review screen shows a check's independence in the UX pass.

## 2026-10-12: Plugin API 0.3.12: who started a run, where work starts, questions from drafts

**Decided by:** Claude (design), from plugin questions; the owner can override.

**What:**
- A packet function sees who started the run. Only a note from the person counts as their words; a note from an
  outside input is now untrusted, like a scheduled one.
- A task kind can narrow the records it is offered on by field values.
- A draft may end with a few questions for the person, kept beside the version instead of inside the text.
- A person action rerun drops a choice it no longer offers.
- Temporary names for records created earlier in the same answer were not added. One op that creates both records
  covers the need. Handles would break when one op is held or refused and the other applies.

**Why:**
- Treating an outside input's note as the person's words was a trust gap.
- Work offered where it can only fail is noise.
- Questions inside a draft's prose get accepted as text by mistake.

**Impact:**
- New `TextVersion.questions` and `text.draft.questions`.
- `GET /api/task-kinds` takes `id`.
- Rerun the evaluation for the core's note-reading prompt only if inputs start carrying notes (none do today).

## 2026-10-11: Working copies: long text edited in the person's own tools

**Decided by:** Claude (design), building the plugin API; the owner can override.

**What:** Plugin API 0.3.11. A plugin may provide a working-copy format that turns a long text field into a file for
another program and reads it back, both deterministically. The core keeps the file through the file channel, records
each copy with the version and hash it went out with, and files a returned file as a pending proposal made from that
version, so accepting it is the ordinary review, three-way when the text moved on. What the format couldn't read back
is kept on the proposal, never dropped. A format must read its own untouched file back to the same text; the core
checks this at every hand-out and refuses when it fails. Watching the working folder for edits waits for the synced
folder.

**Why:** People write in their own tools; the record stays the source, a file is only a copy, and nothing in a
returned file changes the text without the person's review.

**Impact:** New core record `working_copy`; `TextVersion.unmapped` and `text.propose.unmapped`; five routes under
`/api/working-copies`. The screens to hand out and bring back come with the UX pass.

## 2026-10-11: Backups run on their own; a missing backup folder is never created

**Decided by:** project owner (nobody should have to click backup); Claude (how).

**What:** While the app runs, a background thread makes a backup whenever one is due (`storage.backups.every_hours`),
including right after the computer wakes, and tries again after `retry_minutes` when one fails. `automatic: false`
leaves only backups on request. A target folder that doesn't exist is refused with the reason, never created. Choosing
the off-device folder once stays part of setup, and the header keeps saying when none is set or the last one failed.

**Why:** Backups that depend on remembering to click don't happen. Creating a missing folder would put the "backup" on
this computer's own disk when a drive isn't connected, which looks like a backup and isn't one.

**Impact:** Design 4.15 already called for scheduled backups; this builds them. New settings `automatic` and
`retry_minutes` under `storage.backups`.

## 2026-10-11: The plugin developer guide is generated from the code and is the contract

**Decided by:** project owner (the guide before the rest of the API); Claude (how it is made).

**What:** `docs/plugin-guide.md` is written by `uv run python -m engine.plugin_guide` from docstrings, field
descriptions, `#:` comments and the host's own tables (manifest, events and their payloads, plugin settings, core
records and ops). The self-check fails when it is out of date, and tests check it covers the public API and that real
event payloads match it. Plugin authors get names only from it, never ahead of the code. `docs/plugin-api-0.x.md`
keeps only what changed per version. Core records and ops now carry a description on every field; the op descriptions
also reach the assistant in its task schemas.

**Why:** Names given ahead of the code drifted from what was built. A generated guide can't, and it grows with each
API step, so plugins integrate what exists instead of waiting for the whole API.

**Impact:** Prompts carry the fuller op descriptions; rerun the evaluation on the routine model to confirm results hold.

## 2026-10-11: Long reviews: groups, and items kept or dropped without a rerun

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** Plugin API 0.3.1. A proposal may group its choices and items under headings. Items are judgment calls the
person keeps or drops without the action running again; only kept items' ops apply, each item's ops together. Ticks
carry over a rerun to items that came back unchanged. The changeset records which items were kept and dropped. Field
names are announced only from the code and the contract document.

**Why:** A book-length file gives hundreds of judgment calls; rerunning the action for each tick would be slow and run
programs needlessly, and one long list is unreadable.

**Impact:** New setting `workspace.plugins.actions.max_items`. The review screen shows items in a later UI pass; until
then the review lists every op that applies with the ticks as they are, so nothing applies unseen.

## 2026-10-11: Person actions apply what the person reviewed, as the person

**Decided by:** Claude (design), building plugin API 0.3; the owner can override.

**What:** A plugin's person action returns one proposal (ops, files it made, previews, named choices, notes). The host
keeps it under a token for a while; flipping a choice runs the action again; applying takes exactly the kept proposal,
once, and refuses if the target changed since. It applies as the person (actor `pm`, confirmed), so person-only values
and system ops apply without a second go. Files are added by a core `file.add` op in the same changeset, so Undo takes
them back with everything else; Undo now goes newest first, so an op that refers to an earlier one's record is undone
before it. Actions can't propose ops that need evidence. Previews are pictures or plain text only. The routes are under
`/plugin-actions`, since an "action" in the core is a to-do.

**Why:** The person must approve exact content, never a recomputation of it; and an action's result must come back as
a whole with one Undo.

**Impact:** Plugin API 0.3.0. New core op `file.add` (offered only to actions), `Changeset.action`, settings under
`workspace.plugins.actions`. Manifests move to `'>=0.3,<0.4'`.

## 2026-10-11: How run_tool finds, checks and runs programs

**Decided by:** Claude (design), building plugin API 0.3; the owner can override.

**What:** Where a program is found is set per computer in `.cockpit/tools.yaml` (a path, or a command with its own
environment), falling back to the PATH; it is never synced, so two computers can differ. Each declared tool is probed
when its plugin loads: a missing or too-old required tool keeps the plugin off with the reason; a missing optional one
shows on the plugin's status and `tools.available()` says no. A probe starts with the tool's name. A run happens in a
fresh temporary folder, without a shell, with a minimal environment (PATH, locale, and HOME and temp pointed at the
folder), a timeout the plugin may lower but not raise, and capped output that says when it was cut. Limits are
`workspace.plugins.tools`. Every run is a `tool_run` record. Plugins get tools only in person actions, never in event
handlers, stage checks or validators, which must stay quick and deterministic.

**Why:** Programs differ by computer; a long or hanging program must never stall the engine, and a run must not see
the person's environment or files beyond what it was given.

**Impact:** Plugin API 0.3. New core record `tool_run`; new settings under `workspace.plugins.tools`.

## 2026-10-10: Plugin API 0.2.1: the core keeps its own rules everywhere it applies them

**Decided by:** Claude (design), from trying plugin API 0.2; the owner can override.

**What:** References inside lists are enforced like single ones. Undo skips and reports a group that would break a
unique group or leave a dangling reference. A stale `record.delete` is refused, not raised, and every op applies in its
own savepoint. Event `kinds` filters are checked at load (only on events that carry a kind, naming core or own kinds),
with one handler per event. Lookups refuse unknown fields and list values; `project=None` means "no project" and `ANY`
means no filter; matching is exact and case-sensitive. An op may label itself with `describe()`. Validators may take
`origin` as a keyword. A plugin's ops always act as the assistant, so person-only values wait for the person's release
until person actions (0.3) run as the person. Reaching outside the declared scope still disables the plugin.

**Why:** Each rule the core declares should hold on every path that writes, or a plugin can't rely on it; a typo should
fail at load, not read as silence.

**Impact:** Plugin API 0.2.1, compatible with `'>=0.2,<0.3'` manifests. `docs/plugin-api-0.x.md` updated.

## 2026-10-10: run_tool returns files the program wrote

**Decided by:** Claude (design), from a plugin question; the owner can override.

**What:** `run_tool` (plugin API 0.3) takes `collect` patterns and returns matching files from the program's working
folder as bytes, with per-file and total size caps (config defaults a call may lower, never raise); files over a cap are
listed as omitted, never cut short silently. Only regular files inside the folder match (no `..`, absolute paths or links
out); the folder is deleted afterwards; returned files are untrusted material; each run is recorded.

**Why:** Some programs report through files they write (a converter's log, a rendered page), not their output stream.

**Impact:** Part of `run_tool` in plugin API 0.3.

## 2026-10-10: Plugin API 0.3 comes with the file channel

**Decided by:** Claude (design), from a second round of plugin questions; the owner can override.

**What:** Plugin API 0.3, with the file channel and before the publishing pack, adds: uploads in the UI to the
workspace's plugin data or a project, with metadata a plugin declares per file kind, and a `file.added` event; previews
(images a plugin renders in code) on review items and questions, shown and never saved or sent; person actions
(`registrar.action`), deterministic work the person starts on a record or file that returns one proposal for one review,
with named choices the person flips and the plugin recomputes before anything applies. Later: a `web_search` adapter
capability whose fetched pages are saved as sources for evidence; strict isolation of agent-mode runs (fresh session,
empty folder with only the packet, no memory files), required before an account does independent checks; subscription
accounts counted as usage against their allowance, pausing and resuming at the reset; tool paths and probes per
computer; in 1.0, sending a built file is an export to a chosen folder or a hand-off to the person's mail app, recorded
against the file's version.

**Why:** The publishing pack needs uploads, previews and person actions itself (cover files, page proofs, importing a
manuscript), so they belong in the API it is built on.

**Impact:** Roadmap 2a: "Plugin API 0.3 with the file channel" replaces "file channel".

## 2026-10-10: Tolerate harmless answer shapes; wait out rate limits on the last account

**Decided by:** Claude (design detail), from the owner's first evaluation run on a low-cost model; the owner can override.

**What:** Evidence written as a bare string, or with extra keys beside the quote, is read as the quote; the quote is still
checked word for word against the input. When the last account in line says to slow down, the call waits and tries
again (`ai.rate_limits`: tries, longest wait); with another account available, it moves on at once. Evaluation reports
calls the account refused as "not run" and leaves them out of the score. `cockpit evaluate -w <workspace>` uses that
workspace's cases and AI setup, and `init` copies a template's cases.

**Why:** The run threw away two nearly right answers over their shape and scored four rate-limited calls as failures,
which said nothing about the model.

**Impact:** New config key `ai.rate_limits` (schema, default, description, demo values). No change to what is checked.

## 2026-10-10: Hand-in is one box with a choice of whose words are in it

**Decided by:** project owner (from trying the app); Claude wrote it up.

**What:** The two-box hand-in becomes one box and a required choice, "Whose words are these?". "Someone else's" (the default)
sends the box as pasted content, with an optional line saying what to do with it as the note. "Mine" sends the box as the
note. The API and the trust model are unchanged: other people's words always arrive as pasted (untrusted) content. Alongside:
filed notes can be found under their project, the assistant's state shows on Today with the provider's own reason, and a new
workspace shows a "Start here" card.

**Impact:** Design 7.6 (hand-in wording) and 7.8 (first run) only; no change to scope, the API or the trust rules.

**Why:** A pasted email in the first box was read as instructions with no material to work on. One box with an explicit,
defaulted choice removes the way to get that wrong without weakening it.

## 2026-10-10: Plugin API 0.2 comes before the publishing pack

**Decided by:** Claude (design), from questions raised while building a plugin against 0.1; the owner can override.

**What:** Plugin API 0.2 adds: a data level per record type (up to `restricted`, honored by packets); the change's origin
passed to validators, and person-only field values that hold an op for the person when anything else sets them; unique
fields and `find`; filtered `list` by project and field values; `Ref` fields to core and own records (checked, rewritten
on rename and merge, used for export placement); validators that see the changeset's own transaction; kind filters on
`record.changed` subscriptions; a core `record.delete` op with undo. `ext` on core records is reserved and may be
removed; plugins keep their own linked records. Later, with their features: conversational tasks (6.25), per-task packet
inclusion and reference-only records (prompt bundles), generated read-only files and front-matter layouts (synced
folder), per-project plugin settings.

**Why:** The bundled publishing pack needs most of these itself (references to projects, filtered reads, person-only
values), so building them first keeps the pack on the public API instead of special cases.

**Impact:** Roadmap 2a gains "Plugin API 0.2" before the publishing pack. `Project.parent` and `Project.language` (5.1)
land with long text, also before the pack.

## 2026-10-10: Plugin host and stages reviewed; the rules they follow

**Decided by:** Claude (design detail, from a review of the plugin host and stages work); the owner can override any of it.

**What:** The plugin host (plugin API 0.1) and stages are merged after review, with these rules:
- A plugin op writes only the plugin's own record types. Core records change only through core ops, so evidence, owner and
  tier rules always apply. `outbound` plugin ops are refused until the publisher is part of the API.
- An ordinary refusal inside a plugin op (a stale version, an invalid value) refuses that op; reaching outside the
  plugin's declared scope disables it. A disabled plugin's validators no longer block core ops.
- Notes on scheduled work (plugin requests, stage tasks) reach the assistant as untrusted data, never as the PM's words.
- Stage config naming a plugin that is turned off or failed to load stays in place and shows as unavailable; the workspace
  still starts.
- A stage move goes one stage forward, after that stage's entry checks pass, or back to any earlier stage without checks.
  An item not yet in a stage may start at any stage whose checks pass, so work under way can be brought in where it is.
- Rule-driven moves need an entry check on every stage after the first, and leave an item alone after the person moved it
  back or undid a move.
- A stage task is never queued twice for the same item and stage; moving on before the go closes it, and Undo reopens it.
  Requests that plugins queue in response to a stage move also wait for the go.
- A workspace stage entry without `stages` keeps the pack's list; every stage has a label; record types may not define
  their own `stage` field.

**Also recorded here (from the host work):** registries are per store; events publish after commit only; manifest
contributions without an extension point yet are refused; standing rules may name a deterministic `check`, and prose
rules never allow a move (a general executable rule language stays an open question).

**Why:** The review found paths where a plugin could bypass core checks, where one failing plugin stopped the workspace or
blocked core work, where rules undid the person's Undo, and where skipped stages skipped their checks.

**Impact:** `docs/plugin-api-0.x.md` describes the contract. Plugin settings layered from environment, flags and profiles
are a later change.

## 2026-10-10: The publishing pack is a stretch goal for the 2026-12-01 launch; UX is checked as we go

**Decided by:** project owner.

**What:**
- The owner's manual launch process continues. If the publishing pack is usable by about 2026-11-01, the last weeks of
  the launch can run through it alongside the manual process; if not, nothing is lost. Supersedes "the launch goes ahead
  without the tool" in the entry below.
- Build order: cost control, then the file channel, then dependencies and baselines, then the publishing pack.
- No feature is done without its screen. Before handing a feature over, Claude runs it on the fictional imprint, end to end,
  with desktop and phone screenshots checked against Part 7. The owner tries it weekly for about 15 minutes; friction goes in
  `docs/project/ux-notes.md`. Before November, Today becomes the real home, with plain empty states and a first-run guide.
- From outside reviews, adopted: a one-tap reason on Send back and Undo (wrong fact, wrong person, wrong tone, missing
  context, duplicate), feeding evaluation cases; a permission diff before a plugin is enabled or upgraded; a read-only "why
  did this happen?" trace per run (after the publishing pack). Into cost control: cached input tokens recorded and priced
  separately, cache markers as an adapter capability, and choosing a tier whose context window fits before sending.
- Not adopted: ranking Today with an AI model (Today's order stays rules), showing model names, keeping workflow state or
  keys in the browser.

**Why:** The owner's main concern once the core holds is the experience of using it; the earlier UX fixes came from a few
minutes of real use.

**Impact:** Roadmap section 2a; design 6.16 and 7 get the adopted items when each is built.

## 2026-10-09: Real use starts with the publishing pack

**Decided by:** project owner.

**What:** No real data goes into the cockpit until the publishing pack is ready; all testing is on fictional data. The
2026-10-30 go/no-go and the November freeze no longer apply, and the 2026-12-01 launch goes ahead without the tool. Build
order from now: (1) the plugin host (brief in `docs/project/next-task.md`); (2) what the publishing pack needs from the core:
stages, dependencies and baselines, the file channel, cost control; (3) the publishing pack; (4) Ask the assistant and the
remaining document features.

**Impact:** real use moves from the launch run-up to after the publishing pack; Ask the assistant moves after it.

## 2026-10-09: Build on now; the launch slice was too thin to validate

**Decided by:** project owner, after trying the launch slice.

**What:** Building continues now instead of waiting for 2026-10-31, in this order: (1) people and projects screens, so a
real workspace can be set up without editing files; (2) "Ask the assistant" for drafting on request (6.25); (3) the early
branch work (plugin host, document features, synced folder, developer guide). The launch-slice copy for the launch is commit
`49e95e7`; the owner runs that copy for real launch work if newer builds are unsettled. The settings screen for AI accounts
waits for the automatic restart (6.14), since AI settings changed from the browser need it; `cockpit ai test` covers setup
until then.

**Why:** In real use the slice could not be validated: there was no way to set up the imprint's people and projects without
editing data files, and the first thing the owner asked for (drafting an email) was not built.

**Impact:** the go/no-go on 2026-10-30 judges whatever is built by then; the November freeze applies to the copy in use, not to
development. Owner time unchanged.

## 2026-10-09: Lessons from switching AI providers

**Decided by:** project owner, from the owner's experience switching the AI provider in a private tool.

**What** (design 6.16, 6.14, 6.13, 6.3, 6.7, 3.3, 6.2):
- **No silent provider:** no default account; a tier naming a missing account is a config error; an empty tier makes its
  work wait with the reason. The first run on a new account is shown as such.
- **Smoke test on every change** (`cockpit ai test`): one live call per tier and account with each task's exact parameters;
  agent adapters also get a lock-down test; models declare the parameters they accept and the self-check rejects a tier
  whose model can't take them.
- **Errors read in one place:** only the adapter's `classify_error()` reads vendor error text; a sign-in failure becomes a
  question to the PM with the adapter's `sign_in_hint()`.
- **Changed settings or code under a running process:** no new job starts on old code with new config; the process restarts
  (the launch slice pauses new work and asks for a restart).
- **Canonical form for outside systems:** channels normalize values as the system stores them; after a publish the target is
  pulled again, and a remaining difference is an automation problem, not a draft.
- **Check the premise first:** local records before outside lookups; "can't do" must name what it checked; missing targets
  become a question to the PM; a PM's note is an instruction, and an identical answer after a send-back is refused.
- **Real gaps:** `project.add`, person-owned fields the assistant can't set, and text extractors for office files (spreadsheet
  comments, presentation tables and speaker notes), with unsupported types flagged once.
- **Probation for a new account:** its work always waits for review for `ai.probation.runs` runs per task kind, and the PM's
  Looks good and Send back count toward its score.

Classified as concepts in the core, with two settings (`ai.probation.runs`, and the per-model parameter capabilities in the
adapter) and new evaluation data (a request naming items that don't exist).

**Impact:** in the launch slice now (about a day, done): no default account and config errors for missing ones,
`cockpit ai test` with a start-up notice when untested, pausing work when settings or code change under the server, refusing an
identical answer after a send-back, and the new evaluation case. The rest is version 1 work, listed in the roadmap's open
items; where the adapter items land depends on the open milestone 10 decision. No owner time beyond running
`cockpit ai test` after adding a key.

## 2026-10-09: Long text formats divide text into units

**Decided by:** project owner, answering a question from a plugin kept in another repository.

**What:** Each `long_text` field names its format. The core ships `plain` and `markdown`; plugins can register a text format
(3.3) whose `units(text) -> spans` says where units start and end and which are atomic. Anchors, authorship, per-passage review
and lint anchors all work in units, and a core invariant refuses a draft that splits or merges an atomic unit.

**Why:** Splitting on blank lines breaks fenced blocks, multi-paragraph footnotes and poems; every pack with structured prose
would otherwise re-check this in its own validators.

**Impact:** about half a day on the early branch, with paragraph anchors. No owner time.

## 2026-10-09: Draft checks, plugin lints, project language, tools, plugin data, text events

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Paragraph anchors** (6.7): revising tasks can ask for anchored drafts; the core checks every base paragraph is accounted
  for, strips the markers before storing and keeps the paragraph map for review and authorship.
- **Lints in code** (3.3, 4.17): a lint extension point whose problems point to passages; guidance goes back per passage and
  shows in the compare view.
- **Lints on drafts** (6.16): for a draft or proposed version, a `return` lint still failing counts as "would be held", so it
  gets the escalation re-run, then stays pending with its findings; `warn` only shows.
- **Project language** (5.1, 4.6): a project can override the workspace locale for lints, spelling, dates and drafting.
- **Declared programs** (3.2, 3.5): `requires.tools`, run only through the plugin API, probed on enable and by the
  self-check; a missing optional tool turns off only its features.
- **Plugin data files** (4.12): `<workspace>/plugin-data/<plugin>/` laid over shipped data, versioned and synced.
- **Events** (3.4): `record.changed` carries kind, id, fields, version and op; a new `text.accepted` event.

**Why:** Each is needed by any pack that drafts long text or ships its own data, not by one plugin; deciding them before the
plugin API is frozen avoids a breaking change later.

**Impact:** anchors, code lints, lints on drafts and the events add about two days to the early branch (from 2026-10-31);
project language, declared programs and plugin data files land in version 1 milestone 4. No owner time.

## 2026-10-09: Working copies, a compare view, and validators as invariants

**Decided by:** project owner, answering requests from a plugin kept in another repository.

**What:**
- **Working copies** (design 5.0): a plugin can register a working-copy format (3.3) to hand a `long_text` field out as a file
  for the person's own tools and take it back deterministically; the hand-back becomes a `text.propose` held for review,
  three-way when the base moved, never merged silently.
- **`text.propose` and `text.accept`** (6.7): the person's outside work waits for review like an assistant draft; accepting
  takes per-passage choices and writes one version with authorship per passage. Plain files edited in the synced folder use
  the same path.
- **A compare view** (7.2): two-way and three-way review of `long_text` versions that any declarative panel can use.
- **Validators:** an op validator's refusal counts as an invariant failure for the fix round and escalation (6.16), so
  validators must be deterministic; judgment calls are lints.

**Why:** Long documents are written in the tools people already use; the cockpit is where they review and approve. Without a
core path, every plugin would build its own hand-back, diff and merge.

**Impact:** about three days more on the early branch (from 2026-10-31), which now runs about three and a half weeks. No owner
time. Nothing changes in the launch slice.

## 2026-10-09: Synced folder details and the manuscript contract

**Decided by:** project owner, answering questions from a plugin kept in another repository.

**What:**
- **Nested projects:** `Project` gets an optional parent; a child project's folder sits inside its parent's (a series and its
  titles, a program and its projects).
- **Sources travel:** every source (original file and extracted text) goes into its project's folder in the synced folder,
  so evidence resolves on either computer; sources above a configured data level are encrypted or left out.
- **Own files:** the cockpit records the hash of every file it writes to the folder and ignores matching files when watching;
  outputs go to each project's `outputs/` folder, and an output changed outside asks "rebuild or keep", never counts as an edit.
- **Authorship in three kinds:** written by the person, drafted by the assistant, the person's text changed by the assistant.
- **`publishing/manuscript-source@1`:** fields, events, optional task kinds and the publishing pack's behavior (design 9.7).

**Why:** Handover is only safe if the folder really holds everything; disclosure rules treat drafting and editing
differently; a finished manuscript should start a launch without retyping, from any plugin.

**Impact:** about a day more on the synced folder work in the early branch; the interface lands with the publishing pack
(milestone 8). Nothing changes in the launch slice.

## 2026-10-09: Two computers through a synced folder

**Decided by:** project owner, after a review from a plugin kept in another repository.

**What:** One workspace can be handed between computers through a file-sync folder (design 5.0, 4.15 `sync`). The database
and git history stay on each computer's local disk; the synced folder holds a complete, readable export laid out one folder
per project, written atomically after every changeset; the lease lives in the folder; diverged histories are never merged
silently; outside edits come back as changes to review. Sharing one project between different workspaces is left for later.

**Why:** Long documents need to be readable outside the cockpit and work must continue on a second computer, but file-by-file
syncing corrupts live databases and git repositories. A per-project exchange between separate installs was considered and
rejected for now: ids and people are per workspace, so a project loaded into another install would collide.

**Impact:** about four days of build time, added to the early branch after the document features (from 2026-10-31). No
owner time. Nothing changes in the launch slice.

## 2026-10-09: Plugin host and document features built early, beside the freeze

**Decided by:** project owner.

**What:** From 2026-10-31, on a separate development branch, ahead of milestones 3, 5 and 7:

1. A minimal plugin host (milestone 4): plugin API 0.x, manifests, registries, plugins working together (3.9), one example
   plugin.
2. The core features for document-heavy packs (from milestone 6): long text with versions and authorship (5.0), drafts with
   prose output (6.7), stages (6.26), cost control with estimates, a go above a set amount and budgets per task kind and per
   record (6.16), the independent second opinion (6.16), and the file channel (6.3).
3. A plugin developer guide generated from the plugin API: every extension point, op, event and interface schema, so a plugin
   kept in another repository can be built against it.

The copy the owner uses for the launch stays frozen (fixes only), whatever the go/no-go outcome.

**Why:** The owner wants to build and try plugins during the launch run-up, and plugins kept in other repositories need real,
tested contracts to build against, not a spec that changes once it meets code.

**Impact:** changes the build order only; about two weeks of build time, no owner time required (trying plugins is optional
and never ahead of the launch). The plugin API stays 0.x and may change until both bundled packs run on it.

## 2026-10-09: Plugins work together through the core

**Decided by:** project owner.

**What:** Plugins cooperate in four ways, all through the core (design 3.9): shared core records (a launch is one project
that the publishing pack and a social media pack both link to), versioned interfaces a plugin provides and others use (required or
optional), event subscriptions (now a `1.0` extension point, no longer planned), and requests for another plugin's task
kinds. Plugins still never import each other. Each pack works alone; optional interfaces add features when both are enabled.
CI tests each pack alone, each pair sharing an interface, and the core with none.

**Why:** Some work spans packs (a launch and its announcements, a won deal and its delivery); without a contract between them
the PM would retype everything and the packs would grow hidden dependencies on each other's internals.

**Impact:** adds work to version 1 milestone 4 (the plugin host; a few days of build time), before the plugin API is frozen.
Nothing changes in the launch slice.

## 2026-10-09: Core features for document-heavy packs

**Decided by:** project owner, after checking the candidate packs against the core.

**What:** Six generic features join the core design, in version 1 (milestone 6), before the plugin API is frozen:

- **Long text** (5.0): prose fields stored once per version by hash, with authorship by passage, instead of full copies in the
  ledger; needed before real data exists, because changing the ledger format later is a migration.
- **Drafts and prose output** (6.7): drafting tasks produce a `text.draft` the person reviews; drafts are not claims, so they
  are not held to the evidence rule, but checkable facts inside them are.
- **File channel** (6.3): approved content saved to a configured folder, beside the clipboard.
- **Stages** (6.26, 4.21): one mechanism for work that moves through steps, replacing per-pack stage fields; the publishing
  pack's titles use it first.
- **Independent second opinion** (6.16): a review on a different account from the one that wrote the work.
- **Cost control** (6.16, 4.8): estimates before a run, a go for anything above `budgets.confirm_above_usd` (spending money is
  irreversible, so it confirms like sending does, 7.6), budgets per task kind and per record, spend shown by pack, task kind and
  record. Drafting long documents can cost the person real money; it must never happen without their choice.

**Impact:** adds work to version 1 milestone 6 (about a week of build time; no owner time beyond reading the design). Nothing
changes in the launch slice. The sales pack stays in the Later horizon.

## 2026-10-09: Sales pack recorded as a candidate

**Decided by:** project owner.

**What:** A future sales pack is recorded in design 13.3: business-to-business sales of installed services (accounts,
opportunities, proposals, SOWs, contracts, regulatory requirements as workspace data).

**Impact:** none on the launch slice or version 1; it is in the Later horizon.

## 2026-10-09: License changed to Apache-2.0

**Decided by:** project owner.

**What:** The product is licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`, SPDX `Apache-2.0`), replacing the
AGPL-3.0 chosen earlier the same day.

**Why:** The goal is that people can use it at their companies. Many companies' open-source approval processes restrict or
ban the AGPL, while Apache-2.0 is widely approved. The owner wants attribution (the copyright notice and `NOTICE` must be
kept) and patent protection (an explicit patent grant from every contributor, ending for anyone who sues over patents in the
project); Apache-2.0 gives both. Accepted trade-off: changed versions, including ones run as a service, need not be shared.

**Impact:** none on scope or schedule. Dependencies stay compatible (all are MIT, BSD, Apache-2.0, MPL-2.0 or PSF).

## 2026-10-09: License is AGPL-3.0 (superseded the same day by Apache-2.0)

**Decided by:** project owner.

**What:** The product is licensed under the GNU Affero General Public License v3.0 only (`LICENSE`, SPDX `AGPL-3.0-only`).

**Why:** The product is meant to be run hosted as well as locally. The AGPL keeps changed versions open when they are offered
to others as a network service, not only when they are distributed.

**Impact:** none on scope or schedule. Any dependency added later must be compatible with the AGPL.

## 2026-10-09: Launch slice implementation choices

**Decided by:** built to the design; open for the project owner's review.

- **Facts are their own record kind** (`FACT-n`), not notes with a flag, so they can be looked up and undone on their own.
- **Refusal is per item:** a refused item is dropped and named; the rest of the assistant's work for that input applies.
- **Inputs longer than the limit wait for the PM** instead of being split (splitting is version 1).
- **Pasted text stays local:** a workspace's `sources/` folder is not committed; backups carry it with the database.
- **One database connection per thread,** so a reader never sees another thread's unfinished write.
- **A missing key is its own error** ("the key wasn't found"), apart from a key the vendor refused.
- **"Who is this?" and "Pick an owner" are answered on the item that waits** (What changed), not repeated in Follow-ups; a
  change with an unanswered question stays under Needs attention after Looks good.
- **Mark sent can be undone,** like every other reversible action.
- **`config/ui.yaml`** holds wording overrides, shortcut keys, the one-column width and how long toasts stay.
- **The UI uses system fonts,** loads nothing from elsewhere, and its content policy allows inline styles only for two fixed
  rules of the component library, by hash. People are picked with the browser's own list control, which works best on phones.
- **`cockpit evaluate --ai-config`** scores the PM's own accounts on the fictional cases without copying real data anywhere.
- **Browser tests** run against a test server whose stand-in AI gives each case's ideal answer, so they check the UI and the
  pipeline, not a model.

**Impact:** none on scope or schedule; all within the launch slice.

## 2026-10-09: UI review changes

**Decided by:** project owner, after a UI/UX and React review.

- **A queue, not a dashboard:** Today is the home screen, with one ranked list of things to do; panels are filtered views
  (version 1; the launch slice keeps a single column with What changed and Follow-ups).
- **One primary action per row** with the rest in a menu, and a **wording sheet** so internal terms never reach the screen.
- **Undo toasts instead of confirmations** for anything reversible; only send, publish and post confirm.
- **Keyboard first and phone friendly:** review shortcuts, one column on narrow screens, phone-critical tasks first class.
- **Edit in place before approving; evidence shown on every claim;** details by expanding rows, not tooltips; new items never
  push rows around.
- **First-run setup, real settings UX and WCAG 2.2 AA** accessibility.
- **Front-end architecture:** TanStack Query with server-sent events from the event bus, a TypeScript client generated from
  OpenAPI, React Aria Components, CSS variables for theming, a string table, sanitized rendering with real link domains, strict
  content policy, Playwright with axe.

**Impact:** launch slice gains the UI foundations (about one to two days of build time, no owner time); Today as the queue,
first run, settings UX, side-by-side diffs, virtualization and phone approval flows land in version 1 (milestone 7). Delays
nothing.

## 2026-10-09: AI review changes

**Decided by:** project owner, after an AI systems review.

Launch slice (impact: about a day of build time; owner time is reading one evaluation report; delays nothing else):
- **Evidence on claims:** ops that assert something quote the exact words from a cited source; the quote must be there
  (invariant) and should fit the target (`evidence-fit` lint). Why: with records by id, the dangerous error is a real but wrong
  target; evidence exposes it, gives an audit trail and makes injection harder.
- **Per-task op lists and small schemas, plus deterministic JSON repair, and parameters per task kind.** Why: large schemas
  degrade cheaper models and weak structured-output endpoints.
- **First evaluation set in the launch slice**, deterministic scoring, several runs per case, comparing a low-cost model with a
  stronger one. Why: the model choice should rest on evidence, especially a low-cost one.
- **Provenance everywhere; lessons from inputs are proposed until the PM accepts them;** untrusted-derived glossary meanings are
  shown as data. Why: lessons and glossary entries reach every later packet, which made them a place for injected instructions
  to persist.
- **Input cleaning and one input per call.** Why: quoted history and signatures waste tokens and create duplicate actions;
  several inputs in one call lower accuracy.

Version 1:
- **Escalation on failure** to a stronger tier on deterministic signals only.
- **Three-layer cache layout** with a frozen batch prefix and no volatile values in it.
- **Reproducible runs:** packet fingerprint, versions, parameters, model as served, upstream host; `cockpit replay`; pinned
  aggregator hosts.
- **Budget defaults lowered** to $0.25 a run, $2 a day, $30 a month, warning at 80% (applies from the launch slice).

## 2026-10-09: No code fixer in the product

**Decided by:** project owner.

**What:** The AI code fixer is removed from the product entirely, in every horizon. The product never writes or applies changes
to its own code or to a workspace's plugins. Automation problems are recorded and explained; a problem the PM wants looked at,
or a request no op can do, becomes a report (`dev.request`, now an outbound op) that the PM approves and sends to the
maintainers through a configured route (clipboard by default). Requests about other projects' code remain handoffs. The
`code-fix` tier, the `fix` task kind, `fixer` config, the merge-on-Apply machinery and proposed-fix UI are gone; the "Fix it"
button becomes "Draft a report".

**Why:** The fixer was something the owner wanted for their own development, not something people installing the product should
have: an AI changing installed code can break installations in ways their owners can't diagnose. Development happens in this
repository with the developer's own tools, outside any installation. **Impact:** removes a milestone 11 feature; simplifies
the core and the security model. Supersedes the fixer parts of the earlier entries ("Fixes merge on Apply", "The fixer changes
the workspace, not the product", "A code fix is the last resort"), whose lessons still apply to any developer tool built later.

## 2026-10-09: Launch slice uses only the OpenAI-compatible adapter

**Decided by:** project owner.

**What:** The launch slice builds one AI adapter, `openai-compatible`, which works with a key from most vendors (including
low-cost ones), aggregators and local model servers. Native adapters for vendors with their own API format move to version 1
(milestone 10). **Impact:** less work before the go/no-go; any vendor is still reachable at launch, directly or through an
aggregator. Delays nothing.

## 2026-10-09: The PM's own AI accounts, any vendor or aggregator

**Decided by:** project owner.

**What:** The AI layer is built around the PM's own accounts. Provider kinds: native vendor APIs (`anthropic`, `openai`
adapters, more as plugins), any OpenAI-compatible endpoint through one generic adapter (many vendors such as xAI, inference
hosts, local model servers), aggregators (`openrouter`, with its catalog and routing options such as refusing providers that
collect data), and command-line agents signed in as the PM. Capabilities and prices are per model, from each provider's catalog
(`models()`), with config overrides. Settings has an Add account flow (keychain for the key, Test, model list, tier choice,
data level starting at `open`, evaluation). Fallbacks may cross accounts and vendors.

**Why:** People want to use the accounts they already pay for, and aggregators reach many vendors with one key; per-adapter
capabilities can't describe an aggregator's hundreds of models. **Impact:** launch slice uses `openai-compatible` plus one native
adapter on the owner's key (no extra work: one adapter was planned, and the generic one covers most vendors); the aggregator
adapter, catalog and Add account flow land in version 1 (milestone 10). Delays nothing.

## 2026-10-09: Playbooks, ask the assistant, and project management support

**Decided by:** project owner.

- **Positioning:** a project management assistant, not a PMP replacement or a methodology tool (design 1.5).
- **Playbooks** (3.8): the core ships best-practice guidance for project support and each pack for its field, as guidance
  files, default rules, checklists, glossary seeds, lints and evaluation cases. The workspace's rules override entries by id
  (`config/playbooks.yaml`). Playbooks are scanned like code and change only by release; good workspace rules can be proposed
  upstream. Impact: core playbook first version in the launch slice (it is the guidance milestone 2's notes task needs anyway,
  organized as a playbook); publishing playbook with the publishing pack in version 1. Delays nothing.
- **Ask the assistant** (6.25): ad hoc requests answered from the records with the playbooks, so one-off PMP work doesn't need
  built-in features. Impact: version 1, should.
- **Project management support** (6.24), from the PMP review, accepted into the design now because adding them after the data
  model and screens exist would cost a migration: project issues and assumptions, optional risk fields and reviews
  (`config/raid.yaml`), one suggested escalation for long-unanswered questions, communication cadence on people, meeting
  agendas per attendee. The automation `Issue` record is renamed `Problem` so "issue" keeps its project meaning. Impact:
  version 1, could (the rename is a must, being only a name). Delays nothing in the launch slice.

## 2026-10-09: Project plan, first user and design 1.0 baseline

**Decided by:** project owner, after a project management review.

- **No employer involvement.** This is a personal project on the owner's own account, generalizing ideas from a private tool
  the owner built for their own use. No code, data or systems move between them; only ideas. Recorded as risk R9, closed.
- **First real user: the owner's literary imprint**, in a private workspace, starting with its first book launch on
  2026-12-01. The publishing pack moves to first in the build order (milestone 8); the workplace pack becomes the reference
  pack on fictional data (milestone 9); the personal-projects pack drops out of the plan (it stays as an example in Part 3).
  `demo-b` becomes a fictional small imprint.
- **Launch-safe schedule:** under 5 owner hours a week; a trimmed launch slice of milestones 1 and 2 by 2026-10-30; a go/no-go
  that day; a November freeze; the launch never depends on the tool (`docs/project/schedule.md`).
- **Dependencies and baselines join the core** (6.23): a launch is a chain of lead times, and slips need a baseline to measure
  against. Impact: version 1, must; not in the launch slice. Resetting a baseline is a system op.
- **Design 1.0 is the scope baseline.** From here, changes need a one-line impact note in this log (`docs/project/scope.md`).
  The other PMP suggestions (escalation, communications plan, agendas, risk scoring, PM issues and assumptions) wait there as
  candidate changes.

## 2026-10-09: Packet layout and read-backs, second round with the first design's author

**Decided by:** project owner, on the second-round answers from the first design's author.

- **Packets: stable first, request last.** Instructions, glossary, rules, lessons and all open items come first in a fixed
  order; the input comes last. Adapters with the `prompt_caching` capability mark the stable prefix. Why: the open-items list
  is now the largest and most repeated part of most packets.
- **Open items trimmed by size, not rule.** Full form ("[project] text (owner, due) → how to close it") for the request's own
  projects; other projects switch to compact form (id, owner, title, no closing hint) only past `open_items.compact_share` of
  the budget. Why: real counts were about 50 open actions and 10 questions for one PM with about 20 projects, about 3,000
  tokens, well within budget; the closing hint roughly doubles each line and only the request's own projects need it.
- **Read-backs show effects and overlaps:** applies to, doesn't change, overlaps with, and a dry-run count against current
  data; rules carry a structured target to compute them. A contradiction with an existing rule or setting pauses even a
  PM-typed rule until the PM picks which wins. Why: the misreadings seen in practice came from rule collisions and corrections
  aimed at the wrong place, which a restated rule wouldn't reveal but a count and an overlap would.

## 2026-10-09: Changes from the first design's author

**Decided by:** project owner, on the review by the author of the first design, who ran it daily.

- **Recovery is a tested feature.** The ledger is exported with the records; `import(export(db))` round-trips in the self-check;
  `cockpit restore --as-of` and single-record restore from the ledger. Why: restoring from git history was used in practice,
  and an export that can't be loaded back is only an archive.
- **Off-device backups in local mode**, with a Today line and header mark until one succeeds and the last backup's age always
  shown. Why: the biggest open risk of the first deployment was the whole knowledge base on one laptop.
- **Breadth waits for use:** hosted mode, packs beyond the second and social media start after the reference pack is in daily
  use.
- **The packet replaces browsing:** it always carries the glossary, active lessons, applicable rules and every open action and
  question; new `glossary.add`, `glossary.update`, `lesson.add` ops; bounded search lookups over sources and records.
- **PM-stated system ops apply at once with a read-back and Undo;** only system ops from inputs or the assistant's own initiative
  wait for a confirm. Why: the risk with the PM's own rules was misreading, which a read-back catches and a confirm doesn't.
- **Undo groups:** dependent ops are restored all or nothing; outbound can't be undone (reverting drafts, "already sent").
- **Owners are a list** (shared ownership is deliberate in some programs); team-only owners are refused and an action without a
  known person is held for "Pick an owner".
- **Lint outcomes depend on destination:** after one return, anything reaching another person is held for the PM; internal items
  warn. Missing links on questions to others, restricted content on the wrong audience and unreadable output are invariants.
- **Gaps from running it:** runner errors classified only from exit code and error stream; every waiting state shows why and until
  when; corrections checked against the data first; audiences per destination instead of open versus restricted; shared masters
  with lock checks and outside edits as changes; connectivity checked before refreshing, and failed refreshes stay stale; edits by
  our own accounts marked as ours; requests about other projects' code handed off (`config/code_owners.yaml`), restoring the
  handoff route the first design had and the restructure had dropped.

## 2026-10-09: Systems review changes

**Decided by:** project owner, after a systems design review of the whole design.

- **Database and ledger instead of files plus git as the store.** SQLite is the system of record; every applied op is written
  to an append-only ledger in the same transaction; records carry versions; ids come from sequences; jobs and the single
  running instance use leases; `data/` becomes a readable JSON export committed to git. Why: half of the storage rules
  (merge-on-save, one writer, ids never repeat, undo only if unchanged, one scheduler) were database guarantees rebuilt by hand
  on files, each learned from a failure. Undo becomes a reverse changeset with field-level conflicts instead of file restores.
  Supersedes the storage part of the 2026-10-08 technology stack entry.
- **Ids, not names.** Records refer to people, teams and projects by id; names are rendered. Why: storing "Team (Full Name)"
  strings is what required a names normalizer on every write, a name sweep and a rename reference index across every copy.
- **Op tiers and untrusted input.** Every op is data, outbound or system; system ops (rules, sources, scope, config, plugins,
  code) never apply automatically from an input. Packets mark untrusted content; lookups only reach configured sources;
  evaluation includes hostile inputs. Why: the design had no prompt-injection model, and mailbox and social plugins plus hosted
  mode make that exposure real.
- **Invariants and lints.** Firm checks always refuse and can't be lowered; fuzzy checks (wording, keyword-matched date
  questions, near-duplicates) return the changeset once, then warn, with severities in `config/checks.yaml`. Why: fuzzy checks
  that refuse produce false positives that push people to switch checks off.
- **Walking skeleton first; extension points marked 1.0, core only or planned.** The build plan reaches a version the PM uses
  in milestone 2 (paste-in, one AI task, about ten ops, the ledger, clipboard, a minimal UI). Only the extension points the two
  packs use are frozen at plugin API 1.0. Why: fifteen milestones before daily use, and sixteen hooks before any plugin, freeze
  guesses.
- **Gaps closed:** quality signals from the PM's corrections and private evaluation cases (6.20); standing rules as
  `config/rules.yaml` entries with a review that merges, retires and promotes rules into config (6.21); config versions and
  migrations, presets, basic and advanced levels, `config explain` (4.0); honest plugin security (declared reach is enforced on
  what the core hands out, not a sandbox, 12.3); one running instance per workspace; packet size budgets (6.6); retention and
  forget-a-person (4.15, 12.4).
- **The design is split into one file per part** under `docs/design/`, keeping section numbers, with a reading map in its
  README. Why: at 1,400 lines every coding session paid to read most of it.

## 2026-10-08: Every source is a setting

**Decided by:** project owner.

**What:** Where anything is looked up (a page, page tree, query, folder, feed, field name or schedule) is always configuration,
never code or default prompt text. Core and bundled plugins refer to sources by config key; default prompt templates use
template variables filled from config. Packs ship source settings as templates with placeholders that the workspace fills in,
with a Today setup line until it does. The specificity scan now also reads page titles, queries, folder paths and field names
from the fictional workspaces' config, and scans default prompt templates as well as code.

**Why:** Rules like "look on the release page" are easy to write straight into code or prompts while building for one
deployment, and each one ties the product to that deployment's tools and page layout.

## 2026-10-08: Lessons from the original deployment since the first design

**Decided by:** project owner.

Each came from a failure in the original deployment.

- **Other areas, even when named in minutes or program pages.** Domains now match owner labels as they appear on pages and in
  minutes, and the applier refuses an action whose owner label matches another domain. The owner described this as
  `other_team_owners` and `program_managers` per area; in the product they are each domain's `match.owners` and `contact`.
- **Dates are looked up, not asked.** New `config/facts.yaml` and fact resolver (6.19): an item's release comes from the
  delivery tracker or the tracker item's sprint or fix version, the release's production date from the delivery team's schedule
  page, and nothing found means TBD. The applier refuses questions for those facts, and any date question to the people listed
  in `no_questions_to`. This is a separate file rather than part of `scope.yaml` (where the owner first put it) because it is
  about where facts live, not whose area something is, and other packs need the same mechanism (publication dates, for example).
  Why: people were asked for dates that a schedule page already held, and the answers went stale.
- **Fixes merge on Apply.** A proposed fix keeps the original files and Apply runs a three-way merge, with a union merge for
  Markdown; only a real conflict stops it, and then the fix is redone automatically. Why: a whole-file staleness check made
  nearly every fix on a busy file go stale. The UI never offers an instruction it can't carry out, and a fix shows and is counted
  only on its issue card.
- **Rename is one op.** `record.rename` updates every stored reference through a reference index and keeps the page id, so the
  page is renamed in place. Why: renames done as several edits missed places and broke links.
- **A code fix is the last resort.** `dev.request` must show that no existing op fits; data that needs a new op waits with its
  fix and runs after Apply. Why: requests that ops could do became code fixes, and data changes needing a new op were refused by
  the running applier.
- **Ids never repeat.** Closed ids are retired. Why: a reused question id made old references point at the wrong question.

## 2026-10-08: Scope is enforced by the applier, with named domains and one contact each

**Decided by:** project owner.

**What:** `config/scope.yaml` gains `domains` (other areas, each with match patterns and one `contact`, usually that area's
program manager), `cross_domain` (impact-only questions, to the contact only, batched) and `unclassified` (ask the PM; never
tracked by default). The applier refuses actions owned by anyone outside the tracked area and questions to anyone outside it,
except an impact question to a domain's contact that names the tracked item it affects. A scope sweep finds existing actions and
questions that break this and files one bulk decision to the PM. A new `other-domain` triage matcher closes changes that sit
entirely in another area. One scope resolver is the only place scope is decided.

**Why:** In the original deployment, scope was advisory: the AI was told what to track but nothing stopped it. Changes on shared
pages that mixed several teams' work produced action items and detailed questions for people in other areas, who don't answer to
the workspace; that work is the program level's concern. The PM's inbox filled with follow-ups that should never have existed.
Making scope a deterministic check, with one named contact per other area and only impact questions allowed, stops the failure
at the write path instead of relying on the model.

## 2026-10-08: Local and hosted deployment from the same code; configuration first

**Decided by:** project owner.

**What:** The app runs in two modes, set by configuration: local (on the PM's computer, reachable only from it) and hosted (on a
web host the PM controls, at the PM's domain, optionally under a path such as `/admin` and optionally hidden from anyone not
signed in). Hosted mode requires real sign-in (pluggable auth providers) and refuses to start unless a set of deploy checks pass.
Packaging lives in `deploy/`: one container image plus a recipe per hosting target, starting with a tunnel to a machine the PM
owns and then a container host. Every setting can come from files, environment variables, flags or profiles, and is editable in
a Settings panel generated from the config schemas.

**Why:** The owner wants to run the product locally or on a web host, behind security checks, at a configurable hidden path, and
to change an installation without changing code. Hiding a path is not security on its own, so the deploy checks make real
sign-in, HTTPS and secret handling a condition of serving. The engine needs long-running jobs, a file system and git, so hosted
targets run it as a container or a process, not as short-lived edge functions. This replaces the earlier "local only" part of the
technology stack decision.

## 2026-10-08: Design recast as a generic core with plugins

**Decided by:** project owner.

**What:** The design is now a base for expansion, not a single-purpose tool. The core keeps only the generic loop (watch,
triage, dispatch, apply, review, send out, follow up), its safety rules and a set of extension points. The original workplace
use becomes the reference pack (design Part 9), built on the plugin API like any other pack. A second, smaller pack (personal
projects) is in the build plan to prove the extension points serve a different kind of work.

**Why:** The owner wants to use the same base for other kinds of work later (publishing support, personal projects, social
media). Building the first use as a pack, from the start, keeps workplace-specific behavior out of the core.

## 2026-10-08: Outbound content goes through channels and one approval gate

**Decided by:** project owner.

**What:** Publishing wiki pages becomes one case of a general model: records render into drafts for channels (pages, messages,
email, posts), and the publisher sends only drafts whose exact content the PM approved. Scheduled sending is allowed only for
approved content. Autonomous sending is not a goal.

**Why:** Social media and publishing plugins need outbound targets other than wiki pages. Putting every target behind the same
approval gate keeps the core promise ("the AI drafts; the human approves everything outward") as the product grows.

## 2026-10-08: Technology stack

**Decided by:** project owner.

**What:** Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff; React + TypeScript with Vite and Vitest. Plugins are Python
packages found by entry point or by folder. Storage starts as files in the workspace git repository behind a repository layer.
The app runs locally for one user.

**Why:** The design already called for Python and React. Pydantic generates JSON Schema from the same models that validate config,
records, ops and manifests, so the AI's output schema and the validator can't drift apart. Entry points give installable plugins
without a custom registry. A local, single-user app keeps the security model small until multi-user is needed.

## 2026-10-08: Changesets are JSON

**Decided by:** project owner.

**What:** Changesets are JSON documents validated against a schema generated from the op registry. Human-edited config stays
YAML.

**Why:** The design called them YAML in one place and JSON in another. AI APIs return structured output as JSON, and a generated
schema gives one source of truth.

## 2026-10-08: Naming fixes

**Decided by:** project owner.

**What:** The meeting entity is `Meeting` (was `Task`); a call to the AI provider layer is an `AiTask`. Page-specific ops became
record ops (`record.set`, `record.add`, `record.del`, `record.log`). `config/pages.yaml` became `config/render.yaml`. Tracker- and
wiki-specific triage matchers got generic names (`container-not-mapped`, `child-item`, `unknown-key`).

**Why:** "Task" meant two different things. Page and wiki names don't fit outputs like messages and posts.

## 2026-10-08: Workspaces live outside the repository

**Decided by:** project owner.

**What:** Real workspaces are separate git repositories outside this one, found by `--workspace` or `COCKPIT_WORKSPACE`. Only the
two fictional workspaces are committed, as fixtures, and `.gitignore` admits nothing else under `workspaces/`. The specificity
scan accepts `--workspace` to check code against a private workspace without copying its contents into the repository.

**Why:** Keeps real names and data out of the product repository, and lets the scan catch a deployment's specifics, not only the
demo ones.

## 2026-10-08: The fixer changes the workspace, not the product

**Decided by:** project owner.

**What:** Proposed fixes may change a workspace's config, rules, prompts, templates and private plugins. A fix that needs the core
or a bundled plugin is written as a patch and an issue for this repository.

**Why:** Applying AI-written fixes to an installed engine would make each deployment drift away from the product.

## 2026-10-08: Design document moved to `docs/`

**Decided by:** project owner.

**What:** `DESIGN.md` moved to `docs/DESIGN.md`, where `CLAUDE.md` already pointed. The copy of `CLAUDE.md` that was embedded in
the design was removed; `CLAUDE.md` is the only copy.

**Why:** One copy of each document, at the path the other documents use.

## 2026-10-10: Follow-ups: Copy marks sent, and sent items have their own view

**Decided by:** project owner.

**What:** Copy records the message as sent at once, with an Undo toast; there is no separate Mark sent step. Follow-ups has a
filter, "To send" (default) and "Waiting on them". A person's card under To send lists only what is still to send, with the
message and Copy. Items already sent or told appear only under Waiting on them, grouped by person, one line each ("sent
<date> (N days)") with their own step (They finished it, Record reply). The PM's own decisions stay under To send.

**Why:** Items already sent sat among items still to send and looked unsent; a second click after Copy was easy to forget.

**Impact:** Design 7.5 and the wording sheet. Each question in the follow-ups response carries its sent date. No change to
scope or to the ops.
