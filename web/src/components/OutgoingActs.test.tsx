import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Act } from "../lib/acts";
import { actFixture, recipient } from "../lib/acts-fixtures";
import { besidePane, fakeApi, renderApp, type Routes } from "../test-utils";
import { WaitingToGoOut } from "./WaitingToGoOut";

// What each kind of act says it does (design 6.12, 7.4): the list line and the detail in words for a reply, a change to the
// mail, an answer to an invitation and an event, with each saved message listed and counted; why Copy carries an act; the undo
// toast after a send and Take back in the menu of what went out, each saying whether it worked.

afterEach(() => vi.unstubAllGlobals());

function show(acts: Act[], extra: Routes = {}, options: { unnamed?: boolean } = {}) {
  besidePane();
  const calls = fakeApi({ "GET acts": () => ({ acts }), ...extra });
  renderApp(<WaitingToGoOut onView={vi.fn()} />, {}, options);
  return calls;
}

const about = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `SRC-${i + 1}`, kind: "message" as const, title: `Subject ${i + 1}`, sender: `sender${i + 1}@example.com`, when: `2026-10-0${i + 1}`, end: null }));

const mailbox = (action: string, n: number, over: Partial<Act> = {}) =>
  actFixture({ kind: "mailbox", action, parts: {}, recipients: [], about: about(n), channel_label: "Mailbox", ...over });

const invitation = { id: "EVT-1", kind: "event" as const, title: "Planning session", sender: null, when: "2026-11-02T09:00:00+00:00", end: "2026-11-02T10:00:00+00:00" };
const answer = (how: Act["answer"], over: Partial<Act> = {}) => actFixture({ kind: "calendar", action: "answer", answer: how, parts: {}, recipients: [recipient({ name: "The Organizer", address: "organizer@example.com" })], about: [invitation], ...over });

const rowOf = async (title: string) => within(await screen.findByRole("list", { name: "Waiting to go out" })).getByText(title).closest("li") as HTMLElement;

describe("the list line says what the act does", () => {
  test.each([
    [mailbox("archive", 3), "Archive 3 messages"],
    [mailbox("archive", 1), "Archive 1 message"],
    [mailbox("move", 2, { folder: "Projects" }), "Move 2 messages to Projects"],
    [mailbox("label", 1, { label: "Waiting" }), "Label 1 message Waiting"],
    [mailbox("mark_read", 4), "Mark 4 messages as read"],
    [actFixture({ action: "reply" }), "Reply to Ana Example"],
    [actFixture({ action: "forward" }), "Forward to Ana Example"],
    [answer("accepted"), "Answer to Planning session: accept"],
    [answer("tentative"), "Answer to Planning session: maybe"],
    [answer("declined"), "Answer to Planning session: decline"],
    [answer("propose", { proposed_start: "2026-11-03T14:00:00+00:00", proposed_end: "2026-11-03T15:00:00+00:00" }), "Answer to Planning session: propose another time"],
    [actFixture({ kind: "calendar", action: "create", title: "Review", calendar: "Work", parts: { title: "Review" }, recipients: [] }), "Event on your calendar: Review"],
  ])("%#: %s", async (act, title) => {
    show([act]);
    expect(await rowOf(title)).toBeInTheDocument();
  });
});

