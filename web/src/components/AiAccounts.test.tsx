import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AiAccounts } from "./AiAccounts";

/** The amount the person asked to be asked above. */
const LIMIT = { key: "ai.budgets.confirm_above_usd", value: 0.1 };

// Names are made up here: the service shown comes from the catalog entry the account says it was made from.
const KINDS = [
  { id: "service-a", name: "Service A", adapter: "adapter-one", base_url: "", needs_key: true, note: "" },
  { id: "app-a", name: "App A", adapter: "adapter-two", base_url: "", needs_key: false, note: "", program: "app-a-cli", model_examples: ["alpha", "beta"] },
] as S["EndpointView"][];

const hoursAgo = (n: number) => new Date(Date.now() - n * 3_600_000).toISOString();

const account = (name: string, extra: Partial<S["AiAccountView"]> = {}): S["AiAccountView"] => ({
  name,
  label: "",
  kind: "service-a",
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "model-a" },
  used_for: [],
  backup_for: [],
  has_key: true,
  key_state: extra.has_key === false ? "none" : "saved",
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

// The settings' ids are never shown: the rows carry the names the person gave.
const LIST = [
  account("main", { label: "Main account", used_for: ["routine", "deep"], answered_at: hoursAgo(2), spent_today_usd: 1.2 }),
  account("second", { label: "Second account", kind: "app-a", has_key: false, key_state: "none", backup_for: ["routine", "deep"], checked_for: ["routine", "deep"], checked_at: "2026-10-14T09:00:00+00:00", models: { default: "default" } }),
  account("trial", { label: "Trial account", key_state: "missing", has_key: true }),
];

const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false };

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET ai/accounts": () => LIST,
    "GET ai/endpoints": () => KINDS,
    "GET settings": () => ({ fingerprint: "fp-1", items: [LIMIT] }),
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    "GET ai/skills": () => ({ min_score: 0.8, stale_days: 60, accounts: [] }),
    ...extra,
  });
}

