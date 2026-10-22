import "@testing-library/jest-dom/vitest";
import { useQuery } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, type S } from "../lib/api";
import { addDays, localDate } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { HeldLine, isHeld } from "./HeldLines";

/** The held lines of the queue on their own, as the Today queue draws them among the others. */
function HeldLines(props: {
  onOpenAiAccounts: () => void;
  onOpenHandover: () => void;
  onOpenRules?: () => void;
  onOpenKnowledge?: () => void;
  onAddAccount?: () => void;
  onOpenSources?: () => void;
}) {
  const queue = useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
  const lines = (queue.data ?? []).filter(isHeld);
  if (!lines.length) return null;
  return (
    <div data-held-lines="">
      {lines.map((line) => (
        <HeldLine key={line.key} line={line} {...props} />
      ))}
    </div>
  );
}

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
  const onOpenKnowledge = vi.fn();
  const onAddAccount = vi.fn();
  const onOpenSources = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <HeldLines onOpenAiAccounts={onOpenAiAccounts} onOpenHandover={onOpenHandover} onOpenRules={onOpenRules} onOpenKnowledge={onOpenKnowledge} onAddAccount={onAddAccount} onOpenSources={onOpenSources} />
    </RestartProvider>,
  );
  return { calls, onOpenAiAccounts, onOpenHandover, onOpenRules, onOpenKnowledge, onAddAccount, onOpenSources };
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
  expect(row).toHaveTextContent("Restart to resume 3 waiting tasks");
  expect(row).toHaveTextContent("Work will resume after you restart the app.");
});

test("one waiting request is said in the singular", async () => {
  show([line("restart", { count: 1 })]);
  expect(await screen.findByRole("region", { name: "Restart needed" })).toHaveTextContent("Restart to resume 1 waiting task");
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
  await waitFor(() => expect(row).toHaveTextContent("Close and reopen the app to resume work."));
  expect(within(row).queryByRole("button")).toBeNull();
});

