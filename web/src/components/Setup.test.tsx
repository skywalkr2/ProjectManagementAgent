import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { Setup } from "./Setup";

const project = (id: string, name: string): S["ProjectView"] => ({
  id,
  name,
  group: null,
  status: null,
  phase: null,
  target: null,
  owner: null,
  owner_name: null,
  summary: null,
  language: "en-US",
  language_own: false,
  role: "run",
  spent_usd: 0,
  open_actions: 0,
  open_questions: 0,
});
const note = (id: string, text: string, p: S["ProjectView"] | null): S["NoteView"] => ({
  id,
  text,
  project: p?.id ?? null,
  project_name: p?.name ?? null,
  created_at: "2026-10-09T14:00:00Z",
  trust: "trusted",
});

const first = project("PRJ-1", "First project");
const second = project("PRJ-2", "Second project");

function api(notes: S["NoteView"][]) {
  fakeApi({
    "GET people": () => [],
    "GET projects": () => [first, second],
    "GET notes": () => notes,
  });
}

test("a project's menu shows its notes, newest first, and counts them", async () => {
  const user = userEvent.setup();
  api([note("N-3", "newer note", first), note("N-2", "other project", second), note("N-1", "older note", first)]);
  renderApp(<Setup />);
  const row = (await screen.findByText(first.name)).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Notes (2)" }));
  const items = within(row).getAllByRole("listitem").map((li) => li.textContent);
  expect(items[0]).toContain("newer note");
  expect(items[1]).toContain("older note");
  expect(items.join(" ")).not.toContain("other project");
});

test("a project with no notes says so", async () => {
  const user = userEvent.setup();
  api([]);
  renderApp(<Setup />);
  const row = (await screen.findByText(second.name)).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Notes (0)" }));
  expect(within(row).getByText("No notes are filed under this project yet.")).toBeInTheDocument();
});

test("notes with no project are grouped at the end", async () => {
  api([note("N-1", "loose thought", null)]);
  renderApp(<Setup />);
  const group = (await screen.findByRole("heading", { name: "Notes not filed under a project" })).closest("section")!;
  expect(within(group).getByText("loose thought")).toBeInTheDocument();
});

test("the group is absent when every note is filed under a project", async () => {
  api([note("N-1", "filed", first)]);
  renderApp(<Setup />);
  await screen.findByText(first.name);
  expect(screen.queryByRole("heading", { name: "Notes not filed under a project" })).not.toBeInTheDocument();
});

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
    "GET people": () => [],
    "GET organizations": () => [],
    "GET projects": () => [],
    "GET notes": () => [],
    "GET settings": () => ({ fingerprint: "fp-1", items: [folderItem(folder), languageItem()] }),
    ...routes,
  });
}

async function section(name: string) {
  return (await screen.findByRole("region", { name })) as HTMLElement;
}

test("with no synced folder it says what one is for and offers to choose, without asking for the sync status", async () => {
  const calls = others({ "GET jobs": () => [] }, "");
  renderApp(<Setup />);
  const sync = await section("Synced folder");
  expect(await within(sync).findByText(/A synced folder keeps a readable copy/)).toBeInTheDocument();
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
      <Setup />
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
  await waitFor(() => expect(live).toHaveTextContent("This change needs the app to restart."));
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
  renderApp(<Setup />);
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
  renderApp(<Setup />);
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
  renderApp(<Setup />);
  const sync = await section("Synced folder");
  const rows = (await within(sync).findAllByRole("listitem")).filter((li) => li.classList.contains("line"));
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getByText("book/chapter-1.md")).toBeInTheDocument();
  expect(within(rows[1]).getByText("It isn't a file the app can read back.")).toBeInTheDocument();
  expect(within(rows[1]).queryByRole("button")).toBeNull();
  expect(within(rows[2]).getByText("Waiting for you in What changed.")).toBeInTheDocument();
  expect(within(rows[2]).queryByRole("button")).toBeNull();
  expect(within(sync).getByText("book/chapter-1 (conflicted copy).md")).toBeInTheDocument();
  expect(within(sync).getByText(/These copies were not loaded/)).toBeInTheDocument();
  await user.click(within(rows[0]).getByRole("button", { name: "Review: book/chapter-1.md" }));
  expect(await screen.findByRole("dialog", { name: "Review the changes" })).toBeInTheDocument();
});

