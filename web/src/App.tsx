// The launch-slice home: one column with What changed and Follow-ups under the header (design 7.7).
import { useEffect, useMemo, useRef, useState } from "react";
import type { S } from "./lib/api";
import { useShortcuts } from "./lib/keys";
import { useLive } from "./lib/live";
import { useToasts } from "./lib/toasts";
import { fromHash, parseView, recordView, toHash, type View } from "./lib/views";
import { useWords } from "./lib/wording";
import { AssistantNotice } from "./components/AssistantNotice";
import { Files } from "./components/Files";
import { FollowUps } from "./components/FollowUps";
import { HandIn } from "./components/HandIn";
import { Panel } from "./components/Panel";
import { PluginToday } from "./components/PluginToday";
import { RecordPage } from "./components/RecordPage";
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
  // Where a record's page goes back to: the screen it was opened from.
  const origin = useRef<View>("home");
  const openRecord = (kind: string, id: string) => {
    if (parseView(view).type !== "record") origin.current = view;
    setView(recordView(kind, id));
  };
  const shown = parseView(view);
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
        {shown.type === "panel" ? (
          <Panel key={shown.name} name={shown.name} onOpenRecord={openRecord} />
        ) : shown.type === "record" ? (
          <RecordPage
            key={`${shown.kind}:${shown.id}`}
            kind={shown.kind}
            id={shown.id}
            onBack={() => setView(origin.current)}
          />
        ) : view === "home" ? (
          <>
            <AssistantNotice />
            <StartHere
              workspace={props.rc.workspace_name}
              onHandIn={() => setHandIn(true)}
              onOpenSetup={() => setView("setup")}
            />
            <WhatChanged />
            <PluginToday />
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

export type { View } from "./lib/views";

/** Which view is showing, kept in the address's #fragment so a refresh or the back button keeps it. */
function useView(): [View, (v: View) => void] {
  const [view, setViewState] = useState<View>(() => fromHash(window.location.hash));
  useEffect(() => {
    const onHash = () => setViewState(fromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const setView = (v: View) => {
    window.location.hash = toHash(v);
    setViewState(v);
  };
  return [view, setView];
}
