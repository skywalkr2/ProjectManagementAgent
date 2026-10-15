import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AiAccounts } from "./AiAccounts";

// Names are made up here: the service shown comes from the catalog entry the account says it was made from.
const KINDS = [
  { id: "service-a", name: "Service A", adapter: "adapter-one", base_url: "", needs_key: true, note: "" },
  { id: "app-a", name: "App A", adapter: "adapter-two", base_url: "", needs_key: false, note: "", program: "app-a-cli", model_examples: ["alpha", "beta"] },
] as S["EndpointView"][];

const account = (name: string, extra: Partial<S["AiAccountView"]> = {}): S["AiAccountView"] => ({
  name,
  kind: "service-a",
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "model-a" },
  used_for: [],
  has_key: true,
  key_state: extra.has_key === false ? "none" : "saved",
  key_where: null,
  ...extra,
});

const LIST = [
  account("main", { used_for: ["routine", "deep"] }),
  account("spare", { has_key: false }),
  account("signed-in", { kind: "app-a", has_key: false, models: { default: "default" } }),
  account("odd", { kind: "gone-kind" }),
];

const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false };

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/accounts": () => LIST,
    "GET ai/endpoints": () => KINDS,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    ...extra,
  });
}

const open = (local = true) => renderApp(<AiAccounts local={local} />);
const row = async (name: string) => (await screen.findByText(name, { selector: "strong" })).closest("li") as HTMLElement;
const menu = async (user: ReturnType<typeof userEvent.setup>, name: string, item: string) => {
  await user.click(within(await row(name)).getByRole("button", { name: `More actions for ${name}` }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
};

test("one row per account: its service, a plain key status and one primary action, the rest in its menu", async () => {
  const user = userEvent.setup();
  api();
  open();
  expect(await screen.findByRole("heading", { name: "Your AI accounts" })).toBeInTheDocument();
  const main = await row("main");
  expect(main).toHaveTextContent("Service: Service A");
  expect(main).toHaveTextContent("Key saved");
  expect(main).toHaveTextContent("Does: Everyday work, Harder work");
  expect(within(main).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Test main", "More actions for main"]);
  // Without a key, in words and not by colour.
  expect(await row("spare")).toHaveTextContent("No key");
  expect(await row("spare")).toHaveTextContent("Not used for any work yet.");
  // An app that needs no key does not say it lacks one.
  const app = await row("signed-in");
  expect(app).toHaveTextContent("Service: App A");
  expect(app).toHaveTextContent("No key needed");
  // A kind the list doesn't know leaves just the account's own name.
  expect(await row("odd")).not.toHaveTextContent("Service:");
  await user.click(within(main).getByRole("button", { name: "More actions for main" }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Replace key", "Set when the key ends", "Change models", "Remove"]);
});

test("no accounts says so, and a list that didn't load says so quietly", async () => {
  api({ "GET ai/accounts": () => []});
  const view = open();
  expect(await screen.findByText("No AI account is set up yet.")).toBeInTheDocument();
  view.unmount();
  api({ "GET ai/accounts": () => new Refuse(500, "") });
  open();
  expect(await screen.findByText("The list of AI accounts didn't load.")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Your AI accounts" })).toBeNull();
});

test("Test calls the account's own test and shows its one result line", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/accounts/main/test": () => [{ tier: "account", account: "main", main: true, ok: true, detail: "answered" }],
  });
  open();
  await user.click(within(await row("main")).getByRole("button", { name: "Test main" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/main/test")).toBe(true));
  expect(calls.some((c) => c.route === "POST ai/test")).toBe(false);
  expect(await within(await row("main")).findByText("Answered")).toBeInTheDocument();
  expect(await row("main")).toHaveTextContent("Answered ✓");
});

test("an account that does no work yet can be tested, and a failure shows the detail", async () => {
  const user = userEvent.setup();
  api({
    "POST ai/accounts/spare/test": () => [{ tier: "account", account: "spare", main: false, ok: false, detail: "The key was refused." }],
  });
  open();
  await user.click(within(await row("spare")).getByRole("button", { name: "Test spare" }));
  expect(await within(await row("spare")).findByText(/Didn't answer: The key was refused\./)).toBeInTheDocument();
  expect(await row("spare")).toHaveTextContent("✗");
  expect(screen.queryByText(/nothing to test/)).toBeNull();
});

test("a key that isn't there says where it was looked for, in words and with a mark", async () => {
  api({
    "GET ai/accounts": () => [
      account("lost", { has_key: true, key_state: "missing", key_where: "the environment variable NAME", used_for: ["routine"] }),
      account("plain", { has_key: false, key_state: "none" }),
    ],
  });
  open();
  const lost = await row("lost");
  expect(lost).toHaveTextContent("Key not found: the environment variable NAME");
  expect(lost).not.toHaveTextContent("Key saved");
  // The missing key is marked by an icon as well as by words, never by color alone.
  expect(lost.querySelector(".key-missing")).toHaveTextContent("Key not found");
  expect(lost.querySelector('.key-missing [data-icon="alert"]')).not.toBeNull();
  expect(await row("plain")).toHaveTextContent("No key");
  expect(await row("plain")).not.toHaveTextContent("Key not found");
});

test("accounts that work come first; one with a missing key or no work follows", async () => {
  api({
    "GET ai/accounts": () => [
      account("idle"),
      account("lost", { key_state: "missing", key_where: "somewhere", used_for: ["routine"] }),
      account("busy", { used_for: ["routine"] }),
      account("also-busy", { used_for: ["deep"] }),
    ],
  });
  open();
  await row("busy");
  const names = Array.from(document.querySelectorAll("li[data-row] strong")).map((n) => n.textContent);
  expect(names).toEqual(["busy", "also-busy", "idle", "lost"]);
});

test("Remove acts at once, reads back with Undo, and Undo posts the change back to the settings", async () => {
  const user = userEvent.setup();
  const before = { adapter: "adapter-one", models: { everyday: "model-a" } };
  const calls = api({
    "POST ai/accounts/spare/remove": () => ({
      changes: [{ key: "ai.providers.spare", before, after: null, was_default: false, is_default: true }],
      fingerprint: "fp-2",
      needs_restart: false,
    }),
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
  });
  open();
  await menu(user, "spare", "Remove");
  expect(screen.queryByRole("dialog")).toBeNull();
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare/remove")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("Removed the account spare.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { "ai.providers.spare": before }, reset: [], fingerprint: "fp-2" }));
});

test("a change that needs a restart asks first and never restarts by itself", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/spare/remove": () => ({ ...SAVED, needs_restart: true }) });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <AiAccounts local />
    </RestartProvider>,
  );
  await menu(user, "spare", "Remove");
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("This change needs the app to restart."));
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("a refused removal shows the server's words in the row", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts/spare/remove": () => new Refuse(404, "There is no account called spare.") });
  open();
  await menu(user, "spare", "Remove");
  expect(await within(await row("spare")).findByRole("alert")).toHaveTextContent("There is no account called spare.");
});

test("Replace key sends the new key once and does not keep it on screen", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/spare": () => SAVED });
  open();
  await menu(user, "spare", "Replace key");
  const field = await screen.findByLabelText("New key");
  expect(field).toHaveAttribute("type", "password");
  const save = screen.getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.type(field, "fresh-secret");
  await user.click(save);
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", key: "fresh-secret" }));
  expect(await screen.findByText("Replaced the key for spare.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByLabelText("New key")).toBeNull());
});

test("on a hosted app Replace key asks where the key is and sends a reference", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/spare": () => SAVED });
  open(false);
  await menu(user, "spare", "Replace key");
  await user.type(await screen.findByLabelText("Where the key is"), "env:MODEL_KEY");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", key_ref: "env:MODEL_KEY" }));
});

test("an account whose key has an end date says so, and Set when the key ends sends the day", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET ai/accounts": () => [account("spare", { has_key: false }), account("dated", { credential_expires: "2027-01-31" })],
    "GET ai/endpoints": () => KINDS,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    "POST ai/accounts/spare": () => SAVED,
    "POST ai/accounts/dated": () => SAVED,
  });
  open();
  expect(await row("dated")).toHaveTextContent(/Its key stops working on .*31/);
  expect(await row("spare")).not.toHaveTextContent("stops working");
  await menu(user, "spare", "Set when the key ends");
  const field = await screen.findByLabelText(/The day this key stops working/);
  expect(field).toHaveAttribute("type", "date");
  await user.type(field, "2027-02-15");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", credential_expires: "2027-02-15" }));
  await menu(user, "dated", "Set when the key ends");
  await user.clear(await screen.findByLabelText(/The day this key stops working/));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/dated")?.body).toEqual({ fingerprint: "fp-1", clear_credential_expires: true }));
});

