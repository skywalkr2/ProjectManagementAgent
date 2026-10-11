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
