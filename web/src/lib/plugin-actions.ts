// What a person can start on an item or on the whole workspace, offered by the enabled plugins: person actions and
// kinds of AI work, both as {name, label}.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

/** The actions for one item; with no item, the ones that work on the whole workspace. */
export function usePluginActions(kind?: string, id?: string, enabled = true) {
  return useQuery({
    queryKey: ["plugin-actions", kind ?? null, id ?? null],
    queryFn: () => api.pluginActions(kind, id),
    enabled,
  });
}

/** The kinds of AI work the person can start on one item (or on the whole workspace with no item). */
export function useTaskKinds(kind?: string, id?: string, enabled = true) {
  return useQuery({
    queryKey: ["task-kinds", kind ?? null, id ?? null],
    queryFn: () => api.taskKinds(kind, id),
    enabled,
  });
}

/** Something the person can start: a person action (reviewed, then applied) or a kind of work (started at once). */
export interface Offer {
  name: string;
  label: string;
  is: "action" | "task";
  /** The kind of record it is for, or null for the whole workspace. */
  on: string | null;
}

/** Turn names (a panel's primary and row actions) into offers by looking them up among what is offered on the item:
 * a person action when it is listed as one, otherwise a kind of work. A name offered as neither is not shown. */
export function resolveOffers(
  names: Array<string | null | undefined>,
  actions: Array<{ name: string; label: string; on?: string | null }>,
  tasks: Array<{ name: string; label: string; on?: string | null }>,
): Offer[] {
  const seen = new Set<string>();
  const found: Offer[] = [];
  for (const name of names) {
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const action = actions.find((a) => a.name === name);
    const task = tasks.find((k) => k.name === name);
    if (action) found.push({ name, label: action.label, is: "action", on: action.on ?? null });
    else if (task) found.push({ name, label: task.label, is: "task", on: task.on ?? null });
  }
  return found;
}
