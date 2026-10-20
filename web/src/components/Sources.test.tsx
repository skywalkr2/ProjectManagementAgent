import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { whenText } from "../lib/dates";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { Sources } from "./Sources";

type Source = S["WatchSourceView"];
type Run = NonNullable<Source["last"]>;

const run = (extra: Partial<Run> = {}): Run => ({
  outcome: "ok",
  started_at: "2026-03-04T10:30:00+00:00",
  new: 0,
  changed: 0,
  removed: 0,
  ...extra,
});

const source = (id: string, extra: Partial<Source> = {}): Source => ({
  id,
  label: `Source ${id}`,
  connector: "kind-a",
  connector_label: "A folder",
  enabled: true,
  every_minutes: 15,
  items: 3,
  last: run(),
  read_at: run().started_at,
  failures: 0,
  problem: null,
  ...extra,
});

const closed = (id: string, extra: Partial<S["AutoClosedView"]> = {}): S["AutoClosedView"] => ({
  id,
  version: 4,
  title: `Item ${id}`,
  source: "Source a",
  change: "changed",
  rule: "rule-a",
  reason: "only spacing changed",
  created_at: "2026-03-04T09:00:00+00:00",
  ...extra,
});

const silent = (ref: string, extra: Partial<S["SilentCloseView"]> = {}): S["SilentCloseView"] => ({
  ref,
  kind: "assistant",
  how: "dropped",
  title: `Closed ${ref}`,
  when: "2026-03-04T09:00:00+00:00",
  why: "no longer needed",
  ...extra,
});

const measure = (extra: Partial<S["CloseMeasureView"]> = {}): S["CloseMeasureView"] => ({
  days: 28,
  since: "2026-02-04T09:00:00+00:00",
  until: "2026-03-04T09:00:00+00:00",
  total: 0,
  silent: 0,
  by_person: 0,
  approved: 0,
  rate: null,
  kinds: [],
  ...extra,
});

type Item = S["SettingItem"];
const field = (key: string, type: Item["type"], extra: Partial<Item> = {}): Item => ({
  key,
  file: "source",
  group: "",
  description: `About ${key}`,
  type,
  options: [],
  value: null,
  default: null,
  source: "default",
  locked: false,
  basic: false,
  editable: true,
  ...extra,
});
const kind = (
  name: string,
  label: string,
  plugin: string | null,
  items: Item[],
  first_run: S["WatchKindView"]["first_run"] = "baseline",
): S["WatchKindView"] => ({ name, label, plugin, items, first_run });

const KINDS = [
  kind("folder", "A folder", null, [field("path", "text"), field("patterns", "list", { value: [], default: [] })]),
  kind("demo/calendar", "A calendar", "demo", [
    field("address", "text"),
    field("days_ahead", "integer", { value: 30, default: 30 }),
    field("options.depth", "integer", { value: 1, default: 1 }),
  ]),
  kind("demo/mailbox", "A mailbox", "demo", [field("folder", "text")], "recent"),
  kind("other/feed", "A feed", "other", [field("url", "text")]),
];

const SAVED = (before: unknown[], after: unknown[]) => ({
  changes: [{ key: "watch.sources", before, after, was_default: before.length === 0, is_default: false }],
  fingerprint: "fp-2",
  needs_restart: false,
});

/** The saved settings as they hold the sources: each with the settings it was made with. */
const stored = (list: Array<{ id: string; settings: Record<string, unknown> }>) => ({
  fingerprint: "fp-1",
  items: [field("watch.sources", "other", { value: list, editable: false, default: [] })],
});

function open(
  sources: Source[],
  items: S["AutoClosedView"][] = [],
  extra: Record<string, (b: unknown) => unknown> = {},
  props: Partial<Parameters<typeof Sources>[0]> = {},
) {
  const calls = fakeApi({
    "GET watch": () => sources,
    "GET auto-closed": () => items,
    "GET silent-closes": () => ({ count: 0, closes: [], measure: measure() }),
    "GET watch/kinds": () => KINDS,
    "GET settings": () => stored(sources.map((s) => ({ id: s.id, settings: { path: `${s.id}-folder` } }))),
    "GET projects": () => [],
    "GET watch/authors": () => [],
    ...extra,
  });
  const onAsk = vi.fn();
  renderApp(<Sources onAsk={onAsk} {...props} />);
  return { calls, onAsk };
}

const row = async (label: string) => (await screen.findByRole("listitem", { name: label })) as HTMLElement;

