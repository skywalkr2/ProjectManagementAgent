// What the person can do to an entry or a rule (design 7.18): each acts at once, says what happened in a toast and can be
// undone from it. The server records the signal for each; Undo goes through the change the act made.
import { api, type S } from "./api";
import { useAct } from "./act";
import { useWords } from "./wording";

/** What an act needs of an entry or rule: its id and the version that was read. */
export interface Target {
  id: string;
  version: number;
}

export function useKnowledgeActs() {
  const { t } = useWords();
  const act = useAct();
  const undo = (done: S["Applied"]) => () => api.undo(done.changeset);
  return {
    /** Keep a proposal; `body` carries wording or reach the person changed first. */
    keep: (item: Target, body: { text?: string } = {}) =>
      act(
        () => api.keepKnowledge(item.id, { read_version: item.version, ...body }),
        (done) => ({ message: t("knowledge.toast.kept"), undo: undo(done) }),
      ),
    discard: (item: Target) =>
      act(
        () => api.discardKnowledge(item.id, item.version),
        (done) => ({ message: t("knowledge.toast.discarded"), undo: undo(done) }),
      ),
    justThisTime: (item: Target) =>
      act(
        () => api.justThisTime(item.id, item.version),
        (done) => ({ message: t("knowledge.toast.just_this_time"), undo: undo(done) }),
      ),
    retire: (item: Target) =>
      act(
        () => api.retireKnowledge(item.id, item.version),
        (done) => ({ message: t("knowledge.toast.retired"), undo: undo(done) }),
      ),
    narrow: (item: Target, applies_to: S["Scope"]) =>
      act(
        () => api.narrowKnowledge(item.id, { read_version: item.version, applies_to }),
        (done) => ({ message: t("knowledge.toast.narrowed"), undo: undo(done) }),
      ),
    /** Keep a standing rule as it is in the review: its next review starts now. */
    keepRule: (item: Target) =>
      act(
        () => api.keepRule(item.id, item.version),
        (done) => ({ message: t("rules_review.kept"), undo: undo(done) }),
      ),
  };
}
