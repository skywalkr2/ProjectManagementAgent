import type { S } from "./api";
import { coverage, whenWords } from "./coverage";
import { time } from "./dates";

const NOW = new Date(2026, 9, 19, 9, 0);
const iso = (d: Date) => d.toISOString();

const source = (id: string, extra: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] => ({
  id,
  label: id,
  connector: "kind-a",
  connector_label: "A kind",
  enabled: true,
  every_minutes: 15,
  items: 0,
  last: null,
  read_at: null,
  failures: 0,
  problem: null,
  ...extra,
});
const ran = (outcome: "ok" | "failed" | "offline", when: Date): S["WatchSourceView"]["last"] => ({ outcome, started_at: iso(when), new: 0, changed: 0, removed: 0 });
const readAt = (id: string, when: Date) => source(id, { last: ran("ok", when), read_at: iso(when) });

test("sources are sorted into read, couldn't be read and not read yet, and a source that is off is left out", () => {
  const a = readAt("a", new Date(2026, 9, 19, 7, 40));
  const b = readAt("b", new Date(2026, 9, 19, 7, 10));
  const c = source("c", { last: ran("failed", new Date(2026, 9, 19, 8, 0)), read_at: iso(new Date(2026, 9, 18, 18, 0)) });
  const d = source("d", { enabled: false });
  const e = source("e");
  const found = coverage([a, b, c, d, e]);
  expect(found.enabled).toBe(4);
  expect(found.read.map((s) => s.id)).toEqual(["a", "b"]);
  expect(found.last).toBe(a.read_at);
  expect(found.unread.map((u) => [u.source.id, u.kind])).toEqual([["c", "failed"]]);
  expect(found.pending.map((s) => s.id)).toEqual(["e"]);
  expect(found.complete).toBe(false);
});

test("a try that found no network counts as not read, in its own kind", () => {
  const found = coverage([source("a", { last: ran("offline", NOW), read_at: iso(new Date(2026, 9, 19, 6, 0)) })]);
  expect(found.read).toEqual([]);
  expect(found.unread.map((u) => u.kind)).toEqual(["offline"]);
});

test("everything on and read is complete; nothing on is not a coverage at all", () => {
  expect(coverage([readAt("a", NOW)]).complete).toBe(true);
  expect(coverage([source("a", { enabled: false })]).enabled).toBe(0);
});

test("a time is said by itself today, with yesterday named, and with its day before that", () => {
  const t = (key: string, vars?: Record<string, string | number>) => (key === "coverage.yesterday" ? `yesterday ${vars?.time}` : key);
  expect(whenWords(iso(new Date(2026, 9, 19, 7, 40)), NOW, t)).toBe(time(new Date(2026, 9, 19, 7, 40)));
  expect(whenWords(iso(new Date(2026, 9, 18, 18, 0)), NOW, t)).toBe(`yesterday ${time(new Date(2026, 9, 18, 18, 0))}`);
  expect(whenWords(iso(new Date(2026, 9, 12, 18, 0)), NOW, t)).toMatch(/12/);
});
