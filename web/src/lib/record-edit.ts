// Editing a record's ordinary fields: which fields the form offers, the values it starts with, and which of them the
// person changed. Only the changed ones are sent.
import type { S } from "./api";

type Field = S["FieldView"];
export type Draft = Record<string, string | boolean>;

/** The kinds of record a reference field can be picked from. */
const PICKABLE = new Set(["person", "project"]);

/** The fields the form offers, in the kind's order. Long text and fields of an unknown shape are edited elsewhere or not at
 * all, and a reference to anything but a person or a project has nothing to pick from. */
export function editableFields(fields: Field[]): Field[] {
  return fields.filter((f) => {
    if (f.editable === false) return false;
    if (f.type === "long_text" || f.type === "other" || !f.type) return false;
    if (f.type === "reference") return !!f.refers_to && PICKABLE.has(f.refers_to);
    return true;
  });
}

const asText = (value: unknown): string => (value === null || value === undefined ? "" : String(value));

/** What the form holds for a field before the person types: the record's value as the control shows it. */
export function initialValue(field: Field, value: unknown): string | boolean {
  switch (field.type) {
    case "yes_no":
      return value === true;
    case "date":
      return asText(value).slice(0, 10);
    case "list":
      return Array.isArray(value) ? value.map(asText).join("\n") : asText(value);
    default:
      return asText(value);
  }
}

export function initialDraft(fields: Field[], values: Record<string, unknown>): Draft {
  return Object.fromEntries(fields.map((f) => [f.name, initialValue(f, values[f.name])]));
}

/** A list typed one value per line. */
export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}

/** What the server should store for what the control holds: an empty control clears the field. */
export function storedValue(field: Field, draft: string | boolean): unknown {
  switch (field.type) {
    case "yes_no":
      return draft === true;
    case "number": {
      const text = String(draft).trim();
      return text === "" || Number.isNaN(Number(text)) ? null : Number(text);
    }
    case "list":
      return lines(String(draft));
    default:
      return String(draft) === "" ? null : String(draft);
  }
}

/** The fields whose value differs from the record's, ready to send. */
export function changedFields(fields: Field[], values: Record<string, unknown>, draft: Draft): Record<string, unknown> {
  const changed: Record<string, unknown> = {};
  for (const f of fields) {
    const was = initialValue(f, values[f.name]);
    const now = draft[f.name] ?? was;
    const same = f.type === "list" ? lines(String(was)).join("\n") === lines(String(now)).join("\n") : was === now;
    if (!same) changed[f.name] = storedValue(f, now);
  }
  return changed;
}
