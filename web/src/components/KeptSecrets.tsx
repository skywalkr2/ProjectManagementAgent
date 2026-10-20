// Secrets typed on the screen that no source's form holds: the keys an add-on says it needs, and the key that locks the
// backups. On a local app each is typed (or, for the backup key, made by the app) and kept on this computer; the settings
// hold only where. "Where it is kept instead" is the second choice, and a hosted app takes only that. What is kept is
// never shown again; the one key the app makes is shown once, in this component's own state, for the person to copy.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { readable } from "../lib/records";
import { asReference } from "../lib/secret-ref";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { SecretField } from "./SecretField";

type How = "type" | "where" | "held";
type Held = Pick<S["SourceSecretView"], "where" | "name">;

/** How a secret is kept now, or null when it isn't set. */
export const heldOf = (state: Pick<S["AddonSecretView"], "where" | "name">): Held | null =>
  state.where === "none" ? null : { where: state.where, name: state.name };

/** One secret: its label, the box (or where it is kept), and a button that saves what was typed. */
export function KeptSecretRow(props: {
  id: string;
  label: string;
  saveLabel: string;
  local: boolean;
  held: Held | null;
  hint?: string;
  /** Saves it, typed or as where it is kept; the row clears itself when it is done. */
  onSave: (body: { value: string } | { reference: string }) => Promise<void>;
  /** Extra buttons beside Save. */
  more?: ReactNode;
}) {
  const { t } = useWords();
  const [typed, setTyped] = useState("");
  const [reference, setReference] = useState("");
  const [how, setHow] = useState<How>(props.held ? "held" : "type");
  const [round, setRound] = useState(0);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const byReference = !props.local || how === "where";
  const ready = how !== "held" && (byReference ? reference.trim() !== "" : typed.trim() !== "");
  const save = async () => {
    setBusy(true);
    setProblem("");
    try {
      await props.onSave(byReference ? { reference: asReference(reference) } : { value: typed.trim() });
      setTyped("");
      setReference("");
      setHow("held");
      setRound((n) => n + 1);
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="field kept-secret"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !busy) void save();
      }}
    >
      <span className="setting-label" id={`${props.id}-label`}>
        {props.label}
      </span>
      <SecretField
        key={`${round}-${props.held?.where ?? "none"}`}
        id={props.id}
        labelId={`${props.id}-label`}
        label={props.label}
        local={props.local}
        held={props.held}
        reference={reference}
        onReference={setReference}
        pasted={typed}
        onPaste={setTyped}
        disabled={busy}
        describedBy={props.hint ? `${props.id}-hint` : undefined}
        onMode={setHow}
      />
      {props.hint && (
        <p className="hint" id={`${props.id}-hint`}>
          {props.hint}
        </p>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <div className="row-end">
        {props.more}
        <button type="submit" className="btn small primary" disabled={!ready || busy} aria-label={props.saveLabel}>
          {t(busy ? "secrets.saving" : "secrets.save")}
        </button>
      </div>
    </form>
  );
}

/** The keys one add-on says it needs, each a password box. Nothing is shown for an add-on that needs none. */
export function AddonSecrets(props: { plugin: string; name?: string }) {
  const { t, has } = useWords();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const all = useQuery({ queryKey: ["addon-secrets"], queryFn: api.addonSecrets });
  const base = useId();
  const mine = all.data?.find((a) => a.plugin === props.plugin);
  if (!mine || mine.secrets.length === 0) return null;
  const local = setup.data?.local ?? true;
  const addon = props.name ?? readable(props.plugin);
  const labelOf = (secret: string) => {
    const key = `secrets.addon.${props.plugin}.${secret}`;
    return has(key) ? t(key) : readable(secret);
  };
  return (
    <section className="kept-secrets" aria-labelledby={`${base}-title`}>
      <h3 id={`${base}-title`}>{t("secrets.addon.title")}</h3>
      <p className="hint">{t("secrets.addon.intro", { addon })}</p>
      {mine.secrets.map((s) => (
        <KeptSecretRow
          key={s.secret}
          id={`${base}-${s.secret}`}
          label={labelOf(s.secret)}
          saveLabel={t("secrets.addon.save_named", { label: labelOf(s.secret) })}
          local={local}
          held={heldOf(s)}
          onSave={async (body) => {
            const saved = await api.giveAddonSecret(props.plugin, s.secret, { ...body, fingerprint: await fingerprint() });
            await afterSave(saved, { message: t("secrets.addon.saved", { label: labelOf(s.secret), addon }) });
          }}
        />
      ))}
    </section>
  );
}

/** The key that locks every backup copy: typed, or made by the app and shown once, or as where it is kept. */
export function BackupKey() {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const { push } = useToasts();
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  const state = useQuery({ queryKey: ["backup-key"], queryFn: api.backupKey });
  const base = useId();
  // The key the app just made, shown until the person says they have it. Held in this state only.
  const [made, setMade] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const [problem, setProblem] = useState("");
  if (!state.data) return null;
  const local = setup.data?.local ?? true;
  const held = heldOf(state.data);
  const make = async () => {
    setMaking(true);
    setProblem("");
    try {
      const saved = await api.setBackupKey({ make: true, fingerprint: await fingerprint() });
      setMade(saved.made ?? null);
      await afterSave(saved, { message: t("backup_key.made_saved") });
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setMaking(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(made ?? "");
      push({ message: t("backup_key.copied") });
    } catch {
      push({ message: t("toast.copy_blocked") });
    }
  };
  return (
    <section className="kept-secrets" aria-labelledby={`${base}-title`}>
      <h3 id={`${base}-title`}>{t("backup_key.title")}</h3>
      <p className="hint">{t("backup_key.intro")}</p>
      <p className="hint" id={`${base}-warning`}>
        {t("backup_key.warning")}
      </p>
      {held && local && <p className="hint">{t("backup_key.replace_note")}</p>}
      <KeptSecretRow
        id={`${base}-key`}
        label={t("backup_key.label")}
        saveLabel={t("backup_key.save")}
        local={local}
        held={held}
        hint={held ? undefined : t("backup_key.none")}
        onSave={async (body) => {
          const saved = await api.setBackupKey({ ...body, fingerprint: await fingerprint() });
          await afterSave(saved, { message: t("backup_key.saved") });
        }}
        more={
          local ? (
            <button type="button" className="btn small" disabled={making} onClick={() => void make()}>
              {t("backup_key.make")}
            </button>
          ) : null
        }
      />
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      {made && (
        <div className="made-key" role="group" aria-labelledby={`${base}-made-title`}>
          <p className="what" id={`${base}-made-title`}>
            {t("backup_key.made_title")}
          </p>
          <input type="text" readOnly value={made} aria-labelledby={`${base}-made-title`} onFocus={(e) => e.currentTarget.select()} />
          <p className="hint">{t("backup_key.made_hint")}</p>
          <div className="row-end">
            <button type="button" className="btn small" onClick={() => void copy()}>
              {t("backup_key.copy")}
            </button>
            <button type="button" className="btn small primary" onClick={() => setMade(null)}>
              {t("backup_key.done")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
