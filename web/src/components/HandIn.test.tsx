import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { HandIn } from "./HandIn";

const handed = () => ({ request: "REQ-1", source: null });

const project = (id: string, name: string, extra: Partial<S["ProjectView"]> = {}): S["ProjectView"] => ({
  id,
  name,
  group: null,
  status: null,
  phase: null,
  target: null,
  owner: null,
  owner_name: null,
  summary: null,
  language: "en-US",
  language_own: false,
  spent_usd: 0,
  open_actions: 0,
  open_questions: 0,
  ...extra,
});
const PROJECTS = [
  project("P-1", "Harbor"),
  project("P-2", "Lighthouse", { parent: "P-1" }),
  project("P-3", "Old dock", { status: "Done" }),
  project("P-4", "Ferry"),
];

async function setup() {
  const user = userEvent.setup();
  const calls = fakeApi({ "POST handin": handed, "GET projects": () => PROJECTS });
  const onClose = vi.fn();
  renderApp(<HandIn onClose={onClose} />);
  return { user, calls, onClose };
}

const sent = (calls: Array<{ route: string; body: unknown }>) => calls.find((c) => c.route === "POST handin")?.body;

test("there is one box and it has the focus", async () => {
  await setup();
  const box = screen.getByLabelText("Paste or type it here");
  expect(box).toHaveFocus();
  expect(screen.getAllByRole("textbox")).toHaveLength(2); // the box and the optional line
});

test("someone else's words are the default and are sent as pasted content", async () => {
  const { user, calls, onClose } = await setup();
  expect(screen.getByRole("radio", { name: /Someone else's/ })).toBeChecked();
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(sent(calls)).toEqual({ note: "", pasted: "Subject: dates" });
});

test("the optional line is the note that goes with someone else's words", async () => {
  const { user, calls } = await setup();
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.type(screen.getByLabelText("Anything to do with it? (optional)"), "file the dates");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "file the dates", pasted: "Subject: dates" }));
});

test("choosing Mine sends the box as the note and takes the optional line away", async () => {
  const { user, calls } = await setup();
  await user.type(screen.getByLabelText("Anything to do with it? (optional)"), "ignored line");
  await user.click(screen.getByRole("radio", { name: "Mine" }));
  expect(screen.queryByLabelText("Anything to do with it? (optional)")).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Paste or type it here"), "remember the reading series");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "remember the reading series", pasted: "" }));
});

test("nothing can be handed in with an empty box", async () => {
  const { user } = await setup();
  await user.type(screen.getByLabelText("Anything to do with it? (optional)"), "only a line");
  expect(screen.getByRole("button", { name: "Hand in" })).toBeDisabled();
});

test("the choice can be made from the keyboard", async () => {
  const { user, calls } = await setup();
  await user.type(screen.getByLabelText("Paste or type it here"), "my own words");
  await user.tab(); // the choice
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("radio", { name: "Mine" })).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "my own words", pasted: "" }));
});

test("how sensitive it is starts at the usual and sends nothing about it", async () => {
  const { user, calls } = await setup();
  expect(screen.getByLabelText("How sensitive is this?")).toHaveValue("");
  expect(screen.getByRole("option", { name: "The usual" })).toBeInTheDocument();
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "", pasted: "Subject: dates" }));
  expect(sent(calls)).not.toHaveProperty("data_level");
});

test("Confidential and Private are sent as the level the person chose, in plain words", async () => {
  const { user, calls } = await setup();
  const choice = screen.getByLabelText("How sensitive is this?");
  expect(within(choice).getAllByRole("option").map((o) => o.textContent)).toEqual([
    "The usual",
    "Confidential",
    "Private: only accounts allowed private material",
  ]);
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.selectOptions(choice, "Confidential");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "", pasted: "Subject: dates", data_level: "internal" }));
});

test("Private is sent with the person's own note too", async () => {
  const { user, calls } = await setup();
  await user.click(screen.getByRole("radio", { name: "Mine" }));
  await user.type(screen.getByLabelText("Paste or type it here"), "keep this quiet");
  await user.selectOptions(screen.getByLabelText("How sensitive is this?"), "Private: only accounts allowed private material");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "keep this quiet", pasted: "", data_level: "restricted" }));
});

test("the project choice starts at not sure, lists every project with sub-projects after their parent, and sends none", async () => {
  const { user, calls } = await setup();
  const choice = screen.getByLabelText("Which project is this about?");
  expect(choice).toHaveValue("");
  expect(choice).toHaveAccessibleDescription("Helps Helper file things in the right place.");
  await waitFor(() =>
    expect(within(choice).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Not sure / several",
      "Harbor",
      "Harbor › Lighthouse",
      "Old dock",
      "Ferry",
    ]),
  );
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "", pasted: "Subject: dates" }));
  expect(sent(calls)).not.toHaveProperty("project");
});

test("a chosen project is sent by its id, and choosing not sure again takes it back", async () => {
  const { user, calls } = await setup();
  const choice = screen.getByLabelText("Which project is this about?");
  await screen.findByRole("option", { name: "Harbor › Lighthouse" });
  await user.type(screen.getByLabelText("Paste or type it here"), "Subject: dates");
  await user.selectOptions(choice, "Harbor › Lighthouse");
  await user.selectOptions(choice, "Not sure / several");
  await user.selectOptions(choice, "Ferry");
  await user.click(screen.getByRole("button", { name: "Hand in" }));
  await waitFor(() => expect(sent(calls)).toEqual({ note: "", pasted: "Subject: dates", project: "P-4" }));
});