test("a paused account is a line that names the account, the reset time and the count, and opens the AI accounts", async () => {
  const user = userEvent.setup();
  const { onOpenAiAccounts } = show([paused({ count: 2 })]);
  const row = await screen.findByRole("region", { name: "Paused account" });
  expect(row).toHaveTextContent(/Pick another account, or wait: main's limit resets at 3:30\s?PM \(2 requests waiting\)/);
  expect(row).toHaveTextContent("Work resumes when the limit resets.");
  expect(row.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  await user.click(within(row).getByRole("button", { name: "Open AI accounts" }));
  expect(onOpenAiAccounts).toHaveBeenCalledTimes(1);
});

test("a reset on another day names the day with the time, and one waiting request is singular", async () => {
  show([paused({ count: 1, until: `${addDays(localDate(new Date()), 1)}T08:05:00-05:00` })]);
  const row = await screen.findByRole("region", { name: "Paused account" });
  expect(row).toHaveTextContent(/wait until \w{3}, \w{3} \d{1,2}, 8:05\s?AM, when main's limit resets\. 1 task is waiting\./);
});

test("each paused account has its own line, and both kinds can show together", async () => {
  show([line("restart", { count: 1 }), paused({ account: "main" }), paused({ key: "paused:second", account: "second" })]);
  expect(await screen.findByRole("region", { name: "Restart needed" })).toBeInTheDocument();
  const rows = await screen.findAllByRole("region", { name: "Paused account" });
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("main's limit");
  expect(rows[1]).toHaveTextContent("second's limit");
});

test("work waiting for an internet connection is one line that starts with checking the connection, with the count and since when", async () => {
  show([line("offline", { key: "offline", waiting_since: `${localDate(new Date())}T14:05:00-05:00`, count: 3 })]);
  const row = await screen.findByRole("region", { name: "No internet connection" });
  expect(row).toHaveTextContent(/^No internet connectionCheck your internet connection: 3 tasks have been waiting since 2:05\s?PM/);
  expect(row).toHaveTextContent("Work resumes when your internet connection returns.");
  expect(row.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  expect(within(row).queryByRole("button")).toBeNull();
});

test("one request waiting for an internet connection is singular, and the line is gone once the queue no longer has it", async () => {
  show([line("offline", { key: "offline", waiting_since: `${addDays(localDate(new Date()), -1)}T08:05:00-05:00` })]);
  const row = await screen.findByRole("region", { name: "No internet connection" });
  expect(row).toHaveTextContent(/1 task has been waiting since \w{3}, \w{3} \d{1,2}, 8:05\s?AM/);
});

test("nothing is drawn for the network when the queue has no such line", async () => {
  const { calls } = show([line("overdue", { group: "risk" })]);
  await waitFor(() => expect(calls.some((c) => c.route === "GET today/queue")).toBe(true));
  expect(screen.queryByRole("region", { name: "No internet connection" })).toBeNull();
});

const handover = (state: "diverged" | "chosen" | "elsewhere", text: string | null = "Other laptop") =>
  line("handover", { key: "handover", group: "decide", state, text });

test("copies that disagree are a line that starts with the choice and opens the page that settles it", async () => {
  const user = userEvent.setup();
  const { onOpenHandover } = show([handover("diverged")]);
  const row = await screen.findByRole("region", { name: "Two copies" });
  expect(row).toHaveTextContent("Choose which copy to keep: this computer and the synced folder have different changes");
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
  expect(row).toHaveTextContent("Test this backup account before it handles the work.");
  expect(row.textContent).not.toMatch(/routine|tier|fallback/i);
});

test("a failed check says so, and another kind of work is named in plain words", async () => {
  show([backup({ check_failed: true, tier: "deep" }), backup({ key: "other", tier: "something-new", account: "third" })]);
  const rows = await screen.findAllByRole("region", { name: "Check an account" });
  expect(rows[0]).toHaveTextContent("Check second before it stands in for harder work");
  expect(rows[0]).toHaveTextContent("Fix the account and test again, or remove it as a backup in Settings.");
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
  const row = await screen.findByRole("region", { name: "Rules" });
  expect(row).toHaveTextContent("Review 3 rules unused in the last 30 days");
  await user.click(within(row).getByRole("button", { name: "Look over" }));
  expect(onOpenRules).toHaveBeenCalledTimes(1);
});

test("the rules review has one button, Look over, and Not now is in its menu with what it does under it", async () => {
  const user = userEvent.setup();
  const { onOpenKnowledge } = show([line("rule_review", { key: "rule_review", group: "review", count: 2, days: 30, rules: ["RULE-1"], until: "2026-10-22T09:00:00+00:00" })]);
  const row = await screen.findByRole("region", { name: "Rules" });
  expect(within(row).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual(["Look over", "More actions for Rules"]);
  expect(within(row).queryByRole("button", { name: "Not now" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "More actions for Rules" }));
  const items = await screen.findAllByRole("menuitem");
  expect(items.map((i) => i.querySelector("[slot=label]")?.textContent)).toEqual(["Not now", "Open Knowledge"]);
  // The consequence is said before the click.
  expect(items[0]).toHaveTextContent(/Back on Today on .*22/);
  await user.click(items[1]);
  expect(onOpenKnowledge).toHaveBeenCalledTimes(1);
});

test("Not now puts the review off for its week, the toast says until when, and Undo brings the line back", async () => {
  const user = userEvent.setup();
  let putOff = false;
  const { calls, onOpenRules } = show([], {
    "GET today/queue": () => (putOff ? [] : [line("rule_review", { key: "rule_review", group: "review", count: 2, days: 30, rules: ["RULE-1", "RULE-2"], until: "2026-10-22T09:00:00+00:00" })]),
    "POST knowledge/rules/review/not-now": () => {
      putOff = true;
      return { until: "2026-10-22T09:00:00+00:00", signal: "SIG-7" };
    },
    "POST knowledge/rules/review/not-now/SIG-7/undo": () => {
      putOff = false;
      return { ok: "SIG-7" };
    },
  });
  const row = await screen.findByRole("region", { name: "Rules" });
  await user.click(within(row).getByRole("button", { name: "More actions for Rules" }));
  await user.click(await screen.findByRole("menuitem", { name: /Not now/ }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST knowledge/rules/review/not-now")).toHaveLength(1));
  expect(await screen.findByText(/Off Today until .*22/)).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Rules" })).toBeNull());
  expect(onOpenRules).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST knowledge/rules/review/not-now/SIG-7/undo")).toBe(true));
  expect(await screen.findByRole("region", { name: "Rules" })).toBeInTheDocument();
});

test("work with no AI account is a line that starts with the step that fixes it", async () => {
  const user = userEvent.setup();
  const { onAddAccount } = show([line("no_account", { key: "no_account", group: "risk", count: 2, tier: "routine", names: ["routine", "deep"] })]);
  const row = await screen.findByRole("region", { name: "No AI account" });
  expect(row).toHaveTextContent("Helper has no AI account");
  expect(row).toHaveTextContent("Its work waits until one is added.");
  expect(within(row).getAllByRole("button")).toHaveLength(1);
  await user.click(within(row).getByRole("button", { name: "Add one" }));
  expect(onAddAccount).toHaveBeenCalledTimes(1);
});

test("one rule is singular, and rules only moved out of the always-sent part have their own words", async () => {
  show([line("rule_review", { key: "one", group: "review", count: 1, days: 14 }), line("rule_review", { key: "moved", group: "review", count: 0, moved: 2 })]);
  const rows = await screen.findAllByRole("region", { name: "Rules" });
  expect(rows[0]).toHaveTextContent("Review 1 rule unused in the last 14 days");
  expect(rows[1]).toHaveTextContent("Review rules now sent only when relevant");
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
  const row = await screen.findByRole("region", { name: "Waiting for you to start it" });
  expect(row).toHaveTextContent("Learn from 3 kinds of earlier correction: About $0.42");
  expect(row).toHaveTextContent("Nothing is spent until you press Start.");
  await user.click(within(row).getByRole("button", { name: "Start" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST knowledge/catch-up/go")).toHaveLength(1));
  expect(await screen.findByText("Learning from your earlier corrections has started.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Waiting for you to start it" })).toBeNull());
});

test("a new source's intake is one line with its items and days and the total, and Go starts that source's items", async () => {
  const user = userEvent.setup();
  let started = false;
  const { calls } = show([], {
    "GET today/queue": () => (started ? [] : [line("intake_go", { key: "intake_go:m", group: "decide", source: "m", subject: "Inbox", count: 12, days: 14, estimate_usd: 0.42 })]),
    "POST watch/m/intake/go": () => {
      started = true;
      return { started: 12 };
    },
  });
  const row = await screen.findByRole("region", { name: "Waiting for you to start it" });
  expect(row).toHaveTextContent("Take in Inbox: 12 items from the last 14 days");
  expect(row).toHaveTextContent("About $0.42 in all. Nothing is spent until you press Start.");
  await user.click(within(row).getByRole("button", { name: "Start" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST watch/m/intake/go")).toHaveLength(1));
  expect(await screen.findByText("Taking in Inbox has started.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Waiting for you to start it" })).toBeNull());
});

test("a source with no mail says items without days, one item and one day are singular, and no price says so", async () => {
  show([
    line("intake_go", { key: "intake_go:pages", group: "decide", source: "pages", subject: "Pages", count: 3, days: null, estimate_usd: null, unpriced: 3 }),
    line("intake_go", { key: "intake_go:m", group: "decide", source: "m", subject: "Inbox", count: 1, days: 1, estimate_usd: 0.004, unpriced: 1 }),
  ]);
  const rows = await screen.findAllByRole("region", { name: "Waiting for you to start it" });
  expect(rows[0]).toHaveTextContent("Take in Pages: 3 items");
  expect(rows[0]).not.toHaveTextContent("from the last");
  expect(rows[0]).toHaveTextContent("It uses your plan's allowance. Nothing is spent until you press Start.");
  expect(rows[1]).toHaveTextContent("Take in Inbox: 1 item from the last day");
  expect(rows[1]).toHaveTextContent("plus some of your plan's allowance");
});

test("catch-up runs with no price say they use the plan's allowance", async () => {
  show([line("catch_up_go", { key: "catch_up_go", group: "decide", count: 1, estimate_usd: null, unpriced: 1 })]);
  expect(await screen.findByRole("region", { name: "Waiting for you to start it" })).toHaveTextContent(
    "Learn from 1 kind of earlier correction. It uses your plan's allowance.",
  );
});

test("a kind of file that isn't being read is one line with its kind and why, and no button", async () => {
  show([line("extractor", { key: "extractor:pdf", file_kind: "pdf", text: "the PDF is locked with a password" })]);
  const row = await screen.findByRole("region", { name: "Reading files" });
  expect(row).toHaveTextContent("Reading PDFs isn't working: the PDF is locked with a password");
  expect(row).toHaveTextContent("This notice clears after one is read successfully.");
  expect(within(row).queryByRole("button")).toBeNull();
});

test("a kind of file an add-on named itself is shown as the add-on called it", async () => {
  show([line("extractor", { key: "extractor:Drawings", file_kind: "Drawings", text: "it stopped" })]);
  expect(await screen.findByRole("region", { name: "Reading files" })).toHaveTextContent("Reading Drawings isn't working: it stopped");
});

const borrow = (over: Partial<S["QueueLineView"]> = {}) =>
  line("borrow", {
    key: "borrow:routine",
    group: "decide",
    account: "second",
    model: "default",
    tier: "routine",
    text: "main",
    until: `${localDate(new Date())}T15:30:00-05:00`,
    count: 2,
    estimate_usd: 0.31,
    ...over,
  });

test("borrowing another kind of work's account is a question with the account, the reset time and the estimate", async () => {
  show([borrow()]);
  const row = await screen.findByRole("region", { name: "Account choice" });
  expect(row).toHaveTextContent(/Use second for everyday work until main's limit resets at 3:30\s?PM\?/);
  expect(row).toHaveTextContent("Process 2 waiting items for About $0.31 total, only after you approve.");
  expect(row.textContent).not.toMatch(/tier|fallback/i);
});

test("an account with no price says it would use the plan's allowance", async () => {
  show([borrow({ estimate_usd: null, unpriced: 2, count: 1, tier: "other-kind" })]);
  const row = await screen.findByRole("region", { name: "Account choice" });
  expect(row).toHaveTextContent("for this kind of work until main's limit resets");
  expect(row).toHaveTextContent("Process 1 waiting item using this account's allowance, only after you approve.");
});

test("yes sends the answer with the account the question offered, and nothing is sent before the click", async () => {
  const user = userEvent.setup();
  let answered = false;
  const calls = show([], {
    "GET today/queue": () => (answered ? [] : [borrow()]),
    "POST ai/borrow": () => {
      answered = true;
      return { released: 2 };
    },
  }).calls;
  const row = await screen.findByRole("region", { name: "Account choice" });
  expect(calls.some((c) => c.route === "POST ai/borrow")).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Use second for everyday work until the limit resets" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST ai/borrow")).toHaveLength(1));
  expect(calls.find((c) => c.route === "POST ai/borrow")?.body).toEqual({ tier: "routine", account: "second", model: "default", use: true });
  expect(await screen.findByText(/second is doing the waiting work until/)).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Account choice" })).toBeNull());
});

test("no keeps the work waiting and sends the answer as a no", async () => {
  const user = userEvent.setup();
  let answered = false;
  const calls = show([], {
    "GET today/queue": () => (answered ? [] : [borrow()]),
    "POST ai/borrow": () => {
      answered = true;
      return { released: 0 };
    },
  }).calls;
  const row = await screen.findByRole("region", { name: "Account choice" });
  await user.click(within(row).getByRole("button", { name: "No, wait" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/borrow")?.body).toEqual({ tier: "routine", account: "second", model: "default", use: false }));
  expect(await screen.findByText("Work is waiting for main.")).toBeInTheDocument();
});

const credential = (over: Partial<S["QueueLineView"]> = {}) =>
  line("credential", {
    key: "credential:account:main",
    credential_kind: "account",
    credential_name: "main",
    due: "2027-01-31",
    waiting_days: 5,
    places: ["the AI account main", "the AI account backup", "the key that locks the backups"],
    ...over,
  });

test("a key about to end is a line that starts with renewing it and names every other place it is used", async () => {
  const user = userEvent.setup();
  const { onOpenAiAccounts } = show([credential()]);
  const row = await screen.findByRole("region", { name: "Access key ending" });
  expect(row).toHaveTextContent(/Replace the access key for the AI account main before .*31/);
  expect(row).toHaveTextContent("Replace this access key everywhere it is used:");
  const places = within(row).getAllByRole("listitem").map((i) => i.textContent);
  expect(places).toEqual(["the AI account backup", "the key that locks the backups"]);
  await user.click(within(row).getByRole("button", { name: "Open AI accounts" }));
  expect(onOpenAiAccounts).toHaveBeenCalledTimes(1);
});

test("a key used in one place only says so, and one that has already ended says when it stopped", async () => {
  show([credential({ places: ["the AI account main"], waiting_days: -2 })]);
  const row = await screen.findByRole("region", { name: "Access key ending" });
  expect(row).toHaveTextContent(/Replace the access key for the AI account main: it expired on .*31/);
  expect(row).toHaveTextContent("This access key isn't used elsewhere.");
  expect(within(row).queryAllByRole("listitem")).toHaveLength(0);
});

test("a sign-in about to end offers to sign in again, and names what reads through it", async () => {
  const user = userEvent.setup();
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  const calls = show([credential({ key: "credential:sign_in:p/s", credential_kind: "sign_in", credential_name: "p/s", places: ["the Mail sign-in", "the source Inbox"] })], {
    "POST sign-ins/p/s/start": () => ({ url: "about:blank#signin" }),
  }).calls;
  const row = await screen.findByRole("region", { name: "Access key ending" });
  expect(row).toHaveTextContent(/Sign in again to renew the Mail sign-in before .*31/);
  expect(within(row).getAllByRole("listitem").map((i) => i.textContent)).toEqual(["the source Inbox"]);
  await user.click(within(row).getByRole("button", { name: "Sign in again" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("about:blank#signin"));
  expect(calls.some((c) => c.route === "POST sign-ins/p/s/start")).toBe(true);
});

const switchFailed = (over: Partial<S["QueueLineView"]> = {}) =>
  line("switch_failed", { key: "switch_failed:routine", account: "second", text: "first", tier: "routine", count: 2, names: ["A date in a pasted thread", "A reply that closes one question"], ...over });

test("a failed switch check names the new and the earlier account, what didn't come out right, and the two ways forward", async () => {
  show([switchFailed()]);
  const row = await screen.findByRole("region", { name: "Review account change" });
  expect(row).toHaveTextContent("Switch second back, or keep it, for everyday work");
  expect(row).toHaveTextContent("The account-change test found 2 failed cases. First:");
  expect(within(row).getAllByRole("listitem").map((i) => i.textContent)).toEqual(["A date in a pasted thread", "A reply that closes one question"]);
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Switch back", "Keep it"]);
});

test("Switch back puts the earlier choice back with the current settings and the line goes", async () => {
  const user = userEvent.setup();
  let lines = [switchFailed()];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST ai/switch/routine/back": () => {
      lines = [];
      return { changes: [], fingerprint: "fp-2", needs_restart: false };
    },
  });
  await user.click(within(await screen.findByRole("region", { name: "Review account change" })).getByRole("button", { name: "Switch everyday work back to first" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/switch/routine/back")?.body).toEqual({ fingerprint: "fp-1" }));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Review account change" })).toBeNull());
  expect(await screen.findByText("everyday work is back with first.")).toBeInTheDocument();
});

test("Keep it leaves the switch and the line goes", async () => {
  const user = userEvent.setup();
  let lines = [switchFailed({ count: 1, names: ["A date in a pasted thread"] })];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "POST ai/switch/routine/keep": () => {
      lines = [];
      return { ok: "routine" };
    },
  });
  const row = await screen.findByRole("region", { name: "Review account change" });
  expect(row).toHaveTextContent("The account-change test found 1 failed case:");
  await user.click(within(row).getByRole("button", { name: "Keep second for everyday work" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/switch/routine/keep")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Review account change" })).toBeNull());
});

test("a check that couldn't finish says so and names no cases", async () => {
  show([switchFailed({ count: 0, names: [], check_failed: true })]);
  const row = await screen.findByRole("region", { name: "Review account change" });
  expect(row).toHaveTextContent("The test couldn't finish. The new account's performance is unknown.");
  expect(within(row).queryAllByRole("listitem")).toHaveLength(0);
});

const identityLine = (over: Partial<S["QueueLineView"]> = {}) =>
  line("identity", { key: "identity:second", group: "decide", account: "second", text: "sam@example.com", subject: "alex@example.com", state: "changed", ...over });

test("a changed sign-in says which account now runs as whom and offers Sign in again and Keep it", async () => {
  const { onOpenAiAccounts } = show([identityLine()]);
  const row = await screen.findByRole("region", { name: "Check a sign-in" });
  expect(row).toHaveTextContent("The second agent now runs as sam@example.com: keep it or sign in again?");
  expect(row).toHaveTextContent("Anything above open material waits until you answer.");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Sign in again", "Keep it"]);
  await userEvent.setup().click(within(row).getByRole("button", { name: "Sign in again for second" }));
  expect(onOpenAiAccounts).toHaveBeenCalled();
});

test("Keep it records the new sign-in for the account, says so, and the line goes", async () => {
  const user = userEvent.setup();
  let lines = [identityLine()];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "POST ai/accounts/second/identity/keep": () => {
      lines = [];
      return { ok: "second" };
    },
  });
  const row = await screen.findByRole("region", { name: "Check a sign-in" });
  await user.click(within(row).getByRole("button", { name: "Keep sam@example.com for second" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/second/identity/keep")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Check a sign-in" })).toBeNull());
  expect(await screen.findByText("second now runs as sam@example.com.")).toBeInTheDocument();
});

test("work above the levels a sign-in is set for says so, with how much waits, and opens the account", async () => {
  const { onOpenAiAccounts } = show([identityLine({ key: "identity:second:level", state: "level", subject: null, count: 2, names: ["restricted"] })]);
  const row = await screen.findByRole("region", { name: "Check a sign-in" });
  expect(row).toHaveTextContent("The second agent runs as sam@example.com, which isn't set for restricted material");
  expect(row).toHaveTextContent("2 pieces of work wait.");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Open the account"]);
  await userEvent.setup().click(within(row).getByRole("button", { name: "Open second" }));
  expect(onOpenAiAccounts).toHaveBeenCalled();
});

test("a paused account and a check are named as the person named the account, and the answer still goes to its id", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET today/queue": () => [paused({ account: "acct-1" }), line("account_check", { key: "check", account: "acct-2", tier: "routine", model: "default", group: "risk" })],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
    "GET ai/accounts": () => [
      { name: "acct-1", label: "Main account", kind: null, adapter: "x", models: {}, used_for: [], backup_for: [], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0 },
      { name: "acct-2", label: "Second account", kind: null, adapter: "x", models: {}, used_for: [], backup_for: [], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0 },
    ],
    "GET ai/endpoints": () => [],
    "POST ai/accounts/acct-2/test?tier=routine&model=default": () => [{ tier: "account", account: "acct-2", main: true, ok: true, detail: "answered" }],
  });
  renderApp(
    <RestartProvider hellos={1}>
      <HeldLines onOpenAiAccounts={() => undefined} onOpenHandover={() => undefined} />
    </RestartProvider>,
  );
  const pausedRow = await screen.findByRole("region", { name: "Paused account" });
  await waitFor(() => expect(pausedRow).toHaveTextContent("Main account's limit resets"));
  expect(pausedRow).not.toHaveTextContent("acct-1");
  const check = await screen.findByRole("region", { name: "Check an account" });
  expect(check).toHaveTextContent("Check Second account before it stands in for everyday work");
  await user.click(within(check).getByRole("button", { name: /Check Second account/ }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/acct-2/test?tier=routine&model=default")).toBe(true));
});

const unreadSource = (over: Partial<S["QueueLineView"]> = {}) =>
  line("source_unread", {
    key: "source_unread:work-mail",
    source: "work-mail",
    subject: "Work mail",
    problem_kind: "auth",
    text: "The sign-in was withdrawn. Sign in to it again, then it is read on its next turn.",
    waiting_since: `${addDays(localDate(new Date()), -1)}T18:00:00-05:00`,
    ...over,
  });

test("a source that couldn't be read for too long is a line that starts with what to do, says since when and opens Connections", async () => {
  const user = userEvent.setup();
  const { onOpenSources } = show([unreadSource()]);
  const row = await screen.findByRole("region", { name: "Connection not read" });
  expect(row).toHaveTextContent(/^Connection not readSign in to Work mail again: not read since yesterday/);
  expect(row).toHaveTextContent("The sign-in was withdrawn. Sign in to it again, then it is read on its next turn.");
  await user.click(within(row).getByRole("button", { name: "Open Connections" }));
  expect(onOpenSources).toHaveBeenCalledTimes(1);
});

test("a source line for a kind of failure with no verb of its own still starts with one", async () => {
  show([unreadSource({ problem_kind: "outage" })]);
  expect(await screen.findByRole("region", { name: "Connection not read" })).toHaveTextContent(/Check Work mail: not read since/);
});

const workAccess = (over: Partial<S["QueueLineView"]> = {}) => line("work_access", { key: "work_access:second", group: "decide", account: "second", ...over });

test("an account the person said Not now about is a line that starts with Let, names it and has one button, Allow", async () => {
  show([workAccess()]);
  const row = await screen.findByRole("region", { name: "Access" });
  expect(row).toHaveTextContent("Let second read your work mail and notes");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Allow"]);
  expect(within(row).getByRole("button", { name: "Allow second to read your work mail and notes" })).toBeInTheDocument();
});

test("Allow gives the yes with the current settings, says so, the line goes and Undo puts the answer back", async () => {
  const user = userEvent.setup();
  let lines = [workAccess()];
  const changes = [
    { key: "ai.providers.second.allowed_data", before: ["open"], after: ["open", "internal"], was_default: false, is_default: false },
    { key: "ai.providers.second.work_data", before: "not_now", after: "", was_default: false, is_default: true },
  ];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST ai/accounts/second/allow-work": () => {
      lines = [];
      return { changes, fingerprint: "fp-2", needs_restart: false };
    },
    "POST settings": () => {
      lines = [workAccess()];
      return { changes: [], fingerprint: "fp-3", needs_restart: false };
    },
  });
  const row = await screen.findByRole("region", { name: "Access" });
  await user.click(within(row).getByRole("button", { name: "Allow second to read your work mail and notes" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/second/allow-work")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("second can now read your work mail and notes.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Access" })).toBeNull());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({
      changes: { "ai.providers.second.allowed_data": ["open"], "ai.providers.second.work_data": "not_now" },
      reset: [],
      fingerprint: "fp-2",
    }),
  );
  expect(await screen.findByRole("region", { name: "Access" })).toBeInTheDocument();
});

