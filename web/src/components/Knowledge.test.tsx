import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { Knowledge } from "./Knowledge";

const DAY = 86_400_000;
const ago = (days: number) => new Date(Date.now() - days * DAY - 60_000).toISOString();

const WORKSPACE: S["Scope"] = { scope: "workspace", task_kinds: [], records: [], filter: {}, projects: [], people: [], except: [] };

function entry(id: string, text: string, over: Partial<S["KnowledgeView"]> = {}): S["KnowledgeView"] {
  return {
    id,
    kind: "lesson",
    version: 4,
    text,
    status: "active",
    learned_from: "person",
    trust: "trusted",
    learned_at: ago(10),
    applies_to: WORKSPACE,
    id_patterns: [],
    used: 0,
    given: 0,
    ...over,
  };
}

function rule(id: string, text: string, over: Partial<S["RuleView"]> = {}): S["RuleView"] {
  return {
    id,
    version: 2,
    name: `name-${id}`,
    text,
    status: "active",
    learned_from: "seed",
    trust: "trusted",
    learned_at: ago(20),
    applies_to: WORKSPACE,
    constrains: [],
    enforced: false,
    used: 0,
    given: 0,
    ...over,
  };
}

const PROJECTS = [
  { id: "P-1", name: "First project" },
  { id: "P-2", name: "Second project" },
] as S["ProjectView"][];
const PEOPLE = [{ id: "PER-1", name: "Sample Person" }] as S["PersonView"][];

const ENTRIES: S["KnowledgeView"][] = [
  entry("LES-1", "Release dates come from the schedule.", { used: 12, given: 15, last_used: ago(2) }),
  entry("LES-2", "Catering work goes to the venue lead.", { status: "proposed", learned_from: "input", trust: "untrusted", learned_at: ago(1) }),
  entry("GLOSS-1", "A launch review is the meeting before release.", {
    kind: "glossary_entry",
    applies_to: { ...WORKSPACE, except: ["P-2"] },
    learned_at: ago(5),
  }),
  entry("LES-3", "An old habit.", { status: "retired", learned_at: ago(40) }),
  entry("LES-4", "Questions about budgets go to finance.", {
    kind: "routing_entry",
    status: "proposed",
    learned_at: ago(0.5),
    applies_to: { ...WORKSPACE, scope: "projects", projects: ["P-1"] },
  }),
];
const RULES: S["RuleView"][] = [
  rule("RULE-1", "Every question names its reader.", { used: 3, given: 3, last_used: ago(0) }),
  rule("RULE-2", "Never close an action without an owner.", { status: "retired" }),
];

const REVIEW: S["RuleReviewView"] = { days: 30, flagged: [], stable_chars: 100, stable_budget: 6000, moved: 0, due: false };

function open(extra: Routes = {}, review: S["RuleReviewView"] = REVIEW, onOpenReview = vi.fn()) {
  const calls = fakeApi({
    "GET knowledge": () => ENTRIES,
    "GET knowledge/rules": () => RULES,
    "GET knowledge/rules/review": () => review,
    "GET projects": () => PROJECTS,
    "GET people": () => PEOPLE,
    ...extra,
  });
  renderApp(<Knowledge onOpenReview={onOpenReview} />);
  return { calls, onOpenReview };
}

const rows = () => within(screen.getByRole("list", { name: "What Helper knows" })).getAllByRole("listitem");
const texts = () => rows().map((r) => r.querySelector("p")?.textContent);
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

test("it opens on what waits for the person, with a count on each filter", async () => {
  open();
  expect(await screen.findByRole("list", { name: "What Helper knows" })).toBeInTheDocument();
  expect(texts()).toEqual(["Questions about budgets go to finance.", "Catering work goes to the venue lead."]);
  for (const name of ["Proposed (2)", "Active (3)", "Unused (1)", "No longer used (2)"]) {
    expect(screen.getByRole("radio", { name })).toBeInTheDocument();
  }
  expect(screen.getByRole("radio", { name: "Proposed (2)" })).toBeChecked();
});

test("with nothing waiting it opens on what is active", async () => {
  open({ "GET knowledge": () => ENTRIES.filter((e) => e.status !== "proposed") });
  await screen.findByRole("list", { name: "What Helper knows" });
  expect(screen.getByRole("radio", { name: "Active (3)" })).toBeChecked();
});

