// Asking the assistant (design 6.25): a box for a question, and under it the recent questions with what came of them.
// An answer shows the words it rests on. A suggested setting is applied by the person with one click (and Undo, from
// the read-back toast); a drafted report is theirs to copy and send.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { Heading } from "react-aria-components";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText } from "../lib/dates";
import { mailText, mailtoLink, tooLongForLink } from "../lib/mail";
import { problemText } from "../lib/problem";
import { formatValue, labelOf } from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { ModalPanel } from "./ModalPanel";
import { SafeText } from "./SafeText";

type AskItem = S["AskView"];
const SHOWN = 10;

export function Ask(props: { onClose: () => void; initial?: string; feedbackTo?: string | null }) {
  const { t } = useWords();
  const act = useAct();
  const base = useId();
  const field = useRef<HTMLTextAreaElement>(null);
  const [question, setQuestion] = useState(props.initial ?? "");
  const [busy, setBusy] = useState(false);
  const asks = useQuery({ queryKey: ["asks"], queryFn: api.asks });

  const submit = async () => {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    const asked = await act(
      () => api.ask(text),
      () => ({ message: t("ask.toast.asked") }),
    );
    setBusy(false);
    if (asked) {
      setQuestion("");
      field.current?.focus();
    }
  };

  const titleId = `${base}-title`;
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("ask.title")}
      </Heading>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="field">
          <label htmlFor={`${base}-question`}>{t("ask.question")}</label>
          <textarea
            id={`${base}-question`}
            ref={field}
            className="short"
            autoFocus
            value={question}
            aria-describedby={`${base}-hint`}
            placeholder={t("ask.placeholder")}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              // Enter asks; Shift+Enter starts a new line.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <span id={`${base}-hint`} className="hint">
            {t("ask.hint")}
          </span>
        </div>
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onClose}>
            {t("action.close")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || !question.trim()}>
            {t(busy ? "ask.sending" : "ask.go")}
          </button>
        </div>
      </form>
      <section aria-labelledby={`${base}-recent`} className="asks">
        <h3 id={`${base}-recent`} className="what">
          {t("ask.recent")}
        </h3>
        {asks.isPending ? (
          <p className="hint" role="status">
            {t("loading")}
          </p>
        ) : asks.isError ? (
          <p className="hint">
            {t("ask.load_failed")}{" "}
            <button type="button" className="btn" onClick={() => void asks.refetch()}>
              {t("action.try_again")}
            </button>
          </p>
        ) : asks.data.length === 0 ? (
          <p className="hint">{t("ask.empty")}</p>
        ) : (
          <ul className="queue">
            {asks.data.slice(0, SHOWN).map((item) => (
              <AskRow key={item.id} item={item} onApplied={props.onClose} mailTo={props.feedbackTo} />
            ))}
          </ul>
        )}
      </section>
    </ModalPanel>
  );
}

const PILL: Record<string, string> = {
  queued: "k-wait",
  running: "k-wait",
  review: "k-review",
  done: "k-send",
  needs_you: "k-held",
  failed: "k-risk",
};

