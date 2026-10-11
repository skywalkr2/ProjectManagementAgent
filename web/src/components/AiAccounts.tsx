// The AI accounts that are set up, one row each: its name, the service it is, whether it has a key, and what it does for
// the assistant. The row's one primary action tests it; replacing the key, changing the models and removing it are in its
// menu. Removing acts at once and offers Undo. Used in the AI step of the setup guide and in Settings. The service's
// name comes from the catalog entry the account was made from; a key is never shown, only whether one is kept.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { RowMenu, type MenuAction } from "./RowMenu";

type Account = S["AiAccountView"];
type Kind = S["EndpointView"];
type Mode = "key" | "models" | null;

/** The short model name that stands for the everyday work, and the one added for harder work. */
const EVERYDAY = "everyday";
const HARDER = "harder";

export function AiAccounts(props: {
  /** Whether keys can be pasted here; read from the setup when not given. */
  local?: boolean;
  /** The level of the section's heading: 3 in Settings, 4 inside a step of the setup guide. */
  level?: 3 | 4;
}) {
  const { t } = useWords();
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup, enabled: props.local === undefined });
  const local = props.local ?? setup.data?.local ?? true;
  if (accounts.isPending) return null;
  // A list that didn't load says so quietly, without a heading of its own.
  if (accounts.isError) return <p className="hint">{t("ai_accounts.load_failed")}</p>;
  return (
    <section className="ai-accounts" aria-labelledby="ai-accounts-title">
      <div className="heading">
        {props.level === 4 ? <h4 id="ai-accounts-title">{t("ai_accounts.title")}</h4> : <h3 id="ai-accounts-title">{t("ai_accounts.title")}</h3>}
      </div>
      {accounts.data.length === 0 ? (
        <p className="hint">{t("ai_accounts.none")}</p>
      ) : (
        <>
          <p className="hint">{t("ai_accounts.intro")}</p>
          <ul className="queue">
            {accounts.data.map((account) => (
              <AccountRow
                key={account.name}
                account={account}
                kind={endpoints.data?.find((e) => e.id === account.kind)}
                local={local}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function AccountRow(props: { account: Account; kind: Kind | undefined; local: boolean }) {
  const { t, has } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const { account, kind } = props;
  const base = `ai-account-${account.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [testing, setTesting] = useState(false);
  const [results, setResults] = useState<S["AiTestResult"][] | null>(null);
  const [key, setKey] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [harder, setHarder] = useState("");
  const testButton = useRef<HTMLButtonElement>(null);
  const firstField = useRef<HTMLInputElement>(null);

  const workName = (tier: string) => (has(`welcome.ai.tier.${tier}`) ? t(`welcome.ai.tier.${tier}`) : tier);
  const status = account.has_key
    ? t("ai_accounts.key_saved")
    : kind && !kind.needs_key
      ? t("ai_accounts.no_key_needed")
      : t("ai_accounts.no_key");
  const doing = account.used_for.length ? t("ai_accounts.used_for", { work: account.used_for.map(workName).join(", ") }) : t("ai_accounts.unused");

  const open = (next: Exclude<Mode, null>) => {
    setProblem("");
    setKey("");
    setHarder("");
    setModels({ ...account.models });
    setMode(next);
    restoreFocus(() => firstField.current);
  };
  const close = () => {
    setMode(null);
    setProblem("");
    restoreFocus(() => testButton.current);
  };

  const fail = (err: unknown) => {
    // A changed file means the lists are out of date: load them again, keeping what was typed.
    if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
    setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
  };

  /** Save a change with the settings' current fingerprint, then read it back with Undo (and the restart question if asked). */
  const save = async (work: (fingerprint: string) => Promise<S["SettingsSaved"]>, message: string): Promise<boolean> => {
    setBusy(true);
    setProblem("");
    try {
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await work(current.fingerprint);
      await afterSave(saved, { message });
      return true;
    } catch (err) {
      fail(err);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const remove = () => void save((fingerprint) => api.removeAccount(account.name, fingerprint), t("ai_accounts.removed", { name: account.name }));

  const replaceKey = async () => {
    const pasted = key.trim();
    if (!pasted) return;
    const done = await save(
      (fingerprint) => api.changeAccount(account.name, props.local ? { fingerprint, key: pasted } : { fingerprint, key_ref: pasted }),
      t("ai_accounts.key_replaced", { name: account.name }),
    );
    if (done) {
      setKey("");
      close();
    }
  };

  const changeModels = async () => {
    const next: Record<string, string> = {};
    for (const [short, id] of Object.entries(models)) next[short] = id.trim();
    if (harder.trim()) next[HARDER] = harder.trim();
    const done = await save(
      (fingerprint) => api.changeAccount(account.name, { fingerprint, models: next }),
      t("ai_accounts.models_changed", { name: account.name }),
    );
    if (done) close();
  };

  const test = async () => {
    setTesting(true);
    setProblem("");
    setResults(null);
    try {
      const all = await api.testAi();
      setResults(all.filter((r) => r.account === account.name));
    } catch (err) {
      fail(err);
    } finally {
      setTesting(false);
    }
  };

  const actions: MenuAction[] = [
    { id: "key", label: t("ai_accounts.replace_key"), run: () => open("key") },
    { id: "models", label: t("ai_accounts.change_models"), run: () => open("models") },
    { id: "remove", label: t("ai_accounts.remove"), run: remove },
  ];

  const modelLabel = (short: string) =>
    short === EVERYDAY ? t("ai_accounts.model_everyday") : short === HARDER ? t("ai_accounts.model_harder") : t("ai_accounts.model_other", { short });
  const modelsChanged =
    harder.trim() !== "" || Object.entries(models).some(([short, id]) => id.trim() !== (account.models[short] ?? ""));
  const modelsBlank = Object.values(models).some((id) => id.trim() === "");
  const examplesId = `${base}-examples`;
  const lines = (results ?? []).map((r) => ({
    key: `${r.tier}:${r.main}`,
    ok: r.ok,
    text: t("ai_accounts.test_line", {
      work: workName(r.tier),
      outcome: r.ok ? t("welcome.ai.answered") : r.detail ? t("welcome.ai.failed", { detail: r.detail }) : t("welcome.ai.failed_plain"),
    }),
  }));

  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={`${base}-title`}>
      <div className="row pair">
        <div className="text">
          <strong id={`${base}-title`}>{account.name}</strong>
          {kind && kind.name !== account.name && <span className="sub">{t("ai_accounts.service", { service: kind.name })}</span>}
          <span className="sub">
            <span aria-hidden="true">{account.has_key ? "✓ " : "– "}</span>
            {status}
          </span>
          <span className="sub">{doing}</span>
          {mode === "key" && (
            <form
              className="field"
              onSubmit={(e) => {
                e.preventDefault();
                void replaceKey();
              }}
            >
              <label htmlFor={`${base}-key`}>{t(props.local ? "ai_accounts.new_key" : "welcome.ai.key_where")}</label>
              <input
                id={`${base}-key`}
                ref={firstField}
                type={props.local ? "password" : "text"}
                value={key}
                autoComplete="off"
                spellCheck={false}
                placeholder={props.local ? undefined : "env:NAME"}
                aria-describedby={`${base}-key-hint`}
                onChange={(e) => setKey(e.target.value)}
              />
              <p className="hint" id={`${base}-key-hint`}>
                {t(props.local ? "ai_accounts.new_key_hint" : "welcome.ai.key_where_hint")}
              </p>
              <div className="row-end">
                <button type="button" className="btn quiet" disabled={busy} onClick={close}>
                  {t("ai_accounts.cancel")}
                </button>
                <button type="submit" className="btn primary" disabled={busy || key.trim() === ""}>
                  {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
                </button>
              </div>
            </form>
          )}
          {mode === "models" && (
            <form
              className="field"
              onSubmit={(e) => {
                e.preventDefault();
                if (modelsChanged && !modelsBlank) void changeModels();
              }}
            >
              <fieldset className="details">
                <legend>{t("ai_accounts.models_title", { name: account.name })}</legend>
                {Object.keys(models).map((short, i) => (
                  <div className="field" key={short}>
                    <label htmlFor={`${base}-model-${short}`}>{modelLabel(short)}</label>
                    <input
                      id={`${base}-model-${short}`}
                      ref={i === 0 ? firstField : undefined}
                      type="text"
                      value={models[short]}
                      autoComplete="off"
                      list={kind?.model_examples?.length ? examplesId : undefined}
                      onChange={(e) => setModels({ ...models, [short]: e.target.value })}
                    />
                  </div>
                ))}
                {!(HARDER in account.models) && (
                  <div className="field">
                    <label htmlFor={`${base}-model-new`}>{t("ai_accounts.model_add_harder")}</label>
                    <input
                      id={`${base}-model-new`}
                      type="text"
                      value={harder}
                      autoComplete="off"
                      list={kind?.model_examples?.length ? examplesId : undefined}
                      onChange={(e) => setHarder(e.target.value)}
                    />
                  </div>
                )}
                {kind?.model_examples?.length ? (
                  <datalist id={examplesId}>
                    {kind.model_examples.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                ) : null}
              </fieldset>
              <div className="row-end">
                <button type="button" className="btn quiet" disabled={busy} onClick={close}>
                  {t("ai_accounts.cancel")}
                </button>
                <button type="submit" className="btn primary" disabled={busy || !modelsChanged || modelsBlank}>
                  {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
                </button>
              </div>
            </form>
          )}
          {problem && (
            <p className="problem-note" role="alert">
              {problem}
            </p>
          )}
          <div role="status" aria-live="polite">
            {testing && <p className="hint">{t("ai_accounts.testing")}</p>}
            {results && lines.length === 0 && <p className="hint">{t("ai_accounts.test_nothing", { name: account.name })}</p>}
            {lines.length > 0 && (
              <ul className="plain-list test-results">
                {lines.map((l) => (
                  <li key={l.key} className={l.ok ? "result-ok" : "result-bad"}>
                    {l.text}
                    <span aria-hidden="true">{l.ok ? " ✓" : " ✗"}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            ref={testButton}
            disabled={testing || busy}
            aria-label={t("ai_accounts.test_named", { name: account.name })}
            onClick={() => void test()}
          >
            {t(testing ? "ai_accounts.testing" : "ai_accounts.test")}
          </button>
          <RowMenu label={account.name} actions={actions} />
        </div>
      </div>
    </li>
  );
}