test("after choosing a folder the question about sharing comes first, can be gone back from, and saves nothing by itself", async () => {
  const user = userEvent.setup();
  const calls = others({ "GET jobs": () => [], "GET setup/folders": () => new Refuse(403, "no") }, "");
  renderApp(<Setup />);
  const sync = await section("Synced folder");
  await user.type(await within(sync).findByLabelText("Folder"), "/mnt/team");
  await user.click(within(sync).getByRole("button", { name: "Use this folder" }));
  const first = await within(sync).findByRole("radio", { name: "No, only I use it" });
  expect(first).toHaveFocus(); // the cursor starts in the first field of the step
  expect(first).not.toBeChecked();
  expect(within(sync).getByRole("radio", { name: "Yes, someone else can" })).not.toBeChecked();
  expect(within(sync).getByText(/never taken as your own words/)).toBeInTheDocument();
  await user.click(within(sync).getByRole("button", { name: "Choose another folder" }));
  expect(await within(sync).findByLabelText("Folder")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST settings")).toBe(false);
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
  renderApp(<Setup />);
  const sync = await section("Synced folder");
  const box = await within(sync).findByRole("checkbox", { name: "Others can change this folder" });
  expect(box).not.toBeChecked();
  expect(within(sync).queryByText(/arrive as outside content to check/)).toBeNull();
  expect(within(sync).queryByText(/these may be someone else's changes/)).toBeNull();
  await user.click(box);
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")!.body).toMatchObject({ changes: { "storage.sync.shared": true } }));
  expect(await within(sync).findByText(/arrive as outside content to check, not as your own words/)).toBeInTheDocument();
  expect(within(sync).getByText("The folder is shared, so these may be someone else's changes.")).toBeInTheDocument();
});

test("when the copies need settling the folder panel links to the page that settles it", async () => {
  others({ "GET sync": () => syncView({ handover: "diverged" }), "GET jobs": () => [] });
  renderApp(<Setup />);
  const sync = await section("Synced folder");
  const link = await within(sync).findByRole("link", { name: "Choose which copy to keep" });
  expect(link.getAttribute("href")).toMatch(/#handover$/);
});

test("scheduled work is one row per job with how often, on or off in words, and the last run", async () => {
  others({
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [
      { name: "demo/refresh-feeds", plugin: "demo", enabled: true, every_minutes: 60, last_run_at: "2026-10-09T14:00:00Z", last_outcome: "ok", last_error: null },
      { name: "demo/sweep_old-items", plugin: "demo", enabled: false, every_minutes: 1, last_run_at: "2026-10-09T15:30:00Z", last_outcome: "failed", last_error: "The source didn't answer." },
      { name: "demo/never-ran", plugin: "demo", enabled: true, every_minutes: 15, last_run_at: null, last_outcome: null, last_error: null },
    ],
  });
  renderApp(<Setup />);
  const jobs = await section("Scheduled work");
  const rows = within(jobs).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Refresh feeds");
  expect(rows[0]).toHaveTextContent("On");
  expect(rows[0]).toHaveTextContent("every 60 minutes");
  expect(rows[0]).toHaveTextContent(/Last ran .*: it worked/);
  expect(rows[1]).toHaveTextContent("Sweep old items");
  expect(rows[1]).toHaveTextContent("Off");
  expect(rows[1]).toHaveTextContent("every minute");
  expect(rows[1]).toHaveTextContent(/it failed/);
  expect(rows[1]).toHaveTextContent("The source didn't answer.");
  expect(rows[2]).toHaveTextContent("Hasn't run yet");
  expect(within(jobs).queryByRole("button")).toBeNull();
});

test("the scheduled work section is hidden when there are no jobs", async () => {
  const calls = others({ "GET sync": () => syncView({ folder: "" }), "GET jobs": () => [] });
  renderApp(<Setup />);
  await section("Synced folder");
  await waitFor(() => expect(calls.some((c) => c.route === "GET jobs")).toBe(true));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("region", { name: "Scheduled work" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "Scheduled work" })).toBeNull();
});

const withDetails = (id: string, name: string, extra: Partial<S["ProjectView"]> = {}): S["ProjectView"] => ({
  ...project(id, name),
  ...extra,
});

test("a project's row states where it sits, its own language and its budget as plain facts", async () => {
  others({
    "GET projects": () => [
      withDetails("PRJ-1", "The series"),
      withDetails("PRJ-2", "Book one", { parent: "PRJ-1", language: "en-GB", language_own: true, budget_usd: 250 }),
      withDetails("PRJ-3", "Book two", { parent: "PRJ-1", language: "en-US", language_own: false }),
    ],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
  });
  renderApp(<Setup />);
  const one = (await screen.findByText("Book one")).closest("li")!;
  expect(one).toHaveTextContent("inside The series");
  expect(one).toHaveTextContent("language en-GB");
  expect(one).toHaveTextContent("budget $250.00");
  const two = screen.getByText("Book two").closest("li")!;
  expect(two).toHaveTextContent("inside The series");
  expect(two).not.toHaveTextContent("language");
  expect(two).not.toHaveTextContent("budget");
  expect(screen.getByText("The series").closest("li")).not.toHaveTextContent("inside");
});

test("the project form offers Inside (never itself), Language with the inherited one as a hint, and a budget; they are saved", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET projects": () => [
      withDetails("PRJ-1", "The series", { language: "en-GB", language_own: true }),
      withDetails("PRJ-2", "Book one", { parent: "PRJ-1", language: "en-GB", language_own: false }),
    ],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects/PRJ-2": () => ({ ok: "PRJ-2" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Book one")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const inside = within(row).getByRole("combobox", { name: "Inside" });
  expect(within(inside).getAllByRole("option").map((o) => o.textContent)).toEqual(["None", "The series"]);
  expect(inside).toHaveValue("PRJ-1");
  const language = within(row).getByRole("combobox", { name: /spells and writes/ });
  expect(language).toHaveValue("");
  const labels = within(language).getAllByRole("option").map((o) => o.textContent);
  expect(labels[0]).toBe("Same as English (United Kingdom)");
  expect(labels.slice(1)).toEqual(["English (Australia)", "English (United Kingdom)", "English (United States)", "French (Canada)"]);
  expect(within(row).getByText("(inherited; pick one to set its own)")).toBeInTheDocument();
  const budget = within(row).getByRole("spinbutton", { name: /Budget \(USD\)/ });
  expect(budget).toHaveValue(null);
  await user.selectOptions(language, "en-AU");
  await user.type(budget, "120.5");
  await user.selectOptions(inside, "");
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-2")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-2")?.body).toMatchObject({ parent: null, language: "en-AU", budget_usd: 120.5 });
});

