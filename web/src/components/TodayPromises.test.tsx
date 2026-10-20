import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// Promises on Today (design 6.33, 7.7): the line for a promise past its date with its choices, and the held ending that
// reads as one line the person keeps.

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  return { key: `${kind}:1`, group: "send", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const chase = (over: Partial<Line> = {}) =>
  line("promise", { key: "promise:ACT-1", person: "PER-2", person_name: "Robin Sample", text: "Send the floor plan", subject: "Send the floor plan", due: "2026-10-13", waiting_days: 3, actions: ["ACT-1"], ...over });
const own = (over: Partial<Line> = {}) => chase({ group: "risk", person: null, person_name: null, ...over });

const ending = (held: Partial<S["HeldAsk"]>, over: Partial<Line> = {}) =>
  line("held", {
    key: "held:CS-1:0",
    group: "decide",
    changeset: "CS-1",
    op: 0,
    text: "Close action",
    waiting: "Something that came in says this ended or moved: keep it, or change it.",
    held: { ask: "close", item: "Send the floor plan", record: "ACT-1", owners: ["Robin Sample"], reporter: "Ana Person", quote: "the floor plan went out this morning", told: [], ...held },
    ...over,
  });

const promise = (): S["PromiseView"] => ({
  action: "ACT-1",
  version: 4,
  text: "Send the floor plan",
  status: "open",
  quote: "I will send the floor plan by Tuesday.",
  owners: [{ id: "PER-2", name: "Robin Sample" }],
  mine: false,
  promised_to: [{ id: "PER-1", name: "Ana Person" }],
  due: "2026-10-13",
  due_words: "by Tuesday",
  due_check: false,
  basis: "said",
  said_by: null,
  origin: { kind: "source", source: "SRC-1" },
  news: [],
});

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
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
    "GET people": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    "GET promises/ACT-1": () => promise(),
    ...extra,
  });
  const onOpenRecord = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={onOpenRecord} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { calls, onOpenRecord };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const rowOf = async (title: string) => (await screen.findByRole("group", { name: title })) as HTMLElement;
const menuOf = async (user: ReturnType<typeof userEvent.setup>, row: HTMLElement) => user.click(within(row).getByRole("button", { name: /More actions for/ }));

// ---- a promise past its date ------------------------------------------------------------------------------------

test("a promise someone else owes is a line that starts with Chase, names the words and the day, and offers Followed up first", async () => {
  show([chase()]);
  const row = await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  expect(row).toHaveTextContent("3 days late, and nothing heard since");
  expect(within(row).getByRole("button", { name: "Followed up" })).toBeInTheDocument();
});

test("Followed up records the follow-up, which keeps the promise open, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([chase()], {
    "POST followups/PER-2/actions/ACT-1/followed-up": () => ({ on: "2026-10-16", previous_told: null, request: null }),
    "POST followups/PER-2/actions/ACT-1/unfollow": () => ({ ok: "ACT-1" }),
  });
  await user.click(within(await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`)).getByRole("button", { name: "Followed up" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")).toBe(true));
  expect(calls.some((c) => c.route.includes("/status"))).toBe(false);
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/unfollow")?.body).toEqual({ on: "2026-10-16", previous_told: null }));
});

test("the choices after Followed up are New date, Done and Drop; Done closes it with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([chase()], {
    "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: null }),
  });
  const row = await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  await menuOf(user, row);
  expect(screen.getByRole("menuitem", { name: "New date" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Drop" })).toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "done" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST actions/ACT-1/status").map((c) => c.body)).toEqual([{ status: "done" }, { status: "open" }]));
});

test("a waiting-on owed by someone the person reports to reads Waiting on, with New date first and Done and Drop in the menu", async () => {
  const user = userEvent.setup();
  show([chase({ stance: "report_to" })]);
  const row = await rowOf(`Waiting on Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  expect(row).not.toHaveTextContent("Chase");
  expect(within(row).queryByRole("button", { name: "Followed up" })).toBeNull();
  expect(within(row).getByRole("button", { name: "New date" })).toBeInTheDocument();
  await menuOf(user, row);
  expect(screen.getByRole("menuitem", { name: "Done" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Drop" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Followed up" })).toBeNull();
  expect(screen.queryByRole("menuitem", { name: "New date" })).toBeNull();
  await user.keyboard("{Escape}");
  await user.click(within(row).getByRole("button", { name: "New date" }));
  expect(await screen.findByLabelText("New date", { selector: "input" })).toHaveAttribute("type", "date");
});

