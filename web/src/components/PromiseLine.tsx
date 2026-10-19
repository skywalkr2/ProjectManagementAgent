// The choices of a promise that is past its date with nothing heard since (design 6.33, 7.7). The one that fits comes
// first: Followed up for a promise someone else owes (a nudge: it stays open), Done for the person's own; the others are
// in the row's menu: New date, Done, Drop. Each is the action's own route, so each records what it always did.
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { useDropAction } from "./DropAction";
import { useNoted } from "./NoteBox";
import { NewDate, useCorrectPromise } from "./PromiseWhy";
import type { MenuAction } from "./RowMenu";

type Line = S["QueueLineView"];

export interface PromiseChoices {
  primary: { label: string; run: () => void } | null;
  menu: MenuAction[];
  /** The form a choice opened (a new date, a reason for dropping), shown under the row. */
  form: ReactNode;
}

/** The choices for a promise line; for any other kind of line it holds nothing. The hook is always called, so a row can
 * be any kind. `onClosed` runs when a form goes, so the row can take the cursor back. */
export function usePromiseChoices(line: Line, onClosed?: () => void): PromiseChoices {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const [dating, setDating] = useState(false);
  const action = line.kind === "promise" ? ((line.actions ?? [])[0] ?? "") : "";
  const drop = useDropAction({ id: action }, onClosed);
  const correct = useCorrectPromise(action);
  const found = useQuery({ queryKey: ["promise", action], queryFn: () => api.promise(action), enabled: dating && !!action });
  if (line.kind !== "promise" || !action) return { primary: null, menu: [], form: null };

  const person = line.person ?? null;
  const first = (line.person_name ?? "").split(/\s+/)[0] ?? "";
  const done = () =>
    act(
      () => api.actionStatus(action, "done"),
      (result) => ({
        message: noted(t("toast.action_done"), result.request),
        undo: () => api.actionStatus(action, "open"),
      }),
    );
  const followedUp = () =>
    act(
      () => api.followedUp(person ?? "", action),
      (result) => ({
        message: noted(t("toast.followed_up", { name: first }), result.request),
        undo: () => api.unfollow(person ?? "", action, { on: result.on, previous_told: result.previous_told }),
      }),
    );
  const close = () => {
    setDating(false);
    onClosed?.();
  };
  const newDate: MenuAction = { id: "new-date", label: t("queue.promise.new_date"), run: () => setDating(true) };
  const finish: MenuAction = { id: "done", label: t("queue.promise.done"), run: () => void done() };
  const showDate = dating && !!found.data;
  const form =
    showDate || drop.form ? (
    <>
      {showDate && found.data && (
        <NewDate
          label={t("promise.new_date")}
          value={found.data.due ?? ""}
          onSave={(due) => {
            void correct({ due }, found.data.version).then((ok) => ok !== undefined && close());
          }}
          onCancel={close}
        />
      )}
      {drop.form}
    </>
    ) : null;
  return person
    ? { primary: { label: t("followups.followed_up"), run: () => void followedUp() }, menu: [newDate, finish, drop.entry], form }
    : { primary: { label: t("queue.promise.done"), run: () => void done() }, menu: [newDate, drop.entry], form };
}
