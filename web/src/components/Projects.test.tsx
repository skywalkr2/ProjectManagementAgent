import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project, unfiledView } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { groupProjects, Projects } from "./Projects";

const first = project("PRJ-1", "First project");

const note = (id: string, text: string, p: S["ProjectView"] | null): S["NoteView"] => ({
  id,
  text,
  project: p?.id ?? null,
  project_name: p?.name ?? null,
  created_at: "2026-10-09T14:00:00Z",
  trust: "trusted",
});

function api(projects: S["ProjectView"][], extra: Routes = {}) {
  return fakeApi({
    "GET people": () => [],
    "GET projects": () => projects,
    "GET notes": () => [],
    "GET unfiled": () => unfiledView(),
    "GET settings": () => ({ fingerprint: "fp-1", items: [languageItem()] }),
    "GET lists": () => [],
    ...extra,
  });
}

const languageItem = (): S["SettingItem"] => ({
  key: "workspace.language",
  file: "workspace",
  group: "workspace",
  description: "The language and variety work is written in.",
  type: "choice",
  options: ["en-US", "en-GB", "en-AU", "fr-CA"],
  choices: "languages",
  value: "en-US",
  default: "en-US",
  source: "default",
  locked: false,
  basic: true,
  editable: true,
});

const row = async (name: string) => (await screen.findByRole("link", { name })).closest("tr")!;

/** Opens a project's form in its drawer, from the row's menu. */
async function edit(user: ReturnType<typeof userEvent.setup>, name: string) {
  const tr = await row(name);
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
  return screen.findByRole("dialog", { name: "Edit project" });
}

