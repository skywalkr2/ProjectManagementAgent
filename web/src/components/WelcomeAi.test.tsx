import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { WelcomeAi } from "./WelcomeAi";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

// The names and adapters are made up here: the screen must send whatever the chosen entry says, never a name of its own.
const KINDS: S["EndpointView"][] = ([
  {
    id: "service-a",
    name: "Service A",
    adapter: "adapter-one",
    base_url: `${WEB}api.service-a.example.com/v1`,
    key_url: `${WEB}console.service-a.example.com/keys`,
    signup_url: `${WEB}console.service-a.example.com/signup`,
    credit_url: `${WEB}console.service-a.example.com/billing`,
    recommended: true,
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
    key_url: `${WEB}console.service-b.example.com/keys`,
    signup_url: "",
    credit_url: "",
    alternative: true,
    needs_key: true,
    local: false,
    note: "Many models.",
    allowed_data: ["open"],
  },
  {
    id: "service-c",
    name: "Service C",
    adapter: "adapter-one",
    base_url: `${WEB}api.service-c.example.com/v1`,
    key_url: "",
    needs_key: true,
    local: false,
    note: "Low prices.",
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
  {
    id: "app-a",
    name: "App A",
    adapter: "adapter-two",
    base_url: "",
    key_url: "",
    needs_key: false,
    local: false,
    note: "Uses the app you are signed in to.",
    program: "app-a-cli",
    installed: true,
    model_examples: ["alpha", "beta"],
    model_optional: true,
    allowed_data: ["open"],
  },
  {
    id: "app-b",
    name: "App B",
    adapter: "adapter-two",
    base_url: "",
    key_url: "",
    needs_key: false,
    local: false,
    note: "Another signed-in app.",
    program: "app-b-cli",
    installed: false,
    model_examples: ["gamma", "delta"],
    model_optional: false,
    allowed_data: ["open", "internal"],
  },
] as Omit<S["EndpointView"], "program" | "model_optional" | "model_examples" | "installed">[]).map((k) => ({
  program: "",
  model_optional: false,
  model_examples: [],
  installed: null,
  ...k,
}));

const MODELS: S["AiModelView"][] = [
  { id: "model-a", context_tokens: 200000, input_per_million: 3, output_per_million: 15 },
  { id: "model-b" },
  { id: "model-c", input_per_million: 0.25 },
];

const spendItem = (key: string, value: number): S["SettingItem"] =>
  ({
    key,
    file: "ai",
    group: "ai.budgets",
    description: key,
    type: "number",
    options: [],
    value,
    default: value,
    source: "default",
    locked: false,
    basic: true,
    editable: true,
  }) as S["SettingItem"];

const SPENDING = [spendItem("ai.budgets.confirm_above_usd", 0.1), spendItem("ai.budgets.per_day_usd", 2)];

const WORKS: S["AiAccountChecked"] = {
  ok: true,
  reason: "works",
  message: "",
  identity: null,
  identity_unknown: "the service doesn't say whose account the key belongs to",
};

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET ai/accounts": () => [],
    "GET ai/local": () => [],
    "GET settings": () => ({ fingerprint: "fp-1", items: SPENDING }),
    "POST ai/models": () => ({ models: MODELS }),
    "POST ai/account-check": () => WORKS,
    "POST ai/accounts": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
    "POST ai/test": () => [{ tier: "routine", account: "service-a", main: true, ok: true, detail: "answered" }],
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
    ...extra,
  });
}

const open = (props: { local?: boolean; done?: boolean } = {}) =>
  renderApp(<WelcomeAi local={props.local ?? true} done={props.done ?? false} />);

type User = ReturnType<typeof userEvent.setup>;
const body = (calls: ReturnType<typeof fakeApi>) => calls.find((c) => c.route === "POST ai/accounts")?.body as S["AiAccountAdd"];
const modelsAsked = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST ai/models");
const checks = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST ai/account-check");
const save = () => screen.getByRole("button", { name: "Save" });

async function pick(user: User, name: string) {
  await user.click(await screen.findByRole("radio", { name: new RegExp(`^(Recommended\\s*)?${name}`) }));
}

/** Choose something under "Something else": open it first when it isn't open. */
async function pickElse(user: User, name: string) {
  if (!screen.queryByRole("radio", { name: new RegExp(`^${name}`) })) await user.click(await screen.findByRole("radio", { name: /Something else/ }));
  await pick(user, name);
}

/** Choose a service and paste its key into the empty box: the check runs at once. */
async function pasted(user: User, service = "Service A", key = "secret-value") {
  if (service === "Service A" || service === "Service B") await pick(user, service);
  else await pickElse(user, service);
  await user.click(screen.getByLabelText("Access key"));
  await user.paste(key);
  await screen.findByText("Works. Ready to use.");
}

/** The whole way to a Save that can be pressed: a checked key and the answer to the question about work mail. */
async function ready(user: User, answer: "Allow" | "Not now" = "Allow", service = "Service A") {
  await pasted(user, service);
  await user.click(screen.getByRole("radio", { name: new RegExp(`^${answer}`) }));
}

