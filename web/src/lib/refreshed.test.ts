import { changedTime, changedUnderneath, reconcile, refreshedSettings } from "./refreshed";
import type { S } from "./api";

const item = (key: string, value: unknown): S["SettingItem"] =>
  ({ key, file: "demo", group: "demo", description: `What ${key} does`, type: "text", options: [], value, default: "", source: "file", locked: false, basic: true, editable: true }) as S["SettingItem"];
const t = (key: string, vars?: Record<string, string | number>) => (vars ? `${key}:${JSON.stringify(vars)}` : key);
const has = () => false;

test("a setting the person did not touch that changed underneath is listed with the value it has now", () => {
  const before = [item("a", "old"), item("b", "same"), item("c", "mine-before")];
  const after = [item("a", "new"), item("b", "same"), item("c", "theirs")];
  const lines = refreshedSettings(before, after, (key) => key === "c", t, has);
  expect(lines).toEqual([{ label: "What a does", value: "new" }]);
});

test("a setting the person changed is marked when its saved value moved, and not when it did not", () => {
  const before = [item("a", "x"), item("b", "y")];
  const after = [item("a", "x2"), item("b", "y")];
  expect(changedUnderneath(before, after, "a")).toBe(true);
  expect(changedUnderneath(before, after, "b")).toBe(false);
});

test("the form's own fields: untouched ones take the saved value and are listed, changed ones are kept", () => {
  const out = reconcile({ name: "A", models: "m1", other: "o" }, { name: "A typed", models: "m1", other: "o" }, { name: "A elsewhere", models: "m2", other: "o" });
  expect(out.next).toEqual({ name: "A typed", models: "m2", other: "o" });
  expect(out.refreshed).toEqual(["models"]);
  expect(out.kept).toEqual(["name"]);
});

test("the time the files changed reads in the reader's clock, and is empty when unknown", () => {
  expect(changedTime(undefined)).toBe("");
  expect(changedTime({ changed_at: null })).toBe("");
  expect(changedTime({ changed_at: "2026-10-20T09:14:00Z" })).toMatch(/\d/);
});
