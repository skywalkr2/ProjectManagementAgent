// People and projects (design 5.1): set up a workspace's people and projects without editing files. Records refer to
// people and projects by id, so a rename shows everywhere at once. Every change acts at once with Undo.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, dayAndTime } from "../lib/dates";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";

const list = (text: string) =>
  text
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

export function Setup() {
  return (
    <>
      <PeoplePanel />
      <ProjectsPanel />
    </>
  );
}

// ---- people --------------------------------------------------------------------------------------------------------

function PeoplePanel() {
  const { t } = useWords();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [adding, setAdding] = useState(false);
  const rows = [...(people.data ?? [])].sort((a, b) =>
    a.is_pm === b.is_pm ? a.name.localeCompare(b.name) : a.is_pm ? -1 : 1,
  );
  return (
    <section className="panel-section" aria-labelledby="people-title">
      <div className="heading">
        <h2 id="people-title">{t("setup.people")}</h2>
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("setup.add_person")}
          </button>
        )}
      </div>
      {adding && <PersonForm onDone={() => setAdding(false)} />}
      {people.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="empty">{t("setup.no_people")}</p>
      ) : (
        <ul className="queue">
          {rows.map((p) => (
            <PersonRow key={p.id} person={p} />
          ))}
        </ul>
      )}
    </section>
  );
}

function PersonRow(props: { person: S["PersonView"] }) {
  const { t } = useWords();
  const act = useAct();
  const p = props.person;
  const [editing, setEditing] = useState(false);
  const left = p.status === "left";
  const menu: MenuAction[] = [];
  if (!p.is_pm) {
    menu.push({
      id: "left",
      label: t(left ? "setup.mark_active" : "setup.mark_left"),
      run: () =>
        void act(
          () => api.editPerson(p.id, { status: left ? "active" : "left" }),
          () => ({
            message: t(left ? "toast.marked_active" : "toast.marked_left", { name: p.name }),
            undo: () => api.editPerson(p.id, { status: p.status }),
          }),
        ),
    });
    menu.push({
      id: "remove",
      label: t("setup.remove"),
      run: () =>
        void act(
          () => api.removePerson(p.id),
          () => ({ message: t("toast.removed", { name: p.name }), undo: () => api.restorePerson(p.id) }),
        ),
    });
  }
  const sub = [p.role, p.org, p.aliases.length ? t("setup.also_called", { names: p.aliases.join(", ") }) : ""]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="line">
      <div className="row">
        <span className={`kind ${p.is_pm ? "k-review" : left ? "k-done" : "k-send"}`}>
          {t(p.is_pm ? "setup.you" : left ? "setup.left" : "setup.active")}
        </span>
        <div className="text">
          <strong>{p.name}</strong>
          {sub && <span className="sub">{sub}</span>}
        </div>
        <div className="acts">
          {!editing && (
            <button type="button" className="btn" onClick={() => setEditing(true)}>
              {t("setup.edit")}
            </button>
          )}
          <RowMenu label={p.name} actions={menu} />
        </div>
      </div>
      {editing && (
        <div className="body">
          <PersonForm person={p} onDone={() => setEditing(false)} />
        </div>
      )}
    </li>
  );
}

