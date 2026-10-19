import type { S } from "./api";
import { hasSomething } from "./today";

const line = (kind: S["QueueLineView"]["kind"], count: number): S["QueueLineView"] =>
  ({ key: `${kind}:1`, group: "risk", kind, count, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {} }) as S["QueueLineView"];

test("a line that counts things is shown only when it holds some, whatever the kind", () => {
  for (const kind of ["first_go", "catch_up_go", "restart", "paused", "borrow", "offline", "overdue", "review", "learned", "catch_up", "send", "nudge"] as const) {
    expect(hasSomething(line(kind, 0)), kind).toBe(false);
    expect(hasSomething(line(kind, 1)), kind).toBe(true);
  }
});

test("a line that is about one thing, or words its own count, stays even with a count of zero", () => {
  for (const kind of ["decision", "question", "who_is", "owner", "held", "refused", "failed", "credential", "rule_review"] as const) {
    expect(hasSomething(line(kind, 0)), kind).toBe(true);
  }
});
