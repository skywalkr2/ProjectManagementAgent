import "@testing-library/jest-dom/vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { useShortcuts } from "../lib/keys";
import { showNewLines } from "../lib/queue-hold";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  const group: Line["group"] = ["decision", "question", "who_is", "owner", "held", "go", "first_go", "restart"].includes(kind)
    ? "decide"
    : kind === "review"
      ? "review"
      : kind === "send" || kind === "nudge"
        ? "send"
        : "risk";
  return { key: `${kind}:1`, group, kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const emptyTitle: S["ItemTitle"] = { kind: "email", person_name: "Sam Example", topic: "proof copies" };

const decision: Line = line("decision", { key: "question:Q-1", text: "Matte or soft-touch?", question: "Q-1", project: "PRJ-1", project_name: "Spring book" });
const review: Line = line("review", {
  key: "review:REQ-1",
  count: 3,
  request: "REQ-1",
  changeset: "CS-1",
  title: emptyTitle,
  outcome: { actions_added: 3, held: 1 },
});
const send: Line = line("send", { key: "send:PER-2", person: "PER-2", person_name: "Robin Sample", count: 2, questions: ["Q-2"], actions: ["ACT-2"] });

const pm = (questions: S["FollowupQuestion"][] = []): S["FollowupSection"] => ({
  person: "PER-1",
  name: "Pat Example",
  is_pm: true,
  questions,
  actions: [],
  message: "",
  to_send: 0,
});
const decisionQuestion: S["FollowupQuestion"] = {
  id: "Q-1",
  title: "Matte or soft-touch?",
  text: "",
  links: [],
  kind: "decision",
  status: "open",
  sent: null,
  waiting_days: null,
  chase_due: false, chases: 0,
  about: null,
  options: [],
};
const robin: S["FollowupSection"] = {
  person: "PER-2",
  name: "Robin Sample",
  is_pm: false,
  questions: [{ ...decisionQuestion, id: "Q-2", title: "Is the index final?", kind: "question" }],
  actions: [{ id: "ACT-2", text: "Send the index", due: null, project_name: "", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 }],
  message: "Hi Robin,\n\nIs the index final?",
  to_send: 2,
};

function change(id: string): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: "Email from Sam Example",
    changeset: {
      id: "CS-1",
      summary: "Three actions.",
      status: "applied",
      reviewed: false,
      trust: "untrusted",
      ops: [{ index: 0, op: "action.add", status: "applied", reason: null, group: "op0", title: "Send two spine options", meta: { owners: [] }, evidence: null, record: { kind: "action", id: "ACT-7" }, ask: null }],
    },
  } as S["ChangeItem"];
}

/** The window's shortcut keys, as the app registers them. */
function Keys() {
  useShortcuts({ next: "j", previous: "k", primary: "a", show_new: "N" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined, show_new: showNewLines });
  return null;
}

