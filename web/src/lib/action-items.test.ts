import type { S } from "./api";
import { changedRequests, countKept, countKeptRequests, followsDroppedItem, opsWithTicks, ticksOf } from "./action-items";

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

const request = (id: string, extra: Partial<S["ActionRequestView"]> = {}): S["ActionRequestView"] => ({
  id,
  kept: true,
  task: "t",
  label: id,
  about: null,
  note: "",
  ...extra,
});

test("a request is kept by its own tick unless the item it goes with is dropped", () => {
  const requests = [request("r1"), request("r2", { item: "a" }), request("r3", { item: "b" }), request("r4", { kept: false })];
  const itemTicks = { a: true, b: false, c: true };
  expect(countKeptRequests(requests, items, itemTicks, {})).toBe(2);
  expect(countKeptRequests(requests, items, itemTicks, { r1: false, r4: true })).toBe(2);
  expect(followsDroppedItem(requests[2], items, itemTicks)).toBe(true);
  expect(followsDroppedItem(requests[1], items, itemTicks)).toBe(false);
});

test("only the requests that differ from what was offered are reported", () => {
  const requests = [request("r1"), request("r2", { item: "b" }), request("r3", { kept: false })];
  const itemTicks = { a: true, b: false, c: true };
  expect(changedRequests(requests, items, itemTicks, {})).toEqual({ r2: false });
  expect(changedRequests([request("r1")], items, itemTicks, {})).toBeUndefined();
});
