# Part 13. Build plan

Two principles. **Use it early:** the PM works with a thin end-to-end version within the first weeks, and every later
milestone is judged against real use (with the PM's corrections as the measure, 6.20). **Build the safety first:** the ledger,
the tiers and the invariants are in the first usable version, because they are much harder to add once data and habits exist.

**Earn the breadth:** hosted mode, social media and any pack beyond the three in the plan are a lot of product for a tool whose
first deployment has one user. They come after 1.0 and after real use (13.2).

**The order and the dates are in `docs/project/roadmap-to-1.0.md`** (13.4): phases A to E, each ending on an exit test the owner
can run. This part is the **catalog of work**: what each milestone contains and whether it is built. It is no longer the order
of work. The go/no-go of 2026-10-30 and the freeze before the 2026-12-01 launch that `docs/project/schedule.md` still lists no
longer hold (decisions, 2026-10-09 "Real use starts with the publishing pack" and 2026-10-12 "The go-forward plan"); phase D's
dates are set by the owner when it starts. `schedule.md` is kept for the record, with its launch slice and its acceptance
scenario.

Each milestone ends with tests passing against both fictional workspaces, the core passing alone, and the scans green. Under
the review of 2026-10-12 a milestone also ends with its journey tests (10.5), and nothing is "ready to test" before they pass.

**State key (the audit of 2026-10-12).** Built: the code and a test exist. Partial: part of it exists; the line says what is
left. Not started: nothing exists here. A milestone is never marked done on a part of it.

## 13.1 Milestones

1. **Skeleton and guardrails.** Repository layout (2.2); tooling (uv, ruff, pytest, Vite, Vitest); the database with record
   versions, the ledger, id sequences, the instance lease, the readable export and the export → import round trip with point-in-time restore (5.0); config schemas with versions, layers,
   profiles and `cockpit config show` / `explain` (4.0); the scans and the self-check (10.2); both fictional workspaces as
   importable fixtures; `cockpit serve` in local mode with the install token and base-path support.

   **State: Partial.** Built: layout and tooling, the database with versions, ledger, id sequences and the lease, the readable
   export and the import round trip, config schemas and layers, `cockpit config show`, both fixtures importable, local serve
   with the token and base path. Not yet: point-in-time restore (`cockpit restore`), profiles and `config explain`; the scans
   are partial (10.2).

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
   - read-backs for rules the PM states (*moved to phase E*), and undo from the ledger with op groups;
   - the glossary in every packet, with `glossary.add` and `lesson.add` (*moved to phase L-core*), and every open action and
     question in the packet;
   - waiting states that say why and until when;
   - the clipboard channel;
   - backups to a target off the computer, with the Today and header nag until one has succeeded (4.15);
   - a minimal UI: What changed with the assistant's work nested, and Follow-ups by person with Copy and Mark sent; one
     column on narrow screens; one primary action per row and the wording sheet; undo toasts instead of confirmations; edit in
     place before copying; the evidence line; keyboard shortcuts for the review loop; React Aria Components, the generated API
     client, TanStack Query with server-sent events; safe rendering of untrusted content; Playwright running the acceptance
     scenario with axe checks (Part 7);
   - quality signals recorded from day one (6.20).

   **State: Partial.** Built: paste-in with the two kinds of words, the core playbook, the notes task through the stub and
   OpenAI-compatible adapters, cleaning and one input per call, JSON repair and evidence, provenance, the first evaluation set
   (14 cases in `demo-b`, three runs each), the applier for most of the ten ops, names resolved to ids, owners and held actions,
   undo with op groups, the packet's open items, waiting states, backups with the nag, the minimal UI and quality signals.
   Not yet: read-backs for rules the PM states, the glossary with `glossary.add` and `lesson.add` (so proposed lessons), the
   `source` op, the clipboard as a channel (Copy exists in the screen), and the acceptance scenario's step 6 (export, import,
   identical), with steps 2, 4, 5 and 7 checked less than the scenario says.

3. **Scope and facts.** The scope resolver and its invariants, the scope sweep (6.18); the fact resolver with paste-in and
   local-folder lookups (6.19); search lookups (6.22); audiences and restrictions; the remaining question and action ops;
   action notices; Reassign; checking corrections against the data.

   **State: Not started.** No scope resolver or sweep, fact resolver, search lookups, audiences and restrictions, action
   notices, Reassign, or checking corrections against the data. The remaining question and action ops are not built.

