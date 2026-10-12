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
// outside services; each pair works in one state folder that the start-up script clears. Two pairs: one for the
// journeys that share a workspace (a new workspace, a folder, an add-on installed from the list), and one for the
// mail journey, whose workspace has the mail add-on on and has not yet pressed Go, and one for the new-start journey,
// whose workspace has nothing and whose catalog offers the mail add-on. The services answer over HTTPS
// as well, with a certificate from a throwaway authority that the app trusts through its environment.
const pair = (port: number, fakePort: number, httpsPort: number) => ({
  port,
  fakePort,
  httpsPort,
  state: join(tmpdir(), `cockpit-journeys-${port}`),
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