// ---- the lines about accounts' models and connections --------------------------------------------------------------

const accountMove = (over: Partial<S["QueueLineView"]> = {}) =>
  line("account_move", { key: "account_move:main", group: "decide", account: "main", subject: "Service", ...over });
const readback = (over: Partial<S["AiMoveReadback"]> = {}): S["AiMoveReadback"] => ({
  account: "main", service: "Service", key_ending: "wxyz", key_known: true, key_differs: false, address: "api.example.com", address_was: "api.example.com", address_differs: false, ...over,
});

test("an account that could move offers Move and Not now, and Move shows what the new connection signs in as before anything runs", async () => {
  const user = userEvent.setup();
  const { calls } = show([accountMove()], { "GET ai/accounts/main/move": () => readback() });
  const row = await screen.findByRole("region", { name: "Account connection" });
  expect(row).toHaveTextContent("Move main to its service's own connection");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Move", "Not now"]);
  expect(calls.some((c) => c.route.startsWith("GET ai/accounts/main/move"))).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Move main to its service's own connection" }));
  const list = await within(row).findByRole("list", { name: "What the new connection would sign in as" });
  expect(within(list).getAllByRole("listitem").map((i) => i.textContent)).toEqual(["The same key, ending wxyz", "The same address, api.example.com", "The same account name, main"]);
  expect(calls.some((c) => c.route === "POST ai/accounts/main/move")).toBe(false);
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Check and move", "Not yet"]);
});