const open = (local = true) => renderApp(<AiAccounts local={local} />);
const row = async (name: string) => (await screen.findByText(name, { selector: "li[data-row] span[id$='-title']" })).closest("li") as HTMLElement;
const menu = async (user: ReturnType<typeof userEvent.setup>, name: string, item: string) => {
  await user.click(within(await row(name)).getByRole("button", { name: `More actions for ${name}` }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
};
const answered = (name: string) => () => [{ tier: "account", account: name, main: false, ok: true, detail: "answered" }];

test("a heading with the count, the account that does the work, the one that stands in, and every kind of work backed up", async () => {
  api();
  open();
  expect(await screen.findByRole("heading", { name: /AI accounts/ })).toHaveTextContent("AI accounts3");
  const summary = screen.getByRole("group", { name: "Who does the work" });
  expect(summary).toHaveTextContent("Main account does Helper's work → if it can't answer, Second account stands in.");
  expect(summary).toHaveTextContent("Every kind of work has a backup");
  expect(within(summary).getByText("Main account", { selector: "strong" })).toBeInTheDocument();
});

test("harder work with no backup says so and offers Add one", async () => {
  const user = userEvent.setup();
  const onAdd = vi.fn();
  api({
    "GET ai/accounts": () => [
      account("main", { label: "Main account", used_for: ["routine", "deep"] }),
      account("second", { label: "Second account", backup_for: ["routine"] }),
    ],
  });
  renderApp(<AiAccounts local onAdd={onAdd} />);
  const summary = await screen.findByRole("group", { name: "Who does the work" });
  expect(summary).toHaveTextContent("Harder work has no backup");
  await user.click(within(summary).getByRole("button", { name: "Add one" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
});

test("every row says its role in words, its own name, what it covers, its state in words, and shows no id", async () => {
  api();
  open();
  const main = await row("Main account");
  expect(main).toHaveTextContent("Does the work");
  expect(main).toHaveTextContent("Pay as you go · Service A · everyday and harder work");
  expect(main).toHaveTextContent("Ready · answered 2 hours ago · $1.20 today");
  const second = await row("Second account");
  expect(second).toHaveTextContent("Backup");
  expect(second).toHaveTextContent("Signed-in app · App A · stands in for everyday and harder work");
  expect(second).toHaveTextContent("Checked for every kind of work · Oct 14");
  const trial = await row("Trial account");
  expect(trial).toHaveTextContent("Not used");
  expect(trial).toHaveTextContent("Access key not found on this computer");
  // A state that needs attention has an icon as well as words, and no id of the settings is on screen.
  expect(trial.querySelector('[data-icon="alert"]')).not.toBeNull();
  expect(document.body).not.toHaveTextContent(/\b(main|second|trial)\b(?! account)/);
});

test("an account the person didn't name is called by its service, and one with no service by a plain name", async () => {
  api({ "GET ai/accounts": () => [account("a1", { used_for: ["routine"] }), account("a2", { kind: "gone-kind" }), account("a3", { kind: null })] });
  open();
  expect(await row("Service A account")).toBeInTheDocument();
  expect((await screen.findAllByText("AI account", { selector: "span[id$=title]" })).length).toBe(2);
});

test("accounts that do the work come first, then backups, then the rest; a broken one is last in its group", async () => {
  api({
    "GET ai/accounts": () => [
      account("idle", { label: "Idle" }),
      account("lost", { label: "Lost", key_state: "missing", used_for: ["routine"] }),
      account("busy", { label: "Busy", used_for: ["routine"] }),
      account("spare", { label: "Spare", backup_for: ["routine"], check_failed_for: ["routine"] }),
      account("stand", { label: "Stand", backup_for: ["deep"] }),
    ],
  });
  open();
  await row("Busy");
  const names = Array.from(document.querySelectorAll("li[data-row] span[id$=title]")).map((n) => n.textContent);
  expect(names).toEqual(["Busy", "Lost", "Stand", "Spare", "Idle"]);
});

test("the one next step follows the state: add its key, test, see why, nothing while paused, and Test for a ready account", async () => {
  api({
    "GET ai/accounts": () => [
      account("main", { label: "Main", used_for: ["routine", "deep"], answered_at: hoursAgo(1) }),
      account("keyless", { label: "Keyless", key_state: "missing" }),
      account("fresh", { label: "Fresh" }),
      account("broke", { label: "Broke", backup_for: ["deep"], check_failed_for: ["deep"] }),
      account("paused", { label: "Paused", backup_for: ["routine"], paused_until: "2026-10-16T14:20:00+00:00" }),
    ],
  });
  open();
  const buttons = async (name: string) => within(await row(name)).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
  expect(await buttons("Keyless")).toEqual(["Add the access key for Keyless", "More actions for Keyless"]);
  expect(await buttons("Fresh")).toEqual(["Test Fresh", "More actions for Fresh"]);
  expect(await buttons("Broke")).toEqual(["See why Broke's check failed", "More actions for Broke"]);
  expect(await buttons("Paused")).toEqual(["More actions for Paused"]);
  expect(await buttons("Main")).toEqual(["Test Main", "More actions for Main"]);
  expect(await row("Fresh")).toHaveTextContent("Not tested yet");
  expect(await row("Broke")).toHaveTextContent("Check failed for harder work");
  expect(await row("Paused")).toHaveTextContent(/Paused until .*2:20.* \(usage limit\)/);
  // Only a ready account's Test is quiet; the others' step is the primary action.
  expect(within(await row("Fresh")).getByRole("button", { name: "Test Fresh" })).toHaveClass(/primary/);
  expect(within(await row("Main")).getByRole("button", { name: "Test Main" })).not.toHaveClass(/primary/);
});

test("a key that ends soon says so in the state line; a far end date is a quiet part of the line above", async () => {
  api({
    "GET ai/accounts": () => [
      account("soon", { label: "Soon", key_ending: true, credential_expires: "2026-11-30" }),
      account("far", { label: "Far", credential_expires: "2027-01-31", answered_at: hoursAgo(1) }),
    ],
  });
  open();
  expect(await row("Soon")).toHaveTextContent("Access key stops working on Nov 30");
  expect(await row("Far")).toHaveTextContent("Ready · answered 1 hour ago");
  expect(await row("Far")).toHaveTextContent("access key ends Jan 31");
});

test("the menu holds the rest: test, make main, use as backup or stop, models, key, end date, rename, remove", async () => {
  const user = userEvent.setup();
  api();
  open();
  const items = async (name: string) => {
    await user.click(within(await row(name)).getByRole("button", { name: `More actions for ${name}` }));
    const found = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    await user.keyboard("{Escape}");
    return found;
  };
  expect(await items("Main account")).toEqual(["Test", "Change AI models", "Replace access key", "Set the access key's expiry date", "Rename", "Remove"]);
  expect(await items("Second account")).toEqual(["Test", "Make this the main account", "Stop using as backup", "Change AI models", "Replace access key", "Set the access key's expiry date", "Rename", "Remove"]);
  // Its key is missing, so it can't be made the main account or a backup until one is added.
  expect(await items("Trial account")).toEqual(["Test", "Change AI models", "Replace access key", "Set the access key's expiry date", "Rename", "Remove"]);
});

test("Make this the main account shows its check and cost under it, switches, and keeps the one it replaces as the backup when that passes its check", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [
      account("main", { label: "Main account", used_for: ["routine", "deep"], answered_at: hoursAgo(1) }),
      account("trial", { label: "Trial account", answered_at: hoursAgo(5) }),
    ],
    "POST ai/accounts/trial/switch-estimate": () => ({ offered: true, usd: 0.8, cases: 4, runs: 3 }),
    "POST ai/accounts/trial/switch-check": () => ({ saved: SAVED, checking: true }),
    "POST ai/accounts/main/test?tier=routine&model=everyday": answered("main"),
    "POST ai/accounts/main/test?tier=deep&model=everyday": answered("main"),
    "POST ai/accounts/main": () => SAVED,
  });
  open();
  await user.click(within(await row("Trial account")).getByRole("button", { name: "More actions for Trial account" }));
  const make = await screen.findByRole("menuitem", { name: /Make this the main account/ });
  expect(make).toHaveTextContent("Switch and check (about $0.80)");
  await user.click(make);
  // $0.80 is more than the $0.10 the person asked to be asked about, so it waits for their go.
  expect(await within(await row("Trial account")).findByRole("alert")).toHaveTextContent("This would cost about $0.80, more than the $0.10 you set for asking first.");
  expect(calls.some((c) => c.route === "POST ai/accounts/trial/switch-check")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Go ahead" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/trial/switch-check")?.body).toEqual({ fingerprint: "fp-1", use: { routine: "everyday", deep: "everyday" } }),
  );
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/main")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "everyday" } }),
  );
  expect(await screen.findByText("Helper now works with Trial account. Main account stands in if it can't answer.")).toBeInTheDocument();
});

