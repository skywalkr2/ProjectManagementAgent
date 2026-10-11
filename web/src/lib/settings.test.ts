import type { S } from "./api";
import { formatValue, fromDraft, groupItems, groupLabel, labelForKey, labelOf, restartWhat, toDraft, undoBody } from "./settings";

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
  expect(restartWhat(["demo.known", "demo.known"], [], tw, hasWord)).toBe("Restart to use: Known setting.");
  expect(restartWhat(["demo.known", "demo.a", "code", "plugins/p.q", "mystery.thing"], [], tw, hasWord)).toBe(
    "Restart to use: Known setting, Demo group, an update to the app and 2 more.",
  );
});
