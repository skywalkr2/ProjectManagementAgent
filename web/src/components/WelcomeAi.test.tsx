import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { WelcomeAi } from "./WelcomeAi";

// The adapter names are made up here: the screen must send whatever the chosen entry says, never a name of its own.
const KINDS: S["EndpointView"][] = [
  { id: "local-box", name: "A server on this computer", adapter: "adapter-one", base_url: "http://localhost:1234/v1", note: "Nothing leaves this computer." },
  { id: "other", name: "Another service", adapter: "adapter-one", base_url: "", note: "Enter its address." },
  { id: "runner", name: "A command-line program", adapter: "adapter-two", base_url: "", note: "Give the command that starts it." },
];

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST ai/accounts": () => ({ changes: [], fingerprint: "fp-2", restarts: false }),
    ...extra,
  });
}

const open = (props: { local?: boolean; done?: boolean } = {}) =>
  renderApp(<WelcomeAi local={props.local ?? true} done={props.done ?? false} />);

const body = (calls: ReturnType<typeof fakeApi>) => calls.find((c) => c.route === "POST ai/accounts")?.body as S["AiAccountAdd"];

async function pick(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("radio", { name: new RegExp(name) }));
}

test("the kinds are a list of radios showing each one's name and note", async () => {
  api();
  open();
  expect(await screen.findByRole("radio", { name: /A server on this computer/ })).toBeInTheDocument();
  expect(screen.getByText("Enter its address.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Name for this account")).toBeNull();
});

test("a kind with an address starts from it, suggests a name, and sends its own adapter with the key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "A server on this computer");
  expect(screen.getByLabelText("Name for this account")).toHaveValue("local-box");
  expect(screen.getByLabelText("Address")).toHaveValue("http://localhost:1234/v1");
  const key = screen.getByLabelText("Key");
  expect(key).toHaveAttribute("type", "password");
  expect(key).toHaveAttribute("autocomplete", "off");
  await user.type(key, "secret-value");
  expect(screen.getByLabelText("Or where the key is")).toBeDisabled();
  await user.type(screen.getByLabelText("Model name"), "small-1");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "local-box",
    adapter: "adapter-one",
    base_url: "http://localhost:1234/v1",
    key: "secret-value",
    models: { main: "small-1" },
    allowed_data: ["open"],
    use_for: ["routine", "deep"],
    fingerprint: "fp-1",
  });
  expect(await screen.findByText("Added the account local-box. Test it next.")).toBeInTheDocument();
  // The pasted key is not left on screen after it was sent.
  expect(screen.getByLabelText("Key")).toHaveValue("");
});

test("where the key is can be given instead of the key, and the levels and everyday use follow the boxes", async () => {
  const user = userEvent.setup();
  const calls = api();
  open({ done: true });
  await pick(user, "Another service");
  expect(screen.getByLabelText("Address")).toHaveValue("");
  const add = screen.getByRole("button", { name: "Add account" });
  expect(add).toBeDisabled();
  await user.type(screen.getByLabelText("Address"), "http://model-host:8080/v1");
  await user.type(screen.getByLabelText("Or where the key is"), "env:MODEL_KEY");
  expect(screen.getByLabelText("Key")).toBeDisabled();
  await user.type(screen.getByLabelText("Model name"), "big-2");
  await user.click(screen.getByLabelText("Restricted material"));
  // The step was already done, so using this account for everyday work is not ticked for the person.
  expect(screen.getByLabelText("Use it for everyday work")).not.toBeChecked();
  await user.click(add);
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toMatchObject({
    name: "other",
    adapter: "adapter-one",
    base_url: "http://model-host:8080/v1",
    key_ref: "env:MODEL_KEY",
    allowed_data: ["open", "restricted"],
    use_for: [],
  });
  expect(body(calls).key).toBeUndefined();
});

test("a kind without an address asks for a command and how it is fed, and sends its own adapter", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "A command-line program");
  expect(screen.queryByLabelText("Address")).toBeNull();
  expect(screen.queryByLabelText("Key")).toBeNull();
  expect(screen.getByRole("radio", { name: "On its input" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "On its output" })).toBeChecked();
  await user.type(screen.getByLabelText("Command"), "runner --locked  --model {{model}");
  await user.click(screen.getByRole("radio", { name: "As a file" }));
  await user.click(screen.getByRole("radio", { name: "As a file in a folder" }));
  await user.type(screen.getByLabelText("Model name"), "std");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "runner",
    adapter: "adapter-two",
    models: { main: "std" },
    allowed_data: ["open"],
    agent: { command: ["runner", "--locked", "--model", "{model}"], packet_via: "file", output_via: "outbox" },
    use_for: ["routine", "deep"],
    fingerprint: "fp-1",
  });
});

test("an app that is not on this computer takes no pasted key", async () => {
  const user = userEvent.setup();
  api();
  open({ local: false });
  await pick(user, "A server on this computer");
  expect(screen.queryByLabelText("Key")).toBeNull();
  expect(screen.getByText(/takes keys only from its environment/)).toBeInTheDocument();
});

test("a name that isn't lowercase letters, digits and dashes, or no level at all, stops the button", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "A server on this computer");
  await user.type(screen.getByLabelText("Model name"), "small-1");
  const add = screen.getByRole("button", { name: "Add account" });
  expect(add).toBeEnabled();
  await user.clear(screen.getByLabelText("Name for this account"));
  await user.type(screen.getByLabelText("Name for this account"), "Bad Name");
  expect(add).toBeDisabled();
  await user.clear(screen.getByLabelText("Name for this account"));
  await user.type(screen.getByLabelText("Name for this account"), "good-name");
  expect(add).toBeEnabled();
  await user.click(screen.getByLabelText("Open material"));
  expect(add).toBeDisabled();
});

test("a refusal shows the server's words and keeps what was typed", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts": () => new Refuse(409, "There is already an account called local-box.") });
  open();
  await pick(user, "A server on this computer");
  await user.type(screen.getByLabelText("Model name"), "small-1");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("There is already an account called local-box.");
  expect(screen.getByLabelText("Model name")).toHaveValue("small-1");
  expect(screen.getByLabelText("Name for this account")).toHaveValue("local-box");
});

test("after adding, focus goes to Test, and the results are listed in words", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/test": () => [
      { tier: "routine", account: "local-box", main: true, ok: true, detail: "" },
      { tier: "deep", account: "local-box", main: false, ok: true, detail: "" },
      { tier: "routine", account: "second", main: false, ok: false, detail: "The key was refused." },
    ],
  });
  open();
  await pick(user, "A server on this computer");
  await user.type(screen.getByLabelText("Model name"), "small-1");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  const test = screen.getByRole("button", { name: "Test the connection" });
  await waitFor(() => expect(test).toHaveFocus());
  await user.click(test);
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/test")).toBe(true));
  const rows = await screen.findAllByRole("listitem");
  const results = rows.filter((r) => r.closest(".test-results"));
  expect(results).toHaveLength(2);
  expect(results[0]).toHaveTextContent("local-box: ✓ Answered");
  expect(results[1]).toHaveTextContent("second: ✗ Didn't answer: The key was refused.");
  expect(within(results[1]).queryByText("routine")).toBeNull();
});

test("testing with nothing to test says so", async () => {
  const user = userEvent.setup();
  api({ "POST ai/test": () => [] });
  open();
  await user.click(await screen.findByRole("button", { name: "Test the connection" }));
  expect(await screen.findByText("There is nothing to test yet. Add an account first.")).toBeInTheDocument();
});
