// A question that is ready to send can be held for later: for a meeting (a calendar entry, or a series, which is its next
// one) or for a day. It waits in Later, out of To send, until that day, and "Send now" brings it back. A person's whole
// message (every question in it that is ready to send) can be held the same way, as one choice. Both act at once with Undo.
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, localDate } from "../lib/dates";
import { useWords } from "../lib/wording";
import type { MenuAction } from "./RowMenu";

const DAY = "day";

/** The menu entries for holding one of a person's questions that are ready to send, or all of them (the whole message),
 * and the small form they open: which question (for one, when there is more than one), and a meeting from the calendar
 * or a day. */
export function useHoldFor(
  questions: Array<{ id: string; title: string }>,
  person: string,
): { entry: MenuAction; messageEntry: MenuAction; form: ReactNode } {
  const { t } = useWords();
  const act = useAct();
  const [asking, setAsking] = useState(false);
  const [whole, setWhole] = useState(false);
  const [chosen, setChosen] = useState("");
  const question = questions.find((q) => q.id === chosen) ?? questions[0];
  const [target, setTarget] = useState(DAY);
  const [date, setDate] = useState("");
  const agenda = useQuery({ queryKey: ["today", "agenda"], queryFn: api.agenda, enabled: asking });
  // One choice per meeting the calendar keeps an entry for; a series is held for its next instance.
  const meetings = (agenda.data ?? []).flatMap((item) => {
    if (!item.entry || item.cancelled) return [];
    const when = day(item.days[0]);
    return item.series
      ? [{ value: `series:${item.series}`, label: t("followups.hold_for_series", { title: item.title }), until: when }]
      : [{ value: `event:${item.entry}`, label: t("followups.hold_for_meeting", { title: item.title, date: when }), until: when }];
  });
  const unique = meetings.filter((m, i) => meetings.findIndex((o) => o.value === m.value) === i);
  const ready = target === DAY ? !!date : true;
  const tomorrow = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return localDate(d);
  })();
  const save = async () => {
    if (!ready || !question) return;
    const [kind, id] = target.split(":");
    const heldFor: S["HeldForIn"] = target === DAY ? { on: date } : kind === "series" ? { series: id } : { event: id };
    const until = target === DAY ? day(date) : (unique.find((m) => m.value === target)?.until ?? "");
    const done = whole
      ? await act(
          () => api.holdMessage(person, heldFor),
          (result) => ({
            message: t("toast.held_for", { date: until }),
            undo: () => api.restoreMessageHolds(person, result.previous),
          }),
        )
      : await act(
          () => api.holdQuestion(question.id, heldFor),
          (result) => ({
            message: t("toast.held_for", { date: until }),
            undo: () => api.holdQuestion(question.id, result.previous ?? null),
          }),
        );
    if (done) {
      setAsking(false);
      setDate("");
      setTarget(DAY);
    }
  };
  const entry: MenuAction = {
    id: "hold-for",
    label: t("followups.hold_for"),
    run: () => {
      setWhole(false);
      setAsking(true);
    },
  };
  const messageEntry: MenuAction = {
    id: "hold-message",
    label: t("followups.hold_message"),
    run: () => {
      setWhole(true);
      setAsking(true);
    },
  };
  const form = asking && question ? (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") setAsking(false);
      }}
    >
      {questions.length > 1 && !whole && (
        <>
          <label className="hint" htmlFor={`hold-which-${questions[0].id}`}>
            {t("followups.hold_which")}
          </label>
          <select id={`hold-which-${questions[0].id}`} autoFocus value={question.id} onChange={(e) => setChosen(e.target.value)}>
            {questions.map((q) => (
              <option key={q.id} value={q.id}>
                {q.title}
              </option>
            ))}
          </select>
        </>
      )}
      <label className="hint" htmlFor={`hold-for-${question.id}`}>
        {t("followups.hold_for_label")}
      </label>
      <select id={`hold-for-${question.id}`} autoFocus={questions.length < 2 || whole} value={target} onChange={(e) => setTarget(e.target.value)}>
        <option value={DAY}>{t("followups.hold_for_day")}</option>
        {unique.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
      {target === DAY && (
        <>
          <label className="hint" htmlFor={`hold-date-${question.id}`}>
            {t("followups.hold_for_date")}
          </label>
          <input id={`hold-date-${question.id}`} type="date" min={tomorrow} value={date} onChange={(e) => setDate(e.target.value)} />
        </>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={() => setAsking(false)}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!ready}>
          {t("followups.hold_for_save")}
        </button>
      </div>
    </form>
  ) : null;
  return { entry, messageEntry, form };
}

/** "Send now": the question leaves Later and is to send again. */
export function useSendNow(question: { id: string }): MenuAction {
  const { t } = useWords();
  const act = useAct();
  return {
    id: "send-now",
    label: t("followups.send_now"),
    run: () =>
      void act(
        () => api.holdQuestion(question.id, null),
        (result) => ({
          message: t("toast.sent_now"),
          undo: () => api.holdQuestion(question.id, result.previous ?? null),
        }),
      ),
  };
}
