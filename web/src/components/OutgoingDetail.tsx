// One thing waiting to go out, in full (design 6.12, 7.4): its exact content as plain text, its target (each recipient by name
// with the address as it resolves now), the recipients called out with a box to acknowledge each by name, and the one primary:
// Approve and send, which confirms and then says yes on exactly what is shown and sends. A message the person sends themselves
// (the copy channel) has Copy and Mark sent instead. An act that went stale says what changed and asks to be looked at again
// before the yes is offered. Taking it back is in the menu, with Undo.
import { useId, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  actPhrase,
  actTitle,
  calledOut,
  canApprove,
  canTakeBack,
  changedWords,
  isByHand,
  partLabel,
  useOutgoing,
  type Act,
} from "../lib/acts";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { ActPill } from "./ActPill";
import { ConfirmSend } from "./ConfirmSend";
import { RowMenu, type MenuAction } from "./RowMenu";
import { restoreFocus } from "./ModalPanel";
import styles from "./Outgoing.module.css";

export function OutgoingDetail(props: {
  act: Act;
  /** The person has looked at this one again since it went stale (kept by the list, so a fresh read doesn't lose it). */
  looked: boolean;
  onLook: () => void;
}) {
  const { t, has } = useWords();
  const out = useOutgoing();
  const client = useQueryClient();
  const base = useId();
  const { act } = props;
  // A yes already given covered the recipients called out; one still to be given must name each of them.
  const called = act.status === "approved" ? [] : calledOut(act);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<null | "send" | "again">(null);
  const [busy, setBusy] = useState(false);
  const allTicked = called.every((r) => ticked.has(r.key));
  const acknowledged = called.filter((r) => ticked.has(r.key)).map((r) => r.key);
  const byHand = isByHand(act);
  const stale = act.status === "stale";
  const mustLook = stale && !props.looked;
  const offered = canApprove(act) || act.status === "approved";
  const blocked = !!act.withheld;
  const title = actTitle(act, t);
  const approveId = `${base}-approve`;

  const look = async () => {
    setBusy(true);
    await client.invalidateQueries({ queryKey: ["acts"] });
    props.onLook();
    setBusy(false);
  };
  const guard = async (run: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await run();
    } finally {
      setBusy(false);
    }
  };

  const toggle = (key: string, on: boolean) => {
    const next = new Set(ticked);
    if (on) next.add(key);
    else next.delete(key);
    setTicked(next);
  };

  const menu: MenuAction[] = canTakeBack(act) ? [{ id: "withdraw", label: t("outgoing.withdraw"), run: () => void out.withdraw(act) }] : [];
  const reasonAck = !allTicked ? t("outgoing.reason.acknowledge") : undefined;

  return (
    <div className={styles.detail} data-row="" tabIndex={-1} data-act={act.id}>
      <div className={styles.status}>
        <ActPill status={act.status} />
        <p>{t(`outgoing.state_long.${act.status}`)}</p>
      </div>
      {act.status === "failed" && act.failure && (
        <div role="alert" className="problem-note">
          <p>{t("outgoing.failure.text", { reason: act.failure.reason })}</p>
          <p>{t(`outgoing.failure.${act.failure.kind}`)}</p>
        </div>
      )}
      {mustLook && <p role="status">{t("outgoing.stale.text", { what: actPhrase(act, t), changed: changedWords(act, t) })}</p>}
      {stale && props.looked && <p role="status">{t("outgoing.stale.looked")}</p>}
      {act.status === "uncertain" && <p>{t("outgoing.uncertain.text")}</p>}
      {act.status === "sending" && <p>{t("outgoing.sending.text")}</p>}
      {blocked && (
        <p className="problem-note" role="alert">
          {act.withheld}
        </p>
      )}

      <section className={styles.section} aria-label={t("outgoing.section.content")}>
        <h3>{t("outgoing.section.content")}</h3>
        {Object.entries(act.parts).map(([name, text]) => (
          <div key={name} className={styles.part}>
            <p className={styles.partName}>{partLabel(name, t, has)}</p>
            <p className={styles.text} data-part={name}>
              {text}
            </p>
          </div>
        ))}
      </section>

      <section className={styles.section} aria-label={t(act.kind === "message" ? "outgoing.section.who" : "outgoing.section.where")}>
        <h3>{t(act.kind === "message" ? "outgoing.section.who" : "outgoing.section.where")}</h3>
        <ul className={styles.target}>
          {(act.recipients ?? []).map((r) => (
            <li key={r.key}>{t("outgoing.recipient", { role: t(`outgoing.role.${r.role}`), name: r.name, address: r.address })}</li>
          ))}
          {act.calendar && <li>{t("outgoing.calendar_line", { calendar: act.calendar })}</li>}
          {act.when && <li>{t("outgoing.when_line", { when: act.when })}</li>}
          {act.folder && <li>{t("outgoing.folder_line", { folder: act.folder })}</li>}
          {act.template && <li>{t("outgoing.template_line", { template: act.template })}</li>}
          <li>{t("outgoing.via", { channel: act.channel_label })}</li>
        </ul>
      </section>

      {offered && !mustLook && called.length > 0 && (
        <fieldset className={styles.callouts}>
          <legend>{t("outgoing.callouts.title")}</legend>
          <p className="hint">{t("outgoing.callouts.hint")}</p>
          {called.map((r) => {
            const id = `${base}-${r.key}`.replace(/[^A-Za-z0-9_-]/g, "-");
            return (
              <div key={r.key} className={styles.callout}>
                <label className="check-line" htmlFor={id}>
                  <input
                    id={id}
                    type="checkbox"
                    checked={ticked.has(r.key)}
                    aria-describedby={`${id}-why`}
                    onChange={(e) => toggle(r.key, e.target.checked)}
                  />
                  <span>{t("outgoing.callout.ack", { name: r.name, address: r.address })}</span>
                </label>
                <ul className={styles.reasons} id={`${id}-why`}>
                  {(r.reasons ?? []).map((why) => (
                    <li key={why}>{t(`outgoing.callout.${why}`)}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </fieldset>
      )}

      <div className={styles.actions}>
        {mustLook && (
          <Button variant="primary" disabled={busy} onClick={() => void look()}>
            {t("outgoing.look_again")}
          </Button>
        )}
        {act.status === "uncertain" && (
          <>
            <Button variant="primary" disabled={busy} onClick={() => void guard(() => out.markSent(act))}>
              {t("outgoing.uncertain.sent")}
            </Button>
            <Button id={approveId} disabled={busy} onClick={() => setConfirm("again")}>
              {t("outgoing.uncertain.again")}
            </Button>
          </>
        )}
        {offered && !mustLook && !byHand && (
          <Button
            id={approveId}
            variant="primary"
            disabled={busy || blocked || !allTicked}
            reason={blocked ? undefined : reasonAck}
            onClick={() => setConfirm("send")}
          >
            {t("outgoing.approve_send")}
          </Button>
        )}
        {offered && !mustLook && byHand && (
          <>
            <Button
              variant={act.status === "approved" ? "secondary" : "primary"}
              disabled={busy || blocked || !allTicked}
              reason={blocked ? undefined : reasonAck}
              onClick={() => void guard(() => out.copy(act, acknowledged))}
            >
              {t("outgoing.copy")}
            </Button>
            <Button
              variant={act.status === "approved" ? "primary" : "secondary"}
              disabled={busy || act.status !== "approved"}
              reason={act.status !== "approved" ? t("outgoing.reason.copy_first") : undefined}
              onClick={() => void guard(() => out.markSent(act))}
            >
              {t("outgoing.mark_sent")}
            </Button>
          </>
        )}
        <RowMenu label={title} actions={menu} />
      </div>
      {byHand && offered && !mustLook && <p className="hint">{t("outgoing.by_hand")}</p>}

      {confirm && (
        <ConfirmSend
          act={act}
          again={confirm === "again"}
          onCancel={() => {
            setConfirm(null);
            restoreFocus(() => document.getElementById(approveId));
          }}
          onGo={() => {
            const again = confirm === "again";
            setConfirm(null);
            void guard(() => (again ? out.sendAgain(act) : out.send(act, acknowledged)));
          }}
        />
      )}
    </div>
  );
}