// ---- the choice: one recommended service, one alternative, something else ---------------------------------------------

test("an assistant with no name of its own is called your assistant in the heading, never Assistant", async () => {
  api();
  renderApp(<WelcomeAi local done={false} />, {}, { unnamed: true });
  expect(await screen.findByRole("group", { name: "Which AI should your assistant use?" })).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: /Which AI should Helper use/ })).toBeNull();
});

test("a workspace's own wording for the heading wins over the unnamed variant", async () => {
  api();
  renderApp(<WelcomeAi local done={false} />, { "welcome.ai.kind": "Pick the AI for {assistant}" }, { unnamed: true });
  expect(await screen.findByRole("group", { name: "Pick the AI for Helper" })).toBeInTheDocument();
});

test("the service the data recommends has the tag, the alternative is beside it, and everything else is under Something else", async () => {
  api();
  open();
  const first = await screen.findByRole("radio", { name: /Service A/ });
  expect(first.closest("label")).toHaveTextContent("Recommended");
  const second = screen.getByRole("radio", { name: /Service B/ });
  expect(second.closest("label")).not.toHaveTextContent("Recommended");
  expect(screen.getByText("Pay as you go.")).toBeInTheDocument();
  // The rest waits until Something else is chosen, with a note that it needs a technical setup.
  const more = screen.getByRole("radio", { name: /Something else/ });
  expect(more).not.toBeChecked();
  for (const value of ["service-c", "local-box", "runner", "app-a", "other"]) {
    expect(document.querySelector(`input[name^="ai-kind"][value="${value}"]`)).toBeNull();
  }
  expect(screen.queryByText(/need a technical setup/)).toBeNull();
});

test("choosing Something else lists the other services, the apps and the rest, with a note that they need a technical setup", async () => {
  const user = userEvent.setup();
  api();
  open();
  await user.click(await screen.findByRole("radio", { name: /Something else/ }));
  expect(screen.getByRole("radio", { name: /Something else/ })).toBeChecked();
  expect(screen.getByText(/These need a technical setup/)).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Service C/ })).toBeInTheDocument();
  const apps = screen.getByRole("group", { name: "Use an app you're signed in to" });
  expect(within(apps).getByRole("radio", { name: /App A/ })).toBeInTheDocument();
  expect(within(apps).getByRole("radio", { name: /App B/ })).toBeInTheDocument();
  const more = screen.getByText("More options").closest("details")!;
  expect(within(more).getByRole("radio", { name: /A server on this computer/, hidden: true })).toBeInTheDocument();
  expect(within(more).getByRole("radio", { name: /Another service/, hidden: true })).toBeInTheDocument();
  const inMore = within(more).getAllByRole("radio", { hidden: true }).map((r) => r.getAttribute("value"));
  expect(inMore[inMore.length - 1]).toBe("runner");
  // Choosing a card above closes it again.
  await user.click(screen.getByRole("radio", { name: /Service A/ }));
  expect(screen.queryByRole("radio", { name: /Service C/ })).toBeNull();
});

test("with nothing flagged in the data every service is offered directly, as before", async () => {
  api({ "GET ai/endpoints": () => KINDS.map((k) => ({ ...k, recommended: false, alternative: false })) });
  open();
  expect(await screen.findByRole("radio", { name: /Service A/ })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Service C/ })).toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: /Something else/ })).toBeNull();
  expect(screen.queryByText("Recommended")).toBeNull();
});

// ---- the numbered steps ------------------------------------------------------------------------------------------------

test("the chosen service has four numbered steps, each with a button to its page and its real domain", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  expect(screen.getByRole("heading", { name: "Connect Service A" })).toBeInTheDocument();
  const steps = screen.getAllByRole("listitem").filter((li) => li.classList.contains("numbered-step"));
  expect(steps.map((li) => li.querySelector("strong")?.textContent)).toEqual(["Make an account", "Add credit", "Make a key and copy it", "Paste it here"]);
  const signup = screen.getByRole("link", { name: /Open the sign-up page/ });
  expect(signup).toHaveAttribute("href", `${WEB}console.service-a.example.com/signup`);
  expect(signup).toHaveAttribute("target", "_blank");
  expect(signup).toHaveAttribute("rel", "noopener noreferrer");
  expect(signup).toHaveAccessibleName(/console\.service-a\.example\.com/);
  expect(screen.getByRole("link", { name: /Open the billing page/ })).toHaveAttribute("href", `${WEB}console.service-a.example.com/billing`);
  expect(screen.getByRole("link", { name: /Open the keys page/ })).toHaveAttribute("href", `${WEB}console.service-a.example.com/keys`);
  expect(screen.getByText(/shows it only once, so copy it/)).toBeInTheDocument();
});

test("the credit step says about what to add, from the day limit the app starts with", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  expect(await screen.findByText(/About \$10 is plenty to start; the app stops for the day at \$2 whatever you add\./)).toBeInTheDocument();
});

