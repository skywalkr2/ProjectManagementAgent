// Waiting to go out (design 7.4, 6.12): where what is ready to leave (a message, a calendar entry, a file) waits for the
// person's approval of its exact content. One line for each, with its state in words and an icon and its one button; the one
// chosen shows in full beside the list (a drawer below 1024px). With nothing waiting, the screen says what will wait here, that
// nothing leaves without approval, and how a message leaves in the meantime (copied from Follow-ups, sent by the person,
// marked sent).
import { useEffect, useRef, useState } from "react";
import { actTitle, subjectOf, useWaitingActs, canTakeBack, isByHand, useOutgoing, changedWords, type Act } from "../lib/acts";
import { useRowKeys } from "../lib/keys";
import { useListChoice, type ListChoice } from "../lib/list-choice";
import { useMediaQuery } from "../lib/media";
import { useReveal } from "../lib/reveal";
import type { View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { ListDetail } from "../ui/ListDetail";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { ActPill } from "./ActPill";
import { OutgoingDetail } from "./OutgoingDetail";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SentActs } from "./SentActs";
import { SafeText } from "./SafeText";

export function WaitingToGoOut(props: { onView: (view: View) => void }) {
  const { t } = useWords();
  const acts = useWaitingActs();
  const rows = acts.data ?? [];
  const beside = useMediaQuery("(min-width: 1024px)");
  const choice = useListChoice({ keys: rows.map((a) => a.id), beside });
  // The acts the person has looked at again since they went stale; a fresh read keeps it.
  const [looked, setLooked] = useState<Record<string, true>>({});
  const look = (id: string) => setLooked((now) => ({ ...now, [id]: true }));
  const selected = rows.find((a) => a.id === choice.chosen) ?? null;

  // Another part of the app (a Today line) asks for one to be opened; it may be asked before the list has loaded.
  const [want, setWant] = useState<string | null>(null);
  useReveal("act", (id) => {
    setWant(id);
    return true;
  });
  const { enter } = choice;
  useEffect(() => {
    if (want === null || !acts.data) return;
    if (acts.data.some((a) => a.id === want)) enter(want);
    setWant(null);
  }, [want, acts.data, enter]);

  return (
    <section className="panel-section" aria-labelledby="outgoing-title">
      <div className="heading">
        <h1 id="outgoing-title">{t("nav.outgoing")}</h1>
      </div>
      <p className="hint">{t("outgoing.intro")}</p>
      {acts.isPending ? (
        <Skeleton />
      ) : acts.isError ? (
        <p className="empty">
          {t("outgoing.load_failed")}{" "}
          <Button size="sm" onClick={() => void acts.refetch()}>
            {t("action.try_again")}
          </Button>
        </p>
      ) : rows.length === 0 ? (
        <EmptyState icon="upload" text={t("outgoing.empty")} action={{ label: t("outgoing.open_changes"), onClick: () => props.onView("work/changed") }}>
          <p className="hint">{t("outgoing.today")}</p>
          <button type="button" className="link-button" onClick={() => props.onView("work/followups")}>
            {t("outgoing.open_followups")}
          </button>
        </EmptyState>
      ) : (
        <ListDetail
          title={selected ? actTitle(selected, t) : ""}
          onClose={choice.close}
          detail={
            selected ? <OutgoingDetail key={`${selected.id}:${selected.fingerprint}`} act={selected} looked={!!looked[selected.id]} onLook={() => look(selected.id)} /> : null
          }
        >
          <ol className="queue" aria-label={t("outgoing.list")}>
            {rows.map((a) => (
              <OutgoingRow key={a.id} act={a} choice={choice} onLook={() => look(a.id)} />
            ))}
          </ol>
        </ListDetail>
      )}
      {!acts.isPending && !acts.isError && <SentActs />}
    </section>
  );
}

function OutgoingRow(props: { act: Act; choice: ListChoice; onLook: () => void }) {
  const { t } = useWords();
  const out = useOutgoing();
  const ref = useRef<HTMLLIElement & HTMLDivElement>(null);
  const { act, choice } = props;
  const title = actTitle(act, t);
  const titleId = `outgoing-${act.id}`;

  const label =
    act.status === "stale"
      ? "outgoing.primary.look"
      : act.status === "uncertain"
        ? "outgoing.primary.check"
        : isByHand(act)
          ? "outgoing.primary.review_copy"
          : "outgoing.primary.review";
  const open = () => {
    if (act.status === "stale") props.onLook();
    choice.enter(act.id);
  };
  const primary = act.status === "sending" ? null : open;
  useRowKeys(ref, { toggle: () => choice.enter(act.id), primary: primary ?? undefined });

  const menu: MenuAction[] = canTakeBack(act) ? [{ id: "withdraw", label: t("outgoing.withdraw"), run: () => void out.withdraw(act) }] : [];
  const note =
    act.status === "failed" && act.failure
      ? t("outgoing.failure.text", { reason: act.failure.reason })
      : act.status === "stale"
        ? t("outgoing.stale.row", { changed: changedWords(act, t) })
        : t(`outgoing.state_long.${act.status}`);
  const subject = subjectOf(act);

  return (
    <Row
      ref={ref}
      aria-labelledby={titleId}
      pill={<ActPill status={act.status} />}
      title={
        <span id={titleId}>
          <SafeText text={title} />
        </span>
      }
      meta={[subject, note].filter(Boolean).join(" · ")}
      primary={
        primary ? (
          <Button size="sm" variant="primary" data-key="primary" aria-describedby={titleId} onClick={primary}>
            {t(label)}
          </Button>
        ) : undefined
      }
      menu={<RowMenu label={title} actions={menu} />}
      {...choice.rowProps(act.id)}
    />
  );
}
