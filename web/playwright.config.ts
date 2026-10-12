// Browser tests: the acceptance scenario at the root path and under a nested base path, with accessibility checks.
// Build the UI first (npm run build); each project starts its own server from the repository root.
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const servers = [
  { name: "root", port: 8781, base: "/" },
  { name: "nested", port: 8782, base: "/admin" },
];

// The journeys start the app as a person does (a new workspace, then the serve command) beside a process that plays the
// outside services; both work in one state folder that the start-up script clears.
const journeys = { port: 8783, fakePort: 8790, state: join(tmpdir(), "cockpit-journeys") };

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    launchOptions: { executablePath },
    permissions: ["clipboard-read", "clipboard-write"],
    // No entry animations, so accessibility checks never catch a toast half faded in.
    contextOptions: { reducedMotion: "reduce" },
  },
  projects: [
    ...servers.map((s) => ({
      name: s.name,
      testMatch: /(acceptance|shell)\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${s.port}${s.base === "/" ? "/" : `${s.base}/`}` },
    })),
    {
      name: "journeys",
      testMatch: /journeys\.spec\.ts/,
      use: { baseURL: `http://127.0.0.1:${journeys.port}/` },
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
      command: `uv run python -m tests.e2e_fresh_server --port ${journeys.port} --state "${journeys.state}"`,
      cwd: "..",
      url: `http://127.0.0.1:${journeys.port}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `uv run python -m tests.fake_services --port ${journeys.fakePort} --state "${journeys.state}"`,
      cwd: "..",
      url: `http://127.0.0.1:${journeys.fakePort}/__e2e/info`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
