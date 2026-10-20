import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { org, person } from "../lib/records-fixtures";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { People } from "./People";

const firstOrg = org("ORG-1", "Org one", 2);
const secondOrg = org("ORG-2", "Org two", 0);

function api(people: S["PersonView"][], extra: Routes = {}) {
  return fakeApi({
    "GET people": () => people,
    "GET organizations": () => [firstOrg, secondOrg],
    ...extra,
  });
}

const row = async (name: string) => (await screen.findByRole("link", { name })).closest("tr")!;
const undoToast = async (user: ReturnType<typeof userEvent.setup>) => user.click(await screen.findByRole("button", { name: "Undo" }));

/** Opens a person's form in its drawer, from the row's menu. */
async function edit(user: ReturnType<typeof userEvent.setup>, name: string) {
  const tr = await row(name);
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
  return screen.findByRole("dialog", { name: "Edit person" });
}

test("people are a table with role, organization by name, open items and last contact; the name links to the person's page", async () => {
  api([
    person("P-1", "Ana Person", { role: "Editor", org: firstOrg.id, org_name: firstOrg.name, open_items: 4, last_contact: "2026-10-08", how_to_reach: { email: "ana@example.com" } }),
    person("P-2", "Ben Person"),
  ]);
  renderApp(<People />);
  const tr = await row("Ana Person");
  expect(within(tr).getByRole("link", { name: "Ana Person" }).getAttribute("href")).toMatch(/#records\/person\/P-1$/);
  expect(tr).toHaveTextContent("Editor");
  expect(tr).toHaveTextContent("Org one");
  expect(tr).not.toHaveTextContent(firstOrg.id);
  expect(tr).toHaveTextContent("email: ana@example.com");
  expect(within(tr).getByText("4")).toBeInTheDocument();
  const bare = await row("Ben Person");
  expect(within(bare).queryByText("0")).toBeNull();
});

test("the person themselves is first and tagged, and someone who left or is only watched is tagged, with no Active tag on anyone", async () => {
  api([
    person("P-2", "Ben Person", { status: "left" }),
    person("P-1", "Zed Me", { is_pm: true }),
    person("P-3", "Cal Person", { track_only: true }),
    person("P-4", "Dee Person"),
  ]);
  renderApp(<People />);
  await row("Zed Me");
  const names = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.includes("records/person")).map((a) => a.textContent);
  expect(names).toEqual(["Zed Me", "Ben Person", "Cal Person", "Dee Person"]);
  expect(within(await row("Zed Me")).getByText("You")).toBeInTheDocument();
  expect(within(await row("Ben Person")).getByText("Left")).toBeInTheDocument();
  expect(within(await row("Cal Person")).getByText("Only watching")).toBeInTheDocument();
  expect(screen.queryByText("Active")).toBeNull();
});

