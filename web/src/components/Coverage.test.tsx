import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import type { S } from "../lib/api";
import { time } from "../lib/dates";
import { fakeApi, renderApp } from "../test-utils";
import { CoverageLine, NothingNeedsYou } from "./Coverage";

// Mid-morning on a made-up Monday; only the date is faked so waiting still works.
const NOW = new Date(2026, 9, 19, 9, 0);
const LATEST = new Date(2026, 9, 19, 7, 40);
const YESTERDAY_EVENING = new Date(2026, 9, 18, 18, 0);
const iso = (d: Date) => d.toISOString();

function source(id: string, extra: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] {
  return { id, label: id, connector: "kind-a", connector_label: "A kind", enabled: true, every_minutes: 15, items: 0, last: null, read_at: null, failures: 0, problem: null, ...extra };
}
const outcome = (kind: "ok" | "failed" | "offline", when: Date): S["WatchSourceView"]["last"] => ({ outcome: kind, started_at: iso(when), new: 0, changed: 0, removed: 0 });
const readAt = (id: string, when: Date) => source(id, { last: outcome("ok", when), read_at: iso(when) });
const failing = (id: string, label: string) => source(id, { label, last: outcome("failed", NOW), read_at: iso(YESTERDAY_EVENING), failures: 4 });

const threeRead = [readAt("a", new Date(2026, 9, 19, 7, 10)), readAt("b", LATEST), readAt("c", new Date(2026, 9, 19, 6, 0))];

function open(sources: S["WatchSourceView"][] | null, ui = <CoverageLine />) {
  fakeApi(sources === null ? {} : { "GET watch": () => sources });
  renderApp(ui);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

test("the line says how many sources were read and when the latest read was", async () => {
  open(threeRead);
  const line = await screen.findByText(`Read 3 sources, last at ${time(LATEST)}`);
  expect(line.closest("[data-coverage-line]")).not.toBeNull();
  expect(document.querySelector('[data-coverage="unread"]')).toBeNull();
});

test("a source that couldn't be read is named with since when, apart from what was read, in its own words and style", async () => {
  open([...threeRead.slice(0, 2), failing("m", "Work mail")]);
  const read = await screen.findByText(`Read 2 sources, last at ${time(new Date(2026, 9, 19, 7, 40))}`);
  const unread = screen.getByText(`Work mail couldn't be read since yesterday ${time(YESTERDAY_EVENING)}`);
  // One line, two kinds of thing: marked apart (the style follows the mark) and worded apart, so colour is never the only difference.
  expect(read.closest("[data-coverage-line]")).toBe(unread.closest("[data-coverage-line]"));
  expect(read.getAttribute("data-coverage")).toBe("read");
  expect(unread.getAttribute("data-coverage")).toBe("unread");
});

test("a source that was never read, or is not read yet, is said so", async () => {
  open([readAt("a", LATEST), source("n", { label: "Team calendar" }), source("m", { label: "Work mail", last: outcome("failed", NOW) })]);
  expect(await screen.findByText("Team calendar not read yet")).toBeInTheDocument();
  expect(screen.getByText("Work mail couldn't be read yet")).toBeInTheDocument();
});

test("with no source on, or none known yet, there is no line", async () => {
  open([source("a", { enabled: false })]);
  await waitFor(() => expect(document.querySelector("[data-coverage-line]")).toBeNull());
});

test("an empty Today says nothing needs you together with what was read", async () => {
  open(threeRead, <NothingNeedsYou />);
  const empty = await screen.findByText((_, el) => el?.hasAttribute("data-queue-empty") === true && /^Nothing needs you · Read 3 sources, last at/.test(el.textContent ?? ""));
  expect(empty).toHaveTextContent(`Nothing needs you · Read 3 sources, last at ${time(LATEST)}`);
});

test("an empty Today never says nothing needs you alone when a source couldn't be read", async () => {
  open([readAt("a", LATEST), failing("m", "Work mail")], <NothingNeedsYou />);
  const empty = await screen.findByText((_, el) => el?.hasAttribute("data-queue-empty") === true && /couldn't be read/.test(el.textContent ?? ""));
  expect(empty).toHaveTextContent(`Nothing found that needs you · Read 1 source, last at ${time(LATEST)} · Work mail couldn't be read since yesterday`);
  expect(empty.textContent).not.toMatch(/^Nothing needs you/);
  expect(screen.queryByText("Nothing needs you right now.")).toBeNull();
});

test("an empty Today with sources not read yet is not a clean 'nothing needs you' either", async () => {
  open([source("n", { label: "Team calendar" })], <NothingNeedsYou />);
  const empty = await screen.findByText((_, el) => el?.hasAttribute("data-queue-empty") === true && /Team calendar not read yet/.test(el.textContent ?? ""));
  expect(empty).toHaveTextContent("Nothing found that needs you · Team calendar not read yet");
});

test("with no sources known, the empty Today keeps its plain sentence", async () => {
  open(null, <NothingNeedsYou />);
  expect(await screen.findByText("Nothing needs you right now.")).toBeInTheDocument();
});