function show(lines: Line[], extra: Routes = {}, over: { wide?: boolean } = {}) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: !!over.wide && /min-width: 1680px/.test(query),
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [change("REQ-1")],
    "GET followups": () => [pm([decisionQuestion]), robin],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  const onView = vi.fn();
  const { client } = renderApp(
    <RestartProvider hellos={1}>
      <Keys />
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  /** What the live stream does when something changed elsewhere: the screen asks again. */
  const refresh = () => act(() => client.invalidateQueries());
  return { calls, onView, refresh };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const row = (kind: string) => document.querySelector<HTMLElement>(`[data-queue-line="${kind}"]`)!;

test("the queue is one ranked list in the engine's order, each line starting with a verb and offering one primary", async () => {
  show([decision, review, send]);
  await screen.findByText("Matte or soft-touch?", { selector: "li *" });
  const lines = Array.from(document.querySelectorAll("[data-queue-line]")).map((el) => el.getAttribute("data-queue-line"));
  expect(lines).toEqual(["decision", "review", "send"]);
  // The groups head the lists, in the engine's order.
  expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Decide", "Review", "Send and follow up"]);
  expect(within(row("decision")).getByRole("button", { name: "Answer" })).toBeInTheDocument();
  expect(within(row("review")).getByRole("button", { name: "All looks good" })).toBeInTheDocument();
  expect(within(row("send")).getByRole("button", { name: "Review & copy" })).toBeInTheDocument();
  // One primary per row: the rest is in the menu.
  for (const kind of ["decision", "review", "send"]) {
    expect(within(row(kind)).getAllByRole("button").filter((b) => b.getAttribute("data-variant") === "primary")).toHaveLength(1);
  }
});

test("the heading says how many lines need the person, and the same number is the menu's", async () => {
  show([decision, review, send], { "GET plugin-today": () => [{ plugin: "demo", id: "L-1", text: "Look at the proof", about: null, action: null, action_is: null, why: "", until: null }] });
  // The heading line says it, and so does the pane's own count for a screen reader.
  await waitFor(() => expect(screen.getAllByText(/4 things need you/)).toHaveLength(2));
  expect(screen.getByRole("heading", { level: 2, name: "Needs you" })).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Needs you" })).getByText("4", { selector: "[aria-hidden]" })).toBeInTheDocument();
});

test("an empty queue says so in one line", async () => {
  show([]);
  expect(await screen.findByText("Nothing needs you right now.")).toBeInTheDocument();
  expect(screen.getByText(/Nothing needs you$/)).toBeInTheDocument();
});

const watched = (id: string, over: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] => ({
  id,
  label: id,
  connector: "kind-a",
  connector_label: "A kind",
  enabled: true,
  every_minutes: 15,
  items: 0,
  last: null,
  read_at: null,
  failures: 0,
  problem: null,
  ...over,
});

test("the heading says what was read, and an empty Today says nothing needs you together with it", async () => {
  const read = new Date().toISOString();
  show([], { "GET watch": () => [watched("a", { read_at: read, last: { outcome: "ok", started_at: read, new: 0, changed: 0, removed: 0 } })] });
  const empty = await screen.findByText((_, el) => el?.hasAttribute("data-queue-empty") === true && /Nothing needs you · Read 1 source, last at /.test(el.textContent ?? ""));
  expect(empty).toBeInTheDocument();
  expect(screen.getAllByText(/Read 1 source, last at /).length).toBeGreaterThanOrEqual(2); // the heading's line and the empty state's
  expect(screen.getByText(/Nothing needs you$/)).toBeInTheDocument();
});

test("when a source couldn't be read, neither the heading nor the empty Today says nothing needs you alone", async () => {
  const read = new Date().toISOString();
  show([], { "GET watch": () => [watched("m", { label: "Work mail", read_at: read, last: { outcome: "failed", started_at: read, new: 0, changed: 0, removed: 0 } })] });
  const empty = await screen.findByText((_, el) => el?.hasAttribute("data-queue-empty") === true && /couldn't be read/.test(el.textContent ?? ""));
  expect(empty.textContent).toMatch(/^Nothing found that needs you/);
  expect(screen.getByText(/Nothing found that needs you$/)).toBeInTheDocument();
  expect(screen.queryByText(/Nothing needs you/)).toBeNull();
  expect(screen.getAllByText(/Work mail couldn't be read since/).length).toBeGreaterThanOrEqual(2);
});

test("a row names its project only when the screen holds more than one", async () => {
  const other = line("owner", { key: "question:Q-9", text: "Plan the launch", project: "PRJ-2", project_name: "Autumn book", question: "Q-9" });
  show([decision, other]);
  await screen.findByText("Pick an owner for “Plan the launch”");
  expect(within(row("decision")).getByText("Spring book")).toBeInTheDocument();
  expect(within(row("owner")).getByText("Autumn book")).toBeInTheDocument();
});

test("with one project on screen the tag is left out", async () => {
  show([decision, review]);
  await screen.findByText("Matte or soft-touch?", { selector: "li *" });
  expect(screen.queryByText("Spring book")).toBeNull();
});

test("a review card is titled by what it holds", async () => {
  show([
    review,
    line("review", { key: "review:REQ-2", count: 4, request: "REQ-2", changeset: "CS-2", outcome: { actions_added: 2, questions: 1, notes: 1 } }),
  ]);
  expect(await screen.findByText("Look over 3 to-dos Helper added")).toBeInTheDocument();
  expect(screen.getByText("Look over 4 things Helper did")).toBeInTheDocument();
  expect(within(row("review")).getByText(/1 waits for you/)).toBeInTheDocument();
});

test("a review card whose every change was refused says so instead of counting nothing", async () => {
  show([line("review", { key: "review:REQ-3", count: 2, request: "REQ-3", changeset: "CS-3", outcome: { refused: 2 } })]);
  expect(await screen.findByText("See why 2 things Helper found couldn't be recorded")).toBeInTheDocument();
});

test("All looks good acts at once on the whole review card, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([review], {
    "POST changesets/CS-1/looks-good": () => ({ ok: "CS-1" }),
    "POST changesets/CS-1/reopen": () => ({ ok: "CS-1" }),
  });
  await user.click(await screen.findByRole("button", { name: "All looks good" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/looks-good")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/reopen")).toBe(true));
});

test("the first go is one line with its price, and Go starts the tasks", async () => {
  const user = userEvent.setup();
  const { calls } = show([line("first_go", { key: "first_go", count: 3, estimate_usd: 0.3 })], { "POST runs/first-go": () => ({ started: 3 }) });
  expect(await screen.findByText(/Start the assistant: 3 items, about/)).toBeInTheDocument();
  expect(screen.getByText("Nothing is spent until you press Start.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Start" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST runs/first-go")).toBe(true));
});

test("a line that has items opens them under itself below 1680px, and the primary says it is open", async () => {
  const user = userEvent.setup();
  show([decision]);
  const answer = await screen.findByRole("button", { name: "Answer" });
  expect(answer).toHaveAttribute("aria-expanded", "false");
  await user.click(answer);
  expect(answer).toHaveAttribute("aria-expanded", "true");
  const open = row("decision");
  expect(await within(open).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
  // Close puts it away again.
  await user.click(within(open).getByRole("button", { name: "Close" }));
  expect(within(row("decision")).queryByRole("textbox")).toBeNull();
});

test("from 1680px the items open in the inspector beside the queue, and the row stays one line", async () => {
  const user = userEvent.setup();
  show([decision], {}, { wide: true });
  const inspector = await screen.findByRole("complementary", { name: "Details" });
  // The first line is open from the start, with the items to answer; showing it changes nothing.
  expect(await within(inspector).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
  expect(within(row("decision")).queryByRole("textbox")).toBeNull();
  await waitFor(() => expect(row("decision")).not.toBeNull());
  await user.click(within(row("decision")).getByRole("button", { name: "Answer" }));
  expect(await within(inspector).findByRole("textbox", { name: "Your answer" })).toHaveFocus();
});

test("Review & copy opens the message to copy, with the cursor able to edit it", async () => {
  const user = userEvent.setup();
  show([send]);
  await user.click(await screen.findByRole("button", { name: "Review & copy" }));
  const box = await screen.findByRole("textbox", { name: /Message to Robin Sample/ });
  expect(box).toHaveValue("Hi Robin,\n\nIs the index final?");
  expect(screen.getByText("Send 2 items to Robin Sample")).toBeInTheDocument();
});

test("a card's menu has Look closer and Send back, which opens the note to send it back with", async () => {
  const user = userEvent.setup();
  show([review]);
  await user.click(await screen.findByRole("button", { name: /More actions for Look over 3 to-dos/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Send back with a note" }));
  expect(await screen.findByRole("textbox")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send back" })).toBeDisabled();
});

test("an overdue line opens the to-dos it counts, each to mark done", async () => {
  const user = userEvent.setup();
  const overdue = line("overdue", { key: "overdue", group: "risk", count: 2, actions: ["ACT-1", "ACT-2"], due: "2026-10-08", waiting_days: 5 });
  show([overdue], {
    "GET today/todo": () => [
      { action: "ACT-1", text: "Send the index", project: null, due: "2026-10-08", overdue: true },
      { action: "ACT-2", text: "Approve the proof", project: null, due: "2026-10-09", overdue: true },
      { action: "ACT-3", text: "Plan the launch", project: null, due: "2026-10-20", overdue: false },
    ],
  });
  expect(await screen.findByText("Finish 2 overdue to-dos")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Show" }));
  const open = row("overdue");
  expect(await within(open).findByText("Send the index")).toBeInTheDocument();
  expect(within(open).getByText("Approve the proof")).toBeInTheDocument();
  expect(within(open).queryByText("Plan the launch")).toBeNull();
});

test("the restart and paused lines are rows of the queue, drawn with their own words", async () => {
  show([line("restart", { key: "restart", count: 2 }), line("paused", { key: "paused:main", group: "risk", account: "main", count: 1, until: "2099-01-01T15:30:00+00:00" })], {
    "GET status": () => statusFixture({ can_restart: true }),
  });
  const restart = await screen.findByRole("region", { name: "Restart needed" });
  expect(restart).toHaveTextContent("Restart to resume 2 waiting tasks");
  expect(within(restart).getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  const paused = screen.getByRole("region", { name: "Paused account" });
  expect(paused).toHaveTextContent("main");
  expect(within(paused).getByRole("button", { name: "Open AI accounts" })).toBeInTheDocument();
  // Restart comes first, then the group of what is at risk.
  expect(document.querySelectorAll("[data-queue-line]")[0]).toBe(restart);
});

test("the cursor starts on the first line, and the arrows and Enter walk and open it", async () => {
  const user = userEvent.setup();
  show([decision, review, send]);
  await screen.findByText("Matte or soft-touch?", { selector: "li *" });
  await waitFor(() => expect(row("decision")).toHaveFocus());
  await user.keyboard("{ArrowDown}");
  expect(row("review")).toHaveFocus();
  await user.keyboard("{ArrowUp}");
  expect(row("decision")).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(await within(row("decision")).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
});

test("the arrow keys and the shortcut letters never act while the cursor is in a field", async () => {
  const user = userEvent.setup();
  show([decision, review]);
  await user.click(await screen.findByRole("button", { name: "Answer" }));
  const box = await within(row("decision")).findByRole("textbox", { name: "Your answer" });
  box.focus();
  await user.keyboard("jk{ArrowDown}");
  expect(box).toHaveFocus();
  expect(box).toHaveValue("jk");
});

test("lines that arrive while the person is working in the queue wait behind 'N new · Show'", async () => {
  const user = userEvent.setup();
  let lines = [decision, review];
  show([], {
    "GET today/queue": () => lines,
    "POST changesets/CS-1/looks-good": () => {
      // While the cursor is in the queue, the engine now has a line that wasn't there before, and the old one is done.
      lines = [decision, send];
      return { ok: "CS-1" };
    },
  });
  await user.click(await screen.findByRole("button", { name: "All looks good" }));
  const pill = await screen.findByRole("button", { name: "Show 1 new item" });
  expect(document.querySelector('[data-queue-line="send"]')).toBeNull();
  // Nothing moved under the cursor; Show brings the new line in.
  await user.click(pill);
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Show 1 new item" })).toBeNull();
});

test("a request to look at a changeset opens its line", async () => {
  const { reveal } = await import("../lib/reveal");
  show([review]);
  await screen.findByText("Look over 3 to-dos Helper added");
  let handled = false;
  await act(async () => {
    handled = reveal("changeset", "CS-1");
  });
  expect(handled).toBe(true);
  expect(await within(row("review")).findByText("Send two spine options")).toBeInTheDocument();
});

// ---- one-item lines are titled by the item (designer answer 34) ----------------------------------------------------

test("a line that holds one item is titled by the item itself; a line that groups several keeps its count", async () => {
  const one = line("review", { key: "review:REQ-5", count: 1, request: "REQ-5", changeset: "CS-5", subject: "Send two spine options", outcome: { actions_added: 1 } });
  const overdueOne = line("overdue", { key: "overdue", count: 1, actions: ["ACT-1"], due: "2026-10-08", waiting_days: 5, subject: "Approve the proof" });
  show([decision, one, review, overdueOne]);
  expect(await screen.findByText("Matte or soft-touch?", { selector: "li *" })).toBeInTheDocument();
  expect(screen.queryByText("Make 1 decision")).toBeNull();
  expect(within(row("decision")).getByRole("button", { name: "Answer" })).toBeInTheDocument();
  expect(screen.getByText("Send two spine options")).toBeInTheDocument();
  expect(screen.getByText(/Look over 1 to-do Helper added/)).toBeInTheDocument();
  expect(screen.getByText("Look over 3 to-dos Helper added")).toBeInTheDocument();
  expect(screen.getByText("Approve the proof", { selector: "li *" })).toBeInTheDocument();
  expect(screen.queryByText("Finish 1 overdue to-do")).toBeNull();
  expect(screen.getByText(/Was due .*5 days ago/)).toBeInTheDocument();
});

// ---- the details pane follows the line that has the cursor (designer answer 34) ------------------------------------

const inspector = () => screen.findByRole("complementary", { name: "Details" });

test("from 1680px the pane opens on the first line at once, headed by the line's subject and where it is in the list", async () => {
  show([decision, review, send], {}, { wide: true });
  const pane = await inspector();
  expect(await within(pane).findByRole("heading", { name: "Matte or soft-touch?" })).toBeInTheDocument();
  expect(within(pane).getByText("1 of 3 · j / k")).toBeInTheDocument();
  expect(await within(pane).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
  expect(within(pane).queryByText("Choose an item to see its details.")).toBeNull();
});

test("the pane shows the line that has the cursor, and showing a line marks nothing", async () => {
  const user = userEvent.setup();
  const { calls } = show([decision, review, send], {}, { wide: true });
  const pane = await inspector();
  await within(pane).findByRole("textbox", { name: "Your answer" });
  await waitFor(() => expect(row("decision")).toHaveFocus());
  await user.keyboard("j");
  expect(row("review")).toHaveFocus();
  expect(await within(pane).findByRole("heading", { name: "Look over 3 to-dos Helper added" })).toBeInTheDocument();
  expect(within(pane).getByText("2 of 3 · j / k")).toBeInTheDocument();
  expect(await within(pane).findByText("Send two spine options")).toBeInTheDocument();
  await user.keyboard("j");
  expect(await within(pane).findByRole("heading", { name: "Send 2 items to Robin Sample" })).toBeInTheDocument();
  // Looking at lines wrote nothing.
  expect(calls.filter((c) => c.route.startsWith("POST"))).toEqual([]);
});

test("a click on a line shows it in the pane, and clicking it again keeps it there", async () => {
  const user = userEvent.setup();
  show([decision, review], {}, { wide: true });
  const pane = await inspector();
  await screen.findByText(/Look over 3 to-dos Helper added/, { selector: "li *" });
  await user.click(within(row("review")).getByText(/Look over 3 to-dos/));
  expect(await within(pane).findByRole("heading", { name: "Look over 3 to-dos Helper added" })).toBeInTheDocument();
  await user.click(within(row("review")).getByText(/Look over 3 to-dos/));
  expect(within(pane).getByRole("heading", { name: "Look over 3 to-dos Helper added" })).toBeInTheDocument();
});

test("after a line is settled the cursor and the pane move to the next line, not back to the top", async () => {
  const user = userEvent.setup();
  let lines = [decision, review, send];
  show([], {
    "GET today/queue": () => lines,
    "POST changesets/CS-1/looks-good": () => {
      lines = [decision, send];
      return { ok: "CS-1" };
    },
  }, { wide: true });
  const pane = await inspector();
  await user.click(await screen.findByRole("button", { name: "All looks good" }));
  await waitFor(() => expect(row("send")).toHaveFocus());
  expect(await within(pane).findByRole("heading", { name: "Send 2 items to Robin Sample" })).toBeInTheDocument();
  expect(within(pane).getByText("2 of 2 · j / k")).toBeInTheDocument();
});

test("the pane remembers its line when Today is opened again in the same session", async () => {
  const user = userEvent.setup();
  const first = show([decision, review, send], {}, { wide: true });
  void first;
  const pane = await inspector();
  await screen.findByText(/Send 2 items/, { selector: "li *" });
  await user.click(within(row("send")).getByText(/Send 2 items/));
  expect(await within(pane).findByRole("heading", { name: "Send 2 items to Robin Sample" })).toBeInTheDocument();
  cleanup();
  show([decision, review, send], {}, { wide: true });
  expect(await within(await inspector()).findByRole("heading", { name: "Send 2 items to Robin Sample" })).toBeInTheDocument();
  // If its line is gone, the pane takes the line now in its position.
  cleanup();
  show([decision, review], {}, { wide: true });
  expect(await within(await inspector()).findByRole("heading", { name: "Look over 3 to-dos Helper added" })).toBeInTheDocument();
});

test("with nothing that needs the person the pane says so and what comes next, and is never blank", async () => {
  show([], {
    "GET watch": () => [
      { id: "mail-1", label: "Inbox", connector: "x", connector_label: "", reads: ["mail"], enabled: true, every_minutes: 30, items: 0, read_at: "2026-10-16T11:00:00+00:00", failures: 0, secrets: [] },
    ],
  }, { wide: true });
  const pane = await inspector();
  expect(await within(pane).findByText("Nothing needs you")).toBeInTheDocument();
  expect(within(pane).getByText(/Next check /)).toBeInTheDocument();
});

test("below 1680px nothing changes: there is no pane, and Enter expands the line in place", async () => {
  const user = userEvent.setup();
  show([decision, review]);
  await screen.findByText("Matte or soft-touch?", { selector: "li *" });
  expect(screen.queryByRole("complementary", { name: "Details" })).toBeNull();
  await waitFor(() => expect(row("decision")).toHaveFocus());
  await user.keyboard("{Enter}");
  expect(await within(row("decision")).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
});

// ---- N new, held for the pointer too, removals held, Shift+N (designer answer 38) ----------------------------------

test("the list holds still while the pointer is over it, and the new lines come in once the pointer leaves", async () => {
  const user = userEvent.setup();
  let lines = [decision, review];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText(/Look over 3 to-dos/);
  (document.activeElement as HTMLElement | null)?.blur();
  await user.hover(row("review"));
  lines = [decision, review, send];
  await refresh();
  expect(await screen.findByRole("button", { name: "Show 1 new item" })).toBeInTheDocument();
  expect(document.querySelector('[data-queue-line="send"]')).toBeNull();
  await user.unhover(row("review"));
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Show 1 new item" })).toBeNull();
});

test("an empty list holds nothing: the first lines come straight in even with the cursor in the queue", async () => {
  let lines: typeof decision[] = [];
  const { refresh } = show([], { "GET today/queue": () => lines });
  const needs = await screen.findByRole("heading", { level: 2, name: "Needs you" });
  const region = needs.closest("section") ?? needs.parentElement!;
  region.setAttribute("tabindex", "-1");
  region.focus();
  lines = [decision, review];
  await refresh();
  expect(await screen.findByText(/Look over 3 to-dos/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Show \d+ new/ })).toBeNull();
});

test("with nothing holding the list new lines appear at once", async () => {
  let lines = [decision];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText("Matte or soft-touch?", { selector: "li *" });
  (document.activeElement as HTMLElement | null)?.blur();
  lines = [decision, send];
  await refresh();
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /new · Show/ })).toBeNull();
});

test("a line settled elsewhere stays in place, struck through and muted, until the person moves on or presses Show", async () => {
  const user = userEvent.setup();
  let lines = [decision, review, send];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText(/Look over 3 to-dos/);
  await waitFor(() => expect(row("decision")).toHaveFocus());
  lines = [decision, send];
  await refresh();
  // The line is still there where it was, said to be settled, with no button to press by mistake.
  const ghost = await waitFor(() => {
    const el = row("review");
    expect(el).toHaveAttribute("data-ghost");
    return el;
  });
  expect(within(ghost).getByText(/Settled elsewhere/)).toBeInTheDocument();
  expect(within(ghost).queryByRole("button")).toBeNull();
  expect(screen.getAllByRole("listitem").some((li) => li.contains(ghost))).toBe(true);
  // Show lets it go.
  await user.keyboard("{Shift>}N{/Shift}");
  await waitFor(() => expect(document.querySelector('[data-queue-line="review"]')).toBeNull());
  expect(row("send")).toBeInTheDocument();
});

test("a ghost leaves when the cursor moves off it", async () => {
  const user = userEvent.setup();
  let lines = [decision, review, send];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText(/Look over 3 to-dos/);
  await waitFor(() => expect(row("decision")).toHaveFocus());
  await user.keyboard("j");
  expect(row("review")).toHaveFocus();
  lines = [decision, send];
  await refresh();
  await waitFor(() => expect(row("review")).toHaveAttribute("data-ghost"));
  expect(row("review")).toHaveFocus();
  await user.keyboard("j");
  expect(row("send")).toHaveFocus();
  await waitFor(() => expect(document.querySelector('[data-queue-line="review"]')).toBeNull());
});

test("Shift+N shows the waiting lines and keeps the cursor on the line it was on", async () => {
  const user = userEvent.setup();
  let lines = [decision, review];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText(/Look over 3 to-dos/);
  await waitFor(() => expect(row("decision")).toHaveFocus());
  await user.keyboard("j");
  expect(row("review")).toHaveFocus();
  lines = [decision, line("owner", { key: "question:Q-9", text: "Plan the launch", question: "Q-9" }), review, send];
  await refresh();
  expect(await screen.findByRole("button", { name: "Show 2 new items" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("2 new lines");
  await user.keyboard("{Shift>}N{/Shift}");
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
  expect(screen.getByText("Pick an owner for “Plan the launch”")).toBeInTheDocument();
  expect(row("review")).toHaveFocus();
  expect(screen.queryByRole("button", { name: /new · Show/ })).toBeNull();
});

test("the sidebar's count follows the queue at once, whatever the list is holding back", async () => {
  let lines = [decision, review];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await screen.findByText(/Look over 3 to-dos/);
  await waitFor(() => expect(screen.getAllByText(/2 things need you/).length).toBeGreaterThan(0));
  lines = [decision, review, send];
  await refresh();
  await screen.findByRole("button", { name: "Show 1 new item" });
  expect(screen.getAllByText(/3 things need you/).length).toBeGreaterThan(0);
});

// ---- add-on lines sit in the queue's own groups (designer answer 37) ------------------------------------------------

const pluginLine = (over: Partial<S["TodayLineView"]> = {}): S["TodayLineView"] => ({
  plugin: "publishing",
  id: "L-1",
  text: "Approve the post for Friday",
  about: null,
  action: null,
  action_is: null,
  why: "",
  until: null,
  group: "review",
  ...over,
});

test("an add-on's line sits in the group it names, after the queue's own lines, with its source said quietly", async () => {
  show([decision, review], {
    "GET plugin-today": () => [
      pluginLine({ id: "late", text: "Later post", until: "2026-10-30" }),
      pluginLine({ id: "soon", text: "Sooner post", until: "2026-10-20" }),
      pluginLine({ id: "loose", text: "Loose end", group: null }),
    ],
  });
  await screen.findByText(/Look over 3 to-dos/);
  const group = (name: string) => screen.getByRole("heading", { level: 3, name }).closest("section")!;
  const review_ = within(group("Review")).getAllByRole("listitem");
  // The queue's own line first, then the add-on's by the soonest date; it can't put itself first.
  expect(review_.map((li) => li.textContent)).toEqual([
    expect.stringContaining("Look over 3 to-dos"),
    expect.stringContaining("Sooner post"),
    expect.stringContaining("Later post"),
  ]);
  expect(review_[1]).toHaveTextContent("from Publishing");
  // A line naming no group is under "More for today", at the end.
  const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
  expect(headings).toEqual(["Decide", "Review", "More for today"]);
  expect(within(group("More for today")).getByText("Loose end")).toBeInTheDocument();
});

test("with every add-on line in a group the fallback heading is not drawn", async () => {
  show([decision], { "GET plugin-today": () => [pluginLine({ group: "decide" })] });
  await screen.findByText("Approve the post for Friday");
  expect(screen.queryByRole("heading", { level: 3, name: "More for today" })).toBeNull();
  expect(within(screen.getByRole("heading", { level: 3, name: "Decide" }).closest("section")!).getAllByRole("listitem")).toHaveLength(2);
});

// ---- Draft a nudge (designer answer 36) ---------------------------------------------------------------------------

test("a person who hasn't answered gets a nudge line whose button drafts it, open at once in the details", async () => {
  const user = userEvent.setup();
  const waiting: S["FollowupSection"] = {
    ...robin,
    questions: [{ ...decisionQuestion, id: "Q-8", title: "Is the index final?", kind: "question", status: "sent", sent: "2026-10-10", waiting_days: 6, chase_due: true, chases: 0, followed_up: null }],
    actions: [],
    to_send: 0,
    nudge: { text: "Hi Robin,\n\nFollowing up on one thing.", round: 1, question_ids: ["Q-8"], action_ids: [] },
  };
  show([line("nudge", { key: "nudge:PER-2", person: "PER-2", person_name: "Robin Sample", count: 1, waiting_days: 6, questions: ["Q-8"] })], {
    "GET followups": () => [pm(), waiting],
  });
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  const box = await screen.findByRole("textbox", { name: /Message to Robin Sample/ });
  expect(box).toHaveValue("Hi Robin,\n\nFollowing up on one thing.");
  expect(screen.getByText("1st follow-up")).toBeInTheDocument();
});

test("a line open under itself holds the list too, even with the cursor and the pointer elsewhere", async () => {
  const user = userEvent.setup();
  let lines = [decision, review];
  const { refresh } = show([], { "GET today/queue": () => lines });
  await user.click(await within((await screen.findByText(/Look over 3 to-dos/, { selector: "li *" }).then(() => row("decision")))).findByRole("button", { name: "Answer" }));
  await within(row("decision")).findByRole("textbox", { name: "Your answer" });
  (document.activeElement as HTMLElement | null)?.blur();
  await user.unhover(row("decision"));
  lines = [decision, review, send];
  await refresh();
  expect(await screen.findByRole("button", { name: "Show 1 new item" })).toBeInTheDocument();
  expect(document.querySelector('[data-queue-line="send"]')).toBeNull();
  await user.click(screen.getByRole("button", { name: "Show 1 new item" }));
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
});

test("a line that counts things and holds none is not shown, so no line says zero", async () => {
  show([
    decision,
    line("overdue", { key: "overdue:none", count: 0 }),
    line("send", { key: "send:none", count: 0, person: "PER-9", person_name: "Nobody Example" }),
    line("review", { key: "review:none", count: 0 }),
    line("first_go", { key: "first_go:none", count: 0 }),
  ]);
  expect(await screen.findByText("Matte or soft-touch?")).toBeInTheDocument();
  expect(document.querySelectorAll("[data-queue-line]")).toHaveLength(1);
  expect(document.body.textContent).not.toMatch(/\b0 (things|to-dos|questions|items|overdue)/);
});

test("with nothing to do the Needs you panel has no count, in words or as a badge", async () => {
  show([]);
  expect(await screen.findByText("Nothing needs you right now.")).toBeInTheDocument();
  const panel = screen.getByRole("heading", { level: 2, name: "Needs you" }).closest("section") as HTMLElement;
  expect(within(panel).queryByText("0")).toBeNull();
  expect(panel).not.toHaveTextContent(/\b0 things need you/);
});
