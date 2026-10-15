// The obvious next step from what came in, as one click (design 6.7, 6.9): "Add a new person" beside the list on a "Who is
// this?" question, and the three choices on a project the assistant found that the workspace doesn't have. Each acts at
// once and says what it did with an Undo.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { projectChoices } from "../lib/project-choices";
import { useRowKeys } from "../lib/keys";
import { useWords } from "../lib/wording";
import { RowMenu } from "./RowMenu";

/** The form that answers a "Who is this?" question with a new person. It starts from the name as written and whatever the
 * input says about them, and the cursor is in its first field. */
export function NewPersonForm(props: { question: string; onClose: () => void }) {
  const { t } = useWords();
  const form = useQuery({ queryKey: ["new-person", props.question], queryFn: () => api.newPersonForm(props.question) });
  if (form.isPending) return <p className="hint">{t("loading")}</p>;
  if (form.isError || !form.data) return <p className="hint">{t("newperson.load_failed")}</p>;
  return <NewPersonFields question={props.question} start={form.data} onClose={props.onClose} />;
}

function NewPersonFields(props: { question: string; start: S["NewPersonPrefillView"]; onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const ids = useId();
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: api.organizations });
  const start = props.start;
  const first = useRef<HTMLInputElement>(null);
  const [fullName, setFullName] = useState(start.full_name);
  const [firstName, setFirstName] = useState(start.first_name);
  const [org, setOrg] = useState(start.org);
  const [role, setRole] = useState(start.role);
  const [kind, setKind] = useState(start.contact_kind || start.contact_kinds[0] || "");
  const [value, setValue] = useState(start.contact_value);
  const [busy, setBusy] = useState(false);
  useEffect(() => first.current?.focus(), []);

  const submit = async () => {
    if (!fullName.trim() || busy) return;
    setBusy(true);
    const body: S["NewPersonIn"] = {
      full_name: fullName,
      first_name: firstName.trim() || null,
      org: org.trim() || null,
      role: role.trim() || null,
      contact_kind: value.trim() ? kind : null,
      contact_value: value.trim() || null,
    };
    const done = await act(
      () => api.addNewPerson(props.question, body),
      (made) => ({
        message: t("toast.person_added", { name: made.name }),
        // The released items go back first, then the changes that added the person, newest first.
        undo: async () => {
          if (made.changeset && made.released.length) await api.undo(made.changeset, made.released);
          for (const change of made.undo) await api.undo(change);
        },
      }),
    );
    setBusy(false);
    if (done) props.onClose();
  };

  return (
    <form
      className="answer-form new-person"
      aria-label={t("newperson.title")}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onClose();
      }}
    >
      <div className="field">
        <label htmlFor={`${ids}-name`}>{t("newperson.full_name")}</label>
        <input id={`${ids}-name`} ref={first} type="text" autoComplete="off" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${ids}-first`}>
          {t("newperson.first_name")} <span className="hint">{t("newperson.first_name_hint")}</span>
        </label>
        <input id={`${ids}-first`} type="text" autoComplete="off" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${ids}-org`}>
          {t("newperson.org")} <span className="hint">{t("newperson.org_hint")}</span>
        </label>
        <input id={`${ids}-org`} type="text" autoComplete="off" list={`${ids}-orgs`} value={org} onChange={(e) => setOrg(e.target.value)} />
        <datalist id={`${ids}-orgs`}>
          {(orgs.data ?? []).map((o) => (
            <option key={o.id} value={o.name} />
          ))}
        </datalist>
      </div>
      <div className="field">
        <label htmlFor={`${ids}-role`}>{t("newperson.role")}</label>
        <input id={`${ids}-role`} type="text" autoComplete="off" value={role} onChange={(e) => setRole(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${ids}-kind`}>{t("newperson.kind")}</label>
        <select id={`${ids}-kind`} value={kind} onChange={(e) => setKind(e.target.value)}>
          {start.contact_kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${ids}-value`}>{t("newperson.value")}</label>
        <input id={`${ids}-value`} type="text" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!fullName.trim() || busy}>
          {t("newperson.add")}
        </button>
      </div>
    </form>
  );
}

/** A project the assistant found, held for the person: Add, "It's part of" a project picked from the list, or "Not a
 * project". Add is the row's one primary action; the other two are in its menu. */
export function ProjectProposalRow(props: { op: S["OpView"]; changeset: string }) {
  const { t } = useWords();
  const act = useAct();
  const ids = useId();
  const { op } = props;
  const name = op.meta.name ?? op.title;
  const ref = useRef<HTMLLIElement>(null);
  const [choosing, setChoosing] = useState(false);
  const [into, setInto] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: choosing });
  const choices = projectChoices(projects.data ?? [], (parent, child) => t("handin.project.path", { parent, name: child }));
  const close = () => {
    setChoosing(false);
    setInto("");
    ref.current?.focus();
  };

  const add = () =>
    act(
      () => api.release(props.changeset, op.index),
      () => ({ message: t("toast.project_added", { name }), undo: () => api.undo(props.changeset, [op.index]) }),
    );
  const partOf = async () => {
    if (!into) return;
    const target = choices.find((c) => c.id === into)?.label ?? "";
    const done = await act(
      () => api.projectPartOf(props.changeset, op.index, into),
      (made) => ({ message: t("toast.project_filed", { name, project: target }), undo: () => api.undo(made.changeset) }),
    );
    if (done) close();
  };
  const notOne = () =>
    act(
      () => api.notAProject(props.changeset, op.index),
      (made) => ({ message: t("toast.not_a_project", { name }), undo: () => api.undo(made.changeset) }),
    );

  useRowKeys(ref, { primary: () => void add() });
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="what">
          {t("project_item.what")}
          <span className="pill k-held">{t("op.status.held")}</span>
        </div>
        <div className="title">{t("project_item.ask", { name })}</div>
        {op.evidence && (
          <div className="because">
            {t("op.because")} <q>{op.evidence.quote}</q>
          </div>
        )}
      </div>
      <div className="acts">
        <button type="button" className="btn primary" onClick={() => void add()}>
          {t("project_item.add")}
        </button>
        <RowMenu
          label={name}
          actions={[
            { id: "part-of", label: t("project_item.part_of"), run: () => setChoosing(true) },
            { id: "not-a-project", label: t("project_item.not_a_project"), run: () => void notOne() },
          ]}
        />
      </div>
      {choosing && (
        <form
          className="answer-form"
          onSubmit={(e) => {
            e.preventDefault();
            void partOf();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") close();
          }}
        >
          <label className="hint" htmlFor={`${ids}-into`}>
            {t("project_item.part_of_label", { name })}
          </label>
          <select id={`${ids}-into`} autoFocus value={into} onChange={(e) => setInto(e.target.value)}>
            <option value="">{t("project_item.choose")}</option>
            {choices.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <div className="row-end">
            <button type="button" className="btn quiet" onClick={close}>
              {t("action.cancel")}
            </button>
            <button type="submit" className="btn primary" disabled={!into}>
              {t("project_item.part_of_go")}
            </button>
          </div>
        </form>
      )}
    </li>
  );
}
