import type { S } from "./api";
import { DANGER, TINT, tablesOf, toHtml, toTsv, type TableWords } from "./followup-table";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

const words: TableWords = {
  project: "Project",
  action: "Action",
  question: "Question",
  due: "Due",
  asked: "First asked",
  link: "Link",
  update: "Your update",
  answer: "Your answer",
  notSent: "Not sent yet",
  noLink: "—",
  overdue: (d) => `${d} · overdue`,
  due_day: (iso) => `D(${iso})`,
  asked_day: (iso) => `A(${iso})`,
};

const action = (id: string, text: string, due: string | null, extra: Partial<S["FollowupAction"]> = {}): S["FollowupAction"] => ({
  id,
  text,
  due,
  project_name: "Book",
  links: [],
  told: null,
  told_days: null,
  followed_up: null,
  on_hold: null,
  chase_due: false, chases: 0,
  origin: null,
  ...extra,
});
const question = (id: string, title: string, sent: string | null, extra: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
  id,
  title,
  text: "",
  links: [],
  kind: "question",
  status: "open",
  project_name: "Book",
  sent,
  waiting_days: null,
  chase_due: false, chases: 0,
  about: null,
  options: [],
  ...extra,
});
const section = (actions: S["FollowupAction"][], questions: S["FollowupQuestion"][]): S["FollowupSection"] => ({
  person: "PER-2",
  name: "Robin Sample",
  is_pm: false,
  questions,
  actions,
  message: "",
  to_send: actions.length + questions.length,
});

const TODAY = "2026-10-16";

test("actions go by due date with the overdue first and undated last; questions by first asked with not sent yet last", () => {
  const found = tablesOf(
    section(
      [action("A3", "No date", null), action("A2", "Later", "2026-10-23"), action("A1", "Late", "2026-10-14")],
      [question("Q2", "New one", null), question("Q1", "Old one", "2026-10-10")],
    ),
    words,
    TODAY,
  );
  expect(found.map((t) => t.kind)).toEqual(["actions", "questions"]);
  expect(found[0].columns).toEqual(["Project", "Action", "Due", "Link", "Your update"]);
  expect(found[1].columns).toEqual(["Project", "Question", "First asked", "Link", "Your answer"]);
  expect(found[0].rows.map((r) => r[1].text)).toEqual(["Late", "Later", "No date"]);
  expect(found[0].rows.map((r) => r[2].text)).toEqual(["D(2026-10-14) · overdue", "D(2026-10-23)", ""]);
  expect(found[0].rows[0][2].overdue).toBe(true);
  expect(found[0].rows[1][2].overdue).toBe(false);
  expect(found[1].rows.map((r) => [r[1].text, r[2].text])).toEqual([
    ["Old one", "A(2026-10-10)"],
    ["New one", "Not sent yet"],
  ]);
});

test("only what the message holds is in the tables: told actions and sent questions are left out, and an empty kind has no table", () => {
  const found = tablesOf(section([action("A1", "Told", "2026-10-20", { told: "2026-10-01" })], [question("Q1", "Sent", "2026-10-01", { status: "sent" })]), words, TODAY);
  expect(found).toEqual([]);
});

test("the project is on every row and the fill-in column is last, widest, tinted in the HTML and holds nothing", () => {
  const found = tablesOf(section([action("A1", "One", null), action("A2", "Two", null, { project_name: "Other" })], []), words, TODAY);
  expect(found[0].rows.map((r) => r[0].text)).toEqual(["Book", "Other"]);
  expect(found[0].fill).toBe(4);
  expect(found[0].rows.every((r) => r[4].text === "")).toBe(true);
  const html = toHtml(found, words);
  expect(html).toContain(`background:${TINT};width:38%;">Your update</th>`);
  expect(html.match(new RegExp(`background:${TINT};width:38%;"></td>`, "g"))).toHaveLength(2);
  // No title row, no caption, no instructions and no merged cells.
  expect(html).not.toMatch(/caption|colspan|rowspan|<h\d/);
});

test("overdue is in words and in a danger colour in the HTML; a page is its name there and its full address for a spreadsheet", () => {
  const links = [{ label: "Book page", url: `${WEB}example.com/book` }];
  const found = tablesOf(section([action("A1", "Late", "2026-10-14", { links }), action("A2", "Plain", "2026-10-30")], [question("Q1", "Asked", "2026-10-10", { links })]), words, TODAY);
  const html = toHtml(found, words);
  expect(html).toContain(`color:${DANGER};font-weight:bold;">D(2026-10-14) · overdue</td>`);
  expect(html).toContain(`<a href="${WEB}example.com/book">Book page</a>`);
  expect(html).toContain("<td");
  const sheet = toTsv(found, words);
  expect(sheet.split("\n")[0]).toBe("Project\tAction\tDue\tLink\tYour update");
  expect(sheet).toContain(`Book\tLate\tD(2026-10-14) · overdue\t${WEB}example.com/book\t`);
  expect(sheet).toContain("Book\tPlain\tD(2026-10-30)\t—\t");
  expect(sheet).not.toContain("Book page");
  // Two tables are told apart by a blank line, and every row ends with the empty fill-in cell.
  expect(sheet.split("\n\n")).toHaveLength(2);
  expect(sheet.split("\n").filter((l) => l && !l.startsWith("Project")).every((l) => l.endsWith("\t"))).toBe(true);
});

test("a link that isn't a web address is never made one, and text with tabs or line breaks stays in its cell", () => {
  const found = tablesOf(section([action("A1", "Line one\nLine\ttwo <b>", null, { links: [{ label: "Odd", url: "javascript:alert(1)" }], project_name: "A & B" })], []), words, TODAY);
  const html = toHtml(found, words);
  expect(html).not.toContain("javascript:");
  expect(html).toContain("Odd");
  expect(html).toContain("A &amp; B");
  expect(html).toContain("Line one\nLine\ttwo &lt;b&gt;");
  const sheet = toTsv(found, words);
  expect(sheet).toContain("A & B\tLine one Line two <b>\t\t—\t");
});
