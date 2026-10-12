import type { S } from "../lib/api";
import { initials, isWarn, worstState } from "./status";

const status = (over: Partial<S["Status"]> = {}, backup: Partial<S["BackupStatus"]> = {}, spend: Partial<S["SpendStatus"]> = {}): S["Status"] => ({
  backup: { configured: true, last_success: null, age_hours: 1, needs_attention: false, last_error: null, ...backup },
  ai: { state: "ok", detail: null },
  spend: { today_usd: 0, month_usd: 0, per_day_usd: 2, per_month_usd: 30, warn: false, warn_today: false, warn_month: false, ...spend },
  requests: { queued: 0, running: 0, review: 0, needs_you: 0 },
  version: 1,
  restart_needed: null,
  can_restart: true,
  ...over,
});

test("all good is live", () => {
  expect(worstState({ live: "live", status: status(), restartPhase: "idle" })).toBe("live");
  expect(worstState({ live: "live", status: undefined, restartPhase: "idle" })).toBe("live");
  expect(isWarn("live")).toBe(false);
});

test("the worst state wins: offline, then restart, then backup, then spend", () => {
  const all = status({ restart_needed: "settings" }, { needs_attention: true }, { warn: true });
  expect(worstState({ live: "offline", status: all, restartPhase: "idle" })).toBe("offline");
  expect(worstState({ live: "live", status: all, restartPhase: "idle" })).toBe("restart");
  expect(worstState({ live: "live", status: status({}, { needs_attention: true }, { warn: true }), restartPhase: "idle" })).toBe("backup");
  expect(worstState({ live: "live", status: status({}, {}, { warn: true }), restartPhase: "idle" })).toBe("spend");
  expect(isWarn("offline") && isWarn("restart") && isWarn("backup") && isWarn("spend")).toBe(true);
});

test("a restart being asked about, or stuck, is a restart to finish, and one under way says so", () => {
  for (const phase of ["asking", "stuck", "refused"]) expect(worstState({ live: "live", status: status(), restartPhase: phase })).toBe("restart");
  expect(worstState({ live: "live", status: status(), restartPhase: "waiting" })).toBe("restarting");
  // Done is over: back to what is true now.
  expect(worstState({ live: "live", status: status(), restartPhase: "done" })).toBe("live");
});

test("before the stream connects the chip says it is connecting, not live", () => {
  expect(worstState({ live: "connecting", status: status(), restartPhase: "idle" })).toBe("connecting");
});

test("initials are up to two letters of the name", () => {
  expect(initials("Example Workspace")).toBe("EW");
  expect(initials("Casey Example")).toBe("CE");
  expect(initials("Casey Jordan Example")).toBe("CE");
  expect(initials("Cockpit")).toBe("C");
  expect(initials("  ")).toBe("");
  expect(initials("émile zola")).toBe("ÉZ");
});
