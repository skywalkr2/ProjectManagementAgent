// A conversation on a record (design 6.25, 6.32): a box on a to-do, question, person, project or meeting to ask the
// assistant about it or to ask for something to be done to it. The conversation is kept on the record, oldest first. An
// answer is prose that shows the words it rests on; when it proposes changes they are listed under it, each kept or
// dropped here (an applied one is dropped with Undo, one held for the person is kept or dropped). Work above the amount
// the person asked to be asked about waits for their go, shown with its estimate.
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText } from "../lib/dates";
import { useWords } from "../lib/wording";
import { SafeText } from "./SafeText";

type Turn = S["AskView"];
type Op = S["OpView"];

/** The kinds of record a conversation can be about. */
export const CONVERSATION_KINDS: ReadonlySet<string> = new Set(["action", "question", "person", "project", "event"]);

export function RecordConversation(props: { kind: string; id: string }) {
  const { t } = useWords();
  const act = useAct();
  const base = useId();
  const field = useRef<HTMLTextAreaElement>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const talk = useQuery({
    queryKey: ["conversation", props.kind, props.id],
    queryFn: () => api.conversation(props.kind, props.id),
    // While the assistant is working on a message, look again for the answer.
    refetchInterval: (query) => (query.state.data?.turns.some((x) => x.state === "queued" || x.state === "running") ? 3000 : false),
  });

  const send = async () => {
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    const sent = await act(
      () => api.say(props.kind, props.id, text),
      () => ({ message: t("conversation.toast.sent") }),
    );
    setBusy(false);
    if (sent) {
      setMessage("");
      field.current?.focus();
    }
  };

  const turns = talk.data?.turns ?? [];
  return (
    <section aria-labelledby={`${base}-title`} className="conversation" data-conversation="">
      <h2 id={`${base}-title`} className="what">
        {t("conversation.title")}
      </h2>
      {turns.length === 0 && !talk.isPending ? <p className="hint">{t("conversation.empty")}</p> : null}
      {turns.length > 0 && (
        <ul className="queue">
          {turns.map((turn) => (
            <TurnRow key={turn.id} turn={turn} />
          ))}
        </ul>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <div className="field">
          <label htmlFor={`${base}-message`}>{t("conversation.label")}</label>
          <textarea
            id={`${base}-message`}
            ref={field}
            className="short"
            value={message}
            aria-describedby={`${base}-hint`}
            placeholder={t("conversation.placeholder")}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter starts a new line.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <span id={`${base}-hint`} className="hint">
            {t("conversation.hint")}
          </span>
        </div>
        <div className="row-end">
          <button type="submit" className="btn primary" disabled={busy || !message.trim()}>
            {t(busy ? "conversation.sending" : "conversation.send")}
          </button>
        </div>
      </form>
    </section>
  );
}

function TurnRow(props: { turn: Turn }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { turn } = props;
  const answered = turn.answer && (turn.state === "review" || turn.state === "done");
  const state = answered ? "done" : turn.state;
  const when = whenText(turn.created_at);
  const ops = turn.ops ?? [];
  const cs = turn.changeset;
  const titleId = `turn-${turn.id}`;

  const drop = (op: Op) => {
    if (!cs) return;
    void act(
      async () => (op.status === "held" ? await api.declineOp(cs, op.index) : await api.undo(cs, [op.index])),
      () => ({ message: t("conversation.toast.dropped") }),
    );
  };
  const keep = (op: Op) => {
    if (!cs) return;
    void act(
      () => api.release(cs, op.index),
      () => ({ message: t("conversation.toast.kept") }),
    );
  };
  const keepAll = () => {
    if (!cs) return;
    void act(
      () => api.looksGood(cs),
      () => ({ message: t("conversation.toast.kept_all") }),
    );
  };

  return (
    <li className="line" aria-labelledby={titleId}>
      <div className="row single">
        <div className="text">
          <strong id={titleId}>{turn.question}</strong>
          <span className="sub">
            <span className="kind k-review">{t(`ask.state.${state}`)}</span>
            {!answered && turn.waiting ? ` ${turn.waiting}` : ""}
            {when ? ` · ${when}` : ""}
          </span>
        </div>
      </div>
      <div className="body">
        {turn.waiting_for_go && (
          <div className="ask-item">
            <span className="sub">{turn.estimate_usd != null ? t("conversation.waiting_go_cost", { cost: `$${turn.estimate_usd.toFixed(2)}` }) : t("conversation.waiting_go")}</span>
            <div className="acts">
              <button type="button" className="btn primary" onClick={() => void act(() => api.stageGo(turn.id, turn.version), () => ({ message: t("toast.go") }))}>
                {t("conversation.go")}
              </button>
            </div>
          </div>
        )}
        {turn.answer && (
          <div className="ask-answer">
            <SafeText text={turn.answer.text} />
            {turn.answer.cites.length > 0 && (
              <div className="because">
                <span className="what">{t("ask.based_on")}</span>
                <ul className="plain-list">
                  {turn.answer.cites.map((cite, i) => (
                    <li key={i}>
                      <SafeText text={`“${cite.quote}”`} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {ops.length > 0 && (
          <div className="ask-item">
            <span className="what">{tn("conversation.changes", ops.length)}</span>
            <ul className="plain-list">
              {ops.map((op) => (
                <li key={op.index}>
                  <span>{op.title}</span> <span className="sub">{t(`conversation.op.${op.status}`)}</span>
                  {op.status === "held" && (
                    <button type="button" className="btn" aria-label={t("conversation.keep_named", { what: op.title })} onClick={() => keep(op)}>
                      {t("conversation.keep")}
                    </button>
                  )}
                  {(op.status === "held" || op.status === "applied") && (
                    <button type="button" className="btn quiet" aria-label={t("conversation.drop_named", { what: op.title })} onClick={() => drop(op)}>
                      {t("conversation.drop")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {!turn.reviewed && ops.some((o) => o.status === "applied") && (
              <div className="acts">
                <button type="button" className="btn" onClick={keepAll}>
                  {t("conversation.keep_all")}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
