// A list row (design 7.14): [pill] title (two lines at most) and meta, then the one primary action, then the menu at the
// right edge. The pill column is a fixed width, empty when there is no exception, so titles align on every row of every
// list. `tag` is a second, quieter mark that sits under the pill (what came from outside). `oneLine` keeps the meta to one
// line, cut with an ellipsis, for a list that must stay short (Today). `data-row` puts it in the keyboard loop. Rows are
// separated by hairlines, never cards.
import { Children, type HTMLAttributes, type ReactNode, type Ref } from "react";
import styles from "./Row.module.css";

export interface RowProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  pill?: ReactNode;
  /** A second mark under the pill, in the same column. */
  tag?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  /** Keep the meta to one line, cut with an ellipsis. */
  oneLine?: boolean;
  primary?: ReactNode;
  menu?: ReactNode;
  selected?: boolean;
  /** Content under the row, indented to the title column (an expanded row's items). */
  children?: ReactNode;
  /** Use a list item inside a list (the default) or a plain block. */
  as?: "li" | "div";
  /** The row's element, whichever tag it is drawn as. */
  ref?: Ref<HTMLLIElement & HTMLDivElement>;
}

export function Row(props: RowProps) {
  const { pill, tag, title, meta, oneLine, primary, menu, selected, children, as = "li", className, ...rest } = props;
  const Tag = as;
  return (
    <Tag
      tabIndex={-1}
      {...rest}
      data-row=""
      data-selected={selected ? "" : undefined}
      aria-current={selected ? "true" : undefined}
      className={[styles.row, selected ? styles.selected : "", className ?? ""].filter(Boolean).join(" ")}
    >
      <div className={styles.pill}>
        {pill}
        {tag}
      </div>
      <div className={styles.main}>
        <div className={styles.title}>{title}</div>
        {meta && (
          <p className={oneLine ? `${styles.meta} ${styles.oneLine}` : styles.meta} title={oneLine && typeof meta === "string" ? meta : undefined}>
            {meta}
          </p>
        )}
      </div>
      {(primary || menu) && (
        <div className={styles.actions}>
          {primary}
          {menu}
        </div>
      )}
      {Children.toArray(children).length > 0 && <div className={styles.extra}>{children}</div>}
    </Tag>
  );
}
