// The app shell: the header, the screen the address names, and Today, the home, as a board of columns (design 7.7).
import { useEffect, useMemo, useRef, useState } from "react";
import type { S } from "./lib/api";
import { useShortcuts } from "./lib/keys";
import { useLive } from "./lib/live";
import { RestartNotice, RestartProvider } from "./lib/restart";
import { useRestartWhat } from "./lib/restart-for";
import { useSignInReturn } from "./lib/sign-in-return";
import { useToasts } from "./lib/toasts";
import { fromHash, parseView, recordView, toHash, type View } from "./lib/views";
import { useWords } from "./lib/wording";
import { Addons } from "./components/Addons";
import { Ask } from "./components/Ask";
import { AssistantNotice } from "./components/AssistantNotice";
import { DemoStrip } from "./components/DemoStrip";
import { Feedback } from "./components/Feedback";
import { Files } from "./components/Files";
import { HandIn } from "./components/HandIn";
import { Panel } from "./components/Panel";
import { restoreFocus } from "./components/ModalPanel";
import { RecordPage } from "./components/RecordPage";
import { Header } from "./components/Header";
import { Settings } from "./components/Settings";
import { Sources } from "./components/Sources";
import { Setup } from "./components/Setup";
import { StartHere } from "./components/StartHere";
import { TodayBoard } from "./components/TodayBoard";
import { Stages } from "./components/Stages";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { Welcome, type FocusStep } from "./components/Welcome";

export function App(props: { rc: S["RuntimeConfig"] }) {
  const { t } = useWords();
  const live = useLive();
  const { undoLast } = useToasts();
  useSignInReturn();
  const [handIn, setHandIn] = useState(false);
  const [help, setHelp] = useState(false);
  const [feedback, setFeedback] = useState(false);
  // The Ask box, with the question it opens on when a screen suggests one.
  const [ask, setAsk] = useState<{ question?: string } | null>(null);
  const [view, setView] = useView();
  // The setup guide opens at a step when Today's card sends the person to one.
  const [guideStep, setGuideStep] = useState<FocusStep | null>(null);
  const openGuide = (step?: string) => {
    setGuideStep(step ? { id: step, n: Date.now() } : null);
    setView("welcome");
  };
  // Where a record's page goes back to: the screen it was opened from.
  const origin = useRef<View>("home");
  const openRecord = (kind: string, id: string) => {
    if (parseView(view).type !== "record") origin.current = view;
    setView(recordView(kind, id));
  };
  const shown = parseView(view);
  const handlers = useMemo(
    () => ({ undo: undoLast, hand_in: () => setHandIn(true), ask: () => setAsk({}), help: () => setHelp(true) }),
    [undoLast],
  );
  const keys = props.rc.shortcuts;
  useShortcuts(keys, handlers);
  useNarrow(props.rc.narrow_below_px);
  useEffect(() => {
    document.title = props.rc.workspace_name;
  }, [props.rc.workspace_name]);

  return (
    <RestartProvider hellos={live.hellos}>
      <a href="#main" className="skip">
        {t("app.skip")}
      </a>
      {props.rc.demo && <DemoStrip />}
      <Header
        workspace={props.rc.workspace_name}
        live={live}
        view={view}
        onView={setView}
        onHandIn={() => setHandIn(true)}
        onAsk={() => setAsk({})}
        onHelp={() => setHelp(true)}
      />
      <RestartAsk />
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
              onOpenGuide={openGuide}
            />
            <TodayBoard onView={setView} onOpenRecord={openRecord} />
          </>
        ) : view === "stages" ? (
          <Stages />
        ) : view === "files" ? (
          <Files />
        ) : view === "sources" ? (
          <Sources onAsk={(question) => setAsk({ question })} />
        ) : view === "welcome" ? (
          <Welcome
            focusStep={guideStep}
            onOpenPeople={() => setView("setup")}
            onOpenAddons={() => setView("addons")}
            onHandIn={() => setHandIn(true)}
          />
        ) : view === "settings" ? (
          <Settings onOpenGuide={() => openGuide()} onOpenAddons={() => setView("addons")} />
        ) : view === "addons" ? (
          <Addons onBack={() => setView("settings")} />
        ) : (
          <Setup />
        )}
        <footer className="footer">
          <p>{t("app.footer", { key: props.rc.shortcuts.help ?? "?" })}</p>
          <p className="footer-feedback">
            <button type="button" className="link-button" data-feedback-button onClick={() => setFeedback(true)}>
              {t("feedback.open")}
            </button>
            <span aria-hidden="true">·</span>
            <span>{t("app.version", { version: props.rc.version })}</span>
          </p>
        </footer>
      </main>
      {ask && (
        <Ask
          initial={ask.question}
          feedbackTo={props.rc.feedback_to}
          onClose={() => {
            setAsk(null);
            restoreFocus(() => document.querySelector<HTMLElement>("[data-ask-button]"));
          }}
        />
      )}
      {feedback && (
        <Feedback
          view={view}
          version={props.rc.version}
          to={props.rc.feedback_to}
          onClose={() => {
            setFeedback(false);
            restoreFocus(() => document.querySelector<HTMLElement>("[data-feedback-button]"));
          }}
        />
      )}
      <ShortcutHelp open={help} onClose={() => setHelp(false)} keys={keys} />
    </RestartProvider>
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

/** The restart notice with what waits for the restart named in it. */
function RestartAsk() {
  return <RestartNotice what={useRestartWhat()} />;
}
