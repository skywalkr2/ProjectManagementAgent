// Follow-ups by person (design 7.5): the PM first (decisions and their own actions), then everyone A to Z, each with
// one clean message to copy, then mark sent. The message can be edited where it is shown; what is marked sent is the box's text.
// The same follow-ups can be shown as a table (Message | Table) and copied as one: as an HTML table for mail and chat, or as
// tab-separated cells for a spreadsheet. The table is on screen before anything is copied, and no AI run makes it.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, localDate, monthDay } from "../lib/dates";
import { tablesOf, toHtml, toTsv, type TableWords } from "../lib/followup-table";
import { useRowKeys } from "../lib/keys";
import { showRow, useReveal } from "../lib/reveal";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { AfterMoveAnswers } from "./AfterMoveAnswers";
import { AskChooser } from "./AskChooser";
import { useChangeThis, useQuestionMenu } from "./ChangeThis";
import { LearnedLines } from "./Learned";
import { useDropAction } from "./DropAction";
import { HoldNote, useHold } from "./OnHold";
import { useHoldFor, useSendNow } from "./HoldFor";
import { NoteBox, useNoted } from "./NoteBox";
import { NudgeLeftOut } from "./NudgeLeftOut";
import { OriginLink } from "./Origin";
import { RowMenu, type MenuAction } from "./RowMenu";
import { useAddOwnRequest } from "./HandIn";
import { SafeLink, SafeText } from "./SafeText";
import { Button } from "../ui/Button";
import { SegmentedControl } from "../ui/SegmentedControl";
import { Skeleton } from "../ui/Skeleton";
import { FollowUpTables, tableBar, tableHint } from "./FollowUpTable";

