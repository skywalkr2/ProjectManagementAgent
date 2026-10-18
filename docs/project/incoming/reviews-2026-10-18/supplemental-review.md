# Thimbleby: supplemental review and inputs to the path to 1.0

**Read fourth, after the three Perplexity reviews.**  
**Prepared:** 2026-10-18  
**Reviewed branch:** `claude/tender-tesla-16a8ob`  
**Reviewed commit:** `c7d221f3b65327fe5816b799c9afed584117ad22`

## 1. Purpose and how to use this document

This supplements **Thimbleby product review**, **PM Cockpit repo review**, and **PM Cockpit functional analysis**. It consolidates additional findings from an independent documentation-first review, code inspection, automated checks, and targeted reproductions. It also corrects conclusions in those reviews that are broader than their evidence.

The requested next step is to reconcile these inputs into the existing path to 1.0. Do not treat every recommendation here as an already approved design decision, create a competing roadmap, or mark work complete because a review describes its intended behavior. Verify each finding against the current branch: this document describes the pinned commit above, and subsequent work may have fixed it.

Preserve the repository's change-control process: record the impact of accepted scope/design changes, update the affected design sections and change summary, and reconcile the roadmap, charter, scope, risks, and open promises. Prefer extending an existing item over creating a duplicate. No repository implementation or roadmap changes were made during this review.

## 2. Combined assessment

The core has substantial foundations: transactional records and a ledger, explicit trust and operation boundaries, plugin separation, recovery paths, and extensive automated tests. The daily-steward direction is coherent, and the promise workflow is a sensible first complete outcome.

However, passing the existing suites does not establish that all safety promises hold. Targeted checks found defects in spending enforcement, credential saves, Undo, concurrent source editing, and file downloads. The documentation has strong structure and traceability but conflicting descriptions of current availability and acceptance.

The release should establish three things separately:

1. **Integrity:** internal changes, credentials, spending, and recovery obey their contracts.
2. **Integrated usefulness:** a real user can complete the promised workflow through the application.
3. **Behavioral dependability:** the assistant finds and resolves commitments accurately enough to reduce supervision on real inputs.

One passing category is not evidence that the others pass.

## 3. Corrections and qualifications to the preceding reviews

### 3.1 The repository verdict is too reassuring

The statement that Python 3.14 compatibility is the “one genuine defect” should be read as the finding from that review's limited coverage, not as the combined verdict. That review explicitly did not audit spending enforcement. The additional defects below should precede unrestricted new feature work.

### 3.2 Documentation quality and documentation currency are different

Keep the positive assessment of structure, explicit boundaries, and traceable decisions. Qualify the claim that the documents are well aligned with implementation. Current contradictions include hosted availability, outbound email scope, implemented safeguards marked unbuilt, and learning acceptance described as complete without the specified evidence.

The product rename itself is deliberately deferred to phase I; that is not a defect.

### 3.3 The old go/no-go and freeze are withdrawn

The product review credits these as current governance controls. `docs/project/charter.md:72` explicitly sets aside the go/no-go date; `docs/project/scope.md:67` sets aside the freeze. The risk register must use current controls, not retain withdrawn dates as mitigations.

### 3.4 Outcome measurement is still work to build

The proposed Quality-screen measures are useful design commitments. They should not be described as an implemented measurement system: the outcome-measurement item at `docs/project/roadmap-to-1.0.md:2110` remains unchecked.

### 3.5 Keep the Python and browser evidence precise

The Perplexity review's Python 3.13 comparison usefully narrows the Python 3.14 failures. Canonicalize generated type descriptions instead of merely regenerating the guide under a different interpreter. For the reserved `stage` field, distinguish a plugin's own override from the valid inherited field; checking only membership in `model_fields` would reject valid plugins.

Perplexity reports successful CI browser tests at the reviewed commit. This review observed two local phone-layout assertion failures using installed Chrome. Treat those as environment-specific failures needing reconciliation, not as established failures on every supported browser. The cited CI run was not independently rechecked in this review.

## 4. Verified defects to add to, or merge into, the work plan

File references below are repository-relative and refer to the reviewed commit. Completion tests are recommendations, not claims that the tests already exist.

### A. Enforce spending controls for every account actually called — high priority

**Observed:** the dispatcher checks the initial account's estimate, but fallback can execute a more expensive account without applying the same per-run limit or approval threshold. A mock-backed reproduction with a $0.25 per-run limit recorded a $1.50 backup call without approval. A separate reproduction reached an unpriced escalation account with `confirm_unpriced=True` and no approval.

**Evidence:** `engine/ai/router.py:267`; initial checks in `engine/dispatcher.py:206`; escalation condition at `engine/dispatcher.py:299`.

