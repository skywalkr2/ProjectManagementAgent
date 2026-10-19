import type { S } from "./api";
import { anyReading, failureText, latestRead, readProblem } from "./sources";

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
    source("a", { last: ran("2026-03-04T10:30:00+00:00"), read_at: "2026-03-04T10:30:00+00:00" }),
    source("b", { last: ran("2026-03-04T12:05:00+00:00"), read_at: "2026-03-04T12:05:00+00:00" }),
    source("c", { last: null }),
    source("d", { last: ran("2026-03-03T23:00:00+00:00"), read_at: "2026-03-03T23:00:00+00:00" }),
  ];
  expect(latestRead(sources)).toBe("2026-03-04T12:05:00+00:00");
});

test("a try that found no network does not count as the latest read", () => {
  const away: S["WatchSourceView"]["last"] = { outcome: "offline", started_at: "2026-03-04T20:00:00+00:00", new: 0, changed: 0, removed: 0 };
  expect(latestRead([source("a", { last: away, read_at: "2026-03-04T10:30:00+00:00" })])).toBe("2026-03-04T10:30:00+00:00");
  expect(latestRead([source("a", { last: away, read_at: null })])).toBeNull();
});

describe("why a source couldn't be read", () => {
  const words: Record<string, string> = {
    "sources.advice.create_app_password": "This service wants an app password. Type it in the password box in this source's settings.",
    "sources.problem_generic": "It couldn't be read.",
    "sources.read_failed": "{label} couldn't be read. Open Sources to see why.",
  };
  const t = (key: string, vars: Record<string, string | number> = {}) => (words[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
  const has = (key: string) => key in words;
  const failed = (extra: Partial<NonNullable<S["WatchSourceView"]["last"]>>): S["WatchSourceView"]["last"] => ({
    outcome: "failed",
    started_at: "2026-03-04T10:30:00+00:00",
    new: 0,
    changed: 0,
    removed: 0,
    error_kind: "auth",
    ...extra,
  });
  const said = "the mail server refused the sign-in; it said “Application-specific password required”.";

  test("the connector's advice key is worded from the sheet, after the server's own words", () => {
    const mail = source("m", { last: failed({ error: said, error_advice: "sources.advice.create_app_password" }), problem: `${said} Sign in to it again.` });
    expect(failureText(mail, t, has)).toBe(`${said} This service wants an app password. Type it in the password box in this source's settings.`);
    expect(readProblem(mail, t, has)).toBe(failureText(mail, t, has));
  });

  test("with no advice key, or one the sheet lacks, the kind's usual sentence stands", () => {
    const plain = source("p", { last: failed({ error: "refused" }), problem: "refused. Sign in to it again." });
    expect(failureText(plain, t, has)).toBe("refused. Sign in to it again.");
    const unknown = source("u", { last: failed({ error: "refused", error_advice: "sources.advice.nothing" }), problem: "refused. Sign in to it again." });
    expect(failureText(unknown, t, has)).toBe("refused. Sign in to it again.");
  });

  test("a read that didn't fail has no problem", () => {
    expect(failureText(source("a", { last: ran("2026-03-04T10:30:00+00:00") }), t, has)).toBeNull();
  });
});
