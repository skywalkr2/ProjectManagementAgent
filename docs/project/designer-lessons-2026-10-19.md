# The functional designer's lessons from running (2026-10-19, evening)

As received. What they change is recorded in `docs/decisions.md` (2026-10-19, "the designer's evening lessons"), design
6.34 (stance), 6.16 (which sign-in an agent runs as), 6.22 (a rejected ask is dropped) and 6.19 (adding from a link), and
the roadmap batches S1-2, S1-3, B-6a and C4. The deployment they describe is the designer's own; names are left out.

Four lessons from today. The first two are holes in the plan as it stands this evening. Most important first.

## 1. Who the person is to each other person decides what the assistant may ask them. Nothing in the plan holds it.

In our deployment the person is a project manager, and the people they work with include other teams' architects. The
assistant filed questions quizzing an architect's design (field mappings, an eligibility rule, a timeout, which team
makes a call), asked her to change the sample data on her own page, and asked for next steps the record already held.
The person's replies: "it's not my job to tell the architects how to do their jobs" and "we are project management, not
architect boss". Every question was polite and accurate; each was the wrong thing for *this* person to send *that*
person.

That is a rule for this person, not for the product. Another user might be the architects' manager, want exactly those
design questions, and not care about dates at all.

*The hole:*
- The plan has a role per project (run, design, watch), and the scope resolver, the part that decides what is in scope,
  is in phase E, after the packs.
- From S1, though, the assistant drafts follow-ups and replies to people. People memory (S3) records how they like to be
  reached, but not who they are to the person.

*Rules:*
- A stance per person, as well as a role per project: "I manage them", "I work alongside them", "I report to them", "I
  only watch". Personal life needs the same, with different words (a client, a family member).
- The stance gates what may be drafted to that person. You may ask someone you manage for design detail and chase their
  dates. Someone you work alongside gets only an apparent big mistake (a contradiction with a recorded decision or fact,
  with links to both sides) and nothing a standing rule already answers. Someone you report to gets no chasing at all.
- What the person tracks is a choice too: delivery dates, design quality, decisions, or a mix. Our person tracks dates
  and never design; the architects' manager would be the reverse.
- The default for a new person is "work alongside", because quizzing someone you don't manage costs more than a missed
  question.
- Replies like the two above become a proposed stance, tied to that person or their role, for the person to keep. It's
  probably the most common correction a steward will get.
- Bring a minimal stance forward to S1 or S2: the field, the default and the gate on drafts and questions. The full
  resolver can stay in E.

## 2. Show which sign-in each command-line AI tool is actually using.

Our main runner, a command-line agent, was never signed in on its own, so it silently borrowed another tool's stored
sign-in: an old, abandoned personal account. For ten days every run used that account's small allowance, and work
material went through a personal plan with its own data settings, not the organization's. We found it only when the
allowance ran out and the "quota exceeded" made no sense against the organization's large allowance.

*The hole:* the account check proves a tier can run. It doesn't say *as whom*.

*Rules:*
- The account check reports the identity each tool runs as, read from the tool itself (its sign-in status or its log),
  and Settings shows it next to the account.
- A change of identity between runs is a line for the person ("the agent now runs as <other account>"). So is an
  identity that doesn't match the area's data level: a personal account reading a work area.
- This sits with R14 (work mail in a personal tool): the same leak in the other direction.

## 3. Feedback that says "don't ask" means drop, not reword.

When the person said a question shouldn't be asked, the assistant's first handling reworded two of them into politer
versions of the same ask. One became "are the values synthetic?" instead of "replace the values". And where the person
said "check the ticket first", it rewrote the question instead of checking.

*Rules:*
- A correction whose words reject the ask ("not my job", "why are we asking this?") ends as a drop with the person's
  reason.
- "Check X first" means check it in that run and close the question if X answers it. A reword is right only when the
  person objects to the wording, not to the asking.
- Add a learning pair for each.

## 4. Adding a record from a system of record fills it from that record first.

The person said "track this tool as a project, from this epic". The assistant added the project as "not started", with
one line of notes. The epic had been done for seven months, with its production release accepted. It never looked the
epic up.

*Rules:*
- "Add from <link>" reads the link before adding: its status, what shipped, and its dates.
- Something the source says is finished isn't new work: it's added with the facts, and the person is asked whether to
  mark it complete.
- An unknown status is unknown, never "not started".
