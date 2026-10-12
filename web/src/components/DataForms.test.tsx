import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { DataForms, fileNameOf } from "./DataForms";

type Item = S["SettingItem"];
type DataFile = S["DataFile"];

const field = (key: string, type: Item["type"], extra: Partial<Item> = {}): Item => ({
  key,
  file: "classic.yaml",
  group: "",
  description: `About ${key}`,
  type,
  options: [],
  value: null,
  default: null,
  source: "file",
  locked: false,
  basic: false,
  editable: true,
  ...extra,
});

const FORM: S["DataFormView"] = {
  name: "demo/template",
  plugin: "demo",
  label: "Templates",
  description: "How a book looks.",
  pattern: "*.yaml",
  single: false,
};
const file = (name: string, layers: DataFile["layers"], extra: Partial<DataFile> = {}): DataFile => ({
  file: name,
  layers,
  layer: layers[layers.length - 1] ?? null,
  problem: null,
  ...extra,
});

const ITEMS = [field("title", "text", { value: "Classic", default: "Plain" }), field("sizes.body", "integer", { value: 11, default: 12 })];
const view = (name: string, extra: Partial<S["DataFileView"]> = {}): S["DataFileView"] => ({
  file: name,
  layer: "shipped",
  layers: ["shipped"],
  items: ITEMS,
  ...extra,
});

function open(extra: Record<string, (body: unknown) => unknown> = {}) {
  const calls = fakeApi({
    "GET data-forms": () => [FORM],
    "GET data-forms/demo/template/files": () => [file("classic.yaml", ["shipped"]), file("mine.yaml", ["workspace"]), file("both.yaml", ["shipped", "workspace"])],
    "GET data-forms/demo/template/file?path=classic.yaml": () => view("classic.yaml"),
    "GET projects": () => [],
    ...extra,
  });
  renderApp(<DataForms />);
  return { calls, user: userEvent.setup() };
}

const row = async (name: string) => (await screen.findByRole("listitem", { name })) as HTMLElement;
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

test("a file's name takes the .yaml ending as typed or not", () => {
  expect(fileNameOf(" notes ")).toBe("notes");
  expect(fileNameOf("notes.yaml")).toBe("notes");
  expect(fileNameOf("Notes.YAML")).toBe("Notes");
});

test("nothing shows until an add-on offers a form", async () => {
  const calls = fakeApi({ "GET data-forms": () => [], "GET projects": () => [] });
  renderApp(<DataForms />);
  await waitFor(() => expect(calls.some((c) => c.route === "GET data-forms")).toBe(true));
  expect(screen.queryByRole("heading", { name: "Add-on files" })).toBeNull();
});

