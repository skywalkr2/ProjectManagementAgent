// The to-dos and questions screen's filters, in one place so the screen and its tests agree (design 7.5): a list is
// narrowed by project, by person and by state, each chosen from a list built from what is open, never typed.
import type { S } from "./api";

export type OpenAction = S["OpenActionView"];
export type OpenQuestion = S["OpenQuestionView"];

export interface Filters {
  project: string;
  person: string;
  state: string;
}

export const NO_FILTERS: Filters = { project: "", person: "", state: "" };

/** The states an action can be filtered by, in the order the list offers them. */
export const ACTION_STATES: ReadonlyArray<OpenAction["state"]> = ["overdue", "stale", "on_hold", "no_owner"];
/** The states a question can be filtered by. */
export const QUESTION_STATES: ReadonlyArray<OpenQuestion["state"]> = ["yours", "waiting", "not_sent", "later"];

// A Today line that sends the person here with a state already chosen ("Look over" on the stale to-dos) leaves it here
// for the screen that mounts next, which takes it once.
let pending: Partial<Filters> | null = null;

export function chooseFilters(filters: Partial<Filters>): void {
  pending = filters;
}

export function takeFilters(): Filters {
  const now = { ...NO_FILTERS, ...(pending ?? {}) };
  pending = null;
  return now;
}

export function actionsShown(rows: OpenAction[], f: Filters): OpenAction[] {
  return rows.filter(
    (a) =>
      (!f.project || a.project === f.project) &&
      (!f.person || a.owners.some((o) => o.person === f.person)) &&
      (!f.state || a.state === f.state),
  );
}

export function questionsShown(rows: OpenQuestion[], f: Filters): OpenQuestion[] {
  return rows.filter(
    (q) =>
      (!f.project || (q.projects ?? []).includes(f.project)) &&
      (!f.person || q.to === f.person) &&
      (!f.state || q.state === f.state),
  );
}

/** The owners an action has after one owner is replaced by another: the new person acts for the team the old one did, the
 * others stay, and a person already among them is not listed twice. With one owner the new person simply takes over. */
export function ownersAfter(owners: OpenAction["owners"], from: string, to: string): Array<{ person: string; team?: string }> {
  const out: Array<{ person: string; team?: string }> = [];
  for (const o of owners) {
    const person = o.person === from ? to : o.person;
    if (out.some((x) => x.person === person)) continue;
    out.push(o.team ? { person, team: o.team } : { person });
  }
  return out;
}
