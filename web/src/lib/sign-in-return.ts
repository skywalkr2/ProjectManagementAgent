// Coming back from a service's sign-in page: the app is opened at its root with `sign_in` (and the sign-in's name) in
// the query string. One toast says how it went, then those parameters leave the address so a reload doesn't repeat it.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "./api";
import { useToasts } from "./toasts";
import { useWords } from "./wording";

const OUTCOMES = new Set(["done", "failed", "refused", "expired"]);

/** Removes the sign-in parameters from the address, keeping the path (the base path), any other parameters and the hash. */
export function clearSignInParams(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("sign_in");
  url.searchParams.delete("name");
  const query = url.searchParams.toString();
  window.history.replaceState(window.history.state, "", `${url.pathname}${query ? `?${query}` : ""}${url.hash}`);
}

export function useSignInReturn(): void {
  const { t } = useWords();
  const { push } = useToasts();
  const client = useQueryClient();
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get("sign_in");
    if (outcome === null) return;
    const name = params.get("name");
    // The address is cleaned first, so a second run of this effect (or a reload) finds nothing to announce.
    clearSignInParams();
    if (!OUTCOMES.has(outcome)) return;
    void (async () => {
      let message = t(`sign_in.return.${outcome}`);
      if (outcome === "done") {
        message = t("sign_in.return.done_generic");
        try {
          const all = await client.fetchQuery({ queryKey: ["sign-ins"], queryFn: api.signIns, staleTime: 0 });
          const found = all.find((s) => s.name === name);
          if (found) message = t("sign_in.return.done", { label: found.label });
        } catch {
          // The generic wording stands when the list can't be read.
        }
      }
      push({ message });
    })();
  }, []);
}