test("projects are a table: the name is a link to its page, the counts are numbers, and an empty cell is empty", async () => {
  api([project("PRJ-1", "Harbor", { status: "At risk", owner_name: "Ana Person", open_actions: 3, open_questions: 0 })]);
  renderApp(<Projects />);
  const tr = await row("Harbor");
  expect(within(tr).getByRole("link", { name: "Harbor" }).getAttribute("href")).toMatch(/#records\/project\/PRJ-1$/);
  expect(within(tr).getByText("At risk")).toBeInTheDocument();
  expect(within(tr).getByText("Ana Person")).toBeInTheDocument();
  expect(within(tr).getByText("3")).toBeInTheDocument();
  // Zero is never shown as a number.
  expect(within(tr).queryByText("0")).toBeNull();
  expect(screen.getByRole("columnheader", { name: "Open to-dos" })).toBeInTheDocument();
});

test("a project's status is colored by its status list's tone, and the words stay", async () => {
  api([project("PRJ-1", "Harbor", { status: "Parked", status_tone: "warn", status_meaning: "blocked" }), project("PRJ-2", "Dock", { status: "Plain words" })]);
  renderApp(<Projects />);
  expect(await screen.findByText("Parked")).toHaveAttribute("data-tone", "warn");
  expect(screen.getByText("Plain words")).toHaveAttribute("data-tone", "neutral");
});

test("projects are grouped by their group, those with none after, and finished ones last under Completed with their group kept", () => {
  const rows = [
    project("PRJ-1", "Zebra", { group: "Books" }),
    project("PRJ-2", "Alpha", { group: "Books" }),
    project("PRJ-3", "Loose"),
    project("PRJ-4", "Wrapped", { group: "Films", status: "Done", completed: true }),
    project("PRJ-5", "Other", { group: "Films" }),
  ];
  const groups = groupProjects(rows, { none: "No group", open: "Open projects", completed: "Completed" });
  expect(groups.map((g) => g.title)).toEqual(["Books", "Films", "No group", "Completed"]);
  expect(groups[0].rows.map((p) => p.name)).toEqual(["Alpha", "Zebra"]);
  expect(groups[1].rows.map((p) => p.name)).toEqual(["Other"]);
  expect(groups[3].rows.map((p) => p.name)).toEqual(["Wrapped"]);
  // With no groups at all the open projects need no group name of their own.
  expect(groupProjects([project("P", "Only")], { none: "No group", open: "Open projects", completed: "Completed" }).map((g) => g.title)).toEqual(["Open projects"]);
});

test("a project inside another is listed under its parent, in the parent's group, with the parent's name beside it", () => {
  const rows = [
    project("PRJ-1", "The series", { group: "Books" }),
    project("PRJ-2", "Book two", { group: "Films", parent: "PRJ-1" }),
    project("PRJ-3", "Book one", { parent: "PRJ-1" }),
    project("PRJ-4", "Elsewhere", { group: "Books" }),
    project("PRJ-5", "Chapter", { group: "Films", parent: "PRJ-3" }),
  ];
  const groups = groupProjects(rows, { none: "No group", open: "Open projects", completed: "Completed" });
  expect(groups.map((g) => g.title)).toEqual(["Books"]);
  // The parent first, then what is inside it (and what is inside that), then the next project of the group.
  expect(groups[0].rows.map((p) => p.name)).toEqual(["Elsewhere", "The series", "Book one", "Chapter", "Book two"]);
});

test("a project whose parent is finished or not there is listed on its own", () => {
  const rows = [
    project("PRJ-1", "Wrapped", { completed: true, status: "Done" }),
    project("PRJ-2", "Orphan", { parent: "PRJ-1" }),
    project("PRJ-3", "Lost", { parent: "PRJ-99" }),
  ];
  const groups = groupProjects(rows, { none: "No group", open: "Open projects", completed: "Completed" });
  expect(groups.map((g) => [g.title, g.rows.map((p) => p.name)])).toEqual([
    ["Open projects", ["Lost", "Orphan"]],
    ["Completed", ["Wrapped"]],
  ]);
});

test("the table shows the stage, the target day and when it was last updated in words, and no health column without a pack", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T12:00:00Z"));
  try {
    api([
      project("PRJ-1", "The series", { phase: "Drafting", target: "2026-12-01", last_change: "2026-10-15T09:00:00Z" }),
      project("PRJ-2", "Book one", { parent: "PRJ-1", phase: "Editing", last_change: "2026-10-20T08:00:00Z" }),
      project("PRJ-3", "Old news", { last_change: "2026-08-01T09:00:00Z" }),
    ]);
    renderApp(<Projects />);
    const tr = await row("The series");
    expect(screen.getByRole("columnheader", { name: "Stage" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Last updated" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /health/i })).toBeNull();
    expect(within(tr).getByText("Drafting")).toBeInTheDocument();
    expect(within(tr).getByText("5 days ago")).toBeInTheDocument();
    expect(within(await row("Book one")).getByText("today")).toBeInTheDocument();
    expect(within(await row("Old news")).getByText("2 months ago")).toBeInTheDocument();
    // The one inside another says so, and sits right after it.
    expect(await row("Book one")).toHaveTextContent("inside The series");
    const names = screen.getAllByRole("link").map((l) => l.textContent);
    expect(names.indexOf("Book one")).toBe(names.indexOf("The series") + 1);
  } finally {
    vi.useRealTimers();
  }
});

test("a finished project is under Completed at the bottom, still listed with its group, and never removed", async () => {
  api([project("PRJ-1", "Wrapped", { group: "Films", status: "Done", completed: true }), project("PRJ-2", "Going", { group: "Books" })]);
  renderApp(<Projects />);
  await row("Wrapped");
  const bodies = screen.getAllByRole("rowgroup").filter((g) => g.tagName === "TBODY");
  expect(bodies.map((b) => b.getAttribute("aria-label"))).toEqual(["Books", "Completed"]);
  const done = within(bodies[1]).getByRole("link", { name: "Wrapped" }).closest("tr")!;
  expect(done).toHaveTextContent("Was in Films");
});

test("a row opens its detail with the facts, its notes and a link to its page; Edit opens the form", async () => {
  const user = userEvent.setup();
  api(
    [
      project("PRJ-2", "Book one", {
        parent: "PRJ-1",
        summary: "Where it stands.",
        language: "en-GB",
        language_own: true,
        budget_usd: 250,
        spent_usd: 40,
        owner_name: "Ana Person",
        role: "watch",
        open_actions: 2,
      }),
      project("PRJ-1", "The series"),
    ],
    { "GET notes": () => [note("N-1", "older note", project("PRJ-2", "Book one")), note("N-2", "other project", project("PRJ-9", "Elsewhere"))] },
  );
  renderApp(<Projects />);
  const tr = await row("Book one");
  await user.click(within(tr).getByText("Ana Person"));
  const detail = await screen.findByRole("dialog", { name: "Book one" });
  expect(within(detail).getByText("Where it stands.")).toBeInTheDocument();
  expect(within(detail).getByText("The series")).toBeInTheDocument();
  expect(within(detail).getByText("Only watch it")).toBeInTheDocument();
  expect(within(detail).getByText("$40.00 of $250.00 spent")).toBeInTheDocument();
  expect(within(detail).getByText("2 open to-dos")).toBeInTheDocument();
  expect(within(detail).getByText("older note")).toBeInTheDocument();
  expect(within(detail).queryByText("other project")).toBeNull();
  expect(within(detail).queryByText(/open questions/)).toBeNull();
  expect(within(detail).getByRole("link", { name: "Open Book one's page" }).getAttribute("href")).toMatch(/#records\/project\/PRJ-2$/);
  await user.click(within(detail).getByRole("button", { name: "Edit" }));
  expect(await screen.findByRole("dialog", { name: "Edit project" })).toBeInTheDocument();
});

test("the project form is a drawer with the cursor in the name; Escape closes it without saving", async () => {
  const user = userEvent.setup();
  const calls = api([first]);
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a project" });
  await waitFor(() => expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveFocus());
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add a project" })).toBeNull());
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("the add button says what is missing instead of being silently off", async () => {
  const user = userEvent.setup();
  api([]);
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a project" });
  const save = within(dialog).getByRole("button", { name: "Add a project" });
  expect(save).toBeDisabled();
  expect(within(dialog).getByText("Add a name first.")).toBeInTheDocument();
});

test("a project's own language that isn't on the list is still shown, never replaced by another", async () => {
  const user = userEvent.setup();
  api([project("PRJ-1", "The series", { language: "tlh", language_own: true })]);
  renderApp(<Projects />);
  const dialog = await edit(user, "The series");
  expect(within(dialog).getByRole("combobox", { name: /Writing preferences/ })).toHaveValue("tlh");
});

test("the form's Your role list changes the part the person has, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api([project("PRJ-1", "Watched one", { role: "watch" })], {
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
    "POST projects/PRJ-1/role": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: ["PRJ-1"], skipped: [] }),
  });
  renderApp(<Projects />);
  const dialog = await edit(user, "Watched one");
  const role = within(dialog).getByRole("combobox", { name: /Your role/ });
  expect(within(role).getAllByRole("option").map((o) => o.textContent)).toEqual(["Run it", "Design for it", "Only watch it"]);
  expect(role).toHaveValue("watch");
  await user.selectOptions(role, "run");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1/role")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1/role")?.body).toEqual({ role: "run" });
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("a project that is being added has no role to pick", async () => {
  const user = userEvent.setup();
  api([]);
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  await screen.findByRole("dialog", { name: "Add a project" });
  expect(screen.queryByRole("combobox", { name: /Your role/ })).toBeNull();
});

const projectLists = (): S["ValueListView"][] => [
  { id: "L-1", name: "project-status", label: "Project status", values: ["On track", "At risk"], retired: [], used_by: ["project.status"] },
  { id: "L-2", name: "project-phase", label: "Project phase", values: ["Planning", "Underway"], retired: [], used_by: ["project.phase"] },
  { id: "L-3", name: "project-group", label: "Project group", values: ["Books"], retired: ["Old shelf"], used_by: ["project.group"] },
  { id: "L-4", name: "project-priority", label: "Project priority", values: ["High", "Low"], retired: [], used_by: ["project.priority"] },
];

test("a project's status, phase and group are chosen from their lists, and the chosen values are saved", async () => {
  const user = userEvent.setup();
  const calls = api([project("PRJ-1", "Book one", { status: "On track", group: "Old shelf" })], {
    "GET lists": projectLists,
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
  });
  renderApp(<Projects />);
  const dialog = await edit(user, "Book one");
  const status = within(dialog).getByRole("combobox", { name: "Status" });
  const phase = within(dialog).getByRole("combobox", { name: "Phase" });
  const group = within(dialog).getByRole("combobox", { name: /Group/ });
  await waitFor(() => expect(within(group).getAllByRole("option").map((o) => o.textContent)).toContain("Old shelf (no longer offered)"));
  expect(within(status).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "On track", "At risk", "Add to the list…"]);
  expect(status).toHaveValue("On track");
  expect(group).toHaveValue("Old shelf");
  await user.selectOptions(status, "At risk");
  await user.selectOptions(phase, "Underway");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  // The group it still held is kept; nothing is lost by editing something else.
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")?.body).toMatchObject({ name: "Book one", status: "At risk", phase: "Underway", group: "Old shelf" });
});

