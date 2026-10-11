// Starting a sign-in: ask the server for the service's page, then send this tab there. Shared by every place that offers
// "Sign in" (the Sign-ins rows, the setup guide) so they behave the same. The service sends the person back afterwards
// (see lib/sign-in-return.ts).
import { useState } from "react";
import { api } from "./api";
import { problemText } from "./problem";
import { useWords } from "./wording";

export function useStartSignIn(name: string): { start: () => Promise<void>; busy: boolean; problem: string } {
  const { t } = useWords();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const start = async () => {
    setBusy(true);
    setProblem("");
    try {
      const started = await api.startSignIn(name);
      // The service's own page replaces this one; the busy state stays until it does.
      window.location.assign(started.url);
    } catch (err) {
      setProblem(problemText(err, t));
      setBusy(false);
    }
  };
  return { start, busy, problem };
}
