// "Stop repeating" in a to-do's menu (design 6.32): it acts at once with Undo. The open to-do stays as it is, and no
// next one is made when it ends.
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

/** The menu entry for a to-do that repeats; null for one that doesn't. */
export function useStopRepeat(action: { id: string; repeat?: unknown }): MenuAction | null {
  const { t } = useWords();
  const act = useAct();
  if (!action.repeat) return null;
  return {
    id: "stop-repeat",
    label: t("repeat.stop"),
    note: t("repeat.stop_note"),
    run: () =>
      void act(
        () => api.stopRepeat(action.id),
        (done) => ({ message: t("repeat.stopped"), undo: () => api.undo(done.changeset) }),
      ),
  };
}
