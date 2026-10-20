# UI/UX re-review at `c8f8e18` (received 2026-10-20)

The UI/UX design review session re-reviewed batch B-6b at commit `c8f8e18` and sent its feedback on 2026-10-20. The
full text, its screenshots and the script that measured them are in `reviews/ui-ux-2026-10/rereview-c8f8e18/`
(`README.md`, `screens/`, `tools/capture-and-measure.mjs`, `metrics.json`). This file records what was received and what
the owner accepted; the roadmap's B-7 items carry the work.

## What it found

- **Verdict:** a big step. The header is 56px from 1280px up and 88px from 1024 to 1279px; content fills the width on
  every view with no sideways scroll; no "Loading…", text glyphs or uppercase; bordered nesting at most two; the five
  bugs of the last round are fixed.
- **Its count for C1–C46:** Done 23, Partial 21, Not done 2 (the build's own count was 23 / 23 / 0). Not done: C9 (the
  first queue line is at 429px at 1280×720) and C19 (ids, raw values and ISO dates on record pages and in What changed).
- **Findings, P1:** 3.1 Today's first screen (the backup and This week bars push the queue down); 3.2 record pages (ids,
  raw values, help text, empty separators, field keys in activity); 3.3 tables break words beside the detail pane; 3.4 one
  row per thing (Top priorities repeats the queue; one follow-up line per person); 3.5 the assistant's bookkeeping in
  item text.
- **Findings, P2:** 3.6 What changed fully open; 3.7 header crowding from 1024 to 1440px; 3.8 targets under 24px; 3.9
  weight 700; 3.10 the AI compare wording; 3.11 the setup stepper; 3.12 a form on the rail; 3.13 small layout points;
  3.14 the phone page's length; 3.15 the "From outside" phrase on every review line.
- **Checklist additions:** C47 to C53.
- **Its ask:** demo data with a moved meeting, a held inference, an inferred fact, a series and a rules line, so answers
  27 to 31 show on screen.

## What the owner accepted

All of it (owner, 2026-10-20: "give them what they want and include the ai fixes"), with the choices recorded in
`docs/decisions.md` (2026-10-20, "The UI/UX re-review is accepted in full"). The work is the roadmap's B-7 items.
