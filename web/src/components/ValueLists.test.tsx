import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { ValueLists } from "./ValueLists";

const lists = (): S["ValueListView"][] => [
  {
    id: "L-1",
    name: "project-status",
    label: "Project status",
    values: ["On track", "At risk"],
    retired: ["Cancelled"],
    used_by: ["project.status"],
  },
  { id: "L-2", name: "project-group", label: "Project group", values: [], retired: [], used_by: ["project.group"] },
  { id: "L-3", name: "demo/stages", label: "Stages", values: ["Draft"], retired: [], used_by: ["demo/chapter.stage"] },
  { id: "L-4", name: "loose", label: "Loose list", values: ["One"], retired: [], used_by: [] },
];

function api(extra: Routes = {}) {
  return fakeApi({ "GET lists": lists, ...extra });
}

async function block(label: string) {
  return (await screen.findByText(label)).closest("li")! as HTMLElement;
}

async function pick(user: ReturnType<typeof userEvent.setup>, row: HTMLElement, value: string, action: string) {
  await user.click(within(row).getByRole("button", { name: new RegExp(`More actions for ${value}`) }));
  await user.click(await screen.findByRole("menuitem", { name: action }));
}

test("each list shows its label, where it is used in plain words, and its values in order", async () => {
  api();
  renderApp(<ValueLists />);
  expect(await screen.findByRole("heading", { name: "Lists" })).toBeInTheDocument();
  const status = await block("Project status");
  expect(status).toHaveTextContent("Used for: project status");
  expect(within(status).getAllByRole("listitem").map((li) => li.textContent?.replace(/•+/, ""))).toEqual(["On track", "At risk"]);
  expect(within(await block("Project group")).getByText("Nothing is offered yet.")).toBeInTheDocument();
  // Another add-on's field is named from its kind; a list nothing uses says nothing about use.
  expect(await block("Stages")).toHaveTextContent("Used for: Chapter stage");
  expect(await block("Loose list")).not.toHaveTextContent("Used for");
});

test("nothing shows while the lists load or when there are none, and a failure says so quietly", async () => {
  fakeApi({ "GET lists": () => [] });
  const { unmount } = renderApp(<ValueLists />);
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("heading", { name: "Lists" })).toBeNull();
  unmount();
  fakeApi({ "GET lists": () => new Refuse(500, "") });
  renderApp(<ValueLists />);
  expect(await screen.findByText("The lists didn't load.")).toBeInTheDocument();
});

test("Rename edits the value in place, sends it, and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST lists/project-status/rename": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [{ kind: "value_list", id: "L-1" }], skipped: [] }),
  });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  await pick(user, row, "At risk", "Rename");
  const field = within(row).getByRole("textbox", { name: "New name for At risk" });
  expect(field).toHaveFocus();
  expect(field).toHaveValue("At risk");
  await user.clear(field);
  await user.type(field, "Needs help{Enter}");
  await waitFor(() => expect(calls.some((c) => c.route === "POST lists/project-status/rename")).toBe(true));
  expect(calls.find((c) => c.route === "POST lists/project-status/rename")?.body).toEqual({ value: "At risk", to: "Needs help" });
  expect(await screen.findByText("Renamed At risk to Needs help.")).toBeInTheDocument();
  await waitFor(() => expect(within(row).queryByRole("textbox", { name: /New name/ })).toBeNull());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-1/undo"));
});

test("Escape leaves a value as it was, and a refused rename shows why and keeps what was typed", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST lists/project-status/rename": () => new Refuse(422, "That name is already on the list.") });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  await pick(user, row, "At risk", "Rename");
  await user.type(within(row).getByRole("textbox", { name: "New name for At risk" }), "{Escape}");
  expect(within(row).queryByRole("textbox", { name: /New name/ })).toBeNull();
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
  await pick(user, row, "At risk", "Rename");
  const field = within(row).getByRole("textbox", { name: "New name for At risk" });
  await user.clear(field);
  await user.type(field, "On track{Enter}");
  expect(await within(row).findByRole("alert")).toHaveTextContent("That name is already on the list.");
  expect(within(row).getByRole("textbox", { name: "New name for At risk" })).toHaveValue("On track");
});

test("Stop offering retires the value at once, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST lists/project-status/retire": () => ({ changeset: "CS-2" }),
    "POST changesets/CS-2/undo": () => ({ restored: [{ kind: "value_list", id: "L-1" }], skipped: [] }),
  });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  await pick(user, row, "On track", "Stop offering");
  await waitFor(() => expect(calls.some((c) => c.route === "POST lists/project-status/retire")).toBe(true));
  expect(calls.find((c) => c.route === "POST lists/project-status/retire")?.body).toEqual({ value: "On track" });
  expect(await screen.findByText("On track is no longer offered in Project status.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-2/undo"));
});

test("values that are no longer offered sit behind a disclosure, and Offer again adds the value back, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST lists/project-status/add": () => ({ changeset: "CS-3" }),
    "POST changesets/CS-3/undo": () => ({ restored: [{ kind: "value_list", id: "L-1" }], skipped: [] }),
  });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  const toggle = within(row).getByRole("button", { name: "No longer offered (1)" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(within(row).queryByText("Cancelled", { selector: ".list-value" })).toBeNull();
  await user.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(within(row).getByText("Cancelled", { selector: ".list-value" })).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Offer again Cancelled" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST lists/project-status/add")).toBe(true));
  expect(calls.find((c) => c.route === "POST lists/project-status/add")?.body).toEqual({ value: "Cancelled" });
  expect(await screen.findByText("Cancelled is offered again in Project status.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-3/undo"));
});

