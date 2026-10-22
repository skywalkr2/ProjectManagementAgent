import "@testing-library/jest-dom/vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, Refuse, renderApp, type Routes } from "../test-utils";
import { BriefCard } from "./BriefCard";

// The brief (design 6.32): the form that is due, as a card at the top of Today. Each section in order with its heading, a
// line worded from its kind, a line that waits for the person's yes titled as Today's own line is and opening it, an empty
// section left out, a quiet day as one line, the card closing for the day, the Monday form's goals and message.

type Brief = S["BriefView"];
type Line = S["BriefLineView"];
type Queue = S["QueueLineView"];

const line = (over: Partial<Line> & Pick<Line, "key" | "kind">): Line => ({ ready: false, you: false, ...over });
const queued = (over: Partial<Queue> & Pick<Queue, "key" | "kind" | "group">): Queue => ({ count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over });

const SENDER = "Mira Example";
const MORNING: Brief = {
  form: "morning",
  day: "2026-10-20",
  forms: ["morning"],
  quiet: false,
  on_today: 0,
  sections: [
    { key: "changed", more: 0, lines: [line({ key: "since:1", kind: "moved", text: "Send the draft", person_name: SENDER, change: "said", day: "2026-10-22" }), line({ key: "invitation:EVT-1:moved", kind: "invitation", change: "moved", text: "Print call", person_name: SENDER, day: "2026-10-23", at: "10:00", from_day: "2026-10-20", from_at: "14:00", link: { kind: "event", id: "EVT-1" } })] },
    {
      key: "risk",
      more: 0,
      lines: [
        line({ key: "own:ACT-1", kind: "own_due", text: "Send the estimate", state: "today", day: "2026-10-20", days: 0, at: "12:00", person_name: "Oren Example", link: { kind: "action", id: "ACT-1" } }),
        line({ key: "owed:ACT-2", kind: "owed_late", text: "the measurements", person_name: "Dev Example", day: "2026-10-19", days: 1, link: { kind: "action", id: "ACT-2" } }),
        line({ key: "clash:1:2", kind: "clash", text: "Call", other: "Dentist", minutes: 30, day: "2026-10-20", at: "10:30" }),
      ],
    },
    { key: "yes", more: 2, lines: [line({ key: "yes:nudge:PER-2", kind: "yes", change: "nudge", person: "PER-2", person_name: "Dev Example", queue: "nudge:PER-2", ready: true })] },
  ],
};
const NUDGE = queued({ key: "nudge:PER-2", group: "send", kind: "nudge", person: "PER-2", person_name: "Dev Example" });
const QUIET: Brief = { form: "morning", day: "2026-10-20", forms: ["morning"], quiet: true, on_today: 0, sections: [] };
const EVENING: Brief = {
  form: "evening",
  day: "2026-10-20",
  forms: ["evening"],
  quiet: false,
  on_today: 0,
  sections: [
    { key: "done", more: 0, lines: [line({ key: "done:ACT-1", kind: "done", text: "the proposal", you: true }), line({ key: "done:ACT-2", kind: "done", text: "two illustrations", person_name: "Dev Example", person: "PER-2" })] },
    { key: "moved", more: 0, lines: [line({ key: "moved:ACT-3", kind: "moved_ahead", text: "Edit the website", day: "2026-10-21" }), line({ key: "carried:ACT-4", kind: "carried", text: "Print the estimate", day: "2026-10-20" })] },
    { key: "waiting", more: 0, lines: [line({ key: "waiting:ACT-5", kind: "waiting", text: "the measurements", person_name: "Dev Example", day: "2026-10-22" })] },
  ],
};
const GOALS_PROPOSED: S["BriefGoalsView"] = { first: "2026-10-19", last: "2026-10-23", confirmed: false, goals: [], proposed: ["Ship the proof", "Close the print order", "Plan the launch"], fewest: 3, most: 5 };
const MONDAY: Brief = {
  form: "monday",
  day: "2026-10-19",
  forms: ["monday", "morning"],
  quiet: false,
  on_today: 2,
  sections: [
    { key: "yours", more: 0, lines: [line({ key: "week:ACT-1", kind: "week_promise", text: "Draft the proposal", state: "due", day: "2026-10-21", you: true, person_name: "Mira Example", link: { kind: "action", id: "ACT-1" } })] },
    { key: "owed", more: 0, lines: [line({ key: "week:ACT-2", kind: "week_promise", text: "the measurements", state: "overdue", day: "2026-10-18", person_name: "Dev Example" })] },
    { key: "send", more: 0, lines: [line({ key: "week:Q-1", kind: "send_question", text: "Which cover?", person_name: "Mira Example" })] },
  ],
  goals: GOALS_PROPOSED,
  message: { state: "none", to: [{ person: "PER-9", name: "Lena Example" }] },
};

