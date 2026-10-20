// The answers to a held item, one set for every place that asks it: Today's line and the card of the change (the inspector)
// use these, so the words and the signals are the same wherever the person answers (design 7.6). The first answer applies
// the held change; the other leaves things as they were and records one correction the assistant learns from; each says
// what it did in a toast with Undo.
import { api, type S } from "./api";
import { useAct } from "./act";
import { endingWho, heldAnswers, heldTitle } from "./queue-words";
import { useWords } from "./wording";

export interface HeldAnswers {
  title: string;
  primary: { label: string; run: () => void };
  /** The second visible button; the words that only said "closed" have three answers, so the others sit in the menu. */
  other?: { label: string; run: () => void };
  /** The answers that are not beside the first: "No longer needed" and "Not yet" for the words that only said "closed". */
  menu: Array<{ id: string; label: string; run: () => void }>;
}

export function useHeldAnswers(changeset: string, index: number, held: S["HeldAsk"] | null | undefined): HeldAnswers | null {
  const { t } = useWords();
  const act = useAct();
  if (!held) return null;
  const cs = changeset;
  const words = heldAnswers(held, t);
  const release = () =>
    void act(
      () => api.release(cs, index),
      () => ({ message: t("queue.held.done", { what: held.item }), undo: () => api.undo(cs, [index]) }),
    );
  const decline = () =>
    void act(
      () => api.declineOp(cs, index),
      () => ({ message: t("queue.held.kept", { what: held.item }), undo: () => api.undeclineOp(cs, index) }),
    );
  if (held.ask === "ending") {
    const answer = (ending: "done" | "called_off") =>
      void act(
        () => api.endingAnswer(cs, index, ending),
        () => ({
          message: t(ending === "done" ? "queue.held.ending_done" : "queue.held.ending_off", { what: held.item, who: endingWho(held, t) }),
          undo: () => api.undo(cs, [index]),
        }),
      );
    return {
      title: heldTitle(held, t),
      primary: { label: words.primary, run: () => answer("done") },
      menu: [
        { id: "called-off", label: t("queue.held.e.ending_off"), run: () => answer("called_off") },
        { id: "not-yet", label: words.other, run: decline },
      ],
    };
  }
  return { title: heldTitle(held, t), primary: { label: words.primary, run: release }, other: { label: words.other, run: decline }, menu: [] };
}
