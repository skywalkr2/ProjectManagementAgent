// Today's stage rows (design 6.26, 7.3): stage tasks waiting for the person's go, and items ready to move on.
import { useRef } from "react";
import { useRowKeys } from "../lib/keys";
import {
  sameItem,
  useGo,
  useMove,
  useStageReady,
  useStageRecords,
  useStageRequests,
  useTaskWords,
  waitingForGo,
  type StageRequest,
  type StageView,
} from "../lib/stages";
import { useWords } from "../lib/wording";
import { SafeText } from "./SafeText";

/** The rows Today adds to what needs attention. */
export function useStageToday() {
  const requests = useStageRequests();
  const records = useStageRecords();
  const ready = useStageReady();
  const waiting = waitingForGo(requests.data).map((request) => ({
    request,
    item: (records.data ?? []).find((view) => sameItem(view.record, request.stage_start)) ?? null,
  }));
  const moves = (ready.data ?? []).filter((view) => view.next && view.ready);
  return { waiting, moves, count: waiting.length + moves.length };
}

export function StageTodayRows(props: { today: ReturnType<typeof useStageToday> }) {
  return (
    <>
      {props.today.waiting.map(({ request, item }) => (
        <GoRow key={request.id} request={request} item={item} />
      ))}
      {props.today.moves.map((view) => (
        <ReadyRow key={`${view.record.kind}/${view.record.id}`} view={view} />
      ))}
    </>
  );
}

function GoRow(props: { request: StageRequest; item: StageView | null }) {
  const { t } = useWords();
  const task = useTaskWords();
  const { error, busy, go } = useGo();
  const ref = useRef<HTMLLIElement>(null);
  const run = () => void go(props.request);
  useRowKeys(ref, { primary: run });
  const titleId = `go-${props.request.id}`;
  const title = props.item?.title ?? t("stages.item_unknown");
  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-held">{t("changes.state.needs_you")}</span>
        <div className="text">
          <div id={titleId} className="name">
            <SafeText text={t("stages.go_waiting", { title, task: task(props.request.task) })} />
          </div>
        </div>
        <div className="acts">
          <button type="button" className="btn primary" disabled={busy} onClick={run}>
            {t("stages.go")}
          </button>
        </div>
      </div>
      {error && (
        <div className="body">
          <p className="problem-note" role="alert">
            {error}
          </p>
        </div>
      )}
    </li>
  );
}

function ReadyRow(props: { view: StageView }) {
  const { t } = useWords();
  const { view } = props;
  const { error, busy, move } = useMove();
  const ref = useRef<HTMLLIElement>(null);
  const next = view.next!;
  const run = () => void move(view, next);
  useRowKeys(ref, { primary: run });
  const titleId = `ready-${view.record.kind}-${view.record.id}`;
  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-send">{t("stages.pill_ready")}</span>
        <div className="text">
          <div id={titleId} className="name">
            <SafeText text={t("stages.ready_for", { title: view.title, stage: next.label })} />
          </div>
        </div>
        <div className="acts">
          <button type="button" className="btn primary" disabled={busy} onClick={run}>
            {t("stages.move_to", { stage: next.label })}
          </button>
        </div>
      </div>
      {error && (
        <div className="body">
          <p className="problem-note" role="alert">
            {error}
          </p>
        </div>
      )}
    </li>
  );
}
