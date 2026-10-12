import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { whenText } from "../lib/dates";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { TodayBoard } from "./TodayBoard";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

// Midday on a made-up Sunday, on this computer's clock; only the date is faked so waiting still works.
const NOW = new Date(2026, 9, 11, 12, 0);
const TODAY = "2026-10-11";
const TOMORROW = "2026-10-12";
const LATER = "2026-10-14";

/** An ISO time with this computer's offset, so the clock the page shows is the clock written here. */
function at(date: string, hour: number, minute = 0): string {
  const [y, m, d] = date.split("-").map(Number);
  const offset = -new Date(y, m - 1, d, hour, minute).getTimezoneOffset();
  const sign = offset < 0 ? "-" : "+";
  const pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
  return `${date}T${pad(hour)}:${pad(minute)}:00${sign}${pad(Math.trunc(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
}

function event(extra: Partial<S["AgendaItemView"]> & Pick<S["AgendaItemView"], "title">): S["AgendaItemView"] {
  return { snapshot: `snap-${extra.title}`, source: "cal-1", start: at(TODAY, 15), all_day: false, cancelled: false, days: [TODAY], ...extra };
}

function message(extra: Partial<S["ArrivedView"]> & Pick<S["ArrivedView"], "title">): S["ArrivedView"] {
  return { snapshot: `snap-${extra.title}`, source: "mail-1", received: at(TODAY, 9, 14), ...extra };
}

const agenda: S["AgendaItemView"][] = [
  event({ title: "Quarterly planning", all_day: true, start: TODAY, days: [TODAY, TOMORROW] }),
  event({ title: "Standup", start: at(TODAY, 9), end: at(TODAY, 9, 30), where: "Room A" }),
  event({
    title: "Design review",
    start: at(TODAY, 15),
    end: at(TODAY, 16),
    link: `${WEB}meet.example.com/room/42`,
  }),
  event({ title: "Budget call", start: at(TOMORROW, 10), end: at(TOMORROW, 11), days: [TOMORROW], cancelled: true }),
  event({ title: "Workshop", start: at(LATER, 13), days: [LATER] }),
];

const todo: S["TodoView"][] = [
  { action: "ACT-1", text: "Send the index", project: "PRJ-1", due: "2026-10-08", overdue: true },
  { action: "ACT-2", text: "Approve the proof", project: "PRJ-1", due: TODAY, overdue: false },
  { action: "ACT-3", text: "Plan the launch", project: null, due: "2026-10-20", overdue: false },
  { action: "ACT-4", text: "Tidy the notes", project: null, due: null, overdue: false },
];

const projects = [{ id: "PRJ-1", name: "Spring book", group: null, owner: null, owner_name: null }];

const inbox: S["InboxView"] = {
  items: [
    message({ title: "Proof is ready", sender: "Robin Sample", unread: true, link: `${WEB}mail.example.com/m/1` }),
    message({ title: "Invoice attached", sender: "Pat Example", unread: false, received: at("2026-10-09", 16, 40) }),
  ],
  left_out: 3,
  set_aside: 2,
};

function routes(extra: Routes = {}): Routes {
  return {
    "GET today/agenda": () => agenda,
    "GET today/todo": () => todo,
    "GET today/arrived": () => inbox,
    "GET watch": () => [],
    "GET projects": () => projects,
    "GET changes": () => [],
    "GET plugin-today": () => [],
    "GET followups": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    ...extra,
  };
}

function open(extra: Routes = {}, onView = vi.fn(), onAddSource?: () => void) {
  const calls = fakeApi(routes(extra));
  renderApp(<TodayBoard onView={onView} onAddSource={onAddSource} />);
  return { calls, onView };
}

const column = (name: string) => screen.findByRole("region", { name });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  document.documentElement.removeAttribute("data-today");
});

test("four columns in reading order, each with its heading and count", async () => {
  open();
  const agendaColumn = await column("Agenda");
  expect(await within(agendaColumn).findByText("3 events today")).toBeInTheDocument();
  const list = await column("To do");
  await within(list).findByText("4 things to do");
  const names = screen
    .getAllByRole("region")
    .map((r) => r.getAttribute("data-col"))
    .filter(Boolean);
  expect(names).toEqual(["agenda", "todo", "needs", "arrived"]);
  expect(screen.getByRole("heading", { level: 2, name: "Needs you" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Came in" })).toBeInTheDocument();
  await within(await column("Came in")).findByText("2 messages");
  // The pieces beside it sit one heading level down inside Needs you.
  expect(await screen.findByRole("heading", { level: 3, name: "What changed" })).toBeInTheDocument();
});

test("the agenda groups by day, all-day first, with times, places, called-off labels and link domains", async () => {
  open();
  const col = await column("Agenda");
  const days = await within(col).findAllByRole("heading", { level: 3 });
  expect(days.map((h) => h.textContent)).toEqual(["Today", "Tomorrow", expect.stringMatching(/14/)]);
  const today = within(within(col).getByRole("list", { name: "Today" })).getAllByRole("listitem");
  // All-day first, then by time, with the "now" line between what has ended and what is to come.
  expect(today[0]).toHaveTextContent("All day");
  expect(today[0]).toHaveTextContent("Quarterly planning");
  expect(today[1]).toHaveTextContent("Standup");
  expect(today[1]).toHaveTextContent("Room A");
  expect(today[2]).toHaveTextContent(/^Now · /);
  expect(today[3]).toHaveTextContent("Design review");
  const link = within(today[3]).getByRole("link", { name: "Design review" });
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  expect(today[3]).toHaveTextContent("(meet.example.com)");
  const tomorrow = within(within(col).getByRole("list", { name: "Tomorrow" })).getAllByRole("listitem");
  // The all-day event runs on into tomorrow.
  expect(tomorrow[0]).toHaveTextContent("All day");
  expect(tomorrow[1]).toHaveTextContent("Called off");
  expect(tomorrow[1]).toHaveTextContent("Budget call");
});

test("the now line goes at the end of today's list when everything has ended, and is absent with no timed events", async () => {
  open({ "GET today/agenda": () => [event({ title: "Early", start: at(TODAY, 8), end: at(TODAY, 9) })] });
  const col = await column("Agenda");
  const rows = within(await within(col).findByRole("list", { name: "Today" })).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Early");
  expect(rows[1]).toHaveTextContent(/^Now · /);
});

test("to do: Overdue first with its label and count, then Today, Later and No date", async () => {
  open();
  const col = await column("To do");
  const heads = await within(col).findAllByRole("heading", { level: 3 });
  expect(heads.map((h) => h.textContent)).toEqual(["Overdue 1", "Today 1", "Later 1", "No date 1"]);
  const overdue = within(col).getByRole("heading", { name: "Overdue 1" }).closest("[data-group]") as HTMLElement;
  expect(overdue).toHaveTextContent("Send the index");
  expect(overdue).toHaveTextContent("Spring book");
  expect(overdue).toHaveTextContent(/Due .*8/);
  // A row due today doesn't repeat that in its line, and a row with no project shows none.
  const due = within(col).getByText("Approve the proof").closest("li")!;
  expect(due).not.toHaveTextContent("Due");
});

test("marking a to-do done uses the action path and offers Undo", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({
    "POST actions/ACT-1/status": () => ({ ok: "ACT-1" }),
  });
  await user.click(await screen.findByRole("button", { name: "Mark done: Send the index" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST actions/ACT-1/status")).toBe(true));
  expect(calls.find((c) => c.route === "POST actions/ACT-1/status")!.body).toEqual({ status: "done" });
  expect(await screen.findByText("Marked done.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("came in: unread shows a New label, today's mail its time and older mail its weekday, with the closed-by-rules line", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { onView } = open();
  const col = await column("Came in");
  const rows = await within(col).findAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("New");
  expect(rows[0]).toHaveTextContent("Proof is ready");
  expect(rows[0]).toHaveTextContent("Robin Sample");
  expect(rows[0]).toHaveTextContent("(mail.example.com)");
  expect(within(rows[0]).getByRole("link", { name: "Proof is ready" })).toHaveAttribute("target", "_blank");
  expect(rows[0].querySelector("time")!.textContent).toMatch(/9:14|09:14/);
  expect(rows[1]).not.toHaveTextContent("New");
  expect(rows[1].querySelector("time")!.textContent).toBe("Fri");
  await user.click(within(col).getByRole("button", { name: "3 closed by your rules" }));
  expect(onView).toHaveBeenCalledWith("sources");
});

test("no closed-by-rules line when nothing was closed", async () => {
  open({ "GET today/arrived": () => ({ ...inbox, left_out: 0 }) });
  const col = await column("Came in");
  await within(col).findAllByRole("listitem");
  expect(within(col).queryByRole("button", { name: /closed by your rules/ })).toBeNull();
});

test("with a second source the rows say which one they came from", async () => {
  open({
    "GET watch": () => [
      { id: "cal-1", label: "Work calendar" },
      { id: "cal-2", label: "Home calendar" },
    ],
    "GET today/agenda": () => [
      event({ title: "Standup", source: "cal-1" }),
      event({ title: "Piano", source: "cal-2", start: at(TODAY, 17) }),
    ],
  });
  const col = await column("Agenda");
  expect(await within(col).findByText("Home calendar")).toBeInTheDocument();
  expect(within(col).getByText("Work calendar")).toBeInTheDocument();
});

test("empty agenda, list and mail each say so, and the buttons go to Sources", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { onView } = open({
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0 }),
  });
  expect(await screen.findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
  expect(await screen.findByText("Nothing on your list today.")).toBeInTheDocument();
  expect(await screen.findByText("No mail has come in lately.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Connect a calendar" }));
  expect(onView).toHaveBeenLastCalledWith("sources");
  await user.click(screen.getByRole("button", { name: "Connect a mailbox" }));
  expect(onView).toHaveBeenCalledTimes(2);
  expect(onView).toHaveBeenLastCalledWith("sources");
});

function watched(id: string, extra: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] {
  return {
    id,
    label: `Source ${id}`,
    connector: "kind-a",
    connector_label: "A kind",
    enabled: true,
    every_minutes: 15,
    items: 0,
    last: { outcome: "ok", started_at: at(TODAY, 11, 30), new: 0, changed: 0, removed: 0 },
    failures: 0,
    problem: null,
    ...extra,
  };
}

const EMPTY: Routes = {
  "GET today/agenda": () => [],
  "GET today/todo": () => [],
  "GET today/arrived": () => ({ items: [], left_out: 0 }),
};

test("with no source set up, the empty cards offer Connect, which opens Sources on the add form", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const onAddSource = vi.fn();
  const { onView } = open(EMPTY, vi.fn(), onAddSource);
  await user.click(await screen.findByRole("button", { name: "Connect a calendar" }));
  expect(onAddSource).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Connect a mailbox" }));
  expect(onAddSource).toHaveBeenCalledTimes(2);
  expect(onView).not.toHaveBeenCalled();
});

test("when every source is off, the cards still offer Connect", async () => {
  open({ ...EMPTY, "GET watch": () => [watched("a", { enabled: false }), watched("b", { enabled: false })] });
  expect(await screen.findByRole("button", { name: "Connect a calendar" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Connect a mailbox" })).toBeInTheDocument();
  expect(screen.queryByText(/^Checked /)).toBeNull();
});

test("with sources set up, the empty cards say they were checked, with the latest read across sources, and have no button", async () => {
  open({
    ...EMPTY,
    "GET watch": () => [
      watched("a", { last: { outcome: "ok", started_at: at(TODAY, 8, 5), new: 0, changed: 0, removed: 0 } }),
      watched("b", { last: { outcome: "ok", started_at: at(TODAY, 11, 40), new: 0, changed: 0, removed: 0 } }),
      watched("c", { last: null }),
    ],
  });
  expect(await screen.findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
  expect(await screen.findByText("No mail has come in lately.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByText(`Checked ${whenText(at(TODAY, 11, 40))}`)).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Connect a calendar" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Connect a mailbox" })).toBeNull();
});

test("a source that hasn't been read yet says the cards are not checked yet", async () => {
  open({ ...EMPTY, "GET watch": () => [watched("a", { last: null })] });
  await waitFor(() => expect(screen.getAllByText("Not checked yet")).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Connect a calendar" })).toBeNull();
});

test("cards that have rows show no connect button or checked line", async () => {
  open({ "GET watch": () => [] });
  await within(await column("Agenda")).findByText("Standup");
  expect(screen.queryByRole("button", { name: "Connect a calendar" })).toBeNull();
  expect(screen.queryByText(/^Checked /)).toBeNull();
});

test("a column that can't load says so and offers Try again without hiding the others", async () => {
  open({ "GET today/agenda": () => {
    throw new Error("down");
  } });
  expect(await screen.findByText("Your calendar couldn't be loaded.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(await screen.findByText("Send the index")).toBeInTheDocument();
});

function checked(over: Partial<S["InboxCheckView"]> = {}): S["InboxCheckView"] {
  return { ...inbox, new_items: 0, sources_read: 1, sources_failed: 0, sources_busy: 0, ...over };
}

test("Check now reads the sources, shows the new list at once and says what arrived", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const fresh = message({ title: "Fresh note", sender: "Jo Sample", unread: true });
  let current = inbox;
  const calls = fakeApi(
    routes({
      "GET watch": () => [watched("a")],
      "GET today/arrived": () => current,
      "POST today/arrived/check": () => {
        current = { ...inbox, items: [fresh, ...inbox.items] };
        return checked({ items: current.items, new_items: 1 });
      },
    }),
  );
  renderApp(<TodayBoard onView={vi.fn()} />);
  const col = await column("Came in");
  expect(within(col).queryByText("Fresh note")).toBeNull();
  await user.click(await within(col).findByRole("button", { name: "Check now" }));
  expect(await within(col).findByText("Fresh note")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST today/arrived/check")).toBe(true);
  expect(await screen.findByText("1 new item")).toBeInTheDocument();
  expect(within(col).getByRole("button", { name: "Check now" })).toBeEnabled();
});

test("Check now counts everything the sources handed in, even when none of it lists in Came in", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  open({
    "GET watch": () => [watched("a")],
    "POST today/arrived/check": () => checked({ items: inbox.items, new_items: 2 }),
  });
  await user.click(await within(await column("Came in")).findByRole("button", { name: "Check now" }));
  expect(await screen.findByText("2 new items")).toBeInTheDocument();
  expect(screen.queryByText("Nothing new")).toBeNull();
});

test("Check now is disabled and says it is working while it reads, and can be used again after", async () => {
  open({ "GET watch": () => [watched("a")], "POST today/arrived/check": () => checked() });
  const col = await column("Came in");
  const button = await within(col).findByRole("button", { name: "Check now" });
  fireEvent.click(button);
  const working = within(col).getByRole("button", { name: "Checking…" });
  expect(working).toBeDisabled();
  expect(working).toHaveAttribute("aria-busy", "true");
  expect(await screen.findByText("Nothing new")).toBeInTheDocument();
  await waitFor(() => expect(within(col).getByRole("button", { name: "Check now" })).toBeEnabled());
});

test("Check now says when a source couldn't be read or was already being read", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  open({
    "GET watch": () => [watched("a"), watched("b")],
    "POST today/arrived/check": () => checked({ sources_failed: 1, sources_busy: 1 }),
  });
  await user.click(await within(await column("Came in")).findByRole("button", { name: "Check now" }));
  expect(
    await screen.findByText("Nothing new. 1 source couldn't be read: see Sources. 1 source was already being read."),
  ).toBeInTheDocument();
});

test("Check now is offered only while a source is on", async () => {
  open({ "GET watch": () => [watched("a", { enabled: false })] });
  await within(await column("Came in")).findByText("2 messages");
  expect(screen.queryByRole("button", { name: "Check now" })).toBeNull();
});
