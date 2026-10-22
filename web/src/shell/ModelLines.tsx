// Today's lines about AI accounts' models: a saved account that could move to its service's own connection (with a read-back
// of the identity it would sign in as, and a check before anything is written), a newer model of a tier's own family or a
// price rise (design 6.16), and a tier that moved to a newer model on its own after a check passed.
// Nothing here changes a model or a connection without the person's click, except the move the person allowed with the
// "follow the newest model" setting, which the last line reports with Keep and Switch back.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useAccountNames } from "../lib/account-names";
import { useMoney } from "../lib/money";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import styles from "./HeldLines.module.css";

type Line = S["QueueLineView"];

/** The plain words for the kinds of work a line is about, as a list: "everyday work and harder work". */
function useWorks() {
  const { t, has } = useWords();
  return (tiers: string[]) => {
    const words = tiers.map((tier) => t(has(`queue.switch_failed.work.${tier}`) ? `queue.switch_failed.work.${tier}` : "queue.switch_failed.work.other"));
    return new Intl.ListFormat(undefined, { style: "long", type: "conjunction" }).format(words);
  };
}

/** An account on the generic connection to a service that has its own. Move shows which identity the new connection signs
 * in as and asks again; the yes runs the account check on the new connection, and only a check that passed writes the
 * change, with Undo. Not now is remembered for the account. */
