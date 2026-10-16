import type { S } from "./api";
import { bestOf, cellState, gridOf } from "./ai-compare";

const cell = (over: Partial<S["AiSkillView"]> = {}): S["AiSkillView"] => ({
  id: "s",
  label: "Skill",
  description: "",
  measured: true,
  runs: 10,
  passes: 9,
  pass_rate: 0.9,
  age_days: 2,
  cost_per_pass_usd: 0.05,
  stale: null,
  below_min: false,
  ...over,
});

test("a cell passes, is below the minimum, is old (and counts as unknown) or was never measured", () => {
  expect(cellState(cell())).toBe("pass");
  expect(cellState(cell({ below_min: true, pass_rate: 0.5 }))).toBe("below");
  expect(cellState(cell({ stale: "age" }))).toBe("old");
  expect(cellState(cell({ measured: false, pass_rate: null }))).toBe("none");
  expect(cellState(undefined)).toBe("none");
});

test("the cheapest cell that passes is marked, and a lone passing cell is the only one that passes", () => {
  // Pass rate first: the cheapest overall is below the minimum and is not chosen.
  expect(bestOf([cell({ cost_per_pass_usd: 0.03 }), cell({ cost_per_pass_usd: 0.11 }), cell({ below_min: true, cost_per_pass_usd: 0.01 })])).toEqual({ index: 0, only: false });
  expect(bestOf([cell({ below_min: true }), cell({ cost_per_pass_usd: 0.14 }), undefined])).toEqual({ index: 1, only: true });
  // An old measurement counts as unknown: it can't be the choice.
  expect(bestOf([cell({ stale: "program", cost_per_pass_usd: 0.01 }), cell({ cost_per_pass_usd: 0.2 })])).toEqual({ index: 1, only: true });
  // Nothing passes: nothing is marked.
  expect(bestOf([cell({ below_min: true }), undefined])).toBeNull();
  // Several pass but none has a price: the cheapest can't be told.
  expect(bestOf([cell({ cost_per_pass_usd: null }), cell({ cost_per_pass_usd: null })])).toBeNull();
  // The first of equal prices wins.
  expect(bestOf([cell({ cost_per_pass_usd: 0.05 }), cell({ cost_per_pass_usd: 0.05 })])).toEqual({ index: 0, only: false });
});

test("the grid has a column for each model of each account in the order given, and the kinds of work in the order they are met", () => {
  const model = (name: string, ids: string[]): S["AiModelSkills"] => ({ model: name, measure: null, measure_why: null, skills: ids.map((id) => cell({ id, label: id.toUpperCase() })) });
  const accounts: S["AiAccountSkills"][] = [
    { name: "a", models: [model("everyday", ["x", "y"])] },
    { name: "b", models: [model("everyday", ["y", "z"]), model("harder", ["z"])] },
  ];
  const grid = gridOf(["b", "a", "missing"], accounts);
  expect(grid.columns.map((c) => `${c.account}/${c.model}`)).toEqual(["b/everyday", "b/harder", "a/everyday"]);
  expect(grid.rows.map((r) => r.id)).toEqual(["y", "z", "x"]);
});
