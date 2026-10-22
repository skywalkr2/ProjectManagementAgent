import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { SinceYesterday } from "./SinceYesterday";
import { WhatChanged } from "./WhatChanged";

// What changed since yesterday (design 6.32, 6.35): one row for each thing done on the person's behalf, in the assistant's
// words with the quote and who said it, Open as the one action and Undo in the row's menu, an unseen close marked in words,
// and opening the list marks it seen as it was drawn.

type Entry = S["SinceEntryView"];

const entry = (over: Partial<Entry>): Entry => ({
  ref: "changeset:CS-1:0",
  act: "closed",
  title: "Send the floor plan",
  when: "2026-10-18T19:00:00Z",
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

const CLOSED = entry({});
const MOVED = entry({
  ref: "changeset:CS-2:0",
  act: "moved",
  title: "Book the venue",
  quote: "let's say October 30",
  day: "2026-10-30",
  seen: true,
  record: { kind: "action", id: "ACT-2" },
  changeset: "CS-2",
});
const ADDED = entry({ ref: "changeset:CS-3:0", act: "added", title: "Order the flowers", quote: "I will order the flowers", by_you: true, record: { kind: "action", id: "ACT-3" }, changeset: "CS-3" });
const SORTED = entry({
  ref: "snapshot:SNAP-1",
  act: "set_aside",
  title: "Autumn sale",
  because: "sorting",
  reason: "it is bulk mail",
  quote: null,
  said_by: null,
  said_by_name: null,
  record: null,
  changeset: null,
  op: null,
  snapshot: "SNAP-1",
  undo: "set_aside",
  version: 4,
});
const RULED = entry({
  ref: "request:REQ-1",
  act: "closed",
  title: "Plan",
  because: "rule",
  reason: "only spacing changed",
  quote: null,
  said_by: null,
  said_by_name: null,
  record: null,
  changeset: null,
  op: null,
  request: "REQ-1",
  undo: "closer_look",
  version: 2,
});
const REPLIED = entry({ ref: "changeset:CS-4:0", act: "closed", title: "Tell the shop when the proofs ship", because: "replied", day: "2026-10-18", by_you: true, quote: "The proofs ship November 3.", changeset: "CS-4" });

function view(entries: Entry[]): S["SinceYesterdayView"] {
  return { as_of: "2026-10-19T16:00:00Z", since: "2026-10-18T07:00:00Z", unseen: entries.filter((e) => !e.seen).length, entries };
}

function open(entries: Entry[], extra: Routes = {}) {
  const calls = fakeApi({
    "GET since-yesterday": () => view(entries),
    "POST since-yesterday/seen": () => ({ ok: "seen" }),
    "GET today/queue": () => [],
    ...extra,
  });
  const onOpenRecord = vi.fn();
  renderApp(<SinceYesterday onOpenRecord={onOpenRecord} />);
  return { calls, onOpenRecord };
}

const rows = () => within(screen.getByRole("list", { name: "What changed since yesterday" })).getAllByRole("listitem");
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

test("each row says the act and its reason in the assistant's voice, with the quote and who said it", async () => {
  open([CLOSED, MOVED, ADDED, REPLIED]);
  expect(await screen.findByRole("heading", { level: 1, name: "Since yesterday" })).toBeInTheDocument();
  await screen.findByRole("list", { name: "What changed since yesterday" });
  const [closed, moved, added, replied] = rows();
  expect(closed).toHaveTextContent("Closed “Send the floor plan”: Ana Cole said “it went out this morning”");
  expect(moved).toHaveTextContent("Moved “Book the venue” to");
  expect(moved).toHaveTextContent("Ana Cole said “let's say October 30”");
  expect(added).toHaveTextContent("Added “Order the flowers”: you said “I will order the flowers”");
  expect(replied).toHaveTextContent("Closed “Tell the shop when the proofs ship”: you replied on");
});

test("a close the person has not seen says so in words, and what was seen or isn't a close does not", async () => {
  open([CLOSED, MOVED, ADDED, SORTED]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  const [closed, moved, added, sorted] = rows();
  expect(closed).toHaveTextContent("You haven't seen this close");
  expect(sorted).toHaveTextContent("You haven't seen this close");
  expect(moved).not.toHaveTextContent("You haven't seen this close");
  expect(added).not.toHaveTextContent("You haven't seen this close");
});

test("rules and sorting say which kind of rule did it and why", async () => {
  open([RULED, SORTED]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  const [ruled, sorted] = rows();
  expect(ruled).toHaveTextContent("Closed “Plan”: a rule closed it: only spacing changed");
  expect(sorted).toHaveTextContent("Set aside “Autumn sale”: a sorting rule set it aside: it is bulk mail");
});

test("Open is the row's one button and Undo is in its menu", async () => {
  const user = userEvent.setup();
  const { onOpenRecord } = open([CLOSED]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  const [row] = rows();
  const buttons = within(row).getAllByRole("button");
  expect(buttons.map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(["Open Send the floor plan", "More actions for Send the floor plan"]);
  await user.click(within(row).getByRole("button", { name: "Open Send the floor plan" }));
  expect(onOpenRecord).toHaveBeenCalledWith("action", "ACT-1");
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  expect(await screen.findByRole("menuitem", { name: "Undo" })).toBeInTheDocument();
});

test("Undo from the menu undoes that one op, says so, and the row leaves the list", async () => {
  const user = userEvent.setup();
  const { calls } = open([CLOSED, ADDED], { "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }) });
  await screen.findByRole("list", { name: "What changed since yesterday" });
  await user.click(within(rows()[0]).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Undo" }));
  await waitFor(() => expect(body(calls, "POST changesets/CS-1/undo")).toEqual({ ops: [0] }));
  expect(await screen.findByText("Undone: Send the floor plan.")).toBeInTheDocument();
  expect(rows()).toHaveLength(1);
  expect(rows()[0]).toHaveTextContent("Order the flowers");
});

test("an undo that was skipped because the record changed says so and keeps the row", async () => {
  const user = userEvent.setup();
  open([CLOSED], { "POST changesets/CS-1/undo": () => ({ restored: [], skipped: [{ ops: [0], reason: "changed" }] }) });
  await screen.findByRole("list", { name: "What changed since yesterday" });
  await user.click(within(rows()[0]).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Undo" }));
  expect(await screen.findByText("Couldn't undo this because it has changed since.")).toBeInTheDocument();
  expect(rows()).toHaveLength(1);
});

test("a rule's close offers a closer look and set-aside mail offers This is work, each with the version that was read", async () => {
  const user = userEvent.setup();
  const { calls } = open([RULED, SORTED], {
    "POST requests/REQ-1/closer-look": () => ({ id: "REQ-1" }),
    "POST set-aside/SNAP-1/work": () => ({ id: "SNAP-1", version: 5, section: "sales", address: null, domain: null }),
  });
  await screen.findByRole("list", { name: "What changed since yesterday" });
  await user.click(within(rows()[0]).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Take a closer look" }));
  await waitFor(() => expect(body(calls, "POST requests/REQ-1/closer-look")).toEqual({ read_version: 2 }));
  await user.click(within(rows()[0]).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "This is work" }));
  await waitFor(() => expect(body(calls, "POST set-aside/SNAP-1/work")).toEqual({ read_version: 4 }));
});

test("opening the list marks it seen as it was drawn", async () => {
  const { calls } = open([CLOSED]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  await waitFor(() => expect(body(calls, "POST since-yesterday/seen")).toEqual({ until: "2026-10-19T16:00:00Z" }));
});

test("an empty list says nothing changed and has nothing to mark", async () => {
  const { calls } = open([]);
  expect(await screen.findByText("Nothing changed since yesterday.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST since-yesterday/seen")).toBe(false);
});

test("a list that can't be loaded says so and can be tried again", async () => {
  const user = userEvent.setup();
  let ok = false;
  fakeApi({ "GET since-yesterday": () => (ok ? view([CLOSED]) : new Refuse(500, "no")), "POST since-yesterday/seen": () => ({ ok: "seen" }), "GET today/queue": () => [] });
  renderApp(<SinceYesterday onOpenRecord={vi.fn()} />);
  expect(await screen.findByText("The list couldn't be loaded.")).toBeInTheDocument();
  ok = true;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText(/Closed “Send the floor plan”/)).toBeInTheDocument();
});

test("the What changed screen's header links to the list", async () => {
  fakeApi({ "GET changes": () => [], "GET stages/records": () => [], "GET stages/ready": () => [], "GET stages/requests": () => [], "GET watch": () => [] });
  renderApp(<WhatChanged />);
  const link = await screen.findByRole("link", { name: "Since yesterday" });
  expect(link.getAttribute("href")).toMatch(/#work\/since$/);
});

const FILED = {
  by: "name" as const,
  word: "Salt Orchard",
  project: "PRJ-1",
  project_name: "Business",
  move_to: "PRJ-2",
  move_to_name: "Personal",
  field: "project" as const,
  version: 3,
};
const ADDED_BY_WORDS = entry({ ref: "changeset:CS-9:0", act: "added", title: "Order the cider", record: { kind: "action", id: "ACT-9" }, changeset: "CS-9", filed: FILED });

test("an item filed by words says why on its row, and Move to the other side is in the menu", async () => {
  const user = userEvent.setup();
  open([ADDED_BY_WORDS, ADDED]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  const [filed, plain] = rows();
  expect(filed).toHaveTextContent("Filed under Business: it names Salt Orchard");
  expect(plain).not.toHaveTextContent("Filed under");
  // The row keeps its one button; Move is a menu item.
  expect(within(filed).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(["Open Order the cider", "More actions for Order the cider"]);
  await user.click(within(filed).getByRole("button", { name: /More actions for/ }));
  expect(await screen.findByRole("menuitem", { name: "Move to Personal" })).toBeInTheDocument();
});

test("a sender's domain that filed an item is said as where it is from", async () => {
  open([entry({ ...ADDED_BY_WORDS, filed: { ...FILED, by: "domain", word: "example.com" } })]);
  await screen.findByRole("list", { name: "What changed since yesterday" });
  expect(rows()[0]).toHaveTextContent("Filed under Business: it's from example.com");
});

test("Move edits the item's project as the person, says so with Undo, and the row no longer says why", async () => {
  const user = userEvent.setup();
  const { calls } = open([ADDED_BY_WORDS], {
    "POST records/edit": () => ({ changeset: "CS-20" }),
    "POST changesets/CS-20/undo": () => ({ restored: ["ACT-9"], skipped: [] }),
  });
  await screen.findByRole("list", { name: "What changed since yesterday" });
  await user.click(within(rows()[0]).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Move to Personal" }));
  await waitFor(() => expect(body(calls, "POST records/edit")).toEqual({ kind: "action", id: "ACT-9", fields: { project: "PRJ-2" }, read_version: 3 }));
  expect(await screen.findByText("Moved to Personal.")).toBeInTheDocument();
  expect(rows()[0]).not.toHaveTextContent("Filed under");
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-20/undo")).toBe(true));
});