test("replacing the key takes the date typed with it, and drops the old key's date when none is typed", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET ai/accounts": () => [account("spare", { has_key: false }), account("dated", { credential_expires: "2027-01-31" })],
    "GET ai/endpoints": () => KINDS,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    "POST ai/accounts/spare": () => SAVED,
    "POST ai/accounts/dated": () => SAVED,
  });
  open();
  await menu(user, "spare", "Replace key");
  await user.type(await screen.findByLabelText("New key"), "fresh");
  await user.type(screen.getByLabelText(/The day this key stops working/), "2027-03-01");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", key: "fresh", credential_expires: "2027-03-01" }));
  await menu(user, "dated", "Replace key");
  await user.type(await screen.findByLabelText("New key"), "newer");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/dated")?.body).toEqual({ fingerprint: "fp-1", key: "newer", clear_credential_expires: true }));
});

test("Change models edits the ids it has, can add one for harder work, and Cancel changes nothing", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/spare": () => SAVED });
  open();
  await menu(user, "spare", "Change models");
  const everyday = await screen.findByLabelText("Model for everyday work");
  expect(everyday).toHaveValue("model-a");
  const save = screen.getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("Model for everyday work")).toBeNull();
  expect(calls.some((c) => c.route === "POST ai/accounts/spare")).toBe(false);
  await menu(user, "spare", "Change models");
  const again = await screen.findByLabelText("Model for everyday work");
  await user.clear(again);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  await user.type(again, "model-z");
  await user.type(screen.getByLabelText("Model for harder work (optional)"), "model-y");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({
      fingerprint: "fp-1",
      models: { everyday: "model-z", harder: "model-y" },
    }),
  );
  expect(await screen.findByText("Changed the models of spare.")).toBeInTheDocument();
});

