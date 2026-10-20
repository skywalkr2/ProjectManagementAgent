import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { resetAccountChecks } from "../lib/account-checks";
import { fakeApi, renderApp } from "../test-utils";
import { AiAccounts } from "./AiAccounts";
import { WelcomeAi } from "./WelcomeAi";

// The owner's path (roadmap B-6b, found by the first real use): a second account is added as a backup and its checks take a
// while. The form closes as soon as the account is saved; the account's row shows the checks as they run and the outcome,
// and one toast says when they finish. The form never sits on "Adding…".

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
  accepted_unchecked: false,
  ...extra,
});

const MAIN = view("main", "Main account", { used_for: ["routine", "deep"] });
const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false };
const NEW = "service-a-account";
const answer = (ok: boolean, detail = "answered") => [{ tier: "account", account: NEW, main: false, ok, detail }];

/** A reply the test lets go of when it chooses, standing for a check that takes a while. */
function gate() {
  let release: () => void = () => undefined;
  const wait = new Promise<void>((resolve) => (release = resolve));
  return { wait, release };
}

function server(extra: Record<string, (body: unknown) => unknown> = {}) {
  let accounts = [MAIN];
  const calls = fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET ai/accounts": () => accounts,
    "GET ai/local": () => [],
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    "GET ai/skills": () => ({ min_score: 0.8, stale_days: 60, accounts: [] }),
    "GET ai/check-size": () => ({ calls: 10, input_tokens: 1000, output_tokens: 200 }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [{ key: "ai.budgets.confirm_above_usd", value: 0.1 }] }),
    "POST ai/models": () => ({ models: [{ id: "model-a", input_per_million: 3, output_per_million: 15 }] }),
    "POST ai/accounts": () => {
      accounts = [...accounts, view(NEW, "Service A account")];
      return SAVED;
    },
    "POST settings": () => SAVED,
    ...extra,
  });
  return {
    calls,
    /** What the account list holds after the account stood in. */
    standsIn: () => {
      accounts = accounts.map((a) => (a.name === NEW ? { ...a, backup_for: ["routine", "deep"], checked_for: ["routine", "deep"] } : a));
    },
  };
}

/** The add form beside the list of accounts, as Settings has them: the form is gone once it says the account is added. */
function Page() {
  const [adding, setAdding] = useState(true);
  return (
    <>
      <AiAccounts local level={3} />
      {adding && <WelcomeAi local done drawer={{ onAdded: () => setAdding(false), onCancel: () => setAdding(false) }} />}
    </>
  );
}