test("a step with no page to open has no button", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service B");
  expect(screen.queryByRole("link", { name: /sign-up page/ })).toBeNull();
  expect(screen.queryByRole("link", { name: /billing page/ })).toBeNull();
  expect(screen.getByRole("link", { name: /Open the keys page/ })).toBeInTheDocument();
  expect(screen.getByText("Make an account")).toBeInTheDocument();
});

test("the key hint says in plain words where the key is kept and that it isn't in settings or backups", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  const hint = await screen.findByText(/^Saved only in a private folder on this computer/);
  expect(hint).toHaveTextContent("Saved only in a private folder on this computer, outside your settings and backups.");
  expect(hint.textContent ?? "").not.toMatch(/settings file/i);
});

test("the key box is hidden text that can be shown", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  const key = screen.getByLabelText("Access key");
  expect(key).toHaveAttribute("type", "password");
  expect(key).toHaveAttribute("autocomplete", "off");
  await user.click(screen.getByRole("button", { name: "Show" }));
  expect(key).toHaveAttribute("type", "text");
  await user.click(screen.getByRole("button", { name: "Hide" }));
  expect(key).toHaveAttribute("type", "password");
});

// ---- the check on paste ------------------------------------------------------------------------------------------------

test("there is no Check button for a key: pasting it checks it at once, and says it works", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
  await user.click(screen.getByLabelText("Access key"));
  await user.paste("pasted-key");
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)).toHaveLength(1);
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key: "pasted-key" });
  // Every kind of work is tried with the model it will use, before anything is saved.
  expect(checks(calls)).toHaveLength(1);
  expect(checks(calls)[0].body).toEqual({
    endpoint: "service-a",
    key: "pasted-key",
    models: { everyday: "model-a" },
    use: { routine: "everyday", deep: "everyday" },
  });
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(false);
});

test("a typed key is checked when the cursor leaves the box, or on Enter, never on every letter", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  await user.type(screen.getByLabelText("Access key"), "secret-value");
  expect(checks(calls)).toHaveLength(0);
  await user.tab();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(checks(calls)).toHaveLength(1);
  // Enter checks too, and never adds the account.
  await user.type(screen.getByLabelText("Access key"), "x{Enter}");
  await waitFor(() => expect(checks(calls)).toHaveLength(2));
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(false);
});

test("changing the key takes the answer back until the new key has been checked", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pasted(user);
  await user.type(screen.getByLabelText("Access key"), "x");
  expect(screen.queryByText("Works. Ready to use.")).toBeNull();
  expect(screen.queryByRole("group", { name: /to read your work mail and notes/ })).toBeNull();
});

test.each([
  ["a key the service didn't accept", "The service didn't accept that key. Check that it was copied whole and is still active."],
  ["an account with no credit", "That account has no credit left. Add credit on the service's billing page, then paste the key again."],
  ["a service that can't be reached", "Couldn't reach the service. Check your internet connection and try again."],
])("%s is said in its own words, and Save says what is wrong", async (_, message) => {
  const user = userEvent.setup();
  api({ "POST ai/account-check": () => ({ ok: false, reason: "failed", message }) });
  open();
  await pick(user, "Service A");
  await user.click(screen.getByLabelText("Access key"));
  await user.paste("a-key");
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByText("Works. Ready to use.")).toBeNull();
  expect(save()).toBeDisabled();
  expect(screen.getByText("That didn't work yet. See above, then try again.")).toBeInTheDocument();
  // A hosted service never gets the advice for a service on this computer.
  expect(document.body.textContent ?? "").not.toMatch(/start it if it runs on this computer/);
});

test("a problem listing the models is the reason, and the check isn't run", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/models": () => ({ models: [], problem: "The service didn't accept that key. Check that it was copied whole and is still active." }) });
  open();
  await pick(user, "Service A");
  await user.click(screen.getByLabelText("Access key"));
  await user.paste("wrong");
  expect(await screen.findByRole("alert")).toHaveTextContent("didn't accept that key");
  expect(checks(calls)).toHaveLength(0);
  expect(screen.queryByLabelText("AI model name")).toBeNull();
  expect(save()).toBeDisabled();
});

test("a service that lists no models asks for the model's name, and the check waits for it", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/models": () => ({ models: [] }) });
  open();
  await pick(user, "Service A");
  await user.click(screen.getByLabelText("Access key"));
  await user.paste("secret-value");
  const model = await screen.findByLabelText("AI model name");
  expect(checks(calls)).toHaveLength(0);
  expect(screen.getByText("Name the AI model to go on.")).toBeInTheDocument();
  await user.type(model, "typed-model");
  await user.tab();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(checks(calls)).toHaveLength(1);
  expect(checks(calls)[0].body).toMatchObject({ models: { everyday: "typed-model" } });
});

// ---- the model: chosen for each kind of work, its picker in Advanced ---------------------------------------------------

test("the model is picked for each kind of work and its name is never shown outside Advanced", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pasted(user);
  expect(screen.getByText("A fitting model is picked for each kind of work. You can change it under Advanced.")).toBeInTheDocument();
  const advanced = screen.getByText("Advanced").closest("details")!;
  const everyday = within(advanced).getByLabelText("AI model for everyday work", { selector: "select" });
  expect(everyday).toHaveValue("model-a");
  const outside = (document.body.textContent ?? "").replace(advanced.textContent ?? "", "");
  expect(outside).not.toMatch(/model-a|model-b/);
});

