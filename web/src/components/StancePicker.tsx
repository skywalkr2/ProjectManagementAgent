// Who a person is to the user (design 6.34), picked from a list on the person's page. A choice saves at once as the user's
// own edit of the person, with Undo; "Use my default" clears it so the setting for everyone decides.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { ApiError, api } from "../lib/api";
import { problemText } from "../lib/problem";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";

export const STANCES = ["manage", "alongside", "report_to", "watch"] as const;
type Stance = (typeof STANCES)[number];

const isStance = (value: unknown): value is Stance => STANCES.includes(value as Stance);

export function StancePicker(props: {
  person: string;
  /** The version of the person record the page shows, so a save never overwrites a newer one. */
  version: number;
  /** The stance the person was given, or none. */
  stance: unknown;
  /** Marked as only tracked, which counts as watching when no stance was given. */
  trackOnly: boolean;
}) {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const id = useId();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const shipped = settings.data?.items.find((item) => item.key === "steward.default_stance")?.value;
  const fallback: Stance = props.trackOnly ? "watch" : isStance(shipped) ? shipped : "alongside";
  const chosen = isStance(props.stance) ? props.stance : "";

  const save = async (value: string) => {
    setSaving(true);
    setError(null);
    try {
      const done = await api.editRecord({
        kind: "person",
        id: props.person,
        fields: { stance: value === "" ? null : value },
        read_version: props.version,
      });
      await client.invalidateQueries();
      push({
        message: t("stance.saved"),
        undo: async () => {
          const report = await api.undo(done.changeset);
          await client.invalidateQueries();
          if (!report.restored.length) throw new Error("not undone");
        },
      });
    } catch (err) {
      setError(problemText(err, t));
      if (err instanceof ApiError && err.status === 409) await client.invalidateQueries();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="field">
      <label htmlFor={id}>{t("stance.title")}</label>
      <select id={id} value={chosen} disabled={saving} aria-describedby={`${id}-hint`} onChange={(e) => void save(e.target.value)}>
        <option value="">{t("stance.default", { stance: t(`stance.${fallback}`) })}</option>
        {STANCES.map((s) => (
          <option key={s} value={s}>
            {t(`stance.${s}`)}
          </option>
        ))}
      </select>
      <span id={`${id}-hint`} className="hint">
        {t("stance.hint")}
      </span>
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
