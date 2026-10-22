// Reassigning an action from its row (design 6.9, 7.5): "Reassign…" asks who (a list of people, the cursor in it) and
// acts at once with Undo. On a to-do that has several owners it first asks whose part is changing, so the others stay.
// The change is the person's own edit of the owners, so it is a correction the assistant learns from.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { ownersAfter } from "../lib/open-items";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";
import type { MenuAction } from "./RowMenu";

type Target = { id: string; version: number; owners: S["OpenActionView"]["owners"] };

/** The picker and its Undo, for a place that shows the form itself (Today's suggested escalation); the menu entry below
 * wraps it. `from` is the owner being replaced: the first one when the action has just one. */
export function ReassignForm(props: { action: Target; from?: string; onDone?: () => void; onCancel?: () => void; label?: string }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  const { action } = props;
  const [from, setFrom] = useState(props.from ?? (action.owners.length === 1 ? action.owners[0].person : ""));
  useEffect(() => {
    box.current?.querySelector<HTMLElement>("select")?.focus();
  }, []);
  const choose = async (to: string) => {
    if (!to || !from && action.owners.length > 0) return;
    const name = people.data?.find((p) => p.id === to)?.name ?? "";
    const owners = action.owners.length === 0 ? [{ person: to }] : ownersAfter(action.owners, from, to);
    const done = await act(
      () => api.editRecord({ kind: "action", id: action.id, fields: { owners }, read_version: action.version }),
      (result) => ({ message: t("open.reassigned", { name }), undo: () => api.undo(result.changeset) }),
    );
    if (done) props.onDone?.();
  };
  return (
    <div className="answer-form" ref={box} onKeyDown={(e) => e.key === "Escape" && props.onCancel?.()}>
      {action.owners.length > 1 && !props.from && (
        <div className="field">
          <label htmlFor={`${id}-from`}>{t("open.reassign.from")}</label>
          <select id={`${id}-from`} value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value="">{t("person.choose")}</option>
            {action.owners.map((o) => (
              <option key={o.person} value={o.person}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <PersonPicker
        label={props.label ?? t("open.reassign.to")}
        value=""
        suggested={[]}
        people={(people.data ?? []).filter((p) => p.status !== "left")}
        onChange={(to) => void choose(to)}
      />
      {props.onCancel && (
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onCancel}>
            {t("action.cancel")}
          </button>
        </div>
      )}
    </div>
  );
}

/** The row menu's "Reassign…" entry, and the form it opens. `onClosed` runs when the form goes, so the row can take focus
 * back. */
export function useReassign(action: Target, onClosed?: () => void, from?: string): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const [open, setOpen] = useState(false);
  const close = () => {
    setOpen(false);
    onClosed?.();
  };
  const entry: MenuAction = { id: "reassign", label: t("open.reassign"), run: () => setOpen(true) };
  const form = open ? <ReassignForm action={action} from={from} onDone={close} onCancel={close} /> : null;
  return { entry, form };
}
