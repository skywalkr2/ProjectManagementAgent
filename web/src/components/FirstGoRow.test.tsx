import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { WhatChanged } from "./WhatChanged";

function held(id: string, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id,
    version: 3,
    dismissed: false,
    stage_task: false,
    first_go: true,
    refused: false,
    state: "needs_you",
    approval: "required",
    waiting: "Waiting for your first go.",
    estimate_usd: 0.1,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: `Item ${id}`,
    changeset: null,
    ...extra,
  };
}

const NO_STAGES = {
  "GET stages/records": () => [],
  "GET stages/ready": () => [],
  "GET stages/requests": () => [],
};

test("runs waiting for the first go are one line with their count and total, and no row of their own", async () => {
  fakeApi({
    "GET changes": () => [held("REQ-1"), held("REQ-2", { estimate_usd: 0.12 }), held("REQ-3", { estimate_usd: 0.08 })],
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  const line = await screen.findByRole("listitem", { name: "Start the assistant: 3 items, about $0.30" });
  expect(within(line).getByRole("button", { name: "Start" })).toBeInTheDocument();
  expect(within(line).getByText("Nothing is spent until you press Start.")).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
  expect(screen.queryByText("Item REQ-1")).toBeNull();
});

test("with no price the line says how many and that they use the plan's allowance", async () => {
  fakeApi({
    "GET changes": () => [held("REQ-1", { estimate_usd: null }), held("REQ-2", { estimate_usd: null })],
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  expect(
    await screen.findByRole("listitem", { name: "Start the assistant: 2 items. They use your plan's allowance." }),
  ).toBeInTheDocument();
});

test("one item reads as one item", async () => {
  fakeApi({ "GET changes": () => [held("REQ-1", { estimate_usd: 0.004 })], ...NO_STAGES });
  renderApp(<WhatChanged />);
  expect(await screen.findByRole("listitem", { name: "Start the assistant: 1 item, less than a cent" })).toBeInTheDocument();
});

test("Go starts them all with one call and says the assistant is on it", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [held("REQ-1"), held("REQ-2")],
    "POST runs/first-go": () => ({ started: 2 }),
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  const line = await screen.findByRole("listitem", { name: /^Start the assistant: 2 items/ });
  await user.click(within(line).getByRole("button", { name: "Start" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST runs/first-go")).toHaveLength(1));
  expect(calls.some((c) => /POST requests\/.*\/go/.test(c.route))).toBe(false);
  expect(await screen.findByText("Approved. Helper is on it.")).toBeInTheDocument();
});

test("no line shows when nothing waits for the first go, and a run held for its cost keeps its own row", async () => {
  fakeApi({
    "GET changes": () => [held("REQ-9", { first_go: false, waiting: "About $0.80. Waiting for you to start it.", estimate_usd: 0.8 })],
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  const row = await screen.findByRole("listitem", { name: "Item REQ-9" });
  expect(within(row).getByRole("button", { name: "Start" })).toBeInTheDocument();
  expect(screen.queryByText(/Start the assistant/)).toBeNull();
});

test("the sorting run the go also makes is in the total, so the total is the whole spend", async () => {
  const calls = fakeApi({
    "GET changes": () => [held("REQ-1"), held("REQ-2", { estimate_usd: 0.12 }), held("REQ-3", { estimate_usd: 0.08 })],
    "GET runs/first-go": () => ({ runs: 1, estimate_usd: 0.05, unpriced: 0 }),
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  expect(await screen.findByRole("listitem", { name: "Start the assistant: 3 items, about $0.35" })).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "GET runs/first-go")).toHaveLength(1);
});

test("a sorting run with no price makes the line say some of it is on the plan's allowance", async () => {
  fakeApi({
    "GET changes": () => [held("REQ-1"), held("REQ-2")],
    "GET runs/first-go": () => ({ runs: 1, estimate_usd: null, unpriced: 1 }),
    ...NO_STAGES,
  });
  renderApp(<WhatChanged />);
  expect(
    await screen.findByRole("listitem", { name: "Start the assistant: 2 items, about $0.20 plus some of your plan's allowance" }),
  ).toBeInTheDocument();
});

test("the sorting estimate is not asked for when nothing waits for the first go", async () => {
  const calls = fakeApi({ "GET changes": () => [], ...NO_STAGES });
  renderApp(<WhatChanged />);
  await waitFor(() => expect(calls.some((c) => c.route === "GET changes")).toBe(true));
  expect(calls.some((c) => c.route === "GET runs/first-go")).toBe(false);
});
