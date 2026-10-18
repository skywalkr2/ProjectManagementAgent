# Reminder wording

The wording for phase S1's reminders, chosen from options drafted with an outside assistant (2026-10-18). These become
wording-sheet entries when reminders are built; nothing here is in code. `{task}` is the to-do's own label, which
already starts with what the person does ("Send Oren the estimate"), so lines put the label first and the timing
after it, never "{task} is due". `{assistant}` and `{app}` are the configured names (Reginald and Thimbleby by
default). Every resolved time is shown in the person's time zone.

## On Today

| Where | Wording |
| --- | --- |
| A reminder | `{task} · due now` |
| A late reminder (came due while the computer slept) | `{task} · late: due {due_time}, while this computer was asleep` |

## The snooze menu

Each choice shows the time it resolves to, so "later today" is never a guess (the resolved times come from
`engine/reminders.py`):

- `In 1 hour · {one_hour_time}`
- `Later today · {later_today_time}`
- `This evening · {evening_time}`
- `Tomorrow morning · {tomorrow_morning_time}`
- `Next week · {next_week_date_and_time}`
- `Pick a time…`

A choice that has no time today (later today after working hours) is left out of the menu, not shown greyed.

## The quiet-hours digest

- Title: `Saved during quiet hours`
- Each line: `{task} · was due {due_date_and_time}`

No introduction line; the title says what the list is.

## In the person's own calendar

- Alarm title: `Reminder: {task}`

The calendar shows it outside the app, so "Reminder:" says where it came from.

## The reminder email

- Subject: `Reminder: {task}`
- Body:

  ```
  Due {due_date_and_time}: {task}

  Open {app} to mark it done or pick another time.

  {assistant}
  Sent automatically. No reply needed.
  ```

The plainer of the two drafts ("A small nudge" was dropped as filler). The email carries `Auto-Submitted:
auto-generated` (`engine/reminder_mail.py`), so the mailbox reader never acts on it.