function show(brief: Brief, extra: Routes = {}, over: { unnamed?: boolean } = {}) {
  const calls = fakeApi({ "GET brief": () => brief, "GET today/queue": () => [NUDGE], ...extra });
  const onOpenRecord = vi.fn();
  renderApp(<BriefCard workspace="ws" onOpenRecord={onOpenRecord} />, {}, over);
  return { calls, onOpenRecord };
}

beforeEach(() => window.localStorage.clear());
afterEach(() => cleanup());

const sectionsOf = () => Array.from(document.querySelectorAll<HTMLElement>("[data-section]"));
const headings = () => sectionsOf().map((s) => within(s).getByRole("heading", { level: 3 }).textContent);

test("the morning brief has its sections in order with their headings, and a section with nothing is left out", async () => {
  show({ ...MORNING, sections: MORNING.sections.filter((s) => s.key !== "changed") });
  expect(await screen.findByRole("heading", { level: 2, name: "Morning brief" })).toBeInTheDocument();
  expect(headings()).toEqual(["At risk today", "Needs your yes"]);
  expect(screen.queryByText("Changed overnight")).toBeNull();
});

test("every kind of line is worded from the sheet: one fact each, the day and the time said, no status or progress", async () => {
  show(MORNING);
  await screen.findByRole("heading", { level: 2, name: "Morning brief" });
  expect(headings()).toEqual(["Changed overnight", "At risk today", "Needs your yes"]);
  expect(screen.getByText(`${SENDER} moved Send the draft to Thu, Oct 22`)).toBeInTheDocument();
  expect(screen.getByText(/Print call moved from Tue, Oct 20 2:00 PM to Fri, Oct 23 at 10:00 AM/)).toBeInTheDocument();
  expect(screen.getByText("Send the estimate is due today at 12:00 PM")).toBeInTheDocument();
  expect(screen.getByText("for Oren Example")).toBeInTheDocument();
  expect(screen.getByText("Dev Example: the measurements is a day late")).toBeInTheDocument();
  expect(screen.getByText("Call and Dentist overlap by 30 minutes on Tue, Oct 20 from 10:30 AM")).toBeInTheDocument();
  expect(screen.queryByText(/done|progress|so far/i)).toBeNull();
});

test("a line that waits for the person's yes is titled as Today's own line and says a draft is ready, and a section says how many more", async () => {
  show(MORNING);
  const yes = (await screen.findByText("Follow up with Dev Example")).closest("li");
  expect(yes).not.toBeNull();
  expect(within(yes as HTMLElement).getByText("draft ready")).toBeInTheDocument();
  expect(screen.getByText("And 2 more.")).toBeInTheDocument();
});

test("Open on a yes line opens Today's own line; on another it opens its record", async () => {
  const user = userEvent.setup();
  const revealed = vi.fn((event: Event) => event.preventDefault());
  window.addEventListener("reveal-row", revealed);
  const { onOpenRecord } = show(MORNING);
  const yes = (await screen.findByText("Follow up with Dev Example")).closest("li") as HTMLElement;
  await user.click(within(yes).getByRole("button", { name: "Open" }));
  expect((revealed.mock.calls[0][0] as CustomEvent).detail).toEqual({ type: "line", id: "nudge:PER-2" });
  expect(onOpenRecord).not.toHaveBeenCalled();
  const risk = screen.getByText("Send the estimate is due today at 12:00 PM").closest("li") as HTMLElement;
  await user.click(within(risk).getByRole("button", { name: "Open" }));
  expect(onOpenRecord).toHaveBeenCalledWith("action", "ACT-1");
  window.removeEventListener("reveal-row", revealed);
});

test("a quiet day is one line and no section", async () => {
  show(QUIET);
  expect(await screen.findByText("Nothing needs you this morning.")).toBeInTheDocument();
  expect(sectionsOf()).toHaveLength(0);
});

