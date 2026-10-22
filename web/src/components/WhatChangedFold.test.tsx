import { vi } from "vitest";
// What changed opens the first item only, the rest one line each, and a to-do's owner, promise and day are edited in its
// meta line, each part a button that opens a small popover (design 7.3; finding 3.6).
import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { besidePane, fakeApi, renderApp } from "../test-utils";
import { WhatChanged } from "./WhatChanged";

// The window is wide, so a change's detail stands beside the list (design 7.13).
beforeEach(() => besidePane());
afterEach(() => vi.unstubAllGlobals());

function change(id: string, title: string, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: "SRC-1",
    source_title: title,
    changeset: {
      id: `CS-${id}`,
      summary: `Summary of ${title}.`,
      status: "applied",
      reviewed: false,
      trust: "untrusted",
      ops: [
        {
          index: 0,
          op: "action.add",
          status: "applied",
          reason: null,
          group: "op0",
          title: `Send ${title}`,
          meta: { owners: ["Robin Sample"] },
          evidence: { quote: "I will send it" },
          record: { kind: "action", id: `ACT-${id}` },
          ask: null,
        },
      ],
    },
    ...extra,
  };
}

const people = [
  { id: "PER-1", name: "Ana Person" },
  { id: "PER-2", name: "Robin Sample" },
  { id: "PER-3", name: "Casey Moor" },
] as S["PersonView"][];

const promise = (id: string, over: Partial<S["PromiseView"]> = {}): S["PromiseView"] => ({
  action: id,
  version: 4,
  text: "Send it",
  status: "open",
  quote: "I will send it.",
  owners: [{ id: "PER-2", name: "Robin Sample" }],
  mine: false,
  promised_to: [],
  due: "2026-10-16",
  due_words: null,
  due_check: false,
  basis: null,
  said_by: null,
  origin: { kind: "source", source: "SRC-1" },
  news: [],
  ...over,
});

function show(items: S["ChangeItem"][], extra: Record<string, (b: unknown) => unknown> = {}) {
  return fakeApi({
    "GET changes": () => items,
    "GET people": () => people,
    "GET stages/requests": () => [],
    "GET stages/records": () => [],
    "GET promises/ACT-A": () => promise("ACT-A"),
    "GET promises/ACT-B": () => promise("ACT-B"),
    "GET promises/ACT-C": () => promise("ACT-C"),
    ...extra,
  });
}

const rowButton = (title: string) => screen.getByRole("button", { name: new RegExp(`^${title}`) });

test("only the first item is chosen, so its details are shown; the others are one line each, with nothing of their details", async () => {
  show([change("A", "First thing"), change("B", "Second thing"), change("C", "Third thing")]);
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Summary of First thing.")).toBeInTheDocument();
  expect(rowButton("First thing")).toHaveAttribute("aria-expanded", "true");
  expect(rowButton("Second thing")).toHaveAttribute("aria-expanded", "false");
  expect(rowButton("Third thing")).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Summary of Second thing.")).toBeNull();
  expect(screen.queryByText("Summary of Third thing.")).toBeNull();
  // The rows still say what is to be looked at: each line keeps its primary action (and the detail has its own).
  expect(screen.getAllByRole("button", { name: "Looks good" })).toHaveLength(4);
  expect(within(screen.getByRole("complementary")).getAllByRole("button", { name: "Looks good" })).toHaveLength(1);
});

test("another item is chosen by its line, and its details replace the first's", async () => {
  const user = userEvent.setup();
  show([change("A", "First thing"), change("B", "Second thing")]);
  renderApp(<WhatChanged />);
  await screen.findByText("Summary of First thing.");
  await user.click(rowButton("Second thing"));
  expect(await screen.findByText("Summary of Second thing.")).toBeInTheDocument();
  expect(screen.queryByText("Summary of First thing.")).toBeNull();
  expect(rowButton("Second thing")).toHaveAttribute("aria-expanded", "true");
  expect(rowButton("First thing")).toHaveAttribute("aria-expanded", "false");
});

