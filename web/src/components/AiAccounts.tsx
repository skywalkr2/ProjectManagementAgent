// The AI accounts that are set up, one row each: its name, the service it is, whether it has a key, and what it does for
// the assistant. The row's one primary action tests it; replacing the key, changing the models and removing it are in its
// menu. Removing acts at once and offers Undo. Making an account do the work, or changing the model of one that does,
// is a switch: when checks on a switch are on, its primary action is "Switch and check" with the cost shown first, and
// "Switch without checking" is the other way. Used in the AI step of the setup guide and in Settings. The service's
// name comes from the catalog entry the account was made from; a key is never shown, only whether one is kept.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { day } from "../lib/dates";
import { problemText } from "../lib/problem";
import { asReference } from "../lib/secret-ref";
import { useMoney } from "../lib/money";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { restoreFocus } from "./ModalPanel";
import { RowMenu, type MenuAction } from "./RowMenu";
import { Icon } from "../ui/Icon";

type Account = S["AiAccountView"];
type Kind = S["EndpointView"];
type Mode = "key" | "models" | "expires" | null;

/** The short model name that stands for the everyday work, and the one added for harder work. */
const EVERYDAY = "everyday";
const HARDER = "harder";

/** Accounts that work come first; one whose key is missing, or that does no work yet, follows. Otherwise the order is kept. */
function inOrder(list: Account[]): Account[] {
  const working = (a: Account) => a.key_state !== "missing" && a.used_for.length > 0;
  return [...list.filter(working), ...list.filter((a) => !working(a))];
}

