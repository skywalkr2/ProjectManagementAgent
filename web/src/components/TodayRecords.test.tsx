import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { forgetMoves } from "../lib/moves";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// The Today lines that ask about a held item, about what to check after something moved, and about unfiled work
// (design 7.6, 7.7, 7.14; designer answers 27 and 28; open promise P14).

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  const group: Line["group"] = ["held", "moved", "decision", "question"].includes(kind) ? "decide" : "review";
  return { key: `${kind}:1`, group, kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const held = (ask: S["HeldAsk"], over: Partial<Line> = {}) =>
  line("held", { key: "held:CS-1:0", changeset: "CS-1", op: 0, text: "Close action", waiting: "This rests on something worked out, not something anyone said: close it?", held: ask, ...over });

const question = (id: string, title: string): S["FollowupQuestion"] => ({
  id,
  title,
  text: "",
  links: [],
  kind: "decision",
  status: "open",
  sent: null,
  waiting_days: null,
  chase_due: false,
  chases: 0,
  about: null,
  options: [],
});

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
    "GET followups": () => [{ person: "PER-1", name: "Pat Example", is_pm: true, questions: [question("Q-1", "Should the due day move?"), question("Q-2", "Does the plan still hold?")], actions: [], message: "", to_send: 0 }],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  const onView = vi.fn();
  const onOpenRecord = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={onOpenRecord} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { calls, onView, onOpenRecord };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
  forgetMoves();
});

const rowOf = async (title: string) => (await screen.findByRole("group", { name: title })) as HTMLElement;

// ---- held for a look ------------------------------------------------------------------------------------------------