test("the read-back says plainly when the key or the address would differ, or the key can't be read", async () => {
  const user = userEvent.setup();
  let body = readback({ key_differs: true, key_ending: "abcd", address_differs: true, address: "new.example.com", address_was: "old.example.com" });
  show([accountMove()], { "GET ai/accounts/main/move": () => body });
  const row = await screen.findByRole("region", { name: "Account connection" });
  await user.click(within(row).getByRole("button", { name: /^Move main/ }));
  const items = async () => (await within(row).findAllByRole("listitem")).map((i) => i.textContent);
  expect(await items()).toEqual(["Not the key main uses now: a different one, ending abcd", "The address new.example.com, not old.example.com", "The same account name, main"]);
});

test("a key that can't be read is said so, and a key too short to show shows none of itself", async () => {
  const user = userEvent.setup();
  show([accountMove()], { "GET ai/accounts/main/move": () => readback({ key_known: false, key_ending: "" }) });
  const row = await screen.findByRole("region", { name: "Account connection" });
  await user.click(within(row).getByRole("button", { name: /^Move main/ }));
  expect((await within(row).findAllByRole("listitem"))[0]).toHaveTextContent("A key that can't be read right now");
});

test("the yes runs the check and a passed one moves the account, with Undo", async () => {
  const user = userEvent.setup();
  let lines = [accountMove()];
  const changes = [{ key: "ai.providers.main.adapter", before: "generic", after: "own", was_default: false, is_default: false }];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET ai/accounts/main/move": () => readback(),
    "POST ai/accounts/main/move": () => {
      lines = [];
      return { moved: true, saved: { changes, fingerprint: "fp-2", needs_restart: false } };
    },
    "POST settings": () => {
      lines = [accountMove()];
      return { changes: [], fingerprint: "fp-3", needs_restart: false };
    },
  });
  const row = await screen.findByRole("region", { name: "Account connection" });
  await user.click(within(row).getByRole("button", { name: /^Move main/ }));
  await user.click(await within(row).findByRole("button", { name: "Check main on the new connection and move it" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/accounts/main/move")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("main now uses its service's own connection.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("region", { name: "Account connection" })).toBeNull());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { "ai.providers.main.adapter": "generic" }, reset: [], fingerprint: "fp-2" }));
  expect(await screen.findByRole("region", { name: "Account connection" })).toBeInTheDocument();
});

test("a failed check leaves the account as it was, says why, and the line stays", async () => {
  const user = userEvent.setup();
  show([accountMove()], {
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET ai/accounts/main/move": () => readback(),
    "POST ai/accounts/main/move": () => ({ moved: false, detail: "the service didn't accept the key", saved: null }),
  });
  const row = await screen.findByRole("region", { name: "Account connection" });
  await user.click(within(row).getByRole("button", { name: /^Move main/ }));
  await user.click(await within(row).findByRole("button", { name: /^Check main/ }));
  expect(await within(row).findByRole("status")).toHaveTextContent("main stays as it was. The check said: the service didn't accept the key");
  expect(within(row).getByRole("button", { name: /^Check main/ })).toBeEnabled();
});

test("Not now puts the move off and the line goes", async () => {
  const user = userEvent.setup();
  let lines = [accountMove()];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "POST ai/accounts/main/move/not-now": () => {
      lines = [];
      return { ok: "main" };
    },
  });
  await user.click(within(await screen.findByRole("region", { name: "Account connection" })).getByRole("button", { name: "Don't move main now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/accounts/main/move/not-now")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Account connection" })).toBeNull());
});

const modelWatch = (over: Partial<S["QueueLineView"]> = {}) =>
  line("model_watch", { key: "model_watch:main:newer", group: "decide", account: "main", state: "newer", names: ["routine"], candidates: { routine: "model-new" }, reason: "asks", usd_per_day: -0.4, ...over });
const accountsWith = () => [
  { name: "main", label: "", kind: null, adapter: "x", models: { default: "model-old", harder: "model-big" }, used_for: [], backup_for: [], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0 },
];

test.each([
  [{ reason: "asks", usd_per_day: -0.4 }, "It would cost about $0.40 a day less at your current use."],
  [{ reason: "asks", usd_per_day: 0 }, "It would cost about the same at your current use."],
  [{ reason: "costs_more", usd_per_day: 1.25 }, "It costs about $1.25 a day more at your current use, so it isn't switched to on its own."],
  [{ reason: "price_unknown", usd_per_day: null }, "Its price isn't known yet, so it isn't switched to on its own."],
  [{ reason: "check_failed", count: 2 }, "Its check found 2 cases that didn't come out right, so it wasn't switched to."],
  [{ reason: "check_failed", check_failed: true }, "Its check couldn't finish, so it wasn't switched to."],
  [{ reason: "check_cost", estimate_usd: 5 }, "Its check costs about $5.00, which is above the amount you asked to be asked about. Switch to go ahead."],
])("a newer model says what it would change in cost and why it isn't switched to on its own (%j)", async (over, sub) => {
  show([modelWatch(over as Partial<S["QueueLineView"]>)], { "GET ai/accounts": accountsWith, "GET ai/endpoints": () => [] });
  const row = await screen.findByRole("region", { name: "Newer model" });
  expect(row).toHaveTextContent("Look at a newer model for everyday work");
  expect(row).toHaveTextContent(sub);
  expect(row).not.toHaveTextContent("model-new");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Switch", "Not now"]);
});

test("Switch goes through the settings' own switch with its check, for every tier the line names, and nothing is sent before it", async () => {
  const user = userEvent.setup();
  let lines = [modelWatch({ names: ["routine", "deep"], candidates: { routine: "model-new", deep: "model-big" } })];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET ai/accounts": accountsWith,
    "GET ai/endpoints": () => [],
    "POST ai/accounts/main/switch-check": () => {
      lines = [];
      return { saved: { changes: [], fingerprint: "fp-2", needs_restart: false }, checking: true };
    },
  });
  const row = await screen.findByRole("region", { name: "Newer model" });
  expect(row).toHaveTextContent("everyday work and harder work");
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
  await user.click(await within(row).findByRole("button", { name: "Switch everyday work and harder work to the newer model" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST ai/accounts/main/switch-check")?.body).toEqual({
      fingerprint: "fp-1",
      models: { default: "model-old", harder: "model-big", "model-new": "model-new" },
      use: { routine: "model-new", deep: "harder" },
    }),
  );
  await waitFor(() => expect(screen.queryByRole("region", { name: "Newer model" })).toBeNull());
});

