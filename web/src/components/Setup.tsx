// People and projects (design 5.1): set up a workspace's people and projects without editing files. Records refer to
// people and projects by id, so a rename shows everywhere at once. Every change acts at once with Undo.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { languageChoices, languageLabel } from "../lib/languages";
import { day, dayAndTime } from "../lib/dates";
import { useTotal } from "../lib/money";
import { problemText } from "../lib/problem";
import { readable, readableTail } from "../lib/records";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { FolderPicker, useFolderListing } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";
import { OrgSelect } from "./OrgSelect";
import { PersonPicker } from "./PersonPicker";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";
import { useTextReview } from "./TextReview";
import { ValueSelect } from "./ValueSelect";
import { Skeleton } from "../ui/Skeleton";

/** The value lists a project's fields take their choices from. */
const PROJECT_LISTS = {
  status: "project-status",
  phase: "project-phase",
  group: "project-group",
  priority: "project-priority",
} as const;

/** The parts a person can have in a project, as the pick list offers them. */
const ROLES = ["run", "design", "watch"] as const;
type Role = (typeof ROLES)[number];

const list = (text: string) =>
  text
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

/** `lead` names the part this screen was opened for: its heading is the page's title and it comes first. */
export function Setup(props: { lead?: "people" | "projects" }) {
  const people = <PeoplePanel key="people" lead={props.lead === "people"} />;
  const projects = <ProjectsPanel key="projects" lead={props.lead === "projects"} />;
  return (
    <>
      {props.lead === "projects" ? (
        <>
          {projects}
          {people}
          <OrganizationsPanel />
        </>
      ) : (
        <>
          {people}
          <OrganizationsPanel />
          {projects}
        </>
      )}
      <SyncPanel />
      <JobsPanel />
    </>
  );
}

// ---- people --------------------------------------------------------------------------------------------------------