test("when the account it replaces fails its check it is not made a backup, and the switch still happens", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("trial", { label: "Trial account" })],
    "POST ai/accounts/trial/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/main/test?tier=routine&model=everyday": () => [{ tier: "account", account: "main", main: true, ok: false, detail: "refused" }],
    "POST ai/accounts/trial": () => SAVED,
  });
  open();
  await menu(user, "Trial account", "Make this the main account");
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial")?.body).toEqual({ fingerprint: "fp-1", use: { routine: "everyday", deep: "everyday" } }));
  expect(await screen.findByText("Helper now uses Trial account. Main account failed its test and isn't a backup.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/main")).toBe(false);
});

test("Remove acts at once, reads back with Undo, and Undo posts the change back to the settings", async () => {
  const user = userEvent.setup();
  const before = { adapter: "adapter-one", models: { everyday: "model-a" } };
  const calls = api({
    "POST ai/accounts/trial/remove": () => ({
      changes: [{ key: "ai.providers.trial", before, after: null, was_default: false, is_default: true }],
      fingerprint: "fp-2",
      needs_restart: false,
    }),
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
  });
  open();
  await menu(user, "Trial account", "Remove");
  expect(screen.queryByRole("dialog")).toBeNull();
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial/remove")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("Removed Trial account.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { "ai.providers.trial": before }, reset: [], fingerprint: "fp-2" }));
});