test("the pickers under Advanced list the models with what each costs, and a new choice is checked again", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pasted(user);
  const advanced = screen.getByText("Advanced").closest("details")!;
  const everyday = within(advanced).getByLabelText("AI model for everyday work");
  expect(within(everyday).getAllByRole("option").map((o) => o.textContent)).toEqual(["model-a", "model-b", "model-c"]);
  expect(screen.getByText(/Reads up to about 200,000 text units at once\. Per million text units: \$3\.00 to read, \$15\.00 to write\./)).toBeInTheDocument();
  const harder = within(advanced).getByLabelText("AI model for harder work (optional)");
  expect(within(harder).getAllByRole("option").map((o) => o.textContent)).toEqual(["Same as the everyday model", "model-a", "model-b", "model-c"]);
  await user.selectOptions(harder, "model-b");
  await waitFor(() => expect(checks(calls)).toHaveLength(2));
  expect(checks(calls)[1].body).toMatchObject({ models: { everyday: "model-a", harder: "model-b" }, use: { routine: "everyday", deep: "harder" } });
  await user.selectOptions(everyday, "model-c");
  await waitFor(() => expect(checks(calls)).toHaveLength(3));
  expect(screen.getByText("Reading costs $0.25 per million text units.")).toBeInTheDocument();
});

test("a long list of models can be narrowed by typing, under Advanced", async () => {
  const user = userEvent.setup();
  const many = Array.from({ length: 20 }, (_, i) => ({ id: `model-${String(i).padStart(2, "0")}` }));
  api({ "POST ai/models": () => ({ models: many }) });
  open();
  await pasted(user);
  const everyday = screen.getByLabelText("AI model for everyday work");
  const harder = screen.getByLabelText("AI model for harder work (optional)");
  expect(everyday).toHaveValue("model-00");
  await user.selectOptions(harder, "model-05");
  await user.type(screen.getByLabelText("Find a model"), "model-1");
  expect(within(everyday).getAllByRole("option").map((o) => o.textContent)).toEqual(Array.from({ length: 10 }, (_, i) => `model-${10 + i}`));
  expect(everyday).toHaveValue("model-10");
  expect(harder).toHaveValue("model-10");
  await user.clear(screen.getByLabelText("Find a model"));
  expect(within(everyday).getAllByRole("option")).toHaveLength(20);
});

test("when nothing matches the search there is no model to pick and Save waits", async () => {
  const user = userEvent.setup();
  const many = Array.from({ length: 20 }, (_, i) => ({ id: `model-${String(i).padStart(2, "0")}` }));
  api({ "POST ai/models": () => ({ models: many }) });
  open();
  await ready(user);
  expect(save()).toBeEnabled();
  await user.type(screen.getByLabelText("Find a model"), "zzz");
  expect(screen.getByText("No model matches.")).toBeInTheDocument();
  expect(save()).toBeDisabled();
  await user.clear(screen.getByLabelText("Find a model"));
  expect(save()).toBeEnabled();
});

// ---- the question about work mail and notes ----------------------------------------------------------------------------

test("the question names the account and its sign-in, offers Allow and Not now, and has nothing chosen", async () => {
  const user = userEvent.setup();
  api({ "POST ai/account-check": () => ({ ...WORKS, identity: "sam@example.com", identity_unknown: null }) });
  open();
  await pasted(user);
  const question = await screen.findByRole("group", { name: "Allow Service A account, signed in as sam@example.com, to read your work mail and notes?" });
  const allow = within(question).getByRole("radio", { name: /^Allow/ });
  const notNow = within(question).getByRole("radio", { name: /^Not now/ });
  expect(allow).not.toBeChecked();
  expect(notNow).not.toBeChecked();
  expect(save()).toBeDisabled();
  expect(screen.getByText("Choose Allow or Not now above.")).toBeInTheDocument();
  await user.click(allow);
  expect(save()).toBeEnabled();
});

test("where the account's sign-in can't be told the question says so in plain words", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pasted(user);
  expect(await screen.findByRole("group", { name: "Allow Service A account to read your work mail and notes?" })).toBeInTheDocument();
  expect(screen.getByText("We can't tell who it is signed in as: the service doesn't say whose account the key belongs to.")).toBeInTheDocument();
});

test("the question isn't asked before the key works", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  expect(screen.queryByRole("group", { name: /to read your work mail and notes/ })).toBeNull();
});

test("Allow lets the account read open and internal material; Not now leaves it at open material only", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await ready(user, "Allow");
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).allowed_data).toEqual(["open", "internal"]);
  expect(body(calls).work_data ?? "").toBe("");

  const again = api();
  document.body.innerHTML = "";
  open();
  await ready(user, "Not now");
  await user.click(save());
  await waitFor(() => expect(body(again)).toBeDefined());
  expect(body(again).allowed_data).toEqual(["open"]);
  // Not now is kept with the account, so Today can offer the yes again.
  expect(body(again).work_data).toBe("not_now");
});

