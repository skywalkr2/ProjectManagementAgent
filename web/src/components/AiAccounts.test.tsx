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
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Replace key", "Change models", "Remove"]);
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
  expect(lost.querySelector(".key-missing")).toHaveTextContent("! Key not found");
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
