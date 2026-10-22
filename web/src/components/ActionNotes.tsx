// An action's notes where a row shows its words (design 7.5, 7.7): on hover through the title, to a screen reader through a
// description the row points at, and, where there is no hover (the phone layout), as a second line under the words.
import { useId, type ReactNode } from "react";
import { useIsNarrow } from "../lib/media";
import styles from "./ActionNotes.module.css";

export function NotesTitle(props: { notes: string | null | undefined; children: ReactNode }) {
  const id = useId();
  const narrow = useIsNarrow();
  const { notes, children } = props;
  if (!notes) return <>{children}</>;
  if (narrow)
    return (
      <>
        {children}
        <span className={styles.line} data-notes="">
          {notes}
        </span>
      </>
    );
  return (
    <span title={notes} aria-describedby={id} data-notes="">
      {children}
      <span id={id} className="sr">
        {notes}
      </span>
    </span>
  );
}
