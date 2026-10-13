// Follow-ups by person (design 7.5): the PM first (decisions and their own actions), then everyone A to Z, each with
// one clean message to copy, then mark sent. The message can be edited where it is shown; what is marked sent is the box's text.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import { showRow, useReveal } from "../lib/reveal";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { AskChooser } from "./AskChooser";
import { RowMenu, type MenuAction } from "./RowMenu";
import { useAddOwnRequest } from "./HandIn";
import { SafeLink, SafeText } from "./SafeText";
import { Skeleton } from "../ui/Skeleton";

type Filter = "send" | "waiting";
const FILTERS: Filter[] = ["send", "waiting"];

const toSendQuestions = (s: S["FollowupSection"]) => s.questions.filter((q) => q.status === "open");
const toSendActions = (s: S["FollowupSection"]) => s.actions.filter((a) => a.told === null);
const waitingQuestions = (s: S["FollowupSection"]) => s.questions.filter((q) => q.status === "sent");
const waitingActions = (s: S["FollowupSection"]) => s.actions.filter((a) => a.told !== null);

/** `compact` is for a narrow column on Today: headings sit one level down, and the PM's own actions are left to the to-do list beside it. */
export function FollowUps(props: { compact?: boolean }) {
  const { t } = useWords();
  const compact = !!props.compact;
  const Heading = compact ? "h3" : "h1";
  const [filter, setFilter] = useState<Filter>("send");
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  // A Today line asking for a question to be answered: the PM's own questions show under "to send", so the row is there.
  const [revealed, setRevealed] = useState<{ id: string; n: number } | null>(null);
  const latest = useRef(followups.data);
  latest.current = followups.data;
  useReveal("question", (question) => {
    if (!latest.current?.some((s) => s.is_pm && s.questions.some((q) => q.id === question))) return false;
    setFilter("send");
    setRevealed({ id: question, n: Date.now() });
    return true;
  });
  const sections = (followups.data ?? []).filter((s) => s.questions.length || (s.actions.length && !(compact && s.is_pm)));
  const shown = sections.filter((s) =>
    filter === "send" ? s.is_pm || s.to_send > 0 : !s.is_pm && waitingQuestions(s).length + waitingActions(s).length > 0,
  );
  return (
    <section className={compact ? "panel-section compact" : "panel-section"} aria-labelledby="followups-title">
      <div className="heading">
        <Heading id="followups-title">{t("followups.title")}</Heading>
        <div className="filters" role="group" aria-label={t("followups.filter")}>
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`followups.filter.${f}`)}
            </button>
          ))}
        </div>
      </div>
      {followups.isPending ? (
        <Skeleton />
      ) : followups.isError ? (
        <p className="empty">
          {t("followups.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void followups.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : sections.length === 0 ? (
        <p className="empty">{t("followups.empty")}</p>
      ) : shown.length === 0 ? (
        <p className="empty">{t(filter === "send" ? "followups.empty_send" : "followups.empty_waiting")}</p>
      ) : (
        <ol className="queue">
          {shown.map((s) =>
            s.is_pm ? (
              <YourSection key={s.person} section={s} compact={compact} reveal={revealed} />
            ) : filter === "send" ? (
              <PersonSection key={s.person} section={s} />
            ) : (
              <WaitingSection key={s.person} section={s} compact={compact} />
            ),
          )}
        </ol>
      )}
    </section>
  );
}

