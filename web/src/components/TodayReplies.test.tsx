import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// A reply the person owes (design 6.35, 7.7): one line, "Reply to Ana: Interior proofs", with the draft under it marked as
// a draft until it is copied or written, Copy reply as its one button, and No reply needed, Answered another way and Edit in
// its menu. Each is the person's own change with Undo.

type Line = S["QueueLineView"];

const DRAFT = "The interior proofs ship on November 3.";

function reply(over: Partial<Line> = {}): Line {
  return {
    key: "reply:ACT-1",
    group: "send",
    kind: "reply",
    count: 1,
    untrusted: false,
    unpriced: 0,
    actions: ["ACT-1"],
    questions: [],
    outcome: {},
    text: "Tell the shop when the proofs ship",
    subject: "Interior proofs",
    person: "PER-2",
    person_name: "Ana Cole",
    reply: DRAFT,
    reply_reviewed: false,
    ...over,
  };
}

function show(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
    "GET followups": () => [],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET people": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const TITLE = "Reply to Ana Cole: Interior proofs";
const rowOf = async (title = TITLE) => (await screen.findByRole("group", { name: title })) as HTMLElement;
const menuOf = async (user: ReturnType<typeof userEvent.setup>, row: HTMLElement) => user.click(within(row).getByRole("button", { name: /More actions for/ }));

test("a reply owed is one line with who it is to, the message's subject and the draft marked as a draft", async () => {
  show([reply()]);
  const row = await rowOf();
  expect(within(row).getByText("Reply owed")).toBeInTheDocument();
  expect(within(row).getByText("Draft, not yet reviewed")).toBeInTheDocument();
  expect(within(row).getByText(DRAFT)).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Copy reply" })).toBeInTheDocument();
});

test("a reply to someone who is nobody known is to the sender as the message writes it", async () => {
  show([reply({ person: null, person_name: null, sender: "Zed Alder" })]);
  expect(await rowOf("Reply to Zed Alder: Interior proofs")).toBeInTheDocument();
});

test("a draft the person has reviewed says it is theirs", async () => {
  show([reply({ reply_reviewed: true })]);
  const row = await rowOf();
  expect(within(row).getByText("Your reply")).toBeInTheDocument();
  expect(within(row).queryByText("Draft, not yet reviewed")).toBeNull();
});

test("Copy reply puts the draft on the clipboard and approves it as it is, and Undo takes the approval back", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], { "POST actions/ACT-1/reply": () => ({ changeset: "CS-1" }), "POST changesets/CS-1/undo": () => ({ restored: [0], skipped: [] }) });
  await user.click(within(await rowOf()).getByRole("button", { name: "Copy reply" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/reply")?.body).toEqual({}));
  expect(await navigator.clipboard.readText()).toBe(DRAFT);
  expect(await screen.findByText("Copied. Paste it into your reply.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("copying a draft that is already reviewed approves nothing again", async () => {
  const user = userEvent.setup();
  const calls = show([reply({ reply_reviewed: true })]);
  await user.click(within(await rowOf()).getByRole("button", { name: "Copy reply" }));
  expect(await navigator.clipboard.readText()).toBe(DRAFT);
  expect(calls.some((c) => c.route === "POST actions/ACT-1/reply")).toBe(false);
});

test("every copy is kept as copied, a reviewed draft's included, so the message sent can be matched to it", async () => {
  const user = userEvent.setup();
  const calls = show([reply({ reply_reviewed: true })], { "POST replies/ACT-1/copied": () => ({ id: "COPY-1" }) });
  await user.click(within(await rowOf()).getByRole("button", { name: "Copy reply" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST replies/ACT-1/copied")).toHaveLength(1));
});

test("if the copy can't be kept the draft is still on the clipboard and nothing is shown as wrong", async () => {
  const user = userEvent.setup();
  show([reply({ reply_reviewed: true })]);
  await user.click(within(await rowOf()).getByRole("button", { name: "Copy reply" }));
  expect(await navigator.clipboard.readText()).toBe(DRAFT);
  expect(await screen.findByText("Copied. Paste it into your reply.")).toBeInTheDocument();
});

test("if the browser blocks copying, nothing is approved and the person is told", async () => {
  const user = userEvent.setup();
  const calls = show([reply()]);
  const row = await rowOf();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(within(row).getByRole("button", { name: "Copy reply" }));
  expect(await screen.findByText(/blocked copying/)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST actions/ACT-1/reply")).toBe(false);
});

test("the menu has No reply needed, Answered another way and Edit, and nothing else", async () => {
  const user = userEvent.setup();
  show([reply()]);
  await menuOf(user, await rowOf());
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["No reply needed", "Answered another way", "Edit reply"]);
});

test("No reply needed drops it with the reason at once, and Undo brings it back", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], { "POST actions/ACT-1/drop": () => ({ changeset: "CS-2" }), "POST changesets/CS-2/undo": () => ({ restored: [0], skipped: [] }) });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "No reply needed" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/drop")?.body).toEqual({ reason: "No reply needed" }));
  expect(await screen.findByText("Dropped: no reply needed.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-2/undo")).toBe(true));
});

test("Answered another way opens a short form with the cursor in the words and closes it with them", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], { "POST replies/ACT-1/answered": () => ({ changeset: "CS-3" }) });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Answered another way" }));
  const words = await screen.findByLabelText("How was it answered? (optional)");
  await waitFor(() => expect(words).toHaveFocus());
  await user.type(words, "We settled it on the phone");
  await user.click(screen.getByRole("button", { name: "Close it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST replies/ACT-1/answered")?.body).toEqual({ note: "We settled it on the phone" }));
  expect(await screen.findByText("Closed: answered another way.")).toBeInTheDocument();
});

test("the words are optional: closing with none sends none, and Cancel sends nothing", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], { "POST replies/ACT-1/answered": () => ({ changeset: "CS-4" }) });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Answered another way" }));
  await user.click(await screen.findByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("How was it answered? (optional)")).toBeNull();
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Answered another way" }));
  await user.click(await screen.findByRole("button", { name: "Close it" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST replies/ACT-1/answered").map((c) => c.body)).toEqual([{}]));
});

test("Edit puts the cursor in the draft and saves the person's own words as their reply", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], { "POST actions/ACT-1/reply": () => ({ changeset: "CS-5" }) });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Edit reply" }));
  const box = await screen.findByLabelText("Your reply");
  await waitFor(() => expect(box).toHaveFocus());
  expect(box).toHaveValue(DRAFT);
  await user.clear(box);
  await user.type(box, "Hi, the proofs ship on the third.");
  await user.click(screen.getByRole("button", { name: "Save reply" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/reply")?.body).toEqual({ text: "Hi, the proofs ship on the third." }));
});

test("with no draft the line says why, and Write reply opens the person's own", async () => {
  const user = userEvent.setup();
  const calls = show([reply({ reply: null })], { "POST actions/ACT-1/reply": () => ({ changeset: "CS-6" }) });
  const row = await rowOf();
  expect(within(row).getByText("No draft: nothing recorded holds the answer.")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Write reply" }));
  const box = await screen.findByLabelText("Your reply");
  await waitFor(() => expect(box).toHaveFocus());
  await user.type(box, "On it.");
  await user.click(screen.getByRole("button", { name: "Save reply" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/reply")?.body).toEqual({ text: "On it." }));
  await menuOf(user, row);
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["No reply needed", "Answered another way"]);
});