**Required outcome:** changing accounts, falling back, retrying, or escalating must not bypass the applicable spending policy. Approval must cover the work and cost basis actually presented to the user. Preserve intentional fallback behavior within those limits.

**Completion evidence:** deterministic fake-adapter tests for an inexpensive primary failing over to an over-limit backup, an unpriced backup/escalation, and a permitted fallback. Refused or unapproved calls must never reach the adapter. Also audit cumulative retry costs and task/record/day budgets for the same cause; those broader paths were not all independently reproduced here.

### B. Make credential writes transactional with settings saves — high priority

**Observed:** replacing an existing source password with a stale settings fingerprint returns HTTP 409 but still overwrites the working secret. Secret files are written before settings validation; cleanup removes newly created files only. Similar ordering exists for release tokens and AI account keys. Undo of a successful replacement also cannot recover the old bytes merely by restoring the same file reference.

**Evidence:** `api/setup_routes.py:496–503`, `555–560`, `713–730`, and the AI key write near `963–965` before its later settings save.

**Required outcome:** a rejected save changes neither settings nor credentials. A successful operation's Undo behavior must match its documented contract. Keep prior secret values out of logs, ordinary settings history, and the ledger.

**Completion evidence:** stale-fingerprint replacement leaves the old secret usable; settings-write failure restores prior state; partial multi-secret failure leaves no partial replacement; successful save and Undo follow the agreed secure recovery design. Exercise each affected credential entry point.

### C. Repair Undo's action/question/assignment lifecycle together — high priority

There are two distinct reproduced defects:

1. **Orphaned owner questions:** as the functional review reports, undoing creation of an unowned action removes the action but leaves its “Pick an owner” question open. This was independently reproduced; answering raises `AttributeError` because the action is absent.
2. **Earlier assignments undone by a later operation:** create an unowned action, assign its owner, put the action on hold, then undo only the hold. The result incorrectly loses the earlier owner and remains held instead of returning to owned/open.

**Evidence:** `engine/applier.py:2085–2106` and `_with_answers()` at `2287–2304`. The latter collects historical `action.assign` entries without limiting them to the operation whose ownership decision they belong to.

**Required outcome:** Undo reverses the selected work and its dependent effects while preserving unrelated prior decisions and later valid changes. Obsolete unresolved routing questions are retired when their underlying work disappears. Existing stale questions must have a safe recovery path and never produce a raw server error.

**Completion evidence:** cover both sequences above, shared routing questions, subsequently answered questions, later edits, partial/grouped Undo, and already-stale records. Preserve the ledger/history and conflict protections. Do not fix this solely with a null check.

### D. Prevent stale source forms from overwriting newer edits

**Observed:** a form retains old field values but fetches a fresh fingerprint immediately before submitting them all. Two forms opened at a 60-minute interval can silently overwrite each other: one saves 15 minutes; the other changes only the label and restores 60 minutes.

**Evidence:** `web/src/components/Sources.tsx:320–323` and `378–400`. The corresponding API request sequence returned success while overwriting the newer value.

**Required outcome:** conflict detection uses the snapshot the person actually edited, or a deliberate field-level merge checks the old values of changed fields. Refreshing a token alone must not authorize stale data.

**Completion evidence:** two-tab/source-edit test preserves the newer interval or presents a conflict without losing either person's input. Search other forms for the same fetch-fresh-fingerprint/send-stale-values pattern.

### E. Support international filenames in downloads

**Observed:** `日本語.txt` uploads successfully but downloading it returns HTTP 500. Unicode letters pass the filename filter and enter a header encoded as Latin-1.

**Evidence:** `api/routes.py:1078–1081`.

**Required outcome:** use an ASCII fallback and correctly encoded `filename*`, with safe handling of quotes and control characters.

**Completion evidence:** upload/download round trips for ASCII and non-Latin names preserve bytes and produce valid headers.

### F. Resolve declared Python support and generator portability

Merge this with the first repository review's finding rather than adding a duplicate. The declared `>=3.12` support range includes 3.14, where the reserved-field guard fails and the generated guide differs.

**Completion evidence:** the guard rejects class-local overrides and accepts valid inherited fields on every supported interpreter; generated documentation is stable across those interpreters; CI covers the declared support policy. Restricting the supported range is a possible interim decision, but must be explicit in installation requirements and documentation.

## 5. Documentation and acceptance reconciliation

Treat this as one bounded consistency task, with links to existing decisions and implementation:

