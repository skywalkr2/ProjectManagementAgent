// A message the person copied that no sent message has matched (design 6.35, 7.7): one Today line, "Did your message to
// Ana go out?", with Yes, another way as its one button and Not sent and Still to send in the row's menu. Each is the
// person's own answer with Undo. The line is there only while a sent folder is being read.
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

type Line = S["QueueLineView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** The words of the line: who the message was for. */
export function sentCheckTitle(line: Line, t: T): string {
  return t("queue.sent_check.title", { name: line.person_name ?? t("queue.title.someone") });
}

export interface SentCheckChoices {
  primary: { label: string; run: () => void } | null;
  menu: MenuAction[];
}

/** The choices for a sent_check line; for any other kind of line it holds nothing. The hook is always called, so a row can
 * be any kind. */
export function useSentCheckChoices(line: Line): SentCheckChoices {
  const { t } = useWords();
  const act = useAct();
  const copy = line.kind === "sent_check" ? (line.sent_copy ?? "") : "";
  if (!copy) return { primary: null, menu: [] };
  const answer = (how: S["CopyAnswer"]["how"], toast: string) =>
    void act(
      () => api.settleCopy(copy, how),
      (undo) => ({ message: t(toast), undo: () => api.unsettleCopy(copy, undo) }),
    );
  return {
    primary: { label: t("queue.sent_check.another_way"), run: () => answer("sent_another_way", "queue.sent_check.settled_toast") },
    menu: [
      { id: "not-sent", label: t("queue.sent_check.not_sent"), run: () => answer("not_sent", "queue.sent_check.not_sent_toast") },
      { id: "still-to-send", label: t("queue.sent_check.still_to_send"), run: () => answer("still_to_send", "queue.sent_check.later_toast") },
    ],
  };
}
