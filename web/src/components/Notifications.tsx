// Notices that something needs the person (design 7.19): the ways of getting one, each with "Send me a test". The browser
// needs its own permission, asked for only from a button here. A chat app or push topic is the person's own address, kept
// on this computer like a key. Mail to themselves is listed as coming with mail sending, since nothing sends mail yet.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, ApiError } from "../lib/api";
import { askNotify, notifyState, showNotification, type NotifyState } from "../lib/notify";
import { problemText } from "../lib/problem";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { heldOf, KeptSecretRow } from "./KeptSecrets";
import styles from "./Notifications.module.css";

/** One target's test: runs it, and says how it went in a toast, or in the card when it didn't work. */
function useTest(target: "browser" | "webhook") {
  const { t } = useWords();
  const { push } = useToasts();
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    setProblem("");
    try {
      const answer = await api.testNotify(target);
      if (!answer.ok) {
        setProblem(answer.problem ?? t("notices.test_failed"));
        return;
      }
      if (target === "browser") {
        if (notifyState() !== "granted") {
          setProblem(t("notices.browser.allow_first"));
          return;
        }
        showNotification(answer.message, undefined, "notices-test");
      }
      push({ message: t(target === "browser" ? "notices.test_shown" : "notices.test_sent") });
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  return { run, busy, problem };
}

function BrowserTarget() {
  const { t } = useWords();
  const [state, setState] = useState<NotifyState>(notifyState);
  const test = useTest("browser");
  const base = useId();
  return (
    <li className={styles.target} aria-labelledby={`${base}-name`}>
      <h4 id={`${base}-name`}>{t("notices.browser.title")}</h4>
      <p>{t("notices.browser.hint")}</p>
      {state === "granted" && <p role="status">{t("notify.granted")}</p>}
      {state === "denied" && <p role="status">{t("notify.denied")}</p>}
      {state === "unsupported" && <p role="status">{t("notify.unsupported")}</p>}
      {test.problem && (
        <p className="problem-note" role="alert">
          {test.problem}
        </p>
      )}
      <div className={styles.actions}>
        {state === "default" && (
          <button type="button" className="btn small primary" onClick={() => void askNotify().then(setState)}>
            {t("notify.allow")}
          </button>
        )}
        {state === "granted" && (
          <button type="button" className="btn small" disabled={test.busy} onClick={() => void test.run()}>
            {t("notices.test")}
          </button>
        )}
      </div>
    </li>
  );
}

function WebhookTarget(props: { local: boolean }) {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const view = useQuery({ queryKey: ["notifications"], queryFn: api.notifications });
  const test = useTest("webhook");
  const base = useId();
  const held = view.data ? heldOf(view.data.webhook) : null;
  return (
    <li className={styles.target} aria-labelledby={`${base}-name`}>
      <h4 id={`${base}-name`}>{t("notices.webhook.title")}</h4>
      <p>{t("notices.webhook.hint")}</p>
      <KeptSecretRow
        id={`${base}-address`}
        label={t("notices.webhook.label")}
        saveLabel={t("notices.webhook.save")}
        local={props.local}
        held={held}
        hint={t("notices.webhook.kept")}
        onSave={async (body) => {
          const saved = await api.setNotifyWebhook({ ...body, fingerprint: await fingerprint() });
          await afterSave(saved, { message: t("notices.webhook.saved") });
        }}
        more={
          held ? (
            <button type="button" className="btn small" disabled={test.busy} onClick={() => void test.run()}>
              {t("notices.test")}
            </button>
          ) : null
        }
      />
      {(test.problem || view.data?.problem) && (
        <p className="problem-note" role="alert">
          {test.problem || view.data?.problem}
        </p>
      )}
    </li>
  );
}

/** The ways of getting a notice, under the settings that turn notices on. */
export function Notifications() {
  const { t } = useWords();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const view = useQuery({ queryKey: ["notifications"], queryFn: api.notifications });
  const base = useId();
  return (
    <section className="notice-targets" aria-labelledby={`${base}-title`}>
      <h3 id={`${base}-title`}>{t("notices.title")}</h3>
      <p className="hint">{t("notices.intro")}</p>
      {view.data && !view.data.enabled && <p className="hint">{t("notices.off")}</p>}
      <ul className={styles.targets}>
        <BrowserTarget />
        <WebhookTarget local={setup.data?.local ?? true} />
        {!view.data?.mail_ready && (
          <li className={styles.target} aria-labelledby={`${base}-mail`}>
            <h4 id={`${base}-mail`}>{t("notices.mail.title")}</h4>
            <p>{t("notices.mail.later")}</p>
          </li>
        )}
      </ul>
    </section>
  );
}