test("each file lists where it comes from, and a file that doesn't fit its form has a warning line", async () => {
  open({
    "GET data-forms/demo/template/files": () => [
      file("classic.yaml", ["shipped"]),
      file("mine.yaml", ["workspace"]),
      file("both.yaml", ["shipped", "workspace"], { problem: "sizes.body: Input should be a valid integer" }),
      file("proj.yaml", ["shipped", "project"]),
    ],
  });
  expect(await screen.findByRole("heading", { name: "Add-on files" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Demo: Templates" })).toBeInTheDocument();
  expect(screen.getByText("How a book looks.")).toBeInTheDocument();
  expect(await row("classic.yaml")).toHaveTextContent("Comes with the add-on");
  expect(await row("mine.yaml")).toHaveTextContent("Your copy");
  expect(await row("proj.yaml")).toHaveTextContent("This project's copy");
  const both = await row("both.yaml");
  expect(both).toHaveTextContent("Your copy");
  expect(both).toHaveTextContent("Doesn't fit the form: sizes.body: Input should be a valid integer");
  expect(await row("classic.yaml")).not.toHaveTextContent("Doesn't fit");
});

test("opening a file shows it as a form; saving writes your copy with only what changed, and reads back with Undo", async () => {
  const { calls, user } = open({
    "POST data-forms/demo/template/file": () => ({ before: null }),
    "POST data-forms/demo/template/restore": () => ({ before: null }),
  });
  await user.click(await screen.findByRole("button", { name: "Change classic.yaml" }));
  const form = await screen.findByRole("form", { name: "Changing classic.yaml" });
  expect(within(form).getByText(/Saving writes your own copy/)).toBeInTheDocument();
  expect(await within(form).findByLabelText("About title")).toHaveValue("Classic");
  expect(within(form).getByLabelText("About sizes.body")).toHaveValue("11");
  // Nothing changed yet, so there is nothing to save.
  expect(within(form).getByRole("button", { name: "Save classic.yaml" })).toBeDisabled();
  await user.clear(within(form).getByLabelText("About sizes.body"));
  await user.type(within(form).getByLabelText("About sizes.body"), "10");
  await user.click(within(form).getByRole("button", { name: "Save classic.yaml" }));
  await waitFor(() => expect(body(calls, "POST data-forms/demo/template/file")).toBeDefined());
  expect(body(calls, "POST data-forms/demo/template/file")).toEqual({
    file: "classic.yaml",
    layer: "workspace",
    project: null,
    changes: { "sizes.body": 10 },
  });
  expect(await screen.findByText("Saved your copy of classic.yaml.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("form", { name: "Changing classic.yaml" })).toBeNull());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(body(calls, "POST data-forms/demo/template/restore")).toEqual({ file: "classic.yaml", layer: "workspace", project: null, before: null }),
  );
});

test("the form takes a project: its files are those of the project, and saving writes the project's copy", async () => {
  const { calls, user } = open({
    "GET projects": () => [{ id: "p1", name: "Harbor", parent: null }],
    "GET data-forms/demo/template/files?project=p1": () => [file("classic.yaml", ["shipped", "project"])],
    "GET data-forms/demo/template/file?path=classic.yaml&project=p1": () => view("classic.yaml", { layer: "project", layers: ["shipped", "project"] }),
    "POST data-forms/demo/template/file": () => ({ before: "title: Old\n" }),
    "POST data-forms/demo/template/restore": () => ({ before: null }),
  });
  await user.selectOptions(await screen.findByLabelText("Files for"), "p1");
  expect(await row("classic.yaml")).toHaveTextContent("This project's copy");
  await user.click(screen.getByRole("button", { name: "Change classic.yaml" }));
  const form = await screen.findByRole("form", { name: "Changing classic.yaml" });
  expect(within(form).getByText("Saving writes a copy for this project only.")).toBeInTheDocument();
  await user.clear(await within(form).findByLabelText("About title"));
  await user.type(within(form).getByLabelText("About title"), "Harbor");
  await user.click(within(form).getByRole("button", { name: "Save classic.yaml" }));
  await waitFor(() => expect(body(calls, "POST data-forms/demo/template/file")).toBeDefined());
  expect(body(calls, "POST data-forms/demo/template/file")).toEqual({
    file: "classic.yaml",
    layer: "project",
    project: "p1",
    changes: { title: "Harbor" },
  });
  expect(await screen.findByText("Saved this project's copy of classic.yaml.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(body(calls, "POST data-forms/demo/template/restore")).toEqual({ file: "classic.yaml", layer: "project", project: "p1", before: "title: Old\n" }),
  );
});

test("New file asks for a lowercase name, adds .yaml, starts from the defaults and saves under that name", async () => {
  const { calls, user } = open({
    "GET data-forms/demo/template/file?path=fresh.yaml": () =>
      view("fresh.yaml", { layer: null, layers: [], items: ITEMS.map((i) => ({ ...i, value: i.default, source: "default" as const })) }),
    "POST data-forms/demo/template/file": () => ({ before: null }),
  });
  await user.click(await screen.findByRole("button", { name: "New file for Templates" }));
  const ask = await screen.findByRole("form", { name: "New file" });
  const name = within(ask).getByLabelText("Name of the new file");
  expect(name).toHaveFocus();
  // A name that can't be used says why, and one already taken is named.
  await user.type(name, "Fresh Start");
  expect(within(ask).getByText(/Use lowercase letters, digits/)).toBeInTheDocument();
  expect(within(ask).getByRole("button", { name: "Start from the defaults" })).toBeDisabled();
  await user.clear(name);
  await user.type(name, "mine");
  expect(within(ask).getByText("There is already a file called mine.yaml.")).toBeInTheDocument();
  await user.clear(name);
  await user.type(name, "fresh.yaml");
  await user.click(within(ask).getByRole("button", { name: "Start from the defaults" }));
  const form = await screen.findByRole("form", { name: "New file fresh.yaml" });
  // The defaults, and a new file can be saved as it is.
  expect(await within(form).findByLabelText("About title")).toHaveValue("Plain");
  await user.click(within(form).getByRole("button", { name: "Save fresh.yaml" }));
  await waitFor(() => expect(body(calls, "POST data-forms/demo/template/file")).toBeDefined());
  expect(body(calls, "POST data-forms/demo/template/file")).toEqual({ file: "fresh.yaml", layer: "workspace", project: null, changes: {} });
});

test("a file that has your copy offers Remove your copy, with Undo; one that hasn't doesn't", async () => {
  const { calls, user } = open({
    "POST data-forms/demo/template/remove": () => ({ before: "title: Mine\n" }),
    "POST data-forms/demo/template/restore": () => ({ before: null }),
  });
  // classic.yaml comes only with the add-on: its menu has nothing to remove, so it has no menu.
  expect(within(await row("classic.yaml")).queryByRole("button", { name: "More actions for classic.yaml" })).toBeNull();
  await user.click(within(await row("both.yaml")).getByRole("button", { name: "More actions for both.yaml" }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove your copy" }));
  await waitFor(() =>
    expect(body(calls, "POST data-forms/demo/template/remove")).toEqual({ file: "both.yaml", layer: "workspace", project: null }),
  );
  expect(await screen.findByText("Removed your copy of both.yaml.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(body(calls, "POST data-forms/demo/template/restore")).toEqual({
      file: "both.yaml",
      layer: "workspace",
      project: null,
      before: "title: Mine\n",
    }),
  );
});

test("a refusal from the server is shown on the form, which stays open", async () => {
  const { user } = open({ "POST data-forms/demo/template/file": () => new Refuse(409, "sizes.body: must be at least 6") });
  await user.click(await screen.findByRole("button", { name: "Change classic.yaml" }));
  const form = await screen.findByRole("form", { name: "Changing classic.yaml" });
  await user.clear(await within(form).findByLabelText("About sizes.body"));
  await user.type(within(form).getByLabelText("About sizes.body"), "2");
  await user.click(within(form).getByRole("button", { name: "Save classic.yaml" }));
  expect(await within(form).findByRole("alert")).toHaveTextContent("sizes.body: must be at least 6");
  expect(screen.getByRole("form", { name: "Changing classic.yaml" })).toBeInTheDocument();
});

test("a copy that doesn't fit the form says so on the form and can be saved to fix it", async () => {
  const { user } = open({
    "GET data-forms/demo/template/file?path=classic.yaml": () => view("classic.yaml", { layer: "workspace", layers: ["workspace"], problem: "sizes.body: not a number" }),
  });
  await user.click(await screen.findByRole("button", { name: "Change classic.yaml" }));
  const form = await screen.findByRole("form", { name: "Changing classic.yaml" });
  expect(await within(form).findByText(/doesn't fit the form, so the defaults are shown/)).toBeInTheDocument();
  expect(within(form).getByRole("button", { name: "Save classic.yaml" })).toBeEnabled();
});
