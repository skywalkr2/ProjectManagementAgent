import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project } from "../lib/records-fixtures";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { OpenItems } from "./OpenItems";
import { TodoRow } from "./TodayRail";
import { Today } from "./Today";

// Adding a to-do by hand (design 6.32): the cursor starts in the words, the day and the repeat are said back before
// anything is kept, who and which project are lists, and the toast's Undo takes back every change made. The repeat mark
// shows in words on Today's to-do rows.

const ME = person("P-1", "Quinn Sample", { is_pm: true });
const OTHER = person("P-2", "Robin Example");

const checkedDay = (body: unknown): S["TodoDayView"] => {
  const { words } = body as { words: string };
  return words === "Friday" ? { status: "ok", day: "2026-11-06" } : { status: "unclear", day: null };
};

const checkedRepeat = (body: unknown): S["RepeatCheckView"] => {
  const { phrase, start } = body as { phrase: string; start?: string };
  if (phrase === "every Friday")
    return { status: "ok", rule: "FREQ=WEEKLY;BYDAY=FR", start: start ?? "2026-11-06", shape: { kind: "weekly", interval: 1, weekday: "friday", weekdays: [], days: [], ordinals: [] } };
  if (phrase === "every Tuesday")
    return { status: "off_start", rule: "FREQ=WEEKLY;BYDAY=TU", start: "2026-11-10", shape: { kind: "weekly", interval: 1, weekday: "tuesday", weekdays: [], days: [], ordinals: [] } };
  return { status: "unclear", rule: null, shape: null, start: null };
};

