import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { rememberReturn, useSignInReturn } from "../lib/sign-in-return";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { SignIns } from "./SignIns";

function signIn(name: string, extra: Partial<S["SignInView"]> = {}): S["SignInView"] {
  return {
    name,
    label: `Service ${name}`,
    status: "signed_out",
    ready: true,
    callback: `http://localhost:8080/auth/${name}/callback`,
    app: "workspace",
    can_paste: false,
    needs_secret: false,
    set_aside: false,
    several: false,
    default_unusable: false,
    own_app_steps: [],
    ...extra,
  };
}

const LIST = [
  signIn("demo/one", { status: "signed_in" }),
  signIn("demo/two", { status: "expired" }),
  signIn("demo/three", { status: "signed_out" }),
];

const settings = { "GET settings": () => ({ fingerprint: "fp", items: [] }) };
const open = (onChooseSource: (plugin: string | null) => void = () => undefined) =>
  renderApp(<SignIns onOpenAddons={() => undefined} onChooseSource={onChooseSource} />);
const row = (label: string) => screen.getByText(label).closest("li") as HTMLElement;

let assign: ReturnType<typeof vi.fn>;
beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

test("with no sign-ins, the section says when they appear and offers to open Add-ons", async () => {
  const user = userEvent.setup();
  const onOpenAddons = vi.fn();
  const calls = fakeApi({ ...settings, "GET sign-ins": () => [] });
  renderApp(<SignIns onOpenAddons={onOpenAddons} onChooseSource={() => undefined} />);
  await waitFor(() => expect(calls.some((c) => c.route === "GET sign-ins")).toBe(true));
  const section = (await screen.findByRole("heading", { name: "Accounts" })).closest("section") as HTMLElement;
  expect(section).toHaveTextContent("Turn on a mail or calendar add-on to see its sign-in options.");
  await user.click(within(section).getByRole("button", { name: "Open Add-ons" }));
  expect(onOpenAddons).toHaveBeenCalledTimes(1);
});

test("each status is in words, with one action per row", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => LIST });
  open();
  expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
  const one = row("Service demo/one");
  expect(within(one).getByText("Signed in")).toBeInTheDocument();
  // Once signed in, choosing what to read is the next step and the row's one primary action; the rest is in its menu.
  expect(within(one).getAllByRole("button")).toHaveLength(2);
  const choose = within(one).getByRole("button", { name: "Choose what to read from Service demo/one" });
  expect(choose).toHaveTextContent("Choose what to read");
  expect(choose).toHaveClass("primary");
  const two = row("Service demo/two");
  expect(within(two).getByText("Sign-in expired")).toBeInTheDocument();
  expect(within(two).getByRole("button", { name: "Sign in again to Service demo/two" })).toHaveTextContent("Sign in again");
  const three = row("Service demo/three");
  expect(within(three).getByText("Not signed in")).toBeInTheDocument();
  expect(within(three).getByRole("button", { name: "Sign in to Service demo/three" })).toHaveTextContent("Sign in");
});

test("before signing in, what the person will be asked to allow is listed, one item per line", async () => {
  fakeApi({
    ...settings,
    "GET sign-ins": () => [
      signIn("demo/three", { allows: ["Read your mail", "Read your calendar"] }),
      signIn("demo/one", { status: "signed_in", allows: ["Read your mail"] }),
    ],
  });
  open();
  await screen.findByText("Service demo/three");
  const three = row("Service demo/three");
  expect(within(three).getByText("You'll be asked to allow:")).toBeInTheDocument();
  const list = within(three).getByRole("list", { name: "You'll be asked to allow:" });
  expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Read your mail", "Read your calendar"]);
  // Once signed in there is nothing left to be asked.
  expect(within(row("Service demo/one")).queryByText("You'll be asked to allow:")).toBeNull();
});

test("nothing is listed when the service asks for nothing to say", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three")] });
  open();
  await screen.findByRole("button", { name: "Sign in to Service demo/three" });
  expect(screen.queryByText("You'll be asked to allow:")).toBeNull();
});

test("signed in names the account when it is known", async () => {
  fakeApi({
    ...settings,
    "GET sign-ins": () => [
      signIn("demo/one", { status: "signed_in", account: "pat@example.com" }),
      signIn("demo/two", { status: "signed_in", account: null }),
    ],
  });
  open();
  await screen.findByText("Service demo/one");
  expect(within(row("Service demo/one")).getByText("Signed in as pat@example.com")).toBeInTheDocument();
  expect(within(row("Service demo/two")).getByText("Signed in")).toBeInTheDocument();
});