test("Active, Unused and Retired each show their own entries, rules and entries together, newest first", async () => {
  const user = userEvent.setup();
  open();
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.click(screen.getByRole("radio", { name: "Active (3)" }));
  expect(texts()).toEqual(["A launch review is the meeting before release.", "Release dates come from the schedule.", "Every question names its reader."]);
  // Unused is active and never applied: the rule and the lesson that were used drop out.
  await user.click(screen.getByRole("radio", { name: "Unused (1)" }));
  expect(texts()).toEqual(["A launch review is the meeting before release."]);
  await user.click(screen.getByRole("radio", { name: "No longer used (2)" }));
  expect(texts()).toEqual(["Never close an action without an owner.", "An old habit."]);
});

test("the kind list narrows the rows and the counts to one kind", async () => {
  const user = userEvent.setup();
  open();
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.selectOptions(screen.getByRole("combobox", { name: "Kind" }), "rule");
  expect(screen.getByRole("radio", { name: "Proposed" })).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: "Active (1)" }));
  expect(texts()).toEqual(["Every question names its reader."]);
  expect(screen.getByRole("radio", { name: "No longer used (1)" })).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: "Proposed" }));
  expect(screen.getByText("Nothing to review. New learning from Helper appears here first.")).toBeInTheDocument();
});

test("each row says where it came from, what it reaches and how much it was used", async () => {
  const user = userEvent.setup();
  open();
  await screen.findByRole("list", { name: "What Helper knows" });
  const [budgets, catering] = rows();
  expect(budgets).toHaveTextContent("Only First project");
  expect(budgets).toHaveTextContent("Never used");
  expect(catering).toHaveTextContent("Learned from incoming material");
  expect(catering).toHaveTextContent("From outside · not instructions");
  expect(catering).toHaveTextContent("All projects");
  await user.click(screen.getByRole("radio", { name: "Active (3)" }));
  const [glossary, lesson, ruleRow] = rows();
  expect(ruleRow).toHaveTextContent("Included at setup");
  expect(ruleRow).toHaveTextContent("Used 3 times · last today");
  expect(glossary).toHaveTextContent("All projects except Second project");
  expect(glossary).toHaveTextContent("Never used");
  expect(lesson).toHaveTextContent("Your own words");
  expect(lesson).toHaveTextContent("Used 12 times · last 2 days ago");
  // A word of the row says what it is and what state it is in: status is never colour alone.
  await user.click(screen.getByRole("radio", { name: "No longer used (2)" }));
  expect(rows()[0]).toHaveTextContent("No longer used");
});

