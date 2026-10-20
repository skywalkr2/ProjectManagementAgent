import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { takeFilters } from "../lib/open-items";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { TopPriorities } from "./TopPriorities";

type Line = S["PriorityLineView"];

function line(extra: Partial<Line> & Pick<Line, "key" | "rank" | "kind" | "text">): Line {
  return { person: "PER-1", person_name: "Pat Example", project: null, project_name: null, due: null, days: null, owners: [], things: [], send: 0, chase: 0, overdue: 0, due_soon: 0, ...extra };
}

const overdue = line({
  key: "action:ACT-1",
  rank: "overdue",
  kind: "action",
  text: "Send the proofs",
  due: "2026-10-12",
  days: 3,
  action: "ACT-1",
  version: 4,
  project: "PRJ-1",
  project_name: "Spring book",
  owners: [{ person: "PER-1", name: "Pat Example" }],
});
const dueSoon = line({ key: "action:ACT-2", rank: "due_soon", kind: "action", text: "Check the cover", due: "2026-10-17", action: "ACT-2", version: 1, owners: [{ person: "PER-1", name: "Pat Example" }] });
const asked = line({ key: "question:Q-1", rank: "waiting", kind: "question", text: "Which printer?", question: "Q-1", days: 2 });
const risky = line({ key: "action:ACT-3", rank: "at_risk", kind: "action", text: "Tidy the schedule", action: "ACT-3", version: 1, project: "PRJ-2", project_name: "Autumn book", owners: [{ person: "PER-1", name: "Pat Example" }] });
const person = line({
  key: "person:PER-5",
  rank: "due_soon",
  kind: "person",
  person: "PER-5",
  person_name: "Robin Sample",
  text: "Robin Sample",
  send: 1,
  chase: 3,
  waiting_days: 5,
  things: [
    { kind: "question", id: "Q-7", text: "Which date?", why: "chase", waiting_days: 5 },
    { kind: "question", id: "Q-8", text: "Which size?", why: "chase", waiting_days: 4 },
    { kind: "question", id: "Q-9", text: "Which paper?", why: "chase", waiting_days: 4 },
    { kind: "question", id: "Q-10", text: "Who prints it?", why: "send" },
  ],
});

function priorities(extra: Partial<S["TopPrioritiesView"]> = {}): S["TopPrioritiesView"] {
  return { lines: [overdue, dueSoon, asked, risky, person], more: 0, blocked: 0, coming: [], ...extra };
}

function open(answer: S["TopPrioritiesView"] = priorities(), extra: Routes = {}, onView = vi.fn()) {
  const calls = fakeApi({ "GET today/priorities": () => answer, ...extra });
  renderApp(<TopPriorities onView={onView} />);
  return { calls, onView };
}

/** The rows of the list, once it has loaded. */
const rows = async () => {
  await screen.findByText("Check the cover");
  return Array.from((await screen.findByRole("region", { name: "Top priorities" })).querySelectorAll<HTMLElement>("[data-row]"));
};

test("the lines are listed in the order the server ranks them, each with a chip, a verb first and why on the second line", async () => {
  open();
  const found = await rows();
  expect(found.map((r) => r.querySelector(".tb-title")?.textContent)).toEqual([
    "Spring bookSend the proofs",
    "Check the cover",
    "Which printer?",
    "Autumn bookTidy the schedule",
    "Robin Sample: send 1 question, follow up on 3 waiting up to 5 days",
  ]);
  expect(within(found[0]).getByText("Overdue Mon, Oct 12")).toBeInTheDocument();
  expect(within(found[0]).getByText("Passed 3 days ago, not marked done")).toBeInTheDocument();
  expect(within(found[1]).getByText("Due Sat, Oct 17")).toBeInTheDocument();
  expect(within(found[1]).getByText("Due soon")).toBeInTheDocument();
  expect(within(found[2]).getByText("Waiting for your answer for 2 days")).toBeInTheDocument();
  expect(within(found[3]).getByText("In Autumn book, which is at risk")).toBeInTheDocument();
});

test("one row for a person holds everything of theirs, with the items in its tooltip and for a screen reader", async () => {
  open();
  const found = await rows();
  const title = found[4].querySelector(".tb-title") as HTMLElement;
  expect(title.getAttribute("title")).toBe("Which date?\nWhich size?\nWhich paper?\nWho prints it?");
  expect(within(found[4]).getByText("Which date? · and 3 more")).toBeInTheDocument();
  expect(within(found[4]).queryAllByRole("button")).toEqual([]);
});

test("a row names its project only when the list holds more than one", async () => {
  open();
  expect(await screen.findByText("Spring book")).toBeInTheDocument();
  expect(screen.getByText("Autumn book")).toBeInTheDocument();
});

