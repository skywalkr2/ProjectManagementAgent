// What a follow-up message leaves out (design 7.5, the UI designer's answer 36): the things that went in the same first
// message and have been answered or done since. They are lines in the list above the box, each saying so, so the person
// sees why the message is shorter than the list they sent.
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";

export function NudgeLeftOut(props: { items: S["LeftOutView"][] | undefined }) {
  const { t } = useWords();
  return (
    <>
      {(props.items ?? []).map((item) => (
        <li key={`${item.kind}:${item.id}`} data-left-out="">
          <span className="title">{item.text}</span>
          <span className="meta">{t(item.kind === "question" ? "followups.nudge.left_out_answered" : "followups.nudge.left_out_done", { date: day(item.on) })}</span>
        </li>
      ))}
    </>
  );
}
