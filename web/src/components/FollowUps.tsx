// Follow-ups by person (design 7.5): the PM first (decisions and their own actions), then everyone A to Z, each with
// one clean message to copy. The message can be edited where it is shown; what is copied is what gets recorded.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { AskChooser } from "./AskChooser";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeLink, SafeText } from "./SafeText";

export function FollowUps() {
  const { t } = useWords();
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  const sections = (followups.data ?? []).filter((s) => s.questions.length || s.actions.length);
  return (
    <section className="panel-section" aria-labelledby="followups-title">
      <div className="heading">
        <h2 id="followups-title">{t("followups.title")}</h2>
      </div>
      {followups.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : followups.isError ? (
        <p className="empty">
          {t("followups.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void followups.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : sections.length === 0 ? (
        <p className="empty">{t("followups.empty")}</p>
      ) : (
        <ol className="queue">
          {sections.map((s) => (s.is_pm ? <YourSection key={s.person} section={s} /> : <PersonSection key={s.person} section={s} />))}
        </ol>
      )}
    </section>
  );
}

function YourSection(props: { section: S["FollowupSection"] }) {
  const { t, tn } = useWords();
  const s = props.section;
  return (
    <li className="line">
      <div className="row single">
        <div className="text">
          <h3 className="name">{t("followups.you")}</h3>
          <span className="sub">
            {[s.questions.length ? tn("followups.decisions", s.questions.length) : "", s.actions.length ? tn("followups.your_actions", s.actions.length) : ""]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      </div>
      <div className="body">
        {s.questions.length > 0 && (
          <ul className="children">
            {s.questions.map((q) => (
              <DecisionRow key={q.id} question={q} />
            ))}
          </ul>
        )}
        {s.actions.length > 0 && (
          <ul className="children">
            {s.actions.map((a) => (
              <OwnActionRow key={a.id} action={a} />
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

function DecisionRow(props: { question: S["FollowupQuestion"] }) {
  const { t } = useWords();
  const act = useAct();
  const q = props.question;
  const ref = useRef<HTMLLIElement>(null);
  const [answer, setAnswer] = useState("");
  const who = q.about === "owner" || q.about === "held-op";
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div className="full">
        <div className="what">{t(who ? "followups.who_question" : "followups.decision")}</div>
        <div className="title">{q.title}</div>
        {q.text && <SafeText text={q.text} />}
        {q.links.map((l) => (
          <div key={l.url}>
            <SafeLink label={l.label} url={l.url} />
          </div>
        ))}
      </div>
      <div className="full">
        {who ? (
          <AskChooser ask={{ id: q.id, about: q.about ?? "other", options: q.options, name: null }} />
        ) : (
          <form
            className="answer-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                () => api.answer(q.id, { text: answer }),
                () => ({ message: t("toast.answered") }),
              );
            }}
          >
            <label className="hint" htmlFor={`ans-${q.id}`}>
              {t("followups.answer_label")}
            </label>
            <textarea id={`ans-${q.id}`} className="short" value={answer} onChange={(e) => setAnswer(e.target.value)} />
            <div className="row-end">
              <button type="submit" className="btn primary" data-key="primary" disabled={!answer.trim()}>
                {t("followups.answer")}
              </button>
            </div>
          </form>
        )}
      </div>
    </li>
  );
}

function OwnActionRow(props: { action: S["FollowupAction"] }) {
  const { t } = useWords();
  const act = useAct();
  const a = props.action;
  const ref = useRef<HTMLLIElement>(null);
  const done = () =>
    act(
      () => api.actionStatus(a.id, "done"),
      () => ({ message: t("toast.action_done"), undo: () => api.actionStatus(a.id, "open") }),
    );
  useRowKeys(ref, { primary: () => void done() });
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="title">{a.text}</div>
        <div className="meta">{actionMeta(a, t)}</div>
      </div>
      <div className="acts">
        <button type="button" className="btn primary" onClick={() => void done()}>
          {t("followups.mark_done")}
        </button>
      </div>
    </li>
  );
}

type T = (key: string, vars?: Record<string, string | number>) => string;

function actionMeta(a: S["FollowupAction"], t: T): string {
  return [a.project_name, a.due ? t("op.meta.due", { date: day(a.due) }) : ""].filter(Boolean).join(" · ");
}

function PersonSection(props: { section: S["FollowupSection"] }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const s = props.section;
  const ref = useRef<HTMLLIElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [copied, setCopiedState] = useState<string | null>(() => remembered(s.person));
  const message = draft ?? s.message;
  // Once this exact message is copied, the row's next step is Mark sent; editing it again goes back to Copy.
  const isCopied = copied !== null && copied === message && s.to_send > 0;
  const waitingReplies = s.questions.filter((q) => q.status === "sent").length;

  const setCopied = (text: string | null) => {
    setCopiedState(text);
    remember(s.person, text);
  };

  const markSent = (text: string | null) =>
    act(
      () => api.markSent(s.person, text),
      (counts) => ({
        message: t("toast.marked_sent", { name: s.name }),
        undo: () => api.unmarkSent(s.person, { question_ids: counts.question_ids, action_ids: counts.action_ids }),
      }),
    ).then((result) => {
      if (result) {
        setDraft(null);
        setCopied(null);
      }
    });

  const edit = () => {
    setOpen(true);
    window.setTimeout(() => area.current?.focus(), 0);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(message);
      push({
        message: t("toast.copied", { name: s.name }),
        action: { label: t("followups.mark_sent"), run: () => markSent(message) },
      });
    } catch {
      setOpen(true);
      window.setTimeout(() => {
        area.current?.focus();
        area.current?.select();
      }, 0);
      push({ message: t("toast.copy_blocked") });
    }
  };

  const menu: MenuAction[] = [];
  if (isCopied) {
    menu.push({ id: "copyagain", label: t("followups.copy_again"), run: () => void copy() });
    menu.push({ id: "edit", label: t("followups.edit"), run: edit });
  } else if (s.to_send > 0) {
    menu.push({ id: "edit", label: t("followups.edit"), run: edit });
    menu.push({ id: "marksent", label: t("followups.mark_sent_without_copy"), run: () => void markSent(null) });
  }
  const primary = isCopied ? () => void markSent(copied) : () => void copy();
  useRowKeys(ref, {
    toggle: () => setOpen((v) => !v),
    primary: s.to_send > 0 ? primary : undefined,
    copy: s.to_send > 0 ? () => void copy() : undefined,
    edit: s.to_send > 0 ? edit : undefined,
  });

  const summary = [
    s.questions.length ? tn("followups.questions", s.questions.length) : "",
    s.actions.length ? tn("followups.actions", s.actions.length) : "",
    s.to_send ? tn("followups.to_send", s.to_send) : t("followups.nothing_new"),
    waitingReplies ? tn("followups.waiting_replies", waitingReplies) : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={`p-${s.person}`}>
      <div className="row">
        <span className={`kind ${isCopied ? "k-wait" : s.to_send ? "k-send" : "k-done"}`}>
          {t(isCopied ? "followups.copied" : s.to_send ? "followups.ready" : "followups.waiting")}
        </span>
        <button type="button" className="expander text" aria-expanded={open} onClick={() => setOpen(!open)}>
          <strong id={`p-${s.person}`}>{s.name}</strong>
          <span className="sub">{summary}</span>
        </button>
        <div className="acts">
          {s.to_send > 0 && (
            <button type="button" className="btn primary" onClick={primary}>
              {isCopied ? t("followups.mark_sent") : tn("followups.copy", s.to_send)}
            </button>
          )}
          <RowMenu label={s.name} actions={menu} />
        </div>
      </div>
      {open && (
        <div className="body">
          {s.questions.length > 0 && (
            <ul className="children" aria-label={tn("followups.questions", s.questions.length)}>
              {s.questions.map((q) => (
                <li key={q.id} className="child">
                  <div className="full">
                    <span className={`pill ${q.status === "open" ? "k-send" : "k-wait"}`}>
                      {q.status === "open"
                        ? t("followups.q.ready")
                        : tn("followups.q.waiting_days", q.waiting_days ?? 0)}
                    </span>
                    <div className="title">{q.title}</div>
                    {q.text && <SafeText text={q.text} />}
                    {q.links.map((l) => (
                      <div key={l.url}>
                        <SafeLink label={l.label} url={l.url} />
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {s.actions.length > 0 && (
            <ul className="children" aria-label={tn("followups.actions", s.actions.length)}>
              {s.actions.map((a) => (
                <li key={a.id} className="child">
                  <div className="full">
                    <span className={`pill ${a.told ? "k-done" : "k-send"}`}>
                      {a.told ? tn("followups.a.told_days", a.told_days ?? 0) : t("followups.a.to_send")}
                    </span>
                    <div className="title">{a.text}</div>
                    <div className="meta">{actionMeta(a, t)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {s.to_send > 0 && (
            <div className="message">
              <label className="hint" htmlFor={`msg-${s.person}`}>
                {t("followups.message_label", { name: s.name })}
              </label>
              <textarea
                id={`msg-${s.person}`}
                className="msg"
                ref={area}
                value={message}
                onChange={(e) => setDraft(e.target.value)}
              />
              <div className="row-end">
                <span className="hint">{t("followups.clean_copy")}</span>
                {draft !== null && (
                  <button type="button" className="btn quiet" onClick={() => setDraft(null)}>
                    {t("followups.reset")}
                  </button>
                )}
                <button type="button" className="btn primary" onClick={() => void copy()}>
                  {t("followups.copy_message")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

const COPIED_KEY = "cockpit.copied.";

/** The message last copied for a person, kept for this browser session so a refresh keeps "Mark sent" as the next step. */
function remembered(person: string): string | null {
  try {
    return window.sessionStorage.getItem(COPIED_KEY + person);
  } catch {
    return null;
  }
}

function remember(person: string, text: string | null): void {
  try {
    if (text === null) window.sessionStorage.removeItem(COPIED_KEY + person);
    else window.sessionStorage.setItem(COPIED_KEY + person, text);
  } catch {
    // storage can be unavailable (private windows); the in-page state still works
  }
}
