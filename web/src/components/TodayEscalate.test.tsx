import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { takeFilters } from "../lib/open-items";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { person } from "../lib/records-fixtures";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

type Line = S["QueueLineView"];

const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({
  key: `${kind}:1`,
  group: kind === "stale" ? "review" : "send",
  kind,
  count: 1,
  untrusted: false,
  unpriced: 0,
  actions: [],
  questions: [],
  outcome: {},
  ...over,
});

const pm: S["FollowupSection"] = { person: "PER-1", name: "Pat Example", is_pm: true, questions: [], actions: [], message: "", to_send: 0 };

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
    "GET followups": () => [pm],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET people": () => [person("PER-2", "Robin Sample"), person("PER-3", "Sam Twin")],
    "GET status": () => statusFixture({}, { assistant: { last_run_at: "2026-10-20T08:00:00Z" } }),
    "GET runtime-config": () => ({ instance: null }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
  const onView = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { calls, onView };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const row = (kind: string) => document.querySelector<HTMLElement>(`[data-queue-line="${kind}"]`)!;

const escalate = line("escalate", {
  key: "escalate:PER-2:Q-8",
  person: "PER-2",
  person_name: "Robin Sample",
  text: "Is the index final?",
  count: 2,
  waiting_days: 5,
  questions: ["Q-8"],
});

test("after a second follow-up with no answer the line suggests asking someone else, with Pick who", async () => {
  show([escalate]);
  expect(await screen.findByText("Ask someone else about “Is the index final”?")).toBeInTheDocument();
  const found = row("escalate");
  expect(found).toHaveTextContent("Robin Sample hasn't answered after 2 follow-ups");
  expect(within(found).getByRole("button", { name: "Pick who" })).toBeInTheDocument();
  // One primary only, and nothing in it sends anything.
  expect(within(found).getAllByRole("button").filter((b) => b.getAttribute("data-variant") === "primary")).toHaveLength(1);
});

test("for a question Pick who is a list of people; choosing one asks them instead, with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show([escalate], { "POST questions/Q-8/reroute": () => ({ changeset: "CS-1" }) });
  await user.click(await screen.findByRole("button", { name: "Pick who" }));
  const picker = await screen.findByRole("combobox", { name: "Ask instead" });
  await waitFor(() => expect(picker).toHaveFocus());
  await user.selectOptions(picker, "PER-3");
  await user.click(screen.getByRole("button", { name: "Ask them" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-8/reroute")?.body).toEqual({ to: "PER-3" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("for an action it reassigns it, taking the one who hasn't answered off it", async () => {
  const user = userEvent.setup();
  const open: S["OpenActionView"] = {
    id: "ACT-4",
    version: 6,
    text: "Send the index",
    state: "open",
    owners: [
      { person: "PER-2", name: "Robin Sample" },
      { person: "PER-1", name: "Pat Example" },
    ],
    project_name: "",
    since: "2026-10-01",
    to_send: false,
  };
  const { calls } = show([line("escalate", { ...escalate, key: "escalate:PER-2:ACT-4", text: "Send the index", questions: [], actions: ["ACT-4"] })], {
    "GET open-items": () => ({ actions: [open], questions: [], stale_days: 21 }),
    "POST records/edit": () => ({ changeset: "CS-1" }),
  });
  await user.click(await screen.findByRole("button", { name: "Pick who" }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "Ask instead" }), "PER-3");
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "action", id: "ACT-4", read_version: 6, fields: { owners: [{ person: "PER-3" }, { person: "PER-1" }] } }));
});

test("the stale to-dos are one line that opens the list narrowed to them", async () => {
  const user = userEvent.setup();
  const { onView } = show([line("stale", { key: "stale", count: 3, actions: ["A-1", "A-2", "A-3"], waiting_days: 40 })]);
  expect(await screen.findByText("Keep or drop 3 to-dos nobody has touched lately")).toBeInTheDocument();
  expect(row("stale")).toHaveTextContent("The longest has gone 40 days with no change");
  await user.click(within(row("stale")).getByRole("button", { name: "Look over" }));
  expect(onView).toHaveBeenCalledWith("work/open");
  expect(takeFilters()).toEqual({ project: "", person: "", state: "stale" });
});

test("one stale to-do is titled by its own words", async () => {
  show([line("stale", { key: "stale", count: 1, actions: ["A-1"], waiting_days: 30, subject: "Tidy the style sheet" })]);
  expect(await screen.findByText("Keep or drop: Tidy the style sheet")).toBeInTheDocument();
});

test("a stale line holding none is not shown, so no line says zero", async () => {
  show([line("stale", { key: "stale", count: 0 })]);
  expect(await screen.findByText("Nothing needs you right now.")).toBeInTheDocument();
});
