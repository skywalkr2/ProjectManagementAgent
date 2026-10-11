// Settings forms: turning each setting's value into what a control edits and back, grouping, searching and read-backs.
import type { S } from "./api";

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

/** A heading for a group: the wording sheet's, otherwise its dotted name made readable. */
export function groupLabel(group: string, t: T, has: Has): string {
  const key = `settings.group.${group}`;
  if (has(key)) return t(key);
  const words = group.replace(/[._-]+/g, " ").replace(/\bai\b/g, "AI").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : group;
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
    return [item.key, labelOf(item, t, has), item.description].some((x) => x.toLowerCase().includes(q));
  });
  const groups = new Map<string, Item[]>();
  for (const item of shown) groups.set(item.group, [...(groups.get(item.group) ?? []), item]);
  const out = [...groups].map(([group, list]) => ({
    group,
    items: [...list.filter((i) => i.basic), ...list.filter((i) => !i.basic)],
  }));
  return [...out.filter((g) => g.items.some((i) => i.basic)), ...out.filter((g) => !g.items.some((i) => i.basic))];
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
