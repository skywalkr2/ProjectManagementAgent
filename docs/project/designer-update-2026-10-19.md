# Update for the functional designer (2026-10-19)

Since your answers of 2026-10-15. Part 1 is what changed; Part 2 is the questions that need your judgment. Each question
can be answered on its own, says what the app does today, and gives the default the build follows if you agree.

## Part 1: what changed

**1. A new direction: a daily assistant, not only project support.** On 2026-10-16 and 17 the owner decided the product
becomes **Thimbleby**, a daily assistant for anyone juggling work. The assistant inside it is called **Reginald** by
default, and the person can rename it. The audience is independent professionals juggling clients and personal life.
Project management, writing and publishing become packs on top of the core. The new design section is "the daily
steward" (6.32). Its centre is **dependable memory for commitments**: promises both ways (what the person said they'd do,
and what others said they'd do for them), each found with its evidence, and each ending proposed the same way (done,
date changed, called off, partly delivered, answered without an answer), never closed silently. Around that:
- reminders and snooze;
- a morning brief (changed overnight, at risk today, needs your yes), an evening wrap-up and a Monday briefing;
- replies owed, with drafts in the person's voice;
- meeting prep and capture;
- people memory;
- dates in documents and bills (reminders only, no bank connection);
- areas of life, each with its own data level;
- capture from anywhere;
- an attention budget.

**2. The order of work.** Phase B (finish the screens), phase S (the daily steward, promises first), phase I (Windows and
macOS installers, the name and icons), then phase C (the packs, starting with one plugin API release). Until phase I, the
code and documents still say PM Cockpit.

**3. Sending, brought forward.** Acting in the person's mail and calendar after their yes on the exact content (reply,
forward, archive, label; create, move or answer an event) moved from phase C to phase S (sub-phase S1b), because a daily
assistant that can only copy text isn't one. Nothing runs without the person's yes on that exact act. Not built yet.

**4. Building blocks for phase S, built as rules first.** Each answers yes, no or unknown and is never confidently wrong
on a labeled set. Unknown goes to the AI reading step. They are tested but **not yet connected** to the app:
- reply splitting (new text, quoted history, signatures; checked against 50 hard emails);
- replies owed;
- automatic-mail detection;
- mail threads;
- due phrases;
- dates in documents;
- repeat phrases ("every second Tuesday");
- reminders and snooze times (clocks changing, a computer asleep);
- a capacity check of the day;
- clashes and free slots;
- bookings from confirmation mail;
- bill dates;
- what changed in an invitation;
- signature facts;
- a voice profile;
- the reminder mail.

Connecting them is phase S's work.

**5. Four outside reviews (2026-10-18).** Three from one outside tool and one from another. They praised the trust design
and found real defects. Every defect was reproduced with a failing test and **fixed overnight (2026-10-19)**:
- **Spending:** when the first AI account failed, a backup or a stronger tier could run at a higher cost, or with no
  known price, without the person's go. Now every account a run reaches is held to what the person allowed.
- **Saved passwords and keys:** a refused settings save could still overwrite the password in use, and the cost
  estimate for changing an AI account wrote the key. Now a new value is always kept beside the old one, so a refused
  save changes nothing and Undo brings back the one that worked.
- **Undo:** undoing an action with no owner left its "Pick an owner" question behind, and answering it crashed.
  Undoing a later hold also removed an owner picked earlier. Both are fixed.
- **Two settings forms open at once:** saving the older one silently overwrote the newer change. Now it's refused and
  what was typed stays.
- **Downloads** of files with non-Latin names failed. **Python 3.14** broke a plugin safety check. Both are fixed.

**6. The owner's decisions (2026-10-18).**
- Every defect is fixed before anyone outside tests the app.
- Testers use the mail and calendar add-on, since a test without real mail isn't much of a test. It becomes optional at
  1.0.
- There is no fixed tester date: the tester group follows the gates.
- The product's public website (a coming-soon page today) will be fed what to say by this plan, and later kept in step
  with releases.

**7. Changes the reviews proposed and the owner hasn't decided yet.** These are in Part 2 for your view:
- the tester group as a roadmap milestone with numbers;
- a week on the owner's own mail before phase S goes further;
- numbers for "dependable";
- holding the broader steward features behind a dependable promise workflow;
- a risks register rewritten for the new product;
- a policy for older mail at first run;
- tests for approved sending against hostile input;
- the walkthrough reworked for the new audience;
- a coverage line on Today;
- a way to add a missed promise.

## Part 2: questions

**F1. Gate phase S on proof, not on modules?** Today phase S is a list of features, each "built" when its test passes.
The reviews say twelve tested-but-unconnected rule modules show what module-count exits produce. *Default if you
agree:* phase S gets an acceptance gate after its first sub-phase: the owner's own mailbox for one week, with the
promise workflow whole (found with evidence, on Today, ended, learned from), and a miss rate and false-alarm rate the
owner accepts, set before the week starts. The later sub-phases wait for it.