/** A value once it has stayed the same for a moment, so a price isn't asked for at every keystroke. */
function useSettled<T>(value: T, ms = 500): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

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
            {inOrder(accounts.data).map((account) => (
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
  const freshFingerprint = useFreshFingerprint();
  const money = useMoney();
  const { account, kind } = props;
  const base = `ai-account-${account.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<S["AiTestResult"] | null>(null);
  const [key, setKey] = useState("");
  const [ends, setEnds] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [harder, setHarder] = useState("");
  const testButton = useRef<HTMLButtonElement>(null);
  const firstField = useRef<HTMLInputElement>(null);

  const workName = (tier: string) => (has(`welcome.ai.tier.${tier}`) ? t(`welcome.ai.tier.${tier}`) : tier);
  const keyState = account.key_state ?? (account.has_key ? "saved" : "none");
  const missing = keyState === "missing";
  const status =
    keyState === "saved"
      ? t("ai_accounts.key_saved")
      : missing
        ? account.key_where
          ? t("ai_accounts.key_missing", { where: account.key_where })
          : t("ai_accounts.key_missing_plain")
        : kind && !kind.needs_key
          ? t("ai_accounts.no_key_needed")
          : t("ai_accounts.no_key");
  const doing = account.used_for.length ? t("ai_accounts.used_for", { work: account.used_for.map(workName).join(", ") }) : t("ai_accounts.unused");

  const open = (next: Exclude<Mode, null>) => {
    setProblem("");
    setKey("");
    setEnds(next === "expires" ? (account.credential_expires ?? "") : "");
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
  const save = async (work: (fingerprint: string) => Promise<S["SettingsSaved"]>, message: string | (() => string)): Promise<boolean> => {
    setBusy(true);
    setProblem("");
    try {
      const current = await client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 });
      const saved = await work(current.fingerprint);
      await afterSave(saved, { message: typeof message === "function" ? message() : message });
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
      (fingerprint) => {
        // A new key has its own end date: the one typed, else none is known, so the old key's date is dropped.
        const dates = ends ? { credential_expires: ends } : account.credential_expires ? { clear_credential_expires: true } : {};
        return api.changeAccount(account.name, props.local ? { fingerprint, key: pasted, ...dates } : { fingerprint, key_ref: asReference(pasted), ...dates });
      },
      t("ai_accounts.key_replaced", { name: account.name }),
    );
    if (done) {
      setKey("");
      close();
    }
  };

  const saveEnds = async () => {
    const done = await save(
      (fingerprint) => api.changeAccount(account.name, ends ? { fingerprint, credential_expires: ends } : { fingerprint, clear_credential_expires: true }),
      t(ends ? "ai_accounts.key_ends_saved" : "ai_accounts.key_ends_cleared", { name: account.name, date: ends ? day(ends) : "" }),
    );
    if (done) close();
  };

  const nextModels = () => {
    const next: Record<string, string> = {};
    for (const [short, id] of Object.entries(models)) next[short] = id.trim();
    if (harder.trim()) next[HARDER] = harder.trim();
    return next;
  };

  /** Saves the typed models; with `check`, as a switch whose new choice is checked in the background. */
  const changeModels = async (check = false) => {
    let checking = false;
    const next = nextModels();
    const done = await save(
      async (fingerprint) => {
        if (!check) return api.changeAccount(account.name, { fingerprint, models: next });
        const answer = await api.switchAndCheck(account.name, { fingerprint, models: next });
        checking = answer.checking;
        return answer.saved;
      },
      () => t(checking ? "ai_accounts.switch_checking" : "ai_accounts.models_changed", { name: account.name }),
    );
    if (done) close();
  };

  const test = async () => {
    setTesting(true);
    setProblem("");
    setResult(null);
    try {
      const answer = await api.testAccount(account.name);
      // One answer for the account; a list is read by its first entry.
      setResult((Array.isArray(answer) ? answer[0] : answer) ?? null);
    } catch (err) {
      fail(err);
    } finally {
      setTesting(false);
    }
  };

  // Make this account do the assistant's work: everyday work on its first model, harder work on its harder one. With
  // `check`, as a switch whose new choice is checked in the background.
  const shorts = Object.keys(account.models);
  const everyday = shorts.find((s) => s !== HARDER) ?? shorts[0];
  const deep = HARDER in account.models ? HARDER : everyday;
  const takesWork = account.adapter !== "stub" && account.used_for.length === 0 && shorts.length > 0;
  const useOffer = useQuery({
    queryKey: ["switch-estimate", account.name, "use", everyday, deep],
    queryFn: async () => api.switchEstimate(account.name, { fingerprint: await freshFingerprint(), use: { routine: everyday, deep } }),
    enabled: takesWork,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const offeredUse = takesWork && useOffer.data?.offered === true;
  const useForWork = (check = false) => {
    if (shorts.length === 0) return;
    let checking = false;
    void save(
      async (fingerprint) => {
        const body = { fingerprint, use: { routine: everyday, deep } };
        if (!check) return api.changeAccount(account.name, body);
        const answer = await api.switchAndCheck(account.name, body);
        checking = answer.checking;
        return answer.saved;
      },
      () => t(checking ? "ai_accounts.switch_checking" : "ai_accounts.used_for_work", { name: account.name }),
    );
  };

  // A change of model on an account that does work is a switch too; its price is asked for once the typing settles.
  const typedModels = useSettled(mode === "models" ? JSON.stringify(nextModels()) : "");
  const worksNow = account.used_for.length > 0;
  const typedBlank = Object.values(JSON.parse(typedModels || "{}") as Record<string, string>).some((v) => v === "");
  const modelsOffer = useQuery({
    queryKey: ["switch-estimate", account.name, "models", typedModels],
    queryFn: async () => api.switchEstimate(account.name, { fingerprint: await freshFingerprint(), models: JSON.parse(typedModels) as Record<string, string> }),
    enabled: mode === "models" && worksNow && typedModels !== "" && !typedBlank,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const checkLabel = (offer: S["AiSwitchEstimate"] | undefined) =>
    offer?.usd == null ? t("ai_accounts.switch_check") : offer.usd < 0.005 ? t("ai_accounts.switch_check_cheap") : t("ai_accounts.switch_check_cost", { amount: money(offer.usd) });

  const actions: MenuAction[] = [
    ...(offeredUse
      ? [
          { id: "switch", label: t("ai_accounts.switch_without_check"), run: () => useForWork(false), disabled: busy },
          { id: "test", label: t("ai_accounts.test"), run: () => void test(), disabled: testing || busy },
        ]
      : takesWork
        ? [{ id: "use", label: t("ai_accounts.use_for_work"), run: () => useForWork(false), disabled: busy }]
        : []),
    { id: "key", label: t("ai_accounts.replace_key"), run: () => open("key") },
    { id: "expires", label: t("ai_accounts.key_ends_set"), run: () => open("expires") },
    { id: "models", label: t("ai_accounts.change_models"), run: () => open("models") },
    { id: "remove", label: t("ai_accounts.remove"), run: remove },
  ];

  const modelLabel = (short: string) =>
    short === EVERYDAY ? t("ai_accounts.model_everyday") : short === HARDER ? t("ai_accounts.model_harder") : t("ai_accounts.model_other", { short });
  const modelsChanged =
    harder.trim() !== "" || Object.entries(models).some(([short, id]) => id.trim() !== (account.models[short] ?? ""));
  const modelsBlank = Object.values(models).some((id) => id.trim() === "");
  const offeredModels = worksNow && modelsChanged && !modelsBlank && modelsOffer.data?.offered === true;
  const examplesId = `${base}-examples`;
  const resultText = result
    ? result.ok
      ? t("ai_accounts.test_ok")
      : result.detail
        ? t("ai_accounts.test_failed", { detail: result.detail })
        : t("ai_accounts.test_failed_plain")
    : "";

  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={`${base}-title`}>
      <div className="row pair">
        <div className="text">
          <strong id={`${base}-title`}>{account.name}</strong>
          {kind && kind.name !== account.name && <span className="sub">{t("ai_accounts.service", { service: kind.name })}</span>}
          <span className={missing ? "sub key-missing" : "sub"}>
            {missing ? <Icon name="alert" size={16} /> : <span aria-hidden="true">{keyState === "saved" ? "✓ " : "– "}</span>}
            {status}
          </span>
          <span className="sub">{doing}</span>
          {account.credential_expires && <span className="sub">{t("ai_accounts.key_ends", { date: day(account.credential_expires) })}</span>}
          {mode === "expires" && (
            <form
              className="field"
              onSubmit={(e) => {
                e.preventDefault();
                void saveEnds();
              }}
            >
              <label htmlFor={`${base}-ends`}>{t("ai_accounts.key_ends_label")}</label>
              <input id={`${base}-ends`} ref={firstField} type="date" value={ends} onChange={(e) => setEnds(e.target.value)} aria-describedby={`${base}-ends-hint`} />
              <p className="hint" id={`${base}-ends-hint`}>
                {t("ai_accounts.key_ends_hint")}
              </p>
              <div className="row-end">
                <button type="button" className="btn quiet" disabled={busy} onClick={close}>
                  {t("ai_accounts.cancel")}
                </button>
                <button type="submit" className="btn primary" disabled={busy || ends === (account.credential_expires ?? "")}>
                  {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
                </button>
              </div>
            </form>
          )}
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
              <label htmlFor={`${base}-key-ends`}>{t("ai_accounts.key_ends_label")}</label>
              <input id={`${base}-key-ends`} type="date" value={ends} onChange={(e) => setEnds(e.target.value)} />
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
                if (modelsChanged && !modelsBlank) void changeModels(offeredModels);
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
                {offeredModels && (
                  <button type="button" className="btn quiet" disabled={busy} onClick={() => void changeModels(false)}>
                    {t("ai_accounts.switch_without_check")}
                  </button>
                )}
                <button type="submit" className="btn primary" disabled={busy || !modelsChanged || modelsBlank}>
                  {busy ? t("ai_accounts.saving") : offeredModels ? checkLabel(modelsOffer.data) : t("ai_accounts.save")}
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
            {result && (
              <p className={result.ok ? "result-ok" : "result-bad"}>
                {resultText}
                <span aria-hidden="true">{result.ok ? " ✓" : " ✗"}</span>
              </p>
            )}
          </div>
        </div>
        <div className="acts">
          {offeredUse ? (
            <button
              type="button"
              className="btn primary"
              data-key="primary"
              ref={testButton}
              disabled={busy}
              aria-label={t("ai_accounts.switch_check_named", { name: account.name })}
              onClick={() => useForWork(true)}
            >
              {busy ? t("ai_accounts.saving") : checkLabel(useOffer.data)}
            </button>
          ) : (
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
          )}
          <RowMenu label={account.name} actions={actions} />
        </div>
      </div>
    </li>
  );
}
