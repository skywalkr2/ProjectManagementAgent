// Browser tests: the acceptance scenario at the root path and under a nested base path, with accessibility checks, and
// the layout check (no screen wider than the window).
// Build the UI first (npm run build); each project starts its own server from the repository root.
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

// PW_PORT_OFFSET moves every port the tests use by that much, so two runs (two checkouts) can share a computer.
const offset = Number(process.env.PW_PORT_OFFSET) || 0;
const servers = [
  { name: "root", port: 8781 + offset, base: "/" },
  { name: "nested", port: 8782 + offset, base: "/admin" },
];
// The layout check has a server of its own, because it holds long made-up text that the other scenarios must not see.
const layout = { port: 8786 + offset };
// So does the check of the yes to an AI account reading work mail and notes: its server has a second stand-in account whose
// person said Not now, which the other scenarios must not see on Today.
const access = { port: 8787 + offset };
// And Today's capacity, measured on a fresh demo that no other scenario has added lines to.
const capacity = { port: 8788 + offset };
// And the late-evening check: its server's clock starts just after midnight UTC, the evening before in the demo's time zone
// (which is behind UTC), so a day written or counted in the wrong zone shows as a wait below zero.
const late = { port: 8789 + offset, clockAt: "2026-10-21T00:30:00Z" };

// The journeys start the app as a person does (a new workspace, then the serve command) beside a process that plays the
// outside services; each pair works in one state folder that the start-up script clears. Two pairs: one for the
// journeys that share a workspace (a new workspace, a folder, an add-on installed from the list), and one for the
// mail journey, whose workspace has the mail add-on on and has not yet pressed Go, and one for the new-start journey,
// whose workspace has nothing and whose catalog offers the mail add-on. The services answer over HTTPS
// as well, with a certificate from a throwaway authority that the app trusts through its environment.
const pair = (port: number, fakePort: number, httpsPort: number) => ({
  port: port + offset,
  fakePort: fakePort + offset,
  httpsPort: httpsPort + offset,
  state: join(tmpdir(), `cockpit-journeys-${port + offset}`),
});
const journeys = pair(8783, 8790, 8791);
const mail = pair(8784, 8792, 8793);
const newStart = pair(8785, 8794, 8795);

// The browser tests ask the fake services for what they were asked; they read where from here.
process.env.JOURNEY_FAKE_PORT = String(journeys.fakePort);
process.env.JOURNEY_MAIL_FAKE_PORT = String(mail.fakePort);
process.env.JOURNEY_NEW_START_FAKE_PORT = String(newStart.fakePort);

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

const freshServer = (p: ReturnType<typeof pair>, flags: string) => ({
  command: `uv run python -m tests.e2e_fresh_server --port ${p.port} --state "${p.state}" --https-port ${p.httpsPort} ${flags}`,
  cwd: "..",
  url: `http://127.0.0.1:${p.port}/api/health`,
  reuseExistingServer: false,
  timeout: 60_000,
});

// Started after the app, which clears the state folder first.
const fakeServices = (p: ReturnType<typeof pair>, flags = "") => ({
  command: `uv run python -m tests.fake_services --port ${p.fakePort} --https-port ${p.httpsPort} --state "${p.state}" ${flags}`,
  cwd: "..",
  url: `http://127.0.0.1:${p.fakePort}/__e2e/info`,
  reuseExistingServer: false,
  timeout: 60_000,
});

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  // One lane per server: each project has its own server and workspace, so projects run side by side, while the tests
  // inside a project (and the two that share a server, below) run in order. PW_WORKERS lowers it on a small machine.
  fullyParallel: false,
  workers: Number(process.env.PW_WORKERS) || 5,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    launchOptions: { executablePath },
    permissions: ["clipboard-read", "clipboard-write"],
    // No entry animations, so accessibility checks never catch a toast half faded in.
    contextOptions: { reducedMotion: "reduce" },
  },
  projects: [
    // The acceptance scenario and the shell checks share a server, so the shell checks wait for the scenario to finish.
    ...servers.flatMap((s) => {
      const use = { baseURL: `http://127.0.0.1:${s.port}${s.base === "/" ? "/" : `${s.base}/`}` };
      return [
        { name: s.name, testMatch: /acceptance\.spec\.ts/, use },
        { name: `${s.name}-shell`, testMatch: /shell\.spec\.ts/, use, dependencies: [s.name] },
        // The panes the shell opens (drawer, Ask pane, the stages board, review mode), and every main screen's accessibility
        // checks in light and dark at four widths (once, at the root; the nested path changes no screen).
        { name: `${s.name}-panes`, testMatch: /panes\.spec\.ts/, use, dependencies: [s.name] },
        ...(s.base === "/" ? [{ name: `${s.name}-a11y`, testMatch: /a11y\.spec\.ts/, use, dependencies: [s.name] }] : []),
        // The tables beside the detail pane at 1440px (once, at the root).
        ...(s.base === "/" ? [{ name: `${s.name}-tables`, testMatch: /tables\.spec\.ts/, use, dependencies: [s.name] }] : []),
      ];
    }),
    { name: "layout", testMatch: /layout\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${layout.port}/` } },
    { name: "access", testMatch: /work-access\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${access.port}/` } },
    { name: "capacity", testMatch: /today-capacity\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${capacity.port}/` } },
    { name: "late", testMatch: /late-evening\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${late.port}/` } },
    {
      name: "journeys",
      testMatch: /journeys\.spec\.ts/,
      // The made-up services' sign-in page is served with the throwaway authority's certificate, which this browser
      // doesn't know; the app itself is told to trust it (see the start-up script), and the real one is never touched.
      use: { baseURL: `http://127.0.0.1:${journeys.port}/`, ignoreHTTPSErrors: true },
    },
    {
      name: "journeys-mail",
      testMatch: /journeys-mail\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${mail.port}/`, ignoreHTTPSErrors: true },
    },
    {
      name: "journeys-new-start",
      testMatch: /journeys-new-start\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${newStart.port}/`, ignoreHTTPSErrors: true },
    },
  ],
  webServer: [
    ...servers.map((s) => ({
      command: `uv run python -m tests.e2e_server --port ${s.port} --base-path ${s.base}`,
      cwd: "..",
      url: `http://127.0.0.1:${s.port}${s.base === "/" ? "" : s.base}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    })),
    {
      command: `uv run python -m tests.e2e_server --port ${layout.port} --base-path / --layout-stress`,
      cwd: "..",
      url: `http://127.0.0.1:${layout.port}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `uv run python -m tests.e2e_server --port ${access.port} --base-path / --standin-account`,
      cwd: "..",
      url: `http://127.0.0.1:${access.port}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `uv run python -m tests.e2e_server --port ${capacity.port} --base-path /`,
      cwd: "..",
      url: `http://127.0.0.1:${capacity.port}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `uv run python -m tests.e2e_server --port ${late.port} --base-path / --clock-at ${late.clockAt}`,
      cwd: "..",
      url: `http://127.0.0.1:${late.port}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    freshServer(journeys, "--add-ons"),
    fakeServices(journeys),
    freshServer(mail, "--mail"),
    fakeServices(mail),
    // The new-start journey changes nothing by hand: the catalog is named through the environment, and what the app
    // prints is kept so the restarts can be counted.
    freshServer(newStart, "--add-ons --catalog-by-environment --log"),
    fakeServices(newStart, "--catalog journey_mail"),
  ],
});
