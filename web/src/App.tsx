// The app shell (design 7.1): one grid with the header across the top, the sidebar on the left (a bottom bar on a phone) and
// the content area, which is the only thing that changes when the view does. Every view is a link in the address's fragment.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type S } from "./lib/api";
import { useShortcuts } from "./lib/keys";
import { useLive } from "./lib/live";
import { showNewLines } from "./lib/queue-hold";
import { useNarrow } from "./lib/media";
import { RestartAnnouncer, RestartProvider, useRestart } from "./lib/restart";
import { useRestartWhat } from "./lib/restart-for";
import { useSignInReturn } from "./lib/sign-in-return";
import { useToasts } from "./lib/toasts";
import { fromHash, parseView, recordView, settingsView, toHash, type View } from "./lib/views";
import { screenOf, type Screen } from "./lib/walkthrough";
import { useWords } from "./lib/wording";
import { Addons } from "./components/Addons";
import { AiCompare } from "./components/AiCompare";
import { Ask } from "./components/Ask";
import { Feedback } from "./components/Feedback";
import { Files } from "./components/Files";
import { FollowUps } from "./components/FollowUps";
import { OpenItems } from "./components/OpenItems";
import { HandIn } from "./components/HandIn";
import { Handover } from "./components/Handover";
import { Quality } from "./components/Quality";
import { Knowledge } from "./components/Knowledge";
import { MissedOneProvider } from "./components/MissedOne";
import { Panel } from "./components/Panel";
import { People } from "./components/People";
import { Projects } from "./components/Projects";
import { restoreFocus } from "./components/ModalPanel";
import { RecordPage } from "./components/RecordPage";
import { RuleReview } from "./components/RuleReview";
import { SeriesPage } from "./components/SeriesPage";
import { Settings } from "./components/Settings";
import { Sources, type AddRequest } from "./components/Sources";
import { StyleGuide } from "./components/StyleGuide";
import { Stages } from "./components/Stages";
import { Today } from "./components/Today";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { SinceYesterday } from "./components/SinceYesterday";
import { WhatChanged } from "./components/WhatChanged";
import { Walkthrough } from "./components/Walkthrough";
import { BottomBar } from "./shell/BottomBar";
import { Header } from "./shell/Header";
import { Sidebar, useSidebarMode } from "./shell/Sidebar";
import { EmptyState } from "./ui/EmptyState";
import shell from "./shell/Shell.module.css";

export function App(props: { rc: S["RuntimeConfig"] }) {
  const live = useLive();
  return (
    <RestartProvider hellos={live.hellos}>
      <MissedOneProvider>
        <Shell rc={props.rc} live={live} />
      </MissedOneProvider>
    </RestartProvider>
  );
}

/** The style guide is for development and demo workspaces only. */
const styleGuideShown = (rc: S["RuntimeConfig"]) => rc.demo || import.meta.env.DEV;

/** The first visible element that matches, so a control that exists twice (a field and an icon) is found where it shows. */
function visible(selector: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>(selector));
  return all.find((el) => el.getClientRects().length > 0) ?? all[0] ?? null;
}

