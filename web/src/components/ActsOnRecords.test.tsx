import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { actFixture } from "../lib/acts-fixtures";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { RecordPage } from "./RecordPage";

// What the person does about a saved message or an invitation (design 6.12): Reply, Reply to everyone, Forward, Archive, Move to,
// Label and Mark as read on a message; Accept, Maybe, Decline and Propose a time on an invitation. Each drafts an act through
// POST acts and opens it in Waiting to go out; nothing is sent from here. A plain mailbox can't propose a time, and says why.

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const MESSAGE = "SRC-1";
const ENTRY = "EVT-1";
const SOURCE = "work-mail";

function options(over: Partial<S["ActOptionsView"]> = {}): S["ActOptionsView"] {
  return {
    record: MESSAGE,
    kind: "message",
    account: `mailbox:${SOURCE}`,
    account_label: "Work mail",
    acting: true,
    can_act: true,
    channel_label: "Mailbox",
    actions: ["reply", "reply_all", "forward", "archive", "move", "label", "mark_read"],
    answers: [],
    propose_refusal: null,
    folder_source: SOURCE,
    ...over,
  };
}

function entryOptions(over: Partial<S["ActOptionsView"]> = {}): S["ActOptionsView"] {
  return options({ record: ENTRY, kind: "event", actions: [], answers: ["accepted", "tentative", "declined", "propose"], folder_source: null, ...over });
}

function page(kind: "source" | "event", fields: Record<string, unknown>, extra: Routes = {}): Routes {
  const id = kind === "source" ? MESSAGE : ENTRY;
  return {
    [`GET record?kind=${kind}&id=${id}`]: () => ({ kind, id, version: 1, fields: { id, ...fields }, long_text: [] }),
    [`GET kinds/${kind}`]: () => ({ kind, fields: [{ name: "title", description: "", type: "text", required: true, editable: false }] }),
    "GET people": () => [
      { id: "PER-2", name: "Ana Example", how_to_reach: { email: "ana@example.com" }, is_pm: false },
      { id: "PER-3", name: "Ben Example", how_to_reach: {}, is_pm: false },
      { id: "PER-1", name: "Pat Example", how_to_reach: { email: "pat@example.com" }, is_pm: true },
    ],
    "GET projects": () => [],
    ...extra,
  };
}

const drafted = (over: Partial<S["ActView"]> = {}) => actFixture({ id: "XACT-7", ...over });

function open(kind: "source" | "event", fields: Record<string, unknown>, extra: Routes = {}) {
  const calls = fakeApi(page(kind, fields, extra));
  renderApp(<RecordPage kind={kind} id={kind === "source" ? MESSAGE : ENTRY} onBack={() => {}} />);
  return calls;
}

const post = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST acts");
const menu = async (user: ReturnType<typeof userEvent.setup>, name = "Choose") => user.click(await screen.findByRole("button", { name: new RegExp(`More actions for ${name}`) }));

