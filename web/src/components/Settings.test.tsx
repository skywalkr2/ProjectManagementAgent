import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import type { SettingsSection } from "../lib/views";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Settings } from "./Settings";

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";

function item(key: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  const [file] = key.split(".");
  return {
    key,
    file,
    // The test settings sit in the section for "You and the workspace" unless a test says otherwise.
    group: "workspace",
    description: `What ${key} does`,
    type: "text",
    options: [],
    value: "",
    default: "",
    source: "default",
    locked: false,
    basic: true,
    editable: true,
    ...extra,
  };
}

const ITEMS: S["SettingItem"][] = [
  item("demo.title", { value: "Lantern", default: "Workspace", source: "file", description: "The display name." }),
  item("demo.limit", { type: "number", value: 2, default: 2 }),
  item("demo.count", { type: "integer", value: 4, default: 4 }),
  item("demo.on", { type: "yes_no", value: true, default: true }),
  item("demo.mode", { type: "choice", options: ["person", "rule"], value: "person", default: "person" }),
  item("demo.names", { type: "list", value: ["a", "b"], default: [] }),
  item("demo.fixed", { value: "from env", source: "env", locked: true }),
  item("demo.flagged", { value: "from flag", source: "flag", locked: true }),
  item("demo.table", { type: "other", value: { x: 1 }, editable: false }),
  item("demo.server", { value: "local", editable: false }),
  item("demo.advanced", { value: "deep", basic: false, description: "A rarely needed thing." }),
];

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? "") === JSON.stringify(b ?? "");

/** A fake server that behaves like the real one: it keeps the values, answers a save with what changed and a new
 * fingerprint, and refuses a save made on an old fingerprint. A test may answer saves itself instead. */
function api(items = ITEMS, extra: Record<string, (body: unknown) => unknown> = {}) {
  let fingerprint = "fp-1";
  let n = 1;
  const state = items.map((i) => ({ ...i }));
  return fakeApi({
    "GET settings": () => ({ fingerprint, items: state }),
    ...extra,
    "POST settings": (body) => {
      const handler = extra["POST settings"];
      if (handler) {
        const out = handler(body);
        if (!(out instanceof Refuse)) fingerprint = (out as S["SettingsSaved"]).fingerprint;
        return out;
      }
      const sent = body as S["SettingsSave"];
      if (sent.fingerprint !== fingerprint) return new Refuse(409, "The settings changed since you opened them. Look again, then save.");
      const changes: S["SettingChangeView"][] = [];
      const set = (key: string, after: unknown) => {
        const at = state.find((i) => i.key === key)!;
        changes.push({ key, before: at.value, after, was_default: same(at.value, at.default), is_default: same(after, at.default) });
        at.value = after;
        at.source = "file";
      };
      for (const [key, after] of Object.entries(sent.changes ?? {})) set(key, after);
      for (const key of sent.reset ?? []) set(key, state.find((i) => i.key === key)!.default);
      n += 1;
      fingerprint = `fp-${n}`;
      return { changes, fingerprint, needs_restart: false };
    },
  });
}

