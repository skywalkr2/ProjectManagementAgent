import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartAnnouncer, RestartProvider, useRestart } from "../lib/restart";
import { Refuse, fakeApi, renderApp, statusFixture } from "../test-utils";
import { StatusMenu } from "./StatusMenu";

const NEEDED = "A change needs the app to restart. New AI work waits until then.";

function show(
  status: S["Status"],
  routes: Record<string, (body: unknown) => unknown> = {},
  opts: { live?: "live" | "offline" | "connecting"; demo?: boolean; onOpenGuide?: (step?: string) => void; refresh?: () => void } = {},
) {
  const calls = fakeApi({ "GET status": () => status, "GET runtime-config": () => ({ instance: null }), ...routes });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartAnnouncer />
      <StatusMenu
        live={{ state: opts.live ?? "live", lastUpdate: new Date(2026, 9, 13, 11, 5), refresh: opts.refresh ?? (() => undefined) }}
        demo={opts.demo ?? false}
        onOpenGuide={opts.onOpenGuide ?? (() => undefined)}
      />
    </RestartProvider>,
  );
  return calls;
}

const chip = () => screen.findByRole("button", { name: /^Status: /, hidden: true });
const chipNow = () => document.querySelector("[data-status]") as HTMLElement;
const chipText = (text: string) => waitFor(() => expect(chipNow()).toHaveTextContent(text));
const chipIs = (kind: string) => waitFor(() => expect(chipNow()).toHaveAttribute("data-status", kind));
const open = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await chip());
  return screen.getByRole("dialog", { name: "Status" });
};

test("all good: the chip says Live in words, and the popover says when the screen last updated", async () => {
  const user = userEvent.setup();
  show(statusFixture({}, { backup: { configured: true, age_hours: 0.5, needs_attention: false } }));
  expect(await chip()).toHaveTextContent("Live");
  expect(await chip()).toHaveAttribute("data-status", "live");
  const dialog = await open(user);
  expect(within(dialog).getByText(/Live · updated/)).toBeInTheDocument();
  expect(within(dialog).getByText("Backed up less than an hour ago")).toBeInTheDocument();
});

test("once a backup has succeeded the chip itself shows its age, and its name says it too", async () => {
  show(statusFixture({}, { backup: { configured: true, age_hours: 3, needs_attention: false } }));
  await chipText("Live");
  await chipText("Backed up 3 h ago");
  expect(await chip()).toHaveAccessibleName("Status: Live, Backed up 3 h ago");
});

test("an overdue backup keeps its age on the chip beside the warning", async () => {
  show(statusFixture({}, { backup: { configured: true, age_hours: 100, needs_attention: true } }));
  await chipIs("backup");
  await chipText("Backup needed");
  await chipText("Last backup 4 days ago");
});

test("with no backup yet the chip has no age to show", async () => {
  show(statusFixture({}, { backup: { configured: true, age_hours: null, needs_attention: true } }));
  await chipText("Backup needed");
  expect(chipNow()).not.toHaveTextContent("ago");
});

test("the worst state wins on the chip: backup needed", async () => {
  show(statusFixture({}, { backup: { configured: true, needs_attention: true, age_hours: null } }));
  await chipIs("backup");
  await chipText("Backup needed");
});

test("offline shows as soon as the connection is lost, and Refresh asks for everything again", async () => {
  const user = userEvent.setup();
  const refresh = vi.fn();
  show(statusFixture(), {}, { live: "offline", refresh });
  expect(await chip()).toHaveTextContent("Offline · reconnecting");
  const dialog = await open(user);
  await user.click(within(dialog).getByRole("button", { name: "Refresh" }));
  expect(refresh).toHaveBeenCalledTimes(1);
});

test("Back up now runs the backup, and without one the popover offers to set backups up", async () => {
  const user = userEvent.setup();
  const calls = show(statusFixture({}, {}, ), { "POST backup": () => statusFixture() });
  const dialog = await open(user);
  expect(within(dialog).getByText("No off-device backup")).toBeInTheDocument();
  expect(within(dialog).queryByText(/storage\./)).toBeNull();
  expect(within(dialog).queryByRole("button", { name: "Back up now" })).toBeNull();
  expect(calls.some((c) => c.route === "POST backup")).toBe(false);
});

test("a configured backup has Back up now", async () => {
  const user = userEvent.setup();
  const calls = show(statusFixture({}, { backup: { configured: true, age_hours: 3, needs_attention: false } }), { "POST backup": () => statusFixture() });
  const dialog = await open(user);
  await user.click(within(dialog).getByRole("button", { name: "Back up now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST backup")).toBe(true));
});

test("an unconfigured backup opens the setup guide at the backup step", async () => {
  const user = userEvent.setup();
  const onOpenGuide = vi.fn();
  show(statusFixture(), {}, { onOpenGuide });
  const dialog = await open(user);
  await user.click(within(dialog).getByRole("button", { name: "Set up backups" }));
  await waitFor(() => expect(onOpenGuide).toHaveBeenCalledWith("backup"));
});

test("the spend line shows today's and this month's cost, and says which limit it is near", async () => {
  const user = userEvent.setup();
  show(statusFixture({}, { backup: { configured: true, age_hours: 1 }, spend: { today_usd: 1.7, month_usd: 5, warn: true, warn_today: true } }));
  await chipText("Spend near limit");
  const dialog = await open(user);
  expect(within(dialog).getByText("AI today $1.70 · this month $5.00 · near today's limit")).toBeInTheDocument();
});

test("spend is hidden until a run has cost something", async () => {
  const user = userEvent.setup();
  show(statusFixture());
  const dialog = await open(user);
  expect(within(dialog).queryByText(/AI today/)).toBeNull();
});

