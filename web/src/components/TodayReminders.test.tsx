import "@testing-library/jest-dom/vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { dateAndTime, useReminderNotices } from "./ReminderLine";
import { forgetLine } from "../lib/today";
import { wallTime } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Notifications } from "./Notifications";
import { Today } from "./Today";
import { TodoRow } from "./TodayRail";

// Reminders on Today (design 6.32, 7.7): a line for a reminder that has reached the person, with Done first and the snooze
// choices in its menu, each with the time it moves to; the one line for reminders that waited for quiet hours; and the
// browser notification, which is asked for only from a button in Settings.

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  return { key: `${kind}:1`, group: "risk", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const SNOOZES: S["SnoozeChoiceView"][] = [
  { choice: "in 1 hour", at: "2026-10-19T15:40:00-04:00" },
  { choice: "this evening", at: "2026-10-19T18:00:00-04:00" },
  { choice: "tomorrow morning", at: "2026-10-20T09:00:00-04:00" },
  { choice: "next week", at: "2026-10-26T09:00:00-04:00" },
];

const reminder = (over: Partial<Line> = {}) =>
  line("reminder", { key: "reminder:ACT-1", text: "Send Oren the estimate", subject: "Send Oren the estimate", actions: ["ACT-1"], at: "2026-10-19T14:40:00-04:00", late: false, snoozes: SNOOZES, ...over });

const digest = (over: Partial<Line> = {}) =>
  line("reminder_digest", {
    key: "reminder_digest:quiet",
    count: 2,
    late: false,
    actions: ["ACT-1", "ACT-2"],
    snoozes: SNOOZES,
    reminders: [
      { action: "ACT-1", text: "Send Oren the estimate", at: "2026-10-18T21:30:00-04:00" },
      { action: "ACT-2", text: "Call the printer", at: "2026-10-19T05:00:00-04:00" },
    ],
    ...over,
  });

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
    "GET followups": () => [],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET people": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const rowOf = async (title: string) => (await screen.findByRole("group", { name: title })) as HTMLElement;
const menuOf = async (user: ReturnType<typeof userEvent.setup>, row: HTMLElement) => user.click(within(row).getByRole("button", { name: /More actions for/ }));

// ---- the line --------------------------------------------------------------------------------------------------------

test("a reminder that has come due is the task with when it is due, and Done is its one button", async () => {
  const user = userEvent.setup();
  const calls = show([reminder()], { "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: null }) });
  const row = await rowOf("Send Oren the estimate · due now");
  expect(within(row).getByText("Reminder")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "done" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST actions/ACT-1/status").map((c) => c.body)).toEqual([{ status: "done" }, { status: "open" }]));
});

test("a reminder that came due while the computer was asleep says when it was due and is still shown", async () => {
  show([reminder({ late: true, at: "2026-10-19T09:30:00-04:00" })]);
  const row = await rowOf(`Send Oren the estimate · late: due ${wallTime("2026-10-19T09:30:00-04:00")}, while this computer was asleep`);
  expect(within(row).getByRole("button", { name: "Done" })).toBeInTheDocument();
});

// ---- snooze ----------------------------------------------------------------------------------------------------------

test("the snooze menu lists each choice with the time it moves to and leaves out a choice with no time left", async () => {
  const user = userEvent.setup();
  show([reminder()]);
  await menuOf(user, await rowOf("Send Oren the estimate · due now"));
  const names = screen.getAllByRole("menuitem").map((m) => m.textContent);
  expect(names).toEqual([
    "Add a note",
    `In 1 hour · ${wallTime("2026-10-19T15:40:00-04:00")}`,
    `This evening · ${wallTime("2026-10-19T18:00:00-04:00")}`,
    `Tomorrow morning · ${wallTime("2026-10-20T09:00:00-04:00")}`,
    `Next week · ${dateAndTime("2026-10-26T09:00:00-04:00")}`,
    "Pick a time…",
  ]);
  expect(screen.getByText("Snooze")).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: /Later today/ })).toBeNull();
});

test("a snooze choice moves the reminder as the person's own edit and Undo puts it back", async () => {
  const user = userEvent.setup();
  const calls = show([reminder()], { "POST reminders/ACT-1": () => ({ changeset: "CS-3" }), "POST changesets/CS-3/undo": () => ({ restored: [0], skipped: [] }) });
  await menuOf(user, await rowOf("Send Oren the estimate · due now"));
  await user.click(screen.getByRole("menuitem", { name: /^Tomorrow morning/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST reminders/ACT-1")?.body).toEqual({ choice: "tomorrow morning" }));
  expect(await screen.findByText(`Snoozed until ${wallTime("2026-10-20T09:00:00-04:00")}.`)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-3/undo")).toBe(true));
});

test("Pick a time puts the cursor in a day and time box, and saving sends that time", async () => {
  const user = userEvent.setup();
  const calls = show([reminder()], { "POST reminders/ACT-1": () => ({ changeset: "CS-4" }) });
  await menuOf(user, await rowOf("Send Oren the estimate · due now"));
  await user.click(screen.getByRole("menuitem", { name: "Pick a time…" }));
  const box = await screen.findByLabelText("Remind me at");
  expect(box).toHaveAttribute("type", "datetime-local");
  await waitFor(() => expect(box).toHaveFocus());
  fireEvent.change(box, { target: { value: "2026-10-21T10:30" } });
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST reminders/ACT-1")?.body).toEqual({ at: "2026-10-21T10:30" }));
});

// ---- the quiet-hours digest ---------------------------------------------------------------------------------------

test("reminders that waited for quiet hours to end are one line with a title and a line for each task", async () => {
  const user = userEvent.setup();
  const calls = show([digest()], { "POST actions/ACT-2/status": () => ({ ok: "ACT-2", request: null }) });
  const row = await rowOf("Saved during quiet hours");
  expect(within(row).getByText(`Send Oren the estimate · was due ${dateAndTime("2026-10-18T21:30:00-04:00")}`)).toBeInTheDocument();
  expect(within(row).getByText(`Call the printer · was due ${dateAndTime("2026-10-19T05:00:00-04:00")}`)).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Mark done: Call the printer" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-2/status")?.body).toEqual({ status: "done" }));
});

test("a reminder in the digest can be snoozed from its own menu", async () => {
  const user = userEvent.setup();
  const calls = show([digest()], { "POST reminders/ACT-1": () => ({ changeset: "CS-5" }) });
  const row = await rowOf("Saved during quiet hours");
  const first = row.querySelector<HTMLElement>('[data-reminder="ACT-1"]')!;
  await user.click(within(first).getByRole("button", { name: /More actions for/ }));
  await user.click(screen.getByRole("menuitem", { name: /^In 1 hour/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST reminders/ACT-1")?.body).toEqual({ choice: "in 1 hour" }));
});

test("reminders missed while the computer slept, when the person chose one summary, are a line with their own title", async () => {
  show([digest({ key: "reminder_digest:missed", late: true })]);
  expect(await rowOf("Missed while this computer was asleep")).toBeInTheDocument();
});

// ---- the notification ---------------------------------------------------------------------------------------------

// Shows the lines the test gives it, one list after another, as the queue's polling does.
function lineSource(first: Line[]) {
  let set: (lines: Line[]) => void = () => undefined;
  function Host() {
    const [lines, setLines] = useState(first);
    set = setLines;
    useReminderNotices(lines);
    return null;
  }
  return { Host, show: (lines: Line[]) => act(() => set(lines)) };
}

function stubNotification(permission: NotificationPermission) {
  const shown: Array<{ title: string; options?: NotificationOptions }> = [];
  const request = vi.fn(async () => "granted" as NotificationPermission);
  class Fake {
    static permission = permission;
    static requestPermission = request;
    constructor(title: string, options?: NotificationOptions) {
      shown.push({ title, options });
    }
  }
  vi.stubGlobal("Notification", Fake);
  return { shown, request };
}

test("a reminder line that appears while the app is open is shown as one notification with its words, not the ones already there", () => {
  const { shown } = stubNotification("granted");
  const here = reminder({ key: "reminder:ACT-9", text: "Already here" });
  const source = lineSource([here]);
  renderApp(<source.Host />);
  expect(shown).toEqual([]);
  source.show([here, reminder()]);
  expect(shown.map((s) => s.title)).toEqual(["Send Oren the estimate · due now"]);
});

test("nothing is shown without permission", () => {
  const { shown } = stubNotification("default");
  const source = lineSource([]);
  renderApp(<source.Host />);
  source.show([reminder()]);
  expect(shown).toEqual([]);
});

test("the quiet-hours digest is one notification with its title and a line for each task", () => {
  const { shown } = stubNotification("granted");
  const source = lineSource([]);
  renderApp(<source.Host />);
  source.show([digest()]);
  expect(shown).toHaveLength(1);
  expect(shown[0].title).toBe("Saved during quiet hours");
  expect(shown[0].options?.body).toContain("Call the printer · was due");
});

// ---- the permission button ----------------------------------------------------------------------------------------

const noticesView = (over: Partial<S["NotificationsView"]> = {}): S["NotificationsView"] => ({
  enabled: false,
  browser: true,
  webhook: { where: "none", name: null },
  quiet_now: false,
  mail_ready: false,
  problem: null,
  ...over,
});

function showNotices() {
  fakeApi({ "GET setup": () => ({ local: true, steps: [] }), "GET notifications": () => noticesView() });
  return renderApp(<Notifications />);
}

test("the browser is asked only when the person presses the button in Settings", async () => {
  const user = userEvent.setup();
  const { request } = stubNotification("default");
  showNotices();
  expect(request).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Allow notifications" }));
  expect(request).toHaveBeenCalledTimes(1);
});

test("Settings says when notifications are allowed, blocked or not possible here", () => {
  stubNotification("granted");
  const granted = showNotices();
  expect(screen.getByText("Notifications are allowed in this browser.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Allow notifications" })).toBeNull();
  granted.unmount();
  stubNotification("denied");
  const denied = showNotices();
  expect(screen.getByText(/Notifications are blocked in this browser/)).toBeInTheDocument();
  denied.unmount();
  vi.stubGlobal("Notification", undefined);
  showNotices();
  expect(screen.getByText("This browser can't show notifications.")).toBeInTheDocument();
});

// ---- setting a reminder on a to-do --------------------------------------------------------------------------------

const todo = (over: Partial<S["TodoView"]> = {}): S["TodoView"] => ({ action: "ACT-1", text: "Send Oren the estimate", overdue: false, ...over });

test("a to-do's menu sets a reminder from a day and time, and a set one can be changed or removed", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "POST reminders/ACT-1": () => ({ changeset: "CS-6" }), "GET today/todo": () => [] });
  const first = renderApp(<TodoRow item={todo()} project="" showDue />);
  await user.click(screen.getByRole("button", { name: /More actions for/ }));
  expect(screen.queryByRole("menuitem", { name: "Remove reminder" })).toBeNull();
  await user.click(screen.getByRole("menuitem", { name: "Remind me…" }));
  const box = await screen.findByLabelText("Remind me at");
  fireEvent.change(box, { target: { value: "2026-10-21T10:30" } });
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST reminders/ACT-1")?.body).toEqual({ at: "2026-10-21T10:30" }));
  first.unmount();

  renderApp(<TodoRow item={todo({ remind_at: "2026-10-21T10:30:00-04:00" })} project="" showDue />);
  expect(screen.getByText(`Reminder ${dateAndTime("2026-10-21T10:30:00-04:00")}`)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /More actions for/ }));
  expect(screen.getByRole("menuitem", { name: "Change reminder…" })).toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Remove reminder" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST reminders/ACT-1").map((c) => c.body)).toEqual([{ at: "2026-10-21T10:30" }, {}]));
});
