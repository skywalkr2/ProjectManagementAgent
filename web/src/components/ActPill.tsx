// An outward act's state as a pill: a word and an icon together, never colour alone (design 7.4, 7.12).
import { type ActState } from "../lib/acts";
import { useWords } from "../lib/wording";
import { Icon, type IconName } from "../ui/Icon";
import { Pill, type PillTone } from "../ui/Pill";
import styles from "./Outgoing.module.css";

const MARK: Record<ActState, { icon: IconName; tone: PillTone }> = {
  draft: { icon: "send", tone: "need" },
  approved: { icon: "check", tone: "ok" },
  sending: { icon: "refresh", tone: "neutral" },
  sent: { icon: "check", tone: "ok" },
  failed: { icon: "alert", tone: "danger" },
  uncertain: { icon: "help", tone: "warn" },
  stale: { icon: "refresh", tone: "warn" },
  withdrawn: { icon: "close", tone: "neutral" },
  undone: { icon: "close", tone: "neutral" },
};

export function ActPill(props: { status: ActState }) {
  const { t } = useWords();
  const mark = MARK[props.status];
  return (
    <Pill tone={mark.tone}>
      <span className={styles.mark}>
        <Icon name={mark.icon} size={14} />
        {t(`outgoing.state.${props.status}`)}
      </span>
    </Pill>
  );
}
