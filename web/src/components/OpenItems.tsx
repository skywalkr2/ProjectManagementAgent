// To-dos and questions (design 7.5, 6.8, 6.9): every open to-do and every open question in one place each. A to-do row
// has its owners, due date, project (and the project that holds it), where it came from, and its state; a question row
// who it waits on and since when. Both are narrowed by project, person and state, each chosen from a list. A row's one
// primary act is the likeliest next step, and the rest are in its menu: edit, reassign, merge a near-duplicate, hold,
// drop, a note to the assistant. Every act is the person's own, at once, with Undo; the server records its signal.
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { day, monthDay } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import {
  ACTION_STATES,
  QUESTION_STATES,
  actionsShown,
  questionsShown,
  takeFilters,
  type Filters,
  type OpenAction,
  type OpenQuestion,
} from "../lib/open-items";
import { revealOrKeep } from "../lib/reveal";
import { toHash } from "../lib/views";
import { useWords } from "../lib/wording";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { AskChooser } from "./AskChooser";
import { useChangeThis, useQuestionMenu } from "./ChangeThis";
import { useDropAction } from "./DropAction";
import { useEditAction } from "./EditAction";
import { NoteBox, useNoted } from "./NoteBox";
import { HoldNote, useHold } from "./OnHold";
import styles from "./OpenItems.module.css";
import { OriginLink } from "./Origin";
import { useHandToAssistant } from "./HandToAssistant";
import { useReassign } from "./ReassignAction";
import type { MenuAction } from "./RowMenu";
import { RowMenu } from "./RowMenu";

type Tab = "actions" | "questions";
type T = (key: string, vars?: Record<string, string | number>) => string;

