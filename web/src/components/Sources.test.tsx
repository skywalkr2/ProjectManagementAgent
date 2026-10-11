import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
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

function open(sources: Source[], items: S["AutoClosedView"][] = [], extra: Record<string, (b: unknown) => unknown> = {}) {
  const calls = fakeApi({ "GET watch": () => sources, "GET auto-closed": () => items, ...extra });
  const onAsk = vi.fn();
  renderApp(<Sources onAsk={onAsk} />);
  return { calls, onAsk };
}

const row = async (label: string) => (await screen.findByRole("listitem", { name: label })) as HTMLElement;

test("a source shows its kind, how often it is read and its last read in words", async () => {
  open([source("a", { last: run({ new: 2, changed: 1, removed: 0 }) })]);
  const item = await row("Source a");
  expect(item).toHaveTextContent("A folder · every 15 minutes · 3 items");
  expect(item).toHaveTextContent("2 new, 1 changed, 0 gone");
  expect(item).toHaveTextContent(/Last read .*: 2 new/);
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
    source("fresh", { last: null }),
  ]);
  expect(await row("Source quiet")).toHaveTextContent("Nothing new");
  expect(await row("Source first")).toHaveTextContent("First read: noted what is there");
  expect(await row("Source away")).toHaveTextContent("Not read: no network");
  const broken = await row("Source broken");
  expect(broken).toHaveTextContent("Couldn't be read");
  expect(broken).toHaveTextContent("Failed 3 times in a row");
  expect(within(broken).getByText("It can't be read: refused. Sign in again.")).toBeInTheDocument();
  expect(await row("Source fresh")).toHaveTextContent("Not read yet");
});

test("a source without a kind says so, and a source that is off says Off and can't be read now", async () => {
  open([source("a", { connector_label: "", enabled: false })]);
  const item = await row("Source a");
  expect(item).toHaveTextContent("Not available · Off");
  expect(within(item).getByRole("button", { name: "Read Source a now" })).toBeDisabled();
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
  await user.click(within(await row("Source a")).getByRole("button", { name: "Read Source a now" }));
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
  await user.click(within(await row("Source a")).getByRole("button", { name: "Read Source a now" }));
  await waitFor(() => expect(screen.getByRole("listitem", { name: "Source a" })).toHaveTextContent("4 new, 0 changed, 0 gone"));
  expect(screen.getByRole("listitem", { name: "Source a" })).toHaveTextContent("7 items");
  expect(calls.some((c) => c.route === "POST watch/a/read")).toBe(true);
  expect(await screen.findByText("Source a: 4 new, 0 changed, 0 gone")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST watch/b/read")).toBe(false);
});

test("a read that fails says why in the message", async () => {
  open([source("a")], [], {
    "POST watch/a/read": () =>
      source("a", { last: run({ outcome: "failed" }), failures: 1, problem: "Can't reach it. Try later." }),
  });
  const user = userEvent.setup();
  await user.click(within(await row("Source a")).getByRole("button", { name: "Read Source a now" }));
  expect(await screen.findByText("Source a: Can't reach it. Try later.")).toBeInTheDocument();
});

test("with no sources, the screen says where they are set up and offers to ask how", async () => {
  const { onAsk } = open([]);
  expect(await screen.findByText(/listed in watch\.yaml/)).toBeInTheDocument();
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
  expect(await row("Other item")).toHaveTextContent("Gone");
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
