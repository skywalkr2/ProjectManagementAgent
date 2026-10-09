# Part 10. Guardrails against embedding specifics in code

The failure to prevent: while building for one deployment, every rule a user states ends up as a hardcoded name, team, URL or
`if` in the engine, with the user's quote as a comment. After a few weeks the "generic" code is unusable anywhere else. The
plugin system adds a second failure to prevent: the core growing special cases for one plugin.

## 10.1 The boundary

- **Core code** (`engine/`, `api/`, `web/src/`) may reference only concepts: project, record, person, team, change, source,
  question, action, draft, channel, connector, plugin, rule. Never a specific person, team, organization, product, program,
  system, host, URL or page id, and never a vendor or service name outside `engine/ai/adapters/`.
- **Bundled plugins** may name the product or vendor they connect to, inside that plugin only. They never hold an
  organization's specifics.
- **Workspaces** (config and data, outside this repository) hold every deployment specific.
- **Private plugins** (`<workspace>/plugins/`) may be specific to that deployment and never enter this repository.
- **Sources are config** in core and bundled plugins alike: code never names a page, page tree, query, folder, feed, field or
  schedule to read; it takes them from config keys (4.0). A plugin may name the product it connects to, never what to read in
  it.
- **Deploy recipes** (`deploy/<target>/`) may name their hosting platform. They never contain a user's domain, account or
  secrets; examples everywhere use `example.com`.
- **Rationale** lives in `docs/decisions.md` (product) or the workspace's `docs/decisions.md` (deployment): dated entries with
  what, who decided and why. Code comments explain what the code does in general terms; they never quote a user or carry a date.

## 10.2 Enforcement (automated, part of the test suite and the self-check)

1. **Specificity scan:** reads every name, alias, team, org, group, system name, URL host, page id, page title, query, folder
   path and connector field name (from people data and from `watch.yaml`, `facts.yaml`, `scope.yaml` and connector settings)
   from the fictional workspaces, and with `--workspace <path>` from a private workspace too, and fails if any appears in core code, bundled
   plugins, tests outside fixtures, or UI source. Findings from a private workspace print only file and line, never the matched
   value, so a scan log can't leak it.
2. **Provider scan:** fails if an AI vendor or model name (from the adapter registry and `config/ai.yaml`) appears anywhere
   outside `engine/ai/adapters/`, AI adapter plugins, config, fixtures and docs.
3. **Pattern scan:** fails on URLs (except in config, fixtures and docs), on comments matching dated-decision patterns ("(Name,
   10/8)", "per X", "X said"), and on capitalized multi-word names in code that aren't in the list of concept words. That list
   holds generic concept words only; a flagged name moves to config or data, it is never added to the list.
4. **Config coverage:** every config key used in code exists in the schema with a default and a description; every schema key is
   used somewhere. Same for each plugin's config.
5. **Boundary scan:** core code imports nothing from `plugins/`; plugins import only `engine.plugin_api` from the engine; no
   core code tests for a plugin's name; bundled plugins don't import network or process libraries directly (12.3).
6. **Two workspaces, and core alone:** the suite runs against both fictional workspaces, and once with no bundled packs enabled
   (core plus the fake connector, fake channel and clipboard), so anything that only works for one dataset or one pack fails.
7. **Manifests:** what each plugin registers matches its manifest; declared network hosts, secrets and data levels are the only
   ones it uses.
8. **Prompt templates:** default templates in core and bundled plugins are scanned like code (scans 1 and 3), so a source
   written into a prompt fails the same way as one written into code.
9. **UI labels:** user-visible strings that name the assistant, people or groups come from config; a test renders the UI against
   both fictional workspaces.
10. **Deployment:** hosting platform names appear only in `deploy/` and docs; every recipe's profile passes the deploy checks
    (11.5); the UI and API tests run under the root path and under a nested base path.

## 10.3 Process (for every requirement)

Before writing code, answer and state in the change description:

1. Is this a concept (core), an extension (plugin, or a new generic extension point), a setting (config), a fact (data), a
   standing instruction (`rules.yaml`) or custom to one deployment (private plugin)?
2. If config: the key name, schema, default, and the example value for both fictional workspaces.
3. The decisions.md entry (date, who, what, why), product or workspace.
4. The generic test, run against both fictional workspaces.

When a user states a rule in passing ("don't ask the program manager about program dates"), the default home is config (a scope
or routing rule) or `rules.yaml`, not code.

## 10.4 Review checklist (every change)

- No new specific in core, API, UI or bundled plugin code; the scans pass.
- New behavior has a config key with a default, is a pure concept, or is a plugin.
- No special case for a plugin in the core; a missing capability became a generic extension point.
- Rationale went to decisions.md, not a comment.
- Both fictional workspaces pass, and the core passes alone.