test("Add a value sends it to its own list, clears the field and offers Undo; a list with a namespaced name keeps its slash", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST lists/project-group/add": () => ({ changeset: "CS-5" }),
    "POST lists/demo/stages/add": () => ({ changeset: "CS-6" }),
  });
  renderApp(<ValueLists />);
  const group = await block("Project group");
  const field = within(group).getByRole("textbox", { name: "Add a choice to Project group" });
  expect(within(group).getByRole("button", { name: /^Add/ })).toBeDisabled();
  await user.type(field, "Books{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/project-group/add")?.body).toEqual({ value: "Books" }));
  expect(await screen.findByText("Added Books to Project group.")).toBeInTheDocument();
  await waitFor(() => expect(field).toHaveValue(""));
  const stages = await block("Stages");
  await user.type(within(stages).getByRole("textbox", { name: "Add a choice to Stages" }), "Review");
  await user.click(within(stages).getByRole("button", { name: /^Add/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/demo/stages/add")?.body).toEqual({ value: "Review" }));
});

test("a refused add shows why and keeps what was typed", async () => {
  const user = userEvent.setup();
  api({ "POST lists/project-group/add": () => new Refuse(422, "That is not a valid value.") });
  renderApp(<ValueLists />);
  const group = await block("Project group");
  const field = within(group).getByRole("textbox", { name: "Add a choice to Project group" });
  await user.type(field, "??{Enter}");
  expect(await within(group).findByRole("alert")).toHaveTextContent("That is not a valid value.");
  expect(field).toHaveValue("??");
});

// ---- tone and meaning ---------------------------------------------------------------------------------------------------

const statusList = (): S["ValueListView"] => ({
  id: "L-1",
  name: "project-status",
  label: "Project status",
  values: ["On track", "At risk", "Parked"],
  retired: [],
  used_by: ["project.status"],
  status: true,
  tones: { "On track": "ok", "At risk": "warn", Parked: "neutral" },
  meanings: { "On track": "open", "At risk": "at_risk", Parked: "blocked" },
});

test("each value says what it counts as and how it looks, in words as well as color, and a plain value says nothing", async () => {
  fakeApi({ "GET lists": () => [statusList(), { ...lists()[1], tones: { Books: "danger" }, values: ["Books", "Misc"] }] });
  renderApp(<ValueLists />);
  const status = await block("Project status");
  const items = within(status).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("On trackCounts as: Under way");
  expect(items[1]).toHaveTextContent("At riskCounts as: At risk");
  expect(items[2]).toHaveTextContent("ParkedCounts as: Blocked");
  expect(within(items[1]).getByText("Counts as: At risk")).toHaveAttribute("data-tone", "warn");
  const group = await block("Project group");
  expect(within(group).getByText("Problem")).toBeInTheDocument();
  expect(within(group).getAllByRole("listitem")[1]).toHaveTextContent(/^Misc/);
  expect(within(group).getAllByRole("listitem")[1]).not.toHaveTextContent("Plain");
});

test("adding a value to a status list asks what it means, with the suggestion chosen, and sends both", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET lists": () => [statusList()],
    "GET list-suggestion?list=project-status&value=Paused": () => ({ tone: "warn", meaning: "blocked" }),
    "POST lists/project-status/add": () => ({ changeset: "CS-9" }),
  });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  await user.type(within(row).getByRole("textbox", { name: "Add a choice to Project status" }), "Paused");
  const meaning = within(row).getByRole("combobox", { name: "What it means" });
  await waitFor(() => expect(meaning).toHaveValue("blocked"));
  expect(within(row).getByRole("combobox", { name: "How it looks" })).toHaveValue("warn");
  expect(within(row).getByText("Suggested from the wording; change it if it's wrong.")).toBeInTheDocument();
  await user.selectOptions(meaning, "at_risk");
  expect(within(row).queryByText("Suggested from the wording; change it if it's wrong.")).toBeNull();
  await user.click(within(row).getByRole("button", { name: /^Add/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/project-status/add")?.body).toEqual({ value: "Paused", tone: "warn", meaning: "at_risk" }));
});

test("a status value typed before any suggestion arrives is sent as open work with no color", async () => {
  const user = userEvent.setup();
  const calls = api({ "GET lists": () => [statusList()], "POST lists/project-status/add": () => ({ changeset: "CS-9" }) });
  renderApp(<ValueLists />);
  const row = await block("Project status");
  await user.type(within(row).getByRole("textbox", { name: "Add a choice to Project status" }), "Zzz{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/project-status/add")?.body).toEqual({ value: "Zzz", tone: "neutral", meaning: "open" }));
});

test("a list with no meanings asks only how a value looks, and sends nothing extra when left plain", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST lists/project-group/add": () => ({ changeset: "CS-5" }) });
  renderApp(<ValueLists />);
  const group = await block("Project group");
  await user.type(within(group).getByRole("textbox", { name: "Add a choice to Project group" }), "Books");
  expect(within(group).queryByRole("combobox", { name: "What it means" })).toBeNull();
  const tone = within(group).getByRole("combobox", { name: "How it looks" });
  expect(tone).toHaveValue("neutral");
  await user.click(within(group).getByRole("button", { name: /^Add/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/project-group/add")?.body).toEqual({ value: "Books" }));
});

test("choosing a look for a value on a list with no meanings sends the tone", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST lists/project-group/add": () => ({ changeset: "CS-5" }) });
  renderApp(<ValueLists />);
  const group = await block("Project group");
  await user.type(within(group).getByRole("textbox", { name: "Add a choice to Project group" }), "Urgent");
  await user.selectOptions(within(group).getByRole("combobox", { name: "How it looks" }), "danger");
  await user.click(within(group).getByRole("button", { name: /^Add/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST lists/project-group/add")?.body).toEqual({ value: "Urgent", tone: "danger" }));
});