const open = (section: SettingsSection = "you") =>
  renderApp(<Settings section={section} onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
const posted = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST settings").map((c) => c.body);
const saveButtons = () => screen.queryAllByRole("button", { name: /^Save/ });
const rowOf = (label: string) => screen.getByText(label).closest(".setting") as HTMLElement;

test("a section shows its basic settings, and More settings reveals the rest of that section", async () => {
  const user = userEvent.setup();
  api();
  open();
  expect(await screen.findByLabelText("The display name.")).toBeInTheDocument();
  expect(screen.queryByLabelText("A rarely needed thing.")).toBeNull();
  await user.click(screen.getByRole("button", { name: "More settings" }));
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Fewer settings" })).toHaveAttribute("aria-expanded", "true");
});

test("the section list sits down the side, one link for each section that has something in it, the open one marked", async () => {
  api([...ITEMS, item("ui.theme", { group: "ui" }), item("storage.sync.folder", { group: "storage.sync" })], {
    "GET lists": () => [{ id: "L-1", name: "project-status", label: "Project status", values: ["On track"], retired: [], used_by: [] }],
  });
  open();
  const nav = await screen.findByRole("navigation", { name: "Settings sections" });
  await waitFor(() => expect(within(nav).getByRole("link", { name: "Lists" })).toBeInTheDocument());
  expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual([
    "You and the workspace",
    "AI accounts",
    "Sources",
    "Backups and sync",
    "Appearance",
    "Lists",
  ]);
  expect(within(nav).getByRole("link", { name: "You and the workspace" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: "Backups and sync" })).toHaveAttribute("href", expect.stringMatching(/#settings\/backups$/));
  expect(within(nav).getByRole("link", { name: "Sources" })).toHaveAttribute("href", expect.stringMatching(/#sources$/));
});

test("choosing a section shows that section's settings and no others; the choice goes to the address when the screen asks", async () => {
  const user = userEvent.setup();
  api([...ITEMS, item("ui.theme", { group: "ui", description: "How it looks." })]);
  const chosen = vi.fn();
  renderApp(<Settings section="you" onSection={chosen} onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
  await screen.findByLabelText("The display name.");
  expect(screen.queryByLabelText("How it looks.")).toBeNull();
  await user.click(screen.getByRole("link", { name: "Appearance" }));
  expect(chosen).toHaveBeenCalledWith("appearance");
});

test("without an address to change, the section list still moves between sections", async () => {
  const user = userEvent.setup();
  api([...ITEMS, item("ui.theme", { group: "ui", description: "How it looks." })]);
  renderApp(<Settings onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
  await screen.findByLabelText("The display name.");
  await user.click(screen.getByRole("link", { name: "Appearance" }));
  expect(await screen.findByLabelText("How it looks.")).toBeInTheDocument();
  expect(screen.queryByLabelText("The display name.")).toBeNull();
  expect(screen.getByRole("heading", { level: 2, name: "Appearance" })).toBeInTheDocument();
});

test("the search looks at every setting in every section by its key and description, advanced ones included", async () => {
  const user = userEvent.setup();
  api([...ITEMS, item("ui.theme", { group: "ui", description: "How it looks." })]);
  open();
  await screen.findByLabelText("The display name.");
  const search = screen.getByRole("searchbox", { name: "Search settings" });
  await user.type(search, "rarely");
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  expect(screen.queryByLabelText("The display name.")).toBeNull();
  expect(screen.getByText("1 setting shown.")).toBeInTheDocument();
  await user.clear(search);
  await user.type(search, "demo.advanced");
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  await user.clear(search);
  await user.type(search, "looks");
  expect(screen.getByLabelText("How it looks.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "Appearance" })).toBeInTheDocument();
  await user.clear(search);
  await user.type(search, "zzz");
  expect(screen.getByText("No settings match.")).toBeInTheDocument();
  await user.clear(search);
  expect(await screen.findByLabelText("The display name.")).toBeInTheDocument();
});

test("each type has its own control, with its default shown", async () => {
  api();
  open();
  expect(await screen.findByLabelText("The display name.")).toHaveValue("Lantern");
  expect(screen.getByLabelText("What demo.limit does")).toHaveValue("2");
  expect(screen.getByLabelText("What demo.on does")).toBeChecked();
  expect(screen.getByLabelText("What demo.mode does")).toHaveValue("person");
  expect(screen.getByLabelText("What demo.names does")).toHaveValue("a\nb");
  expect(screen.getByText("Default: Workspace")).toBeInTheDocument();
  expect(screen.getByText("Default: Yes")).toBeInTheDocument();
});

test("a setting's description is the help beside its field, not a line under it, and the field is still described by it", async () => {
  api([item("workspace.name", { value: "Lantern", default: "Workspace", description: "The name shown at the top of every screen." })]);
  open();
  const field = await screen.findByLabelText("Workspace name");
  const row = field.closest(".setting") as HTMLElement;
  const help = row.querySelector("[data-help]") as HTMLElement;
  expect(help).toHaveTextContent("The name shown at the top of every screen.");
  expect(help).toHaveTextContent("Default: Workspace");
  const main = row.querySelector("[data-main]") as HTMLElement;
  expect(main).toContainElement(field);
  expect(main).not.toHaveTextContent("The name shown at the top");
  expect(field).toHaveAccessibleDescription(/The name shown at the top of every screen\./);
});

test("locked settings are disabled and say where they come from; others the screen can't change say which file", async () => {
  api();
  open();
  const env = await screen.findByLabelText("What demo.fixed does");
  expect(env).toBeDisabled();
  expect(screen.getByText("Set outside the app by an environment variable")).toBeInTheDocument();
  expect(screen.getByLabelText("What demo.flagged does")).toBeDisabled();
  expect(screen.getByText("Set by an option used to start the app")).toBeInTheDocument();
  const table = screen.getByText("What demo.table does").closest(".setting") as HTMLElement;
  expect(within(table).getByText("Changed in demo.yaml")).toBeInTheDocument();
  expect(within(table).queryByRole("textbox")).toBeNull();
  const server = screen.getByText("What demo.server does").closest(".setting") as HTMLElement;
  expect(within(server).getByText("local")).toBeInTheDocument();
  expect(within(server).getByText("Changed in demo.yaml")).toBeInTheDocument();
});

test("there is no Save button: a text setting saves when the cursor leaves it, with the fingerprint, and reads back with Undo", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const title = await screen.findByLabelText("The display name.");
  expect(saveButtons()).toHaveLength(0);
  await user.clear(title);
  await user.type(title, "Harbor");
  expect(posted(calls)).toHaveLength(0);
  await user.tab();
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: { "demo.title": "Harbor" }, reset: [], fingerprint: "fp-1" });
  expect(await screen.findByText("Saved. The display name: Harbor")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  expect(screen.getByLabelText("The display name.")).toHaveValue("Harbor");
});

test("Enter saves a text setting without leaving it, once", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const title = await screen.findByLabelText("The display name.");
  await user.type(title, "x{Enter}");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.title": "Lanternx" } });
  expect(title).toHaveFocus();
  await user.tab();
  expect(posted(calls)).toHaveLength(1);
});

test("leaving a field that was not changed saves nothing", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const title = await screen.findByLabelText("The display name.");
  await user.click(title);
  await user.tab();
  await user.type(title, "x");
  await user.type(title, "{Backspace}");
  await user.tab();
  expect(posted(calls)).toHaveLength(0);
});

test("a choice and a yes/no setting save as soon as they change; a list saves when the cursor leaves it", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await user.click(await screen.findByLabelText("What demo.on does"));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.on": false } });
  await user.selectOptions(screen.getByLabelText("What demo.mode does"), "rule");
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toMatchObject({ changes: { "demo.mode": "rule" } });
  const names = screen.getByLabelText("What demo.names does");
  await user.clear(names);
  await user.type(names, "one{Enter}two{Enter}{Enter}three");
  expect(posted(calls)).toHaveLength(2);
  await user.tab();
  await waitFor(() => expect(posted(calls)).toHaveLength(3));
  expect(posted(calls)[2]).toMatchObject({ changes: { "demo.names": ["one", "two", "three"] } });
});

test("a number that isn't one is refused on screen and nothing is sent", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const limit = await screen.findByLabelText("What demo.limit does");
  await user.clear(limit);
  await user.type(limit, "lots");
  expect(screen.getByText("Enter a number.")).toBeInTheDocument();
  await user.tab();
  expect(posted(calls)).toHaveLength(0);
  expect(screen.getByLabelText("What demo.limit does")).toHaveValue("lots");
});

test("each save carries the fingerprint from the one before it, so saves in a row are never refused as out of date", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await user.type(await screen.findByLabelText("The display name."), "x");
  await user.tab();
  await user.click(screen.getByLabelText("What demo.on does"));
  await user.selectOptions(screen.getByLabelText("What demo.mode does"), "rule");
  await waitFor(() => expect(posted(calls)).toHaveLength(3));
  expect(posted(calls).map((b) => (b as { fingerprint: string }).fingerprint)).toEqual(["fp-1", "fp-2", "fp-3"]);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("Undo sends the old values back; after later saves it uses the newest fingerprint, so it still works", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await user.type(await screen.findByLabelText("The display name."), "x");
  await user.tab();
  await screen.findByText("Saved. The display name: Lanternx");
  await user.click(screen.getByLabelText("What demo.on does"));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  await user.click((await screen.findAllByRole("button", { name: "Undo" }))[0]);
  await waitFor(() => expect(posted(calls)).toHaveLength(3));
  expect(posted(calls)[2]).toEqual({ changes: { "demo.title": "Lantern" }, reset: [], fingerprint: "fp-3" });
  expect(await screen.findByText("Undone.")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("The display name.")).toHaveValue("Lantern"));
});

test("a changed setting says Changed with a Reset beside its label; one at its default shows nothing", async () => {
  api();
  open();
  await screen.findByLabelText("The display name.");
  const changed = rowOf("The display name.");
  expect(within(changed).getByText("Changed")).toBeInTheDocument();
  expect(within(changed).getByRole("button", { name: "Reset: The display name." })).toBeInTheDocument();
  const unchanged = rowOf("What demo.limit does");
  expect(within(unchanged).queryByText("Changed")).toBeNull();
  expect(within(unchanged).queryByRole("button", { name: /^Reset/ })).toBeNull();
  // A setting the screen can't change has nothing to reset.
  expect(within(rowOf("What demo.fixed does")).queryByRole("button", { name: /^Reset/ })).toBeNull();
});

test("Reset puts the setting back to its default at once, says so, and can be undone", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  await screen.findByLabelText("The display name.");
  await user.click(screen.getByRole("button", { name: "Reset: The display name." }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: {}, reset: ["demo.title"], fingerprint: "fp-1" });
  expect(await screen.findByText(/back to the default, Workspace/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("The display name.")).toHaveValue("Workspace"));
  expect(within(rowOf("The display name.")).queryByText("Changed")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toEqual({ changes: { "demo.title": "Lantern" }, reset: [], fingerprint: "fp-2" });
  await waitFor(() => expect(screen.getByLabelText("The display name.")).toHaveValue("Lantern"));
});

test("a change made elsewhere meanwhile is refused in the 'changed since you opened it' words, what was typed stays, and the form loads again", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, { "POST settings": () => new Refuse(409, "The settings changed since you opened them. Look again, then save.") });
  open();
  await user.type(await screen.findByLabelText("The display name."), "x");
  const before = calls.filter((c) => c.route === "GET settings").length;
  await user.tab();
  const note = await screen.findByRole("alert");
  expect(note).toHaveTextContent("This was changed since you opened it. What you typed is still here; check it against what is saved now, then save again.");
  expect(rowOf("The display name.")).toContainElement(note);
  expect(screen.getByLabelText("The display name.")).toHaveValue("Lanternx");
  await waitFor(() => expect(calls.filter((c) => c.route === "GET settings").length).toBeGreaterThan(before));
  expect(screen.queryByText(/^Saved/)).toBeNull();
});