test("a refused change shows the server's words and keeps the form open", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts/spare": () => new Refuse(400, "Name at least one model the account uses.") });
  open();
  await menu(user, "spare", "Change models");
  await user.type(await screen.findByLabelText("Model for harder work (optional)"), "model-y");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Name at least one model the account uses.");
  expect(screen.getByLabelText("Model for harder work (optional)")).toHaveValue("model-y");
});

const OFFER = { offered: true, usd: 0.8, cases: 40, runs: 3 };

test("an account that would take the work from another is offered Switch and check, with the cost first, and Switch without checking in its menu", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/accounts/spare/switch-estimate": () => OFFER,
    "POST ai/accounts/spare/switch-check": () => ({ saved: SAVED, checking: true }),
    "POST ai/accounts/spare": () => SAVED,
  });
  open();
  const spare = await row("spare");
  const primary = await within(spare).findByRole("button", { name: "Switch to spare and check it" });
  expect(primary).toHaveTextContent("Switch and check (about $0.80)");
  expect(within(spare).queryByRole("button", { name: "Test spare" })).toBeNull();
  await user.click(within(spare).getByRole("button", { name: "More actions for spare" }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual([
    "Switch without checking",
    "Test",
    "Replace key",
    "Set when the key ends",
    "Change models",
    "Remove",
  ]);
  await user.keyboard("{Escape}");
  await user.click(primary);
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/spare/switch-check")?.body).toEqual({
      fingerprint: "fp-1",
      use: { routine: "everyday", deep: "everyday" },
    }),
  );
  expect(await screen.findByText("Checking spare now. Today says if anything needs a look.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/spare")).toBe(false);
});

test("Switch without checking changes it at once, with the ordinary change and no check", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/accounts/spare/switch-estimate": () => OFFER,
    "POST ai/accounts/spare": () => SAVED,
  });
  open();
  await within(await row("spare")).findByRole("button", { name: "Switch to spare and check it" });
  await menu(user, "spare", "Switch without checking");
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({
      fingerprint: "fp-1",
      use: { routine: "everyday", deep: "everyday" },
    }),
  );
  expect(calls.some((c) => c.route === "POST ai/accounts/spare/switch-check")).toBe(false);
});

