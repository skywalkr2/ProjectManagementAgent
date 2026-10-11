import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { Panel } from "./Panel";

const KIND = "demo/goal";

function panel(extra: Partial<S["PanelView"]> = {}): S["PanelView"] {
  return {
    name: "demo/goals",
    title: "Goals",
    tab: "work",
    kind: KIND,
    view: "table",
    columns: ["title", "due_date", "status"],
    primary_action: "demo/goal.update",
    row_actions: ["demo/goal.close", "demo/summarize"],
    ...extra,
  };
}

const rows: S["PanelRow"][] = [
  { id: "G-1", values: { title: "Finish the draft <b>soon</b>", due_date: "2026-11-01", status: "open" } },
  { id: "G-2", values: { title: "Plan the launch", due_date: null, status: "done" } },
];

const offered = (id: string) => `kind=${encodeURIComponent(KIND)}&id=${id}`;

function routes(view: S["PanelView"], extra: Routes = {}): Routes {
  const perRow: Routes = {};
  for (const row of rows) {
    perRow[`GET plugin-actions?${offered(row.id)}`] = () => [
      { name: "demo/goal.update", label: "Update", on: KIND },
      { name: "demo/goal.close", label: "Close goal", on: KIND },
    ];
    perRow[`GET task-kinds?${offered(row.id)}`] = () => [{ name: "demo/summarize", label: "Summarize", on: KIND }];
  }
  return { "GET panels": () => [view], "GET panels/demo/goals/rows": () => rows, ...perRow, ...extra };
}

test("a table has readable column headers, plain-text cells and the record's title as the first cell", async () => {
  fakeApi(routes(panel()));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const table = await screen.findByRole("table");
  expect(screen.getByRole("heading", { level: 2, name: "Goals" })).toBeInTheDocument();
  expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Title", "Due date", "Status", "Actions"]);
  const first = within(table).getAllByRole("row")[1];
  expect(within(first).getByRole("rowheader")).toHaveTextContent("Finish the draft <b>soon</b>");
  expect(first.querySelector("b")).toBeNull();
  expect(within(first).getByText("2026-11-01")).toBeInTheDocument();
  expect(within(within(table).getAllByRole("row")[2]).getAllByRole("cell")[0]).toHaveTextContent("—");
});

test("the title opens the record's page", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi(routes(panel()));
  renderApp(<Panel name="demo/goals" onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "Plan the launch" }));
  expect(open).toHaveBeenCalledWith(KIND, "G-2");
});

test("a person action as the primary action opens its review; the other actions are in the row's menu", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    routes(panel(), {
      "POST plugin-actions/demo/goal.update/preview": () => ({
        token: "t",
        action: "demo/goal.update",
        summary: "Update the goal",
        ops: [],
        files: [],
        previews: [],
        choices: [],
        notes: [],
        expires_at: "2026-10-09T15:00:00Z",
      }),
      "POST task-kinds/demo/summarize/start": () => ({ request: "REQ-1" }),
    }),
  );
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const update = await screen.findByRole("button", { name: "Update: Plan the launch" });
  expect(screen.getAllByRole("button", { name: /^Update:/ })).toHaveLength(2);
  await user.click(update);
  await screen.findByRole("dialog", { name: "Update the goal" });
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/goal.update/preview")?.body).toEqual({
    target: { kind: KIND, id: "G-2" },
    choices: {},
  });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

  await user.click(screen.getByRole("button", { name: "More actions for Plan the launch" }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Close goal", "Summarize"]);
});

test("a kind of work in the menu starts at once with a toast", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes(panel(), { "POST task-kinds/demo/summarize/start": () => ({ request: "REQ-1" }) }));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "More actions for Plan the launch" }));
  await user.click(screen.getByRole("menuitem", { name: "Summarize" }));
  expect(await screen.findByText("Started: Summarize")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST task-kinds/demo/summarize/start")?.body).toEqual({
    about: { kind: KIND, id: "G-2" },
    note: "",
  });
});

test("a kind of work as the primary action starts at once", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    routes(panel({ primary_action: "demo/summarize", row_actions: [] }), {
      "POST task-kinds/demo/summarize/start": () => ({ request: "REQ-1" }),
    }),
  );
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Summarize: Finish the draft <b>soon</b>" }));
  expect(await screen.findByText("Started: Summarize")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST task-kinds/demo/summarize/start")).toBe(true);
});

