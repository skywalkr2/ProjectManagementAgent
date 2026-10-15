// Dropping an action that is no longer needed (design 6.8): the row menu's "Drop" asks why (the first field has the
// cursor) and acts at once with Undo. A dropped action is never done or credited, and it leaves every list.
import { useId, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

/** The row menu's "Drop" entry for an action, and the small form it opens. `onClosed` runs when the form goes, so the row
 * can take focus back. */
export function useDropAction(action: { id: string }, onClosed?: () => void): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const close = () => {
    setAsking(false);
    setReason("");
    onClosed?.();
  };
  const entry: MenuAction = { id: "drop-action", label: t("action.drop"), run: () => setAsking(true) };
  const form = asking ? (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        const why = reason.trim();
        if (!why) return;
        void act(
          () => api.dropAction(action.id, why),
          (done) => ({ message: t("toast.action_dropped"), undo: () => api.undo(done.changeset) }),
        ).then((done) => done && close());
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") close();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("action.drop_label")}
      </label>
      <input id={id} type="text" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={close}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!reason.trim()}>
          {t("action.drop_go")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, form };
}
