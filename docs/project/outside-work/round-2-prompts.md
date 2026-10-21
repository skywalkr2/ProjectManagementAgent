# Round 2 prompts for the outside helper (2026-10-21)

Three self-contained prompts. Each can be pasted as it is; nothing in them depends on reading the repository.

---

## Prompt A: 29 more promise threads (O1, continued)

You are writing test cases for an assistant that remembers promises made in email and notices when they end. Each
case is one YAML file: an open promise already on record (`given`), one new email arriving with the earlier thread
quoted below it (`pasted`), what the assistant must do (`expect`), what it must not do (`forbid`), and the ideal
answer (`stub_answer`).

**Write 29 files**, named `thread-t27-m<N>-<word>.yaml` to `thread-t55-m<N>-<word>.yaml` (`<N>` is the message's
number in its thread, `<word>` one word for the ending: `done`, `called-off`, `moved`, `part`, `no-answer`). Give each
file's YAML in its own code block, headed by its file name.

**The endings, and how many of each:**
- 4 kept, in other words ("it's attached", "went out this morning", "you should have it now"): `action.close`.
- 5 kept by someone else on the owner's behalf (a colleague sent it): `action.close`, nothing else.
- 5 called off or no longer needed: `action.drop` with a `reason`.
- 5 moved to a new date written in words ("let's say the 14th instead", "after the holidays"): `action.move` with
  the new `due_words`.
- 5 partly delivered, with what is left said: `action.part` with `delivered` and `left`.
- 5 **not** an ending: a thank-you, an "I'll look at it", a question back, a reply about something else.
  `action.news` with a short `text` saying what the reply did say, and `forbid` close, drop and move.

**People.** Use only these. PER-1 is Avery Lane (`avery.lane@example.com`), the person the assistant works for. The
others: PER-101 Mira Hale, PER-102 Tavish Reeve, PER-103 Nessa Ford, PER-104 Oren Pike, PER-105 Liora Marsh, PER-106
Ansel Wick, PER-107 Zella Brook, PER-108 Bram Foley, PER-109 Iona Crane, PER-110 Pella Dunn, PER-111 Varo Stone,
PER-112 Edda Moss, PER-113 Jori Frame, PER-114 Soren Lund, PER-115 Lena Ashby, PER-116 Dev Maran, PER-117 Tess Calder.
Each one's address is their first name in lower case at `example.com` (`mira@example.com`). About half the promises
should be owed by Avery (`owners: [{person: PER-1}]`) and half owed to Avery by someone else
(`owners: [{person: PER-10x}]`, `promised_to: [PER-1]`).

**Rules:**
- Every `evidence.quote` is words that appear exactly, character for character, in `pasted`.
- The open promise is always `id: ACT-101`, `basis: said`, with `due` (a date) and `due_words` (the words it was
  given in), as in the example.
- Dates in November and December 2026; `received` is on or after the dates in the thread.
- Invented companies, products and places only. Nothing real.
- Mix work and personal life (a client, a landlord, a school, a contractor, a friend), and vary the writing: short
  and long, formal and casual, a typo, a signature, a forwarded message, a reply above a long quote.
- Use only the fields shown in the examples below.

**Example (kept):**

```yaml
id: thread-t26-m2-done
title: 'Willow Ledger proposal (message m2): the promise is kept'
skills: [owners, dates, close-right-item, new-message-only]
received: '2026-11-16'
given_file: promise-people.yaml
given:
- kind: action
  id: ACT-101
  fields:
    text: Send Mira the revised Willow Ledger proposal
    owners:
    - person: PER-1
    promised_to: [PER-101]
    basis: said
    due: '2026-11-13'
    due_words: by Friday at noon
pasted: |-
  From: Avery Lane <avery.lane@example.com>
  To: Mira Hale <mira@example.com>
  Subject: Willow Ledger proposal

  Sent. The revised proposal is attached.

  --
  Avery

  Avery Lane <avery.lane@example.com> wrote:
  > I'll send Mira the revised Willow Ledger proposal by Friday at noon.
expect:
- op: action.close
  id: ACT-101
forbid:
- op: action.drop
  id: ACT-101
- op: action.add
stub_answer:
  summary: The promise is kept.
  ops:
  - op: action.close
    id: ACT-101
    evidence:
      quote: The revised proposal is attached
```

**The other endings' `expect`, `forbid` and `stub_answer`** (the rest of each file is shaped as above):