test("a permission that wasn't allowed is named, with Sign in again as a secondary action", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/one", { status: "signed_in", missing: ["Mail.Read", "Calendars.Read"] })],
    "POST sign-ins/demo/one/start": () => ({ url: "http://localhost:9090/login?again=1" }),
  });
  open();
  const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
  const note = within(one).getByText(
    "Allow these missing permissions to use all features: Mail.Read, Calendars.Read. Sign in again to choose.",
  );
  // Choosing what to read stays the row's one primary action.
  expect(within(one).getByRole("button", { name: "Choose what to read from Service demo/one" })).toHaveClass("primary");
  const again = within(one).getByRole("button", { name: "Sign in again to Service demo/one" });
  expect(again).not.toHaveClass("primary");
  expect(again).toHaveAccessibleDescription(note.textContent ?? "");
  await user.click(again);
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?again=1"));
  expect(calls.filter((c) => c.route === "POST sign-ins/demo/one/start")).toHaveLength(1);
});

test("no note about permissions when none are missing", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/one", { status: "signed_in", missing: [] })] });
  open();
  await screen.findByText("Service demo/one");
  expect(screen.queryByText(/Permissions not allowed/)).toBeNull();
  expect(screen.queryByRole("button", { name: /Sign in again/ })).toBeNull();
});

test("the address the registration must allow is always shown, read-only", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [LIST[0], signIn("demo/three", { ready: false })] });
  open();
  const callbacks = await screen.findAllByLabelText("Address to allow");
  expect(callbacks).toHaveLength(2);
  expect(callbacks[0]).toHaveAttribute("readonly");
  expect(callbacks[0]).toHaveValue("http://localhost:8080/auth/demo/one/callback");
  expect(callbacks[1]).toHaveValue("http://localhost:8080/auth/demo/three/callback");
  expect(screen.getAllByText("The service's app registration must allow this address.")).toHaveLength(2);
});

test("Sign in starts the sign-in, then sends this tab to the service's page", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/three")],
    "POST sign-ins/demo/three/start": () => ({ url: "http://localhost:9090/login?x=1" }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Sign in to Service demo/three" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?x=1"));
  expect(calls.filter((c) => c.route.startsWith("POST sign-ins"))).toHaveLength(1);
});

test("a name is encoded per part in the address", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/a b")],
    "POST sign-ins/demo/a%20b/start": () => ({ url: "http://localhost:9090/" }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: /^Sign in to/ }));
  await waitFor(() => expect(assign).toHaveBeenCalled());
  expect(calls.some((c) => c.route === "POST sign-ins/demo/a%20b/start")).toBe(true);
});

test("a refusal to start shows its words on the row and goes nowhere", async () => {
  const user = userEvent.setup();
  fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/three")],
    "POST sign-ins/demo/three/start": () => new Refuse(409, "Set the app registration first."),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Sign in to Service demo/three" }));
  expect(await within(row("Service demo/three")).findByRole("alert")).toHaveTextContent("Set the app registration first.");
  expect(assign).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sign in to Service demo/three" })).toBeEnabled();
});

test("Sign in is disabled until the app registration is set, and says why", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three", { ready: false })] });
  open();
  const button = await screen.findByRole("button", { name: "Sign in to Service demo/three" });
  expect(button).toBeDisabled();
  expect(screen.getByText("Set the add-on's app registration first. Then you can sign in.")).toBeInTheDocument();
  expect(button).toHaveAccessibleDescription("Set the add-on's app registration first. Then you can sign in.");
});

test("Sign out signs out at once and says so, with no undo", async () => {
  const user = userEvent.setup();
  let status: S["SignInView"]["status"] = "signed_in";
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/one", { status })],
    "DELETE sign-ins/demo/one": () => {
      status = "signed_out";
      return { ok: true };
    },
  });
  open();
  await user.click(await screen.findByRole("button", { name: "More actions for Service demo/one" }));
  await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));
  expect(await screen.findByText("Signed out of Service demo/one.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "DELETE sign-ins/demo/one")).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  expect(await screen.findByText("Not signed in")).toBeInTheDocument();
});

