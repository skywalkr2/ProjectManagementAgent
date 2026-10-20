import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

const question: S["FollowupQuestion"] = {
  id: "Q-8",
  title: "Is the index final?",
  text: "",
  links: [],
  kind: "question",
  status: "sent",
  sent: "2026-10-10",
  waiting_days: 6,
  chase_due: true,
  chases: 0,
  followed_up: null,
  about: null,
  options: [],
} as S["FollowupQuestion"];

function show(left_out: S["LeftOutView"][]) {
  const robin: S["FollowupSection"] = {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [question],
    actions: [],
    message: "",
    to_send: 0,
    nudge: { text: "Hi Robin,\n\nFollowing up on one thing.", round: 1, question_ids: ["Q-8"], action_ids: [], left_out },
  };
  fakeApi({ "GET followups": () => [robin], "GET people": () => [], "GET projects": () => [], "GET lists": () => [] });
  renderApp(<FollowUps />);
}

test("what went in the same message and was answered or done since is in the list above the box, saying why it is left out", async () => {
  const user = userEvent.setup();
  show([
    { kind: "question", id: "Q-3", text: "Do we have written permission for the epigraph?", on: "2026-10-12" },
    { kind: "action", id: "ACT-3", text: "Agree on the back-cover copy", on: "2026-10-13" },
  ]);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  const list = (await screen.findByText("In this message")).parentElement!.querySelector("ul")!;
  const items = within(list).getAllByRole("listitem");
  expect(items.map((i) => i.textContent)).toEqual([
    expect.stringContaining("Is the index final?"),
    expect.stringMatching(/Do we have written permission for the epigraph\?.*Answered .*Oct 12.*, left out/),
    expect.stringMatching(/Agree on the back-cover copy.*Done .*Oct 13.*, left out/),
  ]);
  // Said in words, never by color alone, and it is not in the message to copy.
  expect((screen.getByRole("textbox", { name: /Message to Robin Sample/ }) as HTMLTextAreaElement).value).not.toContain("epigraph");
});

test("with nothing left out the list holds only what the message lists", async () => {
  const user = userEvent.setup();
  show([]);
  await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
  await user.click(await screen.findByRole("button", { name: "Draft a nudge" }));
  expect(document.querySelectorAll("[data-left-out]")).toHaveLength(0);
});
