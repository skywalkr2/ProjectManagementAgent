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
