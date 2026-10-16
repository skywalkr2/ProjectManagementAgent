// A language tag in words, in the browser's own language: "en-US" reads "English (United States)". A tag the browser
// can't name is shown as the tag itself, so a list never has a blank entry.

/** The language the person's browser is set to, or undefined where it says none. */
const browserLanguage = (): string | undefined => (typeof navigator !== "undefined" && navigator.language) || undefined;

/** What to call a language tag. `locale` is the language to name it in (the browser's by default). */
export function languageLabel(tag: string, locale: string | undefined = browserLanguage()): string {
  try {
    const names = new Intl.DisplayNames(locale ? [locale] : undefined, { type: "language", languageDisplay: "standard" });
    const named = names.of(tag);
    return named && named !== tag ? named : tag;
  } catch {
    return tag; // a tag or a locale this browser doesn't know
  }
}

/** Language tags, with each one's label, in the order a person reads them: by label. A tag given twice shows once. */
export function languageChoices(tags: string[], locale?: string): { tag: string; label: string }[] {
  const seen = new Set<string>();
  return tags
    .filter((tag) => tag && !seen.has(tag) && !!seen.add(tag))
    .map((tag) => ({ tag, label: languageLabel(tag, locale) }))
    .sort((a, b) => a.label.localeCompare(b.label, locale));
}
