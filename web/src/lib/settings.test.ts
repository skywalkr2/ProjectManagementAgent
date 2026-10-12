import type { S } from "./api";
import {
  changedValues,
  formatValue,
  formValues,
  fromDraft,
  groupItems,
  groupLabel,
  labelForKey,
  labelOf,
  nest,
  prefill,
  restartWhat,
  toDraft,
  undoBody,
  valueAt,
} from "./settings";

const t = (key: string, vars: Record<string, string | number> = {}) =>
  ({ "settings.empty": "(empty)", "settings.yes": "Yes", "settings.no": "No" })[key] ?? `${key}${JSON.stringify(vars)}`;
const none = () => false;

function item(extra: Partial<S["SettingItem"]> & { key: string }): S["SettingItem"] {
  return {
    file: "demo",
    group: "demo",
    description: `About ${extra.key}`,
    type: "text",
    options: [],
    value: "",
    default: "",
    source: "default",
    locked: false,
    basic: false,
    editable: true,
    ...extra,
  };
}

test("values round trip through what a control edits", () => {
  expect(toDraft(item({ key: "a.b", type: "list", value: ["x", "y"] }))).toBe("x\ny");
  expect(fromDraft(item({ key: "a.b", type: "list" }), " x \n\n y ")).toEqual({ ok: true, value: ["x", "y"] });
  expect(toDraft(item({ key: "a.b", type: "yes_no", value: true }))).toBe(true);
  expect(fromDraft(item({ key: "a.b", type: "yes_no" }), false)).toEqual({ ok: true, value: false });
  expect(fromDraft(item({ key: "a.b", type: "number" }), "2.5")).toEqual({ ok: true, value: 2.5 });
  expect(fromDraft(item({ key: "a.b", type: "integer" }), "12")).toEqual({ ok: true, value: 12 });
});

test("a number control refuses what is not a number, and an integer one what is not whole", () => {
  expect(fromDraft(item({ key: "a.b", type: "number" }), "lots")).toEqual({ ok: false, problem: "number" });
  expect(fromDraft(item({ key: "a.b", type: "number" }), "")).toEqual({ ok: false, problem: "number" });
  expect(fromDraft(item({ key: "a.b", type: "integer" }), "2.5")).toEqual({ ok: false, problem: "integer" });
});

test("values are shown in plain words", () => {
  expect(formatValue(true, t)).toBe("Yes");
  expect(formatValue([], t)).toBe("(empty)");
  expect(formatValue(["a", "b"], t)).toBe("a, b");
  expect(formatValue(null, t)).toBe("(empty)");
  expect(formatValue(3, t)).toBe("3");
});

test("a label comes from the wording sheet when there is one, otherwise it is the description", () => {
  const i = item({ key: "a.b" });
  expect(labelOf(i, t, none)).toBe("About a.b");
  expect(labelOf(i, () => "Short label", (k) => k === "settings.key.a.b")).toBe("Short label");
  expect(groupLabel("ai.rate_limits", t, none)).toBe("AI rate limits");
});

test("basic settings come first, the rest only when asked for, and a search looks at everything", () => {
  const items = [
    item({ key: "x.hidden", group: "x", basic: false }),
    item({ key: "y.shown", group: "y", basic: true }),
    item({ key: "x.shown", group: "x", basic: true }),
    item({ key: "z.hidden", group: "z", description: "Needle in here" }),
  ];
  const keys = (groups: ReturnType<typeof groupItems>) => groups.flatMap((g) => g.items.map((i) => i.key));
  expect(keys(groupItems(items, { more: false, query: "" }, t, none))).toEqual(["y.shown", "x.shown"]);
  expect(keys(groupItems(items, { more: true, query: "" }, t, none))).toEqual(["x.shown", "x.hidden", "y.shown", "z.hidden"]);
  expect(keys(groupItems(items, { more: false, query: "needle" }, t, none))).toEqual(["z.hidden"]);
  expect(keys(groupItems(items, { more: false, query: "X.HIDDEN" }, t, none))).toEqual(["x.hidden"]);
});

test("undo puts back the old values, and returns what was default to default", () => {
  const body = undoBody(
    [
      { key: "a.one", before: "old", after: "new", was_default: false, is_default: false },
      { key: "a.two", before: "x", after: "y", was_default: true, is_default: false },
    ],
    "fp-2",
  );
  expect(body).toEqual({ changes: { "a.one": "old" }, reset: ["a.two"], fingerprint: "fp-2" });
});

const words: Record<string, string> = {
  "settings.group.demo": "Demo group",
  "settings.key.demo.known": "Known setting",
  "restart.for": "Restart to use: {what}.",
  "restart.for_more": "{list} and {n} more",
  "restart.for_code": "an update to the app",
  "restart.for_addons": "a change to the add-ons",
  "restart.for_other": "other settings",
};
const tw = (key: string, vars: Record<string, string | number> = {}) =>
  (words[key] ?? key).replace(/\{(\w+)\}/g, (_m, name: string) => String(vars[name]));
