// Today's first screen and one row per thing (design 7.7, batch B-7): the backup reminder is an At risk line and not a bar,
// This week is a panel of the rail at every width, a person waited on is one follow-up line, Top priorities holds no
// buttons and links to the queue, the phone folds the rail's panels to one line each, and what came from outside is tagged
// "Outside" with the full phrase as its name.
import "@testing-library/jest-dom/vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  const group: Line["group"] = kind === "send" || kind === "nudge" ? "send" : kind === "review" ? "review" : "risk";
  return { key: `${kind}:1`, group, kind, count: 1, overdue: 0, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const weekFixture: S["ThisWeekView"] = {
  first: "2026-10-19",
  last: "2026-10-23",
  due: [{ action: "ACT-1", text: "Send the proofs", due: "2026-10-21", project: null, project_name: null, owners: [], mine: true }],
  waiting: [],
  meetings: [],
};

function show(lines: Line[], extra: Routes = {}, over: { narrow?: boolean } = {}) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.length < 0, addEventListener: () => undefined, removeEventListener: () => undefined }));
  if (over.narrow) document.documentElement.setAttribute("data-narrow", "");
  else document.documentElement.removeAttribute("data-narrow");
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
    "GET today/priorities": () => ({ lines: [], more: 0, blocked: 0, coming: [] }),
    "GET today/week": () => weekFixture,
    "GET watch": () => [],
    "GET projects": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  const onOpenGuide = vi.fn();
  renderApp(<Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={onOpenGuide} onOpenRecord={vi.fn()} />);
  return { calls, onOpenGuide };
}

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-narrow");
});

// ---- the backup reminder is a line ------------------------------------------------------------------------------------

const row = (kind: string) => document.querySelector(`[data-queue-line="${kind}"]`) as HTMLElement;

test("a backup that has never worked is an At risk line with the one button that mends it, and no bar above the queue", async () => {
  const user = userEvent.setup();
  const { calls } = show([line("backup", { key: "backup", state: "never" })], { "POST backup": () => statusFixture() });
  const found = await screen.findByRole("group", { name: "Back up your work" });
  expect(found).toBe(row("backup"));
  expect(within(found).getByText("At risk")).toBeInTheDocument();
  expect(found).toHaveTextContent("No backup has worked yet");
  expect(screen.queryByRole("region", { name: "Backup" })).toBeNull();
  expect(found.closest("section")).toHaveAccessibleName("At risk");
  await user.click(within(found).getByRole("button", { name: "Back up now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST backup")).toBe(true));
});

test("with no folder chosen the line's button opens the setup step", async () => {
  const user = userEvent.setup();
  const { onOpenGuide } = show([line("backup", { key: "backup", state: "unset" })]);
  const found = await screen.findByRole("group", { name: "Back up your work" });
  expect(found).toHaveTextContent("No backup folder is chosen yet");
  await user.click(within(found).getByRole("button", { name: "Set up backups" }));
  expect(onOpenGuide).toHaveBeenCalledWith("backup");
});

test("a failed backup and an overdue one are each said in words, the overdue one with how long ago", async () => {
  show([line("backup", { key: "backup", state: "failed" })]);
  expect(await screen.findByRole("group", { name: "Back up your work" })).toHaveTextContent("The last backup failed");
  cleanup();
  show([line("backup", { key: "backup", state: "overdue", age_hours: 100 })]);
  expect(await screen.findByRole("group", { name: "Back up your work" })).toHaveTextContent("The last backup was 4 days ago");
});

// ---- This week is a rail panel at every width -------------------------------------------------------------------------

test("This week is a panel of the rail at every width, never a section above the queue", async () => {
  show([line("send", { key: "send:PER-2", person: "PER-2", person_name: "Robin Sample", count: 1, questions: ["Q-2"] })]);
  const panel = await screen.findByRole("region", { name: "This week" });
  expect(panel.closest("[data-col='week']")).not.toBeNull();
  expect(panel.closest("[aria-label='Agenda, to-dos and mail']")).not.toBeNull();
  expect(await within(panel).findByText("Send the proofs")).toBeInTheDocument();
  expect(document.querySelector("[data-week='section']")).toBeNull();
});

