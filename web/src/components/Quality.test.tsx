import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { Quality } from "./Quality";

// The Quality screen (design 6.32): a section for each measure with its number out of its denominator, the person's own
// daily count (the cursor in its first field, a date defaulting to today, Save with an Undo toast), and an empty state in
// plain words for each section.

type View = S["QualityView"];

const quality = (over: Partial<View> = {}): View => ({
  days: 28,
  min_corrections_per_week: 10,
  knowledge_used: [],
  repeat_corrections: [],
  missing: [],
  missed: [],
  since: "2026-09-21",
  until: "2026-10-19",
  closes: { total: 0, silent: 0, days: [] },
  endings: { made: 0, wrong: 0, declined: 0, undone: 0, reopened: 0, days: [] },
  counts: { person: "PER-1", present: 0, missed: 0, entered: 0, days: [] },
  replays: { count: 0, last_run: null },
  ...over,
});

const FULL = quality({
  closes: { total: 41, silent: 2, days: [{ day: "2026-10-18", total: 30, silent: 1 }, { day: "2026-10-19", total: 11, silent: 1 }] },
  endings: { made: 12, wrong: 3, declined: 1, undone: 1, reopened: 1, days: [{ day: "2026-10-19", made: 12, wrong: 3 }] },
  counts: { person: "PER-1", present: 30, missed: 4, entered: 2, days: [{ day: "2026-10-18", present: 20, missed: 3 }, { day: "2026-10-19", present: 10, missed: 1 }] },
  missed: [
    { person: "PER-1", person_name: "Casey Example", week: "2026-10-12", week_end: "2026-10-18", count: 3 },
    { person: "PER-1", person_name: "Casey Example", week: "2026-10-19", week_end: "2026-10-25", count: 1 },
  ],
  replays: { count: 2, last_run: null },
});

function show(view: View, routes: Routes = {}, onBack = () => undefined) {
  const calls = fakeApi({ "GET quality": () => view, ...routes });
  renderApp(<Quality onBack={onBack} />);
  return calls;
}

/** The screen once its figures have arrived. */
const loaded = () => screen.findByText(/^Counting from /);

const section = (id: string) => document.querySelector<HTMLElement>(`[data-quality-section="${id}"]`) as HTMLElement;

test("the screen has a section for each measure and shows the window's dates", async () => {
  show(FULL);
  expect(screen.getByRole("heading", { level: 1, name: "Quality" })).toBeInTheDocument();
  expect(await screen.findByText("Counting from Sep 21 to Oct 19.")).toBeInTheDocument();
  const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(titles).toEqual([
    "Closes you didn't see",
    "Wrong endings",
    "Promises the app missed",
    "Missed one",
    "Replays",
    "Using what it learned",
    "Corrections that repeated",
    "Things it couldn't do",
  ]);
});

test("each measure is a number out of its denominator in words, never a bare percentage", async () => {
  show(FULL);
  await loaded();
  expect(within(section("quality-closes")).getByText("2 of 41 closes weren't seen by you.")).toBeInTheDocument();
  expect(within(section("quality-closes")).getByText("Oct 18: 1 of 30 closes weren't seen by you.")).toBeInTheDocument();
  expect(within(section("quality-endings")).getByText("3 of 12 endings were wrong.")).toBeInTheDocument();
  expect(within(section("quality-endings")).getByText(/You kept 1 as they were, undid 1 and reopened 1 that a nudge had recorded as done\./)).toBeInTheDocument();
  expect(within(section("quality-counts")).getByText("The app missed 4 of the 30 promises you counted.")).toBeInTheDocument();
  expect(within(section("quality-counts")).getByText("Oct 19: missed 1 of 10 promises.")).toBeInTheDocument();
  expect(within(section("quality-missed")).getByText("Casey Example, Oct 12 to Oct 18: said 3 times.")).toBeInTheDocument();
  expect(within(section("quality-missed")).getByText("Casey Example, Oct 19 to Oct 25: said once.")).toBeInTheDocument();
  expect(within(section("quality-replays")).getByText("2 replays are kept.")).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/\d\s?%/);
});

test("the other measures read in the same plain style", async () => {
  show(
    quality({
      knowledge_used: [{ task: "notes", runs_given: 4, runs_applied: 3, dropped: 0, rate: 0.75 }],
      repeat_corrections: [
        { task: "notes", week: "2026-10-12", corrections: 12, repeats: 5, enough: true, rate: 0.4 },
        { task: "notes", week: "2026-10-19", corrections: 2, repeats: 2, enough: false, rate: null },
      ],
      missing: [{ week: "2026-10-12", groups: [{ wording: "an op to put an action on hold", count: 2, tasks: ["notes"], changesets: ["CS-1", "CS-2"], last_seen: null }] }],
    }),
  );
  await loaded();
  expect(within(section("quality-knowledge")).getByText("filing notes: used it in 3 of 4 pieces of work.")).toBeInTheDocument();
  expect(within(section("quality-repeats")).getByText("Week of Oct 12, filing notes: 5 of 12 corrections repeated a mistake it had been taught about.")).toBeInTheDocument();
  expect(within(section("quality-repeats")).getByText("Week of Oct 19, filing notes: 2 corrections, too few to say.")).toBeInTheDocument();
  expect(within(section("quality-lacking")).getByText("an op to put an action on hold: said 2 times.")).toBeInTheDocument();
});

