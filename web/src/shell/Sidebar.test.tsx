import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Sidebar } from "./Sidebar";

const panel = (name: string, tab: string, title: string): S["PanelView"] => ({
  name,
  title,
  tab,
  kind: "demo/goal",
  view: "table",
  columns: ["title"],
  primary_action: null,
  row_actions: [],
});

const change = (id: string, state: string) => ({ id, state, changeset: null }) as unknown as S["ChangeItem"];

const line = (key: string): S["QueueLineView"] => ({ key, group: "review", kind: "review", count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {} });
const plugin = { plugin: "demo", id: "L-1", text: "Look at this", about: null, action: null, action_is: null, why: "", until: null };

function show(opts: { current?: Parameters<typeof Sidebar>[0]["current"]; expanded?: boolean; panels?: S["PanelView"][]; onToggle?: () => void } = {}) {
  fakeApi({
    "GET panels": () => opts.panels ?? [],
    "GET changes": () => [change("a", "review"), change("b", "needs_you"), change("c", "done")],
    "GET followups": () => [{ person: "p", name: "Sam", is_pm: false, message: "", questions: [], actions: [], to_send: 3 }],
    "GET today/queue": () => [line("a"), line("b"), line("c")],
    "GET plugin-today": () => [plugin],
    "GET stages/requests": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
  });
  renderApp(<Sidebar current={opts.current ?? "today"} expanded={opts.expanded ?? true} onToggle={opts.onToggle ?? (() => undefined)} />);
}

const nav = () => screen.getByRole("navigation", { name: "Views" });

test("the views are links, in the fixed groups, with plugin panels only under Work or Records", async () => {
  show({
    panels: [panel("demo/goals", "work", "Goals"), panel("demo/contacts", "people", "Contacts"), panel("demo/admin", "settings", "Admin things"), panel("demo/board", "today", "Board")],
  });
  // Wait for the panels to arrive by their text, which is cheap to poll; then read every link once, because looking each
  // one up by role and name walks the whole tree again and is what made this test slow under load.
  await screen.findByText("Goals");
  const links = within(nav())
    .getAllByRole("link")
    .map((a) => ({ label: a.querySelector('[class*="label"]')?.textContent, href: a.getAttribute("href") }));
  expect(links.map((l) => l.label)).toEqual([
    "Today",
    "What changed",
    "Follow-ups",
    "Waiting to go out",
    "Stages",
    "Goals",
    "Projects",
    "People",
    "Files",
    "Knowledge",
    "Contacts",
    "Sources",
    "Add-ons",
    "Settings",
  ]);
  const href = (label: string) => links.find((l) => l.label === label)?.href;
  for (const link of links) expect(link.href).toContain("#");
  expect(href("Stages")).toMatch(/#work\/stages$/);
  expect(href("Goals")).toMatch(/#work\/panel\/demo%2Fgoals$/);
  expect(href("Contacts")).toMatch(/#records\/panel\/demo%2Fcontacts$/);
});

test("the current view is marked, and it is the only one", async () => {
  show({ current: "work/followups" });
  const current = await screen.findAllByRole("link", { current: "page" });
  expect(current).toHaveLength(1);
  expect(current[0]).toHaveTextContent("Follow-ups");
});

test("a plugin panel is the current view when its address is", async () => {
  show({ current: "work/panel/demo%2Fgoals", panels: [panel("demo/goals", "work", "Goals")] });
  expect(await screen.findByRole("link", { name: "Goals", current: "page" })).toBeInTheDocument();
});

test("counts show where they help and an empty count shows nothing", async () => {
  show();
  const changed = await screen.findByRole("link", { name: /^What changed/ });
  await within(changed).findByText("2");
  expect(screen.getByRole("link", { name: /^Follow-ups/ })).toHaveTextContent("3");
  // Today counts its own lines (the queue's and the add-ons'), the same number its heading gives; the views with no count
  // have none.
  await within(screen.getByRole("link", { name: /^Today/ })).findByText("4");
  expect(screen.getByRole("link", { name: "Stages" })).toHaveTextContent(/^Stages$/);
});

test("with the sidebar collapsed to a rail, each icon still has its name, and the toggle pins it open", async () => {
  const user = userEvent.setup();
  const onToggle = vi.fn();
  show({ expanded: false, onToggle });
  const stages = await screen.findByRole("link", { name: "Stages" });
  while (document.activeElement !== stages) await user.tab();
  expect(await screen.findByRole("tooltip")).toHaveTextContent("Stages");
  await user.click(screen.getByRole("button", { name: "Pin the sidebar open" }));
  expect(onToggle).toHaveBeenCalledTimes(1);
});

test("the toggle collapses a sidebar that shows labels", async () => {
  show({ expanded: true });
  expect(await screen.findByRole("button", { name: "Collapse the sidebar" })).toBeInTheDocument();
});
