// Today's queue (design 7.7): one ranked list of lines, each starting with a verb and showing the one thing to do for it.
// The engine ranks and groups (6.15); this draws them. A line is a row (pill, words, its one button, a menu), or one of
// the held lines (a restart, a paused account) or a learned line, which have their own cards. A line that has items
// opens them in the inspector from 1680px and under itself below that.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useFirstGoText } from "../lib/first-go";
import { useRowKeys } from "../lib/keys";
import { GROUPS, inGroup, mixesProjects, useQueue, useTodayCount, type QueueLine } from "../lib/today";
import { useWords } from "../lib/wording";
import { HeldLine, isHeld } from "../shell/HeldLines";
import { Button } from "../ui/Button";
import { Panel } from "../ui/Panel";
import { Pill, type PillTone } from "../ui/Pill";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { LearnedLine, isLearned } from "./LearnedToday";
import { PluginToday } from "./PluginToday";
import { QueueGroup } from "./QueueGroup";
import { RowMenu, type MenuAction } from "./RowMenu";
import { StageTodayRows, useStageToday } from "./StageToday";
import { LineDetail, opensItems } from "./TodayDetail";
import styles from "./Today.module.css";

export interface QueueHandlers {
  onOpenAiAccounts: () => void;
  onOpenHandover: () => void;
  onOpenRules: () => void;
  onOpenKnowledge?: () => void;
  onAddAccount?: () => void;
  onOpenRecord?: (kind: string, id: string) => void;
  onOpenGuide?: (step: string) => void;
}

/** What a line is selected as: the line, and whether its card opens on the note to send it back with. */
export interface Selection {
  key: string;
  sendBack: boolean;
}

