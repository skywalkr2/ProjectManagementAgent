// Today's lines for work that has stopped (design 7.7, 8.5): work held until the app restarts, and an AI account paused
// until its usage limit resets. Each is one row that says what to do first, with the one button that does it. The lines
// come from the Today queue; a line is gone once its cause is, and only the person's own click ever restarts the app.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { day, localDate, wallTime } from "../lib/dates";
import { useRestart, useRestartText } from "../lib/restart";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import styles from "./HeldLines.module.css";

type Line = S["QueueLineView"];

/** A reset time as the server wrote it, on the person's own clock: the time alone today, otherwise the day and the time. */
function resetText(iso: string): string {
  const clock = wallTime(iso);
  return iso.slice(0, 10) === localDate(new Date()) ? clock : `${day(iso)}, ${clock}`;
}

export function HeldLines(props: { onOpenAiAccounts: () => void }) {
  const queue = useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
  const lines = (queue.data ?? []).filter((line) => line.kind === "restart" || line.kind === "paused");
  if (!lines.length) return null;
  return (
    <div className={styles.lines} data-held-lines="">
      {lines.map((line) =>
        line.kind === "restart" ? (
          <RestartLine key={line.key} line={line} />
        ) : (
          <PausedLine key={line.key} line={line} onOpenAiAccounts={props.onOpenAiAccounts} />
        ),
      )}
    </div>
  );
}

function RestartLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const restart = useRestart();
  const progress = useRestartText();
  const canRestart = !!status.data?.can_restart;
  const label = tn("queue.restart", props.line.count);
  // While a restart is under way its own words replace the explanation, so the line follows the same flow as the header.
  const sub = progress && restart.phase !== "asking" ? progress : t(status.data && !canRestart ? "queue.restart.manual" : "queue.restart.sub");
  return (
    <section className={styles.line} aria-label={t("queue.restart.label")} data-queue-line="restart">
      <Pill tone="warn">{t("queue.restart.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      {canRestart && (
        <div className={styles.actions}>
          <Button size="sm" variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        </div>
      )}
    </section>
  );
}

function PausedLine(props: { line: Line; onOpenAiAccounts: () => void }) {
  const { t, tn } = useWords();
  const { line } = props;
  const label = tn("queue.paused", line.count, { account: line.account ?? "", time: line.until ? resetText(line.until) : "" });
  return (
    <section className={styles.line} aria-label={t("queue.paused.label")} data-queue-line="paused">
      <Pill tone="warn">{t("queue.paused.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{t("queue.paused.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" onClick={props.onOpenAiAccounts}>
          {t("queue.paused.open")}
        </Button>
      </div>
    </section>
  );
}
