// Rendering components against a fake API: routes map "METHOD path" to a handler that returns the JSON body.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { ToastProvider } from "./lib/toasts";
import { WordingProvider } from "./lib/wording";
import { OwnRequestsProvider } from "./components/HandIn";

export type Routes = Record<string, (body: unknown) => unknown>;

export function fakeApi(routes: Routes) {
  const calls: Array<{ route: string; body: unknown }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/^api\//, "");
    const route = `${init?.method ?? "GET"} ${path}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ route, body });
    const handler = routes[route];
    if (!handler) return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    return new Response(JSON.stringify(handler(body)), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function renderApp(ui: ReactNode, overrides: Record<string, string> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <WordingProvider overrides={overrides} base={{ assistant: "Helper" }}>
      <QueryClientProvider client={client}>
        <ToastProvider seconds={0}>
          <OwnRequestsProvider>{ui}</OwnRequestsProvider>
        </ToastProvider>
      </QueryClientProvider>
    </WordingProvider>,
  );
}
