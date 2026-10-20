// A time zone picked by city (design 7.8, 7.9): type to narrow the list ("new yo"), then choose "New York (Eastern time)".
// The setting holds the zone's id; the person only ever sees cities.
import { useId, useMemo, useState } from "react";
import { zoneChoices, zoneMatches } from "../lib/time-zones";
import { useWords } from "../lib/wording";

export function TimeZoneSelect(props: {
  id: string;
  value: string;
  /** The ids of the zones to offer. */
  options: string[];
  onChange: (id: string) => void;
  disabled?: boolean;
  describedBy?: string;
}) {
  const { t } = useWords();
  const [typed, setTyped] = useState("");
  const findId = useId();
  const all = useMemo(() => zoneChoices(props.options.includes(props.value) || !props.value ? props.options : [props.value, ...props.options]), [props.options, props.value]);
  // The chosen zone stays in the list whatever was typed, so the select never shows one that isn't the value.
  const shown = all.filter((c) => c.id === props.value || zoneMatches(c, typed));
  return (
    <div className="time-zone-select">
      <label htmlFor={findId} className="sr">
        {t("timezone.find")}
      </label>
      <input
        id={findId}
        type="search"
        value={typed}
        autoComplete="off"
        placeholder={t("timezone.find")}
        disabled={props.disabled}
        onChange={(e) => setTyped(e.target.value)}
      />
      <select
        id={props.id}
        value={props.value}
        disabled={props.disabled}
        aria-describedby={props.describedBy}
        onChange={(e) => props.onChange(e.target.value)}
      >
        {shown.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
          </option>
        ))}
      </select>
      {typed.trim() !== "" && shown.length <= 1 && (
        <p className="hint" role="status">
          {t("timezone.none")}
        </p>
      )}
    </div>
  );
}
