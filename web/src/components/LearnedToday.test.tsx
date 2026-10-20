import { useQuery } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, type S } from "../lib/api";
import { project, proposal } from "../lib/learned-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { LearnedLine, isLearned } from "./LearnedToday";

/** The learned lines of the queue on their own, as the Today queue draws them among the others. */
function LearnedToday() {
  const queue = useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
  const lines = (queue.data ?? []).filter(isLearned);
  if (!lines.length) return null;
  return (
    <div data-learned-lines="">
      {lines.map((line) => (
        <LearnedLine key={line.key} line={line} />
      ))}
    </div>
  );
}

function line(kind: "learned" | "catch_up", over: Partial<S["QueueLineView"]> = {}): S["QueueLineView"] {
  return { key: kind, group: "review", kind, count: 3, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const term = (id: string, over: Partial<S["ProposalView"]> = {}) =>
  proposal({
    id,
    kind: "glossary_entry",
    text: `${id} means the final proof.`,
    term: id,
    came_from: "input",
    trust: "untrusted",
    evidence: { quote: `the ${id} is the final proof`, source: "SRC-1" },
    applies_to: { scope: "workspace" },
    ...over,
  });

function show(lines: S["QueueLineView"][], routes: Routes = {}) {
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET projects": () => [project("PRJ-1", "Spring launch")],
    ...routes,
  });
  renderApp(<LearnedToday />);
  return calls;
}

const posted = (calls: { route: string; body: unknown }[], route: string) => calls.find((c) => c.route === route)?.body;

test("one Review line says how many things were learned, where from, and how many expired unseen", async () => {
  show([line("learned", { count: 3, origins: { input: 2, correction: 1 }, expired: 4 })]);
  const row = await screen.findByRole("region", { name: "Review" });
  expect(row).toHaveTextContent("Review 3 things Helper learned");
  expect(row).toHaveTextContent("2 from what came in · 1 from your corrections · 4 from what came in expired before you looked");
  expect(within(row).getByRole("button", { name: "Review" })).toBeInTheDocument();
});