test("a project with no project around it names the workspace as what an empty language follows", async () => {
  const user = userEvent.setup();
  others({ "GET projects": () => [], "GET sync": () => syncView({ folder: "" }), "GET jobs": () => [] });
  renderApp(<Setup />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  const language = await screen.findByRole("combobox", { name: /spells and writes/ });
  expect(within(language).getAllByRole("option")[0]).toHaveTextContent("Same as the workspace");
});

test("a project's own language that isn't on the list is still shown, never replaced by another", async () => {
  const user = userEvent.setup();
  others({
    "GET projects": () => [withDetails("PRJ-1", "The series", { language: "tlh", language_own: true })],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("The series")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  expect(within(row).getByRole("combobox", { name: /spells and writes/ })).toHaveValue("tlh");
});

test("a project's row says when the person only watches it, and the form's Your role list changes it with Undo", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET projects": () => [withDetails("PRJ-1", "Watched one", { role: "watch" }), withDetails("PRJ-2", "Run one")],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
    "POST projects/PRJ-1/role": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: ["PRJ-1"], skipped: [] }),
  });
  renderApp(<Setup />);
  const watched = (await screen.findByText("Watched one")).closest("li")!;
  expect(watched).toHaveTextContent("you only watch it");
  expect(screen.getByText("Run one").closest("li")).not.toHaveTextContent("you ");
  await user.click(within(watched).getByRole("button", { name: "Edit" }));
  const role = within(watched).getByRole("combobox", { name: /Your role/ });
  expect(within(role).getAllByRole("option").map((o) => o.textContent)).toEqual(["Run it", "Design for it", "Only watch it"]);
  expect(role).toHaveValue("watch");
  await user.selectOptions(role, "run");
  await user.click(within(watched).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1/role")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1/role")?.body).toEqual({ role: "run" });
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("a project that is being added has no role to pick", async () => {
  const user = userEvent.setup();
  others({ "GET projects": () => [], "GET sync": () => syncView({ folder: "" }), "GET jobs": () => [] });
  renderApp(<Setup />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  expect(screen.queryByRole("combobox", { name: /Your role/ })).toBeNull();
});

test("choosing Same as for the language and clearing the budget send nothing, so the project inherits and has no cap", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET projects": () => [withDetails("PRJ-1", "The series", { language: "en-GB", language_own: true, budget_usd: 50 })],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("The series")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const language = within(row).getByRole("combobox", { name: /spells and writes/ });
  expect(language).toHaveValue("en-GB");
  await user.selectOptions(language, "");
  await user.clear(within(row).getByRole("spinbutton", { name: /Budget/ }));
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")?.body).toMatchObject({ parent: null, language: null, budget_usd: null });
});