function PeoplePanel(props: { lead?: boolean }) {
  const { t } = useWords();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [adding, setAdding] = useState(false);
  const rows = [...(people.data ?? [])].sort((a, b) =>
    a.is_pm === b.is_pm ? a.name.localeCompare(b.name) : a.is_pm ? -1 : 1,
  );
  return (
    <section className="panel-section" aria-labelledby="people-title">
      <div className="heading">
        {props.lead ? <h1 id="people-title">{t("setup.people")}</h1> : <h2 id="people-title">{t("setup.people")}</h2>}
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("setup.add_person")}
          </button>
        )}
      </div>
      {adding && <PersonForm onDone={() => setAdding(false)} />}
      {people.isPending ? (
        <Skeleton />
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
  const sub = [p.role, p.org_name, p.aliases.length ? t("setup.also_called", { names: p.aliases.join(", ") }) : ""]
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
  const [firstName, setFirstName] = useState(p?.first_name ?? "");
  const [role, setRole] = useState(p?.role ?? "");
  const [org, setOrg] = useState(p?.org ?? "");
  const [aliases, setAliases] = useState(p?.aliases.join(", ") ?? "");
  const key = p?.id ?? "new";
  const save = async () => {
    const body = {
      full_name: name.trim(),
      first_name: firstName.trim() || null,
      role: role.trim() || null,
      org: org || null,
      aliases: list(aliases),
    };
    const done = p
      ? await act(
          () => api.editPerson(p.id, body),
          () => ({
            message: t("toast.saved", { name: body.full_name }),
            undo: () =>
              api.editPerson(p.id, { full_name: p.name, first_name: p.first_name, role: p.role, org: p.org, aliases: p.aliases }),
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
      <Field
        id={`pf-${key}`}
        label={t("setup.first_name")}
        value={firstName}
        onChange={setFirstName}
        hint={t("setup.first_name_hint")}
      />
      <Field id={`pr-${key}`} label={t("setup.role")} value={role} onChange={setRole} hint={t("setup.role_hint")} />
      <OrgSelect id={`po-${key}`} label={t("setup.org")} value={org} onChange={setOrg} hint={t("setup.org_hint")} />
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

// ---- organizations -------------------------------------------------------------------------------------------------

function OrganizationsPanel() {
  const { t } = useWords();
  const act = useAct();
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: api.organizations });
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const rows = [...(orgs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const stop = () => {
    setAdding(false);
    setName("");
  };
  const add = async () => {
    const wanted = name.trim();
    if (!wanted) return;
    const done = await act(
      () => api.addOrganization({ name: wanted }),
      (created) => ({ message: t("toast.added", { name: wanted }), undo: () => api.removeOrganization(created.id) }),
    );
    if (done) stop();
  };
  return (
    <section className="panel-section" aria-labelledby="organizations-title">
      <div className="heading">
        <h2 id="organizations-title">{t("setup.organizations")}</h2>
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("setup.add_organization")}
          </button>
        )}
      </div>
      {adding && (
        <form
          className="panel setup-form"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") stop();
          }}
        >
          <Field id="org-new" label={t("setup.organization_name")} value={name} onChange={setName} required autoFocus />
          <div className="row-end">
            <button type="button" className="btn quiet" onClick={stop}>
              {t("action.cancel")}
            </button>
            <button type="submit" className="btn primary" disabled={!name.trim()}>
              {t("setup.add_organization")}
            </button>
          </div>
        </form>
      )}
      {orgs.isPending ? (
        <Skeleton />
      ) : rows.length === 0 ? (
        <p className="empty">{t("setup.no_organizations")}</p>
      ) : (
        <ul className="queue">
          {rows.map((o) => (
            <OrganizationRow key={o.id} org={o} />
          ))}
        </ul>
      )}
    </section>
  );
}

function OrganizationRow(props: { org: S["OrganizationView"] }) {
  const { t, tn } = useWords();
  const act = useAct();
  const o = props.org;
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(o.name);
  const stop = () => {
    setRenaming(false);
    setName(o.name);
  };
  const rename = async () => {
    const wanted = name.trim();
    if (!wanted) return;
    if (wanted === o.name) {
      stop();
      return;
    }
    const done = await act(
      () => api.editOrganization(o.id, { name: wanted }),
      () => ({ message: t("toast.renamed", { name: wanted }), undo: () => api.editOrganization(o.id, { name: o.name }) }),
    );
    if (done) setRenaming(false);
  };
  const menu: MenuAction[] = [
    { id: "rename", label: t("setup.rename"), run: () => setRenaming(true) },
    {
      id: "remove",
      label: t("setup.remove"),
      disabled: o.people > 0,
      reason: t("setup.org_remove_blocked"),
      run: () =>
        void act(
          () => api.removeOrganization(o.id),
          () => ({ message: t("toast.removed", { name: o.name }), undo: () => api.restoreOrganization(o.id) }),
        ),
    },
  ];
  const sub = [o.people > 0 ? tn("setup.org_people", o.people) : "", o.aliases.length ? t("setup.also_called", { names: o.aliases.join(", ") }) : ""]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="line">
      <div className="row">
        <div className="text">
          {renaming ? (
            <form
              className="inline-field"
              onSubmit={(e) => {
                e.preventDefault();
                void rename();
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") stop();
              }}
            >
              <label className="sr" htmlFor={`org-rename-${o.id}`}>
                {t("setup.organization_name")}
              </label>
              <input
                id={`org-rename-${o.id}`}
                type="text"
                value={name}
                autoFocus
                autoComplete="off"
                required
                onChange={(e) => setName(e.target.value)}
              />
              <button type="submit" className="btn primary" disabled={!name.trim()}>
                {t("setup.save")}
              </button>
              <button type="button" className="btn quiet" onClick={stop}>
                {t("action.cancel")}
              </button>
            </form>
          ) : (
            <strong>{o.name}</strong>
          )}
          <span className="sub">{sub}</span>
        </div>
        <div className="acts">
          <RowMenu label={o.name} actions={menu} />
        </div>
      </div>
    </li>
  );
}

// ---- projects ------------------------------------------------------------------------------------------------------

