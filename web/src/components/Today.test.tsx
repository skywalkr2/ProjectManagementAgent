import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { useShortcuts } from "../lib/keys";
import { RestartProvider } from "../lib/restart";
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
  chase_due: false,
  about: null,
  options: [],
};
const robin: S["FollowupSection"] = {
  person: "PER-2",
  name: "Robin Sample",
  is_pm: false,
  questions: [{ ...decisionQuestion, id: "Q-2", title: "Is the index final?", kind: "question" }],
  actions: [{ id: "ACT-2", text: "Send the index", due: null, project_name: "", told: null, told_days: null, followed_up: null, chase_due: false }],
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
  useShortcuts({ next: "j", previous: "k", primary: "a" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined });
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
  renderApp(
    <RestartProvider hellos={1}>
      <Keys />
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} />
    </RestartProvider>,
  );
  return { calls, onView };
}

afterEach(() => vi.unstubAllGlobals());

const row = (kind: string) => document.querySelector<HTMLElement>(`[data-queue-line="${kind}"]`)!;

test("the queue is one ranked list in the engine's order, each line starting with a verb and offering one primary", async () => {
  show([decision, review, send]);
  await screen.findByText("Answer 1 decision");
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
  expect(await screen.findByText("Nothing needs you right now. New things appear here as they come in.")).toBeInTheDocument();
  expect(screen.getByText(/Nothing needs you$/)).toBeInTheDocument();
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
  await screen.findByText("Answer 1 decision");
  expect(screen.queryByText("Spring book")).toBeNull();
});

test("a review card is titled by what it holds", async () => {
  show([
    review,
    line("review", { key: "review:REQ-2", count: 4, request: "REQ-2", changeset: "CS-2", outcome: { actions_added: 2, questions: 1, notes: 1 } }),
  ]);
  expect(await screen.findByText("Look over 3 actions Helper added")).toBeInTheDocument();
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

test("the first go is one line with its price, and Go starts the runs", async () => {
  const user = userEvent.setup();
  const { calls } = show([line("first_go", { key: "first_go", count: 3, estimate_usd: 0.3 })], { "POST runs/first-go": () => ({ started: 3 }) });
  expect(await screen.findByText(/Start the assistant: 3 items, about/)).toBeInTheDocument();
  expect(screen.getByText("Nothing is spent until you press Go.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Go" }));
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
  expect(within(inspector).getByText("Pick a line to see its items here.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Answer" }));
  expect(await within(inspector).findByRole("textbox", { name: "Your answer" })).toBeInTheDocument();
  expect(within(row("decision")).queryByRole("textbox")).toBeNull();
  await user.click(within(inspector).getByRole("button", { name: "Close" }));
  expect(within(inspector).getByText("Pick a line to see its items here.")).toBeInTheDocument();
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
  await user.click(await screen.findByRole("button", { name: /More actions for Look over 3 actions/ }));
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
  expect(restart).toHaveTextContent("Restart to run 2 waiting requests");
  expect(within(restart).getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  const paused = screen.getByRole("region", { name: "Paused account" });
  expect(paused).toHaveTextContent("main");
  expect(within(paused).getByRole("button", { name: "AI accounts" })).toBeInTheDocument();
  // Restart comes first, then the group of what is at risk.
  expect(document.querySelectorAll("[data-queue-line]")[0]).toBe(restart);
});

test("the cursor starts on the first line, and the arrows and Enter walk and open it", async () => {
  const user = userEvent.setup();
  show([decision, review, send]);
  await screen.findByText("Answer 1 decision");
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
  const pill = await screen.findByRole("button", { name: "1 new · Show" });
  expect(document.querySelector('[data-queue-line="send"]')).toBeNull();
  // Nothing moved under the cursor; Show brings the new line in.
  await user.click(pill);
  expect(await screen.findByText("Send 2 items to Robin Sample")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "1 new · Show" })).toBeNull();
});

test("a request to look at a changeset opens its line", async () => {
  const { reveal } = await import("../lib/reveal");
  show([review]);
  await screen.findByText("Look over 3 actions Helper added");
  let handled = false;
  await act(async () => {
    handled = reveal("changeset", "CS-1");
  });
  expect(handled).toBe(true);
  expect(await within(row("review")).findByText("Send two spine options")).toBeInTheDocument();
});
