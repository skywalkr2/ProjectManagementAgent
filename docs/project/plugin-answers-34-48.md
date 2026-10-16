# Answers to plugin rounds 34 to 48 (2026-10-16)

The outstanding questions from one pack's builder, rounds 34 to 48, answered together. Each answer says what the core
will do, the shape plugin authors will see, and when. Names here are the intended ones; the generated guide is the
contract, and a name is final only once it appears there. "Batch" means the first plugin API release of phase C (the
roadmap's C4), built right after phase B, in one release so a builder adapts once.

Checked against the code where an answer depends on today's behavior: a stage's label is required in `stages.yaml`
(`StageDefinition.label`, `min_length=1`), and the knowledge section is bounded by `knowledge.stable_budget` and
`knowledge.facts_budget` (characters).

## Reviewing and applying

**170, accepting part of an assistant's answer.** Yes, both halves. A task kind may label its answer's ops in groups
(`task_kind(..., groups=fn)`, `fn(op, view) -> label or None`, labels from the plugin's wording); the review shows one
row per group with Keep and Drop for the whole group, and the ops left out are recorded as dropped (a signal, like any
other rejection). Held ops of one changeset can also be released together ("Release all", one Undo). Batch.

**194, referring to a record created earlier in the same proposal.** Yes: `$new:<n>` in an op's fields names the
record op `n` of the same proposal or answer creates, resolved in order by the applier. An op that names a dropped,
refused or held op is refused with that reason, and the review says which op it depended on. Built in the applier by
the main session, with its tests. Batch.

**201, the test kit and requests in a proposal.** Yes: `ActionResult.apply(kept=..., requests=...)`, where
`requests` names the requests to keep (by index or id); the rest are dropped as on screen. Batch.

**205, `about: {item}` on a record the item changes.** Yes: it resolves to the record the item creates or, for an
edit, the record it changes. Batch.

## Records, references and placement

**197, a reference that doesn't block deletion.** Yes: `RefTo(kind, blocks_delete=False)`. Deleting the target
leaves the id in place; the screens show it as removed, and `view` reads it as a missing record, never an error.
Batch.

**200, where a record is written.** The rule today: a record is written in the folder of the project its field named
`project` points to, else at the workspace level. The guide will say so, and a record type may name the reference that
places it (`registrar.record_type(..., placed_by="<field>")`, or `placed_by=None` for always at the workspace level).
Batch.

**204, `where` through a reference.** Yes: `where` accepts a dotted path through one reference
(`{"<ref field>.<field>": value}`), on actions and on runs; deeper paths are refused at load. Batch.

**193, a task kind about either of two record kinds.** Yes: `on=("<kind a>", "<kind b>")`; the packet function's
context says which kind the target is (`context.target_kind`). One set of prompts, guidance and evaluation cases.
Batch.

**199, a part for work that isn't on long text.** Yes: a part may carry `address`, a small flat mapping the pack
defines (short strings, numbers, yes/no; at most 1 KB), compared for equality and never shown. `label` stays screen
wording. Batch.

**188, a plugin's own tag on a request.** Yes: `tag`, the same small flat mapping, set when the request is filed and
returned in `origin`, `view.part` and `PacketContext.request`; never shown and never sent to a model. Batch.

## Screens

**195, offering an action only when other records allow it.** Yes: actions take `show_for=fn(view, target)` (read
only, quick, no AI). The core also runs it again when the action is started, and refuses with the action's own
"not available" wording if it no longer holds. Batch.

**187, a preview beside a data form.** Yes: a data form may declare `preview=fn(view, settings, project, saved_file)`
returning a `Preview` (an image or a short document), run as the person, read only, after each save and on Refresh,
within a time limit that is a setting (`workspace.plugins.preview_seconds`, default 10). A preview that fails or runs
out of time says so beside the form and never blocks the save. Batch.

**189, a computed column's heading.** Yes: `computed={key: fn}` gains `computed_labels={key: "<wording key>"}`.
Batch.

**190, a conversation on a record.** Yes, as asked: a thread on any record, opened from any screen of that record's
work with the record in view as context (shown and clearable); each message a request of the task kind the pack names
for that record kind and stage; replies with citations to records, proposed changes kept or dropped inline, queued work
waiting for its go with its estimate, and questions answered by replying; older turns summarized; the core's search
(207) bringing in the history a message needs, at the data levels the accounts allow. It is the largest item here: it
builds on phase B's Ask side pane and on 207, so it comes after the batch, as the first item of phase C after the pack
is installed. The thread is kept as core records, so other packs get it too.

## Runs, packets and models

**207, the core's search for a pack's packets.** Yes: `view.search(words, kinds=(...), projects=(...), limit=N)` in
a packet function, the same bounded local search the core's own runs use, returning results with their sources, only
at the data levels the run's account is allowed, and logged on the run (what was searched for and what was sent).
Batch.

**210, the knowledge section and a pack's packet cap.** The core keeps its section within its own configured budgets
(`knowledge.stable_budget` and `knowledge.facts_budget`), and the pack can read the section's size before it builds
its parts (`context.knowledge_chars`). After adding the section, the core checks the pack's cap again; if the whole is
over, the core trims its own section first (narrow rules move to the per-input part, facts are cut by rank, both
counted in the packet), never the pack's parts, and a packet still over the cap fails the run before anything is sent,
with that reason. Batch.

**209, a `PacketContext` in the test kit.** Yes: `engine.plugin_api.testing.packet_context(...)` builds one from a
test workspace, with the knowledge section the core would add. Batch.

**191, a task kind that needs a large context.** Yes, worked out by the core: the packet's size is measured against
each model's context window (from the adapter's `models()`), the run goes only to a model whose window fits, and the
estimate names which. A run that fits nowhere says so before anything is sent. A task kind may also declare
`min_context=<tokens>` so the estimate can be given before the packet is built. Part of the capability routing (C0),
built in the batch.

**196, a role's tier and a task kind's tier.** The order becomes: the workspace's `ai.tasks.<kind>.tier`, then the
task kind's declared tier, then the role's tier, then the default. A declared tier is more specific than a role, so it
wins over it. Batch; the guide states the order.

**203, stable failures.** The contract is the failure's kind, never its text. Failures the plugin API raises will
carry a stable `code` from a documented list (the guide's table), and tests match the code. Text keeps improving.
Batch.

## Install and setup

**173, a pack's own libraries.** As accepted in round 35: a release lists every wheel it needs, its own and its
dependencies', each with its SHA-256, per platform tag. Install installs exactly those, never from a package index;
it shows what will be added first, refuses a conflict with the app's own packages and source-only packages, and
Remove takes out only what nothing else uses. `cockpit pack check` verifies the list. Phase C1.

**183, file types a pack needs.** Answered with 185: enabling a pack offers, as a setup step with the person's yes and
Undo, to add the media types its file kinds declare to `files.accepted_types`. The step can also read the effective
list. Batch.

**185, a setup step that adds to a list setting.** Yes: a step may suggest values to add to a list setting, applied as
a union with the person's own list, shown as "adds: …" before the yes. Batch.

## Guide and test kit corrections

**172.** All five, in the batch: `apply(kept=...)` is typed in the guide (a mapping of item id to yes/no);
`actions.preview(...).items` and `.groups` are documented as they are, or typed to match; the test kit runs the core's
list setup itself; the guide says `ws.save(path)` closes the old store; and `current_label` and `next_label` are a
stage's label from `stages.yaml`, which is required there, so they are `None` only when the record has no current or
next stage.

**184.** Yes: `ActionResult.topic`. Batch.

**186.** Intended: the form constructs the schema to get its defaults, so a whole-model "required unless" belongs in
the loader or a lint, not a model validator. The guide will say so next to "every field needs a default". Batch.

**206.** Confirmed: a request waiting for the go is `needs_you` with approval `required`. The guide will say so.
Batch.

## Already answered

202 (the core closes a superseded request in the same transaction), 208 (fixed in 0.3.70), 192 (0.3.61) and 198
(after 1.0, with per-role permissions for organization installs, design 11.8).
