import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { useToasts } from "../lib/toasts";
import { App } from "../App";
import { Refuse, fakeApi, rcFixture, renderApp, setupStep as step, setupView, statusFixture } from "../test-utils";
import { Walkthrough } from "./Walkthrough";

const CORE = ["workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons"];
const SETTINGS = [
  {
    key: "ai.budgets.confirm_above_usd",
    file: "ai",
    group: "ai.budgets",
    description: "Ask for a go above this.",
    type: "number",
    options: [],
    value: 0.1,
    default: 0.1,
    source: "default",
    locked: false,
    basic: true,
    editable: true,
  },
  {
    key: "ai.budgets.per_day_usd",
    file: "ai",
    group: "ai.budgets",
    description: "Stop for the day above this.",
    type: "number",
    options: [],
    value: 2,
    default: 2,
    source: "default",
    locked: false,
    basic: true,
    editable: true,
  },
  {
    key: "workspace.name",
    file: "workspace",
    group: "workspace",
    description: "The workspace's name.",
    type: "text",
    options: [],
    value: "Workspace",
    default: "Workspace",
    source: "default",
    locked: false,
    basic: true,
    editable: true,
  },
  {
    key: "workspace.user.timezone",
    file: "workspace",
    group: "workspace",
    description: "Your time zone.",
    type: "text",
    options: [],
    value: "UTC",
    default: "UTC",
    source: "default",
    locked: false,
    basic: true,
    editable: true,
  },
] as S["SettingItem"][];

const NOTHING = { adds: { item_types: [], screens: 0, today: 0, ai_work: 0, actions: 0, setup_steps: 0, sources: 2 } };
const what = (over: Partial<S["PackSummary"]> = {}): S["PackSummary"] => ({
  ...NOTHING,
  reaches: { sign_ins: ["account"], hosts: ["api.service.example.com"], programs: [], keys: 0 },
  keeps: "internal",
  reads: ["mail", "calendar"],
  ...over,
});

const available = (id: string, over: Partial<S["PackView"]> = {}): S["PackView"] => ({
  id,
  name: `Service ${id}`,
  summary: `Reads from service ${id}.`,
  publisher: "Example",
  maintainers: true,
  updated: "",
  version: "1.0.0",
  price: { model: "free", amount: null, currency: "USD", period: null, note: "" },
  homepage: null,
  homepage_domain: null,
  install: "",
  demo: false,
  compatible: true,
  installed_version: null,
  enabled: false,
  what: what(),
  costs: [],
  feed: "catalog.example.com",
  installable: true,
  removable: false,
  ...over,
});

const installedPack = (name: string, over: Partial<S["InstalledPackView"]> = {}): S["InstalledPackView"] => ({
  name,
  version: "1.0.0",
  description: `Reads from service ${name}.`,
  enabled: false,
  state: "off",
  reason: null,
  what: what(),
  removable: true,
  ...over,
});

const signIn = (name: string, over: Partial<S["SignInView"]> = {}): S["SignInView"] =>
  ({
    name,
    label: "The account",
    status: "signed_out",
    ready: true,
    callback: "http://localhost/api/sign-ins/callback",
    allows: ["Read your mail", "Read your calendar"],
    account: null,
    missing: [],
    app: "add-on",
    app_note: null,
    can_paste: false,
    needs_secret: false,
    set_aside: false,
    default_unusable: false,
    own_app_steps: [],
    not_reading: [],
    ...over,
  }) as S["SignInView"];

const source = (id: string, label: string, over: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] => ({
  id,
  label,
  connector: "x/y",
  connector_label: "",
  reads: ["mail"],
  enabled: true,
  every_minutes: 15,
  items: 0,
  last: null,
  read_at: null,
  failures: 0,
  problem: null,
  ...over,
});

/** The routes every screen of the walkthrough reads, answered with nothing set up. */
function routes(over: Record<string, (body: unknown) => unknown> = {}, steps = CORE.map((id) => step(id)), walk: Partial<S["WalkthroughView"]> = {}) {
  return {
    "GET setup": () => setupView(steps, { walkthrough: { open: true, ...walk } }),
    "GET settings": () => ({ fingerprint: "fp-1", items: SETTINGS }),
    "GET me": () => ({ person: null, full_name: "" }),
    "GET ai/endpoints": () => [],
    "GET ai/accounts": () => [],
    "GET ai/local": () => [],
    "GET packs": () => ({ enabled: true, feeds: [], available: [], installed: [] }),
    "GET sign-ins": () => [],
    "GET watch": () => [],
    "GET status": () => statusFixture(),
    "GET templates": () => [],
    "POST setup/walkthrough": (body: unknown) => ({ open: true, step: "you", closed: false, finished: false, ...(body as object) }),
    ...over,
  };
}

/** One service the AI screen offers, made up; the address is built so none is written out whole. */
const SERVICE: S["EndpointView"] = {
  id: "service-a",
  name: "Service A",
  adapter: "adapter-one",
  base_url: `${"https" + "://"}api.service-a.example.com/v1`,
  key_url: "",
  needs_key: true,
  local: false,
  note: "Pay as you go.",
  allowed_data: ["open"],
  program: "",
  model_examples: [],
  model_optional: false,
  recommended: true,
};
const WITH_SERVICE = { "GET ai/endpoints": () => [SERVICE] };

const handlers = () => ({
  onOpenPeople: vi.fn(),
  onOpenAddons: vi.fn(),
  onHandIn: vi.fn(),
  onChooseSource: vi.fn(),
  onFinishLater: vi.fn(),
  onDone: vi.fn(),
});

function open(props: { at?: { screen: S["WalkthroughView"]["step"]; n: number } | null; hellos?: number } = {}) {
  const h = handlers();
  const view = renderApp(
    <RestartProvider hellos={props.hellos ?? 1} pollSeconds={0.05} doneSeconds={0.05}>
      <Walkthrough at={props.at ?? null} {...h} />
    </RestartProvider>,
  );
  return { ...h, ...view };
}

