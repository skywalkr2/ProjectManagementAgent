import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, Refuse, renderApp, type Routes } from "../test-utils";
import { Panel } from "./Panel";

const WEB = "https" + "://";

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
  expect(screen.getByRole("heading", { level: 1, name: "Goals" })).toBeInTheDocument();
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
  await user.click(await screen.findByRole("button", { name: "Make these changes" }));
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

test("in the context of a project the panel is looked up for that project; without one, with none", async () => {
  const withProject = fakeApi({
    ...routes(panel()),
    "GET panels?project=PRJ-1": () => [panel()],
    "GET panels/demo/goals/rows?project=PRJ-1": () => rows,
  });
  const { unmount } = renderApp(<Panel name="demo/goals" project="PRJ-1" onOpenRecord={() => {}} />);
  await screen.findByRole("table");
  expect(withProject.map((c) => c.route)).toContain("GET panels?project=PRJ-1");
  expect(withProject.map((c) => c.route)).not.toContain("GET panels");
  unmount();

  const without = fakeApi(routes(panel()));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  await screen.findByRole("table");
  expect(without.map((c) => c.route)).toContain("GET panels");
  expect(without.map((c) => c.route).filter((r) => r.startsWith("GET panels?"))).toEqual([]);
});

test("a panel the project's add-on doesn't show there says the list didn't load, not an empty one", async () => {
  fakeApi({ "GET panels?project=PRJ-1": () => [], "GET panels/demo/goals/rows?project=PRJ-1": () => rows });
  renderApp(<Panel name="demo/goals" project="PRJ-1" onOpenRecord={() => {}} />);
  expect(await screen.findByText("This list didn't load.")).toBeInTheDocument();
});

function documentPanel(): S["PanelView"] {
  return panel({ view: "document", kind: "", columns: [], primary_action: null, row_actions: [] });
}

function documentRoutes(input: BlockIn[] | null, extra: Routes = {}): Routes {
  return { "GET panels": () => [documentPanel()], "GET panels/demo/goals/document": () => ({ blocks: input && filled(input) }), ...extra };
}

const plain = (text: string, more: Partial<S["DocumentInline"]> = {}): S["DocumentInline"] => ({
  text,
  strong: false,
  em: false,
  code: false,
  ...more,
});
type BlockIn = Partial<S["DocumentBlock"]> & Pick<S["DocumentBlock"], "type">;
const filled = (blocks: BlockIn[]): S["DocumentBlock"][] => blocks.map((b) => ({ ordered: false, ...b }));

test("a document draws every kind of block as its own elements under the panel's heading", async () => {
  const outside = `${WEB}docs.example.com/guide`;
  fakeApi(
    documentRoutes([
      { type: "heading", level: 1, inlines: [plain("First")] },
      { type: "paragraph", inlines: [plain("Plain "), plain("bold", { strong: true }), plain(" "), plain("slanted", { em: true }), plain(" "), plain("mono", { code: true })] },
      { type: "heading", level: 2, inlines: [plain("Second")] },
      { type: "list", ordered: false, items: [[plain("apple")], [plain("pear")]] },
      { type: "heading", level: 3, inlines: [plain("Third")] },
      { type: "list", ordered: true, items: [[plain("one")], [plain("two")]] },
      { type: "table", header: [[plain("Name")], [plain("Size")]], rows: [[[plain("small")], [plain("S")]], [[plain("large")], [plain("L")]]] },
      { type: "rule" },
      { type: "paragraph", inlines: [plain("See "), plain("the guide", { url: outside, domain: "docs.example.com" })] },
    ]),
  );
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  expect(await screen.findByRole("heading", { level: 3, name: "First" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "Goals" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 4, name: "Second" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 5, name: "Third" })).toBeInTheDocument();
  expect(screen.getByText("bold").tagName).toBe("STRONG");
  expect(screen.getByText("slanted").tagName).toBe("EM");
  expect(screen.getByText("mono").tagName).toBe("CODE");
  const lists = screen.getAllByRole("list");
  expect(lists.map((l) => l.tagName)).toEqual(["UL", "OL"]);
  expect(within(lists[0]).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["apple", "pear"]);
  const table = screen.getByRole("table");
  expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Name", "Size"]);
  expect(within(table).getAllByRole("columnheader").every((h) => h.getAttribute("scope") === "col")).toBe(true);
  expect(within(table).getAllByRole("row")).toHaveLength(3);
  expect(within(table).getByRole("cell", { name: "large" })).toBeInTheDocument();
  expect(table.closest(".table-wrap")).not.toBeNull();
  expect(screen.getByRole("separator")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "the guide" })).toHaveAttribute("href", outside);
});

test("an outside link in a document opens in a new tab safely and shows its real domain", async () => {
  const outside = `${WEB}docs.example.com/guide`;
  fakeApi(documentRoutes([{ type: "paragraph", inlines: [plain("the guide", { url: outside, domain: "docs.example.com" })] }]));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  const link = await screen.findByRole("link", { name: "the guide" });
  expect(link).toHaveAttribute("target", "_blank");
  expect(link.getAttribute("rel")).toContain("noopener");
  expect(screen.getByText("(docs.example.com)")).toBeInTheDocument();
});

test("a record link in a document opens that record's page", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi(documentRoutes([{ type: "paragraph", inlines: [plain("Open "), plain("the goal", { record: { kind: KIND, id: "G-2" } })] }]));
  renderApp(<Panel name="demo/goals" onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "the goal" }));
  expect(open).toHaveBeenCalledWith(KIND, "G-2");
});

test("markup in a document's text stays text", async () => {
  fakeApi(documentRoutes([{ type: "paragraph", inlines: [plain("<script>alert(1)</script> and <b>bold</b>")] }]));
  const { container } = renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  expect(await screen.findByText("<script>alert(1)</script> and <b>bold</b>")).toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("b")).toBeNull();
});

test("a document with nothing to show says so, and does not ask for rows", async () => {
  const calls = fakeApi(documentRoutes(null));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  expect(await screen.findByText("Nothing to show here yet.")).toBeInTheDocument();
  expect(calls.some((c) => c.route.includes("/rows"))).toBe(false);
});

test("a document the server refuses shows the server's words as the panel's problem", async () => {
  fakeApi(documentRoutes(null, { "GET panels/demo/goals/document": () => new Refuse(409, "The add-on is not running.") }));
  renderApp(<Panel name="demo/goals" onOpenRecord={() => {}} />);
  expect(await screen.findByText(/The add-on is not running\./)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

test("a document is looked up for the project in view", async () => {
  const calls = fakeApi({
    "GET panels?project=PRJ-1": () => [documentPanel()],
    "GET panels/demo/goals/document?project=PRJ-1": () => ({ blocks: filled([{ type: "paragraph", inlines: [plain("For the project")] }]) }),
  });
  renderApp(<Panel name="demo/goals" project="PRJ-1" onOpenRecord={() => {}} />);
  expect(await screen.findByText("For the project")).toBeInTheDocument();
  expect(calls.map((c) => c.route)).toContain("GET panels/demo/goals/document?project=PRJ-1");
});
