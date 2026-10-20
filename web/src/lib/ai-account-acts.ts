// The steps that change which AI account does the work, shared by an account's row and the add drawer (design 7.16).
// A change is saved with the settings' current fingerprint and read back with Undo; an account stands in for a kind of
// work only after it passed its check for that work with the exact settings, so the check always comes first.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, type S } from "./api";
import type { Account } from "./ai-accounts";
import { useAfterSave } from "./settings-save";

/** The short name of the model that stands for everyday work, and the one added for harder work. */
export const EVERYDAY = "everyday";
export const HARDER = "harder";

/** The model an account uses for each kind of work: its everyday one, and its harder one when it has one. */
export function modelsOf(account: Account): { everyday: string; deep: string } {
  const shorts = Object.keys(account.models);
  const everyday = shorts.find((s) => s !== HARDER) ?? shorts[0];
  return { everyday, deep: HARDER in account.models ? HARDER : everyday };
}

/** The kinds of work an account does (as a main account), with the model it would use for each. */
export function planFor(account: Account, tiers: string[]): [string, string][] {
  const { everyday, deep } = modelsOf(account);
  return tiers.map((tier) => [tier, tier === "deep" ? deep : everyday]);
}

export function useAccountActs() {
  const client = useQueryClient();
  const afterSave = useAfterSave();
  /** Saves a change with the settings' current fingerprint (or `opened`, the one a form was made from, so a change made
   * since is refused rather than overwritten), then reads it back with Undo. Throws what the server refused. */
  const save = useCallback(
    async (work: (fingerprint: string) => Promise<S["SettingsSaved"]>, message: string | (() => string), opened?: string) => {
      const fingerprint = opened ?? (await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 })).fingerprint;
      const saved = await work(fingerprint);
      await afterSave(saved, { message: typeof message === "function" ? message() : message });
    },
    [client, afterSave],
  );
  /** Checks the account for each kind of work in the plan, with its exact settings; the first that didn't pass, or null.
   * `onStep` is told which kind of work is about to be checked, so a screen can say so. */
  const failing = useCallback(
    async (name: string, plan: [string, string][], onStep?: (tier: string) => void): Promise<S["AiTestResult"] | null> => {
      try {
        for (const [tier, short] of plan) {
          onStep?.(tier);
          const line = (await api.testAccount(name, tier, short))[0];
          if (line && !line.ok) return line;
        }
        return null;
      } finally {
        // What was checked shows on the account's row.
        void client.invalidateQueries({ queryKey: ["ai-accounts"] });
      }
    },
    [client],
  );
  /** Makes the account a backup for the plan's kinds of work once it passed its check for each. Returns the failing check, or null when it stands in now. */
  const standIn = useCallback(
    async (name: string, plan: [string, string][], message: string, onStep?: (tier: string) => void): Promise<S["AiTestResult"] | null> => {
      const bad = await failing(name, plan, onStep);
      if (bad) return bad;
      await save((fingerprint) => api.changeAccount(name, { fingerprint, backup: Object.fromEntries(plan) }), message);
      return null;
    },
    [failing, save],
  );
  return { save, failing, standIn };
}

/** The amount above which the person asked to be asked before money is spent (`ai.budgets.confirm_above_usd`); until the
 * settings have loaded it is zero, so nothing is spent unasked. */
export function useConfirmAbove(): number {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const value = settings.data?.items.find((i) => i.key === "ai.budgets.confirm_above_usd")?.value;
  return typeof value === "number" ? value : 0;
}
