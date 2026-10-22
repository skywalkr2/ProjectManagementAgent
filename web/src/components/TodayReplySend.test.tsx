import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { actFixture } from "../lib/acts-fixtures";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// A reply the person owes, when the account the message came in on can act (design 6.12, 6.35): Send reply is the one button, and
// drafts the drafted reply as an act that opens in Waiting to go out for the person's yes. Copy reply moves into the menu with
// the other ways to deal with the message. When the account can't act, Copy reply stays the one button, as before.

type Line = S["QueueLineView"];

const DRAFT = "The interior proofs ship on November 3.";
const MESSAGE = "SRC-4";

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
  window.location.hash = "";
});

const TITLE = "Reply to Ana Cole: Interior proofs";
const rowOf = async (title = TITLE) => (await screen.findByRole("group", { name: title })) as HTMLElement;
const menuOf = async (user: ReturnType<typeof userEvent.setup>, row: HTMLElement) => user.click(within(row).getByRole("button", { name: /More actions for/ }));


function options(over: Partial<S["ActOptionsView"]> = {}): S["ActOptionsView"] {
  return {
    record: MESSAGE,
    kind: "message",
    account: "mailbox:work",
    account_label: "Work mail",
    acting: true,
    can_act: true,
    channel_label: "Mailbox",
    actions: ["reply", "reply_all", "forward", "archive", "move", "label", "mark_read"],
    answers: [],
    propose_refusal: null,
    folder_source: "work",
    ...over,
  };
}


test("with an account that can act, Send reply is the one button and Copy reply is in the menu", async () => {
  const user = userEvent.setup();
  show([reply()], { "GET acts/options?record=ACT-1": () => options() });
  const row = await rowOf();
  expect(await within(row).findByRole("button", { name: "Send reply" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: "Copy reply" })).toBeNull();
  await menuOf(user, row);
  const items = (await screen.findAllByRole("menuitem")).map((x) => x.textContent);
  expect(items).toEqual(["Copy reply", "Reply to everyone", "Forward", "Archive", "Move to…", "Label…", "Mark as read", "No reply needed", "Answered another way", "Edit reply"]);
});

test("Send reply drafts the drafted reply to the message that asked, with its subject, and opens it in Waiting to go out", async () => {
  const user = userEvent.setup();
  const calls = show([reply()], {
    "GET acts/options?record=ACT-1": () => options(),
    "POST acts": () => ({ ...actFixture({ id: "XACT-5", action: "reply" }) }),
  });
  await user.click(await within(await rowOf()).findByRole("button", { name: "Send reply" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST acts")).toHaveLength(1));
  expect(calls.find((c) => c.route === "POST acts")?.body).toEqual({
    kind: "message",
    action: "reply",
    in_reply_to: MESSAGE,
    recipients: [],
    parts: { subject: "Re: Interior proofs", body: DRAFT },
  });
  await waitFor(() => expect(window.location.hash).toBe("#work/outgoing"));
  expect(calls.some((c) => c.route === "POST actions/ACT-1/reply")).toBe(false); // nothing was copied or marked reviewed
});

test("Copy reply from the menu still copies the draft", async () => {
  const user = userEvent.setup();
  show([reply({ reply_reviewed: true })], { "GET acts/options?record=ACT-1": () => options() });
  const row = await rowOf();
  await within(row).findByRole("button", { name: "Send reply" });
  await menuOf(user, row);
  await user.click(await screen.findByRole("menuitem", { name: "Copy reply" }));
  expect(await navigator.clipboard.readText()).toBe(DRAFT);
});

test("with an account that can't act, Copy reply stays the one button and the other acts are in the menu", async () => {
  const user = userEvent.setup();
  show([reply()], { "GET acts/options?record=ACT-1": () => options({ acting: false, can_act: false }) });
  const row = await rowOf();
  expect(within(row).getByRole("button", { name: "Copy reply" })).toBeInTheDocument();
  await waitFor(() => expect(within(row).queryByRole("button", { name: "Send reply" })).toBeNull());
  await menuOf(user, row);
  expect((await screen.findAllByRole("menuitem")).map((x) => x.textContent)).toContain("Forward");
});

test("with no draft there is no Send reply: the person writes one first", async () => {
  show([reply({ reply: null })], { "GET acts/options?record=ACT-1": () => options() });
  const row = await rowOf();
  expect(within(row).getByRole("button", { name: "Write reply" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: "Send reply" })).toBeNull();
});

test("a message that came in no account way has no acts, and the line is as it was", async () => {
  show([reply()]);
  const row = await rowOf();
  expect(within(row).getByRole("button", { name: "Copy reply" })).toBeInTheDocument();
});