export function TodayQueue(props: {
  selected: Selection | null;
  onSelect: (selection: Selection | null) => void;
  /** The inspector is beside the queue, so a selected line doesn't open under itself. */
  beside: boolean;
  handlers: QueueHandlers;
}) {
  const { t, tn } = useWords();
  const queue = useQueue();
  const count = useTodayCount();
  const stage = useStageToday();
  const pane = useRef<HTMLDivElement>(null);
  const lines = queue.data ?? [];

  // New lines that arrive while the person is working in the queue wait behind "N new · Show", so no row moves under the
  // cursor; otherwise they are in the list at once. Where the cursor is is read as the data changes, before the page does.
  const working = useRef<{ in: boolean; row: number }>({ in: false, row: -1 });
  const rows = pane.current ? Array.from(pane.current.querySelectorAll<HTMLElement>("[data-row]")) : [];
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement.closest<HTMLElement>("[data-row]") : null;
  working.current = { in: !!pane.current?.contains(document.activeElement), row: focused ? rows.indexOf(focused) : -1 };
  const [shown, setShown] = useState<Set<string> | null>(null);
  useEffect(() => {
    if (!queue.data) return;
    const keys = queue.data.map((line) => line.key);
    setShown((prev) => (prev !== null && working.current.in ? prev : new Set(keys)));
    // The line that had the cursor is gone: it goes to the one now in its place, not to the top of the page.
    if (working.current.in && (!document.activeElement || document.activeElement === document.body)) {
      const now = Array.from(pane.current?.querySelectorAll<HTMLElement>("[data-row]") ?? []);
      now[Math.max(0, Math.min(now.length - 1, working.current.row))]?.focus({ preventScroll: true });
    }
  }, [queue.data]);
  const visible = shown ? lines.filter((line) => shown.has(line.key)) : lines;
  const waiting = shown ? lines.length - visible.length : 0;

  // The keyboard starts on the queue: once the lines are there, the first one has the cursor, unless the person has put it
  // somewhere of their own.
  const started = useRef(false);
  useEffect(() => {
    if (started.current || !queue.data || queue.data.length === 0) return;
    started.current = true;
    const active = document.activeElement;
    const free = !active || active === document.body || active.tagName === "MAIN" || !!active.closest("h1");
    if (free) pane.current?.querySelector<HTMLElement>("[data-row]")?.focus({ preventScroll: true });
  }, [queue.data]);

  // A selected line that is gone (dealt with, or answered elsewhere) is no longer selected.
  useEffect(() => {
    if (props.selected && queue.data && !queue.data.some((line) => line.key === props.selected!.key)) props.onSelect(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.data, props.selected]);

  const mixed = mixesProjects(lines);
  return (
    <div ref={pane} className={styles.queue}>
      <Panel
        title={t("today.needs.title")}
        flush
        count={
          count === null ? null : (
            <>
              <span aria-hidden="true">{count}</span>
              <span className="sr">{tn("today.needs.count", count)}</span>
            </>
          )
        }
      >
        {waiting > 0 && (
          <div className={styles.newbar}>
            <Button size="sm" onClick={() => setShown(new Set(lines.map((line) => line.key)))}>
              {tn("queue.new_show", waiting)}
            </Button>
          </div>
        )}
        {queue.isPending ? (
          <Skeleton />
        ) : queue.isError ? (
          <p className={styles.empty}>
            {t("queue.load_failed")}{" "}
            <Button size="sm" onClick={() => void queue.refetch()}>
              {t("action.try_again")}
            </Button>
          </p>
        ) : (
          <>
            {GROUPS.map((group) => {
              const these = inGroup(visible, group);
              const extra = group === "decide" && stage.count > 0;
              if (these.length === 0 && !extra) return null;
              return (
                <QueueGroup key={group} id={`queue-group-${group}`} title={t(`queue.group.${group}`)}>
                  {these.map((line) => (
                    <LineItem
                      key={line.key}
                      line={line}
                      selection={props.selected?.key === line.key ? props.selected : null}
                      beside={props.beside}
                      mixed={mixed}
                      onSelect={props.onSelect}
                      handlers={props.handlers}
                    />
                  ))}
                  {extra && <StageTodayRows today={stage} />}
                </QueueGroup>
              );
            })}
            <PluginToday onOpenRecord={props.handlers.onOpenRecord} />
            {count === 0 && (
              <p className={styles.empty} data-queue-empty="">
                {t("queue.empty")}
              </p>
            )}
          </>
        )}
      </Panel>
    </div>
  );
}

function LineItem(props: {
  line: QueueLine;
  selection: Selection | null;
  beside: boolean;
  mixed: boolean;
  onSelect: (selection: Selection | null) => void;
  handlers: QueueHandlers;
}) {
  const { line, handlers } = props;
  if (isHeld(line)) {
    return (
      <li className={styles.item}>
        <HeldLine line={line} onOpenAiAccounts={handlers.onOpenAiAccounts} onOpenHandover={handlers.onOpenHandover} onOpenRules={handlers.onOpenRules} onOpenKnowledge={handlers.onOpenKnowledge} onAddAccount={handlers.onAddAccount} />
      </li>
    );
  }
  if (isLearned(line)) {
    return (
      <li className={styles.item}>
        <LearnedLine line={line} />
      </li>
    );
  }
  return (
    <li className={styles.item}>
      <QueueRow {...props} />
    </li>
  );
}

type Tone = PillTone;

/** What the row says and does for one kind of line. `opens` is a button that shows the line's items rather than acting. */
interface Described {
  pill: string;
  tone: Tone;
  title: string;
  meta: string;
  primary: { label: string; run?: () => void } | null;
  menu: MenuAction[];
}

type ItemTitle = S["ItemTitle"];

function useTitleWords(): (title: ItemTitle | null | undefined) => string {
  const { t } = useWords();
  return (title) => {
    if (!title) return "";
    const who = title.person_name ?? title.sender ?? t("queue.title.someone");
    const head = t(`queue.title.${title.kind}`, { who });
    return title.topic ? t("queue.title.with_topic", { head, topic: title.topic }) : head;
  };
}

/** What the assistant did, counted, as the card's title: "3 actions it added" when it did one kind of thing, else "3 things
 * it did". */
const REVIEW_KINDS = ["actions_added", "actions_closed", "questions", "notes", "recorded", "people", "projects", "drafts"] as const;

function QueueRow(props: {
  line: QueueLine;
  selection: Selection | null;
  beside: boolean;
  mixed: boolean;
  onSelect: (selection: Selection | null) => void;
  handlers: QueueHandlers;
}) {
  const { t, tn } = useWords();
  const act = useAct();
  const titleWords = useTitleWords();
  const firstGoText = useFirstGoText();
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes, enabled: props.line.kind === "go" });
  const ref = useRef<HTMLLIElement & HTMLDivElement>(null);
  const { line } = props;
  const open = props.selection !== null;
  const opens = opensItems(line);
  const inPlace = open && !props.beside;
  const detailId = `detail-${line.key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const select = (next: boolean, sendBack = false) => props.onSelect(next ? { key: line.key, sendBack } : null);
  const show: MenuAction = { id: "look", label: t("queue.look_closer"), run: () => select(true) };

  const what = titleWords(line.title);
  const name = line.person_name ?? "";
  const meta = (...parts: Array<string | null | undefined | false>) => [...parts, line.untrusted ? t("queue.untrusted") : ""].filter(Boolean).join(" · ");
  const d: Described = (() => {
    switch (line.kind) {
      case "decision":
        return { pill: t("queue.pill.decision"), tone: "need", title: t("queue.decision"), meta: meta(line.text, line.due && t("op.meta.due", { date: day(line.due) })), primary: { label: t("queue.act.answer") }, menu: [] };
      case "question":
        return { pill: t("queue.pill.question"), tone: "need", title: t("queue.question"), meta: meta(line.text), primary: { label: t("queue.act.answer") }, menu: [] };
      case "who_is":
        return { pill: t("queue.pill.waiting"), tone: "warn", title: t("queue.who_is", { name: line.text ?? "" }), meta: meta(what), primary: { label: t("queue.act.pick") }, menu: [] };
      case "owner":
        return { pill: t("queue.pill.waiting"), tone: "warn", title: t("queue.owner", { text: line.text ?? "" }), meta: meta(line.due && t("op.meta.due", { date: day(line.due) })), primary: { label: t("queue.act.pick_owner") }, menu: [] };
      case "held":
        return { pill: t("queue.pill.waiting"), tone: "warn", title: t("queue.held"), meta: meta(line.text, line.waiting, what), primary: { label: t("queue.act.decide") }, menu: [] };
      case "go": {
        const item = changes.data?.find((c) => c.id === line.request);
        return {
          pill: t("queue.pill.go"),
          tone: "warn",
          title: t("queue.go", { what }),
          meta: meta(line.waiting),
          primary: item
            ? { label: t("changes.go"), run: () => void act(() => api.stageGo(item.id, item.version), () => ({ message: t("toast.go") })) }
            : { label: t("queue.act.open") },
          menu: [],
        };
      }
      case "first_go":
        return {
          pill: t("queue.pill.go"),
          tone: "warn",
          title: firstGoText({ count: line.count, estimate: line.estimate_usd ?? null, unpriced: line.unpriced }),
          meta: t("first_go.sub"),
          primary: { label: t("changes.go"), run: () => void act(api.firstGo, () => ({ message: t("toast.go") })) },
          menu: [],
        };
      case "refused":
        return { pill: t("queue.pill.stopped"), tone: "danger", title: t("queue.refused", { what }), meta: meta(line.waiting), primary: { label: t("changes.send_other") }, menu: [] };
      case "failed":
        return { pill: t("queue.pill.stopped"), tone: "danger", title: t("queue.failed", { what }), meta: meta(line.waiting), primary: { label: t("queue.act.open") }, menu: [] };
      case "overdue":
        return {
          pill: t("queue.pill.overdue"),
          tone: "danger",
          title: tn("queue.overdue", line.count),
          meta: line.due ? tn("queue.overdue.oldest", line.waiting_days ?? 0, { date: day(line.due) }) : "",
          primary: { label: t("queue.act.show") },
          menu: [],
        };
      case "review": {
        const kinds = REVIEW_KINDS.filter((k) => ((line.outcome ?? {})[k] ?? 0) > 0);
        const done = kinds.reduce((n, k) => n + ((line.outcome ?? {})[k] ?? 0), 0);
        const title = kinds.length === 1 ? tn(`queue.review.${kinds[0]}`, done) : tn("queue.review.things", line.count);
        const held = (line.outcome ?? {}).held ?? 0;
        return {
          pill: t("queue.pill.review"),
          tone: "neutral",
          title,
          meta: meta(what, held > 0 && tn("queue.review.waits", held)),
          primary: {
            label: t("queue.act.all_good"),
            run: () => void act(() => api.looksGood(line.changeset ?? ""), () => ({ message: t("toast.looks_good"), undo: () => api.reopen(line.changeset ?? "") })),
          },
          menu: [show, { id: "send-back", label: t("changes.send_back"), run: () => select(true, true) }],
        };
      }
      case "send": {
        const q = (line.questions ?? []).length;
        const a = (line.actions ?? []).length;
        const title = q && a ? tn("queue.send.items", q + a, { name }) : q ? tn("queue.send.questions", q, { name }) : tn("queue.send.actions", a || line.count, { name });
        return {
          pill: t("queue.pill.send"),
          tone: "need",
          title,
          meta: q && a ? [tn("queue.send.n_questions", q), tn("queue.send.n_actions", a)].join(" · ") : t("queue.send.ready"),
          primary: { label: t("queue.act.review_copy") },
          menu: [],
        };
      }
      case "nudge": {
        const days = line.waiting_days ?? 0;
        return {
          pill: tn("queue.pill.waiting_days", days),
          tone: "warn",
          title: t("queue.nudge", { name }),
          meta: tn("queue.nudge.meta", line.count, { days }),
          primary: { label: t("queue.act.follow_up") },
          menu: [],
        };
      }
      default:
        // A kind the screen has no words for yet still shows, so nothing the engine ranks is hidden.
        return { pill: "", tone: "neutral", title: line.text ?? line.kind, meta: meta(line.waiting), primary: null, menu: [] };
    }
  })();

  useRowKeys(ref, { toggle: opens ? () => select(!open) : undefined });
  const project = props.mixed && line.project_name ? <span className={styles.tag}>{line.project_name}</span> : null;
  const onClick = (event: React.MouseEvent) => {
    if (!opens || (event.target as HTMLElement).closest("button, a, input, textarea, select, [role='menuitem']")) return;
    select(!open);
  };
  const primary: ReactNode = d.primary ? (
    <Button
      size="sm"
      variant="primary"
      data-key="primary"
      aria-expanded={!d.primary.run && opens && !props.beside ? open : undefined}
      aria-controls={!d.primary.run && opens && !props.beside ? detailId : undefined}
      aria-describedby={`${detailId}-title`}
      onClick={d.primary.run ?? (() => select(true))}
    >
      {d.primary.label}
    </Button>
  ) : undefined;
  return (
    <Row
      as="div"
      ref={ref}
      selected={open}
      data-queue-line={line.kind}
      data-line-key={line.key}
      aria-label={d.title}
      role="group"
      pill={d.pill ? <Pill tone={d.tone}>{d.pill}</Pill> : undefined}
      title={
        <span id={`${detailId}-title`}>
          {project}
          {d.title}
        </span>
      }
      meta={d.meta || undefined}
      primary={primary}
      menu={d.menu.length > 0 ? <RowMenu label={d.title} actions={d.menu} /> : undefined}
      onClick={onClick}
    >
      {inPlace && (
        <div id={detailId} className={styles.detail}>
          <LineDetail line={line} sendBack={props.selection?.sendBack} onOpenGuide={props.handlers.onOpenGuide} />
          <div className={styles.detailEnd}>
            <Button size="sm" variant="ghost" onClick={() => select(false)}>
              {t("action.close")}
            </Button>
          </div>
        </div>
      )}
    </Row>
  );
}
