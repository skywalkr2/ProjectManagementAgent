// Links to the person's own pages (design 7.1, 7.9): a "Your pages" menu in the header, from the list in Settings (a name and
// a web address each), so the boards and pages they check daily are one click away. Each opens in a new tab. Nothing is
// shown when the list is empty. Only web addresses are offered: an entry that isn't one is left out, never opened.
import { useQuery } from "@tanstack/react-query";
import { Button as AriaButton } from "react-aria-components";
import { api } from "../lib/api";
import { useWords } from "../lib/wording";
import { MenuButton } from "../ui/MenuButton";
import styles from "./HeaderLinks.module.css";

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

export function HeaderLinks() {
  const { t } = useWords();
  const links = usePageLinks();
  if (links.length === 0) return null;
  return (
    <MenuButton
      groups={[{ id: "pages", entries: links.map((l, i) => ({ id: `link-${i}`, label: l.name, href: l.address })) }]}
      trigger={<AriaButton className={styles.pages}>{t("header.pages")}</AriaButton>}
    />
  );
}
