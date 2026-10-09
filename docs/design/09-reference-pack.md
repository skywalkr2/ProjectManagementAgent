# Part 9. Packs: workplace PM (reference) and publishing

Two bundled packs. The **workplace PM** pack (9.1 to 9.5) is the use this design came from, built as a pack
(`plugins/workplace-pm/`) on fictional data: the most proven design and the main test that the core is complete. The
**publishing** pack (9.6 to 9.9) is the first pack in real use, for a small imprint bringing titles to launch. Everything here is generic for workplace status reporting; the organization's specifics still
live in a workspace.

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

Both fictional workspaces enable the pack with different organizations, programs, people and vocabulary, a fake wiki and a fake
tracker backed by fixtures.

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
  `config/stages.yaml`), launch date (with baseline, 6.23), identifier status,
  contributors (person ids by role).
- **Launch plan template** (`config/plugins/publishing.yaml`): the milestones of a launch, each with an offset from the launch
  date (its lead time) and the milestones it depends on. The pack ships a starting template the PM edits; every milestone name,
  lead time and dependency is config. `publishing/plan-from-template` creates a title's milestones and dependencies from it.
- **Scope defaults:** the imprint's own work and its contracted contributors are the tracked area; a vendor's internal process
  (a printer's queue, a distributor's listing pipeline) is a domain with the account contact as its one contact (4.4).
- **Fact defaults:** placeholders for dates a vendor publishes (a distributor's listing date, a printer's ship date); none
  found means TBD (6.19).
- **AI task kinds:** `publishing/contributor-message` (read an email or note from a contributor or vendor: updates, actions,
  date changes, questions) and `publishing/promo-draft` (a social post, newsletter section or announcement, drafted to the
  clipboard channel for the PM to approve and paste).
- **Today lines:** launch countdown, milestones due within the configured window, dependencies at risk (6.23).
- **Panels:** launch timeline (baseline against current dates, with dependencies), contributors by role.
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

`demo-b` is a fictional small imprint with one title, a launch plan made from the template, contributors in each role, and
fixture emails from them. The owner's real imprint runs in a private workspace outside this repository.

