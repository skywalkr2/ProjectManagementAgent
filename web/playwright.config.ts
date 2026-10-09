// Browser tests: the acceptance scenario at the root path and under a nested base path, with accessibility checks.
// Build the UI first (npm run build); each project starts its own server from the repository root.
import { defineConfig, devices } from "@playwright/test";

const servers = [
  { name: "root", port: 8781, base: "/" },
  { name: "nested", port: 8782, base: "/admin" },
];

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
  },
  projects: servers.map((s) => ({
    name: s.name,
    use: { baseURL: `http://127.0.0.1:${s.port}${s.base === "/" ? "/" : `${s.base}/`}` },
  })),
  webServer: servers.map((s) => ({
    command: `uv run python -m tests.e2e_server --port ${s.port} --base-path ${s.base}`,
    cwd: "..",
    url: `http://127.0.0.1:${s.port}${s.base === "/" ? "" : s.base}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  })),
});
