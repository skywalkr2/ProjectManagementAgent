// A date format as the date written that way. The settings hold strftime codes; a person is shown today's date in each
// format and picks the one that reads right, never the codes.
const pad = (n: number, width = 2) => String(n).padStart(width, "0");

function part(options: Intl.DateTimeFormatOptions, when: Date, locale?: string): string {
  return new Intl.DateTimeFormat(locale, options).format(when);
}

/** One strftime code as text for a moment; undefined for a code this doesn't know. */
function code(letter: string, when: Date, locale?: string): string | undefined {
  switch (letter) {
    case "a":
      return part({ weekday: "short" }, when, locale);
    case "A":
      return part({ weekday: "long" }, when, locale);
    case "b":
      return part({ month: "short" }, when, locale);
    case "B":
      return part({ month: "long" }, when, locale);
    case "d":
      return pad(when.getDate());
    case "e":
      return String(when.getDate());
    case "m":
      return pad(when.getMonth() + 1);
    case "Y":
      return String(when.getFullYear());
    case "y":
      return pad(when.getFullYear() % 100);
    case "H":
      return pad(when.getHours());
    case "I":
      return pad(when.getHours() % 12 || 12);
    case "M":
      return pad(when.getMinutes());
    case "p":
      return when.getHours() < 12 ? "AM" : "PM";
    case "%":
      return "%";
    default:
      return undefined;
  }
}

/** A format written out for a moment (today by default); a code that isn't known stays as it is. */
export function dateFormatLabel(format: string, when: Date = new Date(), locale?: string): string {
  return format.replace(/%(.)/g, (whole, letter: string) => code(letter, when, locale) ?? whole);
}

/** Formats with each one's label, in the list's order; a format given twice shows once. */
export function dateFormatChoices(formats: string[], when: Date = new Date(), locale?: string): { tag: string; label: string }[] {
  const seen = new Set<string>();
  return formats.filter((f) => f && !seen.has(f) && !!seen.add(f)).map((tag) => ({ tag, label: dateFormatLabel(tag, when, locale) }));
}
