# O1: 30 fictional threads where a promise ends, as evaluation cases

**Why:** the daily steward's first job is to remember promises and notice when they end. Before real use it is
measured on fictional cases. There are 56 thread cases today (`thread-t01` to `thread-t25`); more varied endings make the
measurement trustworthy.

**Read first** (in the repository, branch `claude/tender-tesla-16a8ob`):
- `workspaces/demo-b/evals/thread-t01-m3-done.yaml` and four or five other `thread-*.yaml` files: the format.
- `workspaces/demo-b/evals/promise-people.yaml`: the people every case uses. PER-1 is the person the workspace is for
  (Avery Lane); PER-101 onward are the others. Use only these people and their `example.com` addresses.
- `docs/project/steward-scenarios.md` and `docs/project/steward-promise-threads.yaml`: the kind of situations meant.

**Produce:** 30 files, `workspaces/demo-b/evals/thread-t26-m<N>-<word>.yaml` to `thread-t55-…`, each one message of a
thread arriving with the earlier messages quoted below it, as in `thread-t01-m3-done.yaml`. Each file has `id` (the
file name without `.yaml`), `title`, `skills`, `received`, `given_file: promise-people.yaml`, `given` (the open promise
as an `action` record, as in the examples), `pasted` (the new message with the thread quoted), `expect`, `forbid` and
`stub_answer` (the ideal answer, whose ops match `expect`).

**Cover these endings**, about five cases each, and mix work and personal life (a freelancer's client, a landlord, a
school, a contractor, a friend):
1. Kept, said in other words ("it's attached", "went out this morning", "you should have it now"): `action.close`.
2. Kept by someone else on the person's behalf: `action.close`, and nothing else changed.
3. Called off or no longer needed: `action.drop`.
4. Moved to a new date, written in words ("let's say the 14th instead", "after the holidays"): `action.move`.
5. Partly delivered, with what is left said: `action.part`.
6. **Not** an ending: a thank-you, an "I'll look at it", a question back, or a reply about something else.
   `action.news` or nothing, and `forbid` the close, drop and move.

**Rules:**
- Use only ops and fields that already appear in the existing `thread-*.yaml` files. Don't invent new ones.
- Every `evidence.quote` must be words that appear exactly in `pasted`.
- No real names, companies, products or places; dates in late 2026; `received` on or after the quoted messages' dates.
- Vary the writing: short and long, formal and casual, typos, signatures, a forwarded message, a reply above a long
  quote.

**How it is checked:** `uv run cockpit evaluate --from workspaces/demo-b --stub --case <id>` for every new case (the
stub answers with `stub_answer`, so a failure means the case contradicts itself), then the self-check's specificity
scan (`uv run python -m engine.selfcheck`), then a read. If you can run commands, run both and include the output.
