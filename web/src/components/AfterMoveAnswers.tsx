// The answers to one question after a move (design 7.7, the UI designer's answer 27): "Move it to Oct 22" or "Keep Oct 20" for
// an action whose day the move may have touched, "It holds" or "Needs a change…" for the plan of what moved. Both are answers,
// so both are buttons. Moving the day is the person's own edit with Undo; every answer is the question's answer. When the last
// question of a group is settled, one toast says the move is.
import { useId, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { settleMove } from "../lib/moves";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { useNoted } from "./NoteBox";

export function AfterMoveAnswers(props: { question: { id: string; title: string }; check: S["AfterMoveCheck"]; move: S["AfterMove"] | null | undefined }) {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const id = useId();
  const [changing, setChanging] = useState(false);
  const [note, setNote] = useState("");
  const { check, question } = props;
  const request = props.move?.request ?? "";
  const title = props.move?.title ?? question.title;
  // The toast for an answer, or the move's own when this was the last of its group.
  const said = (message: string, answered: S["Noted"]): string => {
    if (request && settleMove(request, question.id)) return t("queue.moved.settled", { title });
    return noted(message, answered.request);
  };
  const to = check.to_day ? day(check.to_day) : "";
  const from = check.from_day ? day(check.from_day) : "";

  const move = () =>
    act(
      async () => {
        const edit = await api.editRecord({
          kind: "action",
          id: check.action!,
          fields: { due: check.to_day, due_words: null, due_check: false },
          read_version: check.version!,
        });
        const answered = await api.answer(question.id, { text: t("queue.moved.answered.moved", { date: to }) });
        return { edit, answered };
      },
      ({ edit, answered }) => ({ message: said(t("queue.moved.toast.moved", { date: to }), answered), undo: () => api.undo(edit.changeset) }),
    );
  const answer = (text: string, message: string) =>
    act(
      () => api.answer(question.id, { text }),
      (answered) => ({ message: said(message, answered) }),
    );
  const sendChange = (e: React.FormEvent) => {
    e.preventDefault();
    const words = note.trim();
    if (words) void answer(t("queue.moved.answered.change", { note: words }), t("queue.moved.toast.change"));
  };

  if (check.kind === "date") {
    return (
      <div className="row-end" role="group" aria-label={question.title} data-after-move="date">
        <Button size="sm" variant="primary" data-key="primary" onClick={() => void move()}>
          {t("queue.moved.answer.move", { date: to })}
        </Button>
        <Button size="sm" onClick={() => void answer(t("queue.moved.answered.kept", { date: from }), t("queue.moved.toast.kept", { date: from }))}>
          {t("queue.moved.answer.keep", { date: from })}
        </Button>
      </div>
    );
  }
  return (
    <div data-after-move="plan">
      {changing ? (
        <form className="answer-form" onSubmit={sendChange} onKeyDown={(e) => e.key === "Escape" && setChanging(false)}>
          <label className="hint" htmlFor={`${id}-note`}>
            {t("queue.moved.change_label")}
          </label>
          <textarea id={`${id}-note`} className="short" autoFocus value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row-end">
            <Button size="sm" variant="ghost" onClick={() => setChanging(false)}>
              {t("action.cancel")}
            </Button>
            <Button size="sm" variant="primary" type="submit" disabled={!note.trim()}>
              {t("queue.moved.change_send")}
            </Button>
          </div>
        </form>
      ) : (
        <div className="row-end" role="group" aria-label={question.title}>
          <Button size="sm" variant="primary" data-key="primary" onClick={() => void answer(t("queue.moved.answered.holds"), t("queue.moved.toast.holds"))}>
            {t("queue.moved.answer.holds")}
          </Button>
          <Button size="sm" onClick={() => setChanging(true)}>
            {t("queue.moved.answer.change")}
          </Button>
        </div>
      )}
    </div>
  );
}