test("a refused value shows the server's words on its own row and keeps what was typed", async () => {
  const user = userEvent.setup();
  api(ITEMS, { "POST settings": () => new Refuse(400, "demo.title can't be empty here") });
  open();
  const title = await screen.findByLabelText("The display name.");
  await user.clear(title);
  await user.type(title, "Nope");
  await user.tab();
  const note = await screen.findByRole("alert");
  expect(note).toHaveTextContent("demo.title can't be empty here");
  expect(rowOf("The display name.")).toContainElement(note);
  expect(screen.getByLabelText("The display name.")).toHaveValue("Nope");
});

test("the first field of the section has the cursor when it opens", async () => {
  api();
  open();
  await waitFor(() => expect(screen.getByLabelText("The display name.")).toHaveFocus());
});

test("Backups and sync holds the synced folder and the scheduled work, so neither is on the Projects or People screens", async () => {
  api([item("storage.sync.folder", { group: "storage.sync", description: "Where the synced folder is.", value: "/shared/Cockpit", picker: "folder" })], {
    "GET sync": () => ({ folder: "/shared/Cockpit", problem: null, stopped: false, changed_outside: [], removed_outside: [], rebuilt: [], outside_edits: [], conflict_copies: [], shared: false, handover: null }),
    "GET jobs": () => [{ name: "demo/refresh-feeds", plugin: "demo", enabled: true, every_minutes: 60, last_run_at: null, last_outcome: null, last_error: null }],
  });
  open("backups");
  const sync = await screen.findByRole("region", { name: "Synced folder" });
  expect(await within(sync).findByText("Kept in /shared/Cockpit")).toBeInTheDocument();
  const jobs = await screen.findByRole("region", { name: "Scheduled work" });
  expect(jobs).toHaveTextContent("Refresh feeds");
});