test("a new project with nothing chosen sends no status, phase or group", async () => {
  const user = userEvent.setup();
  const calls = api([], { "GET lists": projectLists, "POST projects": () => ({ id: "PRJ-9" }) });
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a project" });
  await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Fresh");
  await user.click(within(dialog).getByRole("button", { name: "Add a project" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects")?.body).toMatchObject({ name: "Fresh", status: null, phase: null, group: null });
});

test("the project form offers Priority from its list, sends it, and Undo puts the old one back", async () => {
  const user = userEvent.setup();
  const calls = api([project("PRJ-1", "Book one", { priority: "High" })], { "GET lists": projectLists, "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }) });
  renderApp(<Projects />);
  const dialog = await edit(user, "Book one");
  const priority = within(dialog).getByRole("combobox", { name: "Priority" });
  await waitFor(() => expect(within(priority).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "High", "Low", "Add to the list…"]));
  expect(priority).toHaveValue("High");
  await user.selectOptions(priority, "Low");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")!.body).toMatchObject({ priority: "Low" });
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST projects/PRJ-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST projects/PRJ-1")[1].body).toMatchObject({ priority: "High" });
});

test("removing a project acts at once and Undo restores it", async () => {
  const user = userEvent.setup();
  const calls = api([first], { "POST projects/PRJ-1/remove": () => ({ ok: "PRJ-1" }), "POST projects/PRJ-1/restore": () => ({ ok: "PRJ-1" }) });
  renderApp(<Projects />);
  const tr = await row("First project");
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1/remove")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1/restore")).toBe(true));
});

test("an empty workspace says so and offers to add a project", async () => {
  api([]);
  renderApp(<Projects />);
  expect(await screen.findByText(/Nothing here yet\. Add a project/)).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Add a project" })).toHaveLength(2);
});

test("unfiled work is gathered above the table, and the group isn't there when nothing is unfiled", async () => {
  api([first]);
  renderApp(<Projects />);
  await row("First project");
  expect(screen.queryByRole("heading", { name: "Unfiled" })).toBeNull();
  expect(screen.queryByText("0 items")).toBeNull();
});

test("the owner list in the project form has Add a person…: a second drawer opens over the first and the new person is the owner picked", async () => {
  const user = userEvent.setup();
  let made = false;
  const calls = api([], {
    "GET people": () => (made ? [person("PER-9", "Casey Moor")] : []),
    "POST people": () => {
      made = true;
      return { id: "PER-9" };
    },
  });
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const project = await screen.findByRole("dialog", { name: "Add a project" });
  await user.type(within(project).getByRole("textbox", { name: "Name" }), "Fresh");
  await user.selectOptions(within(project).getByRole("combobox", { name: "Owner" }), "Add a person…");
  const adding = await screen.findByRole("dialog", { name: "Add a person" });
  await user.type(within(adding).getByRole("textbox", { name: "Full name" }), "Casey Moor");
  await user.click(within(adding).getByRole("button", { name: "Add a person" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add a person" })).toBeNull());
  // The project's own form is still open with what was typed, and the new person is its owner.
  const still = screen.getByRole("dialog", { name: "Add a project" });
  expect(within(still).getByRole("textbox", { name: "Name" })).toHaveValue("Fresh");
  await waitFor(() => expect(within(still).getByRole("combobox", { name: "Owner" })).toHaveValue("PER-9"));
});

test("a project's other names are a list in its form, saved as the aliases and put back by Undo", async () => {
  const user = userEvent.setup();
  const calls = api([project("PRJ-1", "Book one", { aliases: ["B1"] })], { "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }) });
  renderApp(<Projects />);
  const dialog = await edit(user, "Book one");
  const aliases = within(dialog).getByRole("textbox", { name: /Other names/ });
  expect(aliases).toHaveValue("B1");
  await user.clear(aliases);
  await user.type(aliases, "B1, BOOK-1 , ");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")?.body).toMatchObject({ aliases: ["B1", "BOOK-1"] });
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST projects/PRJ-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST projects/PRJ-1")[1].body).toMatchObject({ aliases: ["B1"] });
});

test("a new project can be given other names, and none is sent as an empty list", async () => {
  const user = userEvent.setup();
  const calls = api([], { "POST projects": () => ({ id: "PRJ-9" }) });
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a project" });
  await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Fresh");
  await user.click(within(dialog).getByRole("button", { name: "Add a project" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects")?.body).toMatchObject({ name: "Fresh", aliases: [] });
});
