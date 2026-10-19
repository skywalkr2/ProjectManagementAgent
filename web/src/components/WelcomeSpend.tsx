// What the assistant may spend (design 7.8, the AI step of the walkthrough): the amount above which a run asks first and
// the most it may spend in a day, each with its starting value. They are ordinary settings, saved the way the Settings
// screen saves them, so the change reads back with Undo.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useTotal } from "../lib/money";
import { problemText } from "../lib/problem";
import { fromDraft } from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";

const CONFIRM = "ai.budgets.confirm_above_usd";
const DAY = "ai.budgets.per_day_usd";
const KEYS = [CONFIRM, DAY] as const;

export function WelcomeSpend() {
  const { t } = useWords();
  const total = useTotal();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  if (!settings.data) return null;
  const find = (key: string): S["SettingItem"] | undefined => settings.data.items.find((i) => i.key === key);
  const items = KEYS.map(find);
  if (items.some((i) => !i)) return null;
  const shown = (item: S["SettingItem"]) => edits[item.key] ?? String(item.value ?? "");

  const changes: Record<string, unknown> = {};
  let bad = false;
  for (const item of items as S["SettingItem"][]) {
    if (edits[item.key] === undefined) continue;
    const parsed = fromDraft(item, edits[item.key]);
    if (!parsed.ok) bad = true;
    else if (parsed.value !== item.value) changes[item.key] = parsed.value;
  }
  const pending = Object.keys(changes).length > 0;

  const save = async () => {
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes, reset: [], fingerprint: settings.data.fingerprint });
      setEdits({});
      await afterSave(saved);
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  const field = (item: S["SettingItem"], labelKey: string, hintKey: string) => {
    const id = `spend-${item.key.replace(/\./g, "-")}`;
    const off = item.locked || !item.editable;
    return (
      <div className="field">
        <label htmlFor={id}>{t(labelKey)}</label>
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={shown(item)}
          disabled={off}
          autoComplete="off"
          aria-describedby={`${id}-hint`}
          onChange={(e) => {
            const value = e.target.value;
            setEdits((before) => ({ ...before, [item.key]: value }));
          }}
        />
        <p className="hint" id={`${id}-hint`}>
          {t(hintKey, { amount: total(Number(item.default ?? 0)) })}
        </p>
        {item.locked && <p className="hint">{t(item.source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
      </div>
    );
  };

  return (
    <form
      className="spend"
      aria-labelledby="spend-title"
      onSubmit={(e) => {
        e.preventDefault();
        if (pending && !bad) void save();
      }}
    >
      <h4 id="spend-title">{t("welcome.spend.title")}</h4>
      <p className="hint">{t("welcome.spend.intro")}</p>
      {field(items[0]!, "welcome.spend.confirm", "welcome.spend.confirm_hint")}
      {field(items[1]!, "welcome.spend.day", "welcome.spend.day_hint")}
      {bad && (
        <p className="problem-note" role="alert">
          {t("welcome.spend.bad")}
        </p>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        <button type="submit" className="btn" disabled={busy || bad || !pending}>
          {t("welcome.spend.save")}
        </button>
      </div>
    </form>
  );
}
