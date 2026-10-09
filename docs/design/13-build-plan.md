# Part 13. Build plan

Two principles. **Use it early:** the PM works with a thin end-to-end version within the first weeks, and every later
milestone is judged against real use (with the PM's corrections as the measure, 6.20). **Build the safety first:** the ledger,
the tiers and the invariants are in the first usable version, because they are much harder to add once data and habits exist.

**Earn the breadth:** packs beyond the first two, hosted mode and social media are a lot of product for a tool whose first
deployment has one user. Milestones 12 onward (and every pack after the second) start only once the publishing pack has been in
daily use and its quality signals (6.20) are steady.

**Dates and the launch slice.** The calendar, the go/no-go and the smaller "launch slice" of milestones 1 and 2 (what is built
before the first real deadline and what is deferred) are in `docs/project/schedule.md`. This part lists the milestones in
order; the project plan says when.

Each milestone ends with tests passing against both fictional workspaces, the core passing alone, and the scans green.

## 13.1 Milestones

1. **Skeleton and guardrails.** Repository layout (2.2); tooling (uv, ruff, pytest, Vite, Vitest); the database with record
   versions, the ledger, id sequences, the instance lease, the readable export and the export → import round trip with point-in-time restore (5.0); config schemas with versions, layers,
   profiles and `cockpit config show` / `explain` (4.0); the scans and the self-check (10.2); both fictional workspaces as
   importable fixtures; `cockpit serve` in local mode with the install token and base-path support.

2. **Walking skeleton (the first version the PM uses).** One path through the whole loop, on real work:
   - paste-in with "your note" and "pasted content" (12.2);
   - the core playbook, first version: the guidance the `notes` task needs, organized as a playbook from the start (3.8);
   - one AI task kind (`notes`) through the provider layer with the stub adapter and the `openai-compatible` adapter, which
     works with a key from most vendors, aggregators and local model servers, using the PM's own key;
   - input cleaning (quoted history, signatures) and one input per call;
   - per-task op lists with small generated schemas, JSON repair, and evidence on every claim;
   - provenance on every write, so untrusted-derived content stays marked;
   - the first evaluation set (10 to 20 fictional cases with hostile inputs, deterministic scoring, several runs each), run on a
     low-cost model and a stronger one;
   - the applier with tiers, invariants and lints for about ten ops: `source`, `note`, `fact`, `record.set`, `record.log`,
     `action.add`, `action.close`, `question.add`, `question.done`, `person.add`;
   - names resolved to ids, with routing decisions for unknown people (6.11); owners as a list, and held actions waiting for
     "Pick an owner";
   - read-backs for rules the PM states, and undo from the ledger with op groups;
   - the glossary in every packet, with `glossary.add` and `lesson.add`, and every open action and question in the packet;
   - waiting states that say why and until when;
   - the clipboard channel;
   - backups to a target off the computer, with the Today and header nag until one has succeeded (4.15);
   - a minimal UI: What changed with the assistant's work nested, and Follow-ups by person with Copy and Mark sent; one
     column on narrow screens; one primary action per row and the wording sheet; undo toasts instead of confirmations; edit in
     place before copying; the evidence line; keyboard shortcuts for the review loop; React Aria Components, the generated API
     client, TanStack Query with server-sent events; safe rendering of untrusted content; Playwright running the acceptance
     scenario with axe checks (Part 7);
   - quality signals recorded from day one (6.20).

3. **Scope and facts.** The scope resolver and its invariants, the scope sweep (6.18); the fact resolver with paste-in and
   local-folder lookups (6.19); search lookups (6.22); audiences and restrictions; the remaining question and action ops;
   action notices; Reassign; checking corrections against the data.

4. **Plugin host and the plugin API (0.x).** Manifests, registries for the `1.0` extension points (3.3), the fake plugin;
   move the walking skeleton's built-ins behind the same interfaces. Plugins working together (3.9): interfaces with
   schemas and versions, event subscriptions, requests for another plugin's task kinds, and two fake plugins that use each
   other in tests.

5. **Watchers, triage, supersede.** Fake connectors with fixture changes; the matcher registry; the auto-closed list.

6. **Records, rendering and the publisher.** Core record types and `ext` fields, templates, render-time ordering, roll-ups,
   drafts, content-hash approval, scheduled drafts, concurrency check, shared masters (lock status, outside edits as changes),
   reverting drafts for undone publishes; the fake page channel; Waiting to go out with the diff
   renderer. Long text fields with versions and authorship (5.0), drafts with prose output (6.7), the file channel (6.3),
   stages (6.26), independent reviews (6.16), and cost control: estimates, a go above the configured amount, budgets per task
   kind and per record (6.16).

7. **UI shell and settings.** Today as the home queue (7.7), the first-run setup (7.8), panel registry with declarative panels,
   branding, the Settings panel (7.9), the Admin tab including Quality, side-by-side diffs, virtualized lists, phone-friendly
   approval flows and installing as a web app.

8. **The publishing pack** (9.6 to 9.9), the first in real use, with its playbook, dependencies and baselines (6.23), using
   only the plugin API.

9. **The workplace reference pack** (9.1 to 9.5) on fictional data, to prove the extension points serve a very different kind
   of work. Anything either pack needs that the API lacks becomes a generic extension point, not a special case.

10. **AI breadth and evaluation.** Escalation on failure, the three-layer cache layout with frozen batch prefixes,
    reproducible runs and `cockpit replay`, native adapters for vendors with their own API format, the aggregator adapter with its catalog and routing options, `models()` from provider
    catalogs, the Add account flow in Settings, a command-line agent adapter, capability routing, budgets, data-level routing, packet
    budgets; the golden fixture set with hostile inputs (12.2) and `evaluate`. A second vendor's adapter needs no change outside
    its adapter and `config/ai.yaml` (a test proves it with two adapters).

11. **Governor, scheduler, offline behavior (connectivity first, honest staleness), automation problems and reports**,
    error classification from the runner's own streams, handoffs for code other projects own (4.18), the rules review (6.21).

12. **Hosted deployment** (after the publishing pack is in daily use). Auth providers (password with a second factor, passkeys, OpenID Connect, identity-aware proxy),
    sessions, CSRF, lockout, hiding, the deploy checks, the Security panel, retention and forget-a-person, the container image
    and the first two recipes.

13. **Today builder, meetings, weekly check-up, update writer**, and project management support (6.24): issues, assumptions,
    risk fields and reviews, escalation suggestions, communications cadence, meeting agendas; the Ask box (6.25).

14. **Real connectors and channels** (one wiki, one tracker) as plugins, configured only through config.

**Plugin API 1.0** is declared when both packs run on it unchanged. Until then it is 0.x and may change.

## 13.2 After the base

Each a pack, plugin or recipe, in whatever order is useful: publishing support, social media channels, mailbox and calendar
connectors, more AI vendors, more deploy recipes, Postgres for multi-user, the `planned` extension points (event handlers, API
routes) and opening `core only` ones (auth providers, storage backends) to plugins, running plugins out of process with
enforced limits, roles for several users.

## 13.3 Candidate packs

Recorded so the core's extension points are checked against them; neither is scheduled (`docs/project/scope.md`, Later).

**Sales pack** (`plugins/sales/`): an assistant for business-to-business sales of installed services, from first contact to
signed work.

- **Record types:** accounts and their sites, contacts (people records with an account), opportunities with configurable
  stages, quotes, statements of work, contracts.
- **Playbook:** qualification, discovery and site surveys, proposal structure, SOW scope and exclusions, contract and legal
  review checklists, follow-up cadence. Regulatory requirements (licensing, codes, standards, permits) vary by place and
  trade, so they are data per jurisdiction in the workspace, looked up like any configured source (6.19), never built in.
- **AI tasks:** account notes from meetings and emails, proposal and SOW drafts, a compliance checklist against the
  workspace's requirements. Legal and regulatory text is drafted and checked, never advice; the person approves every
  document, and a lint marks clauses that need review by someone qualified.
- **Data:** customer details are `restricted` (4.8), so they go only to AI accounts allowed that level. One employer's
  pricing, terms or approval rules are a private plugin in that workspace.

**Writing pack** (`plugins/writing/`): an assistant that takes a writer from an idea to a finished manuscript, beside the
publishing pack, which takes a finished book to launch.

- **Stages:** ideation, research, outline and chapter plans, drafting, independent review, the writer's review chapter by
  chapter, revision, proposal, manuscript, ebook. Each stage ends with the writer's approval; nothing moves on without it.
- **Record types:** works, ideas, research notes with their sources, outlines, chapter plans, chapter drafts with versions,
  reviews and the writer's feedback, proposals.
- **AI tasks:** one per stage. Research claims carry evidence from their sources (6.7). Drafts are written in the writer's
  voice from their outline and notes, and every chapter waits for the writer's review.
- **Independent review:** a draft is checked by a model from a different account than the one that wrote it; findings are
  lints the writer decides on, never automatic rewrites.
- **Works with publishing:** provides `writing/manuscript@1` (3.9), so a finished book becomes a launch without retyping.
- **Outputs:** a print-ready manuscript PDF to the configured trim size, margins, bleed and fonts for the chosen
  self-publishing platform, and an ebook from the same manuscript (the owner has a converter that can become this pack's
  renderer).
- **Playbook:** craft and structure guidance by genre, chapter review checklists, and the platforms' rules for disclosing
  AI-assisted content.

**Core needs both packs share** are designed into version 1 (milestone 6), so the plugin API is frozen with them in place:
long text with versions and authorship (5.0), drafts and prose output (6.7), the file channel (6.3), stages (6.26), the
independent second opinion (6.16), and cost control with estimates, a go above a configured amount and budgets per task kind
and per record (6.16, 4.8). The packs themselves stay in the Later horizon.
