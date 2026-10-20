// Waiting to go out (design 7.4): where what is ready to leave (a message, a page, a file) waits for the person's approval
// of its exact content. Sending and publishing are not built yet, so today the screen is its empty state, designed: it says
// what will wait here, that nothing leaves without approval, and how a message leaves in the meantime (copied from
// Follow-ups, sent by the person, marked sent).
import type { View } from "../lib/views";
import { useWords } from "../lib/wording";
import { EmptyState } from "../ui/EmptyState";

export function WaitingToGoOut(props: { onView: (view: View) => void }) {
  const { t } = useWords();
  return (
    <section className="panel-section" aria-labelledby="outgoing-title">
      <div className="heading">
        <h1 id="outgoing-title">{t("nav.outgoing")}</h1>
      </div>
      <p className="hint">{t("outgoing.intro")}</p>
      <EmptyState icon="upload" text={t("outgoing.empty")} action={{ label: t("outgoing.open_changes"), onClick: () => props.onView("work/changed") }}>
        <p className="hint">{t("outgoing.today")}</p>
        <button type="button" className="link-button" onClick={() => props.onView("work/followups")}>
          {t("outgoing.open_followups")}
        </button>
      </EmptyState>
    </section>
  );
}
