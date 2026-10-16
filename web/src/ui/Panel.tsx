// A top-level pane (design 7.12): a surface with a hairline border, no shadow and a 48px header holding the title, a
// count and actions. Nothing inside a panel is another bordered card except the sunken source block. `flush` lets rows
// run edge to edge.
import { useId, type ReactNode } from "react";
import styles from "./Panel.module.css";

export function Panel(props: {
  title: string;
  /** The heading level; a view's own title is the page's h1, so panes are h2 by default. */
  level?: 2 | 3;
  count?: ReactNode;
  actions?: ReactNode;
  /** The smaller title of a rail pane. */
  small?: boolean;
  /** No padding in the body, for rows that run edge to edge. */
  flush?: boolean;
  id?: string;
  className?: string;
  children?: ReactNode;
}) {
  const auto = useId();
  const headId = props.id ?? auto;
  const Heading = props.level === 3 ? "h3" : "h2";
  return (
    <section className={[styles.panel, props.small ? styles.small : "", props.className ?? ""].filter(Boolean).join(" ")} aria-labelledby={headId}>
      <div className={styles.head}>
        <Heading id={headId} className={styles.title}>
          {props.title}
        </Heading>
        {props.count !== undefined && props.count !== null && props.count !== "" && <span className={styles.count}>{props.count}</span>}
        <span className={styles.spacer} />
        {props.actions && <div className={styles.actions}>{props.actions}</div>}
      </div>
      {props.children !== undefined && <div className={props.flush ? styles.flush : styles.body}>{props.children}</div>}
    </section>
  );
}