const projectLists = (): S["ValueListView"][] => [
  { id: "L-1", name: "project-status", label: "Project status", values: ["On track", "At risk"], retired: [], used_by: ["project.status"] },
  { id: "L-2", name: "project-phase", label: "Project phase", values: ["Planning", "Underway"], retired: [], used_by: ["project.phase"] },
  { id: "L-3", name: "project-group", label: "Project group", values: ["Books"], retired: ["Old shelf"], used_by: ["project.group"] },
];

test("a project's status, phase and group are chosen from their lists, and the chosen values are saved", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET lists": projectLists,
    "GET projects": () => [withDetails("PRJ-1", "Book one", { status: "On track", group: "Old shelf" })],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Book one")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const status = within(row).getByRole("combobox", { name: "Status" });
  const phase = within(row).getByRole("combobox", { name: "Phase" });
  const group = within(row).getByRole("combobox", { name: /Group/ });
  await waitFor(() => expect(within(group).getAllByRole("option").map((o) => o.textContent)).toContain("Old shelf (no longer offered)"));
  expect(within(status).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "On track", "At risk", "Add to the list…"]);
  expect(status).toHaveValue("On track");
  expect(group).toHaveValue("Old shelf");
  expect(within(row).queryByRole("textbox", { name: "Status" })).toBeNull();
  await user.selectOptions(status, "At risk");
  await user.selectOptions(phase, "Underway");
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  // The group it still held is kept; nothing is lost by editing something else.
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")?.body).toMatchObject({
    name: "Book one",
    status: "At risk",
    phase: "Underway",
    group: "Old shelf",
  });
});

test("a new project with nothing chosen sends no status, phase or group", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET lists": projectLists,
    "GET projects": () => [],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects": () => ({ id: "PRJ-9" }),
  });
  renderApp(<Setup />);
  await user.click(await screen.findByRole("button", { name: "Add a project" }));
  await user.type(await screen.findByRole("textbox", { name: "Name" }), "Fresh");
  await user.click(screen.getByRole("button", { name: "Add a project" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects")?.body).toMatchObject({ name: "Fresh", status: null, phase: null, group: null });
});

// ---- organizations and priority ------------------------------------------------------------------------------------

const org = (id: string, name: string, people = 0): S["OrganizationView"] => ({ id, name, aliases: [], notes: null, people });
const person = (id: string, name: string, extra: Partial<S["PersonView"]> = {}): S["PersonView"] => ({
  id,
  name,
  role: null,
  aliases: [],
  is_pm: false,
  track_only: false,
  open_items: 0,
  status: "active",
  ...extra,
});

const firstOrg = org("ORG-1", "Org one", 2);
const secondOrg = org("ORG-2", "Org two", 0);

function organizationRoutes(extra: Routes = {}) {
  return others({
    "GET organizations": () => [firstOrg, secondOrg],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    ...extra,
  });
}

const undoToast = async (user: ReturnType<typeof userEvent.setup>) => user.click(await screen.findByRole("button", { name: "Undo" }));

test("a person's row shows the organization's name, never its id", async () => {
  organizationRoutes({ "GET people": () => [person("P-1", "Ana Person", { role: "Editor", org: firstOrg.id, org_name: firstOrg.name })] });
  renderApp(<Setup />);
  const row = (await screen.findByText("Ana Person")).closest("li")!;
  expect(row).toHaveTextContent("Editor · Org one");
  expect(row).not.toHaveTextContent(firstOrg.id);
});

test("the person form chooses the organization by name and sends its id; undo puts the old id back", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes({
    "GET people": () => [person("P-1", "Ana Person", { org: firstOrg.id, org_name: firstOrg.name })],
    "POST people/P-1": () => ({ ok: "P-1" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Ana Person")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const select = within(row).getByRole("combobox", { name: /Organization/ });
  await waitFor(() => expect(select).toHaveValue(firstOrg.id));
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
    "Not set",
    "Org one",
    "Org two",
    "Add an organization…",
  ]);
  await user.selectOptions(select, secondOrg.id);
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST people/P-1")!.body).toMatchObject({ org: secondOrg.id });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST people/P-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST people/P-1")[1].body).toMatchObject({ org: firstOrg.id });
});

