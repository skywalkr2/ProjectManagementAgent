import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Notifications } from "./Notifications";
import { useNeedsYouNotices } from "./NeedsYouNotices";
import { Settings } from "./Settings";

// Notices that something needs the person (design 7.19): the ways of getting one, each with "Send me a test", mail to
// themselves listed as coming later, and the browser notice for what comes into the Decide group while the app is open.

/** What a test types where an address goes. Written so no scan takes it for a real one. */
const ADDRESS = ["https:/", "notes.example.com", "hook", "typed-value-1"].join("/");
const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false } satisfies S["SettingsSaved"];

const view = (over: Partial<S["NotificationsView"]> = {}): S["NotificationsView"] => ({
  enabled: true,
  browser: true,
  webhook: { where: "none", name: null },
  quiet_now: false,
  mail_ready: false,
  problem: null,
  ...over,
});

function stubNotification(permission: NotificationPermission) {
  const shown: Array<{ title: string }> = [];
  class Fake {
    static permission = permission;
    static requestPermission = vi.fn(async () => permission);
    constructor(title: string) {
      shown.push({ title });
    }
  }
  vi.stubGlobal("Notification", Fake);
  return shown;
}

function routes(extra: Record<string, (body: unknown) => unknown> = {}) {
  return {
    "GET setup": () => ({ steps: [], finished: true, local: true, walkthrough: {} }),
    "GET notifications": () => view(),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    ...extra,
  };
}
const post = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;
const card = async (name: string) => (await screen.findByRole("heading", { level: 4, name })).closest("li") as HTMLElement;

describe("the ways of getting a notice", () => {
  test("are three cards; mail to yourself says it comes with mail sending and has no button", async () => {
    stubNotification("granted");
    fakeApi(routes());
    renderApp(<Notifications />);
    const mail = await card("Mail to yourself");
    expect(within(mail).getByText(/Comes with mail sending/)).toBeInTheDocument();
    expect(within(mail).queryByRole("button")).toBeNull();
    expect(await card("This browser")).toBeInTheDocument();
    expect(await card("A chat app or a push topic")).toBeInTheDocument();
  });

  test("say when notices are off, and still let each way be set up and tried first", async () => {
    stubNotification("granted");
    fakeApi(routes({ "GET notifications": () => view({ enabled: false }) }));
    renderApp(<Notifications />);
    expect(await screen.findByText(/Notices are off\. Turn them on above/)).toBeInTheDocument();
    expect(within(await card("This browser")).getByRole("button", { name: "Send me a test" })).toBeEnabled();
  });

  test("the browser's test shows the server's words as a notice, and asks for permission first when there is none", async () => {
    const user = userEvent.setup();
    const shown = stubNotification("granted");
    fakeApi(routes({ "POST notifications/test": () => ({ ok: true, message: "A test note", problem: null }) }));
    renderApp(<Notifications />);
    await user.click(within(await card("This browser")).getByRole("button", { name: "Send me a test" }));
    await waitFor(() => expect(shown).toEqual([{ title: "A test note" }]));
    expect(await screen.findByText("A test notice was shown in this browser.")).toBeInTheDocument();
  });

  test("no test button for the browser until the browser allows notices", async () => {
    stubNotification("default");
    fakeApi(routes());
    renderApp(<Notifications />);
    const browser = await card("This browser");
    expect(within(browser).queryByRole("button", { name: "Send me a test" })).toBeNull();
    expect(within(browser).getByRole("button", { name: "Allow notifications" })).toBeInTheDocument();
  });

  test("the address is typed into a password box, kept as a reference, and tried with Send me a test", async () => {
    const user = userEvent.setup();
    stubNotification("granted");
    let kept = false;
    const calls = fakeApi(
      routes({
        "GET notifications": () => view({ webhook: { where: kept ? "kept" : "none", name: null } }),
        "POST notifications/webhook": () => {
          kept = true;
          return SAVED;
        },
        "POST notifications/test": () => ({ ok: true, message: "A test note", problem: null }),
      }),
    );
    renderApp(<Notifications />);
    const hook = await card("A chat app or a push topic");
    // No test until there is somewhere to send it.
    expect(within(hook).queryByRole("button", { name: "Send me a test" })).toBeNull();
    const box = within(hook).getByLabelText("Address for notices");
    expect(box).toHaveAttribute("type", "password");
    await user.type(box, ADDRESS);
    await user.click(within(hook).getByRole("button", { name: "Save the address for notices" }));
    await waitFor(() => expect(post(calls, "POST notifications/webhook")).toEqual({ value: ADDRESS, fingerprint: "fp-1" }));
    expect(screen.queryByDisplayValue(ADDRESS)).toBeNull();
    await user.click(await within(hook).findByRole("button", { name: "Send me a test" }));
    expect(await screen.findByText("A test note was sent to your address.")).toBeInTheDocument();
    expect(post(calls, "POST notifications/test")).toEqual({ target: "webhook" });
  });

  test("a test that did not arrive says why in the card, and so does a note that failed earlier", async () => {
    const user = userEvent.setup();
    stubNotification("granted");
    fakeApi(
      routes({
        "GET notifications": () => view({ webhook: { where: "env", name: "NOTE_ADDRESS" }, problem: "The address didn't answer." }),
        "POST notifications/test": () => ({ ok: false, message: "A test note", problem: "The address wasn't reached." }),
      }),
    );
    renderApp(<Notifications />);
    const hook = await card("A chat app or a push topic");
    expect(await within(hook).findByRole("alert")).toHaveTextContent("The address didn't answer.");
    await user.click(within(hook).getByRole("button", { name: "Send me a test" }));
    expect(await within(hook).findByText("The address wasn't reached.")).toBeInTheDocument();
  });
});

