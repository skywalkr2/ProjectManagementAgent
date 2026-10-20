import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp } from "../test-utils";
import { RecordPage } from "./RecordPage";
import { SeriesPage } from "./SeriesPage";
import { TodayRail } from "./TodayRail";

// A meeting's agenda (design 7.14): the items put on it, each the words it is there under, linking to the action,
// question or note it came from, with who put it there and when. Shown on the meeting's page, on its series' page and
// under the meeting's row in Today's agenda.

const line = (over: Partial<S["AgendaLine"]> = {}): S["AgendaLine"] => ({
  kind: "action",
  id: "ACT-1",
  text: "Send the interior file",
  added_by: "PER-1",
  added_by_name: "Robin Sample",
  added_at: "2026-10-20T09:00:00Z",
  ...over,
});

const items = [line(), line({ kind: "question", id: "Q-4", text: "Which trim size?", added_by: null, added_by_name: null })];

const page = (over: Partial<S["RecordPageView"]> = {}): S["RecordPageView"] => ({
  kind: "event",
  id: "EVT-1",
  version: 2,
  name: "Planning sessions",
  details: [],
  open_actions: [],
  open_questions: [],
  completed_actions: [],
  fact_source: null,
  activity: [],
  agenda: items,
  ...over,
});

function meeting(shown: S["RecordPageView"]) {
  const fields = { id: "EVT-1", title: "Planning sessions", start: "2026-10-22", agenda: [{ action: "ACT-1", text: "x", added_at: "2026-10-20T09:00:00Z" }] };
  return fakeApi({
    "GET record?kind=event&id=EVT-1": () => ({ kind: "event", id: "EVT-1", version: 3, fields, long_text: [] }),
    "GET kinds/event": () => ({ kind: "event", fields: [] }),
    "GET record-pages/EVT-1?kind=event": () => shown,
    "GET people": () => [person("PER-1", "Robin Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    "GET plugin-actions?kind=event&id=EVT-1": () => [],
    "GET task-kinds?kind=event&id=EVT-1": () => [],
  });
}

test("a meeting's page lists what is on its agenda, each linking to what it came from, with who put it there and when", async () => {
  meeting(page());
  renderApp(<RecordPage kind="event" id="EVT-1" onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Agenda" });
  const rows = within(section).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(within(rows[0]).getByRole("link", { name: "Send the interior file" }).getAttribute("href")).toMatch(/#records\/action\/ACT-1$/);
  expect(rows[0]).toHaveTextContent(`Put there by Robin Sample, ${day("2026-10-20")}`);
  expect(within(rows[1]).getByRole("link", { name: "Which trim size?" }).getAttribute("href")).toMatch(/#records\/question\/Q-4$/);
  expect(rows[1]).toHaveTextContent(`Put there by Helper, ${day("2026-10-20")}`);
  // The list is not shown a second time as a raw detail.
  const details = screen.getByRole("heading", { name: "Details" }).closest("section") as HTMLElement;
  expect(within(details).queryByText("Agenda")).toBeNull();
});

test("a meeting with nothing on its agenda has no agenda section", async () => {
  meeting(page({ agenda: [] }));
  renderApp(<RecordPage kind="event" id="EVT-1" onBack={() => {}} />);
  await screen.findByRole("heading", { level: 1, name: "Planning sessions" });
  expect(screen.queryByRole("region", { name: "Agenda" })).toBeNull();
});

test("a series' page lists the agenda of the series and of its next meeting above what is open", async () => {
  const view: S["SeriesPageView"] = {
    id: "SER-1",
    title: "Planning sessions",
    repeats: "every Thursday",
    next: null,
    past: [],
    open_without_next: 0,
    usually_with: [],
    agenda: items,
  };
  fakeApi({ "GET series/SER-1/page": () => view });
  renderApp(<SeriesPage id="SER-1" onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Agenda" });
  expect(within(section).getAllByRole("listitem")).toHaveLength(2);
  expect(within(section).getByRole("link", { name: "Which trim size?" })).toBeInTheDocument();
});

test("a meeting's row in Today's agenda lists what is on its agenda as links", async () => {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const meetingRow: S["AgendaItemView"] = {
    snapshot: "EVT-1",
    source: "",
    title: "Planning sessions",
    start: iso,
    all_day: true,
    cancelled: false,
    own: true,
    open_items: 0,
    days: [iso],
    agenda: items,
  };
  fakeApi({
    "GET today/week": () => ({ first: iso, last: iso, due: [], waiting: [], meetings: [] }),
    "GET today/agenda": () => [meetingRow, { ...meetingRow, snapshot: "EVT-2", title: "Quiet sync", agenda: [] }],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET today/priorities": () => ({ lines: [], more: 0, blocked: 0, coming: [] }),
    "GET watch": () => [],
    "GET projects": () => [],
  });
  renderApp(<TodayRail onView={() => {}} />);
  const rail = await screen.findByRole("region", { name: "Agenda" });
  const rows = within(await within(rail).findByRole("list", { name: "Today" })).getAllByRole("listitem");
  const planning = rows.find((row) => row.textContent?.includes("Planning sessions"))!;
  const list = within(planning).getByRole("list", { name: "Agenda" });
  expect(within(list).getByRole("link", { name: "Send the interior file" }).getAttribute("href")).toMatch(/#records\/action\/ACT-1$/);
  expect(within(list).getByRole("link", { name: "Which trim size?" })).toBeInTheDocument();
  const quiet = rows.find((row) => row.textContent?.includes("Quiet sync"))!;
  expect(within(quiet).queryByRole("list", { name: "Agenda" })).toBeNull();
});
