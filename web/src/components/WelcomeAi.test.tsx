import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { WelcomeAi } from "./WelcomeAi";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

// The names and adapters are made up here: the screen must send whatever the chosen entry says, never a name of its own.
const KINDS: S["EndpointView"][] = [
  {
    id: "service-a",
    name: "Service A",
    adapter: "adapter-one",
    base_url: `${WEB}api.service-a.example.com/v1`,
    key_url: `${WEB}console.service-a.example.com/keys`,
    needs_key: true,
    local: false,
    note: "Pay as you go.",
    allowed_data: ["open", "internal"],
  },
  {
    id: "service-b",
    name: "Service B",
    adapter: "adapter-one",
    base_url: `${WEB}api.service-b.example.com/v1`,
    key_url: "",
    needs_key: true,
    local: false,
    note: "Many models.",
    allowed_data: ["open"],
  },
  {
    id: "local-box",
    name: "A server on this computer",
    adapter: "adapter-one",
    base_url: "http://localhost:1234/v1",
    key_url: "",
    needs_key: false,
    local: true,
    note: "Nothing leaves this computer.",
    allowed_data: ["open", "internal", "restricted"],
  },
  { id: "other", name: "Another service", adapter: "adapter-one", base_url: "", key_url: "", needs_key: false, local: false, note: "Enter its address." },
  { id: "runner", name: "A command-line program", adapter: "adapter-two", base_url: "", key_url: "", needs_key: false, local: false, note: "Give the command that starts it." },
];

const MODELS: S["AiModelView"][] = [
  { id: "model-a", context_tokens: 200000, input_per_million: 3, output_per_million: 15 },
  { id: "model-b" },
  { id: "model-c", input_per_million: 0.25 },
];

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET ai/local": () => [],
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST ai/models": () => ({ models: MODELS }),
    "POST ai/accounts": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
    "POST ai/test": () => [],
    ...extra,
  });
}

const open = (props: { local?: boolean; done?: boolean } = {}) =>
  renderApp(<WelcomeAi local={props.local ?? true} done={props.done ?? false} />);

const body = (calls: ReturnType<typeof fakeApi>) => calls.find((c) => c.route === "POST ai/accounts")?.body as S["AiAccountAdd"];
const modelsAsked = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST ai/models");

async function pick(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("radio", { name: new RegExp(name) }));
}

/** Choose a service, paste its key and check it. */
async function keyed(user: ReturnType<typeof userEvent.setup>, service = "Service A") {
  await pick(user, service);
  await user.type(screen.getByLabelText("Key"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByLabelText("Model for everyday work");
}

test("services that need a key are large choices with their notes; the rest wait under More options", async () => {
  api();
  open();
  expect(await screen.findByRole("radio", { name: /Service A/ })).toBeInTheDocument();
  expect(screen.getByText("Pay as you go.")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Service B/ })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Which AI should Helper use?" })).toBeInTheDocument();
  const more = screen.getByText("More options").closest("details")!;
  expect(more).not.toHaveAttribute("open");
  expect(within(more).getByRole("radio", { name: /A server on this computer/, hidden: true })).toBeInTheDocument();
  expect(within(more).getByRole("radio", { name: /Another service/, hidden: true })).toBeInTheDocument();
  expect(within(more).getByRole("radio", { name: /A command-line program/, hidden: true })).toBeInTheDocument();
  expect(screen.queryByLabelText("Key")).toBeNull();
});

test("choosing a service shows where to make a key, with its real domain, and a hidden key field", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  const link = screen.getByRole("link", { name: "Open console.service-a.example.com and make a key" });
  expect(link).toHaveAttribute("href", `${WEB}console.service-a.example.com/keys`);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByText("Paste it here")).toBeInTheDocument();
  const key = screen.getByLabelText("Key");
  expect(key).toHaveAttribute("type", "password");
  expect(key).toHaveAttribute("autocomplete", "off");
  await user.click(screen.getByRole("button", { name: "Show" }));
  expect(key).toHaveAttribute("type", "text");
  await user.click(screen.getByRole("button", { name: "Hide" }));
  expect(key).toHaveAttribute("type", "password");
  // Without a page for making keys there is no link to open.
  await pick(user, "Service B");
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.getByText("Make a key on the service's own website")).toBeInTheDocument();
});

