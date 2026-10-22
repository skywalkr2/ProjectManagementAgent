import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { OpenItems } from "./OpenItems";
import { RecordPage } from "./RecordPage";

// Repeating to-dos (design 6.32): the Repeats field in the edit form says what was understood before it is kept, the row
// carries a repeat mark in words, Stop repeating acts at once with Undo, and the detail lists the earlier occurrences.

const weekly: S["RepeatView"] = {
  phrase: "every Friday",
  rule: "FREQ=WEEKLY;BYDAY=FR",
  start: "2026-11-06",
  shape: { kind: "weekly", interval: 1, weekday: "friday", weekdays: [], days: [], ordinals: [] },
};

const action = (over: Partial<S["OpenActionView"]> = {}): S["OpenActionView"] => ({
  id: "A-1",
  version: 3,
  text: "Send the weekly update",
  state: "open",
  owners: [{ person: "P-1", name: "Quinn Sample" }],
  due: "2026-11-02",
  project: null,
  project_name: "",
  parent_name: null,
  notes: null,
  since: "2026-10-01",
  on_hold: null,
  blocker: null,
  duplicate: null,
  origin: null,
  untouched_days: null,
  owner_question: null,
  to_send: false,
  ...over,
});

const checked = (body: unknown): S["RepeatCheckView"] => {
  const { phrase, start } = body as { phrase: string; start?: string };
  if (phrase === "Mondays and Thursdays")
    return {
      status: "ok",
      rule: "FREQ=WEEKLY;BYDAY=MO,TH",
      start: start ?? "2026-11-02",
      shape: { kind: "weekly_days", interval: 1, weekday: null, weekdays: ["monday", "thursday"], days: [], ordinals: [] },
    };
  if (phrase === "every Tuesday")
    return { status: "off_start", rule: "FREQ=WEEKLY;BYDAY=TU", start: "2026-11-03", shape: { kind: "weekly", interval: 1, weekday: "tuesday", weekdays: [], days: [], ordinals: [] } };
  return { status: "unclear", rule: null, shape: null, start: null };
};

