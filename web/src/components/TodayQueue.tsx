// Today's queue (design 7.7): one ranked list of lines, each starting with a verb and showing the one thing to do for it.
// The engine ranks and groups (6.15); this draws them, with the plugins' own lines placed in the groups they name. A line
// is a row (pill, words, its one button, a menu), or one of the held lines (a restart, a paused account) or a learned
// line, which have their own cards. A line that has items opens them in the inspector from 1680px, which shows the line
// that has the cursor, and under itself below that. The list holds still while the person is working in it: new lines
// wait behind "N new · Show", and a line settled somewhere else stays in place until the person moves on.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, wallTime } from "../lib/dates";
import { backupAge } from "../lib/backup";
import { useFirstGoText } from "../lib/first-go";
import { useRowKeys } from "../lib/keys";
import { chooseFilters } from "../lib/open-items";
import { onShowNewLines } from "../lib/queue-hold";
import { afterMove, endingWho, heldAnswers, heldTitle, isEnding, moveTitle } from "../lib/queue-words";
import { revealOrKeep } from "../lib/reveal";
import type { View } from "../lib/views";
import { GROUPS, inGroup, mixesProjects, recallLine, rememberLine, useQueue, useTodayCount, type QueueLine } from "../lib/today";
import { useWords } from "../lib/wording";
import { HeldLine, isHeld } from "../shell/HeldLines";
import { Button } from "../ui/Button";
import { Panel } from "../ui/Panel";
import { Pill, type PillTone } from "../ui/Pill";
import { OutsideTag } from "../ui/OutsideTag";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { NothingNeedsYou } from "./Coverage";
import { usePromiseChoices } from "./PromiseLine";
import { ReminderItems, digestTitle, reminderTitle, useReminderChoices, useReminderNotices } from "./ReminderLine";
import { ReplyDraft, replyTitle, useReplyChoices } from "./ReplyLine";
import { sentCheckTitle, useSentCheckChoices } from "./SentCheckLine";
import { LearnedLine, isLearned } from "./LearnedToday";
import { PluginRows, usePluginToday } from "./PluginToday";
import { QueueGroup } from "./QueueGroup";
import { RowMenu, type MenuAction } from "./RowMenu";
import type { MenuGroup } from "../ui/MenuButton";
import { MissedOneLine } from "./MissedOne";
import { StageTodayRows, useStageToday } from "./StageToday";
import { ThisWeekInspector } from "./ThisWeek";
import { LineDetail, opensItems } from "./TodayDetail";
import styles from "./Today.module.css";

export interface QueueHandlers {
  onOpenAiAccounts: () => void;
  onOpenHandover: () => void;
  onOpenRules: () => void;
  onOpenKnowledge?: () => void;
  onAddAccount?: () => void;
  onOpenSources?: () => void;
  onOpenRecord?: (kind: string, id: string) => void;
  onOpenGuide?: (step: string) => void;
  /** Go to a screen: the Projects list where unfiled work is filed. */
  onOpenView?: (view: View) => void;
}

/** What a line is selected as: the line, and whether its card opens on the note to send it back with. */
export interface Selection {
  key: string;
  sendBack: boolean;
}

