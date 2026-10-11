// The header: one main row (workspace name, the views, and hand in / ask / help), and under it one quiet status row
// (live state, backup age with a nag when there is no off-device backup, spend, and a restart reminder). On a narrow
// screen the name and actions stay on top and the views follow as a strip that scrolls sideways inside itself.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useRestart } from "../lib/restart";
import { useRestartWhat } from "../lib/restart-for";
import { time } from "../lib/dates";
import type { LiveState } from "../lib/live";
import { panelView, type View } from "../lib/views";
import { useTotal } from "../lib/money";
import { useWords } from "../lib/wording";

type T = (key: string, vars?: Record<string, string | number>) => string;

function backupText(b: S["BackupStatus"], t: T): string {
  if (!b.configured) return t("backup.none");
  if (b.age_hours === null) return b.last_error ? t("backup.failed") : t("backup.never");
  const h = b.age_hours;
  const age = h < 1 ? t("age.under_hour") : h < 48 ? t("age.hours", { n: Math.floor(h) }) : t("age.days", { n: Math.floor(h / 24) });
  return b.needs_attention ? t("backup.overdue", { age }) : t("backup.ok", { age });
}

/** The assistant's cost so far, with the limit it is near said in words; nothing until a run has cost something. */
function spendText(sp: S["SpendStatus"], t: T, total: (usd: number) => string): { text: string; near: string | null } | null {
  if (sp.today_usd <= 0 && sp.month_usd <= 0) return null;
  const line = t("spend.line", { today: total(sp.today_usd), month: total(sp.month_usd) });
  if (!sp.warn) return { text: line, near: null };
  const both = sp.warn_today && sp.warn_month;
  return { text: line, near: t(both ? "spend.near_both" : sp.warn_today ? "spend.near_day" : "spend.near_month") };
}

export function Header(props: {
  workspace: string;
  live: { state: LiveState; lastUpdate: Date | null };
  view: View;
  onView: (view: View) => void;
  onHandIn: () => void;
  onAsk: () => void;
  onHelp: () => void;
}) {
  const { t } = useWords();
  const act = useAct();
  const restart = useRestart();
  const restartWhat = useRestartWhat();
  // While the page is asking about the restart (or doing it), that notice says it; the header only reminds afterwards.
  const remind = restart.phase !== "asking" && restart.phase !== "waiting";
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const panels = useQuery({ queryKey: ["panels"], queryFn: () => api.panels() });
  const workPanels = (panels.data ?? []).filter((p) => p.tab === "work");
  const b = status.data?.backup;
  const total = useTotal();
  const spend = status.data ? spendText(status.data.spend, t, total) : null;
  const backupNow = () => void act(() => api.backup(), () => ({ message: t("toast.backup_ran") }));
  return (
    <header className="top">
      <div className="top-inner">
        <div className="top-main">
          <div className="brand">
            <b title={props.workspace}>{props.workspace}</b>
          </div>
          <nav className="tabs" aria-label={t("nav.label")}>
            {(["home", "stages", "files", "sources"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-current={props.view === v ? "page" : undefined}
                onClick={() => props.onView(v)}
              >
                {t(`nav.${v}`)}
              </button>
            ))}
            {workPanels.map((p) => (
              <button
                key={p.name}
                type="button"
                aria-current={props.view === panelView(p.name) ? "page" : undefined}
                onClick={() => props.onView(panelView(p.name))}
              >
                {p.title}
              </button>
            ))}
            <button type="button" aria-current={props.view === "setup" ? "page" : undefined} onClick={() => props.onView("setup")}>
              {t("nav.setup")}
            </button>
            <button type="button" aria-current={props.view === "settings" ? "page" : undefined} onClick={() => props.onView("settings")}>
              {t("nav.settings")}
            </button>
            <button type="button" aria-current={props.view === "addons" ? "page" : undefined} onClick={() => props.onView("addons")}>
              {t("nav.addons")}
            </button>
          </nav>
          <div className="top-acts">
            <button type="button" className="btn primary" onClick={props.onHandIn}>
              {t("handin.open")}
            </button>
            <button type="button" className="btn" data-ask-button onClick={props.onAsk}>
              {t("ask.open")}
            </button>
            <button type="button" className="btn quiet" onClick={props.onHelp} aria-label={t("help.open")}>
              ?
            </button>
          </div>
        </div>
        <div className="top-meta">
          <span className={`live live-${props.live.state}`}>
            <i className="dot" aria-hidden="true" />
            {props.live.state === "live" && props.live.lastUpdate
              ? t("live.on", { time: time(props.live.lastUpdate) })
              : t(`live.${props.live.state}`)}
          </span>
          {status.data?.restart_needed && remind && (
            <span className="backup attention" role="status">
              <span className="mark" aria-hidden="true">
                !
              </span>
              <span>{t(status.data.can_restart ? "restart.needed" : "restart.needed_manual")}</span>
              {restartWhat && <span data-restart-for>{restartWhat}</span>}
              {status.data.can_restart && (
                <button type="button" className="btn quiet small" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
                  {t("restart.now")}
                </button>
              )}
            </span>
          )}
          {spend && (
            <span className={spend.near ? "backup attention" : "backup"} data-spend>
              {spend.near && (
                <span className="mark" aria-hidden="true">
                  !
                </span>
              )}
              {spend.near ? t("spend.with_near", { line: spend.text, near: spend.near }) : spend.text}
            </span>
          )}
          {b && (
            <span className={b.needs_attention ? "backup attention" : "backup"}>
              {b.needs_attention && (
                <span className="mark" aria-hidden="true">
                  !
                </span>
              )}
              {backupText(b, t)}
              {b.configured && (
                <button type="button" className="btn quiet small" onClick={backupNow}>
                  {t("backup.now")}
                </button>
              )}
              {!b.configured && <span className="hint">{t("backup.how")}</span>}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
