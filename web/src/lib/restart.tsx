// Saved settings take effect when the app restarts itself a few seconds later. This keeps a notice up from the save
// until the event stream connects again (or a minute has passed, in case no restart came), so the screen says what
// is happening and the person is not left guessing.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useWords } from "./wording";

interface RestartApi {
  waiting: boolean;
  begin: () => void;
}

const RestartContext = createContext<RestartApi>({ waiting: false, begin: () => undefined });

export function useRestart(): RestartApi {
  return useContext(RestartContext);
}

export const RESTART_WAIT_SECONDS = 60;

/** `hellos` is how many times the event stream has connected; the next one means the app is back. */
export function RestartProvider(props: { hellos: number; seconds?: number; children: ReactNode }) {
  const [since, setSince] = useState<number | null>(null);
  const latest = useRef(props.hellos);
  latest.current = props.hellos;
  const seconds = props.seconds ?? RESTART_WAIT_SECONDS;

  const begin = useCallback(() => setSince(latest.current), []);

  useEffect(() => {
    if (since !== null && props.hellos > since) setSince(null);
  }, [since, props.hellos]);

  useEffect(() => {
    if (since === null) return;
    const timer = window.setTimeout(() => setSince(null), seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [since, seconds]);

  const value = useMemo(() => ({ waiting: since !== null, begin }), [since, begin]);
  return <RestartContext.Provider value={value}>{props.children}</RestartContext.Provider>;
}

/** The live region that says the app is restarting. It is always on the page, so a screen reader hears the change. */
export function RestartNotice() {
  const { t } = useWords();
  const { waiting } = useRestart();
  return (
    <div className="restart-slot" role="status" aria-live="polite">
      {waiting && (
        <p className="notice restart">
          <span className="mark" aria-hidden="true">
            !
          </span>
          <span className="notice-text">{t("restart.restarting")}</span>
        </p>
      )}
    </div>
  );
}
