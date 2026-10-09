// Choosing a person: suggested people first, then everyone, by full name.
import { useId } from "react";
import type { S } from "../lib/api";
import { useWords } from "../lib/wording";

export function PersonPicker(props: {
  label: string;
  value: string;
  onChange: (person: string) => void;
  suggested: S["Option"][];
  people: S["PersonView"][];
}) {
  const { t } = useWords();
  const id = useId();
  const suggestedIds = new Set(props.suggested.map((o) => o.id));
  const others = props.people.filter((p) => !suggestedIds.has(p.id));
  const describe = (p: S["PersonView"]) => (p.role ? t("person.with_role", { name: p.name, role: p.role }) : p.name);
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select id={id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="">{t("person.choose")}</option>
        {props.suggested.length > 0 && (
          <optgroup label={t("person.suggested")}>
            {props.suggested.map((o) => {
              const person = props.people.find((p) => p.id === o.id);
              return (
                <option key={o.id} value={o.id}>
                  {person ? describe(person) : o.name}
                </option>
              );
            })}
          </optgroup>
        )}
        <optgroup label={t("person.everyone")}>
          {others.map((p) => (
            <option key={p.id} value={p.id}>
              {describe(p)}
            </option>
          ))}
        </optgroup>
      </select>
    </div>
  );
}
