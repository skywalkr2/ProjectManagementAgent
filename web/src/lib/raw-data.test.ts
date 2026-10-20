import { holdsRawData } from "./raw-data";

test.each([
  '{"title": "Launch", "due": "2026-10-20"}',
  "Milestone {'name': 'Launch'} is due",
  "Milestone: {name: Launch, due: 2026-10-20}",
  'The fields are "title": and "due": in the data',
  'Review [{"id": 4}] before Friday',
])("data is caught: %s", (text) => {
  expect(holdsRawData(text)).toBe(true);
});

test.each([
  "Write the plan for {full_name} first.",
  "The folder is plan/chapters/{order:02}-{slug}.",
  'Ask "Is the index final?" before Friday',
  "Notes: the printer wants PDF files.",
  "Review the list [Launch, Ship] with Robin",
  "Read the section titled 'Costs': it is short.",
])("an ordinary line is not: %s", (text) => {
  expect(holdsRawData(text)).toBe(false);
});
