// What the assistant may spend, as one sentence (design 7.8, the AI step): "It asks you before anything over $0.10, and stops
// for the day at $2 · Change". Change opens the two amounts as money fields (the workspace's currency symbol in front,
// from the wording sheet). The amounts are ordinary settings; the screen's Continue saves a change with the account, so
// there is one button and one read-back. Until Change is pressed nothing about spending is asked.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAmount } from "../lib/money";
import { problemText } from "../lib/problem";
import { fromDraft } from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";

const CONFIRM = "ai.budgets.confirm_above_usd";
const DAY = "ai.budgets.per_day_usd";

/** A sentence whose amounts are wrapped in \u0001 marks, with the amounts in strong type. */
function emphasised(text: string): ReactNode[] {
  return text.split("\u0001").map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : part));
}

export interface SpendLine {
  /** The sentence, or the two fields once Change was pressed; nothing until the settings have loaded. */
  node: ReactNode;
  /** An amount was changed and isn't saved yet. */
  pending: boolean;
  /** An amount isn't a number. */
  bad: boolean;
  /** Saves the changed amounts with Undo. Returns false, having said why, when the save was refused. */
  save: () => Promise<boolean>;
  /** The amount the person asks to be asked above, for a sentence elsewhere (the credit advice). */
  perDay: number | null;
}

/** The spending sentence and what saving it takes. `enabled` false leaves it out (a form that has no such line). */
export function useSpendLine(enabled = true): SpendLine {
  const { t } = useWords();
  const amount = useAmount();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled });
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const base = useId();
  const find = (key: string): S["SettingItem"] | undefined => settings.data?.items.find((i) => i.key === key);
  const confirm = find(CONFIRM);
  const day = find(DAY);

  const changes: Record<string, unknown> = {};
  let bad = false;
  for (const item of [confirm, day]) {
    if (!item || edits[item.key] === undefined) continue;
    const parsed = fromDraft(item, edits[item.key]);
    if (!parsed.ok) bad = true;
    else if (parsed.value !== item.value) changes[item.key] = parsed.value;
  }
  const pending = Object.keys(changes).length > 0;

  const save = async (): Promise<boolean> => {
    if (!settings.data || !pending || bad) return !bad;
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes, reset: [], fingerprint: settings.data.fingerprint });
      setEdits({});
      setEditing(false);
      await afterSave(saved);
      return true;
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return false;
    }
  };

  const shown = (item: S["SettingItem"]) => edits[item.key] ?? String(item.value ?? "");
  const number = (item: S["SettingItem"]) => {
    const parsed = fromDraft(item, shown(item));
    return parsed.ok ? Number(parsed.value) : Number(item.value ?? 0);
  };

  const field = (item: S["SettingItem"], label: string, hint: string) => {
    const id = `${base}-${item.key.replace(/\./g, "-")}`;
    const off = item.locked || !item.editable;
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <span className="money-field">
          <span aria-hidden="true">{t("money.symbol")}</span>
          <input
            id={id}
            type="text"
            inputMode="decimal"
            value={shown(item)}
            disabled={off}
            autoComplete="off"
            aria-describedby={`${id}-hint`}
            aria-invalid={bad && edits[item.key] !== undefined && !fromDraft(item, edits[item.key]).ok ? true : undefined}
            onChange={(e) => {
              const value = e.target.value;
              setEdits((before) => ({ ...before, [item.key]: value }));
            }}
          />
        </span>
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
        {item.locked && <p className="hint">{t(item.source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
      </div>
    );
  };

  const node =
    enabled && confirm && day ? (
      <section className="spend" aria-labelledby={`${base}-title`}>
        <h4 id={`${base}-title`} className="sr">
          {t("welcome.spend.title")}
        </h4>
        {editing ? (
          <>
            <p className="hint">{t("welcome.spend.intro")}</p>
            {field(confirm, t("welcome.spend.confirm"), t("welcome.spend.confirm_hint", { amount: amount(Number(confirm.default ?? 0)) }))}
            {field(day, t("welcome.spend.day"), t("welcome.spend.day_hint", { amount: amount(Number(day.default ?? 0)) }))}
            {bad && (
              <p className="problem-note" role="alert">
                {t("welcome.spend.bad")}
              </p>
            )}
          </>
        ) : (
          <p className="spend-line" data-spend-line="">
            {emphasised(t("welcome.spend.sentence", { ask: `\u0001${amount(number(confirm))}\u0001`, stop: `\u0001${amount(number(day))}\u0001` }))}{" "}
            <button type="button" className="link-button" aria-expanded={false} onClick={() => setEditing(true)}>
              {t("welcome.spend.change")}
            </button>
          </p>
        )}
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
      </section>
    ) : null;

  return { node, pending, bad, save, perDay: day ? number(day) : null };
}
