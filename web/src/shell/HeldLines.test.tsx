import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { addDays, localDate } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { HeldLines } from "./HeldLines";

function line(kind: S["QueueLineView"]["kind"], over: Partial<S["QueueLineView"]> = {}): S["QueueLineView"] {
  return { key: kind, group: kind === "restart" ? "decide" : "risk", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const paused = (over: Partial<S["QueueLineView"]> = {}) =>
  line("paused", { key: "paused:main", account: "main", until: `${localDate(new Date())}T15:30:00-05:00`, ...over });

function show(lines: S["QueueLineView"][], routes: Record<string, (body: unknown) => unknown> = {}, canRestart = true) {
  const calls = fakeApi({
    "GET today/queue": () => lines,
    "GET status": () => statusFixture({ can_restart: canRestart }),
    "GET runtime-config": () => ({ instance: null }),
    ...routes,
  });
  const onOpenAiAccounts = vi.fn();
  const onOpenHandover = vi.fn();
  const onOpenRules = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <HeldLines onOpenAiAccounts={onOpenAiAccounts} onOpenHandover={onOpenHandover} onOpenRules={onOpenRules} />
    </RestartProvider>,
  );
  return { calls, onOpenAiAccounts, onOpenHandover, onOpenRules };
}

test("nothing is drawn while the queue has neither a restart nor a paused line", async () => {
  const { calls } = show([line("failed", { group: "risk" }), line("overdue", { group: "risk" })]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET today/queue")).toBe(true));
  expect(screen.queryByRole("region", { name: "Restart needed" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Paused account" })).toBeNull();
  expect(document.querySelector("[data-held-lines]")).toBeNull();
});

test("held work is a line that starts with the restart and counts the waiting requests", async () => {
  show([line("restart", { count: 3 })]);
  const row = await screen.findByRole("region", { name: "Restart needed" });
  expect(row).toHaveTextContent("Restart to run 3 waiting requests");
  expect(row).toHaveTextContent("Nothing runs until you restart it.");
});

test("one waiting request is said in the singular", async () => {
  show([line("restart", { count: 1 })]);
  expect(await screen.findByRole("region", { name: "Restart needed" })).toHaveTextContent("Restart to run 1 waiting request");
});

test("Restart now calls the restart route, and only the click does", async () => {
  const user = userEvent.setup();
  const { calls } = show([line("restart", { count: 2 })], { "POST restart": () => ({ restarting: true }) });
  const row = await screen.findByRole("region", { name: "Restart needed" });
  await waitFor(() => expect(calls.some((c) => c.route === "GET status")).toBe(true));
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(await within(row).findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST restart")).toHaveLength(1));
  // The restart flow takes over: the line says it is restarting and the button waits.
  await waitFor(() => expect(row).toHaveTextContent("Restarting to use the new settings"));
  expect(within(row).getByRole("button", { name: "Restart now" })).toBeDisabled();
});

test("when the app can't restart itself the line says to close and start it, with no button", async () => {
  show([line("restart", { count: 2 })], {}, false);
  const row = await screen.findByRole("region", { name: "Restart needed" });
  await waitFor(() => expect(row).toHaveTextContent("Close it and start it again"));
  expect(within(row).queryByRole("button")).toBeNull();
});

test("a paused account is a line that names the account, the reset time and the count, and opens the AI accounts", async () => {
  const user = userEvent.setup();
  const { onOpenAiAccounts } = show([paused({ count: 2 })]);
  const row = await screen.findByRole("region", { name: "Paused account" });
  expect(row).toHaveTextContent(/Pick another account, or wait: main's limit resets at 3:30\s?PM \(2 requests waiting\)/);
  expect(row).toHaveTextContent("They run again by themselves at the reset.");
  expect(row.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  await user.click(within(row).getByRole("button", { name: "AI accounts" }));
  expect(onOpenAiAccounts).toHaveBeenCalledTimes(1);
});

test("a reset on another day names the day with the time, and one waiting request is singular", async () => {
  show([paused({ count: 1, until: `${addDays(localDate(new Date()), 1)}T08:05:00-05:00` })]);
  const row = await screen.findByRole("region", { name: "Paused account" });
  expect(row).toHaveTextContent(/limit resets at \w{3}, \w{3} \d{1,2}, 8:05\s?AM \(1 request waiting\)/);
});

test("each paused account has its own line, and both kinds can show together", async () => {
  show([line("restart", { count: 1 }), paused({ account: "main" }), paused({ key: "paused:second", account: "second" })]);
  expect(await screen.findByRole("region", { name: "Restart needed" })).toBeInTheDocument();
  const rows = await screen.findAllByRole("region", { name: "Paused account" });
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("main's limit");
  expect(rows[1]).toHaveTextContent("second's limit");
});

test("work waiting for the network is one line that starts with checking the connection, with the count and since when", async () => {
  show([line("offline", { key: "offline", waiting_since: `${localDate(new Date())}T14:05:00-05:00`, count: 3 })]);
  const row = await screen.findByRole("region", { name: "No network" });
  expect(row).toHaveTextContent(/^No networkCheck the network connection: 3 requests have been waiting for it since 2:05\s?PM/);
  expect(row).toHaveTextContent("They run again by themselves as soon as the network is back.");
  expect(row.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  expect(within(row).queryByRole("button")).toBeNull();
});

test("one request waiting for the network is singular, and the line is gone once the queue no longer has it", async () => {
  show([line("offline", { key: "offline", waiting_since: `${addDays(localDate(new Date()), -1)}T08:05:00-05:00` })]);
  const row = await screen.findByRole("region", { name: "No network" });
  expect(row).toHaveTextContent(/1 request has been waiting for it since \w{3}, \w{3} \d{1,2}, 8:05\s?AM/);
});

test("nothing is drawn for the network when the queue has no such line", async () => {
  const { calls } = show([line("overdue", { group: "risk" })]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET today/queue")).toBe(true));
  expect(screen.queryByRole("region", { name: "No network" })).toBeNull();
});

const handover = (state: "diverged" | "chosen" | "elsewhere", text: string | null = "Other laptop") =>
  line("handover", { key: "handover", group: "decide", state, text });

test("copies that disagree are a line that starts with the choice and opens the page that settles it", async () => {
  const user = userEvent.setup();
  const { onOpenHandover } = show([handover("diverged")]);
  const row = await screen.findByRole("region", { name: "Two copies" });
  expect(row).toHaveTextContent("Choose which copy to keep: this computer and the synced folder each changed on their own");
  expect(row).toHaveTextContent("Nothing is written to the folder until you choose.");
  expect(within(row).queryByRole("button", { name: "Restart now" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "Choose a copy" }));
  expect(onOpenHandover).toHaveBeenCalledTimes(1);
});

test("once a copy is chosen the line asks for the restart, which only the click starts", async () => {
  const user = userEvent.setup();
  const { calls, onOpenHandover } = show([handover("chosen")], { "POST restart": () => ({ restarting: true }) });
  const row = await screen.findByRole("region", { name: "Two copies" });
  expect(row).toHaveTextContent("Restart to keep the copy you chose");
  await waitFor(() => expect(calls.some((c) => c.route === "GET status")).toBe(true));
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(await within(row).findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST restart")).toHaveLength(1));
  await user.click(within(row).getByRole("button", { name: "Review your choice" }));
  expect(onOpenHandover).toHaveBeenCalledTimes(1);
});

test("a copy that lost the workspace to another computer names it and offers the details, not a restart", async () => {
  show([handover("elsewhere")]);
  const row = await screen.findByRole("region", { name: "Two copies" });
  expect(row).toHaveTextContent("Close this copy: Other laptop opened the workspace, so this copy stopped saving to the synced folder");
  expect(within(row).getByRole("button", { name: "See details" })).toBeInTheDocument();
  expect(within(row).queryByRole("button", { name: "Restart now" })).toBeNull();
});

test("an unknown other computer is said without a name", async () => {
  show([handover("elsewhere", null)]);
  expect(await screen.findByRole("region", { name: "Two copies" })).toHaveTextContent("Close this copy: another computer opened the workspace");
});

const backup = (over: Partial<S["QueueLineView"]> = {}) =>
  line("account_check", { key: "account_check:routine:second/default", account: "second", tier: "routine", model: "default", check_failed: false, ...over });

test("a backup account that was never checked is a line that starts with checking it, for the work it would stand in for", async () => {
  show([backup()]);
  const row = await screen.findByRole("region", { name: "Check an account" });
  expect(row).toHaveTextContent("Check second before it stands in for everyday work");
  expect(row).toHaveTextContent("hasn't passed the connection check for it yet");
  expect(row.textContent).not.toMatch(/routine|tier|fallback/i);
});

test("a failed check says so, and another kind of work is named in plain words", async () => {
  show([backup({ check_failed: true, tier: "deep" }), backup({ key: "other", tier: "something-new", account: "third" })]);
  const rows = await screen.findAllByRole("region", { name: "Check an account" });
  expect(rows[0]).toHaveTextContent("Check second before it stands in for harder work");
  expect(rows[0]).toHaveTextContent("Its last check didn't pass.");
  expect(rows[1]).toHaveTextContent("Check third before it stands in for this kind of work");
});

test("Check now runs the account's test for that work, and the line is gone once the queue no longer has it", async () => {
  const user = userEvent.setup();
  let checked = false;
  const lines = () => (checked ? [] : [backup()]);
  const { calls } = show([], {
    "GET today/queue": () => lines(),
    "POST ai/accounts/second/test?tier=routine&model=default": () => {
      checked = true;
      return [{ tier: "account", account: "second", main: true, ok: true, detail: "answered" }];
    },
  });
  const row = await screen.findByRole("region", { name: "Check an account" });
  await user.click(within(row).getByRole("button", { name: "Check second for everyday work" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/second/test?tier=routine&model=default")).toBe(true));
  expect(await screen.findByText("second passed. It can stand in for everyday work.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Check an account" })).toBeNull());
});

test("a check that doesn't pass says why and leaves the line", async () => {
  const user = userEvent.setup();
  show([backup()], { "POST ai/accounts/second/test?tier=routine&model=default": () => [{ tier: "account", account: "second", main: true, ok: false, detail: "the key was refused" }] });
  const row = await screen.findByRole("region", { name: "Check an account" });
  await user.click(within(row).getByRole("button", { name: "Check second for everyday work" }));
  expect(await screen.findByText("second didn't pass: the key was refused")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Check an account" })).toBeInTheDocument();
});

test("rules to look over are a line that starts with the look and opens the review", async () => {
  const user = userEvent.setup();
  const { onOpenRules } = show([line("rule_review", { key: "rule_review", group: "review", count: 3, days: 30, rules: ["RULE-1"] })]);
  const row = await screen.findByRole("region", { name: "Rules to look over" });
  expect(row).toHaveTextContent("Look over 3 rules that never applied in the last 30 days");
  await user.click(within(row).getByRole("button", { name: "Look over" }));
  expect(onOpenRules).toHaveBeenCalledTimes(1);
});

test("one rule is singular, and rules only moved out of the always-sent part have their own words", async () => {
  show([line("rule_review", { key: "one", group: "review", count: 1, days: 14 }), line("rule_review", { key: "moved", group: "review", count: 0, moved: 2 })]);
  const rows = await screen.findAllByRole("region", { name: "Rules to look over" });
  expect(rows[0]).toHaveTextContent("Look over 1 rule that never applied in the last 14 days");
  expect(rows[1]).toHaveTextContent("Look over the rules: some moved out of the part sent every time");
});

test("the catch-up learning runs are one line with the count and the total, and Go starts them all", async () => {
  const user = userEvent.setup();
  let started = false;
  const { calls } = show([], {
    "GET today/queue": () => (started ? [] : [line("catch_up_go", { key: "catch_up_go", group: "decide", count: 3, estimate_usd: 0.42 })]),
    "POST knowledge/catch-up/go": () => {
      started = true;
      return { started: 3 };
    },
  });
  const row = await screen.findByRole("region", { name: "Go needed" });
  expect(row).toHaveTextContent("Learn from 3 kinds of earlier correction: About $0.42");
  expect(row).toHaveTextContent("Nothing is spent until you press Go.");
  await user.click(within(row).getByRole("button", { name: "Go" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST knowledge/catch-up/go")).toHaveLength(1));
  expect(await screen.findByText("Learning from your earlier corrections has started.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Go needed" })).toBeNull());
});

test("catch-up runs with no price say they use the plan's allowance", async () => {
  show([line("catch_up_go", { key: "catch_up_go", group: "decide", count: 1, estimate_usd: null, unpriced: 1 })]);
  expect(await screen.findByRole("region", { name: "Go needed" })).toHaveTextContent(
    "Learn from 1 kind of earlier correction. It uses your plan's allowance.",
  );
});

test("a kind of file that isn't being read is one line with its kind and why, and no button", async () => {
  show([line("extractor", { key: "extractor:pdf", file_kind: "pdf", text: "the PDF is locked with a password" })]);
  const row = await screen.findByRole("region", { name: "Reading files" });
  expect(row).toHaveTextContent("Reading PDFs isn't working: the PDF is locked with a password");
  expect(row).toHaveTextContent("This line goes once a file of this kind reads well.");
  expect(within(row).queryByRole("button")).toBeNull();
});

test("a kind of file an add-on named itself is shown as the add-on called it", async () => {
  show([line("extractor", { key: "extractor:Drawings", file_kind: "Drawings", text: "it stopped" })]);
  expect(await screen.findByRole("region", { name: "Reading files" })).toHaveTextContent("Reading Drawings isn't working: it stopped");
});
