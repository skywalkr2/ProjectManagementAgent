// What the person can do about an invitation on a calendar entry (design 6.12): accept, say maybe, decline, or propose another
// time. Each drafts the answer as an act and opens it in Waiting to go out, where the person says yes to exactly what goes to
// the organizer. A time to propose is picked from the free times in the person's working week, or typed. An account that can't
// propose (a plain mailbox) doesn't offer it, and the screen says why.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { dayAndTime } from "../lib/dates";
import { useActOptions, useDraftAct } from "../lib/acts";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";

type Answer = "accepted" | "tentative" | "declined" | "propose";

export interface InvitationActs {
  /** The primary answer and the menu of the others, for the entry's heading; nothing when no answer is offered. */
  buttons: ReactNode;
  /** The form for a proposed time, and the reason proposing isn't offered where it isn't. */
  form: ReactNode;
}

/** The answers to an invitation, for the calendar entry `entry`. `enabled` false (not an invitation) asks nothing. */
export function useInvitationActs(entry: string, enabled: boolean): InvitationActs {
  const { t } = useWords();
  const found = useActOptions(entry, enabled);
  const draft = useDraftAct();
  const [proposing, setProposing] = useState(false);
  const options = found.data?.kind === "event" ? found.data : null;
  const answers = options?.answers ?? [];
  if (!enabled || !options || answers.length === 0) return { buttons: null, form: null };

  const answer = (how: Exclude<Answer, "propose">) => void draft({ kind: "calendar", action: "answer", about: [entry], answer: how });
  const menu: MenuAction[] = [
    ...(answers.includes("tentative") ? [{ id: "maybe", label: t("acts.answer.tentative"), run: () => answer("tentative") }] : []),
    ...(answers.includes("declined") ? [{ id: "decline", label: t("acts.answer.declined"), run: () => answer("declined") }] : []),
    ...(answers.includes("propose") ? [{ id: "propose", label: t("acts.answer.propose"), run: () => setProposing(true) }] : []),
  ];
  return {
    buttons: (
      <>
        {answers.includes("accepted") && (
          <button type="button" className="btn primary" onClick={() => answer("accepted")}>
            {t("acts.answer.accepted")}
          </button>
        )}
        <RowMenu label={t("acts.answer.menu")} actions={menu} />
      </>
    ),
    form: (
      <>
        {options.propose_refusal && (
          <p className="hint" data-propose-refused="">
            {t("acts.propose.refused")}
          </p>
        )}
        {proposing && (
          <ProposeForm
            entry={entry}
            onCancel={() => setProposing(false)}
            onSubmit={async (start, end) => {
              const made = await draft({ kind: "calendar", action: "answer", about: [entry], answer: "propose", proposed_start: start, proposed_end: end });
              if (made) setProposing(false);
            }}
          />
        )}
      </>
    ),
  };
}

/** A local date and time as ISO text with its offset, from a `datetime-local` box. */
function isoOf(local: string): string {
  const when = new Date(local);
  return Number.isNaN(when.getTime()) ? "" : when.toISOString();
}

/** The free times to pick from (the first is chosen) or a start and end typed; the cursor starts in the list. */
function ProposeForm(props: { entry: string; onCancel: () => void; onSubmit: (start: string, end: string) => Promise<void> }) {
  const { t } = useWords();
  const base = useId();
  const slots = useQuery({ queryKey: ["free-slots", props.entry], queryFn: () => api.freeSlots(props.entry), staleTime: 60_000 });
  const [picked, setPicked] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [bad, setBad] = useState(false);
  const list = slots.data?.slots ?? [];
  // The cursor starts in the first field there is once the free times are known: the first time, else the typed start.
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (slots.isPending) return;
    form.current?.querySelector<HTMLElement>('input[type="radio"], input[type="datetime-local"]')?.focus();
  }, [slots.isPending]);
  const typed = start !== "" || end !== "";
  const chosen = typed ? null : (list.find((s) => s.start === picked) ?? null);

  const submit = () => {
    const from = chosen ? chosen.start : isoOf(start);
    const to = chosen ? chosen.end : isoOf(end);
    if (!from || !to || new Date(to) <= new Date(from)) {
      setBad(true);
      return;
    }
    setBad(false);
    setBusy(true);
    void props.onSubmit(from, to).finally(() => setBusy(false));
  };

  return (
    <form
      ref={form}
      className="answer-form"
      data-act-form="propose"
      aria-labelledby={`${base}-title`}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <h3 id={`${base}-title`}>{t("acts.propose.title")}</h3>
      {list.length > 0 ? (
        <fieldset disabled={typed}>
          <legend>{t("acts.propose.slots")}</legend>
          {list.map((s) => (
            <label key={s.start} className="radio">
              <input type="radio" name={`${base}-slot`} checked={chosen?.start === s.start} onChange={() => setPicked(s.start)} />
              {t("acts.propose.slot", { start: dayAndTime(s.start), end: dayAndTime(s.end) })}
            </label>
          ))}
        </fieldset>
      ) : (
        !slots.isPending && <p className="hint">{t("acts.propose.none")}</p>
      )}
      <fieldset>
        <legend>{t("acts.propose.typed")}</legend>
        <div className="field">
          <label htmlFor={`${base}-start`}>{t("acts.propose.start")}</label>
          <input id={`${base}-start`} type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${base}-end`}>{t("acts.propose.end")}</label>
          <input id={`${base}-end`} type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </fieldset>
      {bad && (
        <p className="problem-note" role="alert">
          {t("acts.propose.bad")}
        </p>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("acts.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={busy || (!chosen && !typed)}>
          {t("acts.propose.go")}
        </button>
      </div>
    </form>
  );
}