describe("a saved message", () => {
  const message = { title: "The proofs" };
  const routes = (extra: Routes = {}): Routes => ({ [`GET acts/options?record=${MESSAGE}`]: () => options(), ...extra });

  test("offers Reply, and the rest of what the account does are in its menu", async () => {
    const user = userEvent.setup();
    open("source", message, routes());
    expect(await screen.findByRole("button", { name: "Reply" })).toBeInTheDocument();
    await menu(user, "The proofs");
    const items = (await screen.findAllByRole("menuitem")).map((x) => x.textContent);
    expect(items).toEqual(["Reply to everyone", "Forward", "Archive", "Move to…", "Label…", "Mark as read"]);
  });

  test("offers nothing for what the account can't do, and nothing at all for a record that isn't a saved message", async () => {
    const user = userEvent.setup();
    open("source", message, routes({ [`GET acts/options?record=${MESSAGE}`]: () => options({ actions: ["reply", "reply_all", "forward"] }) }));
    await screen.findByRole("button", { name: "Reply" });
    await menu(user, "The proofs");
    expect((await screen.findAllByRole("menuitem")).map((x) => x.textContent)).toEqual(["Reply to everyone", "Forward"]);
  });

  test("a record the server says is no message has no acts", async () => {
    open("source", message, routes({ [`GET acts/options?record=${MESSAGE}`]: () => options({ kind: "missing", actions: [] }) }));
    await screen.findByRole("heading", { level: 1, name: "The proofs" });
    expect(screen.queryByRole("button", { name: "Reply" })).toBeNull();
  });

  test("Reply asks for the words with the cursor in them, then drafts the reply with the subject and opens it in Waiting to go out", async () => {
    const user = userEvent.setup();
    const calls = open("source", message, routes({ "POST acts": () => drafted({ action: "reply" }) }));
    await user.click(await screen.findByRole("button", { name: "Reply" }));
    const words = await screen.findByRole("textbox", { name: "Your reply" });
    expect(words).toHaveFocus();
    await user.type(words, "The proofs ship on Monday.");
    await user.click(screen.getByRole("button", { name: "Draft the reply" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({
      kind: "message",
      action: "reply",
      in_reply_to: MESSAGE,
      recipients: [],
      parts: { subject: "Re: The proofs", body: "The proofs ship on Monday." },
    });
    expect(await screen.findByText(/Drafted the reply to Ana Example/)).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#work/outgoing"));
    expect(screen.queryByRole("textbox", { name: "Your reply" })).toBeNull();
  });

  test("a subject that already starts with Re: isn't given a second one", async () => {
    const user = userEvent.setup();
    const calls = open("source", { title: "RE: The proofs" }, routes({ "POST acts": () => drafted() }));
    await user.click(await screen.findByRole("button", { name: "Reply" }));
    await user.type(await screen.findByRole("textbox", { name: "Your reply" }), "Thanks.");
    await user.click(screen.getByRole("button", { name: "Draft the reply" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect((post(calls)[0].body as { parts: { subject: string } }).parts.subject).toBe("RE: The proofs");
  });

  test("Reply to everyone drafts a reply to everyone on the message", async () => {
    const user = userEvent.setup();
    const calls = open("source", message, routes({ "POST acts": () => drafted({ action: "reply_all" }) }));
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Reply to everyone" }));
    await user.type(await screen.findByRole("textbox", { name: "Your reply" }), "Thanks, all.");
    await user.click(screen.getByRole("button", { name: "Draft the reply" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toMatchObject({ kind: "message", action: "reply_all", in_reply_to: MESSAGE, recipients: [] });
  });

  test("Forward is a pick list of the people with an email address, and then the person's own note", async () => {
    const user = userEvent.setup();
    const calls = open("source", message, routes({ "POST acts": () => drafted({ action: "forward" }) }));
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Forward" }));
    const who = await screen.findByRole("combobox", { name: "Forward to" });
    expect(who).toHaveFocus();
    expect(within(who).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a person…", "Ana Example"]);
    await user.selectOptions(who, "PER-2");
    await user.type(screen.getByRole("textbox", { name: "Your note" }), "For your records.");
    await user.click(screen.getByRole("button", { name: "Draft the forward" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toMatchObject({
      kind: "message",
      action: "forward",
      in_reply_to: MESSAGE,
      recipients: [{ person: "PER-2", kind: "email" }],
      parts: { subject: "Fwd: The proofs", body: "For your records." },
    });
  });

  test.each([
    ["Archive", "archive"],
    ["Mark as read", "mark_read"],
  ])("%s drafts the change to the message at once", async (name, action) => {
    const user = userEvent.setup();
    const calls = open("source", message, routes({ "POST acts": () => drafted({ kind: "mailbox", action, about: [{ id: MESSAGE, kind: "message", title: "The proofs" }], parts: {} }) }));
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({ kind: "mailbox", action, about: [MESSAGE] });
    await waitFor(() => expect(window.location.hash).toBe("#work/outgoing"));
  });

  test("Move to is a pick list of the mailbox's own folders", async () => {
    const user = userEvent.setup();
    const calls = open(
      "source",
      message,
      routes({
        [`GET watch/${SOURCE}/folders`]: () => ({ folders: ["Inbox", "Projects", "Receipts"], sent: null, taken: [] }),
        "POST acts": () => drafted({ kind: "mailbox", action: "move", folder: "Projects", parts: {} }),
      }),
    );
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Move to…" }));
    const folder = await screen.findByRole("combobox", { name: "Move to folder" });
    expect(folder).toHaveFocus();
    await waitFor(() => expect(within(folder).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a folder", "Inbox", "Projects", "Receipts"]));
    expect(screen.getByRole("button", { name: "Draft the move" })).toBeDisabled();
    await user.selectOptions(folder, "Projects");
    await user.click(screen.getByRole("button", { name: "Draft the move" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({ kind: "mailbox", action: "move", about: [MESSAGE], folder: "Projects" });
  });

  test("Label asks for the label with the cursor in it", async () => {
    const user = userEvent.setup();
    const calls = open("source", message, routes({ "POST acts": () => drafted({ kind: "mailbox", action: "label", label: "Waiting", parts: {} }) }));
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Label…" }));
    const label = await screen.findByRole("textbox", { name: "Label" });
    expect(label).toHaveFocus();
    await user.type(label, "Waiting");
    await user.click(screen.getByRole("button", { name: "Draft the label" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({ kind: "mailbox", action: "label", about: [MESSAGE], label: "Waiting" });
  });

  test("when acting is off, Copy carries it and the toast says the person carries it out", async () => {
    const user = userEvent.setup();
    open(
      "source",
      message,
      routes({
        [`GET acts/options?record=${MESSAGE}`]: () => options({ acting: false, can_act: false }),
        "POST acts": () => drafted({ channel: "copy", copied_because: "acting_off", intended_channel: "mailbox" }),
      }),
    );
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Archive" }));
    expect(await screen.findByText(/You carry it out yourself/)).toBeInTheDocument();
  });

  test("a draft the account can't carry is refused with its reason, and the form stays for the person to change it", async () => {
    const user = userEvent.setup();
    open("source", message, routes({ "POST acts": () => new Refuse(409, "the channel mailbox can't label for a mailbox act: it can archive") }));
    await menu(user, "The proofs");
    await user.click(await screen.findByRole("menuitem", { name: "Label…" }));
    await user.type(await screen.findByRole("textbox", { name: "Label" }), "Waiting");
    await user.click(screen.getByRole("button", { name: "Draft the label" }));
    expect(await screen.findByText(/can't label for a mailbox act/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Label" })).toHaveValue("Waiting");
    expect(window.location.hash).not.toBe("#work/outgoing");
  });
});

describe("an invitation", () => {
  const entry = { title: "Planning session", invitation: true };
  const routes = (extra: Routes = {}): Routes => ({ [`GET acts/options?record=${ENTRY}`]: () => entryOptions(), ...extra });

  test("offers Accept, with Maybe, Decline and Propose a time in its menu", async () => {
    const user = userEvent.setup();
    open("event", entry, routes());
    expect(await screen.findByRole("button", { name: "Accept" })).toBeInTheDocument();
    await menu(user, "the invitation's answers");
    expect((await screen.findAllByRole("menuitem")).map((x) => x.textContent)).toEqual(["Maybe", "Decline", "Propose a time…"]);
  });

  test.each([
    ["Accept", "accepted"],
    ["Maybe", "tentative"],
    ["Decline", "declined"],
  ])("%s drafts the answer to the organizer and opens it in Waiting to go out", async (name, answer) => {
    const user = userEvent.setup();
    const calls = open("event", entry, routes({ "POST acts": () => drafted({ kind: "calendar", action: "answer", answer: answer as S["ActView"]["answer"], recipients: [], parts: {} }) }));
    if (name === "Accept") await user.click(await screen.findByRole("button", { name }));
    else {
      await menu(user, "the invitation's answers");
      await user.click(await screen.findByRole("menuitem", { name }));
    }
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({ kind: "calendar", action: "answer", about: [ENTRY], answer });
    await waitFor(() => expect(window.location.hash).toBe("#work/outgoing"));
  });

  const slots = {
    slots: [
      { start: "2026-11-03T14:00:00+00:00", end: "2026-11-03T15:00:00+00:00" },
      { start: "2026-11-04T09:00:00+00:00", end: "2026-11-04T10:00:00+00:00" },
    ],
  };

  test("Propose a time offers the free times of the working week, and the one picked is what is proposed", async () => {
    const user = userEvent.setup();
    const calls = open(
      "event",
      entry,
      routes({ [`GET acts/free-slots?about=${ENTRY}`]: () => slots, "POST acts": () => drafted({ kind: "calendar", action: "answer", answer: "propose", recipients: [], parts: {} }) }),
    );
    await menu(user, "the invitation's answers");
    await user.click(await screen.findByRole("menuitem", { name: "Propose a time…" }));
    const group = await screen.findByRole("group", { name: "Free times in your working week" });
    const choices = within(group).getAllByRole("radio");
    expect(choices).toHaveLength(2);
    expect(choices[0]).toHaveFocus();
    await user.click(choices[1]);
    await user.click(screen.getByRole("button", { name: "Draft the proposal" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    expect(post(calls)[0].body).toEqual({
      kind: "calendar",
      action: "answer",
      about: [ENTRY],
      answer: "propose",
      proposed_start: "2026-11-04T09:00:00+00:00",
      proposed_end: "2026-11-04T10:00:00+00:00",
    });
  });

  test("a time can be typed instead, and an end that doesn't come after the start is refused on the spot", async () => {
    const user = userEvent.setup();
    const calls = open(
      "event",
      entry,
      routes({ [`GET acts/free-slots?about=${ENTRY}`]: () => ({ slots: [] }), "POST acts": () => drafted({ kind: "calendar", action: "answer", answer: "propose", recipients: [], parts: {} }) }),
    );
    await menu(user, "the invitation's answers");
    await user.click(await screen.findByRole("menuitem", { name: "Propose a time…" }));
    expect(await screen.findByText(/No free time was found/)).toBeInTheDocument();
    const start = screen.getByLabelText("Starts");
    await waitFor(() => expect(start).toHaveFocus());
    await user.type(start, "2026-11-05T10:00");
    await user.type(screen.getByLabelText("Ends"), "2026-11-05T09:00");
    await user.click(screen.getByRole("button", { name: "Draft the proposal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Pick a free time, or type a start and an end that comes after it.");
    expect(post(calls)).toHaveLength(0);
    const end = screen.getByLabelText("Ends");
    await user.clear(end);
    await user.type(end, "2026-11-05T11:00");
    await user.click(screen.getByRole("button", { name: "Draft the proposal" }));
    await waitFor(() => expect(post(calls)).toHaveLength(1));
    const sent = post(calls)[0].body as { proposed_start: string; proposed_end: string };
    expect(new Date(sent.proposed_end).getTime() - new Date(sent.proposed_start).getTime()).toBe(3_600_000);
  });

  test("a plain mailbox can't propose: the choice isn't offered, and the screen says why", async () => {
    const user = userEvent.setup();
    open("event", entry, routes({ [`GET acts/options?record=${ENTRY}`]: () => entryOptions({ answers: ["accepted", "tentative", "declined"], propose_refusal: "a mailbox can only accept" }) }));
    expect(await screen.findByRole("button", { name: "Accept" })).toBeInTheDocument();
    await menu(user, "the invitation's answers");
    expect((await screen.findAllByRole("menuitem")).map((x) => x.textContent)).toEqual(["Maybe", "Decline"]);
    expect(screen.getByText(/Proposing another time needs a calendar account/)).toBeInTheDocument();
  });

  test("an entry that isn't an invitation has no answers", async () => {
    open("event", { title: "Planning session", invitation: false }, routes());
    await screen.findByRole("heading", { level: 1, name: "Planning session" });
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });
});
