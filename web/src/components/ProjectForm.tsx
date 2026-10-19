// A project's form, in a drawer from the right so the list or screen it was opened from stays in view (design 7.14). It adds a
// project or edits one; both act at once with Undo. `onSaved` hears the project's id, so a picker can select the project
// that was just added without the person leaving the screen.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useFirstField } from "../lib/focus";
import { languageChoices, languageLabel } from "../lib/languages";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { Field } from "./PersonForm";
import { PersonPicker } from "./PersonPicker";
import { ValueSelect } from "./ValueSelect";

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

export function ProjectDrawer(props: {
  project?: S["ProjectView"];
  onClose: () => void;
  onSaved?: (id: string, name: string) => void;
}) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const all = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const p = props.project;
  const first = useFirstField<HTMLFormElement>();
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
  const others = (all.data ?? []).filter((x) => x.id !== p?.id);
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
        props.onClose();
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
    if (!done) return;
    props.onSaved?.(p?.id ?? (done as S["Created"]).id, body.name);
    props.onClose();
  };
  const dirty =
    p === undefined
      ? [name, status, phase, group, priority, target, owner, summary, parent, language, budget].some((v) => v !== "")
      : name !== p!.name ||
        status !== (p!.status ?? "") ||
        phase !== (p!.phase ?? "") ||
        group !== (p!.group ?? "") ||
        priority !== (p!.priority ?? "") ||
        target !== (p!.target ?? "") ||
        owner !== (p!.owner ?? "") ||
        summary !== (p!.summary ?? "") ||
        parent !== (p!.parent ?? "") ||
        language !== (p!.language_own ? p!.language : "") ||
        budget !== (p!.budget_usd != null ? String(p!.budget_usd) : "") ||
        role !== p!.role;
  const formId = `project-form-${key}`;
  const invalid = !name.trim() || (budgetNumber !== null && !(budgetNumber >= 0));
  return (
    <Drawer
      open
      title={t(p ? "project.edit_title" : "project.add_title")}
      dirty={dirty}
      wide
      onClose={props.onClose}
      footer={
        <>
          <Button onClick={props.onClose}>{t("action.cancel")}</Button>
          <Button
            variant="primary"
            type="submit"
            form={formId}
            disabled={invalid}
            reason={t(!name.trim() ? "setup.name_missing" : "setup.budget_invalid")}
          >
            {t(p ? "setup.save" : "setup.add_project")}
          </Button>
        </>
      }
    >
    <form
      id={formId}
      ref={first}
      className="setup-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <Field id={`jn-${key}`} label={t("setup.project_name")} value={name} onChange={setName} required />
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
    </form>
    </Drawer>
  );
}

