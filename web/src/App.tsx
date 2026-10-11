// The launch-slice home: one column with What changed and Follow-ups under the header (design 7.7).
import { useEffect, useMemo, useState } from "react";
import type { S } from "./lib/api";
import { useShortcuts } from "./lib/keys";
import { useLive } from "./lib/live";
import { useToasts } from "./lib/toasts";
import { useWords } from "./lib/wording";
import { AssistantNotice } from "./components/AssistantNotice";
import { Files } from "./components/Files";
import { FollowUps } from "./components/FollowUps";
import { HandIn } from "./components/HandIn";
import { Header } from "./components/Header";
import { Setup } from "./components/Setup";
import { StartHere } from "./components/StartHere";
import { Stages } from "./components/Stages";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { WhatChanged } from "./components/WhatChanged";

export function App(props: { rc: S["RuntimeConfig"] }) {
  const { t } = useWords();
  const live = useLive();
  const { undoLast } = useToasts();
  const [handIn, setHandIn] = useState(false);
  const [help, setHelp] = useState(false);
  const [view, setView] = useView();
  const handlers = useMemo(
    () => ({ undo: undoLast, hand_in: () => setHandIn(true), help: () => setHelp(true) }),
    [undoLast],
  );
  useShortcuts(props.rc.shortcuts, handlers);
  useNarrow(props.rc.narrow_below_px);
  useEffect(() => {
    document.title = props.rc.workspace_name;
  }, [props.rc.workspace_name]);

  return (
    <>
      <a href="#main" className="skip">
        {t("app.skip")}
      </a>
      <Header
        workspace={props.rc.workspace_name}
        live={live}
        view={view}
        onView={setView}
        onHandIn={() => setHandIn(true)}
        onHelp={() => setHelp(true)}
      />
      <main id="main" tabIndex={-1}>
        {handIn && <HandIn onClose={() => setHandIn(false)} />}
        {view === "home" ? (
          <>
            <AssistantNotice />
            <StartHere
              workspace={props.rc.workspace_name}
              onHandIn={() => setHandIn(true)}
              onOpenSetup={() => setView("setup")}
            />
            <WhatChanged />
            <FollowUps />
          </>
        ) : view === "stages" ? (
          <Stages />
        ) : view === "files" ? (
          <Files />
        ) : (
          <Setup />
        )}
        <p className="footer">{t("app.footer", { key: props.rc.shortcuts.help ?? "?" })}</p>
      </main>
      <ShortcutHelp open={help} onClose={() => setHelp(false)} keys={props.rc.shortcuts} />
    </>
  );
}

/** One column below the configured width: a data attribute the styles key off. */
function useNarrow(px: number) {
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(`(max-width: ${px - 1}px)`);
    const apply = () => document.documentElement.toggleAttribute("data-narrow", query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [px]);
}

export type View = "home" | "stages" | "files" | "setup";

/** Which view is showing, kept in the address's #fragment so a refresh or the back button keeps it. */
function useView(): [View, (v: View) => void] {
  const read = (): View => {
    const hash = window.location.hash.slice(1);
    return hash === "setup" || hash === "stages" || hash === "files" ? hash : "home";
  };
  const [view, setViewState] = useState<View>(read);
  useEffect(() => {
    const onHash = () => setViewState(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const setView = (v: View) => {
    window.location.hash = v === "home" ? "" : v;
    setViewState(v);
  };
  return [view, setView];
}
