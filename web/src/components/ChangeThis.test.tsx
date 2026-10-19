import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person } from "../lib/learned-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { FollowUps } from "./FollowUps";
import { RecordPage } from "./RecordPage";

const posted = (calls: { route: string; body: unknown }[], route: string) => calls.find((c) => c.route === route)?.body;

const question = (id: string, over: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
  id,
  title: "Which cover?",
  text: "",
  links: [],
  kind: "question",
  status: "open",
  sent: null,
  waiting_days: null,
  chase_due: false, chases: 0,
  about: null,
  options: [],
  ...over,
});

function followups(questions: S["FollowupQuestion"][]): S["FollowupSection"][] {
  return [
    {
      person: "PER-1",
      name: "Pat Example",
      is_pm: true,
      questions,
      actions: [{ id: "ACT-9", text: "Approve the proof", due: "2026-11-03", project_name: "Book", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 }],
      message: "",
      to_send: 0,
    },
  ];
}

const menuOf = async (user: ReturnType<typeof userEvent.setup>, name: RegExp | string) => {
  await user.click(await screen.findByRole("button", { name: typeof name === "string" ? `More actions for ${name}` : name }));
  return screen.getAllByRole("menuitem").map((m) => m.textContent);
};

test("Change this on an action takes a note, posts it, and says the assistant will look at it", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => followups([]),
    "GET people": () => [],
    "POST items/action/ACT-9/change": () => ({ ok: "ACT-9", request: "REQ-5", signal: "SIG-1" }),
  });
  renderApp(<FollowUps />);
  expect(await menuOf(user, "Approve the proof")).toContain("Change this");
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  const box = await screen.findByRole("textbox", { name: "Your note" });
  await waitFor(() => expect(box).toHaveFocus());
  const send = screen.getByRole("button", { name: "Ask for the change" });
  expect(send).toBeDisabled();
  await user.type(box, "Make it due on the 5th");
  await user.click(send);
  await waitFor(() => expect(posted(calls, "POST items/action/ACT-9/change")).toEqual({ note: "Make it due on the 5th" }));
  expect(await screen.findByText("Helper will look at it.")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Your note" })).toBeNull();
});

test("a note that couldn't be sent stays in its box", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => followups([]), "GET people": () => [] });
  renderApp(<FollowUps />);
  await menuOf(user, "Approve the proof");
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "Move it");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  expect(await screen.findByText(/That didn.t work/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Your note" })).toHaveValue("Move it");
});

test("a decision's menu changes the question or asks for a change, and a decision is changed as a decision", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => followups([question("Q-5", { kind: "decision" })]),
    "GET people": () => [],
    "POST items/decision/Q-5/change": () => ({ ok: "Q-5", request: null, signal: "SIG-2" }),
  });
  renderApp(<FollowUps />);
  expect(await menuOf(user, "Which cover?")).toEqual(["Reword", "Ask someone else", "Drop", "Change this"]);
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "Ask me on Friday");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  await waitFor(() => expect(posted(calls, "POST items/decision/Q-5/change")).toEqual({ note: "Ask me on Friday" }));
});

// ---- a question's own menu, on its record page ---------------------------------------------------------------------

function page(kind: string, id: string, fields: Record<string, unknown>, extra: Routes = {}): Routes {
  return {
    [`GET record?kind=${kind}&id=${id}`]: () => ({ kind, id, version: 2, fields: { id, ...fields }, long_text: [] }),
    "GET people": () => [person("PER-2", "Robin Sample"), person("PER-3", "Sam Other")],
    "GET projects": () => [],
    ...extra,
  };
}

const openQuestion = (extra: Routes = {}, status = "open") =>
  page("question", "Q-5", { title: "Which cover?", text: "Two options.", status, to: "PER-2" }, {
    "POST changesets/CS-5/undo": () => ({ restored: [1], skipped: [] }),
    ...extra,
  });

test("a question that isn't sent yet offers reword, ask someone else, drop, already sent and change", async () => {
  const user = userEvent.setup();
  fakeApi(openQuestion());
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  expect(await menuOf(user, "Which cover?")).toEqual(["Reword", "Ask someone else", "Drop", "Mark as already sent", "Change this"]);
});