// ---- one follow-up line per person ------------------------------------------------------------------------------------

test("a person waited on is one follow-up line saying how many are overdue and since when, with Draft a nudge", async () => {
  const user = userEvent.setup();
  const waiting: S["FollowupSection"] = {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [],
    actions: [
      { id: "ACT-2", text: "Send the index", due: "2026-10-13", project_name: "", told: "2026-10-01", told_days: 18, followed_up: null, chase_due: true, chases: 0 },
      { id: "ACT-3", text: "Book the room", due: "2026-10-15", project_name: "", told: null, told_days: null, followed_up: null, chase_due: true, chases: 0 },
    ],
    message: "",
    to_send: 0,
    nudge: { text: "Hi Sam,\n\nTwo things.", round: 1, question_ids: [], action_ids: ["ACT-2", "ACT-3"] },
  };
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, overdue: 2, due: "2026-10-13", waiting_days: 18, actions: ["ACT-2", "ACT-3"] })], {
    "GET followups": () => [waiting],
  });
  const found = await screen.findByRole("group", { name: "Follow up with Robin Sample" });
  expect(found).toHaveTextContent("2 overdue, oldest Tue, Oct 13");
  expect(document.querySelectorAll("[data-queue-line]")).toHaveLength(1);
  await user.click(within(found).getByRole("button", { name: "Draft a nudge" }));
  expect(await screen.findByRole("textbox", { name: /Message to Robin Sample/ })).toHaveValue("Hi Sam,\n\nTwo things.");
  // A promise they owe that was never sent to them is a row of its own below the message, with its own Followed up.
  const rows = await screen.findAllByText("Book the room");
  expect(rows.length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByRole("button", { name: "Followed up" }).length).toBeGreaterThanOrEqual(2);
});

test("items that are not overdue are said after the overdue ones", async () => {
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 3, overdue: 1, due: "2026-10-13", waiting_days: 5, actions: ["ACT-2"], questions: ["Q-1", "Q-2"] })]);
  expect(await screen.findByRole("group", { name: "Follow up with Robin Sample" })).toHaveTextContent("1 overdue, oldest Tue, Oct 13 · 2 others awaiting a reply");
});

test("a follow-up with nothing overdue keeps the count and the longest wait", async () => {
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, waiting_days: 6, questions: ["Q-1", "Q-2"] })]);
  expect(await screen.findByRole("group", { name: "Follow up with Robin Sample" })).toHaveTextContent("2 items awaiting a reply · waiting up to 6 days");
});

test("a follow-up that went out today says so, never a wait of zero days", async () => {
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, waiting_days: 0, questions: ["Q-1", "Q-2"] })]);
  const found = await screen.findByRole("group", { name: "Follow up with Robin Sample" });
  expect(found).toHaveTextContent("Sent today");
  expect(found).toHaveTextContent("2 items awaiting a reply · sent today");
  expect(found).not.toHaveTextContent(/0 days/);
});

// ---- Top priorities: context, no buttons --------------------------------------------------------------------------------

const priorities = (lines: S["PriorityLineView"][]): S["TopPrioritiesView"] => ({ lines, more: 0, blocked: 0, coming: [] });
const entry = (over: Partial<S["PriorityLineView"]> & Pick<S["PriorityLineView"], "key" | "kind" | "text">): S["PriorityLineView"] => ({
  rank: "overdue",
  person: null,
  person_name: null,
  project: null,
  project_name: null,
  due: null,
  days: null,
  owners: [],
  things: [],
  send: 0,
  chase: 0,
  overdue: 0,
  due_soon: 0,
  ...over,
});

