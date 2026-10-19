// The walkthrough's first result (design 7.8): once a mailbox is connected and an AI account is chosen, it offers to look
// back over the person's own mail with what that costs shown first; after their Go it lists a handful of the open promises
// found and has one follow-up ready to copy, through the Follow-ups screen's own route. With nothing found it says so and
// offers "Missed one". The server says where it stands; nothing here keeps anything.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useEstimate } from "../lib/money";
import { useToasts } from "../lib/toasts";
import type { Screen } from "../lib/walkthrough";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { costWords } from "./LookBack";
import { useMissedOne } from "./MissedOne";

type Result = S["FirstPromisesView"];

/** The first-result screen's body. `go` moves the walkthrough to another screen (to finish what the first result needs). */
export function FirstPromises(props: { go: (screen: Screen) => void }) {
  const { t } = useWords();
  const result = useQuery({
    queryKey: ["first-promises"],
    queryFn: api.firstPromises,
    // Reading and working end by themselves; the live stream refreshes it too, so this only covers a missed update.
    refetchInterval: (query) => (["reading", "working"].includes(query.state.data?.stage ?? "") ? 3000 : false),
  });
  const data = result.data;
  if (!data) return result.isError ? <p className="empty">{t("welcome.failed")}</p> : <Skeleton />;
  switch (data.stage) {
    case "no_ai":
      return <Needs text={t("walkthrough.promises.no_ai")} label={t("walkthrough.promises.to_ai")} run={() => props.go("ai")} />;
    case "no_mail":
      return <Needs text={t("walkthrough.promises.no_mail")} label={t("walkthrough.promises.to_mail")} run={() => props.go("mail")} />;
    case "reading":
      return (
        <p role="status" data-first-promises="reading">
          {t("walkthrough.promises.reading")}
        </p>
      );
    case "offer":
      return <Offer data={data} />;
    case "working":
      return (
        <p role="status" data-first-promises="working">
          {t("walkthrough.promises.working", { finished: data.finished, count: data.count })}
        </p>
      );
    default:
      return <Found data={data} />;
  }
}

function Needs(props: { text: string; label: string; run: () => void }) {
  return (
    <div className="field" data-first-promises="needs">
      <p>{props.text}</p>
      <div className="row-end">
        <Button onClick={props.run}>{props.label}</Button>
      </div>
    </div>
  );
}

/** The look back, offered with its estimate before anything is read: one total and one Go. */
function Offer(props: { data: Result }) {
  const { t, tn } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const [busy, setBusy] = useState(false);
  const { data } = props;
  const title = data.days == null ? t("walkthrough.promises.offer.title_any") : tn("walkthrough.promises.offer.title", data.days);
  const go = async () => {
    setBusy(true);
    await act(() => api.firstPromisesGo());
    setBusy(false);
  };
  return (
    <div className="field" data-first-promises="offer">
      <h3 id="first-promises-offer">{title}</h3>
      <p role="status">{tn("walkthrough.promises.offer.found", data.count, { cost: costWords(data, estimate, t) })}</p>
      <div className="row-end">
        <Button variant="primary" loading={busy} onClick={() => void go()}>
          {t("walkthrough.promises.go")}
        </Button>
      </div>
    </div>
  );
}

/** What was found: the promises, one follow-up ready to copy, or the plain empty case with "Missed one". */
function Found(props: { data: Result }) {
  const { t, tn } = useWords();
  const missed = useMissedOne();
  const { data } = props;
  if (data.promises.length === 0) {
    return (
      <div className="field" data-first-promises="none">
        <p>{t("walkthrough.promises.none")}</p>
        <p className="hint">{t("walkthrough.promises.none_hint")}</p>
        <div className="row-end">
          <Button onClick={missed}>{t("missed.open")}</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="field" data-first-promises="found">
      <h3 id="first-promises-list">{t("walkthrough.promises.found")}</h3>
      <ul className="plain-list" aria-labelledby="first-promises-list">
        {data.promises.map((p) => (
          <li key={p.action} data-promise={p.action}>
            <span className="title">{p.text}</span>
            <span className="meta">{p.mine ? t("walkthrough.promises.mine") : t("walkthrough.promises.owner", { owner: p.owner })}</span>
            {p.promised_to.length > 0 && <span className="meta">{t("walkthrough.promises.to", { names: p.promised_to.join(", ") })}</span>}
            {p.due && <span className="meta">{t("walkthrough.promises.due", { date: day(p.due) })}</span>}
            {p.quote && <span className="meta">{t("walkthrough.promises.quote", { quote: p.quote })}</span>}
          </li>
        ))}
      </ul>
      {data.more > 0 && <p className="hint">{tn("walkthrough.promises.more", data.more)}</p>}
      {data.follow_up && <FollowUpReady followUp={data.follow_up} />}
    </div>
  );
}

/** The follow-up the Follow-ups screen composes: Copy puts it on the clipboard, then Mark sent keeps it as copied. */
function FollowUpReady(props: { followUp: NonNullable<Result["follow_up"]> }) {
  const { t } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const [copied, setCopied] = useState(false);
  const [sent, setSent] = useState(false);
  const [text, setText] = useState(props.followUp.message);
  const { person, name } = props.followUp;
  const copy = async () => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setCopied(false);
      push({ message: t("toast.copy_blocked") });
      return;
    }
    setCopied(true);
    push({ message: t("toast.copied") });
  };
  const markSent = async () => {
    if (!text.trim()) return;
    const done = await act(
      () => api.markSent(person, text),
      (counts) => ({
        message: t("toast.marked_sent", { name }),
        undo: () => api.unmarkSent(person, { question_ids: counts.question_ids, action_ids: counts.action_ids }),
      }),
    );
    if (done) {
      setSent(true);
      setCopied(false);
    }
  };
  return (
    <section className="field" data-follow-up={person} aria-labelledby="first-promises-follow-up">
      <h3 id="first-promises-follow-up">{t("walkthrough.promises.follow_up")}</h3>
      <p className="hint">{t("walkthrough.promises.follow_up_to", { name })}</p>
      <label htmlFor="first-promises-message">{t("walkthrough.promises.follow_up_text", { name })}</label>
      <textarea id="first-promises-message" className="msg" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row-end">
        <Button variant="primary" disabled={sent} onClick={() => void (copied ? markSent() : copy())}>
          {copied ? t("followups.mark_sent") : t("followups.copy_message")}
        </Button>
      </div>
    </section>
  );
}
