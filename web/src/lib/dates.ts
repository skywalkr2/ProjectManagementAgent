// Dates and ages in the reader's locale. Wording around them comes from the sheet.
const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" });
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return dayFormat.format(new Date(y, m - 1, d));
}

const monthDayFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

/** The day of a date, or of a time as the server wrote it on the person's own clock, as a month and a day: "Oct 14". */
export function monthDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return monthDayFormat.format(new Date(y, m - 1, d));
}

const longDayFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });

/** A date in full words, "Tuesday, October 13", for a heading. */
export function longDay(when: Date): string {
  return longDayFormat.format(when);
}

export function dayAndTime(iso: string): string {
  const when = new Date(iso);
  return `${dayFormat.format(when)}, ${timeFormat.format(when)}`;
}

export function time(when: Date): string {
  return timeFormat.format(when);
}

/** A time the server wrote as an ISO string, day and time in the reader's locale; empty if it can't be read. */
export function whenText(iso: string | null | undefined): string {
  if (!iso) return "";
  const parsed = new Date(iso.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? "" : dayAndTime(parsed.toISOString());
}

const weekdayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short" });
const pad = (n: number) => String(n).padStart(2, "0");

/** The date on this computer's clock, as yyyy-mm-dd. */
export function localDate(when: Date): string {
  return `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
}

/** The coming Monday after a date, as yyyy-mm-dd: on a Monday it is the Monday a week on, never the day itself. */
export function nextMonday(from: Date): string {
  const ahead = (8 - from.getDay()) % 7 || 7;
  return localDate(new Date(from.getFullYear(), from.getMonth(), from.getDate() + ahead));
}

/** How a past day is said in "ready since Tue": the weekday for the last six days, else the month and day ("Oct 6"); empty
 * for today or a day not yet come, since a batch ready today is not a stale one. */
export function sinceDay(iso: string | null | undefined, today: Date): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const then = new Date(y, m - 1, d);
  const ago = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - then.getTime()) / 86_400_000);
  if (ago <= 0) return "";
  return ago < 7 ? weekdayFormat.format(then) : monthDay(iso);
}

/** The date n days after a yyyy-mm-dd date, as yyyy-mm-dd. */
export function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return localDate(new Date(y, m - 1, d + n));
}

/** The time of day exactly as the server wrote it (the person's own clock), in the reader's time format. */
export function wallTime(iso: string): string {
  const found = /T(\d{2}):(\d{2})/.exec(iso);
  return found ? timeFormat.format(new Date(2000, 0, 1, Number(found[1]), Number(found[2]))) : "";
}

/** A time as the server wrote it, on the person's own clock: the time alone today, otherwise the day and the time. */
export function wallWhen(iso: string): string {
  const clock = wallTime(iso);
  return iso.slice(0, 10) === localDate(new Date()) ? clock : `${day(iso)}, ${clock}`;
}

/** The weekday of a yyyy-mm-dd date, short, in the reader's language. */
export function weekday(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return weekdayFormat.format(new Date(y, m - 1, d));
}