function PersonForm(props: { person?: S["PersonView"]; onDone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const p = props.person;
  const [name, setName] = useState(p?.name ?? "");
  const [role, setRole] = useState(p?.role ?? "");
  const [org, setOrg] = useState(p?.org ?? "");
  const [aliases, setAliases] = useState(p?.aliases.join(", ") ?? "");
  const key = p?.id ?? "new";
  const save = async () => {
    const body = { full_name: name.trim(), role: role.trim() || null, org: org.trim() || null, aliases: list(aliases) };
    const done = p
      ? await act(
          () => api.editPerson(p.id, body),
          () => ({
            message: t("toast.saved", { name: body.full_name }),
            undo: () => api.editPerson(p.id, { full_name: p.name, role: p.role, org: p.org, aliases: p.aliases }),
          }),
        )
      : await act(
          () => api.addPerson(body),
          (created) => ({ message: t("toast.added", { name: body.full_name }), undo: () => api.removePerson(created.id) }),
        );
    if (done) props.onDone();
  };
  return (
    <form
      className="panel setup-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onDone();
      }}
    >
      <Field id={`pn-${key}`} label={t("setup.full_name")} value={name} onChange={setName} required autoFocus />
      <Field id={`pr-${key}`} label={t("setup.role")} value={role} onChange={setRole} hint={t("setup.role_hint")} />
      <Field id={`po-${key}`} label={t("setup.org")} value={org} onChange={setOrg} hint={t("setup.org_hint")} />
      <Field id={`pa-${key}`} label={t("setup.aliases")} value={aliases} onChange={setAliases} hint={t("setup.aliases_hint")} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!name.trim()}>
          {t(p ? "setup.save" : "setup.add_person")}
        </button>
      </div>
    </form>
  );
}

// ---- projects ------------------------------------------------------------------------------------------------------

function ProjectsPanel() {
  const { t } = useWords();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const notes = useQuery({ queryKey: ["notes"], queryFn: api.notes });
  const [adding, setAdding] = useState(false);
  const known = new Set((projects.data ?? []).map((p) => p.id));
  // A note filed under a project that no longer exists is shown with the ones that were never filed under one.
  const loose = (notes.data ?? []).filter((n) => !n.project || !known.has(n.project));
  return (
    <section className="panel-section" aria-labelledby="projects-title">
      <div className="heading">
        <h2 id="projects-title">{t("setup.projects")}</h2>
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("setup.add_project")}
          </button>
        )}
      </div>
      {adding && <ProjectForm onDone={() => setAdding(false)} />}
      {projects.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : (projects.data ?? []).length === 0 ? (
        <p className="empty">{t("setup.no_projects")}</p>
      ) : (
        <ul className="queue">
          {(projects.data ?? []).map((p) => (
            <ProjectRow key={p.id} project={p} notes={(notes.data ?? []).filter((n) => n.project === p.id)} />
          ))}
        </ul>
      )}
      {loose.length > 0 && (
        <section className="loose-notes" aria-labelledby="loose-notes-title">
          <h3 id="loose-notes-title">{t("setup.notes_unfiled")}</h3>
          <NoteList notes={loose} />
        </section>
      )}
    </section>
  );
}

function ProjectRow(props: { project: S["ProjectView"]; notes: S["NoteView"][] }) {
  const { t } = useWords();
  const act = useAct();
  const p = props.project;
  const [editing, setEditing] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const menu: MenuAction[] = [
    {
      id: "notes",
      label: t(showNotes ? "setup.notes_hide" : "setup.notes", { n: props.notes.length }),
      run: () => setShowNotes((v) => !v),
    },
    {
      id: "remove",
      label: t("setup.remove"),
      run: () =>
        void act(
          () => api.removeProject(p.id),
          () => ({ message: t("toast.removed", { name: p.name }), undo: () => api.restoreProject(p.id) }),
        ),
    },
  ];
  const sub = [
    p.status,
    p.phase,
    p.target ? t("setup.target_on", { date: day(p.target) }) : "",
    p.owner_name ? t("setup.owned_by", { name: p.owner_name }) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="line">
      <div className="row">
        <span className="kind k-review">{p.group || t("setup.project")}</span>
        <div className="text">
          <strong>{p.name}</strong>
          {sub && <span className="sub">{sub}</span>}
        </div>
        <div className="acts">
          {!editing && (
            <button type="button" className="btn" onClick={() => setEditing(true)}>
              {t("setup.edit")}
            </button>
          )}
          <RowMenu label={p.name} actions={menu} />
        </div>
      </div>
      {showNotes && (
        <div className="body">
          {props.notes.length ? <NoteList notes={props.notes} /> : <p className="hint">{t("setup.notes_none")}</p>}
        </div>
      )}
      {editing && (
        <div className="body">
          <ProjectForm project={p} onDone={() => setEditing(false)} />
        </div>
      )}
    </li>
  );
}

