// Today's rail (design 7.7): top priorities, the week, the agenda, the person's own list and what came in, as panels sized to
// their content beside the queue (below it under 1024px, and on the phone each folded to one line). What needs the person is
// the queue, not the rail.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { addDays, day, localDate, time, wallTime, weekday, whenText as when } from "../lib/dates";
import { useSaid } from "../lib/repeat";
import { useSetAside } from "../lib/set-aside";
import { anyReading, failedReads, latestRead, readProblem } from "../lib/sources";
import { useWords } from "../lib/wording";
import { AgendaItems } from "./AgendaList";
import { useChangeThis } from "./ChangeThis";
import { LearnedLines } from "./Learned";
import { useDropAction } from "./DropAction";
import { HoldNote, useHold } from "./OnHold";
import { NoteBox, useNoted } from "./NoteBox";
import { OriginLink } from "./Origin";
import { dateAndTime, useRemindMe } from "./ReminderLine";
import { RowMenu } from "./RowMenu";
import { SafeLink } from "./SafeText";
import styles from "./Today.module.css";
import { recordView, viewHref, type View } from "../lib/views";
import { Button } from "../ui/Button";
import { useAddTodo } from "./AddTodo";
import { Drawer } from "../ui/Drawer";
import { Skeleton } from "../ui/Skeleton";
import { Empty, Failed, RailPanel } from "./RailPanel";
import { ThisWeekPanel } from "./ThisWeek";
import { TopPriorities } from "./TopPriorities";

type T = ReturnType<typeof useWords>["t"];

/** The current time, refreshed every minute, for the "now" line and for telling today's mail from older mail. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** The rail's panels: top priorities, the week, the agenda, the to-dos and what came in. `onAddSource` opens Sources with the add form open. */
export function TodayRail(props: { onView: (view: View) => void; onAddSource?: () => void }) {
  const { t } = useWords();
  const add = props.onAddSource ?? (() => props.onView("sources"));
  return (
    <div className={styles.rail} role="group" aria-label={t("today.rail.label")}>
      <TopPriorities onView={props.onView} />
      <ThisWeekPanel />
      <AgendaPanel onAddSource={add} />
      <TodoPanel />
      <ArrivedPanel onView={props.onView} onAddSource={add} />
    </div>
  );
}

/** What an empty card says about its sources: a button to connect one while none is set up or reading, otherwise when the
 * sources were last read, so an empty card is known to be up to date rather than unconnected. */
function useSourceState(
  onAdd: (() => void) | undefined,
  label: string,
  kind: "mail" | "calendar",
): { button?: { label: string; run: () => void }; note?: string; problems: string[] } {
  const { t, has } = useWords();
  const watch = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });
  if (!watch.data) return { problems: [] };
  if (!anyReading(watch.data)) return onAdd ? { button: { label, run: onAdd }, problems: [] } : { problems: [] };
  // A source that couldn't be read is said so, with why and what to do, and never leaves the card looking up to date.
  const problems = failedReads(watch.data, kind).map((source) => readProblem(source, t, has));
  if (problems.length > 0) return { problems };
  const last = latestRead(watch.data);
  return { note: last ? t("today.checked", { when: when(last) }) : t("today.not_checked"), problems };
}

/** What a source that couldn't be read says, one line each. */
function SourceProblems(props: { problems: string[] }) {
  if (props.problems.length === 0) return null;
  return (
    <ul className="plain-list" data-source-problems="">
      {props.problems.map((problem) => (
        <li key={problem} className="problem-note" role="alert">
          {problem}
        </li>
      ))}
    </ul>
  );
}

/** Source names are only worth showing when rows come from more than one source. */
function useSourceNames(sources: string[]): (id: string) => string {
  const watch = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });
  const many = new Set(sources).size > 1;
  const names = new Map((watch.data ?? []).map((s) => [s.id, s.label]));
  return (id) => (many ? (names.get(id) ?? "") : "");
}

// ---------------------------------------------------------------- Agenda

type Event = S["AgendaItemView"];

interface DayGroup {
  date: string;
  events: Event[];
}

/** Events by the days they fall on (today onward): the connected calendars' events with all-day ones first, then the
 * app's own entries. */
