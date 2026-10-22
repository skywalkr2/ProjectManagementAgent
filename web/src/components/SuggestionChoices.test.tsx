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
  group: "review",
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

const row = (key: string) => document.querySelector<HTMLElement>(`[data-line-key="${key}"]`)!;
const moved = line("pattern", { key: "pattern:moved:ACT-1", state: "moved", count: 3, text: "Book the studio", actions: ["ACT-1"], choices: ["drop", "weekly", "leave"] });

test("a to-do moved again and again is one line with its first choice as the button, the second beside it and the third in the menu", async () => {
  const user = userEvent.setup();
  show([moved]);
  expect(await screen.findByText("Decide about Book the studio: you have moved its day 3 times")).toBeInTheDocument();
  const found = row("pattern:moved:ACT-1");
  expect(within(found).getAllByRole("button").filter((b) => b.getAttribute("data-variant") === "primary").map((b) => b.textContent)).toEqual(["Drop it"]);
  expect(within(found).getByRole("button", { name: "Make it weekly" })).toBeInTheDocument();
  await user.click(within(found).getByRole("button", { name: /More|menu/i }));
  expect(await screen.findByRole("menuitem", { name: "Leave it" })).toBeInTheDocument();
});

test("Drop it sends the choice with the sheet's words and offers Undo, which takes the choice back", async () => {
  const user = userEvent.setup();
  const { calls } = show([moved], {
    "POST suggestions/choose": () => ({ signal: "SIG-4", changeset: "CS-4" }),
    "POST suggestions/choose/SIG-4/undo": () => ({ ok: "SIG-4" }),
  });
  await user.click(await screen.findByRole("button", { name: "Drop it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST suggestions/choose")?.body).toMatchObject({ key: "pattern:moved:ACT-1", choice: "drop", reason: "Its day kept moving, so it was dropped" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST suggestions/choose/SIG-4/undo")).toBe(true));
});

test("Make it weekly sends the words of the repeat, and Leave it sends only the choice", async () => {
  const user = userEvent.setup();
  const { calls } = show([moved], { "POST suggestions/choose": () => ({ signal: "SIG-5", changeset: null }) });
  await user.click(await screen.findByRole("button", { name: "Make it weekly" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST suggestions/choose")?.body).toMatchObject({ choice: "weekly", weekly: "every week" }));
});

test("replies owed to one person are one line that says how many, with a menu entry that opens them", async () => {
  const user = userEvent.setup();
  const { onOpenRecord } = show([
    line("pattern", { key: "pattern:replies:PER-2", state: "replies", count: 2, person: "PER-2", person_name: "Ana Example", text: "Reply about the cover", actions: ["A-1", "A-2"], choices: ["no_reply", "leave"] }),
  ]);
  expect(await screen.findByText("Answer Ana Example: you owe 2 replies")).toBeInTheDocument();
  const found = row("pattern:replies:PER-2");
  expect(within(found).getByRole("button", { name: "No reply needed" })).toBeInTheDocument();
  await user.click(within(found).getByRole("button", { name: /More|menu/i }));
  await user.click(await screen.findByRole("menuitem", { name: "Open Ana Example" }));
  expect(onOpenRecord).toHaveBeenCalledWith("person", "PER-2");
});

test("one stale to-do asks whether the person is still doing it, with Keep it, Drop it and Snooze", async () => {
  const user = userEvent.setup();
  const { calls } = show(
    [line("stale", { key: "stale", count: 1, actions: ["A-1"], waiting_days: 30, subject: "Tidy the style sheet", choices: ["keep", "drop", "snooze"] })],
    { "POST suggestions/choose": () => ({ signal: "SIG-6", changeset: null }) },
  );
  expect(await screen.findByText("Decide whether you are still doing: Tidy the style sheet")).toBeInTheDocument();
  const found = row("stale");
  expect(within(found).getByRole("button", { name: "Keep it" })).toBeInTheDocument();
  expect(within(found).getByRole("button", { name: "Drop it" })).toBeInTheDocument();
  await user.click(within(found).getByRole("button", { name: /More|menu/i }));
  await user.click(await screen.findByRole("menuitem", { name: "Snooze" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST suggestions/choose")?.body).toMatchObject({ key: "stale", choice: "snooze" }));
});

test("several stale to-dos keep Look over as the button and offer Keep them and Snooze them in the menu", async () => {
  const user = userEvent.setup();
  show([line("stale", { key: "stale", count: 3, actions: ["A-1", "A-2", "A-3"], waiting_days: 40, choices: ["keep", "snooze"] })]);
  await screen.findByText("Keep or drop 3 to-dos nobody has touched lately");
  expect(within(row("stale")).getByRole("button", { name: "Look over" })).toBeInTheDocument();
  await user.click(within(row("stale")).getByRole("button", { name: /More|menu/i }));
  expect(await screen.findByRole("menuitem", { name: "Keep them" })).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Snooze them" })).toBeInTheDocument();
});
