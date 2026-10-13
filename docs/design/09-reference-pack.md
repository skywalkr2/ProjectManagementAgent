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
| Writing (9.11) | A private add-on in its own repository | Loads and registers on the current plugin API, proved by its own repository's tests; it cannot yet be installed from the screen (phase A2), and its review is phase C1 |

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

## 9.5a What the running use needed (the first design author's review)

*Designed, not yet built; not on the roadmap to 1.0* (decisions, 2026-10-12 "The workplace pack review"). 9.1 to 9.5 were
thin for "the most proven design". Much of what made the running version work moved into the core (scope 6.18, facts 6.19,
names 6.11, learning 6.22). These twelve points are what only a workplace PM needs. Each names the core part it builds on.

1. **Roles, shipped as routing templates.** The real use has five roles, not one leader:
   - **the leader** owns the portfolio and decides priority and capacity;
   - **a delivery lead** is the first stop for delivery questions on the projects assigned to them, but doesn't prioritize
     or decide what starts, and is never asked for dates;
   - **program managers** own program dates and decide new scope, and get one impact question at most;
   - **an architect per item** answers design questions;
   - **the PM** owns the meetings and the paperwork.

   The pack ships them as routing-entry templates per role ("first stop for…", "never ask about…", "decides…", 6.22). Setup
   fills them in by naming who holds each role. That keeps the first month's questions from going to the wrong person.
2. **Two kinds of dates, by owner.** Program dates (readiness, launch) come from the program manager. Delivery dates (which
   release, which sprint) come from the delivery lead's sources. One never overrides the other: a TBD on one side doesn't
   erase the other's date. When the two disagree on the same kind of date, it is a private discrepancy to ask about (8.1).
   Neither is picked, and it never goes on a published page. Built on fact kinds with an owner (6.19).
3. **A status rubric as data** (pack config, not code):
   - phases: intake, discovery, design, design review, then handoff, in delivery, live;
   - the target is go-live, as a date or a quarter, never a sentence (8.1), and the handoff is a milestone;
   - status labels map to the dashboard reader's colors, and any other label is refused (a value list, 5.4);
   - flags: a row gone stale, a target passed, done but not archived.
4. **Leader-owned fields and the baseline state.**
   - Priority and capacity are person-owned fields, filled only from the leader (8.8).
   - A project is **baselined** once its page is built from real input. Until then its values are blank or TBD, never
     placeholders, and the weekly check-up asks the leader only about baselined projects.
   - A project whose place on the list is itself in question stays a held draft: never published, and asked about first.
5. **Project page sections:**
   - a snapshot (the row's source);
   - **key players:** name, role, team and *why they matter to our area* (the part people actually read);
   - open issues and risks (teams own risks; who raised each is recorded);
   - action items (people own them);
   - decisions;
   - milestones;
   - links;
   - an update log that every change adds to (an invariant).
6. **The baseline flow, the first week** (the pack's own task kind, `workplace-pm/baseline`). Starting a workplace
   workspace isn't an empty form:
   - find the leader's recent work in the wiki (pages they created or edited);
   - map each list row to its documents;
   - list the work that isn't on the list, and the rows with no source;
   - propose archive candidates: things that look live, or dropped;
   - produce one baseline ask for the leader, covering priorities and capacity, unsourced rows, archive candidates and a
     few design questions.

   The leader's answers fill the person-owned fields and settle the held drafts. By hand, that took most of the running
   version's first week.
7. **Key-player exploration.** A weekly job scans the key players' recent wiki activity for work that touches the tracked
   area before anyone mentions it. It keeps a dismiss list, so an irrelevant page doesn't come back, and offers a way to
   resolve a person's account name when the lookup can't.
8. **Preview through the dashboard's own reader.** The summary page is read by a dashboard with its own parser:
   - fixed column names;
   - a heading structure that can't mix direct rows and sub-groups;
   - compact targets.

   The review screen shows the page as that reader will see it, using its parser (a renderer's reader-preview hook, 3.3), and
   says "nothing the dashboard shows" when that's true. "Dashboard readers to keep compatible with" is the setting; the
   preview is what makes it safe.
9. **The weekly check-up for this use** (rules in the pack's playbook, 3.8):
   - the leader's message asks only about edits the cockpit doesn't already process (unwatched pages, their own design
     edits);
   - delivery dates go to the PM's list, not to the leader;
   - suggested weekly goals are replaced by three to five real ones.
10. **The lens: the pack's default scope** (6.18). The tracked area is a domain, followed from design through deployment:
    what's built, where it ships and what it needs. Deployment schedules belong to someone else: their dates are reported,
    never chased. Other domains appear only when ours owes them input or they could move the overall timeline.
11. **Ship release, not dev sprint** (the `ship_release` fact default, 6.19):
    - items are often pulled into an earlier release, so the release field wins over any sprint number quoted on a page;
    - an item pointing at a release already in production but not done is usually a late patch, so it is flagged to check,
      never dated.
12. **Pages a group edits.** Some outputs are tables where the team edits certain columns (analysis, notes) and the tool
    owns the rest; those are pulled back before every render (6.12). Some pages are locked to a named group, with a banner,
    and may carry that group's restricted material (audiences, 4.1). The pack says which of its outputs use each, so
    per-column ownership is designed for, not discovered.

**Its fictional demo comes first.** The fictional workplace workspace (`workspaces/demo-a`) grows into a busy portfolio:
- about 20 projects and 50 open actions;
- near-namesake items;
- the roles above;
- a fake dashboard reader.

It is built in phase L-core as the golden set's busy fixture (6.16), long before the pack, which later uses it as its
demo (9.4).

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

