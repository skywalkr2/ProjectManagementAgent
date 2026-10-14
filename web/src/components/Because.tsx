// Which knowledge shaped a piece of the assistant's work (design 6.20, 7.18). Its card shows what the run was given and
// applied: "Because you told me: <entry>", linked to the entry. When the work was wrong because of a wrong entry, the
// entry's menu has "This doesn't apply here": leave one project out of it, or retire it, right there, at once with Undo.
// A first run on an account that stands in for another says so.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { narrowedWithout } from "../lib/reach";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { RowMenu } from "./RowMenu";
import styles from "./Learned.module.css";

type Entry = S["AppliedEntryView"];

/** Where an entry opens. */
/** Where an applied entry opens: a rule or fact has its own page; other learned guidance is listed on the Knowledge screen. */
export function entryHref(entry: Pick<Entry, "kind" | "id">): string {
  return entry.kind === "rule" || entry.kind === "fact"
    ? viewHref(recordView(entry.kind, entry.id))
    : viewHref("records/knowledge");
}

/** What an entry can still be narrowed or retired from a card: only a piece of learned guidance that is active. */
const canChange = (entry: Entry) => entry.kind !== "fact" && entry.status === "active";

export function Because(props: { cs: S["ChangesetView"] }) {
  const { t } = useWords();
  const applied = props.cs.applied ?? [];
  const account = props.cs.first_on_account;
  if (!applied.length && !account) return null;
  return (
    <>
      {account && <p className="hint">{t("because.first_run", { account })}</p>}
      {applied.length > 0 && (
        <ul className={styles.because} aria-label={t("because.label")}>
          {applied.map((entry) => (
            <AppliedItem key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </>
  );
}

function AppliedItem(props: { entry: Entry }) {
  const { t } = useWords();
  const { entry } = props;
  const [open, setOpen] = useState(false);
  return (
    <li className={styles.becauseItem} data-applied={entry.id}>
      <span>{t("because.told")}</span>
      <a className={styles.becauseText} href={entryHref(entry)}>
        {entry.text}
      </a>
      {canChange(entry) && (
        <RowMenu label={entry.text} actions={[{ id: "not-here", label: t("because.not_here"), run: () => setOpen(true) }]} />
      )}
      {open && (
        <div className={styles.becauseForm}>
          <NotHere entry={entry} onClose={() => setOpen(false)} />
        </div>
      )}
    </li>
  );
}

/** The projects a leave-out can name: those an entry for a list of projects names (when more than one), else every
 * project it doesn't already leave out. */
function candidates(entry: Entry, all: S["ProjectView"][]): S["ProjectView"][] {
  const scope = entry.applies_to;
  if (!scope) return [];
  return all.filter((p) => narrowedWithout(scope, p.id) !== null && (scope.scope !== "projects" || (scope.projects ?? []).includes(p.id)));
}

function NotHere(props: { entry: Entry; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [project, setProject] = useState("");
  const { entry } = props;
  const choices = candidates(entry, projects.data ?? []);
  const scope = entry.applies_to && project ? narrowedWithout(entry.applies_to, project) : null;
  const narrow = () =>
    scope &&
    act(
      () => api.narrowKnowledge(entry.id, { read_version: entry.version, applies_to: scope }),
      (done) => ({ message: t("toast.narrowed"), undo: () => api.undo(done.changeset) }),
    ).then((done) => done && props.onClose());
  const retire = () =>
    act(
      () => api.retireKnowledge(entry.id, entry.version),
      (done) => ({ message: t("toast.retired"), undo: () => api.undo(done.changeset) }),
    ).then((done) => done && props.onClose());
  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        void narrow();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      {choices.length > 0 ? (
        <div className="field">
          <label htmlFor={id}>{t("because.leave_out")}</label>
          <select id={id} autoFocus value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">{t("because.choose_project")}</option>
            {choices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className="hint">{t("because.only_retire")}</p>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button type="button" className="btn" autoFocus={choices.length === 0} onClick={() => void retire()}>
          {t("because.retire")}
        </button>
        {choices.length > 0 && (
          <button type="submit" className="btn primary" disabled={!scope}>
            {t("because.narrow")}
          </button>
        )}
      </div>
    </form>
  );
}
