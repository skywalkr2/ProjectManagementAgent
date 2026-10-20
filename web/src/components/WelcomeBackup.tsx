// The backup step of the setup guide (design 7.8): the cloud drives found on the computer, by name, with the first
// recommended; "Back up now and continue" makes the folder inside the drive, saves it and makes the first backup. Another
// folder (a USB drive, a network folder) is a path behind "Choose another folder", checked before it is saved. On the
// person's own computer that folder can be picked from a list.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { backupText } from "../lib/backup";
import { problemText } from "../lib/problem";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { FolderPicker } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";
import { useContinue, useHasContinueSlot } from "../lib/walkthrough-continue";
import { Button } from "../ui/Button";

/** The choice that is not one of the drives found: a folder of the person's own. */
const OTHER = "\u0001other";

function size(mb: number, t: (key: string, vars?: Record<string, string | number>) => string): string {
  return mb >= 1024 ? t("welcome.backup.gb", { n: (mb / 1024).toFixed(1) }) : t("welcome.backup.mb", { n: Math.round(mb) });
}

export function WelcomeBackup(props: { local: boolean }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [checked, setChecked] = useState<S["FolderCheckView"] | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const chooser = useRef<HTMLButtonElement>(null);
  const hasSlot = useHasContinueSlot();
  const drives = useQuery({ queryKey: ["cloud-folders"], queryFn: api.cloudFolders, enabled: props.local, retry: false });
  const found = drives.data?.folders ?? [];
  const [choice, setChoice] = useState<string | null>(null);

  const targets = settings.data?.items.find((i) => i.key === "storage.backups.targets")?.value;
  const existing = Array.isArray(targets)
    ? targets.flatMap((x: unknown) => {
        const target = x as { path?: unknown; label?: unknown };
        return typeof target?.path === "string" ? [{ path: target.path, label: typeof target.label === "string" ? target.label : "" }] : [];
      })
    : [];

  // The first backup is made as soon as the folder is chosen: the screen says how it went.
  const backup = existing.length > 0 && status.data?.backup.configured ? status.data.backup : null;
  const failed = !!backup && backup.last_success === null && !!backup.last_error;

  const check = async (at: string) => {
    setProblem("");
    try {
      setChecked(await api.folderCheck(at));
    } catch (err) {
      setChecked(null);
      setProblem(problemText(err, t));
    }
  };

  // Folders already chosen are kept unless the person chooses another way; with none, the first drive found is chosen.
  const looking = props.local && drives.isPending;
  const picked = choice ?? (existing.length > 0 || looking ? null : (found[0]?.name ?? OTHER));
  const ownFolder = picked === OTHER;

  /** Makes the choice real: the drive's folder is made and saved, or the typed folder is. True when it went through. */
  const save = async (): Promise<boolean> => {
    if (!settings.data || picked === null) return true;
    setBusy(true);
    setProblem("");
    try {
      if (ownFolder) {
        const saved = await api.saveBackupFolder({ path: path.trim(), label: label.trim(), fingerprint: settings.data.fingerprint });
        setPath("");
        setLabel("");
        setChecked(null);
        await afterSave(saved, { message: t("welcome.backup.saved", { path: path.trim() }) });
      } else {
        const saved = await api.backupToCloudFolder({ name: picked, fingerprint: settings.data.fingerprint });
        await afterSave(saved, { message: t("welcome.backup.saved_drive", { name: picked }) });
      }
      setChoice(null);
      await client.invalidateQueries({ queryKey: ["status"] });
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const missing = looking ? t("welcome.backup.looking") : ownFolder && !path.trim() ? t("welcome.backup.why_path") : !settings.data ? t("loading") : "";
  useContinue(hasSlot ? { run: save, label: t("welcome.backup.go"), disabled: !!missing, why: missing } : null);

  return (
    <div className="guide-body">
      {existing.length > 0 && (
        <div>
          <p className="what">{t("welcome.backup.current")}</p>
          <ul className="plain-list">
            {existing.map((e) => (
              <li key={e.path}>
                <span className="path">{e.label ? t("welcome.backup.target", { label: e.label, path: e.path }) : e.path}</span>
              </li>
            ))}
          </ul>
          {backup && (
            <p className={failed ? "problem-note" : "hint"} role={failed ? "alert" : "status"} data-first-backup="">
              {failed
                ? t("welcome.backup.first_failed", { problem: backup.last_error ?? "" })
                : backup.last_success === null
                  ? t("welcome.backup.first_making")
                  : backup.needs_attention
                    ? backupText(backup, t)
                    : t("welcome.backup.first_made")}
            </p>
          )}
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
        }}
      >
        {found.length > 0 || existing.length > 0 ? (
          <fieldset className="details">
            <legend>{t("welcome.backup.where")}</legend>
            {found.map((drive) => (
              <label key={drive.name} className="radio kind-choice kind-card">
                <input type="radio" name="backup-where" checked={picked === drive.name} onChange={() => setChoice(drive.name)} />
                <span>
                  <strong>{drive.name}</strong>
                  <span className="hint block">{drives.data?.shown}</span>
                  {drive.recommended && <span className="pill tag-recommended">{t("welcome.ai.recommended")}</span>}
                </span>
              </label>
            ))}
            <label className="radio kind-choice kind-card">
              <input type="radio" name="backup-where" checked={ownFolder} onChange={() => setChoice(OTHER)} />
              <span>
                <strong>{t("welcome.backup.other")}</strong>
                <span className="hint block">{t("welcome.backup.other_note")}</span>
              </span>
            </label>
          </fieldset>
        ) : (
          props.local && !looking && <p className="hint">{t("welcome.backup.none_found")}</p>
        )}
        {ownFolder && (
          <>
            <div className="field">
              <label htmlFor="backup-path">{t("welcome.backup.path")}</label>
              <div className="inline-field">
                <input
                  id="backup-path"
                  type="text"
                  value={path}
                  autoComplete="off"
                  aria-describedby="backup-path-hint"
                  onChange={(e) => {
                    setPath(e.target.value);
                    setChecked(null);
                  }}
                />
                <button type="button" className="btn" disabled={!path.trim()} onClick={() => void check(path.trim())}>
                  {t("welcome.backup.check")}
                </button>
                {props.local && (
                  <button type="button" className="btn" ref={chooser} onClick={() => setPicking(true)}>
                    {t("welcome.backup.choose")}
                  </button>
                )}
              </div>
              <p className="hint" id="backup-path-hint">
                {t("welcome.backup.path_hint")}
              </p>
            </div>
            <div className="field">
              <label htmlFor="backup-label">{t("welcome.backup.label")}</label>
              <input id="backup-label" type="text" value={label} autoComplete="off" onChange={(e) => setLabel(e.target.value)} />
            </div>
            <div role="status">
              {checked && (
                <p className={checked.ok ? "hint" : "problem-note"}>
                  {checked.ok
                    ? checked.free_mb === null || checked.free_mb === undefined
                      ? t("welcome.backup.ok")
                      : t("welcome.backup.ok_free", { size: size(checked.free_mb, t) })
                    : t("welcome.backup.not_ok", { problem: checked.problem ?? "" })}
                </p>
              )}
            </div>
          </>
        )}
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        {!hasSlot && (
          <div className="row-end">
            <Button variant="primary" loading={busy} disabled={!!missing || picked === null} reason={missing || undefined} onClick={() => void save()}>
              {t("welcome.backup.go_here")}
            </Button>
          </div>
        )}
      </form>
      {picking && (
        <FolderPicker
          start={checked?.ok ? path : undefined}
          onClose={() => {
            setPicking(false);
            restoreFocus(() => chooser.current);
          }}
          onPick={(picked) => {
            setPicking(false);
            setPath(picked);
            void check(picked);
            restoreFocus(() => chooser.current);
          }}
        />
      )}
    </div>
  );
}
