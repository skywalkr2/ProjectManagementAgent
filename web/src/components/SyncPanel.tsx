// The synced folder (design 5.0, 7.9): where it is, whether it can be written, what changed outside the app, and the
// choices about it. It lives in Settings under Backups and sync, and every choice is saved like any other setting.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { FolderPicker, useFolderListing } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";
import { useTextReview } from "./TextReview";
import { Skeleton } from "../ui/Skeleton";

// ---- synced folder -------------------------------------------------------------------------------------------------

const SYNC_FOLDER = "storage.sync.folder";
const SYNC_SHARED = "storage.sync.shared";

/** The synced folder isn't set up yet: what it is for, and a way to choose one that is saved like any other setting.
 * Once a folder is chosen it asks whether anyone else can change the files in it, and saves both answers together. */
function SyncUnset(props: { fingerprint: string }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const canList = useFolderListing();
  const [picking, setPicking] = useState(false);
  const [typed, setTyped] = useState("");
  // The folder chosen, waiting for the answer about sharing, and that answer (none until the person gives it).
  const [chosen, setChosen] = useState<string | null>(null);
  const [shared, setShared] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const chooser = useRef<HTMLButtonElement>(null);
  const firstAnswer = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (chosen !== null) firstAnswer.current?.focus();
  }, [chosen]);

  const save = async (path: string, others: boolean) => {
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.saveSettings({
        changes: { [SYNC_FOLDER]: path.trim(), [SYNC_SHARED]: others },
        reset: [],
        fingerprint: props.fingerprint,
      });
      await afterSave(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  if (chosen !== null) {
    return (
      <form
        className="sync-body"
        onSubmit={(e) => {
          e.preventDefault();
          if (shared !== null) void save(chosen, shared);
        }}
      >
        <p className="path">{t("setup.sync_shared_for", { folder: chosen })}</p>
        <fieldset className="change">
          <legend>{t("setup.sync_shared_title")}</legend>
          <div className="choice-row">
            <label className="check-line">
              <input type="radio" name="sync-shared" ref={firstAnswer} checked={shared === false} onChange={() => setShared(false)} />
              <span>{t("setup.sync_shared_no")}</span>
            </label>
            <label className="check-line">
              <input type="radio" name="sync-shared" checked={shared === true} onChange={() => setShared(true)} />
              <span>{t("setup.sync_shared_yes")}</span>
            </label>
          </div>
          <p className="hint">{t("setup.sync_shared_hint")}</p>
        </fieldset>
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        <div className="row-end">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              setChosen(null);
              setShared(null);
            }}
          >
            {t("setup.sync_shared_back")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || shared === null}>
            {t("setup.sync_shared_save")}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="sync-body">
      <p>{t("setup.sync_unset")}</p>
      {canList ? (
        <div className="row-end">
          <button type="button" className="btn primary" ref={chooser} disabled={busy} onClick={() => setPicking(true)}>
            {t("setup.sync_choose")}
          </button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (typed.trim()) setChosen(typed.trim());
          }}
        >
          <div className="field">
            <label htmlFor="sync-path">{t("setup.sync_path")}</label>
            <div className="inline-field">
              <input id="sync-path" type="text" value={typed} autoComplete="off" onChange={(e) => setTyped(e.target.value)} />
              <button type="submit" className="btn primary" disabled={!typed.trim()}>
                {t("setup.sync_save")}
              </button>
            </div>
          </div>
        </form>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      {picking && (
        <FolderPicker
          onClose={() => {
            setPicking(false);
            restoreFocus(() => chooser.current);
          }}
          onPick={(picked) => {
            setPicking(false);
            setChosen(picked.trim());
          }}
        />
      )}
    </div>
  );
}