/** Filed notes, newest first. A note may hold text from outside content, so it is shown as text with real domains. */
function NoteList(props: { notes: S["NoteView"][] }) {
  const { t } = useWords();
  return (
    <ul className="notes">
      {props.notes.map((n) => (
        <li key={n.id}>
          <SafeText text={n.text} />
          <span className="hint">
            {[n.created_at ? t("setup.note_filed", { when: dayAndTime(n.created_at) }) : "", n.trust === "untrusted" ? t("setup.note_outside") : ""]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ProjectForm(props: { project?: S["ProjectView"]; onDone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const p = props.project;
  const [name, setName] = useState(p?.name ?? "");
  const [status, setStatus] = useState(p?.status ?? "");
  const [phase, setPhase] = useState(p?.phase ?? "");
  const [group, setGroup] = useState(p?.group ?? "");
  const [target, setTarget] = useState(p?.target ?? "");
  const [owner, setOwner] = useState(p?.owner ?? "");
  const [summary, setSummary] = useState(p?.summary ?? "");
  const key = p?.id ?? "new";
  const save = async () => {
    const body = {
      name: name.trim(),
      status: status.trim() || null,
      phase: phase.trim() || null,
      group: group.trim() || null,
      target: target || null,
      owner: owner || null,
      summary: summary.trim() || null,
    };
    const done = p
      ? await act(
          () => api.editProject(p.id, body),
          () => ({
            message: t("toast.saved", { name: body.name }),
            undo: () =>
              api.editProject(p.id, {
                name: p.name,
                status: p.status,
                phase: p.phase,
                group: p.group,
                target: p.target,
                owner: p.owner,
                summary: p.summary,
              }),
          }),
        )
      : await act(
          () => api.addProject(body),
          (created) => ({ message: t("toast.added", { name: body.name }), undo: () => api.removeProject(created.id) }),
        );
    if (done) props.onDone();
  };
  return (
    <form
      className="panel setup-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onDone();
      }}
    >
      <Field id={`jn-${key}`} label={t("setup.project_name")} value={name} onChange={setName} required autoFocus />
      <Field id={`jt-${key}`} label={t("setup.target")} value={target} onChange={setTarget} type="date" />
      <Field id={`js-${key}`} label={t("setup.status")} value={status} onChange={setStatus} hint={t("setup.status_hint")} />
      <Field id={`jp-${key}`} label={t("setup.phase")} value={phase} onChange={setPhase} />
      <Field id={`jg-${key}`} label={t("setup.group")} value={group} onChange={setGroup} hint={t("setup.group_hint")} />
      <PersonPicker
        label={t("setup.owner")}
        value={owner}
        onChange={setOwner}
        suggested={[]}
        people={(people.data ?? []).filter((x) => x.status === "active")}
      />
      <div className="field">
        <label htmlFor={`jm-${key}`}>{t("setup.summary")}</label>
        <textarea id={`jm-${key}`} className="short" value={summary} onChange={(e) => setSummary(e.target.value)} />
      </div>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!name.trim()}>
          {t(p ? "setup.save" : "setup.add_project")}
        </button>
      </div>
    </form>
  );
}

function Field(props: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  type?: string;
  required?: boolean;
  autoFocus?: boolean;
}) {
  return (
    <div className="field">
      <label htmlFor={props.id}>
        {props.label} {props.hint && <span className="hint">{props.hint}</span>}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        value={props.value}
        required={props.required}
        autoFocus={props.autoFocus}
        onChange={(e) => props.onChange(e.target.value)}
      />
    </div>
  );
}