/** Opens a row's menu and chooses an item from it. */
async function choose(user: ReturnType<typeof userEvent.setup>, label: string, item: string) {
  await user.click(within(await row(label)).getByRole("button", { name: `More actions for ${label}` }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
}

test("a source shows its kind, how often it is read and its last read in words", async () => {
  open([source("a", { last: run({ new: 2, changed: 1, removed: 0 }) })]);
  const item = await row("Source a");
  expect(item).toHaveTextContent("A folder · 3 items");
  expect(item).toHaveTextContent(/Read every 15 minutes · last read /);
  expect(item).toHaveTextContent("2 new, 1 changed");
});

test("every outcome has its own words", async () => {
  open([
    source("quiet", { last: run() }),
    source("first", { last: run({ outcome: "baseline" }) }),
    source("away", { last: run({ outcome: "offline" }) }),
    source("broken", {
      last: run({ outcome: "failed", error: "refused" }),
      failures: 3,
      problem: "It can't be read: refused. Sign in again.",
    }),
    source("fresh", { last: null, read_at: null }),
  ]);
  expect(await row("Source quiet")).toHaveTextContent("Nothing new");
  expect(await row("Source first")).toHaveTextContent("First check complete; existing items noted");
  expect(await row("Source away")).toHaveTextContent("Not checked: no internet connection");
  const broken = await row("Source broken");
  expect(broken).toHaveTextContent("Couldn't be read");
  expect(broken).toHaveTextContent("Failed 3 times in a row");
  expect(within(broken).getByText("It can't be read: refused. Sign in again.")).toBeInTheDocument();
  expect(await row("Source fresh")).toHaveTextContent("Not read yet");
});

test("a source that found no network shows when it was last really read, not the try", async () => {
  open([source("away", { last: run({ outcome: "offline", started_at: "2026-03-05T08:00:00+00:00" }), read_at: "2026-03-04T10:30:00+00:00" })]);
  const item = await row("Source away");
  expect(item).toHaveTextContent("Not checked: no internet connection");
  expect(item).toHaveTextContent(`last read ${whenText("2026-03-04T10:30:00+00:00")}`);
  expect(item).not.toHaveTextContent(whenText("2026-03-05T08:00:00+00:00"));
});

test("a source without a kind says so, and a source that is off says Off and can't be read now", async () => {
  const user = userEvent.setup();
  open([source("a", { connector_label: "", enabled: false })]);
  const item = await row("Source a");
  expect(item).toHaveTextContent("Not available · 3 items");
  expect(item).toHaveTextContent(/Off · last read /);
  expect(item).not.toHaveTextContent("Read every");
  await user.click(within(item).getByRole("button", { name: "More actions for Source a" }));
  expect(await screen.findByRole("menuitem", { name: "Read now" })).toHaveAttribute("aria-disabled", "true");
  expect(screen.getByRole("menuitem", { name: "Turn on" })).toBeInTheDocument();
});

test("a source that has never been read says how often it will be", async () => {
  open([source("a", { last: null, read_at: null, every_minutes: 1 })]);
  expect(await row("Source a")).toHaveTextContent("Read every minute · Not read yet");
});

test("a source whose reads have all failed gives no item count, since 0 items would say it was read and found nothing", async () => {
  open([
    source("broken", {
      items: 0,
      last: run({ outcome: "failed", error: "refused" }),
      read_at: null,
      failures: 1,
      problem: "It can't be read: refused. Sign in again.",
    }),
  ]);
  const item = await row("Source broken");
  expect(item).toHaveTextContent("A folder");
  expect(item).not.toHaveTextContent(/\d+ items?/);
  expect(item).toHaveTextContent("Couldn't be read");
  expect(within(item).getByText("It can't be read: refused. Sign in again.")).toBeInTheDocument();
});

test("a failing source's problem is announced when the screen opens, and not again on a refresh", async () => {
  let sources = [source("a", { last: run({ outcome: "failed" }), failures: 1, problem: "Can't reach it." })];
  fakeApi({
    "GET watch": () => sources,
    "GET auto-closed": () => [],
    // Reading a also finds that a second source has started failing.
    "POST watch/a/read": () => {
      sources = [...sources, source("b", { last: run({ outcome: "failed" }), failures: 1, problem: "Gone missing." })];
      return sources[0];
    },
  });
  renderApp(<Sources onAsk={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach it.");
  const user = userEvent.setup();
  await choose(user, "Source a", "Read now");
  // The newly failing source is shown in words but not announced as an alert.
  expect(await screen.findByText("Gone missing.")).not.toHaveAttribute("role");
  expect(screen.getAllByRole("alert")).toHaveLength(1);
});

test("a source that isn't failing has no alert", async () => {
  open([source("a")]);
  await row("Source a");
  expect(screen.queryByRole("alert")).toBeNull();
});

test("Read now reads that source and shows what the read returned", async () => {
  let a = source("a");
  const calls = fakeApi({
    "GET watch": () => [a, source("b")],
    "GET auto-closed": () => [],
    "POST watch/a/read": () => (a = source("a", { last: run({ new: 4 }), items: 7 })),
  });
  renderApp(<Sources onAsk={() => {}} />);
  const user = userEvent.setup();
  await choose(user, "Source a", "Read now");
  await waitFor(() => expect(screen.getByRole("listitem", { name: "Source a" })).toHaveTextContent("4 new"));
  expect(screen.getByRole("listitem", { name: "Source a" })).toHaveTextContent("7 items");
  expect(calls.some((c) => c.route === "POST watch/a/read")).toBe(true);
  expect(await screen.findByText("Source a: 4 new")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST watch/b/read")).toBe(false);
});

test("a read that fails says why in the message", async () => {
  open([source("a")], [], {
    "POST watch/a/read": () =>
      source("a", { last: run({ outcome: "failed" }), failures: 1, problem: "Can't reach it. Try later." }),
  });
  const user = userEvent.setup();
  await choose(user, "Source a", "Read now");
  expect(await screen.findByText("Source a: Can't reach it. Try later.")).toBeInTheDocument();
});

test("with no sources, the screen says what a source is and offers to ask how", async () => {
  const { onAsk } = open([]);
  expect(await screen.findByText(/No sources yet/)).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Ask how to add one" }));
  expect(onAsk).toHaveBeenCalledWith("How do I add a source for Helper to keep reading?");
});

test("auto-closed items show their title, source, reason and time", async () => {
  open([source("a")], [closed("r1"), closed("r2", { title: "Other item", change: "removed", reason: "made by us" })]);
  const first = await row("Item r1");
  expect(first).toHaveTextContent("Changed");
  expect(first).toHaveTextContent("Source a");
  expect(first).toHaveTextContent("Set aside because: only spacing changed");
  expect(await row("Other item")).toHaveTextContent("Removed");
});

test("nothing set aside says so", async () => {
  open([source("a")], []);
  expect(await screen.findByText("Nothing has been set aside.")).toBeInTheDocument();
});

test("Take a closer look sends the version that was read, and says so", async () => {
  const { calls } = open([source("a")], [closed("r1", { version: 9 })], {
    "POST requests/r1/closer-look": () => ({ id: "r1" }),
  });
  const user = userEvent.setup();
  await user.click(within(await row("Item r1")).getByRole("button", { name: "Take a closer look at Item r1" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/r1/closer-look")?.body).toEqual({ read_version: 9 }));
  expect(await screen.findByText("Handed in Item r1. Helper is on it.")).toBeInTheDocument();
});

describe("closes nobody has seen", () => {
  const two = [
    silent("changeset:CS-1:0", { title: "Send the proof", why: "the printer said so", run: "RUN-1" }),
    silent("request:REQ-2", { kind: "rule", how: "closed", title: "Plan", rule: "Spacing", why: "only spacing changed" }),
    silent("snapshot:SN-3", { kind: "set_aside", how: "set_aside", title: "A newsletter", rule: "Bulk mail", why: "bulk" }),
  ];

  test("each shows what, by whom, when and why, with the count out of all closes", async () => {
    open([source("a")], [], {
      "GET silent-closes": () => ({ count: 3, closes: two, measure: measure({ total: 12, silent: 3, rate: 0.25 }) }),
    });
    const assistant = await row("Send the proof");
    expect(assistant).toHaveTextContent("Dropped");
    expect(assistant).toHaveTextContent("By Helper");
    expect(assistant).toHaveTextContent("Because: the printer said so");
    expect(await row("Plan")).toHaveTextContent("By the rule Spacing");
    expect(screen.getByTestId("silent-measure")).toHaveTextContent("3 of 12 closes in the last 28 days weren't seen by you.");
  });

  test("set-aside mail points to its folder instead of offering Looks right", async () => {
    open([source("a")], [], {
      "GET silent-closes": () => ({ count: 1, closes: [two[2]], measure: measure({ total: 1, silent: 1, rate: 1 }) }),
    });
    const mail = await row("A newsletter");
    expect(mail).toHaveTextContent("Review it in the Set aside folder above.");
    expect(within(mail).queryByRole("button")).toBeNull();
  });

  test("Looks right sends the close's reference and says it was marked", async () => {
    const { calls } = open([source("a")], [], {
      "GET silent-closes": () => ({ count: 1, closes: [two[1]], measure: measure({ total: 1, silent: 1, rate: 1 }) }),
      "POST silent-closes/seen": () => ({ id: "request:REQ-2" }),
    });
    const user = userEvent.setup();
    await user.click(within(await row("Plan")).getByRole("button", { name: "Looks right: Plan" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST silent-closes/seen")?.body).toEqual({ ref: "request:REQ-2" }));
    expect(await screen.findByText("Marked as seen: Plan.")).toBeInTheDocument();
  });

  test("with none, it says everything closed was made or seen by the person", async () => {
    open([source("a")]);
    expect(await screen.findByText("Everything that was closed, you made or saw.")).toBeInTheDocument();
    expect(screen.queryByTestId("silent-measure")).toBeNull();
  });
});

describe("adding a source", () => {
  const post = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

  test("Add a source offers the kinds by label, add-on kinds under their add-on, then that kind's form", async () => {
    const user = userEvent.setup();
    open([source("a")]);
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    const form = await screen.findByRole("form", { name: "Add a source" });
    expect(within(form).getByRole("group", { name: "Built in" })).toHaveTextContent("A folder");
    const demo = within(form).getByRole("group", { name: "Demo" });
    expect(within(demo).getAllByRole("radio").map((r) => r.parentElement?.textContent)).toEqual(["A calendar", "A mailbox"]);
    expect(within(form).getByRole("group", { name: "Other" })).toHaveTextContent("A feed");
    // No form for a kind until one is chosen.
    expect(within(form).queryByLabelText("Name")).toBeNull();
    await user.click(within(form).getByRole("radio", { name: "A calendar" }));
    expect(within(form).getByLabelText("About address")).toBeInTheDocument();
    expect(within(form).getByLabelText("About days_ahead")).toHaveValue("30");
    expect(within(form).getByLabelText("Name")).toBeInTheDocument();
    expect(within(form).getByLabelText("How often to read")).toHaveValue("60");
    // Switching kind shows that kind's form.
    await user.click(within(form).getByRole("radio", { name: "A mailbox" }));
    expect(within(form).queryByLabelText("About address")).toBeNull();
    expect(within(form).getByLabelText("About folder")).toBeInTheDocument();
  });

  test("a kind whose first read only notes what is there says so, read from how the kind starts, not its name", async () => {
    const user = userEvent.setup();
    open([]);
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    const form = await screen.findByRole("form", { name: "Add a source" });
    expect(form.querySelector("[data-first-read]")).toBeNull();
    await user.click(within(form).getByRole("radio", { name: "A folder" }));
    expect(within(form).getByText("Existing items aren't sent to the assistant. New items are. Choose Look at the last day to include recent arrivals and changes.")).toBeInTheDocument();
    // A kind that also hands in the recent past has nothing to explain.
    await user.click(within(form).getByRole("radio", { name: "A mailbox" }));
    expect(form.querySelector("[data-first-read]")).toBeNull();
  });

  test("a kind that is taken in quietly says what the first read does: one list to look over, and older mail isn't read", async () => {
    const user = userEvent.setup();
    open([], [], { "GET watch/kinds": () => [kind("folder", "A folder", null, [field("path", "text")], "intake")] });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    const form = await screen.findByRole("form", { name: "Add a source" });
    await user.click(within(form).getByRole("radio", { name: "A folder" }));
    expect(within(form).getByText(/taken in quietly: you get one list to look over, not a line for each item/)).toBeInTheDocument();
    expect(within(form).getByText(/Older mail isn't read, and Today says how far back it looked/)).toBeInTheDocument();
  });

  test("how often is 15, 30, 60 or 240 minutes", async () => {
    const user = userEvent.setup();
    open([]);
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A feed" }));
    const every = screen.getByLabelText("How often to read");
    expect(within(every).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "every 15 minutes",
      "every 30 minutes",
      "every 60 minutes",
      "every 240 minutes",
    ]);
  });

  test("saving sends the kind, name, schedule, project and the settings as nested values with the fresh fingerprint, then reads back with Undo", async () => {
    const user = userEvent.setup();
    const { calls } = open([], [], {
      "GET projects": () => [{ id: "p1", name: "Harbor", parent: null }],
      "POST watch/sources": () => SAVED([], [{ id: "work-calendar" }]),
      "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
    });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A calendar" }));
    await user.type(screen.getByLabelText("Name"), "Work calendar");
    await user.type(screen.getByLabelText("About address"), "env:WORK_ADDRESS");
    await user.clear(screen.getByLabelText("About options.depth"));
    await user.type(screen.getByLabelText("About options.depth"), "3");
    await user.selectOptions(screen.getByLabelText("How often to read"), "15");
    await user.selectOptions(await screen.findByLabelText("Project (optional)"), "p1");
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await waitFor(() => expect(post(calls, "POST watch/sources")).toBeDefined());
    expect(post(calls, "POST watch/sources")).toEqual({
      connector: "demo/calendar",
      label: "Work calendar",
      every_minutes: 15,
      project: "p1",
      author: null,
      // Only what differs from the defaults is sent, and dotted keys become nested values.
      settings: { address: "env:WORK_ADDRESS", options: { depth: 3 } },
      fingerprint: "fp-1",
    });
    expect(await screen.findByText("Added Work calendar. It is read within a minute, then every 15 minutes.")).toBeInTheDocument();
    // The form closes and focus goes back to the button that opened it.
    await waitFor(() => expect(screen.queryByRole("form", { name: "Add a source" })).toBeNull());
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(post(calls, "POST settings")).toEqual({ changes: {}, reset: ["watch.sources"], fingerprint: "fp-2" }));
  });

  test("a calendar file on this computer is picked from a list, not typed, and sent as the file's path", async () => {
    const user = userEvent.setup();
    const enc = encodeURIComponent;
    const calendar = kind("calendar", "A calendar file", null, [
      field("file", "text", { picker: "file", file_types: [".ics"] }),
      field("expand_days", "integer", { value: 60, default: 60 }),
    ]);
    const { calls } = open([], [], {
      "GET watch/kinds": () => [...KINDS, calendar],
      "GET setup/folders": () => ({ path: "/home/me", parent: "/home", folders: ["Calendars"], files: [] }),
      [`GET setup/folders?files=${enc(".ics")}`]: () => ({ path: "/home/me", parent: "/home", folders: ["Calendars"], files: ["notes.ics"] }),
      [`GET setup/folders?path=${enc("/home/me/Calendars")}&files=${enc(".ics")}`]: () => ({
        path: "/home/me/Calendars",
        parent: "/home/me",
        folders: [],
        files: ["work.ics", "home.ics"],
      }),
      "POST watch/sources": () => SAVED([], [{ id: "work-file" }]),
    });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A calendar file" }));
    await user.type(screen.getByLabelText("Name"), "Work file");
    await user.click(await screen.findByRole("button", { name: /Choose a file…/ }));
    const dialog = await screen.findByRole("dialog", { name: "Choose a file" });
    // Folders to open and files to choose are in one list; a file is chosen, not typed, and no folder is "used".
    expect(await within(dialog).findByRole("button", { name: "Calendars" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Use notes.ics" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Use this folder" })).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Calendars" }));
    await user.click(await within(dialog).findByRole("button", { name: "Use work.ics" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Choose a file" })).toBeNull());
    expect(screen.getByLabelText("About file")).toHaveValue("/home/me/Calendars/work.ics");
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await waitFor(() => expect(post(calls, "POST watch/sources")).toBeDefined());
    expect(post(calls, "POST watch/sources")).toMatchObject({
      connector: "calendar",
      label: "Work file",
      settings: { file: "/home/me/Calendars/work.ics" },
    });
  });

  test("where the app can't list folders (hosted), a file is not offered from a list", async () => {
    const user = userEvent.setup();
    const calendar = kind("calendar", "A calendar file", null, [field("file", "text", { picker: "file", file_types: [".ics"] })]);
    open([], [], {
      "GET watch/kinds": () => [...KINDS, calendar],
      "GET setup/folders": () => new Refuse(403, "Folders on the server can't be browsed; type the path."),
    });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A calendar file" }));
    expect(await screen.findByLabelText("About file")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Choose a file/ })).toBeNull());
  });

  test("a refusal that names a field is shown on the form, which stays open with what was typed", async () => {
    const user = userEvent.setup();
    open([], [], { "POST watch/sources": () => new Refuse(400, "address: Field required") });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A calendar" }));
    await user.type(screen.getByLabelText("Name"), "Mine");
    await user.click(screen.getByRole("button", { name: "Add source" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("address: Field required");
    expect(screen.getByLabelText("Name")).toHaveValue("Mine");
    expect(screen.getByRole("button", { name: "Add source" })).toBeEnabled();
  });

  test("a number field that isn't a number is said so and can't be saved", async () => {
    const user = userEvent.setup();
    open([]);
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A calendar" }));
    await user.clear(screen.getByLabelText("About days_ahead"));
    await user.type(screen.getByLabelText("About days_ahead"), "soon");
    expect(await screen.findByText("Enter a whole number.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add source" })).toBeDisabled();
  });

  test("from a sign-in, only the kinds of that add-on are offered, and a lone kind is already chosen", async () => {
    const user = userEvent.setup();
    open([source("a")], [], {}, { add: { plugin: "other", n: 1 } });
    const form = await screen.findByRole("form", { name: "Add a source" });
    expect(await within(form).findAllByRole("radio")).toHaveLength(1);
    expect(within(form).getByRole("radio", { name: "A feed" })).toBeChecked();
    expect(within(form).getByLabelText("About url")).toBeInTheDocument();
    // With one add-on there is no heading to tell groups apart.
    expect(within(form).queryByRole("group", { name: "Other" })).toBeNull();
    await user.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Add a source" })).toBeNull();
  });

  test("an add-on with several kinds offers just those", async () => {
    open([], [], {}, { add: { plugin: "demo", n: 1 } });
    const form = await screen.findByRole("form", { name: "Add a source" });
    expect((await within(form).findAllByRole("radio")).map((r) => r.parentElement?.textContent)).toEqual(["A calendar", "A mailbox"]);
  });

  test("asking to add one tells the app the request was taken up, so it isn't repeated", async () => {
    const onAddOpened = vi.fn();
    open([], [], {}, { add: { plugin: null, n: 5 }, onAddOpened });
    await screen.findByRole("form", { name: "Add a source" });
    expect(onAddOpened).toHaveBeenCalled();
  });

  test("with no kinds running, the form says what to turn on", async () => {
    const user = userEvent.setup();
    open([], [], { "GET watch/kinds": () => [] });
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    expect(await screen.findByText(/Turn on a mail or calendar add-on, then sign in to add a source/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add source" })).toBeDisabled();
  });
});

describe("a source's menu", () => {
  const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;
  const items = (kind: string) => [{ id: "a", connector: kind, settings: { path: "inbox", patterns: ["*.md"] } }];

  test("has Read now, Look at the last day, Change, Turn off and Remove", async () => {
    const user = userEvent.setup();
    open([source("a")]);
    const item = await row("Source a");
    // Read now isn't a button on the row any more.
    expect(within(item).queryByRole("button", { name: /Read Source a now/ })).toBeNull();
    await user.click(within(item).getByRole("button", { name: "More actions for Source a" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Read now", "Look at the last day", "Change", "Turn off", "Remove"]);
  });

  test("Change opens the same form filled from the source, and saves the name, schedule and settings", async () => {
    const user = userEvent.setup();
    const { calls } = open([source("a", { connector: "folder", every_minutes: 30 })], [], {
      "GET settings": () => stored(items("folder")),
      "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]),
    });
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: "Change Source a" });
    expect(within(form).queryByRole("radio")).toBeNull();
    expect(within(form).getByLabelText("Name")).toHaveValue("Source a");
    expect(within(form).getByLabelText("How often to read")).toHaveValue("30");
    await waitFor(() => expect(within(form).getByLabelText("About path")).toHaveValue("inbox"));
    expect(within(form).getByLabelText("About patterns")).toHaveValue("*.md");
    await user.clear(within(form).getByLabelText("Name"));
    await user.type(within(form).getByLabelText("Name"), "Renamed");
    await user.selectOptions(within(form).getByLabelText("How often to read"), "240");
    await user.clear(within(form).getByLabelText("About path"));
    await user.type(within(form).getByLabelText("About path"), "docs");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(body(calls, "POST watch/sources/a")).toBeDefined());
    expect(body(calls, "POST watch/sources/a")).toEqual({
      label: "Renamed",
      every_minutes: 240,
      author: null,
      settings: { path: "docs", patterns: ["*.md"] },
      fingerprint: "fp-1",
    });
    expect(await screen.findByText("Saved Renamed.")).toBeInTheDocument();
  });

  test("a save made from a form opened before the settings changed sends the fingerprint it opened with, is refused, and keeps what was typed", async () => {
    const user = userEvent.setup();
    let fingerprint = "fp-1";
    const { calls } = open([source("a", { connector: "folder", every_minutes: 60 })], [], {
      "GET settings": () => ({ ...stored(items("folder")), fingerprint }),
      "POST watch/sources/a": (sent) =>
        (sent as { fingerprint: string }).fingerprint === fingerprint
          ? SAVED([{ id: "a" }], [{ id: "a" }])
          : new Refuse(409, "The settings changed since you opened them. Look again, then save."),
    });
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: "Change Source a" });
    await waitFor(() => expect(within(form).getByLabelText("About path")).toHaveValue("inbox"));
    await waitFor(() => expect(within(form).getByRole("button", { name: "Save changes" })).toBeEnabled());
    // Another form saved a new schedule after this one opened.
    fingerprint = "fp-2";
    await user.clear(within(form).getByLabelText("Name"));
    await user.type(within(form).getByLabelText("Name"), "Renamed");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "This was changed since you opened it. What you typed is still here; check it against what is saved now, then save again.",
    );
    const sent = calls.filter((c) => c.route === "POST watch/sources/a");
    expect(sent).toHaveLength(1);
    expect((sent[0].body as { fingerprint: string }).fingerprint).toBe("fp-1");
    expect(within(form).getByLabelText("Name")).toHaveValue("Renamed");
    expect(within(form).getByLabelText("About path")).toHaveValue("inbox");
    // Nothing was saved behind the person's back, and the form is still open.
    expect(screen.queryByText("Saved Renamed.")).toBeNull();
    // Saving again is the person's own choice, made after the message, and then goes through on what is saved now.
    await waitFor(() => expect(within(form).getByRole("button", { name: "Save changes" })).toBeEnabled());
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved Renamed.")).toBeInTheDocument();
    expect(calls.filter((c) => c.route === "POST watch/sources/a").map((c) => (c.body as { fingerprint: string }).fingerprint)).toEqual(["fp-1", "fp-2"]);
  });

  test("a source's author is picked from a list of the person, colleagues and teams, and saved with the source", async () => {
    const user = userEvent.setup();
    const authors: S["WatchAuthorOption"][] = [
      { id: "p1", name: "Casey Example", kind: "you" },
      { id: "p2", name: "Robin Example", kind: "person" },
      { id: "t1", name: "Design team", kind: "team" },
    ];
    const { calls } = open([source("a", { connector: "folder", author: "p2", author_name: "Robin Example" })], [], {
      "GET watch/authors": () => authors,
      "GET settings": () => stored(items("folder")),
      "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]),
    });
    expect(within(await row("Source a")).getByText(/Written by Robin Example/)).toBeInTheDocument();
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: "Change Source a" });
    const pick = await within(form).findByLabelText("Whose work it holds");
    expect(pick).toHaveValue("p2");
    expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Different people",
      "Casey Example (you)",
      "Robin Example",
      "Design team",
    ]);
    await user.selectOptions(pick, "p1");
    await waitFor(() => expect(within(form).getByLabelText("About path")).toHaveValue("inbox"));
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(body(calls, "POST watch/sources/a")).toBeDefined());
    expect(body(calls, "POST watch/sources/a")).toMatchObject({ author: "p1" });
  });

  describe("which account a source reads", () => {
    const withAccounts = (accounts: string[]): S["WatchKindView"][] => [
      { ...kind("demo/mailbox", "A mailbox", "demo", [field("folder", "text")], "recent"), accounts },
    ];

    test("with several signed in, adding a source asks which account, and saves it", async () => {
      const user = userEvent.setup();
      const { calls } = open([], [], {
        "GET watch/kinds": () => withAccounts(["pat@example.com", "sam@example.com"]),
        "POST watch/sources": () => SAVED([], [{ id: "a" }]),
      }, { add: { plugin: "demo", n: 1 } });
      const form = await screen.findByRole("form", { name: "Add a source" });
      const pick = await within(form).findByLabelText("Account to read");
      expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual([
        "Choose an account",
        "pat@example.com",
        "sam@example.com",
      ]);
      const save = within(form).getByRole("button", { name: "Add source" });
      await waitFor(() => expect(within(form).getByLabelText("About folder")).toBeInTheDocument());
      expect(save).toBeDisabled(); // several accounts: one must be chosen
      await user.type(within(form).getByLabelText("About folder"), "INBOX");
      await user.selectOptions(pick, "sam@example.com");
      expect(save).toBeEnabled();
      await user.click(save);
      await waitFor(() => expect(body(calls, "POST watch/sources")).toBeDefined());
      expect(body(calls, "POST watch/sources")).toMatchObject({ connector: "demo/mailbox", account: "sam@example.com" });
    });

    test("with one signed in it is already chosen, and a source's own account is shown on its row and in Change", async () => {
      const user = userEvent.setup();
      const { calls } = open([source("a", { connector: "demo/mailbox", account: "sam@example.com" })], [], {
        "GET watch/kinds": () => withAccounts(["pat@example.com", "sam@example.com"]),
        "GET settings": () => stored(items("demo/mailbox")),
        "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]),
      });
      expect(within(await row("Source a")).getByText(/Reads sam@example.com/)).toBeInTheDocument();
      await choose(user, "Source a", "Change");
      const form = await screen.findByRole("form", { name: "Change Source a" });
      const pick = await within(form).findByLabelText("Account to read");
      expect(pick).toHaveValue("sam@example.com");
      await user.selectOptions(pick, "pat@example.com");
      await waitFor(() => expect(within(form).getByLabelText("About folder")).toBeInTheDocument());
      await user.click(within(form).getByRole("button", { name: "Save changes" }));
      await waitFor(() => expect(body(calls, "POST watch/sources/a")).toBeDefined());
      expect(body(calls, "POST watch/sources/a")).toMatchObject({ account: "pat@example.com" });
    });

    test("a kind with no accounts has no account list and sends none", async () => {
      open([], [], { "GET watch/kinds": () => KINDS }, { add: { plugin: "other", n: 1 } });
      const form = await screen.findByRole("form", { name: "Add a source" });
      await screen.findByLabelText("How often to read");
      expect(within(form).queryByLabelText("Account to read")).toBeNull();
    });
  });

  test("when the saved settings don't hold the source's own, only its name and schedule can change", async () => {
    const user = userEvent.setup();
    const { calls } = open([source("a", { connector: "folder" })], [], {
      "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
      "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]),
    });
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: "Change Source a" });
    expect(within(form).queryByLabelText("About path")).toBeNull();
    await user.selectOptions(within(form).getByLabelText("How often to read"), "60");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(body(calls, "POST watch/sources/a")).toBeDefined());
    expect(body(calls, "POST watch/sources/a")).toEqual({ label: "Source a", every_minutes: 60, author: null, fingerprint: "fp-1" });
  });

  test("Turn off acts at once, reads back with Undo, and a source that is off offers Turn on", async () => {
    const user = userEvent.setup();
    const { calls } = open([source("a")], [], {
      "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]),
      "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
    });
    await choose(user, "Source a", "Turn off");
    await waitFor(() => expect(body(calls, "POST watch/sources/a")).toEqual({ enabled: false, fingerprint: "fp-1" }));
    expect(await screen.findByText("Turned off Source a.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(body(calls, "POST settings")).toEqual({ changes: { "watch.sources": [{ id: "a" }] }, reset: [], fingerprint: "fp-2" }));
  });

  test("Turn on turns a source that is off back on", async () => {
    const user = userEvent.setup();
    const { calls } = open([source("a", { enabled: false })], [], { "POST watch/sources/a": () => SAVED([{ id: "a" }], [{ id: "a" }]) });
    await choose(user, "Source a", "Turn on");
    await waitFor(() => expect(body(calls, "POST watch/sources/a")).toEqual({ enabled: true, fingerprint: "fp-1" }));
    expect(await screen.findByText("Turned on Source a.")).toBeInTheDocument();
  });

  test("Remove acts at once with Undo, naming the source", async () => {
    const user = userEvent.setup();
    const { calls } = open([source("a")], [], {
      "POST watch/sources/a/remove": () => SAVED([{ id: "a" }], []),
      "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
    });
    await choose(user, "Source a", "Remove");
    await waitFor(() => expect(body(calls, "POST watch/sources/a/remove")).toEqual({ fingerprint: "fp-1" }));
    expect(await screen.findByText("Removed Source a.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  test("a refusal is said in a toast, and the source stays as it was", async () => {
    const user = userEvent.setup();
    open([source("a")], [], { "POST watch/sources/a/remove": () => new Refuse(409, "The settings changed. Try again.") });
    await choose(user, "Source a", "Remove");
    expect(await screen.findByText("That didn't work. The settings changed. Try again.")).toBeInTheDocument();
    expect(await row("Source a")).toBeInTheDocument();
  });
});

describe("a secret setting typed on the screen", () => {
  const post = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;
  const MAIL = kind("demo/mailbox", "A mailbox", "demo", [
    field("host", "text"),
    field("password", "text", { secret: true, description: "Where the password is kept, as a reference." }),
  ]);
  const routes = (local = true, mine: Source[] = []) => ({
    "GET watch/kinds": () => [MAIL],
    "GET setup": () => ({ steps: [], finished: true, local, walkthrough: {} }),
    "GET settings": () =>
      stored(mine.map((s) => ({ id: s.id, settings: { host: "mail.example.com", password: "file:/home/me/.cockpit/keys/source-a-password" } }))),
    "POST watch/sources": () => SAVED([], [{ id: "work-mail" }]),
    "POST watch/sources/a": () => SAVED([], [{ id: "a" }]),
  });

  test("on a local app it is a password box, and what is typed goes apart from the settings", async () => {
    const user = userEvent.setup();
    const calls = open([], [], routes()).calls;
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A mailbox" }));
    await user.type(screen.getByLabelText("Name"), "Work mail");
    await user.type(screen.getByLabelText("About host"), "mail.example.com");
    const box = await screen.findByLabelText("Where the password is kept, as a reference.");
    expect(box).toHaveAttribute("type", "password");
    expect(screen.getByText(/Type or paste it\./)).toBeInTheDocument();
    await user.type(box, "typed-value");
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await waitFor(() => expect(post(calls, "POST watch/sources")).toBeDefined());
    expect(post(calls, "POST watch/sources")).toMatchObject({
      settings: { host: "mail.example.com" },
      secrets: { password: "typed-value" },
    });
    expect(JSON.stringify(post(calls, "POST watch/sources"))).not.toContain('"password":"file');
  });

  test("Where it is kept instead shows a text box for the reference, and nothing typed is sent", async () => {
    const user = userEvent.setup();
    const calls = open([], [], routes()).calls;
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A mailbox" }));
    await user.type(await screen.findByLabelText("Where the password is kept, as a reference."), "abandoned");
    await user.click(screen.getByRole("button", { name: "Where it is kept instead" }));
    const where = screen.getByLabelText("Where the password is kept, as a reference.");
    expect(where).toHaveAttribute("type", "text");
    expect(where).toHaveValue("");
    await user.type(where, "env:MAIL_PASSWORD");
    await user.type(screen.getByLabelText("About host"), "mail.example.com");
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await waitFor(() => expect(post(calls, "POST watch/sources")).toBeDefined());
    const sent = post(calls, "POST watch/sources") as { settings: unknown; secrets: unknown };
    expect(sent.settings).toEqual({ host: "mail.example.com", password: "env:MAIL_PASSWORD" });
    expect(sent.secrets).toBeUndefined();
  });

  test("a secret the app keeps shows Kept on this computer, and Replace takes a new one", async () => {
    const user = userEvent.setup();
    const mine = source("a", { connector: "demo/mailbox", secrets: [{ field: "password", where: "kept", name: null }] });
    const calls = open([mine], [], routes(true, [mine])).calls;
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: /Change/ });
    expect(await within(form).findByText("Kept on this computer")).toBeInTheDocument();
    expect(within(form).queryByLabelText("Where the password is kept, as a reference.")).toBeNull();
    await user.click(within(form).getByRole("button", { name: "Replace Where the password is kept, as a reference." }));
    await user.type(within(form).getByLabelText("Where the password is kept, as a reference."), "new-value");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(post(calls, "POST watch/sources/a")).toBeDefined());
    const sent = post(calls, "POST watch/sources/a") as { settings: Record<string, unknown>; secrets: unknown };
    expect(sent.secrets).toEqual({ password: "new-value" });
    expect(sent.settings).not.toHaveProperty("password");
  });

  test("a secret read from a named place says where, never its value, and keeping the current one sends nothing new", async () => {
    const user = userEvent.setup();
    const mine = source("a", { connector: "demo/mailbox", secrets: [{ field: "password", where: "env", name: "MAIL_PASSWORD" }] });
    const calls = open([mine], [], routes(true, [mine])).calls;
    await choose(user, "Source a", "Change");
    const form = await screen.findByRole("form", { name: /Change/ });
    expect(await within(form).findByText("Stored in the setting named MAIL_PASSWORD")).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(post(calls, "POST watch/sources/a")).toBeDefined());
    expect(post(calls, "POST watch/sources/a")).not.toHaveProperty("secrets");
  });

  test("a calendar's private address is a password box beside the file choice, and what is typed goes apart from the settings", async () => {
    const user = userEvent.setup();
    const CALENDAR = kind("calendar", "A calendar", null, [
      field("address", "text", { secret: true, description: "The calendar's link." }),
      field("file", "text", { picker: "file", file_types: [".ics"], description: "A calendar file on this computer." }),
    ]);
    const address = "https" + "://calendar.example.com/private/token-9.ics";
    const calls = open([], [], { ...routes(), "GET watch/kinds": () => [CALENDAR] }).calls;
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    const box = await screen.findByLabelText("The calendar's link.");
    expect(box).toHaveAttribute("type", "password");
    await user.type(box, address);
    await user.click(screen.getByRole("button", { name: "Add source" }));
    await waitFor(() => expect(post(calls, "POST watch/sources")).toBeDefined());
    const sent = post(calls, "POST watch/sources") as { settings: Record<string, unknown>; secrets: Record<string, string> };
    expect(sent.secrets).toEqual({ address });
    expect(sent.settings).not.toHaveProperty("address");
    expect(JSON.stringify(sent.settings)).not.toContain(address);
  });

  test("on a hosted app only the box for where it is kept is offered", async () => {
    const user = userEvent.setup();
    open([], [], routes(false));
    await user.click(await screen.findByRole("button", { name: "Add a source" }));
    await user.click(await screen.findByRole("radio", { name: "A mailbox" }));
    const box = await screen.findByLabelText("Where the password is kept, as a reference.");
    await waitFor(() => expect(box).toHaveAttribute("type", "text"));
    expect(screen.getByText(/Enter the name of the environment variable storing this secret/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Where it is kept instead" })).toBeNull();
  });
});

test("a count that is zero is never said: a read that found nothing has no item count, and the counts of a read leave out the zeros", async () => {
  open([
    source("a", { items: 0, last: run({ new: 0, changed: 3, removed: 0 }) }),
    source("b", { items: 5, last: run({ new: 0, changed: 0, removed: 2 }) }),
  ]);
  const a = await row("Source a");
  expect(a).toHaveTextContent("A folder");
  expect(a).not.toHaveTextContent(/\b0 items?\b/);
  expect(a).toHaveTextContent("3 changed");
  expect(a).not.toHaveTextContent(/\b0 (new|removed)\b/);
  const b = await row("Source b");
  expect(b).toHaveTextContent("5 items");
  expect(b).toHaveTextContent("2 removed");
  expect(b).not.toHaveTextContent(/\b0 (new|changed)\b/);
});

// ---- the sent folder, offered as a second source (design 6.33) ----------------------------------------------------

const mailbox = (extra: Partial<Source> = {}) => source("work-mail", { connector: "mailbox", connector_label: "A mail folder (IMAP)", reads: ["mail"], ...extra });
const folders = (extra: Partial<S["MailFoldersView"]> = {}): S["MailFoldersView"] => ({ folders: ["INBOX", "Sent Items", "Drafts"], sent: "Sent Items", taken: ["INBOX"], ...extra });

test("a mailbox offers the folder its server marks as sent, picked already, with one button to read it too", async () => {
  const user = userEvent.setup();
  const { calls } = open([mailbox()], [], {
    "GET watch/work-mail/folders": () => folders(),
    "POST watch/work-mail/sent-folder": () => SAVED([], []),
  });
  const item = await row("Source work-mail");
  const list = await within(item).findByRole("combobox", { name: "Folder of the mail you sent" });
  expect(list).toHaveValue("Sent Items");
  expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["Sent Items", "Drafts"]); // INBOX is read already
  expect(item).toHaveTextContent("Also read the mail you sent, so promises you make are noticed.");
  await user.click(within(item).getByRole("button", { name: "Read it too" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST watch/work-mail/sent-folder")?.body).toMatchObject({ folder: "Sent Items", label: "Source work-mail, sent" }));
});

test("when the server marks no sent folder the person picks, and the button waits for the pick", async () => {
  const user = userEvent.setup();
  open([mailbox()], [], { "GET watch/work-mail/folders": () => folders({ sent: null }) });
  const item = await row("Source work-mail");
  const list = await within(item).findByRole("combobox", { name: "Folder of the mail you sent" });
  expect(list).toHaveValue("");
  expect(within(item).getByRole("button", { name: "Read it too" })).toBeDisabled();
  await user.selectOptions(list, "Drafts");
  expect(within(item).getByRole("button", { name: "Read it too" })).toBeEnabled();
});

test("nothing is offered once the sent folder is read, for another kind of source, or while the mailbox can't be read", async () => {
  open([mailbox(), source("a"), mailbox({ id: "broken", label: "Broken", problem: "It can't be read: refused." })], [], {
    "GET watch/work-mail/folders": () => folders({ taken: ["INBOX", "Sent Items"] }),
  });
  await row("Source work-mail");
  await waitFor(() => expect(document.querySelector("[data-sent-offer]")).toBeNull());
  expect(screen.queryByRole("button", { name: "Read it too" })).toBeNull();
});
