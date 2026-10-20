// The AI step of the setup guide (design 7.8), for a person who has never made an account: one recommended service, one
// alternative and "Something else" (the catalog says which; nothing here does), numbered steps for the chosen service (make
// an account, add credit, make a key, paste it), and a check that runs the moment the key is pasted, with every kind of work
// tried before anything is saved. Then one explicit question about reading work mail and notes, with the account's sign-in
// shown, the spending as a sentence, and the screen's one Continue, which saves it all. A pasted key is sent once and kept
// on this computer; the account's settings only refer to it. What a kind needs is read from its catalog entry (a key, an
// address, or a program to start), never from its name. In Settings the same form opens in a drawer (`drawer`): it adds the
// account's own name and "What is it for?" (the assistant's work, a backup, or nothing yet), checks the account for each
// kind of work it was added for with the cost shown first, and never leaves Settings.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAmount, useSmallMoney } from "../lib/money";
import { problemText } from "../lib/problem";
import { asReference } from "../lib/secret-ref";
import { setAccountCheck } from "../lib/account-checks";
import { useAfterSave } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useContinue, useHasContinueSlot } from "../lib/walkthrough-continue";
import { useWords } from "../lib/wording";
import { accountName, roleOf } from "../lib/ai-accounts";
import { HARDER as HARDER_SHORT, planFor, useAccountActs, useConfirmAbove } from "../lib/ai-account-acts";
import { AiAccounts } from "./AiAccounts";
import { useSpendLine } from "./AiSpendLine";
import { domainOf } from "./SafeText";
import { Button } from "../ui/Button";
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
/** An id for the settings from the name the person gave: lowercase letters, digits and dashes, free among the accounts. */
function idFrom(label: string, fallback: string, taken: Set<string>): string {
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/-+$/, "");
  return freeName(ACCOUNT_NAME.test(slug) ? slug : fallback, taken);
}

function freeName(id: string, taken: Set<string>): string {
  if (!taken.has(id)) return id;
  let n = 2;
  while (taken.has(`${id}-${n}`)) n += 1;
  return `${id}-${n}`;
}

type For = "work" | "backup" | "none";
/** The person's answer to "may it read your work mail and notes?"; nothing until they choose. */
type WorkData = "allow" | "not_now";
/** How the check of a new account stands: not yet made, running, passed (with the sign-in it runs as, when found), or why not. */
type Verdict =
  | { state: "idle" }
  | { state: "checking" }
  | { state: "works"; identity: string | null; unknown: string | null }
  | { state: "failed"; message: string };
/** What "Allow" lets a new account read: open material and the internal kind work mail and notes are. */
const ALLOWED: Level[] = ["open", "internal"];

