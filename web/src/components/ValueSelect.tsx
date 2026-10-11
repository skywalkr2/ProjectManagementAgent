// A labelled choice from a value list. It offers the list's values and "Not set"; a value the record still holds but the
// list no longer offers stays shown, marked, so editing other fields never loses it. "Add to the list…" opens a small
// field that adds the value at once (with Undo) and selects it.
import { useId, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { offers, useListChange, useValueLists } from "../lib/lists";
import { useWords } from "../lib/wording";

/** The choice that opens the add field; no list value can look like it. */
const ADD = "\u0001add";

export function ValueSelect(props: {
  /** The list's name. */
  list: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Short text after the label. */
  hint?: ReactNode;
  /** Longer help under the choice. */
  note?: string;
  id?: string;
  required?: boolean;
  autoFocus?: boolean;
}) {
  const { t } = useWords();
  const lists = useValueLists();
  const change = useListChange();
  const own = useId();
  const id = props.id ?? own;
  const select = useRef<HTMLSelectElement>(null);
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const found = lists.data?.find((l) => l.name === props.list);
  const values = found?.values ?? [];
  const { value, required } = props;
  // Held but not offered: shown as an extra choice, marked once the list is known to have dropped it.
  const extra = value !== "" && !values.includes(value) ? value : null;
  const help = props.note ? `${id}-help` : undefined;

  const stop = () => {
    setAdding(false);
    setText("");
    setProblem("");
    window.requestAnimationFrame(() => select.current?.focus());
  };

  const add = async () => {
    const wanted = text.trim();
    if (!wanted || !found || busy) return;
    const existing = offers(values, wanted);
    if (existing) {
      props.onChange(existing);
      stop();
      return;
    }
    setBusy(true);
    setProblem("");
    const failed = await change(
      () => api.listAdd(found.name, wanted),
      t("lists.added_toast", { value: wanted, list: found.label }),
    );
    setBusy(false);
    if (failed) {
      setProblem(failed);
      return;
    }
    props.onChange(wanted);
    stop();
  };

  return (
    <div className="field">
      <label htmlFor={id}>
        {props.label} {props.hint && <span className="hint">{props.hint}</span>}
      </label>
      <select
        id={id}
        ref={select}
        value={value}
        required={required}
        autoFocus={props.autoFocus}
        aria-describedby={help}
        onChange={(e) => {
          if (e.target.value === ADD) setAdding(true);
          else props.onChange(e.target.value);
        }}
      >
        {!required && <option value="">{t("lists.not_set")}</option>}
        {required && value === "" && <option value="" />}
        {values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
        {extra !== null && <option value={extra}>{found ? t("lists.not_offered", { value: extra }) : extra}</option>}
        {found && <option value={ADD}>{t("lists.add_option")}</option>}
      </select>
      {props.note && (
        <span id={help} className="hint">
          {props.note}
        </span>
      )}
      {adding && found && (
        <div className="inline-field list-add">
          <label className="sr" htmlFor={`${id}-new`}>
            {t("lists.add_to", { list: found.label })}
          </label>
          <input
            id={`${id}-new`}
            type="text"
            value={text}
            autoFocus
            autoComplete="off"
            placeholder={t("lists.add_placeholder")}
            aria-describedby={problem ? `${id}-problem` : undefined}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              // The form around this field must neither send nor close because of these keys.
              if (e.key === "Enter") {
                e.preventDefault();
                void add();
              } else if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                stop();
              }
            }}
          />
          <button type="button" className="btn primary" disabled={!text.trim() || busy} onClick={() => void add()}>
            {t("lists.add")}
          </button>
          <button type="button" className="btn quiet" onClick={stop}>
            {t("action.cancel")}
          </button>
        </div>
      )}
      {problem && (
        <p className="problem-note" id={`${id}-problem`} role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
