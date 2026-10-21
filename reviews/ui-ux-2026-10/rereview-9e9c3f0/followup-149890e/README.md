# Follow-up check at `149890e`

**What was checked:** the B-9 fixes, R-0 to R-c and the wording verdict.

**How:** on the full demo and a fresh workspace, at 03:40 UTC on Oct 21. That is 23:40 on Oct 20 in the demo's time zone,
the window where "-1 days" used to show.

| Item | Result | Seen |
|---|---|---|
| R-0: "-1 days" | **Fixed** | No negative day count on Today, Follow-ups, What changed, or To-dos and questions. I marked a message sent at 23:41 local time: it reads "sent today", and Today still has no negative count (`r0-*.png`) |
| R-a: process name as a title | **Fixed** | "After 'Cover review' moved" (`ra-what-changed.png`) |
| R-b: raw model names | **Fixed** | "AI model: Recommended / Stronger / Faster"; the program's own name appears only in the hint (`rb-ai-program.png`) |
| R-c: the question repeated | **Fixed** | The details pane starts with "The words it rests on" (`rc-held-details.png`) |
| Wording: Connections | **Done as marked** | Sidebar, heading, "Add a connection" (`w-connections.png`) |
| Wording: Drop | **Done as marked** | The menu shows "Drop · No longer needed, kept in history" (`w-drop-menu.png`) |
| The estimate on the Start button | **Fine as built** | The line already says "Start the assistant: 1 item, about $0.30". Keep the button as "Start" |

## Three small points (P2)

- **"Waiting 0 days" / "waiting up to 0 days".** When the count is zero, say "Sent today" in the pill and "sent today"
  in the meta (`r0-today-nudges.png`).
- **Connections → Set aside.** The intro still says "Confirm the sorting…", but the button is now "Keep it set aside".
  Use "Choose Keep it set aside to teach the sorting…".
- **Connections → Closed without you seeing.** "0 of 1 closes in the last 28 days weren't seen by you" reads like a log
  entry. Use "You saw everything closed in the last 28 days" when the count is zero, and "1 of 3 closed without you
  seeing it" otherwise.

Nothing here needs a new batch.
