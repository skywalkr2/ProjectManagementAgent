import type { S } from "./api";
import { anyReading, latestRead } from "./sources";

const source = (id: string, extra: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] => ({
  id,
  label: id,
  connector: "kind-a",
  connector_label: "A kind",
  enabled: true,
  every_minutes: 15,
  items: 0,
  last: null,
  failures: 0,
  problem: null,
  ...extra,
});
const ran = (started_at: string): S["WatchSourceView"]["last"] => ({ outcome: "ok", started_at, new: 0, changed: 0, removed: 0 });

test("sources are reading when at least one is on", () => {
  expect(anyReading([])).toBe(false);
  expect(anyReading([source("a", { enabled: false }), source("b", { enabled: false })])).toBe(false);
  expect(anyReading([source("a", { enabled: false }), source("b")])).toBe(true);
});

test("the latest read is the most recent start across sources, whatever order they are in", () => {
  expect(latestRead([])).toBeNull();
  expect(latestRead([source("a")])).toBeNull();
  const sources = [
    source("a", { last: ran("2026-03-04T10:30:00+00:00") }),
    source("b", { last: ran("2026-03-04T12:05:00+00:00") }),
    source("c", { last: null }),
    source("d", { last: ran("2026-03-03T23:00:00+00:00") }),
  ];
  expect(latestRead(sources)).toBe("2026-03-04T12:05:00+00:00");
});
