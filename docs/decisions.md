# Product decisions

Dated entries: what was decided, who decided, why. Newest first. Decisions about one deployment go in that workspace's own
`docs/decisions.md`, not here.

## 2026-10-09: Changes from the first design's author

**Decided by:** project owner, on the review by the author of the first design, who ran it daily.

- **Recovery is a tested feature.** The ledger is exported with the records; `import(export(db))` round-trips in the self-check;
  `cockpit restore --as-of` and single-record restore from the ledger. Why: restoring from git history was used in practice,
  and an export that can't be loaded back is only an archive.
- **Off-device backups in local mode**, with a Today line and header mark until one succeeds and the last backup's age always
  shown. Why: the biggest open risk of the first deployment was the whole knowledge base on one laptop.
- **Breadth waits for use:** hosted mode, packs beyond the second and social media start after the reference pack is in daily
  use.
- **The packet replaces browsing:** it always carries the glossary, active lessons, applicable rules and every open action and
  question; new `glossary.add`, `glossary.update`, `lesson.add` ops; bounded search lookups over sources and records.
- **PM-stated system ops apply at once with a read-back and Undo;** only system ops from inputs or the assistant's own initiative
  wait for a confirm. Why: the risk with the PM's own rules was misreading, which a read-back catches and a confirm doesn't.
- **Undo groups:** dependent ops are restored all or nothing; outbound can't be undone (reverting drafts, "already sent").
- **Owners are a list** (shared ownership is deliberate in some programs); team-only owners are refused and an action without a
  known person is held for "Pick an owner".
- **Lint outcomes depend on destination:** after one return, anything reaching another person is held for the PM; internal items
  warn. Missing links on questions to others, restricted content on the wrong audience and unreadable output are invariants.
- **Gaps from running it:** runner errors classified only from exit code and error stream; every waiting state shows why and until
  when; corrections checked against the data first; audiences per destination instead of open versus restricted; shared masters
  with lock checks and outside edits as changes; connectivity checked before refreshing, and failed refreshes stay stale; edits by
  our own accounts marked as ours; requests about other projects' code handed off (`config/code_owners.yaml`), restoring the
  handoff route the first design had and the restructure had dropped.

## 2026-10-09: Systems review changes

**Decided by:** project owner, after a systems design review of the whole design.

- **Database and ledger instead of files plus git as the store.** SQLite is the system of record; every applied op is written
  to an append-only ledger in the same transaction; records carry versions; ids come from sequences; jobs and the single
  running instance use leases; `data/` becomes a readable JSON export committed to git. Why: half of the storage rules
  (merge-on-save, one writer, ids never repeat, undo only if unchanged, one scheduler) were database guarantees rebuilt by hand
  on files, each learned from a failure. Undo becomes a reverse changeset with field-level conflicts instead of file restores.
  Supersedes the storage part of the 2026-10-08 technology stack entry.
- **Ids, not names.** Records refer to people, teams and projects by id; names are rendered. Why: storing "Team (Full Name)"
  strings is what required a names normalizer on every write, a name sweep and a rename reference index across every copy.
- **Op tiers and untrusted input.** Every op is data, outbound or system; system ops (rules, sources, scope, config, plugins,
  code) never apply automatically from an input. Packets mark untrusted content; lookups only reach configured sources;
  evaluation includes hostile inputs. Why: the design had no prompt-injection model, and mailbox and social plugins plus hosted
  mode make that exposure real.
- **Invariants and lints.** Firm checks always refuse and can't be lowered; fuzzy checks (wording, keyword-matched date
  questions, near-duplicates) return the changeset once, then warn, with severities in `config/checks.yaml`. Why: fuzzy checks
  that refuse produce false positives that push people to switch checks off.
- **Walking skeleton first; extension points marked 1.0, core only or planned.** The build plan reaches a version the PM uses
  in milestone 2 (paste-in, one AI task, about ten ops, the ledger, clipboard, a minimal UI). Only the extension points the two
  packs use are frozen at plugin API 1.0. Why: fifteen milestones before daily use, and sixteen hooks before any plugin, freeze
  guesses.
- **Gaps closed:** quality signals from the PM's corrections and private evaluation cases (6.20); standing rules as
  `config/rules.yaml` entries with a review that merges, retires and promotes rules into config (6.21); config versions and
  migrations, presets, basic and advanced levels, `config explain` (4.0); honest plugin security (declared reach is enforced on
  what the core hands out, not a sandbox, 12.3); one running instance per workspace; packet size budgets (6.6); retention and
  forget-a-person (4.15, 12.4).
