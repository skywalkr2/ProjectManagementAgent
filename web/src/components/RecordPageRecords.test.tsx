import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day, monthDay } from "../lib/dates";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { RecordPage } from "./RecordPage";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

// A record's page as activity beside details (design 7.14): what is open with it, what was finished and by whom, what
// happened to it, and for a fact where it came from (designer answer 29).

const page = (over: Partial<S["RecordPageView"]> = {}): S["RecordPageView"] => ({
  kind: "project",
  id: "PRJ-1",
  version: 2,
  name: "Harbor",
  details: [],
  open_actions: [],
  open_questions: [],
  completed_actions: [],
  fact_source: null,
  activity: [],
  ...over,
});

function api(kind: string, id: string, fields: Record<string, unknown>, shown: S["RecordPageView"], extra: Routes = {}) {
  const k = encodeURIComponent(kind);
  return fakeApi({
    [`GET record?kind=${k}&id=${id}`]: () => ({ kind, id, version: 3, fields: { id, ...fields }, long_text: [] }),
    [`GET kinds/${kind}`]: () => ({ kind, fields: [] }),
    [`GET record-pages/${id}?kind=${k}`]: () => shown,
    "GET people": () => [person("PER-1", "Robin Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    [`GET plugin-actions?kind=${k}&id=${id}`]: () => [],
    [`GET task-kinds?kind=${k}&id=${id}`]: () => [],
    ...extra,
  });
}

test("a project's page shows what is open with it, what was finished and by whom, and what happened, beside its details", async () => {
  api(
    "project",
    "PRJ-1",
    { name: "Harbor", status: "On track" },
    page({
      open_actions: [{ id: "ACT-1", text: "Send the proof", due: "2026-10-20", owners: ["Robin Sample"], project: "PRJ-1", project_name: "Harbor", origin: null }],
      open_questions: [{ id: "Q-1", title: "Which trim size?", to: "PER-1", to_name: "Robin Sample", status: "open", kind: "question", origin: null }],
      completed_actions: [{ id: "ACT-2", text: "Book the printer", project: "PRJ-1", project_name: "Harbor", done_by: ["Jordan Pike"], reported_by: "Robin Sample", done_on: "2026-10-12" }],
      activity: [{ at: "2026-10-12T09:00:00Z", kind: "action", id: "ACT-2", name: "Book the printer", op: "action.close#0", field: "status", actor: "assistant", by_assistant: true }],
    }),
  );
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const open = await screen.findByRole("region", { name: "Open with Harbor" });
  expect(within(open).getByRole("link", { name: "Send the proof" })).toBeInTheDocument();
  expect(within(open).getAllByText(/Robin Sample/).length).toBeGreaterThan(0);
  expect(within(open).getByRole("link", { name: "Which trim size?" })).toBeInTheDocument();
  const done = screen.getByRole("region", { name: "Completed" });
  const row = within(done).getByRole("link", { name: "Book the printer" }).closest("li")!;
  expect(row).toHaveTextContent("done by Jordan Pike");
  expect(row).toHaveTextContent("reported by Robin Sample");
  expect(row).toHaveTextContent(monthDay("2026-10-12"));
  const activity = screen.getByRole("region", { name: "Activity" });
  expect(activity).toHaveTextContent("Helper closed Book the printer");
  expect(activity).not.toHaveTextContent("Status");
  expect(screen.getByRole("region", { name: "Details" })).toBeInTheDocument();
});

test("activity says who changed which field of what, by the field's label and the assistant by its name", async () => {
  const entry = (id: string, name: string, field: string, by_assistant: boolean): S["ActivityEntry"] => ({ at: "2026-10-12T09:00:00Z", kind: "action", id, name, op: "record.edit", field, actor: by_assistant ? "assistant" : "pm", by_assistant });
  const shown = page({ activity: [entry("ACT-1", "Send two spine options", "due", true), entry("ACT-2", "Harbor", "why_they_matter", false), entry("ACT-3", "Harbor", "target", true)] });
  api("project", "PRJ-1", { name: "Harbor" }, shown);
  const first = renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const activity = await screen.findByRole("region", { name: "Activity" });
  const rows = within(activity).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Helper changed the due date of Send two spine options");
  expect(within(rows[0]).getByText("Send two spine options").tagName).toBe("STRONG");
  expect(rows[1]).toHaveTextContent("You changed the why they matter of Harbor");
  expect(rows[2]).toHaveTextContent("Helper changed the target date of Harbor");
  expect(activity.textContent).not.toMatch(/·\s*(due|target|Why)/i);
  first.unmount();
  api("project", "PRJ-1", { name: "Harbor" }, shown);
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />, {}, { unnamed: true });
  expect(within(await screen.findByRole("region", { name: "Activity" })).getAllByRole("listitem")[0]).toHaveTextContent("Your assistant changed the due date of Send two spine options");
});

test("a second move of the same date says it moved again, neutrally, with how many times and since when", async () => {
  const moved = (n: number): S["ActivityEntry"] => ({ at: "2026-10-12T09:00:00Z", kind: "action", id: "ACT-1", name: "Send two spine options", op: "record.edit", field: "due", actor: "pm", by_assistant: false, moved_again: n, moved_since: "2026-10-06" });
  api("project", "PRJ-1", { name: "Harbor" }, page({ activity: [moved(3), moved(2)] }));
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const rows = within(await screen.findByRole("region", { name: "Activity" })).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("moved again (third time since Oct 6)");
  expect(rows[1]).toHaveTextContent("moved again (second time since Oct 6)");
  expect(rows[1].textContent).not.toMatch(/slip/i);
});

test("a meta line joins only the parts it has: no dot beside nothing, no lone dot", async () => {
  api(
    "project",
    "PRJ-1",
    { name: "Harbor" },
    page({
      open_actions: [
        { id: "ACT-1", text: "Send the proof", due: "2026-10-20", owners: ["Robin Sample"], project: "PRJ-1", project_name: "Harbor", origin: null, series: null, series_title: null },
        { id: "ACT-2", text: "Check the cover", owners: ["Robin Sample"], project: "PRJ-1", origin: null },
        { id: "ACT-3", text: "Pick a printer", owners: [], origin: null },
      ],
      open_questions: [{ id: "Q-1", title: "Which trim size?", to: null, to_name: null, status: "open", kind: "question", origin: null }],
    }),
  );
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const open = await screen.findByRole("region", { name: "Open with Harbor" });
  const rows = within(open).getAllByRole("listitem");
  expect(rows).toHaveLength(4);
  expect(rows[0]).toHaveTextContent(`Robin Sample · due ${day("2026-10-20")}`);
  for (const row of rows) {
    expect(row.textContent).not.toMatch(/·\s*·/);
    expect(row.textContent).not.toMatch(/·\s*$/);
    expect(row.textContent).not.toMatch(/^\s*·/);
  }
});

test("a project's page has what the assistant knows about it, and a person's page does not", async () => {
  api("project", "PRJ-1", { name: "Harbor" }, page(), {
    "GET projects/PRJ-1/knows": () => ({ id: "PRJ-1", name: "Harbor", sources: [], facts: [{ id: "FACT-1", version: 1, text: "Trim size is fixed.", key: false, source: { basis: "person", on: "2026-10-08", origin: null } }], terms: [], routing: [], unknown: [], area: false, reading: { state: "none", levels: [], readers: [] } }),
  });
  const { unmount } = renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const knows = await screen.findByRole("region", { name: "What Helper knows" });
  expect(await within(knows).findByRole("link", { name: "Trim size is fixed." })).toBeInTheDocument();
  expect(within(knows).getByText(`from you, ${monthDay("2026-10-08")}`)).toBeInTheDocument();
  unmount();
  api("person", "PER-1", { full_name: "Robin Sample" }, page({ kind: "person", id: "PER-1", name: "Robin Sample" }));
  renderApp(<RecordPage kind="person" id="PER-1" onBack={() => {}} />);
  await screen.findByRole("heading", { level: 1, name: "Robin Sample" });
  expect(screen.queryByRole("region", { name: "What Helper knows" })).toBeNull();
});

test("a section with nothing in it isn't there: no Completed, no zero", async () => {
  api("project", "PRJ-1", { name: "Harbor" }, page());
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  await screen.findByRole("heading", { level: 1, name: "Harbor" });
  expect(await screen.findByText("Nothing has happened here yet.")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Completed" })).toBeNull();
  expect(screen.queryByRole("region", { name: /Open with/ })).toBeNull();
});

test("an item for a meeting says so and links to the series' page, by weekday within a week and by date after", async () => {
  const soon = new Date();
  soon.setDate(soon.getDate() + 2);
  const pad = (n: number) => String(n).padStart(2, "0");
  const near = `${soon.getFullYear()}-${pad(soon.getMonth() + 1)}-${pad(soon.getDate())}`;
  api(
    "project",
    "PRJ-1",
    { name: "Harbor" },
    page({
      open_actions: [
        { id: "ACT-1", text: "Send the proof", owners: [], series: "SER-1", series_title: "Print sync", meeting_on: near, origin: null },
        { id: "ACT-2", text: "Check the cover", owners: [], series: "SER-1", series_title: "Print sync", meeting_on: "2031-10-29", origin: null },
      ],
    }),
  );
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  const weekday = new Intl.DateTimeFormat(undefined, { weekday: "long" }).format(soon);
  const link = await screen.findByRole("link", { name: `for ${weekday}'s print sync` });
  expect(link.getAttribute("href")).toMatch(/#records\/series\/SER-1$/);
  expect(screen.getByRole("link", { name: `for ${monthDay("2031-10-29")}'s print sync` })).toBeInTheDocument();
});

test("a person is edited in the same drawer as on the People screen", async () => {
  const user = userEvent.setup();
  api("person", "PER-1", { full_name: "Robin Sample" }, page({ kind: "person", id: "PER-1", name: "Robin Sample" }), {
    "GET kinds/person": () => ({ kind: "person", fields: [{ name: "full_name", description: "", type: "text", required: true, editable: true }] }),
  });
  renderApp(<RecordPage kind="person" id="PER-1" onBack={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Edit details" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit person" });
  expect(within(dialog).getByRole("textbox", { name: "Full name" })).toHaveValue("Robin Sample");
});

// ---- where a fact came from ------------------------------------------------------------------------------------------

const fact = (source: S["FactSource"]) => api("fact", "FACT-1", { text: "Both spines are in the folder." }, page({ kind: "fact", id: "FACT-1", name: "Both spines are in the folder.", fact_source: source }));

test("a fact the person said is 'from you' with the day, and is a link to where it came from", async () => {
  fact({ basis: "person", on: "2026-10-08", origin: { kind: "link", url: `${WEB}example.com/notes`, source: "SRC-1" } });
  renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  const link = await screen.findByRole("link", { name: `from you, ${monthDay("2026-10-08")}` });
  expect(link.getAttribute("href")).toBe(`${WEB}example.com/notes`);
  expect(screen.queryByText("Inferred")).toBeNull();
  expect(screen.queryByRole("button", { name: "Confirm it" })).toBeNull();
});

test("what someone said is named in their own words, or as reported by another person's input", async () => {
  fact({ basis: "said", by: "Ben Person", kind: "email", sender: "Ben Person", on: "2026-10-08", origin: { kind: "source", source: "SRC-1" } });
  const first = renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  expect(await screen.findByRole("button", { name: `from Ben Person's email, ${monthDay("2026-10-08")}` })).toBeInTheDocument();
  first.unmount();
  fact({ basis: "said", by: "Ana Person", reported_by: "Jordan Pike", kind: "pasted", sender: "Jordan Pike", on: "2026-10-11", origin: { kind: "source", source: "SRC-1" } });
  const second = renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  expect(await screen.findByRole("button", { name: `said by Ana Person, in Jordan Pike's pasted message, ${monthDay("2026-10-11")}` })).toBeInTheDocument();
  second.unmount();
  fact({ basis: "said", kind: "calendar", on: "2026-10-12", origin: { kind: "source", source: "SRC-1" } });
  renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  expect(await screen.findByRole("button", { name: `from a calendar entry, ${monthDay("2026-10-12")}` })).toBeInTheDocument();
});

test("an inference has a dashed Inferred tag, says the assistant worked it out, and Confirm it makes it the person's own with Undo", async () => {
  const user = userEvent.setup();
  const calls = api("fact", "FACT-1", { text: "Both spines are in the folder." }, page({ kind: "fact", id: "FACT-1", name: "Both spines are in the folder.", fact_source: { basis: "inferred", kind: "email", sender: "Robin Sample", on: "2026-10-12", origin: { kind: "source", source: "SRC-1" } } }), {
    "POST records/edit": () => ({ changeset: "CS-5" }),
    "POST changesets/CS-5/undo": () => ({ restored: [0], skipped: [] }),
  });
  renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  const line = (await screen.findByText("Inferred")).closest("[data-fact-source]") as HTMLElement;
  expect(line.querySelector("[data-inferred]")).not.toBeNull();
  expect(line).toHaveTextContent(`Helper inferred this from Robin Sample's email, ${monthDay("2026-10-12")}`);
  // A screen reader hears what the tag means, not just the word.
  expect(within(line).getByText("Inferred by the assistant, not stated")).toBeInTheDocument();
  expect(getComputedStyle(line).fontStyle).not.toBe("italic");
  await user.click(within(line).getByRole("button", { name: "Confirm it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "fact", id: "FACT-1", fields: { basis: "person" }, read_version: 3 }));
  expect(await screen.findByText("Confirmed. It is now from you.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-5/undo")).toBe(true));
});

test("a fact recorded before the source was kept says only when", async () => {
  fact({ basis: null, on: "2026-09-01", origin: null });
  renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => {}} />);
  expect(await screen.findByText(`recorded ${monthDay("2026-09-01")}`)).toBeInTheDocument();
});

// A calendar entry kept from a calendar: who invited, who is asked and the person's own answer (design 7.14).

const entryFields = {
  title: "Floor plan walkthrough",
  start: "2030-03-08T15:00:00+00:00",
  invitation: true,
  response: "tentative",
  key: "invite-1#2030-03-08T15:00:00+00:00",
  organizer: { address: "robin@example.com", name: "Robin S.", person: "PER-1", response: "accepted" },
  attendees: [
    { address: "robin@example.com", name: "Robin S.", person: "PER-1", response: "accepted" },
    { address: "dara.keene@example.com", name: "Dara Keene", person: null, response: "needs-action" },
    { address: "me@example.com", name: null, person: null, response: null },
  ],
  cancelled: false,
  notes: [],
};

test("an invitation's page lists who invited, who is asked with their answers and the person's own answer", async () => {
  api("event", "EVT-1", entryFields, page({ kind: "event", id: "EVT-1", name: "Floor plan walkthrough" }), {
    "GET plugin-actions?kind=event&id=EVT-1": () => [],
  });
  renderApp(<RecordPage kind="event" id="EVT-1" onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Who is asked" });
  expect(within(section).getByText(/Invited by/)).toBeInTheDocument();
  expect(within(section).getByText("Your answer: Maybe")).toBeInTheDocument();
  const rows = within(section).getAllByRole("listitem");
  // A person the workspace knows is shown by their name there and links to their page; others by the name the calendar gave.
  expect(rows[0]).toHaveTextContent("Robin Sample · robin@example.com · Accepted");
  expect(within(rows[0]).getByRole("link", { name: "Robin Sample" })).toHaveAttribute("href", expect.stringContaining("person"));
  expect(rows[1]).toHaveTextContent("Dara Keene · dara.keene@example.com · No answer yet");
  expect(within(rows[1]).queryByRole("link")).toBeNull();
  expect(rows[2]).toHaveTextContent("me@example.com");
  // The entry's internal key and flags are not shown as details.
  const details = screen.getByRole("heading", { name: "Details" }).closest("section") as HTMLElement;
  expect(within(details).queryByText(/invite-1/)).toBeNull();
  expect(within(details).queryByText("Key")).toBeNull();
});

test("an entry with nobody on it has no list of people, and one the person organizes says organized by", async () => {
  api("event", "EVT-2", { title: "Walkthrough", start: "2030-03-08", attendees: [], organizer: null, invitation: false }, page({ kind: "event", id: "EVT-2", name: "Walkthrough" }), {
    "GET plugin-actions?kind=event&id=EVT-2": () => [],
    "GET task-kinds?kind=event&id=EVT-2": () => [],
  });
  const first = renderApp(<RecordPage kind="event" id="EVT-2" onBack={() => {}} />);
  expect(await screen.findByRole("heading", { name: "Walkthrough" })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Who is asked" })).toBeNull();
  first.unmount();
  api("event", "EVT-3", { ...entryFields, invitation: false, response: "accepted" }, page({ kind: "event", id: "EVT-3", name: "Planning hour" }), {
    "GET plugin-actions?kind=event&id=EVT-3": () => [],
    "GET task-kinds?kind=event&id=EVT-3": () => [],
  });
  renderApp(<RecordPage kind="event" id="EVT-3" onBack={() => {}} />);
  const section = await screen.findByRole("region", { name: "Who is asked" });
  expect(within(section).getByText(/Organized by/)).toBeInTheDocument();
  expect(within(section).queryByText(/Your answer/)).toBeNull();
});

const FILED = {
  by: "alias" as const,
  word: "RTE",
  project: "PRJ-1",
  project_name: "Business",
  move_to: "PRJ-2",
  move_to_name: "Personal",
  field: "project" as const,
  version: 3,
};

test("an item the assistant filed by words says why on its page, and Move to the other side edits its project with Undo", async () => {
  const user = userEvent.setup();
  const calls = api(
    "action",
    "ACT-5",
    { text: "Send the proof", project: "PRJ-1", filed_by: { by: "alias", word: "RTE", project: "PRJ-1" } },
    page({ kind: "action", id: "ACT-5", name: "Send the proof", filed: FILED }),
    { "POST records/edit": () => ({ changeset: "CS-30" }), "POST changesets/CS-30/undo": () => ({ restored: ["ACT-5"], skipped: [] }) },
  );
  renderApp(<RecordPage kind="action" id="ACT-5" onBack={() => {}} />);
  expect(await screen.findByText("Filed under Business: it names RTE")).toBeInTheDocument();
  // The stored reason is the line above, never a detail row.
  expect(screen.queryByText(/by: alias/)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Move to Personal" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "action", id: "ACT-5", fields: { project: "PRJ-2" }, read_version: 3 }));
  expect(await screen.findByText("Moved to Personal.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-30/undo")).toBe(true));
});

test("a question is moved by its list of projects, and an item nobody filed by words has no such line", async () => {
  const user = userEvent.setup();
  const calls = api("question", "Q-5", { title: "Which one?", projects: ["PRJ-1"] }, page({ kind: "question", id: "Q-5", name: "Which one?", filed: { ...FILED, by: "domain", word: "example.com", field: "projects" } }), {
    "POST records/edit": () => ({ changeset: "CS-31" }),
  });
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => {}} />);
  expect(await screen.findByText("Filed under Business: it's from example.com")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Move to Personal" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toMatchObject({ fields: { projects: ["PRJ-2"] } }));
});

test("an item with no filing reason shows no filed line", async () => {
  api("action", "ACT-6", { text: "Call", project: "PRJ-1" }, page({ kind: "action", id: "ACT-6", name: "Call" }));
  renderApp(<RecordPage kind="action" id="ACT-6" onBack={() => {}} />);
  await screen.findByRole("heading", { level: 1, name: "Call" });
  expect(screen.queryByText(/Filed under/)).toBeNull();
});