test("the restart-needed line has Restart now when this copy can restart itself, and it asks the app", async () => {
  const user = userEvent.setup();
  const calls = show(statusFixture({ restart_needed: "A setting changed.", can_restart: true }), { "POST restart": () => ({ restarting: true }) });
  await chipIs("restart");
  await chipText("Restart to finish");
  const dialog = await open(user);
  expect(within(dialog).getByText(NEEDED, { exact: false })).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
  await waitFor(() => expect(document.body).toHaveTextContent("Restarting to use the new settings…"));
  await chipText("Restarting");
});

test("when this copy can't restart itself, it says to close and start the app again, with no button", async () => {
  const user = userEvent.setup();
  show(statusFixture({ restart_needed: "A setting changed.", can_restart: false }));
  const dialog = await open(user);
  expect(within(dialog).getByText(/Close the app and start it again/)).toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Restart now" })).toBeNull();
});

test("a refusal from Restart now is shown in the popover, and announced", async () => {
  const user = userEvent.setup();
  show(statusFixture({ restart_needed: "A setting changed.", can_restart: true }), { "POST restart": () => new Refuse(409, "Close it and start it again.") });
  const dialog = await open(user);
  await user.click(within(dialog).getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(within(dialog).getByText("Close it and start it again.")).toBeInTheDocument());
  expect(screen.getAllByRole("status", { hidden: true }).some((el) => el.textContent === "Close it and start it again.")).toBe(true);
});

test("nothing about restarting shows when no restart is needed", async () => {
  const user = userEvent.setup();
  show(statusFixture({ restart_needed: null, can_restart: true }));
  const dialog = await open(user);
  expect(within(dialog).queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(within(dialog).queryByText(/restart/i)).toBeNull();
});

const settingItem = (key: string, description: string): S["SettingItem"] => ({
  key,
  file: key.split(".")[0],
  group: key.split(".").slice(0, 2).join("."),
  description,
  type: "integer",
  options: [],
  value: 1,
  default: 1,
  source: "default",
  locked: false,
  basic: true,
  editable: true,
});

test("the restart line names what waits by the labels Settings shows, never the keys", async () => {
  const user = userEvent.setup();
  show(statusFixture({ restart_needed: "A setting changed.", can_restart: true, restart_for: ["ui.toast_seconds"] }), {
    "GET settings": () => ({ fingerprint: "fp", items: [settingItem("ui.toast_seconds", "How long a message stays.")] }),
  });
  const dialog = await open(user);
  expect(await within(dialog).findByText("Restart to use: Seconds a message stays on screen.")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("ui.toast_seconds");
});

function Asker() {
  const restart = useRestart();
  return (
    <button type="button" onClick={restart.offer}>
      Ask about restarting
    </button>
  );
}

test("when a change asks about restarting, the chip says so and the popover holds Restart now and Later", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET status": () => statusFixture({ restart_needed: null, can_restart: true }), "GET runtime-config": () => ({ instance: null }) });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartAnnouncer />
      <Asker />
      <StatusMenu live={{ state: "live", lastUpdate: null, refresh: () => undefined }} demo={false} onOpenGuide={() => undefined} />
    </RestartProvider>,
  );
  expect(await chip()).toHaveAttribute("data-status", "live");
  await user.click(screen.getByRole("button", { name: "Ask about restarting" }));
  await chipIs("restart");
  expect(screen.getAllByRole("status", { hidden: true }).some((el) => /This change needs the app to restart/.test(el.textContent ?? ""))).toBe(true);
  const dialog = await open(user);
  expect(within(dialog).getAllByRole("button", { name: "Restart now" })).toHaveLength(1);
  await user.click(within(dialog).getByRole("button", { name: "Later" }));
  await chipIs("live");
});

test("an assistant with no account says so and what to do, with a button, and no command line", async () => {
  const user = userEvent.setup();
  const onOpenGuide = vi.fn();
  show(statusFixture({}, { ai: { state: "not_set_up", detail: null } }), {}, { onOpenGuide });
  const dialog = await open(user);
  expect(within(dialog).getByText("The assistant isn't set up yet")).toBeInTheDocument();
  expect(dialog).not.toHaveTextContent(/cockpit /);
  await user.click(within(dialog).getByRole("button", { name: "Open the AI step" }));
  await waitFor(() => expect(onOpenGuide).toHaveBeenCalledWith("ai"));
});

test("the stand-in assistant is a line in the popover, not a banner", async () => {
  const user = userEvent.setup();
  show(statusFixture({}, { ai: { state: "stand_in", detail: null } }));
  const dialog = await open(user);
  expect(within(dialog).getByText("The assistant is a stand-in for trying the app")).toBeInTheDocument();
  expect(dialog).not.toHaveTextContent(/cockpit /);
});

test("a failing account shows the provider's own reason", async () => {
  const user = userEvent.setup();
  show(statusFixture({}, { ai: { state: "failing", detail: "auth: User not found" } }));
  const dialog = await open(user);
  expect(within(dialog).getByText("The assistant can't use its AI account")).toBeInTheDocument();
  expect(within(dialog).getByText("The account said: auth: User not found")).toBeInTheDocument();
});

test("nothing about the assistant shows when it is working", async () => {
  const user = userEvent.setup();
  show(statusFixture());
  const dialog = await open(user);
  expect(dialog.querySelector('[data-state="assistant"]')).toBeNull();
});

test("a demo workspace says so in the popover, with the sentence", async () => {
  const user = userEvent.setup();
  show(statusFixture(), {}, { demo: true });
  const dialog = await open(user);
  expect(within(dialog).getByText("Everything here is made up. Nothing you do here reaches anyone.")).toBeInTheDocument();
});