test("adding an organization from the person form posts it, selects it, and sends its id with the person", async () => {
  const user = userEvent.setup();
  let made = false;
  const calls = organizationRoutes({
    "GET organizations": () => (made ? [firstOrg, secondOrg, org("ORG-3", "Org three")] : [firstOrg, secondOrg]),
    "POST organizations": () => {
      made = true;
      return { id: "ORG-3" };
    },
    "POST people": () => ({ id: "P-9" }),
  });
  renderApp(<Setup />);
  await user.click(await screen.findByRole("button", { name: "Add a person" }));
  const form = screen.getByLabelText("Full name").closest("form")!;
  await user.type(within(form).getByLabelText("Full name"), "New Person");
  await user.selectOptions(within(form).getByRole("combobox", { name: /Organization/ }), "Add an organization…");
  const field = within(form).getByRole("textbox", { name: "Name of the new organization" });
  await user.type(field, "Org three{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST organizations")?.body).toMatchObject({ name: "Org three" }));
  await waitFor(() => expect(within(form).getByRole("combobox", { name: /Organization/ })).toHaveValue("ORG-3"));
  expect(within(form).queryByRole("textbox", { name: "Name of the new organization" })).toBeNull();
  await user.click(within(form).getByRole("button", { name: "Add a person" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people")).toBe(true));
  expect(calls.find((c) => c.route === "POST people")!.body).toMatchObject({ full_name: "New Person", org: "ORG-3" });
});

test("the person form has a first name field; it is sent as typed, or as nothing when empty, and undo puts the old one back", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes({
    "GET people": () => [person("P-1", "Ana Person", { first_name: "Anita" })],
    "POST people/P-1": () => ({ ok: "P-1" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Ana Person")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const field = within(row).getByLabelText(/^First name/);
  expect(field).toHaveValue("Anita");
  await user.clear(field);
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST people/P-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST people/P-1")!.body).toMatchObject({ first_name: null });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST people/P-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST people/P-1")[1].body).toMatchObject({ first_name: "Anita" });
});

test("Escape cancels the new organization field without closing the form", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes();
  renderApp(<Setup />);
  await user.click(await screen.findByRole("button", { name: "Add a person" }));
  const form = screen.getByLabelText("Full name").closest("form")!;
  await user.selectOptions(within(form).getByRole("combobox", { name: /Organization/ }), "Add an organization…");
  await user.type(within(form).getByRole("textbox", { name: "Name of the new organization" }), "Nope{Escape}");
  expect(within(form).queryByRole("textbox", { name: "Name of the new organization" })).toBeNull();
  expect(screen.getByLabelText("Full name")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST organizations")).toBe(false);
});

test("the organizations section has one row each with how many people work there", async () => {
  organizationRoutes();
  renderApp(<Setup />);
  const section = await screen.findByRole("region", { name: "Organizations" });
  const rows = await within(section).findAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("Org one");
  expect(rows[0]).toHaveTextContent("2 people");
  expect(rows[1]).toHaveTextContent("0 people");
  expect(section).not.toHaveTextContent("ORG-1");
});

test("an organization is added from the section and undo removes it", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes({ "POST organizations": () => ({ id: "ORG-3" }), "POST organizations/ORG-3/remove": () => ({ ok: "ORG-3" }) });
  renderApp(<Setup />);
  const section = await screen.findByRole("region", { name: "Organizations" });
  await user.click(within(section).getByRole("button", { name: "Add an organization" }));
  await user.type(within(section).getByLabelText("Organization name"), "Org three{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST organizations")?.body).toMatchObject({ name: "Org three" }));
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-3/remove")).toBe(true));
});