const ASK = "Restart to finish this change? It takes a few seconds and keeps anything you're typing elsewhere.";

function RestartHarness() {
  const [hellos, setHellos] = useState(1);
  return (
    <RestartProvider hellos={hellos}>
      <RestartNotice />
      <button type="button" onClick={() => setHellos(hellos + 1)}>
        reconnect
      </button>
      <Settings onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />
    </RestartProvider>
  );
}

const savedTitle = (needs_restart: boolean) => ({
  changes: [{ key: "demo.title", before: "Lantern", after: "Harborx", was_default: false, is_default: false }],
  fingerprint: "fp-2",
  needs_restart,
});

async function saveTitle(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("The display name."), "x");
  await user.tab();
  return screen.getAllByRole("status").find((el) => el.classList.contains("restart-slot"))!;
}

test("a save that needs a restart asks first; Restart now asks the app, then says so until it is back", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, {
    "POST settings": () => savedTitle(true),
    "POST restart": () => ({ restarting: true }),
    "GET runtime-config": () => ({ instance: null }),
  });
  renderApp(<RestartHarness />);
  const live = await saveTitle(user);
  await waitFor(() => expect(live).toHaveTextContent(ASK));
  expect(live).not.toHaveTextContent("Restarting");
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(within(live).getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
  await waitFor(() => expect(live).toHaveTextContent("Restarting to use the new settings…"));
  expect(within(live).queryByRole("button", { name: "Restart now" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "reconnect" }));
  await waitFor(() => expect(live).toHaveTextContent("Restarted with the new settings."));
});

