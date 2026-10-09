# PM Cockpit: product design for a generic, extensible build

A clean-room design, written from scratch from experience running an AI-assisted PM workflow. It contains no code, names,
company systems or data from any real deployment. All examples are fictional. The repository's `CLAUDE.md` is the short
version for coding agents; `CHANGES.md` in this folder summarizes how this design differs from the first version.

**Two rules above all others:**

1. **The core is generic.** Everything about a particular organization or person (its people, teams, programs, systems, URLs,
   sources, routing, vocabulary, wording rules, schedules) lives in configuration and data, never in code, prompts or comments.
2. **The core is a base, not the whole product.** It provides the loop, the safety rules and the extension points. Anything that
   belongs to one kind of work (a workplace status-page routine, a publishing calendar, a social media account) is a plugin.

**Where this design came from.** It grew out of one use: a program manager supporting a technical leader at a large
organization, with status on wiki pages and work in an issue tracker. That use is kept, fully specified, as the **reference
pack** (Part 9): the most proven pack, built on fictional data, and the main test that the core is complete. The first pack in
real use is **publishing support** for a small imprint (9.6). Other uses (personal projects, social media) are plugins on the
same core (3.7).

**Version.** Design 1.0, the scope baseline as of 2026-10-09. Changes from here go through the change control in
`docs/project/scope.md`.

## Parts

Section numbers are stable: "6.18" is section 18 of Part 6, in `06-engine.md`.

| Part | File | What it covers |
|---|---|---|
| 1 | [01-product.md](01-product.md) | What the product is, the core loop, what's core and what's a plugin, non-goals |
| 2 | [02-architecture.md](02-architecture.md) | Layers, repository and workspace layout, where things go, technology choices |
| 3 | [03-plugins.md](03-plugins.md) | Plugin kinds, manifest, extension points, rules for plugins, lifecycle, worked examples, playbooks, plugins working together |
| 4 | [04-configuration.md](04-configuration.md) | Configuration principles and every config file |
| 5 | [05-data.md](05-data.md) | Storage model (database, ledger, ids), entities, storage rules |
| 6 | [06-engine.md](06-engine.md) | Every core component: plugin host, connectors, channels, applier, questions, scope, facts, AI layer, quality signals |
| 7 | [07-ui.md](07-ui.md) | UI principles, shell, Today, panels, What changed, Waiting to go out, Follow-ups, first run, settings, accessibility, front-end architecture |
| 8 | [08-product-rules.md](08-product-rules.md) | Lessons as product rules, each with where it is enforced |
| 9 | [09-reference-pack.md](09-reference-pack.md) | The packs: workplace PM (reference) and publishing (first in use) |
| 10 | [10-guardrails.md](10-guardrails.md) | Keeping specifics out of code: the boundary, scans, process, review checklist |
| 11 | [11-deployment.md](11-deployment.md) | Local and hosted modes, base path, sign-in, deploy checks, packaging |
| 12 | [12-security.md](12-security.md) | Security and privacy, including untrusted input and op tiers |
| 13 | [13-build-plan.md](13-build-plan.md) | Milestones, starting with a walking skeleton |

## What to read for a task

| Task | Read |
|---|---|
| Any change | this page, Parts 1, 2 and 10 |
| Engine work | Parts 4, 5 and the Part 6 section for the component |
| A plugin or pack | Part 3, then Part 9 as the worked example |
| Config keys | Part 4 (4.0 first) |
| UI | Part 7 (7.0 first), and 6.x for the data a panel shows |
| AI tasks, prompts, providers | 6.6, 6.7, 6.16, Part 12 |
| Deployment, sign-in | Parts 11 and 12 |
| Planning | Part 13 |

## Terms

| Term | Meaning |
|---|---|
| PM | The person the cockpit works for: whoever runs the projects in a workspace (a program manager, an author, anyone) |
| Workspace | One deployment: one PM's config, data, sources, prompts and private plugins |
| Record | A stored thing the cockpit tracks: a project, a person, an action, a question, or a plugin's own type (a manuscript, a post) |
| Id | A record's permanent identity. Records refer to each other by id; names are only displayed (5.1) |
| Source | An input, saved as text: a page version, a tracker item, a pasted note, an email, a file |
| Change | A detected difference in a source that may need work |
| Request | A unit of work queued for the assistant (process a change, record an answer, write an update) |
| Changeset | The assistant's only output: a structured list of typed ops, validated and applied by the applier |
| Op | One typed operation in a changeset (`record.set`, `action.add`, `question.add`, or a plugin's own) |
| Tier | An op's risk level: data, outbound or system (6.7). System ops never apply automatically from an outside input |
| Ledger | The append-only log of every applied op with before and after values; the basis for history and undo (5.0) |
| Invariant / lint | A check that always refuses a changeset / a check that returns it once for a fix, then warns (6.7) |
| Draft | Content waiting to go out through a channel: a page version, a message, a post |
| Audience | Who can see a destination: open, or a named group. A restricted source names the audiences allowed to see it (4.1) |
| Read-back | How the assistant restates a rule or setting the PM just gave, with what it changed and Undo (6.7) |
| Playbook | Built-in practice for a kind of work (core: project support; each pack: its field), switchable entry by entry (3.8) |
| Handoff | A request about code another project owns, drafted for that project's owner instead of fixed here (4.18) |
| Connector | A plugin component that brings inputs in (a wiki, a tracker, a mailbox, a feed) |
| Channel | A plugin component that takes approved drafts out (a wiki page, an email, a blog, a social network) |
| Plugin | A package that registers components at the core's extension points |
| Pack | A plugin that bundles record types, ops, templates, prompts, panels and default config for one kind of work |
| AI task | One call to the AI provider layer: a task kind, a packet, an output schema (6.16) |
| Packet | Everything an AI task is given, each part marked trusted or untrusted (6.6, 12.2) |
| Meeting | A meeting the PM sets up or runs, with attendees and notes |

## Ground rules for this build

- Built from this description only. No code, files or data copied from any real deployment.
- Fictional demo data only.
- Check your employer's policy on outside projects before building, and again before selling or publishing.