test("a screen with nothing to show says so in plain words in every section", async () => {
  show(quality());
  await loaded();
  expect(within(section("quality-closes")).getByText("Nothing was closed in this window.")).toBeInTheDocument();
  expect(within(section("quality-endings")).getByText("The assistant hasn't ended anything in this window.")).toBeInTheDocument();
  expect(within(section("quality-counts")).getByText("You haven't entered a count in this window.")).toBeInTheDocument();
  expect(within(section("quality-missed")).getByText("No one has said the assistant missed something in this window.")).toBeInTheDocument();
  expect(within(section("quality-replays")).getByText("No misses have been kept as replays yet.")).toBeInTheDocument();
  expect(within(section("quality-knowledge")).getByText(/No work was given what you'd taught the assistant/)).toBeInTheDocument();
  expect(within(section("quality-repeats")).getByText("You haven't corrected the assistant in this window.")).toBeInTheDocument();
  expect(within(section("quality-lacking")).getByText("The assistant hasn't said it lacked anything in this window.")).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/NaN|undefined|null/);
});

test("the cursor starts in the form's first field, the date, which holds today and shows that day's count", async () => {
  show(FULL);
  const date = await screen.findByLabelText("Day");
  await waitFor(() => expect(date).toHaveFocus());
  expect(date).toHaveValue("2026-10-19");
  expect(date).toHaveAttribute("max", "2026-10-19");
  expect(screen.getByLabelText("Promises on your own list")).toHaveValue(10);
});

test("Save is off until both numbers are entered, and says why", async () => {
  const user = userEvent.setup();
  show(quality());
  const save = await screen.findByRole("button", { name: "Save" });
  expect(save).toBeDisabled();
  expect(screen.getByText("Enter both numbers to save.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Promises on your own list"), "9");
  expect(save).toBeDisabled();
  await user.type(screen.getByLabelText("Of those, how many the app didn't have"), "2");
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  expect(screen.queryByText("Enter both numbers to save.")).toBeNull();
});

test("more missed than counted is said at once and can't be saved", async () => {
  const user = userEvent.setup();
  show(quality());
  await user.type(await screen.findByLabelText("Promises on your own list"), "2");
  await user.type(screen.getByLabelText("Of those, how many the app didn't have"), "5");
  expect(screen.getByRole("alert")).toHaveTextContent("The app can't have missed more than you counted.");
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

test("saving posts the day's two numbers and an Undo toast takes the save back", async () => {
  const user = userEvent.setup();
  const calls = show(quality(), {
    "PUT quality/counts/2026-10-19": () => ({ id: "PCNT-1", day: "2026-10-19", present: 9, missed: 2, previous: null }),
    "POST quality/counts/2026-10-19/undo": () => ({ ok: "2026-10-19" }),
  });
  await user.type(await screen.findByLabelText("Promises on your own list"), "9");
  await user.type(screen.getByLabelText("Of those, how many the app didn't have"), "2");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Saved Oct 19: missed 2 of 9.")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "PUT quality/counts/2026-10-19")?.body).toEqual({ present: 9, missed: 2 });
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST quality/counts/2026-10-19/undo")?.body).toEqual({ previous: null }));
});

test("a day that already has a count shows it, saving again corrects it, and Undo puts the earlier numbers back", async () => {
  const user = userEvent.setup();
  const calls = show(FULL, {
    "PUT quality/counts/2026-10-19": () => ({ id: "PCNT-1", day: "2026-10-19", present: 11, missed: 0, previous: { present: 10, missed: 1 } }),
    "POST quality/counts/2026-10-19/undo": () => ({ ok: "2026-10-19" }),
  });
  const present = await screen.findByLabelText("Promises on your own list");
  await waitFor(() => expect(present).toHaveValue(10));
  expect(screen.getByLabelText("Of those, how many the app didn't have")).toHaveValue(1);
  await user.clear(present);
  await user.type(present, "11");
  await user.clear(screen.getByLabelText("Of those, how many the app didn't have"));
  await user.type(screen.getByLabelText("Of those, how many the app didn't have"), "0");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Corrected Oct 19: missed 0 of 11.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST quality/counts/2026-10-19/undo")?.body).toEqual({ previous: { present: 10, missed: 1 } }));
});

test("a refused save says why in a toast and keeps what was typed", async () => {
  const user = userEvent.setup();
  show(quality(), { "PUT quality/counts/2026-10-19": () => new Refuse(409, "That day hasn't happened yet.") });
  await user.type(await screen.findByLabelText("Promises on your own list"), "4");
  await user.type(screen.getByLabelText("Of those, how many the app didn't have"), "1");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText(/That day hasn't happened yet\./)).toBeInTheDocument();
  expect(screen.getByLabelText("Promises on your own list")).toHaveValue(4);
});

test("a load that fails says so with Try again, and Back goes back", async () => {
  const user = userEvent.setup();
  const back = vi.fn();
  show(quality(), { "GET quality": () => new Refuse(500, "broken") }, back);
  expect(await screen.findByText("This page didn't load.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Back to Settings" }));
  expect(back).toHaveBeenCalledTimes(1);
});
