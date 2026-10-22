// How long a to-do takes (design 6.32): a list of the common sizes, with "Another length" for any other number of minutes,
// and "No estimate" for none. The to-do's effort is what the day's capacity check adds up.
import { useState } from "react";
import { durationWords, EFFORT_SIZES } from "../lib/duration";
import { useWords } from "../lib/wording";

const OTHER = "other";

export function EffortField(props: { id: string; value: number | null; onChange: (minutes: number | null) => void }) {
  const { t, tn } = useWords();
  const sized = props.value !== null && EFFORT_SIZES.includes(props.value);
  const [other, setOther] = useState(props.value !== null && !sized);
  const picked = props.value === null && !other ? "" : other || !sized ? OTHER : String(props.value);
  return (
    <div className="field">
      <label htmlFor={`${props.id}-effort`}>{t("effort.label")}</label>
      <select
        id={`${props.id}-effort`}
        value={picked}
        onChange={(e) => {
          const next = e.target.value;
          if (next === OTHER) {
            setOther(true);
            return;
          }
          setOther(false);
          props.onChange(next === "" ? null : Number(next));
        }}
      >
        <option value="">{t("effort.none")}</option>
        {EFFORT_SIZES.map((size) => (
          <option key={size} value={size}>
            {durationWords(size, tn)}
          </option>
        ))}
        <option value={OTHER}>{t("effort.other")}</option>
      </select>
      {picked === OTHER && (
        <input
          id={`${props.id}-effort-minutes`}
          type="number"
          min={1}
          max={1440}
          step={1}
          inputMode="numeric"
          aria-label={t("effort.minutes")}
          value={props.value ?? ""}
          onChange={(e) => {
            const n = Math.round(Number(e.target.value));
            props.onChange(e.target.value === "" || !Number.isFinite(n) || n < 1 ? null : Math.min(1440, n));
          }}
        />
      )}
    </div>
  );
}