async function fillAndAdd(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("radio", { name: /Service A/ }));
  await user.type(screen.getByLabelText("Access key"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByLabelText("AI model for everyday work");
  await user.click(screen.getByRole("button", { name: /Add and check/ }));
}

const rowOf = async (name: string) => (await screen.findByText(name, { selector: "li[data-row] span[id$='-title']" })).closest("li") as HTMLElement;

afterEach(() => resetAccountChecks());

test("the form closes once the account is saved, while its checks are still running, and never says Adding… for them", async () => {
  const user = userEvent.setup();
  const routine = gate();
  const { calls } = server({
    [`POST ai/accounts/${NEW}/test?tier=routine&model=everyday`]: async () => {
      await routine.wait;
      return answer(true);
    },
    [`POST ai/accounts/${NEW}/test?tier=deep&model=everyday`]: () => answer(true),
  });
  renderApp(<Page />);
  await fillAndAdd(user);
  // The first check has not answered, and the form is already gone.
  await waitFor(() => expect(screen.queryByRole("radio", { name: /Service A/ })).toBeNull());
  expect(calls.some((c) => c.route === "POST ai/accounts")).toBe(true);
  expect(screen.queryByText("Adding…")).toBeNull();
  expect(screen.queryByRole("button", { name: /Add and check|Add account/ })).toBeNull();
  // The account's row says what is being checked.
  const row = await rowOf("Service A account");
  expect(await within(row).findByText("Checking for everyday work…")).toBeInTheDocument();
  await act(async () => routine.release());
});

test("the row follows the checks, kind of work by kind of work, and one toast says when they are done", async () => {
  const user = userEvent.setup();
  const routine = gate();
  const deep = gate();
  const checked: string[] = [];
  const s = server({
    [`POST ai/accounts/${NEW}/test?tier=routine&model=everyday`]: async () => {
      await routine.wait;
      checked.push("routine");
      return answer(true);
    },
    [`POST ai/accounts/${NEW}/test?tier=deep&model=everyday`]: async () => {
      await deep.wait;
      checked.push("deep");
      return answer(true);
    },
    [`POST ai/accounts/${NEW}`]: () => {
      s.standsIn();
      return SAVED;
    },
  });
  renderApp(<Page />);
  await fillAndAdd(user);
  const row = await rowOf("Service A account");
  expect(await within(row).findByText("Checking for everyday work…")).toBeInTheDocument();
  await act(async () => routine.release());
  expect(await within(row).findByText("Checking for harder work…")).toBeInTheDocument();
  expect(within(row).queryByText("Checking for everyday work…")).toBeNull();
  await act(async () => deep.release());
  // One toast says it is done, and the row ends on who it backs up.
  expect(await screen.findByText("Service A account now stands in when the main account can't answer")).toBeInTheDocument();
  await waitFor(() => expect(within(row).queryByText(/Checking for/)).toBeNull());
  expect(await within(row).findByText("Backs up Main account")).toBeInTheDocument();
  expect(checked).toEqual(["routine", "deep"]);
  expect(screen.getAllByText(/stands in when the main account can't answer/)).toHaveLength(1);
});

test("a check that fails says what failed on the row, with one toast, and offers Use it anyway", async () => {
  const user = userEvent.setup();
  const s = server({
    [`POST ai/accounts/${NEW}/test?tier=routine&model=everyday`]: () => answer(false, "The key was refused."),
    "POST settings": () => SAVED,
    [`POST ai/accounts/${NEW}`]: () => {
      s.standsIn();
      return SAVED;
    },
  });
  renderApp(<Page />);
  await fillAndAdd(user);
  expect(await screen.findByText("Added Service A account, but its check didn't pass: The key was refused.")).toBeInTheDocument();
  const row = await rowOf("Service A account");
  expect(await within(row).findByText(/The key was refused\./)).toBeInTheDocument();
  expect(within(row).queryByText(/Checking for/)).toBeNull();
  // Where the choice exists, it is one button, in plain words about what it means.
  expect(within(row).getByText(/won't be told if it fails/)).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Use it anyway" }));
  await waitFor(() => expect(s.calls.find((c) => c.route === `POST ai/accounts/${NEW}`)?.body).toMatchObject({ backup: { routine: "everyday", deep: "everyday" } }));
  const accepted = s.calls.filter((c) => c.route === "POST settings").map((c) => c.body);
  expect(accepted).toContainEqual(expect.objectContaining({ changes: { [`ai.providers.${NEW}.accepted_unchecked`]: true } }));
  await waitFor(() => expect(within(row).queryByRole("button", { name: "Use it anyway" })).toBeNull());
});

test("Use it anyway is in the menu of an account whose check failed, and not for one already accepted or one that does the work", async () => {
  const user = userEvent.setup();
  const failed = { check_failed_for: ["routine"], checked_at: "2026-10-14T10:00:00Z" };
  const accounts = [
    view("main", "Main account", { used_for: ["routine", "deep"], ...failed }),
    view("broke", "Broke account", failed),
    view("taken", "Taken account", { ...failed, accepted_unchecked: true }),
  ];
  fakeApi({
    "GET ai/endpoints": () => KINDS,
    "GET ai/accounts": () => accounts,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET setup": () => ({ steps: [], finished: false, local: true }),
    "GET ai/skills": () => ({ min_score: 0.8, stale_days: 60, accounts: [] }),
  });
  renderApp(<AiAccounts local level={3} />);
  const entries = async (name: string) => {
    const row = await rowOf(name);
    await user.click(within(row).getByRole("button", { name: `More actions for ${name}` }));
    const found = screen.queryByRole("menuitem", { name: /Use it anyway/ });
    await user.keyboard("{Escape}");
    return found !== null;
  };
  expect(await entries("Broke account")).toBe(true);
  expect(await entries("Taken account")).toBe(false);
  expect(await entries("Main account")).toBe(false);
  // Nothing about it sits on the row itself until a check has just failed.
  expect(screen.queryByRole("button", { name: "Use it anyway" })).toBeNull();
});
