import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { forgetMoves } from "../lib/moves";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// One decision is one Today line (design 7.6, 7.7, 7.14): a held op is asked once, under Decide, and its details hold only
// that decision; the review line of its change says how many wait there; what the assistant did is said in the past tense.

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  const group: Line["group"] = kind === "held" ? "decide" : "review";
  return { key: `${kind}:1`, group, kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const TITLE: S["ItemTitle"] = { kind: "email", person: "PER-2", person_name: "Pat Example", sender: null, topic: "Send two spine options" };
const ASK: S["HeldAsk"] = { ask: "close", item: "Send two spine options", record: "ACT-1", owners: ["Robin Sample"], told: [], quote: "both spines are in the shared folder", reporter: "Robin Sample" };
const WHY = "This rests on something worked out, not something anyone said.";

const heldLine = (over: Partial<Line> = {}) =>
  line("held", { key: "held:CS-1:1", changeset: "CS-1", request: "REQ-1", op: 1, text: "Close 'Send two spine options'", waiting: WHY, held: ASK, title: TITLE, ...over });

const reviewLine = (over: Partial<Line> = {}) =>
  line("review", {
    key: "review:REQ-1",
    request: "REQ-1",
    changeset: "CS-1",
    count: 1,
    subject: "Drop 'Settle the endpaper color'",
    did: { op: "action.drop", item: "Settle the endpaper color" },
    outcome: { actions_closed: 1 },
    deciding: ["held:CS-1:1"],
    title: TITLE,
    ...over,
  });

/** The change both lines come from: one op done and one waiting, with its own Looks good. */
const change = (): S["ChangeItem"] => ({
  id: "REQ-1",
  version: 1,
  dismissed: false,
  stage_task: false,
  first_go: false,
  refused: false,
  state: "review",
  waiting: null,
  created_at: "2026-10-09T14:00:00Z",
  note: null,
  source: "SRC-1",
  source_title: "Email from Pat Example",
  title: TITLE,
  changeset: {
    id: "CS-1",
    summary: "Dropped one to-do and closed another.",
    status: "applied",
    reviewed: false,
    trust: "untrusted",
    ops: [
      { index: 0, op: "action.drop", status: "applied", reason: null, group: "op0", title: "Settle the endpaper color", meta: { owners: [] }, evidence: null, record: { kind: "action", id: "ACT-2" }, ask: null },
      { index: 1, op: "action.close", status: "held", reason: WHY, group: "op1", title: "Send two spine options", meta: { owners: [] }, evidence: { quote: "both spines are in the shared folder" }, record: { kind: "action", id: "ACT-1" }, ask: null, held: ASK },
    ],
  },
});

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [change()],
    "GET followups": () => [],
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
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
  forgetMoves();
});

const rowOf = async (title: string) => (await screen.findByRole("group", { name: title })) as HTMLElement;
const detailOf = (row: HTMLElement) => row.querySelector<HTMLElement>("[id^='detail-']:not([id$='-title'])")!;

test("a review line says what the assistant did in the past tense, with its name, never as an order", async () => {
  show([reviewLine()]);
  const row = await rowOf("Helper dropped 'Settle the endpaper color'");
  expect(within(row).getByText("Review")).toBeInTheDocument();
  expect(screen.queryByText("Drop 'Settle the endpaper color'")).toBeNull();
});

test("a review line with no past-tense words for what was done keeps its own label", async () => {
  show([reviewLine({ did: { op: "plugin/unknown", item: "x" }, subject: "Do the other thing", deciding: [] })]);
  expect(await rowOf("Do the other thing")).toBeInTheDocument();
});

test("the decision stays a question under Decide, and the review line beside it says it waits there", async () => {
  show([heldLine(), reviewLine()]);
  const decide = await rowOf("Close 'Send two spine options'?");
  expect(within(decide).getByRole("button", { name: "Close it" })).toBeInTheDocument();
  const review = await rowOf("Helper dropped 'Settle the endpaper color'");
  expect(review).toHaveTextContent("1 waits for you, under Decide");
  // The held decision is on one line only: the review line has no button that would settle it.
  expect(within(review).queryByRole("button", { name: /Close it|Keep it open/ })).toBeNull();
});

