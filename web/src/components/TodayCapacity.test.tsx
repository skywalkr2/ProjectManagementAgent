import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

type Line = S["QueueLineView"];

const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({
  key: kind,
  group: kind === "stale" || kind === "learned" ? "review" : "risk",
  kind,
  count: 1,
  untrusted: false,
  unpriced: 0,
  actions: [],
  questions: [],
  outcome: {},
  ...over,
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
    "GET status": () => statusFixture({}, { assistant: { last_run_at: "2026-10-20T08:00:00Z" } }),
    "GET runtime-config": () => ({ instance: null }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
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

const row = (kind: string) => document.querySelector<HTMLElement>(`[data-queue-line="${kind}"]`)!;

const capacity = line("capacity", { count: 1, minutes: 90, needed_minutes: 150, actions: ["ACT-2"], due: "2026-10-27" });
const proposal: S["CapacityView"] = {
  fits: false,
  free_minutes: 90,
  needed_minutes: 150,
  over_minutes: 60,
  still_over: 0,
  next_day: "2026-10-27",
  moves: [{ action: "ACT-2", version: 4, text: "Sort the receipts", minutes: 90, promised: false, due: "2026-10-26", due_state: "today" }],
};

test("more to do than today holds is one line saying how many to move and how much time today holds", async () => {
  show([capacity], { "GET capacity": () => proposal });
  expect(await screen.findByText("Move 1 to-do: today holds about 1 hour 30 minutes")).toBeInTheDocument();
  const found = row("capacity");
  expect(found).toHaveTextContent("The to-dos due today need about 2 hours 30 minutes");
  expect(within(found).getAllByRole("button").filter((b) => b.getAttribute("data-variant") === "primary")).toHaveLength(1);
});

test("the line opens what to move; moving one is the person's own date change, at once, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([capacity], { "GET capacity": () => proposal, "POST records/edit": () => ({ changeset: "CS-1" }) });
  await user.click(await screen.findByRole("button", { name: "See what to move" }));
  const move = await screen.findByText("Sort the receipts");
  expect(move.closest("li")).toHaveTextContent("1 hour 30 minutes");
  await user.click(screen.getByRole("button", { name: /^Move to / }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({
      kind: "action",
      id: "ACT-2",
      read_version: 4,
      fields: { due: "2026-10-27", due_words: null, due_check: false },
    }),
  );
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("a day can be picked instead, with the cursor in the day field", async () => {
  const user = userEvent.setup();
  const { calls } = show([capacity], { "GET capacity": () => proposal, "POST records/edit": () => ({ changeset: "CS-1" }) });
  await user.click(await screen.findByRole("button", { name: "See what to move" }));
  await user.click(await screen.findByRole("button", { name: "Pick a day" }));
  const field = await screen.findByLabelText("Move it to");
  await waitFor(() => expect(field).toHaveFocus());
  await user.type(field, "2026-10-30");
  await user.click(screen.getByRole("button", { name: "Move" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toMatchObject({ fields: { due: "2026-10-30" } }));
});

test("a clash is a line that says what clashes and why, and opens the meeting", async () => {
  const user = userEvent.setup();
  const { onOpenRecord } = show([
    line("clash", { key: "clash:a:b:2026-10-27", text: "Site visit", other: "Supplier call", state: "travel", minutes: 20, due: "2026-10-27", at: "2026-10-27T11:10:00+00:00", entry: "EVT-3" }),
  ]);
  expect(await screen.findByText(/^Sort out the clash: Site visit and Supplier call leave 20 minutes too little to travel between them/)).toBeInTheDocument();
  await user.click(within(row("clash")).getByRole("button", { name: "Open the meeting" }));
  expect(onOpenRecord).toHaveBeenCalledWith("event", "EVT-3");
});

test("a suggestion has Not now in its menu, which puts it off with Undo; what is due has none", async () => {
  const user = userEvent.setup();
  const { calls } = show([line("stale", { key: "stale", count: 3, actions: ["A-1", "A-2", "A-3"], waiting_days: 40 }), capacity], {
    "GET capacity": () => proposal,
    "POST suggestions/not-now": () => ({ signal: "SIG-9" }),
    "POST suggestions/not-now/SIG-9/undo": () => ({ ok: "SIG-9" }),
  });
  await screen.findByText("Keep or drop 3 to-dos nobody has touched lately");
  await user.click(within(row("stale")).getByRole("button", { name: /More|menu/i }));
  await user.click(await screen.findByRole("menuitem", { name: "Not now" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST suggestions/not-now")?.body).toEqual({ key: "stale" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST suggestions/not-now/SIG-9/undo")).toBe(true));
  expect(within(row("capacity")).queryByRole("button", { name: /More|menu/i })).toBeNull();
});
