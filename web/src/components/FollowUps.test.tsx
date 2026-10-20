import { act, screen, waitFor, within } from "@testing-library/react";
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
    actions: [{ id: "ACT-9", text: "Approve the proof", due: "2026-11-03", project_name: "Book", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 }],
    message: "",
    to_send: 0,
  },
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [
      { id: "Q-1", title: "Is the index final?", text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, chase_due: false, chases: 0, about: null, options: [] },
    ],
    actions: [{ id: "ACT-1", text: "Send the index", due: "2026-10-16", project_name: "Book", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 }],
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

test("a message that still names the assistant shows why it is held back and cannot be copied", async () => {
  const user = userEvent.setup();
  const reason = "Held back: the message to Robin Sample names Helper. Take the name out before this goes to anyone.";
  const held = [sections[0], { ...sections[1], message: "", withheld: reason }];
  const calls = fakeApi({ ...markSentRoutes, "GET followups": () => held });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(reason);
  expect(screen.getByRole("button", { name: "Copy message" })).toBeDisabled();
  expect(posts(calls)).toHaveLength(0);
});

afterEach(() => {
  // A test that gave the browser a rich clipboard takes it away again.
  vi.unstubAllGlobals();
  if (navigator.clipboard) Reflect.deleteProperty(navigator.clipboard, "write");
});

/** What a rich copy put on the clipboard, as text by kind. */
async function richCopies(): Promise<Record<string, string>[]> {
  const text = (blob: Blob) =>
    new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blob);
    });
  const written: FakeClipboardItem[] = [];
  vi.stubGlobal("ClipboardItem", FakeClipboardItem);
  Object.defineProperty(navigator.clipboard, "write", { configurable: true, value: async (items: FakeClipboardItem[]) => void written.push(...items) });
  return new Proxy([] as Record<string, string>[], {
    get: (_, key) => (key === "read" ? async () => Promise.all(written.map(async (item) => Object.fromEntries(await Promise.all(item.types.map(async (type) => [type, await text(await item.getType(type))]))))) : undefined),
  });
}

test("Copy puts the message on the clipboard formatted and plain together, and what is pasted is the text in the box", async () => {
  const user = userEvent.setup();
  fakeApi(markSentRoutes);
  const rich = (await richCopies()) as unknown as { read: () => Promise<Record<string, string>[]> };
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  const box = screen.getByRole("textbox", { name: /Message to Robin Sample/ });
  await user.type(box, " <b>PS</b>");
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  const [item] = await rich.read();
  expect(item["text/plain"]).toBe(sections[1].message + " <b>PS</b>");
  expect(item["text/html"]).toContain("<p>Hi Robin,</p>");
  expect(item["text/html"]).toContain("Thanks! &lt;b&gt;PS&lt;/b&gt;</p>");
  expect(item["text/html"]).not.toContain("<b>");
});

