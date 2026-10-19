// What the list of sources says about the whole: whether any is reading, and when the latest read happened.
import type { S } from "./api";

type Source = S["WatchSourceView"];

/** Whether a source is set up and reading: at least one is on. */
export const anyReading = (sources: Source[]): boolean => sources.some((s) => s.enabled);

/** The start of the most recent read that actually read a source, across sources (an ISO time), or null when none has
 * been read yet. A try that found no network or failed is not a read. */
export function latestRead(sources: Source[]): string | null {
  let best: { iso: string; at: number } | null = null;
  for (const source of sources) {
    const iso = source.read_at;
    if (!iso) continue;
    const at = new Date(iso.replace(" ", "T")).getTime();
    if (!Number.isNaN(at) && (best === null || at > best.at)) best = { iso, at };
  }
  return best?.iso ?? null;
}

type T = (key: string, vars?: Record<string, string | number>) => string;
type Has = (key: string) => boolean;

/** The sources of one kind of content that are on and whose latest try didn't read them (it failed, or it found no
 * network), so a card built from them never reads as empty when it is really unread. */
export const failedReads = (sources: Source[], kind: "mail" | "calendar"): Source[] =>
  sources.filter((s) => s.enabled && (s.reads ?? []).includes(kind) && (s.last?.outcome === "failed" || s.last?.outcome === "offline"));

/** Why a failed read failed and what to do, in words, or null when it didn't fail. When the connector named its advice
 * by wording key the sentence is what the connector said went wrong followed by that key's words from the sheet; else
 * the engine's own sentence for the kind of failure. */
export function failureText(source: Source, t: T, has: Has): string | null {
  const last = source.last;
  if (last?.outcome !== "failed") return null;
  const key = last.error_advice;
  if (key && last.error && has(key)) return `${/[.!?]$/.test(last.error) ? last.error : `${last.error}.`} ${t(key)}`;
  return source.problem || last.error || null;
}

/** Why a source wasn't read and what to do, in words: the engine's own sentence for a failure, or that there was no
 * network. */
export function readProblem(source: Source, t: T, has: Has): string {
  if (source.last?.outcome === "offline") return t("sources.read_offline", { label: source.label });
  return failureText(source, t, has) || t("sources.read_failed", { label: source.label });
}