export function TodayQueue(props: {
  selected: Selection | null;
  onSelect: (selection: Selection | null) => void;
  /** The inspector is beside the queue: it shows the line that has the cursor, and a selected line doesn't open under itself. */
  beside: boolean;
  handlers: QueueHandlers;
  /** The configured shortcut keys, for the inspector's "j / k". */
  shortcuts?: Record<string, string>;
}) {
  const { t, tn } = useWords();
  const queue = useQueue();
  const count = useTodayCount();
  const stage = useStageToday();
  const plugins = usePluginToday(props.handlers.onOpenRecord);
  const pane = useRef<HTMLDivElement>(null);
  const lines = queue.data ?? [];
  useReminderNotices(queue.data);

  // The list holds still while the person is working in it: keyboard focus or the pointer in the queue or the inspector, or
  // a line open under itself. New lines wait behind "N new · Show". A line settled somewhere else stays in place, struck
  // through, until the person moves on; a line the person settled here leaves at once. `frozen` is the keys on screen
  // while held, in order, and null while nothing holds the list, when it simply follows the data.
  const pointer = useRef(false);
  const touched = useRef<string | null>(null);
  const known = useRef(new Map<string, QueueLine>());
  for (const line of lines) known.current.set(line.key, line);
  const [frozen, setFrozen] = useState<string[] | null>(null);
  const heldNow = () => {
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const here = !!pane.current?.contains(active) || !!active?.closest("[data-queue-inspector]");
    return here || pointer.current || (props.selected !== null && !props.beside);
  };
  // Where the cursor is, read as the data changes and before the page does.
  const working = useRef<{ held: boolean; row: number; keys: string[] }>({ held: false, row: -1, keys: [] });
  const rows = pane.current ? Array.from(pane.current.querySelectorAll<HTMLElement>("[data-row]")) : [];
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement.closest<HTMLElement>("[data-row]") : null;
  working.current = { held: heldNow(), row: focused ? rows.indexOf(focused) : -1, keys: rows.map((row) => row.dataset.lineKey ?? "") };
  const focusKey = useRef<{ key: string; tries: number } | null>(null);

  const live = new Map(lines.map((line) => [line.key, line]));
  const ghostable = (key: string) => {
    const old = known.current.get(key);
    return !!old && key !== touched.current && !isHeld(old) && !isLearned(old);
  };
  // The keys on screen as of the last commit, which is what a hold keeps when the data changes under it.
  const shownKeys = useRef<string[]>([]);
  const onScreen = useRef(false); // the lines have been drawn once; before that there is nothing to hold still
  // While the person is working in the list it keeps what is on screen even in the render that brings the new data, so a row
  // under the cursor is never replaced; the effect below keeps that as the state once the data has changed.
  // An empty list has nothing to hold still: new lines then come straight in.
  const holding = frozen ?? (working.current.held && onScreen.current && shownKeys.current.length > 0 ? shownKeys.current : null);
  type Shown = { line: QueueLine; ghost: boolean };
  const display: Shown[] =
    holding === null
      ? lines.map((line): Shown => ({ line, ghost: false }))
      : holding.flatMap((key): Shown[] => {
          const now = live.get(key);
          if (now) return [{ line: now, ghost: false }];
          return ghostable(key) ? [{ line: known.current.get(key)!, ghost: true }] : [];
        });
  const waiting = holding === null ? 0 : lines.filter((line) => !holding.includes(line.key)).length;

  // The questions left of a move's group, once the group is down to one, stand in the group's place: answering one row of
  // two doesn't send the other behind "1 new · Show", and the line that was open stays open.
  const successorOf = (key: string, taken: string[]): string | null => {
    const request = known.current.get(key)?.after_move?.request;
    if (!request) return null;
    return lines.find((line) => line.after_move?.request === request && line.key !== key && !taken.includes(line.key))?.key ?? null;
  };

  // Before the screen is painted, so a line that should hold is never seen to move.
  useLayoutEffect(() => {
    if (!queue.data) return;
    const keys = new Set(queue.data.map((line) => line.key));
    let after = [...keys];
    if (!working.current.held || (frozen ?? shownKeys.current).length === 0) {
      setFrozen(null);
    } else {
      const base = frozen ?? shownKeys.current;
      after = base.flatMap((key) => {
        if (keys.has(key)) return [key];
        const next = successorOf(key, base);
        return next ? [next] : ghostable(key) ? [key] : [];
      });
      setFrozen(after.length === base.length && frozen && after.every((key, i) => key === frozen[i]) ? frozen : after);
      // The line that had the cursor is gone: the cursor goes to the line now in its place, not to the top of the page.
      const active = document.activeElement;
      if (working.current.row >= 0 && (!active || active === document.body)) {
        const { keys: before, row } = working.current;
        const next = [...before.slice(row + 1), ...before.slice(0, Math.max(0, row)).reverse()].find((key) => key && after.includes(key));
        focusKey.current = { key: next ?? "", tries: 2 };
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.data]);
  // Once the list is as it will stay, the cursor lands on the line chosen for it: tried on the commit of the change and the one
  // after it (a ghost the change keeps is drawn then), never later, so it can't take the cursor from where the person put it.
  useLayoutEffect(() => {
    const want = focusKey.current;
    if (want === null) return;
    const active = document.activeElement;
    const target =
      active && active !== document.body
        ? null
        : want.key
          ? pane.current?.querySelector<HTMLElement>(`[data-line-key="${CSS.escape(want.key)}"]`)
          : pane.current?.querySelector<HTMLElement>("[data-row]");
    if (target) target.focus({ preventScroll: true });
    focusKey.current = target || (active && active !== document.body) || want.tries <= 1 ? null : { ...want, tries: want.tries - 1 };
  });
  useLayoutEffect(() => {
    shownKeys.current = display.map((d) => d.line.key);
    if (queue.data) onScreen.current = true;
  });

  // What the person last acted on here is theirs: when it leaves the list it goes at once, not as a ghost.
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const row = target?.closest<HTMLElement>("[data-line-key]");
      if (row && pane.current?.contains(row)) touched.current = row.dataset.lineKey ?? null;
      else if (target?.closest("[data-queue-inspector]")) touched.current = props.selected?.key ?? null;
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [props.selected]);

  // Letting go: the waiting lines come in and the ghosts leave. The button, Shift+N and the end of every hold do it.
  // Showing makes what is in the data now the list to hold from here (the cursor may still be in it); when nothing holds the
  // list any more it just follows the data.
  const latestKeys = useRef<string[]>([]);
  latestKeys.current = lines.map((line) => line.key);
  const show = () => setFrozen(latestKeys.current);
  useEffect(() => onShowNewLines(show), []);
  const releaseIfFree = () =>
    window.setTimeout(() => {
      if (!heldNow()) setFrozen(null);
    }, 0);
  useEffect(() => {
    if (frozen !== null && !heldNow()) setFrozen(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.selected]);

  // The keyboard starts on the queue: once the lines are there, the line the inspector last showed (else the first) has the
  // cursor, unless the person has put it somewhere of their own.
  const started = useRef(false);
  useEffect(() => {
    if (started.current || !queue.data || queue.data.length === 0) return;
    started.current = true;
    const active = document.activeElement;
    const free = !active || active === document.body || active.tagName === "MAIN" || !!active.closest("h1");
    if (!free) return;
    const all = Array.from(pane.current?.querySelectorAll<HTMLElement>("[data-row]") ?? []);
    const back = props.beside ? recallLine() : null;
    const target = (back && all.find((el) => el.dataset.lineKey === back.key)) || all[0];
    target?.focus({ preventScroll: true });
  }, [queue.data]);

  // From 1680px the inspector shows one line from the moment Today opens: the line that has the cursor, or the one last
  // clicked, the remembered one when there is one. The lines it can show are the queue's own rows, in the order on screen.
  const ordered = GROUPS.flatMap((group) => inGroup(display.map((d) => d.line), group)).filter((line) => !isHeld(line) && !isLearned(line));
  const selectedAt = props.selected ? ordered.findIndex((line) => line.key === props.selected!.key) : -1;
  useEffect(() => {
    if (!props.beside || !queue.data) return;
    if (selectedAt >= 0) {
      rememberLine(ordered[selectedAt].key, selectedAt);
      return;
    }
    if (ordered.length === 0) {
      if (props.selected) props.onSelect(null);
      return;
    }
    const back = recallLine();
    const found = !props.selected && back ? ordered.findIndex((line) => line.key === back.key) : -1;
    const at = found >= 0 ? found : Math.max(0, Math.min(ordered.length - 1, back?.index ?? 0));
    props.onSelect({ key: ordered[at].key, sendBack: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.beside, queue.data, selectedAt, props.selected, frozen]);

  // Below 1680px a selected line that is gone (dealt with, or answered elsewhere) is no longer open.
  useEffect(() => {
    if (props.beside) return;
    if (props.selected && queue.data && !queue.data.some((line) => line.key === props.selected!.key)) {
      const next = successorOf(props.selected.key, []);
      props.onSelect(next ? { key: next, sendBack: false } : null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.data, props.selected, props.beside]);

  // The cursor reaching a line shows it in the inspector, and a ghost whose line the cursor has left goes.
  const onFocus = (event: React.FocusEvent) => {
    const key = (event.target as HTMLElement).closest<HTMLElement>("[data-line-key]")?.dataset.lineKey;
    if (!key) return;
    if (frozen?.some((k) => !live.has(k) && k !== key)) setFrozen((prev) => prev && prev.filter((k) => live.has(k) || k === key));
    if (props.beside && props.selected?.key !== key && ordered.some((line) => line.key === key)) props.onSelect({ key, sendBack: false });
  };

  const lineTitle = useLineTitle();
  const mixed = mixesProjects(lines);
  const shown = display.map((d) => d.line);
  const ghosts = new Set(display.filter((d) => d.ghost).map((d) => d.line.key));
  const empty = count === 0 && !queue.isPending;
  const selectedLine = selectedAt >= 0 ? ordered[selectedAt] : undefined;
  return (
    <>
      <div
        ref={pane}
        className={styles.queue}
        onFocus={onFocus}
        onBlur={(event) => {
          if (!pane.current?.contains(event.relatedTarget as Node | null)) releaseIfFree();
        }}
        onMouseEnter={() => {
          pointer.current = true;
        }}
        onMouseLeave={() => {
          pointer.current = false;
          releaseIfFree();
        }}
      >
        <Panel
          title={t("today.needs.title")}
          flush
          count={
            count === null || count === 0 ? null : (
              <>
                <span aria-hidden="true">{count}</span>
                <span className="sr">{tn("today.needs.count", count)}</span>
              </>
            )
          }
        >
          <div role="status" className="sr">
            {waiting > 0 ? tn("queue.new_announce", waiting) : ""}
          </div>
          {waiting > 0 && (
            <div className={styles.newbar}>
              <Button size="sm" variant="primary" aria-keyshortcuts="Shift+N" onClick={show}>
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
                const these = inGroup(shown, group);
                const extra = group === "decide" && stage.count > 0;
                const added = plugins.in(group);
                if (these.length === 0 && !extra && added.length === 0) return null;
                return (
                  <QueueGroup key={group} id={`queue-group-${group}`} title={t(`queue.group.${group}`)}>
                    {these.map((line) => (
                      <LineItem
                        key={line.key}
                        line={line}
                        ghost={ghosts.has(line.key)}
                        selection={props.selected?.key === line.key ? props.selected : null}
                        beside={props.beside}
                        mixed={mixed}
                        onSelect={props.onSelect}
                        handlers={props.handlers}
                      />
                    ))}
                    {extra && <StageTodayRows today={stage} />}
                    <PluginRows lines={added} plugins={plugins} />
                  </QueueGroup>
                );
              })}
              {plugins.in(null).length > 0 && (
                <QueueGroup id="plugin-today-title" title={t("today.plugins.title")}>
                  <PluginRows lines={plugins.in(null)} plugins={plugins} />
                </QueueGroup>
              )}
              {plugins.review}
              {count === 0 && (
                <>
                  <NothingNeedsYou className={styles.empty} />
                  <MissedOneLine className={styles.empty} />
                </>
              )}
            </>
          )}
        </Panel>
      </div>
      {props.beside && (
        <QueueInspector
          line={selectedLine}
          title={selectedLine ? lineTitle(selectedLine) : ""}
          position={selectedAt >= 0 ? { at: selectedAt + 1, of: ordered.length } : null}
          sendBack={props.selected?.sendBack}
          shortcuts={props.shortcuts}
          empty={empty}
          onOpenGuide={props.handlers.onOpenGuide}
        />
      )}
    </>
  );
}

/** The pane beside the queue (from 1680px): the line that has the cursor, headed by its subject and where it is in the list.
 * With nothing to do it says so and what comes next; it is never blank. */
function QueueInspector(props: {
  line: QueueLine | undefined;
  title: string;
  position: { at: number; of: number } | null;
  sendBack?: boolean;
  shortcuts?: Record<string, string>;
  empty: boolean;
  onOpenGuide?: (step: string) => void;
}) {
  const { t } = useWords();
  const { line } = props;
  const keys = props.shortcuts?.next && props.shortcuts?.previous ? { next: props.shortcuts.next, previous: props.shortcuts.previous } : null;
  const where = props.position
    ? keys
      ? t("queue.inspector.position_keys", { ...props.position, ...keys })
      : t("queue.inspector.position", { ...props.position })
    : undefined;
  return (
    <aside className={styles.inspector} aria-label={t("queue.inspector.title")} data-queue-inspector="">
      <Panel title={line ? props.title : props.empty ? t("queue.inspector.nothing") : t("queue.inspector.title")} count={where}>
        {line ? (
          <div className={styles.detail}>
            {opensItems(line) ? <LineDetail line={line} sendBack={props.sendBack} onOpenGuide={props.onOpenGuide} /> : <p className="hint">{t("queue.inspector.nothing_more")}</p>}
          </div>
        ) : (
          <>
            {props.empty && <NothingNext />}
            <div className={styles.inspectorBody}>
              <ThisWeekInspector />
            </div>
          </>
        )}
      </Panel>
    </aside>
  );
}

/** What the inspector says when nothing needs the person: when the sources are next read. */
function NothingNext() {
  const { t } = useWords();
  const watch = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });
  const next = (watch.data ?? [])
    .filter((source) => source.enabled && source.read_at)
    .map((source) => new Date(new Date(source.read_at!).getTime() + source.every_minutes * 60_000))
    .sort((a, b) => a.getTime() - b.getTime())[0];
  return (
    <div className={styles.inspectorEmpty}>
      <p>{t("queue.inspector.all_clear")}</p>
      {next && <p>{t("queue.inspector.next_check", { time: wallTime(next.toISOString()) })}</p>}
    </div>
  );
}

function LineItem(props: {
  line: QueueLine;
  /** The line was settled somewhere else; it stays, struck through, until the person moves on. */
  ghost: boolean;
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
        <HeldLine line={line} onOpenAiAccounts={handlers.onOpenAiAccounts} onOpenHandover={handlers.onOpenHandover} onOpenRules={handlers.onOpenRules} onOpenKnowledge={handlers.onOpenKnowledge} onAddAccount={handlers.onAddAccount} onOpenSources={handlers.onOpenSources} />
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
  meta: ReactNode;
  primary: { label: string; run?: () => void } | null;
  /** The other answer to a question the line asks, as a visible button (7.6: a held line may show two). */
  other?: { label: string; run: () => void };
  menu: MenuAction[];
  /** Further titled groups of choices in the menu (a reminder's snooze choices). */
  groups?: MenuGroup[];
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

/** What the line for the changes since yesterday counted, in plain words: "3 closed, 2 moved, 4 new". */
const SINCE_ACTS = ["closed", "moved", "added", "merged", "dropped", "set_aside", "news"] as const;

function sinceWords(line: QueueLine, t: (key: string, vars?: Record<string, string | number>) => string): string {
  return SINCE_ACTS.filter((k) => ((line.outcome ?? {})[k] ?? 0) > 0)
    .map((k) => t(`queue.since.count.${k}`, { n: (line.outcome ?? {})[k] ?? 0 }))
    .join(", ");
}

/** What a review line counted, by the kinds of thing the assistant did. */
const REVIEW_KINDS = ["actions_added", "actions_closed", "questions", "notes", "recorded", "people", "projects", "drafts"] as const;

/** A promise that has had replies without an answer, and what to do: "Sam replied twice without a date: ask again?" */
function repliedWords(replies: number, name: string, t: (key: string, vars?: Record<string, string | number>) => string): string {
  const times = replies === 1 ? t("queue.replied.once") : replies === 2 ? t("queue.replied.twice") : t("queue.replied.times", { n: replies });
  return t("queue.replied", { name, times });
}

function reviewParts(line: QueueLine) {
  const kinds = REVIEW_KINDS.filter((k) => ((line.outcome ?? {})[k] ?? 0) > 0);
  const done = kinds.reduce((n, k) => n + ((line.outcome ?? {})[k] ?? 0), 0);
  const refusedOnly = done === 0 && kinds.length === 0 && ((line.outcome ?? {}).refused ?? 0) > 0 && !((line.outcome ?? {}).held ?? 0);
  return { kinds, done, refusedOnly };
}

/** What an intake's results were, in the order a person thinks of them: "3 actions, 2 questions, 4 waiting for you". */
const INTAKE_KINDS = [...REVIEW_KINDS, "other", "held", "refused"] as const;

function useIntakeWords(): (line: QueueLine) => string {
  const { tn } = useWords();
  return (line) =>
    INTAKE_KINDS.filter((k) => ((line.outcome ?? {})[k] ?? 0) > 0)
      .map((k) => tn(`queue.intake_review.${k}`, (line.outcome ?? {})[k] ?? 0))
      .join(", ");
}

/** The words a review line counts, "3 actions it added" when it did one kind of thing, else "3 things it did". */
function useReviewCount(): (line: QueueLine) => string {
  const { tn } = useWords();
  return (line) => {
    const { kinds, done, refusedOnly } = reviewParts(line);
    return refusedOnly ? tn("queue.review.refused_only", line.count) : kinds.length === 1 ? tn(`queue.review.${kinds[0]}`, done) : tn("queue.review.things", line.count);
  };
}

/** A line's title (design 7.14): what to do, in a verb. A line that holds one item is titled by the item itself, with its
 * pill saying what it is and its button what to do; a line that groups several says how many. */
export function useLineTitle(): (line: QueueLine) => string {
  const { t, tn } = useWords();
  const titleWords = useTitleWords();
  const firstGoText = useFirstGoText();
  const reviewCount = useReviewCount();
  return (line) => {
    const what = titleWords(line.title);
    const name = line.person_name ?? "";
    switch (line.kind) {
      case "decision":
        return line.text || t("queue.decision");
      case "question":
        return line.text || t("queue.question");
      case "who_is":
        return t("queue.who_is", { name: line.text ?? "" });
      case "owner":
        return t("queue.owner", { text: line.text ?? "" });
      case "held":
        return line.held ? heldTitle(line.held, t) : t("queue.held");
      case "unfiled":
        return tn("queue.unfiled", line.count);
      case "moved":
        return moveTitle(line, t, tn);
      case "go":
        return t("queue.go", { what });
      case "first_go":
        return firstGoText({ count: line.count, estimate: line.estimate_usd ?? null, unpriced: line.unpriced });
      case "refused":
        return t("queue.refused", { what });
      case "failed":
        return t("queue.failed", { what });
      case "overdue":
        return line.count === 1 && line.subject ? line.subject : tn("queue.overdue", line.count);
      case "review":
        return line.count === 1 && line.subject && !reviewParts(line).refusedOnly ? line.subject : reviewCount(line);
      case "intake_review":
        return tn("queue.intake_review.title", line.count, { source: line.subject ?? line.source ?? "" });
      case "send": {
        const q = (line.questions ?? []).length;
        const a = (line.actions ?? []).length;
        return q && a ? tn("queue.send.items", q + a, { name }) : q ? tn("queue.send.questions", q, { name }) : tn("queue.send.actions", a || line.count, { name });
      }
      case "nudge":
        return t("queue.nudge", { name });
      case "backup":
        return t("queue.backup");
      case "escalate":
        return t("queue.escalate", { text: (line.text ?? "").replace(/[?.!\s]+$/, "") });
      case "stale":
        return line.count === 1 && line.subject ? t("queue.stale.one_named", { text: line.subject }) : tn("queue.stale", line.count);
      case "promise": {
        const vars = { name, text: line.text ?? "", date: line.due ? day(line.due) : "" };
        if ((line.replies ?? 0) > 0) return repliedWords(line.replies ?? 0, name, t);
        // Someone the person reports to is waited on, never chased (design 6.34).
        const waiting = line.stance === "report_to";
        if (!line.due) {
          const n = line.waiting_days ?? 0;
          return waiting ? tn("queue.promise.wait_undated", n, { ...vars, n }) : tn("queue.promise.chase_undated", n, { ...vars, n });
        }
        if (!line.person) return t("queue.promise.own", vars);
        return waiting ? t("queue.promise.wait", vars) : t("queue.promise.chase", vars);
      }
      case "reminder":
        return reminderTitle(line, t);
      case "reminder_digest":
        return digestTitle(line, t);
      case "reply":
        return replyTitle(line, t);
      case "sent_check":
        return sentCheckTitle(line, t);
      case "since_yesterday":
        return t("queue.since.title");
      case "away":
        return tn("queue.away", line.count);
      default:
        return line.text ?? line.kind;
    }
  };
}

function QueueRow(props: {
  line: QueueLine;
  ghost: boolean;
  selection: Selection | null;
  beside: boolean;
  mixed: boolean;
  onSelect: (selection: Selection | null) => void;
  handlers: QueueHandlers;
}) {
  const { t, tn } = useWords();
  const act = useAct();
  const titleWords = useTitleWords();
  const lineTitle = useLineTitle();
  const reviewCount = useReviewCount();
  const intakeWords = useIntakeWords();
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes, enabled: props.line.kind === "go" });
  const ref = useRef<HTMLLIElement & HTMLDivElement>(null);
  const { line } = props;
  const open = props.selection !== null;
  const opens = opensItems(line);
  const inPlace = open && !props.beside;
  const detailId = `detail-${line.key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const select = (next: boolean, sendBack = false) => props.onSelect(next ? { key: line.key, sendBack } : null);
  // Beside the queue the inspector always shows a line, so choosing one never closes it; the cursor goes to its first field.
  const intoPane = () => {
    let tries = 0;
    const look = () => {
      const inner = document.querySelector<HTMLElement>("[data-queue-inspector] textarea, [data-queue-inspector] input, [data-queue-inspector] select");
      if (inner) inner.focus();
      else if (tries++ < 20) window.setTimeout(look, 50);
    };
    look();
  };
  const choose = () => {
    select(true);
    if (props.beside) intoPane();
  };
  const show: MenuAction = { id: "look", label: t("queue.look_closer"), run: choose };
  const promiseRow = usePromiseChoices(line, () => ref.current?.focus());
  const replyRow = useReplyChoices(line, () => ref.current?.focus());
  const sentRow = useSentCheckChoices(line);
  const reminderRow = useReminderChoices(line.kind === "reminder" ? (line.actions ?? [])[0] ?? "" : "", line.snoozes ?? [], () => ref.current?.focus());

  const what = titleWords(line.title);
  const title = lineTitle(line);
  // What came from outside is tagged "Outside" at the end of the line's words; its full phrase is the tag's name.
  const meta = (...parts: Array<string | null | undefined | false>): ReactNode => {
    const words = parts.filter(Boolean).join(" · ");
    if (!line.untrusted) return words;
    return (
      <>
        {words && `${words} · `}
        <OutsideTag />
      </>
    );
  };
  const d: Described = (() => {
    switch (line.kind) {
      case "decision":
        return { pill: t("queue.pill.decision"), tone: "need", meta: meta(what, afterMove(line, t), line.due && t("op.meta.due", { date: day(line.due) })), primary: { label: t("queue.act.answer") }, menu: [] };
      case "question":
        return { pill: t("queue.pill.question"), tone: "need", meta: meta(what, afterMove(line, t)), primary: { label: t("queue.act.answer") }, menu: [] };
      case "who_is":
        return { pill: t("queue.pill.waiting"), tone: "warn", meta: meta(what), primary: { label: t("queue.act.pick") }, menu: [] };
      case "owner":
        return { pill: t("queue.pill.waiting"), tone: "warn", meta: meta(line.due && t("op.meta.due", { date: day(line.due) })), primary: { label: t("queue.act.pick_owner") }, menu: [] };
      case "held": {
        const ask = line.held;
        if (!ask || line.changeset == null || line.op == null) {
          return { pill: t("queue.pill.waiting"), tone: "warn", meta: meta(line.text, line.waiting, what), primary: { label: t("queue.act.decide") }, menu: [] };
        }
        const cs = line.changeset;
        const index = line.op;
        const words = heldAnswers(ask, t);
        const told = ask.told ?? [];
        const release = () =>
          void act(
            () => api.release(cs, index),
            () => ({ message: t("queue.held.done", { what: ask.item }), undo: () => api.undo(cs, [index]) }),
          );
        const decline = () =>
          void act(
            () => api.declineOp(cs, index),
            () => ({ message: t("queue.held.kept", { what: ask.item }), undo: () => api.undeclineOp(cs, index) }),
          );
        if (isEnding(ask)) {
          // An ending an input says happened reads as one line: Keep is the primary; Not yet and Change are in the menu.
          // When its words only said "closed", the primary is Done by its owner and No longer needed is in the menu.
          const record = ask.record ?? "";
          const choice = ask.ask === "ending";
          const answer = (ending: "done" | "called_off") =>
            void act(
              () => api.endingAnswer(cs, index, ending),
              () => ({
                message: t(ending === "done" ? "queue.held.ending_done" : "queue.held.ending_off", { what: ask.item, who: endingWho(ask, t) }),
                undo: () => api.undo(cs, [index]),
              }),
            );
          return {
            pill: t("queue.pill.waiting"),
            tone: "warn",
            meta: (
              <>
                {meta(ask.quote ? t("queue.held.quote", { quote: ask.quote }) : "", ask.earlier ? t("queue.held.e.earlier", { quote: ask.earlier }) : "", ask.reporter ? t("queue.held.e.said_by", { name: ask.reporter }) : "", what)}
                {ask.ask === "drop" && told.length > 0 && (
                  <>
                    {" · "}
                    <strong>{ask.told_on ? t("queue.held.told_on", { names: told.join(", "), date: day(ask.told_on) }) : t("queue.held.told", { names: told.join(", ") })}</strong>
                  </>
                )}
              </>
            ),
            primary: { label: words.primary, run: choice ? () => answer("done") : release },
            menu: [
              ...(choice ? [{ id: "called-off", label: t("queue.held.e.ending_off"), run: () => answer("called_off") }] : []),
              { id: "not-yet", label: words.other, run: decline },
              ...(props.handlers.onOpenRecord ? [{ id: "change", label: t("queue.held.e.change"), run: () => props.handlers.onOpenRecord?.("action", record) }] : []),
            ],
          };
        }
        return {
          pill: t("queue.pill.waiting"),
          tone: "warn",
          meta: (
            <>
              {meta(line.waiting, ask.quote ? t("queue.held.quote", { quote: ask.quote }) : "", what)}
              {ask.ask === "drop" && told.length > 0 && (
                <>
                  {" · "}
                  <strong>{ask.told_on ? t("queue.held.told_on", { names: told.join(", "), date: day(ask.told_on) }) : t("queue.held.told", { names: told.join(", ") })}</strong>
                </>
              )}
            </>
          ),
          primary: {
            label: words.primary,
            run: () =>
              void act(
                () => api.release(cs, index),
                () => ({ message: t("queue.held.done", { what: ask.item }), undo: () => api.undo(cs, [index]) }),
              ),
          },
          other: {
            label: words.other,
            run: () =>
              void act(
                () => api.declineOp(cs, index),
                () => ({ message: t("queue.held.kept", { what: ask.item }), undo: () => api.undeclineOp(cs, index) }),
              ),
          },
          menu: [],
        };
      }
      case "unfiled":
        return {
          pill: t("queue.pill.unfiled"),
          tone: "neutral",
          meta: t("queue.unfiled.meta"),
          primary: { label: t("queue.act.file_them"), run: () => props.handlers.onOpenView?.("records/projects") },
          menu: [],
        };
      case "moved": {
        const after = line.after_move;
        const others = after?.others ?? [];
        const open: MenuAction[] = [];
        if (after && props.handlers.onOpenRecord) open.push({ id: "meeting", label: t("queue.moved.open", { what: after.title }), run: () => props.handlers.onOpenRecord!(after.kind, after.record) });
        if (line.changeset) {
          const cs = line.changeset;
          open.push({ id: "undo-run", label: t("queue.moved.undo"), run: () => void act(() => api.undo(cs), () => ({ message: t("queue.moved.undone") })) });
        }
        return {
          pill: t("queue.pill.moved"),
          tone: "warn",
          meta: meta(
            after && t(after.by === "pm" ? "queue.moved.from_you" : "queue.moved.from_input"),
            others.length > 0 && tn("queue.moved.others", others.length, { names: others.join(", ") }),
          ),
          primary: { label: t("queue.act.look_closer") },
          menu: open,
        };
      }
      case "go": {
        const item = changes.data?.find((c) => c.id === line.request);
        return {
          pill: t("queue.pill.go"),
          tone: "warn",
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
          meta: t("first_go.sub"),
          primary: { label: t("changes.go"), run: () => void act(api.firstGo, () => ({ message: t("toast.go") })) },
          menu: [],
        };
      case "refused":
        return { pill: t("queue.pill.stopped"), tone: "danger", meta: meta(line.waiting), primary: { label: t("changes.send_other") }, menu: [] };
      case "failed":
        return { pill: t("queue.pill.stopped"), tone: "danger", meta: meta(line.waiting), primary: { label: t("queue.act.open") }, menu: [] };
      case "overdue":
        return {
          pill: t("queue.pill.overdue"),
          tone: "danger",
          meta: !line.due
            ? ""
            : line.count === 1 && line.subject
              ? tn("queue.overdue.was_due", line.waiting_days ?? 0, { date: day(line.due) })
              : tn("queue.overdue.oldest", line.waiting_days ?? 0, { date: day(line.due) }),
          primary: { label: t("queue.act.show") },
          menu: [],
        };
      case "review": {
        const held = (line.outcome ?? {}).held ?? 0;
        // A line that holds one item is titled by it, so the counted sentence moves to the words under the title.
        const single = title !== reviewCount(line);
        return {
          pill: t("queue.pill.review"),
          tone: "neutral",
          meta: meta(single && reviewCount(line), what, held > 0 && tn("queue.review.waits", held)),
          primary: {
            label: t("queue.act.all_good"),
            run: () => void act(() => api.looksGood(line.changeset ?? ""), () => ({ message: t("toast.looks_good"), many: (n) => tn("toast.looks_good_many", n), undo: () => api.reopen(line.changeset ?? "") })),
          },
          menu: [show, { id: "send-back", label: t("changes.send_back"), run: () => select(true, true) }],
        };
      }
      case "intake_review": {
        // Opening the list is what clears the line (Undo puts it back); the list narrows to what the source's intake found.
        const source = line.source ?? "";
        const label = line.subject ?? source;
        const seen = () =>
          act(
            () => api.intakeSeen(source),
            (done) => ({ message: t("queue.intake_review.seen_done", { source: label }), undo: () => api.intakeUnseen(source, done.requests) }),
          );
        return {
          pill: t("queue.pill.review"),
          tone: "neutral",
          meta: meta(intakeWords(line)),
          primary: {
            label: t("queue.intake_review.open"),
            run: () => {
              props.handlers.onOpenView?.("work/changed");
              revealOrKeep("intake", source);
              void seen();
            },
          },
          menu: [{ id: "seen", label: t("queue.intake_review.seen"), run: () => void seen() }],
        };
      }
      case "send": {
        const q = (line.questions ?? []).length;
        const a = (line.actions ?? []).length;
        return {
          pill: t("queue.pill.send"),
          tone: "need",
          meta: q && a ? [tn("queue.send.n_questions", q), tn("queue.send.n_actions", a)].join(" · ") : t("queue.send.ready"),
          primary: { label: t("queue.act.review_copy") },
          menu: [],
        };
      }
      case "nudge": {
        // One line for the person: what is past its date and since when, then whatever else waits for a reply.
        const days = line.waiting_days ?? 0;
        const late = line.overdue ?? 0;
        const words =
          late > 0 && line.due
            ? [tn("queue.nudge.overdue", late, { date: day(line.due) }), line.count > late ? tn("queue.nudge.others", line.count - late) : ""].filter(Boolean).join(" · ")
            : tn("queue.nudge.meta", line.count, { days });
        const replied = (line.replies ?? 0) > 0 ? repliedWords(line.replies ?? 0, line.person_name ?? "", t) : "";
        return {
          pill: tn("queue.pill.waiting_days", days),
          tone: "warn",
          meta: meta([words, replied].filter(Boolean).join(" · ")),
          primary: { label: t("queue.act.follow_up") },
          menu: [],
        };
      }
      case "backup": {
        // The one place besides the header chip: Back up now runs it, and with no folder the button opens the step that picks one.
        const state = line.state;
        const words =
          state === "unset" ? t("queue.backup.unset") : state === "failed" ? t("queue.backup.failed") : state === "overdue" ? t("queue.backup.overdue", { age: backupAge({ age_hours: line.age_hours ?? null }, t) ?? "" }) : t("queue.backup.never");
        const run = () => void act(() => api.backup(), () => ({ message: t("toast.backup_ran") }));
        return {
          pill: t("queue.pill.backup"),
          tone: state === "failed" || state === "overdue" ? "danger" : "warn",
          meta: words,
          primary: state === "unset" ? { label: t("status.backup_set_up"), run: () => props.handlers.onOpenGuide?.("backup") } : { label: t("backup.now"), run },
          menu: [],
        };
      }
      case "escalate": {
        const days = line.waiting_days ?? 0;
        return {
          pill: tn("queue.pill.waiting_days", days),
          tone: "warn",
          meta: tn("queue.escalate.meta", line.count, { name: line.person_name ?? "" }),
          primary: { label: t("queue.escalate.pick") },
          menu: [],
        };
      }
      case "stale":
        return {
          pill: t("queue.pill.stale"),
          tone: "neutral",
          meta: tn("queue.stale.meta", line.waiting_days ?? 0),
          primary: {
            label: t("queue.stale.open"),
            run: () => {
              chooseFilters({ state: "stale" });
              props.handlers.onOpenView?.("work/open");
            },
          },
          menu: [],
        };
      case "promise": {
        const days = line.waiting_days ?? 0;
        // A date still ahead and no date at all are the waiting-ons that ask for a nudge early; only a passed date is late.
        const pill = !line.due ? t("queue.pill.undated") : days > 0 ? t("queue.pill.overdue") : t("queue.pill.due_soon");
        const meta = !line.due ? t("queue.promise.undated") : days > 0 ? tn("queue.promise.late", days, { n: days }) : days === 0 ? t("queue.promise.today") : tn("queue.promise.ahead", -days, { n: -days });
        return {
          pill,
          tone: days > 0 ? "danger" : "warn",
          meta,
          primary: promiseRow.primary,
          menu: [show, ...promiseRow.menu],
        };
      }
      case "reminder":
        return {
          pill: t("queue.pill.reminder"),
          tone: line.late ? "danger" : "warn",
          meta: undefined,
          primary: { label: t("queue.reminder.done"), run: reminderRow.done },
          menu: [reminderRow.note],
          groups: reminderRow.groups,
        };
      case "reminder_digest":
        return { pill: t("queue.pill.reminder"), tone: "neutral", meta: undefined, primary: null, menu: [] };
      case "reply":
        return { pill: t("queue.pill.reply"), tone: "warn", meta: meta(), primary: replyRow.primary, menu: replyRow.menu };
      case "sent_check":
        return { pill: t("queue.pill.sent_check"), tone: "warn", meta: meta(), primary: sentRow.primary, menu: sentRow.menu };
      case "since_yesterday":
        // Look over opens the list, and opening it is what marks it seen: the line goes until something new happens.
        return {
          pill: t("queue.pill.since"),
          tone: "neutral",
          meta: sinceWords(line, t),
          primary: { label: t("queue.since.open"), run: () => props.handlers.onOpenView?.("work/since") },
          menu: [],
        };
      case "away":
        // A note, not a task: the lines that waited arrive with it, each in its own place, so it has nothing to press.
        return { pill: t("queue.pill.away"), tone: "neutral", meta: undefined, primary: null, menu: [] };
      default:
        // A kind the screen has no words for yet still shows, so nothing the engine ranks is hidden.
        return { pill: "", tone: "neutral", meta: meta(line.waiting), primary: null, menu: [] };
    }
  })();

  useRowKeys(ref, { toggle: props.beside ? choose : opens ? () => select(!open) : undefined });
  const project = props.mixed && line.project_name ? <span className={styles.tag}>{line.project_name}</span> : null;
  const onClick = (event: React.MouseEvent) => {
    if ((event.target as HTMLElement).closest("button, a, input, textarea, select, [role='menuitem']")) return;
    if (props.beside) select(true);
    else if (opens) select(!open);
  };
  const primary: ReactNode = d.primary ? (
    <>
      {d.other && (
        <Button size="sm" aria-describedby={`${detailId}-title`} onClick={d.other.run}>
          {d.other.label}
        </Button>
      )}
      <Button
        size="sm"
        variant="primary"
        data-key="primary"
        aria-expanded={!d.primary.run && opens && !props.beside ? open : undefined}
        aria-controls={!d.primary.run && opens && !props.beside ? detailId : undefined}
        aria-describedby={`${detailId}-title`}
        onClick={d.primary.run ?? choose}
      >
        {d.primary.label}
      </Button>
    </>
  ) : undefined;
  // A line settled somewhere else stays where it was, said so and with nothing to press, until the person moves on.
  if (props.ghost)
    return (
      <Row
        as="div"
        ref={ref}
        data-queue-line={line.kind}
        data-line-key={line.key}
        data-ghost=""
        aria-label={t("queue.settled_named", { title })}
        role="group"
        pill={d.pill ? <Pill tone="neutral">{d.pill}</Pill> : undefined}
        title={<s id={`${detailId}-title`}>{title}</s>}
        meta={t("queue.settled")}
      />
    );
  return (
    <Row
      as="div"
      ref={ref}
      selected={open}
      data-queue-line={line.kind}
      data-line-key={line.key}
      aria-label={title}
      role="group"
      pill={d.pill ? <Pill tone={d.tone}>{d.pill}</Pill> : undefined}
      title={
        <span id={`${detailId}-title`}>
          {project}
          {title}
        </span>
      }
      meta={d.meta || undefined}
      primary={primary}
      menu={d.menu.length > 0 || (d.groups?.length ?? 0) > 0 ? <RowMenu label={title} actions={d.menu} groups={d.groups} /> : undefined}
      onClick={onClick}
    >
      {line.kind === "reminder_digest" && <ReminderItems line={line} />}
      {line.kind === "reminder" && reminderRow.form}
      {line.kind === "reply" && (
        <>
          <ReplyDraft line={line} />
          {replyRow.form}
        </>
      )}
      {(inPlace || promiseRow.form) && (
        <>
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
          {promiseRow.form}
        </>
      )}
    </Row>
  );
}
