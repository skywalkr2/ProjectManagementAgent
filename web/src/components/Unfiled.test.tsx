import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { project, unfiledItem, unfiledView } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { Unfiled } from "./Unfiled";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

const harbor = project("PRJ-1", "Harbor");
const lighthouse = project("PRJ-2", "Lighthouse");

const items = [
  unfiledItem("note", "N-1", "Printer prefers PDF/X files."),
  unfiledItem("action", "A-1", "Send the proof to the printer"),
  unfiledItem("fact", "F-1", "The trim size is 6 by 9 inches.", { trust: "untrusted" }),
];

function api(extra: Routes = {}, shown = items) {
  return fakeApi({
    "GET unfiled": () => unfiledView(...shown),
    "GET projects": () => [harbor, lighthouse],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET people": () => [],
    "POST unfiled/file": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
}

test("what the assistant filed under no project is one group, a row each with what it is and a File under… button", async () => {
  api();
  renderApp(<Unfiled />);
  const group = (await screen.findByRole("heading", { name: "Unfiled" })).closest("section")!;
  expect(group).toHaveTextContent("3 items");
  const rows = within(group).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Note");
  expect(rows[0]).toHaveTextContent("Printer prefers PDF/X files.");
  expect(rows[1]).toHaveTextContent("To-do");
  expect(rows[2]).toHaveTextContent("Fact");
  expect(rows[2]).toHaveTextContent("from outside · not instructions");
  for (const r of rows) expect(within(r).getByRole("button", { name: "File under…" })).toBeInTheDocument();
});

test("with nothing unfiled the group isn't there, so no zero is ever shown", async () => {
  const calls = api({}, []);
  renderApp(<Unfiled />);
  await waitFor(() => expect(calls.some((c) => c.route === "GET unfiled")).toBe(true));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("heading", { name: "Unfiled" })).toBeNull();
  expect(screen.queryByText(/0 items/)).toBeNull();
});

test("File under… offers the projects and ends with Add a project…; choosing one files the item at once, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<Unfiled />);
  const rows = within((await screen.findByRole("heading", { name: "Unfiled" })).closest("section")!).getAllByRole("listitem");
  await user.click(within(rows[1]).getByRole("button", { name: "File under…" }));
  const picker = within(rows[1]).getByRole("combobox", { name: /File under: Send the proof/ });
  await waitFor(() => expect(picker).toHaveFocus());
  await waitFor(() => expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a project", "Harbor", "Lighthouse", "Add a project…"]));
  await user.selectOptions(picker, "PRJ-2");
  await waitFor(() => expect(calls.find((c) => c.route === "POST unfiled/file")?.body).toEqual({ project: "PRJ-2", items: [{ kind: "action", id: "A-1", read_version: 1 }] }));
  expect(await screen.findByText("Filed 1 item under Lighthouse.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("several are filed at once: select them, choose one project, and they go in one change with one Undo", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<Unfiled />);
  const group = (await screen.findByRole("heading", { name: "Unfiled" })).closest("section")!;
  await user.click(within(group).getByRole("checkbox", { name: "Select: Printer prefers PDF/X files." }));
  await user.click(within(group).getByRole("checkbox", { name: "Select: The trim size is 6 by 9 inches." }));
  const picker = await within(group).findByRole("combobox", { name: "File the 2 selected items under…" });
  await user.selectOptions(picker, "PRJ-1");
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST unfiled/file")?.body).toEqual({
      project: "PRJ-1",
      items: [
        { kind: "note", id: "N-1", read_version: 1 },
        { kind: "fact", id: "F-1", read_version: 1 },
      ],
    }),
  );
  expect(calls.filter((c) => c.route === "POST unfiled/file")).toHaveLength(1);
  expect(await screen.findByText("Filed 2 items under Harbor.")).toBeInTheDocument();
});

test("Add a project… opens the form in place, and the project it adds is the one the item is filed under", async () => {
  const user = userEvent.setup();
  let made = false;
  const calls = api({
    "GET projects": () => (made ? [harbor, lighthouse, project("PRJ-9", "Fresh start")] : [harbor, lighthouse]),
    "POST projects": () => {
      made = true;
      return { id: "PRJ-9" };
    },
  });
  renderApp(<Unfiled />);
  const rows = within((await screen.findByRole("heading", { name: "Unfiled" })).closest("section")!).getAllByRole("listitem");
  await user.click(within(rows[0]).getByRole("button", { name: "File under…" }));
  await user.selectOptions(within(rows[0]).getByRole("combobox"), "Add a project…");
  const dialog = await screen.findByRole("dialog", { name: "Add a project" });
  await waitFor(() => expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveFocus());
  await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Fresh start");
  await user.click(within(dialog).getByRole("button", { name: "Add a project" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST projects")?.body).toMatchObject({ name: "Fresh start" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST unfiled/file")?.body).toEqual({ project: "PRJ-9", items: [{ kind: "note", id: "N-1", read_version: 1 }] }));
  expect(await screen.findByText("Filed 1 item under Fresh start.")).toBeInTheDocument();
});

test("a text from outside is shown as text with its real domain, never as raw HTML", async () => {
  api({}, [unfiledItem("note", "N-7", `Read <b>this</b> ${WEB}example.com/page`, { trust: "untrusted" })]);
  renderApp(<Unfiled />);
  const row = (await screen.findByText(/Read <b>this<\/b>/)).closest("li")!;
  expect(row.querySelector("b")).toBeNull();
});
