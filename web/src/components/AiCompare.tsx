// What each AI account can do (design 6.16, 7.16), as one grid on its own page: kinds of work down the side, one column for
// each account and model. Pass rate comes first, because a cheap wrong answer costs the person a correction; the cost of a
// right answer only matters among the models that pass, and the cheapest of those in each row is marked, which is the one
// the assistant would choose. A rate under the minimum has an icon and words, an old measurement counts as unknown, and a
// model nobody measured offers Measure with its price first, asking before a cost above the amount the person set. It
// shows the account's own name and the short model name the person chose, never the model's own name.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { accountName, orderAccounts } from "../lib/ai-accounts";
import { bestOf, cellState, gridOf, type Column, type SkillCell } from "../lib/ai-compare";
import { useMoney } from "../lib/money";
import { problemText } from "../lib/problem";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { LoadFailed } from "../ui/LoadFailed";
import { Skeleton } from "../ui/Skeleton";
import styles from "./AiCompare.module.css";

const percent = (share: number) => Math.round(share * 100);

export function AiCompare(props: { onBack: () => void }) {
  const { t, tn } = useWords();
  const money = useMoney();
  const client = useQueryClient();
  const { push } = useToasts();
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  // While a measuring the person asked for runs, the grid looks again now and then, so it fills in as the numbers arrive.
  const skills = useQuery({
    queryKey: ["ai-skills"],
    queryFn: api.aiSkills,
    refetchInterval: (query) =>
      query.state.data?.accounts.some((a) => a.models.some((m) => m.measure === "waiting" || m.measure === "measuring")) ? 3000 : false,
  });
  // Which column asked for a go above the amount the person set, and the header's own.
  const [asking, setAsking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  const real = (accounts.data ?? []).filter((a) => a.adapter !== "stub");
  const ordered = orderAccounts(real);
  const nameOf = (account: string) => {
    const a = real.find((x) => x.name === account);
    return a ? accountName(a, endpoints.data?.find((e) => e.id === a.kind), t) : account;
  };
  const grid = skills.data ? gridOf(ordered.map((a) => a.name), skills.data.accounts) : { columns: [] as Column[], rows: [] };
  const columnKey = (c: Column) => `${c.account}/${c.model}`;
  const modelWords = (short: string) =>
    short === "everyday" ? t("ai_compare.model.everyday") : short === "harder" ? t("ai_compare.model.harder") : t("ai_compare.model.other", { short });
  const headOf = (c: Column) => t("ai_compare.column", { name: nameOf(c.account), model: modelWords(c.model) });

  // What measuring each account would cost, for "Measure again", and each model that has something unmeasured, for its cells.
  const wantsMeasure = (c: Column) => grid.rows.some((r) => ["none", "old"].includes(cellState(c.skills.find((s) => s.id === r.id))));
  const columnCost = useQueries({
    queries: grid.columns.map((c) => ({
      queryKey: ["ai-measure-estimate", c.account, c.model],
      queryFn: () => api.measureEstimate(c.account, c.model),
      enabled: wantsMeasure(c),
      retry: false,
      staleTime: 60_000,
    })),
  });
  const accountNames = ordered.map((a) => a.name);
  // Whether any kind of work has a result yet; until one has, the page says nothing is measured rather than showing a grid of blanks.
  const anyResult = grid.columns.some((c) => c.skills.some((s) => ["pass", "below", "old"].includes(cellState(s))));
  const accountCost = useQueries({
    queries: accountNames.map((name) => ({
      queryKey: ["ai-measure-estimate", name, "all"],
      queryFn: () => api.measureEstimate(name),
      retry: false,
      staleTime: 60_000,
    })),
  });
  const costOf = (c: Column) => columnCost[grid.columns.indexOf(c)]?.data;
  const total = accountCost.every((q) => q.data) && accountCost.length > 0 ? accountCost.reduce((sum, q) => (sum === null || q.data?.usd == null ? null : sum + q.data.usd), 0 as number | null) : null;
  const limit = accountCost.find((q) => q.data)?.data?.confirm_above_usd ?? 0;
  const allNeedGo = accountCost.some((q) => q.data?.needs_go) || (total != null && total > limit);

  const run = async (account: string, body: S["AiMeasureIn"]) => {
    setProblem("");
    try {
      const started = await api.measure(account, body);
      await client.invalidateQueries({ queryKey: ["ai-skills"] });
      push({ message: started.started.length ? t("ai_compare.started") : t("ai_compare.nothing") });
      return true;
    } catch (err) {
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return false;
    }
  };
  const measureColumn = async (c: Column, confirmed: boolean) => {
    const estimate = costOf(c);
    if (estimate?.needs_go && !confirmed) {
      setAsking(columnKey(c));
      return;
    }
    setAsking(null);
    await run(c.account, { model: c.model, confirmed: !!estimate?.needs_go });
  };
  const measureAll = async (confirmed: boolean) => {
    if (allNeedGo && !confirmed) {
      setAsking("*");
      return;
    }
    setAsking(null);
    for (const name of accountNames) await run(name, { confirmed: allNeedGo });
  };

  const when = (days: number) => (days <= 0 ? t("ai_skills.age_today") : days === 1 ? t("ai_skills.age_yesterday") : t("ai_skills.age_days", { days }));

  const cell = (c: Column, skill: SkillCell | undefined, best: boolean, only: boolean) => {
    const state = cellState(skill);
    const estimate = costOf(c);
    const key = columnKey(c);
    const measuring = c.measure === "waiting" || c.measure === "measuring";
    const detail = skill
      ? [
          skill.cost_per_pass_usd != null && skill.cost_per_pass_usd > 0 ? t("ai_compare.cost", { amount: money(skill.cost_per_pass_usd) }) : "",
          skill.runs > 0 ? tn("ai_compare.runs", skill.runs) : "",
          when(skill.age_days ?? 0) + (state === "old" ? ` ${t("ai_compare.old")}` : ""),
        ]
          .filter(Boolean)
          .join(" · ")
      : "";
    const measureButton =
      state === "pass" || state === "below" ? null : measuring ? (
        <p className={styles.small}>{t(c.measure === "waiting" ? "ai_compare.waiting" : "ai_compare.measuring")}</p>
      ) : asking === key ? (
        <>
          <p className={styles.confirm} role="alert">
            {t("ai_compare.confirm", { amount: money(estimate?.usd ?? 0), limit: money(estimate?.confirm_above_usd ?? 0) })}
          </p>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" onClick={() => void measureColumn(c, true)}>
              {t("ai_compare.confirm_go")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(null)}>
              {t("ai_compare.confirm_cancel")}
            </Button>
          </div>
        </>
      ) : (
        <div className={styles.actions}>
          <Button size="sm" aria-label={t("ai_compare.measure_named", { name: nameOf(c.account), model: modelWords(c.model) })} onClick={() => void measureColumn(c, false)}>
            {estimate?.usd == null ? t("ai_compare.measure") : t("ai_compare.measure_cost", { amount: money(estimate.usd) })}
          </Button>
        </div>
      );
    return (
      <td key={key} className={best ? styles.best : undefined}>
        <div className={styles.cell}>
          {state === "none" ? (
            <p className={styles.value} data-state="none">
              <span aria-hidden="true">— </span>
              {t("ai_compare.not_measured")}
            </p>
          ) : (
            <p className={styles.value} data-state={state}>
              {state === "below" && <Icon name="alert" size={16} />}
              {percent(skill?.pass_rate ?? 0)}%
            </p>
          )}
          {state !== "none" && <p className={styles.small}>{state === "below" ? `${t("ai_compare.below", { percent: percent(skills.data?.min_score ?? 0) })} · ${detail}` : detail}</p>}
          {state === "old" && <p className={styles.small}>{t("ai_compare.counts_unknown")}</p>}
          {c.measure === "failed" && state !== "pass" && state !== "below" && (
            <p className={styles.small} role="status">
              {t("ai_compare.failed", { why: c.measure_why ?? "" })}
            </p>
          )}
          {best && (
            <p className={styles.mark}>
              <span aria-hidden="true">✓ </span>
              {t(only ? "ai_compare.only" : "ai_compare.cheapest")}
            </p>
          )}
          {measureButton}
        </div>
      </td>
    );
  };

  const header = (
    <>
      <div className="heading">
        <h1 id="ai-compare-title">{t("ai_compare.title")}</h1>
        {accountNames.length > 0 && (
          <div className={styles.actions}>
            <Button variant={anyResult ? "secondary" : "primary"} onClick={() => void measureAll(false)}>
              {anyResult
                ? total == null
                  ? t("ai_compare.measure_all")
                  : t("ai_compare.measure_all_cost", { amount: money(total) })
                : total == null
                  ? t("ai_compare.measure")
                  : t("ai_compare.measure_cost", { amount: money(total) })}
            </Button>
          </div>
        )}
      </div>
      <p className={styles.back}>
        <Button size="sm" variant="ghost" onClick={props.onBack}>
          {t("ai_compare.back")}
        </Button>
      </p>
      {skills.data && <p className={styles.sub}>{t("ai_compare.sub", { percent: percent(skills.data.min_score) })}</p>}
      {asking === "*" && (
        <div role="alert">
          <p className={styles.confirm}>{t("ai_compare.confirm", { amount: money(total ?? 0), limit: money(limit) })}</p>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" onClick={() => void measureAll(true)}>
              {t("ai_compare.confirm_go")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(null)}>
              {t("ai_compare.confirm_cancel")}
            </Button>
          </div>
        </div>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
    </>
  );

  return (
    <section className="panel-section" aria-labelledby="ai-compare-title">
      {header}
      {accounts.isError || skills.isError ? (
        <LoadFailed message={t("ai_compare.load_failed")} onRetry={() => void skills.refetch()} />
      ) : !skills.data || !accounts.data ? (
        <Skeleton />
      ) : accountNames.length === 0 ? (
        <p className={styles.empty}>{t("ai_compare.empty")}</p>
      ) : !anyResult ? (
        <p className={styles.empty} data-nothing-measured="">
          {t("ai_compare.nothing_measured")}
        </p>
      ) : (
        <div className={styles.scroll} role="region" aria-label={t("ai_compare.title")} tabIndex={0}>
          <table className={styles.grid}>
            <thead>
              <tr>
                <th scope="col">{t("ai_compare.kind")}</th>
                {grid.columns.map((c) => (
                  <th key={columnKey(c)} scope="col">
                    {headOf(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.rows.map((row) => {
                const cells = grid.columns.map((c) => c.skills.find((s) => s.id === row.id));
                const best = bestOf(cells);
                return (
                  <tr key={row.id}>
                    <th scope="row">{row.label}</th>
                    {grid.columns.map((c, i) => cell(c, cells[i], best?.index === i, !!best?.only))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