test("the organization filter narrows the table to people who work for it, or for none", async () => {
  const user = userEvent.setup();
  api([person("P-1", "Ana Person", { org: firstOrg.id, org_name: firstOrg.name }), person("P-2", "Ben Person")]);
  renderApp(<People />);
  await row("Ana Person");
  const filter = screen.getByRole("combobox", { name: "Organization" });
  await user.selectOptions(filter, firstOrg.id);
  expect(screen.queryByRole("link", { name: "Ben Person" })).toBeNull();
  expect(screen.getByRole("link", { name: "Ana Person" })).toBeInTheDocument();
  await user.selectOptions(filter, secondOrg.id);
  expect(await screen.findByText("No one works for that organization on file.")).toBeInTheDocument();
  await user.selectOptions(filter, "No organization");
  expect(screen.getByRole("link", { name: "Ben Person" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Ana Person" })).toBeNull();
});

test("a row opens its detail with what is known, never zero, and a link to the page", async () => {
  const user = userEvent.setup();
  api([person("P-1", "Ana Person", { role: "Editor", org: firstOrg.id, org_name: firstOrg.name, aliases: ["Anita"], open_items: 1, how_to_reach: { phone: "555-0100" } })]);
  renderApp(<People />);
  const tr = await row("Ana Person");
  await user.click(within(tr).getByText("Editor"));
  const detail = await screen.findByRole("dialog", { name: "Ana Person" });
  expect(within(detail).getByText("Editor")).toBeInTheDocument();
  expect(within(detail).getByText("Anita")).toBeInTheDocument();
  expect(within(detail).getByText("phone: 555-0100")).toBeInTheDocument();
  expect(within(detail).getByText("1 open item")).toBeInTheDocument();
  expect(within(detail).queryByText(/Last contact/)).not.toBeInTheDocument();
  expect(within(detail).getByRole("link", { name: "Open Ana Person's page" }).getAttribute("href")).toMatch(/#records\/person\/P-1$/);
});

test("adding a person opens a drawer with the cursor in the name, and the form is not inside any row", async () => {
  const user = userEvent.setup();
  const calls = api([], { "POST people": () => ({ id: "P-9" }), "POST people/P-9/remove": () => ({ ok: "P-9" }) });
  renderApp(<People />);
  await user.click((await screen.findAllByRole("button", { name: "Add a person" }))[0]);
  const dialog = await screen.findByRole("dialog", { name: "Add a person" });
  await waitFor(() => expect(within(dialog).getByRole("textbox", { name: "Full name" })).toHaveFocus());
  expect(within(dialog).getByRole("button", { name: "Add a person" })).toBeDisabled();
  await user.type(within(dialog).getByRole("textbox", { name: "Full name" }), "New Person");
  await user.click(within(dialog).getByRole("button", { name: "Add a person" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST people")?.body).toMatchObject({ full_name: "New Person", first_name: null, role: null, org: null, aliases: [] }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add a person" })).toBeNull());
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-9/remove")).toBe(true));
});

test("the person form chooses the organization by name and sends its id; undo puts the old id back", async () => {
  const user = userEvent.setup();
  const calls = api([person("P-1", "Ana Person", { org: firstOrg.id, org_name: firstOrg.name })], { "POST people/P-1": () => ({ ok: "P-1" }) });
  renderApp(<People />);
  const dialog = await edit(user, "Ana Person");
  const select = within(dialog).getByRole("combobox", { name: /Organization/ });
  await waitFor(() => expect(select).toHaveValue(firstOrg.id));
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "Org one", "Org two", "Add an organization…"]);
  await user.selectOptions(select, secondOrg.id);
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST people/P-1")!.body).toMatchObject({ org: secondOrg.id });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST people/P-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST people/P-1")[1].body).toMatchObject({ org: firstOrg.id });
});

test("adding an organization from the person form posts it, selects it, and sends its id with the person", async () => {
  const user = userEvent.setup();
  let made = false;
  const calls = api([], {
    "GET organizations": () => (made ? [firstOrg, secondOrg, org("ORG-3", "Org three")] : [firstOrg, secondOrg]),
    "POST organizations": () => {
      made = true;
      return { id: "ORG-3" };
    },
    "POST people": () => ({ id: "P-9" }),
  });
  renderApp(<People />);
  await user.click((await screen.findAllByRole("button", { name: "Add a person" }))[0]);
  const dialog = await screen.findByRole("dialog", { name: "Add a person" });
  await user.type(within(dialog).getByLabelText("Full name"), "New Person");
  await user.selectOptions(within(dialog).getByRole("combobox", { name: /Organization/ }), "Add an organization…");
  await user.type(within(dialog).getByRole("textbox", { name: "Name of the new organization" }), "Org three{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST organizations")?.body).toMatchObject({ name: "Org three" }));
  await waitFor(() => expect(within(dialog).getByRole("combobox", { name: /Organization/ })).toHaveValue("ORG-3"));
  await user.click(within(dialog).getByRole("button", { name: "Add a person" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people")).toBe(true));
  expect(calls.find((c) => c.route === "POST people")!.body).toMatchObject({ full_name: "New Person", org: "ORG-3" });
});

test("Escape cancels the new organization field without closing the form", async () => {
  const user = userEvent.setup();
  const calls = api([]);
  renderApp(<People />);
  await user.click((await screen.findAllByRole("button", { name: "Add a person" }))[0]);
  const dialog = await screen.findByRole("dialog", { name: "Add a person" });
  await user.selectOptions(within(dialog).getByRole("combobox", { name: /Organization/ }), "Add an organization…");
  await user.type(within(dialog).getByRole("textbox", { name: "Name of the new organization" }), "Nope{Escape}");
  expect(within(dialog).queryByRole("textbox", { name: "Name of the new organization" })).toBeNull();
  expect(screen.getByRole("dialog", { name: "Add a person" })).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST organizations")).toBe(false);
});

test("marking someone as left and removing them act at once, each with Undo", async () => {
  const user = userEvent.setup();
  const calls = api([person("P-1", "Ana Person")], {
    "POST people/P-1": () => ({ ok: "P-1" }),
    "POST people/P-1/remove": () => ({ ok: "P-1" }),
    "POST people/P-1/restore": () => ({ ok: "P-1" }),
  });
  renderApp(<People />);
  const tr = await row("Ana Person");
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Mark as left" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST people/P-1")?.body).toEqual({ status: "left" }));
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST people/P-1")[1].body).toEqual({ status: "active" }));
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1/remove")).toBe(true));
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1/restore")).toBe(true));
});

