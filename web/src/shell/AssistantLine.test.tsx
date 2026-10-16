import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { localDate } from "../lib/dates";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { AssistantLine } from "./AssistantLine";

const TODAY = localDate(new Date());

function show(status: S["Status"], onOpenGuide: (step?: string) => void = () => undefined) {
  fakeApi({ "GET status": () => status, "GET runtime-config": () => ({ instance: null }) });
  renderApp(
    <RestartProvider hellos={1}>
      <AssistantLine onOpenGuide={onOpenGuide} />
    </RestartProvider>,
  );
}

const line = () => screen.findByRole("button", { name: /^Assistant/ });
const lineNow = () => document.querySelector("[data-alive]") as HTMLElement;
const open = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await line());
  return screen.getByRole("dialog", { name: "Assistant" });
};

const ran = { last_run_at: `${TODAY}T09:42:00+09:00` };

test("fine: the line says the assistant is working and when it last ran, with an icon and words", async () => {
  show(statusFixture({}, { assistant: ran }));
  const button = await line();
  expect(button).toHaveTextContent("Assistant");
  expect(button).toHaveTextContent(/last run 9:42/);
  expect(button).toHaveAttribute("data-tone", "ok");
  expect(button.querySelector("[data-icon='check']")).toHaveAccessibleName("Working");
});

test("before the first run the line says there are no runs yet, and still reads as fine", async () => {
  show(statusFixture());
  const button = await line();
  expect(button).toHaveTextContent("no runs yet");
  expect(button).toHaveAttribute("data-tone", "ok");
});

test("amber: work waiting for the network is said in words, with its own icon", async () => {
  show(statusFixture({ network_wait: { count: 2, since: `${TODAY}T09:00:00+00:00` } }, { assistant: ran }));
  await waitFor(() => expect(lineNow()).toHaveAttribute("data-alive", "network"));
  expect(lineNow()).toHaveAttribute("data-tone", "warn");
  expect(lineNow()).toHaveTextContent("waiting for the network");
  expect(lineNow().querySelector("[data-icon='alert']")).toHaveAccessibleName("Needs a look");
});

test("amber: a paused account names itself and when its limit resets", async () => {
  show(statusFixture({}, { assistant: { ...ran, paused: [{ account: "main-account", until: `${TODAY}T11:30:00+09:00` }] } }));
  await waitFor(() => expect(lineNow()).toHaveAttribute("data-alive", "paused"));
  expect(lineNow()).toHaveTextContent(/main-account paused until 11:30/);
  expect(lineNow()).toHaveAttribute("data-tone", "warn");
});

test("amber: a restart waiting to be done shows as waiting for a restart", async () => {
  show(statusFixture({ restart_needed: "A change needs the app to restart." }, { assistant: ran }));
  await waitFor(() => expect(lineNow()).toHaveAttribute("data-alive", "restart"));
  expect(lineNow()).toHaveTextContent("waiting for a restart");
});

test("red: a failed last run says so with its time, with a different icon and words", async () => {
  show(statusFixture({}, { assistant: { ...ran, last_run_failed: true } }));
  await waitFor(() => expect(lineNow()).toHaveAttribute("data-alive", "run_failed"));
  expect(lineNow()).toHaveAttribute("data-tone", "bad");
  expect(lineNow()).toHaveTextContent(/last run failed 9:42/);
  expect(lineNow().querySelector("[data-icon='close']")).toHaveAccessibleName("Not working");
});

test("red: an account that can't be used beats the amber states, and the popover offers the AI step", async () => {
  const user = userEvent.setup();
  const onOpenGuide = vi.fn();
  show(
    statusFixture({ network_wait: { count: 1, since: `${TODAY}T09:00:00+00:00` } }, { ai: { state: "failing", detail: "The account said no." }, assistant: ran }),
    onOpenGuide,
  );
  await waitFor(() => expect(lineNow()).toHaveAttribute("data-alive", "failing"));
  expect(lineNow()).toHaveTextContent("can't use its AI account");
  const dialog = await open(user);
  await user.click(within(dialog).getByRole("button", { name: "Open the AI step" }));
  await waitFor(() => expect(onOpenGuide).toHaveBeenCalledWith("ai"));
});

