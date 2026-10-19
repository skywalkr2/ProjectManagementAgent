import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { fakeApi, renderApp } from "../test-utils";
import { JobsPanel } from "./JobsPanel";

async function section(name: string) {
  return (await screen.findByRole("region", { name })) as HTMLElement;
}

test("scheduled work is one row per job with how often, on or off in words, and the last run", async () => {
  fakeApi({
    "GET jobs": () => [
      { name: "demo/refresh-feeds", plugin: "demo", enabled: true, every_minutes: 60, last_run_at: "2026-10-09T14:00:00Z", last_outcome: "ok", last_error: null },
      { name: "demo/sweep_old-items", plugin: "demo", enabled: false, every_minutes: 1, last_run_at: "2026-10-09T15:30:00Z", last_outcome: "failed", last_error: "The source didn't answer." },
      { name: "demo/never-ran", plugin: "demo", enabled: true, every_minutes: 15, last_run_at: null, last_outcome: null, last_error: null },
    ],
  });
  renderApp(<JobsPanel />);
  const jobs = await section("Scheduled work");
  const rows = within(jobs).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Refresh feeds");
  expect(rows[0]).toHaveTextContent("On");
  expect(rows[0]).toHaveTextContent("every 60 minutes");
  expect(rows[0]).toHaveTextContent(/Last ran .*: it worked/);
  expect(rows[1]).toHaveTextContent("Sweep old items");
  expect(rows[1]).toHaveTextContent("Off");
  expect(rows[1]).toHaveTextContent("every minute");
  expect(rows[1]).toHaveTextContent(/it failed/);
  expect(rows[1]).toHaveTextContent("The source didn't answer.");
  expect(rows[2]).toHaveTextContent("Hasn't run yet");
  expect(within(jobs).queryByRole("button")).toBeNull();
});

test("the scheduled work section is hidden when there are no jobs", async () => {
  const calls = fakeApi({ "GET jobs": () => [] });
  renderApp(<JobsPanel />);
  await waitFor(() => expect(calls.some((c) => c.route === "GET jobs")).toBe(true));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("region", { name: "Scheduled work" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "Scheduled work" })).toBeNull();
});

