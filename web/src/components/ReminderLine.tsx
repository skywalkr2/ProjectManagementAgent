// Reminders on Today and on the to-do list (design 6.32, 7.7): the line for a reminder that has reached the person, with
// Done first and Snooze in its menu (each choice shows the time it moves to), the one line for reminders that waited for
// quiet hours to end, and the browser notification for a line that appears while the app is open. A snooze or a time the
// person picks is their own edit of the reminder, with Undo.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, wallTime } from "../lib/dates";
import { notifyState, showNotification } from "../lib/notify";
import { useWords } from "../lib/wording";
import { NoteBox, useNoted } from "./NoteBox";
import { RowMenu, type MenuAction } from "./RowMenu";
import type { MenuGroup } from "../ui/MenuButton";

type Line = S["QueueLineView"];
type Choice = S["SnoozeChoiceView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** A moment as a day and a time on the person's own clock, as the server wrote it: "Mon, Oct 19, 9:00 PM". */
export const dateAndTime = (iso: string) => `${day(iso)}, ${wallTime(iso)}`;

/** The words of a reminder line, `{task} · due now`. A late one says when it was due: that it came due while the computer was
 * away only when the app knows that (`asleep`), otherwise only that it is overdue. */
export function reminderTitle(line: Line, t: T): string {
  const task = line.text ?? "";
  if (!line.late) return t("queue.reminder.due", { task });
  return t(line.asleep ? "queue.reminder.late" : "queue.reminder.overdue", { task, due_time: line.at ? wallTime(line.at) : "" });
}

/** The title of the line that lists reminders that waited. */
export const digestTitle = (line: Line, t: T): string => t(line.late ? (line.asleep ? "queue.reminder.missed" : "queue.reminder.missed_overdue") : "queue.reminder.digest");

/** One item of that list. */
export const digestLine = (item: S["ReminderItemView"], t: T): string => t("queue.reminder.digest_line", { task: item.text, due_date_and_time: dateAndTime(item.at) });

/** A snooze choice as the menu words it, with the time it resolves to. */
export function snoozeLabel(choice: Choice, t: T): string {
  const time = wallTime(choice.at);
  switch (choice.choice) {
    case "in 1 hour":
      return t("queue.snooze.in_hour", { one_hour_time: time });
    case "later today":
      return t("queue.snooze.later_today", { later_today_time: time });
    case "this evening":
      return t("queue.snooze.this_evening", { evening_time: time });
    case "tomorrow morning":
      return t("queue.snooze.tomorrow_morning", { tomorrow_morning_time: time });
    default:
      return t("queue.snooze.next_week", { next_week_date_and_time: dateAndTime(choice.at) });
  }
}

export interface ReminderChoices {
  /** Done, for a row's one primary button. */
  done: () => void;
  /** "Add a note": the box it opens is in `form`, and sends the note with Done. */
  note: MenuAction;
  /** The titled group of snooze choices, with Pick a time. */
  groups: MenuGroup[];
  /** The form Pick a time opened, shown under the row. */
  form: ReactNode;
}

/** What a person does about one reminder: mark it done, snooze it to a choice, or pick a time. `onClosed` runs when the form
 * goes, so the row can take the cursor back. */
export function useReminderChoices(action: string, snoozes: Choice[], onClosed?: () => void): ReminderChoices {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const [picking, setPicking] = useState(false);
  const [noting, setNoting] = useState(false);
  const doneWith = (note?: string) =>
    act(
      () => api.actionStatus(action, "done", note),
      (result) => ({ message: noted(t("toast.action_done"), result.request), undo: () => api.actionStatus(action, "open") }),
    );
  const done = () => void doneWith();
  const snooze = (body: S["ReminderIn"], when: string) =>
    act(
      () => api.remind(action, body),
      (result) => ({ message: t("reminder.snoozed", { when }), undo: () => api.undo(result.changeset) }),
    );
  const close = () => {
    setPicking(false);
    onClosed?.();
  };
  const entries: MenuAction[] = [
    ...snoozes.map((choice) => ({ id: `snooze-${choice.choice}`, label: snoozeLabel(choice, t), run: () => void snooze({ choice: choice.choice }, choice.choice === "next week" ? dateAndTime(choice.at) : wallTime(choice.at)) })),
    { id: "snooze-pick", label: t("queue.snooze.pick"), run: () => setPicking(true) },
  ];
  const form = (
    <>
      {picking && (
        <PickTime
          onSave={(at) => {
            void act(
              () => api.remind(action, { at }),
              (result) => ({ message: t("reminder.snoozed", { when: dateAndTime(at) }), undo: () => api.undo(result.changeset) }),
            ).then((ok) => ok && close());
          }}
          onCancel={close}
        />
      )}
      {noting && (
        <NoteBox
          sends={[{ label: t("queue.reminder.done"), run: doneWith }]}
          onClose={() => {
            setNoting(false);
            onClosed?.();
          }}
        />
      )}
    </>
  );
  const note: MenuAction = { id: "note", label: t("note.add"), run: () => setNoting(true) };
  return { done, note, groups: [{ id: "snooze", title: t("queue.reminder.snooze"), entries: entries }], form };
}

/** A box to pick a day and time, with the cursor in it. A time without a zone is on the person's own clock. */
export function PickTime(props: { value?: string; onSave: (at: string) => void; onCancel: () => void }) {
  const { t } = useWords();
  const id = useId();
  const [value, setValue] = useState(props.value ?? "");
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (value) props.onSave(value);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("reminder.pick_label")}
      </label>
      <input id={id} type="datetime-local" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!value}>
          {t("reminder.save")}
        </button>
      </div>
    </form>
  );
}

