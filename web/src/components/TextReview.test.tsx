import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { useTextReview } from "./TextReview";

function Harness() {
  const { open, dialog } = useTextReview();
  return (
    <>
      <button type="button" onClick={() => open("V-2")}>
        Open it
      </button>
      {dialog}
    </>
  );
}

function review(extra: Partial<S["TextReview"]> = {}, version: Partial<S["TextVersionView"]> = {}): S["TextReview"] {
  return {
    version: {
      id: "V-2",
      number: 2,
      version: 7,
      status: "pending",
      source: "draft",
      words: 20,
      base: 1,
      note: null,
      created_at: "2026-10-09T14:00:00Z",
      questions: [],
      unmapped: [],
      ...version,
    },
    current: 1,
    three_way: false,
    regions: [
      { id: "r1", side: "pending", base: "", current: "The old opening.", pending: "A <b>new</b> opening." },
      { id: "r2", side: "pending", base: "", current: "", pending: "An added line." },
      { id: "", side: "current", base: "", current: "Already changed here.", pending: "" },
    ],
    pending_text: "",
    ...extra,
  };
}

const REVIEW = "GET text-versions/V-2/review";

function show(routes: Routes) {
  const calls = fakeApi({ [REVIEW]: () => review(), ...routes });
  renderApp(<Harness />);
  return calls;
}

async function open(total = 2) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open it" }));
  const dialog = await screen.findByRole("dialog", { name: "Review the changes" });
  await within(dialog).findByText(`Change 1 of ${total}`);
  return { user, dialog };
}

test("each change shows the current and the proposed passage with Accept chosen; the current text's own changes are only listed", async () => {
  show({});
  const { dialog } = await open();
  const first = within(dialog).getByRole("group", { name: /Change 1 of 2/ });
  expect(within(first).getByText("The old opening.")).toBeInTheDocument();
  expect(within(first).getByText("A <b>new</b> opening.")).toBeInTheDocument();
  expect(first.querySelector("b")).toBeNull();
  expect(within(first).queryByText("Original")).toBeNull();
  expect(within(first).getByRole("radio", { name: "Accept" })).toBeChecked();
  expect(within(first).getByRole("radio", { name: "Keep current" })).not.toBeChecked();
  const second = within(dialog).getByRole("group", { name: /Change 2 of 2/ });
  expect(within(second).getByText("(nothing)")).toBeInTheDocument();
  const kept = within(dialog).getByRole("region", { name: "Already kept" });
  expect(within(kept).getByText("Already changed here.")).toBeInTheDocument();
  expect(within(kept).queryByRole("radio")).toBeNull();
});

test("a radio group can be operated from the keyboard", async () => {
  show({});
  const { user, dialog } = await open();
  const first = within(dialog).getByRole("group", { name: /Change 1 of 2/ });
  within(first).getByRole("radio", { name: "Accept" }).focus();
  await user.keyboard("{ArrowDown}");
  expect(within(first).getByRole("radio", { name: "Keep current" })).toBeChecked();
});

test("when the text moved on, the original is shown too and a passage both sides changed is marked as a conflict in words", async () => {
  show({
    [REVIEW]: () =>
      review({
        three_way: true,
        regions: [{ id: "r1", side: "both", base: "As it was.", current: "As you left it.", pending: "As it came back." }],
      }),
  });
  const { dialog } = await open(1);
  const change = within(dialog).getByRole("group", { name: /Change 1 of 1/ });
  expect(within(change).getByText("Different versions")).toBeInTheDocument();
  expect(within(change).getByText("As it was.")).toBeInTheDocument();
  expect(within(change).getByText("As you left it.")).toBeInTheDocument();
  expect(within(change).getByText("As it came back.")).toBeInTheDocument();
  expect(within(change).getByText("Original")).toBeInTheDocument();
});

test("the draft's questions and what couldn't be read back are shown when there are any", async () => {
  show({ [REVIEW]: () => review({}, { questions: ["Is the date right?"], unmapped: ["A table in section 2"] }) });
  const { dialog } = await open();
  const questions = within(dialog).getByRole("region", { name: "Questions from the draft" });
  expect(within(questions).getByText("Is the date right?")).toBeInTheDocument();
  const unmapped = within(dialog).getByRole("region", { name: "Couldn't read the returned text" });
  expect(within(unmapped).getByText("A table in section 2")).toBeInTheDocument();
});

test("no questions and nothing unmapped means neither section", async () => {
  show({});
  const { dialog } = await open();
  expect(within(dialog).queryByRole("region", { name: "Questions from the draft" })).toBeNull();
  expect(within(dialog).queryByRole("region", { name: "Couldn't read the returned text" })).toBeNull();
});

test("Save my choices sends the record version and every choice, closes, and offers Undo", async () => {
  const calls = show({
    "POST text-versions/V-2/accept": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [{ kind: "x", id: "y" }], skipped: [] }),
  });
  const { user, dialog } = await open();
  await user.click(within(within(dialog).getByRole("group", { name: /Change 2 of 2/ })).getByRole("radio", { name: "Keep current" }));
  await user.click(within(dialog).getByRole("button", { name: "Save my choices" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(calls.find((c) => c.route === "POST text-versions/V-2/accept")?.body).toEqual({
    read_version: 7,
    choices: { r1: "accept", r2: "reject" },
  });
  expect(await screen.findByText("Your choices were saved.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Open it" })).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-1/undo"));
});

test("Discard this version is in the menu and sends no choices", async () => {
  const calls = show({ "POST text-versions/V-2/discard": () => ({ changeset: "CS-2" }) });
  const { user, dialog } = await open();
  expect(within(dialog).queryByRole("button", { name: "Discard this version" })).toBeNull();
  await user.click(within(dialog).getByRole("button", { name: /^More actions/ }));
  await user.click(screen.getByRole("menuitem", { name: "Discard this version" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(calls.find((c) => c.route === "POST text-versions/V-2/discard")?.body).toEqual({ read_version: 7, choices: {} });
  expect(await screen.findByText("That version was discarded.")).toBeInTheDocument();
});

test("if the text changed meanwhile, the server's words and a hint to reload show, and Reload asks again", async () => {
  let reads = 0;
  show({
    [REVIEW]: () => review({}, { version: 7 + reads++ }),
    "POST text-versions/V-2/accept": () => new Refuse(409, "the text changed since you opened it"),
  });
  const { user, dialog } = await open();
  await user.click(within(dialog).getByRole("button", { name: "Save my choices" }));
  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent("the text changed since you opened it");
  expect(alert).toHaveTextContent("Reload it before choosing");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await user.click(within(alert).getByRole("button", { name: "Reload" }));
  await waitFor(() => expect(within(dialog).queryByRole("alert")).toBeNull());
  expect(reads).toBe(2);
});
