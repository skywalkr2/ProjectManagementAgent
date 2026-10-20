// The fields a refused save refreshed from what is saved now, one line each, so the next Save is an informed one.
import type { Refreshed } from "../lib/refreshed";
import { useWords } from "../lib/wording";

export function RefreshedLines(props: { lines: Refreshed[]; time: string }) {
  const { t } = useWords();
  if (!props.lines.length) return null;
  return (
    <ul className="refreshed-lines hint" role="status" aria-label={t("refreshed.title")}>
      {props.lines.map((line) => (
        <li key={`${line.label}:${line.value}`}>
          {props.time ? t("refreshed.line", { label: line.label, value: line.value, time: props.time }) : t("refreshed.line_no_time", { label: line.label, value: line.value })}
        </li>
      ))}
    </ul>
  );
}
