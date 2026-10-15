// How far a piece of what the assistant learned reaches (design 7.18). A proposal starts at the narrowest reach its
// correction supports; widening is a pick from a short list built from that reach, never typed. Narrowing an entry that
// already applies leaves one project out of it.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "./api";
import { useWords } from "./wording";
import { useTaskWords } from "./stages";

type Scope = S["Scope"];

/** One reach to pick: the target it sets, and the parts its words are made of. */
export interface ReachChoice {
  id: "proposed" | "all-projects" | "all-work" | "everywhere";
  scope: Scope;
  kinds: string[];
  where: { mode: "projects" | "except" | "everywhere"; projects: string[] };
}

const key = (scope: Scope) =>
  JSON.stringify([
    [...(scope.task_kinds ?? [])].sort(),
    scope.scope ?? "workspace",
    [...(scope.projects ?? [])].sort(),
    [...(scope.except ?? [])].sort(),
  ]);

function describe(id: ReachChoice["id"], scope: Scope): ReachChoice {
  const projects = scope.scope === "projects" ? (scope.projects ?? []) : [];
  const left = scope.scope === "projects" ? [] : (scope.except ?? []);
  return {
    id,
    scope,
    kinds: scope.task_kinds ?? [],
    where: projects.length ? { mode: "projects", projects } : left.length ? { mode: "except", projects: left } : { mode: "everywhere", projects: [] },
  };
}

/** The reaches to pick from for a target, narrowest first (the target as it stands): the same kind of work on every
 * project, any kind of work on the same projects, and everywhere. A reach that says the same as an earlier one is left
 * out. People and record targets stay as they were. */
export function reachChoices(scope: Scope): ReachChoice[] {
  const kinds = scope.task_kinds ?? [];
  const onProjects = scope.scope === "projects";
  const everyProject: Scope = { ...scope, scope: "workspace", projects: [], except: [] };
  const candidates: Array<[ReachChoice["id"], Scope]> = [["proposed", scope]];
  if (kinds.length && onProjects) candidates.push(["all-projects", everyProject]);
  if (kinds.length) candidates.push(["all-work", { ...scope, task_kinds: [] }]);
  candidates.push(["everywhere", { ...everyProject, task_kinds: [] }]);
  const seen = new Set<string>();
  const out: ReachChoice[] = [];
  for (const [id, target] of candidates) {
    if (seen.has(key(target))) continue;
    seen.add(key(target));
    out.push(describe(id, target));
  }
  return out;
}

/** The target without one project: an entry for a list of projects loses it from the list, one for the whole workspace
 * gains it in its exceptions. None when that changes nothing, or leaves no project at all. */
export function narrowedWithout(scope: Scope, project: string): Scope | null {
  if (scope.scope === "projects") {
    const rest = (scope.projects ?? []).filter((p) => p !== project);
    return rest.length && rest.length !== (scope.projects ?? []).length ? { ...scope, projects: rest } : null;
  }
  const left = scope.except ?? [];
  return left.includes(project) ? null : { ...scope, except: [...left, project] };
}

/** Whether a project can still be left out of a target. */
export function canLeaveOut(scope: Scope, project: string): boolean {
  return narrowedWithout(scope, project) !== null;
}

/** The words for a reach, with the projects named. */
export function useReachWords(names: (id: string) => string): (choice: ReachChoice) => string {
  const { t } = useWords();
  const task = useTaskWords();
  return (choice) => {
    const kinds = choice.kinds.length ? choice.kinds.map(task).join(", ") : t("reach.all_work");
    const list = choice.where.projects.map(names).join(", ");
    const where =
      choice.where.mode === "projects"
        ? t("reach.on_projects", { names: list })
        : choice.where.mode === "except"
          ? t("reach.every_except", { names: list })
          : t("reach.every_project");
    const label = t("reach.label", { kinds, where });
    return label.charAt(0).toUpperCase() + label.slice(1);
  };
}

/** The names a line needs to say what something reaches: every project and person, by id. */
export function useReachNames() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  return {
    projectList: projects.data ?? [],
    names: {
      projects: new Map((projects.data ?? []).map((p) => [p.id, p.name])),
      people: new Map((people.data ?? []).map((p) => [p.id, p.name])),
    },
  };
}
