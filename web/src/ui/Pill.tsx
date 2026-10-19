// A status or kind pill (design 7.12): 22px, sentence case, always a word, never color alone. Pills show exceptions,
// not defaults; a group is meta text, not a pill.
import type { ReactNode } from "react";
import styles from "./Pill.module.css";

export type PillTone = "neutral" | "need" | "warn" | "danger" | "ok";

/** `inferred` is the tag for what the assistant worked out and nobody said: a dashed outline and a ≈ before the word. It is
 * kept for inferences alone, so the person learns one signal for them. `describedAs` is what a screen reader hears instead
 * of the word when the word alone is not enough. */
export function Pill(props: { tone?: PillTone; children: ReactNode; className?: string; inferred?: boolean; describedAs?: string }) {
  const tone = props.tone ?? "neutral";
  return (
    <span
      className={[styles.pill, styles[tone], props.inferred ? styles.inferred : "", props.className ?? ""].filter(Boolean).join(" ")}
      data-tone={tone}
      data-inferred={props.inferred ? "" : undefined}
    >
      {props.inferred && <span aria-hidden="true">≈ </span>}
      {props.describedAs ? (
        <>
          <span aria-hidden="true">{props.children}</span>
          <span className="sr">{props.describedAs}</span>
        </>
      ) : (
        props.children
      )}
    </span>
  );
}
