# Part 10. Guardrails against embedding specifics in code

The failure to prevent: while building for one deployment, every rule a user states ends up as a hardcoded name, team, URL or
`if` in the engine, with the user's quote as a comment. After a few weeks the "generic" code is unusable anywhere else. The
plugin system adds a second failure to prevent: the core growing special cases for one plugin.

## 10.1 The boundary

- **Core code** (`engine/`, `api/`, `web/src/`) may reference only concepts: project, record, person, team, change, source,
  question, action, draft, channel, connector, plugin, rule. Never a specific person, team, organization, product, program,
  system, host, URL or page id, and never a vendor or service name outside `engine/ai/adapters/`.
- **Bundled plugins** (today the example plugin and the define-your-own kit) and **packs in their own repositories** may
  name the product or vendor they connect to, inside that plugin only. They never hold an organization's specifics.
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

Each scan below says what it does today, from the audit of 2026-10-12. "Running" means it is in the suite or the self-check
now; "partial" says what it leaves out; "planned" is not built.

1. **Specificity scan:** reads every name, alias, team, org, group, system name, URL host, page id, page title, query, folder
   path and connector field name (from people data and from `watch.yaml`, `facts.yaml`, `scope.yaml` and connector settings)
   from the fictional workspaces, and with `--workspace <path>` from a private workspace too, and fails if any appears in core code, bundled
   plugins, tests outside fixtures, or UI source. Findings from a private workspace print only file and line, never the matched
   value, so a scan log can't leak it (running). **Partial:** the scan reads workspace and user names, people, organizations,
   teams, project names and aliases, and the URLs in config. It does not yet read system names, page ids, queries, folder
   paths or connector field names, because the files that hold them (`facts.yaml`, `scope.yaml`) are not built.
2. **Provider scan:** fails if an AI vendor or model name (from the adapter registry and `config/ai.yaml`) appears anywhere
   outside `engine/ai/adapters/`, AI adapter plugins, config, fixtures and docs (running).
3. **Pattern scan:** fails on URLs (except in config, fixtures and docs), on comments matching dated-decision patterns ("(Name,
   10/8)", "per X", "X said"), and on capitalized multi-word names in code that aren't in the list of concept words. That list
   holds generic concept words only; a flagged name moves to config or data, it is never added to the list. **Partial:** URL
   and dated-comment patterns run; the capitalized-name check and its concept-word list are not built.
4. **Config coverage:** every config key used in code exists in the schema with a default and a description; every schema key is
   used somewhere. Same for each plugin's config. **Partial:** the check that every key has a default and a description
   runs. The checks that every key used in code is in the schema and that every schema key is read somewhere are not built,
   so keys that do nothing pass today (`storage.export.remote`). Failing on keys nothing reads is planned (10.5).
5. **Boundary scan:** core code imports nothing from `plugins/`; plugins import only `engine.plugin_api` from the engine; no
   core code tests for a plugin's name; bundled plugins don't import network or process libraries directly (12.3). **Running,
   except** the check that no core code tests for a plugin's name, which is not built.
6. **Two workspaces, and core alone:** the suite runs against both fictional workspaces, and once with no bundled packs enabled
   (core plus the fake connector, fake channel and clipboard), so anything that only works for one dataset or one pack fails. **Partial:** the self-check loads and round-trips both
   fixtures, with and without packs. Many route, setup, Today and end-to-end suites run on `demo-b` only, and the CI never
   runs the suite with `COCKPIT_TEST_CORE_ONLY=1`.
7. **Manifests:** what each plugin registers matches its manifest; declared network hosts, secrets and data levels are the only
   ones it uses (running).
8. **Prompt templates and playbooks:** default templates and playbook files in core and bundled plugins are scanned like code
   (scans 1 and 3), so a source or name written into a prompt or a playbook fails the same way as one written into code (running).
9. **UI labels and accessibility:** user-visible text comes from the wording sheet and config, never hard-coded in components
   (a scan checks JSX for literal text); a test renders the UI against both fictional workspaces; the end-to-end runs include
   axe accessibility checks (7.10) in light and dark at phone, laptop and desktop widths. The **visual system** (7.12) is
   enforced too: stylelint fails on a raw color outside the token file, a font size, spacing or radius not taken from a
   token, uppercase text and opacity on disabled controls; the end-to-end suite checks **screen use** (7.13: content covers
   at least 90% of the width beside the sidebar at 1440 and 1920, chrome above content at most 56px) and that no default
   screen shows an id, a raw enum value, a command line or a config path. **Partial:** stylelint and the screen-use checks run,
   and the wording test checks that every key a screen uses exists. There is no scan of JSX for literal text. The end-to-end
   suite runs on `demo-b` only. Axe runs on the style guide and Today in both themes at four widths, and on other screens in
   the light theme at one size. "No id, command or path" is checked on a few screens, not on all of them, and not at all in
   text the server builds (10.5).
10. **Deployment:** hosting platform names appear only in `deploy/` and docs; every recipe's profile passes the deploy checks
    (11.5); the UI and API tests run under the root path and under a nested base path. **Partial:** the base-path runs exist. The
    scan for hosting platform names outside `deploy/` and docs is not built, and there are no recipes or deploy checks yet
    (hosted mode comes after 1.0, Part 11).

