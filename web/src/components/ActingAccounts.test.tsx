import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { ActingAccounts } from "./ActingAccounts";

// Letting the assistant act (design 6.12, 7.9): one switch for each account, off until the person turns it on. A signed-in
// account starts its own sign-in with the wider access first, so the person sees the service's page; a plain mailbox just saves.
// Turning one off saves at once, with Undo.

let assign: ReturnType<typeof vi.fn>;
beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
});
afterEach(() => vi.unstubAllGlobals());

const account = (over: Partial<S["ActAccountView"]> = {}): S["ActAccountView"] => ({ id: "mailbox:work", label: "Work mail", acting: false, sign_in: null, can_act: true, ...over });
const MAIL = account();
const SIGNED = account({ id: "demo-service:pat@example.com", label: "Demo service (pat@example.com)", sign_in: "demo/service" });

const setting = (value: string[]) => ({
  fingerprint: "fp-1",
  items: [{ key: "watch.acting", file: "watch", group: "watch", description: "", type: "list", options: [], value, default: [], source: "file", locked: false, basic: false, editable: true }],
});
const saved = (before: string[], after: string[]) => ({
  changes: [{ key: "watch.acting", before, after, was_default: before.length === 0, is_default: after.length === 0 }],
  fingerprint: "fp-2",
  needs_restart: false,
});

function show(accounts: S["ActAccountView"][], held: string[], extra: Routes = {}, options: { unnamed?: boolean } = {}) {
  const calls = fakeApi({
    "GET acts/accounts": () => ({ accounts }),
    "GET settings": () => setting(held),
    ...extra,
  });
  renderApp(<ActingAccounts />, {}, options);
  return calls;
}
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;
const switchOf = async (label: string) => within((await screen.findByText(label)).closest("li") as HTMLElement).getByRole("checkbox", { name: "Let Helper act after your yes" });

test("each account has the switch, off to begin with, and the intro says what an account that is off still gets", async () => {
  show([MAIL, SIGNED], []);
  expect(await switchOf("Work mail")).not.toBeChecked();
  expect(await switchOf("Demo service (pat@example.com)")).not.toBeChecked();
  expect(screen.getByText(/An account that isn't switched on still gets drafts, which you carry out with Copy/)).toBeInTheDocument();
});

test("while the assistant has no name, the switch doesn't use one", async () => {
  show([MAIL], [], {}, { unnamed: true });
  await screen.findByText("Work mail");
  expect(screen.getByRole("checkbox", { name: "Let your assistant act after your yes" })).toBeInTheDocument();
});

test("an account that is on shows on", async () => {
  show([account({ acting: true })], ["mailbox:work"]);
  expect(await switchOf("Work mail")).toBeChecked();
});

test("turning on a plain mailbox just saves it, keeping the others the setting names, with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([MAIL], ["mailbox:gone"], {
    "POST settings": (b) => (JSON.stringify((b as { changes: unknown }).changes).includes("work") ? saved(["mailbox:gone"], ["mailbox:gone", "mailbox:work"]) : saved(["mailbox:gone", "mailbox:work"], ["mailbox:gone"])),
  });
  await user.click(await switchOf("Work mail"));
  await waitFor(() => expect(body(calls, "POST settings")).toEqual({ changes: { "watch.acting": ["mailbox:gone", "mailbox:work"] }, reset: [], fingerprint: "fp-1" }));
  expect(calls.some((c) => c.route.startsWith("POST sign-ins"))).toBe(false);
  expect(assign).not.toHaveBeenCalled();
  expect(await screen.findByText(/Work mail: Helper can now act after your yes/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST settings")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST settings")[1].body).toMatchObject({ changes: { "watch.acting": ["mailbox:gone"] } });
});

test("turning on a signed-in account starts its sign-in with acting, saves, and sends the person to the service's page", async () => {
  const user = userEvent.setup();
  const calls = show([SIGNED], [], {
    "POST sign-ins/demo/service/start?acting=true": () => ({ url: "http://localhost:9090/login?acting=1" }),
    "POST settings": () => saved([], ["demo-service:pat@example.com"]),
  });
  await user.click(await switchOf("Demo service (pat@example.com)"));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?acting=1"));
  expect(body(calls, "POST settings")).toEqual({ changes: { "watch.acting": ["demo-service:pat@example.com"] }, reset: [], fingerprint: "fp-1" });
  const order = calls.map((c) => c.route).filter((r) => r.startsWith("POST"));
  expect(order).toEqual(["POST sign-ins/demo/service/start?acting=true", "POST settings"]); // asked for the access before anything is saved
});

test("when the service can't be asked, nothing is saved and the person is told", async () => {
  const user = userEvent.setup();
  const calls = show([SIGNED], [], { "POST sign-ins/demo/service/start?acting=true": () => new Refuse(409, "Demo service has no acting access to ask for.") });
  await user.click(await switchOf("Demo service (pat@example.com)"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Demo service has no acting access to ask for.");
  expect(calls.some((c) => c.route === "POST settings")).toBe(false);
  expect(assign).not.toHaveBeenCalled();
  expect(await switchOf("Demo service (pat@example.com)")).not.toBeChecked();
});

test("turning one off saves at once, says what Copy does then, and has Undo", async () => {
  const user = userEvent.setup();
  const calls = show([account({ acting: true })], ["mailbox:work", "mailbox:other"], {
    "POST settings": (b) => ((b as { changes: Record<string, string[]> }).changes["watch.acting"].length === 1 ? saved(["mailbox:work", "mailbox:other"], ["mailbox:other"]) : saved(["mailbox:other"], ["mailbox:work", "mailbox:other"])),
  });
  await user.click(await switchOf("Work mail"));
  await waitFor(() => expect(body(calls, "POST settings")).toEqual({ changes: { "watch.acting": ["mailbox:other"] }, reset: [], fingerprint: "fp-1" }));
  expect(assign).not.toHaveBeenCalled();
  expect(await screen.findByText(/Work mail: nothing is sent or changed there by the app any more/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST settings")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST settings")[1].body).toMatchObject({ changes: { "watch.acting": ["mailbox:work", "mailbox:other"] } });
});

test("a service with no acting access to ask for can't be switched on, and says so", async () => {
  show([account({ id: "plain:me@example.com", label: "Plain service", sign_in: "plain", can_act: false })], []);
  await screen.findByText("Plain service");
  expect(screen.getByRole("checkbox", { name: "Let Helper act after your yes" })).toBeDisabled();
  expect(screen.getByText("Plain service has no extra access to ask for.")).toBeInTheDocument();
});

test("with no accounts it says to sign in or add a mailbox first", async () => {
  show([], []);
  expect(await screen.findByText("No accounts yet. Sign in to a service or add a mailbox first.")).toBeInTheDocument();
});