test("Check lists the service's models, and the selects fill with what each costs", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  const check = screen.getByRole("button", { name: "Check" });
  expect(check).toBeDisabled();
  await user.type(screen.getByLabelText("Key"), "secret-value");
  await user.click(check);
  const everyday = await screen.findByLabelText("Model for everyday work");
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key: "secret-value" });
  expect(within(everyday).getAllByRole("option").map((o) => o.textContent)).toEqual(["model-a", "model-b", "model-c"]);
  expect(everyday).toHaveValue("model-a");
  expect(screen.getByText(/Takes in about 200,000 tokens at a time\. Costs \$3\.00 per million tokens read and \$15\.00 per million tokens written\./)).toBeInTheDocument();
  const harder = screen.getByLabelText("Model for harder work (optional)");
  expect(within(harder).getAllByRole("option").map((o) => o.textContent)).toEqual(["Same as the everyday model", "model-a", "model-b", "model-c"]);
  expect(harder).toHaveValue("");
  await user.selectOptions(everyday, "model-c");
  expect(screen.getByText("Costs $0.25 per million tokens read.")).toBeInTheDocument();
});

test("pasting a key into the empty field checks it at once", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  await user.click(screen.getByLabelText("Key"));
  await user.paste("pasted-key");
  await screen.findByLabelText("Model for everyday work");
  expect(modelsAsked(calls)).toHaveLength(1);
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key: "pasted-key" });
});

test("a problem listing the models is shown in an alert, with no list to pick from", async () => {
  const user = userEvent.setup();
  api({ "POST ai/models": () => ({ models: [], problem: "That key was not accepted." }) });
  open();
  await pick(user, "Service A");
  await user.type(screen.getByLabelText("Key"), "wrong");
  await user.click(screen.getByRole("button", { name: "Check" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That key was not accepted.");
  expect(screen.queryByLabelText("Model for everyday work")).toBeNull();
  expect(screen.queryByLabelText("Model name")).toBeNull();
  expect(screen.getByRole("button", { name: "Add account" })).toBeDisabled();
});

test("a service that lists no models asks for the model's name instead", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/models": () => ({ models: [] }) });
  open();
  await pick(user, "Service A");
  await user.type(screen.getByLabelText("Key"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Check" }));
  await user.type(await screen.findByLabelText("Model name"), "typed-model");
  expect(screen.getByText(/Copy the name from the service's own page/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).models).toEqual({ everyday: "typed-model" });
});

test("a long list can be narrowed by typing", async () => {
  const user = userEvent.setup();
  const many = Array.from({ length: 20 }, (_, i) => ({ id: `model-${String(i).padStart(2, "0")}` }));
  api({ "POST ai/models": () => ({ models: many }) });
  open();
  await keyed(user);
  await user.type(screen.getByLabelText("Find a model"), "model-1");
  const everyday = screen.getByLabelText("Model for everyday work");
  expect(within(everyday).getAllByRole("option")).toHaveLength(11);
  await user.type(screen.getByLabelText("Find a model"), "9x");
  expect(screen.getByText("No model matches.")).toBeInTheDocument();
});

test("adding sends the kind, both models, the data levels the kind allows and what to use them for", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await keyed(user);
  expect(screen.getByLabelText("Open material")).toBeChecked();
  expect(screen.getByLabelText("Internal material")).toBeChecked();
  expect(screen.getByLabelText("Restricted material")).not.toBeChecked();
  expect(screen.getByLabelText("Use it for my work")).toBeChecked();
  await user.selectOptions(screen.getByLabelText("Model for harder work (optional)"), "model-b");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "service-a",
    adapter: "adapter-one",
    endpoint: "service-a",
    base_url: `${WEB}api.service-a.example.com/v1`,
    key: "secret-value",
    models: { everyday: "model-a", harder: "model-b" },
    allowed_data: ["open", "internal"],
    use: { routine: "everyday", deep: "harder" },
    fingerprint: "fp-1",
  });
  expect(await screen.findByText("Added the account service-a. Testing it now.")).toBeInTheDocument();
  // The pasted key is not left on screen after it was sent.
  expect(screen.getByLabelText("Key")).toHaveValue("");
});

test("with one model chosen, both kinds of work use it; with the box off, nothing is switched over", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).models).toEqual({ everyday: "model-a" });
  expect(body(calls).use).toEqual({ routine: "everyday", deep: "everyday" });
});

test("when the guide step was already done, using it for my work starts unticked and sends no use", async () => {
  const user = userEvent.setup();
  const calls = api();
  open({ done: true });
  await keyed(user);
  expect(screen.getByLabelText("Use it for my work")).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).use).toBeUndefined();
});

