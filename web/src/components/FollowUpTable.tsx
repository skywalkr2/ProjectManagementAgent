// A person's follow-ups as the tables they will be copied as (design 7.5), shown before anything reaches the clipboard. What
// is on screen is the data the copies are made from, so the person sees exactly what goes. The fill-in column is last and
// widest and has nothing in it. Overdue is said in words as well as colour.
import { useWords } from "../lib/wording";
import type { Table } from "../lib/followup-table";
import { SafeLink } from "./SafeText";
import styles from "./FollowUpTable.module.css";

export function FollowUpTables(props: { tables: Table[]; name: string; noLink: string }) {
  const { t } = useWords();
  if (props.tables.length === 0) return <p className="empty">{t("followups.table.empty", { name: props.name })}</p>;
  return (
    <div className={styles.wrap}>
      {props.tables.map((table) => {
        const title = t(table.kind === "actions" ? "followups.table.actions" : "followups.table.questions");
        return (
          <div key={table.kind}>
            <h4 className={styles.heading}>{title}</h4>
            <div className={styles.scroll} role="region" aria-label={t("followups.table.label", { name: `${props.name}: ${title}` })} tabIndex={0}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    {table.columns.map((c, i) => (
                      <th key={c} scope="col" className={i === table.fill ? styles.fill : undefined}>
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, i) => (
                        <td key={i} className={[i === table.fill ? styles.fill : "", cell.overdue ? styles.late : ""].filter(Boolean).join(" ") || undefined}>
                          {cell.links ? (
                            cell.links.length ? (
                              cell.links.map((l, k) => (
                                <span key={l.url}>
                                  {k > 0 && ", "}
                                  <SafeLink label={l.label} url={l.url} />
                                </span>
                              ))
                            ) : (
                              props.noLink
                            )
                          ) : (
                            cell.text
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export const tableBar = styles.bar;
export const tableHint = styles.hint;