test("a waiting-on with no date reads Waiting on too, and managed or alongside stay Chase", async () => {
  show([
    chase({ key: "promise:ACT-1", stance: "report_to", due: undefined, waiting_days: 12 }),
    chase({ key: "promise:ACT-2", actions: ["ACT-2"], text: "Book the room", subject: "Book the room", stance: "manage", due: undefined, waiting_days: 12 }),
  ]);
  expect(await rowOf("Waiting on Robin Sample: Send the floor plan, no date, nothing heard for 12 days")).toBeInTheDocument();
  expect(await rowOf("Chase Robin Sample: Book the room, no date, nothing heard for 12 days")).toBeInTheDocument();
});

test("the person's own promise is the same line without Chase, with Done first", async () => {
  const user = userEvent.setup();
  const { calls } = show([own()], { "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: null }) });
  const row = await rowOf(`Send the floor plan, due ${day("2026-10-13")}`);
  expect(row).not.toHaveTextContent("Chase");
  expect(within(row).queryByRole("button", { name: "Followed up" })).toBeNull();
  await menuOf(user, row);
  expect(screen.queryByRole("menuitem", { name: "Done" })).toBeNull();
  expect(screen.getByRole("menuitem", { name: "New date" })).toBeInTheDocument();
  await user.keyboard("{Escape}");
  await user.click(within(row).getByRole("button", { name: "Done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "done" }));
});

test("New date opens a date picker with the cursor in it, and saving corrects the day with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([chase()], { "POST promises/ACT-1/correct": () => ({ changeset: "CS-7" }), "POST changesets/CS-7/undo": () => ({ restored: [0], skipped: [] }) });
  const row = await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  await menuOf(user, row);
  await user.click(screen.getByRole("menuitem", { name: "New date" }));
  const picker = await screen.findByLabelText("New date", { selector: "input" });
  expect(picker).toHaveAttribute("type", "date");
  await waitFor(() => expect(picker).toHaveFocus());
  fireEvent.change(picker, { target: { value: "2026-11-03" } });
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-1/correct")?.body).toEqual({ read_version: 4, due: "2026-11-03" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-7/undo")).toBe(true));
});

test("Drop asks why and drops it, and Look closer shows why the promise exists", async () => {
  const user = userEvent.setup();
  const { calls } = show([chase()], { "POST actions/ACT-1/drop": () => ({ changeset: "CS-8" }) });
  const row = await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  await menuOf(user, row);
  await user.click(screen.getByRole("menuitem", { name: "Look closer" }));
  expect(await screen.findByText("I will send the floor plan by Tuesday.")).toBeInTheDocument();
  await menuOf(user, row);
  await user.click(screen.getByRole("menuitem", { name: "Drop" }));
  // The box the Drop opened, not the one-line meeting form under the agenda.
  const why = (await screen.findAllByRole("textbox")).find((box) => !box.closest('[aria-label="Add a meeting"]'))!;
  await user.type(why, "No longer needed");
  await user.click(screen.getByRole("button", { name: "Drop it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/drop")?.body).toEqual({ reason: "No longer needed" }));
});

// ---- a held ending ------------------------------------------------------------------------------------------------

test("a held close reads as one line: Keep, what the input says happened, and its words under it", async () => {
  show([ending({})]);
  const row = await rowOf("Keep: Robin Sample finished 'Send the floor plan'");
  expect(row).toHaveTextContent("“the floor plan went out this morning”");
  expect(row).toHaveTextContent("Said by Ana Person");
  expect(within(row).getByRole("button", { name: "Keep" })).toBeInTheDocument();
  // The other two answers are in its menu, not beside it.
  expect(within(row).queryByRole("button", { name: "Not yet" })).toBeNull();
});

test.each([
  [{ ask: "drop", reason: "no longer needed" } as Partial<S["HeldAsk"]>, "Keep: 'Send the floor plan' is called off"],
  [{ ask: "move", due_words: "next Tuesday" } as Partial<S["HeldAsk"]>, "Keep: 'Send the floor plan' is now due next Tuesday"],
  [{ ask: "move", due_words: null, value: "2026-11-03" } as Partial<S["HeldAsk"]>, `Keep: 'Send the floor plan' is now due ${day("2026-11-03")}`],
  [{ ask: "part", delivered: "the draft", left: "Send the final plan" } as Partial<S["HeldAsk"]>, "Keep: Robin Sample delivered the draft, and what is left is 'Send the final plan'"],
])("a held ending %# reads as one Keep line", async (held, title) => {
  show([ending(held)]);
  const row = await rowOf(title);
  expect(within(row).getByRole("button", { name: "Keep" })).toBeInTheDocument();
});

test("a promise said again with a new date reads as a move with both quotes under it", async () => {
  show([ending({ ask: "move", due_words: "by October 30", quote: "I will send the floor plan by October 30.", earlier: "I will send the floor plan by Tuesday." })]);
  const row = await rowOf("Keep: 'Send the floor plan' is now due by October 30");
  expect(row).toHaveTextContent("“I will send the floor plan by October 30.”");
  expect(row).toHaveTextContent("Said before: “I will send the floor plan by Tuesday.”");
});

test("Keep releases the ending and says what happened, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([ending({})], { "POST changesets/CS-1/ops/0/release": () => ({ ok: "CS-1" }), "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }) });
  await user.click(within(await rowOf("Keep: Robin Sample finished 'Send the floor plan'")).getByRole("button", { name: "Keep" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/0/release")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-1/undo")?.body).toEqual({ ops: [0] }));
});

