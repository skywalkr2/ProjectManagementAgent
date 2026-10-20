import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, statusFixture } from "../test-utils";
import { joinPath } from "./FolderPicker";
import { WelcomeBackup } from "./WelcomeBackup";

const enc = encodeURIComponent;
const TARGETS = {
  key: "storage.backups.targets",
  file: "storage",
  group: "storage.backups",
  description: "Where full backups go.",
  type: "other",
  options: [],
  value: [{ path: "/mnt/first", label: "Old drive" }],
  default: [],
  source: "file",
  locked: false,
  basic: false,
  editable: false,
};

function api(extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET settings": () => ({ fingerprint: "fp-1", items: [TARGETS] }),
    ...extra,
  });
}

const open = (local = true) => renderApp(<WelcomeBackup local={local} />);

type User = ReturnType<typeof userEvent.setup>;
/** The folder box: with a folder already chosen it is behind "Choose another folder…". */
async function folderBox(user: User) {
  const other = (await screen.findByRole("radio", { name: /Choose another folder/ })) as HTMLInputElement;
  if (!other.checked) await user.click(other);
  return screen.findByLabelText("Folder");
}

test("Check says in words whether the folder will do, and how much room it has", async () => {
  const user = userEvent.setup();
  api({
    [`GET setup/folder-check?path=${enc("/mnt/good")}`]: () => ({ path: "/mnt/good", ok: true, problem: null, free_mb: 12288 }),
    [`GET setup/folder-check?path=${enc("/mnt/bad")}`]: () => ({ path: "/mnt/bad", ok: false, problem: "It is inside the workspace.", free_mb: null }),
  });
  open();
  await user.type(await folderBox(user), "/mnt/good");
  await user.click(screen.getByRole("button", { name: "Check" }));
  expect(await screen.findByText("That folder works. 12.0 GB free.")).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Folder"));
  expect(screen.queryByText(/That folder works/)).toBeNull();
  await user.type(screen.getByLabelText("Folder"), "/mnt/bad");
  await user.click(screen.getByRole("button", { name: "Check" }));
  expect(await screen.findByText("That folder won't work: It is inside the workspace.")).toBeInTheDocument();
});

test("the folders backups already go to are listed", async () => {
  api();
  open();
  expect(await screen.findByText("Old drive: /mnt/first")).toBeInTheDocument();
});

test("Save sends the path, the name and the fingerprint, and says where backups will go", async () => {
  const user = userEvent.setup();
  const calls = api({ "POST setup/backup-folder": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }) });
  open();
  await user.type(await folderBox(user), "/mnt/new");
  await user.type(screen.getByLabelText("Name for this folder (optional)"), "Cloud drive");
  await user.click(screen.getByRole("button", { name: "Back up now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup-folder")).toBe(true));
  expect(calls.find((c) => c.route === "POST setup/backup-folder")!.body).toEqual({
    path: "/mnt/new",
    label: "Cloud drive",
    fingerprint: "fp-1",
  });
  expect(await screen.findByText("Backups will go to /mnt/new.")).toBeInTheDocument();
  // The folder is saved and the raw box goes away again.
  await waitFor(() => expect(screen.queryByLabelText("Folder")).toBeNull());
});

