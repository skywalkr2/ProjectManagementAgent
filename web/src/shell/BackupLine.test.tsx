import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { BackupLine } from "./BackupLine";

function show(backup: Partial<S["BackupStatus"]>, routes: Record<string, (body: unknown) => unknown> = {}) {
  const calls = fakeApi({ "GET status": () => statusFixture({}, { backup }), ...routes });
  const onOpenGuide = vi.fn();
  renderApp(<BackupLine onOpenGuide={onOpenGuide} />);
  return { calls, onOpenGuide };
}

test("with no backup folder it says so, starting with what to do, and opens the setup step", async () => {
  const user = userEvent.setup();
  const { onOpenGuide } = show({ configured: false, needs_attention: true });
  const line = await screen.findByRole("region", { name: "Backup" });
  expect(line).toHaveTextContent("Choose a backup folder. No off-device backup is set up.");
  await user.click(screen.getByRole("button", { name: "Set up backups" }));
  expect(onOpenGuide).toHaveBeenCalledWith("backup");
});

test("with a folder but no backup yet it says so and offers Back up now", async () => {
  const user = userEvent.setup();
  const { calls } = show({ configured: true, needs_attention: true }, { "POST backup": () => statusFixture() });
  const line = await screen.findByRole("region", { name: "Backup" });
  expect(line).toHaveTextContent("Back up now. No backup has succeeded yet.");
  await user.click(screen.getByRole("button", { name: "Back up now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST backup")).toBe(true));
});

test("a failed backup and an overdue one are each said in words", async () => {
  show({ configured: true, needs_attention: true, last_error: "The folder is not there." });
  expect(await screen.findByRole("region", { name: "Backup" })).toHaveTextContent("Back up now. The last backup failed.");
});

test("an overdue backup says how long ago the last one was", async () => {
  show({ configured: true, needs_attention: true, age_hours: 100 });
  expect(await screen.findByRole("region", { name: "Backup" })).toHaveTextContent("Back up now. The last backup was 4 days ago.");
});

test("it is gone while a backup is current", async () => {
  const calls = show({ configured: true, needs_attention: false, age_hours: 2 }).calls;
  await waitFor(() => expect(calls.some((c) => c.route === "GET status")).toBe(true));
  expect(screen.queryByRole("region", { name: "Backup" })).toBeNull();
});