test("a question already sent has no Mark as already sent", async () => {
  const user = userEvent.setup();
  fakeApi(openQuestion({}, "sent"));
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  expect(await menuOf(user, "Which cover?")).toEqual(["Reword", "Ask someone else", "Drop", "Change this"]);
});

test("Reword changes only what was changed, at once, with Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(openQuestion({ "POST questions/Q-5/reword": () => ({ changeset: "CS-5" }) }));
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  await menuOf(user, "Which cover?");
  await user.click(screen.getByRole("menuitem", { name: "Reword" }));
  const title = await screen.findByRole("textbox", { name: "Question" });
  await waitFor(() => expect(title).toHaveFocus());
  expect(screen.getByRole("button", { name: "Reword" })).toBeDisabled();
  await user.clear(title);
  await user.type(title, "Which cover do you want?");
  await user.click(screen.getByRole("button", { name: "Reword" }));
  await waitFor(() => expect(posted(calls, "POST questions/Q-5/reword")).toEqual({ title: "Which cover do you want?" }));
  expect(await screen.findByText("Reworded.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-5/undo"));
});

test("Ask someone else picks a person from a list and moves the question", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(openQuestion({ "POST questions/Q-5/reroute": () => ({ changeset: "CS-5" }) }));
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  await menuOf(user, "Which cover?");
  await user.click(screen.getByRole("menuitem", { name: "Ask someone else" }));
  const pick = await screen.findByRole("combobox", { name: "Ask instead" });
  expect(screen.getByRole("button", { name: "Ask them" })).toBeDisabled();
  await waitFor(() => expect(within(pick).getAllByRole("option").length).toBeGreaterThan(2));
  await user.selectOptions(pick, "PER-3");
  await user.click(screen.getByRole("button", { name: "Ask them" }));
  await waitFor(() => expect(posted(calls, "POST questions/Q-5/reroute")).toEqual({ to: "PER-3" }));
  expect(await screen.findByText("Asking Sam Other instead.")).toBeInTheDocument();
});

test("Drop needs a reason", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(openQuestion({ "POST questions/Q-5/drop": () => ({ changeset: "CS-5" }) }));
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  await menuOf(user, "Which cover?");
  await user.click(screen.getByRole("menuitem", { name: "Drop" }));
  const reason = await screen.findByRole("textbox", { name: "Why isn't it needed?" });
  expect(screen.getByRole("button", { name: "Drop it" })).toBeDisabled();
  await user.type(reason, "Already decided in the meeting");
  await user.click(screen.getByRole("button", { name: "Drop it" }));
  await waitFor(() => expect(posted(calls, "POST questions/Q-5/drop")).toEqual({ reason: "Already decided in the meeting" }));
  expect(await screen.findByText("Dropped.")).toBeInTheDocument();
});

test("Mark as already sent acts at once", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(openQuestion({ "POST questions/Q-5/sent": () => ({ changeset: "CS-5" }) }));
  renderApp(<RecordPage kind="question" id="Q-5" onBack={() => undefined} />);
  await menuOf(user, "Which cover?");
  await user.click(screen.getByRole("menuitem", { name: "Mark as already sent" }));
  await waitFor(() => expect(posted(calls, "POST questions/Q-5/sent")).toEqual({}));
  expect(await screen.findByText("Marked as already sent.")).toBeInTheDocument();
});

test("a fact's page has Change this, posted as a fact", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(
    page("fact", "FACT-1", { text: "The interior is due on the 16th." }, { "POST items/fact/FACT-1/change": () => ({ ok: "FACT-1", request: null, signal: "SIG-3" }) }),
  );
  renderApp(<RecordPage kind="fact" id="FACT-1" onBack={() => undefined} />);
  expect(await menuOf(user, /More actions for/)).toEqual(["Change this"]);
  await user.click(screen.getByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "It is the 18th");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  await waitFor(() => expect(posted(calls, "POST items/fact/FACT-1/change")).toEqual({ note: "It is the 18th" }));
});
