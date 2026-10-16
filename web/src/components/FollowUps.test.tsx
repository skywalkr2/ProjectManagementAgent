import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

const sections: S["FollowupSection"][] = [
  {
    person: "PER-1",
    name: "Pat Example",
    is_pm: true,
    questions: [],
    actions: [{ id: "ACT-9", text: "Approve the proof", due: "2026-11-03", project_name: "Book", told: null, told_days: null, followed_up: null, chase_due: false }],
    message: "",
    to_send: 0,
  },
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [
      { id: "Q-1", title: "Is the index final?", text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, chase_due: false, about: null, options: [] },
    ],
    actions: [{ id: "ACT-1", text: "Send the index", due: "2026-10-16", project_name: "Book", told: null, told_days: null, followed_up: null, chase_due: false }],
    message: "Hi Robin,\n\nIs the index final?\n\nAction items with you:\n- Send the index\n\nThanks!",
    to_send: 2,
  },
];

test("the PM comes first, then each person with Copy", async () => {
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />);
  const items = await screen.findAllByRole("listitem");
  expect(within(items[0]).getByRole("heading", { name: "You" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy 2" })).toBeInTheDocument();
});

const markSentRoutes = {
  "GET followups": () => sections,
  "GET people": () => [],
  "POST followups/PER-2/mark-sent": () => ({ questions: 1, actions: 1, question_ids: ["Q-1"], action_ids: ["ACT-1"] }),
  "POST followups/PER-2/unmark-sent": () => ({ ok: "PER-2" }),
};
const posts = (calls: { route: string }[]) => calls.filter((c) => c.route.startsWith("POST"));

test("Copy puts the edited message on the clipboard and changes nothing on the server", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(markSentRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  const box = screen.getByRole("textbox", { name: /Message to Robin Sample/ });
  await user.type(box, " PS");
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  expect(await navigator.clipboard.readText()).toBe(sections[1].message + " PS");
  expect(await screen.findByText("Copied")).toBeInTheDocument();
  expect(posts(calls)).toHaveLength(0);
  expect(screen.queryByText(/Marked as sent/)).toBeNull();
});

test("after copying, the card's primary and the button under the box become Mark sent", async () => {
  const user = userEvent.setup();
  fakeApi(markSentRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  await user.click(screen.getByRole("button", { name: "Copy 2" }));
  expect(await screen.findAllByRole("button", { name: "Mark sent" })).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "Copy 2" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
});

test("Mark sent records the box's text and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(markSentRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  await user.type(screen.getByRole("textbox", { name: /Message to Robin Sample/ }), " PS");
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  await user.click((await screen.findAllByRole("button", { name: "Mark sent" }))[0]);
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/mark-sent")).toBe(true));
  expect(calls.find((c) => c.route === "POST followups/PER-2/mark-sent")!.body).toEqual({ text: sections[1].message + " PS" });
  expect(await screen.findByText("Marked as sent to Robin Sample")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-2/unmark-sent")?.body).toEqual({
      question_ids: ["Q-1"],
      action_ids: ["ACT-1"],
    }),
  );
});

test("the row menu's Mark sent works without copying", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(markSentRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "More actions for Robin Sample" }));
  await user.click(await screen.findByRole("menuitem", { name: "Mark sent" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-2/mark-sent")?.body).toEqual({ text: sections[1].message }),
  );
  expect(await screen.findByText("Marked as sent to Robin Sample")).toBeInTheDocument();
});

test("when the clipboard is blocked nothing is marked and the card keeps Copy", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />);
  const button = await screen.findByRole("button", { name: "Copy 2" });
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(button);
  expect(await screen.findByText(/blocked copying/)).toBeInTheDocument();
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
  expect(screen.queryByText(/Marked as sent/)).toBeNull();
  expect(screen.queryByText("Copied")).toBeNull();
  expect(screen.queryByRole("button", { name: "Mark sent" })).toBeNull();
  expect(screen.getAllByRole("button", { name: /^Copy/ }).length).toBeGreaterThan(0);
});

