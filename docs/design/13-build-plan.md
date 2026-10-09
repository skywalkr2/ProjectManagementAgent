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
   - the applier with tiers, invariants and lints for about ten ops: `source`, `note`, `fact`, `record.set`, `record.log`,
     `action.add`, `action.close`, `question.add`, `question.done`, `person.add`;
   - names resolved to ids, with routing decisions for unknown people (6.11); owners as a list, and held actions waiting for
     "Pick an owner";
   - read-backs for rules the PM states, and undo from the ledger with op groups;
   - the glossary in every packet, with `glossary.add` and `lesson.add`, and every open action and question in the packet;
   - waiting states that say why and until when;
   - the clipboard channel;
   - backups to a target off the computer, with the Today and header nag until one has succeeded (4.15);
   - a minimal UI: What changed with the assistant's work nested, and Follow-ups by person with Copy and Mark sent;
   - quality signals recorded from day one (6.20).

3. **Scope and facts.** The scope resolver and its invariants, the scope sweep (6.18); the fact resolver with paste-in and
   local-folder lookups (6.19); search lookups (6.22); audiences and restrictions; the remaining question and action ops;
   action notices; Reassign; checking corrections against the data.

4. **Plugin host and the plugin API (0.x).** Manifests, registries for the `1.0` extension points (3.3), the fake plugin;
   move the walking skeleton's built-ins behind the same interfaces.

5. **Watchers, triage, supersede.** Fake connectors with fixture changes; the matcher registry; the auto-closed list.

6. **Records, rendering and the publisher.** Core record types and `ext` fields, templates, render-time ordering, roll-ups,
   drafts, content-hash approval, scheduled drafts, concurrency check, shared masters (lock status, outside edits as changes),
   reverting drafts for undone publishes; the fake page channel; Waiting to go out with the diff
   renderer.

7. **UI shell and settings.** Panel registry with declarative panels, branding, the Settings panel generated from schemas
   (with levels and presets), the Admin tab including Quality.

8. **The publishing pack** (9.6 to 9.9), the first in real use, with its playbook, dependencies and baselines (6.23), using
   only the plugin API.

9. **The workplace reference pack** (9.1 to 9.5) on fictional data, to prove the extension points serve a very different kind
   of work. Anything either pack needs that the API lacks becomes a generic extension point, not a special case.

10. **AI breadth and evaluation.** Native adapters for vendors with their own API format, the aggregator adapter with its catalog and routing options, `models()` from provider
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