test("Not now on a newer model puts it off for that kind of line", async () => {
  const user = userEvent.setup();
  let lines = [modelWatch()];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET ai/accounts": accountsWith,
    "GET ai/endpoints": () => [],
    "POST ai/model-watch/main/newer/not-now": () => {
      lines = [];
      return { ok: "main" };
    },
  });
  await user.click(await within(await screen.findByRole("region", { name: "Newer model" })).findByRole("button", { name: "Not now for the newer model for everyday work" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/model-watch/main/newer/not-now")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Newer model" })).toBeNull());
});

test("a price rise on the current model says the increase and offers no switch", async () => {
  const user = userEvent.setup();
  let lines = [modelWatch({ key: "model_watch:main:price", state: "price", candidates: {}, reason: null, usd_per_day: 0.6 })];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "POST ai/model-watch/main/price/not-now": () => {
      lines = [];
      return { ok: "main" };
    },
  });
  const row = await screen.findByRole("region", { name: "Price change" });
  expect(row).toHaveTextContent("The model for everyday work costs more now");
  expect(row).toHaveTextContent("The same work now costs about $0.60 a day more.");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Got it"]);
  await user.click(within(row).getByRole("button", { name: /^Got it/ }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/model-watch/main/price/not-now")).toBe(true));
});

