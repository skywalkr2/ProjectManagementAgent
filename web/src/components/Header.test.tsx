import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Header } from "./Header";

function status(spend: Partial<S["SpendStatus"]> = {}): S["Status"] {
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
    <Header workspace="Workspace" live={{ state: "live", lastUpdate: null }} view="files" onView={onView} onHandIn={() => {}} onHelp={() => {}} />,
  );
  const views = screen.getByRole("navigation", { name: "Views" });
  expect(Array.from(views.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Today", "Stages", "Files", "People & projects"]);
  expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute("aria-current", "page");
  screen.getByRole("button", { name: "Stages" }).click();
  expect(onView).toHaveBeenCalledWith("stages");
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
    "Goals",
    "People & projects",
  ]);
  await user.click(screen.getByRole("button", { name: "Today" }));
  expect(onView).toHaveBeenCalledWith("home");
  await user.click(goals);
  expect(onView).toHaveBeenLastCalledWith("panel:demo/goals");
});
