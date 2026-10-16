// Today's stage rows (design 6.26, 7.3): stage tasks waiting for the person's go, and items ready to move on.
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
import { useEstimate } from "../lib/money";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
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
  const estimate = useEstimate()(props.request.estimate_usd);
  const { error, busy, go } = useGo();
  const run = () => void go(props.request);
  const titleId = `go-${props.request.id}`;
  const title = props.item?.title ?? t("stages.item_unknown");
  return (
    <Row
      aria-labelledby={titleId}
      pill={<Pill tone="warn">{t("changes.state.needs_you")}</Pill>}
      title={
        <span id={titleId}>
          <SafeText text={t("stages.go_waiting", { title, task: task(props.request.task) })} />
        </span>
      }
      meta={estimate || undefined}
      primary={
        <Button size="sm" variant="primary" data-key="primary" disabled={busy} onClick={run}>
          {t("stages.go")}
        </Button>
      }
    >
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
    </Row>
  );
}

function ReadyRow(props: { view: StageView }) {
  const { t } = useWords();
  const { view } = props;
  const { error, busy, move } = useMove();
  const next = view.next!;
  const run = () => void move(view, next);
  const titleId = `ready-${view.record.kind}-${view.record.id}`;
  return (
    <Row
      aria-labelledby={titleId}
      pill={<Pill tone="need">{t("stages.pill_ready")}</Pill>}
      title={
        <span id={titleId}>
          <SafeText text={t("stages.ready_for", { title: view.title, stage: next.label })} />
        </span>
      }
      primary={
        <Button size="sm" variant="primary" data-key="primary" disabled={busy} onClick={run}>
          {t("stages.move_to", { stage: next.label })}
        </Button>
      }
    >
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
    </Row>
  );
}
