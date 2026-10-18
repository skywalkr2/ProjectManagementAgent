# Review: PM Cockpit (ProjectManagementAgent)

**Branch:** `claude/tender-tesla-16a8ob` · **Commit:** [`c7d221f`](https://github.com/skywalkr2/ProjectManagementAgent/tree/c7d221f3b65327fe5816b799c9afed584117ad22) · **Reviewed:** 2026-10-18

**Runtimes:** Python 3.13.12 with the project's locked dependencies (matching CI), Python 3.14.3 (the declared support range's newest interpreter), Node 22.14.0 (the documented `>=22.12`; the sandbox default Node 20 is below the requirement and was not used for any verdict).

**What this is:** a documentation-first review plus a validation pass — I read the documentation set, traced the key safety promises into code, and ran the project's own check pipeline. It is **not** a line-by-line audit of the ~37k lines of engine code or the React components; that would be a separate pass (see Limitations).

---

## 1. Verdict in one line

On the CI-tested runtimes everything passes and the documentation is unusually honest and well-aligned with the code; the one genuine defect found is a **Python 3.14 compatibility break** in a safety guard and in the self-check, which the CI matrix (3.12/3.13 only) does not catch.

---

## 2. Documentation assessment

The documentation is the strongest part of this repository, and it is written to be read by both humans and agents.

**Structure and honesty.** `docs/design/` parts 1–13 are cross-referenced against a decision log ([`docs/decisions.md`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/decisions.md)) that records owner quotes and dates, a build plan that marks unbuilt scope explicitly, a generated developer guide for plugin authors, and a charter/scope/risks/roadmap set under `docs/project/`. Unbuilt features — most notably the outbound publisher (design 6.12) — are labelled "designed, not yet built" rather than described as working. The security part lists its own known gaps, and a prior audit (2026-10-12) is checked in with its findings and plan.

**Strengths:**
- Decisions are traceable: the design rules I spot-checked each have a dated decision behind them, including the owner's own words.
- `CLAUDE.md`/`AGENTS.md` define agent working rules, boundaries (no org-specific data in core, no vendor names outside adapters), and the exact check pipeline — and that pipeline is real and enforced in CI.
- `docs/getting-started.md` and `docs/install.md` state costs, failure modes, and recovery steps per setup screen — rare and valuable.

**Observations (not defects):**
- The [2026-10-17 decision](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/decisions.md) renames the product to **Thimbleby** with the rename scheduled for phase I; docs and code still say "PM Cockpit" everywhere. That is planned work, not drift — no completed milestone claims otherwise.
- `docs/decisions.md` is very large; when the rename lands it may be worth splitting per phase, since agents are told to read it.

**Claim trace — what I actually checked (docs → code):**

| Promise | Where documented | What I verified | Status |
|---|---|---|---|
| Spend defaults: ask above $0.10, stop above $2.00/day | getting-started.md | Default values in [`engine/config/schema.py`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/config/schema.py) (`confirm_above_usd=0.10`, `per_day_usd=2.0`) match the doc's stated starting values. Defaults matching is not enforcement verification — enforcement code was not audited. | Values match |
| Key stays on this computer; settings hold a reference | getting-started.md | `engine/credentials.py` models secrets as references (env var / file path) and resolves them via `engine.secrets`; the settings hold the reference, not the value, in the code paths I read. Secret-storage permissions on disk were not audited. | Consistent with code read |
| Backups encrypted; wrong key refused before writing | design 4.15, 12.1 | [`engine/backup_crypto.py`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/backup_crypto.py) implements scrypt key derivation, per-chunk AES-GCM, and a sealed check value per its module contract. The implementation and restore path were not independently tested. | Implementation present, untested by me |
| Mail/calendar read only | getting-started.md | No SMTP or IMAP APPEND code path exists in `engine/connectors/mailbox.py` or `calendar.py` (string search only). | No write path found |
| Outbound sending always needs the PM's approval, via the publisher | design 6.12 | No publisher module exists — and the design doc says so ("designed, not yet built", phase C4). Drafts currently end at approval/undo (`api/routes.py` `looks_good`/`send_back`); nothing sends. | Honest gap, correctly labelled |
| Person-only ops (e.g. `question.mark_sent`) blocked from outside content | design + invariants | `engine/applier.py:185` refuses person-only ops unless `_from_pm()` (`applier.py:668`) holds: origin `pm`, trusted input, and content not relayed from someone else. | Matches |

---

## 3. Validation results