const modelMoved = (over: Partial<S["QueueLineView"]> = {}) =>
  line("model_moved", { key: "model_moved:routine", group: "decide", account: "main", text: "main", tier: "routine", usd_per_day: -0.4, ...over });

test("a tier moved on its own says what moved and what it changes in cost, with Keep it and Switch back", async () => {
  show([modelMoved()]);
  const row = await screen.findByRole("region", { name: "Moved to a newer model" });
  expect(row).toHaveTextContent("everyday work moved to a newer model after its check passed");
  expect(row).toHaveTextContent("It costs about $0.40 a day less at your current use.");
  expect(row).not.toHaveTextContent("model-");
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual(["Keep it", "Switch back"]);
});

test("Switch back restores the earlier model through the switch route, with Undo, and Keep it clears the line", async () => {
  const user = userEvent.setup();
  let lines = [modelMoved()];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST ai/switch/routine/back": () => {
      lines = [];
      return { changes: [{ key: "ai.tiers.routine.use", before: "main/new", after: "main/default", was_default: false, is_default: false }], fingerprint: "fp-2", needs_restart: false };
    },
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
  });
  await user.click(within(await screen.findByRole("region", { name: "Moved to a newer model" })).getByRole("button", { name: "Switch everyday work back to its earlier model" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/switch/routine/back")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("everyday work is back on its earlier model.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { "ai.tiers.routine.use": "main/new" }, reset: [], fingerprint: "fp-2" }));
});

test("Keep it on a moved tier clears the line and nothing else changes", async () => {
  const user = userEvent.setup();
  let lines = [modelMoved({ usd_per_day: null })];
  const { calls } = show(lines, {
    "GET today/queue": () => lines,
    "POST ai/switch/routine/keep": () => {
      lines = [];
      return { ok: "routine" };
    },
  });
  const row = await screen.findByRole("region", { name: "Moved to a newer model" });
  expect(row).toHaveTextContent("It costs about the same at your current use.");
  await user.click(within(row).getByRole("button", { name: "Keep the newer model for everyday work" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST ai/switch/routine/keep")).toBe(true));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Moved to a newer model" })).toBeNull());
  expect(calls.filter((c) => c.route.startsWith("POST")).map((c) => c.route)).toEqual(["POST ai/switch/routine/keep"]);
});
