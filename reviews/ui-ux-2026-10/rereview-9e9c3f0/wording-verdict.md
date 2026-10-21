# Verdict on `docs/project/wording-review-2026-10.md`

**From:** the UI designer, at `9e9c3f0`.

**How to read this:**
- Each row of the outside review is marked **accept** (use the suggested words), **change** (use my words) or **reject**
  (keep the current words).
- Rows not listed here are accepted as suggested.
- Apply the accepted rows through the wording test as planned.

**One thing to fix in the review itself:** its "current words" column is out of date in places. `stages.go`,
`changes.go` and `today.plugins.give_go` already say "Start", and `nav.records` already says "Saved items". Check each
row against `en.json` before applying it.

## 1. The four renames

| Rename | Verdict | Why |
|---|---|---|
| **Sources → Connections** | **Accept, for the area and what's set up in it.** | "Connections" names what a person does: connect a mailbox, a calendar or a folder. But "source" has a second meaning in the product: **the original text something came from** ("Show source", "Where it came from", a fact's source). That stays "source". So rename the area, its buttons and its counts (`nav.sources`, `sources.*`, `today.arrived.*`, `sign_in.intro`, and the Today header line "Read 1 source" → "Checked 1 connection"). Keep "Show source" and every evidence use as they are. **Reject `op.source`** ("Recorded a source" → "Added a connection"): that op saves an input's text, not a connection. Use "Saved the original text" |
| **Stages → Steps** | **Reject. Keep "Stages".** | "Steps" already means three other things on screen: the setup guide's steps ("Setup 3 of 5", "this step is waiting"), the numbered steps for an AI key, and a template's steps. "Move to step Captured" would be read as a setup step. "Stage" is an everyday word (a project's stage), not jargon. Do take the shorter sentences from those rows with "stage" kept, for example `stages.empty`: "Nothing is moving through stages yet. Items appear here once their stages are set up." |
| **Go → Start** | **Accept (already done in most places).** | "Start" matches the setup guide ("nothing is spent until you press Start"). Where the button starts paid work, add the estimate to it: "Start (about $0.30)". `changes.go`: keep "Start"; the review's "Start the check" is wrong, because it starts the assistant's work, not a check. `role.run` "Run it": change to **"Start"**, not "Start this step", for the same reason as Stages |
| **Drop → Remove** | **Reject. Keep "Drop".** | In this product "drop" means "no longer needed, kept in history with the reason". "Remove" already means delete (remove an account, remove a person nobody refers to). Using one word for both would make a reversible act sound permanent, and the held answer "Drop it" would clash with the menu. To make "Drop" clear, give the menu item a second line: **"Drop · no longer needed, kept in history"** |

## 2. Other rows that are changed or rejected

| Key | Verdict | Use / keep | Why |
|---|---|---|---|
| `op.record.log` | change | "Added to the project's history" | "Notes" is already a different thing (notes filed under a project) |
| `feedback.screen.record` | change | "A project or person page" | "Item page" is vaguer than what it is |
| `addons.demo_command` | change | Keep the command, but only under a "For developers" disclosure on Add-ons | It's a developer tool; it shouldn't be on the default path (N5), and it shouldn't pretend to be a button either |
| `sign_in.own.client_id` | change | "Sign-in app ID", with the hint "Some sites call it a client ID" | People copy it from a console that uses the technical name |
| `settings.group.server` | change | "How the app is reached" (under Advanced) | "Local connection" clashes with Connections |
| `styleguide.*` | reject | — | The style guide is developer-only; it isn't worth the churn |
| `welcome.ai.model_choice`, `welcome.ai.model`, `ai_accounts.models_title` | **reject** | Keep "model" | "AI choice" is vaguer. "Model" is the word the person meets on every AI service's own pages, where they have to pick one. The picker already sits under Advanced; explain it once in the hint: "the version of the AI, which the service calls a model" |
| `welcome.ai.model_program_picks_hint` | change | "This app chooses its own model; change it in that app's own settings." | Keep "model", and fix the repeated "program" |
| `addons.token.*` (5 rows) | change | "read key", with "(some sites call it a token)" in `addons.token.intro` only | Matches "access key" elsewhere; the hint helps people copying from a site that says "token" |
| `queue.restart.manual` | change | "The app needs to restart for this change. Close it and open it again; the assistant waits until you do." | The suggestion dropped the most important part: nothing runs until the restart |
| `newperson.first_name_hint` | change | "Used in greetings. Leave it blank to use the first word of the full name." | The suggestion dropped what the field is for |
| `followups.empty_waiting` | change | "Nothing is waiting for a reply. What you send shows here until they reply or it's done." | "The matter is settled" is vague |
| `setup.sync_unset` | change | "A synced folder keeps a copy of your work in your cloud drive, so your other computers have it." | **"Shared folder" is wrong:** it suggests other people. This is your own folder across your own computers. Keep "synced", which is the word cloud-drive users know |
| `handover.*` (5 rows) | change | Take the shorter sentences, but "synced folder", not "shared folder". In `handover.elsewhere*`: "{computer} opened your work, so this computer stopped saving to the synced folder. Changes here stay on this computer." | They opened the workspace, not "this shared folder" |
| `setup_step.ai.explanation`, `sources.first_read_noted`, `walkthrough.done.next`, `setaside.intro` | change | Keep "hand in" wherever the suggestion says "share" | **"Hand something in" is the main button.** Every explanation should use the same verb as that button. Take the rest of each suggestion |
| `walkthrough.why.people` | change | "…so the assistant can say who owns each to-do. …" | The product's word is "to-do", not "task" |
| `walkthrough.why.done` | change | "Here's what you set up and what you skipped. On Today, one line starts the assistant; nothing is spent until you press Start on it." | The suggestion said "Choose Start to see the first task on Today", but the button here is "Go to Today" |
| `setaside.confirm` / `confirm_all` | change | "Keep it set aside" / "Keep them all set aside" | It confirms the sorting; "Set aside this message" sounds like a new action |
| `today.plugins.waiting`, `waiting_until`, `until` | **reject** | Keep "Waiting: {why} · until {until}" | These lines describe a state, not an action. "Wait until {why}" breaks when {why} is a reason ("Wait until the account is paused"). Rule 7.6 asks waiting lines to say why and until when; they already do |
| `ai_accounts.ago.now` | reject | Keep "just now" | It's the standard phrase |
| `*just_this_time*` (8 rows) | reject | Keep "Just this time" | It's a natural, friendly idiom, not dismissive. Changing 8 strings buys nothing |
| `walkthrough.mail.connect` | change | "Install and connect {service}" | "This tool" is vague; name the service |

**Accepted as suggested** (the rest of the review, including the following):
- the "packs → add-ons" rows
- `addons.no_catalog` and `addons.no_packs_failed`
- `sign_in.default_unusable` and `sign_in.missing`
- `settings.intro` and `secret.type_hint`
- `sources.field.author_hint` and `dataform.*`
- `walkthrough.why.you`, `walkthrough.why.mail` and `walkthrough.why.backup`
- the walkthrough restart, manual and sorting hints
- `rules_review.intro`
- `queue.extractor.sub`, `queue.account_check.*` and `queue.borrow.*`
- `ai_add.over`, `note.hint` and `learned.discard_label`
- `walkthrough.mail.restart`
- `welcome.ai.command_hint`
- `nav.records`: no change (already "Saved items")

## 3. Three notes from the end of the review

1. **One word for one thing:** agreed. "Connections" applies to the area only; "source" keeps its evidence meaning.
2. **"Model":** keep it (see above).
3. **Developer screens may keep technical words:** agreed, provided they sit behind "Advanced" or "For developers" and are
   never on the setup path (N5).

## 4. `first-run-coverage-wording.md`

No comments are needed this round. I'll look at it when phase S builds it.
