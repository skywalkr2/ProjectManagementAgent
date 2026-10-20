// A table of records (design 7.13, 7.14): one row each, grouped when it helps, with the name as the link to the record's
// page and the row's menu at the end. A row opens its detail pane by a click, by Enter on the row or by its name; there is
// no button of its own for that. Columns drop out as the window narrows (their `rank`: 1 always, 2 from 1280px, 3 from
// 1024px) and stack on a phone, so the table is never wider than the window. While a pane stands beside the table only the
// columns marked `core` stay; the column picker shows or hides any column. No word is ever broken: a value too long for its
// column ends in an ellipsis, with the whole value as its title.
import { useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useRowKeys } from "../lib/keys";
import { useIsNarrow } from "../lib/media";
import { useWords } from "../lib/wording";
import { IconButton } from "./IconButton";
import { MenuButton } from "./MenuButton";
import { usePane } from "./paneContext";
import styles from "./RecordsTable.module.css";

export interface TableColumn<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** 1: always shown. 2: hidden under 1280px. 3: hidden under 1024px (tablet and phone: in the detail pane). */
  rank?: 1 | 2 | 3;
  numeric?: boolean;
  /** Stays while a detail pane stands beside the table. When no column is marked, every column stays. */
  core?: boolean;
}

export interface TableGroup<T> {
  id: string;
  title: string;
  rows: T[];
}

export function RecordsTable<T>(props: {
  label: string;
  /** The first column: the record's name, usually a link to its page. `open` is the link's click handler: a plain click opens
   * the row's pane, a modified one (a new tab) is left to the browser. */
  name: {
    header: string;
    cell: (row: T, open: (event: MouseEvent) => void) => ReactNode;
    /** The whole name, as the cell's title, for when a name too long for its column ends in an ellipsis. */
    title?: (row: T) => string;
  };
  columns: TableColumn<T>[];
  groups: TableGroup<T>[];
  rowKey: (row: T) => string;
  selected?: string | null;
  onSelect?: (row: T) => void;
  /** The row's menu, at the end (a row has no primary button when a click on it opens its pane). */
  actions?: (row: T) => ReactNode;
  actionsHeader?: string;
}) {
  const { t } = useWords();
  const narrow = useIsNarrow();
  const { squeezed } = usePane();
  // What the person chose in the column picker beats what the pane leaves room for.
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const hasCore = props.columns.some((c) => c.core);
  const standard = (c: TableColumn<T>) => !squeezed || !hasCore || !!c.core;
  const shown = (c: TableColumn<T>) => picked[c.id] ?? standard(c);
  const visible = props.columns.filter((c) => narrow || shown(c));
  const span = visible.length + 1 + (props.actions ? 1 : 0);
  // A column the person asked for stays whatever the window width; the others drop out by rank.
  const rank = (c: TableColumn<T>) => (picked[c.id] ? "" : c.rank === 2 ? styles.rank2 : c.rank === 3 ? styles.rank3 : "");
  const optional = hasCore && !narrow;
  return (
    <div className={styles.wrap}>
      {optional && (
        <div className={styles.tools}>
          <MenuButton
            trigger={<IconButton icon="grid" size="sm" label={t("table.choose_columns")} />}
            groups={[
              {
                id: "columns",
                title: t("table.columns"),
                checked: props.columns.filter(shown).map((c) => c.id),
                entries: props.columns.map((c) => ({ id: c.id, label: c.header, run: () => setPicked((was) => ({ ...was, [c.id]: !shown(c) })) })),
              },
            ]}
          />
        </div>
      )}
      <table className={styles.table}>
        <caption className="sr">{props.label}</caption>
        <thead>
          <tr>
            <th scope="col">{props.name.header}</th>
            {visible.map((c) => (
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
              <TableRow key={props.rowKey(row)} row={row} table={props} columns={visible} rank={rank} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function TableRow<T>(props: { row: T; table: Parameters<typeof RecordsTable<T>>[0]; columns: TableColumn<T>[]; rank: (c: TableColumn<T>) => string }) {
  const { row, table, rank } = props;
  const ref = useRef<HTMLTableRowElement>(null);
  const key = table.rowKey(row);
  // Enter on the row chooses it, as it does in every list.
  const choose = table.onSelect ? () => table.onSelect!(row) : undefined;
  useRowKeys(ref, { toggle: choose, primary: choose });
  // The name link: a plain click opens the pane; a click for a new tab or window is the browser's.
  const open = (event: MouseEvent) => {
    if (!table.onSelect || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    table.onSelect(row);
  };
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
      <td className={styles.name} title={table.name.title?.(row) || undefined}>
        {table.name.cell(row, open)}
      </td>
      {props.columns.map((c) => {
        const content = c.cell(row);
        return (
          <td key={c.id} data-label={c.header} title={typeof content === "string" && content ? content : undefined} className={[rank(c), c.numeric ? styles.num : ""].filter(Boolean).join(" ")}>
            {content}
          </td>
        );
      })}
      {table.actions && (
        <td className={styles.acts}>
          <div className={styles.actsInner}>{table.actions(row)}</div>
        </td>
      )}
    </tr>
  );
}
