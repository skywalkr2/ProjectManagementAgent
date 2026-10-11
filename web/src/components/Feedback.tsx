// Sending feedback: the person writes what happened, sees exactly what the email will say, and either opens it in
// their own mail program or copies it. The app sends nothing, and the only facts it adds (if the person leaves that on)
// are the app's version and the name of the screen they were on.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Heading } from "react-aria-components";
import { api } from "../lib/api";
import { mailText, mailtoLink, tooLongForLink } from "../lib/mail";
import { useToasts } from "../lib/toasts";
import { parseView, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { ModalPanel } from "./ModalPanel";

/** The name of the screen as the person sees it: the tab's name, a plugin panel's title, or a general name for a record page. */
export function useScreenLabel(view: View): string {
  const { t } = useWords();
  const panels = useQuery({ queryKey: ["panels"], queryFn: () => api.panels() });
  const parsed = parseView(view);
  if (parsed.type === "panel") return panels.data?.find((p) => p.name === parsed.name)?.title ?? parsed.name;
  if (parsed.type === "record") return t("feedback.screen.record");
  return parsed.view === "welcome" ? t("welcome.title") : t(`nav.${parsed.view}`);
}

export function Feedback(props: { onClose: () => void; view: View; version: string; to: string | null | undefined }) {
  const { t } = useWords();
  const { push } = useToasts();
  const base = useId();
  const screen = useScreenLabel(props.view);
  const [message, setMessage] = useState("");
  const [include, setInclude] = useState(true);
  const [blocked, setBlocked] = useState(false);

  const subject = t("feedback.subject", { app: t("app.name") });
  const body = [
    message.trim(),
    ...(include ? ["", t("feedback.body_version", { version: props.version }), t("feedback.body_screen", { screen })] : []),
  ].join("\n");
  const ready = message.trim() !== "";
  const link = ready ? mailtoLink(props.to, subject, body) : null;
  const tooLong = ready && tooLongForLink(props.to, subject, body);
  const noAddress = !props.to?.trim();
  // The mail link is the main action when there is one; otherwise copying is.
  const mailIsMain = !noAddress && !tooLong;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(mailText(subject, body));
    } catch {
      setBlocked(true);
      return;
    }
    setBlocked(false);
    push({ message: t("feedback.toast.copied") });
  };

  const titleId = `${base}-title`;
  const fieldId = `${base}-message`;
  const hintId = `${base}-hint`;
  const requiredId = `${base}-required`;
  const noteId = `${base}-note`;
  const note = tooLong ? t("feedback.too_long") : noAddress ? t("feedback.no_address") : "";
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("feedback.title")}
      </Heading>
      <form onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor={fieldId}>{t("feedback.message")}</label>
          <textarea
            id={fieldId}
            className="short"
            autoFocus
            required
            value={message}
            aria-describedby={ready ? hintId : `${hintId} ${requiredId}`}
            onChange={(e) => {
              setMessage(e.target.value);
              setBlocked(false);
            }}
          />
          <span id={hintId} className="hint">
            {t("feedback.message_hint")}
          </span>
          {!ready && (
            <span id={requiredId} className="hint">
              {t("feedback.required")}
            </span>
          )}
        </div>
        <label className="check-line">
          <input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} />
          <span>{t("feedback.include")}</span>
        </label>
        <fieldset className="details">
          <legend>{t("feedback.preview")}</legend>
          <div className="field">
            <label htmlFor={`${base}-subject`}>{t("feedback.preview_subject")}</label>
            <input id={`${base}-subject`} readOnly value={subject} />
          </div>
          <div className="field">
            <label htmlFor={`${base}-body`}>{t("feedback.preview_body")}</label>
            <textarea id={`${base}-body`} className="short" readOnly rows={Math.min(8, body.split("\n").length + 1)} value={body} />
          </div>
        </fieldset>
        {note && (
          <p id={noteId} className="hint" role="status">
            {note}
          </p>
        )}
        {blocked && (
          <p className="problem-note" role="alert">
            {t("feedback.copy_blocked")}
          </p>
        )}
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onClose}>
            {t("action.close")}
          </button>
          <button type="button" className={`btn${mailIsMain ? "" : " primary"}`} disabled={!ready} onClick={() => void copy()}>
            {t("feedback.copy")}
          </button>
          {mailIsMain &&
            (link ? (
              <a className="btn primary" href={link}>
                {t("feedback.mail")}
              </a>
            ) : (
              <button type="button" className="btn primary" disabled>
                {t("feedback.mail")}
              </button>
            ))}
        </div>
      </form>
    </ModalPanel>
  );
}
