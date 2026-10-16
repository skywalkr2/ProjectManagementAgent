import type { S } from "./api";
import { accountName, ago, broken, nextStep, orderAccounts, roleOf, stateOf, summarize, workWords } from "./ai-accounts";

type A = S["AiAccountView"];
const account = (name: string, extra: Partial<A> = {}): A => ({
  name,
  label: "",
  kind: null,
  adapter: "x",
  base_url: null,
  models: { everyday: "m" },
  used_for: [],
  backup_for: [],
  has_key: true,
  key_state: "saved",
  key_where: null,
  key_ending: false,
  answered_at: null,
  spent_today_usd: 0,
  checked_for: [],
  check_failed_for: [],
  checked_at: null,
  paused_until: null,
  check_usd: null,
  ...extra,
});
const t = (key: string, vars: Record<string, string | number> = {}) => `${key}${Object.keys(vars).length ? JSON.stringify(vars) : ""}`;
const names = (list: A[]) => list.map((a) => a.name);
const BOTH = ["routine", "deep"];

test("the summary names who does the work, who stands in and which kinds of work have no backup, for every combination", () => {
  // Nothing set up.
  expect(summarize([])).toMatchObject({ empty: true, mains: [], backups: [], gaps: [] });
  // Accounts, but none does the work.
  expect(summarize([account("a")])).toMatchObject({ empty: false, mains: [], gaps: [] });
  // One account does everything and nothing stands in: both kinds of work have a gap.
  const alone = summarize([account("a", { used_for: BOTH })]);
  expect(alone.mains.map((m) => [m.account.name, m.tiers])).toEqual([["a", BOTH]]);
  expect(alone.backups).toEqual([]);
  expect(alone.gaps).toEqual(BOTH);
  // One backs up everything: no gap.
  const covered = summarize([account("a", { used_for: BOTH }), account("b", { backup_for: BOTH })]);
  expect(names(covered.backups)).toEqual(["b"]);
  expect(covered.gaps).toEqual([]);
  // Only everyday work has a backup: harder work is the gap.
  expect(summarize([account("a", { used_for: BOTH }), account("b", { backup_for: ["routine"] })]).gaps).toEqual(["deep"]);
  // Two accounts split the work: each is named with what it does, and each kind of work needs its own backup.
  const split = summarize([account("a", { used_for: ["routine"] }), account("b", { used_for: ["deep"] }), account("c", { backup_for: ["routine"] })]);
  expect(split.mains.map((m) => [m.account.name, m.tiers])).toEqual([
    ["a", ["routine"]],
    ["b", ["deep"]],
  ]);
  expect(split.gaps).toEqual(["deep"]);
  // Two backups come in the order given; an account that does work is never also listed as a backup.
  expect(names(summarize([account("a", { used_for: BOTH }), account("b", { backup_for: BOTH }), account("c", { backup_for: ["deep"] })]).backups)).toEqual(["b", "c"]);
  expect(names(summarize([account("a", { used_for: ["routine"], backup_for: ["deep"] })]).backups)).toEqual([]);
});

test("a name is the person's own, else the service's and 'account', else a plain name", () => {
  expect(accountName(account("x", { label: " Main account " }), undefined, t)).toBe("Main account");
  expect(accountName(account("x"), { id: "k", name: "Service A" } as S["EndpointView"], t)).toBe('ai_accounts.default_name{"service":"Service A"}');
  expect(accountName(account("stub"), undefined, t)).toBe("ai_accounts.default_name_plain");
});

test("roles, and the order: the working account, then backups, then the rest, a broken one last in its group", () => {
  expect([roleOf(account("a", { used_for: ["deep"] })), roleOf(account("b", { backup_for: ["deep"] })), roleOf(account("c"))]).toEqual(["work", "backup", "none"]);
  expect(broken(account("a", { key_state: "missing" }))).toBe(true);
  expect(broken(account("a", { check_failed_for: ["deep"] }))).toBe(true);
  expect(broken(account("a"))).toBe(false);
  const list = [account("none"), account("work-lost", { used_for: ["routine"], key_state: "missing" }), account("work", { used_for: ["deep"] }), account("back", { backup_for: ["deep"] })];
  expect(names(orderAccounts(list))).toEqual(["work", "work-lost", "back", "none"]);
});

test("the kinds of work in words", () => {
  expect(workWords(BOTH, t)).toBe("ai_accounts.work.both");
  expect(workWords(["routine"], t)).toBe("ai_accounts.work.routine");
  expect(workWords(["deep"], t)).toBe("ai_accounts.work.deep");
  expect(workWords(["routine", "other"], t)).toBe("ai_accounts.work.other");
});

test("the worst state wins, and the next step follows it", () => {
  const needsKey = { needs_key: true } as S["EndpointView"];
  const first = (a: A, kind?: S["EndpointView"]) => stateOf(a, kind, BOTH).kind;
  expect(first(account("a", { key_state: "missing", check_failed_for: ["deep"], paused_until: "2026-10-16T10:00:00Z" }))).toBe("missing");
  expect(first(account("a", { key_state: "none" }), needsKey)).toBe("no_key");
  expect(first(account("a", { key_state: "none" }), { needs_key: false } as S["EndpointView"])).toBe("untested");
  expect(first(account("a", { check_failed_for: ["deep"], paused_until: "2026-10-16T10:00:00Z" }))).toBe("failed");
  expect(first(account("a", { paused_until: "2026-10-16T10:00:00Z", key_ending: true }))).toBe("paused");
  expect(first(account("a", { key_ending: true, answered_at: "2026-10-16T10:00:00Z" }))).toBe("ending");
  expect(first(account("a", { answered_at: "2026-10-16T10:00:00Z", checked_for: BOTH }))).toBe("ready");
  expect(stateOf(account("a", { checked_for: BOTH }), undefined, BOTH)).toEqual({ kind: "checked", tiers: [] });
  expect(stateOf(account("a", { checked_for: ["deep"] }), undefined, BOTH)).toEqual({ kind: "checked", tiers: ["deep"] });
  expect(first(account("a"))).toBe("untested");
  expect(nextStep("missing")).toEqual({ step: "add_key", primary: true });
  expect(nextStep("no_key")).toEqual({ step: "add_key", primary: true });
  expect(nextStep("untested")).toEqual({ step: "test", primary: true });
  expect(nextStep("failed")).toEqual({ step: "see_why", primary: true });
  expect(nextStep("paused")).toEqual({ step: null, primary: false });
  expect(nextStep("ready")).toEqual({ step: "test", primary: false });
  expect(nextStep("checked")).toEqual({ step: "test", primary: false });
});

test("how long ago is said in the sheet's words", () => {
  const now = new Date("2026-10-16T12:00:00Z");
  expect(ago("2026-10-16T11:59:40Z", now, t)).toBe("ai_accounts.ago.now");
  expect(ago("2026-10-16T11:30:00Z", now, t)).toBe('ai_accounts.ago.min{"n":30}');
  expect(ago("2026-10-16T10:00:00Z", now, t)).toBe('ai_accounts.ago.hours{"n":2}');
  expect(ago("2026-10-12T12:00:00Z", now, t)).toBe('ai_accounts.ago.days{"n":4}');
});