test("Choose what to read opens the form that adds a source, on the kinds of that sign-in's add-on", async () => {
  const user = userEvent.setup();
  const onChooseSource = vi.fn();
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/one", { status: "signed_in" }), signIn("plain", { status: "signed_in" })] });
  open(onChooseSource);
  await user.click(await screen.findByRole("button", { name: "Choose what to read from Service demo/one" }));
  expect(onChooseSource).toHaveBeenLastCalledWith("demo");
  // A sign-in whose name has no add-on part offers every kind.
  await user.click(screen.getByRole("button", { name: "Choose what to read from Service plain" }));
  expect(onChooseSource).toHaveBeenLastCalledWith(null);
});

test("a signed-in row's menu has Sign out and Sign in again; Sign in again starts the sign-in", async () => {
  const user = userEvent.setup();
  fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/one", { status: "signed_in" })],
    "POST sign-ins/demo/one/start": () => ({ url: "http://localhost:9090/login?again=1" }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "More actions for Service demo/one" }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Sign out", "Sign in again"]);
  await user.click(screen.getByRole("menuitem", { name: "Sign in again" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?again=1"));
});

const WEB = "https" + "://";
const STEPS = [
  { text: "Open the service's developer page", link: `${WEB}portal.example.com/apps` },
  { text: "Register a new app and allow the address below", link: null },
];
const menuOf = (r: HTMLElement) => within(r).getByRole("button", { name: /^More actions for/ });

describe("the app registration", () => {
  test("the add-on's own registration works as before, shows its note, and offers your own in the menu", async () => {
    const user = userEvent.setup();
    fakeApi({
      ...settings,
      "GET sign-ins": () => [
        signIn("demo/three", { app: "add-on", app_note: "Using the add-on's shared registration.", can_paste: true, own_app_steps: STEPS }),
      ],
    });
    open();
    const three = await screen.findByText("Service demo/three").then((el) => el.closest("li") as HTMLElement);
    expect(within(three).getByText("Using the add-on's shared registration.")).toBeInTheDocument();
    expect(within(three).getByRole("button", { name: "Sign in to Service demo/three" })).toBeEnabled();
    expect(within(three).queryByRole("form")).toBeNull();
    await user.click(menuOf(three));
    await user.click(await screen.findByRole("menuitem", { name: "Use your own app registration" }));
    const form = await within(three).findByRole("form", { name: "Your own app registration for Service demo/three" });
    await waitFor(() => expect(within(form).getByLabelText("Client ID from the service")).toHaveFocus());
    // Cancel closes it and focus goes back to the menu button.
    await user.click(within(form).getByRole("button", { name: /^Cancel/ }));
    expect(within(three).queryByRole("form")).toBeNull();
    await waitFor(() => expect(menuOf(three)).toHaveFocus());
  });

  test("the menu offers nothing to paste when the person can't paste here", async () => {
    fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three", { app: "add-on", app_note: "Shared.", can_paste: false })] });
    open();
    const three = await screen.findByText("Service demo/three").then((el) => el.closest("li") as HTMLElement);
    expect(within(three).queryByRole("button", { name: /^More actions/ })).toBeNull();
  });

  test("a row with no registration shows the form with steps, links with their domain, and the address to allow", async () => {
    fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/three", { app: "none", ready: false, can_paste: true, own_app_steps: STEPS })],
    });
    open();
    const three = await screen.findByText("Service demo/three").then((el) => el.closest("li") as HTMLElement);
    const form = within(three).getByRole("form");
    expect(within(form).getByRole("heading", { name: "How to make your own" })).toBeInTheDocument();
    const list = within(form).getByRole("list", { name: "How to make your own" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const link = within(items[0]).getByRole("link", { name: "Open the service's developer page" });
    expect(link).toHaveAttribute("href", `${WEB}portal.example.com/apps`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(items[0]).toHaveTextContent("(portal.example.com)");
    expect(within(items[1]).queryByRole("link")).toBeNull();
    expect(within(form).getByLabelText("Address to allow")).toHaveAttribute("readonly");
    expect(screen.getAllByLabelText("Address to allow")).toHaveLength(1);
    // The old not-ready line gives way to the form; sign in stays off.
    expect(within(three).queryByText("Set the add-on's app registration first. Then you can sign in.")).toBeNull();
    expect(within(three).getByRole("button", { name: "Sign in to Service demo/three" })).toBeDisabled();
    // No secret asked for.
    expect(within(form).queryByLabelText("Client secret from the service")).toBeNull();
  });

  test("a row with no registration and no way to paste keeps the not-ready line", async () => {
    fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three", { app: "none", ready: false, can_paste: false })] });
    open();
    expect(await screen.findByText("Set the add-on's app registration first. Then you can sign in.")).toBeInTheDocument();
    expect(screen.queryByRole("form")).toBeNull();
  });

  test("Save stays off until filled, trims, and sends the client id alone when no secret is needed", async () => {
    const user = userEvent.setup();
    let app: S["SignInView"]["app"] = "none";
    const calls = fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/three", { app, ready: app !== "none", can_paste: true })],
      "POST sign-ins/demo/three/app": () => {
        app = "pasted";
        return signIn("demo/three", { app: "pasted", can_paste: true });
      },
    });
    open();
    const save = await screen.findByRole("button", { name: "Save the app registration for Service demo/three" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Client ID from the service"), "   ");
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Client ID from the service"), " abc-123 {Enter}");
    await waitFor(() => expect(calls.filter((c) => c.route === "POST sign-ins/demo/three/app")).toHaveLength(1));
    expect(calls.find((c) => c.route === "POST sign-ins/demo/three/app")?.body).toEqual({ client_id: "abc-123" });
    expect(await screen.findByText("Saved your app registration for Service demo/three. Sign in to use it.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("form")).toBeNull());
    expect(screen.getByText("Using your own app registration")).toBeInTheDocument();
  });

  test("a secret is asked for when the service issues one, hidden, and Enter waits until both are filled", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/three", { app: "none", ready: false, can_paste: true, needs_secret: true })],
      "POST sign-ins/demo/three/app": () => signIn("demo/three", { app: "pasted", can_paste: true, needs_secret: true }),
    });
    open();
    const secret = await screen.findByLabelText("Client secret from the service");
    expect(secret).toHaveAttribute("type", "password");
    expect(secret).toHaveAttribute("autocomplete", "off");
    await user.type(screen.getByLabelText("Client ID from the service"), "abc-123{Enter}");
    expect(calls.some((c) => c.route === "POST sign-ins/demo/three/app")).toBe(false);
    expect(screen.getByRole("button", { name: /^Save the app registration/ })).toBeDisabled();
    await user.type(secret, " s3cret {Enter}");
    await waitFor(() => expect(calls.some((c) => c.route === "POST sign-ins/demo/three/app")).toBe(true));
    expect(calls.find((c) => c.route === "POST sign-ins/demo/three/app")?.body).toEqual({
      client_id: "abc-123",
      client_secret: "s3cret",
    });
  });

  test("a refusal shows the server's words on the row and keeps what was typed", async () => {
    const user = userEvent.setup();
    fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/three", { app: "none", ready: false, can_paste: true })],
      "POST sign-ins/demo/three/app": () => new Refuse(422, "That client ID isn't valid."),
    });
    open();
    await user.type(await screen.findByLabelText("Client ID from the service"), "nope");
    await user.click(screen.getByRole("button", { name: /^Save the app registration/ }));
    expect(await within(row("Service demo/three")).findByRole("alert")).toHaveTextContent("That client ID isn't valid.");
    expect(screen.getByLabelText("Client ID from the service")).toHaveValue("nope");
    expect(screen.getByRole("button", { name: /^Save the app registration/ })).toBeEnabled();
  });

  test("Cancel closes the form and the not-ready line returns, with a way to open it again", async () => {
    const user = userEvent.setup();
    fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three", { app: "none", ready: false, can_paste: true })] });
    open();
    await user.click(await screen.findByRole("button", { name: /^Cancel/ }));
    const three = row("Service demo/three");
    expect(within(three).queryByRole("form")).toBeNull();
    expect(within(three).getByText("Set the add-on's app registration first. Then you can sign in.")).toBeInTheDocument();
    await user.click(menuOf(three));
    await user.click(await screen.findByRole("menuitem", { name: "Use your own app registration" }));
    expect(await within(three).findByRole("form")).toBeInTheDocument();
  });

  test("a pasted registration says so, and Stop using it acts at once with an Undo that brings it back", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/one", { app: "pasted", can_paste: true })],
      "POST sign-ins/demo/one/app/set-aside": () => signIn("demo/one", { app: "add-on", set_aside: true }),
      "POST sign-ins/demo/one/app/bring-back": () => signIn("demo/one", { app: "pasted" }),
    });
    open();
    const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
    expect(within(one).getByText("Using your own app registration")).toBeInTheDocument();
    expect(within(one).queryByRole("form")).toBeNull();
    await user.click(menuOf(one));
    await user.click(await screen.findByRole("menuitem", { name: "Stop using it" }));
    expect(
      await screen.findByText("Stopped using your own app registration for Service demo/one. You'll need to sign in again."),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.route === "POST sign-ins/demo/one/app/set-aside")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST sign-ins/demo/one/app/bring-back")).toBe(true));
  });

  test("a set-aside registration can be brought back from the menu", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      ...settings,
      "GET sign-ins": () => [signIn("demo/one", { app: "add-on", set_aside: true, can_paste: true })],
      "POST sign-ins/demo/one/app/bring-back": () => signIn("demo/one", { app: "pasted" }),
    });
    open();
    const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
    await user.click(menuOf(one));
    expect(screen.queryByRole("menuitem", { name: "Stop using it" })).toBeNull();
    await user.click(await screen.findByRole("menuitem", { name: "Use the registration you set aside" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST sign-ins/demo/one/app/bring-back")).toBe(true));
    expect(await screen.findByText(/You'll need to sign in again\./)).toBeInTheDocument();
  });

  test("a workspace registration has nothing new, and no menu", async () => {
    fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/one", { app: "workspace", can_paste: true })] });
    open();
    const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
    expect(within(one).queryByRole("button", { name: /^More actions/ })).toBeNull();
    expect(within(one).queryByRole("form")).toBeNull();
  });
});

function Return() {
  useSignInReturn();
  return null;
}

describe("coming back from the service", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  test("done names the service, from the list", async () => {
    window.history.replaceState(null, "", "/?sign_in=done&name=demo%2Ftwo");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText("Signed in to Service demo/two.")).toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  test("a refusal with the service's code and description shows both as text, and cleans the address", async () => {
    window.history.replaceState(
      null,
      "",
      `/tools/cockpit/?keep=1&sign_in=refused&name=demo%2Ftwo&error=access_denied&detail=${encodeURIComponent("<b>User</b> said no")}#/settings`,
    );
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    const toast = await screen.findByText("The service didn't allow the sign-in (access_denied): <b>User</b> said no");
    expect(toast.querySelector("b")).toBeNull();
    expect(window.location.pathname).toBe("/tools/cockpit/");
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#/settings");
  });

  test("a long description is cut at 200 characters", async () => {
    const detail = "x".repeat(300);
    window.history.replaceState(null, "", `/?sign_in=refused&error=access_denied&detail=${detail}`);
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText(`The service didn't allow the sign-in (access_denied): ${"x".repeat(200)}`)).toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  test("a refusal with only a code says so without a description", async () => {
    window.history.replaceState(null, "", "/?sign_in=refused&error=access_denied");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText("The service didn't allow the sign-in (access_denied).")).toBeInTheDocument();
  });

  test("a code or description on a different outcome is cleaned from the address and not shown", async () => {
    window.history.replaceState(null, "", "/?sign_in=failed&error=boom&detail=details");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    await screen.findByText("The sign-in didn't finish. Try again from Sources.");
    expect(screen.queryByText(/boom/)).toBeNull();
    expect(window.location.search).toBe("");
  });

  test("done falls back to a general line when the service isn't in the list", async () => {
    window.history.replaceState(null, "", "/?sign_in=done&name=other%2Fone");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText("Signed in.")).toBeInTheDocument();
  });

  test.each([
    ["failed", "The sign-in didn't finish. Try again from Sources."],
    ["refused", "The service didn't allow the sign-in."],
    ["expired", "That sign-in took too long. Start it again from Sources."],
  ])("%s says so once and leaves the address clean", async (outcome, words) => {
    window.history.replaceState(null, "", `/?sign_in=${outcome}&name=demo%2Ftwo`);
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText(words)).toBeInTheDocument();
    expect(window.location.search).toBe("");
    expect(screen.getAllByText(words)).toHaveLength(1);
  });

  test("a nested base path, other parameters and the hash stay", async () => {
    window.history.replaceState(null, "", "/tools/cockpit/?keep=1&sign_in=failed&name=demo%2Ftwo#/settings");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    await screen.findByText("The sign-in didn't finish. Try again from Sources.");
    expect(window.location.pathname).toBe("/tools/cockpit/");
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#/settings");
  });

  test("coming back opens the screen the sign-in was started from, once", async () => {
    window.history.replaceState(null, "", "/#/setup");
    rememberReturn();
    window.history.replaceState(null, "", "/?sign_in=done&name=demo%2Ftwo");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    await screen.findByText("Signed in to Service demo/two.");
    expect(window.location.hash).toBe("#/setup");
    expect(window.sessionStorage.getItem("cockpit.sign-in-from")).toBeNull();
  });

  test("nothing is shown when the address has no sign-in outcome", async () => {
    window.history.replaceState(null, "", "/?other=1");
    const calls = fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("button")).toBeNull();
    expect(calls).toHaveLength(0);
    expect(window.location.search).toBe("?other=1");
  });
});

