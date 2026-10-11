// A form for a kind of file's details, generated from the JSON schema the server gives for them. It supports the
// plain shapes (text, numbers, yes/no, a pick from a list, each optionally left out); anything else makes the whole
// kind "unsupported" so the screen says so instead of guessing.
type Json = Record<string, unknown>;

export interface DetailField {
  key: string;
  label: string;
  help: string;
  type: "text" | "number" | "integer" | "boolean" | "choice";
  required: boolean;
  defaultValue?: unknown;
  maxLength?: number;
  minLength?: number;
  min?: number;
  max?: number;
  choices: Array<{ value: unknown; label: string }>;
}

const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

function lookup(root: Json, ref: string): Json | null {
  if (!ref.startsWith("#/")) return null;
  let at: unknown = root;
  for (const part of ref.slice(2).split("/")) {
    at = isObject(at) ? at[part.replace(/~1/g, "/").replace(/~0/g, "~")] : undefined;
  }
  return isObject(at) ? at : null;
}

/** Follow references, single-item allOf and "this or nothing" unions down to the field's own shape. */
function settle(node: Json, root: Json): Json | null {
  let current = node;
  for (let i = 0; i < 8; i++) {
    const { $ref, allOf, anyOf, oneOf, ...rest } = current;
    if (typeof $ref === "string") {
      const target = lookup(root, $ref);
      if (!target) return null;
      current = { ...target, ...rest };
      continue;
    }
    if (Array.isArray(allOf)) {
      if (allOf.length !== 1 || !isObject(allOf[0])) return null;
      current = { ...allOf[0], ...rest };
      continue;
    }
    const union = anyOf ?? oneOf;
    if (Array.isArray(union)) {
      const real = union.filter((u) => !(isObject(u) && u.type === "null"));
      if (real.length !== 1 || !isObject(real[0])) return null;
      current = { ...real[0], ...rest };
      continue;
    }
    return current;
  }
  return null;
}

function humanize(key: string): string {
  const words = key.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function field(key: string, node: Json, root: Json, required: boolean): DetailField | null {
  const shape = settle(node, root);
  if (!shape) return null;
  const types = (Array.isArray(shape.type) ? shape.type : [shape.type]).filter((x) => x !== "null");
  const one = types.length === 1 ? types[0] : undefined;
  const base = {
    key,
    label: typeof shape.title === "string" && shape.title ? shape.title : humanize(key),
    help: typeof shape.description === "string" ? shape.description : "",
    required,
    defaultValue: "default" in shape ? shape.default : undefined,
    maxLength: typeof shape.maxLength === "number" ? shape.maxLength : undefined,
    minLength: typeof shape.minLength === "number" ? shape.minLength : undefined,
    min: typeof shape.minimum === "number" ? shape.minimum : undefined,
    max: typeof shape.maximum === "number" ? shape.maximum : undefined,
  };
  const list = Array.isArray(shape.enum) ? shape.enum : "const" in shape ? [shape.const] : null;
  if (list) {
    if (!list.length || list.some((v) => !["string", "number", "boolean"].includes(typeof v))) return null;
    return { ...base, type: "choice", choices: list.map((v) => ({ value: v, label: String(v) })) };
  }
  if (one === "string") return { ...base, type: "text", choices: [] };
  if (one === "integer") return { ...base, type: "integer", choices: [] };
  if (one === "number") return { ...base, type: "number", choices: [] };
  if (one === "boolean") return { ...base, type: "boolean", choices: [] };
  return null;
}

/** The fields to ask for, or null when the details have a shape this form can't ask for. */
export function detailFields(schema: Json): DetailField[] | null {
  const properties = schema.properties;
  if (properties === undefined) return schema.type === undefined || schema.type === "object" ? [] : null;
  if (!isObject(properties)) return null;
  const required = Array.isArray(schema.required) ? (schema.required as string[]) : [];
  const out: DetailField[] = [];
  for (const [key, node] of Object.entries(properties)) {
    const made = isObject(node) ? field(key, node, schema, required.includes(key)) : null;
    if (!made) return null;
    out.push(made);
  }
  return out;
}

export type FormValues = Record<string, string | boolean>;

/** What a field shows before the person touches it. */
export function initialValue(f: DetailField): string | boolean {
  if (f.type === "boolean") return f.defaultValue === true;
  if (f.defaultValue !== undefined && f.defaultValue !== null) return String(f.defaultValue);
  if (f.type === "choice" && f.required) return String(f.choices[0].value);
  return "";
}

export type Built = { meta: Record<string, unknown> } | { missing: string };

/** The details to send. Empty optional fields are left out so the server's defaults apply; a required one left empty is named. */
export function buildDetails(fields: DetailField[], values: FormValues): Built {
  const meta: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = values[f.key] ?? initialValue(f);
    if (f.type === "boolean") {
      if (f.required || f.defaultValue !== undefined || raw === true) meta[f.key] = raw === true;
      continue;
    }
    const text = String(raw);
    if (text.trim() === "") {
      if (f.required) return { missing: f.label };
      continue;
    }
    if (f.type === "choice") {
      meta[f.key] = f.choices.find((c) => String(c.value) === text)?.value ?? text;
    } else if (f.type === "text") {
      meta[f.key] = text;
    } else {
      const n = Number(text);
      if (!Number.isFinite(n) || (f.type === "integer" && !Number.isInteger(n))) return { missing: f.label };
      meta[f.key] = n;
    }
  }
  return { meta };
}
