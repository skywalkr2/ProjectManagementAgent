# Part 13. Build plan

Two principles. **Use it early:** the PM works with a thin end-to-end version within the first weeks, and every later
milestone is judged against real use (with the PM's corrections as the measure, 6.20). **Build the safety first:** the ledger,
the tiers and the invariants are in the first usable version, because they are much harder to add once data and habits exist.

Each milestone ends with tests passing against both fictional workspaces, the core passing alone, and the scans green.

## 13.1 Milestones

1. **Skeleton and guardrails.** Repository layout (2.2); tooling (uv, ruff, pytest, Vite, Vitest); the database with record
   versions, the ledger, id sequences, the instance lease and the readable export (5.0); config schemas with versions, layers,
   profiles and `cockpit config show` / `explain` (4.0); the scans and the self-check (10.2); both fictional workspaces as
   importable fixtures; `cockpit serve` in local mode with the install token and base-path support.

2. **Walking skeleton (the first version the PM uses).** One path through the whole loop, on real work:
   - paste-in with "your note" and "pasted content" (12.2);
   - one AI task kind (`notes`) through the provider layer with the stub adapter and the first vendor's API adapter;
   - the applier with tiers, invariants and lints for about ten ops: `source`, `note`, `fact`, `record.set`, `record.log`,
     `action.add`, `action.close`, `question.add`, `question.done`, `person.add`;
   - names resolved to ids, with routing decisions for unknown people (6.11);
   - undo from the ledger;
   - the clipboard channel;
   - a minimal UI: What changed with the assistant's work nested, and Follow-ups by person with Copy and Mark sent;
   - quality signals recorded from day one (6.20).

3. **Scope and facts.** The scope resolver and its invariants, the scope sweep (6.18); the fact resolver with paste-in and
   local-folder lookups (6.19); the remaining question and action ops; action notices; Reassign.

4. **Plugin host and the plugin API (0.x).** Manifests, registries for the `1.0` extension points (3.3), the fake plugin;
   move the walking skeleton's built-ins behind the same interfaces.

5. **Watchers, triage, supersede.** Fake connectors with fixture changes; the matcher registry; the auto-closed list.

6. **Records, rendering and the publisher.** Core record types and `ext` fields, templates, render-time ordering, roll-ups,
   drafts, content-hash approval, scheduled drafts, concurrency check; the fake page channel; Waiting to go out with the diff
   renderer.

7. **UI shell and settings.** Panel registry with declarative panels, branding, the Settings panel generated from schemas
   (with levels and presets), the Admin tab including Quality.

8. **The reference pack** (Part 9) on the fictional workspaces, using only the plugin API. Anything it needs that the API lacks
   becomes a generic extension point, not a special case.

9. **The second pack** (personal projects) to prove the extension points serve a different kind of work.

10. **AI breadth and evaluation.** A command-line agent adapter, capability routing, budgets, data-level routing, packet
    budgets; the golden fixture set with hostile inputs (12.2) and `evaluate`. A second vendor's adapter needs no change outside
    its adapter and `config/ai.yaml` (a test proves it with two adapters).

11. **Governor, scheduler, offline behavior, issues and the fixer** (merge on Apply), the rules review (6.21).

12. **Hosted deployment.** Auth providers (password with a second factor, passkeys, OpenID Connect, identity-aware proxy),
    sessions, CSRF, lockout, hiding, the deploy checks, the Security panel, retention and forget-a-person, the container image
    and the first two recipes.

13. **Today builder, meetings, weekly check-up, update writer.**

14. **Real connectors and channels** (one wiki, one tracker) as plugins, configured only through config.

**Plugin API 1.0** is declared when both packs run on it unchanged. Until then it is 0.x and may change.

## 13.2 After the base

Each a pack, plugin or recipe, in whatever order is useful: publishing support, social media channels, mailbox and calendar
connectors, more AI vendors, more deploy recipes, Postgres for multi-user, the `planned` extension points (event handlers, API
routes) and opening `core only` ones (auth providers, storage backends) to plugins, running plugins out of process with
enforced limits, roles for several users.
