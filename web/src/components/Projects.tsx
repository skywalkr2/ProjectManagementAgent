// Projects (design 7.13, 7.14): the portfolio as a table, grouped by the configured grouping, with what the assistant filed
// under no project gathered above it and the finished ones under Completed at the end (kept, with their group, never
// removed). A row, Enter on it or its name opens the detail pane beside the table (over it when the priority columns would
// not fit, a drawer on a narrower window); the name's link is the project's page for a new tab. Adding and editing happen in a
// drawer.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useAgo } from "../lib/ago";
import { day, dayAndTime } from "../lib/dates";
import { useTotal } from "../lib/money";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { ListDetail } from "../ui/ListDetail";
import { Pill } from "../ui/Pill";
import { RecordsTable, type TableColumn, type TableGroup } from "../ui/RecordsTable";
import { Skeleton } from "../ui/Skeleton";
import { ProjectDrawer } from "./ProjectForm";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";
import { Unfiled } from "./Unfiled";
import styles from "./Projects.module.css";

type Project = S["ProjectView"];

/** The projects in groups: each configured group in turn, those with none, and last the finished ones. A project inside
 * another that is also listed follows it right away, whatever group it has itself; what is inside that follows in turn. */
export function groupProjects(projects: Project[], labels: { none: string; open: string; completed: string }): TableGroup<Project>[] {
  const byName = (a: Project, b: Project) => a.name.localeCompare(b.name);
  const nest = (set: Project[]): Project[] => {
    const ids = new Set(set.map((p) => p.id));
    const inside = (parent: string) => set.filter((p) => p.parent === parent).sort(byName);
    const walk = (p: Project, seen: Set<string>): Project[] => (seen.has(p.id) ? [] : [p, ...inside(p.id).flatMap((c) => walk(c, new Set([...seen, p.id])))]);
    // A project listed with the one it is inside is not a top row of its own (a cycle keeps every project listed once).
    const listed = set.filter((p) => !p.parent || !ids.has(p.parent) || p.parent === p.id).sort(byName).flatMap((p) => walk(p, new Set()));
    const shown = new Set(listed.map((p) => p.id));
    return [...listed, ...set.filter((p) => !shown.has(p.id)).sort(byName)];
  };
  const live = projects.filter((p) => !p.completed);
  const liveById = new Map(live.map((p) => [p.id, p]));
  // A project is in the group of the top project it is inside (a cycle stops at the first project seen twice).
  const top = (p: Project, seen: Set<string> = new Set()): Project => {
    const parent = p.parent ? liveById.get(p.parent) : undefined;
    return parent && !seen.has(p.id) ? top(parent, new Set([...seen, p.id])) : p;
  };
  const groupOf = (p: Project) => top(p).group ?? null;
  const named = [...new Set(live.map(groupOf).filter((g): g is string => !!g))].sort((a, b) => a.localeCompare(b));
  const groups: TableGroup<Project>[] = named.map((g) => ({ id: `group:${g}`, title: g, rows: nest(live.filter((p) => groupOf(p) === g)) }));
  const rest = nest(live.filter((p) => !groupOf(p)));
  if (rest.length) groups.push({ id: "open", title: named.length ? labels.none : labels.open, rows: rest });
  const done = projects.filter((p) => p.completed).sort(byName);
  if (done.length) groups.push({ id: "completed", title: labels.completed, rows: done });
  return groups;
}

/** The width the priority columns (name, status, target, owner, open to-dos and the menu) need beside the pane. */
const PROJECTS_FIT = 640;

