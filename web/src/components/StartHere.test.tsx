import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { StartHere } from "./StartHere";

const person = (id: string): S["PersonView"] => ({
  id,
  name: `Person ${id}`,
  role: null,
  org: null,
  aliases: [],
  status: "active",
  is_pm: id === "1",
});

function api(opts: { ai?: S["AiState"]["state"]; people?: number; handed?: boolean }) {
  return fakeApi({
    "GET status": () => ({
      backup: { configured: false, last_success: null, age_hours: null, needs_attention: false, last_error: null },
      ai: { state: opts.ai ?? "untested", detail: null },
      spend: { today_usd: 0, month_usd: 0, per_day_usd: 2, per_month_usd: 30, warn: false, warn_today: false, warn_month: false },
      requests: { queued: 0, running: 0, review: 0, needs_you: 0 },
      version: 1,
      restart_needed: null,
    }),
    "GET people": () => Array.from({ length: opts.people ?? 1 }, (_, i) => person(String(i + 1))),
    "GET changes": () =>
      opts.handed
        ? [{ id: "REQ-1", version: 1, dismissed: false, state: "done", waiting: null, created_at: "2026-10-09T14:00:00Z", note: "hello", source: null, source_title: null, changeset: null }]
        : [],
  });
}

const open = () => {
  const onHandIn = vi.fn();
  const onOpenSetup = vi.fn();
  renderApp(<StartHere workspace="Test" onHandIn={onHandIn} onOpenSetup={onOpenSetup} />);
  return { onHandIn, onOpenSetup };
};

beforeEach(() => window.localStorage.clear());

test("a new workspace shows three steps, each saying in words whether it is done", async () => {
  api({ ai: "untested", people: 1 });
  open();
  const steps = within(await screen.findByRole("list")).getAllByRole("listitem");
  expect(steps).toHaveLength(3);
  for (const step of steps) expect(step).toHaveTextContent("Not done yet");
});

test("the steps turn to done as the setup progresses", async () => {
  api({ ai: "ok", people: 3 });
  open();
  const steps = within(await screen.findByRole("list")).getAllByRole("listitem");
  expect(steps[0]).toHaveTextContent("Done");
  expect(steps[1]).toHaveTextContent("Done");
  expect(steps[2]).toHaveTextContent("Not done yet");
});

test("the buttons open People & projects and the hand-in", async () => {
  const user = userEvent.setup();
  api({});
  const { onHandIn, onOpenSetup } = open();
  await user.click(await screen.findByRole("button", { name: "Open People & projects" }));
  await user.click(screen.getByRole("button", { name: "Hand something in" }));
  expect(onOpenSetup).toHaveBeenCalledTimes(1);
  expect(onHandIn).toHaveBeenCalledTimes(1);
});

test("once something was handed in the card is gone", async () => {
  const calls = api({ handed: true });
  open();
  await vi.waitFor(() => expect(calls.filter((c) => c.route === "GET changes").length).toBeGreaterThan(0));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
});

test("hiding the card is remembered in this browser", async () => {
  const user = userEvent.setup();
  api({});
  open();
  await user.click(await screen.findByRole("button", { name: "Hide this" }));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
  document.body.innerHTML = "";
  api({});
  open();
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
});

test("a browser that blocks storage still shows the card", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  api({});
  open();
  expect(await screen.findByRole("heading", { name: "Start here" })).toBeInTheDocument();
  vi.restoreAllMocks();
});