test("with no price known the button says Switch and check and no amount; with checks off the row stays as it was", async () => {
  api({ "POST ai/accounts/spare/switch-estimate": () => ({ ...OFFER, usd: null }) });
  const view = open();
  expect(await within(await row("spare")).findByRole("button", { name: "Switch to spare and check it" })).toHaveTextContent(/^Switch and check$/);
  view.unmount();
  api({ "POST ai/accounts/spare/switch-estimate": () => ({ offered: false, usd: null, cases: 0, runs: 0 }) });
  open();
  expect(await within(await row("spare")).findByRole("button", { name: "Test spare" })).toBeInTheDocument();
  await userEvent.setup().click(within(await row("spare")).getByRole("button", { name: "More actions for spare" }));
  expect((await screen.findAllByRole("menuitem"))[0]).toHaveTextContent("Use for the assistant's work");
});

test("changing the model of an account that does the work is a switch: the cost is on the primary button", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/accounts/main/switch-estimate": () => OFFER,
    "POST ai/accounts/main/switch-check": () => ({ saved: SAVED, checking: true }),
  });
  open();
  await menu(user, "main", "Change models");
  const field = await screen.findByLabelText("Model for everyday work");
  await user.clear(field);
  await user.type(field, "model-z");
  const go = await screen.findByRole("button", { name: "Switch and check (about $0.80)" });
  expect(screen.getByRole("button", { name: "Switch without checking" })).toBeInTheDocument();
  await user.click(go);
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/main/switch-check")?.body).toEqual({
      fingerprint: "fp-1",
      models: { everyday: "model-z" },
    }),
  );
  expect(await screen.findByText("Checking main now. Today says if anything needs a look.")).toBeInTheDocument();
});

test("Use as backup checks the account for each kind of work first, then adds it as the backup with Undo", async () => {
  const user = userEvent.setup();
  const answered = (name: string) => () => [{ tier: "account", account: name, main: false, ok: true, detail: "answered" }];
  const calls = api({
    "GET ai/accounts": () => [account("main", { used_for: ["routine", "deep"] }), account("second", { models: { everyday: "model-b", harder: "model-c" } })],
    "POST ai/accounts/second/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/second/test?tier=routine&model=everyday": answered("second"),
    "POST ai/accounts/second/test?tier=deep&model=harder": answered("second"),
    "POST ai/accounts/second": () => ({
      changes: [{ key: "ai.tiers.routine.fallback", before: [], after: ["second/everyday"], was_default: true, is_default: false }],
      fingerprint: "fp-2",
      needs_restart: false,
    }),
  });
  open();
  await menu(user, "second", "Use as backup");
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/second")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "harder" } }),
  );
  const tests = calls.filter((c) => c.route.startsWith("POST ai/accounts/second/test")).map((c) => c.route);
  expect(tests).toEqual(["POST ai/accounts/second/test?tier=routine&model=everyday", "POST ai/accounts/second/test?tier=deep&model=harder"]);
  expect(await screen.findByText("second now stands in when the main account can't answer")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("a failed check adds nothing and shows why; a backup says what it backs up and isn't offered again", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { used_for: ["routine", "deep"] }), account("second")],
    "POST ai/accounts/second/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/second/test?tier=routine&model=everyday": () => [{ tier: "account", account: "second", main: false, ok: false, detail: "The key was refused." }],
  });
  open();
  await menu(user, "second", "Use as backup");
  expect(await within(await row("second")).findByText(/Didn't answer: The key was refused\./)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/second")).toBe(false);
});

test("an account already standing in says so and is offered nothing more; with no account doing the work there is no backup to be", async () => {
  const user = userEvent.setup();
  api({
    "GET ai/accounts": () => [account("main", { used_for: ["routine", "deep"] }), account("second", { backup_for: ["routine", "deep"] }), account("third")],
    "POST ai/accounts/second/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/third/switch-estimate": () => ({ offered: false }),
  });
  open();
  expect(await row("second")).toHaveTextContent("Backup for: Everyday work, Harder work");
  await user.click(within(await row("second")).getByRole("button", { name: "More actions for second" }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).not.toContain("Use as backup");
  await user.keyboard("{Escape}");
  await user.click(within(await row("third")).getByRole("button", { name: "More actions for third" }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toContain("Use as backup");
});

test("Add an account shows only where the screen gives a way to add one", async () => {
  const user = userEvent.setup();
  api();
  const onAdd = vi.fn();
  renderApp(<AiAccounts local onAdd={onAdd} />);
  await user.click(await screen.findByRole("button", { name: "Add an account" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
});

test("without a way to add, as inside the setup guide, there is no Add button", async () => {
  api();
  open();
  await screen.findByRole("heading", { name: "Your AI accounts" });
  expect(screen.queryByRole("button", { name: "Add an account" })).toBeNull();
});
