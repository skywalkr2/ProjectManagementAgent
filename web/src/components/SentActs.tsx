// What went out (design 6.12, 7.4): the acts that were sent, newest first, under what still waits. A mailbox change, or an
// event the app created, can be taken back while its service allows: Take back is in the line's menu, with the answer in a toast
// (done, or why not). One that was taken back says so, and one the service refused to take back keeps the reason.
import { dayAndTime } from "../lib/dates";
import { actTitle, useOutgoing, useSentActs, type Act } from "../lib/acts";
import { useWords } from "../lib/wording";
import { Row } from "../ui/Row";
import { ActPill } from "./ActPill";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";

export function SentActs() {
  const { t } = useWords();
  const sent = useSentActs();
  const rows = sent.data ?? [];
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="outgoing-sent-title" data-sent-acts="">
      <h2 id="outgoing-sent-title">{t("outgoing.sent.title")}</h2>
      <ol className="queue" aria-label={t("outgoing.sent.list")}>
        {rows.map((a) => (
          <SentRow key={a.id} act={a} />
        ))}
      </ol>
    </section>
  );
}

function SentRow(props: { act: Act }) {
  const { t } = useWords();
  const out = useOutgoing();
  const { act } = props;
  const title = actTitle(act, t);
  const titleId = `sent-${act.id}`;
  const menu: MenuAction[] = act.undoable ? [{ id: "take-back", label: t("outgoing.take_back"), run: () => void out.takeBack(act) }] : [];
  const note = act.undo_failure ? t("outgoing.take_back.failed", { reason: act.undo_failure.reason }) : "";
  const when = act.sent_at ? t("outgoing.sent.when", { when: dayAndTime(act.sent_at) }) : "";
  return (
    <Row
      aria-labelledby={titleId}
      pill={<ActPill status={act.status} />}
      title={
        <span id={titleId}>
          <SafeText text={title} />
        </span>
      }
      meta={[when, note].filter(Boolean).join(" · ")}
      menu={menu.length > 0 ? <RowMenu label={title} actions={menu} /> : undefined}
      data-act-sent={act.id}
    />
  );
}