type Filter = "send" | "later" | "waiting";
const FILTERS: Filter[] = ["send", "later", "waiting"];

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
  // A link to a person's group (a to-do that waits on them): the filter that shows them is chosen, and their group is looked at.
  const [seeking, setSeeking] = useState<{ id: string; n: number } | null>(null);
  useReveal("person", (person) => {
    const found = latest.current?.find((s) => !s.is_pm && s.person === person);
    if (!found) return false;
    setFilter(waitingQuestions(found).length + waitingActions(found).length > 0 ? "waiting" : "send");
    setSeeking({ id: person, n: Date.now() });
    return true;
  });
  useEffect(() => {
    if (!seeking) return;
    const group = document.getElementById(`w-${seeking.id}`) ?? document.getElementById(`p-${seeking.id}`);
    const row = group?.closest<HTMLElement>("li");
    if (row) {
      showRow(row);
      setSeeking(null);
    }
  }, [seeking, filter, followups.data]);
  const sections = (followups.data ?? []).filter(
    (s) => s.questions.length || (s.later ?? []).length || (s.actions.length && !(compact && s.is_pm)),
  );
  const shown = sections.filter((s) =>
    filter === "send"
      ? s.is_pm || s.to_send > 0
      : filter === "later"
        ? (s.later ?? []).length > 0
        : !s.is_pm && waitingQuestions(s).length + waitingActions(s).length > 0,
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
        <p className="empty">{t(`followups.empty_${filter}`)}</p>
      ) : (
        <ol className="queue">
          {shown.map((s) =>
            filter === "later" ? (
              <LaterSection key={s.person} section={s} />
            ) : s.is_pm ? (
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
  const decisions = s.questions.filter((q) => q.kind === "decision").length;
  const asked = s.questions.length - decisions;
  return (
    <li className="line">
      <div className="row single">
        <div className="text">
          <Heading className="name">{t("followups.you")}</Heading>
          <span className="sub">
            {[
              decisions ? tn("followups.decisions", decisions) : "",
              asked ? tn("followups.questions", asked) : "",
              actions.length ? tn("followups.your_actions", actions.length) : "",
            ]
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

/** A question the person is asked. After a move, `check` gives it its own two answers in place of the answer form; `move` is
 * what it came after. */
export function DecisionRow(props: { question: S["FollowupQuestion"]; reveal: number; check?: S["AfterMoveCheck"] | null; move?: S["AfterMove"] | null }) {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const q = props.question;
  const ref = useRef<HTMLLIElement>(null);
  const [answer, setAnswer] = useState("");
  const who = q.about === "owner" || q.about === "held-op";
  const back = () => ref.current?.focus();
  const menu = useQuestionMenu(q, { canMarkSent: false, onClosed: back });
  const change = useChangeThis({ kind: q.kind === "decision" ? "decision" : "question", id: q.id }, back);
  useEffect(() => {
    if (props.reveal) showRow(ref.current, true);
  }, [props.reveal]);
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="what">{t(who ? "followups.who_question" : q.kind === "decision" ? "followups.decision" : "followups.question")}</div>
        <div className="title">{q.title}</div>
        {q.text && <SafeText text={q.text} />}
        {q.links.map((l) => (
          <div key={l.url}>
            <SafeLink label={l.label} url={l.url} />
          </div>
        ))}
        <OriginLink origin={q.origin} />
      </div>
      <div className="acts">
        <RowMenu label={q.title} actions={[...menu.entries, change.entry]} />
      </div>
      {menu.form}
      {change.form}
      <LearnedLines records={[q.id]} />
      <div className="full">
        {who ? (
          <AskChooser ask={{ id: q.id, about: q.about ?? "other", options: q.options, name: null }} />
        ) : props.check ? (
          <AfterMoveAnswers question={q} check={props.check} move={props.move} />
        ) : (
          <form
            className="answer-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                () => api.answer(q.id, { text: answer }),
                (done) => ({ message: noted(t("toast.answered"), done.request) }),
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
  const noted = useNoted();
  const a = props.action;
  const ref = useRef<HTMLLIElement>(null);
  const hold = useHold(a);
  const [noting, setNoting] = useState(false);
  const change = useChangeThis({ kind: "action", id: a.id }, () => ref.current?.focus());
  const drop = useDropAction(a, () => ref.current?.focus());
  const done = (note?: string) =>
    act(
      () => api.actionStatus(a.id, "done", note),
      (result) => ({ message: noted(t("toast.action_done"), result.request), undo: () => api.actionStatus(a.id, "open") }),
    );
  useRowKeys(ref, { primary: () => void done() });
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="title">
          {a.text}
          <HoldNote on_hold={a.on_hold} blocker={a.blocker} due={a.due} />
        </div>
        <div className="meta">{actionMeta(a, t)}</div>
        <OriginLink origin={a.origin} />
      </div>
      <div className="acts">
        <button type="button" className="btn primary" onClick={() => void done()}>
          {t("followups.mark_done")}
        </button>
        <RowMenu label={a.text} actions={[{ id: "note", label: t("note.add"), run: () => setNoting(true) }, hold.entry, change.entry, drop.entry]} />
      </div>
      {noting && (
        <NoteBox
          sends={[{ label: t("followups.mark_done"), run: done }]}
          onClose={() => {
            setNoting(false);
            ref.current?.focus();
          }}
        />
      )}
      {hold.form}
      {change.form}
      {drop.form}
      <LearnedLines records={[a.id]} />
    </li>
  );
}

type T = (key: string, vars?: Record<string, string | number>) => string;
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

function actionMeta(a: S["FollowupAction"], t: T): string {
  return [a.project_name, a.due ? t("op.meta.due", { date: day(a.due) }) : ""].filter(Boolean).join(" · ");
}

/** One person's message to send. `open` shows the message box from the start (the Today inspector). */
export function PersonSection(props: { section: S["FollowupSection"]; open?: boolean }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const s = props.section;
  const ref = useRef<HTMLLIElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(!!props.open);
  const [draft, setDraft] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [view, setView] = useState<"message" | "table">("message");
  const message = draft ?? s.message;
  const questions = toSendQuestions(s);
  const actions = toSendActions(s);

  const edit = () => {
    setView("message");
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

  // The table is what the message holds, in rows: its words come from the sheet and nothing is added to it.
  const words: TableWords = {
    project: t("followups.table.project"),
    action: t("followups.table.action"),
    question: t("followups.table.question"),
    due: t("followups.table.due"),
    asked: t("followups.table.asked"),
    link: t("followups.table.link"),
    update: t("followups.table.update"),
    answer: t("followups.table.answer"),
    notSent: t("followups.table.not_sent"),
    noLink: t("followups.table.no_link"),
    overdue: (date) => t("followups.table.overdue", { date }),
    due_day: day,
    asked_day: monthDay,
  };
  const tables = tablesOf(s, words, localDate(new Date()));
  const preview = useRef<HTMLDivElement>(null);
  // If the browser won't copy, the table on screen is selected so the person can copy it by hand.
  const blocked = () => {
    setCopied(false);
    const shown = preview.current;
    if (shown) {
      const range = document.createRange();
      range.selectNodeContents(shown);
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
    }
    push({ message: t("toast.copy_blocked") });
  };
  /** Copies the table as HTML (with the tab-separated cells as its plain text), for mail and chat. */
  const copyTable = async () => {
    if (!tables.length) return;
    try {
      if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) throw new Error("no rich copy");
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([toHtml(tables, words)], { type: "text/html" }),
          "text/plain": new Blob([toTsv(tables, words)], { type: "text/plain" }),
        }),
      ]);
    } catch {
      blocked();
      return;
    }
    setCopied(true);
    push({ message: t("toast.copied_table") });
  };
  /** Copies the table as tab-separated cells with full web addresses, for a spreadsheet. */
  const copySheet = async () => {
    if (!tables.length) return;
    try {
      await navigator.clipboard.writeText(toTsv(tables, words));
    } catch {
      blocked();
      return;
    }
    setCopied(true);
    push({ message: t("toast.copied_sheet") });
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

  // Copy never reaches the clipboard unless the message it copies is on screen: on a closed card it opens the message
  // (with the cursor in it) and the next Copy is the one that copies.
  const copyShown = () => void (!open ? edit() : view === "table" ? copyTable() : copy());
  const primary = () => void (copied ? markSent() : copyShown());
  const hold = useHoldFor(questions);
  const menu: MenuAction[] = [
    { id: "edit", label: t("followups.edit"), run: edit },
    ...(questions.length > 0 ? [hold.entry] : []),
    { id: "mark-sent", label: t("followups.mark_sent"), run: () => void markSent() },
  ];
  useRowKeys(ref, {
    toggle: () => setOpen((v) => !v),
    primary,
    copy: copyShown,
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
      {hold.form}
      {open && (
        <div className="body">
          <SegmentedControl
            label={t("followups.view")}
            value={view}
            onChange={setView}
            options={[
              { value: "message", label: t("followups.view.message") },
              { value: "table", label: t("followups.view.table") },
            ]}
          />
          {view === "table" ? (
            <>
              <div ref={preview}>
                <FollowUpTables tables={tables} name={s.name} noLink={words.noLink} />
              </div>
              <div className={tableBar}>
                <Button variant="primary" disabled={!tables.length} onClick={() => void copyTable()}>
                  {t("followups.copy_table")}
                </Button>
                <Button disabled={!tables.length} onClick={() => void copySheet()}>
                  {t("followups.copy_sheet")}
                </Button>
                <p className={tableHint}>{t("followups.copy_table_hint")}</p>
                <Button variant={copied ? "primary" : "secondary"} onClick={() => void markSent()}>
                  {t("followups.mark_sent")}
                </Button>
              </div>
            </>
          ) : (
            <>
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
                <textarea id={`msg-${s.person}`} className="msg" ref={area} value={message} onChange={(e) => setDraft(e.target.value)} />
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
            </>
          )}
        </div>
      )}
    </li>
  );
}

// Questions held for a meeting or a day, per person: out of To send until that day, with the way to send one now.
function LaterSection(props: { section: S["FollowupSection"] }) {
  const { tn } = useWords();
  const s = props.section;
  const later = s.later ?? [];
  return (
    <li className="line" aria-labelledby={`l-${s.person}`}>
      <div className="row pair">
        <div className="text">
          <strong id={`l-${s.person}`}>{s.name}</strong>
          <span className="sub">{tn("followups.later_count", later.length)}</span>
        </div>
      </div>
      <div className="body">
        <ul className="plain-list" aria-labelledby={`l-${s.person}`}>
          {later.map((q) => (
            <LaterQuestion key={q.id} question={q} />
          ))}
        </ul>
      </div>
    </li>
  );
}

function LaterQuestion(props: { question: S["FollowupQuestion"] }) {
  const { t } = useWords();
  const q = props.question;
  const sendNow = useSendNow(q);
  const when = q.held_until ? day(q.held_until) : "";
  return (
    <li>
      <span className="title">{q.title}</span>
      <span className="meta">
        {q.held_for_name ? t("followups.later_for", { meeting: q.held_for_name, date: when }) : t("followups.later_until", { date: when })}
      </span>
      <RowMenu label={q.title} actions={[sendNow]} />
    </li>
  );
}

// What each person has already been sent or told, one line each, with the step that closes it.
export function WaitingSection(props: { section: S["FollowupSection"]; compact: boolean; nudgeOpen?: boolean }) {
  const { tn } = useWords();
  const s = props.section;
  const Heading = props.compact ? "h4" : "h3";
  const questions = waitingQuestions(s);
  const actions = waitingActions(s);
  return (
    <li className="line" tabIndex={-1} aria-labelledby={`w-${s.person}`}>
      <div className="row single">
        <div className="text">
          <Heading className="name" id={`w-${s.person}`}>
            {s.name}
          </Heading>
          <span className="sub">{tn("followups.waiting_count", questions.length + actions.length)}</span>
        </div>
      </div>
      <div className="body">
        {s.nudge && <NudgeCard section={s} nudge={s.nudge} start={!!props.nudgeOpen} />}
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

/** The drafted follow-up to one person, from a template with no AI run: what it lists, the message to edit, then Copy and
 * Mark sent, as for every message. Marking it sent records a chase on each item and starts the wait again; what the
 * message listed was first asked stays on each item. */
function NudgeCard(props: { section: S["FollowupSection"]; nudge: S["NudgeView"]; start: boolean }) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const { push } = useToasts();
  const s = props.section;
  const { nudge } = props;
  const [open, setOpen] = useState(props.start);
  const [focusBox, setFocusBox] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const text = draft ?? nudge.text;
  const today = localDate(new Date());
  const questions = s.questions.filter((q) => nudge.question_ids.includes(q.id));
  const actions = s.actions.filter((a) => nudge.action_ids.includes(a.id));
  const first = s.name.split(" ")[0];
  const round = has(`followups.nudge.round.${nudge.round}`) ? t(`followups.nudge.round.${nudge.round}`) : t("followups.nudge.round_n", { n: nudge.round });
  const copy = async () => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setCopied(false);
      area.current?.focus();
      area.current?.select();
      push({ message: t("toast.copy_blocked") });
      return;
    }
    setCopied(true);
    push({ message: t("toast.copied") });
  };
  const markSent = async () => {
    if (!text.trim()) return;
    const done = await act(
      () => api.nudgeSent(s.person, { text, question_ids: nudge.question_ids, action_ids: nudge.action_ids }),
      (result) => ({
        message: t("toast.followed_up", { name: first }),
        undo: () =>
          api.nudgeUnsent(s.person, {
            question_ids: result.question_ids,
            action_ids: result.action_ids,
            on: result.on,
            previous_told: result.previous_told,
            signal_at: result.signal_at ?? null,
          }),
      }),
    );
    if (done) {
      setDraft(null);
      setCopied(false);
      setOpen(false);
    }
  };
  if (!open)
    return (
      <div className="nudge-start">
        <button
          type="button"
          className="btn primary"
          onClick={() => {
            setFocusBox(true);
            setOpen(true);
          }}
        >
          {t("followups.nudge.draft")}
        </button>
      </div>
    );
  return (
    <div className="nudge" data-nudge="">
      <div className="what" id={`nudge-${s.person}`}>
        {t("followups.in_message")}
      </div>
      <ul className="plain-list" aria-labelledby={`nudge-${s.person}`}>
        {questions.map((q) => (
          <li key={q.id}>
            <span className="title">{q.title}</span>
            <span className="meta">
              {[
                q.sent ? t("followups.nudge.first_asked", { date: day(q.sent) }) : "",
                q.followed_up ? t("followups.followed_up_on", { date: day(q.followed_up) }) : "",
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </li>
        ))}
        {actions.map((a) => (
          <li key={a.id}>
            <span className="title">{a.text}</span>
            <span className="meta">
              {[
                a.due ? t(a.due < today ? "followups.nudge.overdue" : "op.meta.due", { date: day(a.due) }) : "",
                a.told ? tn("followups.sent_on", a.told_days ?? 0, { date: day(a.told) }) : "",
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </li>
        ))}
        <NudgeLeftOut items={nudge.left_out} />
      </ul>
      <div className="message">
        <label className="hint" htmlFor={`nudge-msg-${s.person}`}>
          {t("followups.message_label", { name: s.name })}
        </label>
        <textarea
          id={`nudge-msg-${s.person}`}
          className="msg"
          ref={area}
          autoFocus={focusBox}
          value={text}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="row-end">
          <span className="hint">{round}</span>
          {draft !== null && (
            <button type="button" className="btn quiet" onClick={() => setDraft(null)}>
              {t("followups.reset")}
            </button>
          )}
          {!copied && (
            <button type="button" className="btn quiet" onClick={() => void markSent()}>
              {t("followups.mark_sent")}
            </button>
          )}
          <button type="button" className="btn primary" onClick={() => void (copied ? markSent() : copy())}>
            {copied ? t("followups.mark_sent") : t("followups.nudge.copy")}
          </button>
        </div>
      </div>
    </div>
  );
}

function sentLine(date: string | null, days: number | null, project: string, tn: Tn, t: T): string {
  const when = !date ? "" : !days ? t("followups.sent_today") : tn("followups.sent_on", days, { date: day(date) });
  return [project, when].filter(Boolean).join(" · ");
}

/** "waiting 5 days", in the warning color and with "follow up" added once the follow-up rule says it is time. */
function WaitingPill(props: { days: number | null; chase: boolean }) {
  const { tn } = useWords();
  if (props.days === null) return null;
  return (
    <span className={props.chase ? "pill k-risk" : "pill k-wait"}>
      {props.chase ? tn("followups.waiting_pill.chase", props.days) : tn("followups.waiting_pill", props.days)}
    </span>
  );
}

function WaitingQuestion(props: { question: S["FollowupQuestion"]; person: string }) {
  const { t, tn } = useWords();
  const act = useAct();
  const addOwn = useAddOwnRequest();
  const q = props.question;
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState("");
  const row = useRef<HTMLLIElement>(null);
  const menu = useQuestionMenu(q, { canMarkSent: false, onClosed: () => row.current?.focus() });
  const change = useChangeThis({ kind: "question", id: q.id }, () => row.current?.focus());
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
    <li className="child" ref={row} tabIndex={-1}>
      <div>
        <div className="title">
          {q.title}
          <WaitingPill days={q.waiting_days} chase={!!q.chase_due} />
        </div>
        {meta && <div className="meta">{meta}</div>}
        <OriginLink origin={q.origin} />
      </div>
      <div className="acts">
        {!replying && (
          <button type="button" className="btn" onClick={() => setReplying(true)}>
            {t("followups.record_reply")}
          </button>
        )}
        <RowMenu label={q.title} actions={[...menu.entries, change.entry]} />
      </div>
      {menu.form}
      {change.form}
      <LearnedLines records={[q.id]} />
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
  const noted = useNoted();
  const a = props.action;
  const first = props.name.split(" ")[0];
  const ref = useRef<HTMLLIElement>(null);
  const [noting, setNoting] = useState(false);
  const finished = (note?: string) =>
    act(
      () => api.theyFinished(props.person, a.id, note),
      (result) => ({
        message: noted(t("toast.they_finished", { name: first }), result.request),
        undo: () => api.actionStatus(a.id, "open"),
      }),
    );
  const followedUp = (note?: string) =>
    act(
      () => api.followedUp(props.person, a.id, note),
      (done) => ({
        message: noted(t("toast.followed_up", { name: first }), done.request),
        undo: () => api.unfollow(props.person, a.id, { on: done.on, previous_told: done.previous_told }),
      }),
    );
  const chase = a.chase_due;
  const hold = useHold(a);
  const change = useChangeThis({ kind: "action", id: a.id }, () => ref.current?.focus());
  const drop = useDropAction(a, () => ref.current?.focus());
  const meta = a.followed_up
    ? [a.project_name, t("followups.followed_up_on", { date: day(a.followed_up) })].filter(Boolean).join(" · ")
    : sentLine(a.told, a.told_days, a.project_name, tn, t);
  const finish: MenuAction = { id: "finished", label: t("followups.they_finished"), run: () => void finished() };
  const chased: MenuAction = { id: "followed-up", label: t("followups.followed_up"), run: () => void followedUp() };
  const note: MenuAction = { id: "note", label: t("note.add"), run: () => setNoting(true) };
  // A note can go with either act; the row's main one comes first, so Enter sends that one.
  const sends = [
    { label: t("followups.they_finished"), run: finished },
    { label: t("followups.followed_up"), run: followedUp },
  ];
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="title">
          {a.text}
          {a.on_hold || a.blocker ? <HoldNote on_hold={a.on_hold} blocker={a.blocker} due={a.due} /> : <WaitingPill days={a.told_days} chase={chase} />}
        </div>
        {meta && <div className="meta">{meta}</div>}
        <OriginLink origin={a.origin} />
      </div>
      <div className="acts">
        <button type="button" className="btn primary" onClick={() => void (chase ? followedUp() : finished())}>
          {t(chase ? "followups.followed_up" : "followups.they_finished")}
        </button>
        <RowMenu label={a.text} actions={[chase ? finish : chased, note, hold.entry, change.entry, drop.entry]} />
      </div>
      {noting && (
        <NoteBox
          sends={chase ? [sends[1], sends[0]] : sends}
          onClose={() => {
            setNoting(false);
            ref.current?.focus();
          }}
        />
      )}
      {hold.form}
      {change.form}
      {drop.form}
      <LearnedLines records={[a.id]} />
    </li>
  );
}