test("with one project in the list the tag is left out", async () => {
  open(priorities({ lines: [overdue] }));
  await screen.findByText("Send the proofs");
  expect(screen.queryByText("Spring book")).toBeNull();
});

test("an entry has no buttons and no menu, only its words as a link", async () => {
  open();
  const found = await rows();
  expect(found).toHaveLength(5);
  for (const row of found) {
    expect(within(row).queryAllByRole("button")).toEqual([]);
    expect(within(row).queryAllByRole("menuitem")).toEqual([]);
    expect(within(row).getAllByRole("link")).toHaveLength(1);
  }
});

test("with no line in the queue an entry links to its record", async () => {
  open(priorities(), { "GET today/queue": () => [] });
  const panel = await screen.findByRole("region", { name: "Top priorities" });
  expect(await within(panel).findByRole("link", { name: "Send the proofs" })).toHaveAttribute("href", expect.stringContaining("#records/action/ACT-1"));
  expect(within(panel).getByRole("link", { name: "Which printer?" })).toHaveAttribute("href", expect.stringContaining("#records/question/Q-1"));
  expect(within(panel).getByRole("link", { name: /^Robin Sample: / })).toHaveAttribute("href", expect.stringContaining("#records/person/PER-5"));
});

function queueLine(over: Partial<S["QueueLineView"]> & Pick<S["QueueLineView"], "key" | "kind">): S["QueueLineView"] {
  return { group: "risk", count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

test("an entry that has a line in the queue links to it, and choosing it asks Today to open that line", async () => {
  const user = userEvent.setup();
  const seen: unknown[] = [];
  const listen = (event: Event) => {
    seen.push((event as CustomEvent).detail);
    event.preventDefault();
  };
  window.addEventListener("reveal-row", listen);
  open(priorities(), {
    "GET today/queue": () => [
      queueLine({ key: "overdue", kind: "overdue", count: 2, actions: ["ACT-1", "ACT-9"] }),
      queueLine({ key: "question:Q-1", kind: "question", group: "decide", question: "Q-1" }),
      queueLine({ key: "nudge:PER-5", kind: "nudge", group: "send", person: "PER-5", count: 3, questions: ["Q-7"] }),
    ],
  });
  const panel = await screen.findByRole("region", { name: "Top priorities" });
  await waitFor(() => expect(within(panel).getByRole("link", { name: "Send the proofs" })).toHaveAttribute("href", expect.not.stringContaining("#records")));
  await user.click(within(panel).getByRole("link", { name: "Send the proofs" }));
  await user.click(within(panel).getByRole("link", { name: "Which printer?" }));
  await user.click(within(panel).getByRole("link", { name: /^Robin Sample: / }));
  window.removeEventListener("reveal-row", listen);
  expect(seen).toEqual([
    { type: "line", id: "overdue" },
    { type: "line", id: "question:Q-1" },
    { type: "line", id: "nudge:PER-5" },
  ]);
});

test("the rest are counted with a way to see them, and the blocked ones are counted too", async () => {
  const user = userEvent.setup();
  const { onView } = open(priorities({ more: 3, blocked: 2 }));
  await user.click(await screen.findByRole("button", { name: "3 more · See every to-do and question" }));
  expect(onView).toHaveBeenLastCalledWith("work/open");
  await user.click(screen.getByRole("button", { name: "2 actions are blocked, waiting on something" }));
  expect(onView).toHaveBeenLastCalledWith("work/open");
  expect(takeFilters().state).toBe("on_hold");
});

test("nothing blocked and nothing more says nothing about either", async () => {
  open();
  await screen.findByText("Send the proofs");
  expect(screen.queryByText(/blocked/)).toBeNull();
  expect(screen.queryByText(/See every to-do/)).toBeNull();
});

test("the next days' dated to-dos follow the lines", async () => {
  open(priorities({ lines: [overdue], coming: [{ action: "ACT-9", text: "Order the samples", due: "2026-10-20", project: null, project_name: null, owners: [], mine: true }] }));
  const group = (await screen.findByRole("heading", { name: "Coming up" })).closest("[data-group]") as HTMLElement;
  expect(within(group).getByText("Order the samples")).toBeInTheDocument();
  expect(within(group).getByText("Yours")).toBeInTheDocument();
});

test("with nothing pressing it says so, and when it can't load it offers Try again", async () => {
  open(priorities({ lines: [] }));
  expect(await screen.findByText("Nothing is pressing across your projects.")).toBeInTheDocument();
});

test("a list that can't load says so and tries again", async () => {
  const user = userEvent.setup();
  let ask = 0;
  fakeApi({
    "GET today/priorities": () => {
      ask += 1;
      if (ask === 1) throw new Error("down");
      return priorities({ lines: [overdue] });
    },
  });
  renderApp(<TopPriorities onView={vi.fn()} />);
  expect(await screen.findByText("Top priorities couldn't be loaded.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Send the proofs")).toBeInTheDocument();
});