test("Later hides the question and sends nothing", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, { "POST settings": () => savedTitle(true) });
  renderApp(<RestartHarness />);
  const live = await saveTitle(user);
  await waitFor(() => expect(live).toHaveTextContent(ASK));
  await user.click(within(live).getByRole("button", { name: "Later" }));
  expect(live).toBeEmptyDOMElement();
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("a save that needs no restart says nothing about restarting", async () => {
  const user = userEvent.setup();
  api(ITEMS, { "POST settings": () => savedTitle(false) });
  renderApp(<RestartHarness />);
  const live = await saveTitle(user);
  expect(await screen.findByText(/Saved/)).toBeInTheDocument();
  expect(live).toBeEmptyDOMElement();
  expect(screen.queryByRole("button", { name: "Restart now" })).toBeNull();
  expect(screen.queryByText(/Restarting|Restarted/)).toBeNull();
});

test("when this copy can't restart itself, the refusal's words are shown in the notice", async () => {
  const user = userEvent.setup();
  api(ITEMS, {
    "POST settings": () => savedTitle(true),
    "POST restart": () => new Refuse(409, "Close it and start it again."),
  });
  renderApp(<RestartHarness />);
  const live = await saveTitle(user);
  await user.click(await within(live).findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(live).toHaveTextContent("Close it and start it again."));
  expect(live).not.toHaveTextContent("Restarting");
  await user.click(within(live).getByRole("button", { name: "Dismiss" }));
  expect(live).toBeEmptyDOMElement();
});

test("undoing a save asks about a restart when the undo needs one", async () => {
  const user = userEvent.setup();
  api(ITEMS, {
    "POST settings": (body) => ((body as { changes: Record<string, unknown> }).changes["demo.title"] === "Lantern" ? { changes: [], fingerprint: "fp-3", needs_restart: true } : savedTitle(false)),
  });
  renderApp(<RestartHarness />);
  const live = await saveTitle(user);
  expect(live).toBeEmptyDOMElement();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(live).toHaveTextContent(ASK));
});

const DEPENDENTS: S["SettingItem"][] = [
  item("demo.auto", { type: "yes_no", value: false, default: false, description: "Do it on a schedule." }),
  item("demo.hours", { type: "integer", value: 6, default: 6, enabled_by: "demo.auto", description: "Hours between runs." }),
  item("demo.folder", { value: "", picker: "folder", description: "Where it goes." }),
  item("demo.keep", { type: "integer", value: 3, default: 3, enabled_by: "demo.folder", description: "How many to keep." }),
];

test("a setting that needs a switch is greyed with a reason while it is off, and works once the switch is turned on", async () => {
  const user = userEvent.setup();
  const calls = api(DEPENDENTS);
  open();
  const hours = await screen.findByLabelText("Hours between runs.");
  expect(hours).toBeDisabled();
  expect(hours).toHaveAccessibleDescription(/Turn on “Do it on a schedule\.” to change this\./);
  expect(screen.getByText("Turn on “Do it on a schedule.” to change this.")).toBeInTheDocument();
  expect(hours.closest(".setting")).toHaveClass("dependent");
  // Turning the switch on is saved at once; the setting then wakes up.
  await user.click(screen.getByLabelText("Do it on a schedule."));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.auto": true } });
  await waitFor(() => expect(screen.getByLabelText("Hours between runs.")).toBeEnabled());
  expect(screen.queryByText(/Turn on “Do it on a schedule/)).toBeNull();
  await user.clear(screen.getByLabelText("Hours between runs."));
  await user.type(screen.getByLabelText("Hours between runs."), "8");
  await user.tab();
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toMatchObject({ changes: { "demo.hours": 8 } });
});

test("turning the switch back off greys the setting again", async () => {
  const user = userEvent.setup();
  api(DEPENDENTS);
  open();
  await user.click(await screen.findByLabelText("Do it on a schedule."));
  await waitFor(() => expect(screen.getByLabelText("Hours between runs.")).toBeEnabled());
  await user.click(screen.getByLabelText("Do it on a schedule."));
  await waitFor(() => expect(screen.getByLabelText("Hours between runs.")).toBeDisabled());
});

test("a setting that depends on a text setting waits until that has a value", async () => {
  const user = userEvent.setup();
  api(DEPENDENTS, { "GET setup/folders": () => ({ path: "/home/me", parent: "/home", folders: ["shared"] }) });
  open();
  const keep = await screen.findByLabelText("How many to keep.");
  expect(keep).toBeDisabled();
  expect(screen.getByText("Set “Where it goes.” to change this.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Where it goes."), "/mnt/x");
  expect(screen.getByLabelText("How many to keep.")).toBeEnabled();
});