export function Projects() {
  const { t, tn } = useWords();
  const act = useAct();
  const total = useTotal();
  const ago = useAgo();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const all = projects.data ?? [];
  const selected = all.find((p) => p.id === chosen) ?? null;
  const byId = new Map(all.map((p) => [p.id, p]));

  const menu = (p: Project): MenuAction[] => [
    { id: "edit", label: t("setup.edit"), run: () => setEditing(p) },
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

  // Projects at a glance: the stage, the target day and when it was last updated come first. A health column is for a pack
  // that provides one; the core has none.
  const columns: TableColumn<Project>[] = [
    { id: "status", header: t("setup.status"), rank: 1, core: true, cell: (p) => (p.status ? <Pill tone={p.status_tone ?? "neutral"}>{p.status}</Pill> : "") },
    { id: "stage", header: t("projects.col.stage"), rank: 1, cell: (p) => p.phase ?? "" },
    { id: "target", header: t("projects.col.target"), rank: 1, core: true, cell: (p) => (p.target ? day(p.target) : "") },
    { id: "updated", header: t("projects.col.updated"), rank: 2, cell: (p) => ago(p.last_change) },
    { id: "group", header: t("projects.col.group"), rank: 2, cell: (p) => p.group ?? "" },
    { id: "owner", header: t("setup.owner"), rank: 2, core: true, cell: (p) => p.owner_name ?? "" },
    { id: "actions", header: t("projects.col.actions"), rank: 1, core: true, numeric: true, cell: (p) => (p.open_actions > 0 ? p.open_actions : "") },
    { id: "questions", header: t("projects.col.questions"), rank: 3, numeric: true, cell: (p) => (p.open_questions > 0 ? p.open_questions : "") },
  ];
  // How deep a project sits inside the ones listed with it, for the indent.
  const depth = (p: Project, seen: Set<string> = new Set()): number => {
    const parent = p.parent && !p.completed ? byId.get(p.parent) : undefined;
    return parent && !parent.completed && !seen.has(p.id) ? 1 + depth(parent, new Set([...seen, p.id])) : 0;
  };

  return (
    <section className="panel-section" aria-labelledby="projects-title">
      <div className="heading">
        <h1 id="projects-title">{t("setup.projects")}</h1>
        <Button variant="primary" onClick={() => setAdding(true)}>
          {t("setup.add_project")}
        </Button>
      </div>
      <Unfiled />
      <ListDetail
        title={selected?.name ?? ""}
        onClose={() => setChosen(null)}
        fit={PROJECTS_FIT}
        detail={selected ? <ProjectDetail project={selected} parent={selected.parent ? byId.get(selected.parent) : undefined} total={total} onEdit={() => setEditing(selected)} /> : null}
      >
        {projects.isPending ? (
          <Skeleton />
        ) : all.length === 0 ? (
          <EmptyState text={t("setup.no_projects")} action={{ label: t("setup.add_project"), onClick: () => setAdding(true) }} />
        ) : (
          <>
            <RecordsTable
              label={t("setup.projects")}
              name={{
                header: t("projects.col.name"),
                cell: (p, open) => (
                  <span className={styles.inside} data-depth={depth(p)} style={{ "--depth": depth(p) } as React.CSSProperties}>
                    <a href={viewHref(recordView("project", p.id))} onClick={open}>
                      {p.name}
                    </a>
                    {p.completed && p.group && <div className="hint">{t("projects.was_in", { group: p.group })}</div>}
                    {p.parent && byId.get(p.parent) && <div className="hint">{t("setup.inside_of", { name: byId.get(p.parent)!.name })}</div>}
                  </span>
                ),
              }}
              columns={columns}
              groups={groupProjects(all, { none: t("projects.group.none"), open: t("projects.group.open"), completed: t("projects.group.completed") })}
              rowKey={(p) => p.id}
              selected={chosen}
              onSelect={(p) => setChosen(p.id)}
              actionsHeader={t("people.col.actions")}
              actions={(p) => <RowMenu label={p.name} actions={menu(p)} />}
            />
            <p className="hint">{tn("projects.count", all.length)}</p>
          </>
        )}
      </ListDetail>
      {adding && <ProjectDrawer onClose={() => setAdding(false)} onSaved={(id) => setChosen(id)} />}
      {editing && <ProjectDrawer project={editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function ProjectDetail(props: { project: Project; parent?: Project; total: (n: number) => string; onEdit: () => void }) {
  const { t, tn } = useWords();
  const p = props.project;
  const notes = useQuery({ queryKey: ["notes"], queryFn: api.notes });
  const mine = (notes.data ?? []).filter((n) => n.project === p.id);
  const fact = (label: string, value: React.ReactNode) =>
    value ? (
      <div className="detail">
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>
    ) : null;
  return (
    <>
      <div className="row-end">
        {p.completed && <Pill tone="ok">{t("projects.group.completed")}</Pill>}
        {p.status && !p.completed && <Pill tone={p.status_tone ?? "neutral"}>{p.status}</Pill>}
      </div>
      {p.summary && <SafeText text={p.summary} />}
      <dl className="details-list">
        {fact(t("setup.group"), p.group)}
        {fact(t("setup.phase"), p.phase)}
        {fact(t("setup.priority"), p.priority)}
        {fact(t("projects.col.target"), p.target ? day(p.target) : null)}
        {fact(t("setup.owner"), p.owner_name)}
        {fact(t("setup.inside"), props.parent?.name)}
        {fact(t("setup.my_role"), p.role !== "run" ? t(`role.${p.role}`) : null)}
        {fact(t("setup.budget"), p.budget_usd != null ? t("projects.budget_spent", { budget: props.total(p.budget_usd), spent: props.total(p.spent_usd) }) : null)}
        {fact(t("projects.col.actions"), p.open_actions > 0 ? tn("projects.open_actions", p.open_actions) : null)}
        {fact(t("projects.col.questions"), p.open_questions > 0 ? tn("projects.open_questions", p.open_questions) : null)}
        {fact(t("projects.col.changed"), p.last_change ? dayAndTime(p.last_change) : null)}
      </dl>
      {mine.length > 0 && (
        <section aria-label={t("projects.notes")}>
          <h3 className="what">{t("projects.notes")}</h3>
          <ul className="notes">
            {mine.map((n) => (
              <li key={n.id}>
                <SafeText text={n.text} />
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="row-end">
        <a className="btn" href={viewHref(recordView("project", p.id))}>
          {t("records.open_page", { name: p.name })}
        </a>
        <Button variant="primary" onClick={props.onEdit}>
          {t("setup.edit")}
        </Button>
      </div>
    </>
  );
}