**F2. Hold the broader steward features behind that gate?** Today phase S plans everything in 6.32 in about six
sessions. *Default:* the brief, meeting prep, people memory, areas of life, capture from anywhere and the conversation
stay in the design and the roadmap, but start only after F1's gate passes. Reminders and replies owed stay in the first
slice because promises depend on them.

**F3. How do we measure "dependable"?** Today the Quality screen design names measures (promises found and kept, false
alerts, review time, follow-ups completed), but none is built and none has a number. Counting what the assistant finds
can't reveal what it missed. *Default:* for a bounded, consented sample of real inputs, someone independently lists the
commitments and how each ended. We then compare that list with the assistant's results:
- missed out of present;
- wrong ones out of proposed;
- wrong endings, especially unfinished work marked done;
- changed dates, cancellations, partial deliveries and owner changes handled correctly;
- review time;
- sources not read.

Results are counts with their denominators, by account and by kind of commitment. A held-out set isn't tuned against.
The owner sets the thresholds before the run.

**F4. A coverage line on Today.** Today, "nothing needs you" and "couldn't check" can look alike: a source that failed
shows as a problem in the side column, but an empty Today doesn't say what was read. *Default:* Today's header says what
was covered in one line: the sources read, when each was last read successfully, and any that weren't ("Read 3 sources,
last at 7:40; work mail couldn't be read since yesterday"). An empty Today with a source not read never says "nothing
needs you".

**F5. Adding a promise the assistant missed.** Promise records aren't built yet. Today the person can correct, drop or hold
an action the assistant found, but a missed one can only be added by typing a note, and a miss isn't counted anywhere. *Default:* a
"Missed one" action on any message or note opens a short form (who owes what to whom, by when), with the source's words
as evidence. It records a "missed" signal the learning loop uses, and the Quality screen counts misses.

**F6. Older mail at first run.** Today a new mailbox source reads recent mail only (a setting), plus an on-request "look
at the last day". Nothing says what Thimbleby takes responsibility for before that. *Default:* first run reads the last
14 days, and a promise whose thread already shows it answered or done isn't raised. Today says plainly that "promises
from before <date> weren't looked at". The person can ask for a longer look-back, which shows its cost first.

**F7. Tests for approved sending before S1b is accepted.** The sender isn't built. *Default:* S1b isn't accepted until
named tests pass:
- the exact approved content and recipients go out;
- an approval goes stale when the draft or recipients change;
- a timeout, retry or restart never sends twice;
- an uncertain result from the service shows as uncertain, never as sent;
- a withdrawn sign-in stops the act plainly;
- content from outside that tries to change a recipient or add an act is refused.

Plugins stay trusted code: the app doesn't claim to sandbox an installed add-on.

**F8. The tester milestone's exit.** The owner decided testers wait for every defect fix. Today the roadmap has no
measured exit for the tester group. *Default:* two weeks with a feedback form. The exit is F3's measures against the
owner's thresholds, plus whether testers spend less time checking the assistant by week two. Giving up their own backup
list isn't a requirement.

**F9. Today judged by the next action.** Today's design shows every line that needs the person, in priority order.
*Default:* Today's test in phase B and S is whether the top line is the next worthwhile action. A browser test on the
fictional workspaces checks the first line for each of a handful of set-ups, and the attention budget (6.32) keeps the
rest below a cap.

**F10. The risks register.** Today it still describes the earlier product (the launch slice, the publishing pack) and
relied on the go/no-go date and freeze, which are set aside. The overnight docs pass replaces those mitigations and adds
"a memory product that silently drops commitments is worse than paper". *Default:* a full rewrite for the steward
product before phase S starts, adding three more risks:
- the cost of a daily driver running many more AI calls;
- life data kept on one laptop;
- "full featured" pressure against scope.

**F11. Bundling the mail and calendar add-on for testers.** The owner wants testers to have it with no separate install.
*Default:* the add-on stays a plugin (provider code stays out of the core). The installer offers it during setup with
Skip. Connecting an account is the only thing that starts reading, and the core stays testable without it. How it ships
(inside the installer or from the catalog during setup) is decided in phase I.

**F12. What a refused form save does next.** Overnight, a stale settings form became a refusal that keeps what was
typed. After the refusal, the form takes the current settings for the next save, but fields the person didn't touch
still hold the values from when it opened, so a second Save could write an old value back. *Default:* after a refusal,
untouched fields are refreshed from what is saved now, and fields the person changed are kept and marked.

**F13. Old kept passwords.** Overnight, a changed password or key is kept beside the old one so Undo works. The old
files stay in the private keys folder. *Default:* an old kept secret that no setting refers to is removed after 30 days
(a setting), and removing a source or account removes its kept secrets at once, with a line saying so.

**F14. What a go on spending covers.** Overnight, every account a request reaches was held to the amount the person
allowed, per call. But the estimate the person says yes to is for one call, and a request can make several: a fix round
when checks fail, then one on a stronger tier (up to four calls with today's settings), plus searches. The daily and
per-kind budgets still stop runs once they're reached. *Default:* the estimate shown is for the whole request, as a
range ("about $0.04, up to $0.16 if it needs another try"). The request's calls together stop at the upper figure, and
a further call that would pass it waits for another go.
