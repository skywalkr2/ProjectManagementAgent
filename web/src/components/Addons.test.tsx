import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { wordsOfWork } from "../lib/packs";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { Addons } from "./Addons";

type Pack = S["PackView"];
type Summary = S["PackSummary"];
type Packs = S["PacksView"];

const NOTHING: Summary = {
  adds: { item_types: [], screens: 0, today: 0, ai_work: 0, actions: 0, setup_steps: 0, sources: 0 },
  reaches: { sign_ins: [], hosts: [], programs: [], keys: 0 },
  keeps: "open",
};

function summary(extra: { adds?: Partial<Summary["adds"]>; reaches?: Partial<Summary["reaches"]>; keeps?: Summary["keeps"] } = {}): Summary {
  return {
    adds: { ...NOTHING.adds, ...extra.adds },
    reaches: { ...NOTHING.reaches, ...extra.reaches },
    keeps: extra.keeps ?? "open",
  };
}

const HOST = "packs.example.com";
const SITE = "print.example.com";
const LINK = "https://" + SITE + "/x";

function pack(id: string, extra: Partial<Pack> = {}): Pack {
  return {
    id,
    name: `Name of ${id}`,
    summary: `What ${id} does`,
    publisher: `Publisher of ${id}`,
    maintainers: false,
    updated: "2026-09-01",
    version: "1.0.0",
    price: { model: "free", amount: null, currency: "USD", period: null, note: "" },
    homepage: null,
    homepage_domain: null,
    install: `install ${id}`,
    demo: false,
    compatible: null,
    installed_version: null,
    removable: false,
    enabled: false,
    feed: HOST,
    what: summary(),
    costs: [],
    ...extra,
  };
}

function feed(extra: Partial<S["PackFeedView"]> = {}): S["PackFeedView"] {
  return { domain: HOST, error: null, notes: [], read_at: "2026-10-01T09:30:00+00:00", ...extra };
}

function view(extra: Partial<Packs> = {}): Packs {
  return { enabled: true, feeds: [feed()], available: [], installed: [], ...extra };
}

function open(data: Packs, more: Record<string, (body: unknown) => unknown> = {}) {
  const calls = fakeApi({ "GET packs": () => data, ...more });
  const onBack = vi.fn();
  renderApp(<Addons onBack={onBack} />);
  return { calls, onBack, user: userEvent.setup() };
}

const row = async (name: string) => (await screen.findByRole("listitem", { name })).closest("li")!;

test("the screen has Available and Installed tabs, Available first, and the arrow keys move between them", async () => {
  const { user } = open(view({ available: [pack("a")] }));
  const tabs = screen.getAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Available", "Installed"]);
  expect(screen.getByRole("tablist", { name: "Add-ons" })).toBeInTheDocument();
  expect(tabs[0]).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText("Name of a")).toBeInTheDocument();
  tabs[0].focus();
  await user.keyboard("{ArrowRight}");
  expect(tabs[1]).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toBeInTheDocument();
  expect(screen.queryByText("Name of a")).toBeNull();
});

test("Back to Settings goes back", async () => {
  const { user, onBack } = open(view());
  await user.click(screen.getByRole("button", { name: "Back to Settings" }));
  expect(onBack).toHaveBeenCalled();
});

test("each price model is written in words, with the publisher's note after it", async () => {
  const price = (model: S["PackPrice"]["model"], extra: Partial<S["PackPrice"]> = {}) => ({
    model,
    amount: null,
    currency: "USD",
    period: null,
    note: "",
    ...extra,
  });
  open(
    view({
      available: [
        pack("free", { price: price("free") }),
        pack("once", { price: price("one_time", { amount: 12 }) }),
        pack("month", { price: price("subscription", { amount: 4.5, period: "month" }) }),
        pack("year", { price: price("subscription", { amount: 40, period: "year" }) }),
        pack("see", { price: price("see_publisher") }),
        pack("noted", { price: price("free", { note: "Support is extra" }) }),
        pack("euro", { price: price("one_time", { amount: 9, currency: "EUR" }) }),
      ],
    }),
  );
  expect(await within(await row("Name of free")).findByText("Free")).toBeInTheDocument();
  expect(within(await row("Name of once")).getByText("$12.00 one time")).toBeInTheDocument();
  expect(within(await row("Name of month")).getByText("$4.50 a month")).toBeInTheDocument();
  expect(within(await row("Name of year")).getByText("$40.00 a year")).toBeInTheDocument();
  expect(within(await row("Name of see")).getByText("Price on the publisher's page")).toBeInTheDocument();
  expect(within(await row("Name of noted")).getByText("Free · Support is extra")).toBeInTheDocument();
  expect(within(await row("Name of euro")).getByText("9.00 EUR one time")).toBeInTheDocument();
});

test("the header says who made it, the publisher, when it was updated and whether it works with this version", async () => {
  open(
    view({
      available: [
        pack("mine", { maintainers: true, compatible: true }),
        pack("theirs", { compatible: false }),
        pack("unknown", { compatible: null }),
      ],
    }),
  );
  const mine = await row("Name of mine");
  expect(mine).toHaveTextContent("Made by the app's developers · Publisher of mine · updated 2026-09-01 · Works with this version");
  expect(await row("Name of theirs")).toHaveTextContent("Made by someone else · Publisher of theirs · updated 2026-09-01 · Needs a different version of the app");
  const unknown = await row("Name of unknown");
  expect(unknown).toHaveTextContent("Made by someone else · Publisher of unknown · updated 2026-09-01");
  expect(unknown).not.toHaveTextContent("Works with");
  expect(unknown).not.toHaveTextContent("Needs a different");
  expect(within(mine).getByText("What mine does")).toBeInTheDocument();
});

