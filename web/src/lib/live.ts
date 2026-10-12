// Live updates: the server's event stream says when anything changed, and only the queries that change affects refresh.
// No polling. The browser's own offline and online events count too, so a lost connection shows within moments.
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { EVENTS_PATH } from "./api";

export type LiveState = "connecting" | "live" | "offline";

const CHANGES = ["changes", "source", "auto-closed", "request-accounts", "asks", "plugin-today", "stages", "status", "jobs", "today", "text-review"];
const FOLLOWUPS = ["followups", "today", "status", "plugin-today", "changes"];
const FILES = ["files", "text", "working-copies", "text-review", "file-kinds", "changes", "record", "plugin-today"];
const PLUGIN = ["plugin-today", "panels", "panel-rows", "panel-document", "record", "kind", "stages", "plugin-actions", "text", "working-copies", "today", "changes"];

/** The query families each kind of record affects (the first part of their keys). */
const AFFECTS: Record<string, string[]> = {
  request: CHANGES,
  changeset: CHANGES,
  run: CHANGES,
  source: CHANGES,
  signal: CHANGES,
  question: FOLLOWUPS,
  action: FOLLOWUPS,
  fact: ["notes", "changes", "today", "record", "projects"],
  note: ["notes", "changes", "today", "record", "projects"],
  person: ["people", "followups", "today", "me", "setup", "organizations", "record"],
  team: ["people", "organizations", "followups", "record"],
  organization: ["organizations", "people", "record"],
  project: ["projects", "followups", "today", "stages", "panels", "setup", "record", "notes"],
  file: FILES,
  working_copy: FILES,
  text_version: FILES,
  answer: ["asks", "status", "changes"],
  setting_proposal: ["asks", "status"],
  report: ["asks", "status"],
  job_run: ["jobs", "watch", "today", "status", "setup", "sync"],
  watch_run: ["watch", "watch-kinds", "today", "status", "sign-ins", "jobs"],
  tool_run: ["jobs", "status", "files", "working-copies"],
  snapshot: ["status", "sync", "setup"],
  setting_change: ["settings", "status", "setup", "panels", "today", "lists", "ai-accounts", "ai-endpoints", "watch", "packs"],
  value_list: ["lists", "settings", "people", "projects"],
};

/** The query keys' first parts to refresh for the kinds of record written, or null to refresh everything: an empty list
 * means something other than a record changed (a setting, a source's state), and a kind this table doesn't know is not
 * guessed at. A plugin's own kind (it has a slash) refreshes the plugin's screens. */
export function familiesFor(kinds: readonly string[]): string[] | null {
  if (!kinds.length) return null;
  const families = new Set<string>();
  for (const kind of kinds) {
    const known = AFFECTS[kind] ?? (kind.includes("/") ? PLUGIN : null);
    if (!known) return null;
    for (const family of known) families.add(family);
  }
  return [...families];
}

/** What a "changed" event's data says: the kinds written, or null when it names none (an older server sends a number). */
export function kindsOf(data: string): string[] | null {
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed && typeof parsed === "object" && "kinds" in parsed && Array.isArray(parsed.kinds)) {
      return parsed.kinds.filter((k): k is string => typeof k === "string");
    }
  } catch {
    // A bare number, or anything else, means everything may have changed.
  }
  return null;
}

/** Refreshes the queries an event's data says it affects, or all of them when it doesn't say. */
export function invalidateFor(client: QueryClient, data: string): void {
  const families = familiesFor(kindsOf(data) ?? []);
  if (!families) {
    void client.invalidateQueries();
    return;
  }
  const wanted = new Set(families);
  void client.invalidateQueries({ predicate: (query) => wanted.has(String(query.queryKey[0])) });
}

/** `hellos` counts how many times the stream has (re)connected, so a caller can wait for the next one. */
export function useLive(): { state: LiveState; lastUpdate: Date | null; hellos: number; refresh: () => void } {
  const client = useQueryClient();
  const [state, setState] = useState<LiveState>(() => (typeof navigator !== "undefined" && navigator.onLine === false ? "offline" : "connecting"));
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [hellos, setHellos] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const source = useRef<EventSource | null>(null);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const stream = new EventSource(EVENTS_PATH);
    source.current = stream;
    stream.addEventListener("hello", () => {
      setState("live");
      setHellos((n) => n + 1);
      setLastUpdate(new Date());
      void client.invalidateQueries();
    });
    stream.addEventListener("changed", (event) => {
      setLastUpdate(new Date());
      invalidateFor(client, (event as MessageEvent<string>).data);
    });
    stream.onerror = () => setState("offline");
    return () => stream.close();
  }, [client, attempt]);

  useEffect(() => {
    const goOffline = () => setState("offline");
    const goOnline = () => {
      setState("connecting");
      // A stream the server closed does not retry by itself; a fresh one is opened.
      if (source.current?.readyState === 2) setAttempt((n) => n + 1);
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    // The connection may already have been lost before this ran.
    if (navigator.onLine === false) goOffline();
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, []);

  const refresh = useCallback(() => {
    setLastUpdate(new Date());
    void client.invalidateQueries();
  }, [client]);

  return { state, lastUpdate, hellos, refresh };
}