test("removing the main account when a backup exists hands the work to it and says so in the toast", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/main/remove": () => ({ ...SAVED, changes: [{ key: "ai.providers.main", before: {}, after: null, was_default: false, is_default: true }] }) });
  open();
  await user.click(within(await row("Main account")).getByRole("button", { name: "More actions for Main account" }));
  // With a backup the menu says nothing more than Remove.
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/main/remove")?.body).toEqual({ fingerprint: "fp-1", take_over: "second" }));
  expect(await screen.findByText("Removed Main account. Second account now does Helper's work.")).toBeInTheDocument();
});

test("removing the main account with no backup says so in the menu before the click and in the toast after", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] })],
    "POST ai/accounts/main/remove": () => ({ ...SAVED, changes: [{ key: "ai.providers.main", before: {}, after: null, was_default: false, is_default: true }] }),
  });
  open();
  await user.click(within(await row("Main account")).getByRole("button", { name: "More actions for Main account" }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove · Helper will have no account for its work" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/main/remove")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("Removed Main account. Helper has no account for its work.")).toBeInTheDocument();
});

test("a change that needs a restart asks first and never restarts by itself", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/trial/remove": () => ({ ...SAVED, needs_restart: true }) });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <AiAccounts local />
    </RestartProvider>,
  );
  await menu(user, "Trial account", "Remove");
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("Restart to finish this change?"));
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("a refused removal shows the server's words in the row", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts/trial/remove": () => new Refuse(404, "There is no account called trial.") });
  open();
  await menu(user, "Trial account", "Remove");
  expect(await within(await row("Trial account")).findByRole("alert")).toHaveTextContent("There is no account called trial.");
});

test("Test calls the account's own test and shows its one result line", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/main/test": answered("main") });
  open();
  await user.click(within(await row("Main account")).getByRole("button", { name: "Test Main account" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/main/test")).toBe(true));
  expect(calls.some((c) => c.route === "POST ai/test")).toBe(false);
  expect(await within(await row("Main account")).findByText("Answered")).toBeInTheDocument();
  expect(await row("Main account")).toHaveTextContent("Answered ✓");
});

test("See why runs the check again and shows what went wrong", async () => {
  const user = userEvent.setup();
  api({
    "GET ai/accounts": () => [account("broke", { label: "Broke", backup_for: ["deep"], check_failed_for: ["deep"] })],
    "POST ai/accounts/broke/test": () => [{ tier: "account", account: "broke", main: false, ok: false, detail: "The key was refused." }],
  });
  open();
  await user.click(within(await row("Broke")).getByRole("button", { name: "See why Broke's check failed" }));
  expect(await within(await row("Broke")).findByText(/Didn't answer: The key was refused\./)).toBeInTheDocument();
  expect(await row("Broke")).toHaveTextContent("✗");
});

test("Add its key opens the key form with the cursor in it, and the new key is sent once and not kept on screen", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/trial": () => SAVED });
  open();
  await user.click(within(await row("Trial account")).getByRole("button", { name: "Add the access key for Trial account" }));
  const field = await screen.findByLabelText("New access key");
  expect(field).toHaveAttribute("type", "password");
  await waitFor(() => expect(field).toHaveFocus());
  const save = screen.getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  await user.type(field, "fresh-secret");
  await user.click(save);
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial")?.body).toEqual({ fingerprint: "fp-1", key: "fresh-secret" }));
  expect(await screen.findByText("Replaced the access key for Trial account.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByLabelText("New access key")).toBeNull());
});

test("on a hosted app Replace key asks where the key is and sends a reference", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/trial": () => SAVED });
  open(false);
  await menu(user, "Trial account", "Replace access key");
  await user.type(await screen.findByLabelText("Where the access key is kept"), "env:MODEL_KEY");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial")?.body).toEqual({ fingerprint: "fp-1", key_ref: "env:MODEL_KEY" }));
});

test("Set the access key's expiry date sends the day, and clearing it sends the clearing", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("spare", { label: "Spare" }), account("dated", { label: "Dated", credential_expires: "2027-01-31" })],
    "POST ai/accounts/spare": () => SAVED,
    "POST ai/accounts/dated": () => SAVED,
  });
  open();
  await menu(user, "Spare", "Set the access key's expiry date");
  const field = await screen.findByLabelText(/Expiry date, if known/);
  expect(field).toHaveAttribute("type", "date");
  await user.type(field, "2027-02-15");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", credential_expires: "2027-02-15" }));
  await menu(user, "Dated", "Set the access key's expiry date");
  await user.clear(await screen.findByLabelText(/Expiry date, if known/));
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/dated")?.body).toEqual({ fingerprint: "fp-1", clear_credential_expires: true }));
});

