// A status or kind pill (design 7.12): 22px, sentence case, always a word, never color alone. Pills show exceptions,
// not defaults; a group is meta text, not a pill.
import type { ReactNode } from "react";
import styles from "./Pill.module.css";

export type PillTone = "neutral" | "need" | "warn" | "danger" | "ok";

export function Pill(props: { tone?: PillTone; children: ReactNode; className?: string }) {
  const tone = props.tone ?? "neutral";
  return (
    <span className={[styles.pill, styles[tone], props.className ?? ""].filter(Boolean).join(" ")} data-tone={tone}>
      {props.children}
    </span>
  );
}
