import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import type { SettingsSection } from "../lib/views";
import { useShortcuts } from "../lib/keys";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { sweep } from "../test-sweep";
import { besidePane, fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";
import { Addons } from "./Addons";
import { Files } from "./Files";
import { FollowUps } from "./FollowUps";
import { Handover } from "./Handover";
import { Quality } from "./Quality";
import { RecordPage } from "./RecordPage";
import { Knowledge } from "./Knowledge";
import { Settings } from "./Settings";
import { SinceYesterday } from "./SinceYesterday";
import { Sources } from "./Sources";
import { Stages } from "./Stages";
import { WhatChanged } from "./WhatChanged";

// The view sweep: the main views other than the records, each drawn from a payload shaped the way the server sends it
// (ids on every record, dates as stored, stored choice words, references by id with their names, a field left out so a
// line has a gap), then checked by the same sweep as the record pages. A new view that leaks an id, a stored date, a dot
// beside nothing or a stored word fails here.

/** Midday on a made-up Sunday, on this computer's clock; only the date is faked so waiting still works. */
const NOW = new Date(2026, 9, 11, 12, 0);
const TODAY = "2026-10-11";
const TOMORROW = "2026-10-12";

/** An ISO time with this computer's offset, so the clock the page shows is the clock written here. */
function at(date: string, hour: number, minute = 0): string {
  const [y, m, d] = date.split("-").map(Number);
  const offset = -new Date(y, m - 1, d, hour, minute).getTimezoneOffset();
  const sign = offset < 0 ? "-" : "+";
  const pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
  return `${date}T${pad(hour)}:${pad(minute)}:00${sign}${pad(Math.trunc(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  forgetLine();
});

// ---- Today ---------------------------------------------------------------------------------------------------------

type Line = S["QueueLineView"];

function line(kind: Line["kind"], group: Line["group"], over: Partial<Line> = {}): Line {
  return { key: `${kind}:1`, group, kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

function Keys() {
  useShortcuts({ next: "j", previous: "k", primary: "a" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined });
  return null;
}

function changeItem(id: string): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: at(TODAY, 8),
    note: null,
    source: null,
    source_title: "Email from Sam Example",
    changeset: {
      id: "CS-1",
      summary: "Two to-dos.",
      status: "applied",
      reviewed: false,
      trust: "untrusted",
      ops: [{ index: 0, op: "action.add", status: "applied", reason: null, group: "op0", title: "Send two spine options", meta: { owners: [], due: TOMORROW }, evidence: null, record: { kind: "action", id: "ACT-7" }, ask: null }],
    },
  } as S["ChangeItem"];
}

const decisionQuestion: S["FollowupQuestion"] = { id: "Q-1", title: "Matte or soft-touch?", text: "", links: [], kind: "decision", status: "open", sent: null, waiting_days: null, chase_due: false, chases: 0, about: null, options: [] };
const sectionRobin: S["FollowupSection"] = {
  person: "PER-2",
  name: "Robin Sample",
  is_pm: false,
  questions: [{ ...decisionQuestion, id: "Q-2", title: "Is the index final?", kind: "question", status: "sent", sent: "2026-10-04", waiting_days: 7 }],
  actions: [{ id: "ACT-2", text: "Send the index", due: "2026-10-09", project_name: "Spring book", told: "2026-10-01", told_days: 10, followed_up: null, chase_due: true, chases: 1 }],
  message: "Hi Robin,\n\nIs the index final?",
  to_send: 2,
};
const sectionPm: S["FollowupSection"] = { person: "PER-1", name: "Pat Example", is_pm: true, questions: [decisionQuestion], actions: [], message: "", to_send: 0 };

const decision = line("decision", "decide", { key: "question:Q-1", text: "Matte or soft-touch?", question: "Q-1", project: "PRJ-1", project_name: "Spring book" });
const review = line("review", "review", { key: "review:REQ-1", count: 2, request: "REQ-1", changeset: "CS-1", title: { kind: "email", person_name: "Sam Example", topic: "proof copies" }, outcome: { actions_added: 2, held: 1 } });
const send = line("send", "send", { key: "send:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, questions: ["Q-2"], actions: ["ACT-2"] });
const nudge = line("nudge", "send", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, overdue: 1, due: "2026-10-09", waiting_days: 7, actions: ["ACT-2"], questions: ["Q-2"] });
const overdue = line("overdue", "risk", { key: "overdue", count: 1, actions: ["ACT-1"], due: "2026-10-08", waiting_days: 3, subject: "Approve the proof" });
const promise = line("promise", "risk", { key: "promise:ACT-1", person: "PER-2", person_name: "Robin Sample", text: "Send the floor plan", subject: "Send the floor plan", due: "2026-10-13", waiting_days: 3, actions: ["ACT-1"] });
const backup = line("backup", "risk", { key: "backup", state: "overdue", age_hours: 100 });
const paused = line("paused", "risk", { key: "paused:main", account: "main", count: 1, until: at(TOMORROW, 15, 30) });
const reminder = line("reminder", "risk", { key: "reminder:ACT-1", text: "Call the printer", late: false, at: at(TODAY, 15) });
const escalate = line("escalate", "send", { key: "escalate:PER-2:Q-2", person: "PER-2", person_name: "Robin Sample", text: "Is the index final?", count: 2, waiting_days: 5, questions: ["Q-2"] });
const stale = line("stale", "review", { key: "stale", count: 2, actions: ["ACT-1", "ACT-2"], waiting_days: 40 });
const moved = line("moved", "review", {
  key: "moved:REQ-9",
  count: 2,
  text: "Print sync",
  due: "2026-10-22",
  changeset: "CS-9",
  questions: ["Q-1", "Q-2"],
  after_move: { kind: "event", record: "EVT-1", title: "Print sync", to: "2026-10-22", earlier: true, by: "assistant", replaced: false, request: "REQ-9", changeset: "CS-9", others: ["Casey Moor"] },
});
const since = line("since_yesterday", "risk", { key: "since_yesterday", count: 3, outcome: { closed: 2, moved: 1 } });
const unfiled = line("unfiled", "review", { key: "unfiled", count: 4 });
const todayLines = [decision, review, send, nudge, escalate, overdue, promise, stale, moved, since, unfiled, backup, paused, reminder];

function railRoutes(): Routes {
  const event = (extra: Partial<S["AgendaItemView"]> & Pick<S["AgendaItemView"], "title">): S["AgendaItemView"] => ({ snapshot: `snap-${extra.title}`, source: "cal-1", start: at(TODAY, 15), all_day: false, cancelled: false, own: false, open_items: 0, days: [TODAY], ...extra });
  return {
    "GET today/agenda": () => [event({ title: "Standup", start: at(TODAY, 9), end: at(TODAY, 9, 30), where: "Room A" }), event({ title: "Quarterly planning", all_day: true, start: TODAY, days: [TODAY, TOMORROW] }), event({ title: "Workshop", start: at(TOMORROW, 13), days: [TOMORROW], open_items: 2 })],
    "GET today/todo": () => [
      { action: "ACT-1", text: "Send the index", project: "PRJ-1", due: "2026-10-08", overdue: true },
      { action: "ACT-4", text: "Tidy the notes", project: null, due: null, overdue: false },
    ],
    "GET today/arrived": () => ({
      items: [
        { snapshot: "s1", source: "mail-1", title: "Proof is ready", sender: "Robin Sample", unread: true, received: at(TODAY, 9, 14) },
        { snapshot: "s2", source: "mail-1", title: "Invoice attached", received: at("2026-10-09", 16, 40) },
      ],
      left_out: 3,
      set_aside: 2,
    }),
    "GET today/priorities": () => ({
      lines: [
        {
          key: "action:ACT-1",
          rank: "overdue",
          kind: "action",
          text: "Send the proofs",
          person: "PER-1",
          person_name: "Pat Example",
          project: "PRJ-1",
          project_name: "Spring book",
          due: "2026-10-08",
          days: 3,
          owners: [{ person: "PER-1", name: "Pat Example" }],
          things: [],
          holds_up: 0,
          send: 0,
          chase: 0,
          overdue: 0,
          due_soon: 0,
          action: "ACT-1",
          version: 4,
        },
      ],
      more: 0,
      blocked: 0,
      coming: [],
    }),
    "GET today/week": () => ({
      first: "2026-10-05",
      last: "2026-10-09",
      due: [{ action: "ACT-3", text: "Plan the launch", due: "2026-10-09", project: "PRJ-1", project_name: "Spring book", mine: true, owners: [{ person: "PER-1", name: "Pat Example" }] }],
      waiting: [{ person: "PER-2", person_name: "Robin Sample", count: 2, due: "2026-10-09" }],
      meetings: [],
    }),
  };
}

async function showToday(lines: Line[], wide: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: wide && /min-width: 1680px/.test(query), addEventListener: () => undefined, removeEventListener: () => undefined }));
  fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [changeItem("REQ-1")],
    "GET followups": () => [sectionPm, sectionRobin],
    "GET plugin-today": () => [{ plugin: "demo", id: "L-1", text: "Look at the proof", about: null, action: null, action_is: null, why: "The printer is waiting", until: at(TOMORROW, 9) }],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET watch": () => [],
    "GET projects": () => [{ id: "PRJ-1", name: "Spring book", group: null, owner: null, owner_name: null }],
    "GET status": () => statusFixture({}, { assistant: { last_run_at: at(TODAY, 8) } }),
    "GET runtime-config": () => ({ instance: null }),
    ...railRoutes(),
  });
  const view = renderApp(
    <RestartProvider hellos={1}>
      <Keys />
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  await screen.findByText("Proof is ready");
  return view;
}

test("Today, with the inspector open on each line and with its rail, says names, dates and words", async () => {
  const view = await showToday(todayLines, true);
  const pane = await screen.findByRole("complementary", { name: "Details" });
  // The inspector follows the line that has the cursor: it is swept on each line in turn.
  const user = userEvent.setup();
  const rows = Array.from(view.container.querySelectorAll<HTMLElement>("[data-queue-line]"));
  expect(rows.length).toBeGreaterThan(5);
  for (const row of rows) {
    await user.click(row);
    await waitFor(() => expect(within(pane).queryByText(/Loading/)).toBeNull());
    sweep(view.container);
  }
});

test("Today below the inspector's width, with each line's items open under it, says names, dates and words", async () => {
  const view = await showToday(todayLines, false);
  const user = userEvent.setup();
  sweep(view.container);
  for (const row of Array.from(view.container.querySelectorAll<HTMLElement>("[data-queue-line]"))) {
    await user.click(row);
    sweep(view.container);
  }
});

// ---- What changed --------------------------------------------------------------------------------------------------

function op(index: number, kind: string, status: S["OpView"]["status"], title: string, meta: Partial<S["OpMeta"]> = {}, extra: Partial<S["OpView"]> = {}): S["OpView"] {
  return { index, op: kind, status, reason: null, group: `op${index}`, title, meta: { owners: [], ...meta }, evidence: null, record: null, ask: null, ...extra };
}

function change(id: string, over: Partial<S["ChangeItem"]> = {}, ops: S["OpView"][] = []): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: at("2026-10-09", 14),
    note: null,
    source: "SRC-1",
    source_title: "Email from the printer",
    changeset: { id: `CS-${id}`, summary: "A few changes.", status: "applied", reviewed: false, trust: "untrusted", ops },
    ...over,
  };
}

test("What changed, with its first change chosen and the others one line, says names, dates and words", async () => {
  besidePane();
  const ops = [
    op(0, "action.add", "applied", "Send two spine options", { owners: ["Robin Sample"], due: "2026-10-16", to_send: true, project: "Spring book" }, { record: { kind: "action", id: "ACT-7" }, evidence: { quote: "please send two spine options" } }),
    op(1, "action.add", "applied", "Check the cover", { owners: [], due: null }, { record: { kind: "action", id: "ACT-8" } }),
    op(2, "question.add", "applied", "Which paper stock?", { to: "Robin Sample" }, { record: { kind: "question", id: "Q-4" } }),
    op(3, "fact", "applied", "Proof copies ship Nov 5", {}, { record: { kind: "fact", id: "FACT-1" } }),
    op(4, "note", "applied", "Printer prefers PDF/X files", { project: null }, { record: { kind: "note", id: "NOTE-1" } }),
    op(5, "record.set", "applied", "Robin Sample", { field: "due", value: "2026-10-19" }, { record: { kind: "person", id: "PER-2" } }),
    op(6, "project.add", "applied", "Autumn book", { name: "Autumn book", note: "The link could not be read." }),
    op(7, "project.role", "applied", "Spring book", { role: "run" }),
    op(8, "person.stance", "applied", "Robin Sample", { stance: "report_to" }),
    op(9, "action.add", "held", "Send the proofs", { owners: ["Robin"], due: "2026-10-20", action_status: "held" }, {
      reason: "Waiting for you to say who this is",
      ask: { id: "Q-7", status: "open", about: "held-op", name: "Robin", options: [{ id: "PER-2", name: "Robin Sample" }, { id: "PER-5", name: "Robin Other" }] },
    }),
    op(10, "action.close", "held", "Book the printer", {}, {
      reason: "The message says it is done",
      held: { ask: "close", item: "ACT-3", reporter: "Robin Sample", told_on: "2026-10-12", delivered: "2026-10-12", due_words: "Mon, Oct 12", to_name: "Pat Example" },
    }),
  ];
  const first = change("REQ-1", { estimate_usd: 0.02, spent_usd: 0.01, follows: "REQ-0", follows_summary: "Two spine options", title: { kind: "email", person_name: "Robin Sample", topic: "spine options" } }, ops);
  first.changeset!.second_opinion = "other_account";
  first.changeset!.made = [{ id: "DR-1", kind: "draft", label: "Reply to Robin Sample", record: { kind: "draft", id: "DR-1" } }];
  first.changeset!.applied = [{ id: "L-1", kind: "lesson", status: "active", text: "Spine questions go to the designer.", version: 1, applies_to: { scope: "workspace" } }];
  const items: S["ChangeItem"][] = [
    first,
    change("REQ-2", { state: "done", changeset: { ...first.changeset!, id: "CS-2", reviewed: true, ops: [ops[0]] } }),
    change("REQ-3", { state: "needs_you", refused: true, created_at: at("2026-10-10", 9), cause: { kind: "no_person" }, changeset: null, note: "Write an email to the printer" }),
    change("REQ-4", { state: "failed", created_at: at("2026-10-10", 10), changeset: null, source: null, source_title: null, note: "Plan the launch" }),
    change("REQ-5", { state: "queued", waiting: at(TOMORROW, 8), created_at: at(TODAY, 8), changeset: null, title: { kind: "calendar", subject: "Print sync", topic: "print sync" } }),
    change("REQ-6", { state: "running", created_at: at(TODAY, 9), changeset: null, title: { kind: "pasted", topic: "meeting notes" } }),
  ];
  fakeApi({
    "GET changes": () => items,
    "GET sources/SRC-1": () => ({ id: "SRC-1", title: "Email from the printer", kind: "pasted", trust: "untrusted", received_at: at("2026-10-09", 14), url: null, text: "Please send two spine options.", limit: null }),
    "GET people": () => [],
    "GET projects": () => [],
    "GET status": () => statusFixture(),
  });
  const view = renderApp(<WhatChanged />);
  await screen.findByText("Send two spine options");
  await waitFor(() => expect(view.container.querySelectorAll("[data-row]").length).toBeGreaterThan(5));
  sweep(view.container);
  // Each filter shows more rows (the done and stopped ones), swept as well.
  const user = userEvent.setup();
  for (const name of ["Done", "All"]) {
    await user.click(screen.getByRole("button", { name }));
    sweep(view.container);
  }
  expect(screen.getByText("Plan the launch")).toBeInTheDocument();
});

// ---- Follow-ups ----------------------------------------------------------------------------------------------------

function question(id: string, title: string, over: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] {
  return { id, title, text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, chase_due: false, chases: 0, about: null, options: [], ...over };
}
function owed(id: string, text: string, over: Partial<S["FollowupAction"]> = {}): S["FollowupAction"] {
  return { id, text, due: null, project_name: "", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0, ...over };
}

const followSections: S["FollowupSection"][] = [
  {
    person: "PER-1",
    name: "Pat Example",
    is_pm: true,
    questions: [question("Q-1", "Matte or soft-touch?", { kind: "decision", options: [{ id: "OPT-1", name: "Matte" }, { id: "OPT-2", name: "Soft-touch" }], origin: { kind: "source", source: "SRC-1" }, project_name: "Spring book" })],
    actions: [
      owed("ACT-9", "Approve the proof", { due: "2026-11-03", project_name: "Spring book", blocker: { id: "PER-2", kind: "person", name: "Robin Sample", state: "waiting", sent: "2026-10-05", who: "Robin Sample" } }),
      owed("ACT-10", "Pick a launch date", { on_hold: "the printer's quote" }),
    ],
    message: "",
    to_send: 0,
  },
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [
      question("Q-2", "Is the index final?", { project_name: "Spring book" }),
      question("Q-3", "Who prints the cover?", { status: "sent", sent: "2026-10-04", waiting_days: 7, chase_due: true, chases: 1, followed_up: "2026-10-08", project_name: "Spring book" }),
    ],
    actions: [
      owed("ACT-1", "Send the index", { due: "2026-10-16", project_name: "Spring book", told: "2026-10-01", told_days: 10, chase_due: true, chases: 1, followed_up: "2026-10-09", origin: { kind: "source", source: "SRC-1" } }),
      owed("ACT-2", "Check the spine", { due: "2026-10-20" }),
    ],
    message: "Hi Robin,\n\nIs the index final?\n\nThanks!",
    to_send: 2,
    nudge: { round: 1, text: "Hi Robin,\n\nA reminder about the index.", action_ids: ["ACT-1"], question_ids: ["Q-3"] },
    later: [question("Q-5", "Which proof round is this?", { held_until: "2026-10-20", held_for_name: "Print sync", project_name: "Spring book" }), question("Q-6", "Any news on the barcode?", { held_until: "2026-10-25" })],
  },
  {
    person: "PER-3",
    name: "Dana Whitlock",
    is_pm: false,
    questions: [],
    actions: [owed("ACT-3", "Book the printer", { due: "2026-10-12", project_name: "Autumn book", told: "2026-10-02", told_days: 9, on_hold: "the printer's quote" }), owed("ACT-4", "Order the sample copies", { told: "2026-10-03", told_days: 8 })],
    message: "",
    to_send: 0,
  },
];

test("Follow-ups, by person on each tab and by project, with a person's message in the detail, says names, dates and words", async () => {
  besidePane();
  fakeApi({
    "GET followups": () => followSections,
    "GET people": () => [],
    "GET today/agenda": () => [],
    "GET projects": () => [],
    "GET sources/SRC-1": () => ({ id: "SRC-1", title: "Email from the printer", kind: "pasted", trust: "untrusted", received_at: at("2026-10-09", 14), url: null, text: "Text.", limit: null }),
  });
  const user = userEvent.setup();
  const view = renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  await screen.findByRole("textbox", { name: /Message to Robin Sample/ });
  sweep(view.container);
  await user.click(screen.getByRole("button", { name: "Waiting on them" }));
  await screen.findByText("Who prints the cover?");
  // Each person's line chooses them, and the detail beside the list is swept for each.
  for (const open of screen.queryAllByRole("button", { name: /^(Dana Whitlock|Robin Sample)/ })) {
    await user.click(open);
    sweep(view.container);
  }
  await user.click(screen.getByRole("button", { name: /^Robin Sample/ }));
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  await screen.findByRole("textbox", { name: /nudge|Message/i });
  sweep(view.container);
  await user.click(screen.getByRole("button", { name: "Later" }));
  await screen.findByText("Which proof round is this?");
  sweep(view.container);
  await user.click(screen.getByRole("radio", { name: "By project" }));
  await screen.findAllByText("Spring book");
  sweep(view.container);
});

// ---- Sources -------------------------------------------------------------------------------------------------------

/** Made-up addresses are built from parts, so none is written out whole. */
const AT = "@";

function watched(id: string, label: string, over: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] {
  const started = at("2026-10-10", 10, 30);
  return { id, label, connector: "folder", connector_label: "A folder", enabled: true, every_minutes: 15, items: 3, last: { outcome: "ok", started_at: started, new: 0, changed: 0, removed: 0 }, read_at: started, failures: 0, problem: null, ...over };
}

test("Sources, with every kind of read and the closes nobody saw, says names, dates and words", async () => {
  const started = at("2026-10-10", 10, 30);
  const sources: S["WatchSourceView"][] = [
    watched("SRC-A", "Inbox", { connector_label: "A mailbox", items: 12, last: { outcome: "ok", started_at: started, new: 2, changed: 1, removed: 0, unsorted: "2 messages weren't sorted by the assistant, so they were handed in as work." }, looked_back_to: "2026-09-10", look_back_choices: [7, 30], account: `pat${AT}example.com`, author: "PER-1", author_name: "Pat Example", reads: ["mail"] }),
    watched("SRC-B", "Quiet folder"),
    watched("SRC-C", "First read", { last: { outcome: "baseline", started_at: started, new: 0, changed: 0, removed: 0 } }),
    watched("SRC-D", "Away", { last: { outcome: "offline", started_at: at("2026-10-11", 8), new: 0, changed: 0, removed: 0 }, read_at: started }),
    watched("SRC-E", "Slowed", { last: { outcome: "throttled", started_at: started, new: 0, changed: 0, removed: 0, retry_at: at("2026-10-11", 15) } }),
    watched("SRC-F", "Broken", { last: { outcome: "failed", started_at: started, error: "refused", error_kind: "auth", error_advice: "Sign in again.", new: 0, changed: 0, removed: 0, retry_at: at("2026-10-11", 16) }, failures: 3, problem: "It can't be read: refused. Sign in again." }),
    watched("SRC-G", "Not yet read", { last: null, read_at: null }),
    watched("SRC-H", "Switched off", { enabled: false, connector_label: "" }),
    watched("SRC-I", "Stale one", { stale: true }),
  ];
  fakeApi({
    "GET watch": () => sources,
    "GET auto-closed": () => [{ id: "REQ-9", version: 4, title: "Spacing change in the style sheet", source: "Quiet folder", change: "changed", rule: "Spacing only", reason: "only spacing changed", created_at: at("2026-10-10", 9) }],
    "GET silent-closes": () => ({
      count: 3,
      closes: [
        { ref: "changeset:CS-1:0", kind: "assistant", how: "dropped", title: "Send the proof", when: at("2026-10-10", 9), why: "the printer said so", run: "RUN-1" },
        { ref: "request:REQ-2", kind: "rule", how: "closed", title: "Plan the launch", rule: "Spacing", when: at("2026-10-10", 9), why: "only spacing changed" },
        { ref: "snapshot:SN-3", kind: "set_aside", how: "set_aside", title: "A newsletter", rule: "Bulk mail", when: at("2026-10-10", 9), why: "bulk" },
      ],
      measure: { days: 28, since: at("2026-09-13", 9), until: at("2026-10-11", 9), total: 12, silent: 3, by_person: 6, approved: 3, rate: 0.25, kinds: [{ kind: "rule", silent: 1, total: 4 }] },
    }),
    "GET set-aside": () => ({
      items: [{ id: "SA-1", version: 3, section: "sales", title: "Offer one", sender: `Sender <one${AT}lists.example.com>`, source: "Inbox", received: at("2026-10-11", 8, 30), reason: "it was sent to many people", address: `one${AT}lists.example.com`, domain: "lists.example.com" }, { id: "SA-2", version: 3, section: "personal", title: "Offer two", source: "Inbox", received: null, reason: "you set it aside as personal mail", address: `two${AT}example.com`, domain: null }],
      deleted: 0,
    }),
    "GET sign-ins": () => [
      { name: "demo/one", label: "Service one", status: "signed_in", ready: true, callback: "http://localhost:8080/auth/demo/one/callback", app: "workspace", account: `pat${AT}example.com`, missing: ["Mail.Read"] },
      { name: "demo/two", label: "Service two", status: "expired", ready: true, callback: "http://localhost:8080/auth/demo/two/callback", app: "workspace", allows: ["Read your mail"] },
    ],
    "GET watch/kinds": () => [{ name: "folder", label: "A folder", plugin: null, items: [], first_run: "baseline" }],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET projects": () => [],
    "GET watch/authors": () => [{ id: "PER-1", name: "Pat Example" }],
  });
  const view = renderApp(<Sources onAsk={vi.fn()} />);
  await screen.findByText("Switched off");
  await screen.findByText("Send the proof");
  await screen.findByText("Offer two");
  sweep(view.container);
});

// ---- Settings ------------------------------------------------------------------------------------------------------

function setting(key: string, over: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  const [file] = key.split(".");
  return { key, file, group: "workspace", description: `What ${key} does.`, type: "text", options: [], value: "", default: "", source: "default", locked: false, basic: true, editable: true, ...over };
}

const STANCES = ["manage", "alongside", "report_to", "watch"];

const settingItems: S["SettingItem"][] = [
  setting("workspace.name", { value: "Spring workspace", default: "Workspace", source: "file" }),
  setting("workspace.language", { type: "choice", choices: "languages", options: ["en-US", "en-GB"], value: "en-GB", default: "en-US", source: "file" }),
  setting("workspace.timezone", { type: "choice", options: ["Europe/London", "America/New_York"], choices: "time_zones", value: "Europe/London", default: "Europe/London" }),
  setting("workspace.limit", { type: "integer", value: 4, default: 4 }),
  setting("workspace.on", { type: "yes_no", value: true, default: true }),
  setting("workspace.names", { type: "list", value: ["Rob"], default: [] }),
  setting("workspace.fixed", { value: "from env", source: "env", locked: true }),
  setting("workspace.table", { type: "other", value: { x: 1 }, editable: false }),
  setting("workspace.hidden", { basic: false, advanced: true, value: "deep" }),
  setting("steward.default_stance", { group: "steward", type: "choice", options: STANCES, value: "alongside", default: "manage", source: "file" }),
  setting("ai.budget", { group: "ai", type: "number", value: 2, default: 2 }),
  setting("storage.backups.every_hours", { group: "storage.backups", type: "integer", value: 24, default: 24 }),
  setting("storage.sync.folder", { group: "storage.sync", picker: "folder", value: "", default: "" }),
  setting("ui.today.limit", { group: "ui.today", type: "integer", value: 5, default: 5 }),
  setting("ui.theme", { group: "ui", type: "choice", options: ["system", "dark"], value: "system", default: "system" }),
  setting("demo.title", { group: "workspace.plugins.demo", plugin: "demo", value: "Lantern", source: "file" }),
];

const aiAccount = (name: string, over: Partial<S["AiAccountView"]> = {}): S["AiAccountView"] => ({
  name, label: "", kind: "service-a", adapter: "adapter-one", base_url: null, models: { everyday: "model-a" }, used_for: [], backup_for: [], has_key: true, key_state: "saved", key_where: null, key_ending: false, answered_at: null, spent_today_usd: 0, checked_for: [], check_failed_for: [], checked_at: null, paused_until: null, check_usd: null, accepted_unchecked: false, ...over,
});
const aiAccounts = [
  aiAccount("main", { label: "Main account", used_for: ["routine", "deep"], answered_at: at("2026-10-10", 12), spent_today_usd: 1.2, paused_until: at("2026-10-11", 15) }),
  aiAccount("second", { label: "Second account", has_key: false, key_state: "none", backup_for: ["routine", "deep"], checked_for: ["routine", "deep"], checked_at: at("2026-10-10", 9), models: { default: "default" } }),
  aiAccount("trial", { label: "Trial account", key_state: "missing" }),
];
const fit = (tier: string, over: Partial<S["AiKindFit"]> = {}): S["AiKindFit"] => ({ tier, skills: 2, measured: 2, stale: 0, below: 0, runs: 20, passes: 18, cost_per_pass_usd: 0.02, status: "ok", ...over });
const aiRouting: S["AiRoutingView"] = {
  kinds: [{ name: "notes", label: "Notes", tier: "routine", default_tier: "routine", custom: false, source: "default", fits: [fit("routine"), fit("deep", { status: "stale" })], suggested_tier: null, suggestion_why_not: null }],
  tiers: [
    { name: "routine", account: "main", escalate_to: "deep", escalate_source: "file" },
    { name: "deep", account: "second", escalate_to: null, escalate_source: "default" },
  ],
  rules: [{ task: "notes", input_chars_over: null, quoted_messages_over: 3, data_level: null, tier: "deep" }],
  rules_source: "file",
  rule_suggestions: [],
  min_score: 0.8,
  confirm_above_usd: 0.1,
  per_run_usd: 0.25,
};

function SettingsScreen() {
  const [section, setSection] = useState<SettingsSection>("you");
  return <Settings section={section} onSection={setSection} onOpenGuide={vi.fn()} onOpenAddons={vi.fn()} onChooseSource={vi.fn()} />;
}

test("Settings, in every section, says names, dates and words", async () => {
  fakeApi({
    "GET settings": () => ({ fingerprint: "fp-1", items: settingItems, changed_at: at("2026-10-10", 10, 30) }),
    "GET setup": () => ({ steps: [], finished: true, local: true, walkthrough: {} }),
    "GET ai/accounts": () => aiAccounts,
    "GET ai/endpoints": () => [{ id: "service-a", name: "Service A", adapter: "adapter-one", base_url: "", needs_key: true, note: "" }],
    "GET ai/skills": () => ({ min_score: 0.8, stale_days: 60, accounts: [] }),
    "GET ai/routing": () => aiRouting,
    "GET data-forms": () => [],
    "GET addon-secrets": () => [],
    "GET backup-key": () => ({ where: "none", name: null }),
    "GET setup/folders": () => [],
    "GET notifications": () => ({ enabled: true, browser: true, webhook: { where: "none", name: null }, quiet_now: false, mail_ready: false, problem: null }),
    "GET jobs": () => [
      { name: "demo/refresh-feeds", plugin: "demo", enabled: true, every_minutes: 60, last_run_at: at("2026-10-10", 14), last_outcome: "ok", last_error: null },
      { name: "demo/sweep-old-items", plugin: "demo", enabled: false, every_minutes: 1, last_run_at: at("2026-10-10", 15, 30), last_outcome: "failed", last_error: "The source didn't answer." },
      { name: "demo/never-ran", plugin: "demo", enabled: true, every_minutes: 15, last_run_at: null, last_outcome: null, last_error: null },
    ],
    "GET lists": () => [{ id: "L-1", name: "project-status", label: "Project status", values: ["On track"], retired: [], used_by: [] }],
  });
  const user = userEvent.setup();
  const view = renderApp(<SettingsScreen />);
  const nav = await screen.findByRole("navigation", { name: "Settings sections" });
  await within(nav).findByRole("link", { name: "You and the workspace" });
  await within(nav).findByRole("link", { name: "Lists" });
  const seen: string[] = [];
  for (const name of within(nav).getAllByRole("link").map((a) => a.textContent ?? "")) {
    const link = within(nav).getByRole("link", { name });
    // Connections and Quality are screens of their own; the rest are sections of this one.
    if (!/^(#|\/)?(settings|$)/.test(link.getAttribute("href") ?? "") && !/#settings/.test(link.getAttribute("href") ?? "")) continue;
    await user.click(link);
    seen.push(name);
    sweep(view.container, STANCES);
  }
  expect(seen.length).toBeGreaterThan(5);
});

// ---- Since yesterday -----------------------------------------------------------------------------------------------

type Entry = S["SinceEntryView"];

const entry = (over: Partial<Entry>): Entry => ({
  ref: "changeset:CS-1:0",
  act: "closed",
  title: "Send the floor plan",
  when: at("2026-10-10", 19),
  because: "said",
  seen: false,
  undo: "changeset",
  quote: "it went out this morning",
  said_by: "PER-2",
  said_by_name: "Ana Cole",
  by_you: false,
  record: { kind: "action", id: "ACT-1" },
  changeset: "CS-1",
  op: 0,
  ...over,
});

test("Since yesterday, with every kind of act and reason, says names, dates and words", async () => {
  const entries: Entry[] = [
    entry({}),
    entry({ ref: "changeset:CS-2:0", act: "moved", title: "Book the venue", quote: "let's say October 30", day: "2026-10-30", seen: true, record: { kind: "action", id: "ACT-2" }, changeset: "CS-2" }),
    entry({ ref: "changeset:CS-5:0", act: "moved", title: "Order the paper", quote: "later", seen: true, record: { kind: "action", id: "ACT-5" }, changeset: "CS-5" }),
    entry({ ref: "changeset:CS-3:0", act: "added", title: "Order the flowers", quote: "I will order the flowers", by_you: true, record: { kind: "action", id: "ACT-3" }, changeset: "CS-3" }),
    entry({ ref: "snapshot:SNAP-1", act: "set_aside", title: "Autumn sale", because: "sorting", reason: "it is bulk mail", quote: null, said_by: null, said_by_name: null, record: null, changeset: null, op: null, snapshot: "SNAP-1", undo: "set_aside", version: 4 }),
    entry({ ref: "request:REQ-1", act: "closed", title: "Plan", because: "rule", reason: "only spacing changed", quote: null, said_by: null, said_by_name: null, record: null, changeset: null, op: null, request: "REQ-1", undo: "closer_look", version: 2 }),
    entry({ ref: "changeset:CS-4:0", act: "closed", title: "Tell the shop when the proofs ship", because: "replied", day: "2026-10-10", by_you: true, quote: "The proofs ship November 3.", changeset: "CS-4" }),
    entry({ ref: "changeset:CS-6:0", act: "closed", title: "Check the index", because: "meeting", quote: null, said_by: null, said_by_name: null, changeset: "CS-6" }),
    entry({ ref: "changeset:CS-7:0", act: "dropped", title: "Reprint the flyer", quote: "no longer needed", said_by: null, said_by_name: null, changeset: "CS-7" }),
  ];
  fakeApi({
    "GET since-yesterday": () => ({ as_of: at("2026-10-11", 9), since: at("2026-10-10", 7), unseen: 5, entries }),
    "POST since-yesterday/seen": () => ({ ok: "seen" }),
    "GET today/queue": () => [],
  });
  const view = renderApp(<SinceYesterday onOpenRecord={vi.fn()} />);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(entries.length);
  sweep(view.container);
});

// ---- Knowledge -----------------------------------------------------------------------------------------------------

const WORKSPACE: S["Scope"] = { scope: "workspace", task_kinds: [], records: [], filter: {}, projects: [], people: [], except: [] };

function lesson(id: string, text: string, over: Partial<S["KnowledgeView"]> = {}): S["KnowledgeView"] {
  return { id, kind: "lesson", version: 4, text, status: "active", learned_from: "person", trust: "trusted", learned_at: at("2026-10-01", 9), applies_to: WORKSPACE, id_patterns: [], used: 0, given: 0, ...over };
}
function rule(id: string, name: string, text: string, over: Partial<S["RuleView"]> = {}): S["RuleView"] {
  return { id, version: 2, name, text, status: "active", learned_from: "seed", trust: "trusted", learned_at: at("2026-09-20", 9), applies_to: WORKSPACE, constrains: [], enforced: false, used: 0, given: 0, ...over };
}

test("Knowledge, with lessons, rules and their scopes and evidence, says names, dates and words", async () => {
  const entries = [
    lesson("LES-1", "Release dates come from the schedule.", { used: 12, given: 15, last_used: at("2026-10-09", 9), kept_at: at("2026-10-02", 9), kept_by: "PER-1", evidence: { quote: "the schedule is the source", request: "REQ-1" } }),
    lesson("LES-2", "Catering work goes to the venue lead.", { status: "proposed", learned_from: "input", trust: "untrusted", learned_at: at("2026-10-10", 9), person: "PER-2", project: "PRJ-1", origin: { kind: "source", source: "SRC-1" } }),
    lesson("GLOSS-1", "A launch review is the meeting before release.", { kind: "glossary_entry", term: "launch review", meaning: "the meeting before release", applies_to: { ...WORKSPACE, except: ["PRJ-2"] } }),
    lesson("LES-3", "An old habit.", { status: "retired", learned_at: at("2026-09-01", 9) }),
    lesson("LES-4", "Questions about budgets go to finance.", { kind: "routing_entry", status: "proposed", learned_at: at("2026-10-11", 8), applies_to: { ...WORKSPACE, scope: "projects", projects: ["PRJ-1"], people: ["PER-1"], task_kinds: ["notes"] } }),
    lesson("LES-5", "Say the date before the time.", { kind: "style_note", discard_reason: undefined, status: "discarded" }),
  ];
  const rules = [
    rule("RULE-1", "question-names-reader", "Every question names its reader.", { used: 3, given: 3, last_used: at("2026-10-11", 8), kept_at: at("2026-10-02", 9), kept_by: "PER-1" }),
    rule("RULE-2", "owner-needed", "Never close an action without an owner.", { status: "retired", constrains: ["action.close"] }),
    rule("RULE-3", "one-input", "One input per call.", { status: "proposed", learned_from: "assistant", enforced: true, applies_to: { ...WORKSPACE, scope: "projects", projects: ["PRJ-1"] } }),
  ];
  fakeApi({
    "GET knowledge": () => entries,
    "GET knowledge/rules": () => rules,
    "GET knowledge/rules/review": () => ({ days: 30, flagged: [{ id: "RULE-1", name: "question-names-reader", text: "Every question names its reader.", version: 2, applied: 3, present: 0, applies_to: WORKSPACE }], stable_chars: 100, stable_budget: 6000, moved: 2, due: true }),
    "GET projects": () => [{ id: "PRJ-1", name: "Spring book" }, { id: "PRJ-2", name: "Autumn book" }],
    "GET people": () => [{ id: "PER-1", name: "Sample Person" }, { id: "PER-2", name: "Robin Sample" }],
  });
  const view = renderApp(<Knowledge onOpenReview={vi.fn()} />);
  await screen.findByRole("list", { name: "What Helper knows" });
  // Each filter shows other rows, and each row says where it came from, what it reaches and how much it was used.
  const user = userEvent.setup();
  for (const filter of [/^Proposed/, /^Active/, /^Unused/, /^No longer used/]) {
    await user.click(screen.getByRole("radio", { name: filter }));
    sweep(view.container);
  }
  await user.click(screen.getByRole("radio", { name: /^Active/ }));
  const rows = within(screen.getByRole("list", { name: "What Helper knows" })).getAllByRole("listitem");
  expect(rows.length).toBeGreaterThan(2);
  for (const row of rows) {
    for (const more of within(row).queryAllByRole("button", { name: /^(Narrow|Where|Details|More)/ })) await user.click(more);
    sweep(view.container);
  }
});

// ---- Files ---------------------------------------------------------------------------------------------------------

test("Files, with a project, a built file, a replaced file and one whose project is gone, says names, dates and words", async () => {
  const file = (id: string, name: string, over: Partial<S["FileView"]> = {}): S["FileView"] => ({
    id, version: 1, name, media_type: "text/plain", size: 2048, file_kind: "attachment", kind_label: "Attachment", project: null, meta: {}, origin: "upload", replaces: null, added_at: at("2026-10-09", 14), data_level: "internal", ...over,
  });
  fakeApi({
    "GET files": () => [
      file("FILE-3", "built.pdf", { size: 3 * 1024 * 1024, origin: "tool", kind_label: "Build", project: "PRJ-1", meta: { pages: 120, built_on: "2026-10-09" }, data_level: "restricted" }),
      file("FILE-2", "notes v2.txt", { replaces: "FILE-1", project: "PRJ-9" }),
      file("FILE-1", "notes.txt", { file_kind: "", kind_label: "" }),
    ],
    "GET projects": () => [{ id: "PRJ-1", name: "Spring book", group: null, owner: null, owner_name: null }],
    "GET plugin-actions": () => [],
  });
  const view = renderApp(<Files />);
  await screen.findByRole("listitem", { name: "built.pdf" });
  sweep(view.container);
});

// ---- Handover ------------------------------------------------------------------------------------------------------

test("Handover, in each state, says names, dates and words", async () => {
  const side = (computer: string, changes: number, latest: string) => ({ computer, changes, latest });
  const states: S["HandoverView"][] = [
    { state: "diverged", here: side("Desk", 7, at("2026-10-10", 16, 10)), folder: side("Laptop", 1, at("2026-10-09", 9, 5)), computer: "", last_seen: null, minutes_left: 0, chosen: null },
    { state: "chosen", here: null, folder: null, computer: "", last_seen: null, minutes_left: 0, chosen: "folder" },
    { state: "elsewhere", here: null, folder: null, computer: "Laptop", last_seen: at("2026-10-10", 16, 10), minutes_left: 6, chosen: null },
    { state: "clear", here: null, folder: null, computer: "", last_seen: null, minutes_left: 0, chosen: null },
  ];
  for (const state of states) {
    fakeApi({
      "GET sync/handover": () => state,
      "GET status": () => statusFixture({ can_restart: true }),
      "GET runtime-config": () => ({ instance: null }),
    });
    const view = renderApp(
      <RestartProvider hellos={1}>
        <Handover />
      </RestartProvider>,
    );
    await screen.findByRole("heading", { name: "Which copy to keep" });
    await waitFor(() => expect(view.container.querySelectorAll("p, li").length).toBeGreaterThan(0));
    sweep(view.container);
    view.unmount();
  }
});

// ---- Quality -------------------------------------------------------------------------------------------------------

test("Quality, with every measure filled, says names, dates and words", async () => {
  fakeApi({
    "GET quality": () => ({
      days: 28,
      min_corrections_per_week: 10,
      since: "2026-09-13",
      until: "2026-10-11",
      knowledge_used: [{ task: "notes", runs_given: 4, runs_applied: 3, dropped: 0, rate: 0.75 }],
      repeat_corrections: [
        { task: "notes", week: "2026-10-05", corrections: 12, repeats: 5, enough: true, rate: 0.4 },
        { task: "notes", week: "2026-10-12", corrections: 2, repeats: 2, enough: false, rate: null },
      ],
      missing: [{ week: "2026-10-05", groups: [{ wording: "an op to put an action on hold", count: 2, tasks: ["notes"], changesets: ["CS-1", "CS-2"], last_seen: at("2026-10-08", 9) }] }],
      closes: { total: 41, silent: 2, days: [{ day: "2026-10-09", total: 30, silent: 1 }, { day: "2026-10-10", total: 11, silent: 1 }] },
      endings: { made: 12, wrong: 3, declined: 1, undone: 1, reopened: 1, days: [{ day: "2026-10-10", made: 12, wrong: 3 }] },
      counts: { person: "PER-1", present: 30, missed: 4, entered: 2, days: [{ day: "2026-10-09", present: 20, missed: 3 }, { day: "2026-10-10", present: 10, missed: 1 }] },
      missed: [
        { person: "PER-1", person_name: "Casey Example", week: "2026-10-05", week_end: "2026-10-11", count: 3 },
        { person: "PER-1", person_name: "Casey Example", week: "2026-10-12", week_end: "2026-10-18", count: 1 },
      ],
      replays: { count: 2, last_run: at("2026-10-09", 9) },
      apart: { missed: 3, declined: 1, dropped: 2, weeks: [{ week: "2026-10-05", week_end: "2026-10-11", missed: 3, declined: 1, dropped: 2 }] },
    }),
  });
  const view = renderApp(<Quality onBack={vi.fn()} />);
  await screen.findByText(/^Counting from /);
  sweep(view.container);
});

// ---- Stages --------------------------------------------------------------------------------------------------------

test("Stages, as a board and as a list, says names, dates and words", async () => {
  const stages = [{ id: "first", label: "First step" }, { id: "second", label: "Second step" }, { id: "third", label: "Third step" }];
  const record = (id: string, title: string, over: Partial<S["StageView"]> = {}): S["StageView"] => ({
    record: { kind: "project", id }, title, version: 3, current: "second", current_label: "Second step", next: stages[2], stages, checks: [], ready: true, project: null, owners: [], due: null, ...over,
  });
  const items = [
    record("PRJ-1", "Alpha item", { project: "Harbor refit", owners: ["Ada Example", "Bo Example"], due: "2026-11-02" }),
    record("PRJ-2", "Beta item", { current: "first", current_label: "First step", next: stages[1], ready: false, checks: [{ id: "one", passed: false, reason: "Add the missing text first." }, { id: "two", passed: true, reason: "Already fine." }] }),
    record("PRJ-3", "Gamma item", { current: null, current_label: null, next: stages[0] }),
  ];
  const request: S["StageRequestView"] = { id: "REQ-1", version: 2, task: "notes", state: "needs_you", approval: "required", waiting: "Waiting for you to start it.", stage_start: { kind: "project", record: "PRJ-1", stage: "second", changeset: "CS-1" } };
  for (const mode of ["board", "list"]) {
    window.localStorage.setItem("stages.view", mode);
    fakeApi({ "GET stages/records": () => items, "GET stages/requests": () => [request] });
    const view = renderApp(<Stages />);
    await screen.findByText("Alpha item");
    sweep(view.container);
    view.unmount();
  }
  window.localStorage.clear();
});

// ---- Add-ons -------------------------------------------------------------------------------------------------------

test("Add-ons, available and installed, says names, dates and words", async () => {
  const none: S["PackSummary"] = { adds: { item_types: [], screens: 0, today: 0, ai_work: 0, actions: 0, setup_steps: 0, sources: 0 }, reaches: { sign_ins: [], hosts: [], programs: [], keys: 0 }, keeps: "open" };
  const pack = (id: string, over: Partial<S["PackView"]> = {}): S["PackView"] => ({
    id, name: `Name of ${id}`, summary: `What ${id} does`, publisher: `Publisher of ${id}`, maintainers: false, updated: "2026-09-01", version: "1.0.0", price: { model: "free", amount: null, currency: "USD", period: null, note: "" },
    homepage: null, homepage_domain: null, install: `install ${id}`, demo: false, compatible: null, installed_version: null, removable: false, enabled: false, feed: "packs.example.com", what: none, costs: [], ...over,
  });
  fakeApi({
    "GET packs": () => ({
      enabled: true,
      feeds: [{ domain: "packs.example.com", error: null, notes: [], read_at: at("2026-10-10", 9, 30) }],
      available: [
        pack("a", { price: { model: "one_time", amount: 20, currency: "USD", period: null, note: "" }, compatible: true, what: { adds: { ...none.adds, screens: 2, item_types: ["chapter"] }, reaches: { ...none.reaches, hosts: ["print.example.com"] }, keeps: "restricted" }, costs: [{ label: "Drafting a chapter", tokens: 8000, usd: 0.04, account: true }, { label: "Reading a source", tokens: 13333, usd: null, account: true }] }),
        pack("b", { price: { model: "subscription", amount: 5, currency: "USD", period: "month", note: "" }, compatible: false, homepage: "https" + "://print.example.com/x", homepage_domain: "print.example.com" }),
      ],
      installed: [
        { name: "alpha", version: "0.2.0", description: "Does alpha things", enabled: true, state: "enabled", reason: null, removable: false, what: none },
        { name: "gamma", version: "1.0.0", description: "Needs more", enabled: true, state: "disabled", reason: "it needs a newer version of the app", removable: false, what: none },
      ],
    }),
  });
  const user = userEvent.setup();
  const view = renderApp(<Addons onBack={vi.fn()} />);
  await screen.findByText("Name of a");
  sweep(view.container);
  await user.click(screen.getByRole("tab", { name: "Installed" }));
  await screen.findByText("Does alpha things");
  sweep(view.container);
});

// ---- Drafts --------------------------------------------------------------------------------------------------------

test("a long text's versions and the review of a pending draft say names, dates and words", async () => {
  const KIND = "demo/chapter";
  const on = `kind=${encodeURIComponent(KIND)}&id=CHP-1`;
  const field = "body_text";
  const version = (over: Partial<S["TextVersionView"]>): S["TextVersionView"] => ({ id: "V-1", number: 1, version: 1, status: "accepted", source: "edit", words: 12, base: null, note: null, created_at: at("2026-10-09", 14), questions: [], unmapped: [], ...over });
  const pending = version({ id: "V-2", number: 2, version: 7, status: "pending", source: "draft", words: 20, base: 1, note: "A tighter opening", questions: ["Is the harbor scene before the storm?"], unmapped: ["A table the editor could not map"] });
  fakeApi({
    [`GET record?${on}`]: () => ({ kind: KIND, id: "CHP-1", version: 4, fields: { id: "CHP-1", title: "The harbor", owner: "PER-2", due: "2026-11-01", body_text: "" }, long_text: [field] }),
    [`GET kinds/${KIND}`]: () => ({
      kind: KIND,
      fields: [
        { name: "id", description: "", type: "text", required: true, editable: false },
        { name: "title", description: "What the chapter is called.", type: "text", required: true, editable: true },
        { name: "owner", description: "", refers_to: "person", type: "reference", required: false, editable: true },
        { name: "due", description: "", type: "date", required: false, editable: true },
        { name: field, description: "The chapter itself.", long_text: "plain", type: "long_text", required: false, editable: false },
      ],
    }),
    "GET people": () => [{ id: "PER-2", name: "Robin Example" }],
    "GET projects": () => [],
    "GET lists": () => [],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    [`GET record-pages/CHP-1?kind=${encodeURIComponent(KIND)}`]: () => ({
      kind: KIND, id: "CHP-1", version: 4, name: "The harbor",
      details: [{ field: "owner", value: "PER-2", type: "text", refs: [{ kind: "person", id: "PER-2", name: "Robin Example" }] }],
      open_actions: [], open_questions: [], completed_actions: [], fact_source: null,
      activity: [{ at: at("2026-10-09", 14), kind: KIND, id: "CHP-1", name: "The harbor", op: "text.propose", field, actor: "assistant", by_assistant: true }],
    }),
    [`GET texts?kind=${encodeURIComponent(KIND)}&id=CHP-1&field=${field}`]: () => ({
      text: "First paragraph.\n\nSecond paragraph.",
      current: 1,
      authorship: [{ start: 0, end: 20, kind: "person", words: 5 }, { start: 20, end: 40, kind: "assistant", words: 3 }, { start: 40, end: 50, kind: "assistant_edit", words: 2 }],
      versions: [pending, version({}), version({ id: "V-3", number: 3, version: 2, status: "discarded", source: "draft", note: null })],
    }),
    "GET text-versions/V-2/review": () => ({
      version: pending,
      current: 1,
      three_way: true,
      regions: [
        { id: "r1", side: "pending", base: "The first opening.", current: "The old opening.", pending: "A new opening." },
        { id: "r2", side: "pending", base: "", current: "", pending: "An added line." },
        { id: "", side: "current", base: "", current: "Already changed here.", pending: "" },
      ],
      pending_text: "",
    }),
    [`GET working-copies/formats?kind=${encodeURIComponent(KIND)}&field=${field}`]: () => [],
    [`GET working-copies?${on}`]: () => [],
    [`GET plugin-actions?${on}`]: () => [],
    [`GET task-kinds?${on}`]: () => [],
  });
  const user = userEvent.setup();
  const view = renderApp(<RecordPage kind={KIND} id="CHP-1" onBack={vi.fn()} />);
  const section = await screen.findByRole("region", { name: "Body text" });
  await within(section).findByText("A tighter opening");
  sweep(view.container);
  await user.click(within(section).getByRole("button", { name: "Review version 2" }));
  const dialog = await screen.findByRole("dialog", { name: "Review the changes" });
  await within(dialog).findByText(/^Change 1 of/);
  sweep(dialog);
});