test("the menu's Copy as plain text puts only the plain text on the clipboard, and then the card offers Mark sent", async () => {
  const user = userEvent.setup();
  fakeApi(markSentRoutes);
  const rich = (await richCopies()) as unknown as { read: () => Promise<Record<string, string>[]> };
  const plain = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  await user.click(screen.getByRole("button", { name: "More actions for Robin Sample" }));
  await user.click(await screen.findByRole("menuitem", { name: "Copy as plain text" }));
  await waitFor(() => expect(plain).toHaveBeenCalledWith(sections[1].message));
  expect(await rich.read()).toHaveLength(0);
  expect(await screen.findByText("Copied as plain text")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Mark sent" }).length).toBeGreaterThan(0);
});

test("the person's own to-do can be handed to the assistant from its row's menu", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ ...markSentRoutes, "POST actions/ACT-9/hand-over": () => ({ request: "R-1" }) });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "More actions for Approve the proof" }));
  await user.click(await screen.findByRole("menuitem", { name: "Hand to the assistant" }));
  await user.click(await screen.findByRole("button", { name: "Hand it over" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST actions/ACT-9/hand-over")).toBe(true));
});

test("Copy on a closed card opens the message first and copies nothing, with the cursor in the message", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(markSentRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Copy 2" }));
  const box = await screen.findByRole("textbox", { name: /Message to Robin Sample/ });
  expect(box).toHaveValue(sections[1].message);
  await waitFor(() => expect(box).toHaveFocus());
  expect(await navigator.clipboard.readText()).toBe("");
  expect(screen.queryByText("Copied")).toBeNull();
  expect(posts(calls)).toHaveLength(0);
  // Only the message on screen is copied, and then the card offers Mark sent.
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  expect(await navigator.clipboard.readText()).toBe(sections[1].message);
  expect(await screen.findByText("Copied")).toBeInTheDocument();
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
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(screen.getByRole("button", { name: "Copy message" }));
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
    id: "Q-2", title: "Did the cover ship?", text: "", links: [], kind: "question", status: "sent", sent: "2026-10-08", waiting_days: 2, chase_due: false, chases: 0, about: null, options: [],
  });
  mixed[1].actions.push({ id: "ACT-2", text: "Return the proof", due: null, project_name: "Book", told: "2026-10-08", told_days: 2, followed_up: null, chase_due: false, chases: 0 });
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
  expect(await screen.findByText("Nothing left to send. Sent messages are under Waiting on them.")).toBeInTheDocument();
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
  expect(within(rows[1]).getByRole("button", { name: "Mark their work done" })).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("Waiting on them has its own empty state, and the PM's decisions stay under To send", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />);
  expect(await screen.findByRole("heading", { name: "You" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Waiting on them" }));
  expect(screen.getByText(/You're not waiting for any replies/)).toBeInTheDocument();
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
  await user.click(screen.getByRole("button", { name: "Add reply" }));
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

test("Mark their work done closes the action as the person's work and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => waitingSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  expect(screen.queryByRole("button", { name: "Followed up" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Mark their work done" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/finished")).toBe(true));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "open" }));
});

test("once the follow-up rule says it is time, Followed up is the primary and Mark their work done moves to the row's menu", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => chaseSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  const row = screen.getByText("Send the index").closest("li") as HTMLElement;
  expect(within(row).getByRole("button", { name: "Followed up" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: "Mark their work done" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "More actions for Send the index" }));
  expect(await screen.findByRole("menuitem", { name: "Mark their work done" })).toBeInTheDocument();
});

test("Followed up records the chase, says so on the row and can be undone", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET followups": () => chaseSections(), "GET people": () => [], ...finishRoutes });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(screen.getByRole("button", { name: "Followed up" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")).toBe(true));
  expect(calls.some((c) => c.route === "POST actions/ACT-1/status")).toBe(false);
  expect(await screen.findByText("Recorded your follow-up with Robin. It stays open.")).toBeInTheDocument();
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
    chase_due: false, chases: 0,
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
  const calm = screen.getByText("waiting 3 days");
  expect(calm).toHaveClass("k-wait");
  const late = screen.getByText("waiting 6 days · follow up");
  expect(late).toHaveClass("k-risk");
});

