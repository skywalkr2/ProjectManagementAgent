// What the checks of an account that was just added are doing (design 7.16): the add form closes as soon as the account is
// saved, and the checks go on after it. They are kept here, outside any screen, so the account's row can say which kind of
// work is being checked now and, when one didn't pass, why. Nothing here is kept past a reload: the row's state comes from
// the account itself.
import { useSyncExternalStore } from "react";

export interface AccountCheck {
  /** The kind of work being checked now (a tier), or null when no check is running. */
  running: string | null;
  /** The check that didn't pass: what the account said, and the kinds of work it was being checked for. */
  failed: { detail: string; tiers: string[] } | null;
}

const checks = new Map<string, AccountCheck>();
const listeners = new Set<() => void>();
let version = 0;

function changed() {
  version += 1;
  listeners.forEach((fn) => fn());
}

/** Note what an account's check is doing; `null` forgets it. */
export function setAccountCheck(account: string, check: AccountCheck | null): void {
  if (check === null) checks.delete(account);
  else checks.set(account, check);
  changed();
}

export function accountCheck(account: string): AccountCheck | undefined {
  return checks.get(account);
}

/** Forget every check (for tests, which share one page). */
export function resetAccountChecks(): void {
  checks.clear();
  changed();
}

/** An account's check as it stands, and the screen follows it as it moves. */
export function useAccountCheck(account: string): AccountCheck | undefined {
  useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => version,
  );
  return checks.get(account);
}
