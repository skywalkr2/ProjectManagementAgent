// Today's lines for work that has stopped or that needs a look before it can go on (design 7.7, 8.5): work held until the
// app restarts, an AI account paused until its usage limit resets, work waiting for the network, the synced folder that
// can't be used until the person settles which copy to keep, a backup account that hasn't passed its check, a kind of
// file that isn't being read, and the standing rules to look over.
// Each is one row that says what to do first, with the one button that does it. The lines come from the Today queue; a
// line is gone once its cause is, and only the person's own click ever restarts the app.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { wallWhen } from "../lib/dates";
import { useEstimate } from "../lib/money";
import { useRestart, useRestartText } from "../lib/restart";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import styles from "./HeldLines.module.css";

type Line = S["QueueLineView"];

const SHOWN: Line["kind"][] = ["restart", "paused", "offline", "handover", "account_check", "extractor", "rule_review", "catch_up_go"];

export function HeldLines(props: { onOpenAiAccounts: () => void; onOpenHandover: () => void; onOpenRules?: () => void }) {
  const queue = useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
  const lines = (queue.data ?? []).filter((line) => SHOWN.includes(line.kind));
  if (!lines.length) return null;
  return (
    <div className={styles.lines} data-held-lines="">
      {lines.map((line) =>
        line.kind === "restart" ? (
          <RestartLine key={line.key} line={line} />
        ) : line.kind === "handover" ? (
          <HandoverLine key={line.key} line={line} onOpen={props.onOpenHandover} />
        ) : line.kind === "offline" ? (
          <OfflineLine key={line.key} line={line} />
        ) : line.kind === "account_check" ? (
          <AccountCheckLine key={line.key} line={line} />
        ) : line.kind === "extractor" ? (
          <ExtractorLine key={line.key} line={line} />
        ) : line.kind === "rule_review" ? (
          <RuleReviewLine key={line.key} line={line} onOpen={props.onOpenRules} />
        ) : line.kind === "catch_up_go" ? (
          <CatchUpGoLine key={line.key} line={line} />
        ) : (
          <PausedLine key={line.key} line={line} onOpenAiAccounts={props.onOpenAiAccounts} />
        ),
      )}
    </div>
  );
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
    <section className={styles.line} aria-label={t("queue.restart.label")} data-queue-line="restart">
      <Pill tone="warn">{t("queue.restart.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      {canRestart && (
        <div className={styles.actions}>
          <Button size="sm" variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        </div>
      )}
    </section>
  );
}

function PausedLine(props: { line: Line; onOpenAiAccounts: () => void }) {
  const { t, tn } = useWords();
  const { line } = props;
  const label = tn("queue.paused", line.count, { account: line.account ?? "", time: line.until ? wallWhen(line.until) : "" });
  return (
    <section className={styles.line} aria-label={t("queue.paused.label")} data-queue-line="paused">
      <Pill tone="warn">{t("queue.paused.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{label}</p>
        <p className={styles.sub}>{t("queue.paused.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" onClick={props.onOpenAiAccounts}>
          {t("queue.paused.open")}
        </Button>
      </div>
    </section>
  );
}

function OfflineLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const { line } = props;
  const label = tn("queue.offline", line.count, { time: line.waiting_since ? wallWhen(line.waiting_since) : "" });
  return (
    <section className={styles.line} aria-label={t("queue.offline.label")} data-queue-line="offline">
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
    <section className={styles.line} aria-label={t("queue.handover.label")} data-queue-line="handover">
      <Pill tone="warn">{t("queue.handover.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t(`queue.handover.${state}_sub`)}</p>
      </div>
      <div className={styles.actions}>
        {canRestart && (
          <Button size="sm" variant="primary" disabled={restart.busy || restart.waiting} onClick={() => void restart.now()}>
            {t("restart.now")}
          </Button>
        )}
        <Button size="sm" variant={canRestart ? "secondary" : "primary"} onClick={props.onOpen}>
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
  const [checking, setChecking] = useState(false);
  const { line } = props;
  const account = line.account ?? "";
  const work = t(has(`queue.account_check.work.${line.tier}`) ? `queue.account_check.work.${line.tier}` : "queue.account_check.work.other");
  const run = async () => {
    setChecking(true);
    await act(
      () => api.testAccount(account, line.tier ?? undefined, line.model ?? undefined),
      (results) => {
        const bad = results.find((r) => !r.ok);
        return { message: bad ? t("queue.account_check.not_passed", { account, detail: bad.detail }) : t("queue.account_check.passed", { account, work }) };
      },
    );
    setChecking(false);
  };
  return (
    <section className={styles.line} aria-label={t("queue.account_check.label")} data-queue-line="account_check">
      <Pill tone="warn">{t("queue.account_check.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.account_check", { account, work })}</p>
        <p className={styles.sub}>{t(line.check_failed ? "queue.account_check.sub_failed" : "queue.account_check.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" loading={checking} aria-label={t("queue.account_check.run_named", { account, work })} onClick={() => void run()}>
          {t("queue.account_check.run")}
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
    <section className={styles.line} aria-label={t("queue.extractor.label")} data-queue-line="extractor">
      <Pill tone="warn">{t("queue.extractor.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.extractor", { kind: named, reason: line.text ?? "" })}</p>
        <p className={styles.sub}>{t("queue.extractor.sub")}</p>
      </div>
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
    <section className={styles.line} aria-label={t("queue.catch_up_go.label")} data-queue-line="catch_up_go">
      <Pill tone="warn">{t("queue.catch_up_go.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t("queue.catch_up_go.sub")}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" loading={busy} onClick={() => void go()}>
          {t("queue.catch_up_go.run")}
        </Button>
      </div>
    </section>
  );
}

/** The standing rules given to runs and never shown applying: the line opens the review. */
function RuleReviewLine(props: { line: Line; onOpen?: () => void }) {
  const { t, tn } = useWords();
  const { line } = props;
  const text = line.count > 0 ? tn("queue.rule_review", line.count, { days: line.days ?? "" }) : t("queue.rule_review.moved");
  return (
    <section className={styles.line} aria-label={t("queue.rule_review.label")} data-queue-line="rule_review">
      <Pill tone="neutral">{t("queue.rule_review.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{text}</p>
        <p className={styles.sub}>{t("queue.rule_review.sub")}</p>
      </div>
      {props.onOpen && (
        <div className={styles.actions}>
          <Button size="sm" variant="primary" onClick={props.onOpen}>
            {t("queue.rule_review.open")}
          </Button>
        </div>
      )}
    </section>
  );
}
