# Wording for the first run's coverage (2026-10-21)

For the S1-3 item "first-run coverage" (`docs/project/roadmap-to-1.0.md`, from the design review in
`docs/project/reviews/steward-design-review-2026-10.md`): a person can see a credible first result and wrongly believe
the assistant checked everything. Drafted by the outside helper (round 2, prompt C), checked and corrected by the main
session. These are the starting words for the wording sheet when the item is built; the UI/UX reviewer has the last say.

Placeholders: `{assistant}` the assistant's name, `{account}` the mail account, `{ai_account}` the AI account the person
chose, `{folders}` the folders read, `{folder}` one folder, `{from_date}` the first day read.

| Where | Words | Action |
| --- | --- | --- |
| Before Start | {assistant} reads {folders} in {account} from {from_date}. Only the text it needs goes to {ai_account}. Older mail and other folders aren't read. | Start |
| After the first run, everything read | {assistant} read {folders} in {account}, from {from_date} through today. | — |
| After the first run, sent mail not included | Promises you made in your sent mail aren't here yet: {assistant} hasn't read it. Add your sent mail to include them. | Add sent mail |
| After the first run, a folder couldn't be read | {assistant} couldn't read {folder} in {account}, so promises there are missing. Try again, or remove {folder} from what's read. | Try again |
| The first promise list's heading | Promises found in {folders} since {from_date} | — |

## What changed from the helper's picks, and why

- **The assistant is the one reading.** The helper's "Read {folders}…" was addressed to the person but described the
  assistant's work, so it could be taken as an instruction. The app speaks of the assistant by name ("{assistant}
  reads…"), almost never "we".
- **The assistant isn't the AI account.** The helper's "your chosen AI account, {assistant}" made them one thing; the
  AI account has its own placeholder.
- **One folder is `{folder}`.** The line about a folder that couldn't be read is about one folder.
- **"Sent mail", not "Sent".** The sent folder's name differs between mail services.
- **Kept as the helper wrote it:** the heading's "found", which doesn't claim every promise was found, and "through
  today", which gives the read an end.

## The helper's other options

Kept for the reviewer. Before Start: "Read {folders} in {account} from {from_date}. Send only needed text to
{assistant}. Sent is included only if listed; other folders and older mail stay unread." Everything read: "This first
read covered {folders} in {account}, from {from_date} through today." Sent not included: "We can't see promises you
made in Sent mail yet. Add the Sent folder to include them." Heading: "Promises from {folders}, starting {from_date}".