test("a held close is the action as a question, the reason and the words it rests on first, and two answers that say what they do", async () => {
  show([held({ ask: "close", item: "Send two spine options", quote: "both spines are in the shared folder", told: [] })]);
  const row = await rowOf("Close 'Send two spine options'?");
  expect(within(row).getByText("Waiting for you")).toBeInTheDocument();
  expect(row).toHaveTextContent("This rests on something worked out, not something anyone said: close it?");
  expect(row).toHaveTextContent("“both spines are in the shared folder”");
  expect(within(row).getByRole("button", { name: "Close it" })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Keep it open" })).toBeInTheDocument();
  // Never the generic words that make the person read the title again.
  expect(within(row).queryByRole("button", { name: /Do it anyway|Leave it|Decide/ })).toBeNull();
});

test("the primary releases the item and says what happened, with Undo for that item", async () => {
  const user = userEvent.setup();
  const { calls } = show([held({ ask: "close", item: "Send two spine options", told: [] })], {
    "POST changesets/CS-1/ops/0/release": () => ({ ok: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
  });
  await user.click(within(await rowOf("Close 'Send two spine options'?")).getByRole("button", { name: "Close it" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/0/release")).toBe(true));
  expect(await screen.findByText("Done: 'Send two spine options'")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-1/undo")?.body).toEqual({ ops: [0] }));
});

test("the other answer keeps things as they are, says so with Undo, and records no change to the item", async () => {
  const user = userEvent.setup();
  const { calls } = show([held({ ask: "close", item: "Send two spine options", told: [] })], {
    "POST changesets/CS-1/ops/0/decline": () => ({ ok: "CS-1" }),
    "POST changesets/CS-1/ops/0/undecline": () => ({ ok: "CS-1" }),
  });
  await user.click(within(await rowOf("Close 'Send two spine options'?")).getByRole("button", { name: "Keep it open" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/0/decline")).toBe(true));
  expect(calls.some((c) => c.route.includes("/release"))).toBe(false);
  expect(await screen.findByText("Kept as it was: 'Send two spine options'")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/0/undecline")).toBe(true));
});

test.each([
  [{ ask: "date", item: "Book a photographer", value: "2026-11-05", from_value: "2026-10-30", told: [] } as S["HeldAsk"], "Change the due date of 'Book a photographer' to " + day("2026-11-05") + "?", "Change it to " + day("2026-11-05"), "Keep " + day("2026-10-30")],
  [{ ask: "owner", item: "Book a photographer", to_name: "Robin Sample", from_value: "Ana Person", told: [] } as S["HeldAsk"], "Give 'Book a photographer' to Robin Sample?", "Give it to Robin", "Keep Ana"],
  [{ ask: "routing", item: "Which bio?", to_name: "Jordan Pike", from_value: "Ana Person", told: [] } as S["HeldAsk"], "Send 'Which bio?' to Jordan Pike instead?", "Send it to Jordan", "Keep it with Ana"],
  [{ ask: "drop", item: "Agree the trim size with the printer", told: [] } as S["HeldAsk"], "Drop 'Agree the trim size with the printer'?", "Drop it", "Keep it"],
  [{ ask: "owner", item: "Book a photographer", to_name: "Robin Sample", told: [] } as S["HeldAsk"], "Give 'Book a photographer' to Robin Sample?", "Give it to Robin", "Keep it as it is"],
])("a held %# is titled as a question and its buttons name the result", async (ask, title, primary, other) => {
  show([held(ask)]);
  const row = await rowOf(title);
  expect(within(row).getByRole("button", { name: primary })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: other })).toBeInTheDocument();
});

test("a drop of something that reached someone says so in bold, with who and when", async () => {
  show([held({ ask: "drop", item: "Send the interior file", told: ["Robin Sample", "Casey Moor"], told_on: "2026-10-10" })]);
  const row = await rowOf("Drop 'Send the interior file'?");
  const strong = row.querySelector("strong");
  expect(strong).toHaveTextContent(`Robin Sample, Casey Moor were told on ${day("2026-10-10")}`);
});

test("a held item the engine doesn't shape as a question is still shown by its label, as before", async () => {
  show([line("held", { key: "held:CS-2:0", changeset: "CS-2", op: 0, text: "Add a way to reach Jordan", waiting: "A way to reach someone waits for your confirmation." })]);
  const row = await rowOf("Review a waiting change");
  expect(row).toHaveTextContent("Add a way to reach Jordan");
  expect(within(row).getByRole("button", { name: "Decide" })).toBeInTheDocument();
});

// ---- after a move -------------------------------------------------------------------------------------------------

const moved = (over: Partial<S["AfterMove"]> = {}, line_: Partial<Line> = {}): Line =>
  line("moved", {
    key: "moved:REQ-9",
    count: 2,
    text: "Print sync",
    due: "2026-10-22",
    changeset: "CS-9",
    questions: ["Q-1", "Q-2"],
    after_move: { kind: "event", record: "EVT-1", title: "Print sync", to: "2026-10-22", earlier: false, by: "pm", replaced: false, request: "REQ-9", changeset: "CS-9", others: [], ...over },
    ...line_,
  });

test("the questions after one move are one line under the move with how many things to check, who moved it and who else was asked", async () => {
  show([moved({ others: ["Casey Moor"] })]);
  const title = `Print sync moved to ${day("2026-10-22")} · 2 things to check`;
  const row = await rowOf(title);
  expect(within(row).getByText("Moved")).toBeInTheDocument();
  expect(row).toHaveTextContent("From your edit");
  expect(row).toHaveTextContent("1 question also went to Casey Moor (in Follow-ups)");
  expect(within(row).getByRole("button", { name: "Look closer" })).toBeInTheDocument();
});

test("an earlier move says so, since those are the risky ones; a move the assistant read says where it came from", async () => {
  show([moved({ earlier: true, by: "assistant" })]);
  const row = await rowOf(`Print sync moved earlier to ${day("2026-10-22")} · 2 things to check`);
  expect(row).toHaveTextContent("From a change the assistant read in something that came in");
});

test("looking closer opens one row for each thing to check, each with its own answer", async () => {
  const user = userEvent.setup();
  show([moved()]);
  const row = await rowOf(`Print sync moved to ${day("2026-10-22")} · 2 things to check`);
  await user.click(within(row).getByRole("button", { name: "Look closer" }));
  expect(await within(row).findByText("Should the due day move?")).toBeInTheDocument();
  expect(within(row).getByText("Does the plan still hold?")).toBeInTheDocument();
});

test("the group's menu opens the meeting and undoes the follow-on run", async () => {
  const user = userEvent.setup();
  const { calls, onOpenRecord } = show([moved()], { "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }) });
  const row = await rowOf(`Print sync moved to ${day("2026-10-22")} · 2 things to check`);
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Open Print sync" }));
  expect(onOpenRecord).toHaveBeenCalledWith("event", "EVT-1");
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Undo the move's follow-on run" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("a question that is alone after a move is a normal row that says what it came after", async () => {
  show([
    line("decision", {
      key: "question:Q-1",
      text: "Should the due day move?",
      question: "Q-1",
      after_move: { kind: "event", record: "EVT-1", title: "Print sync", to: "2026-10-22", earlier: false, by: "pm", replaced: false, request: "REQ-9", changeset: "CS-9", others: [] },
    }),
  ]);
  const row = await rowOf("Should the due day move?");
  expect(row).toHaveTextContent(`because Print sync moved to ${day("2026-10-22")}`);
});

// ---- unfiled work ---------------------------------------------------------------------------------------------------

test("Today has one line for unfiled work with its count, and File them goes to the projects", async () => {
  const user = userEvent.setup();
  const { onView } = show([line("unfiled", { key: "unfiled", group: "review", count: 4 })]);
  const row = await rowOf("File 4 items under a project");
  expect(within(row).getByText("Unfiled")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "File them" }));
  expect(onView).toHaveBeenCalledWith("records/projects");
});

test("a line for one unfiled item reads in the singular", async () => {
  show([line("unfiled", { key: "unfiled", group: "review", count: 1 })]);
  expect(await rowOf("File 1 item under a project")).toBeInTheDocument();
});

test("with nothing unfiled there is no line and no zero", async () => {
  const { calls } = show([line("unfiled", { key: "unfiled", group: "review", count: 0 })]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET today/queue")).toBe(true));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByText(/File 0 items/)).toBeNull();
  expect(screen.queryByRole("group", { name: /under a project/ })).toBeNull();
});

// ---- each row after a move has its own answers (design 7.7, answer 27) ---------------------------------------------------

const dateCheck: S["AfterMoveCheck"] = { kind: "date", action: "ACT-4", version: 6, text: "Send the interior file to the printer", from_day: "2026-10-20", to_day: "2026-10-22" };
const planCheck: S["AfterMoveCheck"] = { kind: "plan", record: "EVT-1" };
const withRows = (over: Partial<S["AfterMove"]> = {}) => moved({ rows: [{ question: "Q-1", check: dateCheck }, { question: "Q-2", check: planCheck }], ...over });

/** Today with a moved group, opened to its rows. */
async function opened(extra: Routes = {}, group: Line = withRows()) {
  const user = userEvent.setup();
  const { calls } = show([group], extra);
  const row = await rowOf(`Print sync moved to ${day("2026-10-22")} · 2 things to check`);
  await user.click(within(row).getByRole("button", { name: "Look closer" }));
  await within(row).findByText("Should the due day move?");
  return { user, row, calls };
}

const body = (calls: Array<{ route: string; body: unknown }>, route: string) => calls.find((c) => c.route === route)?.body;

test("a date question has Move it to the new day as its answer and Keep the old day beside it, both visible", async () => {
  const { row } = await opened();
  expect(within(row).getByRole("button", { name: `Move it to ${day("2026-10-22")}` })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: `Keep ${day("2026-10-20")}` })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "It holds" })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Needs a change…" })).toBeInTheDocument();
  expect(within(row).queryByRole("textbox", { name: "Your answer" })).toBeNull();
});

test("a question with no structured answer keeps its own answer form", async () => {
  const { row } = await opened({}, moved({ rows: [{ question: "Q-1", check: null }, { question: "Q-2", check: planCheck }] }));
  expect(within(row).getByLabelText(/answer/i, { selector: "textarea" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: /^Move it to/ })).toBeNull();
});

test("Move it changes the action's day as the person's own edit, answers the question and offers Undo", async () => {
  const { user, row, calls } = await opened({
    "POST records/edit": () => ({ changeset: "CS-20" }),
    "POST questions/Q-1/answer": () => ({ ok: "Q-1", request: null }),
    "POST changesets/CS-20/undo": () => ({ restored: [0], skipped: [] }),
  });
  await user.click(within(row).getByRole("button", { name: `Move it to ${day("2026-10-22")}` }));
  await waitFor(() => expect(body(calls, "POST records/edit")).toEqual({ kind: "action", id: "ACT-4", fields: { due: "2026-10-22", due_words: null, due_check: false }, read_version: 6 }));
  await waitFor(() => expect(body(calls, "POST questions/Q-1/answer")).toEqual({ text: `Moved it to ${day("2026-10-22")}.` }));
  expect(await screen.findByText(`Moved it to ${day("2026-10-22")}.`)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-20/undo")).toBe(true));
});

test("Keep answers the question and changes nothing", async () => {
  const { user, row, calls } = await opened({ "POST questions/Q-1/answer": () => ({ ok: "Q-1", request: null }) });
  await user.click(within(row).getByRole("button", { name: `Keep ${day("2026-10-20")}` }));
  await waitFor(() => expect(body(calls, "POST questions/Q-1/answer")).toEqual({ text: `Kept ${day("2026-10-20")}.` }));
  expect(calls.some((c) => c.route === "POST records/edit")).toBe(false);
});

test("It holds answers the plan question", async () => {
  const { user, row, calls } = await opened({ "POST questions/Q-2/answer": () => ({ ok: "Q-2", request: null }) });
  await user.click(within(row).getByRole("button", { name: "It holds" }));
  await waitFor(() => expect(body(calls, "POST questions/Q-2/answer")).toEqual({ text: "The plan still holds." }));
});

test("Needs a change opens a note with the cursor in it and sends it as the answer", async () => {
  const { user, row, calls } = await opened({ "POST questions/Q-2/answer": () => ({ ok: "Q-2", request: "REQ-30" }) });
  await user.click(within(row).getByRole("button", { name: "Needs a change…" }));
  const note = await within(row).findByRole("textbox", { name: "What should Helper change? Add a note." });
  await waitFor(() => expect(note).toHaveFocus());
  expect(within(row).getByRole("button", { name: "Send the note" })).toBeDisabled();
  await user.type(note, "Proof approval needs a later day");
  await user.click(within(row).getByRole("button", { name: "Send the note" }));
  await waitFor(() => expect(body(calls, "POST questions/Q-2/answer")).toEqual({ text: "The plan needs a change: Proof approval needs a later day" }));
});

test("settling the last row says the move is settled in one toast", async () => {
  // After the first answer the group is one row; answering that one settles the move.
  let current: Line[] = [withRows()];
  const alone = line("decision", {
    key: "question:Q-2",
    text: "Does the plan still hold?",
    question: "Q-2",
    after_move: { kind: "event", record: "EVT-1", title: "Print sync", to: "2026-10-22", earlier: false, by: "pm", replaced: false, request: "REQ-9", changeset: "CS-9", others: [], check: planCheck },
  });
  const user = userEvent.setup();
  const { calls } = show(current, {
    "GET today/queue": () => current,
    "POST questions/Q-1/answer": () => {
      current = [alone];
      return { ok: "Q-1", request: null };
    },
    "POST questions/Q-2/answer": () => ({ ok: "Q-2", request: null }),
  });
  const group = await rowOf(`Print sync moved to ${day("2026-10-22")} · 2 things to check`);
  await user.click(within(group).getByRole("button", { name: "Look closer" }));
  await user.click(await within(group).findByRole("button", { name: `Keep ${day("2026-10-20")}` }));
  // The row left of the group takes the group's place, still open, instead of waiting behind "1 new · Show".
  await waitFor(() => expect(document.querySelector('[data-line-key="question:Q-2"]')).not.toBeNull());
  expect(screen.queryByRole("button", { name: /new · Show/ })).toBeNull();
  const single = document.querySelector('[data-line-key="question:Q-2"]') as HTMLElement;
  await user.click(await within(single).findByRole("button", { name: "It holds" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST questions/Q-2/answer")).toBe(true));
  expect(await screen.findByText("Everything to check after Print sync moved is settled.")).toBeInTheDocument();
});

test("an answer that isn't the last says what it did and not that the move is settled", async () => {
  const { user, row } = await opened({ "POST questions/Q-1/answer": () => ({ ok: "Q-1", request: null }) });
  await user.click(within(row).getByRole("button", { name: `Keep ${day("2026-10-20")}` }));
  expect(await screen.findByText(`Kept ${day("2026-10-20")}.`)).toBeInTheDocument();
  expect(screen.queryByText(/is settled/)).toBeNull();
});
