// The stages board (design 7.13): one column per stage, filling the width (a frame that scrolls inside itself past about six
// stages, never the page), a card for each item with its title, project, owners and due date. A card moves by its menu,
// by the move key and then a stage, or by dragging it to a column, all through the same stage move and its entry checks;
// a refusal is said on the card (or above the board for a drag), and Undo is in the toast as everywhere.
import { useRef, useState } from "react";
import { monthDay } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import { usePluginActions } from "../lib/plugin-actions";
import { sameItem, useMove, type StageRequest, type StageView } from "../lib/stages";
import { useWords } from "../lib/wording";
import { initials } from "../shell/status";
import { IconButton } from "../ui/IconButton";
import { MenuButton } from "../ui/MenuButton";
import { Button } from "../ui/Button";
import { useActionReview } from "./ActionReview";
import { SafeText } from "./SafeText";
import { History, WaitingLine } from "./StageParts";
import styles from "./StagesBoard.module.css";

/** More columns than this scroll inside the board's own frame instead of wrapping. */
const FIT = 6;
const NONE = "";

interface Column {
  id: string;
  label: string;
}

/** The columns for a kind: Not started, then every stage the items have, in the order their own lists give them. Items
 * in a stage the settings no longer name stay in a column of their own, after the rest. */
function columnsOf(views: StageView[], notStarted: string, unknown: string): Column[] {
  const stages: Column[] = [];
  for (const view of views) {
    let after = -1;
    for (const stage of view.stages) {
      const at = stages.findIndex((s) => s.id === stage.id);
      if (at >= 0) after = at;
      else {
        stages.splice(after + 1, 0, stage);
        after += 1;
      }
    }
  }
  const strays = views.some((v) => v.current !== null && !stages.some((s) => s.id === v.current));
  return [{ id: NONE, label: notStarted }, ...stages, ...(strays ? [{ id: "?", label: unknown }] : [])];
}

const columnOf = (view: StageView, columns: Column[]): string =>
  view.current === null ? NONE : columns.some((c) => c.id === view.current) ? view.current : "?";

