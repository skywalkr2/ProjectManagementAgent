// Editing a to-do from its row (design 7.5): "Edit…" opens its words and its due date (the cursor in the words) and
// saves only what changed, as the person's own edit with Undo. A new date drops the words the old one was read from, as
// correcting a promise's date does.
import { useId, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

type Target = Pick<S["OpenActionView"], "id" | "version" | "text" | "due">;

export function useEditAction(action: Target, onClosed?: () => void): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(action.text);
  const [due, setDue] = useState(action.due ?? "");
  const close = () => {
    setOpen(false);
    onClosed?.();
  };
  const start = () => {
    setText(action.text);
    setDue(action.due ?? "");
    setOpen(true);
  };
  const words = text.trim();
  const fields: Record<string, unknown> = {};
  if (words && words !== action.text) fields.text = words;
  if (due !== (action.due ?? "")) Object.assign(fields, { due: due || null, due_words: null, due_check: false });
  const save = async () => {
    if (!words || Object.keys(fields).length === 0) return;
    const done = await act(
      () => api.editRecord({ kind: "action", id: action.id, fields, read_version: action.version }),
      (result) => ({ message: t("open.edit.saved"), undo: () => api.undo(result.changeset) }),
    );
    if (done) close();
  };
  const entry: MenuAction = { id: "edit-action", label: t("open.edit"), run: start };
  const form = open ? (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onKeyDown={(e) => e.key === "Escape" && close()}
    >
      <label className="hint" htmlFor={`${id}-text`}>
        {t("open.edit.text")}
      </label>
      <input id={`${id}-text`} type="text" autoFocus value={text} onChange={(e) => setText(e.target.value)} />
      <label className="hint" htmlFor={`${id}-due`}>
        {t("open.edit.due")}
      </label>
      <input id={`${id}-due`} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={close}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!words || Object.keys(fields).length === 0}>
          {t("open.edit.save")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, form };
}