test("a folder setting offers a chooser that saves the folder picked, and a way to clear it", async () => {
  const user = userEvent.setup();
  const calls = api(DEPENDENTS, {
    "GET setup/folders": () => ({ path: "/home/me", parent: "/home", folders: ["shared"] }),
    [`GET setup/folders?path=${encodeURIComponent("/home/me/shared")}`]: () => ({ path: "/home/me/shared", parent: "/home/me", folders: [] }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: /Choose a folder…/ }));
  await user.click(await screen.findByRole("button", { name: "shared" }));
  await user.click(await screen.findByRole("button", { name: "Use this folder" }));
  await waitFor(() => expect(screen.getByLabelText("Where it goes.")).toHaveValue("/home/me/shared"));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.folder": "/home/me/shared" } });
  expect(screen.getByLabelText("How many to keep.")).toBeEnabled();
  await user.click(screen.getByRole("button", { name: /Clear/ }));
  expect(screen.getByLabelText("Where it goes.")).toHaveValue("");
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toMatchObject({ changes: { "demo.folder": "" } });
});

test("where folders can't be listed the folder setting is a plain text box with no error", async () => {
  api(DEPENDENTS, { "GET setup/folders": () => new Refuse(403, "Folders can't be listed here.") });
  open();
  const input = await screen.findByLabelText("Where it goes.");
  await waitFor(() => expect(screen.queryByRole("button", { name: /Choose a folder…/ })).toBeNull());
  expect(input).toBeEnabled();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("Add-ons opens the add-ons screen", async () => {
  api();
  const onOpenAddons = vi.fn();
  const user = userEvent.setup();
  renderApp(<Settings onOpenGuide={() => undefined} onOpenAddons={onOpenAddons} onChooseSource={() => undefined} />);
  await user.click(screen.getByRole("button", { name: "Open Add-ons" }));
  expect(onOpenAddons).toHaveBeenCalled();
});

test("Lists is a section of its own, where the choices dropdowns offer can be changed", async () => {
  api(ITEMS, {
    "GET lists": () => [
      { id: "L-1", name: "project-status", label: "Project status", values: ["On track"], retired: [], used_by: ["project.status"] },
    ],
  });
  open("lists");
  expect(await screen.findByRole("heading", { level: 2, name: "Lists" })).toBeInTheDocument();
  expect(screen.getByText("Project status")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Add a choice to Project status" })).toBeInTheDocument();
  expect(screen.queryByLabelText("The display name.")).toBeNull();
});

// ---- an add-on's settings ------------------------------------------------------------------------------------------

function addonItem(name: string, field: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  return {
    ...item(`demo.${field}`),
    key: `plugins/${name}.${field}`,
    file: `plugins/${name}`,
    group: `plugins/${name}`,
    plugin: name,
    description: `What ${field} does for the add-on`,
    ...extra,
  };
}

const ADDON_ITEMS: S["SettingItem"][] = [
  addonItem("sample-pack", "greeting", { value: "Hello", default: "Hi", source: "file" }),
  addonItem("sample-pack", "loud", { type: "yes_no", value: false, default: false }),
  addonItem("sample-pack", "mode", { type: "choice", options: ["quiet", "bold"], value: "quiet", default: "quiet" }),
  addonItem("sample-pack", "fixed", { editable: false, value: "set elsewhere" }),
  addonItem("other-pack", "limit", { type: "integer", value: 3, default: 3 }),
];

test("each add-on has a section of its own, after the app's own, and its settings never show where they live", async () => {
  api([...ADDON_ITEMS, ...ITEMS]);
  open("addon/sample-pack");
  await screen.findByLabelText("What greeting does for the add-on");
  const nav = screen.getByRole("navigation", { name: "Settings sections" });
  const links = within(nav).getAllByRole("link").map((a) => a.textContent);
  expect(links.slice(-2)).toEqual(["Sample pack", "Other pack"]);
  expect(links.indexOf("You and the workspace")).toBeLessThan(links.indexOf("Sample pack"));
  expect(within(nav).getByRole("link", { name: "Sample pack" })).toHaveAttribute("aria-current", "page");
  expect(document.body).not.toHaveTextContent("plugins/");
  expect(screen.getByRole("heading", { level: 2, name: "Sample pack" })).toBeInTheDocument();
  expect(screen.getByLabelText("What greeting does for the add-on")).toHaveValue("Hello");
  expect(screen.getByLabelText("What loud does for the add-on")).not.toBeChecked();
  expect(screen.getByLabelText("What mode does for the add-on")).toHaveValue("quiet");
  expect(screen.getByText("Default: Hi")).toBeInTheDocument();
  const fixed = screen.getByText("What fixed does for the add-on").closest(".setting") as HTMLElement;
  expect(within(fixed).getByText("Change this setting outside this screen.")).toBeInTheDocument();
  // Another add-on's setting is in its own section, and the app's own is in theirs.
  expect(screen.queryByLabelText("What limit does for the add-on")).toBeNull();
  expect(screen.queryByLabelText("The display name.")).toBeNull();
});

test("an add-on's settings save like the app's: under the key the file uses, as they change, with undo", async () => {
  const user = userEvent.setup();
  const calls = api([...ADDON_ITEMS, ...ITEMS]);
  open("addon/sample-pack");
  const greeting = await screen.findByLabelText("What greeting does for the add-on");
  await user.clear(greeting);
  await user.type(greeting, "Howdy");
  // Moving on to the next setting saves the one that was typed in.
  await user.click(screen.getByLabelText("What loud does for the add-on"));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[0]).toEqual({ changes: { "plugins/sample-pack.greeting": "Howdy" }, reset: [], fingerprint: "fp-1" });
  expect(posted(calls)[1]).toEqual({ changes: { "plugins/sample-pack.loud": true }, reset: [], fingerprint: "fp-2" });
  expect((await screen.findAllByText(/Saved/)).length).toBeGreaterThan(0);
  expect(document.body).not.toHaveTextContent("plugins/");
});

test("the search finds an add-on's settings by the add-on's name", async () => {
  const user = userEvent.setup();
  api([...ADDON_ITEMS, ...ITEMS]);
  open();
  await screen.findByLabelText("The display name.");
  await user.type(screen.getByRole("searchbox", { name: "Search settings" }), "other pack");
  expect(screen.getByLabelText("What limit does for the add-on")).toBeInTheDocument();
  expect(screen.queryByLabelText("What greeting does for the add-on")).toBeNull();
});

test("Advanced groups the rest by topic, each topic closed until it is opened, and the standing instructions point to Knowledge", async () => {
  const user = userEvent.setup();
  const onOpenKnowledge = vi.fn();
  api([
    item("rules.rules", { type: "list", group: "rules", value: [], default: [], basic: false }),
    item("dispatch.knowledge.learn", { type: "yes_no", group: "dispatch.knowledge", value: true, default: true, basic: false, description: "Learn from corrections." }),
  ]);
  renderApp(
    <Settings section="advanced" onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} onOpenKnowledge={onOpenKnowledge} />,
  );
  const topic = await screen.findByRole("button", { name: "Rules" });
  expect(topic).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByLabelText("Learn from corrections.")).toBeNull();
  await user.click(topic);
  expect(topic).toHaveAttribute("aria-expanded", "true");
  const region = screen.getByRole("group", { name: "Rules" });
  expect(region).toHaveTextContent("Review what Helper has learned and your saved rules in Knowledge.");
  await user.click(within(region).getByRole("button", { name: "Open Knowledge" }));
  expect(onOpenKnowledge).toHaveBeenCalledTimes(1);
  // The other topic is still closed.
  expect(screen.getByRole("button", { name: "Dispatch knowledge", expanded: false })).toBeInTheDocument();
});