test("a card lists only what is still to send, with no buttons or pills on the items", async () => {
  const user = userEvent.setup();
  const mixed = structuredClone(sections);
  mixed[1].questions.push({
    id: "Q-2", title: "Did the cover ship?", text: "", links: [], kind: "question", status: "sent", sent: "2026-10-08", waiting_days: 2, chase_due: false, about: null, options: [],
  });
  mixed[1].actions.push({ id: "ACT-2", text: "Return the proof", due: null, project_name: "Book", told: "2026-10-08", told_days: 2, followed_up: null, chase_due: false });
  mixed[1].to_send = 2;
  fakeApi({ "GET followups": () => mixed, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  const list = screen.getByRole("list", { name: "In this message" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  expect(within(list).getByText("Is the index final?")).toBeInTheDocument();
  expect(within(list).getByText(/Send the index/)).toBeInTheDocument();
  expect(within(list).queryByRole("button")).toBeNull();
  expect(screen.queryByText("Did the cover ship?")).toBeNull();
  expect(screen.queryByText("Return the proof")).toBeNull();
  expect(screen.getByRole("button", { name: /^Robin Sample/ })).toHaveTextContent("2 to send");
});

test("the workspace can rename the section", async () => {
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />, { "followups.title": "Chasers" });
  expect(await screen.findByRole("heading", { name: "Chasers" })).toBeInTheDocument();
});


function waitingSections(): S["FollowupSection"][] {
  const sent = structuredClone(sections.slice(1));
  sent[0].questions[0].status = "sent";
  sent[0].questions[0].sent = "2026-10-08";
  sent[0].questions[0].waiting_days = 2;
  sent[0].actions[0].told = "2026-10-09";
  sent[0].actions[0].told_days = 1;
  sent[0].message = "";
  sent[0].to_send = 0;
  return sent;
}

test("the default view hides what was already sent; Waiting on them shows it, one line each", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => waitingSections(), "GET people": () => [] });
  renderApp(<FollowUps />);
  expect(await screen.findByText("Nothing left to send. Anything you have sent is under Waiting on them.")).toBeInTheDocument();
  expect(screen.queryByText("Is the index final?")).toBeNull();
  expect(screen.queryByRole("button", { name: /Copy/ })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Waiting on them" }));
  const card = screen.getByRole("listitem", { name: "Robin Sample" });
  expect(within(card).getByText("2 waiting")).toBeInTheDocument();
  const rows = within(card).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent(/Is the index final\?/);
  expect(rows[0]).toHaveTextContent(/sent .* \(2 days\)/);
  expect(rows[1]).toHaveTextContent(/sent .* \(1 day\)/);
  expect(within(rows[0]).getByRole("button", { name: "Record reply" })).toBeInTheDocument();
  expect(within(rows[1]).getByRole("button", { name: "They finished it" })).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("Waiting on them has its own empty state, and the PM's decisions stay under To send", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />);
  expect(await screen.findByRole("heading", { name: "You" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Waiting on them" }));
  expect(screen.getByText(/Nobody is waiting on you to hear back/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "You" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "To send" }));
  expect(screen.getByRole("heading", { name: "You" })).toBeInTheDocument();
});

test("a waiting question takes its reply right on its line", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => waitingSections(),
    "GET people": () => [],
    "POST questions/Q-1/reply": () => ({ request: "REQ-5", source: "SRC-5" }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(screen.getByRole("button", { name: "Record reply" }));
  await user.type(screen.getByRole("textbox", { name: /Robin's reply/ }), "Yes, the index is final.");
  await user.click(screen.getByRole("button", { name: "Hand in reply" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST questions/Q-1/reply")?.body).toEqual({ text: "Yes, the index is final." }),
  );
});

const finishRoutes = {
  "POST followups/PER-2/actions/ACT-1/finished": () => ({ ok: "ACT-1" }),
  "POST actions/ACT-1/status": () => ({ ok: "ACT-1" }),
  "POST followups/PER-2/actions/ACT-1/followed-up": () => ({ on: "2026-10-13", previous_told: "2026-10-09" }),
  "POST followups/PER-2/actions/ACT-1/unfollow": () => ({ ok: "ACT-1" }),
};

function chaseSections(): S["FollowupSection"][] {
  const waiting = waitingSections();
  waiting[0].actions[0].told_days = 5;
  waiting[0].actions[0].chase_due = true;
  return waiting;
}

test("They finished it closes the action as the person's work and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waitingSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  expect(screen.queryByRole("button", { name: "Followed up" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "They finished it" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/finished")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "open" }));
});

test("once the follow-up rule says it is time, Followed up is the primary and They finished it moves to the row's menu", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => chaseSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  expect(within(row).getByRole("button", { name: "Followed up" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: "They finished it" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  expect(await screen.findByRole("menuitem", { name: "They finished it" })).toBeInTheDocument();
});

test("Followed up records the chase, says so on the row and can be undone", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => chaseSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(screen.getByRole("button", { name: "Followed up" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")).toBe(true));
  expect(calls.some((c) => c.route === "POST actions/ACT-1/status")).toBe(false);
  expect(await screen.findByText("Recorded that you followed up with Robin. It stays open.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/unfollow")?.body).toEqual({
      on: "2026-10-13",
      previous_told: "2026-10-09",
    }),
  );
});

test("a followed-up row shows when, and the menu can chase again", async () => {
  const user = userEvent.setup();
  const chased = chaseSections();
  chased[0].actions[0].followed_up = "2026-10-10";
  chased[0].actions[0].chase_due = false;
  const calls = fakeApi({ "GET followups": () => chased, "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  expect(row).toHaveTextContent(/followed up .*/);
  expect(row).not.toHaveTextContent(/sent .*\(/);
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Followed up" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")).toBe(true));
});

test("a question to the PM shows as a decision or as a question by its stored kind", async () => {
  const withQuestions = structuredClone(sections);
  const ask = (id: string, title: string, kind: string): S["FollowupQuestion"] => ({
    id,
    title,
    text: "",
    links: [],
    kind,
    status: "open",
    sent: null,
    waiting_days: null,
    chase_due: false,
    about: null,
    options: [],
  });
  withQuestions[0].questions = [ask("Q-7", "Ship the proof now?", "decision"), ask("Q-8", "Which cover do you prefer?", "question")];
  fakeApi({ "GET followups": () => withQuestions, "GET people": () => [] });
  renderApp(<FollowUps />);
  const decision = (await screen.findByText("Ship the proof now?")).closest("li")!;
  const question = screen.getByText("Which cover do you prefer?").closest("li")!;
  expect(within(decision).getByText("Decision")).toBeInTheDocument();
  expect(within(question).getByText("Question")).toBeInTheDocument();
  expect(within(question).queryByText("Decision")).toBeNull();
  expect(screen.getByText(/1 decision · 1 question/)).toBeInTheDocument();
});

test("a waiting pill says how long, and says follow up in words as well as color once it is time", async () => {
  const user = userEvent.setup();
  const waiting = waitingSections();
  waiting[0].actions[0].told_days = 3;
  waiting[0].questions[0].waiting_days = 6;
  waiting[0].questions[0].chase_due = true;
  fakeApi({ "GET followups": () => waiting, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const calm = screen.getByText("waiting 3d");
  expect(calm).toHaveClass("k-wait");
  const late = screen.getByText("waiting 6d · follow up");
  expect(late).toHaveClass("k-risk");
});

test("an action on hold shows what it waits for with its old due date in the tooltip, and is not chased", async () => {
  const user = userEvent.setup();
  const waiting = waitingSections();
  waiting[0].actions[0].told_days = 30;
  waiting[0].actions[0].on_hold = "the printer's quote";
  fakeApi({ "GET followups": () => waiting, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  const pill = within(row).getByText("On hold: the printer's quote");
  expect(pill).toHaveAttribute("title", expect.stringMatching(/^Was due .*16/));
  expect(within(row).queryByText(/waiting 30d/)).toBeNull();
  expect(within(row).queryByRole("button", { name: "Followed up" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  expect(await screen.findByRole("menuitem", { name: "Take off hold" })).toBeInTheDocument();
});

test("Put on hold asks what it waits for with the cursor in the field, acts at once and can be undone", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => waitingSections(),
    "GET people": () => [],
    "POST actions/ACT-1/hold": () => ({ ok: "ACT-1", previous: null }),
    "POST actions/ACT-1/hold/restore": () => ({ ok: "ACT-1" }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Put on hold" }));
  const field = within(row).getByRole("textbox", { name: "What is it waiting for?" });
  expect(field).toHaveFocus();
  expect(within(row).getByRole("button", { name: "Put on hold" })).toBeDisabled();
  await user.type(field, "the printer's quote");
  await user.click(within(row).getByRole("button", { name: "Put on hold" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold")?.body).toEqual({ waiting_for: "the printer's quote" }));
  expect(await screen.findByText("Put on hold, waiting for the printer's quote.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold/restore")?.body).toEqual({ hold: null }));
});

test("Drop on an action row asks why with the cursor in the field, acts at once and Undo takes it back", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => waitingSections(),
    "GET people": () => [],
    "POST actions/ACT-1/drop": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop" }));
  const field = within(row).getByRole("textbox", { name: "Why isn't it needed?" });
  expect(field).toHaveFocus();
  expect(within(row).getByRole("button", { name: "Drop it" })).toBeDisabled();
  await user.type(field, "The printer did it already");
  await user.click(within(row).getByRole("button", { name: "Drop it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/drop")?.body).toEqual({ reason: "The printer did it already" }));
  expect(await screen.findByText("Dropped.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("Escape closes the Drop form and sends nothing", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "More actions for Approve the proof" }));
  await user.click(await screen.findByRole("menuitem", { name: "Drop" }));
  const field = await screen.findByRole("textbox", { name: "Why isn't it needed?" });
  await user.type(field, "x{Escape}");
  expect(screen.queryByRole("textbox", { name: "Why isn't it needed?" })).toBeNull();
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("Take off hold acts at once and Undo puts the old hold back", async () => {
  const user = userEvent.setup();
  const held = waitingSections();
  held[0].actions[0].on_hold = "the printer's quote";
  const previous = { waiting_for: "the printer's quote", since: "2026-10-10" };
  const calls = fakeApi({
    "GET followups": () => held,
    "GET people": () => [],
    "POST actions/ACT-1/unhold": () => ({ ok: "ACT-1", previous }),
    "POST actions/ACT-1/hold/restore": () => ({ ok: "ACT-1" }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  await user.click(await screen.findByRole("menuitem", { name: "Take off hold" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST actions/ACT-1/unhold")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold/restore")?.body).toEqual({ hold: previous }));
});

// ---- the table view (design 7.5) ----------------------------------------------------------------------------------------

const tableSections: S["FollowupSection"][] = [
  sections[0],
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [
      { id: "Q-1", title: "Is the index final?", text: "", links: [{ label: "Book page", url: `${WEB}example.com/book` }], kind: "question", status: "open", project_name: "Book", sent: null, waiting_days: null, chase_due: false, about: null, options: [] },
      { id: "Q-2", title: "Who writes the jacket copy?", text: "", links: [], kind: "question", status: "open", project_name: "Book", sent: "2026-10-10", waiting_days: null, chase_due: false, about: null, options: [] },
    ],
    actions: [
      { id: "ACT-2", text: "Send the acknowledgments page", due: "2099-10-23", project_name: "Book", links: [], told: null, told_days: null, followed_up: null, chase_due: false },
      { id: "ACT-1", text: "Send the index", due: "2020-10-14", project_name: "Book", links: [{ label: "Book page", url: `${WEB}example.com/book` }], told: null, told_days: null, followed_up: null, chase_due: false },
    ],
    message: "Hi Robin",
    to_send: 4,
  },
] as S["FollowupSection"][];

const tableRoutes = { ...markSentRoutes, "GET followups": () => tableSections };

async function showTable(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  await user.click(screen.getByRole("radio", { name: "Table" }));
}

test("a person's group has a Message | Table switch, and the message is what shows first", async () => {
  const user = userEvent.setup();
  fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  const switcher = screen.getByRole("radiogroup", { name: "Show as" });
  expect(within(switcher).getAllByRole("radio").map((b) => b.textContent)).toEqual(["Message", "Table"]);
  expect(within(switcher).getByRole("radio", { name: "Message" })).toBeChecked();
  expect(screen.getByRole("textbox", { name: /Message to Robin Sample/ })).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});

test("the table is on screen before anything is copied: actions by due date with overdue first, questions by first asked", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await showTable(user);
  const [actions, questions] = screen.getAllByRole("table");
  expect(within(actions).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Project", "Action", "Due", "Link", "Your update"]);
  expect(within(questions).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Project", "Question", "First asked", "Link", "Your answer"]);
  const bodyRows = (table: HTMLElement) => within(table).getAllByRole("row").slice(1);
  const a = bodyRows(actions).map((r) => within(r).getAllByRole("cell").map((c) => c.textContent));
  expect(a.map((r) => r[1])).toEqual(["Send the index", "Send the acknowledgments page"]);
  // The project is on every row; overdue is said in words; no link is a dash; the fill-in column is empty.
  expect(a.map((r) => r[0])).toEqual(["Book", "Book"]);
  expect(a[0][2]).toMatch(/ · overdue$/);
  expect(a[1][2]).not.toMatch(/overdue/);
  expect(a[0][3]).toContain("Book page");
  expect(a[1][3]).toBe("—");
  expect(a.map((r) => r[4])).toEqual(["", ""]);
  const q = bodyRows(questions).map((r) => within(r).getAllByRole("cell").map((c) => c.textContent));
  expect(q.map((r) => r[1])).toEqual(["Who writes the jacket copy?", "Is the index final?"]);
  expect(q[0][2]).toMatch(/Oct 10/);
  expect(q[1][2]).toBe("Not sent yet");
  expect(q.map((r) => r[4])).toEqual(["", ""]);
  // Nothing has been copied, and no AI run or other request was made for it.
  expect(await navigator.clipboard.readText()).toBe("");
  expect(posts(calls)).toHaveLength(0);
});

test("the fill-in column is the last one, and a table switch back to the message keeps the message", async () => {
  const user = userEvent.setup();
  fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await showTable(user);
  for (const table of screen.getAllByRole("table")) {
    const headers = within(table).getAllByRole("columnheader");
    expect(headers[headers.length - 1].textContent).toMatch(/^Your (update|answer)$/);
  }
  await user.click(screen.getByRole("radio", { name: "Message" }));
  expect(screen.getByRole("textbox", { name: /Message to Robin Sample/ })).toHaveValue("Hi Robin");
});

/** The browser's rich clipboard item, which the test browser lacks. */
class FakeClipboardItem {
  constructor(private data: Record<string, Blob>) {}
  get types() {
    return Object.keys(this.data);
  }
  async getType(type: string) {
    return this.data[type];
  }
}

test("Copy as table puts an HTML table on the clipboard and Copy for a spreadsheet puts tab-separated cells with full addresses", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await showTable(user);
  await user.click(screen.getByRole("button", { name: "Copy for a spreadsheet" }));
  const sheet = await navigator.clipboard.readText();
  expect(sheet.split("\n")[0]).toBe("Project\tAction\tDue\tLink\tYour update");
  expect(sheet).toContain("Send the index");
  expect(sheet).toContain(`${WEB}example.com/book`);
  expect(sheet).not.toContain("Book page");
  expect(await screen.findByText("Copied for a spreadsheet.")).toBeInTheDocument();
  // The rich copy needs the browser's clipboard item, which the test browser lacks.
  vi.stubGlobal("ClipboardItem", FakeClipboardItem);
  const written: FakeClipboardItem[] = [];
  Object.defineProperty(navigator.clipboard, "write", { configurable: true, value: async (items: FakeClipboardItem[]) => void written.push(...items) });
  await user.click(screen.getByRole("button", { name: "Copy as table" }));
  await waitFor(() => expect(written).toHaveLength(1));
  const textOf = (blob: Blob) =>
    new Promise<string>((done) => {
      const reader = new FileReader();
      reader.onload = () => done(String(reader.result));
      reader.readAsText(blob);
    });
  const html = await textOf(await written[0].getType("text/html"));
  expect(html).toContain("<table");
  expect(html).toContain(`<a href="${WEB}example.com/book">Book page</a>`);
  expect(html).not.toContain("<caption");
  expect(await textOf(await written[0].getType("text/plain"))).toBe(sheet);
  expect(await screen.findByText("Copied as a table.")).toBeInTheDocument();
  expect(posts(calls)).toHaveLength(0);
});

test("when the browser can't copy a table the person is told, and nothing is marked sent", async () => {
  vi.stubGlobal("ClipboardItem", undefined);
  const user = userEvent.setup();
  const calls = fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await showTable(user);
  await user.click(screen.getByRole("button", { name: "Copy as table" }));
  expect(await screen.findByText(/Your browser blocked copying/)).toBeInTheDocument();
  // The table is selected, so the toast is true: it can be copied by hand.
  expect(window.getSelection()?.toString()).toContain("Send the index");
  expect(posts(calls)).toHaveLength(0);
});

test("the two copy buttons are named for where the table goes, with one hint, and Mark sent sits beside them", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(tableRoutes);
  renderApp(<FollowUps />);
  await showTable(user);
  const buttons = screen.getAllByRole("button").map((b) => b.textContent);
  const at = buttons.indexOf("Copy as table");
  expect(buttons.slice(at, at + 3)).toEqual(["Copy as table", "Copy for a spreadsheet", "Mark sent"]);
  expect(screen.getByText(/For a spreadsheet.*copies tab-separated cells with full web addresses/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Copy as table" }));
  await user.click(screen.getAllByRole("button", { name: "Mark sent" })[0]);
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/mark-sent")).toBe(true));
  expect(await screen.findByText("Marked as sent to Robin Sample")).toBeInTheDocument();
});