## 10.3 Process (for every requirement)

Before writing code, answer and state in the change description:

1. Is this a concept (core), an extension (plugin, or a new generic extension point), a setting (config), a fact (data), a
   standing instruction (`rules.yaml`) or custom to one deployment (private plugin)?
2. If config: the key name, schema, default, and the example value for both fictional workspaces.
3. The decisions.md entry (date, who, what, why), product or workspace.
4. The generic test, run against both fictional workspaces.
5. What the person sees in their first five minutes with the change, with no file edited and no second command.
6. For a reported problem: the failing test of the person's path first, then everything with the same cause, and the reply
   says what was checked (decisions, 2026-10-12).

When a user states a rule in passing ("don't ask the program manager about program dates"), the default home is config (a scope
or routing rule) or `rules.yaml`, not code.

## 10.4 Review checklist (every change)

- No new specific in core, API, UI or bundled plugin code; the scans pass.
- New behavior has a config key with a default, is a pure concept, or is a plugin.
- No special case for a plugin in the core; a missing capability became a generic extension point.
- Rationale went to decisions.md, not a comment.
- Both fictional workspaces pass, and the core passes alone.
- The default produces a visible result for a real person, and the journey tests that cover it pass (10.5).
- No text the server builds names a settings file, a key path, `env:` or a command.

## 10.5 Guardrails from the review of 2026-10-12

The review found that small errors reached the owner because the try-it path ran on test fixtures, safe defaults together
produced nothing, no test followed a person's journey, and the rules were checked in the screens' code but not in text the
server builds (`docs/project/review-2026-10-12.md`). These guardrails answer that.

| Guardrail | State |
|---|---|
| **Journey tests** (Playwright, with a fake AI service and fake mail and calendar services): fresh workspace, add an AI account, hand in, result on Today; sign in, mail and calendar read, assistant, review on Today; a source added on screen, read, assistant; an add-on installed from the screen, turned on, its screens appear; backup then restore; the acceptance scenario steps 1 to 7, step 6 included. **Nothing is "ready to test" until these pass.** | Planned (roadmap A3). Today the 33 end-to-end tests start from the demo workspace with the stand-in assistant, and step 6 of the scenario (export, import, identical) has no test |
| **Server-side wording scan:** the strings in `engine/` and `api/` that reach the screen may not contain `.yaml`, `env:`, `cockpit ` command lines, dotted key paths or manifest field names. About 50 such strings are known and are rewritten or put behind Details | Planned (roadmap A2). The screens' own wording is checked today |
| **Config coverage fails on keys nothing reads** (extends 10.2.4) | Planned |
| **A fresh workspace shows no problem:** the self-check makes a workspace with no template and checks that it has no account, source or setting that shows an error | Planned (roadmap A1) |
| **A starter separate from the fixtures:** `cockpit init` with no template is the documented start; the fictional workspaces are named as test fixtures and the sandbox | Planned (roadmap A1) |
| **Every default produces a visible result:** a brief says what the person sees in the first five minutes | Process rule, in force (`CLAUDE.md`) |
| **Fix the cause, then its siblings:** a failing test of the person's path first, then the same cause searched everywhere, and the reply says what was checked | Process rule, in force (`CLAUDE.md`) |
| **Nothing is "ready to test"** until the journey tests pass; the message to the owner gives the exact commands and what to see | Process rule, in force (`CLAUDE.md`); the journey tests are planned |
| **A plan item is never marked done on a part of it:** say what is left | Process rule, in force (`CLAUDE.md`) |
| **"Built" means a named test passes:** checked roadmap boxes and "Built" rows cite their tests, and the self-check fails on a cited test that doesn't exist | The "built claims" step is in the self-check (`tests/test_built_claims.py`); see the rule below |
| **Nothing lives only in the conversation:** commitments are written in the same turn to the roadmap or `docs/project/open-promises.md`, which a project hook shows to the session at start, resume and after a compaction | In force (`CLAUDE.md`, `.claude/settings.json`) |
| **Screen wording checked where responses leave:** the API's response serializer refuses settings-file names, `env:`, key paths and commands in user-facing text, in tests and dev mode; it reads the words with links taken out first (6.7) | Planned (roadmap A2) |
| **Part 8 is generated from the seed lessons**, and every instruction-only rule has a fixture case; the self-check fails when the page is stale or a case is missing (decisions, 2026-10-12) | Planned (roadmap L) |

**The built-claims rule.** A claim is a checked roadmap box (`- [x]`) or, in a design file, a bold "Built" marker (in a
paragraph, a list item or a table row), a table cell that starts with "Built", or a build-plan state line that reads Built;
the claim is the list item, table row, milestone or paragraph it sits in. It passes when it cites at
least one test that exists (a test file by path or bare file name, a `file::test_name` whose name the file defines, or a bare
`test_name` that some test defines), or says "checked by reading" for docs and process items. It fails when anything it cites
is missing. The step runs in `engine/selfcheck/built_claims.py`; claims still being sorted out go in its `UNDER_REVIEW` set,
and an entry that passes is itself reported. Plain "Built" in running prose is not a claim.
