import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AiCompare } from "./AiCompare";

const account = (name: string, label: string, extra: Partial<S["AiAccountView"]> = {}): S["AiAccountView"] => ({
  name,
  label,
  kind: null,
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "m-1", harder: "m-2" },
  used_for: [],
  backup_for: [],
  has_key: true,
  key_state: "saved",
  key_where: null,
  key_ending: false,
  answered_at: null,
  spent_today_usd: 0,
  checked_for: [],
  check_failed_for: [],
  checked_at: null,
  paused_until: null,
  check_usd: null,
  accepted_unchecked: false,
  ...extra,
});

const cell = (id: string, label: string, over: Partial<S["AiSkillView"]> = {}): S["AiSkillView"] => ({
  id,
  label,
  description: "",
  measured: false,
  runs: 0,
  passes: 0,
  pass_rate: null,
  age_days: null,
  cost_per_pass_usd: null,
  stale: null,
  below_min: false,
  ...over,
});
const measured = (id: string, label: string, rate: number, cost: number | null, over: Partial<S["AiSkillView"]> = {}) =>
  cell(id, label, { measured: true, runs: 18, passes: Math.round(rate * 18), pass_rate: rate, age_days: 2, cost_per_pass_usd: cost, ...over });
const model = (name: string, skills: S["AiSkillView"][], over: Partial<S["AiModelSkills"]> = {}): S["AiModelSkills"] => ({ model: name, measure: null, measure_why: null, skills, ...over });

const SKILLS: S["AiSkillsView"] = {
  min_score: 0.8,
  stale_days: 60,
  accounts: [
    {
      name: "main",
      models: [
        model("everyday", [measured("notes", "Pull actions from meeting notes", 0.94, 0.03), measured("route", "Route a question to who decides", 0.9, 0.02), measured("term", "Use a known term", 0.88, 0.02), cell("voice", "Write an update in your voice")]),
        model("harder", [measured("notes", "Pull actions from meeting notes", 0.97, 0.11), measured("route", "Route a question to who decides", 0.96, 0.08), measured("term", "Use a known term", 1, 0.07), measured("voice", "Write an update in your voice", 0.91, 0.14, { runs: 6, age_days: 40, stale: "age" })]),
      ],
    },
    {
      name: "second",
      models: [model("everyday", [measured("notes", "Pull actions from meeting notes", 0.89, 0.04), measured("route", "Route a question to who decides", 0.85, 0.01), measured("term", "Use a known term", 0.56, 0.05, { below_min: true }), cell("voice", "Write an update in your voice")])],
    },
  ],
};

const estimate = (usd: number | null, needs_go = false): S["AiMeasureEstimate"] => ({ models: ["everyday"], level: "internal", cases: 12, skipped: 0, runs: 3, usd, confirm_above_usd: 0.1, needs_go });

function api(extra: Record<string, (body: unknown) => unknown> = {}, skills: S["AiSkillsView"] = SKILLS) {
  return fakeApi({
    "GET ai/accounts": () => [account("main", "Main account", { used_for: ["routine", "deep"] }), account("second", "Second account", { backup_for: ["routine"] }), account("stub", "Stand-in", { adapter: "stub" })],
    "GET ai/endpoints": () => [],
    "GET ai/skills": () => skills,
    "POST ai/skills/main/estimate": (body) => estimate((body as { model?: string } | undefined)?.model ? 0.12 : 0.4),
    "POST ai/skills/second/estimate": (body) => estimate((body as { model?: string } | undefined)?.model ? 0.12 : 0.08),
    ...extra,
  });
}

const cellOf = async (kind: string, column: string) => {
  const table = await screen.findByRole("table");
  const headers = within(table).getAllByRole("columnheader");
  const index = headers.findIndex((h) => h.textContent === column);
  const row = within(table).getByRole("rowheader", { name: kind }).closest("tr") as HTMLElement;
  return within(row).getAllByRole("cell")[index - 1];
};

test("kinds of work down the side, one column for each account and model with the main account first, and no stand-in account", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  const headers = (await screen.findAllByRole("columnheader")).map((h) => h.textContent);
  expect(headers).toEqual(["Kind of work", "Main account · everyday", "Main account · harder", "Second account · everyday"]);
  const rows = screen.getAllByRole("rowheader").map((r) => r.textContent);
  expect(rows).toEqual(["Pull actions from meeting notes", "Route a question to who decides", "Use a known term", "Write an update in your voice"]);
  expect(screen.getByRole("heading", { level: 1, name: "Compare what accounts can do" })).toBeInTheDocument();
  expect(screen.getByText("Correct answers · cost per correct answer · pass mark 80%")).toBeInTheDocument();
  // The model's own id is never shown.
  expect(document.body).not.toHaveTextContent("m-1");
});