test("the three levels stay under Advanced, with Open the only one ticked until the person says more", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pasted(user);
  const advanced = screen.getByText("Advanced").closest("details")!;
  const levels = within(advanced).getByRole("group", { name: "What it may see" });
  expect(within(levels).getByLabelText("Open material")).toBeChecked();
  expect(within(levels).getByLabelText("Internal material")).not.toBeChecked();
  expect(within(levels).getByLabelText("Restricted material")).not.toBeChecked();
  expect(within(levels).getByText("Material goes only to AI accounts you've allowed for its privacy level.")).toBeInTheDocument();
  expect(within(levels).getByText("Your notes, mail and meetings are internal, so the assistant can work on them only once Internal is ticked.")).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: /^Allow/ }));
  expect(within(levels).getByLabelText("Internal material")).toBeChecked();
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  expect(within(levels).getByLabelText("Internal material")).not.toBeChecked();
});

test("no level at all stops Save", async () => {
  const user = userEvent.setup();
  api();
  open();
  await ready(user, "Not now");
  expect(save()).toBeEnabled();
  await user.click(within(screen.getByText("Advanced").closest("details")!).getByLabelText("Open material"));
  expect(save()).toBeDisabled();
});

// ---- spending as a sentence --------------------------------------------------------------------------------------------

test("spending is one sentence with the amounts in the workspace's currency, and Change opens money fields", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pick(user, "Service A");
  const line = await screen.findByText(/It asks you before anything over/);
  expect(line).toHaveTextContent("It asks you before anything over $0.10, and stops for the day at $2. Change");
  expect(within(line).getByText("$0.10").tagName).toBe("STRONG");
  expect(screen.queryByLabelText("Ask me before anything over")).toBeNull();
  await user.click(within(line).getByRole("button", { name: "Change" }));
  const ask = screen.getByLabelText("Ask me before anything over");
  const day = screen.getByLabelText("Stop for the day at");
  expect(ask).toHaveValue("0.1");
  expect(day).toHaveValue("2");
  expect(ask.closest(".money-field")).toHaveTextContent("$");
  expect(document.body.textContent ?? "").not.toMatch(/\(USD\)/);
});

test("the currency symbol comes from the workspace's own wording", async () => {
  const user = userEvent.setup();
  api();
  renderApp(<WelcomeAi local done={false} />, { "money.symbol": "€", "money.usd": "€{amount}" });
  await pick(user, "Service A");
  expect(await screen.findByText(/It asks you before anything over/)).toHaveTextContent("€0.10");
});

test("a changed amount is saved with Save, together with the account, and a bad one stops Save", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await ready(user);
  await user.click(screen.getByRole("button", { name: "Change" }));
  const day = screen.getByLabelText("Stop for the day at");
  await user.clear(day);
  await user.type(day, "abc");
  expect(screen.getByRole("alert")).toHaveTextContent("Use a number, such as 0.10.");
  expect(save()).toBeDisabled();
  await user.clear(day);
  await user.type(day, "5");
  await user.click(save());
  await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
  expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { "ai.budgets.per_day_usd": 5 }, reset: [], fingerprint: "fp-1" });
  expect(body(calls)).toBeDefined();
});

// ---- saving ------------------------------------------------------------------------------------------------------------

test("Save adds the account with the model chosen, tests it, and lists one plain line per kind of work", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/test": () => [
      { tier: "routine", account: "service-a", main: true, ok: true, detail: "answered" },
      { tier: "deep", account: "service-a", main: true, ok: true, detail: "answered" },
    ],
  });
  open();
  await ready(user);
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "service-a",
    label: "Service A account",
    adapter: "adapter-one",
    endpoint: "service-a",
    base_url: `${WEB}api.service-a.example.com/v1`,
    key: "secret-value",
    models: { everyday: "model-a" },
    allowed_data: ["open", "internal"],
    use: { routine: "everyday", deep: "everyday" },
    fingerprint: "fp-1",
  });
  await waitFor(() => expect(calls.filter((c) => c.route === "POST ai/test")).toHaveLength(1));
  const results = (await screen.findAllByRole("listitem")).filter((r) => r.closest(".test-results"));
  expect(results.map((r) => r.textContent)).toEqual(["Everyday work: service-a — answered ✓", "Harder work: service-a — answered ✓"]);
  expect(document.body.textContent ?? "").not.toMatch(/temperature|max output|stub|routine|deep|restart/i);
});