| Area | Required reconciliation |
|---|---|
| Hosted mode | README lines 16–18 advertise hosting; `engine/cli.py:603–605` refuses it. State current local availability and label hosting as future work. |
| Outbound scope | Scope excludes v1 email channels and charter excludes email integrations; S1b now includes approved mail/calendar actions. Update the accepted scope baseline and remaining exclusions. |
| Safeguard status | Parts 10 and 12 still describe existing journey, fresh-workspace, Host/Origin, and knowledge-consumption checks as unbuilt. Update current-state tables or clearly label historical snapshots. |
| Setup cost | Distinguish explicitly initiated paid account checks from processing personal material. The blanket “nothing spent before Go” promise is inaccurate. |
| Learning acceptance | Separate implemented lesson retrieval from demonstrated behavioral improvement. Roadmap lines 327–333 require every learning pair and the day-30 expectations to pass; the evaluation history records incomplete/partial runs and continuing misses while closing O3. |
| Risks and promises | Replace withdrawn date/freeze mitigations; reconcile pending account evaluations and current commitments without silently closing them. |

Historical model failures do not prove the same failures remain at HEAD. Conversely, later code fixes do not prove the behavioral gate now passes. Require fresh evidence or an explicit approved change to the criterion.

Use a compact current-state index linking to the authoritative design, roadmap item, and evidence. Avoid duplicating another full set of status descriptions that will drift again.

## 6. Additions to the product and pilot recommendations

### 6.1 Measure omissions independently

Counting promises the assistant finds and the user keeps cannot reveal promises it missed. For a bounded, consented sample of real inputs, independently identify the commitments and their outcomes, then compare the assistant's results.

Measure at least:

- Commitments missed, out of commitments actually present.
- Incorrect commitments raised, out of commitments proposed.
- Wrong resolutions, particularly unfinished work incorrectly marked complete.
- Changed dates, cancellations, partial deliveries, and owner changes handled correctly.
- Review/correction time and continued duplicate checking.
- Coverage failures and delays: sources not read, partial reads, or stale data.

Report counts and denominators, not only percentages. Break results down by account/model and important commitment type so an average cannot conceal a weak case. Keep a separate evaluation set that is not repeatedly adjusted while developing the prompts.

The owner should approve thresholds before the acceptance run. This review does not invent numerical targets without a baseline. A material change to scoring or allowed outputs must be recorded, and before/after results must use comparable criteria.

### 6.2 Make the coverage contract visible

Users should be able to distinguish “nothing needs attention” from “the assistant could not check.” Define the selected sources, initial lookback window, last successful read, exclusions, delayed work, and limitations on older commitments. Do not present historical coverage that the onboarding process has not actually established.

### 6.3 Stage the pilot around proof of one workflow

Support the product review's proposed owner real-mail gate and external pilot. Make them explicit roadmap gates, not implied activities. The first integrated slice should demonstrate capture with evidence, ownership and dates, surfacing on Today, correction, and resolution across a bounded source set.

Track whether users spend less time supervising the system. Do not make abandoning their backup list an early pilot requirement; reduced duplicate checking should follow demonstrated reliability.

A read-only pilot can establish remembering and review value before the app performs external actions. It does not replace the separate S1b acceptance gate for executing approved actions, and any sequencing change requires an explicit design decision.

### 6.4 Give outbound actions their own failure and approval tests

Before S1b is accepted, test exact approved content and destinations, stale approvals after edits, duplicate execution after timeout/retry/restart, ambiguous remote success, revoked credentials, and malicious source content attempting to redirect an action. The user must be able to tell whether an action happened, failed, or has an uncertain result.

These are proposed acceptance requirements for the publisher, not claims that its current implementation is defective: the publisher is not yet built. Keep the existing trusted-plugin threat model explicit; do not imply the current in-process plugin host can sandbox arbitrary malicious installed code.

## 7. Proposed ordering within the existing path to 1.0

1. **Integrity fixes:** spending, credential-save atomicity, and both Undo defects. Reproduce first, fix siblings with the same cause, and add targeted regression tests.
2. **Remaining correctness and support:** stale source edits, international downloads, and Python support. Reconcile browser evidence and run the required complete checks at the verified integration point.
3. **Current-truth reconciliation:** align scope, documentation, risks, open promises, and learning acceptance status. This can accompany the relevant fixes rather than become a long separate phase.
4. **Complete the bounded promise workflow:** follow the accepted phase order, distinguishing helper completion from integrated user outcomes.
5. **Owner real-mail acceptance and external pilot:** preserve evidence, use agreed thresholds, and measure supervision as well as discovery.
6. **Broader expansion:** use those results to decide when later steward features and packs are justified. Preserve the long-term ambition without treating every accepted capability as a prerequisite for the first useful release.

For each accepted item, the revised roadmap should identify its existing phase, prerequisite, current state, observable user outcome, named acceptance evidence, and any owner decision still needed. Mark a helper as built when its tests pass; mark the user capability as built only when its integrated journey passes; mark behavioral acceptance only when the relevant real-model evaluation passes.

## 8. Subsequent progress: temporary public website

