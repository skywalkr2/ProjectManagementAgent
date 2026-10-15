import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { learnedLine, project, proposal } from "../lib/learned-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { LearnedLines } from "./Learned";

function show(lines: S["LearnedLine"][], routes: Routes = {}, props: { changesets?: string[]; records?: string[] } = { changesets: ["CS-1"] }) {
  const calls = fakeApi({
    "GET knowledge/learned": () => ({ lines }),
    "GET projects": () => [project("PRJ-1", "Spring launch")],
    "POST knowledge/LES-1/keep": () => ({ changeset: "CS-9" }),
    "POST knowledge/LES-1/just-this-time": () => ({ changeset: "CS-9" }),
    "POST knowledge/LES-1/discard": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [1], skipped: [] }),
    ...routes,
  });
  renderApp(<LearnedLines {...props} />);
  return calls;
}

const posted = (calls: { route: string; body: unknown }[], route: string) => calls.find((c) => c.route === route)?.body;

test("the line says what was learned, with the narrowest reach picked, and Keep acts at once with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  const line = await screen.findByText("Interior files go to the editor before the printer.");
  expect(line.closest("p")).toHaveTextContent("Learned: Interior files go to the editor before the printer.");
  const reach = await screen.findByRole("combobox", { name: "Keep for" });
  await waitFor(() => expect(within(reach).getAllByRole("option")[0]).toHaveTextContent("Filing notes on Spring launch"));
  expect(reach).toHaveValue("proposed");
  await user.click(screen.getByRole("button", { name: "Keep" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/keep")).toEqual({ read_version: 3 }));
  expect(await screen.findByText("Kept. Helper will use it from now on.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("widening the reach is one pick from a list, and Keep sends that target", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  const reach = await screen.findByRole("combobox", { name: "Keep for" });
  await waitFor(() => expect(within(reach).getAllByRole("option")).toHaveLength(4));
  expect(within(reach).getAllByRole("option").map((o) => o.textContent)).toEqual([
    "Filing notes on Spring launch",
    "Filing notes on every project",
    "All kinds of work on Spring launch",
    "All kinds of work on every project",
  ]);
  await user.selectOptions(reach, "All kinds of work on every project");
  await user.click(screen.getByRole("button", { name: "Keep" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/keep")).toMatchObject({ read_version: 3, applies_to: { scope: "workspace", task_kinds: [] } }));
});

test("Just this time sets it aside at once and says nothing is kept", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  await user.click(await screen.findByRole("button", { name: "Just this time" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/just-this-time")).toEqual({ read_version: 3 }));
  expect(await screen.findByText("Noted as just this time. Nothing is kept.")).toBeInTheDocument();
});

test("a correction said to be just this time before says how many times", async () => {
  show([learnedLine({ proposal: proposal({ just_this_time_before: 2 }) })]);
  expect(await screen.findByText("You said “just this time” to this 2 times before.")).toBeInTheDocument();
});

test("Edit opens a drawer, and Keep there keeps the person's own wording", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  const drawer = await screen.findByRole("dialog", { name: "Edit what was learned" });
  const box = within(drawer).getByRole("textbox", { name: "What Helper will remember" });
  await waitFor(() => expect(box).toHaveFocus());
  await user.clear(box);
  await user.type(box, "Send interior files to the editor first.");
  await user.click(within(drawer).getByRole("button", { name: "Keep" }));
  await waitFor(() =>
    expect(posted(calls, "POST knowledge/LES-1/keep")).toEqual({ read_version: 3, text: "Send interior files to the editor first." }),
  );
});

test("Discard asks why, which is optional, and keeps the proposal as discarded", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  await user.click(await screen.findByRole("button", { name: "Discard" }));
  const reason = await screen.findByRole("textbox", { name: "Why was it wrong? (optional)" });
  expect(reason).toHaveFocus();
  await user.type(reason, "It is about a different book.");
  await user.click(within(reason.closest("form")!).getByRole("button", { name: "Discard" }));
  await waitFor(() =>
    expect(posted(calls, "POST knowledge/LES-1/discard")).toEqual({ read_version: 3, reason: "It is about a different book." }),
  );
  expect(await screen.findByText("Discarded.")).toBeInTheDocument();
});

test("a discard with no reason sends none", async () => {
  const user = userEvent.setup();
  const calls = show([learnedLine()]);
  await user.click(await screen.findByRole("button", { name: "Discard" }));
  const form = (await screen.findByRole("textbox", { name: "Why was it wrong? (optional)" })).closest("form")!;
  await user.click(within(form).getByRole("button", { name: "Discard" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/discard")).toEqual({ read_version: 3, reason: null }));
});

test("while the assistant is still learning, the line says so and why it waits", async () => {
  show([learnedLine({ state: "learning", proposal: null, waiting: "Learning from this correction with the next batch, at 3:30 PM." })]);
  expect(await screen.findByRole("status")).toHaveTextContent("Learning from this…");
  expect(screen.getByText("Learning from this correction with the next batch, at 3:30 PM.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Keep" })).toBeNull();
});

test("the person's own words are already kept, so the line shows Undo instead of Keep", async () => {
  const user = userEvent.setup();
  const calls = show(
    [learnedLine({ state: "kept", undo: "CS-7", proposal: proposal({ status: "active", learned_from: "person" }) })],
    { "POST changesets/CS-7/undo": () => ({ restored: [1], skipped: [] }) },
  );
  expect(await screen.findByText(/Interior files go to the editor before the printer/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Keep" })).toBeNull();
  expect(screen.queryByRole("combobox", { name: "Keep for" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-7/undo"));
});

test("what came from outside content shows the words beside it, marked as from outside", async () => {
  show([learnedLine({ proposal: proposal({ trust: "untrusted", evidence: { quote: "interior files go to the editor", source: "SRC-1" } }) })]);
  const evidence = await screen.findByText(/interior files go to the editor/);
  expect(evidence.closest("p")).toHaveTextContent("From: interior files go to the editor From outside");
});

test("words the person's own correction gave carry no outside mark", async () => {
  show([learnedLine()]);
  await screen.findByText(/go to the editor first/);
  expect(screen.queryByText("From outside")).toBeNull();
});

test("a line shows on the card it was learned from and on the records it names, and nowhere else", async () => {
  show([learnedLine(), learnedLine({ signal: "SIG-2", changeset: null, refs: ["ACT-1"], proposal: proposal({ id: "LES-2", text: "Photos go to the designer." }) })], {}, { changesets: ["CS-5"], records: ["ACT-1"] });
  expect(await screen.findByText("Photos go to the designer.")).toBeInTheDocument();
  expect(screen.queryByText("Interior files go to the editor before the printer.")).toBeNull();
});

test("nothing is drawn when nothing was learned from the card", async () => {
  const calls = show([], {}, { changesets: ["CS-1"] });
  await waitFor(() => expect(calls.some((c) => c.route === "GET knowledge/learned")).toBe(true));
  expect(screen.queryByRole("list", { name: "What Helper learned from this" })).toBeNull();
});

test("the chosen reach is said in plain words beside Keep for, and follows the pick", async () => {
  const user = userEvent.setup();
  show([learnedLine()], { "GET people": () => [] });
  const reach = await screen.findByRole("combobox", { name: "Keep for" });
  const said = () => reach.parentElement!.querySelector("[data-reach-said]")!;
  await waitFor(() => expect(said()).toHaveTextContent("Only Spring launch · for filing notes"));
  expect(reach).toHaveAccessibleDescription("Only Spring launch · for filing notes");
  await user.selectOptions(reach, "All kinds of work on every project");
  await waitFor(() => expect(said()).toHaveTextContent(/^All projects$/));
});

test("a reach that leaves projects out says which, by name", async () => {
  const everyProjectButOne = proposal({ applies_to: { task_kinds: ["notes"], scope: "workspace", projects: [], except: ["PRJ-2"] } });
  show([learnedLine({ proposal: everyProjectButOne })], {
    "GET projects": () => [project("PRJ-1", "Spring launch"), project("PRJ-2", "Autumn list")],
    "GET people": () => [],
  });
  const reach = await screen.findByRole("combobox", { name: "Keep for" });
  await waitFor(() =>
    expect(reach.parentElement!.querySelector("[data-reach-said]")).toHaveTextContent("All projects except Autumn list · for filing notes"),
  );
});