test("a refused folder shows the server's words and keeps what was typed", async () => {
  const user = userEvent.setup();
  api({ "POST setup/backup-folder": () => new Refuse(409, "Backups already go to that folder.") });
  open();
  await user.type(await folderBox(user), "/mnt/first");
  await user.click(screen.getByRole("button", { name: "Back up now" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Backups already go to that folder.");
  expect(screen.getByLabelText("Folder")).toHaveValue("/mnt/first");
});

test("an app that is not on this computer has no folder list to choose from", async () => {
  const user = userEvent.setup();
  api();
  open(false);
  await folderBox(user);
  expect(screen.queryByRole("button", { name: "Choose…" })).toBeNull();
});

test("choosing a folder: open folders, go up, use the one shown, and it is checked", async () => {
  const user = userEvent.setup();
  const calls = api({
    "GET setup/folders": () => ({ path: "/home/me", parent: "/home", folders: ["Documents", "Drive"] }),
    [`GET setup/folders?path=${enc("/home/me/Drive")}`]: () => ({ path: "/home/me/Drive", parent: "/home/me", folders: ["Backups"] }),
    [`GET setup/folders?path=${enc("/home/me")}`]: () => ({ path: "/home/me", parent: "/home", folders: ["Documents", "Drive"] }),
    [`GET setup/folders?path=${enc("/home/me/Drive/Backups")}`]: () => ({ path: "/home/me/Drive/Backups", parent: "/home/me/Drive", folders: [] }),
    [`GET setup/folder-check?path=${enc("/home/me/Drive/Backups")}`]: () => ({ path: "/home/me/Drive/Backups", ok: true, problem: null, free_mb: 500 }),
  });
  open();
  await folderBox(user);
  const choose = await screen.findByRole("button", { name: "Choose…" });
  await user.click(choose);
  const dialog = await screen.findByRole("dialog", { name: "Choose a folder" });
  expect(await within(dialog).findByText("You are in /home/me")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Drive" }));
  const here = await within(dialog).findByText("You are in /home/me/Drive");
  await waitFor(() => expect(here).toHaveFocus());
  await user.click(within(dialog).getByRole("button", { name: "Go up one folder" }));
  expect(await within(dialog).findByText("You are in /home/me")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Drive" }));
  await user.click(await within(dialog).findByRole("button", { name: "Backups" }));
  expect(await within(dialog).findByText("There are no folders here.")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Use this folder" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByLabelText("Folder")).toHaveValue("/home/me/Drive/Backups");
  expect(await screen.findByText("That folder works. 500 MB free.")).toBeInTheDocument();
  await waitFor(() => expect(choose).toHaveFocus());
  expect(calls.filter((c) => c.route.startsWith("GET setup/folders?path=")).map((c) => c.route.split("=")[1])).toEqual(
    ["/home/me/Drive", "/home/me", "/home/me/Drive", "/home/me/Drive/Backups"].map(enc),
  );
});

test("a folder that did not check out is not where the list starts", async () => {
  const user = userEvent.setup();
  api({
    [`GET setup/folder-check?path=${enc("/nowhere")}`]: () => ({ path: "/nowhere", ok: false, problem: "No such folder.", free_mb: null }),
    [`GET setup/folders?path=${enc("/nowhere")}`]: () => new Refuse(400, "That folder doesn't exist."),
    "GET setup/folders": () => ({ path: "/home/me", parent: null, folders: [] }),
  });
  open();
  await user.type(await folderBox(user), "/nowhere");
  await user.click(screen.getByRole("button", { name: "Choose…" }));
  // A folder that isn't a good one is not where the list starts.
  expect(await screen.findByText("You are in /home/me")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Go up one folder" })).toBeDisabled();
});

test("when a folder can't be listed the reason shows, and Start from the beginning recovers", async () => {
  const user = userEvent.setup();
  api({
    [`GET setup/folder-check?path=${enc("/gone")}`]: () => ({ path: "/gone", ok: true, problem: null, free_mb: 10 }),
    [`GET setup/folders?path=${enc("/gone")}`]: () => new Refuse(400, "That folder doesn't exist."),
    "GET setup/folders": () => ({ path: "/home/me", parent: null, folders: [] }),
  });
  open();
  await user.type(await folderBox(user), "/gone");
  await user.click(screen.getByRole("button", { name: "Check" }));
  await screen.findByText(/That folder works/);
  await user.click(screen.getByRole("button", { name: "Choose…" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That folder doesn't exist.");
  await user.click(screen.getByRole("button", { name: "Start from the beginning" }));
  expect(await screen.findByText("You are in /home/me")).toBeInTheDocument();
});

test("folder addresses are joined with the separator the address already uses", () => {
  expect(joinPath("/a/b", "c")).toBe("/a/b/c");
  expect(joinPath("/", "c")).toBe("/c");
  expect(joinPath("C:\\Users", "me")).toBe("C:\\Users\\me");
  expect(joinPath("C:\\", "me")).toBe("C:\\me");
});

describe("the first backup", () => {
  const statusWith = (backup: Partial<S["BackupStatus"]>) => ({
    "GET status": () => statusFixture({}, { backup: { configured: true, ...backup } }),
  });

  test("while the first backup is being made the screen says so, and it asks for nothing", async () => {
    api(statusWith({}));
    open();
    expect(await screen.findByText("Making the first backup…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("once it is made the screen says: First backup made", async () => {
    api(statusWith({ last_success: "2026-10-12T10:00:00Z", age_hours: 0.1 }));
    open();
    expect(await screen.findByText("First backup made.")).toBeInTheDocument();
  });

  test("a first backup that failed shows why, in words, as an alert", async () => {
    api(statusWith({ last_error: "The drive isn't connected." }));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("The first backup didn't work: The drive isn't connected.");
  });

  test("with no folder chosen there is no backup line", async () => {
    api({ "GET settings": () => ({ fingerprint: "fp-1", items: [] }), "GET status": () => statusFixture() });
    open();
    await screen.findByLabelText("Folder");
    expect(document.querySelector("[data-first-backup]")).toBeNull();
  });
});

describe("the cloud drives found on this computer", () => {
  const NONE = { "GET settings": () => ({ fingerprint: "fp-1", items: [] }) };
  const drives = (...names: string[]) => ({
    "GET setup/backup-folders": () => ({ folders: names.map((name, n) => ({ name, recommended: n === 0 })), shown: "Backups › Example App" }),
  });

  test("they are offered by name with the path as plain names, the first recommended, and nothing raw", async () => {
    api({ ...NONE, ...drives("Drive One", "Drive Two") });
    open();
    const first = await screen.findByRole("radio", { name: /Drive One/ });
    expect(first).toBeChecked();
    expect(first.closest("label")).toHaveTextContent("Backups › Example App");
    expect(first.closest("label")).toHaveTextContent("Recommended");
    const second = screen.getByRole("radio", { name: /Drive Two/ });
    expect(second).not.toBeChecked();
    expect(second.closest("label")).not.toHaveTextContent("Recommended");
    expect(screen.getByRole("radio", { name: /Choose another folder/ }).closest("label")).toHaveTextContent("a USB drive or a network folder");
    // The raw folder box and its buttons wait behind "Choose another folder".
    expect(screen.queryByLabelText("Folder")).toBeNull();
    expect(screen.queryByRole("button", { name: "Choose…" })).toBeNull();
  });

  test("Back up now makes the drive's folder, saves it and says where backups will go", async () => {
    const user = userEvent.setup();
    const calls = api({
      ...NONE,
      ...drives("Drive One", "Drive Two"),
      "POST setup/backup-folder/cloud": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
    });
    open();
    await user.click(await screen.findByRole("radio", { name: /Drive Two/ }));
    await user.click(screen.getByRole("button", { name: "Back up now" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup-folder/cloud")).toBe(true));
    expect(calls.find((c) => c.route === "POST setup/backup-folder/cloud")!.body).toEqual({ name: "Drive Two", fingerprint: "fp-1" });
    expect(calls.some((c) => c.route === "POST setup/backup-folder")).toBe(false);
    expect(await screen.findByText("Backups will go to Drive Two.")).toBeInTheDocument();
  });

  test("another folder shows the raw box and sends the path, never the drive route", async () => {
    const user = userEvent.setup();
    const calls = api({ ...NONE, ...drives("Drive One"), "POST setup/backup-folder": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }) });
    open();
    await user.click(await screen.findByRole("radio", { name: /Choose another folder/ }));
    expect(screen.getByRole("button", { name: "Back up now" })).toBeDisabled();
    expect(screen.getByText("Choose a folder to go on.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Folder"), "/mnt/usb");
    await user.click(screen.getByRole("button", { name: "Back up now" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup-folder")).toBe(true));
    expect(calls.some((c) => c.route === "POST setup/backup-folder/cloud")).toBe(false);
  });

  test("with none found it says so and asks for a folder", async () => {
    api({ ...NONE, ...drives() });
    open();
    expect(await screen.findByText(/We didn't find a cloud drive folder on this computer/)).toBeInTheDocument();
    expect(screen.getByLabelText("Folder")).toBeInTheDocument();
  });

  test("a refused drive shows the server's words", async () => {
    const user = userEvent.setup();
    api({ ...NONE, ...drives("Drive One"), "POST setup/backup-folder/cloud": () => new Refuse(400, "That drive isn't on this computer. Choose another folder.") });
    open();
    await screen.findByRole("radio", { name: /Drive One/ });
    await user.click(screen.getByRole("button", { name: "Back up now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That drive isn't on this computer.");
  });
});
