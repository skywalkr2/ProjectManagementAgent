# Evaluation reports

Reports of `cockpit evaluate` on real AI accounts, kept so later runs can be compared with earlier ones. Each file is
the JSON report of one account on one version of the golden set, named `<date>-<set>-<tier>.json` (for example
`2026-10-12-before-low-cost.json`). The account itself is described in words in the table below, never by key or
address.

| Date | Set | Account | Pass rate | Notes |
|---|---|---|---|---|
| 2026-10-14 | before (14 cases, commit `802538e`) | The owner's command-line agent account, on a subscription (both tiers use it) | 1.0 (42 of 42) | `2026-10-14-before-agent.json`. Every case passed every run, 4 to 13 s each, no cost charged per call; `shared-first-name` held its one item each run, as designed. The set has no headroom on this account, so the L4 comparison rests on the harder set and the learning pairs. Run with the account file trimmed of one setting the pinned version predates (`budgets.first_go`), which doesn't touch the cases, the scoring or the packet. |
