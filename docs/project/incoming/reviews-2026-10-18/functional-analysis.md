# Functional Analysis: PM Cockpit Core

**Branch:** `claude/tender-tesla-16a8ob` · **Commit:** [`c7d221f`](https://github.com/skywalkr2/ProjectManagementAgent/tree/c7d221f3b65327fe5816b799c9afed584117ad22) · **Analyzed:** 2026-10-18

**Method:** I ran the application live (fresh scratch workspace, server on 127.0.0.1:8765, locked Python 3.13 runtime), exercised the core flows through the real API, and traced the daily-steward (Phase S) capabilities into their production callers. AI-dependent paths were driven by a mock endpoint speaking the chat-completions format through the **production adapter** — a mock-backed integration test, not a real AI run. It verifies transport, schema validation, application, and review behavior; it does not verify any real model's extraction quality or judgment (that is `cockpit evaluate` and the owner-validation phase's job).

---

## 1. The product answer, in short

**What is good:** the existing core provides a working capture, internal-change, review and recovery foundation. Intake through internal application, review and undo was exercised end-to-end, with honest empty states, verbatim-citation checking on answers, and working backup/restore.

**What is missing:** the next daily-assistant capabilities are incomplete. Several deterministic building blocks for the [Phase S daily steward](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/project/roadmap-to-1.0.md) — the layer the owner's 2026-10-17 decision names as the reason to choose the product — are implemented and tested, but **I found no production wiring for them at the reviewed commit**. Other accepted Phase S workflows (promise records and resolution, the publisher and mail/calendar actions, reminders as a system, briefs, areas, capture) remain open in the roadmap. The publisher (acting on mail/calendar after a yes) is now scheduled as S1b, brought forward from C4, and is the gate through which any of that work could reach another person.

**The core-versus-pack boundary:** writing and PM/publishing support are deliberately packs (phases C/P), not core. The core's stated destination is the steward.

---

## 2. What I verified live

Two separate scenarios, run in one scratch workspace.

**Scenario A — the loop and the undo defect (unowned actions, a question, a fact):**

| Step | Observed |
|---|---|
| Hand in a note, no AI account | Request refused on Today with a plain-words reason ("no AI account is set up for the 'routine' tier") |
| Add a local account; retry; press Go | Run started through the real adapter |
| Malformed ops | Refused with the exact op and its allowed fields ("action.hold … takes: op, id, waiting_for, evidence") |
| Valid ops | Applied as a changeset while the request entered review |
| "Looks good" | Review acknowledged; item left Today |
| Undo | All ops restored in reverse; changeset `undone`; a correction-learning signal queued |

**Scenario B — owned actions and calendar events:**

| Step | Observed |
|---|---|
| Hand in a note with owned actions + a meeting | 2 owned actions applied with due dates; 1 event applied; a second event **refused** because its evidence quote was not verbatim in the input |
| Today todo | Both actions listed with dues and origin tracing (changeset + request) |
| Today agenda | Empty — correctly, the default window is today + 1 day and the event is two days out |
| Ask | An answer op was rejected for an unmatched quote, then accepted with a matching quote and its cite's source tracked — verbatim citation validation. This does not establish semantic support for every assertion in the answer. |

**Cross-cutting:** backup wrote dated folders; `cockpit restore` completed and reported 26 records and 536 logged changes into a new workspace without modifying the backup (no corruption was observed; I did not diff the restored ledger against the original). The AI account test judged a fictional case precisely ("It was asked for one proposal and gave 4"). The follow-ups view lists open questions per person.

**What the review click means:** internal changes can apply before review; "Looks good" acknowledges that review. The approval gate the README actually promises — "you approve everything that goes **out**" — is the publisher, which is not built. That phrasing is accurate; the nuance is worth keeping in mind when reading the flow.

---

## 3. The defect: orphaned "Pick an owner" questions after undo

**Reproduced in Scenario A. A user-blocking dead-end state, not an application-wide failure.**

