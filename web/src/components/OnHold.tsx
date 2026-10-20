// An action on hold waits for something outside the person's control and is never due, overdue or chased. "Put on hold"
// asks what it waits for (the first field has the cursor) and acts at once with Undo; "Take off hold" does too.
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { revealOrKeep } from "../lib/reveal";
import { toHash, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

type Blocker = NonNullable<S["TodoView"]["blocker"]>;

/** What an action can be blocked on, for the picker: people, the other open to-dos and the questions still open or waiting
 * for an answer. Never typed; a hold with only words leaves it empty. */
function useBlockers(except: string, enabled: boolean) {
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled });
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups, enabled });
  const actions = new Map<string, string>();
  const questions = new Map<string, string>();
  for (const section of followups.data ?? []) {
    for (const a of section.actions) if (a.id !== except) actions.set(a.id, a.text);
    for (const q of [...section.questions, ...(section.later ?? [])]) questions.set(q.id, q.title);
  }
  return { people: people.data ?? [], actions: [...actions], questions: [...questions] };
}

/** The row menu's entry for an action, and the small form it opens to ask what the action waits for: words, or a person, a
 * to-do or a question picked from a list. */
export function useHold(action: { id: string; on_hold?: string | null; blocker?: Blocker | null }): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [asking, setAsking] = useState(false);
  const [what, setWhat] = useState("");
  const [on, setOn] = useState("");
  const options = useBlockers(action.id, asking);
  const label = (id: string) =>
    options.people.find((p) => p.id === id)?.name ?? options.actions.find(([a]) => a === id)?.[1] ?? options.questions.find(([q]) => q === id)?.[1] ?? "";
  const put = async () => {
    const waiting = what.trim();
    if (!waiting && !on) return;
    const named = waiting || label(on);
    const done = await act(
      () => api.putOnHold(action.id, waiting, on || null),
      (result) => ({
        message: t("toast.put_on_hold", { what: named }),
        undo: () => api.restoreHold(action.id, result.previous ?? null),
      }),
    );
    if (done) {
      setAsking(false);
      setWhat("");
      setOn("");
    }
  };
  const release = () =>
    void act(
      () => api.takeOffHold(action.id),
      (result) => ({ message: t("toast.taken_off_hold"), undo: () => api.restoreHold(action.id, result.previous ?? null) }),
    );
  // An action whose blocker is over still carries the hold until it is taken off, so the menu offers that.
  const held = !!action.on_hold || (!!action.blocker && action.blocker.state !== "waiting");
  const entry: MenuAction = held
    ? { id: "take-off-hold", label: t("hold.take_off"), run: release }
    : { id: "put-on-hold", label: t("hold.put"), run: () => setAsking(true) };
  const form = asking ? (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        void put();
      }}
    >
      <label className="hint" htmlFor={`hold-${action.id}`}>
        {t("hold.label")}
      </label>
      <input
        id={`hold-${action.id}`}
        type="text"
        autoFocus
        value={what}
        onChange={(e) => setWhat(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setAsking(false);
        }}
      />
      <label className="hint" htmlFor={`hold-on-${action.id}`}>
        {t("hold.on_label")}
      </label>
      <select id={`hold-on-${action.id}`} value={on} onChange={(e) => setOn(e.target.value)}>
        <option value="">{t("hold.on_none")}</option>
        {options.people.length > 0 && (
          <optgroup label={t("hold.on_people")}>
            {options.people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </optgroup>
        )}
        {options.actions.length > 0 && (
          <optgroup label={t("hold.on_actions")}>
            {options.actions.map(([id, text]) => (
              <option key={id} value={id}>
                {text}
              </option>
            ))}
          </optgroup>
        )}
        {options.questions.length > 0 && (
          <optgroup label={t("hold.on_questions")}>
            {options.questions.map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={() => setAsking(false)}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!what.trim() && !on}>
          {t("hold.put")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, form };
}

const LETTER = "\\p{L}\\p{N}";

/** The one known person whose full name is in the words, as it is written: the longest such name, and only when no one
 * else has the same name. A first name alone or a likeness matches nobody, so a link is never to the wrong person. */
export function namedPerson(words: string, people: Array<{ id: string; name: string }>): { id: string; start: number; end: number } | null {
  const byName = new Map<string, string[]>();
  for (const p of people) byName.set(p.name, [...(byName.get(p.name) ?? []), p.id]);
  const names = [...byName.keys()].filter((n) => n.trim()).sort((a, b) => b.length - a.length);
  for (const name of names) {
    const found = new RegExp(`(?<![${LETTER}])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![${LETTER}])`, "u").exec(words);
    if (!found) continue;
    const ids = byName.get(name)!;
    if (ids.length !== 1) return null;
    return { id: ids[0], start: found.index, end: found.index + name.length };
  }
  return null;
}

/** "On hold: what it waits for", with the date it was due before it went on hold in its tooltip. A person named in the
 * words is a link to their group in Follow-ups, where what they owe is. */
export function HoldPill(props: { what: string; due?: string | null }) {
  const { t } = useWords();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const who = namedPerson(props.what, people.data ?? []);
  const open = (event: React.MouseEvent) => {
    if (!who) return;
    event.preventDefault();
    event.stopPropagation();
    // Follow-ups opens on the person's group; when it is already showing it does so at once.
    if (!revealOrKeep("person", who.id)) window.location.hash = toHash("work/followups");
  };
  const what = who ? (
    <>
      {props.what.slice(0, who.start)}
      <a href={viewHref("work/followups")} onClick={open}>
        {props.what.slice(who.start, who.end)}
      </a>
      {props.what.slice(who.end)}
    </>
  ) : (
    props.what
  );
  const [before, after] = t("hold.pill", { what: "\u0001" }).split("\u0001");
  return (
    <span className="pill k-held" title={props.due ? t("hold.was_due", { date: day(props.due) }) : undefined}>
      {before}
      {what}
      {after}
    </span>
  );
}

/** A name that is a link to what it names: a person's group in Follow-ups, an action's or a question's own page. */
function BlockerName(props: { blocker: Blocker }) {
  const { blocker } = props;
  if (blocker.kind === "person") {
    const open = (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (!revealOrKeep("person", blocker.id)) window.location.hash = toHash("work/followups");
    };
    return (
      <a href={viewHref("work/followups")} onClick={open}>
        {blocker.name}
      </a>
    );
  }
  return <a href={viewHref(`records/${blocker.kind}/${blocker.id}` as never)}>{blocker.name}</a>;
}

/** Fills the one {placeholder} of a wording line with a node, so a name inside a sentence can be a link. */
function around(line: string, mark: string, inner: ReactNode): ReactNode {
  const [before, after] = line.split(mark);
  return (
    <>
      {before}
      {inner}
      {after}
    </>
  );
}

/** What a to-do or a follow-up waits on, in the words the design gives it: "Blocked, waiting on <person or action>",
 * "Waits on: <question> (<who>, sent <date>)", then "Unblocked: <who> answered <date>" once it is over; a hold with only
 * words is "On hold: …". */
export function HoldNote(props: { on_hold?: string | null; blocker?: Blocker | null; due?: string | null }) {
  const { t } = useWords();
  const { blocker } = props;
  if (blocker && blocker.state === "waiting") {
    const title = props.due ? t("hold.was_due", { date: day(props.due) }) : undefined;
    const mark = "\u0001";
    if (blocker.kind === "question") {
      const key = blocker.sent
        ? "hold.waits_on_question"
        : blocker.who
          ? "hold.waits_on_question_unsent"
          : "hold.waits_on_question_nobody";
      const line = t(key, { question: mark, who: blocker.who ?? "", date: blocker.sent ? day(blocker.sent) : "" });
      return (
        <span className="pill k-held wraps" title={title}>
          {around(line, mark, <BlockerName blocker={blocker} />)}
        </span>
      );
    }
    return (
      <span className="pill k-held wraps" title={title}>
        {around(t("hold.blocked", { what: mark }), mark, <BlockerName blocker={blocker} />)}
      </span>
    );
  }
  if (blocker) {
    const line =
      blocker.kind === "question"
        ? blocker.answered
          ? t("hold.unblocked_answered", { who: blocker.who ?? blocker.name, date: day(blocker.answered) })
          : t("hold.unblocked_answered_undated", { who: blocker.who ?? blocker.name })
        : t("hold.unblocked_done", { what: blocker.name });
    return <span className="pill k-send wraps">{line}</span>;
  }
  return props.on_hold ? <HoldPill what={props.on_hold} due={props.due} /> : null;
}
