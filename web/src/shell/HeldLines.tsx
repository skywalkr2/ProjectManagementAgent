// Today's lines for work that has stopped (design 7.7, 8.5): work held until the app restarts, an AI account paused
// until its usage limit resets, and the synced folder that can't be used until the person settles which copy to keep.
// Each is one row that says what to do first, with the one button that does it. The lines come from the Today queue; a
// line is gone once its cause is, and only the person's own click ever restarts the app.
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

export function HeldLines(props: { onOpenAiAccounts: () => void; onOpenHandover: () => void }) {
  const queue = useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
  const lines = (queue.data ?? []).filter((line) => line.kind === "restart" || line.kind === "paused" || line.kind === "handover");
  if (!lines.length) return null;
  return (
    <div className={styles.lines} data-held-lines="">
      {lines.map((line) =>
        line.kind === "restart" ? (
          <RestartLine key={line.key} line={line} />
        ) : line.kind === "handover" ? (
          <HandoverLine key={line.key} line={line} onOpen={props.onOpenHandover} />
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

function HandoverLine(props: { line: Line; onOpen: () => void }) {
  const { t } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const restart = useRestart();
  const state = props.line.state ?? "diverged";
  const computer = props.line.text ?? "";
  const text =
    state === "chosen"
      ? t("queue.handover.chosen")
      : state === "elsewhere"
        ? computer
          ? t("queue.handover.elsewhere", { computer })
          : t("queue.handover.elsewhere_unknown")
        : t("queue.handover.diverged");
  // Once a copy is chosen the one thing left is the restart, and only the person's click restarts.
  const canRestart = state === "chosen" && !!status.data?.can_restart;
  return (
    <section className={styles.line} aria-label={t("queue.handover.label")} data-queue-line="handover">
      <Pill tone="warn">{t("queue.handover.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t(`queue.handover.${state}_sub`)}</p>
      </div>
      <div className={styles.actions}>
        {canRestart && (
          <Button size="sm" variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        )}
        <Button size="sm" variant={canRestart ? "secondary" : "primary"} onClick={props.onOpen}>
          {t(`queue.handover.open_${state}`)}
        </Button>
      </div>
    </section>
  );
}