test("a test that fails after saving shows its reason with a word and a cross, and saving again tests again without adding twice", async () => {
  const user = userEvent.setup();
  let first = true;
  const calls = api({
    "POST ai/test": () => {
      const bad = first;
      first = false;
      return [{ tier: "routine", account: "service-a", main: true, ok: !bad, detail: bad ? "The key was refused." : "answered" }];
    },
  });
  open();
  await ready(user);
  await user.click(save());
  const line = await screen.findByText(/didn't answer/);
  expect(line).toHaveTextContent("Everyday work: service-a — didn't answer: The key was refused. ✗");
  await user.click(save());
  await waitFor(() => expect(calls.filter((c) => c.route === "POST ai/test")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST ai/accounts")).toHaveLength(1);
});

test("a refusal shows the server's words and keeps what was typed", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts": () => new Refuse(409, "There is already an account called service-a.") });
  open();
  await ready(user);
  await user.click(save());
  expect(await screen.findByRole("alert")).toHaveTextContent("There is already an account called service-a.");
  expect(screen.getByLabelText("Access key")).toHaveValue("secret-value");
});

test("Save says what is missing until a service is chosen, and when one already works it only asks nothing", async () => {
  const user = userEvent.setup();
  api();
  open();
  await screen.findByRole("radio", { name: /Service A/ });
  expect(save()).toBeDisabled();
  expect(screen.getByText("Choose an AI service to go on.")).toBeInTheDocument();
  await pick(user, "Service A");
  expect(screen.getByText("Paste your key to go on.")).toBeInTheDocument();
  document.body.innerHTML = "";
  api();
  open({ done: true });
  await screen.findByRole("radio", { name: /Service A/ });
  expect(save()).toBeEnabled();
});

test("when the guide step was already done, using it for my work starts unticked, under Advanced, and sends no use", async () => {
  const user = userEvent.setup();
  const calls = api();
  open({ done: true });
  await ready(user);
  const advanced = screen.getByText("Advanced").closest("details")!;
  expect(within(advanced).getByLabelText("Use it for my work")).not.toBeChecked();
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).use).toBeUndefined();
});

test("after saving, the next suggested name looks at the accounts as they are now", async () => {
  const user = userEvent.setup();
  let existing: S["AiAccountView"][] = [];
  api({
    "GET ai/accounts": () => existing,
    "POST ai/accounts": () => {
      existing = [{ name: "service-a", label: "Service A account", kind: "service-a", adapter: "adapter-one", models: { everyday: "model-a" }, used_for: [], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0, accepted_unchecked: false }];
      return { changes: [], fingerprint: "fp-2", needs_restart: false };
    },
  });
  open();
  await ready(user);
  await user.click(save());
  // The account just made is listed by the name the person sees (never its id), with a way to fix or remove it.
  const row = (await screen.findByText("Service A account", { selector: "li[data-row] span[id$=title]" })).closest("li")!;
  expect(within(row).getByRole("button", { name: "More actions for Service A account" })).toBeInTheDocument();
});

test("the suggested name is the service's name, numbered when taken, and the id in the settings follows it", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET settings": () => ({
      fingerprint: "fp-1",
      items: [...SPENDING, { key: "ai.providers.service-a.adapter" }, { key: "ai.providers.service-a-2.adapter" }, { key: "ai.tiers.routine.use" }],
    }),
  });
  open();
  await ready(user);
  const advanced = screen.getByText("Advanced").closest("details")!;
  expect(within(advanced).getByLabelText("Account name", { selector: "input" })).toHaveValue("Service A account");
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).name).toBe("service-a-3");
  expect(body(calls).label).toBe("Service A account");
});

test("a name the person typed under Advanced makes its own id", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await ready(user);
  const name = within(screen.getByText("Advanced").closest("details")!).getByLabelText("Account name", { selector: "input" });
  await user.clear(name);
  await user.type(name, "My AI");
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).name).toBe("my-ai");
  expect(body(calls).label).toBe("My AI");
});

test("Advanced holds the account name, the fixed address read-only and the key's other home", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pick(user, "Service A");
  const advanced = screen.getByText("Advanced").closest("details")!;
  expect(advanced).not.toHaveAttribute("open");
  const address = within(advanced).getByLabelText("Service address", { selector: "input", exact: true });
  expect(address).toHaveValue(`${WEB}api.service-a.example.com/v1`);
  expect(address).toHaveAttribute("readonly");
  await user.type(within(advanced).getByLabelText("Use a saved access key instead"), "env:MODEL_KEY{Enter}");
  expect(screen.getByLabelText("Access key")).toBeDisabled();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key_ref: "env:MODEL_KEY" });
  expect(checks(calls)[0].body).toMatchObject({ key_ref: "env:MODEL_KEY" });
  await user.clear(within(advanced).getByLabelText("Account name", { selector: "input" }));
  expect(save()).toBeDisabled();
});

// ---- something else: servers, programs and other services --------------------------------------------------------------

