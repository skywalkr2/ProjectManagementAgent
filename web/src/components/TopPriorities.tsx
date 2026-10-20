// Top priorities (design 7.7): a short ranked list across every project, in the rail, as context and never as the place to
// act. One row for each of the person's own things, one row for everyone else however much they hold ("Robin Sample · 1
// overdue · 3 waiting up to 5 days", the items in its tooltip; the link is the name only). The server ranks it by rules; this draws it.
// A row has no buttons and no menu: its words are a link, to its line in the queue (which opens it) or, when the queue
// has none, to its record.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { day } from "../lib/dates";
import { chooseFilters } from "../lib/open-items";
import { revealOrKeep } from "../lib/reveal";
import { useQueue, type QueueLine } from "../lib/today";
import { recordView, viewHref, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Pill, type PillTone } from "../ui/Pill";
import { Skeleton } from "../ui/Skeleton";
import { Empty, Failed, RailPanel } from "./RailPanel";
import styles from "./Today.module.css";

type Line = S["PriorityLineView"];
type T = ReturnType<typeof useWords>["t"];
type Tn = ReturnType<typeof useWords>["tn"];

/** What a person's row says after their name, one fact at a time: "1 overdue · 3 waiting up to 5 days · send 1 question". */
export function personParts(line: Line, tn: Tn): string {
  const sent = (line.things ?? []).filter((x) => x.why === "send");
  const questions = sent.filter((x) => x.kind === "question").length;
  const actions = sent.filter((x) => x.kind === "action").length;
  return [
    line.overdue > 0 ? tn("today.priorities.part.overdue", line.overdue) : "",
    line.chase > 0 ? tn("today.priorities.part.chase", line.chase, { days: line.waiting_days ?? 0 }) : "",
    line.due_soon > 0 ? tn("today.priorities.part.due_soon", line.due_soon) : "",
    questions > 0 ? tn("today.priorities.part.send_questions", questions) : "",
    actions > 0 ? tn("today.priorities.part.tell", actions) : "",
  ]
    .filter(Boolean)
    .join(" · ");
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

/** The second line: why it is listed, and for someone else what it is about; a question or action that holds others up says how many. */
function metaOf(line: Line, t: T, tn: Tn): string {
  const base = baseMeta(line, t, tn);
  return (line.holds_up ?? 0) > 0 ? [base, tn("today.priorities.holds_up", line.holds_up ?? 0)].filter(Boolean).join(" · ") : base;
}

function baseMeta(line: Line, t: T, tn: Tn): string {
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
  const queue = useQueue();
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
    <RailPanel id="priorities" title={t("today.priorities.title")} count={data ? lines.length : null} countText={tn("today.priorities.count", lines.length)} summary={data ? (lines.length > 0 ? String(lines.length) : t("today.rail.nothing")) : ""} footer={footer || undefined}>
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
                <PriorityRow key={line.key} line={line} mixed={mixed} queue={queue.data} />
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


/** The line of the queue a priority is about: the one that lists its to-do, asks its question, or follows up with its person. */
export function queueLineOf(line: Line, queue: QueueLine[] | undefined): QueueLine | undefined {
  if (!queue) return undefined;
  if (line.kind === "action") return queue.find((l) => !!line.action && (l.actions ?? []).includes(line.action));
  if (line.kind === "question") return queue.find((l) => !!line.question && (l.question === line.question || (l.questions ?? []).includes(line.question)));
  const mine = queue.filter((l) => !!line.person && l.person === line.person);
  return mine.find((l) => l.kind === "nudge") ?? mine.find((l) => l.kind === "escalate") ?? mine.find((l) => l.kind === "send");
}

/** One row: the chip, the words as a link, the second line and the items for the tooltip. */
function PriorityRow(props: { line: Line; mixed: boolean; queue: QueueLine[] | undefined }) {
  const { t, tn } = useWords();
  const { line } = props;
  const target = queueLineOf(line, props.queue);
  const record = line.kind === "action" && line.action ? recordView("action", line.action) : line.kind === "question" && line.question ? recordView("question", line.question) : line.person ? recordView("person", line.person) : null;
  const c = chip(line, t, tn);
  // A person's row links their name only; what is open with them follows it as plain words.
  const title = line.text;
  const rest = line.kind === "person" ? personParts(line, tn) : "";
  const items = line.kind === "person" ? (line.things ?? []).map((x) => x.text) : [];
  const project = props.mixed && line.project_name ? <span className={styles.tag}>{line.project_name}</span> : null;
  const words = target ? (
    // The queue is where it is done: choosing the link opens its line there, without leaving Today.
    <a
      href={viewHref("today")}
      onClick={(event) => {
        event.preventDefault();
        revealOrKeep("line", target.key);
      }}
    >
      {title}
    </a>
  ) : record ? (
    <a href={viewHref(record)}>{title}</a>
  ) : (
    title
  );
  return (
    <li className={`tb-row ${styles.priority}`} data-row tabIndex={-1} data-priority={line.rank}>
      <Pill tone={c.tone}>{c.text}</Pill>
      <div className="tb-what">
        <div className="tb-title" title={items.length > 0 ? items.join("\n") : undefined}>
          {project}
          {words}
          {rest && ` · ${rest}`}
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
    </li>
  );
}
