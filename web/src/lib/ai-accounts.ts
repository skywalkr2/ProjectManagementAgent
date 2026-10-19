// What an AI account's row says (design 7.16): its name, its role in words, what it covers, its state and the one next step.
// Plain functions over the account views, so every combination of main and backup accounts is tested without a screen.
import type { S } from "./api";

export type Account = S["AiAccountView"];
export type Kind = S["EndpointView"];
export type Role = "work" | "backup" | "none";
type T = (key: string, vars?: Record<string, string | number>) => string;

/** The tiers in the order a person meets them: everyday work first, then harder work, then anything else. */
const TIERS = ["routine", "deep"];
const byTier = (a: string, b: string) => {
  const rank = (t: string) => (TIERS.includes(t) ? TIERS.indexOf(t) : TIERS.length);
  return rank(a) - rank(b) || a.localeCompare(b);
};

export function accountName(account: Account, kind: Kind | undefined, t: T): string {
  const own = (account.label ?? "").trim();
  if (own) return own;
  return kind ? t("ai_accounts.default_name", { service: kind.name }) : t("ai_accounts.default_name_plain");
}

export const roleOf = (a: Account): Role => (a.used_for.length ? "work" : (a.backup_for ?? []).length ? "backup" : "none");

/** Something is wrong with the account: its key is gone, or its last check failed. */
export const broken = (a: Account): boolean => a.key_state === "missing" || (a.check_failed_for ?? []).length > 0;

/** The working account first, then backups, then the rest; a broken one goes last within its group. Otherwise the order is kept. */
export function orderAccounts(list: Account[]): Account[] {
  const rank = (a: Account) => ["work", "backup", "none"].indexOf(roleOf(a)) * 2 + (broken(a) ? 1 : 0);
  return list.map((a, i) => ({ a, i })).sort((x, y) => rank(x.a) - rank(y.a) || x.i - y.i).map((x) => x.a);
}

/** The kinds of work an account does (or backs up) as words: "everyday and harder work". */
export function workWords(tiers: string[], t: T): string {
  const set = new Set(tiers);
  const has = (tier: string) => set.has(tier);
  const other = [...set].some((x) => !TIERS.includes(x));
  if (has("routine") && has("deep") && !other) return t("ai_accounts.work.both");
  if (has("routine") && !other && !has("deep")) return t("ai_accounts.work.routine");
  if (has("deep") && !other && !has("routine")) return t("ai_accounts.work.deep");
  return t("ai_accounts.work.other");
}

export interface Summary {
  /** No account is set up at all. */
  empty: boolean;
  /** The distinct accounts that do some work, each with the tiers it does, in the order the work is met. */
  mains: { account: Account; tiers: string[] }[];
  /** The accounts that stand in, in the order they are tried (the first tier's chain first). */
  backups: Account[];
  /** Tiers that someone does and nobody stands in for. */
  gaps: string[];
}

/** Who does the work and who stands in, for the line above the rows. `chains` is not needed: an account's own lists say it. */
export function summarize(accounts: Account[]): Summary {
  const tiers = [...new Set(accounts.flatMap((a) => a.used_for))].sort(byTier);
  const mains: Summary["mains"] = [];
  for (const tier of tiers) {
    const account = accounts.find((a) => a.used_for.includes(tier));
    if (!account) continue;
    const found = mains.find((m) => m.account.name === account.name);
    if (found) found.tiers.push(tier);
    else mains.push({ account, tiers: [tier] });
  }
  const backups = accounts.filter((a) => (a.backup_for ?? []).length > 0 && !a.used_for.length);
  const covered = new Set(accounts.flatMap((a) => a.backup_for ?? []));
  return { empty: accounts.length === 0, mains, backups, gaps: tiers.filter((tier) => !covered.has(tier)) };
}

/** How long ago, in the words the sheet gives: "just now", "12 minutes ago", "2 hours ago", "3 days ago". */
export function ago(iso: string, now: Date, t: T): string {
  const then = new Date(iso);
  const minutes = Math.max(0, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (minutes < 1) return t("ai_accounts.ago.now");
  const form = (n: number) => (n === 1 ? "one" : "other");
  if (minutes < 60) return t(`ai_accounts.ago.min.${form(minutes)}`, { n: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t(`ai_accounts.ago.hours.${form(hours)}`, { n: hours });
  return t("ai_accounts.ago.days", { n: Math.round(hours / 24) });
}

export type StateKind = "no_key" | "missing" | "failed" | "paused" | "ending" | "ready" | "checked" | "untested";

/** The worst state of the account, which is the one its row shows, and which tiers it concerns. */
export function stateOf(account: Account, kind: Kind | undefined, allTiers: string[]): { kind: StateKind; tiers: string[] } {
  if (account.key_state === "missing") return { kind: "missing", tiers: [] };
  if (account.key_state === "none" && kind?.needs_key) return { kind: "no_key", tiers: [] };
  const failed = account.check_failed_for ?? [];
  if (failed.length) return { kind: "failed", tiers: [...failed].sort(byTier) };
  if (account.paused_until) return { kind: "paused", tiers: [] };
  if (account.key_ending) return { kind: "ending", tiers: [] };
  if (account.answered_at) return { kind: "ready", tiers: [] };
  const checked = account.checked_for ?? [];
  if (checked.length) return { kind: "checked", tiers: allTiers.every((x) => checked.includes(x)) ? [] : [...checked].sort(byTier) };
  return { kind: "untested", tiers: [] };
}

/** The tiers that exist, as far as the accounts say: those somebody does or stands in for, checked or failed. */
export function knownTiers(accounts: Account[]): string[] {
  return [...new Set(accounts.flatMap((a) => [...a.used_for, ...(a.backup_for ?? [])]))].sort(byTier);
}

export type Next = "add_key" | "test" | "see_why" | null;

/** The one next step, by state: no key adds one, an untested account is tested, a failed check is looked at, a paused
 * account has nothing (its line says until when), and a ready one can still be tested. */
export function nextStep(state: StateKind): { step: Next; primary: boolean } {
  switch (state) {
    case "no_key":
    case "missing":
      return { step: "add_key", primary: true };
    case "untested":
      return { step: "test", primary: true };
    case "failed":
      return { step: "see_why", primary: true };
    case "paused":
      return { step: null, primary: false };
    default:
      return { step: "test", primary: false };
  }
}
