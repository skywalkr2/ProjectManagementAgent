# Questions for the morning (2026-10-23)

Collected while building past the owner's evening (open promise P31). Each says who it is for, what it decides, what
the build does meanwhile, and whether it blocks anything. Answered questions move into `docs/decisions.md` and leave
this file.

## For the functional designer

## For the owner

1. **Why your account answers corrections with nothing (pairs 23, 24, 25, `rejected-ask`).** With the exact learning
   packets, a low-cost model proposes the right lesson for 23, 24 and 25; your account proposed nothing. The report
   keeps each run's error, which the summary lines don't show. Please run this from `~/dev/thimbleby` and paste what it
   prints:

   ```
   uv run python -c "import json,os; r=json.load(open(os.path.expanduser('~/tonight-pairs.json')))['results']; [print(x['case'], '|', x['error'], '|', x['got']) for x in r if not x['passed']]"
   ```

   - Decides: whether the fix is in the app (a failed or unreadable learning answer) or in the instructions.
   - Meanwhile: the packet now says what a decline and a drop mean, and a correction saying something was missed can no
     longer be answered with nothing (it proposes the narrow lesson or asks you).
   - Blocks: nothing else.
