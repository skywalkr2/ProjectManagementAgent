// This week (design 7.7): what is due by the end of the week, who is waiting on the person and which meetings to hold,
// across projects. Below 2560px it is a section of Today folded to one line; from 2560px it is a panel of the rail; and it
// is what the inspector shows when no line is selected. It is never counted in Today's heading or the menu.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, type S } from "../lib/api";
import { day, wallTime } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";
import { Empty, Failed, RailPanel } from "./RailPanel";
import styles from "./Today.module.css";

type Week = S["ThisWeekView"];
type T = ReturnType<typeof useWords>["t"];
type Tn = ReturnType<typeof useWords>["tn"];

export function useThisWeek() {
  return useQuery({ queryKey: ["today", "week"], queryFn: api.thisWeek });
}

/** "3 due · 2 waiting on you · 4 meetings": the one line a folded week says. */
export function weekSummary(week: Week, tn: Tn): string {
  return [
    week.due.length > 0 ? tn("today.week.due", week.due.length) : "",
    week.waiting.length > 0 ? tn("today.week.waiting", week.waiting.length) : "",
    week.meetings.length > 0 ? tn("today.week.meetings", week.meetings.length) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function whenOf(m: Week["meetings"][number], t: T): string {
  const first = m.days[0] ?? m.start.slice(0, 10);
  return [day(first), m.all_day ? t("today.agenda.all_day") : wallTime(m.start)].join(" ");
}

/** The three groups of the week; a group with nothing in it is left out. */
export function WeekBody(props: { week: Week }) {
  const { t, tn } = useWords();
  const { week } = props;
  if (week.due.length === 0 && week.waiting.length === 0 && week.meetings.length === 0) return <Empty text={t("today.week.empty", { date: day(week.last) })} />;
  return (
    <div className={styles.weekBody}>
      <p className="hint">{t("today.week.through", { date: day(week.last) })}</p>
      {week.due.length > 0 && (
        <div className="tb-group" data-group="due">
          <h3 className="tb-group-head">{t("today.week.due_head")}</h3>
          <ul className="tb-list">
            {week.due.map((item) => (
              <li key={item.action} className="tb-row">
                <span className="tb-when">{day(item.due)}</span>
                <div className="tb-what">
                  <div className="tb-title">{item.text}</div>
                  <div className="tb-meta">
                    {[item.project_name, item.mine ? t("today.priorities.yours") : (item.owners ?? []).map((o) => o.name).join(", ")].filter(Boolean).join(" · ")}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {week.waiting.length > 0 && (
        <div className="tb-group" data-group="waiting">
          <h3 className="tb-group-head">{t("today.week.waiting_head")}</h3>
          <ul className="tb-list">
            {week.waiting.map((w) => (
              <li key={w.person} className="tb-row">
                <div className="tb-what">
                  <div className="tb-title">{tn("today.week.waiting_row", w.count, { name: w.person_name })}</div>
                  {w.due && <div className="tb-meta">{t("today.week.waiting_since", { date: day(w.due) })}</div>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {week.meetings.length > 0 && (
        <div className="tb-group" data-group="meetings">
          <h3 className="tb-group-head">{t("today.week.meetings_head")}</h3>
          <ul className="tb-list">
            {week.meetings.map((m, i) => (
              <li key={`${m.snapshot}:${i}`} className="tb-row">
                <span className="tb-when">{whenOf(m, t)}</span>
                <div className="tb-what">
                  <div className="tb-title">{m.title}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The week folded to one line below 2560px: its heading says what is in it, and a press opens it. */
export function ThisWeekSection() {
  const { t, tn } = useWords();
  const week = useThisWeek();
  const [open, setOpen] = useState(false);
  const id = useId();
  const summary = week.data ? weekSummary(week.data, tn) : "";
  return (
    <section className={styles.week} aria-labelledby={`${id}-head`} data-week="section">
      <h2 id={`${id}-head`} className={styles.weekHead}>
        <button type="button" className={styles.weekToggle} aria-expanded={open} aria-controls={`${id}-body`} onClick={() => setOpen(!open)}>
          <span>{t("today.week.title")}</span>
          <span className={styles.weekSummary}>{week.isError ? t("today.week.load_failed") : summary || (week.data ? t("today.week.nothing") : "")}</span>
        </button>
      </h2>
      {open && (
        <div id={`${id}-body`}>
          {week.isPending ? <Skeleton /> : week.isError ? <Failed text={t("today.week.load_failed")} retry={() => void week.refetch()} /> : week.data ? <WeekBody week={week.data} /> : null}
        </div>
      )}
    </section>
  );
}

/** The week as a panel of the rail, from 2560px. */
export function ThisWeekPanel() {
  const { t, tn } = useWords();
  const week = useThisWeek();
  return (
    <RailPanel id="week" title={t("today.week.title")} count={null} countText={week.data ? weekSummary(week.data, tn) : ""}>
      {week.isPending ? <Skeleton /> : week.isError ? <Failed text={t("today.week.load_failed")} retry={() => void week.refetch()} /> : week.data ? <WeekBody week={week.data} /> : null}
    </RailPanel>
  );
}

/** What the inspector shows when no line is selected: the week, with its summary as the lead. */
export function ThisWeekInspector() {
  const { t, tn } = useWords();
  const week = useThisWeek();
  if (week.isPending) return <Skeleton />;
  if (week.isError || !week.data) return <Failed text={t("today.week.load_failed")} retry={() => void week.refetch()} />;
  const summary = weekSummary(week.data, tn);
  return (
    <div data-week="inspector">
      <h3 className={styles.weekInspectorHead}>
        {t("today.week.title")}
        {summary && <span className={styles.weekSummary}>{summary}</span>}
      </h3>
      <WeekBody week={week.data} />
    </div>
  );
}