What ran where (local results marked; everything else verified from the [CI run for this exact commit](https://github.com/skywalkr2/ProjectManagementAgent/actions/runs/39062677342), where all steps of the `python (3.12)`, `python (3.13)`, and `web` jobs — including "Browser tests with accessibility checks" — passed):

| Check | Python 3.13 (locked) | Python 3.14.3 (local) | Node 22.14 (local) |
|---|---|---|---|
| `uv sync`, ruff check, ruff format | CI (both 3.12 & 3.13 jobs): pass | Local: pass | — |
| `pytest` full suite (3,737 tests) | CI: pass | Local: **1 failure** (Finding 1) | — |
| `engine.selfcheck` (17 checks) | CI + local: pass (17/17) | Local: **1 failure** (Finding 1) | — |
| Stage-guard test (`tests/test_stages.py`, 44 tests) | Local: pass | Local: fail | — |
| `npm test` (1,070 tests, 89 files) | — | — | Local: **pass** |
| `npm run build` | — | — | Local: pass (with a pre-existing >500 kB chunk warning) |
| `npm run e2e` (134 browser tests) | — | — | **Blocked locally**; CI: pass |

An initial frontend failure I reproduced (`RecordPage.test.tsx`, focus restore after save) was **withdrawn**: it was caused by the sandbox's Node 20 default. On Node 22.14 all 1,070 frontend tests pass. No product defect.

---

## 4. Findings

### Finding 1 — Python 3.14 breaks a safety guard and the self-check (Medium)

**Severity:** Medium (compatibility + invariant enforcement). **Confidence:** high — reproduced and isolated on both interpreters.

`pyproject.toml` declares `requires-python = ">=3.12"` and the docs say "Python 3.12 or newer", so 3.14 is inside the declared range. On Python 3.14.3 with the locked pydantic 2.14.0:

1. **The plugin stage-field guard silently stops working.** [`engine/plugin_host.py:1566`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/plugin_host.py#L1566) rejects record types that redefine the core `stage` field with `if "stage" in vars(model).get("__annotations__", {})`. In my repro on 3.14, the class's `__annotations__` entry is absent from `vars()`, so `.get(...)` falls back to the empty-dict default and the membership test is always false — the guard never fires. The same repro on locked 3.13 materializes the annotations and the guard works. This matches Python 3.14's lazy-annotation behavior (PEP 649/749); `tests/test_stages.py::test_record_types_may_not_redefine_the_stage_field` fails on 3.14 for exactly this reason.
2. **The self-check fails.** `engine.selfcheck` reports `docs/plugin-guide.md` out of date on 3.14: the guide generator renders type annotations differently under 3.14 (`Optional[X]` → `X | None`), so the committed guide — which is correct for the locked 3.13 runtime, where selfcheck passes — no longer matches generated output.

**Impact:** a user installing on Python 3.14 gets a workspace where the plugin contract guard is a no-op and the project's own quality gate fails. I found no privilege-escalation path — the applier's op allow-lists still run — but an invariant the project explicitly tests for is unenforced on that interpreter.

**Recommended fix (two options):**
- **Quick:** pin `requires-python = ">=3.12,<3.14"` in `pyproject.toml` and note the limit in the install docs until 3.14 is supported.
- **Proper:** make the guard 3.14-safe. Note that simply checking `"stage" in model.model_fields` is wrong — `Record` already supplies the inherited core `stage` field, so the fix must distinguish the inherited field from a plugin's own redefinition (class-local annotation inspection that works on both runtimes, tested against valid plugins and against overrides). Make the guide generator produce canonical output independent of interpreter version. Then add 3.14 to the CI matrix so this class of break is caught.

### Finding 2 — E2E not verified locally (environment limitation, not a defect)

Playwright 1.56.1 refuses to install browsers on this sandbox's Ubuntu 26.04, so the 134 browser tests were not executed locally; the 5 errors in my first attempt were browser-launch failures, not application failures. The [CI run for this commit](https://github.com/skywalkr2/ProjectManagementAgent/actions/runs/39062677342) executed the "Browser tests with accessibility checks" step successfully on all three jobs, so browser behavior is verified by CI, not by me.

### Finding 3 — Generated guide depends on interpreter (subsumed by Finding 1)

The committed `docs/plugin-guide.md` is correct for the locked runtime (selfcheck passes on 3.13). The drift only appears under 3.14 and is cosmetic. The fix is canonical generator output (Finding 1, option B) rather than committing the 3.14-regenerated file, which would just move the failure to the CI runtime.

---

## 5. What is working well

- The check pipeline in `CLAUDE.md` is real and CI-enforced: ruff, format, 3,737 pytest tests, a 17-part self-check, 1,070 frontend tests, a typed build, and browser tests with accessibility checks, on every push.
- The person-only op guard (`_from_pm` in `engine/applier.py`) is carefully reasoned: it checks origin, trust level, and whether the content merely reports what someone else said.
- The safety-relevant paths I traced (spend defaults, credential references, backup encryption, read-only mail) are consistent with their documentation.
- Docs label unbuilt scope honestly, which makes them trustworthy to review against.

## 6. Prioritized next steps

1. Decide the Python 3.14 stance (pin `<3.14` now, or fix the guard + generator and add 3.14 to CI). The only change I'd make before new work on the branch.
2. Optional: sweep docs, code identifiers, and the generated guide together when the Thimbleby rename lands (phase I).
3. Optional: a scheduled CI job on the newest stable Python to catch interpreter-dependent breakage early.

## Limitations

- Browser tests verified via CI only; the sandbox OS cannot install Playwright's browsers.
- This pass covered documentation, claim-tracing of selected safety promises, and the validation pipeline on two interpreters. Not covered: a line-by-line audit of the engine (~37k lines) and React code, spend-limit enforcement logic, secret-storage permissions, backup encryption implementation details, and the plugin host's full loading path.
- The working tree was left pristine; nothing was committed or pushed.