/** Whether anyone else can change the folder: a setting the running app takes in at once, saved like any other. */
function SharedSwitch(props: { shared: boolean }) {
  const { t } = useWords();
  const afterSave = useAfterSave();
  const fresh = useFreshFingerprint();
  const [problem, setProblem] = useState("");
  const change = async (next: boolean) => {
    setProblem("");
    try {
      const saved = await api.saveSettings({ changes: { [SYNC_SHARED]: next }, reset: [], fingerprint: await fresh() });
      await afterSave(saved);
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    }
  };
  return (
    <div className="field">
      <label className="check-line">
        <input type="checkbox" checked={props.shared} onChange={(e) => void change(e.target.checked)} />
        <span>{t("setup.sync_shared_switch")}</span>
      </label>
      {props.shared && <p className="hint">{t("setup.sync_shared_on")}</p>}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

export function SyncPanel() {
  const { t, tn } = useWords();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const saved = settings.data?.items.find((i) => i.key === SYNC_FOLDER)?.value;
  const folderSet = typeof saved === "string" && saved.trim() !== "";
  // Nothing is asked of the sync route until a folder is set; a failed answer is retried quietly before it is shown.
  const sync = useQuery({
    queryKey: ["sync"],
    queryFn: api.sync,
    enabled: folderSet,
    retry: 3,
    retryDelay: (attempt) => Math.min(500 * 2 ** attempt, 4000),
  });
  const { open, dialog } = useTextReview();
  const data = sync.data;
  return (
    <section className="panel-section" aria-labelledby="sync-title">
      <div className="heading">
        <h3 id="sync-title">{t("setup.sync")}</h3>
      </div>
      {settings.isPending || (folderSet && sync.isPending) ? (
        <Skeleton />
      ) : settings.isError ? (
        <p className="empty">
          {t("setup.sync_failed")}{" "}
          <button type="button" className="btn" onClick={() => void settings.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : !folderSet ? (
        <SyncUnset fingerprint={settings.data!.fingerprint} />
      ) : sync.isError || !data ? (
        <p className="empty">
          {t("setup.sync_failed")}{" "}
          <button type="button" className="btn" onClick={() => void sync.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : !data.folder ? (
        <p className="empty">{t("setup.sync_off")}</p>
      ) : (
        <div className="sync-body">
          <p>{t("setup.sync_in", { folder: data.folder })}</p>
          <SharedSwitch shared={data.shared} />
          {data.handover && (
            <p>
              <a className="btn primary" href={viewHref("handover")}>
                {t("setup.sync_handover")}
              </a>
            </p>
          )}
          {data.stopped && (
            <p className="problem-note" role="alert">
              {t("setup.sync_stopped")}
            </p>
          )}
          {data.problem && (
            <p className="problem-note" role="alert">
              {t("setup.sync_problem", { problem: data.problem })}
            </p>
          )}
          {data.changed_outside.length > 0 && <p className="hint">{tn("setup.sync_changed", data.changed_outside.length)}</p>}
          {data.removed_outside.length > 0 && <p className="hint">{tn("setup.sync_removed", data.removed_outside.length)}</p>}
          {data.outside_edits.length > 0 && (
            <section aria-labelledby="sync-edits">
              <h3 id="sync-edits" className="what">
                {t("setup.sync_edits")}
              </h3>
              {data.shared && <p className="hint">{t("setup.sync_edits_shared")}</p>}
              <ul className="queue">
                {data.outside_edits.map((edit) => (
                  <OutsideEdit key={edit.path} edit={edit} onReview={open} />
                ))}
              </ul>
            </section>
          )}
          {data.conflict_copies.length > 0 && (
            <section aria-labelledby="sync-copies">
              <h3 id="sync-copies" className="what">
                {t("setup.sync_copies")}
              </h3>
              <ul className="plain-list">
                {data.conflict_copies.map((path) => (
                  <li key={path} className="path">
                    {path}
                  </li>
                ))}
              </ul>
              <p className="hint">{t("setup.sync_copies_note")}</p>
            </section>
          )}
        </div>
      )}
      {dialog}
    </section>
  );
}

function OutsideEdit(props: { edit: S["OutsideEditView"]; onReview: (version: string, returnTo?: () => HTMLElement | null | undefined) => void }) {
  const { t } = useWords();
  const { edit } = props;
  const button = useRef<HTMLButtonElement>(null);
  return (
    <li className="line">
      <div className="row">
        <div className="text">
          <strong className="path">{edit.path}</strong>
          {edit.problem && <span className="sub">{edit.problem}</span>}
          {!edit.version && !edit.problem && <span className="sub">{t("setup.sync_waiting")}</span>}
        </div>
        {edit.version && (
          <div className="acts">
            <button
              type="button"
              className="btn primary"
              ref={button}
              aria-label={t("panel.action_for", { action: t("setup.sync_review"), what: edit.path })}
              onClick={() => props.onReview(edit.version!, () => button.current)}
            >
              {t("setup.sync_review")}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

