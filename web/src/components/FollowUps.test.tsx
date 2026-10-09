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
      { id: "Q-1", title: "Is the index final?", text: "", links: [], kind: "question", status: "open", waiting_days: null, about: null, options: [] },
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

test("Copy puts the edited message on the clipboard, then Mark sent records it with Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => sections,
    "GET people": () => [],
    "POST followups/PER-2/mark-sent": () => ({ questions: 1, actions: 1, question_ids: ["Q-1"], action_ids: ["ACT-1"] }),
    "POST followups/PER-2/unmark-sent": () => ({ ok: "PER-2" }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: /^Robin Sample/ }));
  const box = screen.getByRole("textbox", { name: /Message to Robin Sample/ });
  await user.type(box, " PS");
  await user.click(screen.getByRole("button", { name: "Copy message" }));
  expect(await navigator.clipboard.readText()).toBe(sections[1].message + " PS");
  // The toast offers Mark sent, and so does the row itself once the message is copied.
  expect(screen.getAllByRole("button", { name: "Mark sent" })).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "Copy 2" })).toBeNull();
  await user.click(screen.getAllByRole("button", { name: "Mark sent" })[0]);
  await waitFor(() => expect(calls.some((c) => c.route === "POST followups/PER-2/mark-sent")).toBe(true));
  expect(calls.find((c) => c.route === "POST followups/PER-2/mark-sent")!.body).toEqual({ text: sections[1].message + " PS" });
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-2/unmark-sent")?.body).toEqual({
      question_ids: ["Q-1"],
      action_ids: ["ACT-1"],
    }),
  );
});

test("the workspace can rename the section", async () => {
  fakeApi({ "GET followups": () => sections, "GET people": () => [] });
  renderApp(<FollowUps />, { "followups.title": "Chasers" });
  expect(await screen.findByRole("heading", { name: "Chasers" })).toBeInTheDocument();
});


test("after copying, the row's next step is Mark sent, even once the toast is gone", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => sections,
    "GET people": () => [],
    "POST followups/PER-2/mark-sent": () => ({ questions: 1, actions: 1, question_ids: ["Q-1"], action_ids: ["ACT-1"] }),
  });
  renderApp(<FollowUps />);
  await user.click(await screen.findByRole("button", { name: "Copy 2" }));
  await user.click(await screen.findByRole("button", { name: "Dismiss" }));
  const row = screen.getByRole("listitem", { name: /Robin Sample/ });
  await user.click(within(row).getByRole("button", { name: "Mark sent" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST followups/PER-2/mark-sent")?.body).toEqual({ text: sections[1].message }),
  );
});
