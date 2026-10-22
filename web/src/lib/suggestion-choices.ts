// The choices a suggestion line offers (design 6.32, Manner): each acts at once, records a signal and has Undo on its
// toast. The words a choice writes into a record (a reason for a drop, what a hold waits for) come from the sheet.
import { api, type S } from "./api";
import { useAct } from "./act";
import { useWords } from "./wording";

type Line = S["QueueLineView"];
export type Choice = "drop" | "weekly" | "hold" | "no_reply" | "leave" | "keep" | "snooze";

/** The label of a choice; a stale line covering several to-dos says "them". */
export function choiceLabel(t: (key: string) => string, choice: string, many: boolean): string {
  return t(many && (choice === "keep" || choice === "snooze") ? `queue.choice.${choice}.many` : `queue.choice.${choice}`);
}

export function useChoices(line: Line): { id: string; label: string; run: () => void }[] {
  const { t } = useWords();
  const act = useAct();
  const many = line.kind === "stale" && line.count > 1;
  // The reason a drop keeps depends on why the line was offered.
  const reason = t(line.kind === "stale" ? "queue.choice.reason.stale" : line.state === "replies" ? "queue.choice.reason.replies" : "queue.choice.reason.moved");
  return (line.choices ?? []).map((id) => ({
    id,
    label: choiceLabel(t, id, many),
    run: () =>
      void act(
        () =>
          api.chooseSuggestion({
            key: line.key,
            choice: id as Choice,
            reason,
            waiting: t("queue.choice.waiting"),
            weekly: t("queue.choice.weekly_words"),
          }),
        (done) => ({ message: t(`queue.choice.done.${id}`), undo: () => api.undoChoice(done.signal) }),
      ),
  }));
}