test("when the add-on's own registration can't be used at this address, the row says so and shows the paste form", async () => {
  fakeApi({
    ...settings,
    "GET sign-ins": () => [
      signIn("demo/three", { app: "none", ready: false, can_paste: true, default_unusable: true }),
      signIn("demo/one", { status: "signed_in", app: "workspace" }),
    ],
  });
  open();
  await screen.findByText("Service demo/three");
  const three = row("Service demo/three");
  expect(
    within(three).getByText(
      "The add-on's own app registration doesn't work at this app's address, because the app is served under another path or is hosted. To sign in, use your own app registration.",
    ),
  ).toBeInTheDocument();
  expect(within(three).getByRole("form", { name: "Your own app registration for Service demo/three" })).toBeInTheDocument();
  expect(within(row("Service demo/one")).queryByText(/doesn't work at this app's address/)).toBeNull();
});

test("no such hint while the add-on's own registration works", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/three", { app: "add-on", app_note: "Uses the add-on's own." })] });
  open();
  await screen.findByText("Service demo/three");
  expect(screen.queryByText(/doesn't work at this app's address/)).toBeNull();
});

const account = (address: string | null, key: string, status: "signed_in" | "expired" = "signed_in") => ({
  key,
  address,
  status,
  missing: [] as string[],
});