test("nothing shows before the brief is due, or when it can't be read", async () => {
  show({ ...QUIET, form: null, forms: [] });
  await waitFor(() => expect(document.querySelector("[data-brief]")).toBeNull());
  cleanup();
  fakeApi({ "GET brief": () => new Refuse(500, "no"), "GET today/queue": () => [] });
  renderApp(<BriefCard workspace="ws" onOpenRecord={() => undefined} />);
  await waitFor(() => expect(document.querySelector("[data-brief]")).toBeNull());
});

test("the evening wrap-up credits the work to whoever did it, and its quiet day is its own line", async () => {
  show(EVENING);
  expect(await screen.findByRole("heading", { level: 2, name: "Evening wrap-up" })).toBeInTheDocument();
  expect(headings()).toEqual(["Done today", "Moved to tomorrow", "Still waiting on others"]);
  expect(screen.getByText("You finished the proposal")).toBeInTheDocument();
  expect(screen.getByText("Dev Example finished two illustrations")).toBeInTheDocument();
  expect(screen.getByText("Edit the website, now due Wed, Oct 21")).toBeInTheDocument();
  expect(screen.getByText("Print the estimate is still open and was due today")).toBeInTheDocument();
  expect(screen.getByText("Dev Example still owes you the measurements, due Thu, Oct 22")).toBeInTheDocument();
  cleanup();
  show({ ...EVENING, quiet: true, sections: [] });
  expect(await screen.findByText("Nothing carries over to tomorrow.")).toBeInTheDocument();
});

test("closing the card for the day hides it, is remembered for that day only, and records nothing", async () => {
  const user = userEvent.setup();
  const { calls } = show(MORNING);
  await user.click(await screen.findByRole("button", { name: "Close for today" }));
  expect(document.querySelector("[data-brief]")).toBeNull();
  expect(window.localStorage.getItem("brief-closed:ws:morning:2026-10-20")).toBe("1");
  expect(calls.filter((c) => c.route.startsWith("POST") || c.route.startsWith("PUT"))).toEqual([]);
  cleanup();
  show(MORNING);
  await waitFor(() => expect(document.querySelector("[data-brief]")).toBeNull());
  cleanup();
  show({ ...MORNING, day: "2026-10-21" });
  expect(await screen.findByRole("heading", { level: 2, name: "Morning brief" })).toBeInTheDocument();
  cleanup();
  show({ ...EVENING });
  expect(await screen.findByRole("heading", { level: 2, name: "Evening wrap-up" })).toBeInTheDocument();
});

test("another form that is due can be shown from the card", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET brief": () => MONDAY, "GET brief?form=morning": () => ({ ...MORNING, forms: ["monday", "morning"] }), "GET today/queue": () => [NUDGE] });
  renderApp(<BriefCard workspace="ws" onOpenRecord={() => undefined} />);
  expect(await screen.findByRole("heading", { level: 2, name: "Monday briefing" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Show the morning brief" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Morning brief" })).toBeInTheDocument();
  expect(calls.some((c) => c.route === "GET brief?form=morning")).toBe(true);
  expect(screen.getByRole("button", { name: "Show the Monday briefing" })).toBeInTheDocument();
});

test("the Monday briefing lists the week by who owns it, says how much Today already holds and repeats none of it", async () => {
  show(MONDAY);
  expect(await screen.findByRole("heading", { level: 2, name: "Monday briefing" })).toBeInTheDocument();
  expect(headings()).toEqual(["Your promises this week", "Promised to you", "Questions to send"]);
  expect(screen.getByText("Draft the proposal, due Wed, Oct 21")).toBeInTheDocument();
  expect(screen.getByText("to Mira Example")).toBeInTheDocument();
  expect(screen.getByText("Dev Example: the measurements, was due Sun, Oct 18")).toBeInTheDocument();
  expect(screen.getByText("Send Mira Example: Which cover?")).toBeInTheDocument();
  expect(screen.getByText("2 more things are already on Today.")).toBeInTheDocument();
});

