import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { OpenItems } from "./OpenItems";

const WEB = "https" + "://";

const action = (id: string, text: string, over: Partial<S["OpenActionView"]> = {}): S["OpenActionView"] => ({
  id,
  version: 3,
  text,
  state: "open",
  owners: [{ person: "P-1", name: "Quinn Sample" }],
  due: null,
  project: "PRJ-1",
  project_name: "Harbor",
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

const question = (id: string, title: string, over: Partial<S["OpenQuestionView"]> = {}): S["OpenQuestionView"] => ({
  id,
  version: 2,
  title,
  text: "",
  kind: "question",
  state: "waiting",
  to: "P-2",
  to_name: "Robin Sample",
  project_name: "Harbor",
  projects: ["PRJ-1"],
  since: "2026-10-08",
  waiting_days: 6,
  chases: 0,
  held_until: null,
  origin: null,
  ...over,
});

const actions = [
  action("A-1", "Send the proof to the printer", {
    due: "2026-10-12",
    state: "overdue",
    parent_name: "Upper Shelf",
    notes: "Ask about the paper too",
    origin: { kind: "link", url: `${WEB}docs.example.com/plan`, source: "S-1" },
  }),
  action("A-2", "Order the sample copies", { owners: [{ person: "P-2", name: "Robin Sample" }], project: "PRJ-2", project_name: "Lighthouse", due: "2026-10-30" }),
  action("A-3", "Tidy the style sheet", { state: "stale", untouched_days: 30 }),
  action("A-4", "Book the room", { owners: [], state: "no_owner", owner_question: "Q-9" }),
  action("A-5", "Wait for the printer's quote", { state: "on_hold", on_hold: "the printer's quote" }),
];
const questions = [
  question("Q-1", "Is the acknowledgments page final?"),
  question("Q-2", "Which cover finish?", { state: "yours", to: "P-1", to_name: "Quinn Sample", waiting_days: null, since: "2026-10-10" }),
];

function api(extra: Routes = {}, shown: { actions?: S["OpenActionView"][]; questions?: S["OpenQuestionView"][] } = {}) {
  return fakeApi({
    "GET open-items": () => ({ actions: shown.actions ?? actions, questions: shown.questions ?? questions, stale_days: 21 }),
    "GET people": () => [person("P-1", "Quinn Sample"), person("P-2", "Robin Sample"), person("P-3", "Sam Twin")],
    "GET projects": () => [project("PRJ-1", "Harbor"), project("PRJ-2", "Lighthouse")],
    "POST actions/A-1/status": () => ({ ok: "A-1", request: null }),
    "POST records/edit": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
}

async function rows() {
  const list = await screen.findByRole("list", { name: "Open to-dos" });
  return within(list).getAllByRole("listitem");
}

test("every open to-do is a row with its owners, due date, project and the project it is part of, and where it came from", async () => {
  api();
  renderApp(<OpenItems />);
  const all = await rows();
  expect(all).toHaveLength(5);
  const first = all[0];
  expect(first).toHaveTextContent("Send the proof to the printer");
  expect(first).toHaveTextContent("Quinn Sample");
  expect(first).toHaveTextContent("Oct 12");
  expect(first).toHaveTextContent("Harbor");
  expect(first).toHaveTextContent("Upper Shelf");
  expect(within(first).getByRole("link", { name: "Where it came from" })).toHaveAttribute("href", `${WEB}docs.example.com/plan`);
  expect(within(first).getByText("Overdue")).toBeInTheDocument();
  expect(all[2]).toHaveTextContent("Not touched for 30 days");
  expect(all[3]).toHaveTextContent("Nobody yet");
  expect(all[4]).toHaveTextContent("On hold: the printer's quote");
});

test("a to-do whose owner hasn't been told says to send, and the others don't", async () => {
  api({}, { actions: [action("A-1", "Send the proof", { to_send: true }), action("A-2", "Review it", { to_send: false })] });
  renderApp(<OpenItems />);
  const [first, second] = await rows();
  expect(within(first).getByText("To send")).toBeInTheDocument();
  expect(within(second).queryByText("To send")).toBeNull();
});

test("a row's notes are on hover and read by a screen reader too", async () => {
  api();
  renderApp(<OpenItems />);
  const [first, second] = await rows();
  const title = within(first).getByText("Send the proof to the printer");
  expect(title.closest("[title]")).toHaveAttribute("title", "Ask about the paper too");
  const described = title.closest("[aria-describedby]")!.getAttribute("aria-describedby")!;
  expect(document.getElementById(described)).toHaveTextContent("Ask about the paper too");
  expect(second.querySelector("[title]")).toBeNull();
});

test("the questions are another list: who each waits on and since when", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: /Questions/ }));
  const list = await screen.findByRole("list", { name: "Open questions" });
  const [waiting, yours] = within(list).getAllByRole("listitem");
  expect(waiting).toHaveTextContent("Is the acknowledgments page final?");
  expect(waiting).toHaveTextContent("Waiting on Robin Sample");
  expect(waiting).toHaveTextContent("since Oct 8");
  expect(waiting).toHaveTextContent("6 days");
  expect(yours).toHaveTextContent("Waiting on you");
  expect(yours).toHaveTextContent("since Oct 10");
});

