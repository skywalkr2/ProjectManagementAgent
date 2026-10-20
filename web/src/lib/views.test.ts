import { fromHash, panelView, parseView, recordView, settingsSectionOf, settingsView, toHash, viewHref } from "./views";

const routes = [
  "today",
  "work/changed",
  "work/followups",
  "work/open",
  "work/outgoing",
  "work/stages",
  "records/projects",
  "records/people",
  "records/files",
  "records/knowledge",
  "records/rules-review",
  "sources",
  "addons",
  "settings",
  "settings/ai-compare",
  "setup",
  "quality",
  "styleguide",
] as const;

test("every view's fragment names it, and Today is the empty fragment's view", () => {
  for (const view of routes) {
    expect(toHash(view)).toBe(view);
    expect(fromHash(`#${view}`)).toBe(view);
  }
  expect(fromHash("")).toBe("today");
  expect(fromHash("#")).toBe("today");
  expect(fromHash("#nonsense")).toBe("today");
});

test("fragments from earlier versions still open the matching view", () => {
  expect(fromHash("#stages")).toBe("work/stages");
  expect(fromHash("#files")).toBe("records/files");
  expect(fromHash("#sources")).toBe("sources");
  expect(fromHash("#settings")).toBe("settings");
  expect(fromHash("#addons")).toBe("addons");
  // The guide had two names; both open it.
  expect(fromHash("#welcome")).toBe("setup");
  expect(fromHash("#setup")).toBe("setup");
  expect(fromHash("#panel:demo%2Fgoals")).toBe(panelView("demo/goals", "work"));
  expect(fromHash("#record:demo%2Fchapter:CH%201")).toBe(recordView("demo/chapter", "CH 1"));
});

test("a plugin's panel round trips under Work or Records, with awkward characters in its name", () => {
  for (const group of ["work", "records"] as const) {
    const panel = panelView("demo/goals #1", group);
    expect(parseView(panel)).toEqual({ type: "panel", group, name: "demo/goals #1" });
    expect(toHash(panel)).not.toContain("#");
    expect(fromHash(`#${toHash(panel)}`)).toBe(panel);
  }
  // A hand-typed address with the slash unencoded is understood too.
  expect(fromHash("#work/panel/demo/goals")).toBe(panelView("demo/goals", "work"));
});

test("a record page round trips with awkward characters in its kind and id", () => {
  const record = recordView("demo/chapter", "CH 1:2#3");
  expect(parseView(record)).toEqual({ type: "record", kind: "demo/chapter", id: "CH 1:2#3" });
  expect(fromHash(`#${toHash(record)}`)).toBe(record);
  expect(parseView(recordView("person", "PER-1"))).toEqual({ type: "record", kind: "person", id: "PER-1" });
  expect(toHash(recordView("person", "PER-1"))).toBe("records/person/PER-1");
});

test("a core view parses as one", () => {
  expect(parseView("work/changed")).toEqual({ type: "core", view: "work/changed" });
});

test("a fragment that names nothing is Today", () => {
  expect(fromHash("#work/panel/")).toBe("today");
  expect(fromHash("#panel:")).toBe("today");
  expect(fromHash("#record:demo%2Fchapter")).toBe("today");
  expect(fromHash("#records/person")).toBe("today");
  expect(fromHash("#records/%E0%A4%A/x")).toBe("today");
});

test("a view's link keeps this page's path and query, so it works in a new tab", () => {
  window.history.replaceState(null, "", "/admin/?token=t");
  expect(viewHref("work/stages")).toBe("/admin/?token=t#work/stages");
  window.history.replaceState(null, "", "/");
});

test("each section of Settings has its own address, and an add-on's section carries the add-on's name", () => {
  for (const section of ["you", "ai", "backups", "today", "appearance", "lists", "files", "advanced"] as const) {
    const view = settingsView(section);
    expect(toHash(view)).toBe(`settings/${section}`);
    expect(fromHash(`#${toHash(view)}`)).toBe(view);
    expect(parseView(view)).toEqual({ type: "core", view: "settings", section });
    expect(settingsSectionOf(view)).toBe(section);
  }
  const addon = settingsView("addon/sample pack");
  expect(toHash(addon)).toBe("settings/addon/sample%20pack");
  expect(fromHash(`#${toHash(addon)}`)).toBe(addon);
  expect(parseView(addon)).toEqual({ type: "core", view: "settings", section: "addon/sample pack" });
});

test("Settings without a section, the grid of what accounts can do, and a section nobody knows are not sections", () => {
  expect(settingsSectionOf("settings")).toBeNull();
  expect(settingsSectionOf("settings/ai-compare")).toBeNull();
  expect(parseView("settings")).toEqual({ type: "core", view: "settings" });
  expect(fromHash("#settings/nonsense")).toBe("settings");
  expect(fromHash("#settings/addon/")).toBe("settings");
});
