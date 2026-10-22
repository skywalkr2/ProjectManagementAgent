import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { RecordConversation } from "./RecordConversation";

// A conversation on a record (design 6.25, 6.32): what was said is kept on the record, an answer shows the words it rests
// on, each change it proposes is kept or dropped here, and work above the asked-about amount waits for the go.

type Turn = S["AskView"];

const turn = (id: string, over: Partial<Turn> = {}): Turn => ({
  id,
  version: 3,
  question: `Question ${id}`,
  state: "done",
  waiting: null,
  created_at: "2026-10-20T10:00:00+00:00",
  changeset: null,
  answer: null,
  proposals: [],
  reports: [],
  about: { kind: "action", id: "ACT-1" },
  waiting_for_go: false,
  estimate_usd: null,
  reviewed: false,
  ops: [],
  ...over,
});

const op = (index: number, title: string, status: "applied" | "held" | "refused" | "undone"): S["OpView"] =>
  ({ index, op: "action.add", status, reason: null, group: "g", title, meta: { owners: [] } }) as S["OpView"];

function show(turns: Turn[], routes: Routes = {}) {
  const calls = fakeApi({ "GET records/action/ACT-1/conversation": () => ({ kind: "action", id: "ACT-1", turns }), ...routes });
  renderApp(<RecordConversation kind="action" id="ACT-1" />);
  return calls;
}

test("a record with nothing said says so and has the box for the first message", async () => {
  show([]);
  expect(await screen.findByText("Nothing has been said about this yet.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Talk to Helper" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
});

test("sending a message posts it to the record and says it was sent", async () => {
  const user = userEvent.setup();
  const calls = show([], { "POST records/action/ACT-1/conversation": () => ({ id: "REQ-5" }) });
  await user.type(await screen.findByLabelText("What do you want to know, or have done?"), "What is this waiting on?");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/action/ACT-1/conversation")?.body).toEqual({ message: "What is this waiting on?" }));
  expect(await screen.findByText("Sent")).toBeInTheDocument();
});

test("the conversation is shown oldest first with each answer and the words it rests on", async () => {
  show([
    turn("REQ-1", { question: "What is this waiting on?", answer: { text: "The printer.", cites: [{ quote: "waiting on the printer", source: "help" }] } }),
    turn("REQ-2", { question: "Who owns it?", state: "running", waiting: "With the assistant, starting now" }),
  ]);
  await screen.findByText("The printer.");
  const items = Array.from(document.querySelectorAll<HTMLElement>("li.line"));
  expect(items[0]).toHaveTextContent("What is this waiting on?");
  expect(within(items[0]!).getByText("The printer.")).toBeInTheDocument();
  expect(within(items[0]!).getByText("“waiting on the printer”")).toBeInTheDocument();
  expect(items[1]).toHaveTextContent("Who owns it?");
  expect(items[1]).toHaveTextContent("Working on it");
});

test("each change the assistant proposes is listed; an applied one is dropped with Undo of only that op", async () => {
  const user = userEvent.setup();
  const calls = show(
    [turn("REQ-1", { question: "Add two to-dos", changeset: "CS-7", answer: { text: "Done.", cites: [] }, ops: [op(1, "Confirm the print date", "applied"), op(2, "Check the proof", "applied")] })],
    { "POST changesets/CS-7/undo": () => ({ restored: [2], skipped: [] }), "POST changesets/CS-7/looks-good": () => ({ ok: "CS-7" }) },
  );
  expect(await screen.findByText("Changes it suggests")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Drop: Check the proof" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-7/undo")?.body).toEqual({ ops: [2] }));
  await user.click(screen.getByRole("button", { name: "Keep all" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-7/looks-good")).toBe(true));
});

test("a change held for the person is kept or dropped, and a dropped one has no buttons left", async () => {
  const user = userEvent.setup();
  const calls = show(
    [turn("REQ-1", { changeset: "CS-8", ops: [op(0, "Close the old to-do", "held"), op(1, "Already dropped", "undone")] })],
    { "POST changesets/CS-8/ops/0/release": () => ({ ok: "CS-8" }), "POST changesets/CS-8/ops/0/decline": () => ({ ok: "CS-8" }) },
  );
  await user.click(await screen.findByRole("button", { name: "Keep: Close the old to-do" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-8/ops/0/release")).toBe(true));
  await user.click(screen.getByRole("button", { name: "Drop: Close the old to-do" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-8/ops/0/decline")).toBe(true));
  expect(screen.queryByRole("button", { name: "Drop: Already dropped" })).toBeNull();
});

test("work that waits for the go shows its estimate and a Go ahead button", async () => {
  const user = userEvent.setup();
  const calls = show([turn("REQ-1", { state: "needs_you", waiting_for_go: true, estimate_usd: 0.4 })], { "POST requests/REQ-1/go": () => ({ ok: "REQ-1" }) });
  expect(await screen.findByText("This waits for your go. It would cost about $0.40.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Go ahead" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/REQ-1/go")?.body).toEqual({ read_version: 3 }));
});
