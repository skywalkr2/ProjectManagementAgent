import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { WelcomeAi } from "./WelcomeAi";

/** The amount the person asked to be asked above. */
const LIMIT = { key: "ai.budgets.confirm_above_usd", value: 0.1 };

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

const KINDS = [
  {
    id: "service-a",
    name: "Service A",
    adapter: "adapter-one",
    base_url: `${WEB}api.service-a.example.com/v1`,
    key_url: `${WEB}console.service-a.example.com/keys`,
    needs_key: true,
    local: false,
    note: "",
    allowed_data: ["open"],
    program: "",
    model_optional: false,
    model_examples: [],
    installed: null,
  },
] as S["EndpointView"][];

const MODELS: S["AiModelView"][] = [
  { id: "model-a", input_per_million: 3, output_per_million: 15 },
  { id: "model-b", input_per_million: 6, output_per_million: 30 },
];

const view = (name: string, label: string, extra: Partial<S["AiAccountView"]> = {}): S["AiAccountView"] => ({
  name,
  label,
  kind: "service-a",
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "model-a" },
  used_for: [],
  backup_for: [],
  has_key: true,
  key_state: "saved",
  key_where: null,
  key_ending: false,
  answered_at: null,
  spent_today_usd: 0,
  checked_for: [],
  check_failed_for: [],
  checked_at: null,
  paused_until: null,
  check_usd: null,
  ...extra,
});

const MAIN = view("main", "Main account", { used_for: ["routine", "deep"] });
const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false };
const answered = (name: string) => () => [{ tier: "account", account: name, main: false, ok: true, detail: "answered" }];

function api(accounts: S["AiAccountView"][], extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET ai/accounts": () => accounts,
    "GET ai/local": () => [],
    "GET ai/check-size": () => ({ calls: 10, input_tokens: 1000, output_tokens: 200 }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [LIMIT] }),
    "POST ai/models": () => ({ models: MODELS }),
    "POST ai/accounts": () => SAVED,
    "POST ai/accounts/service-a-account": () => SAVED,
    "POST ai/accounts/main": () => SAVED,
    ...extra,
  });
}

const open = (drawer: Partial<NonNullable<React.ComponentProps<typeof WelcomeAi>["drawer"]>> = {}) => {
  const handlers = { onAdded: vi.fn(), onCancel: vi.fn(), onDirty: vi.fn(), ...drawer };
  renderApp(<WelcomeAi local done drawer={handlers} />);
  return handlers;
};

/** Choose the service, paste its key and check it, which lists its models. */
async function keyed(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("radio", { name: /Service A/ }));
  await user.type(screen.getByLabelText("Key"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByLabelText("Model for everyday work");
}
const body = (calls: ReturnType<typeof fakeApi>) => calls.find((c) => c.route === "POST ai/accounts")?.body as S["AiAccountAdd"];

test("the cursor starts in the first main field, and the account list and the guide's test are not in the drawer", async () => {
  api([MAIN]);
  open();
  await waitFor(() => expect(screen.getByRole("radio", { name: /Service A/ })).toHaveFocus());
  expect(screen.queryByRole("heading", { name: /AI accounts/ })).toBeNull();
  expect(screen.queryByRole("button", { name: "Test AI" })).toBeNull();
});

test("it asks What is it for? with the three choices and what each does, and the button carries the cost of the check", async () => {
  const user = userEvent.setup();
  api([MAIN]);
  open();
  await keyed(user);
  expect(screen.getByLabelText("Name it")).toHaveValue("Service A account");
  const group = screen.getByRole("group", { name: "What is it for?" });
  const choices = within(group).getAllByRole("radio");
  expect(choices.map((c) => c.closest("label")?.querySelector("strong")?.textContent)).toEqual(["Helper's work", "A backup", "Nothing yet"]);
  expect(group).toHaveTextContent("It becomes the main account. Main account becomes its backup.");
  expect(group).toHaveTextContent("Stands in when Main account can't answer. Checked for each kind of work first (about $0.006).");
  expect(group).toHaveTextContent("Kept here to test or compare.");
  // With something already doing the work, a backup is the likely answer.
  expect(within(group).getByRole("radio", { name: /A backup/ })).toBeChecked();
  expect(screen.getByRole("button", { name: "Add and check (about $0.006)" })).toBeEnabled();
  await user.click(within(group).getByRole("radio", { name: /Nothing yet/ }));
  expect(screen.getByRole("button", { name: "Add account" })).toBeEnabled();
});

test("with nothing doing the work there is no backup to be: the account is for the work by default", async () => {
  const user = userEvent.setup();
  api([]);
  open();
  await keyed(user);
  const group = screen.getByRole("group", { name: "What is it for?" });
  expect(within(group).queryByRole("radio", { name: /A backup/ })).toBeNull();
  expect(within(group).getByRole("radio", { name: /Helper's work/ })).toBeChecked();
  expect(group).toHaveTextContent("It becomes the main account.");
  expect(group).not.toHaveTextContent("becomes its backup");
});

test("Nothing yet adds the account with its own name and no check, then closes the drawer", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN]);
  const handlers = open();
  await keyed(user);
  await user.click(screen.getByRole("radio", { name: /Nothing yet/ }));
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(body(calls)).toMatchObject({ name: "service-a-account", label: "Service A account" });
  expect(body(calls).use).toBeUndefined();
  expect(calls.some((c) => c.route.includes("/test"))).toBe(false);
  expect(await screen.findByText("Added Service A account.")).toBeInTheDocument();
});

test("a name the person types is theirs: it is sent as the label, and the id in the settings is made from it", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN]);
  open();
  await keyed(user);
  await user.clear(screen.getByLabelText("Name it"));
  await user.type(screen.getByLabelText("Name it"), "Spare key #2");
  await user.click(screen.getByRole("radio", { name: /Nothing yet/ }));
  await user.click(screen.getByRole("button", { name: "Add account" }));
  await waitFor(() => expect(body(calls)).toBeDefined());
  expect(body(calls)).toMatchObject({ name: "spare-key-2", label: "Spare key #2" });
});