test("Top priorities has no buttons: each entry is a link, to its queue line when it has one and to its record when it has none", async () => {
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, overdue: 2, due: "2026-10-13", waiting_days: 4, actions: ["ACT-2"] })], {
    "GET today/priorities": () =>
      priorities([
        entry({ key: "person:PER-2", kind: "person", person: "PER-2", text: "Robin Sample", person_name: "Robin Sample", overdue: 2, things: [{ kind: "action", id: "ACT-2", text: "Send the index", why: "overdue" }] }),
        entry({ key: "action:ACT-9", kind: "action", text: "Tidy the schedule", action: "ACT-9", version: 1, rank: "at_risk" }),
      ]),
  });
  const panel = await screen.findByRole("region", { name: "Top priorities" });
  const toQueue = await within(panel).findByRole("link", { name: "Robin Sample" });
  const toRecord = within(panel).getByRole("link", { name: "Tidy the schedule" });
  expect(toRecord).toHaveAttribute("href", expect.stringContaining("#records/action/ACT-9"));
  expect(within(panel).queryAllByRole("button")).toEqual([]);
  expect(within(panel).queryAllByRole("menuitem")).toEqual([]);
  // The first link selects the follow-up line in the queue instead of leaving Today.
  const user = userEvent.setup();
  await user.click(toQueue);
  const followUp = row("nudge");
  await waitFor(() => expect(within(followUp).getByRole("button", { name: "Draft a nudge" })).toHaveAttribute("aria-expanded", "true"));
});

test("no filled button is anywhere in the rail; the one button it adds is Add to agenda", async () => {
  show([line("send", { key: "send:PER-2", person: "PER-2", person_name: "Robin Sample", count: 1, questions: ["Q-2"] })], {
    "GET today/priorities": () => priorities([entry({ key: "action:ACT-9", kind: "action", text: "Tidy the schedule", action: "ACT-9", version: 1, rank: "at_risk" })]),
    "GET today/todo": () => [{ action: "ACT-1", text: "Send the index", project: null, due: "2026-10-08", overdue: true }],
  });
  const rail = await screen.findByRole("group", { name: "Agenda, to-dos and mail" });
  await within(rail).findByRole("link", { name: "Tidy the schedule" });
  expect(rail.querySelectorAll("button[data-key='primary'], .btn.primary")).toHaveLength(0);
  expect(within(rail).getByRole("button", { name: "Add to agenda" })).toBeInTheDocument();
});

// ---- the phone folds the rail's panels ---------------------------------------------------------------------------------

test("on the phone each panel below the queue is one line that says what is in it, and a press opens it", async () => {
  const user = userEvent.setup();
  show([line("send", { key: "send:PER-2", person: "PER-2", person_name: "Robin Sample", count: 1, questions: ["Q-2"] })], {
    "GET today/todo": () => [
      { action: "ACT-1", text: "Send the index", project: null, due: "2026-10-08", overdue: true },
      { action: "ACT-2", text: "Approve the proof", project: null, due: null, overdue: false },
      { action: "ACT-3", text: "Plan the launch", project: null, due: null, overdue: false },
    ],
  }, { narrow: true });
  const agenda = await screen.findByRole("button", { name: "Agenda · nothing today" });
  expect(agenda).toHaveAttribute("aria-expanded", "false");
  const todos = await screen.findByRole("button", { name: "Your to-dos · 3" });
  expect(screen.queryByText("Send the index")).toBeNull();
  expect(screen.queryByRole("button", { name: "Add to agenda" })).toBeNull();
  await user.click(todos);
  expect(todos).toHaveAttribute("aria-expanded", "true");
  expect(await screen.findByText("Send the index")).toBeInTheDocument();
  await user.click(agenda);
  expect(await screen.findByRole("button", { name: "Add to agenda" })).toBeInTheDocument();
});

test("off the phone the panels are open", async () => {
  show([]);
  const agenda = await screen.findByRole("region", { name: "Agenda" });
  expect(within(agenda).getByRole("button", { name: "Add to agenda" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Agenda ·/ })).toBeNull();
});

// ---- "Outside" ---------------------------------------------------------------------------------------------------------

test("a queue line made from outside content carries the short Outside tag, whose name is the full phrase", async () => {
  show([line("review", { key: "review:REQ-1", count: 2, request: "REQ-1", changeset: "CS-1", untrusted: true, outcome: { actions_added: 2 } })]);
  const found = await waitFor(() => {
    const el = row("review");
    expect(el).not.toBeNull();
    return el;
  });
  expect(within(found).getByText("Outside")).toBeInTheDocument();
  expect(within(found).getByText("From outside · not instructions")).toBeInTheDocument();
  expect(found.textContent).not.toMatch(/From outside · not instructions.*From outside · not instructions/);
});