function AskRow(props: { item: AskItem; onApplied: () => void; mailTo?: string | null }) {
  const { t } = useWords();
  const { item } = props;
  const titleId = `ask-${item.id}`;
  const state = item.answer && (item.state === "review" || item.state === "done") ? "done" : item.state;
  const answered = state === "done";
  const when = whenText(item.created_at);
  const proposals = item.proposals ?? [];
  const reports = item.reports ?? [];
  return (
    <li className="line" aria-labelledby={titleId}>
      <div className="row single">
        <div className="text">
          <strong id={titleId}>{item.question}</strong>
          <span className="sub">
            <span className={`kind ${PILL[state] ?? "k-review"}`}>{t(`ask.state.${state}`)}</span>
            {!answered && item.waiting ? ` ${item.waiting}` : ""}
            {when ? ` · ${when}` : ""}
          </span>
        </div>
      </div>
      {(item.answer || proposals.length > 0 || reports.length > 0) && (
        <div className="body">
          {item.answer && (
            <div className="ask-answer">
              <SafeText text={item.answer.text} />
              {item.answer.cites.length > 0 && (
                <div className="because">
                  <span className="what">{t("ask.based_on")}</span>
                  <ul className="plain-list">
                    {item.answer.cites.map((cite, i) => (
                      <li key={i}>
                        <SafeText text={`“${cite.quote}”`} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {proposals.map((p) => (
            <Proposal key={p.id} proposal={p} onApplied={props.onApplied} />
          ))}
          {reports.map((r) => (
            <Report key={r.id} report={r} mailTo={props.mailTo} />
          ))}
        </div>
      )}
    </li>
  );
}

function Proposal(props: { proposal: S["SettingProposalView"]; onApplied: () => void }) {
  const { t, has } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const { proposal: p } = props;
  const open = p.status === "open";
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: open });
  const item = settings.data?.items.find((i) => i.key === p.key);
  const label = item ? labelOf(item, t, has) : has(`settings.key.${p.key}`) ? t(`settings.key.${p.key}`) : p.key;

  const apply = async () => {
    setBusy(true);
    setProblem("");
    try {
      // The fingerprint of the settings as they are now, so a change made meanwhile is noticed rather than overwritten.
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await api.applyProposal(p.id, { fingerprint: current.fingerprint, read_version: p.version });
      await afterSave(saved);
      // The dialog closes so the read-back's Undo can be reached from the keyboard.
      props.onApplied();
    } catch (err) {
      setProblem(problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  const notNow = () =>
    void act(
      () => api.dismissProposal(p.id, p.version),
      () => ({ message: t("ask.toast.not_now") }),
    );

  return (
    <div className="ask-item">
      <span className="what">{t("ask.suggestion")}</span>
      <strong>{t("ask.suggestion_line", { label, value: formatValue(p.value, t) })}</strong>
      {p.why && <span className="sub">{p.why}</span>}
      {open ? (
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            aria-label={t("ask.apply_named", { label })}
            onClick={() => void apply()}
          >
            {t("ask.apply")}
          </button>
          <button type="button" className="btn quiet" disabled={busy} aria-label={t("ask.not_now_named", { label })} onClick={notNow}>
            {t("ask.not_now")}
          </button>
        </div>
      ) : (
        <span className="sub">{t(`ask.proposal.${p.status}`)}</span>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

function Report(props: { report: S["ReportView"]; mailTo?: string | null }) {
  const { t } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const { report: r } = props;
  const draft = r.status === "draft";

  // Set once the person has copied the report or opened it in their mail program.
  const [shared, setShared] = useState(false);
  const mail = mailtoLink(props.mailTo, r.title, r.text);
  const tooLong = tooLongForLink(props.mailTo, r.title, r.text);

  // Copying only puts the report on the clipboard; the person sends it outside the app, then marks it sent.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(mailText(r.title, r.text));
    } catch {
      push({ message: t("ask.copy_blocked") });
      return;
    }
    setShared(true);
    push({ message: t("ask.toast.copied") });
  };
  const markSent = () =>
    void act(
      () => api.reportSent(r.id, r.version),
      () => ({ message: t("ask.toast.report_sent") }),
    );
  const setAside = () =>
    void act(
      () => api.dismissReport(r.id, r.version),
      () => ({ message: t("ask.toast.set_aside") }),
    );

  const copyButton = (style: "primary" | "quiet", label: string) => (
    <button key="copy" type="button" className={`btn ${style}`} aria-label={t("ask.copy_named", { title: r.title })} onClick={() => void copy()}>
      {t(label)}
    </button>
  );
  const markSentButton = (style: "primary" | "quiet") => (
    <button key="sent" type="button" className={`btn ${style}`} aria-label={t("ask.mark_sent_named", { title: r.title })} onClick={markSent}>
      {t("ask.mark_sent")}
    </button>
  );
  // Opening the mail program counts as sharing it, as copying does: the person sends it there, then marks it sent.
  const mailLink = (style: "primary" | "quiet") =>
    mail && (
      <a key="mail" className={`btn ${style}`} href={mail} aria-label={t("ask.mail_named", { title: r.title })} onClick={() => setShared(true)}>
        {t("ask.mail")}
      </a>
    );

  return (
    <div className="ask-item">
      <span className="what">{t("ask.report")}</span>
      <strong>{r.title}</strong>
      <SafeText text={r.text} />
      {draft ? (
        <>
          <span className="hint">{t("ask.report_hint")}</span>
          {tooLong && <span className="hint">{t("ask.report_too_long")}</span>}
          <div className="acts">
            {/* Keyed, so the control the person just used keeps its place (and the focus) when the order changes. */}
            {shared
              ? [markSentButton("primary"), mailLink("quiet"), copyButton("quiet", "ask.copy_again")]
              : [mail ? mailLink("primary") : copyButton("primary", "ask.copy"), mail && copyButton("quiet", "ask.copy"), markSentButton("quiet")]}
            <button type="button" className="btn quiet" aria-label={t("ask.set_aside_named", { title: r.title })} onClick={setAside}>
              {t("ask.set_aside")}
            </button>
          </div>
        </>
      ) : (
        <span className="sub">{t(`ask.report_status.${r.status}`)}</span>
      )}
    </div>
  );
}