test("Keep acts at once with the version that was read, says so, and Undo undoes that change", async () => {
  const user = userEvent.setup();
  const { calls } = open({
    "POST knowledge/LES-4/keep": () => ({ changeset: "CS-7" }),
    "POST changesets/CS-7/undo": () => ({ restored: [], skipped: [] }),
  });
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.click(screen.getByRole("button", { name: "Keep: Questions about budgets go to finance." }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-4/keep")).toEqual({ read_version: 4 }));
  expect(await screen.findByText("Kept. It now guides Helper's work.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-7/undo")).toBe(true));
});

test("the menu of a proposal has Edit and keep, Just this time and Discard, each acting at once with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = open({
    "POST knowledge/LES-4/just-this-time": () => ({ changeset: "CS-1" }),
    "POST knowledge/LES-4/discard": () => ({ changeset: "CS-2" }),
    "POST changesets/CS-2/undo": () => ({ restored: [], skipped: [] }),
  });
  await screen.findByRole("list", { name: "What Helper knows" });
  const menu = () => user.click(within(rows()[0]).getByRole("button", { name: "More actions for Questions about budgets go to finance." }));
  await menu();
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Edit and keep", "Just this time", "Discard"]);
  await user.click(screen.getByRole("menuitem", { name: "Just this time" }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-4/just-this-time")).toEqual({ read_version: 4 }));
  expect(await screen.findByText("Set aside, just this time.")).toBeInTheDocument();
  await menu();
  await user.click(screen.getByRole("menuitem", { name: "Discard" }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-4/discard")).toEqual({ read_version: 4, reason: null }));
  expect(await screen.findByText("Discarded.")).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Undo" }).at(-1)!);
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-2/undo")).toBe(true));
});

test("Edit and keep opens the wording in a drawer with the cursor in it and keeps what the person wrote", async () => {
  const user = userEvent.setup();
  const { calls } = open({ "POST knowledge/LES-4/keep": () => ({ changeset: "CS-3" }) });
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.click(within(rows()[0]).getByRole("button", { name: "More actions for Questions about budgets go to finance." }));
  await user.click(screen.getByRole("menuitem", { name: "Edit and keep" }));
  const field = await screen.findByRole("textbox", { name: "Wording" });
  expect(field).toHaveFocus();
  await user.clear(field);
  await user.type(field, "Budget questions go to finance first.");
  await user.click(screen.getByRole("button", { name: "Keep with this wording" }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-4/keep")).toEqual({ read_version: 4, text: "Budget questions go to finance first." }));
});

test("an active row's one action is Narrow, which narrows to chosen projects, and Retire is in its menu", async () => {
  const user = userEvent.setup();
  const { calls } = open({
    "POST knowledge/LES-1/narrow": () => ({ changeset: "CS-4" }),
    "POST knowledge/LES-1/retire": () => ({ changeset: "CS-5" }),
  });
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.click(screen.getByRole("radio", { name: "Active (3)" }));
  const lesson = rows()[1];
  expect(within(lesson).queryByRole("button", { name: /^Keep/ })).toBeNull();
  await user.click(within(lesson).getByRole("button", { name: "Limit where this applies: Release dates come from the schedule." }));
  const only = within(lesson).getByRole("radio", { name: "Only these projects" });
  expect(only).toHaveFocus();
  expect(within(lesson).getByRole("button", { name: "Save limits" })).toBeDisabled();
  expect(within(lesson).getByText("Choose at least one project.")).toBeInTheDocument();
  await user.click(within(lesson).getByRole("checkbox", { name: "First project" }));
  await user.click(within(lesson).getByRole("button", { name: "Save limits" }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-1/narrow")).toEqual({ read_version: 4, applies_to: { ...WORKSPACE, scope: "projects", projects: ["P-1"], except: [] } }));
  expect(await screen.findByText("Updated where this applies.")).toBeInTheDocument();
  await user.click(within(rows()[1]).getByRole("button", { name: "More actions for Release dates come from the schedule." }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Stop using"]);
  await user.click(screen.getByRole("menuitem", { name: "Stop using" }));
  await waitFor(() => expect(body(calls, "POST knowledge/LES-1/retire")).toEqual({ read_version: 4 }));
  expect(await screen.findByText("No longer used by Helper.")).toBeInTheDocument();
});

test("narrowing a rule that applies everywhere can also leave out some projects, and Escape closes the form", async () => {
  const user = userEvent.setup();
  const { calls } = open({ "POST knowledge/RULE-1/narrow": () => ({ changeset: "CS-6" }) });
  await screen.findByRole("list", { name: "What Helper knows" });
  await user.click(screen.getByRole("radio", { name: "Active (3)" }));
  const row = rows()[2];
  await user.click(within(row).getByRole("button", { name: "Limit where this applies: Every question names its reader." }));
  await user.keyboard("{Escape}");
  expect(within(row).queryByRole("radio")).toBeNull();
  await user.click(within(row).getByRole("button", { name: "Limit where this applies: Every question names its reader." }));
  await user.click(within(row).getByRole("radio", { name: "All projects except these" }));
  await user.click(within(row).getByRole("checkbox", { name: "Second project" }));
  await user.click(within(row).getByRole("button", { name: "Save limits" }));
  await waitFor(() => expect(body(calls, "POST knowledge/RULE-1/narrow")).toEqual({ read_version: 2, applies_to: { ...WORKSPACE, scope: "workspace", projects: [], except: ["P-2"] } }));
});

test("rules to look over show as a line that opens the review", async () => {
  const user = userEvent.setup();
  const flagged = { id: "RULE-1", version: 2, name: "n", text: "Every question names its reader.", applies_to: WORKSPACE, present: 4, applied: 0 };
  const { onOpenReview } = open({}, { ...REVIEW, flagged: [flagged], due: true });
  expect(await screen.findByText("Review 1 rule Helper hasn't used.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Look over rules" }));
  expect(onOpenReview).toHaveBeenCalled();
});

test("a failed load says so, and Try again asks again", async () => {
  const user = userEvent.setup();
  let answer: unknown = new Refuse(500, "nope");
  const { calls } = open({ "GET knowledge": () => answer });
  expect(await screen.findByText("What Helper knows couldn't be loaded.")).toBeInTheDocument();
  const before = calls.filter((c) => c.route === "GET knowledge").length;
  answer = ENTRIES;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("list", { name: "What Helper knows" })).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "GET knowledge").length).toBeGreaterThan(before);
});