export function AccountMoveLine(props: { line: Line }) {
  const { t } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const nameOf = useAccountNames();
  const [step, setStep] = useState<"ask" | "read" | "working">("ask");
  const [problem, setProblem] = useState<string | null>(null);
  const accountId = props.line.account ?? "";
  const account = nameOf(accountId);
  const readback = useQuery({ queryKey: ["ai-move", accountId], queryFn: () => api.accountMoveReadback(accountId), enabled: step !== "ask" });
  const back = readback.data;
  const move = async () => {
    setStep("working");
    setProblem(null);
    const done = await act(async () => api.moveAccount(accountId, await fingerprint()));
    if (done?.moved && done.saved) {
      await afterSave(done.saved, { message: t("queue.account_move.moved", { account }) });
      return;
    }
    if (done) setProblem(t("queue.account_move.failed", { account, detail: done.detail ?? "" }));
    setStep("read");
  };
  const notNow = async () => {
    await act(
      () => api.moveAccountNotNow(accountId),
      () => ({ message: t("queue.account_move.put_off", { account }) }),
    );
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.account_move.label")} data-queue-line="account_move">
      <Pill tone="neutral">{t("queue.account_move.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.account_move", { account })}</p>
        <p className={styles.sub}>{t("queue.account_move.sub")}</p>
        {step !== "ask" && back && (
          <ul className={styles.places} aria-label={t("queue.account_move.readback")}>
            <li>{!back.key_known ? t("queue.account_move.key_unknown") : back.key_differs ? t(back.key_ending ? "queue.account_move.key_other" : "queue.account_move.key_other_short", { account, ending: back.key_ending }) : t(back.key_ending ? "queue.account_move.key_same" : "queue.account_move.key_same_short", { ending: back.key_ending })}</li>
            <li>{back.address_differs ? t("queue.account_move.address_other", { address: back.address, was: back.address_was }) : t("queue.account_move.address_same", { address: back.address })}</li>
            <li>{t("queue.account_move.name_same", { account: back.account })}</li>
          </ul>
        )}
        {step !== "ask" && !back && readback.isError && <p className={styles.sub}>{t("queue.account_move.readback_failed")}</p>}
        {problem && <p className={styles.sub} role="status">{problem}</p>}
      </div>
      <div className={styles.actions}>
        {step === "ask" ? (
          <>
            <Button size="sm" variant="primary" data-key="primary" aria-label={t("queue.account_move.move_named", { account })} onClick={() => setStep("read")}>
              {t("queue.account_move.move")}
            </Button>
            <Button size="sm" variant="secondary" aria-label={t("queue.account_move.not_now_named", { account })} onClick={() => void notNow()}>
              {t("queue.account_move.not_now")}
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="primary" data-key="primary" loading={step === "working"} disabled={!back || step === "working"} aria-label={t("queue.account_move.confirm_named", { account })} onClick={() => void move()}>
              {t("queue.account_move.confirm")}
            </Button>
            <Button size="sm" variant="secondary" disabled={step === "working"} onClick={() => { setStep("ask"); setProblem(null); }}>
              {t("queue.account_move.back")}
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

/** A day's cost change in plain words, from a signed number of US dollars. */
function useChange() {
  const { t } = useWords();
  const money = useMoney();
  return (usd: number | null | undefined, more: string, less: string, same: string) =>
    usd == null ? null : Math.abs(usd) < 0.005 ? t(same) : t(usd > 0 ? more : less, { amount: money(Math.abs(usd)) });
}

/** News about an account's models: a newer model of a tier's own family (what it would change in cost per day at the
 * current use, and why it isn't moved to on its own), or a price rise of the tier's current model. Switch is the settings'
 * own switch, with its check; Not now is kept until a different newer model, or a different price rise, appears. */
export function ModelWatchLine(props: { line: Line }) {
  const { t, tn } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const money = useMoney();
  const works = useWorks();
  const change = useChange();
  const nameOf = useAccountNames();
  const [busy, setBusy] = useState<"switch" | "not_now" | null>(null);
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const { line } = props;
  const accountId = line.account ?? "";
  const price = line.state === "price";
  const tiers = line.names ?? [];
  const work = works(tiers);
  const candidates = line.candidates ?? {};
  const reason = line.reason ?? "asks";
  const sub = (() => {
    if (price) return change(line.usd_per_day, "queue.model_watch.sub.price_more", "queue.model_watch.sub.price_more", "queue.model_watch.sub.price_same") ?? t("queue.model_watch.sub.price_same");
    if (reason === "price_unknown") return t("queue.model_watch.sub.price_unknown");
    if (reason === "costs_more") return change(line.usd_per_day, "queue.model_watch.sub.costs_more", "queue.model_watch.sub.costs_more", "queue.model_watch.sub.costs_more_unused") ?? t("queue.model_watch.sub.costs_more_unused");
    if (reason === "check_failed") return line.check_failed ? t("queue.model_watch.sub.check_unfinished") : tn("queue.model_watch.sub.check_failed", line.count);
    if (reason === "check_cost") return line.estimate_usd == null ? t("queue.model_watch.sub.check_cost_unknown") : t("queue.model_watch.sub.check_cost", { cost: money(line.estimate_usd) });
    return change(line.usd_per_day, "queue.model_watch.sub.asks_more", "queue.model_watch.sub.asks_less", "queue.model_watch.sub.asks_same") ?? t("queue.model_watch.sub.price_unknown");
  })();
  const switchNow = async () => {
    const account = accounts.data?.find((a) => a.name === accountId);
    if (!account) return;
    setBusy("switch");
    const models = { ...account.models };
    const use: Record<string, string> = {};
    for (const [tier, model] of Object.entries(candidates)) {
      const known = Object.entries(models).find(([, id]) => id === model)?.[0];
      const short = known ?? model;
      models[short] = model;
      use[tier] = short;
    }
    const done = await act(async () => api.switchAndCheck(accountId, { fingerprint: await fingerprint(), models, use }));
    if (done) await afterSave(done.saved, { message: t("queue.model_watch.switched", { work }) });
    setBusy(null);
  };
  const notNow = async () => {
    setBusy("not_now");
    await act(
      () => api.modelWatchNotNow(accountId, price ? "price" : "newer"),
      () => ({ message: t("queue.model_watch.put_off") }),
    );
    setBusy(null);
  };
  const key = price ? "price" : "newer";
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t(`queue.model_watch.label.${key}`)} data-queue-line="model_watch">
      <Pill tone="neutral">{t(`queue.model_watch.label.${key}`)}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t(price ? "queue.model_watch.price" : "queue.model_watch", { work, account: nameOf(accountId) })}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      <div className={styles.actions}>
        {!price && (
          <Button size="sm" variant="primary" data-key="primary" loading={busy === "switch"} disabled={busy !== null || !accounts.data} aria-label={t("queue.model_watch.switch_named", { work })} onClick={() => void switchNow()}>
            {t("queue.model_watch.switch")}
          </Button>
        )}
        <Button size="sm" variant={price ? "primary" : "secondary"} data-key={price ? "primary" : undefined} loading={busy === "not_now"} disabled={busy !== null} aria-label={t(price ? "queue.model_watch.got_it_named" : "queue.model_watch.not_now_named", { work })} onClick={() => void notNow()}>
          {t(price ? "queue.model_watch.got_it" : "queue.model_watch.not_now")}
        </Button>
      </div>
    </section>
  );
}

/** A tier moved on its own to a newer model of its family after a check passed (the person allowed it in Settings): what
 * moved, what it changes in cost, and Keep or Switch back, which restores the earlier model with Undo. */
export function ModelMovedLine(props: { line: Line }) {
  const { t } = useWords();
  const act = useAct();
  const fingerprint = useFreshFingerprint();
  const afterSave = useAfterSave();
  const works = useWorks();
  const change = useChange();
  const [busy, setBusy] = useState<"back" | "keep" | null>(null);
  const { line } = props;
  const tier = line.tier ?? "";
  const work = works([tier]);
  const sub = change(line.usd_per_day, "queue.model_moved.sub_more", "queue.model_moved.sub_less", "queue.model_moved.sub_same") ?? t("queue.model_moved.sub_same");
  const back = async () => {
    setBusy("back");
    const saved = await act(async () => api.switchBack(tier, await fingerprint()));
    if (saved) await afterSave(saved, { message: t("queue.model_moved.back_toast", { work }) });
    setBusy(null);
  };
  const keep = async () => {
    setBusy("keep");
    await act(
      () => api.keepSwitch(tier),
      () => ({ message: t("queue.model_moved.keep_toast", { work }) }),
    );
    setBusy(null);
  };
  return (
    <section className={styles.line} data-row="" tabIndex={-1} aria-label={t("queue.model_moved.label")} data-queue-line="model_moved">
      <Pill tone="neutral">{t("queue.model_moved.label")}</Pill>
      <div className={styles.body}>
        <p className={styles.text}>{t("queue.model_moved", { work })}</p>
        <p className={styles.sub}>{sub}</p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" data-key="primary" loading={busy === "keep"} disabled={busy !== null} aria-label={t("queue.model_moved.keep_named", { work })} onClick={() => void keep()}>
          {t("queue.model_moved.keep")}
        </Button>
        <Button size="sm" variant="secondary" loading={busy === "back"} disabled={busy !== null} aria-label={t("queue.model_moved.back_named", { work })} onClick={() => void back()}>
          {t("queue.model_moved.back")}
        </Button>
      </div>
    </section>
  );
}
