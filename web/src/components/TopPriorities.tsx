// Top priorities (design 7.7): a short ranked list across every project, in the rail. One row for each of the person's own
// things, one row for everyone else however much they hold ("Robin Sample: send 1 question, follow up on 3 waiting up to 5
// days", the items in its tooltip). The server ranks it by rules; this draws it. Its row actions are the ones the to-do
// list has: Mark done, with Reassign and Hand to the assistant in the menu.
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { chooseFilters } from "../lib/open-items";
import { revealOrKeep } from "../lib/reveal";
import type { View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill, type PillTone } from "../ui/Pill";
import { Skeleton } from "../ui/Skeleton";
import { useHandToAssistant } from "./HandToAssistant";
import { useNoted } from "./NoteBox";
import { Empty, Failed, RailPanel } from "./RailPanel";
import { useReassign } from "./ReassignAction";
import { RowMenu } from "./RowMenu";
import styles from "./Today.module.css";

type Line = S["PriorityLineView"];
type T = ReturnType<typeof useWords>["t"];
type Tn = ReturnType<typeof useWords>["tn"];

/** What a person's row says in one line: "Robin Sample: send 1 question, follow up on 3 waiting up to 5 days". */
export function personWords(line: Line, t: T, tn: Tn): string {
  const sent = (line.things ?? []).filter((x) => x.why === "send");
  const questions = sent.filter((x) => x.kind === "question").length;
  const actions = sent.filter((x) => x.kind === "action").length;
  const parts = [
    questions > 0 ? tn("today.priorities.part.send_questions", questions) : "",
    actions > 0 ? tn("today.priorities.part.tell", actions) : "",
    line.chase > 0 ? tn("today.priorities.part.chase", line.chase, { days: line.waiting_days ?? 0 }) : "",
    line.overdue > 0 ? tn("today.priorities.part.overdue", line.overdue) : "",
    line.due_soon > 0 ? tn("today.priorities.part.due_soon", line.due_soon) : "",
  ].filter(Boolean);
  return t("today.priorities.person", { name: line.text, what: parts.join(", ") });
}

/** The row's title: the thing's own words, or a person's summary. */
function titleOf(line: Line, t: T, tn: Tn): string {
  return line.kind === "person" ? personWords(line, t, tn) : line.text;
}

/** The chip before a row: the date, red and worded as overdue when it has passed, or what the row waits for. */
function chip(line: Line, t: T, tn: Tn): { text: string; tone: PillTone } {
  if (line.rank === "overdue") return { text: line.due ? t("today.priorities.pill.overdue", { date: day(line.due) }) : t("queue.pill.overdue"), tone: "danger" };
  if (line.rank === "due_soon") {
    if (line.due) return { text: t("today.priorities.pill.due", { date: day(line.due) }), tone: "warn" };
    return { text: tn("queue.pill.waiting_days", line.waiting_days ?? 0), tone: "warn" };
  }
  if (line.rank === "waiting") return { text: t("queue.pill.waiting"), tone: "need" };
  return { text: t("today.priorities.pill.at_risk"), tone: "warn" };
}

/** The second line: why it is listed, and for someone else what it is about. */
function metaOf(line: Line, t: T, tn: Tn): string {
  if (line.kind === "person") {
    const things = line.things ?? [];
    const first = things[0]?.text ?? "";
    const rest = things.length - 1;
    return rest > 0 ? tn("today.priorities.and_more", rest, { text: first }) : first;
  }
  if (line.rank === "overdue") return tn("today.priorities.passed", line.days ?? 0);
  if (line.rank === "due_soon") return t("today.priorities.due_soon");
  if (line.rank === "waiting") return (line.days ?? 0) > 0 ? tn("today.priorities.asked", line.days ?? 0) : t("today.priorities.asked_today");
  return t("today.priorities.at_risk", { project: line.project_name ?? "" });
}