const screenTitle = () => screen.findByRole("heading", { level: 2 });

describe("opening", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  test("it opens by itself on a fresh workspace, with the introduction", async () => {
    fakeApi({
      ...routes(),
      "GET panels": () => [],
      "GET asks": () => [],
      "GET changes": () => [],
      "GET followups": () => [],
      "GET runtime-config": () => ({ instance: null }),
    });
    renderApp(<App rc={rcFixture()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Set up your workspace" })).toBeInTheDocument();
    expect(screen.getByText("About 10–20 minutes. You can stop and come back.")).toBeInTheDocument();
    expect(await screenTitle()).toHaveTextContent("You");
    expect(await screen.findByLabelText("Your full name")).toBeInTheDocument();
    // The cursor starts where the person types, not on a label or the step list.
    await waitFor(() => expect(screen.getByLabelText("Your full name")).toHaveFocus());
    expect(window.location.hash).toBe("#setup");
  });

  test("it does not open by itself when the server says it should not", async () => {
    fakeApi({
      ...routes({}, CORE.map((id) => step(id)), { open: false, closed: true }),
      "GET panels": () => [],
      "GET asks": () => [],
      "GET changes": () => [],
      "GET followups": () => [],
      "GET runtime-config": () => ({ instance: null }),
      "GET today/agenda": () => [],
      "GET today/todo": () => [],
      "GET today/arrived": () => ({ items: [], left_out: 0 }),
      "GET projects": () => [],
    });
    renderApp(<App rc={rcFixture()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Today" })).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("heading", { name: "Set up your workspace" })).toBeNull();
    expect(window.location.hash).not.toBe("#setup");
  });

  test("it does not take the person from a hand-in they already started when setup is read late", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const late = new Promise<void>((resolve) => {
      release = resolve;
    });
    const base = routes();
    fakeApi({
      ...base,
      "GET setup": async () => {
        await late;
        return base["GET setup"]();
      },
      "GET panels": () => [],
      "GET asks": () => [],
      "GET changes": () => [],
      "GET followups": () => [],
      "GET runtime-config": () => ({ instance: null }),
      "GET today/agenda": () => [],
      "GET today/todo": () => [],
      "GET today/arrived": () => ({ items: [], left_out: 0 }),
      "GET projects": () => [],
    });
    renderApp(<App rc={rcFixture()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Today" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Hand something in" })[0]);
    await user.type(await screen.findByLabelText("Paste or type it here"), "Minutes from the call.");
    release();
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("heading", { name: "Set up your workspace" })).toBeNull();
    expect(screen.getByLabelText("Paste or type it here")).toHaveValue("Minutes from the call.");
  });

  test("it resumes at the screen the server kept", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "backup" }));
    open();
    expect(await screenTitle()).toHaveTextContent("Backups");
    expect(screen.getByRole("button", { name: /Backups/, current: "step" })).toBeInTheDocument();
  });

  test("a line elsewhere that sends the person to a step opens that screen and keeps it", async () => {
    const calls = fakeApi(routes());
    open({ at: { screen: "people", n: 1 } });
    expect(await screenTitle()).toHaveTextContent("People");
    await waitFor(() => expect(calls.some((c) => c.route === "POST setup/walkthrough" && (c.body as S["WalkthroughIn"]).step === "people")).toBe(true));
  });

  test("opening it again after it was closed keeps it open", async () => {
    const calls = fakeApi(routes({}, CORE.map((id) => step(id)), { open: false, closed: true }));
    open();
    await screenTitle();
    await waitFor(() =>
      expect(calls.find((c) => c.route === "POST setup/walkthrough")?.body).toMatchObject({ closed: false, finished: false }),
    );
  });

  test("opening it records the screen it shows, so it doesn't open by itself again once nothing it needs is missing", async () => {
    const calls = fakeApi(routes({}, CORE.map((id) => step(id)), { step: "people" }));
    open();
    await screenTitle();
    await waitFor(() =>
      expect(calls.find((c) => c.route === "POST setup/walkthrough")?.body).toEqual({ step: "people" }),
    );
  });

  test("where it stands is sent one request at a time, in the order the person made them", async () => {
    const user = userEvent.setup();
    fakeApi(routes({}, CORE.map((id) => step(id)), { open: false, closed: true }));
    // Answers to the keeps are held until the test lets them go, to see whether the next is sent before the last is back.
    const answer = globalThis.fetch;
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => (release = resolve));
    let sending = 0;
    let most = 0;
    const sent: S["WalkthroughIn"][] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!String(input).endsWith("setup/walkthrough")) return answer(input, init);
      sent.push(JSON.parse(String(init?.body)) as S["WalkthroughIn"]);
      sending += 1;
      most = Math.max(most, sending);
      await held;
      sending -= 1;
      return answer(input, init);
    });
    open({ at: { screen: "people", n: 1 } });
    await screenTitle();
    await waitFor(() => expect(sent.length).toBeGreaterThan(0));
    // Opening asks twice (the screen itself and the request to open at it), and the person moves on meanwhile.
    await user.click(screen.getByRole("button", { name: /^Backups/ }));
    expect(sent).toHaveLength(1);
    release();
    await waitFor(() => expect(sent).toHaveLength(3));
    expect(most).toBe(1);
    expect(sent.map((body) => body.step)).toEqual(["people", "people", "backup"]);
  });
});

