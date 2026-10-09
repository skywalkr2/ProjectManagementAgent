// The API client. Types come from the server's OpenAPI schema (npm run gen:api), so a changed field fails the build.
// Paths are relative: the page's <base> points at the configured base path, so the same build works under any path.
import type { components } from "../api/schema";

export type S = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail || `HTTP ${status}`);
  }
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`api/${path}`, init);
  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: unknown; error?: unknown };
      detail = typeof data.detail === "string" ? data.detail : typeof data.error === "string" ? data.error : "";
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const id = encodeURIComponent;

export const api = {
  runtimeConfig: () => call<S["RuntimeConfig"]>("GET", "runtime-config"),
  status: () => call<S["Status"]>("GET", "status"),
  changes: () => call<S["ChangeItem"][]>("GET", "changes"),
  source: (src: string) => call<S["SourceView"]>("GET", `sources/${id(src)}`),
  followups: () => call<S["FollowupSection"][]>("GET", "followups"),
  people: () => call<S["PersonView"][]>("GET", "people"),

  handIn: (body: S["HandIn"]) => call<S["Handed"]>("POST", "handin", body),
  looksGood: (cs: string) => call<S["Ok"]>("POST", `changesets/${id(cs)}/looks-good`),
  reopen: (cs: string) => call<S["Ok"]>("POST", `changesets/${id(cs)}/reopen`),
  undo: (cs: string, ops?: number[]) => call<S["UndoReport"]>("POST", `changesets/${id(cs)}/undo`, { ops: ops ?? null }),
  sendBack: (cs: string, note: string) => call<S["Requeued"]>("POST", `changesets/${id(cs)}/send-back`, { note }),
  release: (cs: string, index: number, person?: string) =>
    call<S["Ok"]>("POST", `changesets/${id(cs)}/ops/${index}/release`, { person: person ?? null }),
  answer: (q: string, body: S["Answer"]) => call<S["Ok"]>("POST", `questions/${id(q)}/answer`, body),
  actionStatus: (a: string, status: S["ActionState"]["status"]) =>
    call<S["Ok"]>("POST", `actions/${id(a)}/status`, { status }),
  reply: (q: string, text: string) => call<S["Handed"]>("POST", `questions/${id(q)}/reply`, { text }),
  retry: (req: string) => call<S["Ok"]>("POST", `requests/${id(req)}/retry`),
  markSent: (person: string, text: string | null) =>
    call<S["SentCounts"]>("POST", `followups/${id(person)}/mark-sent`, { text }),
  unmarkSent: (person: string, body: S["Unmark"]) =>
    call<S["Ok"]>("POST", `followups/${id(person)}/unmark-sent`, body),
  backup: () => call<S["Status"]>("POST", "backup"),
};

export const EVENTS_PATH = "api/events";
