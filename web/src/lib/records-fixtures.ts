// The records screens' test data: a project, a person, an organization and an unfiled item, with every field the server sends.
import type { S } from "./api";

export const project = (id: string, name: string, extra: Partial<S["ProjectView"]> = {}): S["ProjectView"] => ({
  id,
  name,
  group: null,
  status: null,
  phase: null,
  target: null,
  owner: null,
  owner_name: null,
  summary: null,
  language: "en-US",
  language_own: false,
  role: "run",
  completed: false,
  spent_usd: 0,
  open_actions: 0,
  open_questions: 0,
  ...extra,
});

export const person = (id: string, name: string, extra: Partial<S["PersonView"]> = {}): S["PersonView"] => ({
  id,
  name,
  role: null,
  aliases: [],
  is_pm: false,
  track_only: false,
  open_items: 0,
  status: "active",
  how_to_reach: {},
  ...extra,
});

export const org = (id: string, name: string, people = 0): S["OrganizationView"] => ({ id, name, aliases: [], notes: null, people });

export const unfiledItem = (kind: S["UnfiledItem"]["kind"], id: string, text: string, extra: Partial<S["UnfiledItem"]> = {}): S["UnfiledItem"] => ({
  kind,
  id,
  version: 1,
  text,
  created_at: "2026-10-09T14:00:00Z",
  trust: "trusted",
  ...extra,
});

export const unfiledView = (...items: S["UnfiledItem"][]): S["UnfiledView"] => ({ count: items.length, items });
