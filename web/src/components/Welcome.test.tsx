import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp, setupStep as step, setupView } from "../test-utils";
import { StepList } from "./Welcome";

const setting = (key: string, value: unknown, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] => ({
  key,
  file: "workspace",
  group: "workspace",
  description: key,
  type: "text",
  options: [],
  value,
  default: value,
  source: "default",
  locked: false,
  basic: true,
  editable: true,
  ...extra,
});

const ITEMS = [
  setting("workspace.name", "Workspace"),
  setting("workspace.user.timezone", "UTC"),
];

const CORE = ["workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons"];

function api(steps: S["SetupStepView"][], extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET setup": () => setupView(steps),
    "GET settings": () => ({ fingerprint: "fp-1", items: ITEMS }),
    "GET me": () => ({ person: null, full_name: "" }),
    "GET templates": () => [
      {
        id: "tpl-a",
        name: "Book project",
        description: "Chapters and drafts.",
        set_up: false,
        adds: [
          { name: "Chapters", fields: ["Title", "Length"], stages: ["Outline", "Draft", "Final"] },
          { name: "Notes", fields: [], stages: [] },
        ],
      },
      { id: "tpl-b", name: "Event", description: "Dates and tasks.", set_up: false, adds: [{ name: "Dates", fields: ["When"], stages: ["Planned"] }] },
      { id: "tpl-c", name: "Trip", description: "Places and plans.", set_up: true, adds: [{ name: "Places", fields: ["Where"], stages: [] }] },
    ],
    "GET ai/endpoints": () => [],
    ...extra,
  });
}

const open = (props: Partial<Parameters<typeof StepList>[0]> = {}) => {
  const onOpenPeople = vi.fn();
  const onOpenAddons = vi.fn();
  const onHandIn = vi.fn();
  const onChooseSource = vi.fn();
  const view = renderApp(
    <StepList focusStep={null} onOpenPeople={onOpenPeople} onOpenAddons={onOpenAddons} onHandIn={onHandIn} onChooseSource={onChooseSource} {...props} />,
  );
  return { onOpenPeople, onOpenAddons, onHandIn, onChooseSource, ...view };
};

const section = (id: string) => document.querySelector(`[data-step="${id}"]`) as HTMLElement;

test("one section per step, in the server's order, each saying in words where it stands", async () => {
  api([
    step("workspace", { done: true }),
    step("template", { skipped: true }),
    step("ai"),
    step("plugin/tidy", { label: "Connect the tidy-up tool", explanation: "It files things away.", plugin: "plugin" }),
  ]);
  open();
  await screen.findByRole("heading", { name: "Add an AI account and test it" });
  const sections = Array.from(document.querySelectorAll("[data-step]"));
  expect(sections.map((s) => s.getAttribute("data-step"))).toEqual(["workspace", "template", "ai", "plugin/tidy"]);
  expect(within(section("workspace")).getByRole("heading", { name: "Name the workspace and say who you are" })).toBeInTheDocument();
  expect(section("workspace")).toHaveTextContent("Done");
  expect(section("template")).toHaveTextContent("Skipped");
  expect(section("ai")).toHaveTextContent("Not done yet");
  expect(section("plugin/tidy")).toHaveTextContent("Connect the tidy-up tool");
  expect(section("plugin/tidy")).toHaveTextContent("It files things away.");
});

test("Skip posts the step and turns into a way back; Reopen undoes it", async () => {
  const user = userEvent.setup();
  let skipped = false;
  const calls = fakeApi({
    "GET setup": () => setupView([step("backup", { skipped })]),
    "GET settings": () => ({ fingerprint: "fp-1", items: ITEMS }),
    "POST setup/backup/skip": () => {
      skipped = true;
      return { ok: "backup" };
    },
    "POST setup/backup/reopen": () => {
      skipped = false;
      return { ok: "backup" };
    },
  });
  open();
  const button = await screen.findByRole("button", { name: "Skip: Choose a backup folder" });
  await user.click(button);
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup/skip")).toBe(true));
  const back = await screen.findByRole("button", { name: "Do it now: Choose a backup folder" });
  // The same button stays in place, so keyboard focus is not lost.
  expect(back).toBe(button);
  expect(back).toHaveFocus();
  expect(section("backup")).toHaveTextContent("Skipped");
  expect(await screen.findByText(/Skipped: Choose a backup folder/)).toBeInTheDocument();
  await user.click(back);
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup/reopen")).toBe(true));
  expect(await screen.findByRole("button", { name: "Skip: Choose a backup folder" })).toBeInTheDocument();
});

