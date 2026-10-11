import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
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
  expect(Array.from(views.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Today", "Stages", "Files", "Sources", "People & projects", "Settings"]);
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
    ["storage.backups.keep", "workspace.plugins.enabled"],
    [
      settingItem("storage.backups.keep", "How many backups stay."),
      settingItem("workspace.plugins.enabled", "Which add-ons are on", { type: "list", value: [], default: [] }),
    ],
  );
  const line = await screen.findByText("Restart to use: Backups to keep in each folder, Which add-ons are on.");
  expect(line).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("storage.backups.keep");
  expect(document.body).not.toHaveTextContent("workspace.plugins");
});

test("an update to the app is named as one, and only three things are listed before 'and N more'", async () => {
  waiting(
    ["code", "storage.backups.keep", "storage.backups.every_hours", "storage.sync.folder", "ui.toast_seconds"],
    [
      settingItem("storage.backups.keep", "A"),
      settingItem("storage.backups.every_hours", "B"),
      settingItem("storage.sync.folder", "C"),
      settingItem("ui.toast_seconds", "D"),
    ],
  );
  expect(
    await screen.findByText("Restart to use: an update to the app, Backups to keep in each folder, Hours between backups and 2 more."),
  ).toBeInTheDocument();
  expect(document.querySelector(".restart-slot")).toBeInTheDocument();
});

test("a key with no known label is named by its group, or as other settings", async () => {
  waiting(["storage.backups.unknown_thing", "mystery.thing"], []);
  expect(await screen.findByText("Restart to use: Backups, other settings.")).toBeInTheDocument();
});
