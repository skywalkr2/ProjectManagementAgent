# Round 3 prompts for the outside helper (2026-10-21)

Two self-contained prompts. Each can be pasted as it is. Their answers are checked by running every line through the
app's own rules (`engine/due_phrases.py` and `engine/repeat_phrases.py`): each disagreement is either a bug, a phrase
the rules should learn, or a case the rules rightly leave to the person, and the main session decides which.

---

## Prompt D: 80 deadline phrases and what a person means by them

An assistant reads promises in email ("I'll send it by Friday") and turns the deadline words into a date. When the
words could mean two dates, it must not pick one silently: it marks the date "check this". When the deadline depends on
something happening ("once the keys arrive"), there is no date at all. Write the test cases that check this.

**Write one YAML file, `due-phrases-01.yaml`**, a list of 80 entries in one code block:

```yaml
- phrase: by Friday
  received: '2026-11-04T09:30'
  received_day: Wednesday
  zone: America/Chicago
  meaning: date
  start: '2026-11-06'
  end: '2026-11-06'
  time: null
  exact: true
  why: The next Friday after a Wednesday; nobody would read it as a week later.
- phrase: early next week
  received: '2026-11-05T16:00'
  received_day: Thursday
  zone: America/New_York
  meaning: range
  start: '2026-11-09'
  end: '2026-11-11'
  time: null
  exact: false
  why: Monday to Wednesday of the following week; due at the end of the range.
- phrase: once the keys arrive
  received: '2026-11-05T16:00'
  received_day: Thursday
  zone: America/New_York
  meaning: condition
  start: null
  end: null
  time: null
  exact: false
  why: Depends on an event, not a date.
```

**Fields:** `received` is when the message was sent, in `zone`, the sender's time zone. `received_day` is that date's
weekday; check it against a calendar. `meaning` is `date` (one day), `range` (a span, due at its end), `condition`
(waits for something to happen) or `unclear` (no reasonable reader could name a date: "soon", "when I can"). `start` and
`end` are the first and last day (equal for one day; both `null` for `condition` and `unclear`). `time` is `HH:MM` in
`zone` when the words give one ("by 3pm"), else `null`. `exact` is `false` when a reasonable reader could pick a
different date ("next Friday" said on a Wednesday), `true` when nobody would. `why` is one short sentence.

**Cover, about ten each:**
- weekdays: "by Friday", "this Friday", "next Friday", "Fri", said on different days, including on the Friday itself;
- relative: "tomorrow" (also sent at 11:50 pm), "in two weeks", "in a couple of days", "end of day", "first thing
  Monday", "COB Thursday";
- calendar spans: "end of the week", "end of the month", "end of next month", "mid-November", "later this week", "the
  week of the 16th", "by the end of Q4";
- written dates: "11/6", "Nov 6", "the 14th" (also said on the 20th), "January 5" said in December, "6 November";
- times and zones: "by 3pm", "by noon tomorrow", "by 5pm ET" sent from another zone;
- holidays and seasons: "before Thanksgiving", "after the holidays", "over the weekend", "this spring";
- conditions: "once the keys arrive", "after you send the files", "when the budget is approved";
- vague: "soon", "ASAP", "when I can", "shortly", "in a bit".

**Rules:** American English, dates written month/day. Received dates in November and December 2026 and January 2027.
Vary the time zones (US and others). Use only the fields shown. At the end, list every phrase where you think people
would disagree about the date, and what each side would say.

---

## Prompt E: 60 ways people say something repeats

The same assistant keeps repeating to-dos ("pay rent on the 1st", "every other Tuesday"). The person types the repeat
in their own words; the assistant turns them into a standard repeat rule, or, when the words are unclear, says so and
asks, never guessing. Write the test cases that check this.

**Write one YAML file, `repeat-phrases-01.yaml`**, a list of 60 entries in one code block:

```yaml
- phrase: every other Tuesday
  start: '2026-11-03'
  start_day: Tuesday
  rule: FREQ=WEEKLY;INTERVAL=2;BYDAY=TU
  plain: Every two weeks on Tuesday
  next_three: ['2026-11-03', '2026-11-17', '2026-12-01']
- phrase: on the 31st
  start: '2026-10-31'
  start_day: Saturday
  rule: FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1
  plain: Monthly on the 31st, or the month's last day when it is shorter
  next_three: ['2026-10-31', '2026-11-30', '2026-12-31']
- phrase: biweekly
  start: '2026-11-02'
  start_day: Monday
  rule: unclear
  plain: null
  next_three: []
  why: Some people mean every two weeks, others twice a week.
```

**Fields:** `start` is the first time it happens (a date that fits the rule; check its weekday on a calendar). `rule` is
an iCalendar RRULE value (RFC 5545, without `DTSTART`), or `unclear` with a `why`. A day past the 28th falls on the
month's last day in shorter months, written as in the example, never skipping a month. `plain` says the rule back in
everyday words. `next_three` is the first three dates, starting at `start`.

**Cover, about ten each:**
- daily and weekdays: "every day", "every weekday", "weekdays except Friday", "every 3 days", "Mondays and Thursdays";
- weekly: "every Tuesday", "every other week on Monday", "every 3 weeks", "weekly on Fri";
- monthly by day: "on the 1st", "the 1st and 15th", "every month on the 30th", "every 3 months on the 15th", "quarterly";
- monthly by weekday: "the first Monday of each month", "the last Friday of the month", "the second and fourth
  Tuesday", "the last weekday of the month";
- yearly: "every year on March 3", "annually", "every February 29", "each spring";
- unclear: "biweekly", "bimonthly", "every couple of weeks", "now and then", "a few times a month", "regularly".

**Rules:** American English. Starts in November and December 2026. Mix home and work (rent, a standup, a school
pickup, watering plants, a quarterly report). At the end, list any phrase where you think people would disagree about
the rule, and what each side would say.
