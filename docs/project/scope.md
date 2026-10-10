# Scope baseline and change control

Design 1.0 (`docs/design/`, 2026-10-09) is the scope baseline. This page says what is in each horizon and how changes are made.

## Horizons

| Horizon | What it is | When |
|---|---|---|
| **Launch slice** | The smallest useful part of milestones 1 and 2 (`schedule.md`) | by the 2026-10-30 go/no-go |
| **Version 1** | The core complete on its own: the define-your-own kit with templates, guided install and setup, settings screens, agent accounts, ask the assistant, watchers and lookups, the plugin API (decisions, 2026-10-10). Industry packs are add-ons in their own repositories | after the launch |
| **Later** | Milestones 10 onward and everything in "After the base" (design 13.2) | once the publishing pack is in steady daily use |

## Must, should, could, won't

| Item | Launch slice | Version 1 | Design |
|---|---|---|---|
| Database, ledger, ids, export and import round trip | must | must | 5.0 |
| Records by id, names resolved at the boundary | must | must | 5.1, 6.11 |
| Op tiers, invariants and lints | must | must | 6.7 |
| Paste-in with "your note" and "pasted content" | must | must | 12.2 |
| One AI task kind (notes and messages); the `openai-compatible` adapter on the owner's own key | must | must | 6.16 |
| Actions, questions, follow-ups by person, Copy and Mark sent | must | must | 6.8, 6.9, 7.5 |
| UI foundations: responsive single column, one primary action, wording sheet, undo toasts, edit in place, evidence line, keyboard shortcuts, accessible components, generated API client, live updates, safe rendering, Playwright with axe | must | must | Part 7 |
| Today as the home queue, first-run setup, settings form UX, side-by-side diffs, virtualized lists, phone approval flows, installable web app | won't | must | 7.7 to 7.9 |
| Clipboard channel | must | must | 6.3 |
| Undo from the ledger | must | must | 6.7 |
| Evidence on claims, per-task op lists, JSON repair | must | must | 6.7 |
| Input cleaning, one input per call, provenance on writes, proposed lessons | must | must | 6.6, 6.22, 12.2 |
| First evaluation set and model comparison | must | must | 6.16 |
| Escalation on failure, cache layers, reproducible runs, budget defaults | won't (budget defaults: must) | must | 6.16, 4.8 |
| Off-device backup with nag | must | must | 4.15 |
| Waiting states that say why and until when | should | must | 7.6 |
| Scope resolver and fact lookups | could | must | 6.18, 6.19 |
| Dependencies and baselines | won't | must | 6.23 |
| Publishing pack (own private repository, decisions 2026-10-10) | won't | add-on | 9.6 to 9.9 |
| Plugin host and plugin API 0.x | won't | must | Part 3 |
| Read-backs, standing rules review | won't | should | 6.7, 6.21 |
| Glossary, lessons, search lookups | won't | should | 6.22 |
| Quality panel and private evaluation cases | won't (signals recorded only) | should | 6.20 |
| Settings panel generated from schemas | won't | should | 4.0 |
| Workplace pack and its connectors (private add-on, decisions 2026-10-10) | won't | add-on | 9.1 to 9.5 |
| Core playbook, first version (the guidance the notes task needs) | must | must | 3.8 |
| Publishing playbook | won't | must | 3.8, 9.7 |
| Ask the assistant | won't | should | 6.25 |
| Issues and assumptions, risk fields and reviews (`raid.yaml`) | won't | could | 6.24, 4.20 |
| Escalation suggestions, communications cadence, meeting agendas | won't | could | 6.24 |
| Automation `Issue` renamed `Problem` | n/a (naming) | must | 5.1 |
| Native adapters (vendors with their own API format), aggregator adapter with catalog and routing options, Add account flow, models from provider catalogs | won't | must | 6.16 |
| Hosted mode, sign-in providers | won't | won't | Part 11 |
| Social, email and newsletter channels | won't | won't | 3.7 |
| Sales pack (accounts, opportunities, proposals, SOWs, contracts, regulatory data per jurisdiction) | won't | won't | 13.3 |
| Plugins working together: interfaces, event subscriptions, requests for another plugin's work, shared core records | won't | must | 3.9 |
| Long text fields with versions and authorship | won't | must | 5.0 |
| Working copies, `text.propose` and `text.accept`, compare view (two-way and three-way) | won't | must | 5.0, 6.7, 7.2 |
| Two computers through a synced folder (readable export by project, lease in the folder) | won't | must | 5.0, 4.15 |
| Drafts with prose output (`text.draft`), not held to the evidence rule but marked unreviewed | won't | must | 6.7 |
| File channel (approved content saved to a configured folder) | won't | must | 6.3 |
| Stages for record types, with entry checks and the person's go (publishing titles first) | won't | must | 6.26, 4.21 |
| Independent second opinion (a review on a different account) | won't | should | 6.16 |
| Cost control: estimate before a run, a go above a configured amount, budgets per task kind and per record, spend shown | won't (budget defaults only) | must | 6.16, 4.8 |

## Change control

From design 1.0 on, a change to scope or design is accepted only with a one-line impact note in `docs/decisions.md`: what it
adds, which horizon it lands in, and what it delays. During the November freeze (`schedule.md`) only fixes are accepted.

## Candidate changes waiting for a decision

None. The PMP review's product suggestions were accepted into design 1.0 on 2026-10-09 (`docs/decisions.md`), built in
version 1 as listed above.
