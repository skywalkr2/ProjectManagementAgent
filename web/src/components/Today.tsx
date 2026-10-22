// The Today screen (design 7.7): what needs the person as a ranked queue, the line that has the cursor in the inspector
// (from 1680px; below that a line's items open under it), and the rail of top priorities, the week, the agenda, the person's
// to-dos and what came in.
import { useEffect, useRef, useState } from "react";
import { longDay } from "../lib/dates";
import { useMediaQuery } from "../lib/media";
import { showRow, useReveal } from "../lib/reveal";
import { onSide, setSideChoice, useSideFilter } from "../lib/sides";
import { useQueue, useTodayCount } from "../lib/today";
import { settingsView, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { SetupLine } from "../shell/SetupLine";
import { BriefCard } from "./BriefCard";
import { CoverageLine, useNoneText } from "./Coverage";
import { SideFilter } from "./SideFilter";
import { opensItems } from "./TodayDetail";
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
  /** Opens the form that hands something to the assistant. */
  onHandIn?: () => void;
  /** Opens the form that adds an AI account, in Settings. */
  onAddAccount?: () => void;
  onOpenRecord: (kind: string, id: string) => void;
  /** The configured shortcut keys, for the inspector's "j / k". */
  shortcuts?: Record<string, string>;
}) {
  const { t, tn } = useWords();
  const beside = useMediaQuery(INSPECTOR_FROM);
  const filter = useSideFilter();
  const queue = useQueue();
  const count = useTodayCount(filter.choice);
  const none = useNoneText();
  const [selected, setSelected] = useState<Selection | null>(null);

  // Another part of the screen asks for an answer or a question to be looked at: its line opens, with the cursor on it.
  const [shown, setShown] = useState<string | null>(null);
  // A line the side filter hides is still the one asked for, so the filter goes back to All to show it.
  const reveal = (side: Parameters<typeof onSide>[0]) => {
    if (!onSide(side, filter.choice)) setSideChoice("all");
  };
  const open = (find: (l: NonNullable<typeof queue.data>[number]) => boolean) => {
    const found = queue.data?.find((l) => opensItems(l) && find(l));
    if (!found) return false;
    reveal(found.side);
    setSelected({ key: found.key, sendBack: false });
    setShown(found.key);
    return true;
  };
  useReveal("changeset", (id) => open((l) => l.changeset === id));
  useReveal("question", (id) => open((l) => l.question === id));
  // A line named by its key (Top priorities links to the queue line of what it lists): it opens, with the cursor on it.
  useReveal("line", (key) => {
    const found = queue.data?.find((l) => l.key === key);
    if (!found) return false;
    reveal(found.side);
    setSelected({ key: found.key, sendBack: false });
    setShown(found.key);
    return true;
  });
  const shownRow = useRef<string | null>(null);
  useEffect(() => {
    if (!shown || shownRow.current === shown) return;
    shownRow.current = shown;
    showRow(document.querySelector<HTMLElement>(`[data-line-key="${CSS.escape(shown)}"]`));
  }, [shown, selected]);

  const handlers: QueueHandlers = {
    onOpenAiAccounts: () => props.onView(settingsView("ai")),
    onOpenHandover: () => props.onView("handover"),
    onOpenRules: () => props.onView("records/rules-review"),
    onOpenKnowledge: () => props.onView("records/knowledge"),
    onAddAccount: props.onAddAccount,
    onOpenSources: () => props.onView("sources"),
    onOpenRecord: props.onOpenRecord,
    onOpenGuide: props.onOpenGuide,
    onHandIn: props.onHandIn,
    onOpenView: props.onView,
  };
  return (
    <div className={styles.today}>
      <div className={styles.head}>
        <h1>{t("nav.home")}</h1>
        <SideFilter />
        <p>
          {[longDay(new Date()), count === null ? "" : count === 0 ? (filter.choice === "all" ? none : t("sides.today.none", { side: filter.named })) : tn("today.needs.count", count)]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <CoverageLine />
      </div>
      <div className={styles.full}>
        <SetupLine workspace={props.workspace} onOpenGuide={props.onOpenGuide} />
      </div>
      <TodayQueue selected={selected} onSelect={setSelected} beside={beside} handlers={handlers} shortcuts={props.shortcuts} />
      {/* The brief opens the rail, so the queue's own lines stay first on the page. */}
      <TodayRail
        onView={props.onView}
        onAddSource={props.onAddSource}
        brief={<BriefCard workspace={props.workspace} onOpenRecord={props.onOpenRecord} onOpenView={props.onView} />}
      />
    </div>
  );
}