test("the proposed goals are confirmed as they are in one press, and Undo sends back what they replaced", async () => {
  const user = userEvent.setup();
  const calls = show(MONDAY, { "PUT brief/goals": () => ({ previous: [] }) }).calls;
  const block = (await screen.findByRole("heading", { name: "Goals for the week" })).closest("[data-block]") as HTMLElement;
  expect(within(block).getAllByRole("listitem").map((x) => x.textContent)).toEqual(GOALS_PROPOSED.proposed);
  await user.click(within(block).getByRole("button", { name: "Confirm these goals" }));
  await waitFor(() => expect(calls.find((c) => c.route === "PUT brief/goals")?.body).toEqual({ goals: GOALS_PROPOSED.proposed }));
  expect(await screen.findByText("The goals for the week are kept.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "PUT brief/goals")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "PUT brief/goals")[1].body).toEqual({ goals: [] });
});

test("changing the goals puts the cursor in the first field, drops and adds rows within the most, and keeps what was typed", async () => {
  const user = userEvent.setup();
  const calls = show(MONDAY, { "PUT brief/goals": () => ({ previous: [] }) }).calls;
  await user.click(await screen.findByRole("button", { name: "Change goals" }));
  const first = screen.getByRole("textbox", { name: "Goal 1" });
  await waitFor(() => expect(first).toHaveFocus());
  await user.clear(first);
  await user.type(first, "Ship the proofs");
  await user.click(screen.getByRole("button", { name: "Drop goal 3" }));
  await user.click(screen.getByRole("button", { name: "Add a goal" }));
  await user.type(screen.getByRole("textbox", { name: "Goal 3" }), "Call the printer");
  await user.click(screen.getByRole("button", { name: "Confirm goals" }));
  await waitFor(() => expect(calls.find((c) => c.route === "PUT brief/goals")?.body).toEqual({ goals: ["Ship the proofs", "Close the print order", "Call the printer"] }));
});

test("fewer goals than the fewest are not sent, and the reason is said", async () => {
  const user = userEvent.setup();
  const calls = show(MONDAY).calls;
  await user.click(await screen.findByRole("button", { name: "Change goals" }));
  await user.click(screen.getByRole("button", { name: "Drop goal 3" }));
  await user.click(screen.getByRole("button", { name: "Confirm goals" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Give at least 3 goals, or cancel.");
  expect(calls.some((c) => c.route === "PUT brief/goals")).toBe(false);
});

test("a week with no goals to propose offers to set them, and confirmed goals say they are kept", async () => {
  const user = userEvent.setup();
  show({ ...MONDAY, goals: { ...GOALS_PROPOSED, proposed: [] } });
  const block = (await screen.findByRole("heading", { name: "Goals for the week" })).closest("[data-block]") as HTMLElement;
  expect(within(block).queryByRole("button", { name: "Confirm these goals" })).toBeNull();
  await user.click(within(block).getByRole("button", { name: "Set goals" }));
  expect(screen.getByRole("textbox", { name: "Goal 1" })).toHaveValue("");
  cleanup();
  show({ ...MONDAY, goals: { ...GOALS_PROPOSED, confirmed: true, goals: ["One", "Two", "Three"], proposed: [] } });
  expect(await screen.findByText("Kept for the week.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm these goals" })).toBeNull();
});

test("a morning brief shows no goals form, and the Monday message is only there when the person reports to someone", async () => {
  show({ ...MONDAY, message: null });
  await screen.findByRole("heading", { level: 2, name: "Monday briefing" });
  expect(screen.queryByRole("heading", { name: /^Message to/ })).toBeNull();
  cleanup();
  show(MORNING);
  await screen.findByRole("heading", { level: 2, name: "Morning brief" });
  expect(screen.queryByRole("heading", { name: "Goals for the week" })).toBeNull();
});

test("asking for the message says who it is for, queues it and says a draft will wait", async () => {
  const user = userEvent.setup();
  const calls = show(MONDAY, { "POST brief/message": () => ({ request: "REQ-1" }) }).calls;
  expect(await screen.findByRole("heading", { name: "Message to Lena Example" })).toBeInTheDocument();
  expect(screen.getByText("A draft for you to read, change and send yourself. Nothing is sent from here.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Draft the message" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST brief/message")?.body).toEqual({}));
  expect(await screen.findByText("Helper will draft it. A draft will wait for you to read.")).toBeInTheDocument();
});

test("the unnamed assistant is your assistant", async () => {
  show({ ...MONDAY, message: { state: "working", to: [{ person: "PER-9", name: "Lena Example" }] } }, {}, { unnamed: true });
  expect(await screen.findByText("Your assistant is drafting it")).toBeInTheDocument();
});

test("a message waiting for the go says so, with the estimate when there is one", async () => {
  show({ ...MONDAY, message: { state: "needs_go", to: [{ person: "PER-9", name: "Lena Example" }], estimate_usd: 0.31 } });
  expect(await screen.findByText("Waiting for your go ($0.31)")).toBeInTheDocument();
});

test("a draft is shown as a draft and Copy puts it on the clipboard and makes it the persons own", async () => {
  const user = userEvent.setup();
  const text = "Hello,\n\nThe proof shipped.\n";
  const calls = show(
    { ...MONDAY, message: { state: "draft", to: [{ person: "PER-9", name: "Lena Example" }], text } },
    { "POST brief/message/copied": () => ({ ok: "copied" }) },
  ).calls;
  expect(await screen.findByText("Draft, not yet reviewed")).toBeInTheDocument();
  expect(document.querySelector("[data-message='draft']")?.textContent).toBe(text);
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST brief/message/copied")).toBe(true));
  expect(await navigator.clipboard.readText()).toBe(text);
  expect(await screen.findByText("Copied. Paste it into your message.")).toBeInTheDocument();
});

test("if the browser blocks copying, the draft is not made the persons and they are told", async () => {
  const user = userEvent.setup();
  const calls = show({ ...MONDAY, message: { state: "draft", to: [{ person: "PER-9", name: "Lena Example" }], text: "Hello." } }).calls;
  await screen.findByText("Draft, not yet reviewed");
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  expect(await screen.findByText(/wouldn't copy it/)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST brief/message/copied")).toBe(false);
});

test("a message already copied can be copied again without approving anything", async () => {
  const user = userEvent.setup();
  const calls = show({ ...MONDAY, message: { state: "kept", to: [{ person: "PER-9", name: "Lena Example" }], text: "Hello." } }).calls;
  expect(await screen.findByText("Your message, as copied")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  expect(await navigator.clipboard.readText()).toBe("Hello.");
  expect(calls.some((c) => c.route === "POST brief/message/copied")).toBe(false);
});

const MORE: Brief = {
  ...MORNING,
  sections: [
    {
      key: "risk",
      more: 0,
      lines: [
        line({ key: "capacity", kind: "capacity", minutes: 30, needed_minutes: 180, count: 2, queue: "capacity" }),
        line({ key: "clash:a:b:2026-10-22", kind: "clash", state: "travel", text: "Site visit", other: "Supplier call", minutes: 20, day: "2026-10-22", at: "11:10" }),
      ],
    },
    {
      key: "yes",
      more: 0,
      lines: [
        line({ key: "remind:ACT-7", kind: "yes", change: "reminder_offer", text: "Decide on the renewal", day: "2026-10-29", at: "09:00", when: "2026-10-29T09:00:00-05:00", link: { kind: "action", id: "ACT-7" } }),
        line({ key: "digest:stale", kind: "digest", change: "stale", count: 3, queue: "stale" }),
      ],
    },
  ],
};

test("the capacity line says what the to-dos need and what the calendar has, and a clash a few days on says its day and the travel", async () => {
  show(MORE);
  await screen.findByRole("heading", { level: 2, name: "Morning brief" });
  expect(screen.getByText("Your to-dos need about 3 hours; your calendar has about 30 minutes free")).toBeInTheDocument();
  expect(screen.getByText("Site visit and Supplier call leave 20 minutes too little to travel between them on Thu, Oct 22 from 11:10 AM")).toBeInTheDocument();
});

test("a reminder offer says when and Remind me sets it at that moment, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show(MORE, { "POST reminders/ACT-7": () => ({ changeset: "CS-5" }), "POST changesets/CS-5/undo": () => ({ restored: [0], skipped: [] }) });
  expect(await screen.findByText("Add a reminder on Thu, Oct 29 at 9:00 AM for 'Decide on the renewal'")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remind me" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST reminders/ACT-7")?.body).toEqual({ at: "2026-10-29T09:00:00-05:00" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-5/undo")).toBe(true));
});

test("a suggestion that waited for the brief is worded as the brief's own line and opens where it is dealt with", async () => {
  const user = userEvent.setup();
  const onOpenView = vi.fn();
  fakeApi({ "GET brief": () => MORE, "GET today/queue": () => [] });
  renderApp(<BriefCard workspace="ws" onOpenRecord={vi.fn()} onOpenView={onOpenView} />);
  expect(await screen.findByText("Keep or drop 3 to-dos nobody has touched lately")).toBeInTheDocument();
  const item = screen.getByText("Keep or drop 3 to-dos nobody has touched lately").closest("li")!;
  await user.click(within(item).getByRole("button", { name: "Open" }));
  expect(onOpenView).toHaveBeenCalledWith("work/open");
});