test("project, person and state each narrow the list, from lists to pick from", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  await rows();
  const project = screen.getByRole("combobox", { name: "Project" });
  expect(within(project).getAllByRole("option").map((o) => o.textContent)).toEqual(["All projects", "Harbor", "Lighthouse"]);
  await user.selectOptions(project, "PRJ-2");
  expect(await rows()).toHaveLength(1);
  expect((await rows())[0]).toHaveTextContent("Order the sample copies");
  await user.selectOptions(project, "");
  const who = screen.getByRole("combobox", { name: "Person" });
  expect(within(who).getAllByRole("option").map((o) => o.textContent)).toEqual(["Everyone", "Quinn Sample", "Robin Sample"]);
  await user.selectOptions(who, "P-1");
  expect((await rows()).map((r) => r.textContent).join(" ")).not.toContain("Order the sample copies");
  expect(await rows()).toHaveLength(3);
  await user.selectOptions(who, "");
  await user.selectOptions(screen.getByRole("combobox", { name: "State" }), "stale");
  expect(await rows()).toHaveLength(1);
  expect((await rows())[0]).toHaveTextContent("Tidy the style sheet");
});

test("the state list for questions is its own", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: /Questions/ }));
  const state = await screen.findByRole("combobox", { name: "State" });
  expect(within(state).getAllByRole("option").map((o) => o.textContent)).toEqual(["Any state", "Waiting on you", "Waiting on them", "Not sent yet", "For later"]);
  await user.selectOptions(state, "yours");
  const list = await screen.findByRole("list", { name: "Open questions" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(1);
});

test("Mark done acts at once, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  const [first] = await rows();
  await user.click(within(first).getByRole("button", { name: "Mark done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-1/status")?.body).toEqual({ status: "done" }));
  expect(await screen.findByText("Marked done.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST actions/A-1/status").pop()?.body).toEqual({ status: "open" }));
});

test("a note typed on Mark done reaches the assistant with the act", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST actions/A-1/status": () => ({ ok: "A-1", request: "R-1" }) });
  renderApp(<OpenItems />);
  const [first] = await rows();
  await user.click(within(first).getByRole("button", { name: /More actions for Send the proof/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Add a note" }));
  const box = await screen.findByRole("textbox", { name: /note/i });
  await waitFor(() => expect(box).toHaveFocus());
  await user.type(box, "Done, the printer has it{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-1/status")?.body).toEqual({ status: "done", note: "Done, the printer has it" }));
});

