// The navigation (design 7.1): the groups and the bottom entries are fixed, and a plugin's panel adds an entry only under
// Work (its tab is `work`) or Records (`people`). Panels for Settings and Today do not appear here. The counts come from
// the queries the screens already make.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { panelView, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { needsAttention } from "../components/WhatChanged";
import type { IconName } from "../ui/Icon";

export interface NavEntry {
  view: View;
  label: string;
  icon?: IconName;
  /** A plugin's panel has no icon of its own: its first letter stands in. */
  glyph?: string;
  count?: number | null;
}

export interface NavModel {
  today: NavEntry;
  work: NavEntry[];
  records: NavEntry[];
  bottom: NavEntry[];
}

/** How many things wait: changes that need a look, and follow-ups still to send. Null until the queries have answered. */
export function useCounts(): { changed: number | null; followups: number | null } {
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  const followups = useQuery({ queryKey: ["followups"], queryFn: api.followups });
  return {
    changed: changes.data ? changes.data.filter(needsAttention).length : null,
    followups: followups.data ? followups.data.reduce((n, s) => n + s.to_send, 0) : null,
  };
}

const some = (n: number | null): number | null => (n ? n : null);

export function useNav(): NavModel {
  const { t } = useWords();
  const panels = useQuery({ queryKey: ["panels"], queryFn: () => api.panels() });
  const counts = useCounts();
  const plugin = (tab: string, group: "work" | "records"): NavEntry[] =>
    (panels.data ?? [])
      .filter((p: S["PanelView"]) => p.tab === tab)
      .map((p) => ({ view: panelView(p.name, group), label: p.title, glyph: [...p.title.trim()][0]?.toUpperCase() ?? "" }));
  const today = (counts.changed ?? 0) + (counts.followups ?? 0);
  return {
    today: { view: "today", label: t("nav.home"), icon: "home", count: some(today) },
    work: [
      { view: "work/changed", label: t("nav.changed"), icon: "inbox", count: some(counts.changed) },
      { view: "work/followups", label: t("nav.followups"), icon: "send", count: some(counts.followups) },
      { view: "work/outgoing", label: t("nav.outgoing"), icon: "upload" },
      { view: "work/stages", label: t("nav.stages"), icon: "layers" },
      ...plugin("work", "work"),
    ],
    records: [
      { view: "records/projects", label: t("nav.projects"), icon: "grid" },
      { view: "records/people", label: t("nav.people"), icon: "users" },
      { view: "records/files", label: t("nav.files"), icon: "folder" },
      { view: "records/knowledge", label: t("nav.knowledge"), icon: "book" },
      ...plugin("people", "records"),
    ],
    bottom: [
      { view: "sources", label: t("nav.sources"), icon: "rss" },
      { view: "addons", label: t("nav.addons"), icon: "puzzle" },
      { view: "settings", label: t("nav.settings"), icon: "gear" },
    ],
  };
}