describe("closing", () => {
  test("Finish later is kept on the server and closes it", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes());
    const { onFinishLater, onDone } = open();
    await screenTitle();
    await user.click(screen.getByRole("button", { name: "Finish later" }));
    await waitFor(() => expect(onFinishLater).toHaveBeenCalledTimes(1));
    expect(calls.filter((c) => c.route === "POST setup/walkthrough").at(-1)?.body).toEqual({ closed: true });
    expect(onDone).not.toHaveBeenCalled();
  });

  test("the last button keeps it as finished and closes it", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes({}, CORE.map((id) => step(id)), { step: "done" }));
    const { onDone, onFinishLater } = open();
    await user.click(await screen.findByRole("button", { name: "Go to Today" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(calls.filter((c) => c.route === "POST setup/walkthrough").at(-1)?.body).toEqual({ finished: true });
    expect(onFinishLater).not.toHaveBeenCalled();
  });

  test("the last button lands on Today with the first-go line in focus, and the walkthrough is finished", async () => {
    const user = userEvent.setup();
    window.location.hash = "#setup";
    let finished = false;
    const waiting = {
      id: "REQ-1",
      version: 3,
      dismissed: false,
      stage_task: false,
      first_go: true,
      refused: false,
      state: "needs_you",
      approval: "required",
      waiting: "Waiting for your first go.",
      estimate_usd: 0.1,
      created_at: "2026-10-09T14:00:00Z",
      note: null,
      source: null,
      source_title: "Item REQ-1",
      changeset: null,
    } as S["ChangeItem"];
    fakeApi({
      ...routes(
        {
          "GET setup": () => setupView(CORE.map((id) => step(id)), { walkthrough: { open: !finished, step: "done", finished } }),
          "POST setup/walkthrough": (body) => {
            finished = (body as S["WalkthroughIn"]).finished ?? finished;
            return { open: false, step: "done", closed: false, finished };
          },
        },
      ),
      "GET panels": () => [],
      "GET asks": () => [],
      "GET changes": () => [waiting],
      "GET today/queue": () => [
        { key: "first_go", group: "decide", kind: "first_go", count: 1, estimate_usd: 0.1, unpriced: 0, untrusted: false, actions: [], questions: [], outcome: {} },
      ],
      "GET followups": () => [],
      "GET runtime-config": () => ({ instance: null }),
      "GET today/agenda": () => [],
      "GET today/todo": () => [],
      "GET today/arrived": () => ({ items: [], left_out: 0 }),
      "GET projects": () => [],
      "GET stages/records": () => [],
      "GET stages/ready": () => [],
      "GET stages/requests": () => [],
    });
    renderApp(<App rc={rcFixture()} />);
    await user.click(await screen.findByRole("button", { name: "Go to Today" }));
    const line = await screen.findByRole("group", { name: /^Start the assistant: 1 item/ });
    await waitFor(() => expect(line).toHaveFocus());
    expect(screen.queryByRole("heading", { name: "Set up your workspace" })).toBeNull();
    expect(finished).toBe(true);
  });

  test("a closed walkthrough stays closed on Today, and Continue setup brings it back at the next step", async () => {
    const user = userEvent.setup();
    window.location.hash = "";
    let walk: Partial<S["WalkthroughView"]> = { open: false, closed: true, step: "mail" };
    const steps = CORE.map((id) => step(id, id === "workspace" || id === "ai" ? { done: true } : {}));
    fakeApi({
      ...routes({ "GET setup": () => setupView(steps, { walkthrough: walk }) }),
      "GET panels": () => [],
      "GET asks": () => [],
      "GET changes": () => [],
      "GET followups": () => [],
      "GET runtime-config": () => ({ instance: null }),
      "GET today/agenda": () => [],
      "GET today/todo": () => [],
      "GET today/arrived": () => ({ items: [], left_out: 0 }),
      "GET projects": () => [],
      "POST setup/walkthrough": (body) => {
        walk = { ...walk, open: true, closed: false, ...(body as object) };
        return { open: true, step: "mail", closed: false, finished: false, ...(body as object) };
      },
    });
    renderApp(<App rc={rcFixture()} />);
    const line = await screen.findByRole("region", { name: "Setup" });
    expect(line).toHaveTextContent("Setup 2 of 5");
    expect(screen.queryByRole("heading", { name: "Set up your workspace" })).toBeNull();
    await user.click(within(line).getByRole("button", { name: "Continue setup" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Set up your workspace" })).toBeInTheDocument();
    expect(await screenTitle()).toHaveTextContent("Mail and calendar");
  });
});

describe("toasts", () => {
  function Pusher() {
    const { push } = useToasts();
    return (
      <button type="button" onClick={() => push({ message: "Saved. Workspace name: Offsite team" })}>
        say something
      </button>
    );
  }
  const openWith = () => {
    const h = handlers();
    renderApp(
      <RestartProvider hellos={1} pollSeconds={0.05} doneSeconds={0.05}>
        <Walkthrough at={null} {...h} />
        <Pusher />
      </RestartProvider>,
    );
  };
  const region = () => screen.getByRole("region", { name: "Notifications" });

  test("what a screen said in a toast is gone when the walkthrough moves to another screen, by Continue, Back or the list", async () => {
    const user = userEvent.setup();
    fakeApi(routes({}, CORE.map((id) => step(id, id === "workspace" ? { done: true } : {})), { step: "you" }));
    openWith();
    await screenTitle();
    await user.click(screen.getByRole("button", { name: "say something" }));
    expect(within(region()).getByText("Saved. Workspace name: Offsite team")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Your AI account" })).toBeInTheDocument();
    expect(within(region()).queryByText(/Saved\./)).toBeNull();

    await user.click(screen.getByRole("button", { name: "say something" }));
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("heading", { level: 2, name: "You" })).toBeInTheDocument();
    expect(within(region()).queryByText(/Saved\./)).toBeNull();

    await user.click(screen.getByRole("button", { name: "say something" }));
    await user.click(screen.getByRole("button", { name: /^Backups/ }));
    expect(await screen.findByRole("heading", { level: 2, name: "Backups" })).toBeInTheDocument();
    expect(within(region()).queryByText(/Saved\./)).toBeNull();
  });

  test("a toast stays while the person stays on the screen that made it", async () => {
    const user = userEvent.setup();
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "you" }));
    openWith();
    await screenTitle();
    await user.click(screen.getByRole("button", { name: "say something" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(within(region()).getByText("Saved. Workspace name: Offsite team")).toBeInTheDocument();
  });

  test("a toast that arrives as the walkthrough opens at a screen is not cleared by opening", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "ai" }));
    const h = handlers();
    function Early() {
      const { push } = useToasts();
      useEffect(() => push({ message: "Signed in to Example mail." }), [push]);
      return null;
    }
    renderApp(
      <RestartProvider hellos={1} pollSeconds={0.05} doneSeconds={0.05}>
        <Early />
        <Walkthrough at={null} {...h} />
      </RestartProvider>,
    );
    await screenTitle();
    expect(within(region()).getByText("Signed in to Example mail.")).toBeInTheDocument();
  });
});

