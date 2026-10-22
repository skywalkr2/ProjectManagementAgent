// Today's lines for work that has stopped or that needs a look before it can go on (design 7.7, 8.5): work held until the
// app restarts, an AI account paused until its usage limit resets, work waiting for the network, the synced folder that
// can't be used until the person settles which copy to keep, a backup account that hasn't passed its check, a kind of
// file that isn't being read, the standing rules to look over, and a switch of account or model whose check found
// problems.
// Each is one row of the Today queue that says what to do first, with the one button that does it (a few offer a second,
// as design 7.6 allows for held lines). The lines come from the queue; a line is gone once its cause is, and only the
// person's own click ever restarts the app.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useAccountNames } from "../lib/account-names";
import { whenWords } from "../lib/coverage";
import { day, wallWhen } from "../lib/dates";
import { useEstimate } from "../lib/money";
import { useRestart, useRestartText } from "../lib/restart";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useStartSignIn } from "../lib/sign-in-start";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { MenuButton } from "../ui/MenuButton";
import { Pill } from "../ui/Pill";
import { AccountMoveLine, ModelMovedLine, ModelWatchLine } from "./ModelLines";
import styles from "./HeldLines.module.css";

type Line = S["QueueLineView"];

/** The kinds of queue line that are a stop or a check on the assistant's own work, each drawn here with its one button. */
export const HELD_KINDS: Line["kind"][] = ["restart", "paused", "borrow", "credential", "no_account", "offline", "handover", "account_check", "switch_failed", "account_move", "model_watch", "model_moved", "identity", "work_access", "extractor", "source_unread", "rule_review", "catch_up_go", "intake_go"];

export function isHeld(line: Line): boolean {
  return HELD_KINDS.includes(line.kind);
}

/** One held line of the Today queue, drawn by its kind. */
export function HeldLine(props: {
  line: Line;
  onOpenAiAccounts: () => void;
  onOpenHandover: () => void;
  onOpenRules?: () => void;
  onOpenKnowledge?: () => void;
  onAddAccount?: () => void;
  onOpenSources?: () => void;
}) {
  const { line } = props;
  switch (line.kind) {
    case "restart":
      return <RestartLine line={line} />;
    case "handover":
      return <HandoverLine line={line} onOpen={props.onOpenHandover} />;
    case "borrow":
      return <BorrowLine line={line} />;
    case "credential":
      return <CredentialLine line={line} onOpenAiAccounts={props.onOpenAiAccounts} />;
    case "offline":
      return <OfflineLine line={line} />;
    case "account_check":
      return <AccountCheckLine line={line} />;
    case "switch_failed":
      return <SwitchFailedLine line={line} />;
    case "account_move":
      return <AccountMoveLine line={line} />;
    case "model_watch":
      return <ModelWatchLine line={line} />;
    case "model_moved":
      return <ModelMovedLine line={line} />;
    case "identity":
      return <IdentityLine line={line} onOpenAiAccounts={props.onOpenAiAccounts} />;
    case "work_access":
      return <WorkAccessLine line={line} />;
    case "extractor":
      return <ExtractorLine line={line} />;
    case "source_unread":
      return <SourceUnreadLine line={line} onOpen={props.onOpenSources} />;
    case "rule_review":
      return <RuleReviewLine line={line} onOpen={props.onOpenRules} onOpenKnowledge={props.onOpenKnowledge} />;
    case "no_account":
      return <NoAccountLine line={line} onAdd={props.onAddAccount ?? props.onOpenAiAccounts} />;
    case "catch_up_go":
      return <CatchUpGoLine line={line} />;
    case "intake_go":
      return <IntakeGoLine line={line} />;
    default:
      return <PausedLine line={line} onOpenAiAccounts={props.onOpenAiAccounts} />;
  }
}

function RestartLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const restart = useRestart();
  const progress = useRestartText();
  const canRestart = !!status.data?.can_restart;
  const label = tn("queue.restart", props.line.count);
  // While a restart is under way its own words replace the explanation, so the line follows the same flow as the header.
  const sub = progress && restart.phase !== "asking" ? progress : t(status.data && !canRestart ? "queue.restart.manual" : "queue.restart.sub");
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.restart.label")} data-queue-line="restart">
      <Pill tone="warn">{t("queue.restart.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      {canRestart && (
        <div className={styles.actions}>
          <Button size="sm" variant="primary" data-key="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        </div>
      )}
    </section>
  );
}

function PausedLine(props: { line: Line; onOpenAiAccounts: () => void }) {
  const { t, tn } = useWords();
  const nameOf = useAccountNames();
  const { line } = props;
  const label = tn("queue.paused", line.count, { account: nameOf(line.account ?? ""), time: line.until ? wallWhen(line.until) : "" });
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.paused.label")} data-queue-line="paused">
      <Pill tone="warn">{t("queue.paused.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{t("queue.paused.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" onClick={props.onOpenAiAccounts}>
          {t("queue.paused.open")}
        </Button>
      </div>
    </section>
  );
}

/** Every account a kind of work can use is waiting for its limit to reset and another kind of work's account is free:
 * the question says which, until when and what it would cost, and nothing is borrowed until the person says yes. */
function BorrowLine(props: { line: Line }) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const nameOf = useAccountNames();
  const { line } = props;
  const accountId = line.account ?? "";
  const account = nameOf(accountId);
  const paused = nameOf(line.text ?? "");
  const time = line.until ? wallWhen(line.until) : "";
  const work = t(has(`queue.borrow.work.${line.tier}`) ? `queue.borrow.work.${line.tier}` : "queue.borrow.work.other");
  const cost = line.estimate_usd == null ? null : estimate(line.estimate_usd);
  const sub =
    cost === null
      ? tn("queue.borrow.unpriced", line.count)
      : line.unpriced > 0
        ? tn("queue.borrow.mixed", line.count, { cost })
        : tn("queue.borrow.priced", line.count, { cost });
  const answer = async (use: boolean) => {
    setBusy(use ? "yes" : "no");
    await act(
      () => api.borrowAccount({ tier: line.tier ?? "", account: accountId, model: line.model ?? "", use }),
      () => ({ message: use ? t("queue.borrow.yes_toast", { account, time }) : t("queue.borrow.no_toast", { paused }) }),
    );
    setBusy(null);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.borrow.label")} data-queue-line="borrow">
      <Pill tone="warn">{t("queue.borrow.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.borrow", { account, work, paused, time })}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy === "yes"} disabled={busy !== null} aria-label={t("queue.borrow.yes_named", { account, work })} onClick={() => void answer(true)}>
          {t("queue.borrow.yes")}
        </Button>
        <Button size="sm" variant="secondary" loading={busy === "no"} disabled={busy !== null} onClick={() => void answer(false)}>
          {t("queue.borrow.no")}
        </Button>
      </div>
    </section>
  );
}

/** A key or sign-in that stops working on a known day, or already has: what to renew and by when, every place the same
 * credential is used, and the one button that starts renewing it. The line is gone once the new end date is set or the
 * sign-in is made again. */
