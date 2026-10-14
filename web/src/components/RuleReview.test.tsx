import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { RuleReview } from "./RuleReview";

const WORKSPACE: S["Scope"] = { scope: "workspace", task_kinds: [], records: [], filter: {}, projects: [], people: [], except: [] };

const flagged = (id: string, text: string, over: Partial<S["RuleReviewRule"]> = {}): S["RuleReviewRule"] => ({
  id,
  version: 3,
  name: `name-${id}`,
  text,
  applies_to: WORKSPACE,
  present: 5,
  applied: 0,
  ...over,
});

const REVIEW: S["RuleReviewView"] = {
  days: 30,
  flagged: [
    flagged("RULE-1", "Every question names its reader.", { present: 7 }),
    flagged("RULE-2", "Close nothing without an owner.", { applies_to: { ...WORKSPACE, except: ["P-2"] }, present: 1 }),
  ],
  stable_chars: 5200,
  stable_budget: 6000,
  moved: 2,
  due: true,
};

function open(extra: Routes = {}, review: S["RuleReviewView"] = REVIEW, onBack = vi.fn()) {
  const calls = fakeApi({
    "GET knowledge/rules/review": () => review,
    "GET projects": () => [{ id: "P-1", name: "First project" }, { id: "P-2", name: "Second project" }],
    "GET people": () => [],
    ...extra,
  });
  renderApp(<RuleReview onBack={onBack} />);
  return { calls, onBack };
}

const rows = () => within(screen.getByRole("list", { name: "Rules to look over" })).getAllByRole("listitem");
const body = (calls: ReturnType<typeof fakeApi>, route: string) => calls.find((c) => c.route === route)?.body;

test("it lists the flagged rules with how often each was given, and the size against its budget and the rules moved", async () => {
  open();
  expect(await screen.findByRole("heading", { level: 1, name: "Rules to look over" })).toBeInTheDocument();
  expect(await screen.findByText(/none of them showed in its work in the last 30 days/)).toBeInTheDocument();
  expect(screen.getByText("Sent with every run: 5200 of 6000 characters of rules, lessons and terms.")).toBeInTheDocument();
  expect(screen.getByText("2 rules moved out of the part sent every time. They go only with the runs they cover.")).toBeInTheDocument();
  const [first, second] = rows();
  expect(first).toHaveTextContent("Every question names its reader.");
  expect(first).toHaveTextContent("Given to 7 runs, never applied");
  expect(first).toHaveTextContent("All projects");
  expect(second).toHaveTextContent("Given to 1 run, never applied");
  expect(second).toHaveTextContent("All projects except Second project");
});

test("Keep starts the rule's review clock again with the version that was read, and Undo puts the old clock back", async () => {
  const user = userEvent.setup();
  const { calls } = open({
    "POST knowledge/RULE-1/keep-rule": () => ({ changeset: "CS-1" }),
    "POST changesets/CS-1/undo": () => ({ restored: [], skipped: [] }),
  });
  await screen.findByRole("list", { name: "Rules to look over" });
  await user.click(screen.getByRole("button", { name: "Keep: Every question names its reader." }));
  await waitFor(() => expect(body(calls, "POST knowledge/RULE-1/keep-rule")).toEqual({ read_version: 3 }));
  expect(await screen.findByText("Kept. Its next review starts now.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-1/undo")).toBe(true));
});

test("Narrow and Retire are in each row's menu and act at once with Undo", async () => {
  const user = userEvent.setup();
  const { calls } = open({
    "POST knowledge/RULE-1/narrow": () => ({ changeset: "CS-2" }),
    "POST knowledge/RULE-2/retire": () => ({ changeset: "CS-3" }),
  });
  await screen.findByRole("list", { name: "Rules to look over" });
  await user.click(within(rows()[0]).getByRole("button", { name: "More actions for Every question names its reader." }));
  expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Narrow", "Retire"]);
  await user.click(screen.getByRole("menuitem", { name: "Narrow" }));
  const row = rows()[0];
  expect(within(row).getByRole("radio", { name: "Only these projects" })).toHaveFocus();
  await user.click(within(row).getByRole("checkbox", { name: "First project" }));
  await user.click(within(row).getByRole("button", { name: "Narrow" }));
  await waitFor(() =>
    expect(body(calls, "POST knowledge/RULE-1/narrow")).toEqual({ read_version: 3, applies_to: { ...WORKSPACE, scope: "projects", projects: ["P-1"], except: [] } }),
  );
  expect(await screen.findByText("Narrowed.")).toBeInTheDocument();
  await user.click(within(rows()[1]).getByRole("button", { name: "More actions for Close nothing without an owner." }));
  await user.click(screen.getByRole("menuitem", { name: "Retire" }));
  await waitFor(() => expect(body(calls, "POST knowledge/RULE-2/retire")).toEqual({ read_version: 3 }));
  expect(await screen.findByText("Retired. It no longer guides Helper's work.")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Notifications" })).getAllByRole("button", { name: "Undo" }).length).toBeGreaterThan(0);
});

test("with nothing flagged it says so, and Back returns to Knowledge", async () => {
  const user = userEvent.setup();
  const { onBack } = open({}, { ...REVIEW, flagged: [], moved: 0 });
  expect(await screen.findByText("No rules to look over right now.")).toBeInTheDocument();
  expect(screen.queryByText(/moved out of the part sent every time/)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Back to Knowledge" }));
  expect(onBack).toHaveBeenCalled();
});

test("a failed load says so, with Try again", async () => {
  const user = userEvent.setup();
  let answer: unknown = new Refuse(500, "nope");
  const { calls } = open({ "GET knowledge/rules/review": () => answer });
  expect(await screen.findByText("The rules to look over couldn't be loaded.")).toBeInTheDocument();
  answer = REVIEW;
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("list", { name: "Rules to look over" })).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "GET knowledge/rules/review").length).toBeGreaterThan(1);
});
