import { dateFormatChoices, dateFormatLabel } from "./date-formats";

// A fixed moment, so each format reads the same wherever the test runs: Tuesday, October 20, 2026, 9:05 in the evening.
const WHEN = new Date(2026, 9, 20, 21, 5);

test("a format is shown as the date written that way, never as its codes", () => {
  expect(dateFormatLabel("%a, %b %d", WHEN, "en-US")).toBe("Tue, Oct 20");
  expect(dateFormatLabel("%A, %B %d", WHEN, "en-US")).toBe("Tuesday, October 20");
  expect(dateFormatLabel("%Y-%m-%d", WHEN, "en-US")).toBe("2026-10-20");
  expect(dateFormatLabel("%m/%d/%Y", WHEN, "en-US")).toBe("10/20/2026");
  expect(dateFormatLabel("%a, %b %d, %Y, %H:%M", WHEN, "en-US")).toBe("Tue, Oct 20, 2026, 21:05");
  expect(dateFormatLabel("%b %d, %Y, %I:%M %p", WHEN, "en-US")).toBe("Oct 20, 2026, 09:05 PM");
});

test("a code the list doesn't know is left as it is, so a format set by hand still shows", () => {
  expect(dateFormatLabel("%d.%m.%y %Q", WHEN, "en-US")).toBe("20.10.26 %Q");
});

test("the choices keep the list's order and show each format once", () => {
  const out = dateFormatChoices(["%Y-%m-%d", "%a, %b %d", "%Y-%m-%d"], WHEN, "en-US");
  expect(out).toEqual([
    { tag: "%Y-%m-%d", label: "2026-10-20" },
    { tag: "%a, %b %d", label: "Tue, Oct 20" },
  ]);
});
