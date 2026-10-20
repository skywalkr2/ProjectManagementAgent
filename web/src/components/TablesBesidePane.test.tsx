// Tables beside the detail pane (design 7.13, 7.14; findings 3.3 and C49): a row opens the pane without a button of its own;
// with the pane beside the table only the priority columns stay, the rest behind the column picker; when even those do
// not fit, the pane overlays the table; no break inside a word; the organizations are a table.
import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { org, person, project, unfiledView } from "../lib/records-fixtures";
import { fakeApi, renderApp } from "../test-utils";
import { People } from "./People";
import { Projects } from "./Projects";
import { useShortcuts } from "../lib/keys";

const firstOrg = org("ORG-1", "Org one", 2);

/** The window is wide: the split is `width` pixels, and the media query for a pane beside the list matches. */
function wide(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: /min-width:\s*1024px/.test(query), media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute("data-split") ? width : 0;
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute("data-detail-pane") ? 420 : 0;
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const projects = () => [
  project("PRJ-1", "Harbor", { status: "At risk", phase: "Build", target: "2026-12-01", owner_name: "Ana Person", group: "Books", open_actions: 3, open_questions: 2, last_change: "2026-10-09T14:00:00Z" }),
  project("PRJ-2", "Dock"),
];

function projectsApi() {
  return fakeApi({
    "GET people": () => [],
    "GET projects": () => projects(),
    "GET notes": () => [],
    "GET unfiled": () => unfiledView(),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET lists": () => [],
  });
}

const rowOf = async (name: string) => (await screen.findByRole("link", { name })).closest("tr")!;
const headers = () => Array.from(document.querySelectorAll("thead th")).map((h) => h.textContent);

test("a project row has no Details button and no filled button; a click on the row opens its detail", async () => {
  const user = userEvent.setup();
  projectsApi();
  renderApp(<Projects />);
  const tr = await rowOf("Harbor");
  expect(within(tr).queryByRole("button", { name: /Details/ })).toBeNull();
  // The only button on the row is its menu.
  expect(within(tr).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["More actions for Harbor"]);
  await user.click(within(tr).getByText("Ana Person"));
  expect(await screen.findByRole("dialog", { name: "Harbor" })).toBeInTheDocument();
});

// The shortcuts the app installs: Enter on a row chooses it.
function WithShortcuts() {
  useShortcuts({ next: "j", previous: "k", primary: "a" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined });
  return <Projects />;
}

test("Enter on a focused row opens the detail", async () => {
  const user = userEvent.setup();
  projectsApi();
  renderApp(<WithShortcuts />);
  const tr = await rowOf("Dock");
  tr.focus();
  await user.keyboard("{Enter}");
  expect(await screen.findByRole("dialog", { name: "Dock" })).toBeInTheDocument();
});

test("the name link opens the pane on a plain click and still points at the page for a new tab", async () => {
  const user = userEvent.setup();
  projectsApi();
  renderApp(<Projects />);
  const link = await screen.findByRole("link", { name: "Harbor" });
  expect(link.getAttribute("href")).toMatch(/#records\/project\/PRJ-1$/);
  // A modified click is the browser's own (a new tab); the pane stays shut.
  const notPrevented = fireEvent.click(link, { ctrlKey: true });
  expect(notPrevented).toBe(true);
  expect(screen.queryByRole("dialog", { name: "Harbor" })).toBeNull();
  await user.click(link);
  expect(await screen.findByRole("dialog", { name: "Harbor" })).toBeInTheDocument();
});

test("beside the pane only the priority columns stay, and the column picker brings the others back", async () => {
  const user = userEvent.setup();
  wide(1200);
  projectsApi();
  renderApp(<Projects />);
  const tr = await rowOf("Harbor");
  // Closed: every column.
  expect(headers()).toEqual(expect.arrayContaining(["Stage", "Last updated", "Group", "Open questions"]));
  await user.click(within(tr).getByText("Ana Person"));
  const pane = await screen.findByRole("complementary", { name: "Harbor" });
  expect(pane).toBeInTheDocument();
  expect(document.querySelector("[data-split]")).toHaveAttribute("data-pane", "beside");
  expect(headers().filter(Boolean)).toEqual(["Project", "Status", "Target", "Owner", "Open to-dos", "Actions"]);
  // The picker lists the others, checked or not, and choosing one shows it.
  await user.click(screen.getByRole("button", { name: "Choose columns" }));
  const stage = await screen.findByRole("menuitemcheckbox", { name: "Stage" });
  expect(stage).toHaveAttribute("aria-checked", "false");
  expect(screen.getByRole("menuitemcheckbox", { name: "Status" })).toHaveAttribute("aria-checked", "true");
  await user.click(stage);
  await waitFor(() => expect(headers()).toContain("Stage"));
});

test("when even the priority columns don't fit beside the pane, the pane overlays the table and every column stays", async () => {
  const user = userEvent.setup();
  wide(900);
  projectsApi();
  renderApp(<Projects />);
  const tr = await rowOf("Harbor");
  await user.click(within(tr).getByText("Ana Person"));
  await screen.findByRole("complementary", { name: "Harbor" });
  expect(document.querySelector("[data-split]")).toHaveAttribute("data-pane", "overlay");
  expect(headers()).toEqual(expect.arrayContaining(["Stage", "Last updated"]));
  // Escape, with the cursor in the pane, closes the overlay.
  within(screen.getByRole("complementary", { name: "Harbor" })).getByRole("link", { name: "Open Harbor's page" }).focus();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("complementary", { name: "Harbor" })).toBeNull());
});

