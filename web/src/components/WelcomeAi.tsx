// The AI step of the setup guide (design 7.8): pick a service by name, get a key from its page, paste it, pick a model from
// the list the service gives, choose what it may see, add it, then test it. A pasted key is sent once and kept on this
// computer; the settings file only refers to it. What a kind needs is read from its catalog entry (a key, an address, or a
// command for a command-line agent), never from its name.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useSmallMoney } from "../lib/money";
import { problemText } from "../lib/problem";
import { asReference } from "../lib/secret-ref";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { AiAccounts } from "./AiAccounts";
import { domainOf } from "./SafeText";
import { Skeleton } from "../ui/Skeleton";

type Kind = S["EndpointView"];
type ModelInfo = S["AiModelView"];
type Level = "open" | "internal" | "restricted";

const LEVELS: Level[] = ["open", "internal", "restricted"];
const ACCOUNT_NAME = /^[a-z0-9][a-z0-9-]{0,40}$/;
const OTHER_KIND = "other";
/** Past this many models the list can be narrowed by typing. */
const SEARCH_ABOVE = 15;
const HARDER_SAME = "";
/** The choice in a program's model list that lets the person type a model's name. */
const OTHER_MODEL = "\u0001other";

/** A kind that has an address of its own, or is the one where the person types it; the rest are started by a command. */
const takesAddress = (kind: Kind) => kind.base_url !== "" || kind.id === OTHER_KIND;
/** A kind where the person types the address. */
const asksAddress = (kind: Kind) => takesAddress(kind) && kind.base_url === "";
/** A service the person reaches with a key, shown as a large choice of its own. */
const isService = (kind: Kind) => kind.needs_key && kind.base_url !== "" && !kind.local;
/** A command-line program the app knows how to start: the person names no command. */
const isBuiltin = (kind: Kind) => (kind.program ?? "") !== "" && !takesAddress(kind);

/** The kind's id, or the id with -2, -3 … when an account of that name is already set up. */
function freeName(id: string, taken: Set<string>): string {
  if (!taken.has(id)) return id;
  let n = 2;
  while (taken.has(`${id}-${n}`)) n += 1;
  return `${id}-${n}`;
}

