// The backup step of the setup guide (design 7.8): a folder outside the workspace, checked before it is saved. On the
// person's own computer the folder can be picked from a list.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { FolderPicker } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";

function size(mb: number, t: (key: string, vars?: Record<string, string | number>) => string): string {
  return mb >= 1024 ? t("welcome.backup.gb", { n: (mb / 1024).toFixed(1) }) : t("welcome.backup.mb", { n: Math.round(mb) });
}

export function WelcomeBackup(props: { local: boolean }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [checked, setChecked] = useState<S["FolderCheckView"] | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const chooser = useRef<HTMLButtonElement>(null);

  const targets = settings.data?.items.find((i) => i.key === "storage.backups.targets")?.value;
  const existing = Array.isArray(targets)
    ? targets.flatMap((x: unknown) => {
        const target = x as { path?: unknown; label?: unknown };
        return typeof target?.path === "string" ? [{ path: target.path, label: typeof target.label === "string" ? target.label : "" }] : [];
      })
    : [];

  const check = async (at: string) => {
    setProblem("");
    try {
      setChecked(await api.folderCheck(at));
    } catch (err) {
      setChecked(null);
      setProblem(problemText(err, t));
    }
  };

  const save = async () => {
    if (!settings.data) return;
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveBackupFolder({ path: path.trim(), label: label.trim(), fingerprint: settings.data.fingerprint });
      setPath("");
      setLabel("");
      setChecked(null);
      await afterSave(saved, { message: t("welcome.backup.saved", { path: path.trim() }) });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

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
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
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
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        <div className="row-end">
          <button type="submit" className="btn primary" disabled={busy || !path.trim() || !settings.data}>
            {t("welcome.backup.save")}
          </button>
        </div>
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