test("a server found on this computer is offered first, checked at once with no key, and asked about like any account", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/local": () => [{ endpoint: "local-box", name: "A server on this computer", models: ["small-1", "small-2"] }],
  });
  open();
  await user.click(await screen.findByRole("radio", { name: /Something else/ }));
  expect(await screen.findByText("Found A server on this computer on this computer with 2 models. Nothing leaves this computer.")).toBeInTheDocument();
  expect(document.querySelector('input[name^="ai-kind"][value="local-box"]')).toBeNull();
  const use = screen.getByRole("button", { name: "Use it" });
  expect(use).toHaveAttribute("aria-pressed", "false");
  await user.click(use);
  expect(use).toHaveAttribute("aria-pressed", "true");
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)).toHaveLength(0);
  expect(checks(calls)[0].body).toEqual({ endpoint: "local-box", models: { everyday: "small-1" }, use: { routine: "everyday", deep: "everyday" } });
  expect(screen.queryByLabelText("Access key")).toBeNull();
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "local-box",
    label: "A server on this computer account",
    adapter: "adapter-one",
    endpoint: "local-box",
    base_url: "http://localhost:1234/v1",
    models: { everyday: "small-1" },
    allowed_data: ["open"],
    work_data: "not_now",
    use: { routine: "everyday", deep: "everyday" },
    fingerprint: "fp-1",
  });
});

test("a server found with no models says so, never \"0 models\"", async () => {
  const user = userEvent.setup();
  api({ "GET ai/local": () => [{ endpoint: "local-box", name: "A server on this computer", models: [] }] });
  open();
  await user.click(await screen.findByRole("radio", { name: /Something else/ }));
  expect(await screen.findByText(/Found A server on this computer on this computer, but it has no models yet/)).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/\b0 models?\b/);
});

test("a kind on this computer that isn't running is listed under Something else and checked at once with no key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "A server on this computer");
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "local-box" });
  expect(screen.queryByLabelText("Access key")).toBeNull();
});

test("another service asks for its address, checks it when the cursor leaves, and takes an optional key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "Another service");
  expect(save()).toBeDisabled();
  expect(screen.getByText("Enter the service's address to go on.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Service address"), "http://model-host:8080/v1{Enter}");
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(false);
  await user.tab();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "other", base_url: "http://model-host:8080/v1" });
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toMatchObject({ name: "other", endpoint: "other", base_url: "http://model-host:8080/v1" });
  expect(body(calls).key).toBeUndefined();
});

test("a kind chosen under Something else stays chosen, and Something else with it: they are separate choices", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pickElse(user, "Another service");
  expect(screen.getByRole("radio", { name: /^Another service/ })).toBeChecked();
  expect(screen.getByRole("radio", { name: /Something else/ })).toBeChecked();
  const group = (name: RegExp) => screen.getByRole("radio", { name }).getAttribute("name");
  expect(group(/^Another service/)).not.toBe(group(/Something else/));
});

test("a program started by a command asks for it and how it is fed, checks it with the command, and sends its own adapter", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "A command-line program");
  expect(screen.queryByLabelText("Service address")).toBeNull();
  expect(screen.queryByLabelText("Access key")).toBeNull();
  expect(screen.getByRole("radio", { name: "Directly to the app" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Directly from the app" })).toBeChecked();
  await user.type(screen.getByLabelText("How to start the AI app"), "runner --locked  --model {{model}");
  await user.click(screen.getByRole("radio", { name: "As a file" }));
  await user.click(screen.getByRole("radio", { name: "As a file in a folder" }));
  await user.type(screen.getByLabelText("AI model name"), "std");
  await user.tab();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(checks(calls)[0].body).toEqual({
    endpoint: "runner",
    models: { everyday: "std" },
    use: { routine: "everyday", deep: "everyday" },
    agent: { command: ["runner", "--locked", "--model", "{model}"], packet_via: "file", output_via: "outbox" },
  });
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "runner",
    label: "A command-line program account",
    adapter: "adapter-two",
    endpoint: "runner",
    models: { everyday: "std" },
    allowed_data: ["open"],
    work_data: "not_now",
    agent: { command: ["runner", "--locked", "--model", "{model}"], packet_via: "file", output_via: "outbox" },
    use: { routine: "everyday", deep: "everyday" },
    fingerprint: "fp-1",
  });
  expect(modelsAsked(calls)).toHaveLength(0);
});

test("an app that isn't on this computer or can't be asked for a key sends a reference, never a key", async () => {
  const user = userEvent.setup();
  const calls = api();
  open({ local: false });
  await pick(user, "Service A");
  expect(screen.queryByLabelText("Access key")).toBeNull();
  expect(screen.queryByRole("button", { name: "Show" })).toBeNull();
  const where = screen.getByLabelText("Where the access key is kept");
  expect(screen.getByText("Say where the key is kept")).toBeInTheDocument();
  expect(save()).toBeDisabled();
  await user.type(where, "MODEL_KEY");
  await user.tab();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(modelsAsked(calls)[0].body).toEqual({ endpoint: "service-a", key_ref: "env:MODEL_KEY" });
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).key_ref).toBe("env:MODEL_KEY");
  expect(body(calls).key).toBeUndefined();
});

// ---- apps the person is signed in to -----------------------------------------------------------------------------------

test("an installed app asks for no key and no command, is checked at once, and says it is installed", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "App A");
  expect(screen.queryByLabelText("Access key")).toBeNull();
  expect(screen.queryByLabelText("How to start the AI app")).toBeNull();
  expect(screen.getByText("Installed on this computer")).toBeInTheDocument();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  // An app left to choose its own model is checked on its own first one.
  expect(checks(calls)[0].body).toEqual({ endpoint: "app-a", models: { default: "default" }, use: {} });
});