const ACCOUNT: S["AiAccountView"] = {
  name: "main",
  label: "Main account",
  kind: "svc",
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "m" },
  used_for: ["routine"],
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
};
const AI_ROUTES = {
  "GET ai/accounts": () => [ACCOUNT],
  "GET ai/endpoints": () => [{ id: "svc", name: "A service", adapter: "adapter-one", base_url: `${WEB}api.svc.example.com/v1`, needs_key: true, key_url: "", local: false, note: "", allowed_data: ["open"], program: "", model_optional: false, model_examples: [], installed: null }],
  "GET ai/skills": () => ({ min_score: 0.8, stale_days: 60, accounts: [] }),
  "GET ai/check-size": () => ({ calls: 10, input_tokens: 1000, output_tokens: 200 }),
  "GET ai/local": () => [],
  "GET setup": () => ({ steps: [], finished: false, local: true }),
};

test("the AI section lists the accounts that are set up, one row each, with its role, its name and one next step", async () => {
  api(ITEMS, AI_ROUTES);
  open("ai");
  expect(await screen.findByRole("heading", { name: /AI accounts/ })).toBeInTheDocument();
  const row = screen.getByText("Main account", { selector: "li[data-row] span[id$=title]" }).closest("li") as HTMLElement;
  expect(row).toHaveTextContent("Does the work");
  expect(row).toHaveTextContent("A service");
  expect(within(row).getByRole("button", { name: "Test Main account" })).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "More actions for Main account" })).toBeInTheDocument();
});

