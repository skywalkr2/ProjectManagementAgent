import type { S } from "./api";
import { countKept, opsWithTicks, ticksOf } from "./action-items";

const op = (label: string): S["ProposedOp"] => ({ op: "note", label });
const item = (id: string, kept: boolean, ops: S["ProposedOp"][]): S["ActionItem"] => ({ id, label: id, kept, ops, group: null });

function proposal(items: S["ActionItem"][], ops: S["ProposedOp"][]): S["ActionProposalView"] {
  return { token: "t", action: "a", summary: "s", ops, files: [], previews: [], choices: [], notes: [], expires_at: "", items };
}

const items = [item("a", true, [op("A")]), item("b", false, [op("B")]), item("c", true, [op("C1"), op("C2")])];
const base = proposal(items, [op("Always"), op("A"), op("C1"), op("C2")]);

test("ticks start as the proposal came", () => {
  expect(ticksOf(items)).toEqual({ a: true, b: false, c: true });
  expect(ticksOf(undefined)).toEqual({});
});

test("the changes are the proposal's own while the ticks are unchanged", () => {
  expect(opsWithTicks(base, ticksOf(items)).map((o) => o.label)).toEqual(["Always", "A", "C1", "C2"]);
});

test("dropping an item takes its changes out and keeping a dropped one puts them in", () => {
  const labels = opsWithTicks(base, { a: false, b: true, c: true }).map((o) => o.label);
  expect(labels).toEqual(["Always", "C1", "C2", "B"]);
});

test("items are counted by their current ticks", () => {
  expect(countKept(items, { a: false, b: false, c: true })).toBe(1);
  expect(countKept(items, {})).toBe(2);
});
