import { fromHash, panelView, recordView, toHash } from "./views";

test("core views round trip, and home has no fragment", () => {
  expect(toHash("home")).toBe("");
  expect(toHash("files")).toBe("files");
  expect(fromHash("#files")).toBe("files");
  expect(toHash("welcome")).toBe("welcome");
  expect(fromHash("#welcome")).toBe("welcome");
  expect(fromHash("#settings")).toBe("settings");
  expect(fromHash("")).toBe("home");
  expect(fromHash("#nonsense")).toBe("home");
});

test("a panel and a record round trip with awkward characters in their names", () => {
  const panel = panelView("demo/goals");
  expect(fromHash(toHash(panel))).toBe(panel);
  const record = recordView("demo/chapter", "CH 1:2#3");
  expect(toHash(record)).not.toContain("#");
  expect(fromHash(`#${toHash(record)}`)).toBe(record);
});

test("a fragment that names nothing is home", () => {
  expect(fromHash("#panel:")).toBe("home");
  expect(fromHash("#record:demo%2Fchapter")).toBe("home");
  expect(fromHash("#record:%E0%A4%A:x")).toBe("home");
});
