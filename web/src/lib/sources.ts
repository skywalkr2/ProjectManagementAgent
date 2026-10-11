// What the list of sources says about the whole: whether any is reading, and when the latest read happened.
import type { S } from "./api";

type Source = S["WatchSourceView"];

/** Whether a source is set up and reading: at least one is on. */
export const anyReading = (sources: Source[]): boolean => sources.some((s) => s.enabled);

/** The start of the most recent read across sources (an ISO time), or null when none has been read yet. */
export function latestRead(sources: Source[]): string | null {
  let best: { iso: string; at: number } | null = null;
  for (const source of sources) {
    const iso = source.last?.started_at;
    if (!iso) continue;
    const at = new Date(iso.replace(" ", "T")).getTime();
    if (!Number.isNaN(at) && (best === null || at > best.at)) best = { iso, at };
  }
  return best?.iso ?? null;
}