4. **Plugin host and the plugin API (0.x).** Manifests, registries for the `1.0` extension points (3.3), the fake plugin;
   move the walking skeleton's built-ins behind the same interfaces. Plugins working together (3.9): interfaces with
   schemas and versions, event subscriptions, requests for another plugin's task kinds, and two fake plugins that use each
   other in tests.

   **State: Built, except one item.** Manifests, registries, the fake plugin, interfaces, events, requests for another plugin's
   task kinds and two fake plugins that use each other are built and tested (plugin API 0.3.55, with a generated guide). Not
   yet: the walking skeleton's built-ins (AI adapters, channels) behind the same registries; adapters are a fixed list.

5. **Watchers, triage, supersede.** Fake connectors with fixture changes; the matcher registry; the auto-closed list.

   **State: Built.** Fake connectors, the matcher registry and the auto-closed list, and beyond the milestone the core's folder,
   feed, calendar-file and mailbox connectors (the core ships them; 1.4 and 6.2 are corrected by another writer).

6. **Records, rendering and the publisher.** Core record types and `ext` fields, templates, render-time ordering, roll-ups,
   drafts, content-hash approval, scheduled drafts, concurrency check, shared masters (lock status, outside edits as changes),
   reverting drafts for undone publishes; the fake page channel; Waiting to go out with the diff
   renderer. Long text fields with versions and authorship (5.0), drafts with prose output (6.7), the file channel (6.3),
   stages (6.26), independent reviews (6.16), and cost control: estimates, a go above the configured amount, budgets per task
   kind and per record (6.16).

   **State: Partial.** Built: core record types and `ext` fields, drafts, the concurrency check, long text with versions and
   authorship, drafts with prose output, stages, independent reviews and cost control. Not yet: templates, render ordering and
   roll-ups, content-hash approval and scheduled drafts, shared masters, reverting drafts after an undone publish, the fake
   page channel, Waiting to go out with the diff renderer, and the file channel. These are the publisher (roadmap C4).

7. **UI shell and settings.** Today as the home queue (7.7), the first-run setup (7.8), panel registry with declarative panels,
   branding, the Settings panel (7.9), the Admin tab including Quality, side-by-side diffs, virtualized lists, phone-friendly
   approval flows and installing as a web app.

   **State: Partial.** Built: the shell and visual system, the first-run setup, the panel registry with declarative panels,
   branding and the Settings forms generated from the schemas. Today as the queue has its engine and API but the screen still
   shows the earlier board. Not yet: the Admin tab with Quality, side-by-side diffs (the long-text compare exists), virtualized
   lists, the phone review mode and the installable web app. Phase B finishes this (7.17).

8. **The publishing pack** (9.6 to 9.9), the first in real use, with its playbook, using
   only the plugin API. Dependencies and baselines (6.23) belong to the project management pack (9.10); the pack lives in its
   own repository, not in this one.

   **State: Not started.** The pack lives in its own private repository and is not yet created (roadmap C3; 9.6 to 9.9).

9. **The workplace reference pack** (9.1 to 9.5) on fictional data, to prove the extension points serve a very different kind
   of work. It is an add-on in its own repository. Anything either pack needs that the API lacks becomes a generic extension point, not a special case.

   **State: Not started.** A private add-on in its own repository (9.1 to 9.5); not on the roadmap to 1.0.

10. **AI breadth and evaluation.** Escalation on failure, the three-layer cache layout (the batch prefix is not frozen, 6.6),
    reproducible runs and `cockpit replay`, native adapters for vendors with their own API format, the aggregator adapter with its catalog and routing options, `models()` from provider
    catalogs, the Add account flow in Settings, a command-line agent adapter, capability routing, budgets, data-level routing, packet
    budgets; the golden fixture set with hostile inputs (12.2) and `evaluate`. A second vendor's adapter needs no change outside
    its adapter and `config/ai.yaml` (a test proves it with two adapters).

    **State: Partial.** Built: escalation on failed checks, `models()` from provider catalogs, the Add account flow, the
    command-line agent adapter, budgets, data-level routing and `evaluate`. Partial: the cache layout, the aggregator adapter
    (a catalog entry through the OpenAI-compatible adapter, with no routing options), capability routing, packet budgets and the
    golden fixtures. Not yet: reproducible runs and `cockpit replay`, native adapters, and the test that a second vendor's
    adapter needs no change elsewhere.