test("replacing the key takes the date typed with it, and drops the old key's date when none is typed", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("spare", { label: "Spare" }), account("dated", { label: "Dated", credential_expires: "2027-01-31" })],
    "POST ai/accounts/spare": () => SAVED,
    "POST ai/accounts/dated": () => SAVED,
  });
  open();
  await menu(user, "Spare", "Replace access key");
  await user.type(await screen.findByLabelText("New access key"), "fresh");
  await user.type(screen.getByLabelText(/Expiry date, if known/), "2027-03-01");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/spare")?.body).toEqual({ fingerprint: "fp-1", key: "fresh", credential_expires: "2027-03-01" }));
  await menu(user, "Dated", "Replace access key");
  await user.type(await screen.findByLabelText("New access key"), "newer");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/dated")?.body).toEqual({ fingerprint: "fp-1", key: "newer", clear_credential_expires: true }));
});

test("Rename changes the name the person sees and nothing else", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/trial": () => SAVED });
  open();
  await menu(user, "Trial account", "Rename");
  const field = await screen.findByLabelText("Name");
  expect(field).toHaveValue("Trial account");
  await user.clear(field);
  await user.type(field, "Spare key");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial")?.body).toEqual({ fingerprint: "fp-1", label: "Spare key" }));
  expect(await screen.findByText("Renamed to Spare key.")).toBeInTheDocument();
});

test("Change AI models edits the ids it has, can add one for harder work, and Cancel changes nothing", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/trial": () => SAVED });
  open();
  await menu(user, "Trial account", "Change AI models");
  const everyday = await screen.findByLabelText("AI model for everyday work");
  expect(everyday).toHaveValue("model-a");
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("AI model for everyday work")).toBeNull();
  expect(calls.some((c) => c.route === "POST ai/accounts/trial")).toBe(false);
  await menu(user, "Trial account", "Change AI models");
  const again = await screen.findByLabelText("AI model for everyday work");
  await user.clear(again);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  await user.type(again, "model-z");
  await user.type(screen.getByLabelText("AI model for harder work (optional)"), "model-y");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/trial")?.body).toEqual({ fingerprint: "fp-1", models: { everyday: "model-z", harder: "model-y" } }));
  expect(await screen.findByText("Changed the models for Trial account.")).toBeInTheDocument();
});