test("an app left to choose its own model is added with no models and works through its first one", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "App A");
  const model = screen.getByLabelText("AI model");
  expect(within(model).getAllByRole("option").map((o) => o.textContent)).toEqual(["Let the app choose", "alpha", "beta", "Another AI model"]);
  expect(model).toHaveValue("");
  await screen.findByText("Works. Ready to use.");
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toEqual({
    name: "app-a",
    label: "App A account",
    adapter: "adapter-two",
    endpoint: "app-a",
    models: {},
    allowed_data: ["open"],
    work_data: "not_now",
    use_for: ["routine", "deep"],
    fingerprint: "fp-1",
  });
  expect(modelsAsked(calls)).toHaveLength(0);
});

test("an app that picks its own model and names no examples asks for no model", async () => {
  const user = userEvent.setup();
  api({ "GET ai/endpoints": () => KINDS.map((k) => (k.id === "app-a" ? { ...k, model_examples: [] } : k)) });
  open();
  await pickElse(user, "App A");
  expect(screen.queryByLabelText("AI model")).toBeNull();
  expect(screen.getByText("Change the model in that app's settings.")).toBeInTheDocument();
});

test("an app's example models can be chosen, checked again, and another model can be typed", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "App A");
  await screen.findByText("Works. Ready to use.");
  await user.selectOptions(screen.getByLabelText("AI model"), "beta");
  await waitFor(() => expect(checks(calls)).toHaveLength(2));
  expect(checks(calls)[1].body).toMatchObject({ models: { everyday: "beta" } });
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls).models).toEqual({ everyday: "beta" });
  expect(body(calls).agent).toBeUndefined();
});

test("choosing another model asks for its name, and Save waits for it", async () => {
  const user = userEvent.setup();
  api();
  open();
  await pickElse(user, "App A");
  await screen.findByText("Works. Ready to use.");
  await user.selectOptions(screen.getByLabelText("AI model"), "Another AI model");
  await user.type(screen.getByLabelText("AI model name"), "typed-model");
  await user.tab();
  await screen.findByText("Works. Ready to use.");
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  expect(save()).toBeEnabled();
});

test("an app whose model must be named starts on its first example", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await pickElse(user, "App B");
  const model = screen.getByLabelText("AI model");
  expect(within(model).getAllByRole("option").map((o) => o.textContent)).toEqual(["gamma", "delta", "Another AI model"]);
  expect(model).toHaveValue("gamma");
  expect(checks(calls)).toHaveLength(0); // not installed yet: nothing to check
});

test("an app that is not found says what to do, and Check looks again and then checks it", async () => {
  const user = userEvent.setup();
  let installed = false;
  const calls = api({ "GET ai/endpoints": () => KINDS.map((k) => (k.id === "app-b" ? { ...k, installed } : k)) });
  open();
  await pickElse(user, "App B");
  expect(screen.getByText("This app isn't on this computer yet. Install it and sign in to it, then choose Check.")).toBeInTheDocument();
  expect(save()).toBeDisabled();
  installed = true;
  await user.click(screen.getByRole("button", { name: "Check" }));
  expect(await screen.findByText("Installed on this computer")).toBeInTheDocument();
  expect(await screen.findByText("Works. Ready to use.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "GET ai/endpoints").length).toBeGreaterThan(1);
  expect(checks(calls)[0].body).toMatchObject({ endpoint: "app-b", models: { everyday: "gamma" } });
});

test("when it can't be told whether a program is installed, nothing is claimed", async () => {
  const user = userEvent.setup();
  api({ "GET ai/endpoints": () => KINDS.map((k) => (k.id === "app-b" ? { ...k, installed: null } : k)) });
  open();
  await pickElse(user, "App B");
  expect(screen.queryByText(/^Installed on this computer/)).toBeNull();
  expect(screen.queryByText(/isn't on this computer yet/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Check" })).toBeNull();
});

test("after saving an app, a sign-in failure shows the hint from its test", async () => {
  const user = userEvent.setup();
  api({
    "POST ai/test": () => [{ tier: "routine", account: "app-a", main: true, ok: false, detail: "Sign in once in a terminal." }],
  });
  open();
  await pickElse(user, "App A");
  await screen.findByText("Works. Ready to use.");
  await user.click(screen.getByRole("radio", { name: /^Not now/ }));
  await user.click(save());
  const line = await screen.findByText(/didn't answer/);
  expect(line).toHaveTextContent("Everyday work: app-a — didn't answer: Sign in once in a terminal. ✗");
});

test("an account whose sign-in the app can read is asked about by that sign-in", async () => {
  const user = userEvent.setup();
  api({ "POST ai/account-check": () => ({ ...WORKS, identity: "pat@example.com", identity_unknown: null }) });
  open();
  await pickElse(user, "App A");
  expect(await screen.findByRole("group", { name: "Allow App A account, signed in as pat@example.com, to read your work mail and notes?" })).toBeInTheDocument();
});