After the pinned repository review, the owner created the temporary coming-soon website in a separate repository, based on an existing site's layout. The setup conversation records a successful deployment and the owner confirming that the custom domain worked on their phone. This review inspected that conversation and its saved screenshot; a fresh fetch of the public domain through the web tool was unsuccessful, so current live availability was not independently established here.

The existing work includes the thimble-and-bow logo, burgundy/cream palette, light/dark variants, responsive layout, a Reginald introduction, and explicit in-development/no-download wording. The owner intends to continue developing it. Record this as completed temporary website and brand groundwork, and reuse it when planning public launch materials rather than commissioning the same work again.

Hosting the public website does not establish that the assistant itself supports hosted operation, that installers exist, or that pilot acceptance has passed. The hosted-product documentation finding therefore still stands. Future website copy, download links, and any tester recruitment flow should be aligned with the actual release state. The current temporary page is evidence of public-facing progress, not a new blocker or a reason to expand the core's scope.

## 9. Proposed standard bundle: mail and calendar integration

**Owner input after the review:** the owner is considering shipping the Gmail/Microsoft integration with the Windows and macOS installers, rather than requiring testers to find and install it separately, and asked whether it should become part of core. The recommendation below addresses that usability goal while preserving the existing architecture. It is a proposed packaging/setup decision for the design bot to reconcile, not an instruction to move vendor-specific code into core.

**Recommended decision:** “Mail and calendar integration ships with the standard installer; connecting accounts remains optional.”

Separate three choices:

- **Included in the installer:** bundle a compatible version of the integration so first-time users do not need a separate plugin-install step.
- **Offered during setup:** present Gmail and Microsoft account connection as normal setup choices, with a clear Skip option and a useful note/paste path for people who skip.
- **Authorized to read an account:** inclusion alone grants no account access. Reading begins only after the person connects an account and chooses the sources and scope to include. Preserve the existing approval rules for AI spending and outward actions.

**Classification:** an extension plus a packaging/setup change. Keep provider-specific authentication, APIs, and service behavior in the plugin. Keep generic messages, calendar events, commitments, source status, and approved outbound-action contracts in core. If bundling needs a missing capability, add a generic extension point rather than a special case for this plugin.

**Roadmap implications:** merge this into the existing installer, onboarding, and mail-integration work. Verify the integration's actual supported account types and capabilities before promising them in setup or release copy. Specify how the bundled version is selected, updated, disabled, and kept compatible with the core/plugin API; reinstallation or upgrade must preserve account settings and credentials. Reconcile the existing rule that core works without packs with the standard bundle: a bundled integration must still be optional to use, and the core must remain testable without it.

**Acceptance evidence for the invited pilot:**

1. Both installer bundles include the intended compatible integration, and account setup requires no separate plugin download, developer tools, or manual file editing.
2. A fresh installation can skip account connection and reach a useful result through note/paste intake.
3. Each account type advertised for the pilot completes sign-in and reads the selected sources on the supported operating system. Distinguish personal Microsoft accounts from employer-managed accounts; administrator consent, restrictions, or unsupported cases must be stated clearly rather than discovered as an unexplained failure.
4. Cancellation, expired/revoked sign-in, and reconnecting produce understandable states without losing existing work or silently widening source access.
5. Merely installing or enabling the bundle does not read accounts, incur AI spending, or execute outward actions without the applicable user choices and approvals.
6. Upgrade/reinstall preserves the person's configuration and credentials, and disabling the integration leaves the core's independent workflow usable.

**Pilot planning context:** the owner is aiming for Tuesday, October 20, 2026, to share the core and installer bundles with a small invited group. The owner will test macOS and a friend will test Windows. Treat this as the owner's current target, not evidence of readiness or a reinstatement of the previously withdrawn project-wide freeze. Start clean-machine installer and sign-in testing alongside the integrity fixes, and use the same short install-to-result-to-Undo-to-reopen journey on both platforms. Scope the pilot claims to what those tests actually establish.

## 10. Evidence and limits

At the reviewed commit this review observed: Python lint and formatting passed; 1,070 web unit tests passed; production build passed; 3,734 Python tests passed with three initial failures. The local-server failure passed outside the sandbox; the stage guard and generated-guide/self-check failures remained under Python 3.14. Browser testing using installed Chrome produced 132 passes and two phone-layout assertion failures. These results should not be merged with Perplexity's reported CI results as if all ran in the same environment.

Targeted reproductions established the spending, credential, source-edit, download, and Undo findings. They used temporary workspaces or fake adapters; no real paid model run was needed to establish those control-flow defects. This was not a line-by-line audit of the entire application, a cryptographic audit, or a real-world model-quality evaluation.

The technical-design update should preserve these evidence boundaries. The goal is a defensible path to 1.0: safe underlying operations, a complete promise workflow, and measured relief for the person using it.
