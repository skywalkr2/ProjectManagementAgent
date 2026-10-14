// What the Knowledge screen shows of an entry or a rule (design 7.18): one shape for both, and the plain words for where it
// came from, what it reaches and how much it was used. No text is built here that the wording sheet could say.
import type { S } from "./api";
import type { useWords } from "./wording";

type T = ReturnType<typeof useWords>;

export const KINDS = ["rule", "lesson", "glossary_entry", "routing_entry", "style_note"] as const;
export type Kind = (typeof KINDS)[number];
export type Status = S["KnowledgeView"]["status"];
export const FILTERS = ["proposed", "active", "unused", "retired"] as const;
export type Filter = (typeof FILTERS)[number];

/** An entry or a rule, in one shape. */
export interface Item {
  id: string;
  kind: Kind;
  version: number;
  text: string;
  status: Status;
  learnedFrom: S["KnowledgeView"]["learned_from"] | S["RuleView"]["learned_from"];
  untrusted: boolean;
  scope: S["Scope"];
  used: number;
  given: number;
  lastUsed: string | null;
  learnedAt: string;
  /** A code check enforces the rule, so it holds whether or not anything triggers it. */
  enforced: boolean;
  origin: S["Origin"] | null;
}

/** Every entry and rule as items, newest first. */
export function itemsOf(entries: S["KnowledgeView"][], rules: S["RuleView"][]): Item[] {
  const found: Item[] = [
    ...entries.map((e) => ({
      id: e.id,
      kind: e.kind,
      version: e.version,
      text: e.text,
      status: e.status,
      learnedFrom: e.learned_from,
      untrusted: e.trust === "untrusted",
      scope: e.applies_to,
      used: e.used ?? 0,
      given: e.given ?? 0,
      lastUsed: e.last_used ?? null,
      learnedAt: e.learned_at,
      enforced: false,
      origin: e.origin ?? null,
    })),
    ...rules.map((r) => ({
      id: r.id,
      kind: "rule" as const,
      version: r.version,
      text: r.text || r.name,
      status: r.status,
      learnedFrom: r.learned_from,
      untrusted: r.trust === "untrusted",
      scope: r.applies_to,
      used: r.used ?? 0,
      given: r.given ?? 0,
      lastUsed: r.last_used ?? null,
      learnedAt: r.learned_at ?? "",
      enforced: r.enforced,
      origin: r.origin ?? null,
    })),
  ];
  return found.sort((a, b) => (a.learnedAt === b.learnedAt ? b.id.localeCompare(a.id) : a.learnedAt < b.learnedAt ? 1 : -1));
}

/** Which filters an item is in: unused means active and never applied by a run. */
export function inFilter(item: Item, filter: Filter): boolean {
  if (filter === "unused") return item.status === "active" && item.used === 0;
  return item.status === filter;
}

export function counts(items: Item[]): Record<Filter, number> {
  return Object.fromEntries(FILTERS.map((f) => [f, items.filter((i) => inFilter(i, f)).length])) as Record<Filter, number>;
}

/** "today", "yesterday", "3 days ago" or "2 months ago". */
export function agoWords(iso: string, now: Date, { t }: T): string {
  const days = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000));
  if (days === 0) return t("knowledge.ago.today");
  if (days === 1) return t("knowledge.ago.yesterday");
  if (days < 60) return t("knowledge.ago.days", { n: days });
  return t("knowledge.ago.months", { n: Math.floor(days / 30) });
}

/** "Used 12 times · last 2 days ago", or "Never used". */
export function usedWords(item: Pick<Item, "used" | "lastUsed">, now: Date, words: T): string {
  if (item.used === 0) return words.t("knowledge.never_used");
  return words.tn("knowledge.used", item.used, { when: item.lastUsed ? agoWords(item.lastUsed, now, words) : words.t("knowledge.ago.unknown") });
}

const list = (names: string[]) => names.join(", ");

/** What an item reaches, in words: "All projects except Apollo, Borealis", "Only Apollo", plus the kinds of work and the
 * people it is limited to. */
export function reachWords(
  scope: S["Scope"],
  names: { projects: Map<string, string>; people: Map<string, string> },
  words: T,
): string {
  const { t, has } = words;
  const project = (id: string) => names.projects.get(id) ?? t("knowledge.reach.removed_project");
  const parts: string[] = [];
  if (scope.scope === "projects") parts.push(t("knowledge.reach.only", { names: list((scope.projects ?? []).map(project)) }));
  else if ((scope.except ?? []).length) parts.push(t("knowledge.reach.except", { names: list((scope.except ?? []).map(project)) }));
  else parts.push(t("knowledge.reach.all"));
  if ((scope.task_kinds ?? []).length) {
    const work = (scope.task_kinds ?? []).map((k) => (has(`task.${k}`) ? t(`task.${k}`) : t("task.other")));
    parts.push(t("knowledge.reach.work", { names: list([...new Set(work)]) }));
  }
  if ((scope.people ?? []).length) {
    parts.push(t("knowledge.reach.people", { names: list((scope.people ?? []).map((p) => names.people.get(p) ?? t("knowledge.reach.removed_person"))) }));
  }
  if ((scope.records ?? []).length) parts.push(t("knowledge.reach.records"));
  return parts.join(" · ");
}
