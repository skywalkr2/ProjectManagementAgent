// The sections of Settings (design 7.9): which section each setting belongs to, which sections are listed down the side,
// and how a long section is grouped by topic. A setting lives in exactly one section.
import type { Item } from "./settings";
import { SETTINGS_SECTIONS, type SettingsSection } from "./views";

type Fixed = (typeof SETTINGS_SECTIONS)[number];

/** The section for a settings group, by its name or the front of it; the longest front wins. A group that no section
 * claims is under Advanced. */
const BY_GROUP: Array<[front: string, section: Fixed]> = [
  ["workspace.plugins", "advanced"],
  ["workspace", "you"],
  ["ai", "ai"],
  ["storage", "backups"],
  ["ui.today", "today"],
  ["ui.followups", "today"],
  ["ui.notifications", "today"],
  ["ui.walkthrough", "you"],
  ["steward", "today"],
  ["ui", "appearance"],
];

const within = (group: string, front: string) => group === front || group.startsWith(`${front}.`);

/** The section a setting is shown in: an add-on's settings are in its own section. */
export function sectionOfItem(item: Pick<Item, "group" | "plugin" | "advanced">): SettingsSection {
  if (item.plugin) return `addon/${item.plugin}`;
  // A technical setting is under Advanced, whatever its group, so no other section shows it.
  if (item.advanced) return "advanced";
  const found = BY_GROUP.filter(([front]) => within(item.group, front)).sort((a, b) => b[0].length - a[0].length)[0];
  return found ? found[1] : "advanced";
}

/** Settings that a part of their section edits in its own way, so they aren't also listed as rows: the tier each kind of
 * work uses, what a tier tries once more on, the routing rules (Which model does what), the backup key, the keys an
 * add-on needs (password boxes of their own), the notices' address and the list of the person's own pages. */
const OWN_PART = [
  "ai.tasks",
  "ai.tiers",
  "ai.routing",
  "storage.backups.encrypt",
  "workspace.plugins.secrets",
  "ui.notifications.webhook",
  "ui.links",
  // Where reminders reach you away from the app is one choice with its own yes, not two rows.
  "steward.reminders.where",
  "steward.reminders.where_account",
  // The accounts the assistant may act on are a switch on each account, not a list to tick.
  "watch.acting",
  // The cloud drives the backup step looks for are a list of records, changed in the file; the step shows what it found.
  "storage.backups.cloud_folders",
];

/** Whether a setting is listed as a row of its own. */
export const isListed = (item: Pick<Item, "key">): boolean => !OWN_PART.includes(item.key);

/** A section's settings, the basic ones first. */
export function sectionItems(items: Item[], section: SettingsSection): Item[] {
  const mine = items.filter((i) => isListed(i) && sectionOfItem(i) === section);
  return [...mine.filter((i) => i.basic), ...mine.filter((i) => !i.basic)];
}

/** The sections to list down the side, in order: the basic ones first, then Lists and the add-on files where there are
 * some, Advanced, then one for each add-on that has settings. AI accounts is always there, for its list of accounts. */
export function navSections(items: Item[], has: { lists: boolean; files: boolean; keyed?: string[] }): SettingsSection[] {
  const present = new Set(items.map(sectionOfItem));
  // An add-on that needs keys has a section for them even when it has no settings of its own.
  for (const plugin of has.keyed ?? []) present.add(`addon/${plugin}`);
  const out: SettingsSection[] = [];
  for (const id of SETTINGS_SECTIONS) {
    const shown = id === "ai" || (id === "lists" ? has.lists : id === "files" ? has.files : present.has(id));
    if (shown) out.push(id);
  }
  const addons = [...present].filter((s) => s.startsWith("addon/"));
  return [...out, ...addons];
}

export interface Topic {
  group: string;
  items: Item[];
}

/** A section's settings by topic (one topic for each group), in the order the groups first appear. */
export function topics(items: Item[]): Topic[] {
  const out = new Map<string, Item[]>();
  for (const item of items) out.set(item.group, [...(out.get(item.group) ?? []), item]);
  return [...out].map(([group, list]) => ({ group, items: list }));
}
