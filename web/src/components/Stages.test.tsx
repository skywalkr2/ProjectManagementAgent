import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Stages } from "./Stages";
import { WhatChanged } from "./WhatChanged";

const stages = [
  { id: "first", label: "First step" },
  { id: "second", label: "Second step" },
  { id: "third", label: "Third step" },
];

function view(id: string, title: string, extra: Partial<S["StageView"]> = {}): S["StageView"] {
  return {
    record: { kind: "project", id },
    title,
    version: 3,
    current: "second",
    current_label: "Second step",
    next: stages[2],
    stages,
    checks: [],
    ready: true,
    ...extra,
  };
}

const ready = view("A-1", "Alpha item");
const blocked = view("A-2", "Beta item", {
  current: "first",
  current_label: "First step",
  next: stages[1],
  ready: false,
  checks: [
    { id: "one", passed: false, reason: "Add the missing text first." },
    { id: "two", passed: true, reason: "Already fine." },
  ],
});
const fresh = view("A-3", "Gamma item", { current: null, current_label: null, next: stages[0] });

function request(extra: Partial<S["StageRequestView"]> = {}): S["StageRequestView"] {
  return {
    id: "R-1",
    version: 2,
    task: "notes",
    state: "needs_you",
    approval: "required",
    waiting: "Waiting for your go.",
    stage_start: { kind: "project", record: "A-1", stage: "second", changeset: "CS-1" },
    ...extra,
  };
}

const row = (title: string) => screen.getByRole("listitem", { name: title });

test("a ready item shows where it is and one action to move on, and moving offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET stages/records": () => [ready, blocked, fresh],
    "GET stages/requests": () => [],
    "POST stages/move": () => ({ changeset: "CS-9", stages: ready }),
    "POST changesets/CS-9/undo": () => ({ restored: [{ kind: "project", id: "A-1" }], skipped: [] }),
  });
  renderApp(<Stages />);
  const alpha = await screen.findByRole("listitem", { name: "Alpha item" });
  expect(within(alpha).getByText("Second step")).toBeInTheDocument();
  expect(within(alpha).getByText("Ready for Third step")).toBeInTheDocument();
  expect(within(row("Gamma item")).getByText("Not started")).toBeInTheDocument();
  await user.click(within(alpha).getByRole("button", { name: "Move to Third step" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST stages/move")?.body).toEqual({
      record: ready.record,
      to: "third",
      read_version: 3,
    }),
  );
  expect(await screen.findByText("Moved Alpha item to Third step.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("a blocked item lists each failed check and has no move button", async () => {
  fakeApi({ "GET stages/records": () => [blocked], "GET stages/requests": () => [] });
  renderApp(<Stages />);
  const beta = await screen.findByRole("listitem", { name: "Beta item" });
  expect(within(beta).getByText("Not ready for Second step yet")).toBeInTheDocument();
  expect(within(beta).getByText("Before it can move to Second step:")).toBeInTheDocument();
  expect(within(beta).getByText("Add the missing text first.")).toBeInTheDocument();
  expect(within(beta).queryByText("Already fine.")).toBeNull();
  expect(within(beta).queryByRole("button", { name: /^Move to/ })).toBeNull();
});

