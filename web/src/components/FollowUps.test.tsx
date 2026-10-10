import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

const sections: S["FollowupSection"][] = [
  {
    person: "PER-1",
    name: "Pat Example",
    is_pm: true,
    questions: [],
    actions: [{ id: "ACT-9", text: "Approve the proof", due: "2026-11-03", project_name: "Book", told: null, told_days: null }],
    message: "",
    to_send: 0,
  },
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [
      { id: "Q-1", title: "Is the index final?", text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, about: null, options: [] },
    ],
    actions: [{ id: "ACT-1", text: "Send the index", due: "2026-10-16", project_name: "Book", told: null, told_days: null }],
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
    id: "Q-2", title: "Did the cover ship?", text: "", links: [], kind: "question", status: "sent", sent: "2026-10-08", waiting_days: 2, about: null, options: [],
  });
  mixed[1].actions.push({ id: "ACT-2", text: "Return the proof", due: null, project_name: "Book", told: "2026-10-08", told_days: 2 });
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

test("They finished it closes the action with Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => waitingSections(),
    "GET people": () => [],
    "POST actions/ACT-1/status": () => ({ ok: "ACT-1" }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(screen.getByRole("button", { name: "They finished it" }));
  await waitFor(() => expect(calls.some((c) => c.route.includes("ACT-1"))).toBe(true));
});
