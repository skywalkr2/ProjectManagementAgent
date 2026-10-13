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
  renderApp(
    <RestartProvider hellos={1}>
      <HeldLines onOpenAiAccounts={onOpenAiAccounts} onOpenHandover={onOpenHandover} />
    </RestartProvider>,
  );
  return { calls, onOpenAiAccounts, onOpenHandover };
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
