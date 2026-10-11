// Saved settings take effect when the app restarts itself a few seconds later. This keeps a notice up from the save
// until the app answers as a new start (or, with a server that can't say, until the event stream connects again). If
// no restart came in time, the notice says so and stays until dismissed, so nobody is left thinking it restarted.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { useWords } from "./wording";

type Phase = "idle" | "waiting" | "done" | "stuck";

interface RestartApi {
  waiting: boolean;
  phase: Phase;
  begin: () => void;
  dismiss: () => void;
}

const RestartContext = createContext<RestartApi>({ waiting: false, phase: "idle", begin: () => undefined, dismiss: () => undefined });

export function useRestart(): RestartApi {
  return useContext(RestartContext);
}

export const RESTART_WAIT_SECONDS = 60;
export const RESTART_DONE_SECONDS = 4;
export const RESTART_POLL_SECONDS = 2;

/** `hellos` is how many times the event stream has connected; the next one is a hint that the app is back. */
export function RestartProvider(props: { hellos: number; seconds?: number; doneSeconds?: number; pollSeconds?: number; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [since, setSince] = useState(0);
  // The start the app was on when the wait began: a text, null when the server doesn't say, undefined while it is looked up.
  const [baseline, setBaseline] = useState<string | null | undefined>(undefined);
  const latest = useRef(props.hellos);
  latest.current = props.hellos;
  const known = useRef<string | null | undefined>(undefined);
  const round = useRef(0);
  const seconds = props.seconds ?? RESTART_WAIT_SECONDS;
  const doneSeconds = props.doneSeconds ?? RESTART_DONE_SECONDS;
  const pollSeconds = props.pollSeconds ?? RESTART_POLL_SECONDS;

  const begin = useCallback(() => {
    const mine = ++round.current;
    setPhase("waiting");
    setSince(latest.current);
    setBaseline(known.current);
    if (known.current !== undefined) return;
    api.runtimeConfig().then(
      (config) => {
        known.current = config.instance ?? null;
        if (round.current === mine) setBaseline(known.current);
      },
      () => {
        if (round.current === mine) setBaseline(null);
      },
    );
  }, []);

  const dismiss = useCallback(() => {
    round.current += 1;
    setPhase("idle");
  }, []);

  // Asks the app which start it is on; a different one than before means it restarted. Failures are expected meanwhile.
  const check = useCallback(
    (mine: number, was: string, finish: () => void) => {
      api.runtimeConfig().then(
        (config) => {
          if (round.current !== mine) return;
          if (config.instance) known.current = config.instance;
          if (config.instance && config.instance !== was) finish();
        },
        () => undefined,
      );
    },
    [],
  );

  useEffect(() => {
    if (phase !== "waiting") return;
    const mine = round.current;
    const finish = () => setPhase("done");
    if (baseline === undefined) return;
    if (baseline === null) {
      if (props.hellos > since) finish();
      return;
    }
    if (props.hellos > since) check(mine, baseline, finish);
    const timer = window.setInterval(() => check(mine, baseline, finish), pollSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [phase, baseline, since, props.hellos, pollSeconds, check]);

  useEffect(() => {
    if (phase !== "waiting") return;
    const mine = round.current;
    const timer = window.setTimeout(() => {
      if (round.current === mine) setPhase("stuck");
    }, seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [phase, since, seconds]);

  useEffect(() => {
    if (phase !== "done") return;
    const timer = window.setTimeout(() => setPhase("idle"), doneSeconds * 1000);
    return () => window.clearTimeout(timer);
  }, [phase, doneSeconds]);

  const value = useMemo(() => ({ waiting: phase === "waiting", phase, begin, dismiss }), [phase, begin, dismiss]);
  return <RestartContext.Provider value={value}>{props.children}</RestartContext.Provider>;
}

/** The live region that says the app is restarting. It is always on the page, so a screen reader hears the change. */
export function RestartNotice() {
  const { t } = useWords();
  const { phase, dismiss } = useRestart();
  return (
    <div className="restart-slot" role="status" aria-live="polite">
      {phase !== "idle" && (
        <p className="notice restart">
          <span className="mark" aria-hidden="true">
            {phase === "done" ? "✓" : "!"}
          </span>
          <span className="notice-text">{t(phase === "waiting" ? "restart.restarting" : phase === "done" ? "restart.done" : "restart.stuck")}</span>
          {phase === "stuck" && (
            <button type="button" className="btn small" onClick={dismiss}>
              {t("restart.dismiss")}
            </button>
          )}
        </p>
      )}
    </div>
  );
}