/** The reminders that waited, each with its words, when it was due and its own Done and Snooze. */
export function ReminderItems(props: { line: Line }) {
  return (
    <ul className="reminder-items">
      {(props.line.reminders ?? []).map((item) => (
        <ReminderItem key={item.action} item={item} snoozes={props.line.snoozes ?? []} />
      ))}
    </ul>
  );
}

function ReminderItem(props: { item: S["ReminderItemView"]; snoozes: Choice[] }) {
  const { t } = useWords();
  const ref = useRef<HTMLLIElement>(null);
  const choices = useReminderChoices(props.item.action, props.snoozes, () => ref.current?.focus());
  const text = digestLine(props.item, t);
  return (
    <li ref={ref} tabIndex={-1} className="reminder-item" data-reminder={props.item.action}>
      <span>{text}</span>
      <button type="button" className="btn small primary" aria-label={t("today.todo.done_named", { text: props.item.text })} onClick={choices.done}>
        {t("queue.reminder.done")}
      </button>
      <RowMenu label={text} actions={[choices.note]} groups={choices.groups} />
      {choices.form}
    </li>
  );
}

/** Shows one browser notification for each reminder line that appears while the app is open, when the person has allowed
 * them. What is there when the screen first loads is not announced: the person is looking at it. */
export function useReminderNotices(lines: Line[] | undefined) {
  const { t } = useWords();
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!lines) return;
    const now = lines.filter((l) => l.kind === "reminder" || l.kind === "reminder_digest");
    const before = seen.current;
    seen.current = new Set(now.map((l) => l.key));
    if (before === null) return;
    for (const line of now) {
      if (before.has(line.key) || notifyState() !== "granted") continue;
      if (line.kind === "reminder") showNotification(reminderTitle(line, t), undefined, line.key);
      else showNotification(digestTitle(line, t), (line.reminders ?? []).map((i) => digestLine(i, t)).join("\n"), line.key);
    }
    // Only when the lines change; the wording sheet doesn't.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines]);
}

/** The to-do row's entries for its own reminder: set one (a day and a time), change it, or remove it; each with Undo. */
export function useRemindMe(action: string, remindAt: string | null | undefined, onClosed?: () => void): { entries: MenuAction[]; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [picking, setPicking] = useState(false);
  const close = () => {
    setPicking(false);
    onClosed?.();
  };
  const entries: MenuAction[] = [{ id: "remind-set", label: t(remindAt ? "reminder.menu_change" : "reminder.menu_set"), run: () => setPicking(true) }];
  if (remindAt) {
    entries.push({
      id: "remind-clear",
      label: t("reminder.menu_clear"),
      run: () =>
        void act(
          () => api.remind(action, {}),
          (result) => ({ message: t("reminder.cleared"), undo: () => api.undo(result.changeset) }),
        ),
    });
  }
  const form = picking ? (
    <PickTime
      value={remindAt ? remindAt.slice(0, 16) : undefined}
      onSave={(at) => {
        void act(
          () => api.remind(action, { at }),
          (result) => ({ message: t("reminder.set", { when: dateAndTime(at) }), undo: () => api.undo(result.changeset) }),
        ).then((ok) => ok && close());
      }}
      onCancel={close}
    />
  ) : null;
  return { entries, form };
}
