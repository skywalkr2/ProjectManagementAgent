import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider, useRestart } from "../lib/restart";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { Header } from "./Header";

function status(spend: Partial<S["SpendStatus"]> = {}, over: Partial<S["Status"]> = {}): S["Status"] {
  return {
    backup: { configured: false, last_success: null, age_hours: null, needs_attention: false, last_error: null },
    ai: { state: "ok", detail: null },
    spend: {
      today_usd: 0,
      month_usd: 0,
      per_day_usd: 2,
      per_month_usd: 30,
      warn: false,
      warn_today: false,
      warn_month: false,
      ...spend,
    },
    requests: { queued: 0, running: 0, review: 0, needs_you: 0 },
    version: 1,
    restart_needed: null,
    can_restart: false,
    ...over,
  };
}

function show(spend: Partial<S["SpendStatus"]>) {
  fakeApi({ "GET status": () => status(spend) });
  return renderApp(
    <Header
      workspace="Workspace"
      live={{ state: "live", lastUpdate: null }}
      view="home"
      onView={() => {}}
      onHandIn={() => {}}
      onAsk={() => {}}
      onHelp={() => {}}
    />,
  );
}

test("the spend line shows today's and this month's cost", async () => {
  show({ today_usd: 0.12, month_usd: 1.4 });
  expect(await screen.findByText("AI today $0.12 · this month $1.40")).toBeInTheDocument();
  expect(screen.queryByText(/limit/)).toBeNull();
});

test("the spend line is hidden until a run has cost something", async () => {
  show({});
  await screen.findByText("No off-device backup");
  expect(screen.queryByText(/AI today/)).toBeNull();
});