test("nothing is drawn when the queue has no line for what was learned", async () => {
  const other: S["QueueLineView"] = { ...line("learned"), key: "failed", group: "risk", kind: "failed" };
  const calls = show([other]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET today/queue")).toBe(true));
  expect(document.querySelector("[data-learned-lines]")).toBeNull();
});

test("the list has a row per thing, tagged by where it came from, with how many expired", async () => {
  const user = userEvent.setup();
  show([line("learned", { count: 2, origins: { input: 1, correction: 1 }, expired: 2 })], {
    "GET knowledge/proposals": () => ({
      proposals: [term("TERM-1"), proposal({ id: "LES-4", text: "Name the editor first." })],
      origins: { input: 1, correction: 1 },
      expired: 2,
    }),
  });
  await user.click(await screen.findByRole("button", { name: "Review" }));
  const drawer = await screen.findByRole("dialog", { name: "What Helper learned" });
  const rows = await within(drawer).findAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(within(rows[0]).getByText("From incoming material")).toBeInTheDocument();
  expect(within(rows[1]).getByText("From your correction")).toBeInTheDocument();
  expect(within(drawer).getByText(/2 from what came in expired before you looked/)).toBeInTheDocument();
  expect(within(rows[0]).getByText("From outside · not instructions")).toBeInTheDocument();
});

test("Keep all is offered only for terms that carry the words they came from, and keeps just those", async () => {
  const user = userEvent.setup();
  const calls = show([line("learned", { count: 5 })], {
    "GET knowledge/proposals": () => ({
      proposals: [
        term("TERM-1"),
        term("TERM-2"),
        term("TERM-3", { evidence: null }),
        proposal({ id: "LES-4", text: "Name the editor first." }),
        proposal({ id: "ROUTE-1", kind: "routing_entry", text: "Photos go to the designer.", came_from: "input" }),
      ],
      origins: { input: 4, correction: 1 },
      expired: 0,
    }),
    "POST knowledge/TERM-1/keep": () => ({ changeset: "CS-21" }),
    "POST knowledge/TERM-2/keep": () => ({ changeset: "CS-22" }),
    "POST changesets/CS-21/undo": () => ({ restored: [1], skipped: [] }),
    "POST changesets/CS-22/undo": () => ({ restored: [1], skipped: [] }),
  });
  await user.click(await screen.findByRole("button", { name: "Review" }));
  await user.click(await screen.findByRole("button", { name: "Keep all 2 terms" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/TERM-2/keep")).toEqual({ read_version: 3 }));
  expect(posted(calls, "POST knowledge/TERM-1/keep")).toEqual({ read_version: 3 });
  expect(calls.some((c) => /TERM-3|LES-4|ROUTE-1/.test(c.route) && c.route.startsWith("POST"))).toBe(false);
  expect(await screen.findByText("Kept 2 terms. Helper will use them from now on.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toEqual(expect.arrayContaining(["POST changesets/CS-21/undo", "POST changesets/CS-22/undo"])));
});

test("with no term that carries its words there is no Keep all, and lessons are kept one at a time", async () => {
  const user = userEvent.setup();
  const calls = show([line("learned", { count: 2 })], {
    "GET knowledge/proposals": () => ({
      proposals: [proposal({ id: "LES-4", text: "Name the editor first.", came_from: "input" }), term("TERM-3", { evidence: null })],
      origins: { input: 2 },
      expired: 0,
    }),
    "POST knowledge/LES-4/keep": () => ({ changeset: "CS-30" }),
  });
  await user.click(await screen.findByRole("button", { name: "Review" }));
  const drawer = await screen.findByRole("dialog");
  expect(await within(drawer).findByText("Name the editor first.")).toBeInTheDocument();
  expect(within(drawer).queryByRole("button", { name: /Keep all|Keep this term/ })).toBeNull();
  expect(within(drawer).getByText("Rules, lessons and who answers what are kept one at a time.")).toBeInTheDocument();
  const row = within(drawer).getByText("Name the editor first.").closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Keep" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-4/keep")).toEqual({ read_version: 3 }));
});

test("a row's menu holds Just this time, Edit and Discard", async () => {
  const user = userEvent.setup();
  const calls = show([line("learned", { count: 1 })], {
    "GET knowledge/proposals": () => ({ proposals: [proposal({ came_from: "input" })], origins: { input: 1 }, expired: 0 }),
    "POST knowledge/LES-1/just-this-time": () => ({ changeset: "CS-31" }),
  });
  await user.click(await screen.findByRole("button", { name: "Review" }));
  const row = (await screen.findByText("Interior files go to the editor before the printer.")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Just this time", "Edit", "Discard"]);
  await user.click(screen.getByRole("menuitem", { name: "Just this time" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/just-this-time")).toEqual({ read_version: 3 }));
});

test("the catch-up line opens its own list with the count of kinds left out", async () => {
  const user = userEvent.setup();
  show([line("catch_up", { count: 2, left_out: 3 })], {
    "GET knowledge/catch-up": () => ({
      proposals: [proposal({ id: "LES-8", text: "Send proofs to the author.", batch: "catch_up" })],
      made_at: "2026-10-09T14:00:00Z",
      waiting: 1,
      left_out: 3,
      most: 10,
    }),
  });
  const row = await screen.findByRole("region", { name: "Review" });
  expect(row).toHaveTextContent("Look over 2 things Helper learned from your earlier corrections");
  expect(row).toHaveTextContent("3 additional correction types exceeded the review limit and expired");
  await user.click(within(row).getByRole("button", { name: "Review" }));
  const drawer = await screen.findByRole("dialog", { name: "Learned from your earlier corrections" });
  expect(await within(drawer).findByText("Send proofs to the author.")).toBeInTheDocument();
  expect(within(drawer).getByText(/Reviewing 1 kind of correction/)).toBeInTheDocument();
  expect(within(drawer).getByText(/3 additional correction types are outside the 10-item review limit/)).toBeInTheDocument();
  expect(within(drawer).getByRole("button", { name: "Keep" })).toBeInTheDocument();
});