export function TopPriorities(props: { onView: (view: View) => void }) {
  const { t, tn } = useWords();
  const found = useQuery({ queryKey: ["today", "priorities"], queryFn: api.priorities });
  const data = found.data;
  const lines = data?.lines ?? [];
  const coming = data?.coming ?? [];
  // A row names its project only when the list holds more than one.
  const mixed = new Set(lines.map((line) => line.project).filter(Boolean)).size > 1;
  const seeBlocked = () => {
    chooseFilters({ state: "on_hold" });
    props.onView("work/open");
  };
  const footer = data && (data.more > 0 || data.blocked > 0) && (
    <>
      {data.more > 0 && (
        <button type="button" className="link-button" onClick={() => props.onView("work/open")}>
          {tn("today.priorities.more", data.more)}
        </button>
      )}
      {data.blocked > 0 && (
        <button type="button" className="link-button" onClick={seeBlocked}>
          {tn("today.priorities.blocked", data.blocked)}
        </button>
      )}
    </>
  );
  return (
    <RailPanel id="priorities" title={t("today.priorities.title")} count={data ? lines.length : null} countText={tn("today.priorities.count", lines.length)} footer={footer || undefined}>
      {found.isPending ? (
        <Skeleton />
      ) : found.isError ? (
        <Failed text={t("today.priorities.load_failed")} retry={() => void found.refetch()} />
      ) : lines.length === 0 && coming.length === 0 ? (
        <Empty text={t("today.priorities.empty")} />
      ) : (
        <>
          {lines.length > 0 ? (
            <ul className="tb-list">
              {lines.map((line) => (
                <PriorityRow key={line.key} line={line} mixed={mixed} onView={props.onView} />
              ))}
            </ul>
          ) : (
            <Empty text={t("today.priorities.empty")} />
          )}
          {coming.length > 0 && (
            <div className="tb-group" data-group="coming">
              <h3 className="tb-group-head">{t("today.priorities.coming")}</h3>
              <ul className="tb-list">
                {coming.map((item) => (
                  <li key={item.action} className="tb-row">
                    <span className="tb-when">{day(item.due)}</span>
                    <div className="tb-what">
                      <div className="tb-title">{item.text}</div>
                      <div className="tb-meta">{[item.project_name, item.mine ? t("today.priorities.yours") : (item.owners ?? []).map((o) => o.name).join(", ")].filter(Boolean).join(" · ")}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </RailPanel>
  );
}

function PriorityRow(props: { line: Line; mixed: boolean; onView: (view: View) => void }) {
  const { line } = props;
  if (line.kind === "action" && line.action) return <ActionRow {...props} />;
  return <OtherRow {...props} />;
}

/** The part every row shares: the chip, the title with its project tag, the second line and the items for the tooltip. */
function Body(props: { line: Line; mixed: boolean }) {
  const { t, tn } = useWords();
  const { line } = props;
  const c = chip(line, t, tn);
  const title = titleOf(line, t, tn);
  const items = line.kind === "person" ? (line.things ?? []).map((x) => x.text) : [];
  const project = props.mixed && line.project_name ? <span className={styles.tag}>{line.project_name}</span> : null;
  return (
    <>
      <Pill tone={c.tone}>{c.text}</Pill>
      <div className="tb-what">
        <div className="tb-title" title={items.length > 0 ? items.join("\n") : undefined}>
          {project}
          {title}
        </div>
        <div className="tb-meta">{metaOf(line, t, tn)}</div>
        {items.length > 1 && (
          <ul className="sr">
            {items.map((text, i) => (
              <li key={`${i}:${text}`}>{text}</li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

/** One of the person's own to-dos: Mark done is the row's button; Reassign and a note are in its menu. */
function ActionRow(props: { line: Line; mixed: boolean; onView: (view: View) => void }) {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const row = useRef<HTMLLIElement>(null);
  const { line } = props;
  const id = line.action!;
  const reassign = useReassign({ id, version: line.version ?? 0, owners: line.owners ?? [] }, () => row.current?.focus());
  const hand = useHandToAssistant({ id }, () => row.current?.focus());
  const done = (note?: string) =>
    act(
      () => api.actionStatus(id, "done", note),
      (result) => ({ message: noted(t("toast.action_done"), result.request), undo: () => api.actionStatus(id, "open") }),
    );
  return (
    <li className={`tb-row ${styles.priority}`} data-row tabIndex={-1} ref={row} data-priority={line.rank}>
      <Body line={line} mixed={props.mixed} />
      <Button size="sm" variant="primary" data-key="primary" aria-label={t("today.todo.done_named", { text: line.text })} onClick={() => void done()}>
        {t("followups.mark_done")}
      </Button>
      <RowMenu label={line.text} actions={[reassign.entry, ...(hand.entry ? [hand.entry] : [])]} />
      {reassign.form}
      {hand.form}
    </li>
  );
}

/** A question for the person, or everyone else's one row: its button takes the person to where it is answered. */
function OtherRow(props: { line: Line; mixed: boolean; onView: (view: View) => void }) {
  const { t, tn } = useWords();
  const { line } = props;
  const label =
    line.kind === "question" ? t("queue.act.answer") : line.chase > 0 ? t("queue.act.follow_up") : t("queue.act.review_copy");
  const go = () => {
    if (line.kind === "question" && line.question) {
      revealOrKeep("question", line.question);
      return;
    }
    props.onView("work/followups");
    if (line.person) revealOrKeep("person", line.person);
  };
  return (
    <li className={`tb-row ${styles.priority}`} data-row tabIndex={-1} data-priority={line.rank}>
      <Body line={line} mixed={props.mixed} />
      <Button size="sm" variant="primary" data-key="primary" aria-label={`${label}: ${titleOf(line, t, tn)}`} onClick={go}>
        {label}
      </Button>
    </li>
  );
}
