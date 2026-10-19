import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import type { SettingsSection } from "../lib/views";
import { fakeApi, renderApp } from "../test-utils";
import { Addons } from "./Addons";
import { Settings } from "./Settings";

/** What a test types where a key goes. Written so no scan takes it for a real one. */
const TYPED = "typed-" + "secret-value-1";
const MADE = "made-" + "key-value-1";

const SAVED = { changes: [], fingerprint: "fp-2", needs_restart: false } satisfies S["SettingsSaved"];

function setting(key: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  const [file] = key.split(".");
  return {
    key,
    file,
    group: key.split(".").slice(0, -1).join("."),
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

// The two settings that hold a secret reference: neither shows as a row of its own.
const ITEMS = [
  setting("storage.backups.encrypt", { secret: true, description: "Where the backup key is kept." }),
  setting("workspace.plugins.secrets", { type: "other", editable: false, description: "Each add-on's secrets." }),
  setting("storage.backups.keep", { type: "integer", value: 14, default: 14, description: "How many backups to keep." }),
];

const key = (where: S["BackupKeyView"]["where"] = "none", name: string | null = null): S["BackupKeyView"] => ({ where, name });

function routes(local: boolean, extra: Record<string, (body: unknown) => unknown> = {}) {
  return {
    "GET settings": () => ({ fingerprint: "fp-1", items: ITEMS }),
    "GET setup": () => ({ steps: [], finished: true, local, walkthrough: {} }),
    "GET backup-key": () => key(),
    "GET addon-secrets": () => [],
    ...extra,
  };
}

const openSettings = (section: SettingsSection) =>
  renderApp(<Settings section={section} onOpenGuide={() => undefined} onOpenAddons={() => undefined} onChooseSource={() => undefined} />);
const post = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

describe("the backup key", () => {
  test("is a password box with a plain warning, and no second box for the same setting", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes(true, { "POST backup-key": () => ({ ...SAVED, made: null }) }));
    openSettings("backups");
    const group = await screen.findByRole("region", { name: "Backup key" });
    expect(within(group).getByText(/If it is lost, your backups can't be read/)).toBeInTheDocument();
    const box = within(group).getByLabelText("Key for locking backups");
    expect(box).toHaveAttribute("type", "password");
    expect(screen.queryByLabelText("Where the backup key is kept.")).toBeNull();
    expect(within(group).getByRole("button", { name: "Save backup key" })).toBeDisabled();
    await user.type(box, TYPED);
    await user.click(within(group).getByRole("button", { name: "Save backup key" }));
    await waitFor(() => expect(post(calls, "POST backup-key")).toBeDefined());
    expect(post(calls, "POST backup-key")).toEqual({ value: TYPED, fingerprint: "fp-1" });
    expect(await screen.findByText("Saved the backup key.")).toBeInTheDocument();
    // The typed key is gone from the screen once it is kept.
    expect(screen.queryByDisplayValue(TYPED)).toBeNull();
  });

  test("a kept one says so, never shows it, and Replace takes a new one", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes(true, { "GET backup-key": () => key("kept"), "POST backup-key": () => ({ ...SAVED, made: null }) }));
    openSettings("backups");
    const group = await screen.findByRole("region", { name: "Backup key" });
    expect(await within(group).findByText("Kept on this computer")).toBeInTheDocument();
    expect(within(group).queryByLabelText("Key for locking backups")).toBeNull();
    expect(within(group).getByText(/Backups made before keep the key they were locked with/)).toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Replace Key for locking backups" }));
    await user.type(within(group).getByLabelText("Key for locking backups"), TYPED);
    await user.click(within(group).getByRole("button", { name: "Save backup key" }));
    await waitFor(() => expect(post(calls, "POST backup-key")).toEqual({ value: TYPED, fingerprint: "fp-1" }));
  });

  test("Make one for me shows the key once to copy, and it is gone when it is dismissed", async () => {
    const user = userEvent.setup();
    const copied = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: copied }, configurable: true });
    let kept = false;
    const calls = fakeApi(
      routes(true, {
        "GET backup-key": () => (kept ? key("kept") : key()),
        "POST backup-key": () => {
          kept = true;
          return { ...SAVED, made: MADE };
        },
      }),
    );
    openSettings("backups");
    const group = await screen.findByRole("region", { name: "Backup key" });
    await user.click(await within(group).findByRole("button", { name: "Make one for me" }));
    await waitFor(() => expect(post(calls, "POST backup-key")).toEqual({ make: true, fingerprint: "fp-1" }));
    const shown = await within(group).findByRole("group", { name: "Your new backup key" });
    expect(within(shown).getByDisplayValue(MADE)).toHaveAttribute("readonly");
    expect(within(shown).getByText(/shown only now/)).toBeInTheDocument();
    await user.click(within(shown).getByRole("button", { name: "Copy key" }));
    expect(copied).toHaveBeenCalledWith(MADE);
    await user.click(within(shown).getByRole("button", { name: "I have copied it" }));
    expect(screen.queryByDisplayValue(MADE)).toBeNull();
    expect(await within(group).findByText("Kept on this computer")).toBeInTheDocument();
  });

  test("on a hosted app it is a place the key is kept, there is no Make one for me, and a bare name is a variable", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes(false, { "POST backup-key": () => ({ ...SAVED, made: null }) }));
    openSettings("backups");
    const group = await screen.findByRole("region", { name: "Backup key" });
    const box = await within(group).findByLabelText("Key for locking backups");
    expect(box).toHaveAttribute("type", "text");
    expect(within(group).queryByRole("button", { name: "Make one for me" })).toBeNull();
    await user.type(box, "BACKUP_KEY");
    await user.click(within(group).getByRole("button", { name: "Save backup key" }));
    await waitFor(() => expect(post(calls, "POST backup-key")).toEqual({ reference: "env:BACKUP_KEY", fingerprint: "fp-1" }));
  });
});

