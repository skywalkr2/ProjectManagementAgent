// Settings forms: turning each setting's value into what a control edits and back, grouping, searching and read-backs.
import type { S } from "./api";
import { readable } from "./records";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Has = (key: string) => boolean;
export type Draft = string | boolean;
export type Item = S["SettingItem"];

/** What a control shows for a setting's value: text for most, a box for yes/no, one value a line for a list. */
export function toDraft(item: Item): Draft {
  const v = item.value;
  if (item.type === "yes_no") return v === true;
  if (item.type === "list") return Array.isArray(v) ? v.map(String).join("\n") : "";
  if (v === null || v === undefined) return "";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

export type Parsed = { ok: true; value: unknown } | { ok: false; problem: "number" | "integer" };

/** What to send for what a control holds, or what is wrong with it. */
export function fromDraft(item: Item, draft: Draft): Parsed {
  switch (item.type) {
    case "yes_no":
      return { ok: true, value: draft === true };
    case "list":
      return {
        ok: true,
        value: String(draft)
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      };
    case "number":
    case "integer": {
      const text = String(draft).trim();
      const n = Number(text);
      if (!text || !Number.isFinite(n)) return { ok: false, problem: item.type };
      if (item.type === "integer" && !Number.isInteger(n)) return { ok: false, problem: "integer" };
      return { ok: true, value: n };
    }
    default:
      return { ok: true, value: String(draft).trim() };
  }
}

/** A value in plain words, for a default, a read-only value and the read-back after a save. */
export function formatValue(value: unknown, t: T): string {
  if (value === null || value === undefined || value === "") return t("settings.empty");
  if (typeof value === "boolean") return t(value ? "settings.yes" : "settings.no");
  if (Array.isArray(value)) return value.length ? value.map((v) => formatValue(v, t)).join(", ") : t("settings.empty");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Where a setting that this screen can't change is changed. */
export const fileName = (item: Pick<Item, "file">) => `${item.file}.yaml`;

/** A short label from the wording sheet when there is one, otherwise the setting's own description. */
export function labelOf(item: Pick<Item, "key" | "description">, t: T, has: Has): string {
  const key = `settings.key.${item.key}`;
  return has(key) ? t(key) : item.description;
}

/** Add-on settings sit in a group named for the add-on: "plugins/<name>". */
const ADDON_PREFIX = "plugins/";

/** The add-on a group belongs to, if it is an add-on's. */
export const addonOf = (group: string): string | null => (group.startsWith(ADDON_PREFIX) ? group.slice(ADDON_PREFIX.length) : null);

/** An add-on's name for showing: the wording sheet's when it has one, otherwise its name made readable. */
export function addonLabel(name: string, t: T, has: Has): string {
  const key = `settings.addon.${name}`;
  return has(key) ? t(key) : readable(name);
}

/** A heading for a group: an add-on's name, the wording sheet's, otherwise its dotted name made readable. */
export function groupLabel(group: string, t: T, has: Has): string {
  const addon = addonOf(group);
  if (addon !== null) return addonLabel(addon, t, has);
  const key = `settings.group.${group}`;
  if (has(key)) return t(key);
  const words = group.replace(/[._-]+/g, " ").replace(/\bai\b/g, "AI").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : group;
}

/** The words that end a name: dots, ellipses and spaces, so a sentence built around the name ends in exactly one period. */
const trimEnd = (text: string) => text.replace(/[\s.…]+$/u, "");

/** A setting's short name for use in a sentence: the wording sheet's label, otherwise the first sentence of its
 * description without its closing period, otherwise its key. */
export function shortLabel(item: Pick<Item, "key" | "description">, t: T, has: Has): string {
  const key = `settings.key.${item.key}`;
  if (has(key)) return trimEnd(t(key)) || item.key;
  const first = (item.description ?? "").trim().split(/(?<=[.!?])\s+/u)[0] ?? "";
  return trimEnd(first) || item.key;
}

/** What to call a setting by its key: the label its screen shows (shortened to a name), else its group's, else a general phrase. */
export function labelForKey(key: string, items: Item[], t: T, has: Has): string {
  const item = items.find((i) => i.key === key);
  if (item) return shortLabel(item, t, has);
  if (has(`settings.key.${key}`)) return t(`settings.key.${key}`);
  const parts = key.split(".");
  for (let n = parts.length - 1; n >= 1; n -= 1) {
    const group = parts.slice(0, n).join(".");
    if (addonOf(group) !== null || has(`settings.group.${group}`)) return groupLabel(group, t, has);
  }
  return t("restart.for_other");
}

const RESTART_SHOWN = 3;

/** What waits for a restart, in plain words: each settings key by its label, "code" as an update to the app. Up to three
 * are named, then how many more. Nothing when nothing waits. */
export function restartWhat(keys: string[], items: Item[], t: T, has: Has): string {
  const names: string[] = [];
  for (const key of keys) {
    const name = key === "code" ? t("restart.for_code") : labelForKey(key, items, t, has);
    if (!names.includes(name)) names.push(name);
  }
  if (!names.length) return "";
  const shown = names.slice(0, RESTART_SHOWN).join(", ");
  const list = names.length > RESTART_SHOWN ? t("restart.for_more", { list: shown, n: names.length - RESTART_SHOWN }) : shown;
  return t("restart.for", { what: trimEnd(list) });
}

export interface Group {
  group: string;
  items: Item[];
}

/** The items to show, grouped: basic ones first, the rest only when asked for or when searching, which looks at every
 * setting by its key, label and description. */
export function groupItems(items: Item[], opts: { more: boolean; query: string }, t: T, has: Has): Group[] {
  const q = opts.query.trim().toLowerCase();
  const shown = items.filter((item) => {
    if (!q) return opts.more || item.basic;
    const addon = item.plugin ? [addonLabel(item.plugin, t, has)] : [];
    return [item.key, labelOf(item, t, has), item.description, ...addon].some((x) => x.toLowerCase().includes(q));
  });
  const groups = new Map<string, Item[]>();
  for (const item of shown) groups.set(item.group, [...(groups.get(item.group) ?? []), item]);
  const out = [...groups].map(([group, list]) => ({
    group,
    items: [...list.filter((i) => i.basic), ...list.filter((i) => !i.basic)],
  }));
  const ordered = [...out.filter((g) => g.items.some((i) => i.basic)), ...out.filter((g) => !g.items.some((i) => i.basic))];
  // The app's own groups come first; each add-on's follows, one group each.
  return [...ordered.filter((g) => addonOf(g.group) === null), ...ordered.filter((g) => addonOf(g.group) !== null)];
}

/** The setting that switches this one on or off, if there is one. */
export function switchOf(item: Pick<Item, "enabled_by">, items: Item[]): Item | undefined {
  return item.enabled_by ? items.find((i) => i.key === item.enabled_by) : undefined;
}

/** Whether a switch is off: a yes/no setting that is not on, or a text setting (such as a folder) that is empty. Reads
 * what is on screen when it was changed there, otherwise the saved value. */
export function isOff(switchItem: Item, edits: Record<string, Draft>): boolean {
  const draft = switchItem.key in edits ? edits[switchItem.key] : toDraft(switchItem);
  return switchItem.type === "yes_no" ? draft !== true : String(draft).trim() === "";
}

/** How many switches sit above a setting, so dependents can be indented under theirs. */
export function depthOf(item: Item, items: Item[]): number {
  let depth = 0;
  for (let at = switchOf(item, items); at && depth < 4; at = switchOf(at, items)) depth += 1;
  return depth;
}

/** The body that puts a save back as it was: what was default goes back to default, the rest to its old value. */
export function undoBody(changes: S["SettingChangeView"][], fingerprint: string): S["SettingsSave"] {
  const body: S["SettingsSave"] = { changes: {}, reset: [], fingerprint };
  for (const c of changes) {
    if (c.was_default) body.reset!.push(c.key);
    else body.changes![c.key] = c.before;
  }
  return body;
}
