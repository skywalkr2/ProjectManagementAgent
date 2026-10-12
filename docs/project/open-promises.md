# Open promises

Every commitment made to the owner, or to a plugin builder, that isn't yet a checked roadmap item. A promise is written
here in the same turn it is made, and leaves only when its item is checked off with the test that proves it, or the
owner withdraws it. The session reads this file when it starts, resumes, or comes back from a compaction (the hook in
`.claude/settings.json`).

| # | Promised | To | Where it is tracked | State |
|---|---|---|---|---|
| P1 | Run the golden set's "before" report on real models, then summarize it and compare it with the "after" run | owner, design author | roadmap O1 (owner) and L4 | Waiting on the owner's own computer |
| P2 | Answer plugin rounds 34 (170, 172), 35 (173, dependency install) and 38 (183 to 186) in one weekly batch; 183 together with the dependency install | writing pack builder | task list; roadmap A2 (dependency install), C1 | Acknowledged to the builder; not started |
| P4 | Tell the writing pack about `pm/schedule@1` when the project management pack starts | writing pack builder | roadmap C2 | Not due yet |
| P5 | Ask the design author for a paragraph on a typical week of real input, for the day-30 history's noise | design author | roadmap L4 | Offered to the owner; optional |
| P6 | Tell the writing pack's builder what the core will now provide, so it doesn't build it: generic scorers, web search, the research list, the knowledge section; ask it to tag fiction with `learning: own` when that lands, and to keep kills at line level | writing pack builder | this file | Sent 2026-10-12 as a heads-up; details answered in the weekly batch |
| P7 | Tell the mail add-on's builder: attachments will be handed to the core as files once a connector item can carry them; the received date must come from `received`, not the last-changed time; sources will get a default data level; its connectors should declare `reads` (mail or calendar, plugin API 0.3.56) so the new-start walkthrough offers it without guessing from names; and its CI was asked to run less on branch pushes (sent 2026-10-12); mail items should carry the service's own categories and the bulk-mail headers in `categories` and `bulk` (built in plugin API 0.3.57, phase A5), and `sender` as `Name <address>` so sender rules match | mail add-on builder | weekly batch | In the next weekly batch |
| P8 | Microsoft mail and calendar set up as well as Google before 1.0: personal and work accounts, administrator approval said plainly, the setup checklist, a live check and a journey test | owner | roadmap phase D | Recorded 2026-10-12; tell the mail add-on's builder in the weekly batch |
| P9 | The owner's Gmail social and sales mail stops reaching the assistant: the core sets it aside (phase A5, built), and the mail add-on 0.0.9 fills `bulk`, `categories` and `sender` (listed 2026-10-12, catalog PR #5). Leaves this list once the owner's exit test shows mail set aside | owner | phase A exit test | The owner updates the add-on to 0.0.9 and drops the interim Gmail search |