describe("an add-on's own keys", () => {
  const NEEDS: S["AddonSecretsView"][] = [
    {
      plugin: "keyed",
      secrets: [
        { secret: "api-key", where: "none", name: null },
        { secret: "client-secret", where: "kept", name: null },
      ],
    },
  ];
  const addonRoutes = (local = true) =>
    routes(local, {
      "GET addon-secrets": () => NEEDS,
      "POST addons/keyed/secrets/api-key": () => SAVED,
      "POST addons/keyed/secrets/client-secret": () => SAVED,
    });

  test("the add-on has a Settings section with a password box for each key it needs, even with no settings of its own", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(addonRoutes());
    openSettings("addon/keyed");
    const group = await screen.findByRole("region", { name: "Keys this add-on needs" });
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(nav).getByRole("link", { name: "Keyed" })).toHaveAttribute("aria-current", "page");
    const box = within(group).getByLabelText("Api key");
    expect(box).toHaveAttribute("type", "password");
    expect(within(group).getByText("Kept on this computer")).toBeInTheDocument();
    await user.type(box, TYPED);
    await user.click(within(group).getByRole("button", { name: "Save Api key" }));
    await waitFor(() => expect(post(calls, "POST addons/keyed/secrets/api-key")).toEqual({ value: TYPED, fingerprint: "fp-1" }));
    expect(screen.queryByText("Each add-on's secrets.")).toBeNull();
  });

  test("a kept one is replaced with Replace, and a hosted app takes only where it is kept", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(addonRoutes());
    openSettings("addon/keyed");
    const group = await screen.findByRole("region", { name: "Keys this add-on needs" });
    await user.click(await within(group).findByRole("button", { name: "Replace Client secret" }));
    await user.type(within(group).getByLabelText("Client secret"), TYPED);
    await user.click(within(group).getByRole("button", { name: "Save Client secret" }));
    await waitFor(() => expect(post(calls, "POST addons/keyed/secrets/client-secret")).toEqual({ value: TYPED, fingerprint: "fp-1" }));
  });

  test("on a hosted app the box names where the key is kept", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(addonRoutes(false));
    openSettings("addon/keyed");
    const group = await screen.findByRole("region", { name: "Keys this add-on needs" });
    const box = within(group).getByLabelText("Api key");
    expect(box).toHaveAttribute("type", "text");
    await user.type(box, "API_KEY");
    await user.click(within(group).getByRole("button", { name: "Save Api key" }));
    await waitFor(() => expect(post(calls, "POST addons/keyed/secrets/api-key")).toEqual({ reference: "env:API_KEY", fingerprint: "fp-1" }));
  });

  test("the Add-ons screen shows them on the add-on's own row, and nothing for one that needs none", async () => {
    const what = {
      adds: { item_types: [], screens: 0, today: 0, ai_work: 0, actions: 0, setup_steps: 0, sources: 0 },
      reaches: { sign_ins: [], hosts: [], programs: [], keys: 2 },
      keeps: "open",
    } satisfies S["PackSummary"];
    const installed = (name: string) => ({ name, version: "1.0.0", description: "", enabled: true, state: "enabled", reason: null, removable: false, what });
    fakeApi({
      ...addonRoutes(),
      "GET packs": () => ({ enabled: true, feeds: [], available: [], installed: [installed("keyed"), installed("plain")] }),
    });
    const user = userEvent.setup();
    renderApp(<Addons onBack={() => undefined} />);
    await user.click(screen.getByRole("tab", { name: "Installed" }));
    const keyed = (await screen.findByText("keyed")).closest("li")!;
    expect(await within(keyed).findByLabelText("Api key")).toHaveAttribute("type", "password");
    const plain = screen.getByText("plain").closest("li")!;
    expect(within(plain).queryByRole("region", { name: "Keys this add-on needs" })).toBeNull();
  });
});
