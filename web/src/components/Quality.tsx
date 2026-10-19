// The Quality screen (design 6.32, "Measures"): one section for each measure, each a sentence with its number out of its
// denominator and a short list by day, never a bare percentage and never a colour. The person's own daily count of
// promises the app missed is entered here: a day, how many promises are on their own list, how many of those the app
// didn't have. Saving acts at once with an Undo toast, and saving the same day again corrects it. The screen is not on
// Today: status and progress never go there.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { localDate, monthDay } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { LoadFailed } from "../ui/LoadFailed";
import { Skeleton } from "../ui/Skeleton";
import styles from "./Quality.module.css";

type View = S["QualityView"];

/** A whole number typed in a field, or null when it isn't one. */
function whole(text: string): number | null {
  return /^\d+$/.test(text.trim()) ? Number(text.trim()) : null;
}

function Section(props: { id: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-labelledby={`${props.id}-title`} data-quality-section={props.id}>
      <h2 id={`${props.id}-title`}>{props.title}</h2>
      {props.hint && <p className="hint">{props.hint}</p>}
      {props.children}
    </section>
  );
}

function Empty(props: { text: string }) {
  return <p className="empty">{props.text}</p>;
}

function Days(props: { label: string; rows: string[] }) {
  if (props.rows.length === 0) return null;
  return (
    <ul className={styles.list} aria-label={props.label}>
      {props.rows.map((row) => (
        <li key={row}>{row}</li>
      ))}
    </ul>
  );
}