function CredentialLine(props: { line: Line; onOpenAiAccounts: () => void }) {
  const { t } = useWords();
  const { line } = props;
  const [first = "", ...others] = line.places ?? [];
  const signIn = line.credential_kind === "sign_in";
  const past = (line.waiting_days ?? 0) < 0;
  const date = line.due ? day(line.due) : "";
  const { start, busy, problem } = useStartSignIn(line.credential_name ?? "");
  const text = t(`queue.credential.${signIn ? "sign_in" : "account"}.${past ? "past" : "soon"}`, { thing: first, date });
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.credential.label")} data-queue-line="credential">
      <Pill tone="warn">{t("queue.credential.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        {others.length > 0 ? (
          <>
            <p className={styles.sub}>{t("queue.credential.also")}</p>
            <ul className={styles.places}>
              {others.map((place) => (
                <li key={place}>{place}</li>
              ))}
            </ul>
          </>
        ) : (
          <p className={styles.sub}>{t("queue.credential.only")}</p>
        )}
        {problem && <p className="problem-note">{problem}</p>}
      </div>
      <div className={styles.actions}>
        {signIn ? (
          <Button size="sm" variant="primary" data-key="primary" loading={busy} onClick={() => void start()}>
            {t("queue.credential.sign_in")}
          </Button>
        ) : (
          <Button size="sm" variant="primary" data-key="primary" onClick={props.onOpenAiAccounts}>
            {t("queue.credential.open")}
          </Button>
        )}
      </div>
    </section>
  );
}

function OfflineLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const { line } = props;
  const label = tn("queue.offline", line.count, { time: line.waiting_since ? wallWhen(line.waiting_since) : "" });
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.offline.label")} data-queue-line="offline">
      <Pill tone="warn">{t("queue.offline.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{t("queue.offline.sub")}</p>
      </div>
    </section>
  );
}

