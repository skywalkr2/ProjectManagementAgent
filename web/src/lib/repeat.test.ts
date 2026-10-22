import sheet from "../wording/en.json";
import { format } from "./wording";
import { saidRepeat, saidShape, type Shape } from "./repeat";

const t = (key: string, vars: Record<string, string | number> = {}) => format(sheet, key, vars);
const shape = (over: Partial<Shape> & Pick<Shape, "kind">): Shape => ({ weekdays: [], days: [], ordinals: [], ...over });

test("a repeat is said back from the wording sheet, with its start", () => {
  const said = saidRepeat(t, shape({ kind: "weekly_days", interval: 1, weekdays: ["monday", "thursday"] }), "2026-11-02");
  expect(said).toBe("Every Monday and Thursday, starting November 2");
});

test.each([
  [shape({ kind: "daily", interval: 1 }), "Every day"],
  [shape({ kind: "daily", interval: 3 }), "Every 3 days"],
  [shape({ kind: "weekdays" }), "Every weekday"],
  [shape({ kind: "weekly", interval: 2, weekday: "tuesday" }), "Every other Tuesday"],
  [shape({ kind: "weekly", interval: 3, weekday: "tuesday" }), "Every 3 weeks on Tuesday"],
  [shape({ kind: "weekly_days", interval: 1, weekdays: ["monday", "wednesday", "friday"] }), "Every Monday, Wednesday, and Friday"],
  [shape({ kind: "monthly_days", interval: 1, days: [1, 15] }), "On the 1st and 15th of each month"],
  [shape({ kind: "monthly_day", interval: 2, day: 10 }), "On the 10th of every other month"],
  [shape({ kind: "monthly_day", interval: 1, day: 22 }), "On the 22nd of each month"],
  [shape({ kind: "monthly_day", interval: 1, day: 31 }), "On the 31st of each month, or the last day of a shorter month"],
  [shape({ kind: "monthly_last_day", interval: 1 }), "On the last day of each month"],
  [shape({ kind: "monthly_nths", ordinals: ["second", "fourth"], weekday: "tuesday" }), "On the second and fourth Tuesday of each month"],
  [shape({ kind: "monthly_weekday", position: "last" }), "On the last weekday of each month"],
  [shape({ kind: "yearly", month: "february", day: 29 }), "Every year on February 29, or the last day of a shorter month"],
  [shape({ kind: "yearly_nth", month: "november", ordinal: "last", weekday: "friday" }), "Every year on the last Friday in November"],
])("a shape is said in plain words: %#", (given, words) => {
  expect(saidShape(t, given)).toBe(words);
});
