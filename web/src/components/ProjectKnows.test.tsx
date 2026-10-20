import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day, monthDay } from "../lib/dates";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { ProjectKnows } from "./ProjectKnows";

// What the assistant knows about a project (design 7.18), on its page: where its inputs come from and the last of each,
// its facts with who they rest on and when (answer 29), the terms used there, who answers what, and what is still unknown
// with the question asked for it. One row per thing; every section says so in plain words when it is empty.

type View = S["ProjectKnowsView"];

const knows = (over: Partial<View> = {}): View => ({
  id: "PRJ-1",
  name: "Harbor",
  sources: [],
  facts: [],
  terms: [],
  routing: [],
  unknown: [],
  ...over,
});

const FULL = knows({
  sources: [
    { key: "kind:pasted", label: null, kind: "pasted", inputs: 3, last: { id: "SRC-3", title: "Thursday notes", received_at: "2026-10-12T09:00:00Z" } },
    { key: "watch:folder", label: "Production folder", kind: null, inputs: 1, last: { id: "SRC-4", title: "Press schedule", received_at: "2026-10-09T09:00:00Z" } },
  ],
  facts: [
    { id: "FACT-1", version: 2, text: "Trim size is fixed.", key: true, source: { basis: "person", on: "2026-10-08", origin: { kind: "source", source: "SRC-1" } } },
    { id: "FACT-2", version: 4, text: "Both spines are in the folder.", key: false, source: { basis: "inferred", input: "Robin's email", on: "2026-10-12", origin: { kind: "source", source: "SRC-2" } } },
    { id: "FACT-3", version: 1, text: "The proof is approved.", key: false, source: { basis: null, on: null, origin: null } },
  ],
  terms: [
    { id: "GLOSS-1", term: "Bleed", meaning: "the part of the art that is trimmed off", confidence: "confirmed" },
    { id: "GLOSS-2", term: "Gutter", meaning: "the inner margin", confidence: "assumed" },
    { id: "GLOSS-3", term: "Folio", meaning: "not known yet", confidence: "unknown" },
  ],
  routing: [
    { id: "ROUTE-1", topic: "Printing", who: "Robin Sample", negative: false, look_up: null },
    { id: "ROUTE-2", topic: "Legal", who: "Dara Keene", negative: true, look_up: "the style sheet" },
  ],
  unknown: [
    { kind: "field", field: "status", term: null, entry: null, question: null },
    { kind: "field", field: "owner", term: null, entry: null, question: null },
    { kind: "term", field: null, term: "Folio", entry: "GLOSS-3", question: { id: "Q-1", title: "What does folio mean here?", to: "PER-1", to_name: "Robin Sample", status: "open" } },
    { kind: "term", field: null, term: "Recto", entry: "GLOSS-4", question: null },
  ],
});

function show(view: View, routes: Routes = {}) {
  const calls = fakeApi({ "GET projects/PRJ-1/knows": () => view, ...routes });
  renderApp(<ProjectKnows id="PRJ-1" />);
  return calls;
}

const section = (name: string) => screen.findByRole("region", { name });

test("a section for each part, headed by what the assistant knows, each row one thing", async () => {
  show(FULL);
  expect(await screen.findByRole("heading", { level: 2, name: "What Helper knows" })).toBeInTheDocument();
  await section("Sources");
  const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
  expect(titles).toEqual(["Sources", "Facts", "Terms used here", "Who answers what", "Still unknown"]);
});

test("each source says how many inputs it gave and the last one, which opens", async () => {
  show(FULL);
  const sources = await section("Sources");
  const rows = within(sources).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Pasted notes");
  expect(rows[0]).toHaveTextContent(`3 inputs · last ${monthDay("2026-10-12")}`);
  expect(within(rows[0]).getByRole("button", { name: "Thursday notes" })).toBeInTheDocument();
  expect(rows[1]).toHaveTextContent("Production folder");
  expect(rows[1]).toHaveTextContent(`1 input · last ${monthDay("2026-10-09")}`);
});