function CountForm(props: { view: View; focusFirst: boolean }) {
  const { t } = useWords();
  const act = useAct();
  const base = useId();
  const dateField = useRef<HTMLInputElement>(null);
  const today = props.view.until || localDate(new Date());
  const [date, setDate] = useState("");
  const [present, setPresent] = useState("");
  const [missed, setMissed] = useState("");
  const [busy, setBusy] = useState(false);
  const day = date || today;
  const entry = props.view.counts.days.find((d) => d.day === day);
  // The cursor starts in the first field once the screen has what it needs.
  useEffect(() => {
    if (props.focusFirst) dateField.current?.focus();
  }, [props.focusFirst]);
  // A day that has a count shows it, so saving again corrects it.
  useEffect(() => {
    setPresent(entry ? String(entry.present) : "");
    setMissed(entry ? String(entry.missed) : "");
  }, [day, entry?.present, entry?.missed]); // eslint-disable-line react-hooks/exhaustive-deps

  const counted = whole(present);
  const gone = whole(missed);
  const tooMany = counted !== null && gone !== null && gone > counted;
  const ready = counted !== null && gone !== null && !tooMany && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (counted === null || gone === null || !ready) return;
    setBusy(true);
    await act(
      () => api.saveCount(day, { present: counted, missed: gone }),
      (saved) => ({
        message: t(saved.previous ? "quality.counts.corrected" : "quality.counts.saved", { day: monthDay(day), missed: gone, present: counted }),
        undo: () => api.undoCount(day, saved.previous ?? null),
      }),
    );
    setBusy(false);
  };

  return (
    <form className={styles.form} onSubmit={(e) => void submit(e)} aria-label={t("quality.counts.form")}>
      <div className="field">
        <label htmlFor={`${base}-date`}>{t("quality.counts.date")}</label>
        <input id={`${base}-date`} ref={dateField} type="date" value={day} max={today} onChange={(e) => setDate(e.target.value)} required />
      </div>
      <div className="field">
        <label htmlFor={`${base}-present`}>{t("quality.counts.present")}</label>
        <input id={`${base}-present`} type="number" inputMode="numeric" min={0} step={1} value={present} onChange={(e) => setPresent(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${base}-missed`}>{t("quality.counts.missed")}</label>
        <input
          id={`${base}-missed`}
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={missed}
          aria-invalid={tooMany || undefined}
          aria-describedby={tooMany ? `${base}-problem` : undefined}
          onChange={(e) => setMissed(e.target.value)}
        />
      </div>
      <div className={styles.act}>
        <Button type="submit" variant="primary" disabled={!ready} reason={busy || tooMany ? undefined : t("quality.counts.why_disabled")}>
          {t(busy ? "quality.counts.saving" : "quality.counts.save")}
        </Button>
      </div>
      {tooMany && (
        <p id={`${base}-problem`} className="problem-note" role="alert">
          {t("quality.counts.too_many")}
        </p>
      )}
    </form>
  );
}

export function Quality(props: { onBack: () => void }) {
  const { t, tn, has } = useWords();
  const page = useQuery({ queryKey: ["quality"], queryFn: api.quality });
  const view = page.data;
  const work = (kind: string) => (has(`task.${kind}`) ? t(`task.${kind}`) : t("task.other"));
  // The cursor goes to the form's first field once, when the figures first arrive.
  const [arrived, setArrived] = useState(false);
  useEffect(() => {
    if (view && !arrived) setArrived(true);
  }, [view, arrived]);

  return (
    <section className="panel-section" aria-labelledby="quality-title">
      <div className="heading">
        <h1 id="quality-title">{t("quality.title")}</h1>
      </div>
      <p className="hint">
        <Button size="sm" variant="ghost" onClick={props.onBack}>
          {t("quality.back")}
        </Button>
      </p>
      {page.isPending ? (
        <Skeleton />
      ) : page.isError || !view ? (
        <LoadFailed message={t("quality.load_failed")} onRetry={() => void page.refetch()} />
      ) : (
        <>
          <p className={styles.window} data-quality-window="">
            {t("quality.window", { from: monthDay(view.since), to: monthDay(view.until) })}
          </p>
          <p className="hint">{t("quality.intro")}</p>
          <div className={styles.sections}>
            <Section id="quality-closes" title={t("quality.closes.title")} hint={t("quality.closes.hint")}>
              {view.closes.total === 0 ? (
                <Empty text={t("quality.closes.empty")} />
              ) : (
                <>
                  <p className={styles.sum}>{tn("quality.closes.sum", view.closes.total, { silent: view.closes.silent })}</p>
                  <Days
                    label={t("quality.day_list")}
                    rows={view.closes.days.map((d) => tn("quality.closes.day", d.total, { day: monthDay(d.day), silent: d.silent }))}
                  />
                </>
              )}
            </Section>

            <Section id="quality-endings" title={t("quality.endings.title")} hint={t("quality.endings.hint")}>
              {view.endings.made === 0 ? (
                <Empty text={t("quality.endings.empty")} />
              ) : (
                <>
                  <p className={styles.sum}>{tn("quality.endings.sum", view.endings.made, { wrong: view.endings.wrong })}</p>
                  <p>{t("quality.endings.how", { declined: view.endings.declined, undone: view.endings.undone, reopened: view.endings.reopened })}</p>
                  <Days
                    label={t("quality.day_list")}
                    rows={view.endings.days.map((d) => tn("quality.endings.day", d.made, { day: monthDay(d.day), wrong: d.wrong }))}
                  />
                </>
              )}
            </Section>

            <Section id="quality-counts" title={t("quality.counts.title")} hint={t("quality.counts.hint")}>
              {view.counts.entered === 0 ? (
                <Empty text={t("quality.counts.empty")} />
              ) : (
                <>
                  <p className={styles.sum}>{tn("quality.counts.sum", view.counts.present, { missed: view.counts.missed })}</p>
                  <Days
                    label={t("quality.day_list")}
                    rows={view.counts.days.map((d) => tn("quality.counts.day", d.present, { day: monthDay(d.day), missed: d.missed }))}
                  />
                </>
              )}
              <CountForm view={view} focusFirst={arrived} />
            </Section>

            <Section id="quality-missed" title={t("quality.missed.title")} hint={t("quality.missed.hint")}>
              {(view.missed ?? []).length === 0 ? (
                <Empty text={t("quality.missed.empty")} />
              ) : (
                <Days
                  label={t("quality.missed.title")}
                  rows={(view.missed ?? []).map((w) => tn("quality.missed.week", w.count, { name: w.person_name, from: monthDay(w.week), to: monthDay(w.week_end) }))}
                />
              )}
            </Section>

            <Section id="quality-replays" title={t("quality.replays.title")} hint={t("quality.replays.hint")}>
              {view.replays.count === 0 ? (
                <Empty text={t("quality.replays.empty")} />
              ) : (
                <>
                  <p className={styles.sum}>{tn("quality.replays.count", view.replays.count)}</p>
                  {view.replays.last_run && <p>{t("quality.replays.last", { when: monthDay(view.replays.last_run) })}</p>}
                </>
              )}
            </Section>

            <Section id="quality-knowledge" title={t("quality.knowledge.title")} hint={t("quality.knowledge.hint")}>
              {view.knowledge_used.length === 0 ? (
                <Empty text={t("quality.knowledge.empty")} />
              ) : (
                <Days
                  label={t("quality.knowledge.title")}
                  rows={view.knowledge_used.map((k) => tn("quality.knowledge.row", k.runs_given, { work: work(k.task), applied: k.runs_applied }))}
                />
              )}
            </Section>

            <Section id="quality-repeats" title={t("quality.repeats.title")} hint={t("quality.repeats.hint")}>
              {view.repeat_corrections.length === 0 ? (
                <Empty text={t("quality.repeats.empty")} />
              ) : (
                <Days
                  label={t("quality.repeats.title")}
                  rows={view.repeat_corrections.map((w) =>
                    w.enough
                      ? tn("quality.repeats.row", w.corrections, { week: monthDay(w.week), work: work(w.task), repeats: w.repeats })
                      : tn("quality.repeats.few", w.corrections, { week: monthDay(w.week), work: work(w.task) }),
                  )}
                />
              )}
            </Section>

            <Section id="quality-lacking" title={t("quality.lacking.title")} hint={t("quality.lacking.hint")}>
              {view.missing.length === 0 ? (
                <Empty text={t("quality.lacking.empty")} />
              ) : (
                view.missing.map((w) => (
                  <div key={w.week}>
                    <p className={styles.sum}>{t("quality.lacking.week", { week: monthDay(w.week) })}</p>
                    <Days label={t("quality.lacking.title")} rows={w.groups.map((g) => tn("quality.lacking.row", g.count, { wording: g.wording }))} />
                  </div>
                ))
              )}
            </Section>
          </div>
        </>
      )}
    </section>
  );
}