test("near a limit, the line says which one in words", async () => {
  const { unmount } = show({ today_usd: 1.7, month_usd: 5, warn: true, warn_today: true });
  expect(await screen.findByText("AI today $1.70 · this month $5.00 · near today's limit")).toBeInTheDocument();
  unmount();
  show({ today_usd: 0.1, month_usd: 25, warn: true, warn_month: true });
  expect(await screen.findByText(/near this month's limit$/)).toBeInTheDocument();
});

test("Files is one of the views beside Today, Stages and People & projects", async () => {
  const onView = vi.fn();
  fakeApi({ "GET status": () => status() });
  renderApp(
    <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="files" onView={onView} onHandIn={() => {}} onAsk={() => {}} onHelp={() => {}} />,
  );
  const views = screen.getByRole("navigation", { name: "Views" });
  expect(Array.from(views.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Today", "Stages", "Files", "Sources", "People & projects", "Settings", "Add-ons"]);
  expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute("aria-current", "page");
  screen.getByRole("button", { name: "Stages" }).click();
  expect(onView).toHaveBeenCalledWith("stages");
  screen.getByRole("button", { name: "Sources" }).click();
  expect(onView).toHaveBeenCalledWith("sources");
  await screen.findByText("No off-device backup");
});

test("the Ask button opens the Ask box", async () => {
  const user = userEvent.setup();
  const onAsk = vi.fn();
  fakeApi({ "GET status": () => status() });
  renderApp(
    <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="home" onView={() => {}} onHandIn={() => {}} onAsk={onAsk} onHelp={() => {}} />,
  );
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(onAsk).toHaveBeenCalledTimes(1);
  await screen.findByText("No off-device backup");
});

test("panels on the work tab are views of their own; other tabs' panels are not", async () => {
  const user = userEvent.setup();
  const onView = vi.fn();
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
  fakeApi({
    "GET status": () => status(),
    "GET panels": () => [panel("demo/goals", "work", "Goals"), panel("demo/admin", "admin", "Admin things")],
  });
  renderApp(
    <Header
      workspace="Workspace"
      live={{ state: "live", lastUpdate: null }}
      view="panel:demo/goals"
      onView={onView}
      onHandIn={() => {}}
      onAsk={() => {}}
      onHelp={() => {}}
    />,
  );
  const goals = await screen.findByRole("button", { name: "Goals" });
  expect(goals).toHaveAttribute("aria-current", "page");
  expect(screen.queryByRole("button", { name: "Admin things" })).toBeNull();
  expect(within(screen.getByRole("navigation", { name: "Views" })).getAllByRole("button").map((b) => b.textContent)).toEqual([
    "Today",
    "Stages",
    "Files",
    "Sources",
    "Goals",
    "People & projects",
    "Settings",
    "Add-ons",
  ]);
  await user.click(screen.getByRole("button", { name: "Settings" }));
  expect(onView).toHaveBeenCalledWith("settings");
  await user.click(screen.getByRole("button", { name: "Today" }));
  expect(onView).toHaveBeenCalledWith("home");
  await user.click(goals);
  expect(onView).toHaveBeenLastCalledWith("panel:demo/goals");
});

const NEEDED = "A change needs the app to restart. New AI work waits until then.";

function showRestart(over: Partial<S["Status"]>, routes: Record<string, (body: unknown) => unknown> = {}) {
  const calls = fakeApi({ "GET status": () => status({}, over), "GET runtime-config": () => ({ instance: null }), ...routes });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="home" onView={() => {}} onHandIn={() => {}} onAsk={() => {}} onHelp={() => {}} />
    </RestartProvider>,
  );
  return calls;
}

test("the restart-needed line has Restart now when this copy can restart itself, and it asks the app", async () => {
  const user = userEvent.setup();
  const calls = showRestart({ restart_needed: "A setting changed.", can_restart: true }, { "POST restart": () => ({ restarting: true }) });
  expect(await screen.findByText(NEEDED, { exact: false })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("Restarting to use the new settings…"));
});

test("when this copy can't restart itself, the line says to close and start the app again, with no button", async () => {
  showRestart({ restart_needed: "A setting changed.", can_restart: false });
  expect(await screen.findByText(/Close the app and start it again/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restart now" })).toBeNull();
});

test("a refusal from the header's Restart now is shown in the notice", async () => {
  const user = userEvent.setup();
  showRestart({ restart_needed: "A setting changed.", can_restart: true }, { "POST restart": () => new Refuse(409, "Close it and start it again.") });
  await user.click(await screen.findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("Close it and start it again."));
});

test("nothing about restarting shows when no restart is needed", async () => {
  showRestart({ restart_needed: null, can_restart: true });
  await screen.findByText("No off-device backup");
  expect(screen.queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(screen.queryByText(/restart/i)).toBeNull();
});

const settingItem = (key: string, description: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] => ({
  key,
  file: key.split(".")[0],
  group: key.split(".").slice(0, 2).join("."),
  description,
  type: "integer",
  options: [],
  value: 1,
  default: 1,
  source: "default",
  locked: false,
  basic: true,
  editable: true,
  ...extra,
});

function waiting(keys: string[], items: S["SettingItem"][]) {
  showRestart(
    { restart_needed: "A setting changed.", can_restart: true, restart_for: keys },
    { "GET settings": () => ({ fingerprint: "fp", items }) },
  );
}

test("the restart line names what waits by the labels Settings shows, never the keys", async () => {
  waiting(
    ["ui.toast_seconds", "workspace.plugins.enabled"],
    [
      settingItem("ui.toast_seconds", "How long a message stays."),
      settingItem("workspace.plugins.enabled", "Which add-ons are on", { type: "list", value: [], default: [] }),
    ],
  );
  const line = await screen.findByText("Restart to use: Seconds a message stays on screen, Which add-ons are on.");
  expect(line).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("ui.toast_seconds");
  expect(document.body).not.toHaveTextContent("workspace.plugins");
});

test("a setting with no short label is named by the first sentence of its description, ending in exactly one period", async () => {
  waiting(
    ["demo.long", "demo.dotted", "demo.bare"],
    [
      settingItem("demo.long", "Where the copies go. Use at least one folder outside the workspace so a lost computer loses nothing."),
      settingItem("demo.dotted", "Which things to keep.."),
      settingItem("demo.bare", ""),
    ],
  );
  const line = await screen.findByText("Restart to use: Where the copies go, Which things to keep, demo.bare.");
  expect(line).toBeInTheDocument();
  expect(line.textContent).not.toMatch(/\.\./);
});

test("an update to the app is named as one, and only three things are listed before 'and N more'", async () => {
  waiting(
    ["code", "ui.toast_seconds", "ai.budgets.per_day_usd", "workspace.language", "workspace.name"],
    [
      settingItem("ui.toast_seconds", "A"),
      settingItem("ai.budgets.per_day_usd", "B"),
      settingItem("workspace.language", "C"),
      settingItem("workspace.name", "D"),
    ],
  );
  expect(
    await screen.findByText(
      "Restart to use: an update to the app, Seconds a message stays on screen, Most to spend in a day (USD) and 2 more.",
    ),
  ).toBeInTheDocument();
  expect(document.querySelector(".restart-slot")).toBeInTheDocument();
});

test("a key with no known label is named by its group, or as other settings", async () => {
  waiting(["ai.budgets.unknown_thing", "mystery.thing"], []);
  expect(await screen.findByText("Restart to use: AI spending, other settings.")).toBeInTheDocument();
});

function Asker() {
  const restart = useRestart();
  return (
    <button type="button" onClick={restart.offer}>
      Ask about restarting
    </button>
  );
}

test("the restart need is said once: the header's line hides while the page asks, and returns as the reminder after Later", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET status": () => status({}, { restart_needed: "A setting changed.", can_restart: true, restart_for: ["code"] }),
    "GET runtime-config": () => ({ instance: null }),
  });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <Asker />
      <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="home" onView={() => {}} onHandIn={() => {}} onAsk={() => {}} onHelp={() => {}} />
    </RestartProvider>,
  );
  const header = screen.getByRole("banner");
  // Before the page asks, the header's line is the one notice.
  expect(await within(header).findByText(NEEDED, { exact: false })).toBeInTheDocument();
  expect(document.querySelector(".restart-slot")).toBeEmptyDOMElement();
  await user.click(screen.getByRole("button", { name: "Ask about restarting" }));
  expect(document.querySelector(".restart-slot")).toHaveTextContent("This change needs the app to restart.");
  expect(within(header).queryByText(NEEDED, { exact: false })).toBeNull();
  expect(within(header).queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(screen.getAllByRole("button", { name: "Restart now" })).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Later" }));
  expect(await within(header).findByText(NEEDED, { exact: false })).toBeInTheDocument();
  expect(within(header).getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  expect(document.querySelector(".restart-slot")).toBeEmptyDOMElement();
});

test("the main row holds the name, the views and the buttons; the status row sits under it", async () => {
  fakeApi({ "GET status": () => status({}, { restart_needed: "A setting changed.", can_restart: true }), "GET runtime-config": () => ({ instance: null }) });
  renderApp(
    <RestartProvider hellos={1}>
      <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="home" onView={() => {}} onHandIn={() => {}} onAsk={() => {}} onHelp={() => {}} />
    </RestartProvider>,
  );
  const header = screen.getByRole("banner");
  await within(header).findByText("No off-device backup");
  const main = header.querySelector(".top-main") as HTMLElement;
  const statusRow = header.querySelector(".top-meta") as HTMLElement;
  expect(main).not.toBeNull();
  expect(statusRow).not.toBeNull();
  // Name, views and the three buttons share the main row, in that order.
  expect(within(main).getByText("Workspace")).toBeInTheDocument();
  expect(within(main).getByRole("navigation", { name: "Views" })).toBeInTheDocument();
  const buttons = ["Hand something in", "Ask", "Keyboard shortcuts"].map((name) => within(main).queryByRole("button", { name }));
  expect(buttons.every(Boolean)).toBe(true);
  const order = (a: Node, b: Node) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  expect(order(main.querySelector(".brand")!, main.querySelector("nav")!)).toBe(true);
  expect(order(main.querySelector("nav")!, main.querySelector(".top-acts")!)).toBe(true);
  // The main row has none of the status; the status row has none of the buttons or views.
  expect(within(main).queryByText("No off-device backup")).toBeNull();
  expect(within(main).queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(order(main, statusRow)).toBe(true);
  expect(within(statusRow).getByText("No off-device backup")).toBeInTheDocument();
  expect(within(statusRow).getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  expect(within(statusRow).queryByRole("navigation")).toBeNull();
  expect(within(statusRow).queryByRole("button", { name: "Hand something in" })).toBeNull();
});

test("Add-ons is a view of its own, next to Settings", async () => {
  const user = userEvent.setup();
  const onView = vi.fn();
  fakeApi({ "GET status": () => status() });
  renderApp(<Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="addons" onView={onView} onHandIn={() => {}} onAsk={() => {}} onHelp={() => {}} />);
  const addons = screen.getByRole("button", { name: "Add-ons" });
  expect(addons).toHaveAttribute("aria-current", "page");
  expect(addons.previousElementSibling).toHaveTextContent("Settings");
  await user.click(addons);
  expect(onView).toHaveBeenCalledWith("addons");
  await screen.findByText("No off-device backup");
});
