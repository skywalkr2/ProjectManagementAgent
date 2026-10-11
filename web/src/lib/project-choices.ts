// The projects a person can pick from when saying what something is about: every project, a project inside another
// shown after it as "Parent › Child", in the order the workspace lists them. A project's status is the person's own
// words, so none is guessed to be over.
import type { S } from "./api";

export interface ProjectChoice {
  id: string;
  label: string;
}

export function projectChoices(projects: S["ProjectView"][], path: (parent: string, name: string) => string): ProjectChoice[] {
  const byId = new Map(projects.map((p) => [p.id, p]));
  const children = new Map<string | null, S["ProjectView"][]>();
  for (const p of projects) {
    const parent = p.parent && byId.has(p.parent) && p.parent !== p.id ? p.parent : null;
    children.set(parent, [...(children.get(parent) ?? []), p]);
  }
  const out: ProjectChoice[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, prefix: string) => {
    for (const p of children.get(parent) ?? []) {
      if (seen.has(p.id)) continue;
      seen.add(p.id);
      const label = prefix ? path(prefix, p.name) : p.name;
      out.push({ id: p.id, label });
      walk(p.id, label);
    }
  };
  walk(null, "");
  return out;
}
