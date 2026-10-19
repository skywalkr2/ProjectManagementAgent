import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { PromiseWhy } from "./PromiseWhy";

// Every promise shows why, and each part of it is one click to correct from a list (design 6.33).

const people = [
  { id: "PER-1", name: "Ana Person" },
  { id: "PER-2", name: "Robin Sample" },
  { id: "PER-3", name: "Casey Moor" },
] as S["PersonView"][];

const view = (over: Partial<S["PromiseView"]> = {}): S["PromiseView"] => ({
  action: "ACT-1",
  version: 4,
  text: "Send the floor plan",
  status: "open",
  quote: "I will send the floor plan by Tuesday.",
  owners: [{ id: "PER-2", name: "Robin Sample (Print)" }],
  mine: false,
  promised_to: [{ id: "PER-1", name: "Ana Person" }],
  due: "2026-10-13",
  due_words: "by Tuesday",
  due_check: false,
  basis: "inferred",
  said_by: null,
  origin: { kind: "source", source: "SRC-1" },
  news: [],
  ...over,
});

function show(found: S["PromiseView"], extra: Routes = {}, props: { quiet?: boolean; omitQuote?: boolean } = {}) {
  const calls = fakeApi({
    "GET promises/ACT-1": () => found,
    "GET people": () => people,
    "POST promises/ACT-1/correct": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }),
    ...extra,
  });
  const rendered = renderApp(<PromiseWhy action="ACT-1" {...props} />);
  return { calls, ...rendered };
}

const row = (name: string) => document.querySelector(`[data-promise="${name}"]`) as HTMLElement;

test("it shows the exact words, who owes it to whom, the day with its words, where it came from and how it is known", async () => {
  show(view());
  expect(await screen.findByText("I will send the floor plan by Tuesday.")).toBeInTheDocument();
  expect(row("owner")).toHaveTextContent("Robin Sample (Print)");
  expect(row("to")).toHaveTextContent("Ana Person");
  expect(row("due")).toHaveTextContent(`${day("2026-10-13")} from “by Tuesday”`);
  expect(row("basis")).toHaveTextContent("Worked out");
  expect(screen.getByRole("button", { name: "Where it came from" })).toBeInTheDocument();
  // Never a score, and a certain date has no doubt flag.
  expect(screen.queryByText(/confidence|score|%/i)).toBeNull();
  expect(screen.queryByText("Check this date")).toBeNull();
});

test("a said promise says who said it; a doubtful date says to check it", async () => {
  show(view({ basis: "said", said_by: "Ana Person", due_check: true }));
  await screen.findByText("I will send the floor plan by Tuesday.");
  expect(row("basis")).toHaveTextContent("Said (said by Ana Person)");
  expect(row("due")).toHaveTextContent("Check this date");
});

test("who owes it is a list of people with the cursor in it, and picking one corrects it with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = show(view());
  await user.click(await screen.findByRole("button", { name: "Change: Who owes it" }));
  const list = screen.getByRole("combobox", { name: "Who owes it" });
  expect(list).toHaveFocus();
  expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["Ana Person", "Robin Sample", "Casey Moor"]);
  await user.selectOptions(list, "PER-3");
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-1/correct")?.body).toEqual({ read_version: 4, owner: "PER-3" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("promised to is a list that can say no one", async () => {
  const user = userEvent.setup();
  const { calls } = show(view());
  await user.click(await screen.findByRole("button", { name: "Change: Promised to" }));
  const list = screen.getByRole("combobox", { name: "Promised to" });
  expect(within(list).getAllByRole("option")[0]).toHaveTextContent("No one in particular");
  await user.selectOptions(list, "");
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-1/correct")?.body).toEqual({ read_version: 4, promised_to: [] }));
});

test("how it is known is the two values to pick from", async () => {
  const user = userEvent.setup();
  const { calls } = show(view());
  await user.click(await screen.findByRole("button", { name: "Change: How it is known" }));
  const list = screen.getByRole("combobox", { name: "How it is known" });
  expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["Said", "Worked out"]);
  await user.selectOptions(list, "said");
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-1/correct")?.body).toEqual({ read_version: 4, basis: "said" }));
});

test("the day is a date picker with the cursor in it, and saving sends the new day", async () => {
  const user = userEvent.setup();
  const { calls } = show(view());
  await user.click(await screen.findByRole("button", { name: "Change: Due" }));
  const picker = screen.getByLabelText("Due", { selector: "input" });
  expect(picker).toHaveAttribute("type", "date");
  expect(picker).toHaveFocus();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  fireEvent.change(picker, { target: { value: "2026-11-03" } });
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-1/correct")?.body).toEqual({ read_version: 4, due: "2026-11-03" }));
});

test("what was heard since is newest first, and a delivered part reads as done and credited to the owners", async () => {
  show(
    view({
      news: [
        { on: "2026-10-15", text: "Sent the draft", delivered: true, credited: ["Robin Sample (Print)"], quote: "the draft is attached" },
        { on: "2026-10-12", text: "Replied but gave no date", delivered: false, credited: [], quote: null },
      ],
    }),
  );
  const items = await screen.findAllByRole("listitem");
  expect(items[0]).toHaveTextContent(`${day("2026-10-15")}: delivered, Sent the draft. Credit goes to Robin Sample (Print).`);
  expect(items[0]).toHaveTextContent("“the draft is attached”");
  expect(items[1]).toHaveTextContent(`${day("2026-10-12")}: Replied but gave no date`);
});

test("a plain to-do has no why to show when quiet, and the words are left out when the place already shows them", async () => {
  const plain = view({ quote: null, basis: null, promised_to: [], due_words: null, origin: null });
  const { unmount } = show(plain, {}, { quiet: true });
  await waitFor(() => expect(document.querySelector("[data-promise-why]")).toBeNull());
  unmount();
  show(view(), {}, { quiet: true, omitQuote: true });
  await screen.findByRole("region", { name: "Why this is here" });
  expect(screen.queryByText("I will send the floor plan by Tuesday.")).toBeNull();
});