test("the account name gets -2 when an account of that name exists, and can be changed under Advanced", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET settings": () => ({
      fingerprint: "fp-1",
      items: [{ key: "ai.providers.service-a.adapter" }, { key: "ai.providers.service-a-2.adapter" }, { key: "ai.tiers.routine.use" }],
    }),
  });
  open();
  await keyed(user);
  const advanced = screen.getByText("Advanced").closest("details")!;
  expect(within(advanced).getByLabelText("Account name", { selector: "input" })).toHaveValue("service-a-3");
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).name).toBe("service-a-3");
});

test("Advanced holds the account name, the fixed address read-only and the key's other home", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  const advanced = screen.getByText("Advanced").closest("details")!;
  expect(advanced).not.toHaveAttribute("open");
  const address = within(advanced).getByLabelText("Address", { selector: "input", exact: true });
  expect(address).toHaveValue(`${WEB}api.service-a.example.com/v1`);
  expect(address).toHaveAttribute("readonly");
  await user.type(within(advanced).getByLabelText("Or where the key is"), "env:MODEL_KEY");
  expect(screen.getByLabelText("Key")).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByLabelText("Model for everyday work");
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key_ref: "env:MODEL_KEY" });
  await user.clear(within(advanced).getByLabelText("Account name", { selector: "input" }));
  await user.type(within(advanced).getByLabelText("Account name", { selector: "input" }), "Bad Name");
  expect(screen.getByRole("button", { name: "Add account" })).toBeDisabled();
});

test("no level at all stops the button", async () => {
  const user = userEvent.setup();
  api();
  open();
  await keyed(user, "Service B");
  const add = screen.getByRole("button", { name: "Add account" });
  expect(add).toBeEnabled();
  await user.click(screen.getByLabelText("Open material"));
  expect(add).toBeDisabled();
});

test("a server found on this computer is offered first and is added without a key", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/local": () => [{ endpoint: "local-box", name: "A server on this computer", models: ["small-1", "small-2"] }],
  });
  open();
  expect(await screen.findByText("Found A server on this computer on this computer with 2 models. Nothing leaves this computer.")).toBeInTheDocument();
  // The kind found running is not listed a second time.
  expect(screen.queryByRole("radio", { name: /A server on this computer/, hidden: true })).toBeNull();
  const use = screen.getByRole("button", { name: "Use it" });
  expect(use).toHaveAttribute("aria-pressed", "false");
  await user.click(use);
  expect(use).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Chosen")).toBeInTheDocument();
  expect(screen.queryByLabelText("Key")).toBeNull();
  const everyday = screen.getByLabelText("Model for everyday work");
  expect(within(everyday).getAllByRole("option").map((o) => o.textContent)).toEqual(["small-1", "small-2"]);
  expect(modelsAsked(calls)).toHaveLength(0);
  expect(screen.getByLabelText("Restricted material")).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "local-box",
    adapter: "adapter-one",
    endpoint: "local-box",
    base_url: "http://localhost:1234/v1",
    models: { everyday: "small-1" },
    allowed_data: ["open", "internal", "restricted"],
    use: { routine: "everyday", deep: "everyday" },
    fingerprint: "fp-1",
  });
});

test("a computer-local kind that isn't running is under More options and lists its models with no key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "A server on this computer");
  expect(await screen.findByLabelText("Model for everyday work")).toBeInTheDocument();
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "local-box" });
  expect(screen.queryByLabelText("Key")).toBeNull();
});

test("another service asks for its address first, then lists models, with an optional key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Another service");
  const check = screen.getByRole("button", { name: "Check" });
  expect(check).toBeDisabled();
  await user.type(screen.getByLabelText("Address"), "http://model-host:8080/v1");
  await user.click(check);
  await screen.findByLabelText("Model for everyday work");
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "other", base_url: "http://model-host:8080/v1" });
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toMatchObject({ name: "other", endpoint: "other", base_url: "http://model-host:8080/v1" });
  expect(body(calls).key).toBeUndefined();
});

test("a command-line program asks for a command and how it is fed, and sends its own adapter", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "A command-line program");
  expect(screen.queryByLabelText("Address")).toBeNull();
  expect(screen.queryByLabelText("Key")).toBeNull();
  expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
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
    endpoint: "runner",
    models: { everyday: "std" },
    allowed_data: ["open"],
    agent: { command: ["runner", "--locked", "--model", "{model}"], packet_via: "file", output_via: "outbox" },
    use: { routine: "everyday", deep: "everyday" },
    fingerprint: "fp-1",
  });
  expect(modelsAsked(calls)).toHaveLength(0);
});