```yaml
# called off
expect:
- op: action.drop
  id: ACT-101
forbid:
- op: action.close
  id: ACT-101
- op: action.add
stub_answer:
  summary: The promise is called off.
  ops:
  - op: action.drop
    id: ACT-101
    reason: Nessa called off the launch and no longer needs the flyer
    evidence:
      quote: Please cancel the flyer; we don't need it
---
# moved
expect:
- op: action.move
  id: ACT-101
  due_words: Friday morning
forbid:
- op: action.close
  id: ACT-101
- op: action.add
stub_answer:
  summary: The date moves.
  ops:
  - op: action.move
    id: ACT-101
    due_words: Friday morning
    evidence:
      quote: I'll send the feedback Friday morning instead
---
# partly delivered
expect:
- op: action.part
  id: ACT-101
forbid:
- op: action.close
  id: ACT-101
- op: action.add
stub_answer:
  summary: Part of it arrives.
  ops:
  - op: action.part
    id: ACT-101
    delivered: The logo files
    left: Send Avery the usage guide
    evidence:
      quote: The logo files are attached. The usage guide isn't ready yet
---
# not an ending
expect:
- op: action.news
  id: ACT-101
forbid:
- op: action.close
  id: ACT-101
- op: action.drop
  id: ACT-101
- op: action.add
stub_answer:
  summary: The reply doesn't answer.
  ops:
  - op: action.news
    id: ACT-101
    text: Liora praised the layout but did not say whether the quote is approved
    evidence:
      quote: The layout looks lovely, Avery. Nice work
```

At the end, list anything you were unsure of.

---

## Prompt B: 20 messages that sound like promises but aren't

Same assistant: it records a promise when someone commits to doing something. The hard part is not recording things
that only **sound** like promises. Write 20 test cases where the new email must produce **no** promise.

**Cover, about three to four each:**
- Hedges and wishes: "I'll try to…", "hopefully by Friday", "we should catch up sometime".
- Automatic and marketing mail: "We'll send you a code", "Your order will ship in 3–5 days", an out-of-office reply
  ("I'll respond when I'm back on the 12th").
- Promises about the past or already done: "I sent it yesterday", "as I promised last week, here it is".
- Someone else's promise reported second-hand, with no one in the thread committing: "Mira said she'd look at it".
- Questions and offers that wait for a yes: "Shall I send the draft?", "I can bring the chairs if you like".
- Conditional on something unknown with no commitment: "If the budget comes through, maybe we'll redo the site".

**File names:** `not-promise-01-<word>.yaml` to `not-promise-20-<word>.yaml`, each in its own code block headed by its
file name. **People:** the same list as prompt A (Avery Lane is PER-1, the person the assistant works for).

**Format** (no `given`; the assistant starts with no open promise):

```yaml
id: not-promise-01-hedge
title: 'A hedge is not a promise: "I''ll try to send it"'
skills: [owners, evidence]
received: '2026-11-04'
given_file: promise-people.yaml
pasted: |-
  From: Tavish Reeve <tavish@example.com>
  To: Avery Lane <avery.lane@example.com>
  Subject: Site photos

  I'll try to dig out the site photos at some point, but no promises — this week is chaos.
forbid:
- op: action.add
stub_answer:
  summary: No promise; Tavish only said he would try.
  ops: []
```

Rules as in prompt A: invented names, products and places only; vary the writing; list anything you were unsure of.

---

## Prompt C: Wording for the first run's coverage

The assistant's first run reads part of the person's mailbox: by default the last two weeks of the inbox, and the
sent folder only if the person added it. A design review found that a person can see a credible first result and
wrongly believe the assistant checked everything. Draft the words the app shows, in plain language for someone who is
not technical, in American English.

Write, for each, two or three options of at most 25 words:
1. **Before Start:** what will be read (which account, which folders, from which date), what goes to the AI account
   they chose, and what won't be read.
2. **After the first run, everything read:** which folders and dates were read.
3. **After the first run, sent mail not included:** say plainly that promises the person made in their own sent mail
   can't be seen yet, and offer the one action that adds the sent folder.
4. **After the first run, a folder couldn't be read:** which one, that its promises are missing, and what to do.
5. **The first promise list's heading line**, saying what the list covers.

Rules: no technical words (no "IMAP", "OAuth", "sync", "source", "token", "workspace"); start any instruction with the
verb; never blame the person; no "simply" or "just". Use `{account}`, `{folders}`, `{from_date}` and `{assistant}`
for the parts that change. At the end, say which option you would pick for each and why.