function api(shown: S["OpenActionView"][], extra: Routes = {}) {
  return fakeApi({
    "GET open-items": () => ({ actions: shown, questions: [], stale_days: 21 }),
    "GET people": () => [person("P-1", "Quinn Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "POST repeats/check": checked,
    "POST records/edit": () => ({ changeset: "CS-1" }),
    "POST actions/A-1/repeat": () => ({ changeset: "CS-2" }),
    "POST actions/A-1/repeat/stop": () => ({ changeset: "CS-3" }),
    "POST changesets/CS-3/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
}

async function openEdit(user: ReturnType<typeof userEvent.setup>) {
  const list = await screen.findByRole("list", { name: "Open to-dos" });
  await user.click(within(list).getByRole("button", { name: /More actions for Send the weekly update/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit…" }));
  return screen.findByRole("textbox", { name: "Repeats" });
}

test("the Repeats field says back what was understood, under the field, before anything is kept", async () => {
  const user = userEvent.setup();
  const calls = api([action()]);
  renderApp(<OpenItems />);
  const field = await openEdit(user);
  expect(await screen.findByRole("textbox", { name: "What to do" })).toHaveFocus();
  await user.type(field, "Mondays and Thursdays");
  expect(await screen.findByText("Every Monday and Thursday, starting November 2")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST actions/A-1/repeat")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-1/repeat")?.body).toEqual({ phrase: "Mondays and Thursdays", start: "2026-11-02" }));
  expect(calls.some((c) => c.route === "POST records/edit")).toBe(false);
  expect(await screen.findByText("Saved. It repeats.")).toBeInTheDocument();
});

test("words that aren't clear say so with an example, and keep nothing", async () => {
  const user = userEvent.setup();
  const calls = api([action()]);
  renderApp(<OpenItems />);
  await user.type(await openEdit(user), "quarterly");
  expect(await screen.findByText("Not clear: try 'every Tuesday'")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(calls.some((c) => c.route === "POST actions/A-1/repeat")).toBe(false);
});

test("a day that isn't one of the words' days offers the first that is", async () => {
  const user = userEvent.setup();
  const calls = api([action()]);
  renderApp(<OpenItems />);
  await user.type(await openEdit(user), "every Tuesday");
  expect(await screen.findByText(/isn't one of those days/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: /^Use / }));
  expect((screen.getByLabelText("Due") as HTMLInputElement).value).toBe("2026-11-03");
  await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());
  expect(calls.some((c) => c.route === "POST actions/A-1/repeat")).toBe(false);
});

test("a to-do that repeats has a repeat mark in words, and its menu stops the repeat at once with Undo", async () => {
  const user = userEvent.setup();
  const calls = api([action({ due: "2026-11-06", repeat: weekly })]);
  renderApp(<OpenItems />);
  const list = await screen.findByRole("list", { name: "Open to-dos" });
  const [row] = within(list).getAllByRole("listitem");
  const mark = within(row).getByText("Repeats");
  expect(mark).toHaveAttribute("title", "Every Friday, starting November 6");
  await user.click(within(row).getByRole("button", { name: /More actions for Send the weekly update/ }));
  await user.click(await screen.findByRole("menuitem", { name: /Stop repeating/ }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST actions/A-1/repeat/stop")).toBe(true));
  expect(await screen.findByText("Stopped repeating.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-3/undo")).toBe(true));
});

test("a to-do that doesn't repeat has no mark and no Stop repeating", async () => {
  const user = userEvent.setup();
  api([action()]);
  renderApp(<OpenItems />);
  const list = await screen.findByRole("list", { name: "Open to-dos" });
  expect(within(list).queryByText("Repeats")).toBeNull();
  await user.click(within(list).getByRole("button", { name: /More actions for Send the weekly update/ }));
  expect(screen.queryByRole("menuitem", { name: /Stop repeating/ })).toBeNull();
});

test("the to-do's page says how it repeats and lists the earlier ones with their day and how each ended", async () => {
  const page: S["RecordPageView"] = {
    kind: "action",
    id: "A-3",
    version: 1,
    name: "Send the weekly update",
    details: [],
    open_actions: [],
    open_questions: [],
    completed_actions: [],
    fact_source: null,
    repeat: weekly,
    earlier_occurrences: [
      { id: "A-1", due: "2026-10-30", how: "done" },
      { id: "A-2", due: "2026-11-06", how: "dropped" },
    ],
    activity: [],
  };
  fakeApi({
    "GET record?kind=action&id=A-3": () => ({ kind: "action", id: "A-3", version: 1, fields: { id: "A-3" }, long_text: [] }),
    "GET kinds/action": () => ({ kind: "action", fields: [] }),
    "GET record-pages/A-3?kind=action": () => page,
    "GET people": () => [person("P-1", "Quinn Sample")],
    "GET projects": () => [],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    "GET plugin-actions?kind=action&id=A-3": () => [],
    "GET task-kinds?kind=action&id=A-3": () => [],
  });
  renderApp(<RecordPage kind="action" id="A-3" onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Repeats" });
  expect(within(section).getByText("Every Friday, starting November 6")).toBeInTheDocument();
  const rows = within(section).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Done");
  expect(rows[1]).toHaveTextContent("Dropped");
});

test("the edit form shows how long a to-do takes, and a change is sent as its own edit of the to-do", async () => {
  const user = userEvent.setup();
  const calls = api([action({ effort_minutes: 60 })]);
  renderApp(<OpenItems />);
  await openEdit(user);
  const sizes = screen.getByRole("combobox", { name: "How long it takes" });
  expect(sizes).toHaveValue("60");
  await user.selectOptions(sizes, "120");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "action", id: "A-1", read_version: 3, fields: { effort_minutes: 120 } }));
});

test("choosing no estimate clears it, and a length not on the list shows as another length", async () => {
  const user = userEvent.setup();
  const calls = api([action({ effort_minutes: 50 })]);
  renderApp(<OpenItems />);
  await openEdit(user);
  const sizes = screen.getByRole("combobox", { name: "How long it takes" });
  expect(sizes).toHaveValue("other");
  expect(screen.getByRole("spinbutton", { name: "Minutes" })).toHaveValue(50);
  await user.selectOptions(sizes, "");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toMatchObject({ fields: { effort_minutes: null } }));
});