test("each cell has the pass rate first, then cost per right answer, runs and age", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  const c = await cellOf("Pull actions from meeting notes", "Main account · everyday");
  expect(c).toHaveTextContent("94%");
  expect(c).toHaveTextContent("$0.03 · 18 tasks · 2 days ago");
  // Pass rate comes before the cost in reading order.
  expect(c.textContent?.indexOf("94%")).toBeLessThan(c.textContent?.indexOf("$0.03") ?? 0);
});

test("the cheapest cell that passes is marked in each row, in words, and a lone passing cell says only one", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  expect(await cellOf("Pull actions from meeting notes", "Main account · everyday")).toHaveTextContent("✓ Cheapest that passes");
  expect(await cellOf("Route a question to who decides", "Second account · everyday")).toHaveTextContent("✓ Cheapest that passes");
  // "Use a known term": the cheapest overall is below the minimum, so the choice is the cheapest that passes.
  expect(await cellOf("Use a known term", "Main account · everyday")).toHaveTextContent("✓ Cheapest that passes");
  expect(await cellOf("Use a known term", "Second account · everyday")).not.toHaveTextContent("Cheapest");
  // Only one passes: the other is old (counts as unknown) or not measured.
  expect(await cellOf("Write an update in your voice", "Main account · harder")).not.toHaveTextContent("Only one that passes");
});

test("a rate under the minimum has an icon and words, never colour alone", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  const c = await cellOf("Use a known term", "Second account · everyday");
  expect(c).toHaveTextContent("56%");
  expect(c).toHaveTextContent("Below 80%");
  expect(c.querySelector('[data-icon="alert"]')).not.toBeNull();
});

test("an old measurement says so and counts as unknown; one never measured offers Measure with its estimate first", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  const old = await cellOf("Write an update in your voice", "Main account · harder");
  expect(old).toHaveTextContent("40 days ago (old)");
  expect(old).toHaveTextContent("Result unknown");
  expect(old).not.toHaveTextContent("Cheapest");
  const none = await cellOf("Write an update in your voice", "Main account · everyday");
  expect(none).toHaveTextContent("— Not measured yet");
  expect(await within(none).findByRole("button", { name: "Measure Main account · everyday" })).toHaveTextContent("Measure (about $0.12)");
});

test("Measure starts the measuring of that model with the person's go only when it was asked for, and the grid says it is measuring", async () => {
  const user = userEvent.setup();
  let state: S["AiModelSkills"]["measure"] = null;
  const calls = api({
    "GET ai/skills": () => ({ ...SKILLS, accounts: SKILLS.accounts.map((a) => (a.name === "main" ? { ...a, models: a.models.map((m) => (m.model === "everyday" ? { ...m, measure: state } : m)) } : a)) }),
    "POST ai/skills/main/measure": () => {
      state = "measuring";
      return { started: ["everyday"], already: [], estimate: estimate(0.12) };
    },
  });
  renderApp(<AiCompare onBack={() => undefined} />);
  const none = await cellOf("Write an update in your voice", "Main account · everyday");
  await user.click(await within(none).findByRole("button", { name: "Measure Main account · everyday" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/skills/main/measure")?.body).toEqual({ model: "everyday", confirmed: false }));
  expect(await screen.findByText("Testing. Results appear as each test finishes.")).toBeInTheDocument();
  expect(await within(await cellOf("Write an update in your voice", "Main account · everyday")).findByText("Testing…")).toBeInTheDocument();
});

test("a measuring above the amount the person set asks first, with the cost, and starts only after the go", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/skills/main/estimate": () => estimate(0.5, true),
    "POST ai/skills/main/measure": () => ({ started: ["everyday"], already: [], estimate: estimate(0.5, true) }),
  });
  renderApp(<AiCompare onBack={() => undefined} />);
  const none = await cellOf("Write an update in your voice", "Main account · everyday");
  await user.click(await within(none).findByRole("button", { name: "Measure Main account · everyday" }));
  expect(calls.some((c) => c.route === "POST ai/skills/main/measure")).toBe(false);
  expect(within(await cellOf("Write an update in your voice", "Main account · everyday")).getByRole("alert")).toHaveTextContent("This would cost about $0.50, more than the $0.10 you set for asking first.");
  await user.click(screen.getByRole("button", { name: "Test anyway" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST ai/skills/main/measure")?.body).toEqual({ model: "everyday", confirmed: true }));
});

test("Test again shows the total estimate first and, below the amount the person set, measures each account at once", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/skills/main/estimate": () => estimate(0.03),
    "POST ai/skills/second/estimate": () => estimate(0.02),
    "POST ai/skills/main/measure": () => ({ started: ["everyday", "harder"], already: [], estimate: estimate(0.03) }),
    "POST ai/skills/second/measure": () => ({ started: ["everyday"], already: [], estimate: estimate(0.02) }),
  });
  renderApp(<AiCompare onBack={() => undefined} />);
  await user.click(await screen.findByRole("button", { name: "Test again (about $0.05)" }));
  await waitFor(() => expect(calls.filter((c) => c.route.endsWith("/measure")).map((c) => c.route)).toEqual(["POST ai/skills/main/measure", "POST ai/skills/second/measure"]));
  expect(calls.find((c) => c.route === "POST ai/skills/main/measure")?.body).toEqual({ confirmed: false });
});

