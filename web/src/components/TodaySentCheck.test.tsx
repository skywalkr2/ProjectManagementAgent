import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, Refuse, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// A message the person copied that no sent message has matched (design 6.35, 7.7): one line, "Did your message to Ana go out?",
// with Yes, another way as its one button and Not sent and Still to send in its menu. Each answer is the person's own, with
// Undo, which takes back what the answer returned. Copying a drafted reply keeps the copy.

type Line = S["QueueLineView"];

function check(over: Partial<Line> = {}): Line {
  return {
    key: "sent_check:COPY-1",
    group: "send",
    kind: "sent_check",
    count: 1,
    untrusted: false,
    unpriced: 0,
    actions: [],
    questions: ["Q-1"],
    outcome: {},
    person: "PER-2",
    person_name: "Ana Cole",
    sent_copy: "COPY-1",
    ...over,
  };
}

const SETTLED: S["CopySettled"] = { settled: null, ask_again_at: null, sent_at: { "Q-1": "2026-10-17T10:00:00Z" }, told: {} };

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

const TITLE = "Did your message to Ana Cole go out?";
const rowOf = async () => (await screen.findByRole("group", { name: TITLE })) as HTMLElement;
const menuOf = async (user: ReturnType<typeof userEvent.setup>, row: HTMLElement) => user.click(within(row).getByRole("button", { name: /More actions for/ }));

test("the line names who the message was to and has one button, with the other two answers in its menu", async () => {
  const user = userEvent.setup();
  show([check()]);
  const row = await rowOf();
  expect(within(row).getByText("Did it go out?")).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Yes, another way" })).toBeInTheDocument();
  await menuOf(user, row);
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Not sent", "Still to send"]);
});

test("a message to nobody known says someone", async () => {
  show([check({ person: null, person_name: null })]);
  expect(await screen.findByRole("group", { name: "Did your message to someone go out?" })).toBeInTheDocument();
});

test("Yes, another way settles it at once, and Undo gives back what the answer returned", async () => {
  const user = userEvent.setup();
  const calls = show([check()], {
    "POST copies/COPY-1/settle": () => SETTLED,
    "POST copies/COPY-1/unsettle": () => ({ ok: "COPY-1" }),
  });
  await user.click(within(await rowOf()).getByRole("button", { name: "Yes, another way" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST copies/COPY-1/settle")?.body).toEqual({ how: "sent_another_way" }));
  expect(await screen.findByText("Noted: it went out another way.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST copies/COPY-1/unsettle")?.body).toEqual(SETTLED));
});

test("Not sent puts the questions back and Undo marks them sent again", async () => {
  const user = userEvent.setup();
  const calls = show([check()], {
    "POST copies/COPY-1/settle": () => SETTLED,
    "POST copies/COPY-1/unsettle": () => ({ ok: "COPY-1" }),
  });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Not sent" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST copies/COPY-1/settle")?.body).toEqual({ how: "not_sent" }));
  expect(await screen.findByText("Noted: it was not sent. Its questions are open again.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST copies/COPY-1/unsettle")).toBe(true));
});

test("Still to send asks again later, and Undo asks again now", async () => {
  const user = userEvent.setup();
  const calls = show([check()], {
    "POST copies/COPY-1/settle": () => SETTLED,
    "POST copies/COPY-1/unsettle": () => ({ ok: "COPY-1" }),
  });
  await menuOf(user, await rowOf());
  await user.click(screen.getByRole("menuitem", { name: "Still to send" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST copies/COPY-1/settle")?.body).toEqual({ how: "still_to_send" }));
  expect(await screen.findByText("Noted: you will be asked again.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST copies/COPY-1/unsettle")).toBe(true));
});

test("a refused answer says so and changes nothing", async () => {
  const user = userEvent.setup();
  const calls = show([check()], { "POST copies/COPY-1/settle": () => new Refuse(409, "that copy is gone") });
  await user.click(within(await rowOf()).getByRole("button", { name: "Yes, another way" }));
  expect(await screen.findByText(/that copy is gone/)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST copies/COPY-1/unsettle")).toBe(false);
});