test("a service that names its accounts lists each by its address with Sign out on each, and Add another account", async () => {
  const user = userEvent.setup();
  let accounts = [account("pat@example.com", "k1"), account("sam@example.com", "k2")];
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [signIn("demo/one", { status: "signed_in", several: true, account: "pat@example.com", accounts })],
    "POST sign-ins/demo/one/start": () => ({ url: "http://localhost:9090/login?another=1" }),
    "DELETE sign-ins/demo/one?account=k1": () => {
      accounts = accounts.filter((a) => a.key !== "k1");
      return { ok: true };
    },
  });
  open();
  const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
  const list = within(one).getByRole("list", { name: "Signed-in accounts" });
  expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "pat@example.comSign out",
    "sam@example.comSign out",
  ]);
  expect(within(one).queryByText("Signed in as pat@example.com")).toBeNull();
  // Signing one account out forgets only that one; the other stays listed.
  await user.click(within(list).getByRole("button", { name: "Sign out pat@example.com" }));
  expect(await screen.findByText("Signed out pat@example.com of Service demo/one.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "DELETE sign-ins/demo/one?account=k1")).toHaveLength(1);
  await waitFor(() => expect(within(one).queryByText("pat@example.com")).toBeNull());
  // With one account left the row says whose it is in a sentence.
  expect(within(one).getByText("Signed in as sam@example.com")).toBeInTheDocument();
  // Adding another account starts the same sign-in flow.
  await user.click(within(one).getByRole("button", { name: "Add another account to Service demo/one" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?another=1"));
  expect(calls.filter((c) => c.route === "POST sign-ins/demo/one/start")).toHaveLength(1);
});

test("an account that needs signing in again says so beside its address and can sign in again", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...settings,
    "GET sign-ins": () => [
      signIn("demo/one", {
        status: "signed_in",
        several: true,
        accounts: [account("pat@example.com", "k1", "expired"), account("sam@example.com", "k2")],
      }),
    ],
    "POST sign-ins/demo/one/start": () => ({ url: "http://localhost:9090/login?again=1" }),
  });
  open();
  const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
  expect(within(one).getByText("pat@example.com · Sign-in expired")).toBeInTheDocument();
  expect(within(one).getAllByText(/Sign-in expired/)).toHaveLength(1);
  await user.click(within(one).getByRole("button", { name: "Sign in again as pat@example.com" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?again=1"));
  expect(calls.filter((c) => c.route === "POST sign-ins/demo/one/start")).toHaveLength(1);
});

test("a service that doesn't name its accounts keeps the one row and its menu's Sign out", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => [signIn("demo/one", { status: "signed_in", account: "pat@example.com" })] });
  open();
  const one = await screen.findByText("Service demo/one").then((el) => el.closest("li") as HTMLElement);
  expect(within(one).getByText("Signed in as pat@example.com")).toBeInTheDocument();
  expect(within(one).queryByRole("button", { name: /Add another account/ })).toBeNull();
  expect(within(one).queryByRole("list", { name: "Signed-in accounts" })).toBeNull();
});