test("a list has one row per record with the other columns as labelled facts", async () => {
  fakeApi(routes(panel({ view: "list" })));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const items = await screen.findAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("Due date");
  expect(items[0]).toHaveTextContent("2026-11-01");
  expect(screen.queryByRole("table")).toBeNull();
});

test("a board groups the rows by the first column's value", async () => {
  fakeApi(
    routes(panel({ view: "board", columns: ["status", "title"] }), {
      "GET panels/demo/goals/rows": () => [
        { id: "G-1", values: { status: "open", title: "One" } },
        { id: "G-2", values: { status: "done", title: "Two" } },
        { id: "G-3", values: { status: "open", title: "Three" } },
      ],
      [`GET plugin-actions?${offered("G-3")}`]: () => [],
      [`GET task-kinds?${offered("G-3")}`]: () => [],
    }),
  );
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const open = await screen.findByRole("region", { name: "open" });
  expect(within(open).getAllByRole("button", { name: /^(One|Three)$/ })).toHaveLength(2);
  const done = screen.getByRole("region", { name: "done" });
  expect(within(done).getByRole("button", { name: "Two" })).toBeInTheDocument();
});

test("an action the record isn't offered is not shown, and an empty panel says so", async () => {
  fakeApi({
    "GET panels": () => [panel()],
    "GET panels/demo/goals/rows": () => [rows[0]],
    [`GET plugin-actions?${offered("G-1")}`]: () => [],
    [`GET task-kinds?${offered("G-1")}`]: () => [],
  });
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await screen.findByRole("table");
  await waitFor(() => expect(screen.queryByRole("button", { name: /^Update/ })).toBeNull());
  expect(screen.queryByRole("button", { name: /More actions/ })).toBeNull();
});

test("no rows says there is nothing yet", async () => {
  fakeApi({ "GET panels": () => [panel()], "GET panels/demo/goals/rows": () => [] });
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
});

test("a new action shows as a button above the rows, opens its review with no target and refreshes the rows after it applies", async () => {
  const user = userEvent.setup();
  let added = false;
  const calls = fakeApi(
    routes(panel({ new_action: "demo/goal.add" }), {
      "GET plugin-actions": () => [
        { name: "demo/other", label: "Something else", on: null },
        { name: "demo/goal.add", label: "Add a goal", on: null },
      ],
      "GET panels/demo/goals/rows": () => (added ? [...rows, { id: "G-3", values: { title: "A brand new goal", due_date: null, status: "open" } }] : rows),
      "POST plugin-actions/demo/goal.add/preview": () => ({
        token: "t",
        action: "demo/goal.add",
        summary: "Add a goal",
        ops: [{ op: "record.set", label: "Add the goal" }],
        files: [],
        previews: [],
        choices: [],
        notes: [],
        expires_at: "2026-10-09T15:00:00Z",
      }),
      "POST plugin-actions/apply": () => {
        added = true;
        return { changeset: "CS-1", applied: 1, held: 0, refused: 0 };
      },
    }),
  );
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const add = await screen.findByRole("button", { name: "Add a goal" });
  const table = await screen.findByRole("table");
  expect(add.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await user.click(add);
  await screen.findByRole("dialog", { name: "Add a goal" });
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/goal.add/preview")?.body).toEqual({ target: null, choices: {} });
  await user.click(await screen.findByRole("button", { name: "Apply" }));
  expect(await screen.findByText("A brand new goal")).toBeInTheDocument();
  await waitFor(() => expect(add).toHaveFocus());
});

test("with no new action there is no add button", async () => {
  fakeApi(routes(panel(), { "GET plugin-actions": () => [{ name: "demo/goal.add", label: "Add a goal", on: null }] }));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await screen.findByRole("table");
  expect(screen.queryByRole("button", { name: "Add a goal" })).toBeNull();
});

test("a new action nobody offers is not shown", async () => {
  fakeApi(routes(panel({ new_action: "demo/goal.add" }), { "GET plugin-actions": () => [] }));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await screen.findByRole("table");
  expect(screen.queryByRole("button", { name: "Add a goal" })).toBeNull();
});