function HandoverLine(props: { line: Line; onOpen: () => void }) {
  const { t } = useWords();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const restart = useRestart();
  const state = props.line.state ?? "diverged";
  const computer = props.line.text ?? "";
  const text =
    state === "chosen"
      ? t("queue.handover.chosen")
      : state === "elsewhere"
        ? computer
          ? t("queue.handover.elsewhere", { computer })
          : t("queue.handover.elsewhere_unknown")
        : t("queue.handover.diverged");
  // Once a copy is chosen the one thing left is the restart, and only the person's click restarts.
  const canRestart = state === "chosen" && !!status.data?.can_restart;
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.handover.label")} data-queue-line="handover">
      <Pill tone="warn">{t("queue.handover.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t(`queue.handover.${state}_sub`)}</p>
      </div>
      <div className={styles.actions}>
        {canRestart && (
          <Button size="sm" variant="primary" data-key="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        )}
        <Button size="sm" variant={canRestart ? "secondary" : "primary"} data-key={canRestart ? undefined : "primary"} onClick={props.onOpen}>
          {t(`queue.handover.open_${state}`)}
        </Button>
      </div>
    </section>
  );
}

/** A backup account that hasn't passed its check for the work it would stand in for: Check now runs that test, and the
 * line is gone once it passes. */
function AccountCheckLine(props: { line: Line }) {
  const { t, has } = useWords();
  const act = useAct();
  const nameOf = useAccountNames();
  const [checking, setChecking] = useState(false);
  const { line } = props;
  const accountId = line.account ?? "";
  const account = nameOf(accountId);
  const work = t(has(`queue.account_check.work.${line.tier}`) ? `queue.account_check.work.${line.tier}` : "queue.account_check.work.other");
  const run = async () => {
    setChecking(true);
    await act(
      () => api.testAccount(accountId, line.tier ?? undefined, line.model ?? undefined),
      (results) => {
        const bad = results.find((r) => !r.ok);
        return { message: bad ? t("queue.account_check.not_passed", { account, detail: bad.detail }) : t("queue.account_check.passed", { account, work }) };
      },
    );
    setChecking(false);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.account_check.label")} data-queue-line="account_check">
      <Pill tone="warn">{t("queue.account_check.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.account_check", { account, work })}</p>
        <p className={styles.sub}>{t(line.check_failed ? "queue.account_check.sub_failed" : "queue.account_check.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={checking} aria-label={t("queue.account_check.run_named", { account, work })} onClick={() => void run()}>
          {t("queue.account_check.run")}
        </Button>
      </div>
    </section>
  );
}

/** A switch of a kind of work's account or model whose check found problems, or couldn't finish: what didn't come out
 * right, and the two ways forward. Switch back puts the earlier choice back at once, with Undo; Keep it leaves the
 * switch. The line is gone once either is chosen. */
function SwitchFailedLine(props: { line: Line }) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const fingerprint = useFreshFingerprint();
  const [busy, setBusy] = useState<"back" | "keep" | null>(null);
  const nameOf = useAccountNames();
  const { line } = props;
  const tier = line.tier ?? "";
  const account = nameOf(line.account ?? "");
  const previous = nameOf(line.text ?? "");
  const work = t(has(`queue.switch_failed.work.${tier}`) ? `queue.switch_failed.work.${tier}` : "queue.switch_failed.work.other");
  const names = line.names ?? [];
  const back = async () => {
    setBusy("back");
    await act(
      async () => api.switchBack(tier, await fingerprint()),
      () => ({ message: t("queue.switch_failed.back_toast", { work, previous }) }),
    );
    setBusy(null);
  };
  const keep = async () => {
    setBusy("keep");
    await act(
      () => api.keepSwitch(tier),
      () => ({ message: t("queue.switch_failed.keep_toast", { account, work }) }),
    );
    setBusy(null);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.switch_failed.label")} data-queue-line="switch_failed">
      <Pill tone="warn">{t("queue.switch_failed.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.switch_failed", { account, work })}</p>
        <p className={styles.sub}>{line.check_failed ? t("queue.switch_failed.sub_unfinished") : tn("queue.switch_failed.sub", line.count)}</p>
        {names.length > 0 && (
          <ul className={styles.places}>
            {names.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        )}
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy === "back"} disabled={busy !== null} aria-label={t("queue.switch_failed.back_named", { work, previous })} onClick={() => void back()}>
          {t("queue.switch_failed.back")}
        </Button>
        <Button size="sm" variant="secondary" loading={busy === "keep"} disabled={busy !== null} aria-label={t("queue.switch_failed.keep_named", { account, work })} onClick={() => void keep()}>
          {t("queue.switch_failed.keep")}
        </Button>
      </div>
    </section>
  );
}

/** An agent account whose sign-in changed (keep the new one, or sign in again), or whose sign-in isn't set for the level of
 * the work waiting on it (open the account). Work above open material waits until the person answers. */
function IdentityLine(props: { line: Line; onOpenAiAccounts: () => void }) {
  const { t, tn } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const nameOf = useAccountNames();
  const { line } = props;
  const account = nameOf(line.account ?? "");
  const identity = line.text ?? "";
  if (line.state === "level") {
    const levels = (line.names ?? []).map((level) => t(`changes.level.${level}`)).join(", ");
    return (
      <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.identity.label")} data-queue-line="identity">
        <Pill tone="warn">{t("queue.identity.label")}</Pill>
        <div className={styles.body}>
          <p className={styles.text}>{t(identity ? "queue.identity.level" : "queue.identity.level_unknown", { account, identity, levels })}</p>
          <p className={styles.sub}>{tn("queue.identity.level.sub", line.count)}</p>
        </div>
        <div className={styles.actions}>
          <Button size="sm" variant="primary" data-key="primary" aria-label={t("queue.identity.open_named", { account })} onClick={props.onOpenAiAccounts}>
            {t("queue.identity.open")}
          </Button>
        </div>
      </section>
    );
  }
  const keep = async () => {
    setBusy(true);
    await act(
      () => api.keepIdentity(line.account ?? ""),
      () => ({ message: t("queue.identity.keep_toast", { account, identity }) }),
    );
    setBusy(false);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.identity.label")} data-queue-line="identity">
      <Pill tone="warn">{t("queue.identity.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.identity", { account, identity })}</p>
        <p className={styles.sub}>{t("queue.identity.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" disabled={busy} aria-label={t("queue.identity.sign_in_named", { account })} onClick={props.onOpenAiAccounts}>
          {t("queue.identity.sign_in")}
        </Button>
        <Button size="sm" variant="secondary" loading={busy} disabled={busy} aria-label={t("queue.identity.keep_named", { account, identity })} onClick={() => void keep()}>
          {t("queue.identity.keep")}
        </Button>
      </div>
    </section>
  );
}

/** An account the person said Not now about reading their work mail and notes: one line with Allow, which gives the yes as one
 * settings change with Undo. Allow changes what the account may read, not the assistant's output, so it has no signal. */
function WorkAccessLine(props: { line: Line }) {
  const { t } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const [busy, setBusy] = useState(false);
  const nameOf = useAccountNames();
  const account = nameOf(props.line.account ?? "");
  const allow = async () => {
    setBusy(true);
    const saved = await act(async () => api.allowWork(props.line.account ?? "", await fingerprint()));
    if (saved) await afterSave(saved, { message: t("queue.work_access.toast", { account }) });
    setBusy(false);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.work_access.label")} data-queue-line="work_access">
      <Pill tone="neutral">{t("queue.work_access.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.work_access", { account })}</p>
        <p className={styles.sub}>{t("queue.work_access.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy} disabled={busy} aria-label={t("queue.work_access.allow_named", { account })} onClick={() => void allow()}>
          {t("queue.work_access.allow")}
        </Button>
      </div>
    </section>
  );
}

/** A kind of file that isn't being read: it says which and why. It has no button; it goes once a file of that kind reads
 * well. */
function ExtractorLine(props: { line: Line }) {
  const { t, has } = useWords();
  const { line } = props;
  const kind = line.file_kind ?? "";
  const named = has(`queue.extractor.kind.${kind}`) ? t(`queue.extractor.kind.${kind}`) : kind;
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.extractor.label")} data-queue-line="extractor">
      <Pill tone="warn">{t("queue.extractor.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.extractor", { kind: named, reason: line.text ?? "" })}</p>
        <p className={styles.sub}>{t("queue.extractor.sub")}</p>
      </div>
    </section>
  );
}

/** A source that has failed for longer than its usual gap: what to do about it, since when it hasn't been read, and why;
 * one button, to the screen where it is signed in again or changed. It goes once the source is read again. */
function SourceUnreadLine(props: { line: Line; onOpen?: () => void }) {
  const { t, has } = useWords();
  const { line } = props;
  const kind = `queue.source_unread.${line.problem_kind ?? ""}`;
  const key = line.problem_kind && has(kind) ? kind : "queue.source_unread.other";
  const since = line.waiting_since ? whenWords(line.waiting_since, new Date(), t, true) : "";
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.source_unread.label")} data-queue-line="source_unread">
      <Pill tone="warn">{t("queue.source_unread.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t(key, { label: line.subject ?? "", when: since })}</p>
        {line.text && <p className={styles.sub}>{line.text}</p>}
      </div>
      {props.onOpen && (
        <div className={styles.actions}>
          <Button size="sm" variant="primary" data-key="primary" onClick={props.onOpen}>
            {t("queue.source_unread.open")}
          </Button>
        </div>
      )}
    </section>
  );
}

/** The learning runs for the corrections made before the assistant could learn from them, held together for one go: the
 * count and what they would cost together, and the one Go that starts them all. */
function CatchUpGoLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const [busy, setBusy] = useState(false);
  const { line } = props;
  const cost = line.estimate_usd == null ? null : estimate(line.estimate_usd);
  const text =
    cost === null
      ? tn("queue.catch_up_go.unpriced", line.count)
      : line.unpriced > 0
        ? tn("queue.catch_up_go.mixed", line.count, { cost })
        : tn("queue.catch_up_go.priced", line.count, { cost });
  const go = async () => {
    setBusy(true);
    await act(api.catchUpGo, () => ({ message: t("queue.catch_up_go.started") }));
    setBusy(false);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.catch_up_go.label")} data-queue-line="catch_up_go">
      <Pill tone="warn">{t("queue.catch_up_go.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t("queue.catch_up_go.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy} onClick={() => void go()}>
          {t("queue.catch_up_go.run")}
        </Button>
      </div>
    </section>
  );
}

/** A newly added source taken in quietly, held for one go: how many items (from how many days of mail, when it has mail),
 * what they would cost together, and the one Go that starts them all. */
function IntakeGoLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const [busy, setBusy] = useState(false);
  const { line } = props;
  const source = line.subject ?? line.source ?? "";
  const text =
    line.days != null
      ? tn("queue.intake_go.mail", line.count, { source, since: tn("queue.intake_go.days", line.days) })
      : tn("queue.intake_go.items", line.count, { source });
  const cost = line.estimate_usd == null ? null : estimate(line.estimate_usd);
  const sub = t(cost === null ? "queue.intake_go.cost.unpriced" : line.unpriced > 0 ? "queue.intake_go.cost.mixed" : "queue.intake_go.cost.priced", { cost: cost ?? "" });
  const go = async () => {
    setBusy(true);
    await act(
      () => api.intakeGo(line.source ?? ""),
      () => ({ message: t("queue.intake_go.started", { source }) }),
    );
    setBusy(false);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.intake_go.label")} data-queue-line="intake_go">
      <Pill tone="warn">{t("queue.intake_go.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy} onClick={() => void go()}>
          {t("queue.intake_go.run")}
        </Button>
      </div>
    </section>
  );
}

/** The standing rules given to runs and never shown applying: the line opens the review, and "Not now" puts it off for
 * its week without deciding anything. */
function RuleReviewLine(props: { line: Line; onOpen?: () => void; onOpenKnowledge?: () => void }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { line } = props;
  const text = line.count > 0 ? tn("queue.rule_review", line.count, { days: line.days ?? "" }) : t("queue.rule_review.moved");
  // Not now puts the line off; it doesn't answer it, so it is in the menu with what it does, not a button beside the answer.
  const notNow = () =>
    void act(api.ruleReviewNotNow, (put) => ({
      message: t("queue.rule_review.not_now_done", { day: day(put.until) }),
      undo: () => api.ruleReviewNotNowUndo(put.signal),
    }));
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.rule_review.label")} data-queue-line="rule_review">
      <Pill tone="neutral">{t("queue.rule_review.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t("queue.rule_review.sub")}</p>
      </div>
      <div className={styles.actions}>
        {props.onOpen && (
          <Button size="sm" variant="primary" data-key="primary" onClick={props.onOpen}>
            {t("queue.rule_review.open")}
          </Button>
        )}
        <MenuButton
          groups={[
            {
              id: "rule-review",
              entries: [
                {
                  id: "not-now",
                  label: t("queue.rule_review.not_now"),
                  note: line.until ? t("queue.rule_review.not_now_back", { day: day(line.until) }) : undefined,
                  run: notNow,
                },
                ...(props.onOpenKnowledge ? [{ id: "knowledge", label: t("queue.rule_review.open_knowledge"), run: props.onOpenKnowledge }] : []),
              ],
            },
          ]}
          trigger={<IconButton icon="more" size="sm" label={t("menu.more", { what: t("queue.rule_review.label") })} tooltip={false} />}
        />
      </div>
    </section>
  );
}

/** Work with no AI account at all: it waits until one is added, so the line says so and offers the one step that fixes it. */
function NoAccountLine(props: { line: Line; onAdd: () => void }) {
  const { t } = useWords();
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.no_account.label")} data-queue-line="no_account">
      <Pill tone="warn">{t("queue.no_account.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.no_account")}</p>
        <p className={styles.sub}>{t("queue.no_account.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" onClick={props.onAdd}>
          {t("queue.no_account.open")}
        </Button>
      </div>
    </section>
  );
}
