// The first go (design 7.8): until the person's first go in a workspace, AI runs wait, and Today shows them as one line
// with how many there are and what they would cost together.
import type { S } from "./api";
import { useTotal } from "./money";
import { useWords } from "./wording";

export interface FirstGo {
  /** How many runs wait for the first go. */
  count: number;
  /** What the runs that have a price would cost together, or null when none has one. */
  estimate: number | null;
  /** How many of the runs have no price (they use the plan's allowance). */
  unpriced: number;
}

/** The requests waiting on the first go, counted as one thing. Dismissed ones don't wait. */
export function firstGoOf(changes: S["ChangeItem"][] | undefined): FirstGo {
  const waiting = (changes ?? []).filter((c) => c.first_go && !c.dismissed && c.state === "needs_you");
  const priced = waiting.filter((c) => c.estimate_usd != null);
  return {
    count: waiting.length,
    estimate: priced.length ? priced.reduce((sum, c) => sum + (c.estimate_usd ?? 0), 0) : null,
    unpriced: waiting.length - priced.length,
  };
}

/** The line's words: "Start the assistant: 12 items, about $0.30", or the count and the plan's allowance when there
 * is no price. */
export function useFirstGoText(): (first: FirstGo) => string {
  const { t, tn } = useWords();
  const total = useTotal();
  return (first) => {
    if (first.estimate === null) return tn("first_go.unpriced", first.count);
    const cost = first.estimate < 0.005 ? t("first_go.under_cent") : t("first_go.about", { amount: total(first.estimate) });
    return first.unpriced > 0
      ? tn("first_go.mixed", first.count, { cost })
      : tn("first_go.priced", first.count, { cost });
  };
}