function api(actions: S["OpenActionView"][] = [], extra: Routes = {}) {
  return fakeApi({
    "GET open-items": () => ({ actions, questions: [], stale_days: 21 }),
    "GET people": () => [ME, OTHER],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "POST todos/day": checkedDay,
    "POST repeats/check": checkedRepeat,
    "POST todos": () => ({ action: "A-9", changesets: ["CS-1", "CS-2"] }),
    "POST changesets/CS-2/undo": () => ({ restored: [0], skipped: [] }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
}

const sent = (calls: Array<{ route: string; body: unknown }>) => calls.find((c) => c.route === "POST todos")?.body;

test("an empty list offers Add a to-do as its one primary, and the cursor starts in the words", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  const button = await screen.findByRole("button", { name: "Add a to-do" });
  expect(button).toHaveAttribute("data-variant", "primary");
  await user.click(button);
  expect(await screen.findByRole("textbox", { name: "What to do" })).toHaveFocus();
});

test("with to-dos on the list the button is in the header and is not a primary", async () => {
  const action: S["OpenActionView"] = {
    id: "A-1", version: 1, text: "Send the weekly update", state: "open", owners: [{ person: "P-1", name: "Quinn Sample" }], due: null, project: null, project_name: "",
    parent_name: null, notes: null, since: "2026-10-01", on_hold: null, blocker: null, duplicate: null, origin: null, untouched_days: null, owner_question: null, to_send: false,
  };
  api([action]);
  renderApp(<OpenItems />);
  expect(await screen.findByRole("button", { name: "Add a to-do" })).not.toHaveAttribute("data-variant", "primary");
});

test("the day and the repeat are said back, the person is the default owner, and nothing is kept until Add", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await user.type(screen.getByRole("textbox", { name: "Due (optional)" }), "Friday");
  expect(await screen.findByText(/^Due Fri, Nov 6/)).toBeInTheDocument();
  await user.type(screen.getByRole("textbox", { name: "Repeats" }), "every Friday");
  expect(await screen.findByText("Every Friday, starting November 6")).toBeInTheDocument();
  // Who and which project are lists to pick from.
  const who = screen.getByRole("combobox", { name: "Who does it" });
  await waitFor(() => expect(who).toHaveValue("P-1"));
  await user.selectOptions(who, "P-2");
  await user.selectOptions(screen.getByRole("combobox", { name: "Project (optional)" }), "PRJ-1");
  expect(calls.some((c) => c.route === "POST todos")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(sent(calls)).toEqual({ text: "Send the weekly update", owners: ["P-2"], when: "Friday", project: "PRJ-1", repeat: "every Friday" }));
  expect(await screen.findByText("Added: Send the weekly update")).toBeInTheDocument();
});

test("a day or a repeat that isn't clear is said so and Add stays off", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Water the plants");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Who does it" })).toHaveValue("P-1"));
  await user.type(screen.getByRole("textbox", { name: "Due (optional)" }), "when the moon is out");
  expect(await screen.findByText("Not clear: try 'Friday' or 'next Tuesday', or leave it empty")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  await user.clear(screen.getByRole("textbox", { name: "Due (optional)" }));
  await user.type(screen.getByRole("textbox", { name: "Repeats" }), "quarterly");
  expect(await screen.findByText("Not clear: try 'every Tuesday'")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  await user.clear(screen.getByRole("textbox", { name: "Repeats" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Add" })).toBeEnabled());
  expect(calls.some((c) => c.route === "POST todos")).toBe(false);
});

test("a repeat that doesn't fall on the day says which day it does", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Who does it" })).toHaveValue("P-1"));
  await user.type(screen.getByRole("textbox", { name: "Due (optional)" }), "Friday");
  await screen.findByText(/^Due Fri, Nov 6/);
  await user.type(screen.getByRole("textbox", { name: "Repeats" }), "every Tuesday");
  expect(await screen.findByText(/isn't one of those days/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
});

test("the toast's Undo takes back every change, last first", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Who does it" })).toHaveValue("P-1"));
  await user.click(screen.getByRole("button", { name: "Add" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route.includes("/undo")).map((c) => c.route)).toEqual(["POST changesets/CS-2/undo", "POST changesets/CS-1/undo"]));
});

test("a refusal is said in the toast and the form stays open", async () => {
  const user = userEvent.setup();
  api([], { "POST todos": () => new Refuse(409, "That repeat isn't clear.") });
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Who does it" })).toHaveValue("P-1"));
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByText(/That repeat isn't clear/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "What to do" })).toBeInTheDocument();
});

test("Today's to-do row carries the repeat mark in words", async () => {
  const weekly: S["RepeatView"] = {
    phrase: "every Friday",
    rule: "FREQ=WEEKLY;BYDAY=FR",
    start: "2026-11-06",
    shape: { kind: "weekly", interval: 1, weekday: "friday", weekdays: [], days: [], ordinals: [] },
  };
  fakeApi({ "GET projects": () => [], "GET people": () => [ME] });
  const { container } = renderApp(
    <ul>
      <TodoRow item={{ action: "A-1", text: "Send the weekly update", project: null, due: "2026-11-06", overdue: false, repeat: weekly }} project="" showDue />
      <TodoRow item={{ action: "A-2", text: "Tidy the notes", project: null, due: null, overdue: false }} project="" showDue />
    </ul>,
  );
  const rows = container.querySelectorAll("li");
  expect(within(rows[0] as HTMLElement).getByText("Repeats")).toBeInTheDocument();
  expect(within(rows[0] as HTMLElement).getByText("Repeats")).toHaveAttribute("title", "Every Friday, starting November 6");
  expect(within(rows[1] as HTMLElement).queryByText("Repeats")).toBeNull();
});

test("Add a to-do is a quiet button with Today's to-dos, not in the heading, which stays one row", async () => {
  fakeApi({ "GET projects": () => [], "GET people": () => [ME] });
  const { container } = renderApp(<Today workspace="Demo" onView={() => undefined} onAddSource={() => undefined} onOpenGuide={() => undefined} onOpenRecord={() => undefined} />);
  const button = await screen.findByRole("button", { name: "Add a to-do" });
  expect(button).toHaveAttribute("data-variant", "ghost");
  expect(button.closest('[data-col="todo"]')).not.toBeNull();
  expect(container.querySelector("h1")?.parentElement?.contains(button)).toBe(false);
});

test("how long it takes is a list of common sizes, with another length typed, and is sent as minutes", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  const sizes = screen.getByRole("combobox", { name: "How long it takes" });
  expect(within(sizes).getAllByRole("option").map((o) => o.textContent)).toEqual(["No estimate", "15 minutes", "30 minutes", "45 minutes", "1 hour", "1 hour 30 minutes", "2 hours", "3 hours", "4 hours", "8 hours", "Another length"]);
  await user.selectOptions(sizes, "90");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(sent(calls)).toMatchObject({ text: "Send the weekly update", effort_minutes: 90 }));
});

test("another length is typed in minutes, and no estimate sends none", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await user.selectOptions(screen.getByRole("combobox", { name: "How long it takes" }), "other");
  await user.type(screen.getByRole("spinbutton", { name: "Minutes" }), "50");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(sent(calls)).toMatchObject({ effort_minutes: 50 }));
});

test("with no estimate chosen nothing about effort is sent", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: "Add a to-do" }));
  await user.type(await screen.findByRole("textbox", { name: "What to do" }), "Send the weekly update");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(sent(calls)).toBeDefined());
  expect(sent(calls)).not.toHaveProperty("effort_minutes");
});
