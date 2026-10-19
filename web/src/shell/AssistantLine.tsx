// The header's line that says the assistant is alive (design 7.1): its name, an icon and a few words, such as when it last
// ran. It turns amber when work is held up and red when the assistant can't do its work, in the words and the icon as well
// as the color. Its popover shows today's runs by account, what waits for the assistant and the order the accounts are
// tried in. It sits beside the status chip, whose own states it reuses and does not repeat.
import { useQuery } from "@tanstack/react-query";
import { Button as AriaButton, Dialog, DialogTrigger, Popover } from "react-aria-components";
import { useAccountNames } from "../lib/account-names";
import { api, type S } from "../lib/api";
import { wallWhen } from "../lib/dates";
import { useRestart } from "../lib/restart";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Icon, type IconName } from "../ui/Icon";
import { afterClose } from "../ui/afterClose";
import { aliveState, type AliveKind, type AliveTone } from "./status";
import styles from "./AssistantLine.module.css";

const ICON: Record<AliveTone, IconName> = { ok: "check", warn: "alert", bad: "close" };

/** The words after the icon: the problem when there is one, otherwise when the assistant last ran. */
function sayText(kind: AliveKind, a: S["AssistantStatus"], t: (key: string, vars?: Record<string, string | number>) => string, nameOf: (id: string) => string): string {
  const when = a.last_run_at ? wallWhen(a.last_run_at) : "";
  switch (kind) {
    case "fine":
      return a.last_run_at ? t("alive.last_run", { time: when }) : t("alive.no_runs");
    case "run_failed":
      return t("alive.say.run_failed", { time: when });
    case "paused": {
      const first = a.paused[0];
      return t("alive.say.paused", { account: nameOf(first.account), time: wallWhen(first.until) });
    }
    default:
      return t(`alive.say.${kind}`);
  }
}

/** The assistant's alive state in words, for the line beside the status chip and for the chip's popover on a phone; null
 * until the status has answered. */
export function useAlive(): { kind: AliveKind; tone: AliveTone; say: string; icon: IconName } | null {
  const { t } = useWords();
  const restart = useRestart();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const nameOf = useAccountNames();
  if (!status.data) return null;
  const { kind, tone } = aliveState({ status: status.data, restartPhase: restart.phase });
  return { kind, tone, say: sayText(kind, status.data.assistant, t, nameOf), icon: ICON[tone] };
}

export function AssistantLine(props: { onOpenGuide: (step?: string) => void }) {
  const { t, tn, has } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const nameOf = useAccountNames();
  const alive = useAlive();
  if (!status.data || !alive) return null;
  const a = status.data.assistant;
  const { kind, tone, say } = alive;
  const work = (tier: string) => (has(`welcome.ai.tier.${tier}`) ? t(`welcome.ai.tier.${tier}`) : tier);
  const toGuide = (close: () => void) => {
    close();
    afterClose(() => props.onOpenGuide("ai"));
  };
  return (
    <DialogTrigger>
      <AriaButton className={styles.line} data-tone={tone} data-alive={kind}>
        <span className={styles.name}>{t("alive.name")}</span>
        <Icon name={ICON[tone]} size={16} label={t(`alive.icon.${tone}`)} />
        <span className={styles.say}>{say}</span>
      </AriaButton>
      <Popover placement="bottom end" className={styles.popover}>
        <Dialog aria-label={t("alive.title")} className={styles.dialog}>
          {({ close }) => (
            <ul className={styles.sections}>
              {tone !== "ok" && (
                <li className={[styles.section, styles.problem].join(" ")} data-section="problem" data-tone={tone}>
                  <p className={styles.heading}>{t("alive.name")}</p>
                  <p className={styles.text}>
                    <Icon name={ICON[tone]} size={16} /> {say}
                  </p>
                  {(kind === "failing" || kind === "not_set_up") && (
                    <Button size="sm" onClick={() => toGuide(close)}>
                      {t("alive.open")}
                    </Button>
                  )}
                </li>
              )}
              <li className={styles.section} data-section="runs">
                <p className={styles.heading}>{t("alive.runs")}</p>
                {a.runs_today.length === 0 ? (
                  <p className={styles.text}>{t("alive.runs_none")}</p>
                ) : (
                  <ul className={styles.rows}>
                    {a.runs_today.filter((r) => r.count > 0).map((r) => (
                      <li key={r.account} className={styles.text}>
                        {tn("alive.runs_row", r.count, { account: nameOf(r.account), failed: r.failed ? t("alive.runs_failed", { failed: r.failed }) : "" })}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
              <li className={styles.section} data-section="queue">
                <p className={styles.heading}>{t("alive.queue")}</p>
                <p className={styles.text}>
                  {a.queued > 0 && a.oldest_queued_since
                    ? tn("alive.queue_some", a.queued, { time: wallWhen(a.oldest_queued_since) })
                    : t("alive.queue_none")}
                </p>
              </li>
              <li className={styles.section} data-section="chains">
                <p className={styles.heading}>{t("alive.chains")}</p>
                {a.chains.length === 0 ? (
                  <p className={styles.text}>{t("alive.chain_none")}</p>
                ) : (
                  <ul className={styles.rows}>
                    {a.chains.map((c) => (
                      <li key={c.tier} className={styles.text}>
                        {t("alive.chain_row", { work: work(c.tier), accounts: c.accounts.map(nameOf).join(t("alive.chain_join")) })}
                      </li>
                    ))}
                  </ul>
                )}
                {a.paused.map((p) => (
                  <p key={p.account} className={styles.note}>
                    {t("alive.paused_until", { account: nameOf(p.account), time: wallWhen(p.until) })}
                  </p>
                ))}
              </li>
            </ul>
          )}
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