11. **Governor, scheduler, offline behavior (connectivity first, honest staleness), automation problems and reports**,
    error classification from the runner's own streams, handoffs for code other projects own (4.18), the rules review (6.21).

    **State: Partial.** Built: the scheduler, reports and error classification from the runner's own streams. Partial: offline
    behavior and automation problems. Not yet: the governor (re-queue of crashed runs, stale-item sweeps, outage handling, the
    scheduled export), handoffs for code other projects own, and the rules review.

12. **Hosted deployment** (after 1.0). Auth providers (password with a second factor, passkeys, OpenID Connect, identity-aware proxy),
    sessions, CSRF, lockout, hiding, the deploy checks, the Security panel, retention and forget-a-person, the container image
    and the first two recipes.

    **State: Not started.** After 1.0 (Part 11).

13. **Today builder, meetings, weekly check-up, update writer**, and project management support (6.24): issues, assumptions,
    risk fields and reviews, escalation suggestions, communications cadence, meeting agendas; the Ask box (6.25).

    **State: Partial.** Built: the Today builder (the queue and the agenda) and the Ask box. Not yet: meetings, the weekly
    check-up and the update writer. Issues, assumptions, risk fields and reviews, escalation suggestions, cadence and meeting
    agendas (6.24) moved to the project management pack (9.10).

14. **Real connectors and channels** (one wiki, one tracker) as plugins, configured only through config.

    **State: Not started here.** The core ships the folder, feed, calendar-file and mailbox connectors. A mail and calendar
    add-on that signs in to two named services is built in its own private repository and listed in the catalog. A wiki and a
    tracker connector are not built.

**Plugin API 1.0** is declared when the packs of the plan (writing, project management, publishing) run on it unchanged. Until
then it is 0.x and may change. It is at 0.3.55 and not declared.

## 13.2 After the base

Each a pack, plugin or recipe, in whatever order is useful, and none of it in 1.0: hosted mode and its sign-in (Part 11),
social media, email and newsletter channels, more AI vendors, more deploy recipes, Postgres for multi-user, the `planned`
extension points (event handlers, API routes) and opening `core only` ones (auth providers, storage backends) to plugins,
running plugins out of process with enforced limits, roles for several users. Publishing support and the mail and calendar
connectors are already in the plan or built (13.1, 13.4).

## 13.3 Candidate packs

Recorded so the core's extension points are checked against them; not scheduled (`docs/project/scope.md`, Later).

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

**Core needs for document-heavy packs** are designed into version 1 (milestone 6), so the plugin API is frozen with them in
place: long text with versions and authorship (5.0), drafts and prose output (6.7), the file channel (6.3), stages (6.26), the
independent second opinion (6.16), and cost control with estimates, a go above a configured amount and budgets per task kind
and per record (6.16, 4.8).

## 13.4 The plan to 1.0

The current plan is `docs/project/roadmap-to-1.0.md`, rewritten on 2026-10-12 after the review (decisions, 2026-10-12 "The
go-forward plan: a working baseline, then the UI, then the packs"). One phase at a time, one stream of work at a time, and a phase
ends when its exit test passes, not when its code is written. Durations are estimates in working sessions; dates are set when a
phase starts.

The phases, in order. What each holds, its size and its exit test are in the roadmap only, so the two can't drift apart
(the first design author's review of the plan found they had):

| Phase | In short |
|---|---|
| 0 | The plan and the rules (done) |
| A | A baseline that works with no demo data |
| L-core | The learning loop; the owner's real use starts when it passes |
| B | The UI/UX redesign finished |
| C | The packs in the owner's workspace, learning included |
| L-more | The rest of learning |
| D | Owner sign-off |
| E | The rest of version 1, then Publish 1.0 |

**Not in 1.0:** hosted mode and sign-in (Part 11), social, email and newsletter channels, the sales pack (13.3), and licensed
(paid) packs, which are the owner's call after launch.
