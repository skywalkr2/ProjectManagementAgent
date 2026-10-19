// The note box on the action buttons: each button still acts at once; its menu's "Add a note" opens a box that sends
// the note on the same route. No note sends none.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AskChooser } from "./AskChooser";
import { FollowUps } from "./FollowUps";

const NOTE = "The printer moved the proof to Friday.";

const action = (over: Partial<S["FollowupAction"]> = {}): S["FollowupAction"] => ({
  id: "ACT-1",
  text: "Send the index",
  due: null,
  project_name: "Book",
  told: null,
  told_days: null,
  followed_up: null,
  chase_due: false, chases: 0,
  ...over,
});

const section = (over: Partial<S["FollowupSection"]>): S["FollowupSection"] => ({
  person: "PER-1",
  name: "Pat Example",
  is_pm: true,
  questions: [],
  actions: [],
  message: "",
  to_send: 0,
  ...over,
});

const mine = [section({ actions: [action({ id: "ACT-9", text: "Approve the proof" })] })];

/** One person's action that was sent and is now waiting on them. */
const waiting = (over: Partial<S["FollowupAction"]> = {}) => [
  section({
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    actions: [action({ told: "2026-10-09", told_days: 1, ...over })],
  }),
];

const routes = {
  "GET people": () => [],
  "POST actions/ACT-9/status": () => ({ ok: "ACT-9", request: "REQ-7" }),
  "POST followups/PER-2/actions/ACT-1/finished": () => ({ ok: "ACT-1", request: "REQ-8" }),
  "POST followups/PER-2/actions/ACT-1/followed-up": () => ({ on: "2026-10-13", previous_told: null, request: "REQ-8" }),
};

async function openNote(user: ReturnType<typeof userEvent.setup>, rowName: string) {
  await user.click(await screen.findByRole("button", { name: `More actions for ${rowName}` }));
  await user.click(await screen.findByRole("menuitem", { name: "Add a note" }));
  return screen.findByRole("textbox", { name: "Your note" });
}

test("Mark done: the note box takes the cursor, and Enter sends the note with the act", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => mine, ...routes });
  renderApp(<FollowUps />);
  const box = await openNote(user, "Approve the proof");
  expect(box).toHaveFocus();
  await user.type(box, NOTE);
  await user.keyboard("{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-9/status")?.body).toEqual({ status: "done", note: NOTE }));
  expect(await screen.findByText("Marked done. Helper will read your note.")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Your note" })).toBeNull();
});

test("Mark done with no note sends none and says nothing about reading one", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => mine, ...routes, "POST actions/ACT-9/status": () => ({ ok: "ACT-9", request: null }) });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Mark done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-9/status")?.body).toEqual({ status: "done" }));
  expect(await screen.findByText("Marked done.")).toBeInTheDocument();
  expect(screen.queryByText(/will read your note/)).toBeNull();
});

test("Escape closes the box without acting, and Enter in an empty box sends nothing", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => mine, ...routes });
  renderApp(<FollowUps />);
  const box = await openNote(user, "Approve the proof");
  await user.keyboard("{Enter}");
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
  await user.type(box, "Half a thought");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("textbox", { name: "Your note" })).toBeNull();
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("a note that could not be sent stays in the box", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => mine, ...routes, "POST actions/ACT-9/status": () => new Refuse(409, "this action needs an owner first") });
  renderApp(<FollowUps />);
  const box = await openNote(user, "Approve the proof");
  await user.type(box, NOTE);
  await user.keyboard("{Enter}");
  expect(await screen.findByText(/needs an owner first/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Your note" })).toHaveValue(NOTE);
});

test("Mark their work done takes a note, and the plain button sends none", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waiting(), ...routes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const box = await openNote(user, "Send the index");
  expect(box).toHaveFocus();
  await user.type(box, NOTE);
  await user.keyboard("{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/finished")?.body).toEqual({ note: NOTE }));
  expect(await screen.findByText("Marked done for Robin. Helper will read your note.")).toBeInTheDocument();
});

