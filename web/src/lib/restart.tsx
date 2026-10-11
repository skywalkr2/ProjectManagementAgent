// A change that needs a restart never restarts the app by itself: the person is asked first ("asking"), and only
// "Restart now" sends the request. Then a notice stays up until the app answers as a new start (or, with a server that
// can't say, until the event stream connects again). If no restart came in time, or the app can't restart itself, the
// notice says so and stays until dismissed, so nobody is left thinking it restarted.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { problemText } from "./problem";
import { useWords } from "./wording";

type Phase = "idle" | "asking" | "waiting" | "done" | "stuck" | "refused";

interface RestartApi {
  waiting: boolean;
  phase: Phase;
  /** The words for a restart the app couldn't do, when the phase is "refused". */
  problem: string;
  /** A restart was asked for and the answer has not come yet. */
  busy: boolean;
  /** Starts the notice that waits for the app to come back; the request itself is `now`. */
  begin: () => void;
  /** Asks the person whether to restart now; nothing restarts until they say so. */
  offer: () => void;
  /** Asks the app to restart, then waits for it. A refusal is shown in the notice. */
  now: () => Promise<void>;
  dismiss: () => void;
}

const RestartContext = createContext<RestartApi>({
  waiting: false,
  phase: "idle",
  problem: "",
  busy: false,
  begin: () => undefined,
  offer: () => undefined,
  now: () => Promise.resolve(),
  dismiss: () => undefined,
});

export function useRestart(): RestartApi {
  return useContext(RestartContext);
}

export const RESTART_WAIT_SECONDS = 60;
export const RESTART_DONE_SECONDS = 4;
export const RESTART_POLL_SECONDS = 2;

/** `hellos` is how many times the event stream has connected; the next one is a hint that the app is back. */
export function RestartProvider(props: { hellos: number; seconds?: number; doneSeconds?: number; pollSeconds?: number; children: ReactNode }) {
  const { t } = useWords();
  const [phase, setPhase] = useState<Phase>("idle");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
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

  const offer = useCallback(() => {
    setPhase((cur) => (cur === "idle" || cur === "stuck" || cur === "refused" ? "asking" : cur));
  }, []);

  const now = useCallback(async () => {
    setBusy(true);
    try {
      await api.restart();
      begin();
    } catch (err) {
      round.current += 1;
      setProblem(problemText(err, t));
      setPhase("refused");
    } finally {
      setBusy(false);
    }
  }, [begin, t]);

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

  const value = useMemo(
    () => ({ waiting: phase === "waiting", phase, problem, busy, begin, offer, now, dismiss }),
    [phase, problem, busy, begin, offer, now, dismiss],
  );
  return <RestartContext.Provider value={value}>{props.children}</RestartContext.Provider>;
}

/** The live region that asks about a restart and says it is happening. It is always on the page, so a screen reader hears the change. */
export function RestartNotice() {
  const { t } = useWords();
  const { phase, problem, busy, now, dismiss } = useRestart();
  const text =
    phase === "asking"
      ? t("restart.ask")
      : phase === "waiting"
        ? t("restart.restarting")
        : phase === "done"
          ? t("restart.done")
          : phase === "refused"
            ? problem
            : t("restart.stuck");
  return (
    <div className="restart-slot" role="status" aria-live="polite">
      {phase !== "idle" && (
        <p className="notice restart">
          <span className="mark" aria-hidden="true">
            {phase === "done" ? "✓" : "!"}
          </span>
          <span className="notice-text">{text}</span>
          {phase === "asking" && (
            <>
              <button type="button" className="btn primary small" disabled={busy} onClick={() => void now()}>
                {t("restart.now")}
              </button>
              <button type="button" className="btn small" onClick={dismiss}>
                {t("restart.later")}
              </button>
            </>
          )}
          {(phase === "stuck" || phase === "refused") && (
            <button type="button" className="btn small" onClick={dismiss}>
              {t("restart.dismiss")}
            </button>
          )}
        </p>
      )}
    </div>
  );
}
