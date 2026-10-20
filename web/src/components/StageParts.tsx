// The pieces a stage item shows under its title, in the list and on the board: the task waiting for the person's go, and
// where the item has been.
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../lib/api";
import { dayAndTime } from "../lib/dates";
import { useRowKeys } from "../lib/keys";
import { useEstimate } from "../lib/money";
import { upperFirst, useGo, useTaskWords, type StageRequest, type StageView } from "../lib/stages";
import { useWords } from "../lib/wording";

export function WaitingLine(props: { request: StageRequest }) {
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

export function History(props: { view: StageView }) {
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