export function WelcomeAi(props: { local: boolean; done: boolean }) {
  const { t, tn, has } = useWords();
  const money = useSmallMoney();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  const found = useQuery({ queryKey: ["ai-local"], queryFn: api.aiLocal });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const [kindId, setKindId] = useState("");
  const [usingFound, setUsingFound] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [address, setAddress] = useState("");
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keyRef, setKeyRef] = useState("");
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [listProblem, setListProblem] = useState("");
  const [listing, setListing] = useState(false);
  const [filter, setFilter] = useState("");
  const [everyday, setEveryday] = useState("");
  const [harder, setHarder] = useState(HARDER_SAME);
  const [levels, setLevels] = useState<Level[]>(["open"]);
  const [useForWork, setUseForWork] = useState(!props.done);
  const [customModel, setCustomModel] = useState(false);
  const [command, setCommand] = useState("");
  const [packetVia, setPacketVia] = useState<"stdin" | "file">("stdin");
  const [outputVia, setOutputVia] = useState<"stdout" | "outbox">("stdout");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState<string | null>(null);
  const [results, setResults] = useState<S["AiTestResult"][] | null>(null);
  const [testProblem, setTestProblem] = useState("");
  const [testing, setTesting] = useState(false);
  const testButton = useRef<HTMLButtonElement>(null);
  const lookup = useRef(0);

  const kind = endpoints.data?.find((e) => e.id === kindId);
  const server = usingFound ? found.data?.find((s) => s.endpoint === kindId) : undefined;
  const agent = kind ? !takesAddress(kind) : false;
  // A program the app knows picks its command for itself; any other command-line agent asks for one.
  const builtin = !!kind && isBuiltin(kind);
  const generic = agent && !builtin;
  const examples = builtin ? (kind.model_examples ?? []) : [];
  const optional = builtin && !!kind.model_optional;
  // The program picks its own model when none is named and the person has not typed one.
  const programPicks = optional && !customModel && everyday.trim() === "";
  // A service's models can be listed when it has an address of its own or this app can reach a typed one.
  const canList = !!kind && !agent && !server && (kind.base_url !== "" || props.local);
  const hasKeyField = !!kind && !agent && !server && !kind.local && (kind.needs_key || asksAddress(kind));
  const taken = new Set([
    ...(settings.data?.items ?? []).flatMap((i) => (i.key.startsWith("ai.providers.") ? [i.key.split(".")[2]] : [])),
    ...(accounts.data ?? []).map((a) => a.name),
  ]);
  const accountName = nameTouched ? name : kind ? freeName(kind.id, taken) : "";
  const nameBad = accountName !== "" && !ACCOUNT_NAME.test(accountName);

  const list: ModelInfo[] = server ? server.models.map((id) => ({ id })) : (models ?? []);
  const asked = models !== null || listProblem !== "";
  const manualModel = builtin
    ? examples.length === 0 && !optional
    : generic || (!!kind && !server && (!canList || (asked && !listProblem && list.length === 0)));
  const showModels = !!kind && (agent || !!server || !canList || asked);
  const shown = filter.trim() ? list.filter((m) => m.id.toLowerCase().includes(filter.trim().toLowerCase())) : list;
  // Nothing in the list matches what was typed: there is no model to pick until the search changes.
  const noMatch = !manualModel && !builtin && list.length > 0 && shown.length === 0;

  /** Narrow the list; a chosen model that the search hides is replaced by the first one still shown. */
  const narrow = (text: string) => {
    setFilter(text);
    const wanted = text.trim().toLowerCase();
    const next = wanted ? list.filter((m) => m.id.toLowerCase().includes(wanted)) : list;
    if (next.length === 0) return;
    if (!next.some((m) => m.id === everyday)) setEveryday(next[0].id);
    if (harder !== HARDER_SAME && !next.some((m) => m.id === harder)) setHarder(next[0].id);
  };

  useEffect(() => {
    if (added) testButton.current?.focus();
  }, [added]);

  const keyArgs = (over?: { key?: string }) => {
    const pasted = (over?.key ?? key).trim();
    if (props.local && pasted) return { key: pasted };
    if (keyRef.trim()) return { key_ref: asReference(keyRef) };
    return {};
  };

  /** Ask the service for its models. A newer question, or a different choice, makes an older answer irrelevant. */
  const check = async (picked: Kind, over?: { key?: string; address?: string }) => {
    const mine = ++lookup.current;
    setListing(true);
    setListProblem("");
    const body: S["AiModelsAsk"] = { endpoint: picked.id, ...keyArgs(over) };
    if (asksAddress(picked)) body.base_url = (over?.address ?? address).trim();
    try {
      const answer = await api.aiModels(body);
      if (mine !== lookup.current) return;
      const got = answer.models ?? [];
      setModels(got);
      setListProblem(answer.problem ?? "");
      setFilter("");
      if (got.length) {
        setEveryday((cur) => (got.some((m) => m.id === cur) ? cur : got[0].id));
        setHarder((cur) => (got.some((m) => m.id === cur) ? cur : HARDER_SAME));
      }
    } catch (err) {
      if (mine !== lookup.current) return;
      setModels(null);
      setListProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      if (mine === lookup.current) setListing(false);
    }
  };

  const reset = (picked: Kind) => {
    lookup.current += 1;
    setKindId(picked.id);
    setAddress(picked.base_url);
    setKey("");
    setShowKey(false);
    setKeyRef("");
    setModels(null);
    setListProblem("");
    setListing(false);
    setFilter("");
    setEveryday(isBuiltin(picked) && !picked.model_optional ? (picked.model_examples ?? [])[0] ?? "" : "");
    setCustomModel(false);
    setHarder(HARDER_SAME);
    setLevels(picked.allowed_data?.length ? picked.allowed_data : ["open"]);
    setProblem("");
  };

  const choose = (id: string) => {
    const picked = endpoints.data?.find((e) => e.id === id);
    if (!picked) return;
    reset(picked);
    setUsingFound(false);
    if (!isService(picked) && !isBuiltin(picked)) setMoreOpen(true);
    // A service with an address and no key needs nothing more from the person: its models are listed at once.
    if (picked.base_url !== "" && !picked.needs_key) void check(picked, {});
  };

  const chooseFound = (endpoint: string) => {
    const picked = endpoints.data?.find((e) => e.id === endpoint);
    const running = found.data?.find((s) => s.endpoint === endpoint);
    if (!picked || !running) return;
    reset(picked);
    setUsingFound(true);
    setEveryday(running.models[0] ?? "");
  };

  /** Enter in a key field runs Check, as pressing the button does; it never adds the account. */
  const enterChecks = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (kind && canCheck) void check(kind);
  };

  const keyReady = !kind?.needs_key || !!server || key.trim() !== "" || keyRef.trim() !== "";
  const canCheck =
    canList && !listing && keyReady && (!kind || !asksAddress(kind) || address.trim() !== "");

  const ready =
    !!kind &&
    ACCOUNT_NAME.test(accountName) &&
    (programPicks || everyday.trim() !== "") &&
    !noMatch &&
    levels.length > 0 &&
    (generic ? command.trim() !== "" : builtin || !takesAddress(kind) || address.trim() !== "") &&
    (agent || keyReady) &&
    !!settings.data &&
    !busy;

  const test = async () => {
    setTesting(true);
    setTestProblem("");
    setResults(null);
    try {
      setResults(await api.testAi());
      void client.invalidateQueries();
    } catch (err) {
      setTestProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setTesting(false);
    }
  };

  const add = async () => {
    if (!kind || !settings.data) return;
    const second = !agent && harder !== HARDER_SAME && harder !== everyday ? harder : "";
    const body: S["AiAccountAdd"] = {
      name: accountName,
      adapter: kind.adapter,
      endpoint: kind.id,
      models: programPicks ? {} : second ? { everyday: everyday.trim(), harder: second } : { everyday: everyday.trim() },
      allowed_data: levels,
      fingerprint: settings.data.fingerprint,
    };
    // With no model named there is no short name to point at, so the account's own first model does the work.
    if (useForWork) {
      if (programPicks) body.use_for = ["routine", "deep"];
      else body.use = { routine: "everyday", deep: second ? "harder" : "everyday" };
    }
    if (takesAddress(kind) && address.trim()) body.base_url = address.trim();
    if (generic) {
      body.agent = { command: command.trim().split(/\s+/), packet_via: packetVia, output_via: outputVia };
    } else if (!agent) {
      Object.assign(body, keyArgs());
    }
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.addAccount(body);
      setKey("");
      setKeyRef("");
      setResults(null);
      setAdded(accountName);
      // The next suggested name looks at the accounts as they are now, so a second account of this kind gets -2.
      setName("");
      setNameTouched(false);
      await afterSave(saved, { message: t("welcome.ai.added", { name: accountName }) });
      await client.invalidateQueries({ queryKey: ["ai-accounts"] });
      void test();
    } catch (err) {
      // The typed values stay, so a correction is one edit away. A changed file means the form is out of date.
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

  // One line per kind of work: the work, the account that does it, and whether it answered, in words and a mark.
  const rows = (results ?? []).map((r) => {
    const outcome = r.ok ? t("welcome.ai.answered") : r.detail ? t("welcome.ai.failed", { detail: r.detail }) : t("welcome.ai.failed_plain");
    const work = has(`welcome.ai.tier.${r.tier}`) ? t(`welcome.ai.tier.${r.tier}`) : r.tier;
    const text = t(r.main ? "welcome.ai.result" : "welcome.ai.result_backup", { work, account: r.account, outcome });
    return { key: `${r.tier}:${r.account}:${r.main}`, ok: r.ok, text };
  });
  const canTest = !!added || props.done;

  const all = endpoints.data ?? [];
  const foundIds = new Set((found.data ?? []).map((s) => s.endpoint));
  const services = all.filter((k) => isService(k));
  const apps = all.filter((k) => isBuiltin(k) && !foundIds.has(k.id));
  const others = all.filter((k) => !isService(k) && !isBuiltin(k) && !foundIds.has(k.id));
  // The command-line agent that needs a command typed comes last.
  const more = [...others.filter((k) => takesAddress(k)), ...others.filter((k) => !takesAddress(k))];

  const kindChoice = (e: Kind) => (
    <label key={e.id} className="radio kind-choice kind-card">
      <input type="radio" name="ai-kind" value={e.id} checked={kindId === e.id && !usingFound} onChange={() => choose(e.id)} />
      <span>
        <strong>{e.name}</strong>
        {e.note && <span className="hint block">{e.note}</span>}
      </span>
    </label>
  );

  const keyDomain = kind?.key_url ? domainOf(kind.key_url) : null;

  /** What a model costs and how much it takes in, in the words the sheet gives. */
  const modelNote = (id: string) => {
    const info = list.find((m) => m.id === id);
    if (!info) return "";
    const parts: string[] = [];
    if (info.context_tokens) parts.push(t("welcome.ai.model_context", { n: info.context_tokens.toLocaleString("en-US") }));
    const read = info.input_per_million;
    const write = info.output_per_million;
    if (read != null && write != null) parts.push(t("welcome.ai.model_price_both", { read: money(read), write: money(write) }));
    else if (read != null) parts.push(t("welcome.ai.model_price_read", { read: money(read) }));
    else if (write != null) parts.push(t("welcome.ai.model_price_write", { write: money(write) }));
    return parts.join(" ");
  };

  const modelSelect = (props2: { id: string; label: string; value: string; onChange: (v: string) => void; same?: boolean }) => {
    const options = shown;
    const note = props2.value === HARDER_SAME ? "" : modelNote(props2.value);
    return (
      <div className="field">
        <label htmlFor={props2.id}>{props2.label}</label>
        <select
          id={props2.id}
          value={props2.value}
          aria-describedby={note ? `${props2.id}-note` : undefined}
          onChange={(e) => props2.onChange(e.target.value)}
        >
          {props2.same && <option value={HARDER_SAME}>{t("welcome.ai.model_same")}</option>}
          {options.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}
            </option>
          ))}
        </select>
        {note && (
          <p className="hint" id={`${props2.id}-note`}>
            {note}
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="guide-body">
      {endpoints.isPending ? (
        <Skeleton />
      ) : endpoints.isError || !endpoints.data?.length ? (
        <p className="empty">{t("welcome.ai.no_kinds")}</p>
      ) : (
        <form
          onSubmit={(e) => {
            // Enter in a field never adds the account: only the Add button does.
            e.preventDefault();
          }}
        >
          <fieldset className="details">
            <legend>{t("welcome.ai.kind")}</legend>
            {(found.data ?? []).map((s) => {
              const chosen = usingFound && kindId === s.endpoint;
              return (
                <div key={s.endpoint} className="found-local" data-chosen={chosen ? "true" : undefined}>
                  <p id={`ai-found-${s.endpoint}`}>{tn("welcome.ai.local_found", s.models.length, { name: s.name })}</p>
                  <div className="inline-field">
                    <button
                      type="button"
                      className="btn primary"
                      aria-pressed={chosen}
                      aria-describedby={`ai-found-${s.endpoint}`}
                      onClick={() => chooseFound(s.endpoint)}
                    >
                      {t("welcome.ai.local_use")}
                    </button>
                    {chosen && (
                      <span className="pill">
                        <span aria-hidden="true">✓ </span>
                        {t("welcome.ai.chosen")}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
            <div className="kinds kind-grid">{services.map(kindChoice)}</div>
            {apps.length > 0 && (
              <div role="group" className="kind-group" aria-labelledby="ai-apps-title">
                <h4 id="ai-apps-title">{t("welcome.ai.apps")}</h4>
                <div className="kinds kind-grid">{apps.map(kindChoice)}</div>
              </div>
            )}
            {more.length > 0 && (
              <details
                className="more-options"
                open={moreOpen}
                onToggle={(e) => setMoreOpen((e.currentTarget as HTMLDetailsElement).open)}
              >
                <summary>{t("welcome.ai.more")}</summary>
                <div className="kinds">{more.map(kindChoice)}</div>
              </details>
            )}
          </fieldset>
          {kind && (
            <>
              {kind && asksAddress(kind) && (
                <div className="field">
                  <label htmlFor="ai-address">{t("welcome.ai.address")}</label>
                  <input
                    id="ai-address"
                    type="text"
                    value={address}
                    autoComplete="off"
                    aria-describedby="ai-address-hint"
                    onChange={(e) => setAddress(e.target.value)}
                  />
                  <p className="hint" id="ai-address-hint">
                    {t("welcome.ai.address_hint")}
                  </p>
                </div>
              )}
              {builtin && kind.installed != null && (
                <div className="check-row">
                  <p className="hint" id="ai-app-status" role="status">
                    <span aria-hidden="true">{kind.installed ? "✓ " : "✗ "}</span>
                    {endpoints.isFetching ? t("welcome.ai.app_checking") : t(kind.installed ? "welcome.ai.app_installed" : "welcome.ai.app_missing")}
                  </p>
                  <button
                    type="button"
                    className="btn"
                    disabled={endpoints.isFetching}
                    aria-describedby="ai-app-status"
                    onClick={() => void endpoints.refetch()}
                  >
                    {t("welcome.ai.check")}
                  </button>
                </div>
              )}
              {generic && (
                <>
                  <div className="field">
                    <label htmlFor="ai-command">{t("welcome.ai.command")}</label>
                    <input
                      id="ai-command"
                      type="text"
                      value={command}
                      autoComplete="off"
                      aria-describedby="ai-command-hint"
                      onChange={(e) => setCommand(e.target.value)}
                    />
                    <p className="hint" id="ai-command-hint">
                      {t("welcome.ai.command_hint")}
                    </p>
                  </div>
                  <fieldset className="details">
                    <legend>{t("welcome.ai.packet_via")}</legend>
                    <div className="choice-row">
                      {(["stdin", "file"] as const).map((v) => (
                        <label key={v} className="check-line">
                          <input type="radio" name="ai-packet-via" checked={packetVia === v} onChange={() => setPacketVia(v)} />
                          <span>{t(`welcome.ai.packet_via.${v}`)}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <fieldset className="details">
                    <legend>{t("welcome.ai.output_via")}</legend>
                    <div className="choice-row">
                      {(["stdout", "outbox"] as const).map((v) => (
                        <label key={v} className="check-line">
                          <input type="radio" name="ai-output-via" checked={outputVia === v} onChange={() => setOutputVia(v)} />
                          <span>{t(`welcome.ai.output_via.${v}`)}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                </>
              )}
              {hasKeyField && (
                <section className="key-step" aria-labelledby="ai-key-steps">
                  {kind.needs_key && (
                    <>
                      <h4 id="ai-key-steps">{t("welcome.ai.key_steps")}</h4>
                      <ol className="plain-list key-steps">
                        <li>
                          {keyDomain ? (
                            <a href={kind.key_url} target="_blank" rel="noopener noreferrer">
                              {t("welcome.ai.key_open", { domain: keyDomain })}
                            </a>
                          ) : (
                            t("welcome.ai.key_make")
                          )}
                        </li>
                        <li>{t(props.local ? "welcome.ai.key_paste" : "welcome.ai.key_paste_hosted")}</li>
                      </ol>
                    </>
                  )}
                  {props.local ? (
                    <div className="field">
                      <label htmlFor="ai-key">{t("welcome.ai.key")}</label>
                      <div className="inline-field">
                        <input
                          id="ai-key"
                          type={showKey ? "text" : "password"}
                          value={key}
                          autoComplete="off"
                          spellCheck={false}
                          disabled={keyRef.trim() !== ""}
                          aria-describedby="ai-key-hint"
                          onKeyDown={enterChecks}
                          onChange={(e) => setKey(e.target.value)}
                          onPaste={(e) => {
                            // A key pasted into an empty field is checked at once; typing waits for Check.
                            const pasted = e.clipboardData.getData("text").trim();
                            if (key === "" && pasted && canList && (!asksAddress(kind) || address.trim() !== "")) void check(kind, { key: pasted });
                          }}
                        />
                        <button
                          type="button"
                          className="btn small"
                          aria-controls="ai-key"
                          onClick={() => setShowKey((v) => !v)}
                        >
                          {t(showKey ? "welcome.ai.key_hide" : "welcome.ai.key_show")}
                        </button>
                      </div>
                      <p className="hint" id="ai-key-hint">
                        {t("welcome.ai.key_hint")} {!kind.needs_key && t("welcome.ai.key_optional")}
                      </p>
                    </div>
                  ) : (
                    <div className="field">
                      <label htmlFor="ai-key-where">{t("welcome.ai.key_where")}</label>
                      <input
                        id="ai-key-where"
                        type="text"
                        value={keyRef}
                        autoComplete="off"
                        placeholder="env:NAME"
                        aria-describedby="ai-key-where-hint"
                        onKeyDown={enterChecks}
                        onChange={(e) => setKeyRef(e.target.value)}
                      />
                      <p className="hint" id="ai-key-where-hint">
                        {t("welcome.ai.key_where_hint")}
                      </p>
                    </div>
                  )}
                </section>
              )}
              {canList && (
                <div className="check-row">
                  <button type="button" className="btn" disabled={!canCheck} onClick={() => void check(kind)}>
                    {t("welcome.ai.check")}
                  </button>
                  <div role="status" aria-live="polite">
                    {listing && <p className="hint">{t("welcome.ai.checking")}</p>}
                  </div>
                  {listProblem && (
                    <p className="problem-note" role="alert">
                      {listProblem}
                    </p>
                  )}
                </div>
              )}
              {showModels && (
                <>
                  {manualModel ? (
                    <div className="field">
                      <label htmlFor="ai-model">{t("welcome.ai.model")}</label>
                      <input
                        id="ai-model"
                        type="text"
                        value={everyday}
                        autoComplete="off"
                        aria-describedby="ai-model-hint"
                        onChange={(e) => setEveryday(e.target.value)}
                      />
                      <p className="hint" id="ai-model-hint">
                        {t(agent ? "welcome.ai.model_agent_hint" : "welcome.ai.model_hint")}
                      </p>
                    </div>
                  ) : builtin && optional && examples.length === 0 ? (
                    // The program's command names no model, so a name typed here would never reach it.
                    <p className="hint">{t("welcome.ai.model_program_picks_hint")}</p>
                  ) : builtin ? (
                    <>
                      <div className="field">
                        <label htmlFor="ai-model">{t("welcome.ai.model_choice")}</label>
                        <select
                          id="ai-model"
                          value={customModel ? OTHER_MODEL : everyday}
                          onChange={(e) => {
                            const other = e.target.value === OTHER_MODEL;
                            setCustomModel(other);
                            setEveryday(other ? "" : e.target.value);
                          }}
                        >
                          {optional && <option value="">{t("welcome.ai.model_program_picks")}</option>}
                          {examples.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                          <option value={OTHER_MODEL}>{t("welcome.ai.model_other")}</option>
                        </select>
                      </div>
                      {customModel && (
                        <div className="field">
                          <label htmlFor="ai-model-custom">{t("welcome.ai.model")}</label>
                          <input
                            id="ai-model-custom"
                            type="text"
                            value={everyday}
                            autoComplete="off"
                            aria-describedby="ai-model-custom-hint"
                            onChange={(e) => setEveryday(e.target.value)}
                          />
                          <p className="hint" id="ai-model-custom-hint">
                            {t("welcome.ai.model_agent_hint")}
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    list.length > 0 && (
                      <>
                        {list.length > SEARCH_ABOVE && (
                          <div className="field">
                            <label htmlFor="ai-model-find">{t("welcome.ai.model_find")}</label>
                            <input
                              id="ai-model-find"
                              type="search"
                              value={filter}
                              autoComplete="off"
                              onChange={(e) => narrow(e.target.value)}
                            />
                            {noMatch && (
                              <p className="hint" role="status">
                                {t("welcome.ai.model_none")}
                              </p>
                            )}
                          </div>
                        )}
                        {!noMatch &&
                          modelSelect({ id: "ai-model", label: t("welcome.ai.model_everyday"), value: everyday, onChange: setEveryday })}
                        {!noMatch &&
                          modelSelect({
                            id: "ai-model-harder",
                            label: t("welcome.ai.model_harder"),
                            value: harder,
                            onChange: setHarder,
                            same: true,
                          })}
                      </>
                    )
                  )}
                </>
              )}
              <fieldset className="details">
                <legend>{t("welcome.ai.data")}</legend>
                <div className="choice-row level-list">
                  {LEVELS.map((level) => (
                    <div key={level} className="level">
                      <label className="check-line">
                        <input
                          type="checkbox"
                          checked={levels.includes(level)}
                          aria-describedby={`ai-level-${level}`}
                          onChange={(e) => setLevels(e.target.checked ? [...levels, level] : levels.filter((l) => l !== level))}
                        />
                        <span>{t(`welcome.ai.data.${level}`)}</span>
                      </label>
                      <p className="hint level-hint" id={`ai-level-${level}`}>
                        {t(`welcome.ai.data.${level}_hint`)}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="hint">{t("welcome.ai.data_hint")}</p>
              </fieldset>
              <label className="check-line">
                <input type="checkbox" checked={useForWork} onChange={(e) => setUseForWork(e.target.checked)} />
                <span>{t("welcome.ai.everyday")}</span>
              </label>
              <details className="more-options advanced">
                <summary>{t("welcome.ai.advanced")}</summary>
                <div className="field">
                  <label htmlFor="ai-name">{t("welcome.ai.name")}</label>
                  <input
                    id="ai-name"
                    type="text"
                    value={accountName}
                    autoComplete="off"
                    aria-invalid={nameBad ? true : undefined}
                    aria-describedby="ai-name-hint"
                    onChange={(e) => {
                      setName(e.target.value);
                      setNameTouched(true);
                    }}
                  />
                  <p className={nameBad ? "problem-note" : "hint"} id="ai-name-hint">
                    {t("welcome.ai.name_hint")}
                  </p>
                </div>
                {takesAddress(kind) && !asksAddress(kind) && (
                  <div className="field">
                    <label htmlFor="ai-address-fixed">{t("welcome.ai.address")}</label>
                    <input id="ai-address-fixed" type="text" value={kind.base_url} readOnly />
                  </div>
                )}
                {!agent && (props.local || !hasKeyField) && (
                  <div className="field">
                    <label htmlFor="ai-key-ref">{t("welcome.ai.key_ref")}</label>
                    <input
                      id="ai-key-ref"
                      type="text"
                      value={keyRef}
                      autoComplete="off"
                      disabled={key.trim() !== ""}
                      aria-describedby="ai-key-ref-hint"
                      onKeyDown={enterChecks}
                      onChange={(e) => setKeyRef(e.target.value)}
                    />
                    <p className="hint" id="ai-key-ref-hint">
                      {t(props.local ? "welcome.ai.key_ref_hint" : "welcome.ai.key_where_hint")}
                    </p>
                  </div>
                )}
              </details>
              {problem && (
                <p className="problem-note" role="alert">
                  {problem}
                </p>
              )}
              <div className="row-end">
                <button type="button" className="btn primary" disabled={!ready} onClick={() => void add()}>
                  {t(busy ? "welcome.ai.adding" : "welcome.ai.add")}
                </button>
              </div>
            </>
          )}
        </form>
      )}
      <AiAccounts local={props.local} level={4} />
      <div className="guide-test">
        {canTest && (
          <button type="button" className="btn" ref={testButton} disabled={testing} onClick={() => void test()}>
            {t(added || results ? "welcome.ai.test_again" : "welcome.ai.test")}
          </button>
        )}
        <div role="status" aria-live="polite">
          {testing && <p className="hint">{t("welcome.ai.testing")}</p>}
          {results && rows.length === 0 && <p className="hint">{t("welcome.ai.test_none")}</p>}
          {rows.length > 0 && (
            <ul className="plain-list test-results">
              {rows.map((r) => (
                <li key={r.key} className={r.ok ? "result-ok" : "result-bad"}>
                  {r.text}
                  <span aria-hidden="true">{r.ok ? " ✓" : " ✗"}</span>
                </li>
              ))}
            </ul>
          )}
          {testProblem && <p className="problem-note">{testProblem}</p>}
        </div>
      </div>
    </div>
  );
}
