// The header: workspace name, live status, backup age (with a nag when there is no off-device backup), hand in, help.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { time } from "../lib/dates";
import type { LiveState } from "../lib/live";
import type { View } from "../App";
import { useWords } from "../lib/wording";

type T = (key: string, vars?: Record<string, string | number>) => string;

function backupText(b: S["BackupStatus"], t: T): string {
  if (!b.configured) return t("backup.none");
  if (b.age_hours === null) return b.last_error ? t("backup.failed") : t("backup.never");
  const h = b.age_hours;
  const age = h < 1 ? t("age.under_hour") : h < 48 ? t("age.hours", { n: Math.floor(h) }) : t("age.days", { n: Math.floor(h / 24) });
  return b.needs_attention ? t("backup.overdue", { age }) : t("backup.ok", { age });
}

export function Header(props: {
  workspace: string;
  live: { state: LiveState; lastUpdate: Date | null };
  view: View;
  onView: (view: View) => void;
  onHandIn: () => void;
  onHelp: () => void;
}) {
  const { t } = useWords();
  const act = useAct();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const b = status.data?.backup;
  const backupNow = () => void act(() => api.backup(), () => ({ message: t("toast.backup_ran") }));
  return (
    <header className="top">
      <div className="top-inner">
        <div className="brand">
          <b>{props.workspace}</b>
        </div>
        <nav className="tabs" aria-label={t("nav.label")}>
          {(["home", "stages", "setup"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-current={props.view === v ? "page" : undefined}
              onClick={() => props.onView(v)}
            >
              {t(`nav.${v}`)}
            </button>
          ))}
        </nav>
        <div className="top-meta">
          <span className={`live live-${props.live.state}`}>
            <i className="dot" aria-hidden="true" />
            {props.live.state === "live" && props.live.lastUpdate
              ? t("live.on", { time: time(props.live.lastUpdate) })
              : t(`live.${props.live.state}`)}
          </span>
          {status.data?.restart_needed && (
            <span className="backup attention" role="status">
              <span className="mark" aria-hidden="true">
                !
              </span>
              {t("restart.needed")}
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
        <div className="top-acts">
          <button type="button" className="btn primary" onClick={props.onHandIn}>
            {t("handin.open")}
          </button>
          <button type="button" className="btn quiet" onClick={props.onHelp} aria-label={t("help.open")}>
            ?
          </button>
        </div>
      </div>
    </header>
  );
}
