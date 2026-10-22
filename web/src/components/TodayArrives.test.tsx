import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// What arrives (design 6.32): a dated item's reminder on Today, and an area of life offered for items that share a word.

type Line = S["QueueLineView"];

const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({
  key: kind,
  group: kind === "area" ? "review" : "risk",
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

const row = (kind: string) => document.querySelector<HTMLElement>(`[data-queue-line="${kind}"]`)!;

test("a reminder for a dated fact says what kind of day it is and opens the fact", async () => {
  const reminder = line("date_reminder", { text: "The studio plan renews", due: "2026-12-15", state: "renewal", fact: "FACT-4", at: "2026-12-01T09:00:00+00:00" });
  const { onOpenRecord } = show([reminder]);
  expect(await screen.findByText(/^Decide on the renewal: The studio plan renews \(.*15\)$/)).toBeInTheDocument();
  const found = row("date_reminder");
  expect(found).toHaveTextContent("Date coming");
  await userEvent.click(within(found).getByRole("button", { name: "Open it" }));
  expect(onOpenRecord).toHaveBeenCalledWith("fact", "FACT-4");
});

const area = line("area", { text: "Dentist", subject: "dentist", count: 4, names: ["Book the dentist", "Ask about the crown", "Closed on Fridays"] });

test("an area offered for items that share a word is started and filled with one press, and Undo takes both changes back", async () => {
  const keep = vi.fn(() => ({ project: "PRJ-9", filed: "CS-2", started: "CS-1" }));
  const undone: string[] = [];
  const { calls } = show([area], {
    "POST areas/keep": keep,
    "POST changesets/CS-2/undo": () => {
      undone.push("CS-2");
      return { restored: [0], skipped: [] };
    },
    "POST changesets/CS-1/undo": () => {
      undone.push("CS-1");
      return { restored: [0], skipped: [] };
    },
  });
  expect(await screen.findByText("File 4 items under a new area, Dentist?")).toBeInTheDocument();
  expect(row("area")).toHaveTextContent("Book the dentist; Ask about the crown; Closed on Fridays");
  await userEvent.click(within(row("area")).getByRole("button", { name: "Start Dentist" }));
  await waitFor(() => expect(keep).toHaveBeenCalled());
  expect(calls.find((c) => c.route === "POST areas/keep")?.body).toEqual({ word: "dentist" });
  expect(await screen.findByText("Started Dentist and filed 4 items under it")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(undone).toEqual(["CS-2", "CS-1"]));
});

test("an offered area can be put off with Not now, like any suggestion", async () => {
  const user = userEvent.setup();
  const { calls } = show([area], { "POST suggestions/not-now": () => ({ signal: "SIG-3" }) });
  await screen.findByText("File 4 items under a new area, Dentist?");
  await user.click(within(row("area")).getByRole("button", { name: /More|menu/i }));
  await user.click(await screen.findByRole("menuitem", { name: "Not now" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST suggestions/not-now")?.body).toEqual({ key: "area" }));
});