test("the popover shows today's runs by account with failures, what waits and since when, and each tier's fallback order", async () => {
  const user = userEvent.setup();
  show(
    statusFixture(
      {},
      {
        assistant: {
          ...ran,
          runs_today: [
            { account: "main-account", count: 5, failed: 1 },
            { account: "backup-account", count: 1, failed: 0 },
          ],
          queued: 3,
          oldest_queued_since: `${TODAY}T08:15:00+09:00`,
          chains: [
            { tier: "routine", accounts: ["main-account", "backup-account"] },
            { tier: "custom-tier", accounts: ["backup-account"] },
          ],
        },
      },
    ),
  );
  const dialog = await open(user);
  const runs = within(dialog).getByText("Runs today").closest("li")!;
  expect(runs).toHaveTextContent("main-account: 5 runs, 1 failed");
  expect(runs).toHaveTextContent("backup-account: 1 run");
  expect(runs).not.toHaveTextContent("backup-account: 1 run, ");
  const queue = within(dialog).getByText("Waiting for the assistant").closest("li")!;
  expect(queue).toHaveTextContent(/3 requests, the oldest waiting since 8:15/);
  const chains = within(dialog).getByText(/^If an account can't serve/).closest("li")!;
  expect(chains).toHaveTextContent("Everyday work: main-account then backup-account");
  expect(chains).toHaveTextContent("custom-tier: backup-account");
});

test("the popover with nothing to show says so in words, and has no problem row when all is fine", async () => {
  const user = userEvent.setup();
  show(statusFixture());
  const dialog = await open(user);
  expect(within(dialog).getByText("No runs yet today.")).toBeInTheDocument();
  expect(within(dialog).getByText("Nothing is waiting.")).toBeInTheDocument();
  expect(within(dialog).getByText("No account is set up yet.")).toBeInTheDocument();
  expect(dialog.querySelector("[data-section='problem']")).toBeNull();
});

test("accounts are called by the names the person gave them, in the line and in the details, never by their ids", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET status": () =>
      statusFixture(
        {},
        {
          assistant: {
            ...ran,
            runs_today: [{ account: "acct-1", count: 3, failed: 0 }],
            chains: [{ tier: "routine", accounts: ["acct-1", "acct-2"] }],
            paused: [{ account: "acct-1", until: `${TODAY}T14:20:00+09:00` }],
          },
        },
      ),
    "GET runtime-config": () => ({ instance: null }),
    "GET ai/accounts": () => [
      { name: "acct-1", label: "Main account", kind: null, adapter: "x", models: {}, used_for: ["routine"], backup_for: [], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0 },
      { name: "acct-2", label: "", kind: "svc", adapter: "x", models: {}, used_for: [], backup_for: ["routine"], has_key: true, key_state: "saved", key_ending: false, spent_today_usd: 0 },
    ],
    "GET ai/endpoints": () => [{ id: "svc", name: "Service A", adapter: "x", base_url: "", needs_key: true }],
  });
  renderApp(
    <RestartProvider hellos={1}>
      <AssistantLine onOpenGuide={() => undefined} />
    </RestartProvider>,
  );
  const button = await line();
  await waitFor(() => expect(button).toHaveTextContent("Main account"));
  expect(button).not.toHaveTextContent("acct-1");
  await user.click(button);
  const dialog = screen.getByRole("dialog", { name: "Assistant" });
  expect(dialog).toHaveTextContent("Main account");
  expect(dialog).toHaveTextContent("Service A account");
  expect(dialog).not.toHaveTextContent(/acct-/);
});