test("a second account of the same service gets the next free name", async () => {
  const user = userEvent.setup();
  api([view("service-a", "Service A account")]);
  open();
  await keyed(user);
  expect(screen.getByLabelText("Name it")).toHaveValue("Service A account 2");
});

test("a backup is added, then checked for each kind of work with its exact settings, then made the backup", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN], {
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday": answered("service-a-account"),
    "POST ai/accounts/service-a-account/test?tier=deep&model=everyday": answered("service-a-account"),
  });
  const handlers = open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: /Add and check/ }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(body(calls).use).toBeUndefined();
  const order = calls.map((c) => c.route).filter((r) => r.startsWith("POST ai/accounts"));
  expect(order).toEqual([
    "POST ai/accounts",
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday",
    "POST ai/accounts/service-a-account/test?tier=deep&model=everyday",
    "POST ai/accounts/service-a-account",
  ]);
  expect(calls.find((c) => c.route === "POST ai/accounts/service-a-account")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "everyday" } });
});

test("a backup that fails its check stays added but is not a backup, and the person is told why", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN], {
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday": () => [{ tier: "account", account: "service-a-account", main: false, ok: false, detail: "The key was refused." }],
  });
  const handlers = open();
  await keyed(user);
  await user.click(screen.getByRole("button", { name: /Add and check/ }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Added Service A account, but its check didn't pass: The key was refused.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/service-a-account")).toBe(false);
});

test("for the work it replaces the main account, which stays as its backup when it passes its own check", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN], {
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday": answered("service-a-account"),
    "POST ai/accounts/service-a-account/test?tier=deep&model=everyday": answered("service-a-account"),
    "POST ai/accounts/main/test?tier=routine&model=everyday": answered("main"),
    "POST ai/accounts/main/test?tier=deep&model=everyday": answered("main"),
  });
  const handlers = open();
  await keyed(user);
  await user.click(screen.getByRole("radio", { name: /Helper's work/ }));
  await user.click(screen.getByRole("button", { name: /Add and check/ }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(body(calls).use).toEqual({ routine: "everyday", deep: "everyday" });
  expect(calls.find((c) => c.route === "POST ai/accounts/main")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "everyday" } });
  expect(await screen.findByText("Helper now works with Service A account. Main account stands in if it can't answer.")).toBeInTheDocument();
});

test("when the account it replaces fails its check it is not kept as a backup", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN], {
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday": answered("service-a-account"),
    "POST ai/accounts/service-a-account/test?tier=deep&model=everyday": answered("service-a-account"),
    "POST ai/accounts/main/test?tier=routine&model=everyday": () => [{ tier: "account", account: "main", main: true, ok: false, detail: "refused" }],
  });
  const handlers = open();
  await keyed(user);
  await user.click(screen.getByRole("radio", { name: /Helper's work/ }));
  await user.click(screen.getByRole("button", { name: /Add and check/ }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(await screen.findByText("Helper now works with Service A account. Main account didn't pass its check, so it isn't a backup.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/main")).toBe(false);
});

test("a typed key is unsaved text the drawer asks about, and Cancel closes it", async () => {
  const user = userEvent.setup();
  api([MAIN]);
  const handlers = open();
  await user.click(await screen.findByRole("radio", { name: /Service A/ }));
  expect(handlers.onDirty).toHaveBeenLastCalledWith(false);
  await user.type(screen.getByLabelText("Key"), "secret-value");
  expect(handlers.onDirty).toHaveBeenLastCalledWith(true);
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(handlers.onCancel).toHaveBeenCalledTimes(1);
});

test("a check that would cost more than the amount the person set asks for a second press, with its cost on screen", async () => {
  const user = userEvent.setup();
  const calls = api([MAIN], {
    "GET ai/check-size": () => ({ calls: 10, input_tokens: 1_000_000, output_tokens: 200_000 }),
    "POST ai/accounts/service-a-account/test?tier=routine&model=everyday": answered("service-a-account"),
    "POST ai/accounts/service-a-account/test?tier=deep&model=everyday": answered("service-a-account"),
  });
  const handlers = open();
  await keyed(user);
  // model-a is $3 and $15 per million: 1M read and 0.2M written is $6.
  await user.click(screen.getByRole("button", { name: "Add and check (about $6.00)" }));
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(false);
  expect(screen.getByRole("alert")).toHaveTextContent("The check would cost about $6.00, more than the $0.10 you asked to be asked about.");
  await user.click(screen.getByRole("button", { name: "Go ahead and check (about $6.00)" }));
  await waitFor(() => expect(handlers.onAdded).toHaveBeenCalledTimes(1));
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(true);
});
