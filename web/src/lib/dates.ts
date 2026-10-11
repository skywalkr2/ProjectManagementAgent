// Dates and ages in the reader's locale. Wording around them comes from the sheet.
const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" });
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return dayFormat.format(new Date(y, m - 1, d));
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

/** The weekday of a yyyy-mm-dd date, short, in the reader's language. */
export function weekday(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return weekdayFormat.format(new Date(y, m - 1, d));
}