test("a row that holds a question for the person is the one chosen first, whichever place it has", async () => {
  const asking = change("B", "Second thing", { state: "done" });
  asking.changeset!.ops[0] = {
    ...asking.changeset!.ops[0],
    status: "held",
    reason: "Waiting for you to say who this is",
    ask: { id: "Q-B", status: "open", about: "held-op", name: "Robin", options: [{ id: "PER-2", name: "Robin Sample" }] },
  };
  show([change("A", "First thing"), asking]);
  renderApp(<WhatChanged />);
  expect(await screen.findByRole("combobox", { name: "Who is “Robin”?" })).toBeInTheDocument();
  expect(rowButton("Second thing")).toHaveAttribute("aria-expanded", "true");
});

test("a to-do's owner, promise and day are one meta line, each part a button, with no stacked Change links", async () => {
  show([change("A", "First thing")]);
  renderApp(<WhatChanged />);
  const line = (await screen.findByRole("button", { name: /^Robin Sample/ })).closest("[data-promise-line]") as HTMLElement;
  expect(line).toHaveTextContent(`Robin Sample · due ${day("2026-10-16")} · promised to no one`);
  expect(within(line).getAllByRole("button").map((b) => b.textContent)).toEqual(["Robin Sample", `due ${day("2026-10-16")}`, "promised to no one"]);
  // Nothing is labeled Change, and the field names are not stacked as a list.
  expect(screen.queryByRole("button", { name: /^Change/ })).toBeNull();
  expect(screen.queryByText("Change")).toBeNull();
  expect(screen.queryByText("Who owes it", { selector: "dt" })).toBeNull();
  expect(document.querySelector("[data-promise-why] dl")).toBeNull();
});

test("a part opens a small popover to change it from a list, and picking applies it with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([change("A", "First thing")], {
    "POST promises/ACT-A/correct": () => ({ changeset: "CS-9" }),
    "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "Robin Sample · Change: Who owes it" }));
  const popover = await screen.findByRole("dialog", { name: "Who owes it" });
  const list = within(popover).getByRole("combobox", { name: "Who owes it" });
  await waitFor(() => expect(list).toHaveFocus());
  await user.selectOptions(list, "PER-3");
  await waitFor(() => expect(calls.find((c) => c.route === "POST promises/ACT-A/correct")?.body).toMatchObject({ owner: "PER-3", read_version: 4 }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Who owes it" })).toBeNull());
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
});

test("the day part opens a date picker, and Escape closes the popover without a change", async () => {
  const user = userEvent.setup();
  const calls = show([change("A", "First thing")], { "POST promises/ACT-A/correct": () => ({ changeset: "CS-9" }) });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: `due ${day("2026-10-16")} · Change: Due` }));
  const popover = await screen.findByRole("dialog", { name: "Due" });
  await waitFor(() => expect(within(popover).getByLabelText("Due")).toHaveFocus());
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Due" })).toBeNull());
  expect(calls.some((c) => c.route === "POST promises/ACT-A/correct")).toBe(false);
  // The part that opened it has the cursor back.
  await waitFor(() => expect(screen.getByRole("button", { name: `due ${day("2026-10-16")} · Change: Due` })).toHaveFocus());
});

test("the meta line names who it was promised to, and how it is known when that is on file", async () => {
  show([change("A", "First thing")], {
    "GET promises/ACT-A": () => promise("ACT-A", { promised_to: [{ id: "PER-1", name: "Ana Person" }], basis: "said", said_by: "Ana Person", due: null }),
  });
  renderApp(<WhatChanged />);
  const line = (await screen.findByRole("button", { name: /^promised to Ana Person/ })).closest("[data-promise-line]") as HTMLElement;
  expect(line).toHaveTextContent("Robin Sample · no date · promised to Ana Person · said by Ana Person");
});
