// Where reminders reach the person when the app isn't open (design 6.12, 7.9): nowhere, the app's own calendar (local, no
// yes needed), or an account's calendar or mail. For the two accounts the exact reminder is shown before anything is set,
// and "Yes, send my reminders there without asking" is the person's standing yes; "Ask me each time" leaves each reminder
// as a draft in Waiting to go out. Ending the yes, like giving it, has Undo.
import { useId, useState } from "react";
import { api, ApiError } from "../lib/api";
import { problemText } from "../lib/problem";
import { useReminderWhere, whereWords, type Where } from "../lib/reminder-where";
import { knownFingerprint, rememberFingerprint, useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { undoBody } from "../lib/settings";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/Button";
import styles from "./ReminderWhere.module.css";

const WHERE_KEY = "steward.reminders.where";
const ACCOUNT_KEY = "steward.reminders.where_account";
type Outward = "calendar" | "mail";

export function ReminderWhere() {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const view = useReminderWhere();
  const [pick, setPick] = useState<Where | null>(null);
  const [account, setAccount] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const group = useId();
  const accountId = useId();
  const data = view.data;
  if (!data) return null;

  const where: Where = pick ?? data.where;
  const outward = where === "calendar" || where === "mail" ? (where as Outward) : null;
  const chosenAccount = account ?? (pick === null ? data.account : null);
  const options = (data.accounts ?? []).filter((a) => (outward ? a[outward] : false));
  const going = data.standing && data.standing.form === outward && data.standing.account === chosenAccount ? data.standing : null;

  const refresh = () => client.invalidateQueries({ queryKey: ["reminder-where"] });
  const undoYes = async (changeset: string) => {
    await api.undo(changeset);
    await client.invalidateQueries();
  };
  const attempt = async (run: () => Promise<void>) => {
    setBusy(true);
    setProblem("");
    try {
      await run();
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  const save = async (to: Where, acct: string) =>
    api.saveSettings({ changes: { [WHERE_KEY]: to, [ACCOUNT_KEY]: acct }, reset: [], fingerprint: await fingerprint() });
  const endStanding = async () => {
    const ended = await api.endReminderYes();
    push({ message: t("reminders.where.ended"), undo: () => undoYes(ended.changeset) });
  };

  /** Nowhere and the app's own calendar need no yes: they are set at once, and any standing yes ends. */
  const settle = (to: "nowhere" | "app") =>
    attempt(async () => {
      setPick(to);
      setAccount(null);
      await afterSave(await save(to, ""), { message: t("reminders.where.saved", { state: t(`reminders.where.state.${to}`) }) });
      if (data.standing) await endStanding();
      await refresh();
    });

  const choose = (to: Where) => {
    if (to === "nowhere" || to === "app") void settle(to);
    else {
      setPick(to);
      setAccount(null);
    }
  };

  const ask = () =>
    attempt(async () => {
      if (!outward || !chosenAccount) return;
      await afterSave(await save(outward, chosenAccount), {
        message: t("reminders.where.saved", { state: t("reminders.where.state.ask") }),
      });
      if (data.standing) await endStanding();
      await refresh();
    });

  const yes = () =>
    attempt(async () => {
      if (!outward || !chosenAccount) return;
      const saved = await save(outward, chosenAccount);
      rememberFingerprint(client, saved.fingerprint);
      const given = await api.giveReminderYes({ form: outward, account: chosenAccount, template_version: data.template_version });
      // Undo takes back both steps: the yes, then the choice and account it was given for, as they were before.
      const undoBoth = async () => {
        await api.undo(given.changeset);
        if (saved.changes.length > 0) {
          const back = await api.saveSettings(undoBody(saved.changes, knownFingerprint(client, saved.fingerprint) ?? saved.fingerprint));
          rememberFingerprint(client, back.fingerprint);
        }
        await client.invalidateQueries();
      };
      push({ message: t("reminders.where.given"), undo: undoBoth });
      await client.invalidateQueries();
    });

  const shown = data.example.item;
  const plain = data.example.plain;
  const preview = outward === "mail" ? t("reminders.where.preview.mail", { subject: shown.subject }) : t("reminders.where.preview.calendar", { title: shown.event_title });
  const plainWords = outward === "mail" ? plain.subject : plain.event_title;
  const state = going
    ? t("reminders.where.state.going", {
        where: whereWords(going.form, t),
        account: going.account_label ?? going.account,
        since: going.given_at.slice(0, 10),
      })
    : outward && chosenAccount && data.where === outward && data.account === chosenAccount
      ? t("reminders.where.state.ask")
      : "";
  const choices: Array<{ id: Where; label: string; hint?: string }> = [
    { id: "nowhere", label: t("reminders.where.nowhere") },
    { id: "app", label: t("reminders.where.app"), hint: t("reminders.where.app.hint") },
    { id: "calendar", label: t("reminders.where.calendar"), hint: t("reminders.where.calendar.hint") },
    { id: "mail", label: t("reminders.where.mail"), hint: t("reminders.where.mail.hint") },
  ];

  return (
    <section className={styles.where} aria-labelledby={`${group}-title`}>
      <h3 id={`${group}-title`}>{t("reminders.where.title")}</h3>
      <p className="hint">{t("reminders.where.intro")}</p>
      <fieldset className={styles.choices} disabled={busy}>
        <legend className="sr">{t("reminders.where.choose")}</legend>
        {choices.map((c) => (
          <div key={c.id} className={styles.choice}>
            <label>
              <input type="radio" name={group} checked={where === c.id} onChange={() => choose(c.id)} />
              {c.label}
            </label>
            {c.hint && <p className={styles.hint}>{c.hint}</p>}
            {where === c.id && (c.id === "calendar" || c.id === "mail") && (
              <div className={styles.account}>
                {options.length === 0 ? (
                  <p role="status">{t(`reminders.where.none_${c.id}`)}</p>
                ) : (
                  <>
                    <label htmlFor={accountId}>{t("reminders.where.account")}</label>
                    <select id={accountId} value={chosenAccount ?? ""} onChange={(e) => setAccount(e.target.value || null)}>
                      <option value="">{t("reminders.where.account.pick")}</option>
                      {options.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.label}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </fieldset>
      {outward && chosenAccount && (
        <div className={styles.preview} aria-label={t("reminders.where.preview")}>
          <p>{t("reminders.where.preview")}</p>
          <p>{preview}</p>
          <blockquote>{shown.body}</blockquote>
          <p>{t("reminders.where.preview.plain", { words: plainWords })}</p>
          {state && <p role="status">{state}</p>}
          <div className={styles.actions}>
            {going ? (
              <Button size="sm" disabled={busy} onClick={() => void attempt(endStanding).then(refresh)}>
                {t("reminders.where.stop")}
              </Button>
            ) : (
              <>
                <Button size="sm" variant="primary" disabled={busy} onClick={() => void yes()}>
                  {t("reminders.where.go")}
                </Button>
                <Button size="sm" disabled={busy} onClick={() => void ask()}>
                  {t("reminders.where.ask")}
                </Button>
              </>
            )}
          </div>
          {!going && <p className={styles.hint}>{t("reminders.where.ask.hint")}</p>}
        </div>
      )}
      {!outward && <p role="status">{t(`reminders.where.state.${where === "app" ? "app" : "nowhere"}`)}</p>}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </section>
  );
}
