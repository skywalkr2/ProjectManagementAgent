// An action on hold waits for something outside the person's control and is never due, overdue or chased. "Put on hold"
// asks what it waits for (the first field has the cursor) and acts at once with Undo; "Take off hold" does too.
import { useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

/** The row menu's entry for an action, and the small form it opens to ask what the action waits for. */
export function useHold(action: { id: string; on_hold?: string | null }): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [asking, setAsking] = useState(false);
  const [what, setWhat] = useState("");
  const put = async () => {
    const waiting = what.trim();
    if (!waiting) return;
    const done = await act(
      () => api.putOnHold(action.id, waiting),
      (result) => ({
        message: t("toast.put_on_hold", { what: waiting }),
        undo: () => api.restoreHold(action.id, result.previous ?? null),
      }),
    );
    if (done) {
      setAsking(false);
      setWhat("");
    }
  };
  const release = () =>
    void act(
      () => api.takeOffHold(action.id),
      (result) => ({ message: t("toast.taken_off_hold"), undo: () => api.restoreHold(action.id, result.previous ?? null) }),
    );
  const entry: MenuAction = action.on_hold
    ? { id: "take-off-hold", label: t("hold.take_off"), run: release }
    : { id: "put-on-hold", label: t("hold.put"), run: () => setAsking(true) };
  const form = asking ? (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        void put();
      }}
    >
      <label className="hint" htmlFor={`hold-${action.id}`}>
        {t("hold.label")}
      </label>
      <input
        id={`hold-${action.id}`}
        type="text"
        autoFocus
        value={what}
        onChange={(e) => setWhat(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setAsking(false);
        }}
      />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={() => setAsking(false)}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!what.trim()}>
          {t("hold.put")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, form };
}

/** "On hold: what it waits for", with the date it was due before it went on hold in its tooltip. */
export function HoldPill(props: { what: string; due?: string | null }) {
  const { t } = useWords();
  return (
    <span className="pill k-held" title={props.due ? t("hold.was_due", { date: day(props.due) }) : undefined}>
      {t("hold.pill", { what: props.what })}
    </span>
  );
}
