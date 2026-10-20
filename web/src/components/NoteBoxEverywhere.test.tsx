import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// Every button that acts on a to-do has a note box in its row's menu, so a note typed on any of them reaches the assistant
// with the act (design 7.5). The to-do rows of Follow-ups and Today's rail are tested in NoteBox.test.tsx; these are the
// two lines Today holds: a promise past its date, and a reminder.

type Line = S["QueueLineView"];

const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({
  key: `${kind}:1`,
  group: "risk",
  kind,
  count: 1,
  untrusted: false,
  unpriced: 0,
  actions: [],
  questions: [],
  outcome: {},
  ...over,
});

const chase = line("promise", {
  key: "promise:ACT-1",
  group: "send",
  person: "PER-2",
  person_name: "Robin Sample",
  text: "Send the floor plan",
  subject: "Send the floor plan",
  due: "2026-10-13",
  waiting_days: 3,
  actions: ["ACT-1"],
});
const own = { ...chase, person: null, person_name: null, group: "risk" as const };
const reminder = line("reminder", {
  key: "reminder:ACT-2",
  text: "Send Oren the estimate",
  subject: "Send Oren the estimate",
  actions: ["ACT-2"],
  at: "2026-10-19T14:40:00-04:00",
  late: false,
  snoozes: [{ choice: "in 1 hour", at: "2026-10-19T15:40:00-04:00" }],
});

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

async function typeNote(user: ReturnType<typeof userEvent.setup>, row: HTMLElement, note: string, send?: string) {
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Add a note" }));
  const box = await screen.findByRole("textbox", { name: /note/i });
  await waitFor(() => expect(box).toHaveFocus());
  await user.type(box, note);
  if (send) await user.click(screen.getByRole("button", { name: send }));
  else await user.keyboard("{Enter}");
}

const title = `Chase Robin Sample: Send the floor plan, due ${day("2026-10-13")}`;

test("a promise someone else owes: a note goes with Followed up, the line's own act, on the same route", async () => {
  const user = userEvent.setup();
  const calls = show([chase], { "POST followups/PER-2/actions/ACT-1/followed-up": () => ({ on: "2026-10-16", previous_told: null, request: "R-1" }) });
  await typeNote(user, (await screen.findByRole("group", { name: title })) as HTMLElement, "Left a voicemail");
  await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-2/actions/ACT-1/followed-up")?.body).toEqual({ note: "Left a voicemail" }));
  expect(await screen.findByText(/the assistant will read it|Helper reads it|read your note/i)).toBeInTheDocument();
});

test("the same note box can send it with Done instead", async () => {
  const user = userEvent.setup();
  const calls = show([chase], { "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: null }) });
  await typeNote(user, (await screen.findByRole("group", { name: title })) as HTMLElement, "It went out Monday", "Done");
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "done", note: "It went out Monday" }));
});

test("the person's own promise: a note goes with Done", async () => {
  const user = userEvent.setup();
  const calls = show([own], { "POST actions/ACT-1/status": () => ({ ok: "ACT-1", request: null }) });
  await typeNote(user, (await screen.findByRole("group", { name: /Send the floor plan/ })) as HTMLElement, "Sent it by post");
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/status")?.body).toEqual({ status: "done", note: "Sent it by post" }));
});

test("a reminder: a note goes with Done", async () => {
  const user = userEvent.setup();
  const calls = show([reminder], { "POST actions/ACT-2/status": () => ({ ok: "ACT-2", request: null }) });
  await typeNote(user, (await screen.findByRole("group", { name: /Send Oren the estimate/ })) as HTMLElement, "Called instead");
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-2/status")?.body).toEqual({ status: "done", note: "Called instead" }));
});

test("with no note the buttons send what they always did", async () => {
  const user = userEvent.setup();
  const calls = show([reminder], { "POST actions/ACT-2/status": () => ({ ok: "ACT-2", request: null }) });
  await user.click(within((await screen.findByRole("group", { name: /Send Oren the estimate/ })) as HTMLElement).getByRole("button", { name: "Done" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-2/status")?.body).toEqual({ status: "done" }));
});
