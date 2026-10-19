import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { SyncPanel } from "./SyncPanel";

const syncView = (extra: Partial<S["SyncView"]> = {}): S["SyncView"] => ({
  folder: "/shared/Cockpit",
  problem: null,
  stopped: false,
  changed_outside: [],
  removed_outside: [],
  rebuilt: [],
  outside_edits: [],
  conflict_copies: [],
  shared: false,
  handover: null,
  ...extra,
});

const folderItem = (value: string): S["SettingItem"] => ({
  key: "storage.sync.folder",
  file: "storage",
  group: "storage.sync",
  description: "Where the synced folder is.",
  type: "text",
  options: [],
  value,
  default: "",
  source: "default",
  locked: false,
  basic: true,
  editable: true,
  picker: "folder",
});

const languageItem = (): S["SettingItem"] => ({
  key: "workspace.language",
  file: "workspace",
  group: "workspace",
  description: "The language and variety work is written in.",
  type: "choice",
  options: ["en-US", "en-GB", "en-AU", "fr-CA"],
  choices: "languages",
  value: "en-US",
  default: "en-US",
  source: "default",
  locked: false,
  basic: true,
  editable: true,
});

function others(routes: Routes, folder = "/shared/Cockpit") {
  return fakeApi({
    "GET settings": () => ({ fingerprint: "fp-1", items: [folderItem(folder), languageItem()] }),
    ...routes,
  });
}

async function section(name: string) {
  return (await screen.findByRole("region", { name })) as HTMLElement;
}

