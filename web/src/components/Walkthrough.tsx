// The new-start walkthrough (design 7.8): the setup as one guided path, full window, one screen at a time in the order a
// person needs them: You, Your AI account, Mail and calendar, Your promises (the first result: the look back and what it
// found), Backups, People, Done. Every screen says why it matters and
// can be skipped now and done later. The server keeps the screen the person is on, so it resumes where they left it,
// also after a restart; "Finish later" closes it for good, and it opens again only when the person asks. The core's own
// step forms are the ones the setup list uses.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useToastCount, useToasts } from "../lib/toasts";
import { after, before, counted, SCREENS, standing, STEP_OF, type Screen } from "../lib/walkthrough";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { FirstPromises } from "./FirstPromises";
import { StepList, WorkspaceStep } from "./Welcome";
import { WalkthroughMail } from "./WalkthroughMail";
import { WelcomeAi } from "./WelcomeAi";
import { WelcomeBackup } from "./WelcomeBackup";
import { WelcomeSpend } from "./WelcomeSpend";
import styles from "./Walkthrough.module.css";

export interface Handlers {
  onOpenPeople: () => void;
  onOpenAddons: () => void;
  onHandIn: () => void;
  onChooseSource: (plugin: string | null) => void;
}

export function Walkthrough(
  props: Handlers & {
    /** Open at this screen, when a line elsewhere sent the person to a step; `n` tells one request from the next. */
    at?: { screen: Screen; n: number } | null;
    /** Finish later was chosen, and kept. */
    onFinishLater: () => void;
    /** The last button was pressed, and kept. */
    onDone: () => void;
  },
) {
  const { t } = useWords();
  const client = useQueryClient();
  const { dismissAll } = useToasts();
  const shownToasts = useToastCount();
  const foot = useRef<HTMLDivElement>(null);
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const [chosen, setChosen] = useState<Screen | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const reopened = useRef(false);
  const requested = useRef(0);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const data = setup.data;
  // The screen the server named when this opened stays until the person moves: finishing a step must not move them on.
  const first = useRef<Screen | null>(null);
  if (data && first.current === null) first.current = data.walkthrough.step;
  const current: Screen | null = data ? (chosen ?? props.at?.screen ?? first.current) : null;

  // The request being sent, so the next waits for it: requests sent together can be handled in either order, and an
  // earlier screen arriving after a later one would be the one remembered.
  const sending = useRef<Promise<void>>(Promise.resolve());

  /** Keep where the walkthrough stands on the server, and in the list the other screens read. One request at a time,
   * in the order they were made. */
  const keep = (body: S["WalkthroughIn"]): Promise<void> => {
    const send = async () => {
      try {
        const view = await api.keepWalkthrough(body);
        client.setQueryData<S["SetupView"]>(["setup"], (old) => (old ? { ...old, walkthrough: view } : old));
      } catch {
        // The screen still works; it just won't be remembered.
      }
    };
    sending.current = sending.current.then(send);
    return sending.current;
  };

  // Opening it is the person's choice, so a walkthrough closed or finished before is open again from here. Keeping its
  // screen also records that it was shown, so it opens by itself again only while something it needs is missing.
  useEffect(() => {
    if (!data || !current || reopened.current) return;
    reopened.current = true;
    const again = data.walkthrough.closed || data.walkthrough.finished ? { closed: false, finished: false } : {};
    void keep({ step: current, ...again });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // A later request to open at a screen (the setup line, a status line) moves to it.
  useEffect(() => {
    if (!props.at || props.at.n === requested.current) return;
    requested.current = props.at.n;
    setChosen(props.at.screen);
    void keep({ step: props.at.screen, closed: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.at?.n]);

  // On opening and on every move, the cursor goes to the screen's first field, so the person can start typing; a screen
  // with no field puts it on its heading instead. A screen's fields can arrive a moment later, so it waits briefly.
  useEffect(() => {
    if (!current) return;
    let tries = 0;
    let timer = 0;
    const place = () => {
      const main = heading.current?.closest("main");
      const field = main?.querySelector<HTMLElement>(
        "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])",
      );
      if (field) field.focus();
      else if (tries++ < 10) timer = window.setTimeout(place, 50);
      else heading.current?.focus();
    };
    place();
    return () => window.clearTimeout(timer);
  }, [current]);

  // What a screen said in a toast is about that screen: moving to another one clears it.
  const shownScreen = useRef<Screen | null>(null);
  useEffect(() => {
    if (current && shownScreen.current && shownScreen.current !== current) dismissAll();
    if (current) shownScreen.current = current;
  }, [current, dismissAll]);

  // A toast that appears over the screen's own buttons moves them clear of it; buttons that are off the screen stay put.
  useEffect(() => {
    if (!shownToasts) return;
    // After the page has made room for them.
    const frame = window.requestAnimationFrame(() => {
      const buttons = foot.current?.getBoundingClientRect();
      const toasts = document.querySelector("[data-toast-region]")?.getBoundingClientRect();
      if (!buttons || !toasts) return;
      if (buttons.top < window.innerHeight && buttons.bottom > toasts.top) {
        window.scrollBy?.({ top: buttons.bottom - toasts.top + 8 });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [shownToasts]);

  if (!data || !current) {
    return (
      <div className={styles.root}>
        <div className={styles.layout}>{setup.isError ? <p className="empty">{t("welcome.failed")}</p> : <Skeleton />}</div>
      </div>
    );
  }

  const steps = data.steps;
  const go = (screen: Screen) => {
    setChosen(screen);
    void keep({ step: screen });
  };
  const here = standing(steps, current);
  const next = after(current);
  const previous = before(current);

  const skip = async () => {
    const id = STEP_OF[current];
    if (!id) return;
    setBusy(true);
    setProblem("");
    try {
      await api.skipStep(id);
      await client.invalidateQueries({ queryKey: ["setup"] });
      if (next) go(next);
    } catch (err) {
      setProblem(problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  const finishLater = async () => {
    await keep({ closed: true });
    props.onFinishLater();
  };
  const finish = async () => {
    await keep({ finished: true });
    props.onDone();
  };

  const stepData = (id: string) => steps.find((s) => s.id === id);
  const aiDone = !!stepData("ai")?.done;
  const hasMailSteps = steps.some((s) => s.group === "mail" && !!s.plugin && !s.sign_in);
  const handlers = {
    onOpenPeople: props.onOpenPeople,
    onOpenAddons: props.onOpenAddons,
    onHandIn: props.onHandIn,
    onChooseSource: props.onChooseSource,
  };

  return (
    <div className={styles.root} data-walkthrough="">
      <header className={styles.head}>
        <div className={styles.title}>
          <h1 id="walkthrough-title">{t("walkthrough.title")}</h1>
          <p className={styles.intro}>{t("walkthrough.intro")}</p>
        </div>
        <Button onClick={() => void finishLater()}>{t("walkthrough.later")}</Button>
      </header>
      <div className={styles.layout}>
        <nav aria-label={t("walkthrough.screens")}>
          <ol className={styles.screens}>
            {SCREENS.map((screen) => {
              const state = standing(steps, screen);
              return (
                <li key={screen}>
                  <button
                    type="button"
                    className={styles.screen}
                    data-screen={screen}
                    data-state={state ?? undefined}
                    aria-current={screen === current ? "step" : undefined}
                    onClick={() => go(screen)}
                  >
                    <span>{t(`walkthrough.screen.${screen}`)}</span>
                    {state && (
                      <span className={styles.mark}>
                        <span aria-hidden="true">{state === "done" ? "✓ " : state === "skipped" ? "– " : "○ "}</span>
                        {t(`walkthrough.state.${state}`)}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        <main id="main" className={styles.step} tabIndex={-1} aria-labelledby="walkthrough-screen-title" data-screen={current}>
          <h2 id="walkthrough-screen-title" ref={heading} tabIndex={-1}>
            {t(`walkthrough.screen.${current}`)}
          </h2>
          <p className={styles.why}>{t(`walkthrough.why.${current}`)}</p>
          {current === "you" && <WorkspaceStep />}
          {current === "ai" && (
            <>
              <WelcomeAi local={data.local} done={aiDone} />
              <WelcomeSpend />
            </>
          )}
          {current === "mail" && (
            <>
              <WalkthroughMail onChooseSource={props.onChooseSource} onOpenAddons={props.onOpenAddons} />
              {hasMailSteps && <StepList include={(s) => s.group === "mail" && !!s.plugin && !s.sign_in} {...handlers} />}
            </>
          )}
          {current === "promises" && <FirstPromises go={go} />}
          {current === "backup" && <WelcomeBackup local={data.local} />}
          {current === "people" && (
            <div className="row-end">
              <button type="button" className="btn" onClick={props.onOpenPeople}>
                {t("walkthrough.people.open")}
              </button>
            </div>
          )}
          {current === "done" && <DoneScreen go={go} {...handlers} />}
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          <div className={styles.foot} ref={foot}>
            {previous && <Button onClick={() => go(previous)}>{t("walkthrough.back")}</Button>}
            <span className={styles.grow} />
            {current === "done" ? (
              <Button variant="primary" onClick={() => void finish()}>
                {t("walkthrough.finish")}
              </Button>
            ) : here === "todo" ? (
              <Button disabled={busy} onClick={() => void skip()}>
                {t("walkthrough.skip")}
              </Button>
            ) : (
              next && (
                <Button variant="primary" onClick={() => go(next)}>
                  {t("walkthrough.next")}
                </Button>
              )
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

/** The last screen: what was set up and what was skipped (each with a way back to it), then the optional extras. */
function DoneScreen(props: Handlers & { go: (screen: Screen) => void }) {
  const { t } = useWords();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  if (!setup.data) return <Skeleton />;
  const steps = counted(setup.data.steps);
  return (
    <>
      <ul className={styles.recap} aria-label={t("walkthrough.done.recap")}>
        {steps.map((step) => {
          const screen = step.group;
          const state = step.done ? "done" : step.skipped ? "skipped" : "todo";
          const label = t(`walkthrough.screen.${screen}`);
          return (
            <li key={step.id} data-step={step.id} data-state={state}>
              <span className={`what ${styles.what}`}>
                <span aria-hidden="true">{state === "done" ? "✓ " : state === "skipped" ? "– " : "○ "}</span>
                {label}
              </span>
              <span className="sub">{t(`walkthrough.done.${state}`)}</span>
              {state !== "done" && (
                <button
                  type="button"
                  className="btn"
                  aria-label={t("walkthrough.done.set_up_named", { label })}
                  onClick={() => props.go(screen)}
                >
                  {t("walkthrough.done.set_up")}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <section className={styles.extras} aria-labelledby="walkthrough-extras">
        <h3 id="walkthrough-extras">{t("walkthrough.extras.title")}</h3>
        <p className={styles.why}>{t("walkthrough.extras.why")}</p>
        <StepList
          include={(s) => s.group === "done"}
          onOpenPeople={props.onOpenPeople}
          onOpenAddons={props.onOpenAddons}
          onHandIn={props.onHandIn}
          onChooseSource={props.onChooseSource}
        />
      </section>
      <p className={styles.why}>{t("walkthrough.done.next")}</p>
    </>
  );
}
