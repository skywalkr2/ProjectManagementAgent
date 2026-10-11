import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { wordsOfWork } from "../lib/packs";
import { fakeApi, renderApp } from "../test-utils";
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
  expect(mine).toHaveTextContent("Made by the app's maintainers · Publisher of mine · updated 2026-09-01 · Works with this version");
  expect(await row("Name of theirs")).toHaveTextContent("Third party · Publisher of theirs · updated 2026-09-01 · Needs a different version of the app");
  const unknown = await row("Name of unknown");
  expect(unknown).toHaveTextContent("Third party · Publisher of unknown · updated 2026-09-01");
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
    "Item types: book, chapter",
    "1 screen",
    "1 kind of line on Today",
    "2 kinds of AI work",
    "3 actions",
    "1 setup step",
    "2 places it keeps reading",
  ]);
  const reaches = within(full).getByRole("list", { name: "Reaches" });
  expect(within(reaches).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Signs in to: print service",
    `Internet: ${SITE}, files.example.com`,
    "Programs on this computer: ebook-checker",
    "Keys you provide: 1",
  ]);
  expect(full).toHaveTextContent("May hold private material. It goes only to AI accounts you allow for private material.");

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
    "Reading a source: about 10,000 words of AI work (an estimate)",
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
  expect(within(dialog).getByText("To try it on made-up data first:")).toBeInTheDocument();
  expect(within(dialog).getByText("cockpit demo --plugin tool")).toBeInTheDocument();
  expect(within(dialog).getByText(/Read it before you run anything/)).toBeInTheDocument();
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
  expect(off).toHaveTextContent("Turn on in Settings");
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
  expect(within(current).queryByRole("button")).toBeNull();
});

test("when the catalog is off, nothing is listed and the reason is given", async () => {
  open(view({ enabled: false, feeds: [] }));
  expect(await screen.findByText("The catalog is off in this workspace's settings.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
});

test("with no catalog it says so and points to Installed", async () => {
  open(view({ feeds: [] }));
  expect(
    await screen.findByText("This copy of the app doesn't list a catalog. Packs you install still show under Installed."),
  ).toBeInTheDocument();
});

test("a catalog with no packs says none are listed yet", async () => {
  open(view());
  expect(await screen.findByText("No packs are listed yet.")).toBeInTheDocument();
  expect(screen.getByText(`${HOST} · read`, { exact: false })).toBeInTheDocument();
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
          what: summary({ adds: { screens: 1 }, reaches: { hosts: [SITE] }, keeps: "restricted" }),
        },
        { name: "beta", version: null, description: "", enabled: false, state: "off", reason: null, what: summary() },
        {
          name: "gamma",
          version: "1.0.0",
          description: "Needs more",
          enabled: true,
          state: "disabled",
          reason: "it needs a newer version of the app",
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
  expect(within(alpha).getByRole("list", { name: "Reaches" })).toHaveTextContent(`Internet: ${SITE}`);
  expect(alpha).toHaveTextContent("May hold private material");
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