test("Reassign picks a person from a list and changes the owner, with Undo", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  const [first] = await rows();
  await user.click(within(first).getByRole("button", { name: /More actions for Send the proof/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Reassign…" }));
  const picker = await screen.findByRole("combobox", { name: "Reassign to" });
  await waitFor(() => expect(picker).toHaveFocus());
  await user.selectOptions(picker, "P-3");
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({
      kind: "action",
      id: "A-1",
      read_version: 3,
      fields: { owners: [{ person: "P-3" }] },
    }),
  );
  expect(await screen.findByText("Reassigned to Sam Twin.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("on a shared to-do, Reassign changes one owner and leaves the rest", async () => {
  const user = userEvent.setup();
  const shared = action("A-7", "Agree on the back-cover copy", {
    owners: [
      { person: "P-1", name: "Quinn Sample" },
      { person: "P-2", name: "Robin Sample" },
    ],
  });
  const calls = api({}, { actions: [shared] });
  renderApp(<OpenItems />);
  const [row] = await rows();
  await user.click(within(row).getByRole("button", { name: /More actions for Agree on the back-cover copy/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Reassign…" }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "Whose part" }), "P-2");
  await user.selectOptions(await screen.findByRole("combobox", { name: "Reassign to" }), "P-3");
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toMatchObject({ fields: { owners: [{ person: "P-1" }, { person: "P-3" }] } }));
});

test("Edit changes the words and the due date from the row, sending only what changed", async () => {
  const user = userEvent.setup();
  const calls = api();
  renderApp(<OpenItems />);
  const [first] = await rows();
  await user.click(within(first).getByRole("button", { name: /More actions for Send the proof/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit…" }));
  const text = await screen.findByRole("textbox", { name: "What to do" });
  await waitFor(() => expect(text).toHaveFocus());
  await user.clear(text);
  await user.type(text, "Send the corrected proof to the printer");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({
      kind: "action",
      id: "A-1",
      read_version: 3,
      fields: { text: "Send the corrected proof to the printer" },
    }),
  );
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
});

test("a to-do that nearly repeats another offers Merge with it, at once and with one Undo; one that doesn't offers nothing", async () => {
  const user = userEvent.setup();
  const twin = action("A-8", "Order the sample copies today", {
    duplicate: { id: "A-9", text: "Order the sample copies for the reviewers", version: 4 },
  });
  const calls = api({ "POST actions/A-8/merge": () => ({ changeset: "CS-1" }) }, { actions: [twin, actions[1]] });
  renderApp(<OpenItems />);
  const [row, other] = await rows();
  await user.click(within(other).getByRole("button", { name: /More actions for Order the sample copies$/ }));
  expect(screen.queryByRole("menuitem", { name: /Merge with/ })).toBeNull();
  await user.keyboard("{Escape}");
  await user.click(within(row).getByRole("button", { name: /More actions for Order the sample copies today/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Merge with “Order the sample copies for the reviewers”" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/A-8/merge")?.body).toEqual({ other: "A-9", read_version: 3, other_version: 4 }));
  expect(await screen.findByText("Merged: “Order the sample copies for the reviewers” is closed.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("a to-do with no owner asks who, in the row", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST questions/Q-9/answer": () => ({ ok: "Q-9", request: null }) });
  renderApp(<OpenItems />);
  const row = (await rows())[3];
  await user.click(within(row).getByRole("button", { name: "Pick an owner" }));
  await user.selectOptions(await within(row).findByRole("combobox"), "P-2");
  await user.click(within(row).getByRole("button", { name: "Add the to-do" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-9/answer")?.body).toEqual({ person: "P-2" }));
});

test("a question can be answered, reworded, asked of someone else or dropped from its row", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<OpenItems />);
  await user.click(await screen.findByRole("button", { name: /Questions/ }));
  const [waiting] = within(await screen.findByRole("list", { name: "Open questions" })).getAllByRole("listitem");
  await user.click(within(waiting).getByRole("button", { name: /More actions for Is the acknowledgments page final/ }));
  const names = (await screen.findAllByRole("menuitem")).map((m) => m.textContent);
  expect(names).toEqual(expect.arrayContaining(["Reword", "Ask someone else", "Drop"]));
});

test("with nothing open the screen says so, and a failed load offers to try again", async () => {
  api({}, { actions: [], questions: [] });
  renderApp(<OpenItems />);
  expect(await screen.findByText("Nothing is open. To-dos and questions appear here as they are made.")).toBeInTheDocument();
});

test("reassigning keeps the team the owner acted for", async () => {
  const user = userEvent.setup();
  const teamed = action("A-6", "Print the proofs", { owners: [{ person: "P-1", name: "Quinn Sample (Print)", team: "T-1" }] });
  const calls = api({}, { actions: [teamed] });
  renderApp(<OpenItems />);
  const [row] = await rows();
  await user.click(within(row).getByRole("button", { name: /More actions for Print the proofs/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Reassign…" }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "Reassign to" }), "P-3");
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toMatchObject({ fields: { owners: [{ person: "P-3", team: "T-1" }] } }));
});
