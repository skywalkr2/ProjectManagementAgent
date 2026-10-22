import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { org, person, project } from "../lib/records-fixtures";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { People } from "./People";
import { Projects } from "./Projects";
import { SyncPanel } from "./SyncPanel";

// The forms that set a workspace up (design 5.1, 7.14): a person's, a project's and the synced folder's. The screens that
// hold them are People and Projects, and Settings for the folder; each has its own test file for the rest.

const undoToast = async (user: ReturnType<typeof userEvent.setup>) => user.click(await screen.findByRole("button", { name: "Undo" }));

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

const folderItem = (value: string): S["SettingItem"] => ({
  key: "storage.sync.folder",
  file: "storage",
  group: "storage.sync",
  description: "Where the synced folder is.",
  type: "text",
  options: [],
  value,
  default: "",
  source: "default",
  locked: false,
  basic: true,
  editable: true,
  picker: "folder",
});

/** A fake server for the project screen. */
function api(projects: S["ProjectView"][], extra: Routes = {}) {
  return fakeApi({
    "GET people": () => [],
    "GET projects": () => projects,
    "GET notes": () => [],
    "GET unfiled": () => ({ count: 0, items: [] }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [languageItem()] }),
    "GET lists": () => [],
    ...extra,
  });
}

const row = async (name: string) => (await screen.findByRole("link", { name })).closest("tr")!;

async function edit(user: ReturnType<typeof userEvent.setup>, name: string, title: string) {
  const tr = await row(name);
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
  return screen.findByRole("dialog", { name: title });
}


function others(routes: Routes, folder = "/shared/Cockpit") {
  return fakeApi({
    "GET settings": () => ({ fingerprint: "fp-1", items: [folderItem(folder), languageItem()] }),
    ...routes,
  });
}

async function section(name: string) {
  return (await screen.findByRole("region", { name })) as HTMLElement;
}

test("the person form has a first name field; it is sent as typed, or as nothing when empty, and undo puts the old one back", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET people": () => [person("P-1", "Ana Person", { first_name: "Anita" })],
    "GET organizations": () => [org("ORG-1", "Org one")],
    "POST people/P-1": () => ({ ok: "P-1" }),
  });
  renderApp(<People />);
  const tr = (await screen.findByRole("link", { name: "Ana Person" })).closest("tr")!;
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit person" });
  const field = within(dialog).getByLabelText(/^First name/);
  expect(field).toHaveValue("Anita");
  await user.clear(field);
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST people/P-1")!.body).toMatchObject({ first_name: null });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST people/P-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST people/P-1")[1].body).toMatchObject({ first_name: "Anita" });
});

test("the project form offers Inside (never itself), Language with the inherited one as a hint, and a budget; they are saved", async () => {
  const user = userEvent.setup();
  const calls = api(
    [
      project("PRJ-1", "The series", { language: "en-GB", language_own: true }),
      project("PRJ-2", "Book one", { parent: "PRJ-1", language: "en-GB", language_own: false }),
    ],
    { "POST projects/PRJ-2": () => ({ ok: "PRJ-2" }) },
  );
  renderApp(<Projects />);
  const dialog = await edit(user, "Book one", "Edit project");
  const inside = within(dialog).getByRole("combobox", { name: "Inside" });
  expect(within(inside).getAllByRole("option").map((o) => o.textContent)).toEqual(["None", "The series"]);
  expect(inside).toHaveValue("PRJ-1");
  const language = within(dialog).getByRole("combobox", { name: /Writing preferences/ });
  expect(language).toHaveValue("");
  const labels = within(language).getAllByRole("option").map((o) => o.textContent);
  expect(labels[0]).toBe("Same as English (United Kingdom)");
  expect(labels.slice(1)).toEqual(["English (Australia)", "English (United Kingdom)", "English (United States)", "French (Canada)"]);
  expect(within(dialog).getByText("Choose a writing preference to override the parent project's choice.")).toBeInTheDocument();
  const budget = within(dialog).getByRole("spinbutton", { name: /Budget \(US dollars\)/ });
  expect(budget).toHaveValue(null);
  await user.selectOptions(language, "en-AU");
  await user.type(budget, "120.5");
  await user.selectOptions(inside, "");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-2")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-2")?.body).toMatchObject({ parent: null, language: "en-AU", budget_usd: 120.5 });
});

test("a project with no project around it names the workspace as what an empty language follows", async () => {
  const user = userEvent.setup();
  api([]);
  renderApp(<Projects />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const language = await screen.findByRole("combobox", { name: /Writing preferences/ });
  expect(within(language).getAllByRole("option")[0]).toHaveTextContent("Same as the workspace");
});

test("choosing Same as for the language and clearing the budget send nothing, so the project inherits and has no cap", async () => {
  const user = userEvent.setup();
  const calls = api([project("PRJ-1", "The series", { language: "en-GB", language_own: true, budget_usd: 50 })], {
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
  });
  renderApp(<Projects />);
  const dialog = await edit(user, "The series", "Edit project");
  const language = within(dialog).getByRole("combobox", { name: /Writing preferences/ });
  expect(language).toHaveValue("en-GB");
  await user.selectOptions(language, "");
  await user.clear(within(dialog).getByRole("spinbutton", { name: /Budget/ }));
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")?.body).toMatchObject({ parent: null, language: null, budget_usd: null });
});

test("after choosing a folder the question about sharing comes first, can be gone back from, and saves nothing by itself", async () => {
  const user = userEvent.setup();
  const calls = others({ "GET jobs": () => [], "GET setup/folders": () => new Refuse(403, "no") }, "");
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  await user.type(await within(sync).findByLabelText("Folder"), "/mnt/team");
  await user.click(within(sync).getByRole("button", { name: "Use this folder" }));
  const first = await within(sync).findByRole("radio", { name: "No, only I use it" });
  expect(first).toHaveFocus(); // the cursor starts in the first field of the step
  expect(first).not.toBeChecked();
  expect(within(sync).getByRole("radio", { name: "Yes, someone else can" })).not.toBeChecked();
  expect(within(sync).getByText(/never as your instructions/)).toBeInTheDocument();
  await user.click(within(sync).getByRole("button", { name: "Choose another folder" }));
  expect(await within(sync).findByLabelText("Folder")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST settings")).toBe(false);
});
