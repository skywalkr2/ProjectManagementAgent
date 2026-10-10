import { screen } from "@testing-library/react";
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