test("Test again above that amount asks first, with the total, and measures only after the go", async () => {
  const user = userEvent.setup();
  const calls = api({
    "POST ai/skills/main/measure": () => ({ started: ["everyday", "harder"], already: [], estimate: estimate(0.4) }),
    "POST ai/skills/second/measure": () => ({ started: ["everyday"], already: [], estimate: estimate(0.08) }),
  });
  renderApp(<AiCompare onBack={() => undefined} />);
  await user.click(await screen.findByRole("button", { name: "Test again (about $0.48)" }));
  expect(calls.some((c) => c.route.endsWith("/measure"))).toBe(false);
  expect(screen.getByRole("alert")).toHaveTextContent("This would cost about $0.48, more than the $0.10 you set for asking first.");
  await user.click(screen.getByRole("button", { name: "Test anyway" }));
  await waitFor(() => expect(calls.filter((c) => c.route.endsWith("/measure")).length).toBe(2));
  expect(calls.find((c) => c.route === "POST ai/skills/main/measure")?.body).toEqual({ confirmed: true });
});

test("a measuring that failed says why in the cell", async () => {
  api({}, { ...SKILLS, accounts: SKILLS.accounts.map((a) => (a.name === "main" ? { ...a, models: a.models.map((m) => (m.model === "everyday" ? { ...m, measure: "failed" as const, measure_why: "The key was refused." } : m)) } : a)) });
  renderApp(<AiCompare onBack={() => undefined} />);
  expect(await cellOf("Write an update in your voice", "Main account · everyday")).toHaveTextContent("Didn't finish: The key was refused.");
});

test("Back returns to Settings, and a list that didn't load says so with Try again", async () => {
  const user = userEvent.setup();
  const onBack = vi.fn();
  const view = renderApp(<AiCompare onBack={onBack} />);
  api();
  view.unmount();
  renderApp(<AiCompare onBack={onBack} />);
  await user.click(await screen.findByRole("button", { name: "Back to settings" }));
  expect(onBack).toHaveBeenCalledTimes(1);
  view.unmount();
  api({ "GET ai/skills": () => new Refuse(500, "") });
  renderApp(<AiCompare onBack={onBack} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("What the accounts can do didn't load.");
});

test("with nothing measured and no accounts it says there is nothing to compare", async () => {
  api({ "GET ai/accounts": () => [] }, { min_score: 0.8, stale_days: 60, accounts: [] });
  renderApp(<AiCompare onBack={() => undefined} />);
  expect(await screen.findByText("There is nothing to compare yet. Add an account first.")).toBeInTheDocument();
});

test("a cell that was never measured says so and never counts zero tasks", async () => {
  api();
  renderApp(<AiCompare onBack={() => undefined} />);
  const c = await cellOf("Write an update in your voice", "Main account · everyday");
  expect(c).toHaveTextContent("Not measured yet");
  expect(c).not.toHaveTextContent(/\b0 tasks?\b/);
});

const UNMEASURED: S["AiSkillsView"] = {
  min_score: 0.8,
  stale_days: 60,
  accounts: [
    { name: "main", models: [model("everyday", [cell("notes", "Pull actions from meeting notes"), cell("route", "Route a question to who decides")])] },
    { name: "second", models: [model("everyday", [cell("notes", "Pull actions from meeting notes"), cell("route", "Route a question to who decides")])] },
  ],
};

test("with accounts but nothing measured the page says so and offers Measure with the app's own estimate, not a grid of blanks", async () => {
  const user = userEvent.setup();
  const calls = api({}, UNMEASURED);
  renderApp(<AiCompare onBack={() => undefined} />);
  expect(await screen.findByText(/Nothing measured yet\./)).toBeInTheDocument();
  expect(screen.queryByText("There is nothing to compare yet. Add an account first.")).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
  const measure = await screen.findByRole("button", { name: "Measure (about $0.48)" });
  expect(measure).toBeEnabled();
  await user.click(measure);
  // About $0.48 is more than the amount the person asked to be asked above, so it asks first.
  expect(await screen.findByText(/This would cost about \$0\.48, more than the \$0\.10 you set for asking first\./)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Test anyway" }));
  await waitFor(() => expect(calls.filter((c) => c.route.startsWith("POST ai/skills/") && c.route.endsWith("/measure"))).toHaveLength(2));
});

test("with no account at all the page asks for one first", async () => {
  api({ "GET ai/accounts": () => [] }, UNMEASURED);
  renderApp(<AiCompare onBack={() => undefined} />);
  expect(await screen.findByText("There is nothing to compare yet. Add an account first.")).toBeInTheDocument();
  expect(screen.queryByText(/Nothing measured yet/)).toBeNull();
});
