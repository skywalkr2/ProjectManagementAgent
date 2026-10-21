// A labelled choice of organization, by name. It offers the organizations on file and "Not set"; "Add an organization…"
// opens a small field that adds one at once (with Undo) and selects it. The value is the organization's id; only names show.
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { useFocusAfterRender } from "../lib/focus-after-render";

/** The choice that opens the add field; no organization id can look like it. */
const ADD = "\u0001add";

export function OrgSelect(props: {
  label: string;
  /** The chosen organization's id, or an empty text for none. */
  value: string;
  onChange: (id: string) => void;
  hint?: ReactNode;
  id?: string;
}) {
  const { t } = useWords();
  const act = useAct();
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: api.organizations });
  const own = useId();
  const id = props.id ?? own;
  const select = useRef<HTMLSelectElement>(null);
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const rows = [...(orgs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  // A choice the list no longer holds is not offered, so the select shows "Not set" rather than a stray id.
  const held = rows.some((o) => o.id === props.value) ? props.value : "";

  const focusAfterRender = useFocusAfterRender();
  const stop = () => {
    setAdding(false);
    setText("");
    focusAfterRender(() => select.current);
  };

  const add = async () => {
    const wanted = text.trim();
    if (!wanted || busy) return;
    const existing = rows.find((o) => o.name.toLocaleLowerCase() === wanted.toLocaleLowerCase());
    if (existing) {
      props.onChange(existing.id);
      stop();
      return;
    }
    setBusy(true);
    const created = await act(
      () => api.addOrganization({ name: wanted }),
      (made) => ({ message: t("toast.added", { name: wanted }), undo: () => api.removeOrganization(made.id) }),
    );
    setBusy(false);
    if (!created) return;
    props.onChange(created.id);
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
        value={held}
        onChange={(e) => {
          if (e.target.value === ADD) setAdding(true);
          else props.onChange(e.target.value);
        }}
      >
        <option value="">{t("org.not_set")}</option>
        {rows.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
        <option value={ADD}>{t("org.add_option")}</option>
      </select>
      {adding && (
        <div className="inline-field list-add">
          <label className="sr" htmlFor={`${id}-new`}>
            {t("org.add_to")}
          </label>
          <input
            id={`${id}-new`}
            type="text"
            value={text}
            autoFocus
            autoComplete="off"
            placeholder={t("org.add_placeholder")}
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
            {t("org.add")}
          </button>
          <button type="button" className="btn quiet" onClick={stop}>
            {t("action.cancel")}
          </button>
        </div>
      )}
    </div>
  );
}