test("Change AI models saves with the fingerprint it opened with: a change made since is refused, the typed ids stay, and saving again is the person's own choice", async () => {
  const user = userEvent.setup();
  let fingerprint = "fp-1";
  const calls = api({
    "GET settings": () => ({ fingerprint, items: [LIMIT] }),
    "POST ai/accounts/trial": (sent) => ((sent as { fingerprint: string }).fingerprint === fingerprint ? SAVED : new Refuse(409, "The settings changed since you opened them. Look again, then save.")),
  });
  open();
  await screen.findByText("Trial account");
  await waitFor(() => expect(calls.some((c) => c.route === "GET settings")).toBe(true));
  const before = calls.filter((c) => c.route === "GET settings").length;
  await menu(user, "Trial account", "Change AI models");
  const everyday = await screen.findByLabelText("AI model for everyday work");
  // Something else changed the settings after the form opened and read them.
  await waitFor(() => expect(calls.filter((c) => c.route === "GET settings").length).toBeGreaterThan(before));
  fingerprint = "fp-2";
  await user.clear(everyday);
  await user.type(everyday, "model-z");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("This was changed since you opened it. What you typed is still here; check it against what is saved now, then save again.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST ai/accounts/trial").map((c) => (c.body as { fingerprint: string }).fingerprint)).toEqual(["fp-1"]);
  expect(screen.getByLabelText("AI model for everyday work")).toHaveValue("model-z");
  await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Changed the models for Trial account.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST ai/accounts/trial").map((c) => (c.body as { fingerprint: string }).fingerprint)).toEqual(["fp-1", "fp-2"]);
});

test("a backup that gains a harder model offers to move its harder work there, checked first, in one click", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("stand", { label: "Stand", backup_for: ["routine", "deep"] })],
    "POST ai/accounts/stand": () => SAVED,
    "POST ai/accounts/stand/test?tier=deep&model=harder": answered("stand"),
  });
  open();
  await menu(user, "Stand", "Change AI models");
  expect(screen.queryByRole("checkbox")).toBeNull();
  await user.type(await screen.findByLabelText("AI model for harder work (optional)"), "model-y");
  const move = await screen.findByRole("checkbox", { name: /harder-work model for backup too/ });
  expect(move).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/stand/test?tier=deep&model=harder")).toBe(true));
  const posts = calls.filter((c) => c.route === "POST ai/accounts/stand").map((c) => c.body);
  expect(posts).toEqual([
    { fingerprint: "fp-1", models: { everyday: "model-a", harder: "model-y" } },
    { fingerprint: "fp-1", backup: { deep: "harder" } },
  ]);
  expect(await screen.findByText("Stand now stands in for harder work with its harder model.")).toBeInTheDocument();
});

test("when the harder model fails its check the models are still saved and harder work stays where it was", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("stand", { label: "Stand", backup_for: ["deep"] })],
    "POST ai/accounts/stand": () => SAVED,
    "POST ai/accounts/stand/test?tier=deep&model=harder": () => [{ tier: "account", account: "stand", main: false, ok: false, detail: "no such model" }],
  });
  open();
  await menu(user, "Stand", "Change AI models");
  await user.type(await screen.findByLabelText("AI model for harder work (optional)"), "model-y");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText(/The harder-work model failed its test.*no such model/)).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST ai/accounts/stand").length).toBe(1);
});

test("a refused change shows the server's words and keeps the form open", async () => {
  const user = userEvent.setup();
  api({ "POST ai/accounts/trial": () => new Refuse(400, "Name at least one model the account uses.") });
  open();
  await menu(user, "Trial account", "Change AI models");
  await user.type(await screen.findByLabelText("AI model for harder work (optional)"), "model-y");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Name at least one model the account uses.");
  expect(screen.getByLabelText("AI model for harder work (optional)")).toHaveValue("model-y");
});

const OFFER = { offered: true, usd: 0.8, cases: 40, runs: 3 };

