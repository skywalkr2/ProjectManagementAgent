// A list row (design 7.14): [pill] title (two lines at most) and meta, then the one primary action, then the menu at the
// right edge. The pill column is a fixed width, empty when there is no exception, so titles align on every row of every
// list. `data-row` puts it in the keyboard loop. Rows are separated by hairlines, never cards.
import type { HTMLAttributes, ReactNode } from "react";
import styles from "./Row.module.css";

export interface RowProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  pill?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  primary?: ReactNode;
  menu?: ReactNode;
  selected?: boolean;
  /** Content under the row, indented to the title column (an expanded row's items). */
  children?: ReactNode;
  /** Use a list item inside a list (the default) or a plain block. */
  as?: "li" | "div";
}

export function Row(props: RowProps) {
  const { pill, title, meta, primary, menu, selected, children, as = "li", className, ...rest } = props;
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
      <div className={styles.pill}>{pill}</div>
      <div className={styles.main}>
        <p className={styles.title}>{title}</p>
        {meta && <p className={styles.meta}>{meta}</p>}
      </div>
      {(primary || menu) && (
        <div className={styles.actions}>
          {primary}
          {menu}
        </div>
      )}
      {children && <div className={styles.extra}>{children}</div>}
    </Tag>
  );
}