export function WelcomeAi(props: {
  local: boolean;
  done: boolean;
  /** Set in Settings' drawer: the form asks what the account is for and the list and the guide's test are left out. */
  drawer?: { onAdded: () => void; onCancel: () => void; onDirty?: (dirty: boolean) => void };
}) {
  const { t, tn, has } = useWords();
  const money = useSmallMoney();
  const amount = useAmount();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const acts = useAccountActs();
  const confirmAbove = useConfirmAbove();
  const [askedGo, setAskedGo] = useState(false);
  const { push } = useToasts();
  const drawer = props.drawer;
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  const found = useQuery({ queryKey: ["ai-local"], queryFn: api.aiLocal });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const checkSize = useQuery({ queryKey: ["ai-check-size"], queryFn: api.aiCheckSize, enabled: !!drawer });
  const [labelText, setLabelText] = useState("");
  const [labelTouched, setLabelTouched] = useState(false);
  const [forWhat, setForWhat] = useState<For | null>(null);
  const [kindId, setKindId] = useState("");
  const [usingFound, setUsingFound] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [modelsOpen, setModelsOpen] = useState(false);
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
  const [workData, setWorkData] = useState<WorkData | null>(null);
  const [verdict, setVerdict] = useState<Verdict>({ state: "idle" });
  const [elseOpen, setElseOpen] = useState(false);
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
  const lookup = useRef(0);
  const verifying = useRef(0);
  /** The key the last check was made with, so the box changing to that same key (a paste) doesn't undo the check. */
  const verifiedKey = useRef("");

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
  // The name the person sees: theirs, else the service's name and "account", numbered when that is taken.
  const labels = new Set((accounts.data ?? []).map((a) => accountName(a, endpoints.data?.find((e) => e.id === a.kind), t)));
  const defaultLabel = (() => {
    if (!kind) return "";
    const base = t("ai_accounts.default_name", { service: kind.name });
    let n = 2;
    let found = base;
    while (labels.has(found)) found = `${base} ${n++}`;
    return found;
  })();
  const shownLabel = labelTouched ? labelText : defaultLabel;
  // The id in the settings: typed under Advanced in the guide, made from the name in the drawer.
  // Left as suggested in the guide, the id stays the kind's own; a name the person typed makes its own.
  const accountId = kind ? (drawer || labelTouched ? idFrom(shownLabel, kind.id, taken) : freeName(kind.id, taken)) : "";

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

  // In the drawer: a typed key or name is unsaved text, and the cursor starts in the first main field, the choice of service.
  const typed = key.trim() !== "" || keyRef.trim() !== "" || labelTouched;
  const onDirty = drawer?.onDirty;
  useEffect(() => {
    onDirty?.(typed);
  }, [typed, onDirty]);
  const firstKind = useRef<HTMLDivElement>(null);
  const kindsShown = !!endpoints.data?.length;
  useEffect(() => {
    if (!drawer || !kindsShown) return;
    // After the drawer has taken focus itself, which it does as it opens.
    const frame = window.requestAnimationFrame(() => firstKind.current?.querySelector<HTMLInputElement>('input[name="ai-kind"]')?.focus());
    return () => window.cancelAnimationFrame(frame);
    // Only when the choices first appear.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kindsShown]);

  const keyArgs = (over?: { key?: string }) => {
    const pasted = (over?.key ?? key).trim();
    if (props.local && pasted) return { key: pasted };
    if (keyRef.trim()) return { key_ref: asReference(keyRef) };
    return {};
  };

  /** Ask the service for its models. A newer question, or a different choice, makes an older answer irrelevant (null). */
  const check = async (picked: Kind, over?: { key?: string; address?: string }): Promise<{ models: ModelInfo[]; problem: string } | null> => {
    const mine = ++lookup.current;
    setListing(true);
    setListProblem("");
    const body: S["AiModelsAsk"] = { endpoint: picked.id, ...keyArgs(over) };
    if (asksAddress(picked)) body.base_url = (over?.address ?? address).trim();
    try {
      const answer = await api.aiModels(body);
      if (mine !== lookup.current) return null;
      const got = answer.models ?? [];
      setModels(got);
      setListProblem(answer.problem ?? "");
      setFilter("");
      if (got.length) {
        setEveryday((cur) => (got.some((m) => m.id === cur) ? cur : got[0].id));
        setHarder((cur) => (got.some((m) => m.id === cur) ? cur : HARDER_SAME));
      }
      return { models: got, problem: answer.problem ?? "" };
    } catch (err) {
      if (mine !== lookup.current) return null;
      const problem = err instanceof ApiError && err.detail ? err.detail : problemText(err, t);
      setModels(null);
      setListProblem(problem);
      return { models: [], problem };
    } finally {
      if (mine === lookup.current) setListing(false);
    }
  };

  /** The check of a new account, run the moment its key is pasted (or its address or program is given): every kind of work is
   * tried with the exact settings it will use, before anything is saved. Says "works" with the sign-in it runs as, or why it
   * doesn't, in words that fit the kind of account. The values the screen has only just set are passed in `over`. */
  const verify = async (
    picked: Kind,
    over: {
      key?: string;
      address?: string;
      command?: string;
      model?: string;
      everyday?: string;
      harder?: string;
      found?: boolean;
      packetVia?: "stdin" | "file";
      outputVia?: "stdout" | "outbox";
    } = {},
  ) => {
    const mine = ++verifying.current;
    verifiedKey.current = (over.key ?? key).trim();
    const asAgent = !takesAddress(picked);
    const typedAddress = (over.address ?? address).trim();
    const typedKey = (over.key ?? key).trim();
    const typedCommand = (over.command ?? command).trim();
    const waiting =
      (picked.needs_key && !typedKey && keyRef.trim() === "") ||
      (asksAddress(picked) && !typedAddress) ||
      (asAgent && !isBuiltin(picked) && !typedCommand);
    if (waiting) {
      setVerdict({ state: "idle" });
      return;
    }
    if (isBuiltin(picked) && picked.installed === false) {
      setVerdict({ state: "idle" });
      return;
    }
    setVerdict({ state: "checking" });
    let first = over.everyday ?? over.model ?? everyday;
    let second = over.harder ?? harder;
    const onFound = over.found ?? (usingFound && picked.id === kindId);
    if (!asAgent && !onFound && (picked.base_url !== "" || props.local) && over.everyday === undefined) {
      const got = await check(picked, { key: over.key, address: over.address });
      if (mine !== verifying.current) return;
      if (!got || got.problem) {
        setVerdict({ state: "failed", message: got?.problem ?? t("welcome.ai.check_failed") });
        return;
      }
      if (got.models.length) {
        first = got.models.some((m) => m.id === first) ? first : got.models[0].id;
        second = got.models.some((m) => m.id === second) ? second : HARDER_SAME;
      }
    }
    // A program that picks its own model is checked on the account's own first one.
    const picksItself = isBuiltin(picked) && !!picked.model_optional && !customModel && first.trim() === "";
    if (!picksItself && first.trim() === "") {
      // A model that has to be named by hand is asked for first: nothing is checked on a name that isn't there.
      setVerdict({ state: "idle" });
      return;
    }
    const named = second !== HARDER_SAME && second !== first ? second : "";
    const asked: S["AiAccountCheck"] = {
      endpoint: picked.id,
      ...(props.local && typedKey ? { key: typedKey } : keyRef.trim() ? { key_ref: asReference(keyRef) } : {}),
      models: picksItself ? { default: "default" } : named ? { everyday: first.trim(), harder: named } : { everyday: first.trim() },
      use: picksItself ? {} : { routine: "everyday", deep: named ? "harder" : "everyday" },
    };
    if (asksAddress(picked)) asked.base_url = typedAddress;
    if (asAgent && !isBuiltin(picked)) asked.agent = { command: typedCommand.split(/\s+/), packet_via: over.packetVia ?? packetVia, output_via: over.outputVia ?? outputVia };
    try {
      const answer = await api.checkAccount(asked);
      if (mine !== verifying.current) return;
      setVerdict(
        answer.ok
          ? { state: "works", identity: answer.identity ?? null, unknown: answer.identity_unknown ?? null }
          : { state: "failed", message: answer.message },
      );
    } catch (err) {
      if (mine !== verifying.current) return;
      setVerdict({ state: "failed", message: err instanceof ApiError && err.detail ? err.detail : problemText(err, t) });
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
    // A new account reads open material only until the person says more (the question on the step, or a tick in the form).
    setLevels(["open"]);
    setWorkData(null);
    verifying.current += 1;
    setVerdict({ state: "idle" });
    setProblem("");
  };

  const choose = (id: string) => {
    const picked = endpoints.data?.find((e) => e.id === id);
    if (!picked) return;
    reset(picked);
    setUsingFound(false);
    if (!isService(picked) && !isBuiltin(picked)) setMoreOpen(true);
    setElseOpen(!picked.recommended && !picked.alternative);
    if (!drawer) {
      // The check runs by itself as soon as the kind has all it needs from the person: nothing, for a server or a program.
      if (!picked.needs_key && (picked.base_url !== "" || isBuiltin(picked))) {
        void verify(picked, { model: isBuiltin(picked) && !picked.model_optional ? (picked.model_examples ?? [])[0] ?? "" : "" });
      }
      return;
    }
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
    if (!drawer) void verify(picked, { found: true, model: running.models[0] ?? "" });
  };

  /** Enter in a key field runs the check, as pressing the button does; it never adds the account. */
  const enterChecks = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
    e.preventDefault();
    if (!kind) return;
    if (drawer) {
      if (canCheck) void check(kind);
    } else void verify(kind, e.currentTarget.id === "ai-key" ? { key: e.currentTarget.value } : {});
  };

  const keyReady = !kind?.needs_key || !!server || key.trim() !== "" || keyRef.trim() !== "";
  const canCheck =
    canList && !listing && keyReady && (!kind || !asksAddress(kind) || address.trim() !== "");

  const ready =
    !!kind &&
    ACCOUNT_NAME.test(accountId) && shownLabel.trim() !== "" &&
    (programPicks || everyday.trim() !== "") &&
    !noMatch &&
    levels.length > 0 &&
    (generic ? command.trim() !== "" : builtin || !takesAddress(kind) || address.trim() !== "") &&
    (agent || keyReady) &&
    !!settings.data &&
    !busy;

  /** Tests every account the assistant's work uses; the lines say how each kind of work answered. Null when it couldn't run. */
  const test = async (): Promise<S["AiTestResult"][] | null> => {
    setTesting(true);
    setTestProblem("");
    setResults(null);
    try {
      const found = await api.testAi();
      setResults(found);
      void client.invalidateQueries();
      return found;
    } catch (err) {
      setTestProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return null;
    } finally {
      setTesting(false);
    }
  };

  // What the new account is for, in the drawer: the assistant's work when nothing does it yet, a backup once something does.
  const mains = (accounts.data ?? []).filter((a) => roleOf(a) === "work");
  const mainName = mains[0] ? accountName(mains[0], endpoints.data?.find((e) => e.id === mains[0].kind), t) : "";
  const chosenFor: For = forWhat ?? (mains.length ? "backup" : "work");

  /** About what checking the new account costs: the check's calls priced with the dearest model it will use. */
  const checkUsd = (() => {
    if (!drawer || !checkSize.data || agent || server) return null;
    const second = harder !== HARDER_SAME && harder !== everyday ? harder : "";
    const used = [everyday, ...(second ? [second] : [])].map((id) => list.find((m) => m.id === id));
    if (used.some((m) => m?.input_per_million == null || m?.output_per_million == null)) return null;
    return Math.max(...used.map((m) => ((m?.input_per_million ?? 0) * checkSize.data.input_tokens + (m?.output_per_million ?? 0) * checkSize.data.output_tokens) / 1e6));
  })();

  // A check that would cost more than the person asked to be asked about waits for a second press, with its cost shown.
  const overLimit = !!drawer && chosenFor !== "none" && checkUsd != null && checkUsd > confirmAbove;
  const addOrAsk = () => {
    if (overLimit && !askedGo) {
      setAskedGo(true);
      return;
    }
    setAskedGo(false);
    void add();
  };

  /** Saves the account. In the guide it then tests it and says whether the work is ready (true), so Continue can go on. */
  const add = async (): Promise<boolean> => {
    if (!kind || !settings.data) return false;
    const second = !agent && harder !== HARDER_SAME && harder !== everyday ? harder : "";
    const body: S["AiAccountAdd"] = {
      name: accountId,
      label: shownLabel.trim(),
      adapter: kind.adapter,
      endpoint: kind.id,
      models: programPicks ? {} : second ? { everyday: everyday.trim(), harder: second } : { everyday: everyday.trim() },
      allowed_data: levels,
      fingerprint: settings.data.fingerprint,
    };
    // Not now is kept with the account, so Today offers the yes again until the person gives it.
    if (guide && workData === "not_now") body.work_data = "not_now";
    const asWork = drawer ? chosenFor === "work" : useForWork;
    // With no model named there is no short name to point at, so the account's own first model does the work.
    if (asWork) {
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
      setAdded(accountId);
      // The next suggested name looks at the accounts as they are now, so a second account of this kind gets -2.
      setLabelText("");
      setLabelTouched(false);
      if (drawer) {
        const shown = body.label ?? accountId;
        await afterSave(saved, { message: t(asWork ? "ai_add.done_main" : "ai_add.done", { name: shown }) });
        // The form is done: it closes now, and the checks go on after it. Each kind of work it was added for is checked with
        // the exact settings, so a failure is said; the account's row shows the checks as they run (`lib/account-checks`),
        // and one toast says how they ended.
        const shorts = programPicks ? { everyday: "default", deep: "default" } : { everyday: "everyday", deep: second ? HARDER_SHORT : "everyday" };
        const plan: [string, string][] = [
          ["routine", shorts.everyday],
          ["deep", shorts.deep],
        ];
        const replaced = mains;
        const forBackup = chosenFor === "backup";
        drawer.onAdded();
        void (async () => {
          const step = (name: string) => (tier: string) => setAccountCheck(name, { running: tier, failed: null });
          const ended = (name: string, bad: S["AiTestResult"] | null) =>
            setAccountCheck(name, bad ? { running: null, failed: { detail: bad.detail ?? "", tiers: plan.map(([tier]) => tier) } } : null);
          try {
            if (forBackup) {
              const bad = await acts.standIn(accountId, plan, t("ai_accounts.backup_set", { name: shown }), step(accountId));
              ended(accountId, bad);
              if (bad) push({ message: t("ai_add.check_failed", { name: shown, detail: bad.detail }) });
            } else if (asWork) {
              const bad = await acts.failing(accountId, plan, step(accountId));
              ended(accountId, bad);
              if (bad) push({ message: t("ai_add.check_failed", { name: shown, detail: bad.detail }) });
              // The account it replaces stays as its backup when it passes its own check, so the work is never left with nothing.
              for (const prev of replaced) {
                const prevPlan = planFor(prev, prev.used_for);
                const prevName = accountName(prev, endpoints.data?.find((e) => e.id === prev.kind), t);
                const prevBad = await acts.failing(prev.name, prevPlan, step(prev.name));
                setAccountCheck(prev.name, null);
                if (prevBad) {
                  push({ message: t("ai_accounts.main_made_not_kept", { name: shown, previous: prevName }) });
                } else {
                  await acts.save(
                    (fingerprint) => api.changeAccount(prev.name, { fingerprint, backup: Object.fromEntries(prevPlan) }),
                    t("ai_accounts.main_made_kept", { name: shown, previous: prevName }),
                  );
                }
              }
            }
          } catch (err) {
            // Nothing is left on the row that would say a check is still running.
            for (const name of [accountId, ...replaced.map((a) => a.name)]) setAccountCheck(name, null);
            push({ message: t("error.failed", { detail: err instanceof ApiError ? err.detail : "" }) });
          }
          await client.invalidateQueries({ queryKey: ["ai-accounts"] });
        })();
        return true;
      }
      await afterSave(saved, { message: t("welcome.ai.added", { name: shownLabel.trim() }) });
      await client.invalidateQueries({ queryKey: ["ai-accounts"] });
      const tried = await test();
      return !!tried && tried.length > 0 && tried.every((r) => r.ok);
    } catch (err) {
      // The typed values stay, so a correction is one edit away. A changed file means the form is out of date.
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      return false;
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

  const all = endpoints.data ?? [];
  const guide = !drawer;
  const foundIds = new Set((found.data ?? []).map((s) => s.endpoint));
  const services = all.filter((k) => isService(k));
  // In the guide the catalog says which service to offer first and which beside it; the rest are "Something else".
  const recommended = guide ? services.find((k) => k.recommended) : undefined;
  const alternative = guide ? services.find((k) => k.alternative && k !== recommended) : undefined;
  const featured = [recommended, alternative].filter((k): k is Kind => !!k);
  const gated = featured.length > 0;
  const restServices = services.filter((k) => !featured.includes(k));
  const apps = all.filter((k) => isBuiltin(k) && !foundIds.has(k.id));
  const others = all.filter((k) => !isService(k) && !isBuiltin(k) && !foundIds.has(k.id));
  // The command-line agent that needs a command typed comes last.
  const more = [...others.filter((k) => takesAddress(k)), ...others.filter((k) => !takesAddress(k))];
  // Something else is open while the person chose it or one of the kinds under it.
  const elseShown = !gated || elseOpen || (!!kind && !featured.includes(kind)) || (found.data ?? []).some((s) => usingFound && kindId === s.endpoint);

  const spend = useSpendLine(guide);
  const hasSlot = useHasContinueSlot();
  const chooseWorkData = (answer: WorkData) => {
    setWorkData(answer);
    setLevels(answer === "allow" ? LEVELS.filter((l) => ALLOWED.includes(l) || levels.includes(l)) : ["open"]);
  };

  /** Why Continue can't be pressed yet, in words; nothing when it can. */
  const missing = (() => {
    if (!guide) return "";
    if (!kind) return props.done ? "" : t("welcome.ai.why.kind");
    if (added) return "";
    if (builtin && kind.installed === false) return t("welcome.ai.why.app");
    if (!keyReady) return t("welcome.ai.why.key");
    if (asksAddress(kind) && address.trim() === "") return t("welcome.ai.why.address");
    if (generic && command.trim() === "") return t("welcome.advanced.why_command");
    if (verdict.state === "checking") return t("welcome.ai.why.checking");
    if (verdict.state === "failed") return t("welcome.ai.why.failed");
    if (verdict.state === "idle" && (manualModel || (!builtin && list.length === 0 && asked)) && everyday.trim() === "") return t("welcome.ai.why.model");
    if (verdict.state === "idle") return t("welcome.ai.why.not_checked");
    if (workData === null) return t("welcome.ai.why.allow");
    if (!ready) return t("welcome.ai.why.not_ready");
    return "";
  })();
  const spendWhy = guide && spend.bad ? t("welcome.spend.bad") : "";

  /** Continue: saves the account, tests it, and saves the spending when it was changed. Stays put, saying why, when any of it
   * didn't work. */
  const carryOn = async (): Promise<boolean> => {
    if (kind) {
      const worked = added
        ? (() => test().then((tried) => !!tried && tried.length > 0 && tried.every((r) => r.ok)))()
        : await add();
      if (!(await worked)) return false;
    }
    if (spend.pending && !(await spend.save())) return false;
    if (kind) {
      setKindId("");
      setAdded(null);
      setVerdict({ state: "idle" });
      setWorkData(null);
    }
    return true;
  };
  useContinue(guide ? { run: carryOn, disabled: !!(missing || spendWhy), why: missing || spendWhy } : null);

  const kindChoice = (e: Kind) => (
    <label key={e.id} className={`radio kind-choice kind-card${e.recommended && guide ? " recommended" : ""}`}>
      <input type="radio" name="ai-kind" value={e.id} checked={kindId === e.id && !usingFound} onChange={() => choose(e.id)} />
      <span>
        {e.recommended && guide && <span className="pill tag-recommended">{t("welcome.ai.recommended")}</span>}
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

  /** Choosing another model starts the check again with it, since the check is of the model that will do the work. */
  const pickModel = (setter: (v: string) => void, which: "everyday" | "harder") => (value: string) => {
    setter(value);
    if (guide && kind && verdict.state !== "idle") void verify(kind, which === "everyday" ? { everyday: value } : { everyday, harder: value });
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

  /** The models the service lists, to choose from: the first is already chosen. */
  const modelFields = (
    <>
      {list.length > SEARCH_ABOVE && (
        <div className="field">
          <label htmlFor="ai-model-find">{t("welcome.ai.model_find")}</label>
          <input id="ai-model-find" type="search" value={filter} autoComplete="off" onChange={(e) => narrow(e.target.value)} />
          {noMatch && (
            <p className="hint" role="status">
              {t("welcome.ai.model_none")}
            </p>
          )}
        </div>
      )}
      {!noMatch && modelSelect({ id: "ai-model", label: t("welcome.ai.model_everyday"), value: everyday, onChange: pickModel(setEveryday, "everyday") })}
      {!noMatch &&
        modelSelect({ id: "ai-model-harder", label: t("welcome.ai.model_harder"), value: harder, onChange: pickModel(setHarder, "harder"), same: true })}
    </>
  );

  /** The three levels of what an account may see: how the drawer asks, and what Advanced holds in the guide. */
  const levelFields = (
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
      <p className="hint" data-internal-note="">
        {t("welcome.ai.data_internal_note")}
      </p>
    </fieldset>
  );

  /** How the check of a new account stands, as a line: checking, "Works", or what to do about it. */
  const verdictLine = (
    <div role="status" aria-live="polite" className="verdict">
      {verdict.state === "checking" && <p className="hint">{t("welcome.ai.checking_key")}</p>}
      {verdict.state === "works" && (
        <p className="check-ok" data-works="">
          <span aria-hidden="true">✓ </span>
          {t("welcome.ai.works")}
        </p>
      )}
      {verdict.state === "failed" && (
        <p className="problem-note" role="alert">
          {verdict.message}
        </p>
      )}
    </div>
  );

  /** The service's numbered steps: make an account, add credit, make a key and copy it, paste it. */
  const link = (url: string | null | undefined, label: string) => {
    const domain = url ? domainOf(url) : null;
    return url && domain ? (
      <a className="btn" href={url} target="_blank" rel="noopener noreferrer">
        {label} <span aria-hidden="true">↗</span>
        <span className="sr"> {t("welcome.ai.step.opens", { domain })}</span>
      </a>
    ) : null;
  };
  const step = (n: number, title: string, hint: string, action?: ReactNode, body?: ReactNode) => (
    <li className="numbered-step" key={n}>
      <span className="step-number" aria-hidden="true">
        {n}
      </span>
      <div className="step-text">
        <strong>{title}</strong>
        <span className="hint block">{hint}</span>
        {body}
      </div>
      {action && <div className="step-action">{action}</div>}
    </li>
  );
  const credit = spend.perDay != null && spend.perDay > 0 ? amount(Math.round(spend.perDay * 5)) : null;

  /** Where the key is pasted, or (on a hosted app) where it is kept; the check runs when it is pasted. */
  const keyField = !kind ? null : props.local ? (
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
          onBlur={(e) => {
            if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind, { key: e.target.value });
          }}
          onChange={(e) => {
            setKey(e.target.value);
            if (guide && e.target.value.trim() !== verifiedKey.current) {
              verifying.current += 1;
              setVerdict({ state: "idle" });
            }
          }}
          onPaste={(e) => {
            // A key pasted into an empty field is checked at once; typing waits until the cursor leaves the box.
            const pasted = e.clipboardData.getData("text").trim();
            if (key !== "" || !pasted) return;
            if (guide) void verify(kind, { key: pasted });
            else if (canList && (!asksAddress(kind) || address.trim() !== "")) void check(kind, { key: pasted });
          }}
        />
        <button type="button" className="btn small" aria-controls="ai-key" onClick={() => setShowKey((v) => !v)}>
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
        aria-describedby="ai-key-where-hint"
        onKeyDown={enterChecks}
        onBlur={(e) => {
          if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind);
        }}
        onChange={(e) => {
          setKeyRef(e.target.value);
          if (guide) {
            verifying.current += 1;
            setVerdict({ state: "idle" });
          }
        }}
      />
      <p className="hint" id="ai-key-where-hint">
        {t("welcome.ai.key_where_hint")}
      </p>
    </div>
  );

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
            {guide && <p className="hint">{t("welcome.ai.intro", { amount: credit ?? "" })}</p>}
            {gated && (
              <div className="kinds kind-grid" ref={firstKind}>
                {featured.map(kindChoice)}
                <label className="radio kind-choice kind-card">
                  <input type="radio" name="ai-kind" value="" checked={elseShown} onChange={() => setElseOpen(true)} />
                  <span>
                    <strong>{t("welcome.ai.else")}</strong>
                    <span className="hint block">{t("welcome.ai.else_note")}</span>
                  </span>
                </label>
              </div>
            )}
            {elseShown && (
              <div className={gated ? "else-list" : undefined}>
                {gated && <p className="hint">{t("welcome.ai.else_technical")}</p>}
                {(found.data ?? []).map((s) => {
                  const chosen = usingFound && kindId === s.endpoint;
                  return (
                    <div key={s.endpoint} className="found-local" data-chosen={chosen ? "true" : undefined}>
                      <p id={`ai-found-${s.endpoint}`}>
                        {s.models.length > 0 ? tn("welcome.ai.local_found", s.models.length, { name: s.name }) : t("welcome.ai.local_found_none", { name: s.name })}
                      </p>
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
                {(gated ? restServices : services).length > 0 && (
                  <div className="kinds kind-grid" ref={gated ? undefined : firstKind}>
                    {(gated ? restServices : services).map(kindChoice)}
                  </div>
                )}
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
              </div>
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
                    onChange={(e) => {
                      setAddress(e.target.value);
                      if (guide) {
                        verifying.current += 1;
                        setVerdict({ state: "idle" });
                      }
                    }}
                    onBlur={(e) => {
                      if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind, { address: e.target.value });
                    }}
                  />
                  <p className="hint" id="ai-address-hint">
                    {t(guide ? "welcome.ai.address_hint_guide" : "welcome.ai.address_hint")}
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
                    onClick={() =>
                      void endpoints.refetch().then((again) => {
                        const now = again.data?.find((e) => e.id === kind.id);
                        if (guide && now?.installed) void verify(now, { model: !now.model_optional ? (now.model_examples ?? [])[0] ?? "" : "" });
                      })
                    }
                  >
                    {t("welcome.ai.check")}
                  </button>
                </div>
              )}
              {generic && (
                <>
                  <div className="field">
                    <label htmlFor="ai-command">{t("welcome.advanced.command")}</label>
                    <input
                      id="ai-command"
                      type="text"
                      value={command}
                      autoComplete="off"
                      aria-describedby="ai-command-hint"
                      onChange={(e) => {
                        setCommand(e.target.value);
                        if (guide) {
                          verifying.current += 1;
                          setVerdict({ state: "idle" });
                        }
                      }}
                      onBlur={(e) => {
                        if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind, { command: e.target.value });
                      }}
                    />
                    <p className="hint" id="ai-command-hint">
                      {t("welcome.advanced.command_hint")}
                    </p>
                  </div>
                  <fieldset className="details">
                    <legend>{t("welcome.ai.packet_via")}</legend>
                    <div className="choice-row">
                      {(["stdin", "file"] as const).map((v) => (
                        <label key={v} className="check-line">
                          <input
                            type="radio"
                            name="ai-packet-via"
                            checked={packetVia === v}
                            onChange={() => {
                              setPacketVia(v);
                              if (guide && verdict.state !== "idle") void verify(kind, { packetVia: v });
                            }}
                          />
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
                          <input
                            type="radio"
                            name="ai-output-via"
                            checked={outputVia === v}
                            onChange={() => {
                              setOutputVia(v);
                              if (guide && verdict.state !== "idle") void verify(kind, { outputVia: v });
                            }}
                          />
                          <span>{t(`welcome.ai.output_via.${v}`)}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                </>
              )}
              {hasKeyField && (
                <section className="key-step" aria-labelledby="ai-key-steps">
                  {guide && kind.needs_key ? (
                    <>
                      <h4 id="ai-key-steps">{t("welcome.ai.steps_title", { name: kind.name })}</h4>
                      <ol className="plain-list numbered-steps">
                        {step(
                          1,
                          t("welcome.ai.step.account"),
                          t("welcome.ai.step.account_hint", { name: kind.name }),
                          link(kind.signup_url, t("welcome.ai.step.open_signup")),
                        )}
                        {step(
                          2,
                          t("welcome.ai.step.credit"),
                          credit ? t("welcome.ai.step.credit_hint", { amount: credit, day: amount(spend.perDay ?? 0) }) : t("welcome.ai.step.credit_hint_plain"),
                          link(kind.credit_url, t("welcome.ai.step.open_billing")),
                        )}
                        {step(3, t("welcome.ai.step.key"), t("welcome.ai.step.key_hint"), link(kind.key_url, t("welcome.ai.step.open_keys")))}
                        {step(
                          4,
                          t(props.local ? "welcome.ai.step.paste" : "welcome.ai.step.paste_hosted"),
                          t(props.local ? "welcome.ai.step.paste_hint" : "welcome.ai.key_where_hint"),
                          undefined,
                          keyField,
                        )}
                      </ol>
                    </>
                  ) : (
                    <>
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
                      {keyField}
                    </>
                  )}
                </section>
              )}
              {guide && verdictLine}
              {canList && !guide && (
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
                        onChange={(e) => {
                          setEveryday(e.target.value);
                          if (guide) {
                            verifying.current += 1;
                            setVerdict({ state: "idle" });
                          }
                        }}
                        onBlur={(e) => {
                          if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind, { everyday: e.target.value });
                        }}
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
                            if (guide && !other) void verify(kind, { everyday: e.target.value, model: e.target.value });
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
                            onChange={(e) => {
                              setEveryday(e.target.value);
                              if (guide) {
                                verifying.current += 1;
                                setVerdict({ state: "idle" });
                              }
                            }}
                            onBlur={(e) => {
                              if (guide && e.target.value.trim() !== "" && verdict.state === "idle") void verify(kind, { everyday: e.target.value });
                            }}
                          />
                          <p className="hint" id="ai-model-custom-hint">
                            {t("welcome.ai.model_agent_hint")}
                          </p>
                        </div>
                      )}
                    </>
                  ) : guide ? (
                    list.length > 0 && <p className="hint">{t("welcome.ai.model_auto")}</p>
                  ) : (
                    list.length > 0 && (
                      // The first model is already chosen; the choice is one line until the person asks to change it.
                      <details
                        className="more-options model-details"
                        open={modelsOpen || noMatch}
                        onToggle={(e) => setModelsOpen((e.currentTarget as HTMLDetailsElement).open)}
                      >
                        <summary>{t("welcome.ai.models_summary", { model: everyday || list[0].id })}</summary>
                        {modelFields}
                      </details>
                    )
                  )}
                </>
              )}
              {guide && verdict.state === "works" && (
                <fieldset className="details allow-question" data-allow-question="">
                  <legend>
                    {verdict.identity
                      ? t("welcome.ai.allow.title", { account: shownLabel, identity: verdict.identity })
                      : t("welcome.ai.allow.title_unknown", { account: shownLabel })}
                  </legend>
                  {!verdict.identity && verdict.unknown && <p className="hint">{t("welcome.ai.allow.unknown", { reason: verdict.unknown })}</p>}
                  {(["allow", "not_now"] as const).map((answer) => (
                    <label key={answer} className="radio kind-choice">
                      <input type="radio" name="ai-work-data" value={answer} checked={workData === answer} onChange={() => chooseWorkData(answer)} />
                      <span>
                        <strong>{t(`welcome.ai.allow.${answer}`)}</strong>
                        <span className="hint block">{t(`welcome.ai.allow.${answer}_note`)}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
              {!guide && levelFields}
              {drawer ? (
                <>
                  <div className="field">
                    <label htmlFor="ai-label">{t("ai_add.name")}</label>
                    <input
                      id="ai-label"
                      type="text"
                      value={shownLabel}
                      autoComplete="off"
                      aria-describedby="ai-label-hint"
                      onChange={(e) => {
                        setLabelText(e.target.value);
                        setLabelTouched(true);
                      }}
                    />
                    <p className="hint" id="ai-label-hint">
                      {t("ai_add.name_hint")}
                    </p>
                  </div>
                  <fieldset className="details">
                    <legend>{t("ai_add.for")}</legend>
                    {(["work", "backup", "none"] as const)
                      .filter((choice) => choice !== "backup" || mains.length > 0)
                      .map((choice) => (
                        <label key={choice} className="radio kind-choice">
                          <input type="radio" name="ai-for" value={choice} checked={chosenFor === choice} onChange={() => setForWhat(choice)} />
                          <span>
                            <strong>{t(`ai_add.for.${choice}`)}</strong>
                            <span className="hint block">
                              {choice === "work"
                                ? mains.length
                                  ? t("ai_add.for.work_note", { main: mainName })
                                  : t("ai_add.for.work_note_first")
                                : choice === "backup"
                                  ? checkUsd == null
                                    ? t("ai_add.for.backup_note_free", { main: mainName })
                                    : t("ai_add.for.backup_note", { main: mainName, amount: money(checkUsd) })
                                  : t("ai_add.for.none_note")}
                            </span>
                          </span>
                        </label>
                      ))}
                  </fieldset>
                </>
              ) : null}
              {guide && spend.node}
              <details className="more-options advanced">
                <summary>{t("welcome.ai.advanced")}</summary>
                {!drawer && (
                  <div className="field">
                    <label htmlFor="ai-name">{t("welcome.ai.name")}</label>
                    <input
                      id="ai-name"
                      type="text"
                      value={shownLabel}
                      autoComplete="off"
                      aria-describedby="ai-name-hint"
                      onChange={(e) => {
                        setLabelText(e.target.value);
                        setLabelTouched(true);
                      }}
                    />
                    <p className="hint" id="ai-name-hint">
                      {t("welcome.ai.name_hint")}
                    </p>
                  </div>
                )}
                {guide && !builtin && !manualModel && list.length > 0 && modelFields}
                {guide && levelFields}
                {guide && (
                  <label className="check-line">
                    <input type="checkbox" checked={useForWork} onChange={(e) => setUseForWork(e.target.checked)} />
                    <span>{t("welcome.ai.everyday")}</span>
                  </label>
                )}
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
              {overLimit && askedGo && checkUsd != null && (
                <p className="hint" role="alert">
                  {t("ai_add.over", { amount: money(checkUsd), limit: money(confirmAbove) })}
                </p>
              )}
              {problem && (
                <p className="problem-note" role="alert">
                  {problem}
                </p>
              )}
              {drawer && (
                <div className="row-end">
                  <button type="button" className="btn quiet" disabled={busy} onClick={drawer.onCancel}>
                    {t("ai_add.cancel")}
                  </button>
                  <button type="button" className="btn primary" disabled={!ready} onClick={addOrAsk}>
                    {busy
                      ? t("ai_add.adding")
                      : chosenFor === "none"
                        ? t("ai_add.add")
                        : checkUsd == null
                          ? t("ai_add.add_check")
                          : overLimit && askedGo
                            ? t("ai_add.go_ahead", { amount: money(checkUsd) })
                            : t("ai_add.add_check_cost", { amount: money(checkUsd) })}
                  </button>
                </div>
              )}
            </>
          )}
          {guide && !kind && spend.node}
          {guide && !hasSlot && (
            <div className="row-end">
              <Button variant="primary" loading={busy || testing} disabled={!!(missing || spendWhy)} reason={missing || spendWhy || undefined} onClick={() => void carryOn()}>
                {t("welcome.ai.save")}
              </Button>
            </div>
          )}
        </form>
      )}
      {guide && (
        <>
          <AiAccounts local={props.local} level={4} />
          <div className="guide-test">
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
        </>
      )}
    </div>
  );
}