- **The design is split into one file per part** under `docs/design/`, keeping section numbers, with a reading map in its
  README. Why: at 1,400 lines every coding session paid to read most of it.

## 2026-10-08: Every source is a setting

**Decided by:** project owner.

**What:** Where anything is looked up (a page, page tree, query, folder, feed, field name or schedule) is always configuration,
never code or default prompt text. Core and bundled plugins refer to sources by config key; default prompt templates use
template variables filled from config. Packs ship source settings as templates with placeholders that the workspace fills in,
with a Today setup line until it does. The specificity scan now also reads page titles, queries, folder paths and field names
from the fictional workspaces' config, and scans default prompt templates as well as code.

**Why:** Rules like "look on the release page" are easy to write straight into code or prompts while building for one
deployment, and each one ties the product to that deployment's tools and page layout.

## 2026-10-08: Lessons from the original deployment since the first design

**Decided by:** project owner.

Each came from a failure in the original deployment.

- **Other areas, even when named in minutes or program pages.** Domains now match owner labels as they appear on pages and in
  minutes, and the applier refuses an action whose owner label matches another domain. The owner described this as
  `other_team_owners` and `program_managers` per area; in the product they are each domain's `match.owners` and `contact`.
- **Dates are looked up, not asked.** New `config/facts.yaml` and fact resolver (6.19): an item's release comes from the
  delivery tracker or the tracker item's sprint or fix version, the release's production date from the delivery team's schedule
  page, and nothing found means TBD. The applier refuses questions for those facts, and any date question to the people listed
  in `no_questions_to`. This is a separate file rather than part of `scope.yaml` (where the owner first put it) because it is
  about where facts live, not whose area something is, and other packs need the same mechanism (publication dates, for example).
  Why: people were asked for dates that a schedule page already held, and the answers went stale.
- **Fixes merge on Apply.** A proposed fix keeps the original files and Apply runs a three-way merge, with a union merge for
  Markdown; only a real conflict stops it, and then the fix is redone automatically. Why: a whole-file staleness check made
  nearly every fix on a busy file go stale. The UI never offers an instruction it can't carry out, and a fix shows and is counted
  only on its issue card.
- **Rename is one op.** `record.rename` updates every stored reference through a reference index and keeps the page id, so the
  page is renamed in place. Why: renames done as several edits missed places and broke links.
- **A code fix is the last resort.** `dev.request` must show that no existing op fits; data that needs a new op waits with its
  fix and runs after Apply. Why: requests that ops could do became code fixes, and data changes needing a new op were refused by
  the running applier.
- **Ids never repeat.** Closed ids are retired. Why: a reused question id made old references point at the wrong question.

## 2026-10-08: Scope is enforced by the applier, with named domains and one contact each

**Decided by:** project owner.

**What:** `config/scope.yaml` gains `domains` (other areas, each with match patterns and one `contact`, usually that area's
program manager), `cross_domain` (impact-only questions, to the contact only, batched) and `unclassified` (ask the PM; never
tracked by default). The applier refuses actions owned by anyone outside the tracked area and questions to anyone outside it,
except an impact question to a domain's contact that names the tracked item it affects. A scope sweep finds existing actions and
questions that break this and files one bulk decision to the PM. A new `other-domain` triage matcher closes changes that sit
entirely in another area. One scope resolver is the only place scope is decided.

**Why:** In the original deployment, scope was advisory: the AI was told what to track but nothing stopped it. Changes on shared
pages that mixed several teams' work produced action items and detailed questions for people in other areas, who don't answer to
the workspace; that work is the program level's concern. The PM's inbox filled with follow-ups that should never have existed.
Making scope a deterministic check, with one named contact per other area and only impact questions allowed, stops the failure
at the write path instead of relying on the model.

## 2026-10-08: Local and hosted deployment from the same code; configuration first

**Decided by:** project owner.

**What:** The app runs in two modes, set by configuration: local (on the PM's computer, reachable only from it) and hosted (on a
web host the PM controls, at the PM's domain, optionally under a path such as `/admin` and optionally hidden from anyone not
signed in). Hosted mode requires real sign-in (pluggable auth providers) and refuses to start unless a set of deploy checks pass.
Packaging lives in `deploy/`: one container image plus a recipe per hosting target, starting with a tunnel to a machine the PM
owns and then a container host. Every setting can come from files, environment variables, flags or profiles, and is editable in
a Settings panel generated from the config schemas.

