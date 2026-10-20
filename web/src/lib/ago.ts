// How long ago something was, in words from the sheet: "today", "yesterday", "5 days ago", "3 weeks ago", "2 months ago".
import { useWords } from "./wording";

/** Whole days from a time as the server wrote it to `now`, never negative; null when the time can't be read. */
export function daysSince(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  const then = new Date(iso.replace(" ", "T"));
  if (Number.isNaN(then.getTime())) return null;
  const midnight = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.max(0, Math.round((midnight(now) - midnight(then)) / 86_400_000));
}

export function useAgo() {
  const { t, tn } = useWords();
  return (iso: string | null | undefined, now: Date = new Date()): string => {
    const days = daysSince(iso, now);
    if (days === null) return "";
    if (days === 0) return t("ago.today");
    if (days === 1) return t("ago.yesterday");
    if (days < 14) return t("ago.days", { n: days });
    if (days < 60) return tn("ago.weeks", Math.floor(days / 7));
    return tn("ago.months", Math.floor(days / 30));
  };
}