test("a plugin's step id keeps its slash in the address, and Undo on the toast puts it back", async () => {
  const user = userEvent.setup();
  const calls = api([step("plugin/tidy", { label: "Connect the tidy-up tool" })], {
    "POST setup/plugin/tidy/skip": () => ({ ok: "plugin/tidy" }),
    "POST setup/plugin/tidy/reopen": () => ({ ok: "plugin/tidy" }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Skip: Connect the tidy-up tool" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/plugin/tidy/reopen")).toBe(true));
});

test("the template step's skip is called Start empty, and a done step has no skip", async () => {
  api([step("workspace", { done: true }), step("template")]);
  open();
  expect(await screen.findByRole("button", { name: "Start empty: Pick a starting template" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Skip: Name the workspace/ })).toBeNull();
});

test("the workspace step starts the time zone from this browser while it is still the default", async () => {
  const user = userEvent.setup();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({ timeZone: "Europe/Paris" } as Intl.ResolvedDateTimeFormatOptions);
  const calls = api([step("workspace")], {
    "POST settings": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
    "POST me": () => ({ person: "PER-1", full_name: "Sam Tester" }),
  });
  open();
  expect(await screen.findByLabelText("Your time zone")).toHaveValue("Europe/Paris");
  await user.type(screen.getByLabelText("Your full name"), "Sam Tester");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
  // The name goes to the person record (the one place it is kept); the time zone is a setting.
  expect(calls.find((c) => c.route === "POST me")!.body).toEqual({ full_name: "Sam Tester" });
  const body = calls.find((c) => c.route === "POST settings")!.body as { changes: Record<string, string> };
  expect(body.changes).toEqual({ "workspace.user.timezone": "Europe/Paris" });
  vi.restoreAllMocks();
});

test("the workspace step shows the server's words when a value is refused, and keeps what was typed", async () => {
  const user = userEvent.setup();
  api([step("workspace")], { "POST settings": () => new Refuse(400, "That time zone isn't one we know.") });
  open();
  const name = await screen.findByLabelText("Workspace name");
  await user.clear(name);
  await user.type(name, "Harbor");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That time zone isn't one we know.");
  expect(screen.getByLabelText("Workspace name")).toHaveValue("Harbor");
});

