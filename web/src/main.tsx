import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { api, ApiError, type S } from "./lib/api";
import { ToastProvider } from "./lib/toasts";
import { WordingProvider, useWords } from "./lib/wording";
import { OwnRequestsProvider } from "./components/HandIn";
import "./styles.css";

const client = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: true, retry: 1 } },
});

function Problem(props: { signedOut: boolean }) {
  const { t } = useWords();
  return (
    <main id="main" className="problem">
      <h1>{t(props.signedOut ? "app.signed_out_title" : "app.unreachable_title")}</h1>
      <p>{t(props.signedOut ? "app.signed_out" : "app.unreachable")}</p>
      {!props.signedOut && (
        <button type="button" className="btn primary" onClick={() => window.location.reload()}>
          {"↻"} {t("action.try_again")}
        </button>
      )}
    </main>
  );
}

function start(rc: S["RuntimeConfig"]) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <WordingProvider overrides={rc.wording} base={{ assistant: rc.assistant_name, workspace: rc.workspace_name }}>
        <QueryClientProvider client={client}>
          <ToastProvider seconds={rc.toast_seconds}>
            <OwnRequestsProvider>
              <App rc={rc} />
            </OwnRequestsProvider>
          </ToastProvider>
        </QueryClientProvider>
      </WordingProvider>
    </StrictMode>,
  );
}

api.runtimeConfig().then(start, (err: unknown) => {
  createRoot(document.getElementById("root")!).render(
    <WordingProvider>
      <Problem signedOut={err instanceof ApiError && err.status === 401} />
    </WordingProvider>,
  );
});
