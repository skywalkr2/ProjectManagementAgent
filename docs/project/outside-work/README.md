# Work for an outside helper

Self-contained jobs the owner can hand to an outside assistant (a chat model with or without access to this
repository). Each brief says what to produce, in which format and where, and how the main session checks it. Nothing an
outside helper writes lands without that check: the self-check's specificity scan, the evaluation harness's stub run
where a brief makes cases, and a read by the main session.

Rules for every brief:
- **Fictional only.** Invented people, companies and places; addresses at `example.com`. No real names, products,
  brands, systems or URLs, and nothing from anyone's real mail.
- **New files only,** in the folder the brief names. Never edit an existing file.
- **Work on a branch of your own,** named `outside/<brief>` (for example `outside/o1-promise-threads`), from
  `claude/tender-tesla-16a8ob`. Without repository access, return the files in the reply and the owner passes them on.
- **Say what you were unsure of** at the end of the reply, rather than guessing quietly.
- American English, plain words.

| Brief | What | Size | Checked by |
|---|---|---|---|
| [O1](o1-promise-threads.md) | 30 fictional mail threads where a promise ends, as evaluation cases | about a day | the stub run and a read |
| [O2](o2-life-scenarios.md) | 15 scenarios for the daily steward's next features (bills, bookings, reminders, the morning brief) | half a day | a read |
| [O3](o3-mail-signin-research.md) | Research memo: mail sign-in rules at Google and Microsoft, with sources | half a day | each claim's source |
| [O4](o4-wording-review.md) | Plain-language review of the app's on-screen wording | half a day | a read |
| [O5](o5-steward-design-review.md) | Second-opinion review of the daily steward's design | half a day | a read |