test("the template step applies one template and asks before the app restarts", async () => {
  const user = userEvent.setup();
  const calls = api([step("template")], { "POST templates/apply": () => ({ plugins: [], needs_restart: true }) });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <StepList focusStep={null} onOpenPeople={() => undefined} onOpenAddons={() => undefined} onHandIn={() => undefined} onChooseSource={() => undefined} />
    </RestartProvider>,
  );
  expect(await screen.findByText("Chapters and drafts.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Apply Event" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST templates/apply")?.body).toEqual({ id: "tpl-b" }));
  expect(await screen.findByText("Applied Event.")).toBeInTheDocument();
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("This change needs the app to restart."));
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("People & projects and Hand in are buttons that open those screens", async () => {
  const user = userEvent.setup();
  api(CORE.filter((id) => id === "people" || id === "first_note").map((id) => step(id)));
  const { onOpenPeople, onHandIn } = open();
  await user.click(await screen.findByRole("button", { name: "Open People & projects" }));
  await user.click(screen.getByRole("button", { name: "Hand something in" }));
  expect(onOpenPeople).toHaveBeenCalledTimes(1);
  expect(onHandIn).toHaveBeenCalledTimes(1);
});

test("a plugin's step with an action starts that action for the whole workspace", async () => {
  const user = userEvent.setup();
  const calls = api([step("plugin/tidy", { label: "Connect the tidy-up tool", action: "plugin/connect", plugin: "plugin" })], {
    "POST plugin-actions/plugin/connect/preview": () => ({
      token: "tok-1",
      action: "plugin/connect",
      summary: "Connect it",
      ops: [],
      files: [],
      previews: [],
      choices: [],
      notes: [],
      expires_at: "2026-10-09T15:00:00Z",
    }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Connect the tidy-up tool" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST plugin-actions/plugin/connect/preview")).toBe(true));
  expect(calls.find((c) => c.route === "POST plugin-actions/plugin/connect/preview")!.body).toMatchObject({ target: null });
});

test("opening the guide at a step puts focus on that step's heading", async () => {
  api(CORE.map((id) => step(id)));
  open({ focusStep: { id: "backup", n: 1 } });
  const heading = await screen.findByRole("heading", { name: "Choose a backup folder" });
  await waitFor(() => expect(heading).toHaveFocus());
});

test("a plugin's step shows the settings it suggests in words, and Apply sends the current fingerprint", async () => {
  const user = userEvent.setup();
  const calls = api(
    [
      step("plugin/tidy", {
        label: "Connect the tidy-up tool",
        plugin: "plugin",
        settings: { "workspace.name": "Harbor", "storage.backups.automatic": true },
      }),
    ],
    {
      "POST setup/plugin/tidy/apply-settings": () => ({
        changes: [{ key: "workspace.name", before: "Workspace", after: "Harbor", was_default: true, is_default: false }],
        fingerprint: "fp-2",
        needs_restart: false,
      }),
    },
  );
  open();
  const suggested = await screen.findByRole("list", { name: "Suggested settings" });
  expect(within(suggested).getByText("Workspace name: Harbor")).toBeInTheDocument();
  expect(within(suggested).getByText("Back up on a schedule: Yes")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Apply these settings" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST setup/plugin/tidy/apply-settings")?.body).toEqual({ fingerprint: "fp-1" }),
  );
  // The read-back with Undo, as after any saved setting.
  expect(await screen.findByText("Saved. Workspace name: Harbor")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
});

test("a refused apply is said in words and nothing is read back", async () => {
  const user = userEvent.setup();
  api([step("plugin/tidy", { label: "Connect the tidy-up tool", plugin: "plugin", settings: { "workspace.name": "Harbor" } })], {
    "POST setup/plugin/tidy/apply-settings": () => new Refuse(409, "The settings changed since you looked."),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Apply these settings" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The settings changed since you looked.");
});

test("a step that suggests nothing shows no settings", async () => {
  api([step("plugin/tidy", { label: "Connect the tidy-up tool", plugin: "plugin", settings: {} })]);
  open();
  await screen.findByRole("heading", { name: "Connect the tidy-up tool" });
  expect(screen.queryByRole("button", { name: "Apply these settings" })).toBeNull();
});

describe("a sign-in's step", () => {
  const signInStep = (extra: Partial<S["SetupStepView"]> = {}) =>
    step("demo/mail", {
      sign_in: "demo/mail",
      label: "Demo Mail",
      explanation: "Read your mail; Read your calendar",
      plugin: "demo",
      ...extra,
    });
  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("reads 'Sign in to {label}', says what will be asked, and Sign in starts the sign-in", async () => {
    const user = userEvent.setup();
    const calls = api([signInStep()], {
      "POST sign-ins/demo/mail/start": () => ({ url: "http://localhost:9090/login?x=1" }),
    });
    open();
    const heading = await screen.findByRole("heading", { name: "Sign in to Demo Mail" });
    expect(heading).toBeInTheDocument();
    const mine = section("demo/mail");
    expect(within(mine).getByText("You'll be asked to allow: Read your mail; Read your calendar")).toBeInTheDocument();
    expect(mine).toHaveTextContent("Not done yet");
    await user.click(within(mine).getByRole("button", { name: "Sign in to Demo Mail" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("http://localhost:9090/login?x=1"));
    expect(calls.filter((c) => c.route === "POST sign-ins/demo/mail/start")).toHaveLength(1);
    expect(within(mine).getByRole("button", { name: "Sign in to Demo Mail" })).toHaveTextContent("Opening the sign-in page");
  });

  test("a refusal to start is said on the step and goes nowhere", async () => {
    const user = userEvent.setup();
    api([signInStep()], { "POST sign-ins/demo/mail/start": () => new Refuse(409, "Set the app registration first.") });
    open();
    await user.click(await screen.findByRole("button", { name: "Sign in to Demo Mail" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Set the app registration first.");
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in to Demo Mail" })).toBeEnabled();
  });

  test("no explanation line when the sign-in asks for nothing to say", async () => {
    api([signInStep({ explanation: "" })]);
    open();
    await screen.findByRole("heading", { name: "Sign in to Demo Mail" });
    expect(screen.queryByText(/You'll be asked to allow/)).toBeNull();
  });

  test("done shows no Sign in button, and skipped can be reopened like any step", async () => {
    api([signInStep({ done: true }), signInStep({ id: "demo/other", sign_in: "demo/other", label: "Demo Other", skipped: true })]);
    open();
    await screen.findByRole("heading", { name: "Sign in to Demo Mail" });
    expect(section("demo/mail")).toHaveTextContent("Done");
    expect(within(section("demo/mail")).queryByRole("button", { name: "Sign in to Demo Mail" })).toBeNull();
    expect(section("demo/other")).toHaveTextContent("Skipped");
    expect(within(section("demo/other")).getByRole("button", { name: "Sign in to Demo Other" })).toBeInTheDocument();
    expect(within(section("demo/other")).getByRole("button", { name: /^Do it now/ })).toBeInTheDocument();
  });
});

describe("a sign-in step that is done", () => {
  const done = { sign_in: "demo/mail", label: "Demo Mail", plugin: "demo", done: true };
  const signedIn = (): S["SignInView"] => ({
    name: "demo/mail",
    label: "Demo Mail",
    status: "signed_in",
    ready: true,
    callback: "http://localhost:8080/auth/demo/mail/callback",
    app: "workspace",
    account: "pat@example.com",
    can_paste: false,
    needs_secret: false,
    set_aside: false,
    default_unusable: false,
  });

  test("still shows the sign-in row's actions: choose what to read, sign out and sign in again", async () => {
    const user = userEvent.setup();
    api([step("demo/mail", done)], { "GET sign-ins": () => [signedIn()] });
    const { onChooseSource } = open();
    await screen.findByRole("heading", { name: "Sign in to Demo Mail" });
    const mine = section("demo/mail");
    expect(await within(mine).findByText("Signed in as pat@example.com")).toBeInTheDocument();
    await user.click(within(mine).getByRole("button", { name: "Choose what to read from Demo Mail" }));
    expect(onChooseSource).toHaveBeenCalledWith("demo");
    await user.click(within(mine).getByRole("button", { name: "More actions for Demo Mail" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Sign out", "Sign in again"]);
  });
});

test("each template lists what it adds as short lists, and one already set up says so instead of offering Apply", async () => {
  api([step("template")]);
  open();
  const book = (await screen.findByText("Book project")).closest("li") as HTMLElement;
  const chapters = within(book).getByText("Chapters").closest("li") as HTMLElement;
  expect(within(chapters).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Fields: Title, Length", "Steps: Outline → Draft → Final"]);
  // A kind with no fields or steps is just named.
  const notes = within(book).getByText("Notes").closest("li") as HTMLElement;
  expect(within(notes).queryAllByRole("listitem")).toHaveLength(0);
  expect(within(book).getByRole("button", { name: "Apply Book project" })).toBeInTheDocument();
  const trip = screen.getByText("Trip").closest("li") as HTMLElement;
  expect(trip).toHaveTextContent("Already set up");
  expect(within(trip).queryByRole("button")).toBeNull();
  expect(within(trip).getByText("Fields: Where")).toBeInTheDocument();
  expect(within(trip).queryByText(/^Steps:/)).toBeNull();
});

test("the step says plainly that applying turns on item types and may need a restart, which is asked first", async () => {
  api([step("template")]);
  open();
  expect(await screen.findByText(/Applying one turns on the item types it lists and may need a restart; the app asks you first\./)).toBeInTheDocument();
});

const installed = (name: string, enabled: boolean): S["InstalledPackView"] =>
  ({ name, enabled, state: enabled ? "enabled" : "disabled", description: "", reason: null, version: "1.0.0" }) as S["InstalledPackView"];

test("the add-ons step says what add-ons do, names the ones installed but off, and opens the Add-ons screen", async () => {
  const user = userEvent.setup();
  api([step("addons")], {
    "GET packs": () => ({
      enabled: true,
      feeds: [],
      available: [],
      installed: [installed("mail-sample", false), installed("calendar-sample", true), installed("notes-sample", false)],
    }),
  });
  const { onOpenAddons } = open();
  const addons = await screen.findByRole("heading", { name: "Turn on your add-ons" });
  expect(addons).toBeInTheDocument();
  expect(section("addons")).toHaveTextContent(
    "Add-ons connect the assistant to your mail, calendar and other tools. Turn on the ones you installed, then sign in to them.",
  );
  const off = await within(section("addons")).findByRole("list", { name: "Installed but turned off" });
  expect(within(off).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Mail sample", "Notes sample"]);
  await user.click(within(section("addons")).getByRole("button", { name: "Open Add-ons" }));
  expect(onOpenAddons).toHaveBeenCalledTimes(1);
});

test("Leave the rest off keeps the installed add-ons off, says so, and refreshes the guide", async () => {
  const user = userEvent.setup();
  let left = false;
  const calls = api([step("addons", { done: left })], {
    "GET packs": () => ({ enabled: true, feeds: [], available: [], installed: [installed("mail-sample", false), installed("calendar-sample", true)] }),
    "POST setup/addons/leave-off": () => {
      left = true;
      return { ok: true };
    },
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Leave the rest off" }));
  expect(await screen.findByText("Left the rest off. You can turn them on any time in Add-ons.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST setup/addons/leave-off")).toHaveLength(1);
  // The guide is read again after it.
  await waitFor(() => expect(calls.filter((c) => c.route === "GET setup").length).toBeGreaterThan(1));
});

test("the add-ons step has no Leave the rest off when nothing is waiting to be turned on", async () => {
  api([step("addons")], {
    "GET packs": () => ({ enabled: true, feeds: [], available: [], installed: [installed("calendar-sample", true)] }),
  });
  open();
  await screen.findByRole("button", { name: "Open Add-ons" });
  expect(screen.queryByRole("button", { name: "Leave the rest off" })).toBeNull();
});

test("the add-ons step still has its button when nothing is installed or the list didn't load", async () => {
  api([step("addons")]);
  open();
  expect(await screen.findByRole("button", { name: "Open Add-ons" })).toBeInTheDocument();
  expect(screen.queryByText("Installed but turned off")).toBeNull();
});