describe("the detail", () => {
  test("a mailbox act lists each message with its sender, subject and date, and counts them", async () => {
    show([mailbox("move", 3, { folder: "Projects" })]);
    const pane = await screen.findByRole("complementary", { name: "Move 3 messages to Projects" });
    const list = within(pane).getByRole("region", { name: "The messages" });
    expect(within(list).getByText("This changes 3 messages.")).toBeInTheDocument();
    expect(within(list).getAllByRole("listitem").map((x) => x.textContent)).toEqual([
      "sender1@example.com: Subject 1, 2026-10-01",
      "sender2@example.com: Subject 2, 2026-10-02",
      "sender3@example.com: Subject 3, 2026-10-03",
    ]);
    expect(within(pane).getByText("Folder: Projects")).toBeInTheDocument();
    expect(within(pane).queryByRole("region", { name: "What will go" })).toBeNull(); // a mailbox act has no words of its own
  });

  test("one message is counted as one, and a label is shown", async () => {
    show([mailbox("label", 1, { label: "Waiting" })]);
    const pane = await screen.findByRole("complementary");
    expect(within(pane).getByText("This changes 1 message.")).toBeInTheDocument();
    expect(within(pane).getByText("Label: Waiting")).toBeInTheDocument();
  });

  test("an answer names the invitation, the answer and, for a proposal, the proposed time, and goes to the organizer", async () => {
    show([answer("propose", { proposed_start: "2026-11-03T14:00:00+00:00", proposed_end: "2026-11-03T15:00:00+00:00" })]);
    const pane = await screen.findByRole("complementary", { name: "Answer to Planning session: propose another time" });
    const event = within(pane).getByRole("region", { name: "The event" });
    expect(within(event).getByText(/The invitation: Planning session, 2026-11-02T09:00:00\+00:00 to 2026-11-02T10:00:00\+00:00/)).toBeInTheDocument();
    expect(within(event).getByText("Your answer: propose another time")).toBeInTheDocument();
    expect(within(event).getByText("Proposed time: 2026-11-03T14:00:00+00:00 to 2026-11-03T15:00:00+00:00")).toBeInTheDocument();
    expect(within(pane).getByText("To: The Organizer, organizer@example.com")).toBeInTheDocument();
  });

  test("an event the app creates shows its title, time and alarm", async () => {
    show([
      actFixture({
        kind: "calendar",
        action: "create",
        title: "Review",
        start: "2026-11-05T10:00:00+00:00",
        end: "2026-11-05T11:00:00+00:00",
        alarm_minutes: 15,
        calendar: "Work",
        parts: {},
        recipients: [],
      }),
    ]);
    const pane = await screen.findByRole("complementary", { name: "Event on your calendar: Review" });
    expect(within(pane).getByText("Title: Review")).toBeInTheDocument();
    expect(within(pane).getByText("When: 2026-11-05T10:00:00+00:00 to 2026-11-05T11:00:00+00:00")).toBeInTheDocument();
    expect(within(pane).getByText("Alarm: 15 minutes before")).toBeInTheDocument();
  });

  test("an act Copy carries says why and what to do, in the assistant's name or, while it has none, without it", async () => {
    const copied = mailbox("archive", 1, { channel: "copy", channel_label: "Copy", copied_because: "acting_off", intended_channel: "mailbox", account_label: "Work mail" });
    show([copied]);
    expect(await screen.findByText(/Helper isn't allowed to act on Work mail yet, so you carry this out yourself/)).toBeInTheDocument();
  });

  test("while the assistant has no name the reason doesn't use one", async () => {
    show([mailbox("archive", 1, { channel: "copy", channel_label: "Copy", copied_because: "acting_off", account_label: "Work mail" })], {}, { unnamed: true });
    expect(await screen.findByText(/Your assistant isn't allowed to act on Work mail yet/)).toBeInTheDocument();
  });

  test("Copy on a mailbox act puts what it does and the messages on the clipboard, since it has no words", async () => {
    const user = userEvent.setup();
    const copied = mailbox("archive", 2, { channel: "copy", channel_label: "Copy", copied_because: "acting_off" });
    show([copied], { "POST acts/XACT-1/approve": () => ({ id: "XACT-1", status: "approved", reason: null, changeset: "CS-1" }) });
    await user.click(await screen.findByRole("button", { name: "Copy" }));
    await waitFor(async () => expect(await navigator.clipboard.readText()).toContain("Archive 2 messages"));
    const text = await navigator.clipboard.readText();
    expect(text).toContain("sender1@example.com: Subject 1, 2026-10-01");
    expect(text).toContain("sender2@example.com: Subject 2, 2026-10-02");
  });

  test("the confirm for a change to the mail says what it does and that it can be taken back", async () => {
    const user = userEvent.setup();
    show([mailbox("archive", 3)]);
    await user.click(await screen.findByRole("button", { name: "Approve and send" }));
    const dialog = await screen.findByRole("dialog", { name: "Go ahead with this now: Archive 3 messages?" });
    expect(within(dialog).getByText(/You can take it back afterward, where your mail service allows/)).toBeInTheDocument();
  });

  test("the confirm for an answer says what it does, and a send still says it can't be taken back", async () => {
    const user = userEvent.setup();
    show([answer("accepted")]);
    await user.click(await screen.findByRole("button", { name: "Approve and send" }));
    const dialog = await screen.findByRole("dialog", { name: "Go ahead with this now: Answer to Planning session: accept?" });
    expect(within(dialog).getByText(/can't be taken back/)).toBeInTheDocument();
  });
});

describe("after a send", () => {
  const sentResult = { id: "XACT-1", status: "sent", reason: null, changeset: null };
  const send = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(await screen.findByRole("button", { name: "Approve and send" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Send" }));
  };

  test("the toast offers Undo while the act can be taken back, and Undo takes it back and says so", async () => {
    const user = userEvent.setup();
    const calls = show([mailbox("archive", 2)], {
      "POST acts/XACT-1/approve": () => ({ id: "XACT-1", status: "approved", reason: null, changeset: "CS-1" }),
      "POST acts/XACT-1/send": () => sentResult,
      "GET acts/XACT-1": () => mailbox("archive", 2, { status: "sent", undoable: true }),
      "POST acts/XACT-1/undo": () => ({ id: "XACT-1", status: "undone", reason: null, changeset: null }),
    });
    await send(user);
    expect(await screen.findByText("Sent the change to your mail.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST acts/XACT-1/undo")).toBe(true));
    expect(await screen.findByText("Took back the change to your mail.")).toBeInTheDocument();
  });

  test("an act that can't be taken back has no Undo in its toast", async () => {
    const user = userEvent.setup();
    show([answer("accepted")], {
      "POST acts/XACT-1/approve": () => ({ id: "XACT-1", status: "approved", reason: null, changeset: "CS-1" }),
      "POST acts/XACT-1/send": () => sentResult,
      "GET acts/XACT-1": () => answer("accepted", { status: "sent", undoable: false }),
    });
    await send(user);
    expect(await screen.findByText("Sent the answer to Planning session.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  test("when the service won't take it back the person is told why, and it stays sent", async () => {
    const user = userEvent.setup();
    show([mailbox("archive", 1)], {
      "POST acts/XACT-1/approve": () => ({ id: "XACT-1", status: "approved", reason: null, changeset: "CS-1" }),
      "POST acts/XACT-1/send": () => sentResult,
      "GET acts/XACT-1": () => mailbox("archive", 1, { status: "sent", undoable: true }),
      "POST acts/XACT-1/undo": () => ({ id: "XACT-1", status: "sent", reason: "The message is no longer in that folder.", changeset: null }),
    });
    await send(user);
    await user.click(await screen.findByRole("button", { name: "Undo" }));
    expect(await screen.findByText("It couldn't be taken back: The message is no longer in that folder.")).toBeInTheDocument();
  });
});

describe("what went out", () => {
  const went = (over: Partial<Act> = {}) => mailbox("archive", 2, { status: "sent", sent_at: "2026-10-22T09:30:00+00:00", sent_by: "publisher", ...over });

  test("is listed under what waits, newest first, with taken-back ones marked", async () => {
    show([went({ id: "XACT-3", undoable: true }), went({ id: "XACT-2", status: "undone" }), actFixture({ id: "XACT-9" })]);
    const sent = await screen.findByRole("list", { name: "Went out" });
    const rows = within(sent).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Archive 2 messages")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Sent")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Undone")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Went out" })).toBeInTheDocument();
    // what still waits is a list of its own
    expect(within(screen.getByRole("list", { name: "Waiting to go out" })).getAllByRole("listitem")).toHaveLength(1);
  });

  test("Take back is in the menu of an act that can be taken back, and nowhere else", async () => {
    const user = userEvent.setup();
    show([went({ id: "XACT-3", undoable: true }), went({ id: "XACT-2", undoable: false })]);
    const sent = await screen.findByRole("list", { name: "Went out" });
    const rows = within(sent).getAllByRole("listitem");
    expect(within(rows[1]).queryByRole("button", { name: /More actions/ })).toBeNull();
    await user.click(within(rows[0]).getByRole("button", { name: /More actions for/ }));
    expect(await screen.findByRole("menuitem", { name: "Take back" })).toBeInTheDocument();
  });

  test("Take back asks the service once and says it is done", async () => {
    const user = userEvent.setup();
    const calls = show([went({ undoable: true })], { "POST acts/XACT-1/undo": () => ({ id: "XACT-1", status: "undone", reason: null, changeset: null }) });
    const row = (await screen.findByRole("list", { name: "Went out" })).querySelector("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /More actions for/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Take back" }));
    await waitFor(() => expect(calls.filter((c) => c.route === "POST acts/XACT-1/undo")).toHaveLength(1));
    expect(await screen.findByText("Took back the change to your mail.")).toBeInTheDocument();
  });

  test("Take back says why when the service refuses, and a refusal kept on the act is shown on its line", async () => {
    const user = userEvent.setup();
    show([went({ undoable: true, undo_failure: { at: "2026-10-22T10:00:00+00:00", kind: "refused", reason: "The folder is gone." } })], {
      "POST acts/XACT-1/undo": () => ({ id: "XACT-1", status: "sent", reason: "The folder is gone.", changeset: null }),
    });
    const row = (await screen.findByRole("list", { name: "Went out" })).querySelector("li") as HTMLElement;
    expect(within(row).getByText(/It couldn't be taken back: The folder is gone\./)).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: /More actions for/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Take back" }));
    expect((await screen.findAllByText(/It couldn't be taken back: The folder is gone\./)).length).toBeGreaterThan(1);
  });

  test("nothing sent means no list of what went out", async () => {
    show([actFixture()]);
    await screen.findByRole("list", { name: "Waiting to go out" });
    expect(screen.queryByRole("heading", { name: "Went out" })).toBeNull();
  });
});