1. Unowned actions in a changeset auto-generate "Pick an owner" questions with `resolves: {action: ACT-1, changeset: CS-1, kind: owner}`.
2. Undoing the changeset removes the actions but does **not** retire the routing questions. They remain on Today pointing at records that no longer exist.
3. **Answering returns a raw 500.** Root cause at [`engine/applier.py:2096`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/applier.py#L2096): `pick_owner` does `a = tx.get("action", action_id)` and then `a.version` without a `None` check. The same crash occurs on the dedicated pick-owner endpoint.
4. **Dropping is refused** (409, "holds something that waits for the answer").
5. `reply` returns 200 but does not clear the obsolete owner decision — it is not a resolution.

**Fix, two layers:**
- **Recovery for existing stale questions:** guard `pick_owner` (missing action → a plain-words `StoreError`), and allow dropping a routing question whose action no longer exists. Preserve question history; do not delete questions that were subsequently answered or edited.
- **Lifecycle correction:** undo should retire unresolved routing questions whose underlying work it removed. Add a regression test that undoes a changeset with unowned actions and asserts the questions are retired or answerable.

---

## 4. Daily-steward outcomes: what exists, what is wired, what is open

Each row labels the evidence honestly: **observed working**, **helper implemented but no wiring found**, **open in roadmap**, or **not independently verified**.

| User outcome (Phase S commitment) | State | Evidence |
|---|---|---|
| **Remember commitments both ways** — promises from mail and notes, and how they resolve | **Helpers built, no wiring found; lifecycle open** | [`due_phrases`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/due_phrases.py), [`mail_threads`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/mail_threads.py), [`automatic_mail`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/automatic_mail.py), [`reply_split`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/reply_split.py) have tests and no production callers I found. Promise records, resolution, partial delivery, correction, and the five-minute onboarding journey remain [roadmap items](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/project/roadmap-to-1.0.md). |
| **Act after approval** — the publisher, mail/calendar actions | **Open (S1b)** | No publisher module; the [roadmap](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/project/roadmap-to-1.0.md) brings it forward from C4. [`itip`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/itip.py) (reading invitations) is built and unwired; sending waits for the publisher. The publisher is required for the application itself to execute approved outbound mail/calendar actions; read-only assistance and user-mediated follow-through are distinct. |
| **Help manage the day** — reminders, capacity, clashes, free slots, attention | **Helpers built, no wiring found; systems open** | [`reminders`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/reminders.py), [`capacity`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/capacity.py), [`free_slots`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/free_slots.py), [`clashes`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/clashes.py), [`attention`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/attention.py) have tests and no production callers I found. Persistence, snooze, wake recovery, notifications, repeating to-dos and briefs are [roadmap items](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/project/roadmap-to-1.0.md). |
| **Prepare for people and meetings** | **Foundation observed; prep and people memory open** | The follow-ups view works (observed). Meeting prep, after-meeting capture and richer people memory are roadmap items. |
| **Handle personal and work context** — document dates, bookings, bills, areas, capture | **Helpers built (bookings, bill dates), no wiring found; areas and capture open** | [`bookings`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/bookings.py), [`bill_dates`](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/engine/bill_dates.py) have tests and no production callers I found. Areas, isolation and capture routes are [roadmap items](https://github.com/skywalkr2/ProjectManagementAgent/blob/c7d221f3b65327fe5816b799c9afed584117ad22/docs/project/roadmap-to-1.0.md). |
| **Demonstrate improvement** | **Learning scheduled, not executed; outcome measurement open** | A correction signal was queued for the next batch (observed); the executed result was not observed. The Quality-screen outcome measurements are roadmap items. |

**How I checked the wiring:** repository-wide search at the reviewed commit for each module name across tracked Python, TypeScript and YAML, excluding tests and the module's own file — import forms, bare names, and plugin code. The bare-name hits I found for "attention" and "reminders" were English words in docstrings, not references. This is a scoped conclusion from search, not an exhaustive call-graph proof: *I found no production wiring for these twelve tested rule helpers at the reviewed commit.*

---

## 5. Capability and gap matrix

| Capability | State | Evidence |
|---|---|---|
| Intake → AI → review → undo | **Observed working** | Both scenarios above |
| Verbatim citation validation on answers | **Observed working** | Rejected an unmatched quote; accepted a matching quote |
| Follow-ups view | **Observed working** | `/api/followups` populated |
| Backup + restore | **Observed working** | Restore reported 26 records / 536 changes |
| AI account quality gate | **Observed working** | "asked for one proposal, gave 4" |
| Records (project) CRUD | **Partially verified** | Project created; full round-trip not exercised |
| Correction learning | **Scheduled, not executed** | Signal queued; result not observed |
| Search / retrieval effectiveness | **Not independently verified** | Mock-backed ask does not establish it |
| The twelve steward helpers | **Built + tested, no wiring found** | Section 4 |
| Publisher / acting on mail & calendar (S1b) | **Open in roadmap** | No module |
| Mail/calendar live sync | **Not independently verified** | Empty without connections; unit/CI coverage only |
| Audiences | **Open** | Design says so |
| Writing / PM packs | **Deliberately packs** | Phases C/P |

---

## 6. Prioritized recommendations

1. **Fix the user-blocking undo defect first** (section 3): the recovery guard, the drop allowance, the undo cascade, and a regression test.
2. **Complete the S1 promise-tracking slice** — following the owner's chosen order (promises and how they end come first), not as one undifferentiated "wire all twelve helpers" task. That means wiring `due_phrases`/`mail_threads`/`automatic_mail`/`reply_split` into intake, building the promise records and resolution flow on top, and delivering the five-minute first success.
3. **Build the publisher (S1b)** — it is required for the application itself to execute approved outbound mail/calendar actions; read-only assistance and user-mediated follow-through are distinct.
4. **Observe an executed learning result** to close the improvement loop.

---

## Limitations

- The AI was a mock through the production adapter — a transport and validation test, not a model-quality test.
- Mail/calendar live sync, and the steward rules with real data, were not exercised live. CI's browser suite passed for this commit; its feature coverage was not audited. The steward helpers have unit tests, but their integrated workflows were not independently verified. The integration claim in section 4 comes from reference search, not from observing rule behavior.
- The browser UI was not driven (API-level only).
- Learning was verified as scheduled, not executed; full records edit/remove and the follow-up chase round-trip were not exercised.
- Everything ran in scratch directories under /tmp; nothing was committed to the repo.