test("an app that is not on this computer asks where the key is and sends a reference, never a key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open({ local: false });
  await pick(user, "Service A");
  expect(screen.queryByLabelText("Key")).toBeNull();
  expect(screen.queryByRole("button", { name: "Show" })).toBeNull();
  const where = screen.getByLabelText("Where the key is");
  expect(screen.getByText(/takes keys only from its environment/)).toBeInTheDocument();
  const check = screen.getByRole("button", { name: "Check" });
  expect(check).toBeDisabled();
  await user.type(where, "env:MODEL_KEY");
  await user.click(check);
  await screen.findByLabelText("Model for everyday work");
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key_ref: "env:MODEL_KEY" });
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).key_ref).toBe("env:MODEL_KEY");
  expect(body(calls).key).toBeUndefined();
});

test("a refusal shows the server's words and keeps what was typed", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts": () => new Refuse(409, "There is already an account called service-a.") });
  open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: "Add account" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("There is already an account called service-a.");
  expect(screen.getByLabelText("Key")).toHaveValue("secret-value");
  expect(screen.getByLabelText("Model for everyday work")).toHaveValue("model-a");
});

test("there is no Test button before an account exists to test", async () => {
  api();
  open();
  await screen.findByRole("radio", { name: /Service A/ });
  expect(screen.queryByRole("button", { name: /Test/ })).toBeNull();
  expect(screen.queryByText("Test the connection")).toBeNull();
});

test("after adding, focus goes to Test again, the test runs by itself, and one plain line is listed per kind of work", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/test": () => [
      { tier: "routine", account: "main-account", main: true, ok: true, detail: "answered" },
      { tier: "deep", account: "main-account", main: true, ok: true, detail: "answered" },
      { tier: "routine", account: "second", main: false, ok: true, detail: "answered" },
      { tier: "deep", account: "second", main: false, ok: false, detail: "The key was refused." },
      { tier: "review", account: "second", main: true, ok: true, detail: "answered" },
    ],
  });
  open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: "Add account" }));
  const test = await screen.findByRole("button", { name: "Test again" });
  await waitFor(() => expect(test).toHaveFocus());
  await waitFor(() => expect(calls.filter((c) => c.route === "POST ai/test")).toHaveLength(1));
  const rows = await screen.findAllByRole("listitem");
  const results = rows.filter((r) => r.closest(".test-results"));
  expect(results.map((r) => r.textContent)).toEqual([
    "Everyday work: main-account — answered ✓",
    "Harder work: main-account — answered ✓",
    "Everyday work (backup): second — answered ✓",
    "Harder work (backup): second — didn't answer: The key was refused. ✗",
    "review: second — answered ✓",
  ]);
  const body = document.body.textContent ?? "";
  expect(body).not.toMatch(/temperature|max output|stub|routine|deep/i);
  await user.click(test);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST ai/test")).toHaveLength(2));
});

test("adding stays on the step and shows no restart notice, because accounts apply at once", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/test": () => [{ tier: "routine", account: "main-account", main: true, ok: true, detail: "answered" }] });
  open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(document.querySelector(".test-results li")).toHaveTextContent("Everyday work: main-account — answered ✓"));
  expect(screen.queryByText(/restart/i)).toBeNull();
  expect(screen.queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  expect(screen.getByLabelText("Key")).toBeInTheDocument();
});

test("a failure shows its reason with the word and a cross, not colour alone", async () => {
  const user = userEvent.setup();
  api({ "POST ai/test": () => [{ tier: "routine", account: "main-account", main: true, ok: false, detail: "The key was refused." }] });
  open({ done: true });
  await user.click(await screen.findByRole("button", { name: "Test the connection" }));
  const line = await screen.findByText(/didn't answer/);
  expect(line).toHaveTextContent("Everyday work: main-account — didn't answer: The key was refused. ✗");
});

test("when the step was already done, the test button is there from the start", async () => {
  const user = userEvent.setup();
  api({ "POST ai/test": () => [] });
  open({ done: true });
  await user.click(await screen.findByRole("button", { name: "Test the connection" }));
  expect(await screen.findByText("There is nothing to test yet. Add an account first.")).toBeInTheDocument();
});