test("a fact has its source label in the meta line, key facts are marked, and what was worked out is Inferred with Confirm it", async () => {
  const user = userEvent.setup();
  const calls = show(FULL, {
    "POST records/edit": () => ({ changeset: "CS-5" }),
    "POST changesets/CS-5/undo": () => ({ restored: [0], skipped: [] }),
  });
  const facts = await section("Facts");
  const rows = within(facts).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getByText("Key")).toBeInTheDocument();
  expect(within(rows[0]).getByRole("button", { name: `from you, ${day("2026-10-08")}` })).toBeInTheDocument();
  expect(within(rows[0]).queryByText("Inferred")).toBeNull();
  const inferred = rows[1].querySelector("[data-fact-source]") as HTMLElement;
  expect(inferred.querySelector("[data-inferred]")).not.toBeNull();
  expect(inferred).toHaveTextContent(`Helper inferred this from Robin's email, ${day("2026-10-12")}`);
  expect(within(inferred).getByText("Inferred by the assistant, not stated")).toBeInTheDocument();
  expect(getComputedStyle(inferred).fontStyle).not.toBe("italic");
  // a fact with no source and no day says it was recorded, with nothing made up
  expect(rows[2]).toHaveTextContent("recorded");
  await user.click(within(inferred).getByRole("button", { name: "Confirm it" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "fact", id: "FACT-2", fields: { basis: "person" }, read_version: 4 }),
  );
  expect(await screen.findByText("Confirmed. It is now from you.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-5/undo")).toBe(true));
});

test("the source label is kept out of what is copied: it is its own marked element and the fact's text stands alone", async () => {
  show(FULL);
  const facts = await section("Facts");
  for (const row of within(facts).getAllByRole("listitem")) {
    const label = row.querySelector("[data-fact-source]") as HTMLElement;
    expect(label.closest("[data-copy='never']")).not.toBeNull();
    const copyable = row.cloneNode(true) as HTMLElement;
    copyable.querySelectorAll("[data-copy='never']").forEach((el) => el.remove());
    expect(copyable.textContent?.replace(/\s+/g, " ").trim()).toMatch(/^(Key)?(Trim size is fixed\.|Both spines are in the folder\.|The proof is approved\.)$/);
  }
});

test("each term is marked confirmed, assumed or not known yet, and a term not known has no made-up meaning", async () => {
  show(FULL);
  const terms = await section("Terms used here");
  const rows = within(terms).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Bleed");
  expect(rows[0]).toHaveTextContent("the part of the art that is trimmed off");
  expect(within(rows[0]).getByText("Confirmed")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Assumed")).toBeInTheDocument();
  expect(within(rows[2]).getByText("Not known yet")).toBeInTheDocument();
  expect(rows[2].textContent).not.toContain("not known yet");
});

test("who answers what names the person or team, or says who doesn't and where to look instead", async () => {
  show(FULL);
  const routing = await section("Who answers what");
  const rows = within(routing).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Printing");
  expect(rows[0]).toHaveTextContent("Robin Sample answers");
  expect(rows[1]).toHaveTextContent("Legal");
  expect(rows[1]).toHaveTextContent("Dara Keene doesn't answer this · Look it up: the style sheet");
});

test("what is still unknown says each blank field and each term, with the question asked or that nobody has been", async () => {
  show(FULL);
  const unknown = await section("Still unknown");
  const rows = within(unknown).getAllByRole("listitem");
  expect(rows).toHaveLength(4);
  expect(rows[0]).toHaveTextContent("Its status isn't known");
  expect(rows[1]).toHaveTextContent("Nobody is named as its owner");
  expect(rows[2]).toHaveTextContent("What “Folio” means isn't known");
  expect(within(rows[2]).getByRole("link", { name: "What does folio mean here?" })).toHaveAttribute("href", expect.stringContaining("question"));
  expect(rows[2]).toHaveTextContent("Asked of Robin Sample");
  expect(rows[3]).toHaveTextContent("What “Recto” means isn't known");
  expect(rows[3]).toHaveTextContent("Nobody has been asked.");
});

test("a project nothing is known about says so in plain words in every section", async () => {
  show(knows());
  expect(await within(await section("Sources")).findByText("Nothing has come in about this project yet.")).toBeInTheDocument();
  expect(within(await section("Facts")).getByText("No facts are recorded for this project yet.")).toBeInTheDocument();
  expect(within(await section("Terms used here")).getByText("No terms are used here yet.")).toBeInTheDocument();
  expect(within(await section("Who answers what")).getByText("No one is named for any kind of question here yet.")).toBeInTheDocument();
  expect(within(await section("Still unknown")).getByText("Nothing is unknown right now.")).toBeInTheDocument();
});

test("a load that fails says so with Try again", async () => {
  const user = userEvent.setup();
  let fail = true;
  fakeApi({ "GET projects/PRJ-1/knows": () => (fail ? new Refuse(500, "no") : FULL) });
  renderApp(<ProjectKnows id="PRJ-1" />);
  expect(await screen.findByText("What Helper knows about this project couldn't be loaded.")).toBeInTheDocument();
  fail = false;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await section("Sources")).toBeInTheDocument();
});