**Why:** The owner wants to run the product locally or on a web host, behind security checks, at a configurable hidden path, and
to change an installation without changing code. Hiding a path is not security on its own, so the deploy checks make real
sign-in, HTTPS and secret handling a condition of serving. The engine needs long-running jobs, a file system and git, so hosted
targets run it as a container or a process, not as short-lived edge functions. This replaces the earlier "local only" part of the
technology stack decision.

## 2026-10-08: Design recast as a generic core with plugins

**Decided by:** project owner.

**What:** The design is now a base for expansion, not a single-purpose tool. The core keeps only the generic loop (watch,
triage, dispatch, apply, review, send out, follow up), its safety rules and a set of extension points. The original workplace
use becomes the reference pack (design Part 9), built on the plugin API like any other pack. A second, smaller pack (personal
projects) is in the build plan to prove the extension points serve a different kind of work.

**Why:** The owner wants to use the same base for other kinds of work later (publishing support, personal projects, social
media). Building the first use as a pack, from the start, keeps workplace-specific behavior out of the core.

## 2026-10-08: Outbound content goes through channels and one approval gate

**Decided by:** project owner.

**What:** Publishing wiki pages becomes one case of a general model: records render into drafts for channels (pages, messages,
email, posts), and the publisher sends only drafts whose exact content the PM approved. Scheduled sending is allowed only for
approved content. Autonomous sending is not a goal.

**Why:** Social media and publishing plugins need outbound targets other than wiki pages. Putting every target behind the same
approval gate keeps the core promise ("the AI drafts; the human approves everything outward") as the product grows.

## 2026-10-08: Technology stack

**Decided by:** project owner.

**What:** Python 3.12+ with uv, FastAPI, Pydantic v2, pytest, ruff; React + TypeScript with Vite and Vitest. Plugins are Python
packages found by entry point or by folder. Storage starts as files in the workspace git repository behind a repository layer.
The app runs locally for one user.

**Why:** The design already called for Python and React. Pydantic generates JSON Schema from the same models that validate config,
records, ops and manifests, so the AI's output schema and the validator can't drift apart. Entry points give installable plugins
without a custom registry. A local, single-user app keeps the security model small until multi-user is needed.

## 2026-10-08: Changesets are JSON

**Decided by:** project owner.

**What:** Changesets are JSON documents validated against a schema generated from the op registry. Human-edited config stays
YAML.

**Why:** The design called them YAML in one place and JSON in another. AI APIs return structured output as JSON, and a generated
schema gives one source of truth.

## 2026-10-08: Naming fixes

**Decided by:** project owner.

**What:** The meeting entity is `Meeting` (was `Task`); a call to the AI provider layer is an `AiTask`. Page-specific ops became
record ops (`record.set`, `record.add`, `record.del`, `record.log`). `config/pages.yaml` became `config/render.yaml`. Tracker- and
wiki-specific triage matchers got generic names (`container-not-mapped`, `child-item`, `unknown-key`).

**Why:** "Task" meant two different things. Page and wiki names don't fit outputs like messages and posts.

## 2026-10-08: Workspaces live outside the repository

**Decided by:** project owner.

**What:** Real workspaces are separate git repositories outside this one, found by `--workspace` or `COCKPIT_WORKSPACE`. Only the
two fictional workspaces are committed, as fixtures, and `.gitignore` admits nothing else under `workspaces/`. The specificity
scan accepts `--workspace` to check code against a private workspace without copying its contents into the repository.

**Why:** Keeps real names and data out of the product repository, and lets the scan catch a deployment's specifics, not only the
demo ones.

## 2026-10-08: The fixer changes the workspace, not the product

**Decided by:** project owner.

**What:** Proposed fixes may change a workspace's config, rules, prompts, templates and private plugins. A fix that needs the core
or a bundled plugin is written as a patch and an issue for this repository.

**Why:** Applying AI-written fixes to an installed engine would make each deployment drift away from the product.

## 2026-10-08: Design document moved to `docs/`

**Decided by:** project owner.

**What:** `DESIGN.md` moved to `docs/DESIGN.md`, where `CLAUDE.md` already pointed. The copy of `CLAUDE.md` that was embedded in
the design was removed; `CLAUDE.md` is the only copy.

**Why:** One copy of each document, at the path the other documents use.
