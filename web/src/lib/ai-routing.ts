// Which model does what (design 7.9): the plain functions behind the part of Settings that chooses the tier each kind of
// work uses, the tier each tier tries once more on, and the routing rules; and the one hook that saves them. A change is
// saved as it is made, on the fingerprint the screen last knew, and read back with Undo like every other setting.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { api, ApiError, type S } from "./api";
import { problemText } from "./problem";
import { readable } from "./records";
import { knownFingerprint, rememberFingerprint, useAfterSave } from "./settings-save";
import { useWords } from "./wording";

export type Routing = S["AiRoutingView"];
export type WorkKind = S["AiWorkKindView"];
export type Fit = S["AiKindFit"];
export type Level = NonNullable<S["AiRouteRuleView"]["data_level"]>;

/** The data levels, least private first. */
export const LEVELS: Level[] = ["open", "internal", "restricted"];

/** The settings keys this part changes. */
export const taskKey = (kind: string) => `ai.tasks.${kind}.tier`;
export const escalateKey = (tier: string) => `ai.tiers.${tier}.escalate_to`;
export const ROUTING_KEY = "ai.routing";

/** One routing rule as the screen edits it: every part is the text of a control ("" is "any"). */
export interface RuleRow {
  task: string;
  chars: string;
  quotes: string;
  level: string;
  tier: string;
}

export const rowOf = (rule: S["AiRouteRuleView"]): RuleRow => ({
  task: rule.task ?? "",
  chars: rule.input_chars_over == null ? "" : String(rule.input_chars_over),
  quotes: rule.quoted_messages_over == null ? "" : String(rule.quoted_messages_over),
  level: rule.data_level ?? "",
  tier: rule.tier,
});

const whole = (text: string): number | null => (/^\d+$/.test(text.trim()) ? Number(text.trim()) : null);

/** What is wrong with a rule as typed: a number that isn't a whole number, or no part saying when it applies. A rule with
 * no part would send everything, so it is never saved. */
export function ruleProblem(row: RuleRow): "number" | "when" | null {
  if ((row.chars.trim() && whole(row.chars) === null) || (row.quotes.trim() && whole(row.quotes) === null)) return "number";
  return row.task || row.chars.trim() || row.quotes.trim() || row.level ? null : "when";
}

/** The rule to save for a row, in the shape of the setting (only the parts given), or null while the row has a problem. */
export function ruleOf(row: RuleRow) {
  if (ruleProblem(row)) return null;
  const when: Record<string, unknown> = {};
  if (row.task) when.task = row.task;
  if (row.chars.trim()) when.input_chars_over = whole(row.chars);
  if (row.quotes.trim()) when.quoted_messages_over = whole(row.quotes);
  if (row.level) when.data_level = row.level;
  return { when, tier: row.tier };
}

/** The rules to save for the rows on screen: those that are complete, in order. */
export const rulesOf = (rows: RuleRow[]) => rows.flatMap((row) => ruleOf(row) ?? []);

/** The row a suggested rule would add. */
export const suggestedRow = (rule: S["AiRouteRuleView"]): RuleRow => rowOf(rule);

/** Rows with the one at `index` moved by `step` places; the same rows when it can't move that way. */
export function moved(rows: RuleRow[], index: number, step: -1 | 1): RuleRow[] {
  const to = index + step;
  if (to < 0 || to >= rows.length) return rows;
  const next = [...rows];
  [next[index], next[to]] = [next[to], next[index]];
  return next;
}

export type Result = { ok: true } | { ok: false; problem: string };

/** Saves settings changes from this part, one at a time, each on the fingerprint the one before answered with. A save
 * made on an old fingerprint is refused in plain words and the newest fingerprint is adopted, so what the person typed
 * stays and a second try goes through once they have looked. */
export function useRoutingSave() {
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const { t } = useWords();
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  return useCallback(
    (body: { changes?: Record<string, unknown>; reset?: string[] }, message: string): Promise<Result> => {
      const run = async (): Promise<Result> => {
        const view = client.getQueryData<S["SettingsView"]>(["settings"]);
        const fingerprint =
          knownFingerprint(client, view?.fingerprint) ??
          (await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 })).fingerprint;
        try {
          const saved = await api.saveSettings({ changes: body.changes ?? {}, reset: body.reset ?? [], fingerprint });
          await afterSave(saved, { message });
          return { ok: true };
        } catch (err) {
          if (err instanceof ApiError && err.status === 409) {
            const fresh = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
            rememberFingerprint(client, fresh.fingerprint);
            void client.invalidateQueries({ queryKey: ["ai-routing"] });
            return { ok: false, problem: t("settings.changed_since_opened") };
          }
          return { ok: false, problem: err instanceof ApiError && err.detail ? err.detail : problemText(err, t) };
        }
      };
      const next = chain.current.then(run, run);
      chain.current = next;
      return next;
    },
    [client, afterSave, t],
  );
}

/** A tier's name in plain words: the sheet's for the two the app starts with, otherwise its own name made readable. */
export function useTierName() {
  const { t, has } = useWords();
  return useCallback((tier: string) => (has(`welcome.ai.tier.${tier}`) ? t(`welcome.ai.tier.${tier}`) : readable(tier)), [t, has]);
}
