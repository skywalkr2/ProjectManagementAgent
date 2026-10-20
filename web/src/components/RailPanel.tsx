// The panels of Today's rail (design 7.7): a heading with its count, a body sized to its content, and the two one-line
// states a panel has besides its rows, empty and failed to load.
import type { ReactNode } from "react";
import { useWords } from "../lib/wording";
import { Panel } from "../ui/Panel";
import styles from "./Today.module.css";

/** A rail panel: a visible heading with its count (said in words for a screen reader) and a body sized to its content. */
export function RailPanel(props: {
  id: string;
  title: string;
  count: number | null;
  countText: string;
  /** A control at the end of the heading row. */
  action?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div data-col={props.id}>
      <Panel
        small
        flush
        title={props.title}
        count={
          // A panel with nothing in it shows no count, rather than "0".
          props.count === null || props.count === 0 ? null : (
            <>
              <span aria-hidden="true">{props.count}</span>
              <span className="sr">{props.countText}</span>
            </>
          )
        }
        actions={props.action}
      >
        <div className={styles.railBody}>{props.children}</div>
        {props.footer && <div className={styles.railFoot}>{props.footer}</div>}
      </Panel>
    </div>
  );
}

export function Empty(props: { text: string; note?: string; button?: { label: string; run: () => void } }) {
  return (
    <div className="tb-empty">
      <p>{props.text}</p>
      {props.note && <p className="hint">{props.note}</p>}
      {props.button && (
        <button type="button" className="btn" onClick={props.button.run}>
          {props.button.label}
        </button>
      )}
    </div>
  );
}

export function Failed(props: { text: string; retry: () => void }) {
  const { t } = useWords();
  return (
    <p className="empty">
      {props.text}{" "}
      <button type="button" className="btn" onClick={props.retry}>
        {t("action.try_again")}
      </button>
    </p>
  );
}