test("Adds, Reaches and Keeps are short lists in plain words, and zeros are left out", async () => {
  open(
    view({
      available: [
        pack("full", {
          what: summary({
            adds: { item_types: ["book", "chapter"], screens: 1, today: 1, ai_work: 2, actions: 3, setup_steps: 1, sources: 2 },
            reaches: { sign_ins: ["print service"], hosts: [SITE, "files.example.com"], programs: ["ebook-checker"], keys: 1 },
            keeps: "restricted",
          }),
        }),
        pack("plain", { what: summary({ adds: { screens: 2 }, keeps: "internal" }) }),
        pack("open", { what: summary({ keeps: "open" }) }),
      ],
    }),
  );
  const full = await row("Name of full");
  const adds = within(full).getByRole("list", { name: "Adds" });
  expect(within(adds).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Kinds of items: book, chapter",
    "1 screen",
    "1 kind of item on Today",
    "2 kinds of AI work",
    "3 actions",
    "1 setup step",
    "2 places it keeps reading",
  ]);
  const reaches = within(full).getByRole("list", { name: "What it can access" });
  expect(within(reaches).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Signs in to: print service",
    `Websites: ${SITE}, files.example.com`,
    "Programs on this computer: ebook-checker",
    "Access keys you provide: 1",
  ]);
  expect(full).toHaveTextContent("May store private material; only approved AI accounts can read it.");

  const plain = await row("Name of plain");
  expect(within(within(plain).getByRole("list", { name: "Adds" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["2 screens"]);
  expect(within(plain).getByText("Nothing outside the app")).toBeInTheDocument();
  expect(plain).toHaveTextContent("Holds confidential material.");
  expect(plain).not.toHaveTextContent("Programs on this computer");
  expect(plain).not.toHaveTextContent("Keys you provide");

  const open_ = await row("Name of open");
  expect(open_).toHaveTextContent("Holds nothing private.");
  expect(within(open_).getByText("Nothing you would see on screen")).toBeInTheDocument();
});

test("AI cost shows a price, the size of the work, or that no account is set up", async () => {
  open(
    view({
      available: [
        pack("costly", {
          costs: [
            { label: "Drafting a chapter", tokens: 8000, usd: 0.04, account: true },
            { label: "Checking a line", tokens: 500, usd: 0.004, account: true },
            { label: "Reading a source", tokens: 13333, usd: null, account: true },
            { label: "Reviewing a book", tokens: 5000, usd: null, account: false },
          ],
        }),
        pack("free"),
      ],
    }),
  );
  const costly = await row("Name of costly");
  const list = within(costly).getByRole("list", { name: "AI work on your accounts" });
  expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Drafting a chapter: about $0.04",
    "Checking a line: about $0.004",
    "Reading a source: about 10,000 words to process",
    "Reviewing a book: no AI account set up for this yet",
  ]);
  expect(costly).not.toHaveTextContent(/tokens/i);
  expect(costly).toHaveTextContent("These are estimates");
  expect(within(await row("Name of free")).queryByText("AI work on your accounts")).toBeNull();
});

test("words of AI work are tokens at 0.75 words each, to two significant figures", () => {
  expect(wordsOfWork(13333)).toBe(10000);
  expect(wordsOfWork(2000)).toBe(1500);
  expect(wordsOfWork(1234567)).toBe(930000);
  expect(wordsOfWork(40)).toBe(30);
  expect(wordsOfWork(0)).toBe(1);
});