test("changing the model of an account that does the work is a switch: the cost is on the primary button", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/accounts/main/switch-estimate": () => OFFER,
    "POST ai/accounts/main/switch-check": () => ({ saved: SAVED, checking: true }),
  });
  open();
  await menu(user, "Main account", "Change AI models");
  const field = await screen.findByLabelText("AI model for everyday work");
  await user.clear(field);
  await user.type(field, "model-z");
  const go = await screen.findByRole("button", { name: "Switch and check (about $0.80)" });
  expect(screen.getByRole("button", { name: "Switch without checking" })).toBeInTheDocument();
  await user.click(go);
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/main/switch-check")?.body).toEqual({ fingerprint: "fp-1", models: { everyday: "model-z" } }));
  expect(await screen.findByText("Checking Main account. Today will show anything that needs attention.")).toBeInTheDocument();
});

test("Use as backup checks the account for each kind of work first, with its cost under it, then adds it with Undo", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("second", { label: "Second", models: { everyday: "model-b", harder: "model-c" }, check_usd: 0.02 })],
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
  await user.click(within(await row("Second")).getByRole("button", { name: "More actions for Second" }));
  expect(await screen.findByRole("menuitem", { name: /Use as backup/ })).toHaveTextContent("Checked first (about $0.02)");
  await user.click(screen.getByRole("menuitem", { name: /Use as backup/ }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/second")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "harder" } }));
  const tests = calls.filter((c) => c.route.startsWith("POST ai/accounts/second/test")).map((c) => c.route);
  expect(tests).toEqual(["POST ai/accounts/second/test?tier=routine&model=everyday", "POST ai/accounts/second/test?tier=deep&model=harder"]);
  expect(await screen.findByText("Second now stands in when the main account can't answer")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("a failed check adds nothing and shows why", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("second", { label: "Second" })],
    "POST ai/accounts/second/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/second/test?tier=routine&model=everyday": () => [{ tier: "account", account: "second", main: false, ok: false, detail: "The key was refused." }],
  });
  open();
  await menu(user, "Second", "Use as backup");
  expect(await within(await row("Second")).findByText(/Didn't answer: The key was refused\./)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST ai/accounts/second")).toBe(false);
});

test("Stop using as backup takes the account out of every backup with Undo", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST ai/accounts/second": () => ({ ...SAVED, changes: [{ key: "ai.tiers.routine.fallback", before: ["second/default"], after: [], was_default: false, is_default: true }] }) });
  open();
  await menu(user, "Second account", "Stop using as backup");
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/second")?.body).toEqual({ fingerprint: "fp-1", stop_backup: true }));
  expect(await screen.findByText("Second account no longer stands in for any work.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("with no account doing the work there is no backup to be, and the summary says so", async () => {
  const user = userEvent.setup();
  api({ "GET ai/accounts": () => [account("third", { label: "Third" })] });
  open();
  expect(await screen.findByRole("group", { name: "Who does the work" })).toHaveTextContent("No account does Helper's work yet.");
  await user.click(within(await row("Third")).getByRole("button", { name: "More actions for Third" }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).not.toContain("Use as backup");
});

test("Add an account and Compare what they can do show only where the screen gives a way", async () => {
  const user = userEvent.setup();
  api();
  const onAdd = vi.fn();
  const onCompare = vi.fn();
  const view = renderApp(<AiAccounts local onAdd={onAdd} onCompare={onCompare} />);
  await user.click(await screen.findByRole("button", { name: "Add an account" }));
  await user.click(screen.getByRole("button", { name: "Compare what they can do" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
  expect(onCompare).toHaveBeenCalledTimes(1);
  view.unmount();
  open();
  await screen.findByRole("heading", { name: /AI accounts/ });
  expect(screen.queryByRole("button", { name: "Add an account" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Compare what they can do" })).toBeNull();
});

test("no accounts says so, and a list that didn't load says so quietly", async () => {
  api({ "GET ai/accounts": () => [] });
  const view = open();
  expect(await screen.findByText("No AI account is set up yet.")).toBeInTheDocument();
  view.unmount();
  api({ "GET ai/accounts": () => new Refuse(500, "") });
  open();
  expect(await screen.findByText("The list of AI accounts didn't load.")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /AI accounts/ })).toBeNull();
});

const skill = (id: string, label: string, over: Partial<S["AiSkillView"]> = {}): S["AiSkillView"] => ({
  id,
  label,
  description: "",
  measured: false,
  runs: 0,
  passes: 0,
  pass_rate: null,
  age_days: null,
  cost_per_pass_usd: null,
  stale: null,
  below_min: false,
  ...over,
});

const SKILLS: S["AiSkillsView"] = {
  min_score: 0.8,
  stale_days: 60,
  accounts: [
    {
      name: "main",
      models: [
        {
          model: "everyday",
          skills: [
            skill("dates", "Dates", { measured: true, runs: 10, passes: 9, pass_rate: 0.9, age_days: 3, cost_per_pass_usd: 0.04 }),
            skill("use-term", "Using a term", { measured: true, runs: 4, passes: 1, pass_rate: 0.25, age_days: 0, below_min: true }),
            skill("owners", "Owners", { measured: true, runs: 5, passes: 5, pass_rate: 1, age_days: 90, stale: "age" }),
            skill("evidence", "Quoting its evidence"),
          ],
        },
        { model: "harder", skills: [skill("dates", "Dates", { measured: true, runs: 2, passes: 2, pass_rate: 1, age_days: 1 })] },
      ],
    },
  ],
};

test("each row ends with one line of what it can do and See all opens the grid", async () => {
  const user = userEvent.setup();
  api({ "GET ai/skills": () => SKILLS });
  const onCompare = vi.fn();
  renderApp(<AiAccounts local onCompare={onCompare} />);
  const main = await row("Main account");
  // Dates passes (on either model), Using a term is below the minimum, Owners is old and Quoting has no measurement.
  await waitFor(() => expect(main).toHaveTextContent("Good at 1 of 4 kinds of work · 1 below the minimum · 2 not measured · See all"));
  // The model's own id is never shown.
  expect(main).not.toHaveTextContent("model-a");
  expect(main).not.toHaveTextContent("What it can do");
  await user.click(within(main).getByRole("button", { name: "See everything Main account can do" }));
  expect(onCompare).toHaveBeenCalledTimes(1);
});

test("an account the measurements don't know, and a list that didn't load, show no line of what it can do", async () => {
  api({ "GET ai/skills": () => ({ ...SKILLS, accounts: [] }) });
  const view = open();
  expect(await row("Main account")).not.toHaveTextContent("kinds of work");
  view.unmount();
  api({ "GET ai/skills": () => new Refuse(500, "") });
  open();
  expect(await row("Main account")).not.toHaveTextContent("kinds of work");
});

test("a check that would cost more than the amount the person set asks first, with its cost, and runs only after the go", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET ai/accounts": () => [account("main", { label: "Main account", used_for: ["routine", "deep"] }), account("second", { label: "Second", check_usd: 0.5 })],
    "POST ai/accounts/second/switch-estimate": () => ({ offered: false }),
    "POST ai/accounts/second/test?tier=routine&model=everyday": answered("second"),
    "POST ai/accounts/second/test?tier=deep&model=everyday": answered("second"),
    "POST ai/accounts/second": () => SAVED,
  });
  open();
  await menu(user, "Second", "Use as backup");
  const asked = await within(await row("Second")).findByRole("alert");
  expect(asked).toHaveTextContent("This would cost about $0.50, more than the $0.10 you set for asking first.");
  expect(calls.some((c) => c.route.startsWith("POST ai/accounts/second/test"))).toBe(false);
  await user.click(within(asked).getByRole("button", { name: "Cancel" }));
  expect(calls.some((c) => c.route.startsWith("POST ai/accounts/second/test"))).toBe(false);
  await menu(user, "Second", "Use as backup");
  await user.click(await screen.findByRole("button", { name: "Go ahead" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/second")?.body).toEqual({ fingerprint: "fp-1", backup: { routine: "everyday", deep: "everyday" } }));
});
