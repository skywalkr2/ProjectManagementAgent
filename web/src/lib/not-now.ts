// "Not now" on a suggestion line (design 6.32, the attention budget): the line stays off until something about it changes,
// with Undo on the toast. Only suggestions have it; what is due is never put off here.
import { api } from "./api";
import { useAct } from "./act";
import { useWords } from "./wording";

/** The kinds of Today line that are suggestions, which the engine may hold back for the brief. */
export const SUGGESTION_KINDS: ReadonlySet<string> = new Set(["escalate", "stale", "unfiled", "learned", "catch_up"]);

export function useNotNow(): (key: string) => void {
  const { t } = useWords();
  const act = useAct();
  return (key) => {
    void act(
      () => api.notNowSuggestion(key),
      (put) => ({ message: t("queue.notnow.done"), undo: () => api.undoNotNowSuggestion(put.signal) }),
    );
  };
}
