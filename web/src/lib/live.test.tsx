import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { familiesFor, invalidateFor, kindsOf, useLive } from "./live";

test("each kind of record names the queries it affects", () => {
  expect(familiesFor(["request", "changeset"])).toEqual(expect.arrayContaining(["changes", "today", "stages", "plugin-today"]));
  expect(familiesFor(["question"])).toEqual(expect.arrayContaining(["followups", "today"]));
  expect(familiesFor(["action"])).toEqual(expect.arrayContaining(["followups", "today"]));
  expect(familiesFor(["person"])).toEqual(expect.arrayContaining(["people"]));
  expect(familiesFor(["organization"])).toEqual(expect.arrayContaining(["organizations"]));
  expect(familiesFor(["project"])).toEqual(expect.arrayContaining(["projects"]));
  expect(familiesFor(["person"])).not.toContain("changes");
  // A plugin's own kind refreshes the plugin's screens.
  expect(familiesFor(["demo/goal"])).toEqual(expect.arrayContaining(["panel-rows", "plugin-today"]));
});

test("a correction and what was learned from it refresh the lines under cards and the review lists", () => {
  expect(familiesFor(["signal"])).toEqual(expect.arrayContaining(["learned"]));
  for (const kind of ["lesson", "glossary_entry", "routing_entry", "style_note", "rule"]) {
    expect(familiesFor([kind])).toEqual(expect.arrayContaining(["learned", "proposals", "catch-up", "today"]));
  }
});

test("no kinds, or a kind nobody knows, means refresh everything", () => {
  expect(familiesFor([])).toBeNull();
  expect(familiesFor(["person", "something_new"])).toBeNull();
});

test("an event's data is read as kinds, and a bare number names none", () => {
  expect(kindsOf('{"version": 3, "kinds": ["request", "changeset"]}')).toEqual(["request", "changeset"]);
  expect(kindsOf('{"version": 3, "kinds": []}')).toEqual([]);
  expect(kindsOf("7")).toBeNull();
  expect(kindsOf("not json")).toBeNull();
});

function seeded() {
  const client = new QueryClient();
  for (const key of ["changes", "followups", "people", "projects", "settings"]) client.setQueryData([key], []);
  const stale = () => Object.fromEntries(["changes", "followups", "people", "projects", "settings"].map((k) => [k, client.getQueryState([k])!.isInvalidated]));
  return { client, stale };
}

test("an event invalidates only the queries its kinds affect", () => {
  const { client, stale } = seeded();
  invalidateFor(client, '{"version": 2, "kinds": ["person"]}');
  expect(stale()).toEqual({ changes: false, followups: true, people: true, projects: false, settings: false });
});

test("an empty or unknown kind list, and an older server's bare number, invalidate everything", () => {
  for (const data of ['{"version": 2, "kinds": []}', '{"version": 2, "kinds": ["mystery"]}', "5"]) {
    const { client, stale } = seeded();
    invalidateFor(client, data);
    expect(Object.values(stale()).every(Boolean)).toBe(true);
  }
});

class FakeSource {
  static last: FakeSource | null = null;
  readyState = 0;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: unknown) => void>();
  constructor(public url: string) {
    FakeSource.last = this;
  }
  addEventListener(name: string, fn: (event: unknown) => void) {
    this.listeners.set(name, fn);
  }
  close() {
    this.readyState = 2;
  }
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

test("the stream's hello makes it live, and the browser going offline shows at once", () => {
  vi.stubGlobal("EventSource", FakeSource);
  const client = new QueryClient();
  const { result } = renderHook(() => useLive(), { wrapper: wrapper(client) });
  expect(result.current.state).toBe("connecting");
  act(() => FakeSource.last!.listeners.get("hello")!({}));
  expect(result.current.state).toBe("live");
  expect(result.current.hellos).toBe(1);
  act(() => {
    window.dispatchEvent(new Event("offline"));
  });
  expect(result.current.state).toBe("offline");
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
  expect(result.current.state).toBe("connecting");
  act(() => FakeSource.last!.listeners.get("hello")!({}));
  expect(result.current.state).toBe("live");
  vi.unstubAllGlobals();
});

test("a stream error shows offline, and coming back online opens a new stream when the old one closed", () => {
  vi.stubGlobal("EventSource", FakeSource);
  const client = new QueryClient();
  const { result } = renderHook(() => useLive(), { wrapper: wrapper(client) });
  const first = FakeSource.last!;
  act(() => first.onerror!());
  expect(result.current.state).toBe("offline");
  first.readyState = 2;
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
  expect(FakeSource.last).not.toBe(first);
  vi.unstubAllGlobals();
});

test("a changed event refreshes by kind and updates the time", () => {
  vi.stubGlobal("EventSource", FakeSource);
  const { client, stale } = seeded();
  const { result } = renderHook(() => useLive(), { wrapper: wrapper(client) });
  act(() => FakeSource.last!.listeners.get("changed")!({ data: '{"version": 4, "kinds": ["question"]}' }));
  expect(stale().followups).toBe(true);
  expect(stale().people).toBe(false);
  expect(result.current.lastUpdate).not.toBeNull();
  vi.unstubAllGlobals();
});