const hasWord = (key: string) => key in words;

test("an add-on's group is named for the add-on, never by where it lives, and comes after the app's groups", () => {
  const items = [
    item({ key: "plugins/sample-pack.a", group: "plugins/sample-pack", plugin: "sample-pack", basic: true }),
    item({ key: "demo.x", group: "demo", basic: true }),
    item({ key: "plugins/other.b", group: "plugins/other", plugin: "other", basic: true }),
    item({ key: "demo.y", group: "demo.deep", basic: false }),
  ];
  expect(groupLabel("plugins/sample-pack", tw, hasWord)).toBe("Sample pack");
  const groups = groupItems(items, { more: true, query: "" }, tw, hasWord).map((g) => g.group);
  expect(groups).toEqual(["demo", "demo.deep", "plugins/sample-pack", "plugins/other"]);
});

test("a key is named by its setting's label, else its group's, else a general phrase", () => {
  const items = [item({ key: "demo.plain", description: "Plain words" })];
  expect(labelForKey("demo.plain", items, tw, hasWord)).toBe("Plain words");
  expect(labelForKey("demo.known", [], tw, hasWord)).toBe("Known setting");
  expect(labelForKey("demo.other", [], tw, hasWord)).toBe("Demo group");
  expect(labelForKey("plugins/sample-pack.x", [], tw, hasWord)).toBe("Sample pack");
  expect(labelForKey("mystery.thing", [], tw, hasWord)).toBe("other settings");
});

test("what waits for a restart lists up to three names without repeats, then how many more", () => {
  expect(restartWhat([], [], tw, hasWord)).toBe("");
  expect(restartWhat(["code"], [], tw, hasWord)).toBe("Restart to use: an update to the app.");
  expect(restartWhat(["add-ons"], [], tw, hasWord)).toBe("Restart to use: a change to the add-ons.");
  expect(restartWhat(["demo.known", "demo.known"], [], tw, hasWord)).toBe("Restart to use: Known setting.");
  expect(restartWhat(["demo.known", "demo.a", "code", "plugins/p.q", "mystery.thing"], [], tw, hasWord)).toBe(
    "Restart to use: Known setting, Demo group, an update to the app and 2 more.",
  );
});

test("dotted keys become nested values and can be read back by key", () => {
  expect(nest({ a: 1, "b.c": 2, "b.d.e": [3] })).toEqual({ a: 1, b: { c: 2, d: { e: [3] } } });
  expect(valueAt({ b: { c: 2 } }, "b.c")).toBe(2);
  expect(valueAt({ b: { c: 2 } }, "b.x")).toBeUndefined();
  expect(valueAt({ b: [1] }, "b.0")).toBeUndefined();
  expect(valueAt(undefined, "a")).toBeUndefined();
});

test("a form is filled from a nested settings object where it has a value, and keeps the item's own where it hasn't", () => {
  const items = [item({ key: "a", value: "x" }), item({ key: "b.c", value: 1, type: "integer" })];
  const filled = prefill(items, { b: { c: 5 } });
  expect(filled.map((i) => i.value)).toEqual(["x", 5]);
  expect(prefill(items, undefined).map((i) => i.value)).toEqual(["x", 1]);
});

test("a form sends only what differs from the defaults, and names what can't be sent", () => {
  const items = [
    item({ key: "path", default: null, value: null }),
    item({ key: "days", type: "integer", default: 30, value: 30 }),
    item({ key: "on", type: "yes_no", default: false, value: false }),
    item({ key: "tags", type: "list", default: [], value: [] }),
    item({ key: "fixed", default: "x", value: "x", editable: false }),
    item({ key: "raw", type: "other", default: [], value: [] }),
  ];
  expect(formValues(items, {}).values).toEqual({});
  const sent = formValues(items, { path: " inbox ", days: "7", on: true, tags: "a\nb", fixed: "changed", raw: "ignored" });
  expect(sent.values).toEqual({ path: "inbox", days: 7, on: true, tags: ["a", "b"] });
  expect(sent.bad).toEqual([]);
  // A value equal to the default isn't sent, and a number that isn't a number is named.
  expect(formValues(items, { days: "30" }).values).toEqual({});
  expect(formValues(items, { days: "soon" }).bad).toEqual(["days"]);
});

test("a data file save sends only the fields changed on screen", () => {
  const items = [item({ key: "title", value: "A" }), item({ key: "sizes.body", type: "integer", value: 11 }), item({ key: "locked", value: "x", locked: true })];
  expect(changedValues(items, {}).changes).toEqual({});
  expect(changedValues(items, { title: "A", "sizes.body": "12", locked: "y" })).toEqual({ changes: { "sizes.body": 12 }, bad: [] });
  expect(changedValues(items, { "sizes.body": "big" }).bad).toEqual(["sizes.body"]);
});
