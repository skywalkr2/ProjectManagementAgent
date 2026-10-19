// An action on hold waits for something outside the person's control and is never due, overdue or chased. "Put on hold"
// asks what it waits for (the first field has the cursor) and acts at once with Undo; "Take off hold" does too.
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { revealOrKeep } from "../lib/reveal";
import { toHash, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

/** The row menu's entry for an action, and the small form it opens to ask what the action waits for. */
export function useHold(action: { id: string; on_hold?: string | null }): { entry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [asking, setAsking] = useState(false);
  const [what, setWhat] = useState("");
  const put = async () => {
    const waiting = what.trim();
    if (!waiting) return;
    const done = await act(
      () => api.putOnHold(action.id, waiting),
      (result) => ({
        message: t("toast.put_on_hold", { what: waiting }),
        undo: () => api.restoreHold(action.id, result.previous ?? null),
      }),
    );
    if (done) {
      setAsking(false);
      setWhat("");
    }
  };
  const release = () =>
    void act(
      () => api.takeOffHold(action.id),
      (result) => ({ message: t("toast.taken_off_hold"), undo: () => api.restoreHold(action.id, result.previous ?? null) }),
    );
  const entry: MenuAction = action.on_hold
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
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={() => setAsking(false)}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!what.trim()}>
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
