import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { whenText } from "../lib/dates";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { TodayRail } from "./TodayRail";

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
  return { snapshot: `snap-${extra.title}`, source: "cal-1", start: at(TODAY, 15), all_day: false, cancelled: false, own: false, days: [TODAY], ...extra };
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
    ...extra,
  };
}

function open(extra: Routes = {}, onView = vi.fn(), onAddSource?: () => void) {
  const calls = fakeApi(routes(extra));
  renderApp(<TodayRail onView={onView} onAddSource={onAddSource} />);
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

test("three panels in reading order, each with its heading and count, and nothing about what needs you", async () => {
  open();
  const agendaColumn = await column("Agenda");
  expect(await within(agendaColumn).findByText("3 events today")).toBeInTheDocument();
  const list = await column("Your to-dos");
  await within(list).findByText("4 things to do");
  const names = screen
    .getAllByRole("region")
    .map((r) => r.parentElement?.getAttribute("data-col"))
    .filter(Boolean);
  expect(names).toEqual(["agenda", "todo", "arrived"]);
  expect(screen.getByRole("heading", { level: 2, name: "Came in" })).toBeInTheDocument();
  await within(await column("Came in")).findByText("2 messages");
  // What needs the person is the queue, which has its own tests; the rail never draws it.
  expect(screen.queryByRole("heading", { name: "Needs you" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "What changed" })).toBeNull();
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

test("the app's own entries follow the calendar events on each day they cover, marked in words, all-day ones with no time", async () => {
  const own = (extra: Partial<S["AgendaItemView"]>) =>
    event({ title: "Delivery window", snapshot: "EVT-1", source: "", own: true, all_day: true, start: TODAY, end: TOMORROW, days: [TODAY, TOMORROW], ...extra });
  open({
    "GET today/agenda": () => [
      event({ title: "Standup", start: at(TODAY, 9), end: at(TODAY, 9, 30) }),
      event({ title: "Planning", all_day: true, start: TODAY, days: [TODAY] }),
      own({}),
    ],
  });
  const col = await column("Agenda");
  const today = within(await within(col).findByRole("list", { name: "Today" })).getAllByRole("listitem");
  const rowOf = (text: string) => today.findIndex((row) => row.textContent?.includes(text));
  expect(rowOf("Planning")).toBeLessThan(rowOf("Standup"));
  expect(rowOf("Standup")).toBeLessThan(rowOf("Delivery window"));
  expect(today[rowOf("Delivery window")]).toHaveTextContent("All day");
  expect(today.filter((row) => row.textContent?.includes("From your notes"))).toHaveLength(1);
  expect(today[rowOf("Delivery window")]).toHaveTextContent("From your notes");
  const tomorrow = within(within(col).getByRole("list", { name: "Tomorrow" })).getAllByRole("listitem");
  expect(tomorrow[0]).toHaveTextContent("Delivery window");
  expect(tomorrow[0]).toHaveTextContent("From your notes");
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
  const col = await column("Your to-dos");
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

test("to do: an action on hold leaves Overdue and sits last under On hold, saying what it waits for", async () => {
  const held: S["TodoView"] = { action: "ACT-5", text: "Sign the contract", project: null, due: "2026-10-01", overdue: false, on_hold: "legal review" };
  open({ "GET today/todo": () => [...todo, held] });
  const col = await column("Your to-dos");
  const heads = await within(col).findAllByRole("heading", { level: 3 });
  expect(heads.map((h) => h.textContent)).toEqual(["Overdue 1", "Today 1", "Later 1", "No date 1", "On hold 1"]);
  const group = within(col).getByRole("heading", { name: "On hold 1" }).closest("[data-group]") as HTMLElement;
  expect(within(group).getByText("On hold: legal review")).toHaveAttribute("title", expect.stringMatching(/^Was due .*1/));
  expect(group).not.toHaveTextContent(/Due /);
  const overdue = within(col).getByRole("heading", { name: "Overdue 1" }).closest("[data-group]") as HTMLElement;
  expect(overdue).not.toHaveTextContent("Sign the contract");
});

test("marking a to-do done uses the action path and offers Undo", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({
    "POST actions/ACT-1/status": () => ({ ok: "ACT-1" }),
  });
  await user.click(await screen.findByRole("checkbox", { name: "Mark done: Send the index" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST actions/ACT-1/status")).toBe(true));
  expect(calls.find((c) => c.route === "POST actions/ACT-1/status")!.body).toEqual({ status: "done" });
  expect(await screen.findByText("Marked done.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("Drop on a to-do asks why with the cursor in the field, acts at once and Undo takes it back", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({
    "POST actions/ACT-1/drop": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }),
  });
  await user.click(await screen.findByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop" }));
  const field = await screen.findByRole("textbox", { name: "Why isn't it needed?" });
  expect(field).toHaveFocus();
  const form = field.closest("form") as HTMLElement;
  expect(within(form).getByRole("button", { name: "Drop it" })).toBeDisabled();
  await user.type(field, "The index moved to the printer");
  await user.click(within(form).getByRole("button", { name: "Drop it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/drop")?.body).toEqual({ reason: "The index moved to the printer" }));
  expect(await screen.findByText("Dropped.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("a to-do's menu adds a note to Mark done, with the cursor in the box", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({
    "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: "REQ-4" }),
  });
  await user.click(await screen.findByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Add a note" }));
  const box = await screen.findByRole("textbox", { name: "Your note" });
  expect(box).toHaveFocus();
  await user.type(box, "The printer has it now.");
  await user.keyboard("{Enter}");
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST actions/ACT-1/status")!.body).toEqual({ status: "done", note: "The printer has it now." }),
  );
  expect(await screen.findByText("Marked done. Helper will read your note.")).toBeInTheDocument();
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
    read_at: at(TODAY, 11, 30),
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
      watched("a", { last: { outcome: "ok", started_at: at(TODAY, 8, 5), new: 0, changed: 0, removed: 0 }, read_at: at(TODAY, 8, 5) }),
      watched("b", { last: { outcome: "ok", started_at: at(TODAY, 11, 40), new: 0, changed: 0, removed: 0 }, read_at: at(TODAY, 11, 40) }),
      watched("c", { last: null, read_at: null }),
    ],
  });
  expect(await screen.findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
  expect(await screen.findByText("No mail has come in lately.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByText(`Checked ${whenText(at(TODAY, 11, 40))}`)).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Connect a calendar" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Connect a mailbox" })).toBeNull();
});

test("a source that hasn't been read yet says the cards are not checked yet", async () => {
  open({ ...EMPTY, "GET watch": () => [watched("a", { last: null, read_at: null })] });
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
  return { ...inbox, new_items: 0, sources_read: 1, sources_failed: 0, sources_busy: 0, problems: [], ...over };
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
  renderApp(<TodayRail onView={vi.fn()} />);
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

// ---- Change this, and what was learned -------------------------------------------------------------------------------

test("a to-do's menu has Change this, which posts the person's note about that action", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({ "POST items/action/ACT-2/change": () => ({ ok: "ACT-2", request: "REQ-7", signal: "SIG-1" }) });
  const col = await column("Your to-dos");
  await user.click(await within(col).findByRole("button", { name: "More actions for Approve the proof" }));
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "Due on Friday instead");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST items/action/ACT-2/change")?.body).toEqual({ note: "Due on Friday instead" }));
  expect(await screen.findByText("Helper will look at it.")).toBeInTheDocument();
});

test("an entry in the app's own calendar has Change this; an event read from a calendar does not", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  const { calls } = open({
    "GET today/agenda": () => [
      event({ title: "Standup", start: at(TODAY, 9), end: at(TODAY, 9, 30) }),
      event({ title: "Delivery window", snapshot: "EVT-1", source: "", own: true, all_day: true, start: TODAY, days: [TODAY] }),
    ],
    "POST items/event/EVT-1/change": () => ({ ok: "EVT-1", request: null, signal: "SIG-2" }),
  });
  const col = await column("Agenda");
  await within(col).findByText("Delivery window");
  expect(within(col).queryByRole("button", { name: "More actions for Standup" })).toBeNull();
  await user.click(within(col).getByRole("button", { name: "More actions for Delivery window" }));
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "It is a day later");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST items/event/EVT-1/change")?.body).toEqual({ note: "It is a day later" }));
});

test("what is being learned from a change asked for on a to-do shows on that row", async () => {
  open({
    "GET knowledge/learned": () => ({
      lines: [{ signal: "SIG-1", kind: "change_requested", changeset: null, refs: ["ACT-2"], state: "learning", waiting: "With the assistant, starting now" }],
    }),
  });
  const col = await column("Your to-dos");
  const row = (await within(col).findByText("Approve the proof")).closest("li")!;
  expect(await within(row).findByRole("status")).toHaveTextContent("Learning from this…");
});

const unread = (id: string, reads: S["WatchSourceView"]["reads"], outcome: "failed" | "offline", over: Partial<S["WatchSourceView"]> = {}) =>
  watched(id, {
    reads,
    last: { outcome, started_at: at(TODAY, 11, 45), new: 0, changed: 0, removed: 0 },
    read_at: null,
    failures: 1,
    ...over,
  });

test("an empty calendar card says the calendar couldn't be read, with why and what to do, never that it is empty or checked", async () => {
  open({
    ...EMPTY,
    "GET watch": () => [
      unread("cal", ["calendar"], "failed", {
        label: "Work calendar",
        problem: "Work calendar can't be read: the service refused the sign-in. Sign in to it again, then it is read on its next turn.",
      }),
      watched("mail", { reads: ["mail"] }),
    ],
  });
  const col = await column("Agenda");
  expect(await within(col).findByText("Your calendar couldn't be read, so this list may be missing events.")).toBeInTheDocument();
  expect(within(col).getByRole("alert")).toHaveTextContent("the service refused the sign-in. Sign in to it again");
  expect(within(col).queryByText("Nothing on your calendar for the next few days.")).toBeNull();
  expect(within(col).queryByText(/^Checked /)).toBeNull();
  // The mail card has no unread source of its own: it says what it always says.
  expect(await within(await column("Came in")).findByText("No mail has come in lately.")).toBeInTheDocument();
});

test("an empty mail card says the mailbox wasn't read when there was no network, and the calendar card is unaffected", async () => {
  open({
    ...EMPTY,
    "GET watch": () => [unread("mail", ["mail"], "offline", { label: "Work mail" }), watched("cal", { reads: ["calendar"] })],
  });
  const col = await column("Came in");
  expect(await within(col).findByText("Your mail couldn't be read, so this list may be missing messages.")).toBeInTheDocument();
  expect(within(col).getByRole("alert")).toHaveTextContent("Work mail couldn't be checked without an internet connection. It will retry automatically.");
  expect(within(col).queryByText("No mail has come in lately.")).toBeNull();
  expect(await within(await column("Agenda")).findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
});

test("a source of a kind with no unread source never changes the empty card, and a source that is off is not reported", async () => {
  open({ ...EMPTY, "GET watch": () => [unread("cal", ["calendar"], "failed", { enabled: false }), watched("b", { reads: ["calendar"] })] });
  expect(await screen.findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
});

test("Check now says which source couldn't be read and why, in place of only a count", async () => {
  const user = userEvent.setup({ advanceTimers: () => {} });
  open({
    "GET watch": () => [watched("a"), watched("b")],
    "POST today/arrived/check": () =>
      checked({ sources_failed: 1, problems: ["Source b can't be read: the service refused the sign-in. Sign in to it again, then it is read on its next turn."] }),
  });
  await user.click(await within(await column("Came in")).findByRole("button", { name: "Check now" }));
  expect(
    await screen.findByText("Nothing new. Source b can't be read: the service refused the sign-in. Sign in to it again, then it is read on its next turn."),
  ).toBeInTheDocument();
});

test("empty panels show no count of zero, in words or as a badge", async () => {
  open({
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
  });
  expect(await screen.findByText("Nothing on your calendar for the next few days.")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/\b0 (events|things|messages)/);
  for (const column of ["agenda", "todo", "arrived"]) {
    const col = document.querySelector(`[data-col="${column}"]`) as HTMLElement;
    expect(within(col).queryByText("0")).toBeNull();
  }
});
