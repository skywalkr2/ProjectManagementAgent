// How an item that is for a meeting names it (design 7.14): "for Thursday's print sync" within a week, "for Oct 29's print sync"
// further out or already past. The title is the person's own words; a title written as a sentence is kept as written, and one
// that only starts with a capital is lowered to read after "for Thursday's".
import { monthDay } from "./dates";

const weekday = new Intl.DateTimeFormat(undefined, { weekday: "long" });

const lowerFirst = (title: string): string => (/^\p{Lu}[^\p{Lu}]*$/u.test(title) ? title.charAt(0).toLowerCase() + title.slice(1) : title);

/** Whole days from today to a yyyy-mm-dd day on this computer's calendar (negative once it has passed). */
function daysFrom(today: Date, iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - start) / 86_400_000);
}

/** The day a meeting is on, as the label says it: the weekday in the week ahead, else the month and day. */
export function meetingDay(on: string, today: Date = new Date()): string {
  const gap = daysFrom(today, on);
  if (gap >= 0 && gap < 7) {
    const [y, m, d] = on.slice(0, 10).split("-").map(Number);
    return weekday.format(new Date(y, m - 1, d));
  }
  return monthDay(on);
}

/** "for Thursday's print sync", from the label's wording `series.for` ("for {day}'s {title}"). */
export function forMeeting(t: (key: string, vars?: Record<string, string | number>) => string, title: string, on: string | null | undefined, today?: Date): string {
  if (!on) return t("series.for_title", { title: lowerFirst(title) });
  return t("series.for", { day: meetingDay(on, today), title: lowerFirst(title) });
}
