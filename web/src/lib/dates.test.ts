import { expect, test } from "vitest";
import { nextMonday, sinceDay } from "./dates";

test("the coming Monday is never the day itself: a Monday holds for the Monday a week on", () => {
  // The 19th of October is a Monday in this year.
  expect(nextMonday(new Date(2026, 9, 19, 9))).toBe("2026-10-26");
  expect(nextMonday(new Date(2026, 9, 20))).toBe("2026-10-26");
  expect(nextMonday(new Date(2026, 9, 23, 23, 59))).toBe("2026-10-26");
  expect(nextMonday(new Date(2026, 9, 24))).toBe("2026-10-26");
  expect(nextMonday(new Date(2026, 9, 25))).toBe("2026-10-26");
  // across a month and a year
  expect(nextMonday(new Date(2026, 11, 30))).toBe("2027-01-04");
});

test("ready since is the weekday for the last six days, the month and day before that, and nothing for today", () => {
  const today = new Date(2026, 9, 22, 15); // a Thursday
  expect(sinceDay("2026-10-20", today)).toBe("Tue");
  expect(sinceDay("2026-10-21", today)).toBe("Wed");
  expect(sinceDay("2026-10-16", today)).toBe("Fri");
  expect(sinceDay("2026-10-15", today)).toBe("Oct 15");
  expect(sinceDay("2026-09-30", today)).toBe("Sep 30");
  expect(sinceDay("2026-10-22", today)).toBe("");
  expect(sinceDay("2026-10-25", today)).toBe("");
  expect(sinceDay(null, today)).toBe("");
});
