// The status chip and its popover (design 7.1). The chip says the worst state in a word; the popover lists every state
// with its action: when the screen last updated and Refresh, the backup and Back up now, a restart waiting for the person's
// Restart now (the app never restarts on its own), the assistant when it can't do its work yet, and the spend near a limit.
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogTrigger, Popover } from "react-aria-components";
import { RestartNotice, useRestart } from "../lib/restart";
import { useRestartWhat } from "../lib/restart-for";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { time } from "../lib/dates";
import type { LiveState } from "../lib/live";
import { useTotal } from "../lib/money";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { StatusChip } from "../ui/StatusChip";
import { afterClose } from "../ui/afterClose";
import { isWarn, worstState, type StatusKind } from "./status";
import styles from "./StatusMenu.module.css";

type T = (key: string, vars?: Record<string, string | number>) => string;

function backupText(b: S["BackupStatus"], t: T): string {
  if (!b.configured) return t("backup.none");
  if (b.age_hours === null) return b.last_error ? t("backup.failed") : t("backup.never");
  const h = b.age_hours;
  const age = h < 1 ? t("age.under_hour") : h < 48 ? t("age.hours", { n: Math.floor(h) }) : t("age.days", { n: Math.floor(h / 24) });
  return b.needs_attention ? t("backup.overdue", { age }) : t("backup.ok", { age });
}

/** The assistant's cost so far, with the limit it is near said in words; nothing until a run has cost something. */
function spendText(sp: S["SpendStatus"], t: T, total: (usd: number) => string): { text: string; near: boolean } | null {
  if (sp.today_usd <= 0 && sp.month_usd <= 0) return null;
  const line = t("spend.line", { today: total(sp.today_usd), month: total(sp.month_usd) });
  if (!sp.warn) return { text: line, near: false };
  const both = sp.warn_today && sp.warn_month;
  const near = t(both ? "spend.near_both" : sp.warn_today ? "spend.near_day" : "spend.near_month");
  return { text: t("spend.with_near", { line, near }), near: true };
}

/** Closes the popover, then runs an action that takes focus somewhere of its own. */
function leave(close: () => void, run: () => void) {
  close();
  afterClose(run);
}

const CHIP_WORD: Record<StatusKind, string> = {
  connecting: "live.connecting",
  offline: "live.offline",
  restart: "status.chip_restart",
  restarting: "status.chip_restarting",
  backup: "status.chip_backup",
  spend: "status.chip_spend",
  live: "status.chip_live",
};

export function StatusMenu(props: {
  live: { state: LiveState; lastUpdate: Date | null; refresh: () => void };
  demo: boolean;
  /** Opens the setup guide, at a step when one is named. */
  onOpenGuide: (step?: string) => void;
}) {
  const { t } = useWords();
  const act = useAct();
  const restart = useRestart();
  const what = useRestartWhat();
  const total = useTotal();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const kind = worstState({ live: props.live.state, status: status.data, restartPhase: restart.phase });
  const word = t(CHIP_WORD[kind]);
  const b = status.data?.backup;
  const ai = status.data?.ai;
  const spend = status.data ? spendText(status.data.spend, t, total) : null;
  const restartShown = restart.phase !== "idle" || !!status.data?.restart_needed;
  const backupNow = () => void act(() => api.backup(), () => ({ message: t("toast.backup_ran") }));
  const updates =
    props.live.state === "live" && props.live.lastUpdate
      ? t("live.on", { time: time(props.live.lastUpdate) })
      : t(`live.${props.live.state}`);
  const aiText =
    ai && ai.state !== "ok"
      ? ai.state === "failing"
        ? ai.detail
          ? t("ai.failing.what", { reason: ai.detail })
          : t("ai.failing.what_unknown")
        : t(`ai.${ai.state}.what`)
      : "";
  return (
    <DialogTrigger>
      <StatusChip tone={isWarn(kind) ? "warn" : "ok"} aria-label={t("status.chip_named", { state: word })} data-status={kind}>
        {word}
      </StatusChip>
      <Popover placement="bottom end" className={styles.popover}>
        <Dialog aria-label={t("status.title")} className={styles.dialog}>
          {({ close }) => (
          <>
          <ul className={styles.states}>
            <li className={[styles.state, props.live.state === "offline" ? styles.warn : ""].join(" ")} data-state="updates">
              <p className={styles.name}>{t("status.updates")}</p>
              <p className={styles.text}>{updates}</p>
              <Button size="sm" icon="refresh" onClick={props.live.refresh}>
                {t("status.refresh")}
              </Button>
            </li>
            {b && (
              <li className={[styles.state, b.needs_attention ? styles.warn : ""].join(" ")} data-state="backup">
                <p className={styles.name}>{t("status.backup")}</p>
                <p className={styles.text}>{backupText(b, t)}</p>
                {b.configured ? (
                  <Button size="sm" onClick={backupNow}>
                    {t("backup.now")}
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => leave(close, () => props.onOpenGuide("backup"))}>
                    {t("status.backup_set_up")}
                  </Button>
                )}
              </li>
            )}
            {restartShown && (
              <li className={[styles.state, styles.warn].join(" ")} data-state="restart">
                <p className={styles.name}>{t("status.restart")}</p>
                {restart.phase === "idle" ? (
                  <>
                    <p className={`${styles.text} ${styles.full}`}>{t(status.data?.can_restart ? "restart.needed" : "restart.needed_manual")}</p>
                    {what && (
                      <p className={styles.note} data-restart-for>
                        {what}
                      </p>
                    )}
                    {status.data?.can_restart && (
                      <Button size="sm" variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
                        {t("restart.now")}
                      </Button>
                    )}
                  </>
                ) : (
                  <div className={styles.full}>
                    <RestartNotice what={what} live={false} />
                  </div>
                )}
              </li>
            )}
            {ai && ai.state !== "ok" && (
              <li className={[styles.state, styles.warn].join(" ")} data-state="assistant" data-ai-state={ai.state}>
                <p className={styles.name}>{t("status.assistant")}</p>
                <p className={`${styles.text} ${styles.full}`}>{t(`ai.${ai.state}.title`)}</p>
                <p className={styles.note}>{aiText}</p>
                <p className={styles.note}>{t(`ai.${ai.state}.todo`)}</p>
                <Button size="sm" onClick={() => leave(close, () => props.onOpenGuide("ai"))}>
                  {t("status.assistant_open")}
                </Button>
              </li>
            )}
            {spend && (
              <li className={[styles.state, spend.near ? styles.warn : ""].join(" ")} data-state="spend" data-spend>
                <p className={styles.name}>{t("status.spend")}</p>
                <p className={`${styles.text} ${styles.full}`}>{spend.text}</p>
              </li>
            )}
            {props.demo && (
              <li className={styles.state} data-state="demo">
                <p className={styles.name}>{t("demo.region")}</p>
                <p className={`${styles.text} ${styles.full}`}>{t("demo.text")}</p>
              </li>
            )}
          </ul>
          </>
          )}
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
