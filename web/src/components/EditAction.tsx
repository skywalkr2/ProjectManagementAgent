// Editing a to-do from its row (design 7.5): "Edit…" opens its words, its due date and how it repeats (the cursor in the
// words) and saves only what changed, as the person's own edit with Undo. A new date drops the words the old one was
// read from, as correcting a promise's date does. The repeat is typed in words and said back under the field before it is
// kept (design 6.32); words that aren't clear keep nothing.
import { useId, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { saidRepeat, useRepeatCheck } from "../lib/repeat";
import { useWords } from "../lib/wording";
import { EffortField } from "./EffortField";
import type { MenuAction } from "./RowMenu";

type Target = Pick<S["OpenActionView"], "id" | "version" | "text" | "due" | "repeat" | "effort_minutes">;

export function useEditAction(action: Target, onClosed?: () => void): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(action.text);
  const [due, setDue] = useState(action.due ?? "");
  const [repeat, setRepeat] = useState(action.repeat?.phrase ?? "");
  const [effort, setEffort] = useState<number | null>(action.effort_minutes ?? null);
  const close = () => {
    setOpen(false);
    onClosed?.();
  };
  const start = () => {
    setText(action.text);
    setDue(action.due ?? "");
    setRepeat(action.repeat?.phrase ?? "");
    setEffort(action.effort_minutes ?? null);
    setOpen(true);
  };
  const words = text.trim();
  const fields: Record<string, unknown> = {};
  if (words && words !== action.text) fields.text = words;
  if (due !== (action.due ?? "")) Object.assign(fields, { due: due || null, due_words: null, due_check: false });
  if (effort !== (action.effort_minutes ?? null)) fields.effort_minutes = effort;
  const typed = repeat.trim();
  const repeatChanged = typed !== (action.repeat?.phrase ?? "");
  const read = useRepeatCheck(repeatChanged ? typed : "", due || null);
  // A new repeat is kept only when its words are read; clearing the field stops it.
  const repeatOk = !repeatChanged || typed === "" || read?.status === "ok";
  const changed = Object.keys(fields).length > 0 || repeatChanged;
  const save = async () => {
    if (!words || !changed || !repeatOk) return;
    const done = await act(
      async () => {
        const made: string[] = [];
        if (Object.keys(fields).length > 0) {
          made.push((await api.editRecord({ kind: "action", id: action.id, fields, read_version: action.version })).changeset);
        }
        if (repeatChanged) {
          const result = typed ? await api.setRepeat(action.id, { phrase: typed, ...(due ? { start: due } : {}) }) : await api.stopRepeat(action.id);
          made.push(result.changeset);
        }
        return made;
      },
      (made) => ({
        message: Object.keys(fields).length === 0 ? t(typed ? "repeat.saved" : "repeat.stopped") : t("open.edit.saved"),
        undo: async () => {
          for (const changeset of [...made].reverse()) await api.undo(changeset);
        },
      }),
    );
    if (done) close();
  };
  const sayBack = !repeatChanged
    ? action.repeat && saidRepeat(t, action.repeat.shape, action.repeat.start)
    : read?.status === "ok" && read.shape && read.start
      ? saidRepeat(t, read.shape, read.start)
      : null;
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
      <EffortField id={id} value={effort} onChange={setEffort} />
      <label className="hint" htmlFor={`${id}-repeat`}>
        {t("repeat.label")}
      </label>
      <input
        id={`${id}-repeat`}
        type="text"
        value={repeat}
        placeholder={t("repeat.placeholder")}
        aria-describedby={`${id}-said`}
        onChange={(e) => setRepeat(e.target.value)}
      />
      <p className="hint" id={`${id}-said`} aria-live="polite">
        {sayBack}
        {repeatChanged && read?.status === "unclear" && t("repeat.unclear")}
        {repeatChanged && read?.status === "off_start" && read.start && (
          <>
            {t("repeat.off_start", { date: day(due), first: day(read.start) })}{" "}
            <button type="button" className="btn quiet" onClick={() => setDue(read.start ?? "")}>
              {t("repeat.use_first", { first: day(read.start) })}
            </button>
          </>
        )}
      </p>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={close}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!words || !changed || !repeatOk}>
          {t("open.edit.save")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, form };
}
