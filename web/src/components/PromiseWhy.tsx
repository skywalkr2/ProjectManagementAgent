// Why a promise exists (design 6.33): the exact words, who owes it to whom, its day and the words it came from, where it
// came from, and whether it was said or worked out, then what was heard since. Each of owner, promised to, day and how it
// is known is one click to correct, as a list to pick from (people from the people list, the two ways it is known, a date
// picker); a correction is the person's own edit, with Undo, and a signal the assistant learns from. Never a score.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";
import { OriginLink } from "./Origin";

type View = S["PromiseView"];
type Field = "owner" | "to" | "due" | "basis";

/** Whether the action says anything a promise carries; a plain to-do with none of it has no "why" to show. */
export const carriesPromise = (v: View): boolean => !!v.quote || !!v.basis || v.promised_to.length > 0 || !!v.due_words || v.news.length > 0;

/** The one correction a promise takes, with the toast that says so and Undo. */
export function useCorrectPromise(action: string) {
  const { t } = useWords();
  const act = useAct();
  return (body: Omit<S["PromiseCorrection"], "read_version">, readVersion: number) =>
    act(
      () => api.correctPromise(action, { ...body, read_version: readVersion }),
      (done) => ({ message: t("promise.corrected"), undo: () => api.undo(done.changeset) }),
    );
}

/** The promise's why block. `quiet` leaves a plain to-do alone; `omitQuote` and `omitOrigin` are for a place that already
 * shows the words, or the link to where they came from. */
export function PromiseWhy(props: { action: string; quiet?: boolean; omitQuote?: boolean; omitOrigin?: boolean }) {
  const { t } = useWords();
  const found = useQuery({ queryKey: ["promise", props.action], queryFn: () => api.promise(props.action) });
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [editing, setEditing] = useState<Field | null>(null);
  const correct = useCorrectPromise(props.action);
  const view = found.data;
  if (found.isPending) return <Skeleton />;
  if (!view || (props.quiet && !carriesPromise(view))) return null;
  const done = async (body: Omit<S["PromiseCorrection"], "read_version">) => {
    if ((await correct(body, view.version)) !== undefined) setEditing(null);
  };
  const row = (field: Field, label: string, value: ReactNode, editor: ReactNode) => (
    <div className="detail" data-promise={field}>
      <dt>{label}</dt>
      <dd>
        {editing === field ? (
          editor
        ) : (
          <>
            <span>{value}</span>
            <button type="button" className="link-button" aria-label={t("promise.change_named", { what: label })} onClick={() => setEditing(field)}>
              {t("promise.change")}
            </button>
          </>
        )}
      </dd>
    </div>
  );
  const names = people.data ?? [];
  return (
    <section className="promise-why" aria-label={t("promise.why")} data-promise-why={view.action}>
      <dl className="details-list">
        {view.quote && !props.omitQuote && (
          <div className="detail">
            <dt>{t("promise.words")}</dt>
            <dd>
              <q>{view.quote}</q>
              {!props.omitOrigin && <OriginLink origin={view.origin} />}
            </dd>
          </div>
        )}
        {row(
          "owner",
          t("promise.owner"),
          view.owners.map((o) => o.name).join(", "),
          <PickPerson
            label={t("promise.owner")}
            value={view.owners[0]?.id ?? ""}
            people={names}
            onPick={(person) => void done({ owner: person })}
            onCancel={() => setEditing(null)}
          />,
        )}
        {row(
          "to",
          t("promise.to"),
          view.promised_to.length > 0 ? view.promised_to.map((p) => p.name).join(", ") : t("promise.no_one"),
          <PickPerson
            label={t("promise.to")}
            value={view.promised_to[0]?.id ?? ""}
            people={names}
            none={t("promise.no_one")}
            onPick={(person) => void done({ promised_to: person ? [person] : [] })}
            onCancel={() => setEditing(null)}
          />,
        )}
        {row(
          "due",
          t("promise.due"),
          <>
            {view.due ? day(view.due) : t("promise.no_date")}
            {view.due_words && <> {t("promise.due_words", { words: view.due_words })}</>}
            {view.due_check && (
              <>
                {" "}
                <strong>{t("promise.check_date")}</strong>
              </>
            )}
          </>,
          <NewDate label={t("promise.due")} value={view.due ?? ""} onSave={(due) => void done({ due })} onCancel={() => setEditing(null)} />,
        )}
        {view.basis &&
          row(
            "basis",
            t("promise.basis"),
            <>
              {t(`promise.basis.${view.basis}`)}
              {view.basis === "said" && view.said_by && <> ({t("promise.said_by", { name: view.said_by })})</>}
            </>,
            <PickBasis value={view.basis} onPick={(basis) => void done({ basis })} onCancel={() => setEditing(null)} />,
          )}
        {(!view.quote || props.omitQuote) && !props.omitOrigin && (
          <div className="detail">
            <dt />
            <dd>
              <OriginLink origin={view.origin} />
            </dd>
          </div>
        )}
      </dl>
      <PromiseNews news={view.news} />
    </section>
  );
}

/** What was heard that didn't end it, newest first, each with its day and words; a delivered part reads as done and is
 * credited to its owners. */
export function PromiseNews(props: { news: View["news"] }) {
  const { t } = useWords();
  if (props.news.length === 0) return null;
  return (
    <div className="promise-news">
      <h4>{t("promise.news")}</h4>
      <ul className="children">
        {props.news.map((n, i) => (
          <li key={`${n.on}-${i}`} data-delivered={n.delivered ? "" : undefined}>
            <div>
              {n.delivered
                ? t("promise.news.delivered", { date: day(n.on), text: n.text, names: (n.credited ?? []).join(", ") })
                : t("promise.news.item", { date: day(n.on), text: n.text })}
            </div>
            {n.quote && <div className="hint">{t("promise.news.quote", { quote: n.quote })}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A list of the people to pick from; picking applies it, Escape leaves it. The cursor starts in it. */
function PickPerson(props: { label: string; value: string; people: S["PersonView"][]; none?: string; onPick: (person: string) => void; onCancel: () => void }) {
  const id = useId();
  return (
    <select
      id={id}
      autoFocus
      aria-label={props.label}
      value={props.value}
      onChange={(e) => props.onPick(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
      onBlur={props.onCancel}
    >
      {props.none !== undefined && <option value="">{props.none}</option>}
      {props.people.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}

function PickBasis(props: { value: "said" | "inferred"; onPick: (basis: "said" | "inferred") => void; onCancel: () => void }) {
  const { t } = useWords();
  return (
    <select
      autoFocus
      aria-label={t("promise.basis")}
      value={props.value}
      onChange={(e) => props.onPick(e.target.value as "said" | "inferred")}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
      onBlur={props.onCancel}
    >
      <option value="said">{t("promise.basis.said")}</option>
      <option value="inferred">{t("promise.basis.inferred")}</option>
    </select>
  );
}

/** A date picker and Save; the cursor starts in the picker. */
export function NewDate(props: { label: string; value: string; onSave: (due: string) => void; onCancel: () => void }) {
  const { t } = useWords();
  const id = useId();
  const [value, setValue] = useState(props.value);
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
        {props.label}
      </label>
      <input id={id} type="date" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onCancel}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!value || value === props.value}>
          {t("promise.save")}
        </button>
      </div>
    </form>
  );
}