test("Add an account opens its form in a drawer inside Settings, never the setup guide, with the cursor in it", async () => {
  const user = userEvent.setup();
  const onOpenGuide = vi.fn();
  api(ITEMS, AI_ROUTES);
  renderApp(<Settings section="ai" onOpenGuide={onOpenGuide} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
  await user.click(await screen.findByRole("button", { name: "Add an account" }));
  const drawer = await screen.findByRole("dialog", { name: "Add an account" });
  expect(onOpenGuide).not.toHaveBeenCalled();
  expect(within(drawer).getByRole("group", { name: /Which AI should/ })).toBeInTheDocument();
  await waitFor(() => expect(within(drawer).getAllByRole("radio")[0]).toHaveFocus());
  await user.click(within(drawer).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Add an account" })).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Add an account" })).toHaveFocus());
});

test("a Today line that asks for an account to be added opens the same drawer", async () => {
  api(ITEMS, AI_ROUTES);
  const done = vi.fn();
  renderApp(<Settings section="ai" onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} addAccount={Date.now()} onAddAccountOpened={done} />);
  expect(await screen.findByRole("dialog", { name: "Add an account" })).toBeInTheDocument();
  expect(done).toHaveBeenCalled();
});

test("Compare what they can do opens the grid", async () => {
  const user = userEvent.setup();
  const onOpenCompare = vi.fn();
  api(ITEMS, AI_ROUTES);
  renderApp(<Settings section="ai" onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} onOpenCompare={onOpenCompare} />);
  await user.click(await screen.findByRole("button", { name: "Compare what they can do" }));
  expect(onOpenCompare).toHaveBeenCalledTimes(1);
});

test("an add-on's data files are listed in an Add-on files section, and the section is absent when no add-on has any", async () => {
  api(ITEMS, {
    "GET data-forms": () => [{ name: "demo/template", plugin: "demo", label: "Templates", description: "" }],
    "GET data-forms/demo/template/files": () => [{ file: "classic.yaml", layers: ["shipped"], layer: "shipped", problem: null }],
  });
  open("files");
  expect(await screen.findByRole("heading", { name: "Add-on files" })).toBeInTheDocument();
  expect(await screen.findByRole("listitem", { name: "classic.yaml" })).toHaveTextContent("Comes with the add-on");
});

test("with no add-on data files there is no Add-on files section in the list", async () => {
  api(ITEMS, { "GET data-forms": () => [] });
  open();
  const nav = await screen.findByRole("navigation", { name: "Settings sections" });
  await screen.findByLabelText("The display name.");
  expect(within(nav).queryByRole("link", { name: "Add-on files" })).toBeNull();
});

test("the AI section keeps its spending settings below the accounts, and puts the cursor on its heading", async () => {
  api([item("ai.budgets.per_run_usd", { group: "ai.budgets", type: "number", value: 1, default: 1, description: "The most one run may cost." })], AI_ROUTES);
  open("ai");
  expect(await screen.findByLabelText("Maximum cost per AI task (USD)")).toHaveValue("1");
  await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: /AI accounts/ })).toHaveFocus());
});

test("a setting that picks a language shows each tag by its name, sorted by name, and saves the tag", async () => {
  const user = userEvent.setup();
  const calls = api(
    [item("demo.language", { type: "choice", choices: "languages", options: ["fr-FR", "en-US", "en-GB"], value: "en-US", default: "en-US", source: "file" })],
    { "POST settings": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }) },
  );
  open();
  const select = await screen.findByLabelText("What demo.language does");
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["English (United Kingdom)", "English (United States)", "French (France)"]);
  expect(select).toHaveValue("en-US");
  await user.selectOptions(select, "fr-FR");
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.language": "fr-FR" } });
});

test("a choice setting that doesn't name a list keeps its own order and wording", async () => {
  api();
  open();
  const select = await screen.findByLabelText("What demo.mode does");
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["person", "rule"]);
});

test("the Today section holds the reminder settings as lists, and the button that asks the browser for notifications", async () => {
  const user = userEvent.setup();
  const request = vi.fn(async () => "granted");
  vi.stubGlobal("Notification", Object.assign(function Notification() {}, { permission: "default", requestPermission: request }));
  api([
    ...ITEMS,
    item("steward.reminders.quiet_start", { group: "steward.reminders", type: "choice", options: ["20:00", "21:00"], value: "21:00", default: "21:00", choices: "times_of_day" }),
    item("steward.reminders.working_first_day", { group: "steward.reminders", type: "choice", options: ["monday", "tuesday"], value: "monday", default: "monday" }),
  ]);
  renderApp(<Settings section="today" onSection={() => undefined} onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
  expect(await screen.findByRole("combobox", { name: "Quiet hours start" })).toHaveValue("21:00");
  const first = screen.getByRole("combobox", { name: "First working day" });
  expect(within(first).getAllByRole("option").map((o) => o.textContent)).toEqual(["Monday", "Tuesday"]);
  expect(request).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Allow notifications" }));
  expect(request).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});
