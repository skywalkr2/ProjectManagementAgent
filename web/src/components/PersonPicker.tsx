// Choosing a person: suggested people first, then everyone, by full name, and last "Add a person…": the form opens in a
// drawer, and the person it adds is the one picked, so nobody leaves the screen to add someone (open promise P13).
import { useId, useRef, useState } from "react";
import type { S } from "../lib/api";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { PersonDrawer } from "./PersonForm";

/** The choice that opens the add form; no person id can look like it. */
const ADD = "\u0001add";

export function PersonPicker(props: {
  label: string;
  value: string;
  onChange: (person: string) => void;
  suggested: S["Option"][];
  people: S["PersonView"][];
  /** What "Add a person…" does, when it is not the plain form (a question that is answered by who the person is). */
  onAdd?: () => void;
  /** Leave the add choice out (a place that only picks among those already on file). */
  noAdd?: boolean;
}) {
  const { t } = useWords();
  const id = useId();
  const select = useRef<HTMLSelectElement>(null);
  const [adding, setAdding] = useState(false);
  const suggestedIds = new Set(props.suggested.map((o) => o.id));
  const others = props.people.filter((p) => !suggestedIds.has(p.id));
  const describe = (p: S["PersonView"]) => (p.role ? t("person.with_role", { name: p.name, role: p.role }) : p.name);
  const close = () => {
    setAdding(false);
    restoreFocus(() => select.current);
  };
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select
        id={id}
        ref={select}
        value={props.value}
        onChange={(e) => {
          if (e.target.value !== ADD) return props.onChange(e.target.value);
          if (props.onAdd) props.onAdd();
          else setAdding(true);
        }}
      >
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
        {!props.noAdd && <option value={ADD}>{t("person.add_option")}</option>}
      </select>
      {adding && <PersonDrawer onClose={close} onSaved={(personId) => props.onChange(personId)} />}
    </div>
  );
}
