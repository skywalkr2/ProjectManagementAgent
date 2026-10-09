# Part 9. Reference pack: workplace PM

The use this design came from, built as a pack (`plugins/workplace-pm/`) on the core. It is the first pack built and the main
test that the core is complete. Everything here is generic for workplace status reporting; the organization's specifics still
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