test("Not yet declines it and Change opens the action, both from the menu", async () => {
  const user = userEvent.setup();
  const { calls, onOpenRecord } = show([ending({})], { "POST changesets/CS-1/ops/0/decline": () => ({ ok: "CS-1" }), "POST changesets/CS-1/ops/0/undecline": () => ({ ok: "CS-1" }) });
  const row = await rowOf("Keep: Robin Sample finished 'Send the floor plan'");
  await menuOf(user, row);
  await user.click(screen.getByRole("menuitem", { name: "Not yet" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/ops/0/decline")).toBe(true));
  expect(calls.some((c) => c.route.includes("/release"))).toBe(false);
  await menuOf(user, row);
  await user.click(screen.getByRole("menuitem", { name: "Change" }));
  expect(onOpenRecord).toHaveBeenCalledWith("action", "ACT-1");
});

// ---- the waiting-ons that have no date, or whose date is still ahead ---------------------------------------------

test("an undated waiting-on says it has no date and how long nothing has been heard", async () => {
  show([chase({ due: null, waiting_days: 14 })]);
  const row = await rowOf("Chase Robin Sample: Send the floor plan, no date, nothing heard for 14 days");
  expect(within(row).getByText("No date")).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Followed up" })).toBeInTheDocument();
});

test("a dated waiting-on whose date is still ahead says when it is due, and is not called late", async () => {
  show([chase({ waiting_days: -3 })]);
  const row = await rowOf(`Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`);
  expect(row).toHaveTextContent("Due in 3 days, and nothing heard since");
  expect(within(row).getByText("Due soon")).toBeInTheDocument();
  expect(row).not.toHaveTextContent("late");
});
