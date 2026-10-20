import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day, monthDay } from "../lib/dates";
import { fakeApi, renderApp } from "../test-utils";
import { SeriesPage } from "./SeriesPage";

// A series' page (design 7.14, designer answer 30): the next meeting's open items by person with the person last, the
// meetings that passed one line each, and the details beside.

const meeting = (id: string, on: string, title = "Print sync"): S["SeriesMeeting"] => ({ id, title, start: on, on });
const item = (id: string, text: string, over: Partial<S["SeriesItem"]> = {}): S["SeriesItem"] => ({ kind: "action", id, text, status: "open", ...over });

const view = (over: Partial<S["SeriesPageView"]> = {}): S["SeriesPageView"] => ({
  id: "SER-1",
  title: "Print sync",
  repeats: "every Thursday",
  project: "PRJ-1",
  project_name: "Harbor",
  next: {
    ...meeting("EVT-3", "2026-10-22"),
    open: 3,
    groups: [
      { person: "PER-2", name: "Casey Moor", is_pm: false, items: [item("ACT-1", "Send the interior file", { due: "2026-10-20", rolled_from: meeting("EVT-2", "2026-10-15") })] },
      { person: "PER-1", name: "Pat Example", is_pm: true, items: [item("ACT-2", "Check the cover proof"), item("Q-1", "Which trim size?", { kind: "question" })] },
    ],
  },
  past: [
    {
      ...meeting("EVT-2", "2026-10-15"),
      settled: [{ kind: "action", id: "ACT-9", text: "Book the printer", status: "done" }, { kind: "action", id: "ACT-8", text: "Confirm the dates", status: "done" }, { kind: "action", id: "ACT-7", text: "Send the brief", status: "done" }],
      moved: [{ kind: "action", id: "ACT-1", text: "Send the interior file", status: "open", to: meeting("EVT-3", "2026-10-22") }],
    },
  ],
  open_without_next: 0,
  usually_with: [],
  ...over,
});

function show(shown: S["SeriesPageView"]) {
  fakeApi({ "GET series/SER-1/page": () => shown });
  return renderApp(<SeriesPage id="SER-1" onBack={() => {}} />);
}

test("the header names the series and the details say how often it repeats in the person's words, the project and the rolling rule", async () => {
  show(view());
  expect(await screen.findByRole("heading", { level: 1, name: "Print sync" })).toBeInTheDocument();
  const details = screen.getByRole("complementary", { name: "Details" });
  expect(details).toHaveTextContent("every Thursday");
  expect(details).toHaveTextContent("in your words");
  expect(within(details).getByRole("link", { name: "Harbor" }).getAttribute("href")).toMatch(/#records\/project\/PRJ-1$/);
  expect(details).toHaveTextContent("Open items roll to the next meeting when one passes unsettled.");
});

test("the next meeting is its day and how many are open, with the open items by person and the person last as You", async () => {
  show(view());
  const next = (await screen.findByRole("heading", { name: `Next: ${day("2026-10-22")} · 3 open` })).closest("section")!;
  const groups = within(next).getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
  expect(groups).toEqual(["Casey Moor", "You"]);
  expect(within(next).getByRole("link", { name: "Send the interior file" })).toBeInTheDocument();
  expect(within(next).getByRole("link", { name: "Which trim size?" }).getAttribute("href")).toMatch(/#records\/question\/Q-1$/);
});

test("an item that rolled from an earlier meeting says where it came from", async () => {
  show(view());
  const next = (await screen.findByRole("heading", { name: `Next: ${day("2026-10-22")} · 3 open` })).closest("section")!;
  const row = within(next).getByRole("link", { name: "Send the interior file" }).closest("li")!;
  expect(row).toHaveTextContent(`moved from ${monthDay("2026-10-15")}'s Print sync`);
  expect(within(next).getByRole("link", { name: "Check the cover proof" }).closest("li")).not.toHaveTextContent("moved from");
});

test("past meetings are collapsed to one line each: what was settled and what moved on, and open to show them", async () => {
  const user = userEvent.setup();
  show(view());
  const summary = await screen.findByText(`${day("2026-10-15")} · 3 settled · 1 moved to ${monthDay("2026-10-22")}`);
  const details = summary.closest("details")!;
  expect(details).not.toHaveAttribute("open");
  await user.click(summary);
  expect(details).toHaveAttribute("open");
  expect(within(details).getByText("Book the printer")).toBeInTheDocument();
  expect(within(details).getAllByText(`moved to ${monthDay("2026-10-22")}`)).toHaveLength(1);
});

test("with nothing open the next meeting says so, with no zero and no empty person", async () => {
  show(view({ next: { ...meeting("EVT-3", "2026-10-22"), open: 0, groups: [] }, past: [] }));
  expect(await screen.findByRole("heading", { name: `Next: ${day("2026-10-22")}` })).toBeInTheDocument();
  expect(screen.getByText("Nothing is open for it.")).toBeInTheDocument();
  expect(screen.queryByText(/0 open/)).toBeNull();
  expect(screen.queryByRole("heading", { name: "Past meetings" })).toBeNull();
});

test("with no later meeting it says how many open items wait for the next one", async () => {
  show(view({ next: null, open_without_next: 2, past: [] }));
  expect(await screen.findByRole("heading", { name: "No later meeting is scheduled" })).toBeInTheDocument();
  expect(screen.getByText("2 open items wait for the next meeting.")).toBeInTheDocument();
});

test("the details name who the series is usually with, one row each with how many meetings, and say nothing when it isn't known", async () => {
  const { unmount } = show(
    view({
      usually_with: [
        { person: "PER-2", name: "Casey Moor", meetings: 6, of: 6 },
        { person: "PER-3", name: "Dara Keene", meetings: 4, of: 6 },
      ],
    }),
  );
  const details = await screen.findByRole("complementary", { name: "Details" });
  expect(within(details).getByText("Usually with")).toBeInTheDocument();
  const rows = within(within(details).getByRole("list", { name: "Usually with" })).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(within(rows[0]).getByRole("link", { name: "Casey Moor" }).getAttribute("href")).toMatch(/#records\/person\/PER-2$/);
  expect(rows[0]).toHaveTextContent("Casey Moor · 6 of 6 meetings");
  expect(rows[1]).toHaveTextContent("Dara Keene · 4 of 6 meetings");
  unmount();
  show(view());
  expect(within(await screen.findByRole("complementary", { name: "Details" })).queryByText("Usually with")).toBeNull();
});

test("an item listed under Agenda is not listed again under Next, and Next counts what it lists", async () => {
  show(view({ agenda: [{ kind: "question", id: "Q-1", text: "Which trim size?", added_by_name: "Casey Moor", added_at: "2026-10-19T10:00:00Z" }] }));
  const next = (await screen.findByRole("heading", { name: `Next: ${day("2026-10-22")} · 2 open` })).closest("section")!;
  expect(within(next).queryByRole("link", { name: "Which trim size?" })).toBeNull();
  expect(within(next).getByRole("link", { name: "Check the cover proof" })).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Which trim size?" })).toHaveLength(1);
});

test("a person whose only items are on the agenda has no empty group under Next", async () => {
  show(view({ agenda: [{ kind: "action", id: "ACT-1", text: "Send the interior file", added_by_name: null, added_at: "2026-10-19T10:00:00Z" }] }));
  const next = (await screen.findByRole("heading", { name: `Next: ${day("2026-10-22")} · 2 open` })).closest("section")!;
  expect(within(next).getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["You"]);
});
