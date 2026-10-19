// Which model does what (design 7.9), in Settings' AI section under the accounts: the model each kind of work uses, with
// what the tests measured for it and the cheapest model that passed them; the stronger model a failed answer is tried
// once more on; and the rules that send hard work to a stronger model first. Every choice is a list to pick from and is
// saved as it is made, with Undo. A suggestion from the measurements is only ever offered, never applied.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { accountName, type Account, type Kind } from "../lib/ai-accounts";
import {
  LEVELS,
  ROUTING_KEY,
  escalateKey,
  moved,
  rowOf,
  rulesOf,
  ruleProblem,
  taskKey,
  useRoutingSave,
  useTierName,
  type Fit,
  type RuleRow,
  type WorkKind,
} from "../lib/ai-routing";
import { useMoney, useSmallMoney } from "../lib/money";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { RowMenu } from "./RowMenu";
import styles from "./AiRouting.module.css";

type Routing = S["AiRoutingView"];

export function AiRouting() {
  const { t } = useWords();
  const view = useQuery({ queryKey: ["ai-routing"], queryFn: api.aiRouting });
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  // With no account there is nothing to choose between; the accounts list above says so.
  if (view.isPending || accounts.isPending || !accounts.data?.length) return null;
  if (view.isError) return <p className="hint">{t("ai_routing.load_failed")}</p>;
  return <Part view={view.data} accounts={accounts.data} kinds={endpoints.data ?? []} />;
}

function Part(props: { view: Routing; accounts: Account[]; kinds: Kind[] }) {
  const { t } = useWords();
  const tierName = useTierName();
  const money = useMoney();
  const { view } = props;
  /** A tier as a list shows it: its plain name and the account that does its work. */
  const model = (tier: string) => {
    const name = view.tiers.find((x) => x.name === tier)?.account;
    const account = props.accounts.find((a) => a.name === name);
    return account
      ? t("ai_routing.option", { work: tierName(tier), account: accountName(account, props.kinds.find((k) => k.id === account.kind), t) })
      : t("ai_routing.option_none", { work: tierName(tier) });
  };
  return (
    <section className={styles.part} aria-labelledby="ai-routing-title">
      <h3 id="ai-routing-title">{t("ai_routing.title")}</h3>
      <p className="hint">{t("ai_routing.intro")}</p>
      <Kinds view={view} model={model} />
      {view.tiers.length > 1 && <Escalation view={view} model={model} />}
      <Rules view={view} model={model} />
      <p className="hint" data-spending="">
        {t("ai_routing.spending", { amount: money(view.confirm_above_usd), limit: money(view.per_run_usd) })}
      </p>
    </section>
  );
}

const SKIP_WHY = ["no_accounts", "no_cases"];

function Kinds(props: { view: Routing; model: (tier: string) => string }) {
  const { t, has } = useWords();
  const save = useRoutingSave();
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const label = (k: WorkKind) => (has(`ai_routing.kind.${k.name}`) ? t(`ai_routing.kind.${k.name}`) : k.label);

  const choose = async (k: WorkKind, tier: string) => {
    if (tier === k.tier) return;
    setChosen((all) => ({ ...all, [k.name]: tier }));
    setProblems((all) => ({ ...all, [k.name]: "" }));
    // Choosing what the kind of work would use anyway puts it back, so the file holds no needless line.
    const back = k.custom && tier === k.default_tier;
    const done = await save(
      back ? { reset: [taskKey(k.name)] } : { changes: { [taskKey(k.name)]: tier } },
      t(back ? "ai_routing.kind_reset" : "ai_routing.kind_saved", { kind: label(k), model: props.model(tier) }),
    );
    setChosen(({ [k.name]: _gone, ...rest }) => rest);
    if (!done.ok) setProblems((all) => ({ ...all, [k.name]: done.problem }));
  };
  const reset = async (k: WorkKind) => {
    setProblems((all) => ({ ...all, [k.name]: "" }));
    const done = await save({ reset: [taskKey(k.name)] }, t("ai_routing.kind_reset", { kind: label(k), model: props.model(k.default_tier) }));
    if (!done.ok) setProblems((all) => ({ ...all, [k.name]: done.problem }));
  };

  return (
    <div className={styles.group} role="group" aria-labelledby="ai-routing-kinds">
      <h4 id="ai-routing-kinds">{t("ai_routing.kinds")}</h4>
      {props.view.kinds.map((k) => (
        <KindRow
          key={k.name}
          kind={k}
          label={label(k)}
          tiers={props.view.tiers}
          model={props.model}
          value={chosen[k.name] ?? k.tier}
          problem={problems[k.name]}
          onChoose={(tier) => void choose(k, tier)}
          onReset={() => void reset(k)}
          skipWhy={SKIP_WHY}
        />
      ))}
    </div>
  );
}

