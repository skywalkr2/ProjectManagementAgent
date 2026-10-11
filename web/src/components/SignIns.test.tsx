import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { useSignInReturn } from "../lib/sign-in-return";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { Settings } from "./Settings";

function signIn(name: string, extra: Partial<S["SignInView"]> = {}): S["SignInView"] {
  return {
    name,
    label: `Service ${name}`,
    status: "signed_out",
    ready: true,
    callback: `http://localhost:8080/auth/${name}/callback`,
    ...extra,
  };
}

const LIST = [
  signIn("demo/one", { status: "signed_in" }),
  signIn("demo/two", { status: "expired" }),
  signIn("demo/three", { status: "signed_out" }),
];

const settings = { "GET settings": () => ({ fingerprint: "fp", items: [] }) };
const open = () => renderApp(<Settings onOpenGuide={() => undefined} />);
const row = (label: string) => screen.getByText(label).closest("li") as HTMLElement;

let assign: ReturnType<typeof vi.fn>;
beforeEach(() => {
  assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

test("the section is hidden when no add-on signs in to a service", async () => {
  const calls = fakeApi({ ...settings, "GET sign-ins": () => [] });
  open();
  await waitFor(() => expect(calls.some((c) => c.route === "GET sign-ins")).toBe(true));
  await screen.findByText("No settings match.");
  expect(screen.queryByRole("heading", { name: "Sign-ins" })).toBeNull();
});

test("each status is in words, with one action per row", async () => {
  fakeApi({ ...settings, "GET sign-ins": () => LIST });
  open();
  expect(await screen.findByRole("heading", { name: "Sign-ins" })).toBeInTheDocument();
  const one = row("Service demo/one");
  expect(within(one).getByText("Signed in")).toBeInTheDocument();
  expect(within(one).getAllByRole("button")).toHaveLength(1);
  expect(within(one).getByRole("button", { name: "Sign out of Service demo/one" })).toHaveTextContent("Sign out");
  const two = row("Service demo/two");
  expect(within(two).getByText("Sign-in ran out")).toBeInTheDocument();
  expect(within(two).getByRole("button", { name: "Sign in again to Service demo/two" })).toHaveTextContent("Sign in again");
  const three = row("Service demo/three");
  expect(within(three).getByText("Not signed in")).toBeInTheDocument();
  expect(within(three).getByRole("button", { name: "Sign in to Service demo/three" })).toHaveTextContent("Sign in");
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
  await user.click(await screen.findByRole("button", { name: "Sign out of Service demo/one" }));
  expect(await screen.findByText("Signed out of Service demo/one.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "DELETE sign-ins/demo/one")).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  expect(await screen.findByText("Not signed in")).toBeInTheDocument();
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

  test("done falls back to a general line when the service isn't in the list", async () => {
    window.history.replaceState(null, "", "/?sign_in=done&name=other%2Fone");
    fakeApi({ "GET sign-ins": () => LIST });
    renderApp(<Return />);
    expect(await screen.findByText("Signed in.")).toBeInTheDocument();
  });

  test.each([
    ["failed", "The sign-in didn't finish. Try again from Settings."],
    ["refused", "The service didn't allow the sign-in."],
    ["expired", "That sign-in took too long. Start it again from Settings."],
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
    await screen.findByText("The sign-in didn't finish. Try again from Settings.");
    expect(window.location.pathname).toBe("/tools/cockpit/");
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#/settings");
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
