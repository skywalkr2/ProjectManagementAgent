// Coverage (design 6.32, 7.7): what the assistant read and when, and which sources it couldn't read, so an empty Today is
// never mistaken for "couldn't check". Read sources are said in the quiet style; a source that couldn't be read is said
// in its own words and style, never as "nothing new".
import { useCoverage, whenWords, type Coverage } from "../lib/coverage";
import { localDate } from "../lib/dates";
import { useWords } from "../lib/wording";
import styles from "./Today.module.css";

/** The coverage as the parts of one line: what was read, then each source that couldn't be, then each not read yet. */
function useParts(found: Coverage): { kind: "read" | "unread" | "pending"; text: string; key: string }[] {
  const { t, tn } = useWords();
  const now = new Date();
  const parts: { kind: "read" | "unread" | "pending"; text: string; key: string }[] = [];
  if (found.read.length > 0 && found.last) {
    const when = whenWords(found.last, now, t);
    const today = localDate(new Date(found.last)) === localDate(now);
    parts.push({ kind: "read", key: "read", text: today ? tn("coverage.read", found.read.length, { when }) : tn("coverage.read_earlier", found.read.length, { when }) });
  }
  for (const { source, kind } of found.unread) {
    const label = source.label;
    const text = source.read_at
      ? t(`coverage.${kind}.since`, { label, when: whenWords(source.read_at, now, t) })
      : t(`coverage.${kind}.never`, { label });
    parts.push({ kind: "unread", key: `unread:${source.id}`, text });
  }
  for (const source of found.pending) parts.push({ kind: "pending", key: `pending:${source.id}`, text: t("coverage.pending", { label: source.label }) });
  return parts;
}

function Parts(props: { found: Coverage }) {
  const parts = useParts(props.found);
  return (
    <>
      {parts.map((part, i) => (
        <span key={part.key}>
          {i > 0 && " · "}
          <span data-coverage={part.kind} className={styles.coverageSource}>
            {part.text}
          </span>
        </span>
      ))}
    </>
  );
}

/** The one line in Today's header: what was read and when, and what couldn't be. Nothing while no source is on. */
export function CoverageLine() {
  const found = useCoverage();
  if (!found) return null;
  return (
    <p className={styles.coverage} data-coverage-line="">
      <Parts found={found} />
    </p>
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
