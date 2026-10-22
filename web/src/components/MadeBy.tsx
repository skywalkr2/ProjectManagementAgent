// Who made the item a Today line is about, said in the inspector (design 7.7). Suggested (waiting for the person's yes) and
// added (already applied, with Undo) read differently; the person's own items say nothing. The words are built here from
// the wording sheet and the line's data and never leave the person's own screens: they are not stored, copied or sent.
import type { QueueLine } from "../lib/today";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import { OriginLink } from "./Origin";

export function MadeBy(props: { line: QueueLine }) {
  const { t, has } = useWords();
  const made = props.line.made_by;
  if (!made || made.kind === "person") return null;
  const lead =
    made.kind === "rule"
      ? (() => {
          const named = has(`made_by.rule_name.${made.rule?.id}`) ? t(`made_by.rule_name.${made.rule?.id}`) : made.rule?.label;
          return named ? t(`made_by.${made.state}.rule`, { rule: named }) : t(`made_by.${made.state}.rule_unnamed`);
        })()
      : t(`made_by.${made.state}.assistant`);
  const answered = made.answered;
  const what = answered?.on ? day(answered.on) : "";
  const outcome = answered
    ? answered.how === "kept"
      ? t("made_by.kept", { day: what })
      : answered.how === "dropped"
        ? t("made_by.dropped", { day: what })
        : answered.answer
          ? t("made_by.answered_with", { day: what, answer: answered.answer })
          : t("made_by.answered", { day: what })
    : made.state === "suggested"
      ? t("made_by.no_answer")
      : null;
  const origin = made.source?.origin;
  return (
    <div className="made-by hint" data-made-by="">
      <p>
        {lead}
        {made.inferred && <> · {t("made_by.worked_out")}</>}
        {outcome && <> · {outcome}</>}
      </p>
      {origin && <OriginLink origin={origin} label={t("made_by.from", { source: made.source?.title || t("origin.link") })} />}
    </div>
  );
}