export function StagesBoard(props: { kind: string; views: StageView[]; waiting: StageRequest[] }) {
  const { t } = useWords();
  const columns = columnsOf(props.views, t("stages.not_started"), t("stages.unknown_stage"));
  const { error, move } = useMove();
  const dragging = useRef<StageView | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const scroll = columns.length > FIT;
  const drop = (column: Column) => {
    const view = dragging.current;
    dragging.current = null;
    setOver(null);
    // Nothing moves into Not started or a stage that is gone; those have no move.
    if (!view || column.id === NONE || column.id === "?" || view.current === column.id) return;
    const to = view.stages.find((s) => s.id === column.id);
    if (to) void move(view, to);
  };
  return (
    <div className={styles.frame} data-scroll={scroll ? "" : undefined}>
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
      <div className={styles.board} role="group" aria-label={t("stages.board.label", { kind: props.kind })}>
        {columns.map((column) => {
          const here = props.views.filter((v) => columnOf(v, columns) === column.id);
          const headId = `board-${props.views[0]?.record.kind}-${column.id || "none"}`.replace(/[^\w-]/g, "_");
          return (
            <section
              key={column.id}
              className={styles.column}
              aria-labelledby={headId}
              data-over={over === column.id ? "" : undefined}
              onDragOver={(e) => {
                if (!dragging.current) return;
                e.preventDefault();
                setOver(column.id);
              }}
              onDragLeave={() => setOver((now) => (now === column.id ? null : now))}
              onDrop={(e) => {
                e.preventDefault();
                drop(column);
              }}
            >
              <h3 id={headId} className={styles.head}>
                <span>{column.label}</span>
                <span className={styles.count} aria-label={t("stages.board.count", { count: here.length })}>
                  {here.length || ""}
                </span>
              </h3>
              {here.length === 0 ? (
                <p className={styles.empty}>{t("stages.board.empty")}</p>
              ) : (
                <ul className={styles.cards}>
                  {here.map((view) => (
                    <Card
                      key={`${view.record.kind}/${view.record.id}`}
                      view={view}
                      waiting={props.waiting.filter((r) => sameItem(view.record, r.stage_start))}
                      onDrag={(started) => {
                        dragging.current = started ? view : null;
                        if (!started) setOver(null);
                      }}
                    />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Card(props: { view: StageView; waiting: StageRequest[]; onDrag: (started: boolean) => void }) {
  const { t } = useWords();
  const { view } = props;
  const { error, busy, move } = useMove();
  const [history, setHistory] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  const actions = usePluginActions(view.record.kind, view.record.id);
  const { start, review } = useActionReview();
  const ids = view.stages.map((s) => s.id);
  const here = view.current === null ? -1 : ids.indexOf(view.current);
  const next = view.next;
  const failed = view.checks.filter((c) => !c.passed);
  const primary = next && view.ready ? { label: t("stages.move_to", { stage: next.label }), run: () => void move(view, next) } : null;

  // Back to any earlier stage; an item that has not started may begin at any stage whose checks pass.
  const menu = [] as Array<{ id: string; label: string; run: () => void }>;
  for (let i = here - 1; i >= 0; i--) {
    const stage = view.stages[i];
    menu.push({ id: `back-${stage.id}`, label: t("stages.move_back", { stage: stage.label }), run: () => void move(view, stage) });
  }
  if (view.current === null) {
    for (const stage of view.stages) {
      if (stage.id !== next?.id || !primary) menu.push({ id: `to-${stage.id}`, label: t("stages.move_to", { stage: stage.label }), run: () => void move(view, stage) });
    }
  }
  menu.push({ id: "history", label: t(history ? "stages.history_hide" : "stages.history"), run: () => setHistory((v) => !v) });
  for (const action of actions.data ?? []) {
    menu.push({
      id: `action-${action.name}`,
      label: action.label,
      run: () => start(action, { kind: view.record.kind, id: view.record.id }, () => ref.current?.querySelector<HTMLElement>("[data-card-menu]")),
    });
  }
  const openMenu = () => ref.current?.querySelector<HTMLElement>("[data-card-menu]")?.click();
  useRowKeys(ref, { primary: primary?.run, toggle: () => setHistory((v) => !v), move: openMenu });

  const titleId = `card-${view.record.kind}-${view.record.id}`.replace(/[^\w-]/g, "_");
  const sub = !next ? t("stages.sub.last") : view.ready ? t("stages.sub.ready", { stage: next.label }) : t("stages.sub.blocked", { stage: next.label });
  const meta = [view.project, view.due ? t("stages.board.due", { date: monthDay(view.due) }) : null].filter(Boolean);
  return (
    <li
      className={styles.card}
      data-row
      tabIndex={-1}
      ref={ref}
      aria-labelledby={titleId}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", `${view.record.kind}/${view.record.id}`);
        e.dataTransfer.effectAllowed = "move";
        props.onDrag(true);
      }}
      onDragEnd={() => props.onDrag(false)}
    >
      <div className={styles.top}>
        <div id={titleId} className={styles.title}>
          <SafeText text={view.title} />
        </div>
        <MenuButton
          groups={[{ id: "actions", entries: menu }]}
          trigger={<IconButton icon="more" size="sm" label={t("menu.more", { what: view.title })} tooltip={false} data-card-menu="" />}
        />
      </div>
      {meta.length > 0 && <p className={styles.meta}>{meta.join(" · ")}</p>}
      {(view.owners ?? []).length > 0 && (
        <ul className={styles.owners}>
          {(view.owners ?? []).map((name) => (
            <li key={name} className={styles.avatar}>
              <span aria-hidden="true">{initials(name)}</span>
              <span className="sr">{name}</span>
            </li>
          ))}
        </ul>
      )}
      <p className={styles.sub}>{sub}</p>
      {!view.ready && next && failed.length > 0 && (
        <ul className={styles.reasons} aria-label={t("stages.why_not", { stage: next.label })}>
          {failed.map((c) => (
            <li key={c.id}>
              <SafeText text={c.reason} />
            </li>
          ))}
        </ul>
      )}
      {props.waiting.length > 0 && (
        <ul className="children" aria-label={t("stages.waiting_label")}>
          {props.waiting.map((r) => (
            <WaitingLine key={r.id} request={r} />
          ))}
        </ul>
      )}
      {history && <History view={view} />}
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
      {primary && (
        <div className={styles.foot}>
          <Button variant="primary" size="sm" disabled={busy} onClick={primary.run}>
            {primary.label}
          </Button>
        </div>
      )}
      {review}
    </li>
  );
}