describe("each screen", () => {
  test("You: the person's name, the workspace's name and the time zone in one form", async () => {
    fakeApi(routes());
    open();
    expect(await screenTitle()).toHaveTextContent("You");
    expect(await screen.findByLabelText("Your full name")).toBeInTheDocument();
    expect(screen.getByLabelText("Workspace name")).toBeInTheDocument();
    expect(screen.getByLabelText("Your time zone")).toBeInTheDocument();
    expect(screen.getByText(/Saving adds you to People/)).toBeInTheDocument();
  });

  test("Your AI account: spending is one sentence with its starting amounts, and Continue saves a change to them", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(
      routes(
        { ...WITH_SERVICE, "POST settings": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }) },
        CORE.map((id) => step(id, id === "ai" ? { done: true } : {})),
        { step: "ai" },
      ),
    );
    open();
    expect(await screenTitle()).toHaveTextContent("Your AI account");
    const line = await screen.findByText(/It asks you before anything over/);
    expect(line).toHaveTextContent("It asks you before anything over $0.10, and stops for the day at $2.");
    await user.click(within(line).getByRole("button", { name: "Change" }));
    const confirm = screen.getByLabelText("Ask me before anything over");
    const day = screen.getByLabelText("Stop for the day at");
    expect(confirm).toHaveValue("0.1");
    expect(day).toHaveValue("2");
    expect(screen.getByText(/Starts at \$0\.10/)).toBeInTheDocument();
    expect(screen.getByText(/Starts at \$2/)).toBeInTheDocument();
    // There is no Save of its own: the screen's Continue is the one button.
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    await user.clear(day);
    await user.type(day, "5");
    await waitFor(() => expect(day).toHaveValue("5"), { timeout: 3000 });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
    expect(calls.find((c) => c.route === "POST settings")!.body).toEqual({
      changes: { "ai.budgets.per_day_usd": 5 },
      reset: [],
      fingerprint: "fp-1",
    });
    expect(await screen.findByRole("heading", { level: 2, name: "Mail and calendar" })).toBeInTheDocument();
  });

  test("a spending amount that is not a number stops Continue, and says why", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes(WITH_SERVICE, CORE.map((id) => step(id, id === "ai" ? { done: true } : {})), { step: "ai" }));
    open();
    await user.click(await screen.findByRole("button", { name: "Change" }));
    const day = screen.getByLabelText("Stop for the day at");
    await user.clear(day);
    await user.type(day, "lots");
    expect((await screen.findAllByText("Use a number, such as 0.10.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(calls.some((c) => c.route === "POST settings")).toBe(false);
  });

  test("Your AI account: Continue says what is missing until a service is chosen, and I'll do this later skips it", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes({ ...WITH_SERVICE, "POST setup/ai/skip": () => ({ ok: "ai" }) }, CORE.map((id) => step(id)), { step: "ai" }));
    open();
    await screen.findByRole("radio", { name: /Service A/ });
    const go = screen.getByRole("button", { name: "Continue" });
    expect(go).toBeDisabled();
    expect(screen.getByText("Choose an AI service to go on.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "I'll do this later" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST setup/ai/skip")).toBe(true));
  });

  test("Backups: with no drive found the folder form, and the one button says Back up now and continue", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "backup" }));
    open();
    expect(await screenTitle()).toHaveTextContent("Backups");
    expect(await screen.findByLabelText("Folder")).toBeInTheDocument();
    const go = screen.getByRole("button", { name: "Back up now and continue" });
    expect(go).toBeDisabled();
    expect(screen.getByText("Choose a folder to go on.")).toBeInTheDocument();
  });

  test("Backups: Back up now and continue saves the drive found and moves on", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(
      routes(
        {
          "GET setup/backup-folders": () => ({ folders: [{ name: "Drive One", recommended: true }], shown: "Backups › Example App" }),
          "POST setup/backup-folder/cloud": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }),
        },
        CORE.map((id) => step(id)),
        { step: "backup" },
      ),
    );
    open();
    const first = await screen.findByRole("radio", { name: /Drive One/ });
    expect(first).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Back up now and continue" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup-folder/cloud")).toBe(true));
    expect(await screen.findByRole("heading", { level: 2, name: "People" })).toBeInTheDocument();
  });

  test("People: optional, with the plain reason that skipping is fine, and a button to add them", async () => {
    const user = userEvent.setup();
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "people" }));
    const { onOpenPeople } = open();
    expect(await screenTitle()).toHaveTextContent("People");
    expect(screen.getByText(/You can skip this: names the assistant can't place become questions/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add people" }));
    expect(onOpenPeople).toHaveBeenCalledTimes(1);
  });

  test("Skip for now skips the step and moves to the next screen; Back and the list move too, and each is kept", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes({ "POST setup/people/skip": () => ({ ok: "people" }) }, CORE.map((id) => step(id)), { step: "people" }));
    open();
    await screenTitle();
    await user.click(screen.getByRole("button", { name: "I'll do this later" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Done" })).toBeInTheDocument();
    expect(calls.some((c) => c.route === "POST setup/people/skip")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("heading", { level: 2, name: "People" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Your AI account/ }));
    expect(await screen.findByRole("heading", { level: 2, name: "Your AI account" })).toBeInTheDocument();
    const kept = calls.filter((c) => c.route === "POST setup/walkthrough").map((c) => (c.body as S["WalkthroughIn"]).step);
    expect(kept).toEqual(expect.arrayContaining(["done", "people", "ai"]));
  });

  test("a screen that is done offers Continue, not I'll do this later", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id, id === "workspace" ? { done: true } : {}))));
    open();
    expect(await screen.findByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I'll do this later" })).toBeNull();
  });
});

