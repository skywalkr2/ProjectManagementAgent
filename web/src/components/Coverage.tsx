// Coverage (design 6.32, 7.7): what the assistant read and when, and which sources it couldn't read, so an empty Today is
// never mistaken for "couldn't check". Read sources are said in the quiet style; a source that couldn't be read is said
// in its own words and style, never as "nothing new".
import { useState } from "react";
import type { S } from "../lib/api";
import { useCoverage, whenWords, type Coverage } from "../lib/coverage";
import { day, localDate } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { LookBack } from "./LookBack";
import styles from "./Today.module.css";

interface Part {
  kind: "read" | "looked" | "unread" | "stale" | "pending";
  text: string;
  key: string;
  /** The source whose mail wasn't looked at before a day: its part offers to look further back. */
  source?: S["WatchSourceView"];
}

/** The coverage as the parts of one line: what was read, how far back each new mail source looked, then each source that
 * couldn't be read, then each not read yet. */
function useParts(found: Coverage): Part[] {
  const { t, tn } = useWords();
  const now = new Date();
  const parts: Part[] = [];
  if (found.read.length > 0 && found.last) {
    const when = whenWords(found.last, now, t);
    const today = localDate(new Date(found.last)) === localDate(now);
    parts.push({ kind: "read", key: "read", text: today ? tn("coverage.read", found.read.length, { when }) : tn("coverage.read_earlier", found.read.length, { when }) });
  }
  for (const source of found.read) {
    if (source.looked_back_to) parts.push({ kind: "looked", key: `looked:${source.id}`, text: t("coverage.not_looked_at", { date: day(source.looked_back_to) }), source });
  }
  for (const { source, kind } of found.unread) {
    const label = source.label;
    const text = source.read_at
      ? t(`coverage.${kind}.since`, { label, when: whenWords(source.read_at, now, t) })
      : t(`coverage.${kind}.never`, { label });
    parts.push({ kind: "unread", key: `unread:${source.id}`, text });
  }
  for (const source of found.stale) parts.push({ kind: "stale", key: `stale:${source.id}`, text: t("coverage.stale.since", { label: source.label, when: whenWords(source.read_at!, now, t) }) });
  for (const source of found.pending) parts.push({ kind: "pending", key: `pending:${source.id}`, text: t("coverage.pending", { label: source.label }) });
  return parts;
}

export function Parts(props: { found: Coverage; onLookBack?: (source: string) => void }) {
  const { t } = useWords();
  const parts = useParts(props.found);
  return (
    <>
      {parts.map((part, i) => (
        <span key={part.key}>
          {i > 0 && " · "}
          <span data-coverage={part.kind} className={styles.coverageSource}>
            {part.text}
          </span>
          {part.source && props.onLookBack && (
            <>
              {" "}
              <Button size="sm" variant="ghost" aria-label={t("coverage.look_back.label", { label: part.source.label })} onClick={() => props.onLookBack!(part.source!.id)}>
                {t("coverage.look_back.open")}
              </Button>
            </>
          )}
        </span>
      ))}
    </>
  );
}

/** The one line in Today's header: what was read and when, and what couldn't be. Nothing while no source is on. */
export function CoverageLine() {
  const found = useCoverage();
  const [looking, setLooking] = useState<string | null>(null);
  if (!found) return null;
  const source = looking ? found.read.find((s) => s.id === looking) : undefined;
  return (
    <>
      <p className={styles.coverage} data-coverage-line="">
        <Parts found={found} onLookBack={setLooking} />
      </p>
      {source && <LookBack key={source.id} source={source} onClose={() => setLooking(null)} />}
    </>
  );
}

/** What the heading says when nothing needs the person: "nothing needs you" only when every source was read. */
export function useNoneText(): string {
  const { t } = useWords();
  const found = useCoverage();
  return t(found && !found.complete ? "today.needs.none_unchecked" : "today.needs.none");
}

/** The empty queue: that nothing needs the person, together with what was read; with a source that couldn't be read, or
 * not read yet, it says only that nothing was found. */
export function NothingNeedsYou(props: { className?: string }) {
  const { t } = useWords();
  const found = useCoverage();
  const none = useNoneText();
  return (
    <p className={props.className} data-queue-empty="">
      {found ? (
        <>
          {none} · <Parts found={found} />
        </>
      ) : (
        t("queue.empty")
      )}
    </p>
  );
}
