// Looking further back in a mail source (design 6.32): the person picks how many more days from a list, sees how many items
// that is and about what it costs, and confirms; nothing is read before. The older mail is taken in the same quiet way as the
// source's first read. When the source holds no mail that far back the answer says where its mail starts.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useEstimate } from "../lib/money";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import styles from "./Today.module.css";

type Source = S["WatchSourceView"];

/** The look further back for one source: a list of days, what it would take in and cost, and the button that does it. */
export function LookBack(props: { source: Source; onClose: () => void }) {
  const { t, tn } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const { source } = props;
  const base = useId();
  const field = useRef<HTMLSelectElement>(null);
  const [days, setDays] = useState(0);
  const [busy, setBusy] = useState(false);
  // The cursor goes to the list when the form opens.
  useEffect(() => field.current?.focus(), []);
  const preview = useQuery({
    queryKey: ["look-back", source.id, days],
    queryFn: () => api.lookBackPreview(source.id, days),
    enabled: days > 0,
  });
  const found = preview.data;
  const cost = found ? costWords(found, estimate, t) : "";
  const confirm = async () => {
    setBusy(true);
    const done = await act(
      () => api.lookBack(source.id, days),
      (result) => ({ message: doneWords(result, source.label, t, tn) }),
    );
    setBusy(false);
    if (done) props.onClose();
  };
  return (
    <div className={styles.lookBack} role="group" aria-label={t("coverage.look_back.label", { label: source.label })} data-look-back="">
      <label htmlFor={`${base}-days`}>{t("coverage.look_back.days")}</label>
      <select id={`${base}-days`} ref={field} value={days} onChange={(e) => setDays(Number(e.target.value))}>
        <option value={0}>{t("coverage.look_back.choose")}</option>
        {(source.look_back_choices ?? []).map((n) => (
          <option key={n} value={n}>
            {t("coverage.look_back.choice", { n })}
          </option>
        ))}
      </select>
      <p className={styles.lookBackFound} role="status">
        {days === 0
          ? ""
          : preview.isPending
            ? t("coverage.look_back.counting")
            : found && found.count === 0
              ? t("coverage.look_back.none")
              : found
                ? tn("coverage.look_back.found", found.count, { from: day(found.from_date), cost })
                : ""}
        {found && !found.reaches && found.available_from ? ` ${t("coverage.look_back.only_from", { date: day(found.available_from) })}` : ""}
      </p>
      <div className={styles.lookBackActions}>
        <Button size="sm" variant="primary" disabled={!found || found.count === 0} loading={busy} onClick={() => void confirm()}>
          {t("coverage.look_back.confirm")}
        </Button>
        <Button size="sm" variant="ghost" onClick={props.onClose}>
          {t("coverage.look_back.cancel")}
        </Button>
      </div>
    </div>
  );
}

type T = (key: string, vars?: Record<string, string | number>) => string;

/** What the items would cost, in words: the estimate, the plan's allowance, or both. */
function costWords(found: S["LookBackView"], estimate: (usd: number | null | undefined) => string | null, t: T): string {
  const amount = estimate(found.estimate_usd);
  if (amount === null) return t("coverage.look_back.cost.unpriced");
  return t(found.unpriced > 0 ? "coverage.look_back.cost.mixed" : "coverage.look_back.cost.priced", { cost: amount });
}

/** What the look did: how many older items are being taken in, or that they wait for the go, and where the mail starts when
 * the source didn't reach as far as asked. */
function doneWords(done: S["LookBackView"], label: string, t: T, tn: (key: string, n: number, vars?: Record<string, string | number>) => string): string {
  const parts = [done.taken === 0 ? t("coverage.look_back.none") : done.started ? tn("coverage.look_back.done", done.taken, { source: label }) : t("coverage.look_back.done_held", { source: label })];
  if (!done.reaches && done.available_from) parts.push(t("coverage.look_back.only_from", { date: day(done.available_from) }));
  return parts.join(" ");
}