describe("Mail and calendar", () => {
  /** A fake service that moves through the states the screen shows: not here, installed and off, on and waiting for the
   * restart, then running. The restart changes the app's start so the screen sees it come back. */
  function service(start: "none" | "off" | "on", over: { signed?: boolean } = {}) {
    const state = { here: start !== "none", enabled: start === "on", running: start === "on", signed: !!over.signed, restarted: 0 };
    const id = "mail-addon";
    const login = "http://localhost:9090/login?x=1";
    const calls = fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [available(id, { installed_version: state.here ? "1.0.0" : null, enabled: state.enabled })],
        installed: state.here
          ? [installedPack(id, { enabled: state.enabled, state: state.running ? "enabled" : "off" })]
          : [],
      }),
      "POST packs/mail-addon/install": () => {
        state.here = true;
        return { name: id, version: "1.0.0", needs_restart: true };
      },
      "POST packs/mail-addon/on": () => {
        state.enabled = true;
        return { changes: [], fingerprint: "fp-2", needs_restart: true };
      },
      "GET status": () => statusFixture({ can_restart: true }),
      "POST restart": () => {
        // The app is gone for a moment and comes back as a new start.
        setTimeout(() => {
          state.restarted += 1;
          state.running = state.enabled;
        }, 150);
        return { restarting: true };
      },
      "GET runtime-config": () => ({ instance: `start-${state.restarted}` }),
      "GET sign-ins": () => (state.running ? [signIn(`${id}/account`, state.signed ? { status: "signed_in", account: "me@example.com" } : {})] : []),
      "POST sign-ins/mail-addon/account/start": () => ({ url: login }),
      "GET watch": () =>
        state.signed ? [source("s1", "Your inbox"), source("s2", "Your calendar", { reads: ["calendar"] })] : [],
    });
    return { calls, state, login };
  }

  let assign: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const row = async () => (await screen.findByText("Service mail-addon")).closest("li") as HTMLElement;

  test("a service that is not installed: one button installs it and turns it on, then one restart, then Sign in", async () => {
    const user = userEvent.setup();
    const { calls, login } = service("none");
    open();
    expect(await screenTitle()).toHaveTextContent("Mail and calendar");
    const mine = await row();
    expect(within(mine).getByText("Reads your mail and calendar")).toBeInTheDocument();
    expect(within(mine).getByText(/Not on this computer yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Restart to connect/ })).toBeNull();
    await user.click(within(mine).getByRole("button", { name: "Install and connect Service mail-addon" }));
    await waitFor(() => expect(within(mine).getByText("Ready after the restart below.")).toBeInTheDocument());
    const routesCalled = calls.map((c) => c.route);
    expect(routesCalled.indexOf("POST packs/mail-addon/install")).toBeLessThan(routesCalled.indexOf("POST packs/mail-addon/on"));
    expect(calls.find((c) => c.route === "POST packs/mail-addon/on")!.body).toEqual({ fingerprint: "fp-1" });
    // Nothing restarts until the person presses the one button.
    expect(calls.some((c) => c.route === "POST restart")).toBe(false);
    expect(screen.getAllByRole("button", { name: "Restart to connect (a few seconds)" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Restart to connect (a few seconds)" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
    // After the restart the next action is Sign in.
    const signInButton = await screen.findByRole("button", { name: "Sign in to The account" });
    expect(screen.queryByRole("button", { name: /Restart to connect/ })).toBeNull();
    expect(calls.filter((c) => c.route === "POST restart")).toHaveLength(1);
    await user.click(signInButton);
    await waitFor(() => expect(assign).toHaveBeenCalledWith(login));
  });

  test("a service installed but off: one button turns it on, with no install, then the restart, then Sign in", async () => {
    const user = userEvent.setup();
    const { calls } = service("off");
    open();
    const mine = await row();
    expect(within(mine).getByText("Installed, but off.")).toBeInTheDocument();
    await user.click(within(mine).getByRole("button", { name: "Turn on Service mail-addon" }));
    await waitFor(() => expect(within(mine).getByText("Ready after the restart below.")).toBeInTheDocument());
    expect(calls.some((c) => c.route === "POST packs/mail-addon/install")).toBe(false);
    expect(calls.some((c) => c.route === "POST packs/mail-addon/on")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Restart to connect (a few seconds)" }));
    expect(await screen.findByRole("button", { name: "Sign in to The account" })).toBeInTheDocument();
  });

  test("a service that is on goes straight to Sign in, with no restart in the way", async () => {
    const user = userEvent.setup();
    const { calls, login } = service("on");
    open();
    const mine = await row();
    expect(within(mine).getByText("On. Sign in to start reading.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Restart to connect/ })).toBeNull();
    expect(within(mine).queryByRole("button", { name: /Install|Turn on/ })).toBeNull();
    await user.click(within(mine).getByRole("button", { name: "Sign in to The account" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith(login));
    expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  });

  test("a service row says in plain words what it gives and who made it, with what it reaches behind a disclosure", async () => {
    service("on");
    open();
    const mine = await row();
    expect(within(mine).getByText("Reads your mail and calendar")).toBeInTheDocument();
    expect(within(mine).getByText("Made by Example")).toBeInTheDocument();
    // The reach details are not on the row until asked for, and they are in plain words.
    const reach = within(mine).getByText("What it can access").closest("details")!;
    expect(reach).not.toHaveAttribute("open");
    expect(within(reach).getByText(/You sign in on the service's own page/)).toBeInTheDocument();
    expect(within(reach).getByText("Connects to: api.service.example.com")).toBeInTheDocument();
    for (const jargon of [/Signs in to/, /Internet:/, /Keys you provide/, /^account$/]) expect(mine.textContent).not.toMatch(jargon);
  });

  test("what a service reaches in keys and programs is said as what it needs, not as a count", async () => {
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [
          available("mail-addon", {
            what: what({ reaches: { sign_ins: ["account"], hosts: [], programs: ["a-helper"], keys: 2 } }),
          }),
        ],
        installed: [],
      }),
    });
    open();
    const reach = within(await row()).getByText("What it can access").closest("details")!;
    expect(within(reach).getByText("Runs these programs on this computer: a-helper")).toBeInTheDocument();
    expect(within(reach).getByText("Needs 2 keys from you")).toBeInTheDocument();
  });

  test("the assistant's sorting of what the rules can't place is on by default and one switch turns it off", async () => {
    const user = userEvent.setup();
    let sorting = "ai";
    const item = (value: string) =>
      ({
        key: "watch.sorting",
        file: "watch",
        group: "watch",
        description: "How unplaced mail is sorted.",
        type: "choice",
        options: ["ai", "rules"],
        value,
        default: "ai",
        source: "default",
        locked: false,
        basic: false,
        editable: true,
      }) as S["SettingItem"];
    const calls = fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET settings": () => ({ fingerprint: "fp-1", items: [...SETTINGS, item(sorting)] }),
      "POST settings": (body) => {
        const changes = (body as { changes: Record<string, string> }).changes;
        sorting = changes["watch.sorting"];
        return {
          changes: [{ key: "watch.sorting", before: "ai", after: sorting, was_default: true, is_default: false }],
          fingerprint: "fp-2",
          needs_restart: false,
        };
      },
    });
    open();
    const box = await screen.findByRole("checkbox", { name: "Set aside newsletters and personal mail automatically" });
    await waitFor(() => expect(box).toBeChecked());
    expect(screen.getByText(/not the message body/)).toBeInTheDocument();
    await user.click(box);
    await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
    expect(calls.find((c) => c.route === "POST settings")!.body).toEqual({
      changes: { "watch.sorting": "rules" },
      reset: [],
      fingerprint: "fp-1",
    });
    await waitFor(() => expect(box).not.toBeChecked());
  });

  test("a service the catalog names no publisher for shows none", async () => {
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [available("mail-addon", { publisher: "" })],
        installed: [],
      }),
    });
    open();
    expect(within(await row()).queryByText(/^Made by/)).toBeNull();
  });

  test("once signed in the row says who and what is read, offers no Sign in, and no longer says to sign in", async () => {
    service("on", { signed: true });
    open();
    const mine = await row();
    expect(await within(mine).findByText("Signed in as me@example.com")).toBeInTheDocument();
    expect(within(mine).getByText("Reading your mail and calendar.")).toBeInTheDocument();
    expect(within(mine).queryByText(/Sign in to start reading/)).toBeNull();
    expect(within(mine).queryByRole("button", { name: /^Sign in/ })).toBeNull();
    expect(mine).toHaveAttribute("data-signed-in");
  });

  test("a sign-in that has run out still offers Sign in, and the row doesn't claim to be reading", async () => {
    const { state } = service("on");
    state.signed = false;
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [available("mail-addon", { installed_version: "1.0.0", enabled: true })],
        installed: [installedPack("mail-addon", { enabled: true, state: "enabled" })],
      }),
      "GET sign-ins": () => [signIn("mail-addon/account", { status: "expired", account: "me@example.com" })],
    });
    open();
    const mine = await row();
    expect(await within(mine).findByRole("button", { name: "Sign in again to The account" })).toBeInTheDocument();
    expect(within(mine).queryByText(/^Reading your/)).toBeNull();
    expect(mine).not.toHaveAttribute("data-signed-in");
  });

  test("after signing in it says what is read now and that what it reads waits for the first Go", async () => {
    service("on", { signed: true });
    open();
    const mine = await row();
    expect(within(mine).getByText("Signed in as me@example.com")).toBeInTheDocument();
    const reading = await screen.findByText("Now reading");
    const list = reading.closest("[data-reading]") as HTMLElement;
    expect(within(list).getByText("Your inbox")).toBeInTheDocument();
    expect(within(list).getByText("Your calendar")).toBeInTheDocument();
    expect(within(list).getByText(/What it reads waits for you to start the assistant on the next screen/)).toBeInTheDocument();
  });

  test("two services turned on before the restart still need only the one restart button", async () => {
    const user = userEvent.setup();
    const ids = ["mail-addon", "second-addon"];
    const turned = new Set<string>();
    const calls = fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: ids.map((id) => available(id, { installed_version: "1.0.0", enabled: turned.has(id) })),
        installed: ids.map((id) => installedPack(id, { enabled: turned.has(id), state: "off" })),
      }),
      "POST packs/mail-addon/on": () => (turned.add("mail-addon"), { changes: [], fingerprint: "fp-2", needs_restart: true }),
      "POST packs/second-addon/on": () => (turned.add("second-addon"), { changes: [], fingerprint: "fp-3", needs_restart: true }),
      "GET status": () => statusFixture({ can_restart: true }),
    });
    open();
    await user.click(await screen.findByRole("button", { name: "Turn on Service mail-addon" }));
    await user.click(await screen.findByRole("button", { name: "Turn on Service second-addon" }));
    await waitFor(() => expect(turned.size).toBe(2));
    expect(await screen.findAllByText("Ready after the restart below.")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Restart to connect (a few seconds)" })).toHaveLength(1);
    expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  });

  test("where the app can't restart itself the step says to close and start it, and offers no restart button", async () => {
    const user = userEvent.setup();
    const state = { enabled: false };
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [available("mail-addon", { installed_version: "1.0.0", enabled: state.enabled })],
        installed: [installedPack("mail-addon", { enabled: state.enabled })],
      }),
      "POST packs/mail-addon/on": () => ((state.enabled = true), { changes: [], fingerprint: "fp-2", needs_restart: true }),
      "GET status": () => statusFixture({ can_restart: false }),
    });
    open();
    await user.click(await screen.findByRole("button", { name: "Turn on Service mail-addon" }));
    expect(await screen.findByText(/Close and reopen the app to finish adding the add-on/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Restart to connect/ })).toBeNull();
  });

  test("a refusal from the install is said on the row in the server's words, and nothing is turned on", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({ enabled: true, feeds: [], available: [available("mail-addon")], installed: [] }),
      "POST packs/mail-addon/install": () => new Refuse(409, "The release file could not be checked."),
    });
    open();
    await user.click(await screen.findByRole("button", { name: "Install and connect Service mail-addon" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The release file could not be checked.");
    expect(calls.some((c) => c.route === "POST packs/mail-addon/on")).toBe(false);
    expect(screen.queryByRole("button", { name: /Restart to connect/ })).toBeNull();
  });

  test("an add-on that reads no mail or calendar is not offered, and another mail or calendar opens the core's forms", async () => {
    const user = userEvent.setup();
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({
        enabled: true,
        feeds: [],
        available: [
          available("mail-addon"),
          available("other-addon", { what: what({ reads: [] }) }),
          available("no-sign-in-addon", { what: what({ reaches: { sign_ins: [], hosts: [], programs: [], keys: 0 } }) }),
        ],
        installed: [],
      }),
    });
    const { onChooseSource } = open();
    expect(await screen.findByText("Service mail-addon")).toBeInTheDocument();
    expect(screen.queryByText("Service other-addon")).toBeNull();
    expect(screen.queryByText("Service no-sign-in-addon")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Another mail or calendar" }));
    expect(onChooseSource).toHaveBeenCalledWith(null);
  });

  test("with no service listed the step still offers the core's mail folder and calendar address", async () => {
    fakeApi(routes({}, CORE.map((c) => step(c)), { step: "mail" }));
    open();
    expect(await screen.findByText(/No services listed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Another mail or calendar" })).toBeInTheDocument();
  });

  test("a service the app can't install from here points to the Add-ons screen", async () => {
    const user = userEvent.setup();
    fakeApi({
      ...routes({}, CORE.map((c) => step(c)), { step: "mail" }),
      "GET packs": () => ({ enabled: true, feeds: [], available: [available("mail-addon", { installable: false })], installed: [] }),
    });
    const { onOpenAddons } = open();
    await user.click(await screen.findByRole("button", { name: "How to get it" }));
    expect(onOpenAddons).toHaveBeenCalledTimes(1);
  });

  test("an add-on's own steps for mail show on this screen, not under the extras", async () => {
    fakeApi(
      routes(
        {},
        [...CORE.map((c) => step(c)), step("demo/tidy", { label: "Choose which folders to read", plugin: "demo", group: "mail" })],
        { step: "mail" },
      ),
    );
    open();
    expect(await screen.findByRole("heading", { name: "Choose which folders to read" })).toBeInTheDocument();
  });
});

