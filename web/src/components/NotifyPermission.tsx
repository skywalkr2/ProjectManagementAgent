// The one place the browser is asked to allow notifications (design 6.32): a button in Settings, never on load. Reminders
// that appear on Today while the app is open then also show as a notification.
import { useState } from "react";
import { askNotify, notifyState, type NotifyState } from "../lib/notify";
import { useWords } from "../lib/wording";

export function NotifyPermission() {
  const { t } = useWords();
  const [state, setState] = useState<NotifyState>(notifyState);
  return (
    <section className="notify-permission" aria-labelledby="notify-title">
      <h3 id="notify-title">{t("notify.title")}</h3>
      <p className="hint">{t("notify.hint")}</p>
      {state === "default" && (
        <button type="button" className="btn primary" onClick={() => void askNotify().then(setState)}>
          {t("notify.allow")}
        </button>
      )}
      {state === "granted" && <p role="status">{t("notify.granted")}</p>}
      {state === "denied" && <p role="status">{t("notify.denied")}</p>}
      {state === "unsupported" && <p role="status">{t("notify.unsupported")}</p>}
    </section>
  );
}
