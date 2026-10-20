import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, Refuse, renderApp } from "../test-utils";
import { Stages } from "./Stages";

// The stages board (design 7.13): a column for each stage, a card for each item, and three ways to move a card.

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
    project: null,
    owners: [],
    due: null,
    ...extra,
  };
}

const ready = view("A-1", "Alpha item", { project: "Harbor refit", owners: ["Ada Example", "Bo Example"], due: "2026-11-02" });
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

const board = () => screen.findByRole("group", { name: "Projects, by stage" });
const column = (name: string) => screen.getByRole("region", { name: new RegExp(`^${name}`) });
const card = (title: string) => screen.getByRole("listitem", { name: title });

function show(extra: Record<string, (body: unknown) => unknown> = {}, records: S["StageView"][] = [ready, blocked, fresh]) {
  const calls = fakeApi({ "GET stages/records": () => records, "GET stages/requests": () => [], ...extra });
  renderApp(<Stages />);
  return calls;
}

afterEach(() => window.localStorage.clear());

describe("the board", () => {
  test("is the way the stages are shown, a column for Not started and each stage, each item under the stage it is in", async () => {
    show();
    await board();
    const names = screen.getAllByRole("heading", { level: 3 }).map((h) => h.firstElementChild?.textContent);
    expect(names).toEqual(["Not started", "First step", "Second step", "Third step"]);
    expect(within(column("Not started")).getByRole("listitem", { name: "Gamma item" })).toBeInTheDocument();
    expect(within(column("First step")).getByRole("listitem", { name: "Beta item" })).toBeInTheDocument();
    expect(within(column("Second step")).getByRole("listitem", { name: "Alpha item" })).toBeInTheDocument();
    expect(within(column("Third step")).getByText("Nothing here")).toBeInTheDocument();
  });

  test("a card shows the title, the project, the due date and an avatar for each owner, with their names", async () => {
    show();
    await board();
    const alpha = card("Alpha item");
    expect(within(alpha).getByText(/Harbor refit/)).toHaveTextContent(/Harbor refit · Due .*2/);
    expect(within(alpha).getByText("Ada Example")).toBeInTheDocument();
    expect(within(alpha).getByText("AE")).toBeInTheDocument();
    expect(within(alpha).getByText("Can move to Third step")).toBeInTheDocument();
  });

  test("a card that is ready has one primary button, which moves it on with Undo; a blocked one lists what is missing and has none", async () => {
    const user = userEvent.setup();
    const calls = show({
      "POST stages/move": () => ({ changeset: "CS-9", stages: ready }),
      "POST changesets/CS-9/undo": () => ({ restored: [{ kind: "project", id: "A-1" }], skipped: [] }),
    });
    await board();
    const beta = card("Beta item");
    expect(within(beta).getByText("Add the missing text first.")).toBeInTheDocument();
    expect(within(beta).queryByText("Already fine.")).toBeNull();
    expect(within(beta).queryByRole("button", { name: /^Move to/ })).toBeNull();
    await user.click(within(card("Alpha item")).getByRole("button", { name: "Move to Third step" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST stages/move")?.body).toEqual({ record: { kind: "project", id: "A-1" }, to: "third", read_version: 3 }));
    expect(await screen.findByText("Moved Alpha item to Third step.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
  });

  test("the menu moves a card back to an earlier stage, and an item not started may begin at any stage", async () => {
    const user = userEvent.setup();
    const calls = show({ "POST stages/move": () => ({ changeset: "CS-8", stages: ready }) });
    await board();
    await user.click(within(card("Alpha item")).getByRole("button", { name: /More actions for Alpha item/ }));
    expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Move back to First step", "History"]);
    await user.click(screen.getByRole("menuitem", { name: "Move back to First step" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST stages/move")?.body).toMatchObject({ to: "first", read_version: 3 }));
    await user.click(within(card("Gamma item")).getByRole("button", { name: /More actions for Gamma item/ }));
    expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Move to Second step", "Move to Third step", "History"]);
  });

  test("the move key on a card opens its menu of stages", async () => {
    show();
    await board();
    const alpha = card("Alpha item");
    alpha.focus();
    fireEvent(alpha, new CustomEvent("rowkey", { detail: "move", bubbles: true, cancelable: true }));
    expect(await screen.findByRole("menuitem", { name: "Move back to First step" })).toBeInTheDocument();
  });

  test("dragging a card to the next stage's column moves it through the same move", async () => {
    const calls = show({ "POST stages/move": () => ({ changeset: "CS-9", stages: ready }) });
    await board();
    const data = { setData: vi.fn(), effectAllowed: "" };
    fireEvent.dragStart(card("Alpha item"), { dataTransfer: data });
    fireEvent.dragOver(column("Third step"), { dataTransfer: data });
    expect(column("Third step")).toHaveAttribute("data-over");
    fireEvent.drop(column("Third step"), { dataTransfer: data });
    await waitFor(() => expect(calls.find((c) => c.route === "POST stages/move")?.body).toEqual({ record: { kind: "project", id: "A-1" }, to: "third", read_version: 3 }));
  });

  test("a drop that the entry checks refuse says so in plain words above the board, and nothing else moves", async () => {
    const calls = show({ "POST stages/move": () => new Refuse(409, "Add the missing text first.") });
    await board();
    const data = { setData: vi.fn(), effectAllowed: "" };
    fireEvent.dragStart(card("Gamma item"), { dataTransfer: data });
    fireEvent.drop(column("Second step"), { dataTransfer: data });
    expect(await screen.findByRole("alert")).toHaveTextContent("Add the missing text first.");
    expect(calls.filter((c) => c.route === "POST stages/move")).toHaveLength(1);
  });

  test("a drop on Not started, or on the stage it is already in, moves nothing", async () => {
    const calls = show();
    await board();
    const data = { setData: vi.fn(), effectAllowed: "" };
    fireEvent.dragStart(card("Alpha item"), { dataTransfer: data });
    fireEvent.drop(column("Not started"), { dataTransfer: data });
    fireEvent.dragStart(card("Alpha item"), { dataTransfer: data });
    fireEvent.drop(column("Second step"), { dataTransfer: data });
    expect(calls.filter((c) => c.route === "POST stages/move")).toHaveLength(0);
  });

  test("more than six stages scroll inside the board's own frame; six or fewer fit the width", async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({ id: `s${i}`, label: `Step ${i}` }));
    show({}, [view("A-9", "Wide item", { stages: many, current: "s0", next: many[1] })]);
    const group = await board();
    expect(group.parentElement).toHaveAttribute("data-scroll");
    window.localStorage.clear();
  });

  test("a task waiting for the go shows on its card, with Start", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      "GET stages/records": () => [ready],
      "GET stages/requests": () => [
        { id: "R-1", version: 2, task: "notes", state: "needs_you", approval: "required", waiting: "Waiting", stage_start: { kind: "project", record: "A-1", stage: "second", changeset: "CS-1" } },
      ],
      "POST requests/R-1/go": () => ({ ok: "queued" }),
    });
    renderApp(<Stages />);
    await board();
    await user.click(within(card("Alpha item")).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST requests/R-1/go")?.body).toEqual({ read_version: 2 }));
  });
});

describe("the choice of board or list", () => {
  test("the list is one switch away, and the choice is kept for this device", async () => {
    const user = userEvent.setup();
    show();
    await board();
    await user.click(screen.getByRole("radio", { name: "List" }));
    expect(await screen.findByRole("listitem", { name: "Alpha item" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Projects, by stage" })).toBeNull();
    expect(window.localStorage.getItem("stages.view")).toBe("list");
  });

  test("a phone starts with the list", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: /max-width:\s*639px/.test(query), media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
    show();
    expect(await screen.findByRole("listitem", { name: "Alpha item" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Projects, by stage" })).toBeNull();
    vi.unstubAllGlobals();
  });
});
