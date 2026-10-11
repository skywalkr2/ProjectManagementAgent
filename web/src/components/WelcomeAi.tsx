// The AI step of the setup guide (design 7.8): pick a kind of account from the product's catalog, fill in what that kind
// needs, add it, then test it. A pasted key is sent once and kept on this computer; the settings file only refers to it.
// What a kind needs is read from its catalog entry (an address, or a command for a command-line agent), never from its name.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { problemText } from "../lib/problem";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";

type Kind = S["EndpointView"];
type Level = "open" | "internal" | "restricted";

const LEVELS: Level[] = ["open", "internal", "restricted"];
const ACCOUNT_NAME = /^[a-z0-9][a-z0-9-]{0,40}$/;
const OTHER_KIND = "other";

/** A kind that has an address of its own, or is the one where the person types it; the rest are started by a command. */
const takesAddress = (kind: Kind) => kind.base_url !== "" || kind.id === OTHER_KIND;

export function WelcomeAi(props: { local: boolean; done: boolean }) {
  const { t } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [kindId, setKindId] = useState("");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [address, setAddress] = useState("");
  const [key, setKey] = useState("");
  const [keyRef, setKeyRef] = useState("");
  const [model, setModel] = useState("");
  const [levels, setLevels] = useState<Level[]>(["open"]);
  const [everyday, setEveryday] = useState(!props.done);
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

  const kind = endpoints.data?.find((e) => e.id === kindId);
  const agent = kind ? !takesAddress(kind) : false;
  const nameBad = name !== "" && !ACCOUNT_NAME.test(name);

  useEffect(() => {
    if (added) testButton.current?.focus();
  }, [added]);

  const choose = (id: string) => {
    const picked = endpoints.data?.find((e) => e.id === id);
    if (!picked) return;
    setKindId(id);
    setAddress(picked.base_url);
    if (!nameTouched) setName(picked.id);
    setProblem("");
  };

  const ready =
    !!kind &&
    ACCOUNT_NAME.test(name) &&
    model.trim() !== "" &&
    levels.length > 0 &&
    (agent ? command.trim() !== "" : !takesAddress(kind) || address.trim() !== "") &&
    !!settings.data &&
    !busy;

  const add = async () => {
    if (!kind || !settings.data) return;
    const body: S["AiAccountAdd"] = {
      name,
      adapter: kind.adapter,
      models: { main: model.trim() },
      allowed_data: levels,
      use_for: everyday ? ["routine", "deep"] : [],
      fingerprint: settings.data.fingerprint,
    };
    if (takesAddress(kind) && address.trim()) body.base_url = address.trim();
    if (agent) {
      body.agent = { command: command.trim().split(/\s+/), packet_via: packetVia, output_via: outputVia };
    } else if (key.trim()) {
      body.key = key.trim();
    } else if (keyRef.trim()) {
      body.key_ref = keyRef.trim();
    }
    setBusy(true);
    setProblem("");
    try {
      const saved = await api.addAccount(body);
      setKey("");
      setKeyRef("");
      setResults(null);
      setAdded(name);
      await afterSave(saved, { message: t("welcome.ai.added", { name }) });
    } catch (err) {
      // The typed values stay, so a correction is one edit away. A changed file means the form is out of date.
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
    } finally {
      setBusy(false);
    }
  };

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

  // One row per account and outcome: an account that does several kinds of work is not listed once for each.
  const rows = [
    ...new Map(
      (results ?? []).map((r) => {
        const text = r.ok ? t("welcome.ai.answered") : r.detail ? t("welcome.ai.failed", { detail: r.detail }) : t("welcome.ai.failed_plain");
        return [`${r.account}\n${text}`, { account: r.account, ok: r.ok, text }] as const;
      }),
    ).values(),
  ];

  return (
    <div className="guide-body">
      {endpoints.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : endpoints.isError || !endpoints.data?.length ? (
        <p className="empty">{t("welcome.ai.no_kinds")}</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) void add();
          }}
        >
          <fieldset className="details">
            <legend>{t("welcome.ai.kind")}</legend>
            <div className="kinds">
              {endpoints.data.map((e) => (
                <label key={e.id} className="radio kind-choice">
                  <input type="radio" name="ai-kind" value={e.id} checked={kindId === e.id} onChange={() => choose(e.id)} />
                  <span>
                    <strong>{e.name}</strong>
                    {e.note && <span className="hint block">{e.note}</span>}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {kind && (
            <>
              <div className="field">
                <label htmlFor="ai-name">{t("welcome.ai.name")}</label>
                <input
                  id="ai-name"
                  type="text"
                  value={name}
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
              {takesAddress(kind) && (
                <div className="field">
                  <label htmlFor="ai-address">{t("welcome.ai.address")}</label>
                  <input id="ai-address" type="text" value={address} autoComplete="off" onChange={(e) => setAddress(e.target.value)} />
                </div>
              )}
              {agent && (
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
              {!agent && (
                <>
                  {props.local && (
                    <div className="field">
                      <label htmlFor="ai-key">{t("welcome.ai.key")}</label>
                      <input
                        id="ai-key"
                        type="password"
                        value={key}
                        autoComplete="off"
                        disabled={keyRef.trim() !== ""}
                        aria-describedby="ai-key-hint"
                        onChange={(e) => setKey(e.target.value)}
                      />
                      <p className="hint" id="ai-key-hint">
                        {t("welcome.ai.key_hint")}
                      </p>
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="ai-key-ref">{t("welcome.ai.key_ref")}</label>
                    <input
                      id="ai-key-ref"
                      type="text"
                      value={keyRef}
                      autoComplete="off"
                      disabled={key.trim() !== ""}
                      aria-describedby="ai-key-ref-hint"
                      onChange={(e) => setKeyRef(e.target.value)}
                    />
                    <p className="hint" id="ai-key-ref-hint">
                      {t(props.local ? "welcome.ai.key_ref_hint" : "welcome.ai.key_ref_hosted")}
                    </p>
                  </div>
                </>
              )}
              <div className="field">
                <label htmlFor="ai-model">{t("welcome.ai.model")}</label>
                <input
                  id="ai-model"
                  type="text"
                  value={model}
                  autoComplete="off"
                  aria-describedby="ai-model-hint"
                  onChange={(e) => setModel(e.target.value)}
                />
                <p className="hint" id="ai-model-hint">
                  {t("welcome.ai.model_hint")}
                </p>
              </div>
              <fieldset className="details">
                <legend>{t("welcome.ai.data")}</legend>
                <div className="choice-row">
                  {LEVELS.map((level) => (
                    <label key={level} className="check-line">
                      <input
                        type="checkbox"
                        checked={levels.includes(level)}
                        onChange={(e) => setLevels(e.target.checked ? [...levels, level] : levels.filter((l) => l !== level))}
                      />
                      <span>{t(`welcome.ai.data.${level}`)}</span>
                    </label>
                  ))}
                </div>
                <p className="hint">{t("welcome.ai.data_hint")}</p>
              </fieldset>
              <label className="check-line">
                <input type="checkbox" checked={everyday} onChange={(e) => setEveryday(e.target.checked)} />
                <span>{t("welcome.ai.everyday")}</span>
              </label>
              {problem && (
                <p className="problem-note" role="alert">
                  {problem}
                </p>
              )}
              <div className="row-end">
                <button type="submit" className="btn primary" disabled={!ready}>
                  {t("welcome.ai.add")}
                </button>
              </div>
            </>
          )}
        </form>
      )}
      <div className="guide-test">
        <button type="button" className="btn" ref={testButton} disabled={testing} onClick={() => void test()}>
          {t("welcome.ai.test")}
        </button>
        <div role="status" aria-live="polite">
          {testing && <p className="hint">{t("welcome.ai.testing")}</p>}
          {results && rows.length === 0 && <p className="hint">{t("welcome.ai.test_none")}</p>}
          {rows.length > 0 && (
            <ul className="plain-list test-results">
              {rows.map((r) => (
                <li key={`${r.account}:${r.text}`}>
                  <strong>{r.account}</strong>
                  {": "}
                  <span className={r.ok ? "result-ok" : "result-bad"}>
                    <span aria-hidden="true">{r.ok ? "✓ " : "✗ "}</span>
                    {r.text}
                  </span>
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