test("a person row has no Details button either, and a long address is clipped with the whole address as its title", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET people": () => [person("P-1", "Ana Person", { role: "Editor", org: firstOrg.id, org_name: firstOrg.name, how_to_reach: { email: "a.long.address.for.someone@example.org" } })],
    "GET organizations": () => [firstOrg],
  });
  renderApp(<People />);
  const tr = await rowOf("Ana Person");
  expect(within(tr).queryByRole("button", { name: /Details/ })).toBeNull();
  expect(within(tr).getByTitle("email: a.long.address.for.someone@example.org")).toBeInTheDocument();
  await user.click(within(tr).getByText("Editor"));
  expect(await screen.findByRole("dialog", { name: "Ana Person" })).toBeInTheDocument();
});

test("the organization filter is sized to its content", async () => {
  fakeApi({ "GET people": () => [person("P-1", "Ana Person")], "GET organizations": () => [firstOrg] });
  renderApp(<People />);
  const filter = (await screen.findByRole("combobox", { name: "Organization" })).closest(".field")!;
  expect(filter).toHaveAttribute("data-size", "content");
  const css = readFileSync(join(__dirname, "People.module.css"), "utf8");
  expect(css).toMatch(/fit-content/);
  expect(css).toMatch(/select\s*\{[^}]*width:\s*auto/);
});

test("the organizations are a table: name, how many people work there, other names, and the row's menu", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET people": () => [person("P-1", "Ana Person")],
    "GET organizations": () => [{ ...firstOrg, aliases: ["Org 1"] }, org("ORG-2", "Org two", 0)],
  });
  renderApp(<People />);
  const table = await screen.findByRole("table", { name: "Organizations" });
  expect(within(table).getAllByRole("columnheader").map((h) => h.textContent).filter(Boolean)).toEqual(["Organization", "People", "Also called", "Actions"]);
  const one = within(table).getByText("Org one").closest("tr")!;
  expect(one).toHaveTextContent("2");
  expect(one).toHaveTextContent("Org 1");
  // A person count of zero is an empty cell, and the menu is the only button on the row.
  const two = within(table).getByText("Org two").closest("tr")!;
  expect(within(two).queryByText("0")).toBeNull();
  expect(within(two).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["More actions for Org two"]);
  await user.click(within(two).getByRole("button", { name: "More actions for Org two" }));
  expect(await screen.findByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
});

test("the table styles never break inside a word: headers on one line, cells wrap only at spaces and end in an ellipsis", () => {
  const css = readFileSync(join(__dirname, "..", "ui", "RecordsTable.module.css"), "utf8");
  expect(css).not.toMatch(/overflow-wrap:\s*anywhere/);
  expect(css).not.toMatch(/word-break:\s*break-all/);
  expect(css).toMatch(/overflow-wrap:\s*normal/);
  expect(css).toMatch(/word-break:\s*normal/);
  expect(css).toMatch(/text-overflow:\s*ellipsis/);
  expect(css).toMatch(/thead th\s*\{[^}]*white-space:\s*nowrap/);
});