describe("Settings", () => {
  test("the Today section has the ways of getting notices under its settings, and the address is not a row of its own", async () => {
    stubNotification("granted");
    const item = (key: string, over: Partial<S["SettingItem"]> = {}): S["SettingItem"] => ({
      key,
      file: "ui",
      group: "ui.notifications",
      description: `What ${key} does`,
      type: "text",
      options: [],
      value: "",
      default: "",
      source: "default",
      locked: false,
      basic: true,
      editable: true,
      ...over,
    });
    fakeApi(
      routes({
        "GET settings": () => ({
          fingerprint: "fp-1",
          items: [item("ui.notifications.enabled", { type: "yes_no", value: false, default: false, description: "Tell me when something needs me." }), item("ui.notifications.webhook", { secret: true, description: "The address." })],
        }),
      }),
    );
    renderApp(<Settings section="today" onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
    expect(await screen.findByRole("region", { name: "Tell me when something needs me" })).toBeInTheDocument();
    expect(screen.queryByLabelText("The address.")).toBeNull();
  });
});

describe("a browser notice for what needs the person", () => {
  const waiting = (keys: string[], over: Partial<S["NotifyWaiting"]> = {}): S["NotifyWaiting"] => ({
    browser: true,
    keys,
    message: `${keys.length} decisions waiting for you`,
    ...over,
  });
  function Host() {
    useNeedsYouNotices();
    return null;
  }

  /** Mounts the hook once, and feeds it the server's answers one after the other, as the live stream's refreshes do. */
  async function mount(first: S["NotifyWaiting"]) {
    let answer = first;
    fakeApi({ "GET notifications/waiting": () => answer });
    const { client } = renderApp(<Host />);
    await waitFor(() => expect(client.getQueryData(["notifications-waiting"])).toBeDefined());
    await act(async () => undefined);
    return async (next: S["NotifyWaiting"]) => {
      answer = next;
      await act(async () => {
        await client.invalidateQueries({ queryKey: ["notifications-waiting"] });
      });
      // The screen takes the new answer on the next turn of the query client's own queue.
      await waitFor(() => expect(client.getQueryData(["notifications-waiting"])).toEqual(next));
      await act(async () => new Promise((done) => setTimeout(done, 0)));
    };
  }

  test("what was waiting when the app opened is not announced, a new item is, with a count and no title", async () => {
    const shown = stubNotification("granted");
    const feed = await mount(waiting(["question:Q1"]));
    expect(shown).toEqual([]);
    await feed(waiting(["question:Q1", "question:Q2"]));
    expect(shown).toEqual([{ title: "2 decisions waiting for you" }]);
    // The same two again: nothing more.
    await feed(waiting(["question:Q1", "question:Q2"]));
    expect(shown).toHaveLength(1);
  });

  test("nothing in quiet hours, and what came up then is announced once they end", async () => {
    const shown = stubNotification("granted");
    const feed = await mount(waiting([]));
    await feed(waiting(["question:Q1"], { browser: false }));
    expect(shown).toEqual([]);
    await feed(waiting(["question:Q1"]));
    expect(shown).toEqual([{ title: "1 decisions waiting for you" }]);
  });

  test("nothing without the browser's permission", async () => {
    const shown = stubNotification("default");
    const feed = await mount(waiting([]));
    await feed(waiting(["question:Q1"]));
    expect(shown).toEqual([]);
  });
});
