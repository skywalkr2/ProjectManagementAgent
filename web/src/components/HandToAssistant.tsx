// Handing an action to the assistant (design 7.5): the row menu's "Hand to the assistant" asks what is wanted from the work
// (the cursor is in the field) and hands the action over; the assistant drafts the work (a message, a list, a page) as a
// pending draft, under the usual estimate and the person's go. The action stays the person's until they close it. The row
// then says where the work stands: with the assistant, waiting for the go, or a draft ready to review.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useMoney } from "../lib/money";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";
import { useTextReview } from "./TextReview";

/** The actions the assistant has in hand, by action id. A failed read is no actions: the rows simply say nothing. */
export function useHanded(): Map<string, S["HandedActionView"]> {
  const found = useQuery({ queryKey: ["handed"], queryFn: api.handed });
  return new Map((found.data ?? []).map((h) => [h.action, h]));
}

/** The line under a row that says where the handed-over work stands, with Review the draft when there is one. */
function HandedLine(props: { handed: S["HandedActionView"]; onReview: (version: string) => void }) {
  const { t } = useWords();
  const money = useMoney();
  const { handed } = props;
  if (handed.state === "draft" && handed.draft) {
    const version = handed.draft;
    return (
      <p className="hint" data-handed="draft">
        {t("work.hand.draft")}{" "}
        <button type="button" className="btn" onClick={() => props.onReview(version)}>
          {t("work.hand.review")}
        </button>
      </p>
    );
  }
  if (handed.state === "needs_go") {
    const cost = handed.estimate_usd != null ? money(handed.estimate_usd) : null;
    return (
      <p className="hint" data-handed="needs_go">
        {cost ? t("work.hand.needs_go_cost", { cost }) : t("work.hand.needs_go")}
      </p>
    );
  }
  return (
    <p className="hint" data-handed="working">
      {t("work.hand.working")}
    </p>
  );
}

/** The row menu's entry for an action (none while the assistant has its work in hand), the small form it opens, and the line
 * that says where handed-over work stands. `onClosed` runs when the form goes, so the row can take focus back. */
export function useHandToAssistant(
  action: { id: string },
  onClosed?: () => void,
): { entry: MenuAction | null; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const handed = useHanded().get(action.id);
  const review = useTextReview();
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const close = () => {
    setAsking(false);
    setNote("");
    onClosed?.();
  };
  const entry: MenuAction | null = handed ? null : { id: "hand-to-assistant", label: t("work.hand.entry"), run: () => setAsking(true) };
  const form = (
    <>
      {asking && (
        <form
          className="answer-form"
          onSubmit={(e) => {
            e.preventDefault();
            void act(
              () => api.handOver(action.id, note.trim() || undefined),
              () => ({ message: t("work.hand.toast") }),
            ).then((done) => done && close());
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") close();
          }}
        >
          <label className="hint" htmlFor={id}>
            {t("work.hand.label")}
          </label>
          <textarea id={id} className="short" autoFocus value={note} onChange={(e) => setNote(e.target.value)} />
          <p className="hint">{t("work.hand.hint")}</p>
          <div className="row-end">
            <button type="button" className="btn quiet" onClick={close}>
              {t("action.cancel")}
            </button>
            <button type="submit" className="btn primary">
              {t("work.hand.go")}
            </button>
          </div>
        </form>
      )}
      {handed && <HandedLine handed={handed} onReview={(version) => review.open(version)} />}
      {review.dialog}
    </>
  );
  return { entry, form };
}

/** A refusal's own words (the server says why an action can't be handed over), for a place that shows its own message. */
export const refusalText = (err: unknown): string => (err instanceof ApiError ? err.detail : "");