function ProjectsPanel(props: { lead?: boolean }) {
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
        {props.lead ? <h1 id="projects-title">{t("setup.projects")}</h1> : <h2 id="projects-title">{t("setup.projects")}</h2>}
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            {t("setup.add_project")}
          </button>
        )}
      </div>
      {adding && <ProjectForm projects={projects.data ?? []} onDone={() => setAdding(false)} />}
      {projects.isPending ? (
        <Skeleton />
      ) : (projects.data ?? []).length === 0 ? (
        <p className="empty">{t("setup.no_projects")}</p>
      ) : (
        <ul className="queue">
          {(projects.data ?? []).map((p) => (
            <ProjectRow
              key={p.id}
              project={p}
              projects={projects.data ?? []}
              notes={(notes.data ?? []).filter((n) => n.project === p.id)}
            />
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

function ProjectRow(props: { project: S["ProjectView"]; projects: S["ProjectView"][]; notes: S["NoteView"][] }) {
  const { t } = useWords();
  const act = useAct();
  const total = useTotal();
  const p = props.project;
  const parent = p.parent ? props.projects.find((x) => x.id === p.parent) : undefined;
  const [editing, setEditing] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const menu: MenuAction[] = [
    {
      id: "notes",
      // With no notes there is no count to give: "Notes (0)" would be a number for nothing.
      label: props.notes.length
        ? t(showNotes ? "setup.notes_hide" : "setup.notes", { n: props.notes.length })
        : t(showNotes ? "setup.notes_hide_plain" : "setup.notes_plain"),
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
    p.priority ? t("setup.priority_is", { priority: p.priority }) : "",
    p.target ? t("setup.target_on", { date: day(p.target) }) : "",
    p.owner_name ? t("setup.owned_by", { name: p.owner_name }) : "",
    p.role !== "run" ? t("setup.role_is", { role: t(`role.${p.role}_short`) }) : "",
    parent ? t("setup.inside_of", { name: parent.name }) : "",
    p.language_own ? t("setup.language_is", { language: p.language }) : "",
    p.budget_usd != null ? t("setup.budget_is", { amount: total(p.budget_usd) }) : "",
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
          <ProjectForm project={p} projects={props.projects} onDone={() => setEditing(false)} />
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

function ProjectForm(props: { project?: S["ProjectView"]; projects: S["ProjectView"][]; onDone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const p = props.project;
  const [name, setName] = useState(p?.name ?? "");
  const [status, setStatus] = useState(p?.status ?? "");
  const [phase, setPhase] = useState(p?.phase ?? "");
  const [group, setGroup] = useState(p?.group ?? "");
  const [priority, setPriority] = useState(p?.priority ?? "");
  const [target, setTarget] = useState(p?.target ?? "");
  const [owner, setOwner] = useState(p?.owner ?? "");
  const [summary, setSummary] = useState(p?.summary ?? "");
  const [parent, setParent] = useState(p?.parent ?? "");
  const [language, setLanguage] = useState(p?.language_own ? p.language : "");
  const [budget, setBudget] = useState(p?.budget_usd != null ? String(p.budget_usd) : "");
  const [role, setRole] = useState<Role>(p?.role ?? "run");
  const key = p?.id ?? "new";
  const others = props.projects.filter((x) => x.id !== p?.id);
  // An empty language means it follows the project it is inside, so that one's language is what the box suggests.
  const inherited = others.find((x) => x.id === parent)?.language ?? (p && !p.language_own ? p.language : "");
  const budgetNumber = budget.trim() === "" ? null : Number(budget);
  const save = async () => {
    const body = {
      parent: parent || null,
      language: language.trim() || null,
      budget_usd: budgetNumber,
      name: name.trim(),
      status: status.trim() || null,
      phase: phase.trim() || null,
      group: group.trim() || null,
      priority: priority.trim() || null,
      target: target || null,
      owner: owner || null,
      summary: summary.trim() || null,
    };
    const before = p && {
      parent: p.parent ?? null,
      language: p.language_own ? p.language : null,
      budget_usd: p.budget_usd ?? null,
      name: p.name,
      status: p.status,
      phase: p.phase,
      group: p.group,
      priority: p.priority ?? null,
      target: p.target,
      owner: p.owner,
      summary: p.summary,
    };
    if (p && role !== p.role) {
      await act(
        () => api.setProjectRole(p.id, role),
        (applied) => ({
          message: t("toast.role_set", { name: p.name, role: t(`role.${role}`) }),
          undo: async () => {
            const report = await api.undo(applied.changeset);
            if (!report.restored.length) throw new Error("not undone");
          },
        }),
      );
      if (JSON.stringify(body) === JSON.stringify(before)) {
        props.onDone();
        return;
      }
    }
    const done = p
      ? await act(
          () => api.editProject(p.id, body),
          () => ({
            message: t("toast.saved", { name: body.name }),
            undo: () => api.editProject(p.id, before!),
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
      <ValueSelect id={`js-${key}`} list={PROJECT_LISTS.status} label={t("setup.status")} value={status} onChange={setStatus} />
      <ValueSelect id={`jp-${key}`} list={PROJECT_LISTS.phase} label={t("setup.phase")} value={phase} onChange={setPhase} />
      <ValueSelect
        id={`jr-${key}`}
        list={PROJECT_LISTS.priority}
        label={t("setup.priority")}
        value={priority}
        onChange={setPriority}
      />
      <ValueSelect
        id={`jg-${key}`}
        list={PROJECT_LISTS.group}
        label={t("setup.group")}
        value={group}
        onChange={setGroup}
        hint={t("setup.group_hint")}
      />
      <PersonPicker
        label={t("setup.owner")}
        value={owner}
        onChange={setOwner}
        suggested={[]}
        people={(people.data ?? []).filter((x) => x.status === "active")}
      />
      {p && (
        <div className="field">
          <label htmlFor={`jo-${key}`}>
            {t("setup.my_role")} <span className="hint">{t("setup.my_role_hint")}</span>
          </label>
          <select id={`jo-${key}`} value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`role.${r}`)}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor={`jw-${key}`}>{t("setup.inside")}</label>
        <select id={`jw-${key}`} value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">{t("setup.inside_none")}</option>
          {others.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`jl-${key}`}>
          {t("setup.language")} <span className="hint">{p && !p.language_own ? t("setup.language_inherited") : t("setup.language_hint")}</span>
        </label>
        <select id={`jl-${key}`} value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="">{inherited ? t("setup.language_same_as", { language: languageLabel(inherited) }) : t("setup.language_same_workspace")}</option>
          {languageChoices([...(settings.data?.items.find((i) => i.key === "workspace.language")?.options ?? []), ...(language ? [language] : [])]).map((c) => (
            <option key={c.tag} value={c.tag}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`jb-${key}`}>
          {t("setup.budget")} <span className="hint">{t("setup.budget_hint")}</span>
        </label>
        <input
          id={`jb-${key}`}
          type="number"
          min="0"
          step="any"
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`jm-${key}`}>{t("setup.summary")}</label>
        <textarea id={`jm-${key}`} className="short" value={summary} onChange={(e) => setSummary(e.target.value)} />
      </div>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!name.trim() || (budgetNumber !== null && !(budgetNumber >= 0))}>
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

// ---- synced folder -------------------------------------------------------------------------------------------------

const SYNC_FOLDER = "storage.sync.folder";
const SYNC_SHARED = "storage.sync.shared";

/** The synced folder isn't set up yet: what it is for, and a way to choose one that is saved like any other setting.
 * Once a folder is chosen it asks whether anyone else can change the files in it, and saves both answers together. */
function SyncUnset(props: { fingerprint: string }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const canList = useFolderListing();
  const [picking, setPicking] = useState(false);
  const [typed, setTyped] = useState("");
  // The folder chosen, waiting for the answer about sharing, and that answer (none until the person gives it).
  const [chosen, setChosen] = useState<string | null>(null);
  const [shared, setShared] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const chooser = useRef<HTMLButtonElement>(null);
  const firstAnswer = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (chosen !== null) firstAnswer.current?.focus();
  }, [chosen]);

  const save = async (path: string, others: boolean) => {
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveSettings({
        changes: { [SYNC_FOLDER]: path.trim(), [SYNC_SHARED]: others },
        reset: [],
        fingerprint: props.fingerprint,
      });
      await afterSave(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  if (chosen !== null) {
    return (
      <form
        className="sync-body"
        onSubmit={(e) => {
          e.preventDefault();
          if (shared !== null) void save(chosen, shared);
        }}
      >
        <p className="path">{t("setup.sync_shared_for", { folder: chosen })}</p>
        <fieldset className="change">
          <legend>{t("setup.sync_shared_title")}</legend>
          <div className="choice-row">
            <label className="check-line">
              <input type="radio" name="sync-shared" ref={firstAnswer} checked={shared === false} onChange={() => setShared(false)} />
              <span>{t("setup.sync_shared_no")}</span>
            </label>
            <label className="check-line">
              <input type="radio" name="sync-shared" checked={shared === true} onChange={() => setShared(true)} />
              <span>{t("setup.sync_shared_yes")}</span>
            </label>
          </div>
          <p className="hint">{t("setup.sync_shared_hint")}</p>
        </fieldset>
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        <div className="row-end">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              setChosen(null);
              setShared(null);
            }}
          >
            {t("setup.sync_shared_back")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || shared === null}>
            {t("setup.sync_shared_save")}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="sync-body">
      <p>{t("setup.sync_unset")}</p>
      {canList ? (
        <div className="row-end">
          <button type="button" className="btn primary" ref={chooser} disabled={busy} onClick={() => setPicking(true)}>
            {t("setup.sync_choose")}
          </button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (typed.trim()) setChosen(typed.trim());
          }}
        >
          <div className="field">
            <label htmlFor="sync-path">{t("setup.sync_path")}</label>
            <div className="inline-field">
              <input id="sync-path" type="text" value={typed} autoComplete="off" onChange={(e) => setTyped(e.target.value)} />
              <button type="submit" className="btn primary" disabled={!typed.trim()}>
                {t("setup.sync_save")}
              </button>
            </div>
          </div>
        </form>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      {picking && (
        <FolderPicker
          onClose={() => {
            setPicking(false);
            restoreFocus(() => chooser.current);
          }}
          onPick={(picked) => {
            setPicking(false);
            setChosen(picked.trim());
          }}
        />
      )}
    </div>
  );
}

/** Whether anyone else can change the folder: a setting the running app takes in at once, saved like any other. */
function SharedSwitch(props: { shared: boolean }) {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fresh = useFreshFingerprint();
  const [problem, setProblem] = useState("");
  const change = async (next: boolean) => {
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes: { [SYNC_SHARED]: next }, reset: [], fingerprint: await fresh() });
      await afterSave(saved);
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    }
  };
  return (
    <div className="field">
      <label className="check-line">
        <input type="checkbox" checked={props.shared} onChange={(e) => void change(e.target.checked)} />
        <span>{t("setup.sync_shared_switch")}</span>
      </label>
      {props.shared && <p className="hint">{t("setup.sync_shared_on")}</p>}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

function SyncPanel() {
  const { t, tn } = useWords();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const saved = settings.data?.items.find((i) => i.key === SYNC_FOLDER)?.value;
  const folderSet = typeof saved === "string" && saved.trim() !== "";
  // Nothing is asked of the sync route until a folder is set; a failed answer is retried quietly before it is shown.
  const sync = useQuery({
    queryKey: ["sync"],
    queryFn: api.sync,
    enabled: folderSet,
    retry: 3,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4000),
  });
  const { open, dialog } = useTextReview();
  const data = sync.data;
  return (
    <section className="panel-section" aria-labelledby="sync-title">
      <div className="heading">
        <h2 id="sync-title">{t("setup.sync")}</h2>
      </div>
      {settings.isPending || (folderSet && sync.isPending) ? (
        <Skeleton />
      ) : settings.isError ? (
        <p className="empty">
          {t("setup.sync_failed")}{" "}
          <button type="button" className="btn" onClick={() => void settings.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : !folderSet ? (
        <SyncUnset fingerprint={settings.data!.fingerprint} />
      ) : sync.isError || !data ? (
        <p className="empty">
          {t("setup.sync_failed")}{" "}
          <button type="button" className="btn" onClick={() => void sync.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : !data.folder ? (
        <p className="empty">{t("setup.sync_off")}</p>
      ) : (
        <div className="sync-body">
          <p>{t("setup.sync_in", { folder: data.folder })}</p>
          <SharedSwitch shared={data.shared} />
          {data.handover && (
            <p>
              <a className="btn primary" href={viewHref("handover")}>
                {t("setup.sync_handover")}
              </a>
            </p>
          )}
          {data.stopped && (
            <p className="problem-note" role="alert">
              {t("setup.sync_stopped")}
            </p>
          )}
          {data.problem && (
            <p className="problem-note" role="alert">
              {t("setup.sync_problem", { problem: data.problem })}
            </p>
          )}
          {data.changed_outside.length > 0 && <p className="hint">{tn("setup.sync_changed", data.changed_outside.length)}</p>}
          {data.removed_outside.length > 0 && <p className="hint">{tn("setup.sync_removed", data.removed_outside.length)}</p>}
          {data.outside_edits.length > 0 && (
            <section aria-labelledby="sync-edits">
              <h3 id="sync-edits" className="what">
                {t("setup.sync_edits")}
              </h3>
              {data.shared && <p className="hint">{t("setup.sync_edits_shared")}</p>}
              <ul className="queue">
                {data.outside_edits.map((edit) => (
                  <OutsideEdit key={edit.path} edit={edit} onReview={open} />
                ))}
              </ul>
            </section>
          )}
          {data.conflict_copies.length > 0 && (
            <section aria-labelledby="sync-copies">
              <h3 id="sync-copies" className="what">
                {t("setup.sync_copies")}
              </h3>
              <ul className="plain-list">
                {data.conflict_copies.map((path) => (
                  <li key={path} className="path">
                    {path}
                  </li>
                ))}
              </ul>
              <p className="hint">{t("setup.sync_copies_note")}</p>
            </section>
          )}
        </div>
      )}
      {dialog}
    </section>
  );
}

function OutsideEdit(props: { edit: S["OutsideEditView"]; onReview: (version: string, returnTo?: () => HTMLElement | null | undefined) => void }) {
  const { t } = useWords();
  const { edit } = props;
  const button = useRef<HTMLButtonElement>(null);
  return (
    <li className="line">
      <div className="row">
        <div className="text">
          <strong className="path">{edit.path}</strong>
          {edit.problem && <span className="sub">{edit.problem}</span>}
          {!edit.version && !edit.problem && <span className="sub">{t("setup.sync_waiting")}</span>}
        </div>
        {edit.version && (
          <div className="acts">
            <button
              type="button"
              className="btn primary"
              ref={button}
              aria-label={t("panel.action_for", { action: t("setup.sync_review"), what: edit.path })}
              onClick={() => props.onReview(edit.version!, () => button.current)}
            >
              {t("setup.sync_review")}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

// ---- scheduled work ------------------------------------------------------------------------------------------------

const OUTCOMES: Record<string, string> = { ok: "setup.job_ok", failed: "setup.job_failed" };

function JobsPanel() {
  const { t, tn } = useWords();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  const rows = jobs.data ?? [];
  if (rows.length === 0) return null;
  return (
    <section className="panel-section" aria-labelledby="jobs-title">
      <div className="heading">
        <h2 id="jobs-title">{t("setup.jobs")}</h2>
      </div>
      <ul className="queue">
        {rows.map((job) => {
          const outcome = job.last_outcome ? t(OUTCOMES[job.last_outcome] ?? "setup.job_other", { outcome: readable(job.last_outcome) }) : "";
          const last = job.last_run_at ? t("setup.job_last", { when: dayAndTime(job.last_run_at), outcome }) : t("setup.job_never");
          return (
            <li className="line" key={job.name}>
              <div className="row">
                <span className={`kind ${job.enabled ? "k-send" : "k-done"}`}>{t(job.enabled ? "setup.job_on" : "setup.job_off")}</span>
                <div className="text">
                  <strong>{readableTail(job.name)}</strong>
                  <span className="sub">{tn("setup.job_every", job.every_minutes)}</span>
                  <span className="sub">{last}</span>
                  {job.last_error && <span className="sub problem-note">{job.last_error}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