export function groupByDay(events: Event[], today: string): DayGroup[] {
  const days = new Map<string, Event[]>();
  for (const event of events) {
    for (const date of event.days) {
      if (date < today) continue;
      days.set(date, [...(days.get(date) ?? []), event]);
    }
  }
  return [...days.keys()]
    .sort()
    .map((date) => {
      const all = days.get(date)!;
      const connected = all.filter((e) => !e.own);
      return {
        date,
        events: [
          ...connected.filter((e) => e.all_day),
          ...connected.filter((e) => !e.all_day),
          ...all.filter((e) => e.own),
        ],
      };
    });
}

function whenText(event: Event, date: string, t: T): string {
  if (event.all_day) return t("today.agenda.all_day");
  const startDay = event.start.slice(0, 10);
  const endDay = event.end?.slice(0, 10);
  if (date > startDay) {
    return event.end && endDay === date ? t("today.agenda.until", { time: wallTime(event.end) }) : t("today.agenda.all_day");
  }
  return event.end && endDay === date
    ? t("today.agenda.range", { start: wallTime(event.start), end: wallTime(event.end) })
    : wallTime(event.start);
}

function AgendaPanel(props: { onAddSource?: () => void }) {
  const { t, tn } = useWords();
  const sourceState = useSourceState(props.onAddSource, t("today.agenda.connect"), "calendar");
  const agenda = useQuery({ queryKey: ["today", "agenda"], queryFn: api.agenda });
  const now = useNow();
  const today = localDate(now);
  const tomorrow = addDays(today, 1);
  const events = agenda.data ?? [];
  const sourceName = useSourceNames(events.filter((e) => !e.own).map((e) => e.source));
  const groups = groupByDay(events, today);
  const count = events.filter((e) => !e.cancelled && e.days.includes(today)).length;
  const dayLabel = (date: string) =>
    date === today ? t("today.agenda.today") : date === tomorrow ? t("today.agenda.tomorrow") : day(date);

  return (
    <RailPanel
      id="agenda"
      title={t("today.agenda.title")}
      count={agenda.data ? count : null}
      countText={tn("today.agenda.count", count)}
      summary={
        agenda.data
          ? count > 0
            ? tn("today.agenda.count", count)
            : groups.length === 0 && sourceState.problems.length > 0
              ? t("today.rail.not_read")
              : t("today.agenda.none_today")
          : ""
      }
      footer={<AddMeeting today={today} />}
    >
      {agenda.isPending ? (
        <Skeleton />
      ) : agenda.isError ? (
        <Failed text={t("today.agenda.load_failed")} retry={() => void agenda.refetch()} />
      ) : groups.length === 0 ? (
        sourceState.problems.length > 0 ? (
          <div className="tb-empty">
            <p>{t("today.agenda.not_read")}</p>
            <SourceProblems problems={sourceState.problems} />
          </div>
        ) : (
          <Empty inline text={t("today.agenda.empty")} note={sourceState.note} button={sourceState.button} />
        )
      ) : (
        groups.map((group) => {
          const headId = `agenda-day-${group.date}`;
          // On today's list, a line marks where the day has got to: after what has ended, before what is still to come.
          const ended = (e: Event) => new Date(e.end ?? e.start).getTime() <= now.getTime();
          const rows: Array<Event | "now"> = [...group.events];
          if (group.date === today) {
            const timed = group.events.filter((e) => !e.all_day && !e.own);
            if (timed.length > 0) {
              const upcoming = timed.find((e) => !ended(e));
              rows.splice(upcoming ? rows.indexOf(upcoming) : group.events.filter((e) => !e.own).length, 0, "now");
            }
          }
          return (
            <div key={group.date} className="tb-group">
              <h3 id={headId} className="tb-group-head">
                {dayLabel(group.date)}
              </h3>
              <ul className="tb-list" aria-labelledby={headId}>
                {rows.map((row, i) =>
                  row === "now" ? (
                    <li key="now" className="now-line">
                      <span>{t("today.agenda.now", { time: time(now) })}</span>
                    </li>
                  ) : (
                    <AgendaRow
                      key={`${row.snapshot}:${i}`}
                      event={row}
                      when={whenText(row, group.date, t)}
                      past={group.date === today && !row.all_day && !row.own && ended(row)}
                      source={sourceName(row.source)}
                    />
                  ),
                )}
              </ul>
            </div>
          );
        })
      )}
    </RailPanel>
  );
}

