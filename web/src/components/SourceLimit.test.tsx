// A limited message (design 6.35): the saved text says who it is limited to and why, and Widen adds a person from the
// list or removes the limit, each with an Undo toast.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

const limit: S["SourceLimit"] = {
  people: [
    { id: "PER-2", name: "Pat Example" },
    { id: null, name: "guest@example.com" },
  ],
  marking: "internal only",
  why: "Internal only: the date is moving.",
  group: null,
  widened_by: null,
};

const source = (over: Partial<S["SourceView"]> = {}): S["SourceView"] => ({
  id: "SRC-3",
  title: "Email from the printer",
  kind: "pasted",
  trust: "untrusted",
  received_at: "2026-10-09T14:00:00Z",
  url: null,
  text: "Internal only: the date is moving.",
  limit,
  ...over,
});

const people = [
  { id: "PER-2", name: "Pat Example", role: null },
  { id: "PER-3", name: "Sam Sample", role: null },
] as unknown as S["PersonView"][];

const section: S["FollowupSection"][] = [
  {
    person: "PER-1",
    name: "Lee Example",
    is_pm: true,
    questions: [
      { id: "Q-7", title: "Ship the proof now?", text: "", links: [], kind: "decision", status: "open", sent: null, waiting_days: null, about: null, options: [], chase_due: false, chases: 0, origin: { kind: "source", source: "SRC-3" } },
    ],
    actions: [],
    message: "",
    to_send: 0,
  },
];

async function openSource(user: ReturnType<typeof userEvent.setup>) {
  renderApp(<FollowUps />);
  const row = (await screen.findByText("Ship the proof now?")).closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "Where it came from" }));
  return screen.findByRole("dialog", { name: "Where it came from" });
}

beforeEach(() => {
  window.location.hash = "";
});

test("a limited message says who it is limited to and the sentence that limits it", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => section, "GET people": () => people, "GET sources/SRC-3": () => source() });
  const dialog = await openSource(user);
  expect(await within(dialog).findByText("Limited to: Pat Example, guest@example.com")).toBeInTheDocument();
  expect(within(dialog).getByText("It says: Internal only: the date is moving.")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Widen" })).toBeInTheDocument();
});

test("a message with no limit shows no Limited to line and no Widen", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET followups": () => section, "GET people": () => people, "GET sources/SRC-3": () => source({ limit: null }) });
  const dialog = await openSource(user);
  await within(dialog).findByText("Internal only: the date is moving.");
  expect(within(dialog).queryByText(/Limited to/)).toBeNull();
  expect(within(dialog).queryByRole("button", { name: "Widen" })).toBeNull();
});

test("Widen adds a person picked from the list, leaving out those already in, with an Undo toast", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => section,
    "GET people": () => people,
    "GET sources/SRC-3": () => source(),
    "POST sources/SRC-3/widen": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }),
  });
  const dialog = await openSource(user);
  await user.click(await within(dialog).findByRole("button", { name: "Widen" }));
  const pick = within(dialog).getByLabelText("Add someone who may see it");
  // Opening the form puts the cursor in its list.
  await waitFor(() => expect(pick).toHaveFocus());
  expect(within(pick).queryByRole("option", { name: "Pat Example" })).toBeNull();
  await user.selectOptions(pick, "PER-3");
  await user.click(within(dialog).getByRole("button", { name: "Add them" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST sources/SRC-3/widen")).toBe(true));
  expect(calls.find((c) => c.route === "POST sources/SRC-3/widen")!.body).toEqual({ people: ["PER-3"], open: false });
  await screen.findByText("Added to the people who may see that message.");
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("Remove the limit calls the same route with open set", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET followups": () => section,
    "GET people": () => people,
    "GET sources/SRC-3": () => source(),
    "POST sources/SRC-3/widen": () => ({ changeset: "CS-10" }),
  });
  const dialog = await openSource(user);
  await user.click(await within(dialog).findByRole("button", { name: "Widen" }));
  await user.click(within(dialog).getByRole("button", { name: "Remove the limit" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST sources/SRC-3/widen")?.body).toEqual({ people: [], open: true }));
  expect(await screen.findByText("Removed the limit on that message.")).toBeInTheDocument();
});
