// The ticks on a proposal's items. They are kept on the screen while the person decides and go back with the apply;
// the list of changes follows them without asking the action again.
import type { S } from "./api";

export type Ticks = Record<string, boolean>;

/** The ticks the proposal came back with, by item id. */
export function ticksOf(items: S["ActionItem"][] = []): Ticks {
  return Object.fromEntries(items.map((item) => [item.id, item.kept]));
}

const same = (a: S["ProposedOp"], b: S["ProposedOp"]) => a.op === b.op && a.label === b.label;

/** The changes that apply with the ticks as they are now: the proposal's own list, less the changes of an item that
 * was kept when it was made and has since been dropped, plus those of one dropped then and kept since. */
export function opsWithTicks(proposal: S["ActionProposalView"], ticks: Ticks): S["ProposedOp"][] {
  const ops = [...proposal.ops];
  for (const item of proposal.items ?? []) {
    const now = ticks[item.id] ?? item.kept;
    if (now === item.kept) continue;
    if (!now) {
      for (const op of item.ops) {
        const at = ops.findIndex((o) => same(o, op));
        if (at >= 0) ops.splice(at, 1);
      }
    } else {
      ops.push(...item.ops);
    }
  }
  return ops;
}

/** How many of some items are kept. */
export function countKept(items: S["ActionItem"][], ticks: Ticks): number {
  return items.filter((item) => ticks[item.id] ?? item.kept).length;
}

/** The item a request goes with, when it has one that is in the proposal. */
export function itemOf(request: S["ActionRequestView"], items: S["ActionItem"][] = []): S["ActionItem"] | undefined {
  return request.item ? items.find((i) => i.id === request.item) : undefined;
}

/** Whether a request is dropped because the item it goes with is dropped: then its own tick has no say. */
export function followsDroppedItem(request: S["ActionRequestView"], items: S["ActionItem"][], itemTicks: Ticks): boolean {
  const item = itemOf(request, items);
  return !!item && !(itemTicks[item.id] ?? item.kept);
}

/** Whether a request will be queued: kept by its own tick, and not dropped along with its item. */
export function requestKept(request: S["ActionRequestView"], items: S["ActionItem"][], itemTicks: Ticks, ticks: Ticks): boolean {
  return !followsDroppedItem(request, items, itemTicks) && (ticks[request.id] ?? request.kept);
}

/** How many of the requests will be queued with the ticks as they are now. */
export function countKeptRequests(requests: S["ActionRequestView"][], items: S["ActionItem"][], itemTicks: Ticks, ticks: Ticks): number {
  return requests.filter((r) => requestKept(r, items, itemTicks, ticks)).length;
}

/** The requests whose final state differs from what the proposal offered, by id; nothing when none do. */
export function changedRequests(
  requests: S["ActionRequestView"][],
  items: S["ActionItem"][],
  itemTicks: Ticks,
  ticks: Ticks,
): Ticks | undefined {
  const changed: Ticks = {};
  for (const r of requests) {
    const now = requestKept(r, items, itemTicks, ticks);
    if (now !== r.kept) changed[r.id] = now;
  }
  return Object.keys(changed).length ? changed : undefined;
}
