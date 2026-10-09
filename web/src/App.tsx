// The launch-slice home: one column with What changed and Follow-ups under the header (design 7.7).
import { useEffect, useMemo, useState } from "react";
import type { S } from "./lib/api";
import { useShortcuts } from "./lib/keys";
import { useLive } from "./lib/live";
import { useToasts } from "./lib/toasts";
import { useWords } from "./lib/wording";
import { FollowUps } from "./components/FollowUps";
import { HandIn } from "./components/HandIn";
import { Header } from "./components/Header";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { WhatChanged } from "./components/WhatChanged";

export function App(props: { rc: S["RuntimeConfig"] }) {
  const { t } = useWords();
  const live = useLive();
  const { undoLast } = useToasts();
  const [handIn, setHandIn] = useState(false);
  const [help, setHelp] = useState(false);
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
      <Header workspace={props.rc.workspace_name} live={live} onHandIn={() => setHandIn(true)} onHelp={() => setHelp(true)} />
      <main id="main" tabIndex={-1}>
        {handIn && <HandIn onClose={() => setHandIn(false)} />}
        <WhatChanged />
        <FollowUps />
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
