// The AI accounts that are set up, as one place (design 7.16). Above the rows, one line says who does the work and who
// stands in; each row says the account's role in words (does the work, backup, not used), the person's own name for it,
// what it covers, its state in words with a dot, and the one next step the state calls for. Everything else is in the
// row's menu: test, make this the main account, use as backup or stop, change models, replace the key, when the key
// ends, rename and remove. Making an account the main one keeps the one it replaces as its backup when that passes its
// check; an account stands in for a kind of work only once it passed its check for that work, with the cost shown first.
// Removing the account that does the work says in its toast what happens to the work, and Undo puts it back. The
// service's name comes from the catalog entry the account was made from; a key is never shown, only whether one is kept,
// and an account's id in the settings is never shown at all. Each row ends with one line of what its models can do
// (design 6.16), linking to the comparison grid; it shows only the short model name the person chose, never the model's own.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import {
  accountName,
  ago,
  knownTiers,
  nextStep,
  orderAccounts,
  roleOf,
  stateOf,
  summarize,
  workWords,
  broken,
  type Account,
  type Kind,
} from "../lib/ai-accounts";
import { EVERYDAY, HARDER, modelsOf, planFor, useAccountActs, useConfirmAbove } from "../lib/ai-account-acts";
import { day, monthDay, wallWhen } from "../lib/dates";
import { useMoney } from "../lib/money";
import { problemText } from "../lib/problem";
import { asReference } from "../lib/secret-ref";
import { useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { Pill, type PillTone } from "../ui/Pill";
import { Row } from "../ui/Row";
import { restoreFocus } from "./ModalPanel";
import { RowMenu, type MenuAction } from "./RowMenu";
import styles from "./AiAccounts.module.css";

type Mode = "key" | "models" | "expires" | "name" | null;

/** A value once it has stayed the same for a moment, so a price isn't asked for at every keystroke. */
function useSettled<T>(value: T, ms = 500): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** A sentence from the sheet with some of its words as elements (a name in bold): the template's placeholders are swapped for
 * markers and cut at them. */
function withNodes(template: string, nodes: Record<string, ReactNode>): ReactNode[] {
  const marks = new RegExp(`\\u0001(${Object.keys(nodes).join("|")})\\u0001`);
  return template.split(marks).map((part, i) => (i % 2 === 1 ? <span key={i}>{nodes[part]}</span> : part));
}

export function AiAccounts(props: {
  /** Whether keys can be pasted here; read from the setup when not given. */
  local?: boolean;
  /** The level of the section's heading: 2 when it is the heading of Settings' own section (it takes the cursor when the
   * section opens), 3 beside other settings, 4 inside a step of the setup guide. */
  level?: 2 | 3 | 4;
  /** Opens where a new account is added; the button shows only when given. */
  onAdd?: () => void;
  /** Opens the grid of what each account can do; the button and each row's "See all" show only when given. */
  onCompare?: () => void;
}) {
  const { t, tn } = useWords();
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  // What each model can do; a list that didn't load leaves the rows without it.
  const skills = useQuery({ queryKey: ["ai-skills"], queryFn: api.aiSkills });
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup, enabled: props.local === undefined });
  const local = props.local ?? setup.data?.local ?? true;
  if (accounts.isPending) return null;
  // A list that didn't load says so quietly, without a heading of its own.
  if (accounts.isError) return <p className="hint">{t("ai_accounts.load_failed")}</p>;
  const list = accounts.data;
  const Heading = props.level === 4 ? "h4" : props.level === 2 ? "h2" : "h3";
  const kinds = endpoints.data ?? [];
  const kindOf = (a: Account) => kinds.find((k) => k.id === a.kind);
  return (
    <section className="ai-accounts" aria-labelledby="ai-accounts-title">
      <div className="heading">
        <Heading id="ai-accounts-title" {...(props.level === 2 ? { tabIndex: -1, "data-section-heading": "" } : {})}>
          {t("ai_accounts.title")}
          {list.length > 0 && (
            <span className={styles.count} aria-label={tn("ai_accounts.count", list.length)}>
              {list.length}
            </span>
          )}
        </Heading>
        {(props.onCompare || props.onAdd) && (
          <div className="acts wrap">
            {props.onCompare && list.length > 0 && (
              <Button onClick={props.onCompare}>{t("ai_accounts.compare")}</Button>
            )}
            {props.onAdd && (
              <Button variant="primary" onClick={props.onAdd}>
                {t("ai_accounts.add")}
              </Button>
            )}
          </div>
        )}
      </div>
      {list.length === 0 ? (
        <p className="hint">{t("ai_accounts.none")}</p>
      ) : (
        <>
          <Summary accounts={list} kindOf={kindOf} onAddOne={props.onAdd} />
          <ul className={styles.list}>
            {orderAccounts(list).map((account) => (
              <AccountRow
                key={account.name}
                account={account}
                accounts={list}
                kind={kindOf(account)}
                kindOf={kindOf}
                local={local}
                skills={skills.data?.accounts.find((a) => a.name === account.name)}
                onCompare={props.onCompare}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Who does the work and who stands in, and whether every kind of work has a backup. */
function Summary(props: { accounts: Account[]; kindOf: (a: Account) => Kind | undefined; onAddOne?: () => void }) {
  const { t, tn } = useWords();
  const found = summarize(props.accounts);
  const name = (a: Account) => accountName(a, props.kindOf(a), t);
  const bold = (a: Account) => <strong>{name(a)}</strong>;
  const gap =
    found.gaps.length === 0
      ? t("ai_accounts.summary.all_backed")
      : found.gaps.length > 1
        ? t("ai_accounts.summary.gap.all")
        : t(found.gaps[0] === "routine" ? "ai_accounts.summary.gap.routine" : found.gaps[0] === "deep" ? "ai_accounts.summary.gap.deep" : "ai_accounts.summary.gap.other");
  return (
    <div className={styles.summary} role="group" aria-label={t("ai_accounts.summary.label")}>
      <p className={styles.sentence}>
        {found.mains.length === 0
          ? t("ai_accounts.summary.nobody")
          : found.mains.length === 1
            ? withNodes(t("ai_accounts.summary.does", { main: "\u0001main\u0001" }), { main: bold(found.mains[0].account) })
            : found.mains.map((m, i) => (
                <span key={m.account.name}>
                  {i > 0 && t("ai_accounts.summary.and")}
                  {withNodes(t("ai_accounts.summary.does_part", { main: "\u0001main\u0001", work: workWords(m.tiers, t) }), { main: bold(m.account) })}
                </span>
              ))}
        {found.mains.length > 0 && found.backups.length > 0 ? (
          <>
            {" "}
            <span aria-hidden="true">→</span>{" "}
            {withNodes(tn("ai_accounts.summary.backup", found.backups.length, { names: "\u0001names\u0001" }), {
              names: found.backups.map((b, i) => (
                <span key={b.name}>
                  {i > 0 && t("ai_accounts.summary.names")}
                  {bold(b)}
                </span>
              )),
            })}
          </>
        ) : (
          found.mains.length > 0 && t("ai_accounts.summary.end")
        )}
      </p>
      {found.mains.length > 0 && (
        <p className={styles.quiet}>
          {gap}
          {found.gaps.length > 0 && props.onAddOne && (
            <>
              {" · "}
              <button type="button" className="link-button" onClick={props.onAddOne}>
                {t("ai_accounts.summary.add_one")}
              </button>
            </>
          )}
        </p>
      )}
    </div>
  );
}

/** How many kinds of work an account is good at, falls below the minimum on, or has no measurement for (an old one counts as none). */
function skillCounts(models: S["AiModelSkills"][]) {
  const kinds = new Map<string, "good" | "below" | "unknown">();
  for (const model of models) {
    for (const s of model.skills) {
      const counted = s.measured && s.pass_rate != null && !s.stale;
      const here = !counted ? "unknown" : s.below_min ? "below" : "good";
      const before = kinds.get(s.id);
      if (before === undefined || here === "good" || (here === "below" && before === "unknown")) kinds.set(s.id, here);
    }
  }
  const all = [...kinds.values()];
  return { total: all.length, good: all.filter((k) => k === "good").length, below: all.filter((k) => k === "below").length, unknown: all.filter((k) => k === "unknown").length };
}

function AccountRow(props: {
  account: Account;
  accounts: Account[];
  kind: Kind | undefined;
  kindOf: (a: Account) => Kind | undefined;
  local: boolean;
  skills?: S["AiAccountSkills"];
  onCompare?: () => void;
}) {
  const { t, tn } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const acts = useAccountActs();
  const freshFingerprint = useFreshFingerprint();
  const money = useMoney();
  const confirmAbove = useConfirmAbove();
  const { account, kind } = props;
  const name = accountName(account, kind, t);
  const base = `ai-account-${account.name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  const [mode, setMode] = useState<Mode>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<S["AiTestResult"] | null>(null);
  const [key, setKey] = useState("");
  const [ends, setEnds] = useState("");
  const [label, setLabel] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [harder, setHarder] = useState("");
  const [moveHarder, setMoveHarder] = useState(true);
  // A check that would cost more than the person asked to be asked about waits for their go, with its cost on screen.
  const [gate, setGate] = useState<{ usd: number; run: () => void } | null>(null);
  const guard = (usd: number | null | undefined, run: () => void) => {
    if (usd != null && usd > confirmAbove) setGate({ usd, run });
    else run();
  };
  const primaryButton = useRef<HTMLButtonElement>(null);
  const firstField = useRef<HTMLInputElement>(null);

  const role = roleOf(account);
  const backupFor = account.backup_for ?? [];
  const tiers = knownTiers(props.accounts);
  const allTiers = tiers.length ? tiers : ["routine", "deep"];
  const keyState = account.key_state ?? (account.has_key ? "saved" : "none");
  const { everyday, deep } = modelsOf(account);
  const shorts = Object.keys(account.models);
  const others = props.accounts.filter((a) => a.name !== account.name);
  const mains = others.filter((a) => a.used_for.length > 0);

  // The settings as they were when a form that edits what the row holds (its name, its models) opened: its typed values
  // were made from them, so its save sends this fingerprint and a change made since is refused, not overwritten.
  const opened = useRef<Promise<string> | null>(null);
  const baseline = () => {
    const read = freshFingerprint();
    read.catch(() => {});
    opened.current = read;
  };

  const open = (next: Exclude<Mode, null>) => {
    baseline();
    setProblem("");
    setKey("");
    setEnds(next === "expires" ? (account.credential_expires ?? "") : "");
    setLabel(next === "name" ? account.label || name : "");
    setHarder("");
    setMoveHarder(true);
    setModels({ ...account.models });
    setMode(next);
    restoreFocus(() => firstField.current);
  };
  const close = () => {
    setMode(null);
    setProblem("");
    restoreFocus(() => primaryButton.current);
  };

  const fail = (err: unknown, fromForm = false) => {
    // A changed file means the lists are out of date: load them again, keeping what was typed.
    if (err instanceof ApiError && err.status === 409) {
      void client.invalidateQueries({ queryKey: ["settings"] });
      if (fromForm) {
        // Said once; the next save is the person's own, on what is saved now.
        baseline();
        setProblem(t("settings.changed_since_opened"));
        return;
      }
    }
    setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
  };

  /** Saves a change and reads it back with Undo; a refusal is said on the row. Returns whether it was saved. */
  const save = async (work: (fingerprint: string) => Promise<S["SettingsSaved"]>, message: string | (() => string), fromForm = false): Promise<boolean> => {
    setBusy(true);
    setProblem("");
    try {
      await acts.save(work, message, fromForm ? await opened.current! : undefined);
      return true;
    } catch (err) {
      fail(err, fromForm);
      return false;
    } finally {
      setBusy(false);
    }
  };

  // The backup that does this account's work when it is removed: one that stands in for all of it, else any that stands in for some.
  const heir = (() => {
    if (!account.used_for.length) return undefined;
    const backups = others.filter((a) => (a.backup_for ?? []).some((tier) => account.used_for.includes(tier)));
    return backups.find((a) => account.used_for.every((tier) => (a.backup_for ?? []).includes(tier))) ?? backups[0];
  })();
  const remove = () =>
    void save(
      (fingerprint) => api.removeAccount(account.name, fingerprint, heir?.name),
      () =>
        !account.used_for.length
          ? t("ai_accounts.removed", { name })
          : heir
            ? t("ai_accounts.removed_heir", { name, heir: accountName(heir, props.kindOf(heir), t) })
            : t("ai_accounts.removed_nobody", { name }),
    );

  const replaceKey = async () => {
    const pasted = key.trim();
    if (!pasted) return;
    const done = await save(
      (fingerprint) => {
        // A new key has its own end date: the one typed, else none is known, so the old key's date is dropped.
        const dates = ends ? { credential_expires: ends } : account.credential_expires ? { clear_credential_expires: true } : {};
        return api.changeAccount(account.name, props.local ? { fingerprint, key: pasted, ...dates } : { fingerprint, key_ref: asReference(pasted), ...dates });
      },
      t("ai_accounts.key_replaced", { name }),
    );
    if (done) {
      setKey("");
      close();
    }
  };

  const saveEnds = async () => {
    const done = await save(
      (fingerprint) => api.changeAccount(account.name, ends ? { fingerprint, credential_expires: ends } : { fingerprint, clear_credential_expires: true }),
      t(ends ? "ai_accounts.key_ends_saved" : "ai_accounts.key_ends_cleared", { name, date: ends ? day(ends) : "" }),
    );
    if (done) close();
  };

  const rename = async () => {
    const typed = label.trim();
    if (!typed) return;
    const done = await save((fingerprint) => api.changeAccount(account.name, { fingerprint, label: typed }), t("ai_accounts.renamed", { name: typed }), true);
    if (done) close();
  };

  const nextModels = () => {
    const next: Record<string, string> = {};
    for (const [short, id] of Object.entries(models)) next[short] = id.trim();
    if (harder.trim()) next[HARDER] = harder.trim();
    return next;
  };

  /** A backup that gains a harder model can move its harder-work backup there, once that model passed its check. */
  const offersHarderBackup = mode === "models" && backupFor.includes("deep") && !(HARDER in account.models) && harder.trim() !== "";

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
      () => t(checking ? "ai_accounts.switch_checking" : "ai_accounts.models_changed", { name }),
      true,
    );
    if (!done) return;
    if (offersHarderBackup && moveHarder) {
      try {
        const bad = await acts.standIn(account.name, [["deep", HARDER]], t("ai_accounts.harder_backup_set", { name }));
        if (bad) push({ message: t("ai_accounts.harder_backup_failed", { detail: bad.detail }) });
      } catch (err) {
        fail(err);
        return;
      }
    }
    close();
  };

  const test = async () => {
    setTesting(true);
    setProblem("");
    setResult(null);
    try {
      const answer = await api.testAccount(account.name);
      // One answer for the account; a list is read by its first entry.
      setResult((Array.isArray(answer) ? answer[0] : answer) ?? null);
      void client.invalidateQueries({ queryKey: ["ai-accounts"] });
    } catch (err) {
      fail(err);
    } finally {
      setTesting(false);
    }
  };

  // Make this account do the assistant's work: everyday work on its first model, harder work on its harder one. With
  // `check`, as a switch whose new choice is checked in the background. The account it replaces stays as its backup when
  // it passes its own check, so a switch never leaves the work with nothing to fall back on.
  const takesWork = account.adapter !== "stub" && role !== "work" && shorts.length > 0 && keyState !== "missing";
  const useOffer = useQuery({
    queryKey: ["switch-estimate", account.name, "use", everyday, deep],
    queryFn: async () => api.switchEstimate(account.name, { fingerprint: await freshFingerprint(), use: { routine: everyday, deep } }),
    enabled: takesWork,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const offeredUse = takesWork && useOffer.data?.offered === true;
  const makeMain = async (check = false) => {
    if (shorts.length === 0) return;
    // The ones it replaces are checked first, with what they did, so what is kept as a backup is known to work.
    const replaced: { account: Account; plan: [string, string][]; failed: S["AiTestResult"] | null }[] = [];
    setBusy(true);
    try {
      for (const prev of mains) {
        const plan = planFor(prev, prev.used_for).filter(([tier]) => !(prev.backup_for ?? []).includes(tier));
        replaced.push({ account: prev, plan, failed: plan.length ? await acts.failing(prev.name, plan) : null });
      }
    } catch {
      // A check that couldn't be made leaves the one it replaces out of the backups; the switch itself goes on.
    } finally {
      setBusy(false);
    }
    let checking = false;
    const done = await save(
      async (fingerprint) => {
        const body = { fingerprint, use: { routine: everyday, deep } };
        if (!check) return api.changeAccount(account.name, body);
        const answer = await api.switchAndCheck(account.name, body);
        checking = answer.checking;
        return answer.saved;
      },
      () => t(checking ? "ai_accounts.switch_checking" : "ai_accounts.used_for_work", { name }),
    );
    if (!done) return;
    for (const prev of replaced) {
      const prevName = accountName(prev.account, props.kindOf(prev.account), t);
      if (prev.failed || prev.plan.length === 0) {
        if (prev.failed) push({ message: t("ai_accounts.main_made_not_kept", { name, previous: prevName }) });
        continue;
      }
      try {
        await acts.save(
          (fingerprint) => api.changeAccount(prev.account.name, { fingerprint, backup: Object.fromEntries(prev.plan) }),
          t("ai_accounts.main_made_kept", { name, previous: prevName }),
        );
      } catch (err) {
        fail(err);
      }
    }
  };

  // Stand in for the account that does the work: each kind of work it doesn't back up yet is checked with its exact
  // settings on the model it would use, and the account is added only when every check passed.
  const backupPlan = planFor(account, ["routine", "deep"]).filter(([tier]) => !backupFor.includes(tier));
  const backsUp = account.adapter !== "stub" && role === "none" && shorts.length > 0 && mains.length > 0 && backupPlan.length > 0 && (keyState === "saved" || (kind !== undefined && !kind.needs_key));
  const useAsBackup = async () => {
    setTesting(true);
    setProblem("");
    setResult(null);
    try {
      const bad = await acts.standIn(account.name, backupPlan, t("ai_accounts.backup_set", { name }));
      if (bad) setResult(bad);
    } catch (err) {
      fail(err);
    } finally {
      setTesting(false);
    }
  };
  const stopBackup = () => void save((fingerprint) => api.changeAccount(account.name, { fingerprint, stop_backup: true }), t("ai_accounts.backup_stopped", { name }));

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
  const switchNote = (offer: S["AiSwitchEstimate"] | undefined) => (offer?.offered ? checkLabel(offer) : undefined);
  const backupNote = account.check_usd == null ? t("ai_accounts.backup_note_free") : t("ai_accounts.backup_note", { amount: money(account.check_usd) });

  const state = stateOf(account, kind, allTiers);
  const next = nextStep(state.kind);
  const now = new Date();
  const stateText = (() => {
    switch (state.kind) {
      case "missing":
        return account.key_where ? t("ai_accounts.key_missing", { where: account.key_where }) : t("ai_accounts.key_missing_plain");
      case "no_key":
        return t("ai_accounts.state.no_key");
      case "failed":
        return t("ai_accounts.state.failed", { work: workWords(state.tiers, t) });
      case "paused":
        return t("ai_accounts.state.paused", { time: account.paused_until ? wallWhen(account.paused_until) : "" });
      case "ending":
        return t("ai_accounts.state.ending", { date: monthDay(account.credential_expires) });
      case "ready": {
        const when = ago(account.answered_at ?? "", now, t);
        return (account.spent_today_usd ?? 0) > 0
          ? t("ai_accounts.state.ready_cost", { ago: when, amount: money(account.spent_today_usd ?? 0) })
          : t("ai_accounts.state.ready", { ago: when });
      }
      case "checked":
        return t("ai_accounts.state.checked", {
          work: state.tiers.length ? workWords(state.tiers, t) : t("ai_accounts.work.every"),
          date: monthDay(account.checked_at),
        });
      default:
        return t("ai_accounts.state.untested");
    }
  })();
  const identityText = account.identity_changed_to
    ? t("ai_accounts.identity.changed", { account: account.identity_changed_to })
    : account.runs_as
      ? t("ai_accounts.identity.runs_as", { account: account.runs_as })
      : account.identity_unknown
        ? t("ai_accounts.identity.unknown", { reason: account.identity_unknown })
        : "";
  const worry = ["missing", "no_key", "failed", "paused", "ending"].includes(state.kind);
  const dot = worry ? <Icon name="alert" size={16} /> : <span className={styles.dot} data-tone={state.kind === "untested" ? "quiet" : "ok"} aria-hidden="true" />;

  const kindWords = !kind ? "" : kind.local ? t("ai_accounts.kind.local") : kind.needs_key ? t("ai_accounts.kind.paid") : kind.program ? t("ai_accounts.kind.app") : "";
  const covers = role === "work" ? t("ai_accounts.covers.work", { work: workWords(account.used_for, t) }) : role === "backup" ? t("ai_accounts.covers.backup", { work: workWords(backupFor, t) }) : "";
  const keyEnds = account.credential_expires && !account.key_ending ? t("ai_accounts.key_ends_quiet", { date: monthDay(account.credential_expires) }) : "";
  const metaLine = [kindWords, kind?.name, covers, keyEnds].filter(Boolean).join(" · ");
  const pillTone: PillTone = role === "work" ? "need" : role === "none" && broken(account) ? "warn" : "neutral";

  const counts = props.skills ? skillCounts(props.skills.models) : null;
  const skillLine =
    counts && counts.total > 0
      ? [
          t("ai_skills.summary", { good: counts.good, total: counts.total }),
          counts.below > 0 ? tn("ai_skills.summary_below", counts.below) : "",
          counts.unknown > 0 ? t("ai_skills.summary_unmeasured", { n: counts.unknown }) : "",
        ]
          .filter(Boolean)
          .join(" · ")
      : "";

  const modelLabel = (short: string) =>
    short === EVERYDAY ? t("ai_accounts.model_everyday") : short === HARDER ? t("ai_accounts.model_harder") : t("ai_accounts.model_other", { short });
  const modelsChanged = harder.trim() !== "" || Object.entries(models).some(([short, id]) => id.trim() !== (account.models[short] ?? ""));
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
  const onlyMain = role === "work" && !heir;
  const extras = mode !== null || !!problem || testing || !!result || !!gate;

  const actions: MenuAction[] = [
    { id: "test", label: t("ai_accounts.test"), run: () => void test(), disabled: testing || busy },
    ...(takesWork
      ? [
          { id: "main", label: t("ai_accounts.make_main"), note: switchNote(useOffer.data), run: () => guard(offeredUse ? useOffer.data?.usd : null, () => void makeMain(offeredUse)), disabled: busy },
          ...(offeredUse ? [{ id: "main-plain", label: t("ai_accounts.switch_without_check"), run: () => void makeMain(false), disabled: busy }] : []),
        ]
      : []),
    ...(backsUp ? [{ id: "backup", label: t("ai_accounts.use_as_backup"), note: backupNote, run: () => guard(account.check_usd, () => void useAsBackup()), disabled: testing || busy }] : []),
    ...(role === "backup" ? [{ id: "stop-backup", label: t("ai_accounts.stop_backup"), run: stopBackup, disabled: busy }] : []),
    { id: "models", label: t("ai_accounts.change_models"), run: () => open("models") },
    { id: "key", label: t("ai_accounts.replace_key"), run: () => open("key") },
    { id: "expires", label: t("ai_accounts.key_ends_set"), run: () => open("expires") },
    { id: "name", label: t("ai_accounts.rename"), run: () => open("name") },
    { id: "remove", label: onlyMain ? t("ai_accounts.remove_no_account") : t("ai_accounts.remove"), run: remove, disabled: busy },
  ];

  const nextButton =
    next.step === null ? undefined : next.step === "add_key" ? (
      <Button size="sm" variant="primary" data-key="primary" ref={primaryButton} aria-label={t("ai_accounts.add_key_named", { name })} onClick={() => open("key")}>
        {t("ai_accounts.add_key")}
      </Button>
    ) : (
      <Button
        size="sm"
        variant={next.primary ? "primary" : "secondary"}
        data-key="primary"
        ref={primaryButton}
        disabled={testing || busy}
        aria-label={t(next.step === "see_why" ? "ai_accounts.see_why_named" : "ai_accounts.test_named", { name })}
        onClick={() => void test()}
      >
        {t(testing ? "ai_accounts.testing" : next.step === "see_why" ? "ai_accounts.see_why" : "ai_accounts.test")}
      </Button>
    );

  return (
    <Row
      pill={<Pill tone={pillTone}>{t(`ai_accounts.role.${role}`)}</Pill>}
      title={<span id={`${base}-title`}>{name}</span>}
      aria-labelledby={`${base}-title`}
      meta={
        <>
          {metaLine && <span className={styles.meta}>{metaLine}</span>}
          <span className={`${styles.meta} ${styles.state}`} data-tone={worry ? "warn" : "ok"}>
            {dot}
            <span>{stateText}</span>
          </span>
          {identityText && (
            <span className={styles.meta} data-tone={account.identity_changed_to || (!account.runs_as && account.identity_unknown) ? "warn" : "ok"} data-identity="" title={account.runs_as_how ?? undefined}>
              {identityText}
            </span>
          )}
          {skillLine && (
            <span className={styles.skills}>
              {skillLine}
              {props.onCompare && (
                <>
                  {" · "}
                  <button type="button" className="link-button" aria-label={t("ai_skills.see_all_named", { name })} onClick={props.onCompare}>
                    {t("ai_skills.see_all")}
                  </button>
                </>
              )}
            </span>
          )}
        </>
      }
      primary={nextButton}
      menu={<RowMenu label={name} actions={actions} />}
    >
      <div className={styles.forms} hidden={!extras}>
        {mode === "name" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void rename();
            }}
          >
            <label htmlFor={`${base}-label`}>{t("ai_accounts.rename_label")}</label>
            <input id={`${base}-label`} ref={firstField} type="text" value={label} autoComplete="off" aria-describedby={`${base}-label-hint`} onChange={(e) => setLabel(e.target.value)} />
            <p className="hint" id={`${base}-label-hint`}>
              {t("ai_accounts.rename_hint")}
            </p>
            <div className="row-end">
              <Button variant="ghost" disabled={busy} onClick={close}>
                {t("ai_accounts.cancel")}
              </Button>
              <Button variant="primary" type="submit" disabled={busy || label.trim() === "" || label.trim() === name}>
                {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
              </Button>
            </div>
          </form>
        )}
        {mode === "expires" && (
          <form
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
              <Button variant="ghost" disabled={busy} onClick={close}>
                {t("ai_accounts.cancel")}
              </Button>
              <Button variant="primary" type="submit" disabled={busy || ends === (account.credential_expires ?? "")}>
                {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
              </Button>
            </div>
          </form>
        )}
        {mode === "key" && (
          <form
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
              <Button variant="ghost" disabled={busy} onClick={close}>
                {t("ai_accounts.cancel")}
              </Button>
              <Button variant="primary" type="submit" disabled={busy || key.trim() === ""}>
                {t(busy ? "ai_accounts.saving" : "ai_accounts.save")}
              </Button>
            </div>
          </form>
        )}
        {mode === "models" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (modelsChanged && !modelsBlank) void changeModels(offeredModels);
            }}
          >
            <fieldset className="details">
              <legend>{t("ai_accounts.models_title", { name })}</legend>
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
              {offersHarderBackup && (
                <label className="check-line">
                  <input type="checkbox" checked={moveHarder} onChange={(e) => setMoveHarder(e.target.checked)} />
                  <span>{t("ai_accounts.harder_backup")}</span>
                </label>
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
              <Button variant="ghost" disabled={busy} onClick={close}>
                {t("ai_accounts.cancel")}
              </Button>
              {offeredModels && (
                <Button disabled={busy} onClick={() => void changeModels(false)}>
                  {t("ai_accounts.switch_without_check")}
                </Button>
              )}
              <Button variant="primary" type="submit" disabled={busy || !modelsChanged || modelsBlank}>
                {busy ? t("ai_accounts.saving") : offeredModels ? checkLabel(modelsOffer.data) : t("ai_accounts.save")}
              </Button>
            </div>
          </form>
        )}
        {gate && (
          <div role="alert">
            <p className="hint">{t("ai_accounts.over", { amount: money(gate.usd), limit: money(confirmAbove) })}</p>
            <div className="row-end">
              <Button variant="ghost" onClick={() => setGate(null)}>
                {t("ai_accounts.cancel")}
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  const go = gate.run;
                  setGate(null);
                  go();
                }}
              >
                {t("ai_accounts.go_ahead")}
              </Button>
            </div>
          </div>
        )}
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        <div role="status" aria-live="polite">
          {testing && <p className="hint">{t("ai_accounts.testing")}</p>}
          {result && (
            <p className={result.ok ? styles.ok : styles.bad}>
              {resultText}
              <span aria-hidden="true">{result.ok ? " ✓" : " ✗"}</span>
            </p>
          )}
        </div>
      </div>
    </Row>
  );
}