describe("Done", () => {
  const steps = (over: Record<string, Partial<S["SetupStepView"]>>) =>
    CORE.map((id) => step(id, over[id] ?? {}));

  test("it lists what was set up and what was skipped, each skipped item with a Set up button that goes to its screen", async () => {
    const user = userEvent.setup();
    fakeApi(
      routes({}, steps({ workspace: { done: true }, ai: { done: true }, mail: { skipped: true }, backup: { done: true }, people: { skipped: true } }), {
        step: "done",
      }),
    );
    open();
    const recap = await screen.findByRole("list", { name: "What was set up" });
    const item = (id: string) => recap.querySelector(`[data-step="${id}"]`) as HTMLElement;
    expect(item("workspace")).toHaveTextContent("You");
    expect(item("workspace")).toHaveTextContent("Done");
    expect(item("ai")).toHaveTextContent("Done");
    expect(item("mail")).toHaveTextContent("Mail and calendar");
    expect(item("mail")).toHaveTextContent("Skipped");
    expect(item("people")).toHaveTextContent("Skipped");
    expect(within(item("workspace")).queryByRole("button")).toBeNull();
    expect(within(item("mail")).getByRole("button", { name: "Set up: Mail and calendar" })).toBeInTheDocument();
    await user.click(within(item("people")).getByRole("button", { name: "Set up: People" }));
    expect(await screen.findByRole("heading", { level: 2, name: "People" })).toBeInTheDocument();
  });

  test("it shows the optional extras and they do not count: the last button is there with them undone", async () => {
    fakeApi(
      routes({ "GET templates": () => [{ id: "tpl-a", name: "Book project", description: "Chapters and drafts.", set_up: false, adds: [] }] }, steps({}), {
        step: "done",
      }),
    );
    open();
    const extras = await screen.findByRole("region", { name: "Optional extras" });
    expect(await within(extras).findByText("Book project")).toBeInTheDocument();
    expect(within(extras).getByRole("heading", { name: "What kind of work is this?" })).toBeInTheDocument();
    expect(within(extras).getByRole("heading", { name: "Hand in a first note" })).toBeInTheDocument();
    // The counted steps are not among the extras.
    expect(within(extras).queryByRole("heading", { name: "Choose a backup folder" })).toBeNull();
    expect(screen.getByRole("button", { name: "Go to Today" })).toBeEnabled();
  });

  test("the extras include an add-on's step that is not about mail", async () => {
    fakeApi(routes({}, [...steps({}), step("demo/tidy", { label: "Connect the tidy-up tool", plugin: "demo" })], { step: "done" }));
    open();
    const extras = await screen.findByRole("region", { name: "Optional extras" });
    expect(await within(extras).findByRole("heading", { name: "Connect the tidy-up tool" })).toBeInTheDocument();
  });
});

