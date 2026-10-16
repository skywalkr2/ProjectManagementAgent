// The grid of what each AI account can do (design 6.16, 7.16): pass rate first, then cost per right answer among the
// models that pass. Plain functions over the measured skills, so the cell states and the choice of the cheapest passing
// model are tested without a screen.
import type { S } from "./api";

export type SkillCell = S["AiSkillView"];

export type CellState = "pass" | "below" | "old" | "none";

/** What a cell shows: a measurement that counts and passes, one under the minimum, one that is out of date (it counts as
 * unknown), or none at all. */
export function cellState(cell: SkillCell | undefined): CellState {
  if (!cell || !cell.measured || cell.pass_rate == null) return "none";
  if (cell.stale) return "old";
  return cell.below_min ? "below" : "pass";
}

/** In each row, the passing models' cell that costs least for a right answer, by position in the row: marked "Cheapest that
 * passes", or "Only one that passes" when it is the only one. A row where several pass and none has a price marks nothing,
 * since the cheapest can't be told. */
export function bestOf(row: (SkillCell | undefined)[]): { index: number; only: boolean } | null {
  const passing = row.flatMap((cell, index) => (cellState(cell) === "pass" ? [{ index, cost: cell?.cost_per_pass_usd ?? null }] : []));
  if (passing.length === 0) return null;
  if (passing.length === 1) return { index: passing[0].index, only: true };
  const priced = passing.filter((p) => p.cost != null) as { index: number; cost: number }[];
  if (priced.length === 0) return null;
  const best = priced.reduce((a, b) => (b.cost < a.cost ? b : a));
  return { index: best.index, only: false };
}

export interface Column {
  account: string;
  model: string;
  /** Where a measuring the person asked for stands, if one is asked for. */
  measure: S["AiModelSkills"]["measure"];
  measure_why: S["AiModelSkills"]["measure_why"];
  skills: SkillCell[];
}

/** One column for each model of each account, in the order the accounts are given; the skills across them in the order they are first met. */
export function gridOf(order: string[], accounts: S["AiAccountSkills"][]): { columns: Column[]; rows: { id: string; label: string }[] } {
  const columns: Column[] = [];
  for (const name of order) {
    const found = accounts.find((a) => a.name === name);
    for (const model of found?.models ?? []) {
      columns.push({ account: name, model: model.model, measure: model.measure, measure_why: model.measure_why, skills: model.skills });
    }
  }
  const rows: { id: string; label: string }[] = [];
  for (const column of columns) {
    for (const skill of column.skills) {
      if (!rows.some((r) => r.id === skill.id)) rows.push({ id: skill.id, label: skill.label });
    }
  }
  return { columns, rows };
}
