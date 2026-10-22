// What the capacity line opens (design 6.32): the to-dos the rules propose to move out of today, each with Move to the next
// working day and a day to pick. Moving is the person's own change of the to-do's date: it acts at once with Undo, and
// nothing is ever scheduled for them. A to-do not moved stays where it is.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { durationWords } from "../lib/duration";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";

type Move = S["CapacityMoveView"];

function MoveRow(props: { move: Move; nextDay: string }) {
  const { t, tn } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const id = useId();
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState("");
  const { move } = props;
  const to = async (when: string) => {
    const done = await act(
      () => api.editRecord({ kind: "action", id: move.action, fields: { due: when, due_words: null, due_check: false }, read_version: move.version }),
      (result) => ({
        message: t("capacity.moved", { text: move.text, date: day(when) }),
        undo: () => api.undo(result.changeset),
      }),
    );
    if (done) void client.invalidateQueries({ queryKey: ["capacity"] });
  };
  const state = move.due_state === "overdue" ? t("capacity.state.overdue") : move.due_state === "today" ? t("capacity.state.today") : "";
  return (
    <li data-capacity-move={move.action}>
      <div className="title">{move.text}</div>
      <p className="hint">{[durationWords(move.minutes, tn), move.promised ? t("capacity.promised") : "", state].filter(Boolean).join(" · ")}</p>
      <div className="row-end">
        <Button size="sm" variant="primary" onClick={() => void to(props.nextDay)}>
          {t("capacity.move_to", { date: day(props.nextDay) })}
        </Button>
        {!picking && (
          <Button size="sm" onClick={() => setPicking(true)}>
            {t("capacity.pick")}
          </Button>
        )}
      </div>
      {picking && (
        <form
          className="answer-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (picked) void to(picked);
          }}
        >
          <label className="hint" htmlFor={`${id}-day`}>
            {t("capacity.pick_label")}
          </label>
          <input id={`${id}-day`} type="date" autoFocus value={picked} onChange={(e) => setPicked(e.target.value)} />
          <div className="row-end">
            <Button size="sm" onClick={() => setPicking(false)}>
              {t("action.cancel")}
            </Button>
            <Button size="sm" variant="primary" type="submit" disabled={!picked}>
              {t("capacity.pick_move")}
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

export function CapacityDetail() {
  const { t, tn } = useWords();
  const found = useQuery({ queryKey: ["capacity"], queryFn: api.capacity });
  if (found.isPending) return <Skeleton />;
  const view = found.data;
  if (!view || view.fits || !view.next_day) return <p className="hint">{t("capacity.fits")}</p>;
  return (
    <>
      <p className="hint">{t("capacity.summary", { needed: durationWords(view.needed_minutes, tn), free: durationWords(view.free_minutes, tn) })}</p>
      {(view.moves ?? []).length > 0 && (
        <ul className="children">
          {(view.moves ?? []).map((move) => (
            <MoveRow key={move.action} move={move} nextDay={view.next_day ?? ""} />
          ))}
        </ul>
      )}
      {view.still_over > 0 && <p className="hint">{t("capacity.still_over", { time: durationWords(view.still_over, tn) })}</p>}
    </>
  );
}