// The look (design 7.8): the list marks only what is done or skipped and where the person is; one primary button, with
// Skip as a quiet button; and the screen's own form, as wide as what it holds.
// These walk several screens with typing, about four seconds each alone, so a busy machine gets more time for them.
describe("the look", { timeout: 20_000 }, () => {
  const primaries = (root: HTMLElement) => Array.from(root.querySelectorAll("button")).filter((b) => /primary/.test(b.className) && !b.disabled);

  test("the list has no \"Not done yet\" on a row, marks done and skipped ones, and says which screen is open", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id, id === "workspace" ? { done: true } : id === "ai" ? { skipped: true } : {})), { step: "people" }));
    open();
    await screenTitle();
    const list = screen.getByRole("navigation", { name: "Setup steps" });
    expect(within(list).queryByText("Not done yet")).toBeNull();
    const row = (id: string) => list.querySelector<HTMLElement>(`[data-screen="${id}"]`)!;
    expect(row("you")).toHaveTextContent("Done");
    expect(row("ai")).toHaveTextContent("Skipped");
    const here = row("people");
    expect(here).toHaveAttribute("aria-current", "step");
    expect(here).toHaveTextContent("You are here");
    expect(within(list).getAllByText("You are here")).toHaveLength(1);
  });

  test("a screen not done yet has Continue as its one primary button, and I'll do this later is the secondary one beside it", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id)), { step: "people" }));
    open();
    await screenTitle();
    const main = screen.getByRole("main");
    expect(primaries(main).map((b) => b.textContent)).toEqual(["Continue"]);
    expect(within(main).getByRole("button", { name: "I'll do this later" })).toBeEnabled();
    expect(within(main).getByRole("button", { name: "Add people" })).toBeEnabled();
  });

  test("a screen that is done has the same primary button, Continue, and no I'll do this later", async () => {
    fakeApi(routes({}, CORE.map((id) => step(id, id === "people" ? { done: true } : {})), { step: "people" }));
    open();
    await screenTitle();
    const main = screen.getByRole("main");
    expect(primaries(main).map((b) => b.textContent)).toEqual(["Continue"]);
    expect(within(main).queryByRole("button", { name: "I'll do this later" })).toBeNull();
  });

  test("You: Continue says what is missing, then saves the form and opens the next screen", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes({ "POST settings": () => ({ changes: [], fingerprint: "fp-2", needs_restart: false }) }));
    open();
    const name = await screen.findByLabelText("Workspace name");
    const main = screen.getByRole("main");
    // Until something is entered Continue is off, and says why under itself.
    expect(within(main).getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(within(main).getByText("Enter your full name to go on.")).toBeInTheDocument();
    await user.clear(name);
    await user.click(name);
    await user.paste("Harbor work");
    await waitFor(() => expect(within(main).getByRole("button", { name: "Continue" })).toBeEnabled(), { timeout: 5000 });
    expect(within(main).queryByRole("button", { name: "Save and continue" })).toBeNull();
    await user.click(within(main).getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Your AI account" })).toBeInTheDocument();
    expect(calls.find((c) => c.route === "POST settings")!.body).toMatchObject({ changes: { "workspace.name": "Harbor work" } });
  });

  test("a screen that was already done also saves with Continue, and moves on", async () => {
    const user = userEvent.setup();
    let name = "Workspace";
    const calls = fakeApi(
      routes(
        {
          "GET settings": () => ({ fingerprint: "fp-1", items: SETTINGS.map((i) => (i.key === "workspace.name" ? { ...i, value: name } : i)) }),
          "POST settings": (body) => {
            name = String((body as { changes: Record<string, string> }).changes["workspace.name"]);
            return { changes: [], fingerprint: "fp-2", needs_restart: false };
          },
        },
        CORE.map((id) => step(id, id === "workspace" ? { done: true } : {})),
      ),
    );
    open();
    const box = await screen.findByLabelText("Workspace name");
    await user.clear(box);
    await user.click(box);
    await user.paste("Harbor work");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
    expect(await screen.findByRole("heading", { level: 2, name: "Your AI account" })).toBeInTheDocument();
  });

  test("a screen's Continue that couldn't save keeps the person on it", async () => {
    const user = userEvent.setup();
    fakeApi(
      routes(
        {
          "GET setup/backup-folders": () => ({ folders: [{ name: "Drive One", recommended: true }], shown: "Backups › Example App" }),
          "POST setup/backup-folder/cloud": () => new Refuse(400, "That drive isn't on this computer. Choose another folder."),
        },
        CORE.map((id) => step(id)),
        { step: "backup" },
      ),
    );
    open();
    await screen.findByRole("radio", { name: /Drive One/ });
    await user.click(screen.getByRole("button", { name: "Back up now and continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That drive isn't on this computer.");
    expect(screen.getByRole("heading", { level: 2, name: "Backups" })).toBeInTheDocument();
  });
});
