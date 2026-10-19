// A table of records (design 7.13, 7.14): one row each, grouped when it helps, with the name as the link to the record's
// page and one primary action and a menu at the end. A row opens its detail pane, by a click or by its primary action.
// Columns drop out as the window narrows (their `rank`: 1 always, 2 from 1280px, 3 from 1024px) and stack on a phone, so
// the table is never wider than the window.
import { useRef, type ReactNode } from "react";
import { useRowKeys } from "../lib/keys";
import styles from "./RecordsTable.module.css";

export interface TableColumn<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** 1: always shown. 2: hidden under 1280px. 3: hidden under 1024px (tablet and phone: in the detail pane). */
  rank?: 1 | 2 | 3;
  numeric?: boolean;
}

export interface TableGroup<T> {
  id: string;
  title: string;
  rows: T[];
}

export function RecordsTable<T>(props: {
  label: string;
  /** The first column: the record's name, usually a link to its page. */
  name: { header: string; cell: (row: T) => ReactNode };
  columns: TableColumn<T>[];
  groups: TableGroup<T>[];
  rowKey: (row: T) => string;
  selected?: string | null;
  onSelect?: (row: T) => void;
  /** The row's one primary action and its menu, at the end. */
  actions?: (row: T) => ReactNode;
  actionsHeader?: string;
}) {
  const span = props.columns.length + 1 + (props.actions ? 1 : 0);
  const rank = (c: TableColumn<T>) => (c.rank === 2 ? styles.rank2 : c.rank === 3 ? styles.rank3 : "");
  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <caption className="sr">{props.label}</caption>
        <thead>
          <tr>
            <th scope="col">{props.name.header}</th>
            {props.columns.map((c) => (
              <th key={c.id} scope="col" className={rank(c)}>
                {c.header}
              </th>
            ))}
            {props.actions && (
              <th scope="col" className={styles.acts}>
                <span className="sr">{props.actionsHeader}</span>
              </th>
            )}
          </tr>
        </thead>
        {props.groups.map((group) => (
          <tbody key={group.id} aria-label={group.title}>
            {props.groups.length > 1 && (
              <tr className={styles.group}>
                <th colSpan={span} scope="colgroup">
                  {group.title} <span className={styles.groupCount}>· {group.rows.length}</span>
                </th>
              </tr>
            )}
            {group.rows.map((row) => (
              <TableRow key={props.rowKey(row)} row={row} table={props} rank={rank} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function TableRow<T>(props: { row: T; table: Parameters<typeof RecordsTable<T>>[0]; rank: (c: TableColumn<T>) => string }) {
  const { row, table, rank } = props;
  const ref = useRef<HTMLTableRowElement>(null);
  const key = table.rowKey(row);
  // Enter on the row chooses it, as it does in every list.
  useRowKeys(ref, { toggle: table.onSelect ? () => table.onSelect!(row) : undefined });
  return (
    <tr
      ref={ref}
      className={styles.row}
      data-row=""
      data-selected={table.selected === key ? "" : undefined}
      aria-selected={table.onSelect ? table.selected === key : undefined}
      tabIndex={-1}
      onClick={(event) => {
        if (!table.onSelect || (event.target as HTMLElement).closest("a, button, input, select, textarea, [role='menuitem']")) return;
        table.onSelect(row);
      }}
    >
      <td className={styles.name}>{table.name.cell(row)}</td>
      {table.columns.map((c) => (
        <td key={c.id} data-label={c.header} className={[rank(c), c.numeric ? styles.num : ""].filter(Boolean).join(" ")}>
          {c.cell(row)}
        </td>
      ))}
      {table.actions && (
        <td className={styles.acts}>
          <div className={styles.actsInner}>{table.actions(row)}</div>
        </td>
      )}
    </tr>
  );
}
