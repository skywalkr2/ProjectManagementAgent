// A setting that holds a password, a key or a private address. On a local app the person types or pastes it and the app
// keeps it on this computer (the setting then holds only where it is kept); "where it is kept instead" is the second
// choice, a text box for a place of their own. A hosted app takes only that place. What is kept is never shown, only
// where it is read from.
import { useState } from "react";
import { useWords } from "../lib/wording";
import type { S } from "../lib/api";

type Mode = "held" | "type" | "where";

export type SecretState = Pick<S["SourceSecretView"], "where" | "name">;

/** What a form of settings needs to let secrets be typed: whether the app keeps them (local), how each secret is held
 * now by its setting key, and the values typed so far, which are sent apart from the settings. */
export type SecretInput = {
  local: boolean;
  held: Record<string, SecretState>;
  pasted: Record<string, string>;
  onPaste: (key: string, value: string) => void;
};

export function SecretField(props: {
  id: string;
  /** The id of the element that names the field, which labels each box. */
  labelId: string;
  label: string;
  local: boolean;
  held: SecretState | null;
  /** The place the secret is read from, as the setting holds it. */
  reference: string;
  onReference: (reference: string) => void;
  pasted: string;
  onPaste: (value: string) => void;
  disabled: boolean;
  describedBy?: string;
  /** Put the cursor in the box when the field first shows (a form that has just opened). */
  autoFocus?: boolean;
  /** Told which way the person is giving it: typed here, or as a place it is kept. */
  onMode?: (mode: "type" | "where" | "held") => void;
}) {
  const { t } = useWords();
  const [mode, setMode] = useState<Mode>(props.held ? "held" : props.reference !== "" ? "where" : "type");
  const { id } = props;

  const referenceBox = (
    <input
      id={`${id}-where`}
      type="text"
      value={props.reference}
      disabled={props.disabled}
      autoComplete="off"
      autoFocus={props.autoFocus}
      aria-labelledby={props.labelId}
      aria-describedby={props.describedBy}
      onChange={(e) => props.onReference(e.target.value)}
    />
  );
  if (!props.local) {
    return (
      <>
        {referenceBox}
        <p className="hint" id={`${id}-note`}>
          {t("secret.hosted_hint")}
        </p>
      </>
    );
  }

  const go = (next: Mode) => {
    if (next !== "type") props.onPaste("");
    setMode(next);
    props.onMode?.(next);
  };
  const held = props.held;
  const heldWords = !held
    ? ""
    : held.where === "kept"
      ? t("secret.kept")
      : held.where === "env"
        ? t("secret.read_from_env", { name: held.name ?? "" })
        : held.where === "file"
          ? t("secret.read_from_file", { name: held.name ?? "" })
          : t("secret.read_from_other");

  return (
    <div className="secret-field" data-secret-mode={mode}>
      {mode === "held" && (
        <p className="setting-value" id={`${id}-held`}>
          {heldWords}
        </p>
      )}
      {mode === "type" && (
        <>
          <input
            id={`${id}-typed`}
            type="password"
            value={props.pasted}
            disabled={props.disabled}
            autoComplete="new-password"
            autoFocus={props.autoFocus}
            aria-labelledby={props.labelId}
            aria-describedby={`${id}-typed-hint`}
            onChange={(e) => props.onPaste(e.target.value)}
          />
          <p className="hint" id={`${id}-typed-hint`}>
            {t("secret.type_hint")}
          </p>
        </>
      )}
      {mode === "where" && referenceBox}
      <div className="inline-field">
        {mode === "held" && (
          <button
            type="button"
            className="btn small"
            disabled={props.disabled}
            aria-label={t("secret.replace_named", { label: props.label })}
            onClick={() => go("type")}
          >
            {t("secret.replace")}
          </button>
        )}
        {mode === "type" && props.held && (
          <button type="button" className="btn quiet small" disabled={props.disabled} onClick={() => go("held")}>
            {t("secret.keep_current")}
          </button>
        )}
        {mode !== "where" && (
          <button type="button" className="btn quiet small" disabled={props.disabled} onClick={() => go("where")}>
            {t("secret.where_instead")}
          </button>
        )}
        {mode === "where" && (
          <button type="button" className="btn quiet small" disabled={props.disabled} onClick={() => go("type")}>
            {t("secret.type_instead")}
          </button>
        )}
      </div>
    </div>
  );
}