/** The button that adds a meeting to the agenda, opening a drawer with one line to fill: what, the day (today to begin with)
 * and the time (none: all day). The server makes the person's own calendar entry, or merges the meeting into one already
 * there and says so; Undo takes an added one back. The drawer closes once it is added; a refusal leaves what was typed. */
function AddMeeting(props: { today: string }) {
  const { t } = useWords();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        {t("meeting.open")}
      </Button>
      {open && <MeetingDrawer today={props.today} onClose={() => setOpen(false)} />}
    </>
  );
}

function MeetingDrawer(props: { today: string; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const base = useId();
  const [what, setWhat] = useState("");
  const [on, setOn] = useState("");
  const [at, setAt] = useState("");
  const day_ = on || props.today;
  const submit = async () => {
    const title = what.trim();
    if (!title || !day_) return;
    const done = await act(
      () => api.addMeeting({ what: title, day: day_, time: at || null }),
      (added) =>
        added.merged
          ? { message: t("meeting.merged", { what: added.merged_with ?? title }) }
          : { message: t("meeting.added", { what: title }), undo: () => api.undo(added.changeset ?? "") },
    );
    if (done) props.onClose();
  };
  return (
    <Drawer
      open
      title={t("meeting.title")}
      onClose={props.onClose}
      dirty={what.trim() !== ""}
      footer={
        <>
          <Button onClick={props.onClose}>{t("action.cancel")}</Button>
          <Button type="submit" form={`${base}-form`} variant="primary" disabled={!what.trim() || !day_}>
            {t("meeting.add")}
          </Button>
        </>
      }
    >
      <form
        id={`${base}-form`}
        className="meeting-line"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="field">
          <label htmlFor={`${base}-what`}>{t("meeting.what")}</label>
          <input id={`${base}-what`} type="text" value={what} onChange={(e) => setWhat(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${base}-day`}>{t("meeting.day")}</label>
          <input id={`${base}-day`} type="date" value={day_} onChange={(e) => setOn(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${base}-time`}>{t("meeting.time")}</label>
          <input id={`${base}-time`} type="time" value={at} onChange={(e) => setAt(e.target.value)} />
        </div>
        {/* The drawer's Add button is outside the form; this one lets Enter in a field add the meeting. */}
        <button type="submit" hidden tabIndex={-1} aria-hidden="true" />
      </form>
    </Drawer>
  );
}

function AgendaRow(props: { event: Event; when: string; past: boolean; source: string }) {
  const { t, tn } = useWords();
  const { event } = props;
  const row = useRef<HTMLLIElement>(null);
  const change = useChangeThis({ kind: "event", id: event.snapshot }, () => row.current?.focus());
  const act = useAct();
  // A plain entry that reads as a task is offered as a to-do, one click, with Undo.
  const offer = event.entry && event.todo_offer ? { entry: event.entry, text: event.todo_offer } : null;
  const addTodo = offer
    ? {
        id: "add-todo",
        label: t("today.agenda.add_todo"),
        icon: "plus" as const,
        run: () => void act(() => api.entryTodo(offer.entry), (made) => ({ message: t("today.agenda.todo_added", { what: offer.text }), undo: () => api.undo(made.changeset) })),
      }
    : null;
  const meta = [event.where, event.own ? t("today.agenda.own") : props.source].filter(Boolean).join(" · ");
  // A meeting of a series shows how many open items wait for it, linking to the series' page; with none, nothing is said.
  const open = event.series && (event.open_items ?? 0) > 0 ? event.open_items! : 0;
  return (
    <li className={props.past ? "tb-row past" : "tb-row"} ref={row} tabIndex={event.own ? -1 : undefined}>
      <span className="tb-when">{props.when}</span>
      <div className="tb-what">
        <div className="tb-title">
          {event.cancelled && <span className="pill k-risk">{t("today.agenda.called_off")}</span>}
          <span className={event.cancelled ? "struck" : undefined}>
            {event.link ? (
              <SafeLink label={event.title} url={event.link} />
            ) : event.entry ? (
              <a href={viewHref(recordView("event", event.entry))}>{event.title}</a>
            ) : (
              event.title
            )}
          </span>
          {open > 0 && event.series && (
            <>
              {" · "}
              <a href={viewHref(recordView("series", event.series))}>{tn("today.agenda.open", open)}</a>
            </>
          )}
        </div>
        {meta && <div className="tb-meta">{meta}</div>}
        <AgendaItems items={event.agenda ?? []} />
      </div>
      {event.own && <RowMenu label={event.title} actions={[change.entry]} />}
      {!event.own && addTodo && <RowMenu label={event.title} actions={[addTodo]} />}
      {event.own && change.form}
      {event.own && <LearnedLines records={[event.snapshot]} />}
    </li>
  );
}

// ---------------------------------------------------------------- To do

type Todo = S["TodoView"];

function TodoPanel() {
  const { t, tn } = useWords();
  const todo = useQuery({ queryKey: ["today", "todo"], queryFn: api.todo });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const addTodo = useAddTodo();
  const today = localDate(useNow());
  const items = todo.data ?? [];
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  // A to-do whose blocker is over (a question answered, a to-do finished) goes first, saying so.
  const unblocked = items.filter((x) => !!x.blocker && x.blocker.state !== "waiting");
  const live = items.filter((x) => !x.on_hold && !unblocked.includes(x));
  // A date still to be checked is never a deadline: it is not overdue, due today or later, and has its own group.
  const isToday = (x: Todo) => !x.overdue && !x.due_check && !!x.due && x.due <= today;
  const groups = [
    { id: "unblocked", label: t("today.todo.unblocked"), rows: unblocked },
    { id: "overdue", label: t("today.todo.overdue"), rows: live.filter((x) => x.overdue) },
    { id: "today", label: t("today.todo.today"), rows: live.filter(isToday) },
    { id: "later", label: t("today.todo.later"), rows: live.filter((x) => !x.overdue && !x.due_check && !isToday(x) && !!x.due) },
    { id: "check", label: t("today.todo.check_date"), rows: live.filter((x) => !!x.due_check) },
    { id: "none", label: t("today.todo.no_date"), rows: live.filter((x) => !x.overdue && !x.due) },
    { id: "on_hold", label: t("today.todo.on_hold"), rows: items.filter((x) => !!x.on_hold) },
  ].filter((g) => g.rows.length > 0);

  // Adding one by hand sits with the to-dos, not in Today's heading, which stays one row.
  return (
    <RailPanel
      id="todo"
      title={t("today.todo.title")}
      action={
        <>
          <Button variant="ghost" size="sm" icon="plus" onClick={addTodo.open}>
            {t("addtodo.open")}
          </Button>
          {addTodo.form}
        </>
      }
      count={todo.data ? items.length : null}
      countText={tn("today.todo.count", items.length)}
      summary={todo.data ? (items.length > 0 ? String(items.length) : t("today.rail.nothing")) : ""}
    >
      {todo.isPending ? (
        <Skeleton />
      ) : todo.isError ? (
        <Failed text={t("today.todo.load_failed")} retry={() => void todo.refetch()} />
      ) : groups.length === 0 ? (
        <Empty text={t("today.todo.empty")} />
      ) : (
        groups.map((group) => (
          <div key={group.id} className="tb-group" data-group={group.id}>
            <h3 className="tb-group-head">
              {group.label} <span className="tb-count">{group.rows.length}</span>
            </h3>
            <ul className="tb-list">
              {group.rows.map((item) => (
                <TodoRow
                  key={item.action}
                  item={item}
                  project={item.project ? (names.get(item.project) ?? "") : ""}
                  showDue={group.id !== "today" && group.id !== "on_hold"}
                />
              ))}
            </ul>
          </div>
        ))
      )}
    </RailPanel>
  );
}

export function TodoRow(props: { item: Todo; project: string; showDue: boolean }) {
  const { t } = useWords();
  const act = useAct();
  const noted = useNoted();
  const row = useRef<HTMLLIElement>(null);
  const [noting, setNoting] = useState(false);
  const [ticked, setTicked] = useState(false);
  const { item } = props;
  const said = useSaid();
  const hold = useHold({ id: item.action, on_hold: item.on_hold, blocker: item.blocker });
  const change = useChangeThis({ kind: "action", id: item.action }, () => row.current?.focus());
  const drop = useDropAction({ id: item.action }, () => row.current?.focus());
  const remind = useRemindMe(item.action, item.remind_at, () => row.current?.focus());
  const meta = [props.project, props.showDue && item.due ? t(item.due_check ? "today.todo.due_check" : "today.todo.due", { date: day(item.due) }) : "", item.remind_at ? t("today.todo.reminder", { when: dateAndTime(item.remind_at) }) : ""]
    .filter(Boolean)
    .join(" · ");
  const done = (note?: string) =>
    act(
      () => api.actionStatus(item.action, "done", note),
      (result) => ({
        message: noted(t("toast.action_done"), result.request),
        undo: () => api.actionStatus(item.action, "open"),
      }),
    );
  // A tick marks it done at once, with Undo on the toast; the row's menu has the way to add a note to it.
  const tick = async () => {
    setTicked(true);
    if ((await done()) === undefined) setTicked(false);
  };
  return (
    <li className={noting ? "tb-row noting" : "tb-row"} data-row tabIndex={-1} ref={row}>
      <label className="tb-tick">
        <input
          type="checkbox"
          data-key="primary"
          checked={ticked}
          disabled={ticked}
          aria-label={t("today.todo.done_named", { text: item.text })}
          onChange={() => void tick()}
        />
      </label>
      <div className="tb-what">
        <div className="tb-title">
          {item.text}
          <HoldNote on_hold={item.on_hold} blocker={item.blocker} due={item.due} />
        </div>
        {(meta || item.repeat) && (
          <div className="tb-meta">
            {meta}
            {item.repeat && meta ? " · " : ""}
            {item.repeat && (
              <span data-repeat="" title={said(item.repeat)}>
                {t("repeat.mark")}
              </span>
            )}
          </div>
        )}
        <OriginLink origin={item.origin} />
      </div>
      <RowMenu label={item.text} actions={[{ id: "note", label: t("note.add"), run: () => setNoting(true) }, ...remind.entries, hold.entry, change.entry, drop.entry]} />
      {noting && (
        <NoteBox
          sends={[{ label: t("followups.mark_done"), run: done }]}
          onClose={() => {
            setNoting(false);
            row.current?.focus();
          }}
        />
      )}
      {hold.form}
      {remind.form}
      {change.form}
      {drop.form}
      <LearnedLines records={[item.action]} />
    </li>
  );
}

// ---------------------------------------------------------------- Came in

/** What a check says in a toast: what arrived, then any source that couldn't be read or was already being read. */
function checkedText(result: S["InboxCheckView"], t: T, tn: ReturnType<typeof useWords>["tn"]): string {
  const parts = [result.new_items > 0 ? tn("today.arrived.check_new", result.new_items) : t("today.arrived.check_none")];
  // A source that couldn't be read says why and what to do, not only that it failed.
  if (result.sources_failed > 0) {
    const problems = result.problems ?? [];
    parts.push(...(problems.length > 0 ? problems.map((p) => p.replace(/\.$/, "")) : [tn("today.arrived.check_failed", result.sources_failed)]));
  }
  if (result.sources_busy > 0) parts.push(tn("today.arrived.check_busy", result.sources_busy));
  return parts.join(". ") + (parts.length > 1 ? "." : "");
}

/** The button that reads every source now and shows what arrived; it never replaces the sources' own schedule. */
function CheckNow() {
  const { t, tn } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const [checking, setChecking] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const keepFocus = useRef(false);
  // A button that turns off while it works loses the keyboard's place; put it back once it is on again.
  useEffect(() => {
    if (!checking && keepFocus.current) {
      keepFocus.current = false;
      button.current?.focus();
    }
  }, [checking]);
  const run = async () => {
    keepFocus.current = document.activeElement === button.current;
    setChecking(true);
    await act(
      async () => {
        const result = await api.checkArrived();
        // Show the new list at once, without waiting for it to be fetched again.
        client.setQueryData<S["InboxView"]>(["today", "arrived"], {
          items: result.items,
          left_out: result.left_out,
          set_aside: result.set_aside,
        });
        return result;
      },
      (result) => ({ message: checkedText(result, t, tn) }),
    );
    setChecking(false);
  };
  return (
    <button ref={button} type="button" className="btn small" disabled={checking} aria-busy={checking} onClick={() => void run()}>
      {t(checking ? "today.arrived.checking" : "today.arrived.check")}
    </button>
  );
}

function ArrivedPanel(props: { onView: (view: View) => void; onAddSource?: () => void }) {
  const { t, tn } = useWords();
  const sourceState = useSourceState(props.onAddSource, t("today.arrived.connect"), "mail");
  const watch = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });
  const arrived = useQuery({ queryKey: ["today", "arrived"], queryFn: api.arrived });
  const now = useNow();
  const today = localDate(now);
  const items = arrived.data?.items ?? [];
  const leftOut = arrived.data?.left_out ?? 0;
  const setAside = arrived.data?.set_aside ?? 0;
  const { setAside: moveToFolder } = useSetAside();
  // The folder is a section of the Sources screen; once that shows, the page goes to it.
  const openFolder = () => {
    props.onView("sources");
    window.setTimeout(() => document.getElementById("set-aside")?.scrollIntoView?.({ block: "start" }), 50);
  };
  const sourceName = useSourceNames(items.map((m) => m.source));
  const received = (iso: string) => (iso.slice(0, 10) === today ? wallTime(iso) : weekday(iso));

  return (
    <RailPanel
      id="arrived"
      title={t("today.arrived.title")}
      count={arrived.data ? items.length : null}
      countText={tn("today.arrived.count", items.length)}
      summary={
        arrived.data
          ? items.length > 0
            ? String(items.length)
            : sourceState.problems.length > 0
              ? t("today.rail.not_read")
              : t("today.rail.nothing")
          : ""
      }
      action={watch.data && anyReading(watch.data) ? <CheckNow /> : undefined}
      footer={
        (setAside > 0 || leftOut > 0) && (
          <>
            {setAside > 0 && (
              <button type="button" className="link-button" onClick={openFolder}>
                {t("today.arrived.set_aside", { n: setAside })}
              </button>
            )}
            {leftOut > 0 && (
              <button type="button" className="link-button" onClick={() => props.onView("sources")}>
                {t("today.arrived.closed", { n: leftOut })}
              </button>
            )}
          </>
        )
      }
    >
      {arrived.isPending ? (
        <Skeleton />
      ) : arrived.isError ? (
        <Failed text={t("today.arrived.load_failed")} retry={() => void arrived.refetch()} />
      ) : items.length === 0 ? (
        sourceState.problems.length > 0 ? (
          <div className="tb-empty">
            <p>{t("today.arrived.not_read")}</p>
            <SourceProblems problems={sourceState.problems} />
          </div>
        ) : (
          <Empty text={t("today.arrived.empty")} note={sourceState.note} button={sourceState.button} />
        )
      ) : (
        <ul className="tb-list">
          {items.map((message, i) => {
            const meta = [message.sender, sourceName(message.source)].filter(Boolean).join(" · ");
            return (
              <li key={`${message.snapshot}:${i}`} className={message.unread ? "tb-row unread" : "tb-row"}>
                <div className="tb-what">
                  <div className="tb-title">
                    {message.unread && <span className="pill k-wait">{t("today.arrived.new")}</span>}
                    <span>{message.link ? <SafeLink label={message.title} url={message.link} /> : message.title}</span>
                  </div>
                  {meta && <div className="tb-meta">{meta}</div>}
                </div>
                <time className="tb-when" dateTime={message.received}>
                  {received(message.received)}
                </time>
                <RowMenu
                  label={message.title}
                  actions={[
                    { id: "personal", label: t("setaside.menu_personal"), run: () => void moveToFolder({ id: message.snapshot, title: message.title }, "personal") },
                    { id: "sales", label: t("setaside.menu_sales"), run: () => void moveToFolder({ id: message.snapshot, title: message.title }, "sales") },
                  ]}
                />
              </li>
            );
          })}
        </ul>
      )}
    </RailPanel>
  );
}
