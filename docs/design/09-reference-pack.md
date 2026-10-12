# Part 9. Packs: workplace PM (reference), publishing, project management and writing

Packs are **add-ons in their own repositories**, not bundled with the core (decisions, 2026-10-10 "The core is complete on
its own", 2026-10-11 "Packs are found on an Add-ons screen"). The core is a complete product without them; this repository
holds the core, the define-your-own kit, its templates and the example plugin. A person finds a pack on the Add-ons screen
(3.11) and installs it from there (7.15). Each pack works alone and uses another pack only through the core's interfaces
(3.9). The packs prove that the plugin API is enough for very different kinds of work.

This part keeps two designs in full (the first two below) and adds two short entries:
- the **workplace PM** pack (9.1 to 9.5), the use this design came from: the most proven design and the main test that the
  core is complete;
- the **publishing** pack (9.6 to 9.9), for a small imprint bringing titles to launch;
- the **project management** pack (9.10), decided 2026-10-12;
- a **writing** pack (9.11).

Everything here is generic; an organization's specifics live in a workspace.

| Pack | Where it lives | State (2026-10-12) |
|---|---|---|
| Workplace PM (9.1 to 9.5) | A private add-on in its own repository | Not started. The design is kept as the worked example; it is not on the roadmap to 1.0 |
| Publishing (9.6 to 9.9) | A private add-on in its own repository | Designed; not started. Phase C of the roadmap (C3), after the project management pack |
| Project management (9.10) | A private add-on in its own repository, to be created | Decided; not started. Phase C of the roadmap (C2) |
| Writing (9.11) | A private add-on in its own repository | Built far enough to load and register on the current plugin API; it cannot yet be installed from the screen (phase A2), and its review is phase C1 |

## 9.1 The use

A PM supports a busy leader (an architect, a director) who owns a portfolio of projects. Status lives on wiki pages, work lives
in an issue tracker, decisions happen in meetings, chats and email. The leader reads published status pages and dashboards; key
players receive questions and action items as paste-ready messages.

## 9.2 What it needs from other plugins

Connectors of kind wiki (pages and trees, history, recent edits by person), issue tracker (queries, items with changelog),
release tracker (optional) and shared files; a channel of kind wiki page (versioned, pull-edits). The pack depends on these
kinds, not on one vendor: a wiki vendor's connector and channel live in their own plugin.

## 9.3 What it registers

- **Config** (`config/plugins/workplace-pm.yaml`): `leader` (full name, account usernames on each connector, to find their recent
  work), the grouping label ("Program"), sub-groups, `publish` targets (summary page, project pages, archive) and the dashboard
  readers to keep compatible with.
- **Record fields** on `Project` (`ext.workplace-pm`): sub-program, delivery team, delivery lead, tracker keys; risks gain
  `owner_team`.
- **Renderers and templates:** the summary page (rows roll up from project pages), project pages, the archive.
- **Triage defaults:** the `container-not-mapped`, `owner-not-ours` and `child-item` rules pre-filled for page trees and
  tracker sub-tasks.
- **Fact defaults** (a starting `config/facts.yaml`): `ship_release` (a delivery tracker's release field, else the tracker
  item's sprint or fix version field) and `production_date` (a schedule page per delivery team); no release yet means TBD.
  The pack ships these as a template with placeholders; the workspace fills in which connector, which field names and which
  pages. Until it does, a Today line says "Set up: choose the schedule page for each delivery team", and the kinds behave as
  `missing: ask-pm`. Nothing in the pack's code names a field or a page.
- **Routing defaults:** program-date questions observed, not asked; dates never asked of release or delivery people.
- **AI task kinds:** `workplace-pm/checkup-goals` and `workplace-pm/status-update` with their prompt templates.
- **Panels:** portfolio health by program, milestones to check.
- **Today lines:** dashboard drafts waiting, milestones to check this week.
- **Workspace defaults it suggests:** `owner_format: "{team} ({full_name})"`.

## 9.4 Fictional demo setup

Designed, not built. The pack carries a fictional demo of its own, with a fake wiki and a fake tracker backed by fixtures,
for "Try it in the demo" on the Add-ons screen (`cockpit demo --plugin`, 3.11). The repository's two fictional workspaces do
not enable it today; they run the example plugin and the kit.

## 9.5 Pack-specific rules

| Rule | Enforced by |
|---|---|
| Name teams, not individuals, as owners of risks (actions are different: actions name a person) | pack op validator on `risk.add` |
| Owners are "Team (Full Name)" | suggested `owner_format`, rendered from ids |
| Don't chase program milestones run by other PMs or things the leader doesn't own | pack's default `scope.yaml` entries |
| The leader shouldn't have to confirm routine updates | routing defaults |

## 9.6 Publishing: the use

A small imprint or independent author brings a title to launch: a production chain with lead times (final manuscript, edit,
proofread, cover, interior, proof copy, approval, distribution listing, preorders, advance copies, launch), many outside
contributors (editor, proofreader, cover designer, typesetter, printer, distributor, reviewers, venues, media) and a stream of
promotion copy. The PM is the publisher; contributors never use the tool and get paste-ready messages.

## 9.7 Publishing: what it registers

- **Record type** `publishing/title`: working title, formats, stage (core stages, 6.26, with the pack's defaults in
  `config/stages.yaml`), launch date (with a baseline when the project management pack is on, 9.10), identifier status,
  contributors (person ids by role).
- **Launch plan template** (`config/plugins/publishing.yaml`): the milestones of a launch, each with an offset from the launch
  date (its lead time) and the milestones it depends on. When the project management pack is on, the launch plan's milestones
  go into its schedule through `pm/schedule@1`; alone, the plan is a plain list of milestones. The pack ships a starting template the PM edits; every milestone name,
  lead time and dependency is config. `publishing/plan-from-template` creates a title's milestones and dependencies from it.
- **Scope defaults:** the imprint's own work and its contracted contributors are the tracked area; a vendor's internal process
  (a printer's queue, a distributor's listing pipeline) is a domain with the account contact as its one contact (4.4).
- **Fact defaults:** placeholders for dates a vendor publishes (a distributor's listing date, a printer's ship date); none
  found means TBD (6.19).
- **AI task kinds:** `publishing/contributor-message` (read an email or note from a contributor or vendor: updates, actions,
  date changes, questions) and `publishing/promo-draft` (a social post, newsletter section or announcement, drafted to the
  clipboard channel for the PM to approve and paste).
- **Interface it defines for others to provide** (3.9): `publishing/manuscript-source@1`, so any plugin, connector or
  installed or private plugin that produces finished manuscripts can start a launch:
  - **Fields:** project; title, subtitle, series and number in series, language; contributors (person ids with roles);
    word count; editions per format, each with its file, version, content hash and approval date, plus page count and
    trim size for print; front and back matter; description and short blurb, when the provider has marked them ready;
    data level; an authorship breakdown in the three kinds of 5.0 (written by a person, drafted by the assistant, the
    person's text changed by the assistant).
  - **Events:** `approved` (a first or replacement version) and `withdrawn` (the manuscript went back into revision).
  - **Optional task kinds a provider may offer:** short blurb, long description, back-cover copy, contributor bio.
  - **What the pack does with it:** offers "Start a launch for this title?" on Today; on a new approved version, flags the
    milestones that depend on the files; when page count or trim size changes, asks the PM, since it changes the spine
    width and the print price; fills the platforms' AI-disclosure answers from the authorship breakdown, for the PM to
    check; on `withdrawn`, marks the launch milestones that depend on the files as at risk.
- **Today lines:** launch countdown, milestones due within the configured window, and, with the project management pack,
  dependencies at risk.
- **Panels:** launch timeline (with the project management pack: baseline against current dates, with dependencies),
  contributors by role.
- **Listing sheet and prices:** a listing sheet per platform and a price calculator, both from dated platform data in
  config, never in code (roadmap C3).
- **Channels:** clipboard only at first; email, newsletter and social channels are later plugins.
- **Playbook** (3.8): launch practice for a small imprint: typical lead times and the order of production steps (as defaults
  for the launch template), what to confirm with each kind of contributor and when, how to write to editors, reviewers and
  venues, promotion timing before and after launch, a publishing glossary (galley, ARC, ISBN, print proof, trim size, metadata)
  and evaluation cases on fictional titles. No retailer, distributor or service names except in a vendor's own plugin.
- **RAID preset:** risks, issues and dependencies on; assumptions off (4.20).

## 9.8 Publishing: not in the first version

Integrations with distributors, retailers or printers; sales and royalty data; social posting; a public site. Each is a later
connector or channel.

## 9.9 Publishing: fictional demo setup

The two fictional workspaces are **test fixtures and the sandbox**, never a person's starting point; a real workspace starts
from `cockpit init` with no template (decisions, 2026-10-12). `demo-b` is a fictional small imprint. Today it holds people,
projects, evaluation cases and a content-calendar kit configuration; it has no title record or launch plan, because the pack
does not exist yet. The pack will carry its own demo (one title, a launch plan made from the template, contributors in each
role and fixture emails from them), as every pack does (3.11). The owner's real imprint runs in a private workspace outside
this repository.

## 9.10 Project management pack

An AI project manager for any project: it knows what is being done, builds schedules and tracks the action items (decisions,
2026-10-12 "A project management pack"). A private add-on in its own repository; not started (roadmap C2). It is distinct from
the workplace pack (9.1 to 9.5), which is about wiki pages and trackers at a workplace.
- **The core keeps** what every kind of work needs: actions with owners, questions, follow-ups, decisions and Today.
- **The pack adds planning,** through ops and core records:
  - the plan: goals, phases, deliverables and milestones;
  - the schedule: durations, dependencies, a critical path, dates worked out from the dependencies, baselines and slips
    against them (only the person rebaselines);
  - plans and schedules drafted by the assistant from a brief, notes or another pack's milestones, for the person to approve
    like any change;
  - daily at-risk lines on Today, with the action items behind them, and a weekly status report drafted to send;
  - RAID: risks, issues, assumptions and decisions, with owners and review dates.
- **An interface for other packs:** `pm/schedule@1`, through which the writing and publishing packs put their milestones
  into one schedule (3.9). Each pack still works alone.
- **What moves out of the core:** dependencies and baselines (6.23) and RAID with its reviews, escalation suggestions,
  cadence and meeting agendas (6.24) are this pack's work, not the core's.

## 9.11 Writing pack

A writing pack takes a writer from an idea, or from a finished manuscript, to a finished book, and hands the finished book to
the publishing pack through `publishing/manuscript-source@1` (9.7). A private add-on in its own repository; its review is
phase C1 of the roadmap.

