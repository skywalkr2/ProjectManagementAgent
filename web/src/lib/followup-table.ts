// The tables a person's follow-ups copy as (design 7.5): actions as Project, Action, Due, Link and "Your update"; questions as
// Project, Question, the day first put to the person, Link and "Your answer". The same data the message holds, in two shapes: an HTML table for
// mail and chat (link names kept, the fill-in column tinted, overdue in words and colour) and tab-separated cells for a
// spreadsheet (full web addresses, which a spreadsheet turns into links). The project is on every row, so there are no merged
// cells; nothing in either copy is a title, an instruction or placeholder text. The screen shows these tables before anything is
// copied, and nothing here calls an AI.
import type { S } from "./api";

export interface TableLink {
  label: string;
  url: string;
}

export interface TableCell {
  text: string;
  links?: TableLink[];
  overdue?: boolean;
}

export interface Table {
  kind: "actions" | "questions";
  columns: string[];
  /** The one column the reader fills in: last and widest. */
  fill: number;
  rows: TableCell[][];
}

/** The words a table is made of, from the wording sheet, and how a date reads. */
export interface TableWords {
  project: string;
  action: string;
  question: string;
  due: string;
  asked: string;
  link: string;
  update: string;
  answer: string;
  notSent: string;
  noLink: string;
  overdue: (date: string) => string;
  /** "Fri, Oct 23" */
  due_day: (iso: string) => string;
  /** "Oct 10" */
  asked_day: (iso: string) => string;
}

export const TINT = "#e8ecfb";
export const DANGER = "#b42318";
const FILL_WIDTH = "38%";

const safe = (url: string) => /^https?:\/\//i.test(url);

/** The to-send actions by due date, oldest first (so overdue ones lead), undated last; and the to-send questions by when they
 * were first asked, oldest first, with those not sent yet last. `today` is yyyy-mm-dd. */
export function tablesOf(section: S["FollowupSection"], w: TableWords, today: string): Table[] {
  const tables: Table[] = [];
  const actions = section.actions
    .filter((a) => a.told === null)
    .sort((a, b) => (a.due ?? "9999-99-99").localeCompare(b.due ?? "9999-99-99") || a.text.localeCompare(b.text));
  if (actions.length) {
    tables.push({
      kind: "actions",
      columns: [w.project, w.action, w.due, w.link, w.update],
      fill: 4,
      rows: actions.map((a) => {
        const late = !!a.due && a.due.slice(0, 10) < today;
        return [
          { text: a.project_name },
          { text: a.text },
          { text: !a.due ? "" : late ? w.overdue(w.due_day(a.due)) : w.due_day(a.due), overdue: late },
          { text: "", links: a.links },
          { text: "" },
        ];
      }),
    });
  }
  const questions = section.questions
    .filter((q) => q.status === "open")
    .sort((a, b) => (a.sent ?? "9999-99-99").localeCompare(b.sent ?? "9999-99-99") || a.title.localeCompare(b.title));
  if (questions.length) {
    tables.push({
      kind: "questions",
      columns: [w.project, w.question, w.asked, w.link, w.answer],
      fill: 4,
      rows: questions.map((q) => [
        { text: q.project_name ?? "" },
        { text: q.title },
        { text: q.sent ? w.asked_day(q.sent) : w.notSent },
        { text: "", links: q.links },
        { text: "" },
      ]),
    });
  }
  return tables;
}

const escape = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** The tables as HTML for mail and chat. A link is its page's name; one that isn't a web address is plain text. */
export function toHtml(tables: Table[], w: TableWords): string {
  const border = "border:1px solid #c9ced8;padding:6px 10px;text-align:left;vertical-align:top;";
  const one = (table: Table) => {
    const head = table.columns
      .map((c, i) => `<th style="${border}${i === table.fill ? `background:${TINT};width:${FILL_WIDTH};` : ""}">${escape(c)}</th>`)
      .join("");
    const body = table.rows
      .map((row) => {
        const cells = row.map((cell, i) => {
          const style = `${border}${i === table.fill ? `background:${TINT};width:${FILL_WIDTH};` : ""}${cell.overdue ? `color:${DANGER};font-weight:bold;` : ""}`;
          const links = (cell.links ?? []).map((l) => (safe(l.url) ? `<a href="${escape(l.url)}">${escape(l.label)}</a>` : escape(l.label)));
          const content = cell.links ? (links.length ? links.join(", ") : escape(w.noLink)) : escape(cell.text);
          return `<td style="${style}">${content}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      })
      .join("");
    return `<table style="border-collapse:collapse;width:100%;"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  };
  return tables.map(one).join("<br>");
}

const cleaned = (text: string) => text.replace(/[\t\r\n]+/g, " ").trim();

/** The tables as tab-separated cells for a spreadsheet: a link is its full address, several are told apart by a space. */
export function toTsv(tables: Table[], w: TableWords): string {
  return tables
    .map((table) =>
      [
        table.columns.join("\t"),
        ...table.rows.map((row) =>
          row
            .map((cell) => {
              if (!cell.links) return cleaned(cell.text);
              const urls = cell.links.filter((l) => safe(l.url)).map((l) => cleaned(l.url));
              return urls.length ? urls.join(" ") : w.noLink;
            })
            .join("\t"),
        ),
      ].join("\n"),
    )
    .join("\n\n");
}