export function OpenItems() {
  const { t, tn } = useWords();
  const items = useQuery({ queryKey: ["open-items"], queryFn: api.openItems });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [tab, setTab] = useState<Tab>("actions");
  const [filters, setFilters] = useState<Filters>(takeFilters);
  const ids = useId();
  const actions = items.data?.actions ?? [];
  const questions = items.data?.questions ?? [];

  const projectName = (id: string) => projects.data?.find((p) => p.id === id)?.name ?? actions.find((a) => a.project === id)?.project_name ?? id;
  const projectChoices = [...new Set(tab === "actions" ? actions.map((a) => a.project).filter((p): p is string => !!p) : questions.flatMap((q) => q.projects ?? []))]
    .map((id) => ({ id, name: projectName(id) }))
    .sort((a, b) => a.name.localeCompare(b.name));
  const personChoices = [
    ...new Map((tab === "actions" ? actions.flatMap((a) => a.owners.map((o) => [o.person, o.name] as const)) : questions.map((q) => [q.to, q.to_name] as const))).entries(),
  ]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
  const states: readonly string[] = tab === "actions" ? ACTION_STATES : QUESTION_STATES;

  const shownActions = actionsShown(actions, filters);
  const shownQuestions = questionsShown(questions, filters);
  const shown = tab === "actions" ? shownActions.length : shownQuestions.length;
  const set = (patch: Partial<Filters>) => setFilters((now) => ({ ...now, ...patch }));
  const choose = (next: Tab) => {
    setTab(next);
    set({ state: "" });
  };

  return (
    <section className="panel-section" aria-labelledby="open-title" data-open-items="">
      <div className="heading">
        <h1 id="open-title">{t("open.title")}</h1>
        <div className="filters" role="group" aria-label={t("open.tabs")}>
          <button type="button" aria-pressed={tab === "actions"} onClick={() => choose("actions")}>
            {t("open.tab.actions", { n: actions.length })}
          </button>
          <button type="button" aria-pressed={tab === "questions"} onClick={() => choose("questions")}>
            {t("open.tab.questions", { n: questions.length })}
          </button>
        </div>
      </div>
      {items.isPending ? (
        <Skeleton />
      ) : items.isError ? (
        <p className="empty">
          {t("open.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void items.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : actions.length + questions.length === 0 ? (
        <p className="empty">{t("open.empty")}</p>
      ) : (
        <>
          <div className={styles.bar} role="group" aria-label={t("open.filters")}>
            <Choice id={`${ids}-project`} label={t("open.filter.project")} value={filters.project} onChange={(v) => set({ project: v })} none={t("open.filter.all_projects")} options={projectChoices.map((p) => [p.id, p.name])} />
            <Choice id={`${ids}-person`} label={t("open.filter.person")} value={filters.person} onChange={(v) => set({ person: v })} none={t("person.everyone")} options={personChoices.map((p) => [p.id, p.name])} />
            <Choice id={`${ids}-state`} label={t("open.filter.state")} value={filters.state} onChange={(v) => set({ state: v })} none={t("open.filter.any_state")} options={states.map((s) => [s, t(`open.${tab === "actions" ? "state" : "qstate"}.${s}`)])} />
          </div>
          {shown === 0 ? (
            <p className="empty">{t("open.none_match")}</p>
          ) : tab === "actions" ? (
            <ul className="queue" aria-label={t("open.list.actions")}>
              {shownActions.map((a) => (
                <ActionRow key={a.id} action={a} />
              ))}
            </ul>
          ) : (
            <ul className="queue" aria-label={t("open.list.questions")}>
              {shownQuestions.map((q) => (
                <QuestionRow key={q.id} question={q} />
              ))}
            </ul>
          )}
          <p className="hint">{tn("open.count", shown)}</p>
        </>
      )}
    </section>
  );
}

function Choice(props: { id: string; label: string; value: string; onChange: (v: string) => void; none: string; options: Array<[string, string]> }) {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <select id={props.id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="">{props.none}</option>
        {props.options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** The pieces of a meta line, with a dot between them. */
function join(parts: Array<ReactNode | null | undefined | false | "">): ReactNode {
  const kept = parts.filter((p) => p !== null && p !== undefined && p !== false && p !== "");
  return kept.map((p, i) => (
    <span key={i}>
      {i > 0 && " · "}
      {p}
    </span>
  ));
}

function ProjectTag(props: { name: string; parent: string | null | undefined }) {
  const { t } = useWords();
  if (!props.name) return null;
  return <span className={styles.project}>{props.parent ? t("open.project_in", { parent: props.parent, project: props.name }) : props.name}</span>;
}

function ActionRow(props: { action: OpenAction }) {
  const { t, tn } = useWords();
  const act = useAct();
  const noted = useNoted();
  const a = props.action;
  const ref = useRef<HTMLLIElement & HTMLDivElement>(null);
  const notesId = useId();
  const focus = () => ref.current?.focus();
  const [noting, setNoting] = useState(false);
  const [asking, setAsking] = useState(false);
  const hold = useHold(a);
  const change = useChangeThis({ kind: "action", id: a.id }, focus);
  const drop = useDropAction(a, focus);
  const reassign = useReassign(a, focus);
  const hand = useHandToAssistant(a, focus);
  const edit = useEditAction(a, focus);
  const done = (note?: string) =>
    act(
      () => api.actionStatus(a.id, "done", note),
      (result) => ({ message: noted(t("toast.action_done"), result.request), undo: () => api.actionStatus(a.id, "open") }),
    );
  const twin = a.duplicate;
  const merge: MenuAction | null = twin
    ? {
        id: "merge",
        label: t("open.merge", { text: twin.text }),
        run: () =>
          void act(
            () => api.mergeActions(a.id, { other: twin.id, read_version: a.version, other_version: twin.version }),
            (result) => ({ message: t("open.merged", { text: twin.text }), undo: () => api.undo(result.changeset) }),
          ),
      }
    : null;
  const unowned = a.state === "no_owner";
  useRowKeys(ref, { primary: unowned ? () => setAsking(true) : () => void done() });
  const menu: MenuAction[] = [
    ...(unowned ? [] : [{ id: "note", label: t("note.add"), run: () => setNoting(true) } satisfies MenuAction]),
    ...(unowned ? [] : [edit.entry, reassign.entry]),
    ...(merge ? [merge] : []),
    ...(unowned || !hand.entry ? [] : [hand.entry]),
    ...(unowned ? [] : [hold.entry]),
    change.entry,
    drop.entry,
  ];
  const meta = join([
    a.owners.length > 0 ? a.owners.map((o) => o.name).join(", ") : t("open.nobody"),
    a.to_send && (
      <strong key="s" className={styles.toSend} data-to-send="">
        {t("action.to_send")}
      </strong>
    ),
    a.due && t(a.due_check ? "op.meta.due_check" : "op.meta.due", { date: day(a.due) }),
    a.project_name && <ProjectTag key="p" name={a.project_name} parent={a.parent_name} />,
    a.state === "stale" && a.untouched_days != null && tn("open.untouched", a.untouched_days),
    a.on_hold || a.blocker ? <HoldNote key="h" on_hold={a.on_hold} blocker={a.blocker} due={a.due} /> : null,
  ]);
  const title = a.notes ? (
    <span title={a.notes} aria-describedby={notesId}>
      {a.text}
      <span id={notesId} className="sr">
        {a.notes}
      </span>
    </span>
  ) : (
    a.text
  );
  return (
    <Row
      ref={ref}
      pill={pillOf(a, t)}
      title={title}
      meta={
        <>
          {meta}
          <OriginLink origin={a.origin} />
        </>
      }
      primary={
        unowned ? (
          a.owner_question ? (
            <button type="button" className="btn primary" data-key="primary" aria-expanded={asking} onClick={() => setAsking(!asking)}>
              {t("queue.act.pick_owner")}
            </button>
          ) : null
        ) : (
          <button type="button" className="btn primary" data-key="primary" onClick={() => void done()}>
            {t("followups.mark_done")}
          </button>
        )
      }
      menu={<RowMenu label={a.text} actions={menu} />}
    >
      {asking && a.owner_question && <AskChooser ask={{ id: a.owner_question, about: "owner", options: [], suggestion: null }} />}
      {noting && (
        <NoteBox
          sends={[{ label: t("followups.mark_done"), run: done }]}
          onClose={() => {
            setNoting(false);
            focus();
          }}
        />
      )}
      {edit.form}
      {reassign.form}
      {hand.form}
      {hold.form}
      {change.form}
      {drop.form}
    </Row>
  );
}

function pillOf(a: OpenAction, t: T): ReactNode {
  switch (a.state) {
    case "overdue":
      return <Pill tone="danger">{t("open.state.overdue")}</Pill>;
    case "stale":
      return <Pill tone="warn">{t("open.state.stale")}</Pill>;
    case "no_owner":
      return <Pill tone="warn">{t("open.state.no_owner")}</Pill>;
    case "on_hold":
      return <Pill tone="neutral">{t("open.state.on_hold")}</Pill>;
    default:
      return undefined;
  }
}

function QuestionRow(props: { question: OpenQuestion }) {
  const { t, tn } = useWords();
  const q = props.question;
  const ref = useRef<HTMLLIElement & HTMLDivElement>(null);
  const focus = () => ref.current?.focus();
  const menu = useQuestionMenu(q, { canMarkSent: q.state === "not_sent", onClosed: focus });
  const change = useChangeThis({ kind: q.kind === "decision" ? "decision" : "question", id: q.id }, focus);
  // The step itself is in Follow-ups, where the answer, the reply and the message are; the row takes the person to it.
  const open = () => {
    const mine = q.state === "yours";
    if (!revealOrKeep(mine ? "question" : "person", mine ? q.id : q.to)) window.location.hash = toHash("work/followups");
  };
  useRowKeys(ref, { primary: open });
  const label = { yours: "followups.answer", waiting: "followups.record_reply", not_sent: "open.q.to_send", later: "open.q.to_send" }[q.state];
  const who =
    q.state === "yours"
      ? t("open.q.on_you")
      : q.state === "waiting"
        ? t("open.q.waiting_on", { name: q.to_name })
        : q.state === "later"
          ? t("open.q.held", { name: q.to_name, date: q.held_until ? monthDay(q.held_until) : "" })
          : t("open.q.not_sent", { name: q.to_name });
  const meta = join([
    who,
    q.since && t("open.q.since", { date: monthDay(q.since) }),
    q.waiting_days != null && tn("open.q.days", q.waiting_days),
    q.chases > 0 && tn("open.q.chases", q.chases),
    q.project_name && <ProjectTag key="p" name={q.project_name} parent={null} />,
  ]);
  return (
    <Row
      ref={ref}
      pill={q.state === "waiting" || q.state === "yours" ? undefined : <Pill tone="neutral">{t(`open.qstate.${q.state}`)}</Pill>}
      title={q.title}
      meta={
        <>
          {meta}
          <OriginLink origin={q.origin} />
        </>
      }
      primary={
        <button type="button" className="btn primary" data-key="primary" onClick={open}>
          {t(label)}
        </button>
      }
      menu={<RowMenu label={q.title} actions={[...menu.entries, change.entry]} />}
    >
      {menu.form}
      {change.form}
    </Row>
  );
}
