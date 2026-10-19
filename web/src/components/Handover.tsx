// Which copy to keep (design 5.0): this computer and the synced folder each changed while they couldn't sync, or another
// computer has the workspace open. The page shows both sides in plain words and, for a divergence, the two choices with
// what each does. A choice is only noted: it is carried out when the app restarts, before anything is opened, through the
// same checks the command line has, and until then it can be taken back. Only the person's click restarts the app.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type Ref } from "react";
import { api, ApiError, type S } from "../lib/api";
import { day, wallTime } from "../lib/dates";
import { problemText } from "../lib/problem";
import { useRestart } from "../lib/restart";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import styles from "./Handover.module.css";

type Side = S["HandoverSideView"];
type Which = S["HandoverChoice"]["which"];

/** A time the server wrote on the person's own clock, as day and time. */
const when = (iso: string) => `${day(iso)}, ${wallTime(iso)}`;

export function Handover() {
  const { t } = useWords();
  const client = useQueryClient();
  const page = useQuery({ queryKey: ["sync", "handover"], queryFn: api.handover });
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const restart = useRestart();
  const refresh = (view: S["HandoverView"]) => {
    client.setQueryData(["sync", "handover"], view);
    void client.invalidateQueries({ queryKey: ["today"] });
    void client.invalidateQueries({ queryKey: ["sync"] });
  };
  const choose = useMutation({ mutationFn: (which: Which) => api.chooseCopy(which), onSuccess: refresh });
  const changeMind = useMutation({ mutationFn: () => api.changeMindAboutCopy(), onSuccess: refresh });
  const view = page.data;
  const first = useRef<HTMLButtonElement>(null);
  // The cursor starts on the first choice when there is one to make; a page with nothing to choose keeps it on the heading.
  useEffect(() => {
    if (view?.state === "diverged") first.current?.focus();
  }, [view?.state]);
  const failure = choose.error ?? changeMind.error;
  const busy = choose.isPending || changeMind.isPending;
  return (
    <section className="panel-section" aria-labelledby="handover-title">
      <div className="heading">
        <h1 id="handover-title">{t("handover.title")}</h1>
      </div>
      {page.isPending ? (
        <Skeleton />
      ) : page.isError || !view ? (
        <p className="empty">
          {t("handover.failed")}{" "}
          <button type="button" className="btn" onClick={() => void page.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : view.state === "clear" ? (
        <p className="empty">{t("handover.clear")}</p>
      ) : view.state === "elsewhere" ? (
        <Elsewhere view={view} />
      ) : (
        <>
          <p>{t("handover.diverged")}</p>
          <ul className={styles.sides}>
            <SideRow title={t("handover.here")} side={view.here} />
            <SideRow title={t("handover.folder")} side={view.folder} />
          </ul>
          {view.state === "chosen" ? (
            <div className={styles.chosen} role="status">
              <p>{t(view.chosen === "folder" ? "handover.chosen_folder" : "handover.chosen_here")}</p>
              <p className="hint">{t(status.data && !status.data.can_restart ? "handover.chosen_manual" : "handover.chosen_note")}</p>
              <div className="row-end">
                {status.data?.can_restart && (
                  <Button variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
                    {t("restart.now")}
                  </Button>
                )}
                <Button disabled={busy} onClick={() => changeMind.mutate()}>
                  {t("handover.change_mind")}
                </Button>
              </div>
            </div>
          ) : (
            <ul className={styles.choices}>
              <Choice
                label={t("handover.keep_here")}
                what={t("handover.keep_here_what")}
                disabled={busy}
                buttonRef={first}
                onChoose={() => choose.mutate("here")}
              />
              <Choice
                label={t("handover.keep_folder")}
                what={t("handover.keep_folder_what")}
                disabled={busy}
                onChoose={() => choose.mutate("folder")}
              />
            </ul>
          )}
          {view.state === "diverged" && <p className="hint">{t("handover.when_restart")}</p>}
        </>
      )}
      {failure && (
        <p className="problem-note" role="alert">
          {failure instanceof ApiError && failure.detail ? failure.detail : problemText(failure, t)}
        </p>
      )}
    </section>
  );
}

function SideRow(props: { title: string; side?: Side | null }) {
  const { t, tn } = useWords();
  const { side } = props;
  return (
    <li className={styles.side}>
      <strong>{props.title}</strong>
      {side?.computer && <span className="sub">{t("handover.made_on", { computer: side.computer })}</span>}
      {side && side.changes > 0 && <span>{tn("handover.changes", side.changes)}</span>}
      {side?.latest && <span className="sub">{t("handover.latest", { when: when(side.latest) })}</span>}
    </li>
  );
}

function Choice(props: { label: string; what: string; disabled: boolean; onChoose: () => void; buttonRef?: Ref<HTMLButtonElement> }) {
  return (
    <li className={styles.choice}>
      <Button ref={props.buttonRef} disabled={props.disabled} onClick={props.onChoose}>
        {props.label}
      </Button>
      <p className={styles.what}>{props.what}</p>
    </li>
  );
}

function Elsewhere(props: { view: S["HandoverView"] }) {
  const { t, tn } = useWords();
  const { view } = props;
  return (
    <div className={styles.elsewhere}>
      <p>{view.computer ? t("handover.elsewhere", { computer: view.computer }) : t("handover.elsewhere_unknown")}</p>
      {view.last_seen && <p className="sub">{t("handover.elsewhere_seen", { when: when(view.last_seen) })}</p>}
      {view.minutes_left > 0 && <p>{tn("handover.elsewhere_wait", view.minutes_left)}</p>}
      <p className="hint">{t("handover.elsewhere_next")}</p>
    </div>
  );
}
