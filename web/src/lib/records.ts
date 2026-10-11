// Showing any record's values in plain words: field names made readable and values as lines of text.
import { useCallback } from "react";
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