function KindRow(props: {
  kind: WorkKind;
  label: string;
  tiers: Routing["tiers"];
  model: (tier: string) => string;
  value: string;
  problem?: string;
  onChoose: (tier: string) => void;
  onReset: () => void;
  skipWhy: string[];
}) {
  const { t } = useWords();
  const id = useId();
  const { kind } = props;
  const locked = kind.source === "env" || kind.source === "flag";
  const suggested = kind.suggested_tier;
  return (
    <div className="setting beside" data-kind={kind.name}>
      <div className="setting-main">
        <div className="setting-head">
          <label className="setting-label" htmlFor={id}>
            {props.label}
          </label>
          {kind.custom && !locked && (
            <span className="setting-changed">
              <span>{t("settings.changed")}</span>
              <span aria-hidden="true"> · </span>
              <button type="button" className="link-button" aria-label={t("ai_routing.reset_named", { kind: props.label })} onClick={props.onReset}>
                {t("settings.reset")}
              </button>
            </span>
          )}
        </div>
        <select id={id} value={props.value} disabled={locked} onChange={(e) => props.onChoose(e.target.value)}>
          {props.tiers.map((x) => (
            <option key={x.name} value={x.name}>
              {props.model(x.name)}
            </option>
          ))}
        </select>
        {locked && <p className="hint">{t(kind.source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
        {props.problem && (
          <p className="problem-note" role="alert">
            {props.problem}
          </p>
        )}
      </div>
      <div className="setting-help">
        <Measured kind={kind} label={props.label} model={props.model} />
        {suggested && suggested !== kind.tier && (
          <p className={styles.suggest} data-suggestion="">
            <span>{t("ai_routing.suggest", { model: props.model(suggested) })}</span>
            <Button
              size="sm"
              disabled={locked}
              aria-label={t("ai_routing.suggest_use_named", { model: props.model(suggested), kind: props.label })}
              onClick={() => props.onChoose(suggested)}
            >
              {t("ai_routing.suggest_use")}
            </Button>
          </p>
        )}
        {suggested && suggested === kind.tier && <p className="hint">{t("ai_routing.suggest.same")}</p>}
        {!suggested && kind.suggestion_why_not && !props.skipWhy.includes(kind.suggestion_why_not) && (
          <p className="hint">{t(`ai_routing.suggest.why.${kind.suggestion_why_not}`)}</p>
        )}
      </div>
    </div>
  );
}

/** What was measured for a kind of work, for the model each tier uses: counts with their denominators, never a bare
 * percentage, and an out-of-date or missing result said as such. */
function Measured(props: { kind: WorkKind; label: string; model: (tier: string) => string }) {
  const { t } = useWords();
  const small = useSmallMoney();
  const fits = props.kind.fits;
  if (!fits.length) return null;
  if (fits.every((f) => f.skills === 0)) return <p className="hint">{t("ai_routing.fit.none")}</p>;
  const result = (f: Fit) => {
    const cost = f.cost_per_pass_usd == null || f.passes === 0 ? "" : t("ai_routing.fit.cost", { amount: small(f.cost_per_pass_usd) });
    const counts = { passes: f.passes, runs: f.runs, measured: f.measured, skills: f.skills };
    if (f.measured === 0) return t("ai_routing.fit.not_measured");
    if (f.status === "stale") return t("ai_routing.fit.stale", counts);
    if (f.measured < f.skills) return t("ai_routing.fit.partial", counts) + cost;
    return t(f.status === "below_min" ? "ai_routing.fit.below" : "ai_routing.fit.passes", counts) + cost;
  };
  return (
    <ul className={styles.fits} aria-label={t("ai_routing.fit.what", { kind: props.label })}>
      {fits.map((f) => (
        <li key={f.tier} className="hint" data-fit={f.tier} data-status={f.status}>
          {t("ai_routing.fit.line", { model: props.model(f.tier), result: result(f) })}
        </li>
      ))}
    </ul>
  );
}

function Escalation(props: { view: Routing; model: (tier: string) => string }) {
  const { t } = useWords();
  const tierName = useTierName();
  const save = useRoutingSave();
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const { view } = props;
  const change = async (tier: string, to: string) => {
    setChosen((all) => ({ ...all, [tier]: to }));
    setProblems((all) => ({ ...all, [tier]: "" }));
    // "Don't" is how a tier starts, so it is a reset.
    const done = await save(
      to ? { changes: { [escalateKey(tier)]: to } } : { reset: [escalateKey(tier)] },
      to ? t("ai_routing.escalate_saved", { work: tierName(tier), model: props.model(to) }) : t("ai_routing.escalate_off", { work: tierName(tier) }),
    );
    setChosen(({ [tier]: _gone, ...rest }) => rest);
    if (!done.ok) setProblems((all) => ({ ...all, [tier]: done.problem }));
  };
  return (
    <div className={styles.group} role="group" aria-labelledby="ai-routing-escalate">
      <h4 id="ai-routing-escalate">{t("ai_routing.escalate")}</h4>
      <p className="hint">{t("ai_routing.escalate_hint")}</p>
      {view.tiers.map((x) => (
        <EscalationRow
          key={x.name}
          tier={x}
          work={t("ai_routing.escalate_for", { work: props.model(x.name) })}
          others={view.tiers.filter((o) => o.name !== x.name)}
          model={props.model}
          value={chosen[x.name] ?? x.escalate_to ?? ""}
          problem={problems[x.name]}
          onChange={(to) => void change(x.name, to)}
        />
      ))}
    </div>
  );
}

function EscalationRow(props: {
  tier: Routing["tiers"][number];
  work: string;
  others: Routing["tiers"];
  model: (tier: string) => string;
  value: string;
  problem?: string;
  onChange: (to: string) => void;
}) {
  const { t } = useWords();
  const id = useId();
  const locked = props.tier.escalate_source === "env" || props.tier.escalate_source === "flag";
  return (
    <div className="setting" data-tier={props.tier.name}>
      <div className="setting-main">
        <label className="setting-label" htmlFor={id}>
          {props.work}
        </label>
        <select id={id} value={props.value} disabled={locked} onChange={(e) => props.onChange(e.target.value)}>
          <option value="">{t("ai_routing.escalate.never")}</option>
          {props.others.map((o) => (
            <option key={o.name} value={o.name}>
              {t("ai_routing.escalate.to", { model: props.model(o.name) })}
            </option>
          ))}
        </select>
        {locked && <p className="hint">{t(props.tier.escalate_source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
        {props.problem && (
          <p className="problem-note" role="alert">
            {props.problem}
          </p>
        )}
      </div>
    </div>
  );
}

function Rules(props: { view: Routing; model: (tier: string) => string }) {
  const { t, tn, has } = useWords();
  const save = useRoutingSave();
  const { view } = props;
  const served = view.rules.map(rowOf);
  // The rows being worked on; null while they are what is saved. A new rule, or one cleared of every condition, is held
  // here until it has one, since a rule with none would send everything.
  const [local, setLocal] = useState<RuleRow[] | null>(null);
  const rows = local ?? served;
  const [problem, setProblem] = useState("");
  const [focus, setFocus] = useState<number | null>(null);
  const add = useRef<HTMLButtonElement>(null);
  const base = useId();
  const locked = view.rules_source === "env" || view.rules_source === "flag";
  const kinds = view.kinds;
  const kindLabel = (name: string) => {
    const k = kinds.find((x) => x.name === name);
    return has(`ai_routing.kind.${name}`) ? t(`ai_routing.kind.${name}`) : (k?.label ?? name);
  };
  const stronger = view.tiers.find((x) => x.escalate_to)?.escalate_to ?? view.tiers[view.tiers.length - 1]?.name ?? "";

  useEffect(() => {
    if (focus === null) return;
    document.getElementById(`${base}-${focus}-task`)?.focus();
    setFocus(null);
  }, [focus, base]);

  const commit = async (next: RuleRow[]) => {
    const complete = next.every((r) => !ruleProblem(r));
    setProblem("");
    // A number that isn't one holds everything until it is put right; a rule that doesn't say when it applies is only
    // left out, since it would send everything.
    if (next.some((r) => ruleProblem(r) === "number")) {
      setLocal(next);
      return;
    }
    const rules = rulesOf(next);
    if (JSON.stringify(rules) === JSON.stringify(rulesOf(served))) {
      setLocal(complete ? null : next);
      return;
    }
    setLocal(next);
    const done = await save({ changes: { [ROUTING_KEY]: rules } }, tn("ai_routing.rules_saved", rules.length));
    if (!done.ok) {
      setProblem(done.problem);
      return;
    }
    // Everything on screen is saved now unless a row still waits for its conditions.
    if (complete) setLocal(null);
  };
  const edit = (index: number, part: Partial<RuleRow>, now = true) => {
    const next = rows.map((r, i) => (i === index ? { ...r, ...part } : r));
    if (now) void commit(next);
    else setLocal(next);
  };
  const addRule = (row: RuleRow) => {
    setLocal([...rows, row]);
    return rows.length;
  };

  const suggestions = view.rule_suggestions;
  return (
    <div className={styles.group} role="group" aria-labelledby="ai-routing-rules">
      <h4 id="ai-routing-rules">{t("ai_routing.rules")}</h4>
      <p className="hint">{t("ai_routing.rules_hint")}</p>
      {locked && <p className="hint">{t(view.rules_source === "env" ? "settings.locked_env" : "settings.locked_flag")}</p>}
      {rows.length === 0 && <p className="hint">{t("ai_routing.rules_none")}</p>}
      <ol className={styles.rules}>
        {rows.map((row, i) => {
          const wrong = ruleProblem(row);
          return (
            <li key={i}>
              <div className={styles.rule} role="group" aria-label={t("ai_routing.rule", { n: i + 1 })} data-rule={i}>
                <div className={styles.fields}>
                  <Field label={t("ai_routing.rule.task")} id={`${base}-${i}-task`}>
                    {(id) => (
                      <select id={id} value={row.task} disabled={locked} onChange={(e) => edit(i, { task: e.target.value })}>
                        <option value="">{t("ai_routing.rule.any_task")}</option>
                        {kinds.map((k) => (
                          <option key={k.name} value={k.name}>
                            {kindLabel(k.name)}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                  <Field label={t("ai_routing.rule.chars")}>
                    {(id) => (
                      <input
                        type="text"
                        inputMode="numeric"
                        id={id}
                        value={row.chars}
                        disabled={locked}
                        aria-invalid={wrong === "number" && row.chars.trim() !== "" && !/^\d+$/.test(row.chars.trim()) ? true : undefined}
                        onChange={(e) => edit(i, { chars: e.target.value }, false)}
                        onBlur={(e) => void commit(rows.map((r, j) => (j === i ? { ...r, chars: e.target.value } : r)))}
                        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void commit(rows))}
                      />
                    )}
                  </Field>
                  <Field label={t("ai_routing.rule.quotes")}>
                    {(id) => (
                      <input
                        type="text"
                        inputMode="numeric"
                        id={id}
                        value={row.quotes}
                        disabled={locked}
                        aria-invalid={wrong === "number" && row.quotes.trim() !== "" && !/^\d+$/.test(row.quotes.trim()) ? true : undefined}
                        onChange={(e) => edit(i, { quotes: e.target.value }, false)}
                        onBlur={(e) => void commit(rows.map((r, j) => (j === i ? { ...r, quotes: e.target.value } : r)))}
                        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void commit(rows))}
                      />
                    )}
                  </Field>
                  <Field label={t("ai_routing.rule.level")}>
                    {(id) => (
                      <select id={id} value={row.level} disabled={locked} onChange={(e) => edit(i, { level: e.target.value })}>
                        <option value="">{t("ai_routing.rule.any_level")}</option>
                        {LEVELS.map((l) => (
                          <option key={l} value={l}>
                            {t(`welcome.ai.data.${l}`)}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                  <Field label={t("ai_routing.rule.tier")}>
                    {(id) => (
                      <select id={id} value={row.tier} disabled={locked} onChange={(e) => edit(i, { tier: e.target.value })}>
                        {view.tiers.map((x) => (
                          <option key={x.name} value={x.name}>
                            {props.model(x.name)}
                          </option>
                        ))}
                      </select>
                    )}
                  </Field>
                </div>
                <RowMenu
                  label={t("ai_routing.rule", { n: i + 1 })}
                  actions={
                    locked
                      ? []
                      : [
                          { id: "up", label: t("ai_routing.rule.move_up"), disabled: i === 0, run: () => void commit(moved(rows, i, -1)) },
                          { id: "down", label: t("ai_routing.rule.move_down"), disabled: i === rows.length - 1, run: () => void commit(moved(rows, i, 1)) },
                          {
                            id: "remove",
                            label: t("ai_routing.rule.remove"),
                            run: () => {
                              void commit(rows.filter((_, j) => j !== i));
                              setTimeout(() => add.current?.focus(), 0);
                            },
                          },
                        ]
                  }
                />
                {wrong === "when" && <p className="hint">{t("ai_routing.rule.needs_when")}</p>}
                {wrong === "number" && <p className="problem-note">{t("ai_routing.rule.number")}</p>}
              </div>
            </li>
          );
        })}
      </ol>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      {suggestions.map((s) => (
        <p key={`${s.rule.task}-${s.rule.tier}`} className={styles.suggest} data-rule-suggestion="">
          <span>
            {t("ai_routing.rule_suggest", {
              kind: kindLabel(s.rule.task ?? ""),
              model: props.model(s.rule.tier),
              when: s.rule.quoted_messages_over != null
                ? t("ai_routing.rule_suggest.quotes", { n: s.rule.quoted_messages_over })
                : s.rule.input_chars_over != null
                  ? t("ai_routing.rule_suggest.chars", { n: s.rule.input_chars_over })
                  : "",
              skills: s.skills.join(", "),
            })}
          </span>
          <Button
            size="sm"
            disabled={locked}
            aria-label={t("ai_routing.rule_suggest_add_named", { kind: kindLabel(s.rule.task ?? ""), model: props.model(s.rule.tier) })}
            onClick={() => void commit([...rows, rowOf(s.rule)])}
          >
            {t("ai_routing.rule_suggest_add")}
          </Button>
        </p>
      ))}
      <div>
        <Button
          ref={add}
          disabled={locked || !stronger}
          onClick={() => setFocus(addRule({ task: "", chars: "", quotes: "", level: "", tier: stronger }))}
        >
          {t("ai_routing.rule_add")}
        </Button>
      </div>
    </div>
  );
}

/** A control with its label. */
function Field(props: { label: string; id?: string; children: (id: string) => ReactNode }) {
  const own = useId();
  const id = props.id ?? own;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className="setting-label">
        {props.label}
      </label>
      {props.children(id)}
    </div>
  );
}