test("one day of waiting is singular, in the pill and with follow up", async () => {
  const user = userEvent.setup();
  const waiting = waitingSections();
  waiting[0].actions[0].told_days = 1;
  waiting[0].questions[0].waiting_days = 1;
  waiting[0].questions[0].chase_due = true;
  fakeApi({ "GET followups": () => waiting, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  expect(screen.getByText("waiting 1 day")).toHaveClass("k-wait");
  expect(screen.getByText("waiting 1 day · follow up")).toHaveClass("k-risk");
  expect(document.body).not.toHaveTextContent("1 days");
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
      { id: "Q-1", title: "Is the index final?", text: "", links: [{ label: "Book page", url: `${WEB}example.com/book` }], kind: "question", status: "open", project_name: "Book", sent: null, waiting_days: null, chase_due: false, chases: 0, about: null, options: [] },
      { id: "Q-2", title: "Who writes the jacket copy?", text: "", links: [], kind: "question", status: "open", project_name: "Book", sent: "2026-10-10", waiting_days: null, chase_due: false, chases: 0, about: null, options: [] },
    ],
    actions: [
      { id: "ACT-2", text: "Send the acknowledgments page", due: "2099-10-23", project_name: "Book", links: [], told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 },
      { id: "ACT-1", text: "Send the index", due: "2020-10-14", project_name: "Book", links: [{ label: "Book page", url: `${WEB}example.com/book` }], told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 },
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
  expect(within(actions).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Project", "To-do", "Due", "Link", "Your update"]);
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
  expect(sheet.split("\n")[0]).toBe("Project\tTo-do\tDue\tLink\tYour update");
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
  expect(screen.getByText(/Copy for a spreadsheet to paste into cells/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Copy as table" }));
  await user.click(screen.getAllByRole("button", { name: "Mark sent" })[0]);
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/mark-sent")).toBe(true));
  expect(await screen.findByText("Marked as sent to Robin Sample")).toBeInTheDocument();
});

test("a link to a person's group opens the list that shows them, with the cursor on their group", async () => {
  const waiting: S["FollowupSection"] = {
    person: "PER-3",
    name: "Quinn Sample",
    is_pm: false,
    questions: [
      { id: "Q-5", title: "Can proof copies ship by Nov 3?", text: "", links: [], kind: "question", status: "sent", sent: "2026-10-12", waiting_days: 6, chase_due: false, chases: 0, about: null, options: [] },
    ],
    actions: [],
    message: "",
    to_send: 0,
  };
  fakeApi({ "GET followups": () => [...sections, waiting], "GET people": () => [] });
  renderApp(<FollowUps />);
  await screen.findByRole("button", { name: /^Robin Sample/ });
  expect(screen.getByRole("button", { name: "To send" })).toHaveAttribute("aria-pressed", "true");
  const { reveal } = await import("../lib/reveal");
  act(() => {
    expect(reveal("person", "PER-3")).toBe(true);
  });
  expect(await screen.findByRole("heading", { name: "Quinn Sample" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Waiting on them" })).toHaveAttribute("aria-pressed", "true");
  await waitFor(() => expect(screen.getByRole("heading", { name: "Quinn Sample" }).closest("li")).toHaveFocus());
});

const waitingQuestion = (extra: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
  id: "Q-7",
  title: "Do we have written permission for the epigraph?",
  text: "",
  links: [],
  kind: "question",
  status: "sent",
  sent: "2026-10-10",
  followed_up: null,
  chases: 0,
  waiting_days: 6,
  chase_due: true,
  about: null,
  options: [],
  ...extra,
});

const nudgeText = "Hi Quinn,\n\nFollowing up on one thing from my note on Sat, Oct 10:\n\nDo we have written permission for the epigraph?\n\nA quick yes or no, or a date, is plenty.\n\nThanks!";
const nudgeSection = (extra: Partial<S["FollowupSection"]> = {}): S["FollowupSection"] => ({
  person: "PER-4",
  name: "Quinn Sample",
  is_pm: false,
  questions: [waitingQuestion()],
  actions: [],
  message: "",
  to_send: 0,
  nudge: { text: nudgeText, round: 1, question_ids: ["Q-7"], action_ids: [] },
  ...extra,
});

const nudgeRoutes = {
  "GET followups": () => [nudgeSection()],
  "GET people": () => [],
  "POST followups/PER-4/followed-up": () => ({ questions: 1, actions: 0, question_ids: ["Q-7"], action_ids: [], on: "2026-10-16", previous_told: {}, signal_at: null }),
  "POST followups/PER-4/unfollow": () => ({ ok: "PER-4" }),
};

test("a person who hasn't answered gets a drafted nudge: the items, the box with the template's text, then Copy and Mark sent", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(nudgeRoutes);
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  // The cursor is in the message, and what it lists is above it.
  const box = screen.getByRole("textbox", { name: /Message to Quinn Sample/ });
  expect(box).toHaveFocus();
  expect(box).toHaveValue(nudgeText);
  const card = box.closest("[data-nudge]") as HTMLElement;
  expect(within(card).getByText("Do we have written permission for the epigraph?", { selector: "li *, li" })).toBeInTheDocument();
  expect(within(card).getByText("1st follow-up")).toBeInTheDocument();
  // Copy puts the edited text on the clipboard and records nothing; Mark sent records the text as sent, with Undo.
  await user.type(box, " PS");
  await user.click(within(card).getByRole("button", { name: "Copy" }));
  expect(await navigator.clipboard.readText()).toBe(nudgeText + " PS");
  expect(calls.filter((c) => c.route.startsWith("POST"))).toHaveLength(0);
  await user.click(within(card).getByRole("button", { name: "Mark sent" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-4/followed-up")?.body).toEqual({ text: nudgeText + " PS", question_ids: ["Q-7"], action_ids: [] }));
  expect(await screen.findByText(/Recorded your follow-up with Quinn/)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-4/unfollow")?.body).toEqual({
      question_ids: ["Q-7"],
      action_ids: [],
      on: "2026-10-16",
      previous_told: {},
      signal_at: null,
    }),
  );
});

test("a second nudge says which follow-up it is, and an item chased before shows when", async () => {
  const user = userEvent.setup();
  fakeApi({
    ...nudgeRoutes,
    "GET followups": () => [
      nudgeSection({
        questions: [waitingQuestion({ chases: 1, followed_up: "2026-10-12" })],
        nudge: { text: "Hi Quinn,\n\nChecking in again.", round: 2, question_ids: ["Q-7"], action_ids: [] },
      }),
    ],
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  expect(screen.getByText("2nd follow-up")).toBeInTheDocument();
  expect(screen.getByText(/first asked/)).toBeInTheDocument();
});

test("nothing is offered to draft while nothing has waited long enough", async () => {
  const user = userEvent.setup();
  fakeApi({ ...nudgeRoutes, "GET followups": () => [nudgeSection({ nudge: null, questions: [waitingQuestion({ chase_due: false, chases: 0, waiting_days: 1 })] })] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await screen.findByRole("heading", { name: "Quinn Sample" });
  expect(screen.queryByRole("button", { name: "Draft a nudge" })).toBeNull();
});

// ---- Later: a question held for a meeting or a day ---------------------------------------------------------------------

function withLater(): S["FollowupSection"][] {
  const held = structuredClone(sections);
  const [first] = held[1].questions;
  held[1].questions = [];
  held[1].later = [{ ...first, id: "Q-1", held_until: "2026-10-20", held_for_name: null }];
  held[1].to_send = 1;
  return held;
}

test("Later lists the questions held for a meeting or a day, per person, and To send does not", async () => {
  const user = userEvent.setup();
  const held = withLater();
  const later = held[1].later ?? [];
  held[1].later = [...later, { ...later[0], id: "Q-5", title: "Is the cover final?", held_until: "2026-10-22", held_for_name: "Print sync" }];
  fakeApi({ "GET followups": () => held, "GET people": () => [] });
  renderApp(<FollowUps />);
  expect(await screen.findByRole("button", { name: /^Robin Sample/ })).toHaveTextContent("1 to send");
  expect(screen.queryByText("Is the index final?")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Later" }));
  const card = screen.getByRole("listitem", { name: "Robin Sample" });
  expect(within(card).getByText("2 for later")).toBeInTheDocument();
  const rows = within(card).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent(/Is the index final\?/);
  expect(rows[0]).toHaveTextContent(/Waiting until .*20/);
  expect(rows[1]).toHaveTextContent(/Is the cover final\?/);
  expect(rows[1]).toHaveTextContent(/Waiting for Print sync, .*22/);
  expect(screen.queryByRole("button", { name: /Copy/ })).toBeNull();
});

test("Later says so when nothing is held, and Send now brings a question back with Undo", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  const { unmount } = renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Later" }));
  expect(screen.getByText(/Nothing is waiting for later\./)).toBeInTheDocument();
  unmount();
  const previous = { on: "2026-10-20", since: "2026-10-14" };
  const calls = fakeApi({
    "GET followups": () => withLater(),
    "GET people": () => [],
    "POST questions/Q-1/held-for": () => ({ ok: "Q-1", previous }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Later" }));
  await user.click(await screen.findByRole("button", { name: "More actions for Is the index final?" }));
  await user.click(await screen.findByRole("menuitem", { name: "Send now" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-1/held-for")?.body).toEqual({ held_for: null }));
  expect(await screen.findByText("Brought back to what is left to send.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST questions/Q-1/held-for").at(-1)?.body).toEqual({ held_for: previous }));
});

test("Hold for later on a card holds a question for a day, with the cursor in the field, at once and with Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => sections,
    "GET people": () => [],
    "GET today/agenda": () => [],
    "POST questions/Q-1/held-for": () => ({ ok: "Q-1", previous: null }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "More actions for Robin Sample" }));
  await user.click(await screen.findByRole("menuitem", { name: "Hold for later…" }));
  const choice = screen.getByRole("combobox", { name: "Hold it for" });
  expect(choice).toHaveFocus();
  const save = screen.getByRole("button", { name: "Hold for later" });
  expect(save).toBeDisabled();
  await user.type(screen.getByLabelText("Send it on"), "2099-01-05");
  expect(save).toBeEnabled();
  await user.click(save);
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-1/held-for")?.body).toEqual({ held_for: { on: "2099-01-05" } }));
  expect(await screen.findByText(/^Kept for later, until /)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST questions/Q-1/held-for").at(-1)?.body).toEqual({ held_for: null }));
});

test("Hold for later offers the meetings the calendar keeps entries for, a series as its next one, and holds for the one picked", async () => {
  const user = userEvent.setup();
  const meeting = (extra: Partial<S["AgendaItemView"]>): S["AgendaItemView"] => ({
    snapshot: "s", source: "c", title: "Print sync", start: "2026-10-20", all_day: true, cancelled: false, days: ["2026-10-20"], own: true, open_items: 0, entry: "EVT-1", ...extra,
  });
  const calls = fakeApi({
    "GET followups": () => sections,
    "GET people": () => [],
    "GET today/agenda": () => [meeting({ series: "SER-1" }), meeting({ title: "One-off review", entry: "EVT-2", series: null }), meeting({ title: "No entry", entry: null }), meeting({ title: "Called off", entry: "EVT-3", cancelled: true })],
    "POST questions/Q-1/held-for": () => ({ ok: "Q-1", previous: null }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "More actions for Robin Sample" }));
  await user.click(await screen.findByRole("menuitem", { name: "Hold for later…" }));
  const choice = await screen.findByRole("combobox", { name: "Hold it for" });
  await waitFor(() => expect(within(choice).getAllByRole("option")).toHaveLength(3));
  expect(within(choice).getByRole("option", { name: "Print sync, the next one" })).toBeInTheDocument();
  expect(within(choice).getByRole("option", { name: /^One-off review, / })).toBeInTheDocument();
  expect(within(choice).queryByRole("option", { name: /No entry|Called off/ })).toBeNull();
  await user.selectOptions(choice, "series:SER-1");
  expect(screen.queryByLabelText("Send it on")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Hold for later" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-1/held-for")?.body).toEqual({ held_for: { series: "SER-1" } }));
});

// By person or by project (design 7.5): the same open items, grouped under the project each belongs to.

const byProject: S["FollowupSection"][] = [
  sections[0],
  {
    ...sections[1],
    questions: [{ ...sections[1].questions[0], status: "sent", waiting_days: 5, chase_due: true, project_name: "Cover" }],
    actions: [{ ...sections[1].actions[0], project_name: "Book" }],
  },
];

test("a switch groups the open items by project, each saying who it is with and where it stands, the ones with no project last", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => byProject, "GET people": () => [] });
  renderApp(<FollowUps />);
  await screen.findByRole("heading", { name: "You" });
  expect(screen.getByRole("radio", { name: "By person" })).toBeChecked();
  await user.click(screen.getByRole("radio", { name: "By project" }));
  const list = await screen.findByRole("list", { name: "Open follow-ups by project" });
  expect(within(list).getAllByRole("heading").map((h) => h.textContent)).toEqual(["Book", "Cover"]);
  const book = within(list).getByRole("heading", { name: "Book" }).closest("li")!;
  expect(within(book).getByText("You · Yours")).toBeInTheDocument();
  expect(within(book).getByText("Robin Sample · To send")).toBeInTheDocument();
  expect(within(list).getByText("Robin Sample · waiting 5 days · follow up")).toBeInTheDocument();
  // The by-person filters are not shown for a grouping they don't apply to.
  expect(screen.queryByRole("group", { name: "Show" })).toBeNull();
});

test("an item with no project is gathered under No project, after the projects", async () => {
  const user = userEvent.setup();
  const loose = [{ ...sections[1], questions: [], actions: [{ ...sections[1].actions[0], project_name: "" }] }, sections[0]];
  fakeApi({ "GET followups": () => loose, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("radio", { name: "By project" }));
  const list = await screen.findByRole("list", { name: "Open follow-ups by project" });
  expect(within(list).getAllByRole("heading").map((h) => h.textContent)).toEqual(["Book", "No project"]);
});

test("a row's Open goes to that person's group, on the list that holds what is waiting on them", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => byProject, "GET people": () => [] });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("radio", { name: "By project" }));
  await user.click((await screen.findAllByRole("button", { name: "Open Robin Sample's follow-ups" }))[0]);
  expect(screen.getByRole("radio", { name: "By person" })).toBeChecked();
  expect(await screen.findByRole("heading", { name: "Robin Sample" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Waiting on them" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByRole("list", { name: "Open follow-ups by project" })).toBeNull();
});

test("on Today the switch is not shown", async () => {
  fakeApi({ "GET followups": () => byProject, "GET people": () => [] });
  renderApp(<FollowUps compact />);
  await screen.findByRole("button", { name: /^Robin Sample/ });
  expect(screen.queryByRole("radio", { name: "By project" })).toBeNull();
});