test("Mark their work done with no note sends no body", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waiting(), ...routes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Mark their work done" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/finished")).toBe(true));
  expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/finished")!.body).toBeUndefined();
});

test("Followed up takes a note: the box offers both acts, the row's main one first", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waiting({ told_days: 5, chase_due: true, chases: 0 }), ...routes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const box = await openNote(user, "Send the index");
  const form = box.closest("form") as HTMLElement;
  expect(within(form).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cancel", "Followed up", "Mark their work done"]);
  await user.type(box, NOTE);
  await user.keyboard("{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")?.body).toEqual({ note: NOTE }));
  expect(await screen.findByText(/Recorded your follow-up with Robin. It stays open. Helper will read your note./)).toBeInTheDocument();
});

test("Followed up with no note sends no body", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waiting({ told_days: 5, chase_due: true, chases: 0 }), ...routes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Followed up" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")).toBe(true));
  expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")!.body).toBeUndefined();
});

describe("adding an action waiting for an owner to the nearest one", () => {
  const near = { person: null, person_name: null, entry: null, why: null, fold_into: "ACT-5", fold_into_text: "Confirm the printer slot", fold_version: 4 };
  const ask = { id: "Q-7", about: "owner", name: null, options: [], suggestion: near };
  const routes = {
    "GET people": () => [{ id: "PER-2", name: "Robin Sample", role: null }],
    "POST changesets/CS-1/ops/0/fold": () => ({ changeset: "CS-2" }),
    "POST changesets/CS-2/undo": () => ({ restored: [0], skipped: [] }),
  };

  test("Add to the nearest action sends the version read, says where it went and Undo takes it back", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes);
    renderApp(<AskChooser ask={ask} fold={{ changeset: "CS-1", index: 0 }} />);
    expect(await screen.findByRole("button", { name: "Add the to-do" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to “Confirm the printer slot”" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST changesets/CS-1/ops/0/fold")?.body).toEqual({ into: "ACT-5", read_version: 4 }));
    expect(await screen.findByText("Added to Confirm the printer slot.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-2/undo")).toBe(true));
  });

  test("nothing is offered without a near action", async () => {
    fakeApi(routes);
    renderApp(<AskChooser ask={{ ...ask, suggestion: { ...near, fold_into: null, fold_into_text: null, fold_version: null } }} fold={{ changeset: "CS-1", index: 0 }} />);
    expect(await screen.findByRole("button", { name: "Add the to-do" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Add to / })).toBeNull();
  });

  test("nothing is offered where the change isn't known", async () => {
    fakeApi(routes);
    renderApp(<AskChooser ask={ask} />);
    expect(await screen.findByRole("button", { name: "Add the to-do" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Add to / })).toBeNull();
  });
});

describe("picking an owner", () => {
  const ask = { id: "Q-7", about: "owner", name: null, options: [{ id: "PER-2", name: "Robin Sample" }] };
  const people = () => [{ id: "PER-2", name: "Robin Sample", role: null }];

  test("the note goes with the pick on the same route", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({ "GET people": people, "POST questions/Q-7/answer": () => ({ ok: "Q-7", request: "REQ-3" }) });
    renderApp(<AskChooser ask={ask} />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "Who owns this?" }), "PER-2");
    await user.click(screen.getByRole("button", { name: "More actions for Who owns this?" }));
    await user.click(await screen.findByRole("menuitem", { name: "Add a note" }));
    const box = await screen.findByRole("textbox", { name: "Your note" });
    expect(box).toHaveFocus();
    await user.type(box, NOTE);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-7/answer")?.body).toEqual({ person: "PER-2", text: NOTE }));
    expect(await screen.findByText("Added with Robin Sample as the owner. Helper will read your note.")).toBeInTheDocument();
  });

  test("with no note the pick is sent as it always was", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({ "GET people": people, "POST questions/Q-7/answer": () => ({ ok: "Q-7", request: null }) });
    renderApp(<AskChooser ask={ask} />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "Who owns this?" }), "PER-2");
    await user.click(screen.getByRole("button", { name: "Add the to-do" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-7/answer")?.body).toEqual({ person: "PER-2" }));
  });
});