test("the person themselves can be edited but not marked as left or removed", async () => {
  const user = userEvent.setup();
  api([person("P-1", "Zed Me", { is_pm: true })]);
  renderApp(<People />);
  const tr = await row("Zed Me");
  await user.click(within(tr).getByRole("button", { name: /More actions for/ }));
  expect(await screen.findByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Remove" })).toBeNull();
  expect(screen.queryByRole("menuitem", { name: "Mark as left" })).toBeNull();
});

// ---- organizations -------------------------------------------------------------------------------------------------

test("the organizations section has one row each with how many people work there", async () => {
  api([]);
  renderApp(<People />);
  const section = await screen.findByRole("region", { name: "Organizations" });
  const rows = (await within(section).findAllByRole("row")).slice(1);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Org one");
  expect(rows[0]).toHaveTextContent("2");
  expect(rows[1]).toHaveTextContent("Org two");
  expect(rows[1]).not.toHaveTextContent(/\d/);
  expect(section).not.toHaveTextContent("ORG-1");
});

test("an organization is added in a drawer and undo removes it", async () => {
  const user = userEvent.setup();
  const calls = api([], { "POST organizations": () => ({ id: "ORG-3" }), "POST organizations/ORG-3/remove": () => ({ ok: "ORG-3" }) });
  renderApp(<People />);
  const section = await screen.findByRole("region", { name: "Organizations" });
  await user.click(within(section).getByRole("button", { name: "Add an organization" }));
  const dialog = await screen.findByRole("dialog", { name: "Add an organization" });
  await waitFor(() => expect(within(dialog).getByLabelText("Organization name")).toHaveFocus());
  await user.type(within(dialog).getByLabelText("Organization name"), "Org three");
  await user.click(within(dialog).getByRole("button", { name: "Add an organization" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST organizations")?.body).toMatchObject({ name: "Org three" }));
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-3/remove")).toBe(true));
});

test("an organization is renamed in a drawer, and undo renames it back", async () => {
  const user = userEvent.setup();
  const calls = api([], { "POST organizations/ORG-2": () => ({ ok: "ORG-2" }) });
  renderApp(<People />);
  const item = (await screen.findByText("Org two")).closest("tr")!;
  await user.click(within(item).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
  const dialog = await screen.findByRole("dialog", { name: "Rename organization" });
  const field = within(dialog).getByRole("textbox", { name: "Organization name" });
  expect(field).toHaveValue("Org two");
  await user.clear(field);
  await user.type(field, "Org second");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2")).toBe(true));
  expect(calls.find((c) => c.route === "POST organizations/ORG-2")!.body).toEqual({ name: "Org second" });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST organizations/ORG-2")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST organizations/ORG-2")[1].body).toEqual({ name: "Org two" });
});

test("an organization people still work for can't be removed, and the menu says why", async () => {
  const user = userEvent.setup();
  const calls = api([]);
  renderApp(<People />);
  const item = (await screen.findByText("Org one")).closest("tr")!;
  await user.click(within(item).getByRole("button", { name: /More actions for/ }));
  const remove = await screen.findByRole("menuitem", { name: "Remove" });
  expect(remove).toHaveAttribute("aria-disabled", "true");
  expect(remove).toHaveTextContent("Change the organization for its remaining contacts before removing it.");
  await user.click(remove);
  expect(calls.some((c) => c.route.endsWith("/remove"))).toBe(false);
});

test("removing an organization acts at once, undo restores it, and a refusal's own words are shown", async () => {
  const user = userEvent.setup();
  let refuse = false;
  const calls = api([], {
    "POST organizations/ORG-2/remove": () => (refuse ? new Refuse(409, "Two people still work for it.") : { ok: "ORG-2" }),
    "POST organizations/ORG-2/restore": () => ({ ok: "ORG-2" }),
  });
  renderApp(<People />);
  const item = (await screen.findByText("Org two")).closest("tr")!;
  await user.click(within(item).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2/remove")).toBe(true));
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2/restore")).toBe(true));
  refuse = true;
  await user.click(within(item).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  expect(await screen.findByText(/Two people still work for it\./)).toBeInTheDocument();
});
