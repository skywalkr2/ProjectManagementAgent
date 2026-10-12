// An empty state (design 7.12): one sentence that says what will appear, and one button that makes it appear. In a
// rail pane (`inline`) it is one line; in a main pane it is centered, with an optional line icon.
import type { ReactNode } from "react";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";
import styles from "./EmptyState.module.css";

export function EmptyState(props: {
  text: string;
  /** The one button; omit it only where nothing can be done from here. */
  action?: { label: string; onClick: () => void } | null;
  /** One line, for a rail pane. */
  inline?: boolean;
  icon?: IconName;
  children?: ReactNode;
}) {
  return (
    <div className={[styles.empty, props.inline ? styles.inline : ""].filter(Boolean).join(" ")} data-empty="">
      {props.icon && !props.inline && <Icon name={props.icon} size={48} className={styles.icon} />}
      <p className={styles.text}>{props.text}</p>
      {props.children}
      {props.action && (
        <Button size={props.inline ? "sm" : "md"} onClick={props.action.onClick}>
          {props.action.label}
        </Button>
      )}
    </div>
  );
}