test("the menu moves back to each earlier stage and shows the history in plain words", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET stages/records": () => [ready],
    "GET stages/requests": () => [],
    "GET records/A-1/stage-history?kind=project": () => [
      { sequence: 1, at: "2026-10-09T14:00:00Z", from_stage: null, to_stage: "first", version: 1, actor: "pm", op: "stage.move", changeset: "CS-1", request: null, source: null },
      { sequence: 2, at: "2026-10-09T15:00:00Z", from_stage: "first", to_stage: "second", version: 2, actor: "rule", op: "stage.move", changeset: null, request: null, source: null },
      { sequence: 3, at: "2026-10-09T16:00:00Z", from_stage: "second", to_stage: "first", version: 3, actor: "pm", op: "undo", changeset: "CS-1", request: null, source: null },
    ],
    "POST stages/move": () => ({ changeset: "CS-8", stages: ready }),
  });
  renderApp(<Stages />);
  const alpha = await screen.findByRole("listitem", { name: "Alpha item" });
  await user.click(within(alpha).getByRole("button", { name: /More actions for Alpha item/ }));
  const items = await screen.findAllByRole("menuitem");
  expect(items.map((i) => i.textContent)).toEqual(["Move back to First step", "History"]);
  await user.click(items[1]);
  const list = await within(alpha).findByRole("list", { name: "Where it has been" });
  const lines = within(list).getAllByRole("listitem").map((li) => li.textContent ?? "");
  expect(lines[0]).toMatch(/^Second step to First step · .* · by undo$/);
  expect(lines[1]).toMatch(/^First step to Second step · .* · by a rule$/);
  expect(lines[2]).toMatch(/^Not started to First step · .* · by you$/);
  await user.click(within(alpha).getByRole("button", { name: /More actions for Alpha item/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Move back to First step" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST stages/move")?.body).toMatchObject({ to: "first", read_version: 3 }));
});

test("a refusal shows as a plain message on the row", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET stages/records": () => [ready], "GET stages/requests": () => [] });
  renderApp(<Stages />);
  const alpha = await screen.findByRole("listitem", { name: "Alpha item" });
  await user.click(within(alpha).getByRole("button", { name: "Move to Third step" }));
  expect(await within(alpha).findByRole("alert")).toHaveTextContent("That didn't work.");
});

test("a task waiting for the go shows under its item, and Go sends the version read", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET stages/records": () => [ready],
    "GET stages/requests": () => [request(), request({ id: "R-2", approval: "granted" })],
    "POST requests/R-1/go": () => ({ ok: "queued" }),
  });
  renderApp(<Stages />);
  const alpha = await screen.findByRole("listitem", { name: "Alpha item" });
  const waiting = await within(alpha).findByRole("list", { name: "Waiting for your go" });
  expect(within(waiting).getAllByRole("listitem")).toHaveLength(1);
  expect(within(waiting).getByText("Filing notes is waiting for your go")).toBeInTheDocument();
  await user.click(within(waiting).getByRole("button", { name: "Go" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/R-1/go")?.body).toEqual({ read_version: 2 }));
});

test("with nothing in stages, it says so", async () => {
  fakeApi({ "GET stages/records": () => [], "GET stages/requests": () => [] });
  renderApp(<Stages />);
  expect(await screen.findByText(/^Nothing moves through stages yet\./)).toBeInTheDocument();
});

test("Today lists tasks waiting for a go and items ready to move on, never internal names", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [
      { id: "R-1", version: 2, dismissed: false, state: "needs_you", waiting: "Waiting for your go.", created_at: "2026-10-09T14:00:00Z", note: null, source: null, source_title: null, changeset: null },
    ],
    "GET stages/records": () => [ready, blocked],
    "GET stages/ready": () => [ready],
    "GET stages/requests": () => [request({ task: "some/unnamed-kind" })],
    "POST requests/R-1/go": () => ({ ok: "queued" }),
    "POST stages/move": () => ({ changeset: "CS-7", stages: ready }),
  });
  renderApp(<WhatChanged />);
  const go = await screen.findByRole("listitem", { name: "Alpha item: Helper's work is waiting for your go" });
  expect(screen.queryByText(/unnamed-kind/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  const moveRow = screen.getByRole("listitem", { name: "Alpha item is ready for Third step" });
  expect(screen.queryByText("Nothing needs a look right now.")).toBeNull();
  await user.click(within(go).getByRole("button", { name: "Go" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/R-1/go")?.body).toEqual({ read_version: 2 }));
  await user.click(within(moveRow).getByRole("button", { name: "Move to Third step" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST stages/move")?.body).toMatchObject({ to: "third" }));
});
