import type { S } from "./api";
import { isListed, navSections, sectionItems, sectionOfItem, topics } from "./settings-sections";

function item(key: string, group: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  return {
    key,
    file: key.split(".")[0],
    group,
    description: `What ${key} does`,
    type: "text",
    options: [],
    value: "",
    default: "",
    source: "default",
    locked: false,
    basic: true,
    editable: true,
    ...extra,
  };
}

const ITEMS = [
  item("workspace.name", "workspace"),
  item("workspace.user.timezone", "workspace.user"),
  item("workspace.plugins.catalog.enabled", "workspace.plugins.catalog", { basic: false }),
  item("ai.budgets.per_run_usd", "ai.budgets"),
  item("ai.roles.cheap", "ai.roles", { basic: false }),
  item("storage.sync.folder", "storage.sync"),
  item("ui.theme", "ui"),
  item("ui.brand.color", "ui.brand", { basic: false }),
  item("ui.today.lines", "ui.today", { basic: false }),
  item("dispatch.knowledge.learn", "dispatch.knowledge", { basic: false }),
  item("plugins/sample-pack.greeting", "plugins/sample-pack", { plugin: "sample-pack" }),
];

test("each setting belongs to one section, by its group", () => {
  const by = Object.fromEntries(ITEMS.map((i) => [i.key, sectionOfItem(i)]));
  expect(by).toEqual({
    "workspace.name": "you",
    "workspace.user.timezone": "you",
    "workspace.plugins.catalog.enabled": "advanced",
    "ai.budgets.per_run_usd": "ai",
    "ai.roles.cheap": "ai",
    "storage.sync.folder": "backups",
    "ui.theme": "appearance",
    "ui.brand.color": "appearance",
    "ui.today.lines": "today",
    "dispatch.knowledge.learn": "advanced",
    "plugins/sample-pack.greeting": "addon/sample-pack",
  });
});

test("a section lists its basic settings first, and every setting is in exactly one section", () => {
  const you = sectionItems(ITEMS, "you").map((i) => i.key);
  expect(you).toEqual(["workspace.name", "workspace.user.timezone"]);
  const ai = sectionItems(ITEMS, "ai").map((i) => i.key);
  expect(ai).toEqual(["ai.budgets.per_run_usd", "ai.roles.cheap"]);
  const all = navSections(ITEMS, { lists: true, files: true }).flatMap((s) => sectionItems(ITEMS, s));
  expect(all.length).toBe(ITEMS.length);
});

test("the section list has the basic sections first, then lists and files where there are some, Advanced, then each add-on", () => {
  expect(navSections(ITEMS, { lists: true, files: true })).toEqual([
    "you", "ai", "backups", "today", "appearance", "lists", "files", "advanced", "addon/sample-pack",
  ]);
  // Nothing to show means no entry, except AI accounts, which always has its list.
  expect(navSections([item("workspace.name", "workspace")], { lists: false, files: false })).toEqual(["you", "ai"]);
});

test("Advanced is grouped by topic, one topic for each group, in the order the groups first appear", () => {
  const adv = sectionItems(ITEMS, "advanced");
  expect(topics(adv).map((t) => [t.group, t.items.length])).toEqual([
    ["workspace.plugins.catalog", 1],
    ["dispatch.knowledge", 1],
  ]);
});

test("the tier of each kind of work, what a tier tries once more on and the routing rules are not rows of their own: a part of the AI section edits them", () => {
  const own = [item("ai.tasks", "ai", { type: "other" }), item("ai.tiers", "ai", { type: "other" }), item("ai.routing", "ai", { type: "other" })];
  expect(own.map(isListed)).toEqual([false, false, false]);
  expect(sectionItems([...ITEMS, ...own], "ai").map((i) => i.key)).not.toEqual(expect.arrayContaining(["ai.routing"]));
  expect(sectionItems([...ITEMS, ...own], "ai").map((i) => i.key)).toContain("ai.budgets.per_run_usd");
});

test("the accounts the assistant may act on are a switch on each account, not a row of their own", () => {
  const acting = item("watch.acting", "watch", { type: "list" });
  expect(isListed(acting)).toBe(false);
  expect(sectionItems([...ITEMS, acting], "advanced").map((i) => i.key)).not.toContain("watch.acting");
});