test("Go to what waits opens the held line's details", async () => {
  const user = userEvent.setup();
  show([heldLine(), reviewLine()]);
  const review = await rowOf("Helper dropped 'Settle the endpaper color'");
  await user.click(within(review).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Go to what waits" }));
  const decide = await rowOf("Close 'Send two spine options'?");
  expect(await within(decide).findByText("Why it waits")).toBeInTheDocument();
});

test("a held line opens on only its decision: the question, the words and who said them, where it came from, why it waits, and the two answers", async () => {
  const user = userEvent.setup();
  show([heldLine(), reviewLine()]);
  const row = await rowOf("Close 'Send two spine options'?");
  await user.click(within(row).getByText("Waiting for you"));
  const detail = detailOf(row);
  expect(detail).toHaveTextContent("“both spines are in the shared folder” · Said by Robin Sample");
  expect(detail).toHaveTextContent("Where it came from");
  expect(detail).toHaveTextContent("Email from Pat Example · Send two spine options");
  expect(detail).toHaveTextContent(`Why it waits${WHY}`);
  expect(within(detail).getByRole("button", { name: "Close it" })).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Keep it open" })).toBeInTheDocument();
  // Never the change it came from: not its Looks good, not its other ops, not a label that says something was already done.
  expect(within(detail).queryByRole("button", { name: /Looks good/ })).toBeNull();
  expect(detail).not.toHaveTextContent("Settle the endpaper color");
  expect(detail).not.toHaveTextContent("Dropped a to-do");
  expect(detail).not.toHaveTextContent("Closed a to-do");
});

test("a held line's details do not say the question again: it is in the line's title once", async () => {
  const user = userEvent.setup();
  show([heldLine(), reviewLine()]);
  const row = await rowOf("Close 'Send two spine options'?");
  await user.click(within(row).getByText("Waiting for you"));
  const detail = detailOf(row);
  expect(await within(detail).findByText("Why it waits")).toBeInTheDocument();
  expect(within(detail).queryByText("Close 'Send two spine options'?")).toBeNull();
  expect(within(row).getAllByText("Close 'Send two spine options'?")).toHaveLength(1);
  // The section is still named by the question for a screen reader, without repeating it as text.
  expect(within(detail).getByRole("region", { name: "Close 'Send two spine options'?" })).toBeInTheDocument();
});

test("the answers in the details are the line's own answers, and the first one applies the held op", async () => {
  const user = userEvent.setup();
  const calls = show([heldLine()], { "POST changesets/CS-1/ops/1/release": () => ({ ok: "CS-1" }) });
  const row = await rowOf("Close 'Send two spine options'?");
  await user.click(within(row).getByText("Waiting for you"));
  await user.click(within(detailOf(row)).getByRole("button", { name: "Close it" }));
  await vi.waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/1/release")).toBe(true));
});

test("a held op the engine doesn't shape as a question opens as its own row, labelled as what it would do, and nothing around it", async () => {
  const user = userEvent.setup();
  const item = change();
  item.changeset!.ops[1] = { ...item.changeset!.ops[1], op: "person.contact", held: null, title: "A way to reach Jordan", reason: "A way to reach someone waits for your confirmation." };
  show([heldLine({ held: null, text: "Add a way to reach Jordan", waiting: "A way to reach someone waits for your confirmation." }), reviewLine()], { "GET changes": () => [item] });
  const row = await rowOf("Review a waiting change");
  await user.click(within(row).getByText("Waiting for you"));
  const detail = detailOf(row);
  expect(await within(detail).findByText("Would add a way to reach someone")).toBeInTheDocument();
  expect(within(detail).getByText("A way to reach Jordan")).toBeInTheDocument();
  expect(within(detail).queryByRole("button", { name: "Looks good" })).toBeNull();
  expect(detail).not.toHaveTextContent("Settle the endpaper color");
});

test("a held op's label on its change's card says what it would do, and the op that was done says what it did", async () => {
  const { WhatChanged } = await import("./WhatChanged");
  fakeApi({ "GET changes": () => [change()] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Would close a to-do")).toBeInTheDocument();
  expect(screen.getByText("Dropped a to-do")).toBeInTheDocument();
  expect(screen.queryByText("Closed a to-do")).toBeNull();
});

test("the lines that stop or ask for something use the queue's columns: one fixed pill column, so every title starts in line", () => {
  const read = (...parts: string[]) => readFileSync(join(__dirname, ...parts), "utf8");
  for (const css of [read("..", "shell", "HeldLines.module.css"), read("Learned.module.css"), read("..", "ui", "Row.module.css")]) {
    expect(css).toMatch(/grid-template-columns:\s*var\(--row-pill-w\)\s+minmax\(0,\s*1fr\)\s+auto/);
  }
  expect(read("..", "shell", "HeldLines.module.css")).not.toMatch(/\.line\s*\{[^}]*display:\s*flex/);
  expect(read("Learned.module.css")).not.toMatch(/\.todayLine\s*\{[^}]*display:\s*flex/);
});
