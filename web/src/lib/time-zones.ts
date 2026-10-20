// A time zone by its city, as a person says it: "New York (Eastern time)", never the id the settings hold
// ("America/New_York"). The city is the last part of the id; the zone's general name is the browser's own.

/** The city of a time zone id, with spaces for underscores. */
export function zoneCity(id: string): string {
  const last = id.split("/").pop() ?? id;
  return last.replace(/_/g, " ");
}

/** The zone's general name in English ("Eastern time"), or empty where the browser has none. */
function zoneName(id: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: id, timeZoneName: "longGeneric" }).formatToParts(new Date(0));
    return (parts.find((p) => p.type === "timeZoneName")?.value ?? "").replace(/ (Standard|Daylight|Summer) /, " ").replace(/ Time$/, " time");
  } catch {
    return "";
  }
}

/** "New York (Eastern time)". A zone whose general name is its city's (or that has none) shows the city alone. */
export function zoneLabel(id: string): string {
  if (!id.includes("/")) return id; // UTC and the like name no city
  const city = zoneCity(id);
  const name = zoneName(id);
  return name && name !== city && name !== id ? `${city} (${name})` : city;
}

/** The zones with their labels, in the order a person looks them up: by label. */
export function zoneChoices(ids: string[]): { id: string; label: string }[] {
  const seen = new Set<string>();
  return ids
    .filter((id) => id && !seen.has(id) && !!seen.add(id))
    .map((id) => ({ id, label: zoneLabel(id) }))
    .sort((a, b) => a.label.localeCompare(b.label, "en"));
}

/** Whether a zone matches what was typed: by its label, or by its id's words ("new york", "eastern"). */
export function zoneMatches(choice: { id: string; label: string }, typed: string): boolean {
  const wanted = typed.trim().toLowerCase().replace(/_/g, " ");
  return !wanted || choice.label.toLowerCase().includes(wanted) || choice.id.toLowerCase().replace(/_/g, " ").includes(wanted);
}
