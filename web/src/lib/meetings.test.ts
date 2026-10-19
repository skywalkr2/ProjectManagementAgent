import { forMeeting, meetingDay } from "./meetings";
import { monthDay } from "./dates";

const t = (key: string, vars: Record<string, string | number> = {}) =>
  ({ "series.for": `for ${vars.day}'s ${vars.title}`, "series.for_title": `for ${vars.title}` })[key] ?? key;

const NOW = new Date(2026, 9, 19); // Monday, October 19, 2026

test("within a week the weekday names the meeting, further out or already past the date does", () => {
  expect(meetingDay("2026-10-19", NOW)).toBe("Monday");
  expect(meetingDay("2026-10-22", NOW)).toBe("Thursday");
  expect(meetingDay("2026-10-25", NOW)).toBe("Sunday");
  expect(meetingDay("2026-10-26", NOW)).toBe(monthDay("2026-10-26"));
  expect(meetingDay("2026-10-18", NOW)).toBe(monthDay("2026-10-18"));
});

test("the title reads after the day: a title that only starts with a capital is lowered, one with more capitals is kept", () => {
  expect(forMeeting(t, "Print sync", "2026-10-22", NOW)).toBe("for Thursday's print sync");
  expect(forMeeting(t, "QA sync", "2026-10-22", NOW)).toBe("for Thursday's QA sync");
  expect(forMeeting(t, "Print sync", null, NOW)).toBe("for print sync");
});