function Shell(props: { rc: S["RuntimeConfig"]; live: ReturnType<typeof useLive> }) {
  const { rc, live } = props;
  const { t } = useWords();
  const { undoLast, push } = useToasts();
  useSignInReturn();
  const narrow = useNarrow(rc.narrow_below_px);
  const sidebar = useSidebarMode();
  const [handIn, setHandIn] = useState(false);
  const [help, setHelp] = useState(false);
  const [feedback, setFeedback] = useState(false);
  // The Ask box, with the question it opens on when a screen suggests one.
  const [ask, setAsk] = useState<{ question?: string } | null>(null);
  const [view, setView] = useView();
  // The setup walkthrough opens at a screen when a line elsewhere sends the person to a step.
  const [guideAt, setGuideAt] = useState<{ screen: Screen; n: number } | null>(null);
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const focusFirstGo = useFocusFirstGo();
  // Sources opens on the form that adds one when Today or a sign-in sends the person there.
  const [addSource, setAddSource] = useState<AddRequest | null>(null);
  // Settings opens on the form that adds an AI account when a Today line sends the person there.
  const [addAccount, setAddAccount] = useState<number | null>(null);
  // A screen that puts focus somewhere of its own on opening (a step's heading, a form) keeps it.
  const ownFocus = useRef(false);
  const openAddSource = (plugin: string | null = null) => {
    ownFocus.current = true;
    setAddSource({ plugin, n: Date.now() });
    setView("sources");
  };
  const openGuide = (step?: string) => {
    // The walkthrough puts focus on its own heading.
    ownFocus.current = true;
    const screen = step && setup.data ? screenOf(setup.data.steps, step) : null;
    setGuideAt(screen ? { screen, n: Date.now() } : null);
    setView("setup");
  };
  // Where a record's page goes back to: the screen it was opened from.
  const origin = useRef<View>("today");
  const openRecord = (kind: string, id: string) => {
    if (parseView(view).type !== "record") origin.current = view;
    setView(recordView(kind, id));
  };
  const shown = parseView(view);
  // The grid of what each account can do and the quality figures belong to Settings, so Settings stays marked in the navigation.
  const navView: View = view === "settings/ai-compare" || view === "quality" || (shown.type === "core" && shown.view === "settings") ? "settings" : view;
  const inWalkthrough = shown.type === "core" && shown.view === "setup";
  // A new workspace's first visit opens the walkthrough by itself, once: the server says whether it should (it has not
  // been closed or finished, and setup is not done). A person who arrives at another screen, or has already opened
  // something on Today (the hand-in box, Ask, help or feedback), is not taken from it, so nothing they typed is lost.
  const autoOpened = useRef(false);
  useEffect(() => {
    if (autoOpened.current || !setup.data) return;
    autoOpened.current = true;
    const busy = handIn || ask !== null || help || feedback;
    if (setup.data.walkthrough?.open && shown.type === "core" && shown.view === "today" && !busy) setView("setup");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setup.data]);
  const handlers = useMemo(
    () => ({ undo: undoLast, hand_in: () => setHandIn(true), ask: () => setAsk({}), help: () => setHelp(true), show_new: showNewLines }),
    [undoLast],
  );
  const keys = rc.shortcuts;
  useShortcuts(keys, handlers);
  useEffect(() => {
    document.title = rc.workspace_name;
  }, [rc.workspace_name]);

  // After going to another view (not on the first load), focus moves to the new view's heading.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    window.scrollTo?.(0, 0);
    // Settings puts the cursor in the open section's first field itself.
    const now = parseView(view);
    if (now.type === "core" && now.view === "settings") {
      ownFocus.current = false;
      return;
    }
    if (ownFocus.current) {
      ownFocus.current = false;
      return;
    }
    const heading = document.querySelector<HTMLElement>("main h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }, [view]);

  const restart = useRestart();
  const what = useRestartWhat();
  const restartNow = useRef(restart.now);
  restartNow.current = restart.now;
  // A change that needs a restart says so with a toast that holds the button; the status chip keeps it afterwards.
  useEffect(() => {
    if (restart.phase !== "asking") return;
    push({ message: t("restart.toast"), action: { label: t("restart.now"), run: () => restartNow.current() } });
  }, [restart.phase, push, t]);

  const body = (() => {
    if (shown.type === "panel") return <Panel key={shown.name} name={shown.name} onOpenRecord={openRecord} />;
    if (shown.type === "record" && shown.kind === "series") {
      return <SeriesPage key={shown.id} id={shown.id} onBack={() => setView(origin.current)} />;
    }
    if (shown.type === "record") {
      return <RecordPage key={`${shown.kind}:${shown.id}`} kind={shown.kind} id={shown.id} onBack={() => setView(origin.current)} />;
    }
    switch (shown.view) {
      case "today":
        return (
          <Today
            workspace={rc.workspace_name}
            onView={setView}
            onAddSource={() => openAddSource()}
            onOpenRecord={openRecord}
            onOpenGuide={openGuide}
            shortcuts={rc.shortcuts}
            onAddAccount={() => {
              setAddAccount(Date.now());
              setView(settingsView("ai"));
            }}
          />
        );
      case "work/changed":
        return <WhatChanged onOpenGuide={openGuide} />;
      case "work/since":
        return <SinceYesterday onOpenRecord={openRecord} />;
      case "work/followups":
        return <FollowUps />;
      case "work/open":
        return <OpenItems />;
      case "work/outgoing":
        return (
          <section className="panel-section" aria-labelledby="outgoing-title">
            <div className="heading">
              <h1 id="outgoing-title">{t("nav.outgoing")}</h1>
            </div>
            <EmptyState icon="upload" text={t("outgoing.empty")} action={{ label: t("outgoing.open_changes"), onClick: () => setView("work/changed") }} />
          </section>
        );
      case "work/stages":
        return <Stages />;
      case "records/projects":
        return <Projects />;
      case "records/people":
        return <People />;
      case "records/files":
        return <Files />;
      case "records/knowledge":
        return <Knowledge onOpenReview={() => setView("records/rules-review")} />;
      case "records/rules-review":
        return <RuleReview onBack={() => setView("records/knowledge")} />;
      case "sources":
        return (
          <Sources
            onAsk={(question) => setAsk({ question })}
            add={addSource}
            onAddOpened={() => setAddSource(null)}
            onOpenAddons={() => setView("addons")}
          />
        );
      case "setup":
        return null;
      case "settings":
        return (
          <Settings
            onOpenGuide={openGuide}
            onOpenAddons={() => setView("addons")}
            onChooseSource={openAddSource}
            onOpenKnowledge={() => setView("records/knowledge")}
            onOpenCompare={() => setView("settings/ai-compare")}
            onOpenSources={() => setView("sources")}
            onOpenQuality={() => setView("quality")}
            section={shown.section}
            onSection={(section) => setView(settingsView(section))}
            addAccount={addAccount}
            onAddAccountOpened={() => setAddAccount(null)}
          />
        );
      case "settings/ai-compare":
        return <AiCompare onBack={() => setView(settingsView("ai"))} />;
      case "addons":
        return <Addons onBack={() => setView("settings")} />;
      case "handover":
        return <Handover />;
      case "quality":
        return <Quality onBack={() => setView("settings")} />;
      case "styleguide":
        return styleGuideShown(rc) ? <StyleGuide /> : null;
      default:
        return null;
    }
  })();

  const overlays = (
    <>
      <RestartAnnouncer what={what} />
      {ask && (
        <Ask
          initial={ask.question}
          feedbackTo={rc.feedback_to}
          onClose={() => {
            setAsk(null);
            restoreFocus(() => visible("[data-ask-button]"));
          }}
        />
      )}
      {feedback && (
        <Feedback
          view={view}
          version={rc.version}
          to={rc.feedback_to}
          onClose={() => {
            setFeedback(false);
            restoreFocus(() => visible("[data-feedback-button]"));
          }}
        />
      )}
      <ShortcutHelp open={help} onClose={() => setHelp(false)} keys={keys} />
    </>
  );
  if (inWalkthrough) {
    return (
      <>
        <Walkthrough
          at={guideAt}
          onOpenPeople={() => setView("records/people")}
          onOpenAddons={() => setView("addons")}
          onHandIn={() => {
            // The hand-in box takes focus itself.
            ownFocus.current = true;
            setView("today");
            setHandIn(true);
          }}
          onChooseSource={openAddSource}
          onFinishLater={() => setView("today")}
          onDone={() => {
            setView("today");
            focusFirstGo();
          }}
        />
        {handIn && <HandIn onClose={() => setHandIn(false)} />}
        {overlays}
      </>
    );
  }

  const skip = (event: React.MouseEvent) => {
    event.preventDefault();
    document.getElementById("main")?.focus();
  };
  const openFeedback = () => setFeedback(true);
  return (
    <>
      <a href="#main" className="skip" onClick={skip}>
        {t("app.skip")}
      </a>
      <div className={[shell.app, sidebar.expanded ? "" : shell.rail].filter(Boolean).join(" ")} data-nav={sidebar.expanded ? "full" : "rail"}>
        <Header
          rc={rc}
          live={live}
          narrow={narrow}
          shortcuts={keys}
          onHandIn={() => setHandIn(true)}
          onAsk={() => setAsk({})}
          onHelp={() => setHelp(true)}
          onFeedback={openFeedback}
          onOpenGuide={openGuide}
        />
        {!narrow && <Sidebar current={navView} expanded={sidebar.expanded} onToggle={sidebar.toggle} />}
        <main id="main" className={shell.main} tabIndex={-1}>
          {handIn && <HandIn onClose={() => setHandIn(false)} />}
          {body}
        </main>
      </div>
      {narrow && (
        <BottomBar
          current={navView}
          version={rc.version}
          onHandIn={() => setHandIn(true)}
          onAsk={() => setAsk({})}
          onHelp={() => setHelp(true)}
          onFeedback={openFeedback}
          onOpenGuide={() => openGuide()}
        />
      )}
      {overlays}
    </>
  );
}

export type { View } from "./lib/views";

/** Which view is showing, kept in the address's #fragment so a refresh, the back button and a bookmark all keep it. */
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

/** Puts focus on Today's first-go line once it is on the page, after the walkthrough closes onto Today. The line may take a
 * moment to appear; the wait is short and gives up quietly when there is no such line. */
function useFocusFirstGo(): () => void {
  const [asked, setAsked] = useState(0);
  useEffect(() => {
    if (!asked) return;
    let tries = 0;
    const timer = window.setInterval(() => {
      const row = document.querySelector<HTMLElement>('[data-queue-line="first_go"]');
      tries += 1;
      if (row) {
        window.clearInterval(timer);
        row.scrollIntoView?.({ block: "center" });
        row.focus();
        // A row taller than the pane that holds it can't be centered whole; its button must still be on the screen.
        row.querySelector("button")?.scrollIntoView?.({ block: "nearest" });
      } else if (tries >= 25) {
        window.clearInterval(timer);
      }
    }, 200);
    return () => window.clearInterval(timer);
  }, [asked]);
  return () => setAsked(Date.now());
}
