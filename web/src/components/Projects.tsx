// Projects (design 7.13, 7.14): the portfolio as a table, grouped by the configured grouping, with what the assistant filed
// under no project gathered above it and the finished ones under Completed at the end (kept, with their group, never
// removed). A row opens its detail pane beside the table (a drawer on a narrower window); the name opens the project's page.
// Adding and editing happen in a drawer.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, dayAndTime, monthDay } from "../lib/dates";
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

type Project = S["ProjectView"];

/** The projects in groups: each configured group in turn, those with none, and last the finished ones. */
export function groupProjects(projects: Project[], labels: { none: string; open: string; completed: string }): TableGroup<Project>[] {
  const live = projects.filter((p) => !p.completed);
  const named = [...new Set(live.map((p) => p.group).filter((g): g is string => !!g))].sort((a, b) => a.localeCompare(b));
  const byName = (a: Project, b: Project) => a.name.localeCompare(b.name);
  const groups: TableGroup<Project>[] = named.map((g) => ({ id: `group:${g}`, title: g, rows: live.filter((p) => p.group === g).sort(byName) }));
  const rest = live.filter((p) => !p.group).sort(byName);
  if (rest.length) groups.push({ id: "open", title: named.length ? labels.none : labels.open, rows: rest });
  const done = projects.filter((p) => p.completed).sort(byName);
  if (done.length) groups.push({ id: "completed", title: labels.completed, rows: done });
  return groups;
}

export function Projects() {
  const { t, tn } = useWords();
  const act = useAct();
  const total = useTotal();
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

  const columns: TableColumn<Project>[] = [
    { id: "group", header: t("projects.col.group"), rank: 2, cell: (p) => p.group ?? "" },
    { id: "status", header: t("setup.status"), rank: 1, cell: (p) => (p.status ? <Pill tone={p.status_tone ?? "neutral"}>{p.status}</Pill> : "") },
    { id: "phase", header: t("setup.phase"), rank: 3, cell: (p) => p.phase ?? "" },
    { id: "target", header: t("projects.col.target"), rank: 2, cell: (p) => (p.target ? day(p.target) : "") },
    { id: "owner", header: t("setup.owner"), rank: 2, cell: (p) => p.owner_name ?? "" },
    { id: "actions", header: t("projects.col.actions"), rank: 1, numeric: true, cell: (p) => (p.open_actions > 0 ? p.open_actions : "") },
    { id: "questions", header: t("projects.col.questions"), rank: 3, numeric: true, cell: (p) => (p.open_questions > 0 ? p.open_questions : "") },
    { id: "changed", header: t("projects.col.changed"), rank: 3, cell: (p) => (p.last_change ? monthDay(p.last_change) : "") },
  ];

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
                cell: (p) => (
                  <>
                    <a href={viewHref(recordView("project", p.id))}>{p.name}</a>
                    {p.completed && p.group && <div className="hint">{t("projects.was_in", { group: p.group })}</div>}
                    {p.parent && byId.get(p.parent) && <div className="hint">{t("setup.inside_of", { name: byId.get(p.parent)!.name })}</div>}
                  </>
                ),
              }}
              columns={columns}
              groups={groupProjects(all, { none: t("projects.group.none"), open: t("projects.group.open"), completed: t("projects.group.completed") })}
              rowKey={(p) => p.id}
              selected={chosen}
              onSelect={(p) => setChosen(p.id)}
              actionsHeader={t("people.col.actions")}
              actions={(p) => (
                <>
                  <Button size="sm" variant="primary" data-key="primary" aria-label={t("panel.action_for", { action: t("records.details"), what: p.name })} onClick={() => setChosen(p.id)}>
                    {t("records.details")}
                  </Button>
                  <RowMenu label={p.name} actions={menu(p)} />
                </>
              )}
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
