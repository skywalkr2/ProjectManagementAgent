import type { S } from "../lib/api";
import { aliveState, initials, isWarn, worstState } from "./status";

const status = (over: Partial<S["Status"]> = {}, backup: Partial<S["BackupStatus"]> = {}, spend: Partial<S["SpendStatus"]> = {}): S["Status"] => ({
  backup: { configured: true, last_success: null, age_hours: 1, needs_attention: false, last_error: null, encrypted: false, ...backup },
  ai: { state: "ok", detail: null },
  assistant: { last_run_at: null, last_run_failed: false, runs_today: [], queued: 0, oldest_queued_since: null, chains: [], paused: [] },
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

test("work waiting for the network is its own state: after offline, before a restart or a backup", () => {
  const waiting = { count: 2, since: "2026-10-13T14:05:00+00:00" };
  const all = status({ restart_needed: "settings", network_wait: waiting }, { needs_attention: true }, { warn: true });
  expect(worstState({ live: "live", status: all, restartPhase: "idle" })).toBe("network");
  expect(worstState({ live: "offline", status: all, restartPhase: "idle" })).toBe("offline");
  expect(worstState({ live: "live", status: status({ network_wait: null }), restartPhase: "idle" })).toBe("live");
  expect(isWarn("network")).toBe(true);
});

const alive = (over: Partial<S["Status"]> = {}, restartPhase = "idle", assistant: Partial<S["AssistantStatus"]> = {}) => {
  const base = status(over);
  return aliveState({ status: { ...base, assistant: { ...base.assistant, ...assistant } }, restartPhase });
};

test("the assistant's line is fine when nothing is wrong, whatever else the chip says", () => {
  expect(alive()).toEqual({ kind: "fine", tone: "ok" });
  expect(alive({}, "idle", { queued: 3 })).toEqual({ kind: "fine", tone: "ok" });
  expect(alive({ backup: { configured: true, last_success: null, age_hours: 100, needs_attention: true, last_error: null, encrypted: false } })).toEqual({ kind: "fine", tone: "ok" });
});

test("the assistant's line is amber for the states that hold its work up", () => {
  expect(alive({ network_wait: { count: 1, since: "2026-10-14T09:00:00" } })).toEqual({ kind: "network", tone: "warn" });
  expect(alive({ restart_needed: "A change needs a restart." })).toEqual({ kind: "restart", tone: "warn" });
  expect(alive({}, "waiting")).toEqual({ kind: "restarting", tone: "warn" });
  expect(alive({}, "idle", { paused: [{ account: "main", until: "2026-10-14T11:00:00+00:00" }] })).toEqual({ kind: "paused", tone: "warn" });
  expect(alive({ ai: { state: "not_set_up", detail: null } })).toEqual({ kind: "not_set_up", tone: "warn" });
});

test("the assistant's line is red when its account or its last run fails, ahead of the amber states", () => {
  expect(alive({ ai: { state: "failing", detail: null } })).toEqual({ kind: "failing", tone: "bad" });
  expect(alive({ network_wait: { count: 1, since: "2026-10-14T09:00:00" } }, "idle", { last_run_failed: true })).toEqual({ kind: "run_failed", tone: "bad" });
});
