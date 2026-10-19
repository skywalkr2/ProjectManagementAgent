// Scheduled work (design 7.9): one row per job with how often it runs, on or off in words, and its last run. Shown in Settings
// under Backups and sync; with no jobs there is nothing to show.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { dayAndTime } from "../lib/dates";
import { readable, readableTail } from "../lib/records";
import { useWords } from "../lib/wording";

// ---- scheduled work ------------------------------------------------------------------------------------------------

const OUTCOMES: Record<string, string> = { ok: "setup.job_ok", failed: "setup.job_failed" };

export function JobsPanel() {
  const { t, tn } = useWords();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  const rows = jobs.data ?? [];
  if (rows.length === 0) return null;
  return (
    <section className="panel-section" aria-labelledby="jobs-title">
      <div className="heading">
        <h3 id="jobs-title">{t("setup.jobs")}</h3>
      </div>
      <ul className="queue">
        {rows.map((job) => {
          const outcome = job.last_outcome ? t(OUTCOMES[job.last_outcome] ?? "setup.job_other", { outcome: readable(job.last_outcome) }) : "";
          const last = job.last_run_at ? t("setup.job_last", { when: dayAndTime(job.last_run_at), outcome }) : t("setup.job_never");
          return (
            <li className="line" key={job.name}>
              <div className="row">
                <span className={`kind ${job.enabled ? "k-send" : "k-done"}`}>{t(job.enabled ? "setup.job_on" : "setup.job_off")}</span>
                <div className="text">
                  <strong>{readableTail(job.name)}</strong>
                  <span className="sub">{tn("setup.job_every", job.every_minutes)}</span>
                  <span className="sub">{last}</span>
                  {job.last_error && <span className="sub problem-note">{job.last_error}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