test("How to get it shows the install text to copy and the demo line, and Copy puts them on the clipboard", async () => {
  const { user } = open(view({ available: [pack("tool", { demo: true, install: "get-pack tool --yes" })] }));
  const tool = await row("Name of tool");
  await user.click(within(tool).getByRole("button", { name: "How to get Name of tool" }));
  const dialog = await screen.findByRole("dialog", { name: "How to get Name of tool" });
  expect(within(dialog).getByText("get-pack tool --yes")).toBeInTheDocument();
  expect(within(dialog).getByText("Try it with sample data first:")).toBeInTheDocument();
  expect(within(dialog).getByText("cockpit demo --plugin tool")).toBeInTheDocument();
  expect(within(dialog).getByText(/Read these publisher instructions before running anything/)).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Copy the install steps" }));
  expect(await navigator.clipboard.readText()).toBe("get-pack tool --yes");
  await user.click(within(dialog).getByRole("button", { name: "Copy the demo command" }));
  expect(await navigator.clipboard.readText()).toBe("cockpit demo --plugin tool");
  await user.click(within(dialog).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("copying that the browser blocks says so", async () => {
  const { user } = open(view({ available: [pack("tool")] }));
  await user.click(within(await row("Name of tool")).getByRole("button", { name: "How to get Name of tool" }));
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(await screen.findByRole("button", { name: "Copy the install steps" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/wouldn't copy it/);
});

test("the demo line is left out when the pack can't be tried in the demo or its name isn't a plain one", async () => {
  const { user } = open(
    view({ available: [pack("nodemo", { demo: false }), pack("odd; thing", { demo: true, name: "Odd one" })] }),
  );
  await user.click(within(await row("Name of nodemo")).getByRole("button", { name: "How to get Name of nodemo" }));
  expect(screen.queryByText(/made-up data/)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await user.click(within(await row("Odd one")).getByRole("button", { name: "How to get Odd one" }));
  expect(screen.queryByText(/made-up data/)).toBeNull();
});

test("the publisher's page is in the row's menu, opens in a new tab, and always shows its real domain", async () => {
  const { user } = open(view({ available: [pack("site", { homepage: `https://${SITE}/tool`, homepage_domain: SITE })] }));
  const site = await row("Name of site");
  expect(site).toHaveTextContent(`Publisher's page: ${SITE}`);
  await user.click(within(site).getByRole("button", { name: "More actions for Name of site" }));
  const link = await screen.findByRole("menuitem", { name: `Publisher's page (${SITE})` });
  expect(link).toHaveAttribute("href", `https://${SITE}/tool`);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});

test("a pack with no page, or one that isn't a web address, offers no link", async () => {
  open(
    view({
      available: [pack("none"), pack("bad", { homepage: "javascript:alert(1)", homepage_domain: "alert" })],
    }),
  );
  expect(screen.queryByRole("button", { name: "More actions for Name of none" })).toBeNull();
  await row("Name of bad");
  expect(screen.queryByRole("button", { name: "More actions for Name of bad" })).toBeNull();
  expect(document.querySelector("a[href^='javascript']")).toBeNull();
});

test("an installed pack that is off says how to turn it on, and a newer version shows as a line with the way to get it in the menu", async () => {
  const { user } = open(
    view({
      available: [
        pack("off", { installed_version: "1.0.0", enabled: false }),
        pack("old", { installed_version: "0.9.0", enabled: true, version: "1.0.0", install: "upgrade old" }),
        pack("current", { installed_version: "1.0.0", enabled: true }),
      ],
    }),
  );
  const off = await row("Name of off");
  expect(off).toHaveTextContent("Installed (version 1.0.0) and off");
  expect(within(off).getByRole("button", { name: "Turn on Name of off" })).toBeInTheDocument();
  expect(off).not.toHaveTextContent("Turn on in Settings");
  expect(within(off).queryByRole("button", { name: /How to get/ })).toBeNull();

  const old = await row("Name of old");
  expect(old).toHaveTextContent("Update available: 0.9.0 → 1.0.0");
  expect(within(old).queryByRole("button", { name: "How to get Name of old" })).toBeNull();
  await user.click(within(old).getByRole("button", { name: "More actions for Name of old" }));
  await user.click(await screen.findByRole("menuitem", { name: "How to get the update" }));
  expect(await screen.findByText("upgrade old")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

  const current = await row("Name of current");
  expect(current).toHaveTextContent("Installed (version 1.0.0) and on");
  expect(current).not.toHaveTextContent("Update available");
  expect(within(current).queryByRole("button", { name: /^Turn / })).toBeNull();
  expect(within(current).queryByRole("button")).toBeNull();
});

test("when the catalog is off, nothing is listed and the reason is given", async () => {
  open(view({ enabled: false, feeds: [] }));
  expect(await screen.findByText("The add-on catalog is turned off in Settings.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
});

test("with no catalog it says so and points to Installed", async () => {
  open(view({ feeds: [] }));
  expect(
    await screen.findByText("No add-on catalog is connected. Installed add-ons still appear under Installed."),
  ).toBeInTheDocument();
});

test("a catalog with no packs says none are listed yet", async () => {
  open(view());
  expect(await screen.findByText("No add-ons are listed yet.")).toBeInTheDocument();
  expect(screen.getByText(`${HOST} · read`, { exact: false })).toBeInTheDocument();
});

test("a catalog that couldn't be read is not described as having no packs, and says why", async () => {
  open(view({ feeds: [feed({ error: "couldn't read it (outage): the host is down", read_at: null })] }));
  expect(await screen.findByText("The catalog couldn't be read: no add-ons are listed. Check the reason below, then refresh.")).toBeInTheDocument();
  expect(screen.queryByText("No add-ons are listed yet.")).toBeNull();
  expect(screen.getByText("This catalog couldn't be read: couldn't read it (outage): the host is down")).toBeInTheDocument();
});

test("with one catalog read and another failing, the list is still just empty", async () => {
  open(view({ feeds: [feed(), feed({ domain: "other.example.com", error: "it isn't a catalog file" })] }));
  expect(await screen.findByText("No add-ons are listed yet.")).toBeInTheDocument();
});

test("each catalog shows its domain and when it was read, an error in words, and its notes behind a disclosure", async () => {
  const { user } = open(
    view({
      available: [pack("a")],
      feeds: [
        feed({ read_at: null, error: "It could not be reached", notes: ["Skipped one entry", "Skipped another"] }),
        feed({ domain: "more.example.com" }),
      ],
    }),
  );
  expect(await screen.findByText(`${HOST} · not read yet`)).toBeInTheDocument();
  expect(screen.getByText("This catalog couldn't be read: It could not be reached")).toBeInTheDocument();
  expect(screen.getByText(/^more\.example\.com · read /)).toBeInTheDocument();
  const summary = screen.getByText("2 notes");
  const details = summary.closest("details")!;
  expect(details).not.toHaveAttribute("open");
  await user.click(summary);
  expect(details).toHaveAttribute("open");
  expect(within(details).getByText("Skipped one entry")).toBeVisible();
});

test("Refresh calls the route and shows what it returns", async () => {
  const { user, calls } = open(view({ available: [pack("a")] }), {
    "POST packs/refresh": () => view({ available: [pack("a"), pack("b")] }),
  });
  await screen.findByText("Name of a");
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByText("Name of b")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST packs/refresh")).toHaveLength(1);
});

test("a refresh that fails says so", async () => {
  const { user } = open(view({ available: [pack("a")] }));
  await screen.findByText("Name of a");
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByText("Name of a")).toBeInTheDocument();
});

test("Installed lists one row per pack with its version, description, status and what it adds, reaches and keeps", async () => {
  const { user } = open(
    view({
      installed: [
        {
          name: "alpha",
          version: "0.2.0",
          description: "Does alpha things",
          enabled: true,
          state: "enabled",
          reason: null,
          removable: false,
          what: summary({ adds: { screens: 1 }, reaches: { hosts: [SITE] }, keeps: "restricted" }),
        },
        { name: "beta", version: null, description: "", enabled: false, state: "off", reason: null, removable: false, what: summary() },
        {
          name: "gamma",
          version: "1.0.0",
          description: "Needs more",
          enabled: true,
          state: "disabled",
          reason: "it needs a newer version of the app",
          removable: false,
          what: summary(),
        },
      ],
    }),
  );
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  const alpha = await row("alpha");
  expect(alpha).toHaveTextContent("Version 0.2.0");
  expect(alpha).toHaveTextContent("Does alpha things");
  expect(alpha).toHaveTextContent("On and running");
  expect(within(alpha).getByRole("list", { name: "Adds" })).toHaveTextContent("1 screen");
  expect(within(alpha).getByRole("list", { name: "What it can access" })).toHaveTextContent(`Websites: ${SITE}`);
  expect(alpha).toHaveTextContent("May store private material");
  expect(await row("beta")).toHaveTextContent("Off");
  expect(await row("gamma")).toHaveTextContent("Turned off because: it needs a newer version of the app");
  expect(screen.getAllByRole("listitem", { name: /^(alpha|beta|gamma)$/ })).toHaveLength(3);
});

test("Installed with nothing installed says so", async () => {
  const { user } = open(view());
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  expect(await screen.findByText("No add-ons are installed.")).toBeInTheDocument();
});

test("text from a catalog is shown as text: markup stays literal and nothing in it becomes a link", async () => {
  open(
    view({
      available: [
        pack("risky", {
          name: "<i>Risky</i>",
          summary: `Does <b>bold</b> things. See ${LINK}`,
          publisher: "<u>Someone</u>",
          price: { model: "free", amount: null, currency: "USD", period: null, note: "<script>x</script>" },
          costs: [{ label: "<em>Work</em>", tokens: 100, usd: 0.5, account: true }],
        }),
      ],
      feeds: [feed({ notes: ["<b>note</b>"], error: "<b>bad</b>" })],
    }),
  );
  expect(await screen.findByText(`Does <b>bold</b> things. See ${LINK}`)).toBeInTheDocument();
  expect(screen.getByText("<i>Risky</i>")).toBeInTheDocument();
  expect(screen.getByText(/<u>Someone<\/u>/)).toBeInTheDocument();
  expect(screen.getByText(/<script>x<\/script>/)).toBeInTheDocument();
  expect(screen.getByText("<em>Work</em>: about $0.50")).toBeInTheDocument();
  expect(screen.getByText(/<b>bad<\/b>/)).toBeInTheDocument();
  const main = document.body;
  expect(main.querySelector("b, i, u, em, script")).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
});

test("the screen says when the add-ons can't be loaded and tries again", async () => {
  fakeApi({});
  renderApp(<Addons onBack={() => undefined} />);
  expect(await screen.findByText(/The add-ons couldn't be loaded\./)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

const SAVED = (needsRestart: boolean) => ({
  changes: [{ key: "workspace.plugins.enabled", before: [], after: ["beta"], was_default: true, is_default: false }],
  fingerprint: "fp-2",
  needs_restart: needsRestart,
});
const installedRows = (enabled: boolean): Packs["installed"] => [
  { name: "beta", version: "1.0.0", description: "", enabled, state: enabled ? "enabled" : "off", reason: null, removable: false, what: summary() },
];

test("an installed add-on that is off has Turn on as its one action: it acts at once with the fingerprint, and reads back with Undo", async () => {
  const calls = open(view({ installed: installedRows(false) }), {
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST packs/beta/on": () => SAVED(true),
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
  });
  await calls.user.click(await screen.findByRole("tab", { name: "Installed" }));
  const beta = await row("beta");
  expect(within(beta).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Turn on beta"]);
  await calls.user.click(within(beta).getByRole("button", { name: "Turn on beta" }));
  await waitFor(() => expect(calls.calls.find((c) => c.route === "POST packs/beta/on")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("Turned on beta.")).toBeInTheDocument();
  await calls.user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.calls.some((c) => c.route === "POST settings")).toBe(true));
  // Nothing restarts by itself.
  expect(calls.calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("a turned-on add-on offers Turn off, and a catalog row that is installed but off has the button instead of the hint", async () => {
  const calls = open(
    view({ installed: installedRows(true), available: [pack("off", { installed_version: "1.0.0", enabled: false })] }),
    {
      "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
      "POST packs/beta/off": () => SAVED(false),
      "POST packs/off/on": () => SAVED(false),
    },
  );
  const off = await row("Name of off");
  await calls.user.click(within(off).getByRole("button", { name: "Turn on Name of off" }));
  await waitFor(() => expect(calls.calls.some((c) => c.route === "POST packs/off/on")).toBe(true));
  await calls.user.click(await screen.findByRole("tab", { name: "Installed" }));
  await calls.user.click(within(await row("beta")).getByRole("button", { name: "Turn off beta" }));
  await waitFor(() => expect(calls.calls.find((c) => c.route === "POST packs/beta/off")?.body).toEqual({ fingerprint: "fp-1" }));
  expect(await screen.findByText("Turned off beta.")).toBeInTheDocument();
});

test("a refusal shows the server's words on the row", async () => {
  const calls = open(view({ installed: installedRows(false) }), {
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST packs/beta/on": () => new Refuse(409, "The settings changed. Try again."),
  });
  await calls.user.click(await screen.findByRole("tab", { name: "Installed" }));
  const beta = await row("beta");
  await calls.user.click(within(beta).getByRole("button", { name: "Turn on beta" }));
  expect(await within(beta).findByRole("alert")).toHaveTextContent("The settings changed. Try again.");
  expect(within(beta).getByRole("button", { name: "Turn on beta" })).toBeEnabled();
});

test("turning an add-on on that needs a restart asks first, and never restarts by itself", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET packs": () => view({ installed: installedRows(false) }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST packs/beta/on": () => SAVED(true),
    "POST restart": () => ({ restarting: true }),
  });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <Addons onBack={() => undefined} />
    </RestartProvider>,
  );
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  await user.click(within(await row("beta")).getByRole("button", { name: "Turn on beta" }));
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("Restart to finish this change?"));
  expect(screen.getByRole("button", { name: "Restart now" })).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
});

test("after Turn on the row says the add-on is on, and 'On after a restart' while it isn't running, with a way to restart", async () => {
  const user = userEvent.setup();
  let on = false;
  const calls = fakeApi({
    // The list reads which add-ons are on from the saved settings; the add-on isn't running until the restart.
    "GET packs": () => view({ installed: [{ ...installedRows(on)[0], state: "off" }] }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET status": () => ({ restart_needed: on ? "settings" : null, can_restart: true }),
    "POST packs/beta/on": () => {
      on = true;
      return SAVED(true);
    },
    "POST restart": () => ({ restarting: true }),
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Addons onBack={() => undefined} />
    </RestartProvider>,
  );
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  const beta = await row("beta");
  expect(beta).toHaveTextContent("Off");
  await user.click(within(beta).getByRole("button", { name: "Turn on beta" }));
  await waitFor(() => expect(within(beta).getByRole("button", { name: "Turn off beta" })).toBeInTheDocument());
  expect(beta).toHaveTextContent("On after a restart");
  // Asking to restart is the person's choice; nothing restarted by itself.
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(within(beta).getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
});

test("an add-on that is on and running says so, and one that is on but refused keeps its reason", async () => {
  const user = userEvent.setup();
  open(
    view({
      installed: [
        { ...installedRows(true)[0], name: "running" },
        { ...installedRows(true)[0], name: "refused", state: "disabled", reason: "it needs a newer version of the app" },
      ],
    }),
  );
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  expect(await row("running")).toHaveTextContent("On and running");
  expect(await row("refused")).toHaveTextContent("Turned off because: it needs a newer version of the app");
  expect(await row("refused")).not.toHaveTextContent("On after a restart");
});

test("a catalog row for an add-on that is on but not running yet says it is on after a restart", async () => {
  open(
    view({
      installed: [{ ...installedRows(true)[0], state: "off" }],
      available: [pack("beta", { installed_version: "1.0.0", enabled: true })],
    }),
  );
  expect(await row("Name of beta")).toHaveTextContent("Installed (version 1.0.0) and on after a restart");
});

test("turning on refetches the add-ons list so the row reads what was saved", async () => {
  const user = userEvent.setup();
  const calls = open(view({ installed: installedRows(false) }), {
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "POST packs/beta/on": () => SAVED(false),
  });
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  const before = calls.calls.filter((c) => c.route === "GET packs").length;
  await user.click(within(await row("beta")).getByRole("button", { name: "Turn on beta" }));
  await waitFor(() => expect(calls.calls.filter((c) => c.route === "GET packs").length).toBeGreaterThan(before));
});

const INSTALLED = (name: string, version = "1.0.0") => ({ name, version, needs_restart: true });

test("an add-on with a release has Install as its one action: it installs, then says a restart is needed and offers Restart now", async () => {
  const user = userEvent.setup();
  let done = false;
  const calls = fakeApi({
    "GET packs": () => view({ available: [pack("tool", { installable: true, installed_version: done ? "1.0.0" : null })] }),
    "GET status": () => ({ restart_needed: done ? "add-ons" : null, can_restart: true, restart_for: done ? ["add-ons"] : [] }),
    "POST packs/tool/install": () => {
      done = true;
      return INSTALLED("tool");
    },
    "POST restart": () => ({ restarting: true }),
  });
  renderApp(
    <RestartProvider hellos={1}>
      <Addons onBack={() => undefined} />
    </RestartProvider>,
  );
  const tool = await row("Name of tool");
  expect(within(tool).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["Install Name of tool"]);
  expect(within(tool).queryByRole("button", { name: /How to get/ })).toBeNull();
  await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST packs/tool/install")).toBe(true));
  const note = await within(tool).findByText(/Name of tool is installed\. Restart, then turn it on\./);
  expect(note).toBeInTheDocument();
  expect(within(tool).queryByRole("button", { name: "Install Name of tool" })).toBeNull();
  // The restart is the person's choice: nothing restarted by itself.
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(await within(tool).findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
});

test("the install note and its Restart now go once the app has restarted, and stay while the restart is still to come", async () => {
  const user = userEvent.setup();
  let installed = false;
  let instance = "first";
  const calls = fakeApi({
    "GET packs": () => view({ available: [pack("tool", { installable: true, installed_version: installed ? "1.0.0" : null })] }),
    "GET status": () => ({ restart_needed: installed ? "add-ons" : null, can_restart: true, restart_for: [] }),
    "GET runtime-config": () => ({ instance }),
    "POST packs/tool/install": () => {
      installed = true;
      return INSTALLED("tool");
    },
    "POST restart": () => ({ restarting: true }),
  });
  renderApp(
    <RestartProvider hellos={1} pollSeconds={0.05} doneSeconds={0.05}>
      <Addons onBack={() => undefined} />
    </RestartProvider>,
  );
  const tool = await row("Name of tool");
  await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
  await within(tool).findByText(/Name of tool is installed\./);
  // Asking for the restart is not the restart: the note stays while the app is still on the same start.
  await user.click(await within(tool).findByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
  await waitFor(() => expect(calls.filter((c) => c.route === "GET runtime-config").length).toBeGreaterThan(2));
  expect(within(tool).getByText(/Name of tool is installed\./)).toBeInTheDocument();
  const reads = calls.filter((c) => c.route === "GET packs").length;
  // The app answers as a new start: the note and its button are gone, and the list is read again.
  instance = "second";
  await waitFor(() => expect(within(tool).queryByText(/Name of tool is installed\./)).toBeNull());
  expect(within(tool).queryByRole("button", { name: "Restart now" })).toBeNull();
  await waitFor(() => expect(calls.filter((c) => c.route === "GET packs").length).toBeGreaterThan(reads));
});

test("after an install and its restart, Turn on on the same row says a restart is needed and offers its own Restart now", async () => {
  const user = userEvent.setup();
  let enabled = false;
  let instance = "first";
  const calls = fakeApi({
    "GET packs": () =>
      view({
        available: [pack("tool", { installable: true, installed_version: "1.0.0", enabled })],
        installed: [{ ...installedRows(enabled)[0], name: "tool", state: "off" }],
      }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET status": () => ({ restart_needed: "add-ons", can_restart: true, restart_for: [] }),
    "GET runtime-config": () => ({ instance }),
    "POST packs/tool/on": () => {
      enabled = true;
      return SAVED(true);
    },
    "POST restart": () => ({ restarting: true }),
  });
  renderApp(
    <RestartProvider hellos={1} pollSeconds={0.05} doneSeconds={0.05}>
      <Addons onBack={() => undefined} />
    </RestartProvider>,
  );
  const tool = await row("Name of tool");
  // The add-on was installed in an earlier start; nothing waits for a restart yet.
  expect(within(tool).queryByRole("button", { name: "Restart now" })).toBeNull();
  await user.click(within(tool).getByRole("button", { name: "Turn on Name of tool" }));
  await waitFor(() => expect(tool).toHaveTextContent("Installed (version 1.0.0) and on after a restart"));
  expect(within(tool).queryByText(/is installed\. It is ready after a restart/)).toBeNull();
  // Turning on is not a restart: nothing restarted by itself, and the row has its own way to ask for one.
  expect(calls.some((c) => c.route === "POST restart")).toBe(false);
  await user.click(within(tool).getByRole("button", { name: "Restart now" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST restart")).toBe(true));
  instance = "second";
});

test("a refusal to install is the server's own words, with Install still there to try again", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET packs": () => view({ available: [pack("tool", { installable: true })] }),
    "POST packs/tool/install": () => new Refuse(409, "The file doesn't match the checksum, so it wasn't installed."),
  });
  renderApp(<Addons onBack={() => undefined} />);
  const tool = await row("Name of tool");
  const install = within(tool).getByRole("button", { name: "Install Name of tool" });
  await user.click(install);
  expect(await within(tool).findByRole("alert")).toHaveTextContent("The file doesn't match the checksum, so it wasn't installed.");
  expect(within(tool).getByRole("button", { name: "Install Name of tool" })).toBeEnabled();
  expect(calls.filter((c) => c.route === "POST packs/tool/install")).toHaveLength(1);
});

test("while an install runs the button says so and can't be pressed again", async () => {
  const user = userEvent.setup();
  let finish: () => void = () => undefined;
  const hold = new Promise<void>((resolve) => (finish = resolve));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${String(input).replace(/^api\//, "")}`;
      if (route === "POST packs/tool/install") {
        await hold;
        return new Response(JSON.stringify(INSTALLED("tool")), { status: 200, headers: { "content-type": "application/json" } });
      }
      const body = route === "GET packs" ? view({ available: [pack("tool", { installable: true })] }) : {};
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  renderApp(<Addons onBack={() => undefined} />);
  const tool = await row("Name of tool");
  await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
  const busy = await within(tool).findByRole("button", { name: "Install Name of tool" });
  expect(busy).toHaveTextContent("Installing…");
  expect(busy).toBeDisabled();
  finish();
  expect(await within(tool).findByText(/is installed\./)).toBeInTheDocument();
});

test("an add-on with no release keeps the install text to copy, and has no Install button", async () => {
  open(view({ available: [pack("bare", { installable: false }), pack("unsaid")] }));
  for (const name of ["Name of bare", "Name of unsaid"]) {
    const bare = await row(name);
    expect(within(bare).getByRole("button", { name: `How to get ${name}` })).toBeInTheDocument();
    expect(within(bare).queryByRole("button", { name: /^Install/ })).toBeNull();
  }
});

test("Remove is in the menu only for an add-on the app installed that is off, and it acts at once with the restart note", async () => {
  const user = userEvent.setup();
  const calls = open(
    view({
      available: [
        pack("mine", { installed_version: "1.0.0", enabled: false, removable: true }),
        pack("running", { installed_version: "1.0.0", enabled: true, removable: true }),
        pack("other", { installed_version: "1.0.0", enabled: false, removable: false }),
      ],
    }),
    { "POST packs/mine/uninstall": () => INSTALLED("mine") },
  );
  expect(within(await row("Name of running")).queryByRole("button", { name: /More actions/ })).toBeNull();
  expect(within(await row("Name of other")).queryByRole("button", { name: /More actions/ })).toBeNull();
  const mine = await row("Name of mine");
  await user.click(within(mine).getByRole("button", { name: "More actions for Name of mine" }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.calls.some((c) => c.route === "POST packs/mine/uninstall")).toBe(true));
  expect(await within(mine).findByText(/Name of mine is removed\. Restart to finish\./)).toBeInTheDocument();
});

test("on Installed, Remove is offered for an add-on the app installed that is off", async () => {
  const user = userEvent.setup();
  const calls = open(
    view({
      installed: [
        { ...installedRows(false)[0], name: "mine", removable: true },
        { ...installedRows(false)[0], name: "other", removable: false },
        { ...installedRows(true)[0], name: "on", removable: true },
      ],
    }),
    { "POST packs/mine/uninstall": () => INSTALLED("mine") },
  );
  await user.click(await screen.findByRole("tab", { name: "Installed" }));
  expect(within(await row("other")).queryByRole("button", { name: /More actions/ })).toBeNull();
  expect(within(await row("on")).queryByRole("button", { name: /More actions/ })).toBeNull();
  await user.click(within(await row("mine")).getByRole("button", { name: "More actions for mine" }));
  await user.click(await screen.findByRole("menuitem", { name: "Remove" }));
  await waitFor(() => expect(calls.calls.some((c) => c.route === "POST packs/mine/uninstall")).toBe(true));
  expect(await within(await row("mine")).findByText(/mine is removed\./)).toBeInTheDocument();
});

test("the introduction says installing happens here and that the app never takes payment", async () => {
  open(view());
  const intro = await screen.findByText(/Add-ons add a kind of work, such as publishing or social posts/);
  expect(intro).toHaveTextContent("Installing one from the list happens here");
  expect(intro).toHaveTextContent("never takes payment");
  expect(intro).not.toHaveTextContent("never installs");
});

describe("adding a catalog from the screen", () => {
  const SAVED_FEEDS = (before: string[], after: string[]) => ({
    changes: [{ key: "workspace.plugins.catalog.feeds", before, after, was_default: before.length === 0, is_default: false }],
    fingerprint: "fp-2",
    needs_restart: false,
  });
  const ADDRESS = "https://" + "catalog.example.com/packs.yaml";

  test("with no catalog listed the screen offers an address field, with the cursor in it", async () => {
    open(view({ feeds: [] }));
    expect(await screen.findByText(/No add-on catalog is connected/)).toBeInTheDocument();
    const field = await screen.findByLabelText("Catalog address");
    await waitFor(() => expect(field).toHaveFocus());
    expect(screen.getByRole("button", { name: "Add catalog" })).toBeDisabled();
  });

  test("Add catalog saves the address, reads the catalog at once and lists its packs", async () => {
    let listed = false;
    const { calls, user } = open(view({ feeds: [] }), {
      "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
      "POST packs/catalogs": () => {
        listed = true;
        return SAVED_FEEDS([], [ADDRESS]);
      },
      "POST packs/refresh": () => view({ feeds: [feed({ address: ADDRESS, removable: true, domain: "catalog.example.com" })], available: [pack("tool", { installable: true })] }),
      "GET packs": () => (listed ? view({ feeds: [feed({ address: ADDRESS, removable: true })], available: [pack("tool", { installable: true })] }) : view({ feeds: [] })),
    });
    await user.type(await screen.findByLabelText("Catalog address"), ` ${ADDRESS}`);
    await user.click(screen.getByRole("button", { name: "Add catalog" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST packs/refresh")).toBe(true));
    expect(calls.find((c) => c.route === "POST packs/catalogs")?.body).toEqual({ address: ADDRESS, fingerprint: "fp-1" });
    expect(await screen.findByText("Name of tool")).toBeInTheDocument();
    expect(screen.queryByLabelText("Catalog address")).toBeNull();
    expect(await screen.findByText("Added the catalog at catalog.example.com. Its add-ons are listed.")).toBeInTheDocument();
  });

  test("a refusal is shown in the server's words and what was typed stays", async () => {
    const { user } = open(view({ feeds: [] }), {
      "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
      "POST packs/catalogs": () => new Refuse(400, "Give the catalog's address, starting with https:// and no spaces."),
    });
    await user.type(await screen.findByLabelText("Catalog address"), "catalog.example.com");
    await user.click(screen.getByRole("button", { name: "Add catalog" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("starting with https://");
    expect(screen.getByLabelText("Catalog address")).toHaveValue("catalog.example.com");
  });

  test("where catalogs are listed, another can be added, and one the person added can be taken off", async () => {
    const mine = feed({ address: ADDRESS, removable: true, domain: "catalog.example.com" });
    const shipped = feed({ address: "https://" + "built-in.example.com/packs.yaml", removable: false, domain: "built-in.example.com" });
    const { calls, user } = open(view({ feeds: [shipped, mine] }), {
      "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
      "POST packs/catalogs/remove": () => SAVED_FEEDS([ADDRESS], []),
      "POST packs/refresh": () => view({ feeds: [shipped] }),
    });
    await screen.findByText("built-in.example.com · read", { exact: false });
    expect(screen.queryByRole("button", { name: "Remove the catalog built-in.example.com" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Add another catalog" }));
    expect(await screen.findByLabelText("Catalog address")).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Catalog address")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Remove the catalog catalog.example.com" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST packs/catalogs/remove")?.body).toEqual({ address: ADDRESS, fingerprint: "fp-1" }));
    expect(await screen.findByText("Took the catalog at catalog.example.com off the list.")).toBeInTheDocument();
  });
});

describe("a read token for a private release", () => {
  const TOKEN_ROUTES = (local = true) => ({
    "GET setup": () => ({ steps: [], finished: true, local, walkthrough: {} }),
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
    "GET status": () => ({ restart_needed: null, can_restart: true, restart_for: [] }),
  });
  const SAVED_TOKEN = {
    changes: [{ key: "workspace.plugins.catalog.release_tokens", before: {}, after: { "files.example.com": "file:/kept" }, was_default: true, is_default: false }],
    fingerprint: "fp-2",
    needs_restart: false,
  };
  const PRIVATE = () => pack("tool", { installable: true, release_host: "files.example.com" });

  test("a refusal that a token would fix offers Add a download access key in the row, and no other refusal does", async () => {
    const user = userEvent.setup();
    let answer: unknown = new Refuse(409, "The release file couldn't be read: it may be private.", { "X-Cockpit-Needs": "read-token" });
    fakeApi({ ...TOKEN_ROUTES(), "GET packs": () => view({ available: [PRIVATE()] }), "POST packs/tool/install": () => answer });
    renderApp(<Addons onBack={() => undefined} />);
    const tool = await row("Name of tool");
    expect(within(tool).queryByRole("button", { name: /Add a read token/ })).toBeNull();
    await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
    expect(await within(tool).findByRole("button", { name: "Add a download access key for Name of tool" })).toBeInTheDocument();
    answer = new Refuse(409, "The file doesn't match the checksum, so it wasn't installed.");
    await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
    expect(await within(tool).findByText(/doesn't match the checksum/)).toBeInTheDocument();
    expect(within(tool).queryByRole("button", { name: /Add a read token/ })).toBeNull();
  });

  test("on a local app the token is typed into a password box, sent apart, and Install can then be pressed again", async () => {
    const user = userEvent.setup();
    let kept = false;
    const calls = fakeApi({
      ...TOKEN_ROUTES(),
      "GET packs": () => view({ available: [PRIVATE()] }),
      "POST packs/tool/install": () =>
        kept ? INSTALLED("tool") : new Refuse(409, "The release file couldn't be read: it may be private.", { "X-Cockpit-Needs": "read-token" }),
      "POST packs/tool/token": () => {
        kept = true;
        return SAVED_TOKEN;
      },
    });
    renderApp(<Addons onBack={() => undefined} />);
    const tool = await row("Name of tool");
    await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
    await user.click(await within(tool).findByRole("button", { name: "Add a download access key for Name of tool" }));
    expect(within(tool).getByText(/private files at files\.example\.com/)).toHaveTextContent("Enter a read-only access key for the add-on's private files at files.example.com. It is sent only to files.example.com.");
    const box = within(tool).getByLabelText("Download access key");
    expect(box).toHaveAttribute("type", "password");
    expect(box).toHaveFocus();
    await user.type(box, "typed-token");
    await user.click(within(tool).getByRole("button", { name: "Save access key" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST packs/tool/token")?.body).toEqual({ token: "typed-token", fingerprint: "fp-1" }));
    expect(await within(tool).findByText("Access key saved. Choose Install to retry.")).toBeInTheDocument();
    expect(within(tool).queryByRole("alert")).toBeNull();
    await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
    await waitFor(() => expect(calls.filter((c) => c.route === "POST packs/tool/install")).toHaveLength(2));
    expect(JSON.stringify(calls.map((c) => c.body))).not.toContain("file:/kept");
  });

  test("Where it is kept instead sends a reference, and a hosted app offers only that", async () => {
    const user = userEvent.setup();
    const calls = fakeApi({
      ...TOKEN_ROUTES(false),
      "GET packs": () => view({ available: [PRIVATE()] }),
      "POST packs/tool/install": () => new Refuse(409, "The read token for files.example.com isn't available.", { "X-Cockpit-Needs": "read-token" }),
      "POST packs/tool/token": () => SAVED_TOKEN,
    });
    renderApp(<Addons onBack={() => undefined} />);
    const tool = await row("Name of tool");
    await user.click(within(tool).getByRole("button", { name: "Install Name of tool" }));
    await user.click(await within(tool).findByRole("button", { name: "Add a download access key for Name of tool" }));
    const box = within(tool).getByLabelText("Download access key");
    await waitFor(() => expect(box).toHaveAttribute("type", "text"));
    expect(within(tool).queryByRole("button", { name: "Where it is kept instead" })).toBeNull();
    await user.type(box, "RELEASE_TOKEN");
    await user.click(within(tool).getByRole("button", { name: "Save access key" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST packs/tool/token")?.body).toEqual({ reference: "env:RELEASE_TOKEN", fingerprint: "fp-1" }));
  });

  test("an entry with no release keeps its own install text", async () => {
    const user = userEvent.setup();
    fakeApi({ ...TOKEN_ROUTES(), "GET packs": () => view({ available: [pack("bare", { installable: false, release_host: null })] }) });
    renderApp(<Addons onBack={() => undefined} />);
    const bare = await row("Name of bare");
    expect(within(bare).queryByRole("button", { name: /Install|read token/ })).toBeNull();
    await user.click(within(bare).getByRole("button", { name: "How to get Name of bare" }));
    expect(await screen.findByText("install bare")).toBeInTheDocument();
  });
});
