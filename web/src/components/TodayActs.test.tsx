import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Act } from "../lib/acts";
import { actFixture } from "../lib/acts-fixtures";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { Today } from "./Today";

// What went wrong on the way out (design 6.12, 7.7): one Today line for each act that failed ("Sign in to <account> again", or
// the reason), that may or may not have gone out ("Check the Sent folder for the message to Ana", with It was sent and Send it
// again) or whose yes no longer covers it ("Look again at the message to Ana: <what changed>"). Each starts with the verb and
// opens the act in Waiting to go out.

function show(acts: Act[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
    "GET acts": () => ({ acts }),
    "GET today/queue": () => [],
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
  const onView = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { calls, onView };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const failed = (over: Partial<Act> = {}) =>
  actFixture({ status: "failed", failure: { kind: "outage", reason: "The service was down.", at: "2026-10-22T09:00:00Z" }, ...over });
const rowOf = async (name: string) => (await screen.findByRole("listitem", { name })) as HTMLElement;

test("nothing shows for acts that are waiting for a yes, sent or approved", async () => {
  show([actFixture(), actFixture({ id: "XACT-2", status: "approved" }), actFixture({ id: "XACT-3", status: "sent" })]);
  await screen.findByRole("heading", { level: 1 });
  await waitFor(() => expect(screen.queryByText(/Check the Sent folder|Look again at|which didn't go out/)).toBeNull());
});

test("a failure is one line that starts with the verb and says why, and opens the message in Waiting to go out", async () => {
  const user = userEvent.setup();
  const { onView } = show([failed()]);
  const row = await rowOf("Look at the message to Ana Example, which didn't go out: The service was down.");
  await user.click(within(row).getByRole("button", { name: "Open" }));
  expect(onView).toHaveBeenLastCalledWith("work/outgoing");
});

test("a withdrawn sign-in says which account to sign in to again, in the channel's words", async () => {
  show([failed({ failure: { kind: "auth", reason: "Sign in to Work mail again", at: "2026-10-22T09:00:00Z" } })]);
  expect(await rowOf("Sign in to Work mail again")).toBeInTheDocument();
});

test("an unsure act is a line with It was sent as its button and Send it again in its menu", async () => {
  const user = userEvent.setup();
  show([actFixture({ status: "uncertain", why: ["lost_answer"] })]);
  const row = await rowOf("Check the Sent folder for the message to Ana Example");
  expect(within(row).getByRole("button", { name: "It was sent" })).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  expect(await screen.findByRole("menuitem", { name: "Send it again" })).toBeInTheDocument();
});

test("It was sent is the person's answer with Undo, and needs no confirm", async () => {
  const user = userEvent.setup();
  const { calls } = show([actFixture({ status: "uncertain" })], {
    "POST acts/XACT-1/settle": () => ({ id: "XACT-1", status: "sent", reason: null, changeset: "CS-3" }),
    "POST changesets/CS-3/undo": () => ({}),
  });
  const row = await rowOf("Check the Sent folder for the message to Ana Example");
  await user.click(within(row).getByRole("button", { name: "It was sent" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST acts/XACT-1/settle")?.body).toEqual({ answer: "sent" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-3/undo")).toBe(true));
});

test("Send it again asks first, and sends again only when the person says so", async () => {
  const user = userEvent.setup();
  const { calls } = show([actFixture({ status: "uncertain" })], {
    "POST acts/XACT-1/settle": () => ({ id: "XACT-1", status: "sent", reason: null, changeset: "CS-4" }),
  });
  const row = await rowOf("Check the Sent folder for the message to Ana Example");
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Send it again" }));
  const dialog = await screen.findByRole("dialog", { name: "Send this message to Ana Example again?" });
  expect(calls.some((c) => c.route === "POST acts/XACT-1/settle")).toBe(false);
  await user.click(within(dialog).getByRole("button", { name: "Send" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST acts/XACT-1/settle")?.body).toEqual({ answer: "again" }));
});

test("a stale act is a line that says what changed, and its button opens it to look again", async () => {
  const user = userEvent.setup();
  const { onView } = show([actFixture({ status: "stale", why: ["target"] })]);
  const row = await rowOf("Look again at the message to Ana Example: who it goes to");
  await user.click(within(row).getByRole("button", { name: "Look again" }));
  expect(onView).toHaveBeenLastCalledWith("work/outgoing");
});

test("the lines are counted in what needs the person, and the empty Today is not shown beside them", async () => {
  show([failed(), actFixture({ id: "XACT-2", status: "stale", why: ["content"] })]);
  expect((await screen.findAllByText(/2 things need you/)).length).toBeGreaterThan(0);
  expect(screen.queryByText(/Connect an AI service to get started/)).toBeNull();
});

test("a failed or unsure act is at risk and a stale one is a decision", async () => {
  show([failed(), actFixture({ id: "XACT-2", status: "stale", why: ["content"] })]);
  const risk = await screen.findByRole("region", { name: "At risk" });
  expect(within(risk).getByText(/which didn't go out/)).toBeInTheDocument();
  const decide = screen.getByRole("region", { name: "Decide" });
  expect(within(decide).getByText(/Look again at the message to Ana Example/)).toBeInTheDocument();
});
