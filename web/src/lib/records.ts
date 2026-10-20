// Showing any record's values in plain words: field names made readable and values as lines of text.
import { useCallback } from "react";
import { day, whenText } from "./dates";
import { useWords } from "./wording";

/** A field or kind name as words: "_" and "-" become spaces and the first letter is a capital. */
export function readable(name: string): string {
  const spaced = name.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** The part of a namespaced name after the last "/", as words ("plugin/chapter-note" is "Chapter note"). */
export function readableTail(name: string): string {
  return readable(name.slice(name.lastIndexOf("/") + 1));
}

/** A value as lines of plain text: nothing for an empty one, a line for each item of a list. */
export function useValueLines() {
  const { t } = useWords();
  return useCallback((value: unknown): string[] => lines(value, t), [t]);
}

function lines(value: unknown, t: (key: string) => string): string[] {
  if (value === null || value === undefined) return [];
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (typeof value === "number") return [String(value)];
  if (typeof value === "boolean") return [t(value ? "value.yes" : "value.no")];
  if (Array.isArray(value)) return value.flatMap((item) => lines(item, t));
  if (typeof value === "object") return Object.values(value as Record<string, unknown>).flatMap((item) => lines(item, t));
  return [];
}

/** A field's label on screen: the wording sheet's own for the core's fields (`field.org` is "Organization"), else its
 * name made readable. */
export function useFieldLabel() {
  const { t, has } = useWords();
  return useCallback((name: string): string => (has(`field.${name}`) ? t(`field.${name}`) : readable(name)), [t, has]);
}

/** The fields a page lists first, in this order: who it is, their part, where they work, how to reach them. The rest follow
 * in the order the kind declares them. */
const FIRST_DETAILS = ["full_name", "name", "title", "role", "org", "how_to_reach"];

/** The details in the order a reader looks for them. */
export function inReadingOrder<T extends { name: string }>(rows: T[]): T[] {
  const rank = (name: string) => {
    const at = FIRST_DETAILS.indexOf(name);
    return at < 0 ? FIRST_DETAILS.length : at;
  };
  return rows.map((row, i) => ({ row, i })).sort((a, b) => rank(a.row.name) - rank(b.row.name) || a.i - b.i).map(({ row }) => row);
}

/** One line of a detail: words, or a link shown by its title with the domain beside it. */
export type DetailLine = string | { label: string; url: string };

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ISO_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
/** The keys of a map inside a list whose values are one of a fixed set of words, not free text. */
const TOKEN_KEYS = new Set(["role", "status", "kind", "stance", "state", "basis", "type"]);

/** A record's value as lines of plain words: the name of a record an id stands for, a date as elsewhere in the app, a choice
 * as its label, a yes or no, a link by its title, and a map as "Label: value" lines. Nothing empty is a line. */
export function useDetailLines() {
  const { t, has } = useWords();
  return useCallback(
    (name: string, value: unknown, view: { type?: string; value_list?: string | null } | undefined, names: ReadonlyMap<string, string>): DetailLine[] => {
      const scalar = (key: string, v: unknown, token: boolean): string => {
        if (typeof v === "boolean") return t(v ? "value.yes" : "value.no");
        if (typeof v === "number") return String(v);
        if (typeof v !== "string") return "";
        const text = v.trim();
        if (!text) return "";
        const known = names.get(text);
        if (known) return known;
        if (ISO_DAY.test(text)) return day(text);
        if (ISO_TIME.test(text)) return whenText(text) || text;
        return token ? (has(`value.${key}.${text}`) ? t(`value.${key}.${text}`) : readable(text)) : text;
      };
      const plain = (v: unknown) => ["string", "number", "boolean"].includes(typeof v);
      const walk = (key: string, v: unknown, inList: boolean): DetailLine[] => {
        if (v === null || v === undefined) return [];
        if (Array.isArray(v)) return v.flatMap((item) => walk(key, item, true));
        if (typeof v === "object") {
          const o = v as Record<string, unknown>;
          if (typeof o.url === "string" && /^https?:\/\//i.test(o.url)) return [{ label: typeof o.label === "string" ? o.label.trim() : "", url: o.url }];
          const parts = Object.entries(o).map(([k, item]) => [k, item] as const);
          if (inList) return [parts.filter(([, item]) => plain(item)).map(([k, item]) => scalar(k, item, TOKEN_KEYS.has(k))).filter(Boolean).join(" · ")].filter(Boolean);
          return parts.flatMap(([k, item]) => {
            if (!plain(item)) return walk(k, item, false);
            const text = scalar(k, item, TOKEN_KEYS.has(k));
            return text ? [`${readable(k)}: ${text}`] : [];
          });
        }
        const text = scalar(key, v, view?.type === "choice" && !view.value_list && !inList);
        return text ? [text] : [];
      };
      return walk(name, value, false);
    },
    [t, has],
  );
}
