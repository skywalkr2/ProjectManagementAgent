// The first go (design 7.8): until the person's first go in a workspace, AI runs wait, and Today shows them as one line
// with how many there are and what they would cost together.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "./api";
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

/** The requests waiting on the first go, counted as one thing. Dismissed ones don't wait. `sorting` is the sorting run
 * the go also makes for mail handed in unsorted: its price joins the total and a run with no price counts as unpriced. */
export function firstGoOf(changes: S["ChangeItem"][] | undefined, sorting?: S["FirstGoSorting"] | null): FirstGo {
  const waiting = (changes ?? []).filter((c) => c.first_go && !c.dismissed && c.state === "needs_you");
  const priced = waiting.filter((c) => c.estimate_usd != null);
  const requests = priced.reduce((sum, c) => sum + (c.estimate_usd ?? 0), 0);
  const extra = sorting && waiting.length > 0 ? sorting : null;
  const anyPrice = priced.length > 0 || (extra?.estimate_usd ?? null) !== null;
  return {
    count: waiting.length,
    estimate: anyPrice ? requests + (extra?.estimate_usd ?? 0) : null,
    unpriced: waiting.length - priced.length + (extra?.unpriced ?? 0),
  };
}

/** What the first go's sorting run adds to the estimate; read only while runs wait for the go. */
export function useFirstGoSorting(waiting: boolean): S["FirstGoSorting"] | undefined {
  const sorting = useQuery({ queryKey: ["first-go-sorting"], queryFn: api.firstGoSorting, enabled: waiting });
  return sorting.data;
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