function YourSection(props: { section: S["FollowupSection"]; compact: boolean; reveal: { id: string; n: number } | null }) {
  const { t, tn } = useWords();
  const s = props.section;
  const actions = props.compact ? [] : s.actions;
  const Heading = props.compact ? "h4" : "h3";
  return (
    <li className="line">
      <div className="row single">
        <div className="text">
          <Heading className="name">{t("followups.you")}</Heading>
          <span className="sub">
            {[s.questions.length ? tn("followups.decisions", s.questions.length) : "", actions.length ? tn("followups.your_actions", actions.length) : ""]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      </div>
      <div className="body">
        {s.questions.length > 0 && (
          <ul className="children">
            {s.questions.map((q) => (
              <DecisionRow key={q.id} question={q} reveal={props.reveal?.id === q.id ? props.reveal.n : 0} />
            ))}
          </ul>
        )}
        {actions.length > 0 && (
          <ul className="children">
            {actions.map((a) => (
              <OwnActionRow key={a.id} action={a} />
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

function DecisionRow(props: { question: S["FollowupQuestion"]; reveal: number }) {
  const { t } = useWords();
  const act = useAct();
  const q = props.question;
  const ref = useRef<HTMLLIElement>(null);
  const [answer, setAnswer] = useState("");
  const who = q.about === "owner" || q.about === "held-op";
  useEffect(() => {
    if (props.reveal) showRow(ref.current, true);
  }, [props.reveal]);
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
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

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
  const [copied, setCopied] = useState(false);
  const message = draft ?? s.message;
  const questions = toSendQuestions(s);
  const actions = toSendActions(s);

  const edit = () => {
    setOpen(true);
    window.setTimeout(() => area.current?.focus(), 0);
  };

  // Two deliberate steps. Copy only puts the text on the clipboard; nothing changes on the server. Once it has copied, the
  // card offers Mark sent, which records the box's text as sent (with Undo). The row menu always offers Mark sent, for
  // after a reload or a message sent some other way. If the browser blocks the copy, the text is selected for a manual copy.
  const copy = async () => {
    if (!message.trim()) return;
    try {
      await navigator.clipboard.writeText(message);
    } catch {
      setCopied(false);
      setOpen(true);
      window.setTimeout(() => {
        area.current?.focus();
        area.current?.select();
      }, 0);
      push({ message: t("toast.copy_blocked") });
      return;
    }
    setCopied(true);
    push({ message: t("toast.copied") });
  };

  const markSent = async () => {
    if (!message.trim()) return;
    const result = await act(
      () => api.markSent(s.person, message),
      (counts) => ({
        message: t("toast.marked_sent", { name: s.name }),
        undo: () => api.unmarkSent(s.person, { question_ids: counts.question_ids, action_ids: counts.action_ids }),
      }),
    );
    if (result) {
      setDraft(null);
      setCopied(false);
    }
  };

  const primary = () => void (copied ? markSent() : copy());
  const menu: MenuAction[] = [
    { id: "edit", label: t("followups.edit"), run: edit },
    { id: "mark-sent", label: t("followups.mark_sent"), run: () => void markSent() },
  ];
  useRowKeys(ref, {
    toggle: () => setOpen((v) => !v),
    primary,
    copy: () => void copy(),
    edit,
  });

  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={`p-${s.person}`}>
      <div className="row pair">
        <button type="button" className="expander text" aria-expanded={open} onClick={() => setOpen(!open)}>
          <strong id={`p-${s.person}`}>{s.name}</strong>
          <span className="sub">{tn("followups.to_send", s.to_send)}</span>
        </button>
        <div className="acts">
          <button type="button" className="btn primary" onClick={primary}>
            {copied ? t("followups.mark_sent") : tn("followups.copy", s.to_send)}
          </button>
          <RowMenu label={s.name} actions={menu} />
        </div>
      </div>
      {open && (
        <div className="body">
          <div className="what" id={`in-${s.person}`}>
            {t("followups.in_message")}
          </div>
          <ul className="plain-list" aria-labelledby={`in-${s.person}`}>
            {questions.map((q) => (
              <li key={q.id}>
                <span className="title">{q.title}</span>
              </li>
            ))}
            {actions.map((a) => (
              <li key={a.id}>
                <span className="title">{a.text}</span>
                {actionMeta(a, t) && <span className="meta">{actionMeta(a, t)}</span>}
              </li>
            ))}
          </ul>
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
              <button type="button" className="btn primary" onClick={primary}>
                {copied ? t("followups.mark_sent") : t("followups.copy_message")}
              </button>
            </div>
          </div>
        </div>
      )}
    </li>
  );
}

// What each person has already been sent or told, one line each, with the step that closes it.
function WaitingSection(props: { section: S["FollowupSection"]; compact: boolean }) {
  const { tn } = useWords();
  const s = props.section;
  const Heading = props.compact ? "h4" : "h3";
  const questions = waitingQuestions(s);
  const actions = waitingActions(s);
  return (
    <li className="line" aria-labelledby={`w-${s.person}`}>
      <div className="row single">
        <div className="text">
          <Heading className="name" id={`w-${s.person}`}>
            {s.name}
          </Heading>
          <span className="sub">{tn("followups.waiting_count", questions.length + actions.length)}</span>
        </div>
      </div>
      <div className="body">
        <ul className="children">
          {questions.map((q) => (
            <WaitingQuestion key={q.id} question={q} person={s.name} />
          ))}
          {actions.map((a) => (
            <WaitingAction key={a.id} action={a} person={s.person} name={s.name} />
          ))}
        </ul>
      </div>
    </li>
  );
}

function sentLine(date: string | null, days: number | null, project: string, tn: Tn, t: T): string {
  const when = !date ? "" : !days ? t("followups.sent_today") : tn("followups.sent_on", days, { date: day(date) });
  return [project, when].filter(Boolean).join(" · ");
}

function WaitingQuestion(props: { question: S["FollowupQuestion"]; person: string }) {
  const { t, tn } = useWords();
  const act = useAct();
  const addOwn = useAddOwnRequest();
  const q = props.question;
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState("");
  const first = props.person.split(" ")[0];
  const submit = async () => {
    const handed = await act(
      () => api.reply(q.id, text),
      () => ({ message: t("toast.reply_handed_in", { name: first }) }),
    );
    if (handed) {
      addOwn(handed.request);
      setText("");
      setReplying(false);
    }
  };
  const meta = sentLine(q.sent, q.waiting_days, "", tn, t);
  return (
    <li className="child">
      <div>
        <div className="title">{q.title}</div>
        {meta && <div className="meta">{meta}</div>}
      </div>
      <div className="acts">
        {!replying && (
          <button type="button" className="btn" onClick={() => setReplying(true)}>
            {t("followups.record_reply")}
          </button>
        )}
      </div>
      {replying && (
        <form
          className="answer-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label className="hint" htmlFor={`reply-${q.id}`}>
            {t("followups.reply_label", { name: first })}
          </label>
          <textarea
            id={`reply-${q.id}`}
            className="short"
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setReplying(false);
            }}
          />
          <div className="row-end">
            <button type="button" className="btn quiet" onClick={() => setReplying(false)}>
              {t("action.cancel")}
            </button>
            <button type="submit" className="btn primary" disabled={!text.trim()}>
              {t("followups.reply_go")}
            </button>
          </div>
        </form>
      )}
    </li>
  );
}

// A waiting action's one primary is Followed up once it has waited past the nudge threshold, and They finished it before
// then; the other is in the row's menu. A chase keeps the action open and counts as told again.
function WaitingAction(props: { action: S["FollowupAction"]; person: string; name: string }) {
  const { t, tn } = useWords();
  const act = useAct();
  const a = props.action;
  const first = props.name.split(" ")[0];
  const finished = () =>
    act(
      () => api.theyFinished(props.person, a.id),
      () => ({ message: t("toast.they_finished", { name: first }), undo: () => api.actionStatus(a.id, "open") }),
    );
  const followedUp = () =>
    act(
      () => api.followedUp(props.person, a.id),
      (done) => ({
        message: t("toast.followed_up", { name: first }),
        undo: () => api.unfollow(props.person, a.id, { on: done.on, previous_told: done.previous_told }),
      }),
    );
  const chase = a.chase_due;
  const meta = a.followed_up
    ? [a.project_name, t("followups.followed_up_on", { date: day(a.followed_up) })].filter(Boolean).join(" · ")
    : sentLine(a.told, a.told_days, a.project_name, tn, t);
  const finish: MenuAction = { id: "finished", label: t("followups.they_finished"), run: () => void finished() };
  const chased: MenuAction = { id: "followed-up", label: t("followups.followed_up"), run: () => void followedUp() };
  return (
    <li className="child">
      <div>
        <div className="title">{a.text}</div>
        {meta && <div className="meta">{meta}</div>}
      </div>
      <div className="acts">
        <button type="button" className="btn primary" onClick={() => void (chase ? followedUp() : finished())}>
          {t(chase ? "followups.followed_up" : "followups.they_finished")}
        </button>
        <RowMenu label={a.text} actions={[chase ? finish : chased]} />
      </div>
    </li>
  );
}
