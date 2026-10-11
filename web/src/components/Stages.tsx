// Stages (design 6.26): where each item is in its steps, and moving it. One row per item with one primary action: move
// on when it is ready, otherwise the reasons it isn't. Moving back and the history are in the row's menu.
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../lib/api";
import { dayAndTime } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import {
  sameItem,
  upperFirst,
  useGo,
  useKindWords,
  useMove,
  useStageRecords,
  useStageRequests,
  useTaskWords,
  waitingForGo,
  type StageRequest,
  type StageView,
} from "../lib/stages";
import { useEstimate } from "../lib/money";
import { usePluginActions } from "../lib/plugin-actions";
import { useWords } from "../lib/wording";
import { useActionReview } from "./ActionReview";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";

export function Stages() {
  const { t } = useWords();
  const kindWords = useKindWords();
  const records = useStageRecords();
  const requests = useStageRequests();
  const waiting = waitingForGo(requests.data);
  const groups = new Map<string, StageView[]>();
  for (const view of records.data ?? []) groups.set(view.record.kind, [...(groups.get(view.record.kind) ?? []), view]);
  return (
    <>
      {records.isPending ? (
        <section className="panel-section" aria-labelledby="stages-title">
          <h2 id="stages-title" className="sr">
            {t("stages.title")}
          </h2>
          <p className="empty">{t("loading")}</p>
        </section>
      ) : records.isError ? (
        <section className="panel-section" aria-labelledby="stages-title">
          <h2 id="stages-title" className="sr">
            {t("stages.title")}
          </h2>
          <p className="empty">
            {t("stages.load_failed")}{" "}
            <button type="button" className="btn" onClick={() => void records.refetch()}>
              {t("action.try_again")}
            </button>
          </p>
        </section>
      ) : groups.size === 0 ? (
        <section className="panel-section" aria-labelledby="stages-title">
          <h2 id="stages-title" className="sr">
            {t("stages.title")}
          </h2>
          <p className="empty">{t("stages.empty")}</p>
        </section>
      ) : (
        [...groups].map(([kind, views]) => (
          <section key={kind} className="panel-section" aria-labelledby={`stages-${kind}`}>
            <div className="heading">
              <h2 id={`stages-${kind}`}>{kindWords(kind)}</h2>
            </div>
            <ul className="queue">
              {views.map((view) => (
                <StageRow
                  key={`${view.record.kind}/${view.record.id}`}
                  view={view}
                  waiting={waiting.filter((r) => sameItem(view.record, r.stage_start))}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </>
  );
}

function StageRow(props: { view: StageView; waiting: StageRequest[] }) {
  const { t } = useWords();
  const { view } = props;
  const { error, busy, move } = useMove();
  const [history, setHistory] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  const actions = usePluginActions(view.record.kind, view.record.id);
  const { start, review } = useActionReview();
  const ids = view.stages.map((s) => s.id);
  const here = view.current === null ? -1 : ids.indexOf(view.current);
  const failed = view.checks.filter((c) => !c.passed);
  const next = view.next;

  const primary = next && view.ready ? { label: t("stages.move_to", { stage: next.label }), run: () => void move(view, next) } : null;
  const menu: MenuAction[] = [];
  for (let i = here - 1; i >= 0; i--) {
    const stage = view.stages[i];
    menu.push({
      id: `back-${stage.id}`,
      label: t("stages.move_back", { stage: stage.label }),
      run: () => void move(view, stage),
    });
  }
  menu.push({ id: "history", label: t(history ? "stages.history_hide" : "stages.history"), run: () => setHistory((v) => !v) });
  for (const action of actions.data ?? []) {
    menu.push({
      id: `action-${action.name}`,
      label: action.label,
      run: () =>
        start(action, { kind: view.record.kind, id: view.record.id }, () => ref.current?.querySelector<HTMLElement>("button.more")),
    });
  }

  useRowKeys(ref, { primary: primary?.run, toggle: () => setHistory((v) => !v) });

  const stageName = view.current === null ? t("stages.not_started") : (view.current_label ?? t("stages.unknown_stage"));
  const sub = !next
    ? t("stages.sub.last")
    : view.ready
      ? t("stages.sub.ready", { stage: next.label })
      : t("stages.sub.blocked", { stage: next.label });
  const hasBody = (!view.ready && next && failed.length > 0) || props.waiting.length > 0 || history || error;
  const titleId = `st-${view.record.kind}-${view.record.id}`;

  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={titleId}>
      <div className="row">
        <span className={`kind ${view.current === null ? "k-done" : "k-review"}`}>{stageName}</span>
        <div className="text">
          <div id={titleId} className="name">
            <SafeText text={view.title} />
          </div>
          <span className="sub">{sub}</span>
        </div>
        <div className="acts">
          {primary && (
            <button type="button" className="btn primary" disabled={busy} onClick={primary.run}>
              {primary.label}
            </button>
          )}
          <RowMenu label={view.title} actions={menu} />
        </div>
      </div>
      {hasBody && (
        <div className="body">
          {!view.ready && next && failed.length > 0 && (
            <div>
              <p className="what">{t("stages.why_not", { stage: next.label })}</p>
              <ul className="children">
                {failed.map((c) => (
                  <li key={c.id} className="child single">
                    <SafeText text={c.reason} />
                  </li>
                ))}
              </ul>
            </div>
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
        </div>
      )}
      {review}
    </li>
  );
}

function WaitingLine(props: { request: StageRequest }) {
  const { t } = useWords();
  const task = useTaskWords();
  const estimate = useEstimate()(props.request.estimate_usd);
  const { error, busy, go } = useGo();
  const ref = useRef<HTMLLIElement>(null);
  const run = () => void go(props.request);
  useRowKeys(ref, { primary: run });
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="title">{upperFirst(t("stages.go_here", { task: task(props.request.task) }))}</div>
        {estimate && <div className="meta">{estimate}</div>}
      </div>
      <div className="acts">
        <button type="button" className="btn primary" disabled={busy} onClick={run}>
          {t("stages.go")}
        </button>
      </div>
      {error && (
        <p className="problem-note full" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}

function History(props: { view: StageView }) {
  const { t } = useWords();
  const { view } = props;
  const entries = useQuery({
    queryKey: ["stages", "history", view.record.kind, view.record.id],
    queryFn: () => api.stageHistory(view.record.kind, view.record.id),
  });
  const label = (id: string | null) =>
    id === null ? t("stages.not_started") : (view.stages.find((s) => s.id === id)?.label ?? t("stages.unknown_stage"));
  const who = (op: string, actor: string) => t(op === "undo" ? "stages.by_undo" : actor === "rule" ? "stages.by_rule" : "stages.by_you");
  if (entries.isPending) return <p className="hint">{t("loading")}</p>;
  if (entries.isError) return <p className="hint">{t("stages.load_failed")}</p>;
  if (entries.data.length === 0) return <p className="hint">{t("stages.history_empty")}</p>;
  return (
    <ul className="children" aria-label={t("stages.history_label")}>
      {[...entries.data].reverse().map((e) => (
        <li key={e.sequence} className="child single">
          {t("stages.history_entry", {
            from: label(e.from_stage),
            to: label(e.to_stage),
            when: dayAndTime(e.at),
            who: who(e.op, e.actor),
          })}
        </li>
      ))}
    </ul>
  );
}
