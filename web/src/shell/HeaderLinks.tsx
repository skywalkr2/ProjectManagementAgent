// Links to the person's own pages (design 7.1, 7.9): the first group of the person's menu ("Your pages"), from the list in
// Settings (a name and a web address each), so the boards and pages they check daily are a click away. Each opens in a new
// tab. Nothing is shown when the list is empty. Only web addresses are offered: an entry that isn't one is left out, never opened.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";
import type { MenuGroup } from "../ui/MenuButton";

export interface PageLink {
  name: string;
  address: string;
}

const WEB = /^https?:\/\/\S+$/i;

/** The links as the settings hold them, keeping only a name with a web address. */
export function pageLinks(value: unknown): PageLink[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry): PageLink[] => {
    const { name, address } = (entry ?? {}) as Record<string, unknown>;
    return typeof name === "string" && name.trim() && typeof address === "string" && WEB.test(address) ? [{ name: name.trim(), address }] : [];
  });
}

/** The person's links, read live from the settings: a change in Settings shows at once. */
export function usePageLinks(): PageLink[] {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return pageLinks(settings.data?.items.find((i) => i.key === "ui.links")?.value);
}

/** The person's pages as the first group of their menu, each opening in a new tab; null when there are none. */
export function usePagesGroup(): MenuGroup | null {
  const { t } = useWords();
  const links = usePageLinks();
  if (links.length === 0) return null;
  return { id: "pages", title: t("header.pages"), entries: links.map((l, i) => ({ id: `link-${i}`, label: l.name, href: l.address })) };
}