test("an organization is renamed in its row, and undo renames it back", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes({ "POST organizations/ORG-2": () => ({ ok: "ORG-2" }) });
  renderApp(<Setup />);
  const row = (await screen.findByText("Org two")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
  const field = within(row).getByRole("textbox", { name: "Organization name" });
  expect(field).toHaveValue("Org two");
  await user.clear(field);
  await user.type(field, "Org second{Enter}");
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2")).toBe(true));
  expect(calls.find((c) => c.route === "POST organizations/ORG-2")!.body).toEqual({ name: "Org second" });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST organizations/ORG-2")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST organizations/ORG-2")[1].body).toEqual({ name: "Org two" });
});

test("Escape leaves a rename without sending anything", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes();
  renderApp(<Setup />);
  const row = (await screen.findByText("Org two")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
  await user.type(within(row).getByRole("textbox", { name: "Organization name" }), "x{Escape}");
  expect(within(row).queryByRole("textbox")).toBeNull();
  expect(row).toHaveTextContent("Org two");
  expect(calls.some((c) => c.route.startsWith("POST organizations"))).toBe(false);
});

test("an organization people still work for can't be removed, and the menu says why", async () => {
  const user = userEvent.setup();
  const calls = organizationRoutes();
  renderApp(<Setup />);
  const row = (await screen.findByText("Org one")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  const remove = await screen.findByRole("menuitem", { name: "Remove" });
  expect(remove).toHaveAttribute("aria-disabled", "true");
  expect(remove).toHaveTextContent("People still work for it. Change their organization first.");
  await user.click(remove);
  expect(calls.some((c) => c.route.endsWith("/remove"))).toBe(false);
});

test("removing an organization acts at once, undo restores it, and a refusal's own words are shown", async () => {
  const user = userEvent.setup();
  let refuse = false;
  const calls = organizationRoutes({
    "POST organizations/ORG-2/remove": () => (refuse ? new Refuse(409, "Two people still work for it.") : { ok: "ORG-2" }),
    "POST organizations/ORG-2/restore": () => ({ ok: "ORG-2" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Org two")).closest("li")!;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2/remove")).toBe(true));
  await undoToast(user);
  await waitFor(() => expect(calls.some((c) => c.route === "POST organizations/ORG-2/restore")).toBe(true));
  refuse = true;
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  expect(await screen.findByText(/Two people still work for it\./)).toBeInTheDocument();
});

test("the project form offers Priority from its list, sends it, and the row says it", async () => {
  const user = userEvent.setup();
  const calls = others({
    "GET lists": () => [
      ...projectLists(),
      { id: "L-4", name: "project-priority", label: "Project priority", values: ["High", "Low"], retired: [], used_by: ["project.priority"] },
    ],
    "GET projects": () => [withDetails("PRJ-1", "Book one", { priority: "High" }), withDetails("PRJ-2", "Book two")],
    "GET sync": () => syncView({ folder: "" }),
    "GET jobs": () => [],
    "POST projects/PRJ-1": () => ({ ok: "PRJ-1" }),
  });
  renderApp(<Setup />);
  const row = (await screen.findByText("Book one")).closest("li")!;
  expect(row).toHaveTextContent("priority High");
  expect(screen.getByText("Book two").closest("li")).not.toHaveTextContent("priority");
  await user.click(within(row).getByRole("button", { name: "Edit" }));
  const priority = within(row).getByRole("combobox", { name: "Priority" });
  await waitFor(() => expect(within(priority).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not set", "High", "Low", "Add to the list…"]));
  expect(priority).toHaveValue("High");
  await user.selectOptions(priority, "Low");
  await user.click(within(row).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST projects/PRJ-1")).toBe(true));
  expect(calls.find((c) => c.route === "POST projects/PRJ-1")!.body).toMatchObject({ priority: "Low" });
  await undoToast(user);
  await waitFor(() => expect(calls.filter((c) => c.route === "POST projects/PRJ-1")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST projects/PRJ-1")[1].body).toMatchObject({ priority: "High" });
});