test("with no synced folder it says what one is for and offers to choose, without asking for the sync status", async () => {
  const calls = others({ "GET jobs": () => [] }, "");
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  expect(await within(sync).findByText(/Keep a readable copy of your work/)).toBeInTheDocument();
  expect(within(sync).getByRole("button", { name: "Choose a folder" })).toBeInTheDocument();
  expect(within(sync).queryByText(/status didn't load/)).toBeNull();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(calls.some((c) => c.route === "GET sync")).toBe(false);
});

test("choosing a folder saves it as the synced folder setting and asks before restarting", async () => {
  const user = userEvent.setup();
  const calls = others(
    {
      "GET jobs": () => [],
      "GET setup/folders": () => ({ path: "/home/me", parent: "/home", folders: [] }),
      "POST settings": () => ({
        changes: [{ key: "storage.sync.folder", before: "", after: "/home/me", was_default: true, is_default: false }],
        fingerprint: "fp-2",
        needs_restart: true,
      }),
    },
    "",
  );
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <SyncPanel />
    </RestartProvider>,
  );
  const sync = await section("Synced folder");
  await user.click(await within(sync).findByRole("button", { name: "Choose a folder" }));
  await user.click(await screen.findByRole("button", { name: "Use this folder" }));
  // The folder isn't saved until the person says whether anyone else can change it.
  expect(calls.some((c) => c.route === "POST settings")).toBe(false);
  expect(within(sync).getByText("Folder: /home/me")).toBeInTheDocument();
  expect(within(sync).getByRole("button", { name: "Save the folder" })).toBeDisabled();
  await user.click(within(sync).getByRole("radio", { name: "No, only I use it" }));
  await user.click(within(sync).getByRole("button", { name: "Save the folder" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
  expect(calls.find((c) => c.route === "POST settings")!.body).toEqual({
    changes: { "storage.sync.folder": "/home/me", "storage.sync.shared": false },
    reset: [],
    fingerprint: "fp-1",
  });
  const live = screen.getAllByRole("status").find((el) => el.classList.contains("restart-slot"))!;
  await waitFor(() => expect(live).toHaveTextContent("Restart to finish this change?"));
  expect(within(live).getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  expect(live).not.toHaveTextContent("Restarting");
});

test("where folders can't be listed, the synced folder can be typed", async () => {
  const user = userEvent.setup();
  const calls = others(
    {
      "GET jobs": () => [],
      "GET setup/folders": () => new Refuse(403, "no"),
      "POST settings": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
    },
    "",
  );
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  await user.type(await within(sync).findByLabelText("Folder"), "/mnt/shared");
  await user.click(within(sync).getByRole("button", { name: "Use this folder" }));
  await user.click(await within(sync).findByRole("radio", { name: "Yes, someone else can" }));
  await user.click(within(sync).getByRole("button", { name: "Save the folder" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
  expect(calls.find((c) => c.route === "POST settings")!.body).toMatchObject({
    changes: { "storage.sync.folder": "/mnt/shared", "storage.sync.shared": true },
  });
  expect(within(sync).queryByRole("alert")).toBeNull();
});

test("the synced folder shows its path, why it can't write, that this copy stopped, and what changed outside", async () => {
  others({
    "GET sync": () =>
      syncView({
        problem: "the folder is read-only",
        stopped: true,
        changed_outside: ["a.md", "b.md"],
        removed_outside: ["c.md"],
      }),
    "GET jobs": () => [],
  });
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  expect(await within(sync).findByText("Kept in /shared/Cockpit")).toBeInTheDocument();
  const alerts = within(sync).getAllByRole("alert").map((a) => a.textContent);
  expect(alerts).toContain("Another computer opened this workspace, so this copy has stopped writing to the folder.");
  expect(alerts).toContain("It can't write to the folder right now: the folder is read-only");
  expect(within(sync).getByText("2 files were changed outside the app.")).toBeInTheDocument();
  expect(within(sync).getByText("1 file was removed outside the app.")).toBeInTheDocument();
  expect(within(sync).queryByText("Edits made outside the app")).toBeNull();
});

test("an outside edit that became a version can be reviewed; one that failed shows why; the rest wait in What changed", async () => {
  const user = userEvent.setup();
  others({
    "GET sync": () =>
      syncView({
        outside_edits: [
          { path: "book/chapter-1.md", version: "V-1", proposal: null, problem: null },
          { path: "book/chapter-2.md", version: null, proposal: null, problem: "It isn't a file the app can read back." },
          { path: "book/people.yaml", version: null, proposal: "CS-1", problem: null },
        ],
        conflict_copies: ["book/chapter-1 (conflicted copy).md"],
      }),
    "GET jobs": () => [],
    "GET text-versions/V-1/review": () => ({
      version: {
        id: "V-1",
        number: 2,
        version: 3,
        status: "pending",
        source: "edit",
        words: 1,
        base: null,
        note: null,
        created_at: "2026-10-09T14:00:00Z",
        questions: [],
        unmapped: [],
      },
      current: 1,
      three_way: false,
      regions: [],
      pending_text: "",
    }),
  });
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  const rows = (await within(sync).findAllByRole("listitem")).filter((li) => li.classList.contains("line"));
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getByText("book/chapter-1.md")).toBeInTheDocument();
  expect(within(rows[1]).getByText("It isn't a file the app can read back.")).toBeInTheDocument();
  expect(within(rows[1]).queryByRole("button")).toBeNull();
  expect(within(rows[2]).getByText("Waiting for you in What changed.")).toBeInTheDocument();
  expect(within(rows[2]).queryByRole("button")).toBeNull();
  expect(within(sync).getByText("book/chapter-1 (conflicted copy).md")).toBeInTheDocument();
  expect(within(sync).getByText(/These copies weren't imported/)).toBeInTheDocument();
  await user.click(within(rows[0]).getByRole("button", { name: "Review: book/chapter-1.md" }));
  expect(await screen.findByRole("dialog", { name: "Review the changes" })).toBeInTheDocument();
});

test("whether others can change the folder is shown, switched with a save that needs no restart, and shared edits say so", async () => {
  const user = userEvent.setup();
  let shared = false;
  const calls = others({
    "GET sync": () => syncView({ shared, outside_edits: [{ path: "book/chapter-1.md", version: "V-1", proposal: null, problem: null }] }),
    "GET jobs": () => [],
    "POST settings": (body) => {
      shared = (body as { changes: Record<string, boolean> }).changes["storage.sync.shared"];
      return { changes: [{ key: "storage.sync.shared", before: false, after: true, was_default: true, is_default: false }], fingerprint: "fp-2", needs_restart: false };
    },
  });
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  const box = await within(sync).findByRole("checkbox", { name: "Mark this folder as editable by others" });
  expect(box).not.toBeChecked();
  expect(within(sync).queryByText(/arrive as outside content to check/)).toBeNull();
  expect(within(sync).queryByText(/these may be someone else's changes/)).toBeNull();
  await user.click(box);
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")!.body).toMatchObject({ changes: { "storage.sync.shared": true } }));
  expect(await within(sync).findByText(/You'll review changes from this folder as information/)).toBeInTheDocument();
  expect(within(sync).getByText("The folder is shared, so these may be someone else's changes.")).toBeInTheDocument();
});

test("when the copies need settling the folder panel links to the page that settles it", async () => {
  others({ "GET sync": () => syncView({ handover: "diverged" }), "GET jobs": () => [] });
  renderApp(<SyncPanel />);
  const sync = await section("Synced folder");
  const link = await within(sync).findByRole("link", { name: "Choose which copy to keep" });
  expect(link.getAttribute("href")).toMatch(/#handover$/);
});

