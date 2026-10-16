// The Today screen (design 7.7): what needs the person as a ranked queue, the selected line's items in the inspector
// (from 1680px; below that they open under the line), and the rail of the agenda, the person's to-dos and what came in.
import { useEffect, useRef, useState } from "react";
import { longDay } from "../lib/dates";
import { useMediaQuery } from "../lib/media";
import { showRow, useReveal } from "../lib/reveal";
import { useQueue, useTodayCount } from "../lib/today";
import type { View } from "../lib/views";
import { useWords } from "../lib/wording";
import { BackupLine } from "../shell/BackupLine";
import { SetupLine } from "../shell/SetupLine";
import { Button } from "../ui/Button";
import { Panel } from "../ui/Panel";
import { LineDetail, opensItems } from "./TodayDetail";
import { TodayQueue, type QueueHandlers, type Selection } from "./TodayQueue";
import { TodayRail } from "./TodayRail";
import styles from "./Today.module.css";

/** The width from which the inspector sits beside the queue (the layout's third column). */
const INSPECTOR_FROM = "(min-width: 1680px)";

export function Today(props: {
  workspace: string;
  onView: (view: View) => void;
  onAddSource: () => void;
  onOpenGuide: (step?: string) => void;
  onOpenRecord: (kind: string, id: string) => void;
}) {
  const { t, tn } = useWords();
  const beside = useMediaQuery(INSPECTOR_FROM);
  const queue = useQueue();
  const count = useTodayCount();
  const [selected, setSelected] = useState<Selection | null>(null);
  const line = selected ? queue.data?.find((l) => l.key === selected.key) : undefined;

  // Another part of the screen asks for an answer or a question to be looked at: its line opens, with the cursor on it.
  const [shown, setShown] = useState<string | null>(null);
  const open = (find: (l: NonNullable<typeof queue.data>[number]) => boolean) => {
    const found = queue.data?.find((l) => opensItems(l) && find(l));
    if (!found) return false;
    setSelected({ key: found.key, sendBack: false });
    setShown(found.key);
    return true;
  };
  useReveal("changeset", (id) => open((l) => l.changeset === id));
  useReveal("question", (id) => open((l) => l.question === id));
  const shownRow = useRef<string | null>(null);
  useEffect(() => {
    if (!shown || shownRow.current === shown) return;
    shownRow.current = shown;
    showRow(document.querySelector<HTMLElement>(`[data-line-key="${CSS.escape(shown)}"]`));
  }, [shown, selected]);

  const handlers: QueueHandlers = {
    onOpenAiAccounts: () => props.onView("settings"),
    onOpenHandover: () => props.onView("handover"),
    onOpenRules: () => props.onView("records/rules-review"),
    onOpenRecord: props.onOpenRecord,
    onOpenGuide: props.onOpenGuide,
  };
  return (
    <div className={styles.today}>
      <div className={styles.head}>
        <h1>{t("nav.home")}</h1>
        <p>{[longDay(new Date()), count === null ? "" : count === 0 ? t("today.needs.none") : tn("today.needs.count", count)].filter(Boolean).join(" · ")}</p>
      </div>
      <div className={styles.full}>
        <SetupLine workspace={props.workspace} onOpenGuide={props.onOpenGuide} />
      </div>
      <div className={styles.full}>
        <BackupLine onOpenGuide={props.onOpenGuide} />
      </div>
      <TodayQueue selected={selected} onSelect={setSelected} beside={beside} handlers={handlers} />
      {beside && (
        <aside className={styles.inspector} aria-label={t("queue.inspector.title")}>
          <Panel
            title={t("queue.inspector.title")}
            actions={
              line && (
                <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                  {t("action.close")}
                </Button>
              )
            }
          >
            {line ? (
              <div className={styles.detail}>
                <LineDetail line={line} sendBack={selected?.sendBack} onOpenGuide={props.onOpenGuide} />
              </div>
            ) : (
              <p className={styles.inspectorEmpty}>{t("queue.inspector.empty")}</p>
            )}
          </Panel>
        </aside>
      )}
      <TodayRail onView={props.onView} onAddSource={props.onAddSource} />
    </div>
  );
}
