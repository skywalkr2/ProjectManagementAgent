import { mergeRules, type RuleRow } from "./ai-routing";

const row = (task: string, tier = "deep"): RuleRow => ({ task, chars: "", quotes: "", level: "", tier });

test("after a refusal the rules changed elsewhere stay, the person's own added and changed rows are kept, and what they removed stays removed", () => {
  const old = [row("a"), row("b"), row("c")];
  // The person removed b and added d; elsewhere c was changed to a different tier and e was added.
  const mine = [row("a"), row("c"), row("d")];
  const now = [row("a"), row("b"), row("c", "routine"), row("e")];
  expect(mergeRules(old, mine, now)).toEqual([row("a"), row("c", "routine"), row("e"), row("d")]);
});

test("with nothing changed elsewhere the person's rows come back as they were", () => {
  const old = [row("a")];
  const mine = [row("a"), row("b")];
  expect(mergeRules(old, mine, old)).toEqual(mine);
});
