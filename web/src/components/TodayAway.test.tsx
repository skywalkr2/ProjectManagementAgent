import "@testing-library/jest-dom/vitest";
import { act, screen, within } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { useReminderNotices } from "./ReminderLine";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { Today } from "./Today";

// Work the assistant releases on its own keeps the person's hours (design 6.35): what waited for working hours arrives with
// one row, "While you were away", that says how many; the lines it groups are in their own places. A line that is held is not
// in the queue at all, so there is nothing to notify about until it is released.

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  return { key: `${kind}:1`, group: "decide", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const away = (count: number) => line("away", { key: "away", count });
const decision = line("decision", { key: "question:Q-1", text: "Which printer?", question: "Q-1" });

function show(lines: Line[]) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  fakeApi({
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
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

test("what waited arrives under one row that says how many, not a row for each", async () => {
  show([away(3), decision]);
  const row = (await screen.findByRole("group", { name: "While you were away: 3 things arrived" })) as HTMLElement;
  expect(within(row).queryAllByRole("button")).toEqual([]);
  expect(screen.getAllByText(/While you were away/)).toHaveLength(1);
  expect(await screen.findByRole("group", { name: "Which printer?" })).toBeInTheDocument();
});

test("one thing is said in the singular", async () => {
  show([away(1), decision]);
  expect(await screen.findByRole("group", { name: "While you were away: 1 thing arrived" })).toBeInTheDocument();
});

test("with nothing that waited there is no row", async () => {
  show([decision]);
  await screen.findByRole("group", { name: "Which printer?" });
  expect(screen.queryByText(/While you were away/)).toBeNull();
});

// ---- notifications ----------------------------------------------------------------------------------------------

function lineSource(first: Line[]) {
  let set: (lines: Line[]) => void = () => undefined;
  function Host() {
    const [lines, setLines] = useState(first);
    set = setLines;
    useReminderNotices(lines);
    return null;
  }
  return { Host, show: (lines: Line[]) => act(() => set(lines)) };
}

function stubNotification() {
  const shown: string[] = [];
  class Fake {
    static permission: NotificationPermission = "granted";
    static requestPermission = vi.fn(async () => "granted" as NotificationPermission);
    constructor(title: string) {
      shown.push(title);
    }
  }
  vi.stubGlobal("Notification", Fake);
  return shown;
}

test("a held line is not in the queue, so nothing is shown for it, and released lines with their row show no notification", () => {
  const shown = stubNotification();
  const source = lineSource([]);
  renderApp(<source.Host />);
  // Held: the queue holds nothing new while the hours are out.
  source.show([]);
  expect(shown).toEqual([]);
  // Released: the lines and their row arrive together at the start of the hours; none of them is a reminder.
  source.show([away(2), decision, line("go", { key: "go:REQ-1" })]);
  expect(shown).toEqual([]);
});

test("a reminder the person set still notifies at its own time", () => {
  const shown = stubNotification();
  const source = lineSource([]);
  renderApp(<source.Host />);
  source.show([line("reminder", { key: "reminder:ACT-1", group: "risk", text: "Call the printer", late: false })]);
  expect(shown).toEqual(["Call the printer · due now"]);
});
