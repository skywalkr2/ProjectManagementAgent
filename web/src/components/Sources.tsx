// Sources: the places the assistant keeps reading, one row each with how often it reads and how the last read went,
// and under them the mail set aside as not work (the Set aside folder) and what a rule closed without the assistant
// reading it, each with a way to hand it in after all.
// A source is added from a kind (the app's own or an add-on's) with a form built from that kind's settings; a row's menu
// reads it now, changes it, turns it off or on, and removes it, each with Undo. Sources are taken in without a restart.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText as when } from "../lib/dates";
import { problemText } from "../lib/problem";
import { startCursor } from "../lib/cursor";
import { projectChoices } from "../lib/project-choices";
import { failureText } from "../lib/sources";
import { changedTime, reconcile, type Refreshed } from "../lib/refreshed";
import { addonLabel, formatValue, formValues, labelOf, nest, prefill, valueAt, type Draft } from "../lib/settings";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";
import { restoreFocus } from "./ModalPanel";
import { RefreshedLines } from "./RefreshedLines";
import { ItemFields } from "./SettingRow";
import { SetAside } from "./SetAside";
import { SignIns } from "./SignIns";
import { Skeleton } from "../ui/Skeleton";

type Source = S["WatchSourceView"];
type Closed = S["AutoClosedView"];
type SilentClose = S["SilentCloseView"];
type Kind = S["WatchKindView"];
/** Opens the add form: from a sign-in, only the kinds of that sign-in's add-on; `n` tells one request from the next. */
export interface AddRequest {
  plugin: string | null;
  n: number;
}

type T = (key: string, vars?: Record<string, string | number>) => string;

/** How the last read went, in words. A failed read says it failed here; its reason is shown beside it. */
export function lastReadText(source: Source, t: T): string {
  const last = source.last;
  if (!last) return t("sources.never");
  switch (last.outcome) {
    case "ok":
      // Only what there is: "2 new, 1 removed", never "0 changed".
      return last.new + last.changed + last.removed === 0
        ? t("sources.last.nothing")
        : [
            last.new > 0 ? t("sources.last.new", { n: last.new }) : "",
            last.changed > 0 ? t("sources.last.changed", { n: last.changed }) : "",
            last.removed > 0 ? t("sources.last.gone", { n: last.removed }) : "",
          ]
            .filter(Boolean)
            .join(", ");
    case "baseline":
      return t("sources.last.baseline");
    case "offline":
      return t("sources.last.offline");
    default:
      return t("sources.last.failed");
  }
}

/** Why a source can't be read, while its last read failed. */
export function problemOf(source: Source, t: T, has: (key: string) => boolean): string | null {
  if (source.last?.outcome !== "failed") return null;
  return failureText(source, t, has) || t("sources.problem_generic");
}

type Form = { type: "add"; plugin: string | null } | { type: "change"; id: string };

/** How often a source can be read, in minutes. */
const EVERY_CHOICES = [15, 30, 60, 240];

/** Saving a change to the list of sources: the fresh fingerprint, the save, then the read-back with Undo. A refusal is
 * said in a toast. */
function useSourceSave() {
  const { t } = useWords();
  const { push } = useToasts();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  return useCallback(
    async (run: (fingerprint: string) => Promise<S["SettingsSaved"]>, message: string): Promise<boolean> => {
      try {
        const saved = await run(await fingerprint());
        await afterSave(saved, { message });
        return true;
      } catch (err) {
        const detail = err instanceof ApiError ? err.detail : "";
        push({ message: err instanceof ApiError && err.status === 401 ? t("error.signed_out") : t("error.failed", { detail }) });
        return false;
      }
    },
    [fingerprint, afterSave, push, t],
  );
}

export function Sources(props: {
  onAsk: (question?: string) => void;
  add?: AddRequest | null;
  /** The request to add one has been taken up, so it isn't repeated the next time the screen opens. */
  onAddOpened?: () => void;
  /** Opens Add-ons, from the accounts section when no add-on signs in to a service yet. */
  onOpenAddons?: () => void;
}) {
  const { t } = useWords();
  // A source that has never been read is checked on again soon: it is read within a minute of being added.
  const sources = useQuery({
    queryKey: ["watch"],
    queryFn: api.watchSources,
    refetchInterval: (query) => (query.state.data?.some((s) => s.enabled && !s.last) ? 15_000 : false),
  });
  const kinds = useQuery({ queryKey: ["watch-kinds"], queryFn: api.watchKinds });
  const [form, setForm] = useState<Form | null>(() => (props.add ? { type: "add", plugin: props.add.plugin } : null));
  const [seen, setSeen] = useState(props.add?.n ?? 0);
  // Another request to add one (from Today or a sign-in) opens the form again, on its kinds.
  if (props.add && props.add.n !== seen) {
    setSeen(props.add.n);
    setForm({ type: "add", plugin: props.add.plugin });
  }
  const { add, onAddOpened } = props;
  useEffect(() => {
    if (add) onAddOpened?.();
  }, [add, onAddOpened]);
  // Only a failure already there when the screen opened is announced at once; later refreshes don't repeat it.
  const [announce, setAnnounce] = useState<Set<string> | null>(null);
  if (sources.data && announce === null) {
    setAnnounce(new Set(sources.data.filter((s) => s.failures >= 1).map((s) => s.id)));
  }
  const addButton = "source-add-button";
  const closeAdd = () => {
    setForm(null);
    restoreFocus(() => document.getElementById(addButton));
  };
  return (
    <section className="panel-section" aria-labelledby="sources-title">
      <div className="heading">
        <h1 id="sources-title">{t("sources.title")}</h1>
        <div className="acts">
          <button
            type="button"
            id={addButton}
            className="btn primary"
            aria-expanded={form?.type === "add"}
            onClick={() => setForm({ type: "add", plugin: null })}
          >
            {t("sources.add")}
          </button>
        </div>
      </div>
      <p className="hint">{t("sources.intro")}</p>
      <SignIns
        onOpenAddons={() => props.onOpenAddons?.()}
        onChooseSource={(plugin) => setForm({ type: "add", plugin })}
      />
      {form?.type === "add" && (
        <SourceForm
          key={`add-${seen}-${form.plugin ?? ""}`}
          mode={{ type: "add", plugin: form.plugin }}
          kinds={kinds.data}
          kindsFailed={kinds.isError}
          onClose={closeAdd}
        />
      )}
      {sources.isPending ? (
        <Skeleton />
      ) : sources.isError ? (
        <p className="empty">
          {t("sources.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void sources.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : sources.data.length === 0 ? (
        <div className="empty">
          <p>{t("sources.empty")}</p>
          <p>
            <button type="button" className="btn" onClick={() => props.onAsk(t("sources.ask_text"))}>
              {t("sources.empty_ask")}
            </button>
          </p>
        </div>
      ) : (
        <ul className="queue">
          {sources.data.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              alert={announce?.has(source.id) ?? false}
              kinds={kinds.data}
              kindsFailed={kinds.isError}
              changing={form?.type === "change" && form.id === source.id}
              onChange={() => setForm({ type: "change", id: source.id })}
              onChanged={() => setForm(null)}
            />
          ))}
        </ul>
      )}
      <SetAside />
      <AutoClosed />
      <SilentCloses />
    </section>
  );
}

function SourceRow(props: {
  source: Source;
  alert: boolean;
  kinds: Kind[] | undefined;
  kindsFailed: boolean;
  changing: boolean;
  onChange: () => void;
  onChanged: () => void;
}) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const save = useSourceSave();
  const [busy, setBusy] = useState(false);
  const { source } = props;
  const titleId = `source-${source.id}`;
  const menuId = `${titleId}-menu`;
  const problem = problemOf(source, t, has);
  const lastWhen = source.read_at ? when(source.read_at) : "";
  const lastWords = lastReadText(source, t);

  const readNow = async () => {
    setBusy(true);
    await act(
      async () => {
        const fresh = await api.readSource(source.id);
        // Show what the read found at once, without waiting for the list to be fetched again.
        client.setQueryData<Source[]>(["watch"], (all) => all?.map((s) => (s.id === fresh.id ? fresh : s)));
        return fresh;
      },
      (fresh) => ({ message: t("sources.read_toast", { label: fresh.label, result: problemOf(fresh, t, has) ?? lastReadText(fresh, t) }) }),
    );
    setBusy(false);
  };
  // After a first read that only noted what was there: hand the assistant the recent past and near future now.
  const recent = () =>
    void act(
      () => api.handInRecent(source.id),
      () => ({ message: t("sources.recent_toast", { label: source.label }) }),
    );
  const turn = (enabled: boolean) =>
    void save(
      (fingerprint) => api.changeSource(source.id, { enabled, fingerprint }),
      t(enabled ? "sources.turned_on_toast" : "sources.turned_off_toast", { label: source.label }),
    );
  const remove = () =>
    void save((fingerprint) => api.removeSource(source.id, fingerprint), t("sources.removed_toast", { label: source.label }));

  const actions: MenuAction[] = [
    { id: "read", label: t("sources.read_now"), run: () => void readNow(), disabled: !source.enabled || busy },
    { id: "recent", label: t("sources.recent"), run: recent, disabled: busy || source.items === 0 },
    { id: "change", label: t("sources.change"), run: props.onChange },
    { id: "power", label: t(source.enabled ? "sources.turn_off" : "sources.turn_on"), run: () => turn(!source.enabled) },
    { id: "remove", label: t("sources.remove"), run: remove },
  ];

  // Until a read has worked there is no count to give: "0 items" would say it was read and found nothing.
  const facts = [
    source.connector_label || t("sources.kind_none"),
    source.read_at && source.items > 0 ? tn("sources.items", source.items) : "",
    ...(source.author_name ? [t("sources.written_by", { name: source.author_name })] : []),
    ...(source.account ? [t("sources.reads_account", { account: source.account })] : []),
  ].filter(Boolean);
  const schedule = [
    source.enabled ? tn("sources.read_every", source.every_minutes) : t("sources.off"),
    source.read_at ? t("sources.last_read", { when: lastWhen }) : t("sources.never"),
  ];
  const found = [source.last ? lastWords : "", source.failures > 1 ? t("sources.failures", { n: source.failures }) : ""].filter(Boolean);
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row pair">
        <div className="text">
          <strong id={titleId}>{source.label}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          <span className="sub">{schedule.join(" · ")}</span>
          {found.length > 0 && <span className="sub">{found.join(" · ")}</span>}
          {source.last?.unsorted && (
            <p className="hint" data-unsorted="">
              <strong>{t("sources.unsorted")}</strong> {source.last.unsorted}
            </p>
          )}
          {problem && (
            <p className="problem-note" role={props.alert ? "alert" : undefined}>
              {problem}
            </p>
          )}
          {source.connector === "mailbox" && source.enabled && !problem && <SentFolderOffer source={source} save={save} />}
        </div>
        <div className="acts">
          <RowMenu label={source.label} actions={actions} buttonId={menuId} />
        </div>
      </div>
      {props.changing && (
        <SourceForm
          mode={{ type: "change", source }}
          kinds={props.kinds}
          kindsFailed={props.kindsFailed}
          onClose={() => {
            props.onChanged();
            restoreFocus(() => document.getElementById(menuId));
          }}
        />
      )}
    </li>
  );
}

/** One line under a mailbox: the folder of mail the person sent, as a second source, so promises they make are noticed. The
 * list is the mailbox's own, with the folder its server marks as sent picked already (the person picks when it marks none);
 * a folder already read isn't offered. It is taken in quietly like any new source. */
function SentFolderOffer(props: { source: Source; save: ReturnType<typeof useSourceSave> }) {
  const { t } = useWords();
  const id = useId();
  const found = useQuery({ queryKey: ["watch-folders", props.source.id], queryFn: () => api.watchFolders(props.source.id), retry: false, staleTime: 300_000 });
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const data = found.data;
  if (!data) return null;
  const taken = data.taken ?? [];
  const options = data.folders.filter((f) => !taken.includes(f));
  if (options.length === 0 || (data.sent && taken.includes(data.sent))) return null;
  const marked = data.sent && options.includes(data.sent) ? data.sent : "";
  const folder = picked ?? marked;
  const add = async () => {
    setBusy(true);
    await props.save((fingerprint) => api.addSentFolder(props.source.id, { folder, label: t("sources.sent.label", { label: props.source.label }), fingerprint }), t("sources.sent.added_toast", { label: props.source.label }));
    setBusy(false);
  };
  return (
    <div className="sent-offer" data-sent-offer="">
      <label className="sub" htmlFor={id}>
        {t("sources.sent.offer")}
      </label>
      <select id={id} aria-label={t("sources.sent.folder")} value={folder} onChange={(e) => setPicked(e.target.value)}>
        {!marked && <option value="">{t("sources.sent.choose")}</option>}
        {options.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>
      <button type="button" className="btn small" disabled={!folder || busy} onClick={() => void add()}>
        {t("sources.sent.add")}
      </button>
    </div>
  );
}

type Mode = { type: "add"; plugin: string | null } | { type: "change"; source: Source };

/** The form for adding a source or changing one: the kind (adding only), a name, how often, a project (adding only)
 * and the settings that kind takes, as the Settings screen shows them. */
function SourceForm(props: { mode: Mode; kinds: Kind[] | undefined; kindsFailed: boolean; onClose: () => void }) {
  const { t, tn, has } = useWords();
  const afterSave = useAfterSave();
  const fresh = useFreshFingerprint();
  const client = useQueryClient();
  const base = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const { mode } = props;
  const adding = mode.type === "add";
  const source = mode.type === "change" ? mode.source : null;

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: !adding });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: adding });
  const authors = useQuery({ queryKey: ["watch-authors"], queryFn: api.watchAuthors });
  // Whether the app can keep a typed secret: a hosted app takes only where it is kept.
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });

  const available = (props.kinds ?? []).filter((k) => mode.type !== "add" || !mode.plugin || k.plugin === mode.plugin);
  const [picked, setPicked] = useState<string | null>(null);
  const chosen = source ? source.connector : (picked ?? (available.length === 1 ? available[0].name : ""));
  const kind = (props.kinds ?? []).find((k) => k.name === chosen);

  const [label, setLabel] = useState(source?.label ?? "");
  const [every, setEvery] = useState(String(source?.every_minutes ?? 60));
  const [project, setProject] = useState("");
  const [author, setAuthor] = useState(source?.author ?? "");
  const [account, setAccount] = useState(source?.account ?? "");
  const [edits, setEdits] = useState<Record<string, Draft>>({});
  const [pasted, setPasted] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  // The settings as they were when the form opened: what the typed values were made from. A save sends this one, so a
  // change made meanwhile is refused rather than overwritten; it moves on only after the person was told.
  const [opened, setOpened] = useState<string | null>(null);
  // What the form showed when it opened (or was last refreshed), to tell which fields the person touched after a refusal,
  // and what a refusal refreshed.
  const shown = useRef({ label: source?.label ?? "", every: String(source?.every_minutes ?? 60), author: source?.author ?? "", account: source?.account ?? "" });
  const storedWas = useRef<unknown>(undefined);
  const [refreshed, setRefreshed] = useState<{ lines: Refreshed[]; time: string }>({ lines: [], time: "" });

  // The cursor starts in the form's first field (the kind to add, else the name), or on its heading until one has loaded.
  const formEl = useRef<HTMLFormElement>(null);
  useEffect(() => {
    heading.current?.scrollIntoView?.({ block: "nearest" });
    return formEl.current ? startCursor(formEl.current, `${base}-title`) : undefined;
    // Once, when the form opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let live = true;
    fresh().then(
      (fp) => live && setOpened((kept) => kept ?? fp),
      (err) => live && setProblem(problemText(err, t)),
    );
    return () => {
      live = false;
    };
    // Read once, when the form opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A source's own settings are read from the saved settings; without them only its name, schedule and on/off can change.
  const stored = (() => {
    if (!source || !settings.data) return undefined;
    const list = settings.data.items.find((i) => i.key === "watch.sources")?.value;
    if (!Array.isArray(list)) return undefined;
    const mine = list.find((entry) => typeof entry === "object" && entry !== null && (entry as { id?: unknown }).id === source.id);
    return mine ? ((mine as { settings?: unknown }).settings ?? {}) : undefined;
  })();
  useEffect(() => {
    if (storedWas.current === undefined) storedWas.current = stored;
  }, [stored]);
  const waitingForSettings = !adding && settings.isPending;
  const items = kind && !waitingForSettings && (adding || stored !== undefined) ? (adding ? kind.items : prefill(kind.items, stored)) : [];
  const { values, bad } = formValues(items, edits);
  // A secret typed here is sent apart from the settings, and replaces whatever the setting held.
  const typed = Object.fromEntries(Object.entries(pasted).filter(([key, value]) => value.trim() !== "" && items.some((i) => i.key === key)));
  const sent = Object.fromEntries(Object.entries(values).filter(([key]) => !(key in typed)));
  const secret = {
    local: setup.data?.local ?? true,
    held: Object.fromEntries((source?.secrets ?? []).map((x) => [x.field, { where: x.where, name: x.name }])),
    pasted,
    onPaste: (key: string, value: string) => setPasted((all) => ({ ...all, [key]: value })),
  };

  const groups = (() => {
    const order: Array<{ id: string; label: string; kinds: Kind[] }> = [];
    for (const k of available) {
      const id = k.plugin ?? "";
      let group = order.find((g) => g.id === id);
      if (!group) {
        group = { id, label: k.plugin ? addonLabel(k.plugin, t, has) : t("sources.kind_core"), kinds: [] };
        order.push(group);
      }
      group.kinds.push(k);
    }
    return [...order.filter((g) => g.id === ""), ...order.filter((g) => g.id !== "")];
  })();

  const everyOptions = [...new Set([...EVERY_CHOICES, Number(every)])].filter((n) => Number.isFinite(n) && n > 0).sort((a, b) => a - b);
  const choices = projectChoices(projects.data ?? [], (parent, name) => t("handin.project.path", { parent, name }));
  // A kind from an add-on that signs in as the person has a list of accounts to read: the only one is chosen already,
  // and with several one must be chosen. The source's own account stays in the list when it was signed out since.
  const accountList = kind?.accounts ?? null;
  const accountChoices = accountList ? [...new Set([...(accountList ?? []), ...(account ? [account] : [])])] : [];
  const accountChosen = accountList === null ? "" : account || (accountList.length === 1 ? accountList[0] : "");
  const accountMissing = accountList !== null && accountList.length > 1 && accountChosen === "";
  const ready = kind !== undefined && !busy && bad.length === 0 && opened !== null && !accountMissing;

  /** After a refusal: what the person didn't touch takes what is saved now and is listed; what they typed stays. */
  const refreshForm = async (was: Source, of: Kind) => {
    try {
      const [list, view] = await Promise.all([
        client.fetchQuery({ queryKey: ["watch"], queryFn: api.watchSources, staleTime: 0 }),
        client.fetchQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 0 }),
      ]);
      const now = list.find((x) => x.id === was.id);
      if (!now) return;
      const saved = { label: now.label, every: String(now.every_minutes), author: now.author ?? "", account: now.account ?? "" };
      const out = reconcile<string>(shown.current, { label, every, author, account }, saved);
      setLabel(out.next.label);
      setEvery(out.next.every);
      setAuthor(out.next.author);
      setAccount(out.next.account);
      shown.current = saved;
      const lines: Refreshed[] = [];
      const words: Record<string, string> = { label: t("sources.field.label"), every: t("sources.field.every"), author: t("sources.field.author"), account: t("sources.field.account") };
      for (const key of out.refreshed) {
        const value = key === "every" ? tn("sources.every", now.every_minutes) : saved[key as keyof typeof saved] || t("settings.empty");
        lines.push({ label: words[key], value });
      }
      const list2 = view.items.find((i) => i.key === "watch.sources")?.value;
      const mine = Array.isArray(list2) ? list2.find((e) => typeof e === "object" && e !== null && (e as { id?: unknown }).id === was.id) : undefined;
      const storedNow = mine ? ((mine as { settings?: unknown }).settings ?? {}) : undefined;
      if (storedNow !== undefined) {
        for (const item of of.items) {
          const before = valueAt(storedWas.current ?? {}, item.key);
          const after = valueAt(storedNow, item.key);
          if (item.key in edits || JSON.stringify(before ?? null) === JSON.stringify(after ?? null)) continue;
          lines.push({ label: labelOf(item, t, has), value: formatValue(after, t) });
        }
        storedWas.current = storedNow;
      }
      setRefreshed({ lines, time: changedTime(view) });
    } catch {
      // Without the current list the form can't be refreshed; the next look at the screen finds the cause.
    }
  };

  const submit = async () => {
    if (!ready || !kind || opened === null) return;
    setBusy(true);
    setProblem("");
    try {
      const fp = opened;
      const minutes = Number(every);
      const name = label.trim();
      if (mode.type === "add") {
        const saved = await api.addSource({
          connector: kind.name,
          label: name,
          every_minutes: minutes,
          project: project || null,
          author: author || null,
          ...(accountList !== null && accountChosen ? { account: accountChosen } : {}),
          settings: nest(sent),
          ...(Object.keys(typed).length > 0 ? { secrets: typed } : {}),
          fingerprint: fp,
        });
        await afterSave(saved, { message: t("sources.added_toast", { label: name || kind.label, every: tn("sources.every", minutes) }) });
      } else {
        const saved = await api.changeSource(mode.source.id, {
          ...(name ? { label: name } : {}),
          every_minutes: minutes,
          author: author || null,
          ...(accountList !== null && accountChosen ? { account: accountChosen } : {}),
          ...(items.length > 0 ? { settings: nest(sent) } : {}),
          ...(Object.keys(typed).length > 0 ? { secrets: typed } : {}),
          fingerprint: fp,
        });
        await afterSave(saved, { message: t("sources.changed_toast", { label: name || mode.source.label }) });
      }
      props.onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Said once, with what was typed kept; the next save is the person's own, on what is saved now.
        void client.invalidateQueries({ queryKey: ["settings"] });
        setProblem(t("settings.changed_since_opened"));
        try {
          setOpened(await fresh());
        } catch {
          // Without a current fingerprint the form can't save, and the next look at the settings finds the cause.
        }
        if (source && kind) await refreshForm(source, kind);
      } else {
        setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      }
      setBusy(false);
    }
  };

  const titleId = `${base}-title`;
  return (
    <form
      ref={formEl}
      className="panel source-form"
      aria-labelledby={titleId}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h3 id={titleId} tabIndex={-1} ref={heading}>
        {source ? t("sources.change_title", { label: source.label }) : t("sources.add_title")}
      </h3>
      {adding && (
        <fieldset className="details">
          <legend>{t("sources.kind_title")}</legend>
          {props.kindsFailed ? (
            <p className="problem-note">{t("sources.kinds_failed")}</p>
          ) : props.kinds === undefined ? (
            <p className="hint">{t("loading")}</p>
          ) : available.length === 0 ? (
            <p className="hint">{t("sources.kinds_none")}</p>
          ) : (
            groups.map((group) => {
              const groupId = `${base}-group-${group.id || "core"}`;
              return (
                <div key={group.id} role="group" className="kind-group" aria-labelledby={groups.length > 1 ? groupId : undefined}>
                  {groups.length > 1 && (
                    <p className="what" id={groupId}>
                      {group.label}
                    </p>
                  )}
                  <div className="kinds kind-grid">
                    {group.kinds.map((k) => (
                      <label key={k.name} className="radio kind-choice kind-card">
                        <input
                          type="radio"
                          name={`${base}-kind`}
                          value={k.name}
                          checked={chosen === k.name}
                          onChange={() => {
                            setPicked(k.name);
                            setEdits({});
                            setPasted({});
                          }}
                        />
                        <span>
                          <strong>{k.label}</strong>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </fieldset>
      )}
      {kind && (
        <>
          <div className="field">
            <label htmlFor={`${base}-label`}>{t("sources.field.label")}</label>
            <input
              id={`${base}-label`}
              type="text"
              value={label}
              autoComplete="off"
              aria-describedby={`${base}-label-hint`}
              onChange={(e) => setLabel(e.target.value)}
            />
            <p className="hint" id={`${base}-label-hint`}>
              {t("sources.field.label_hint")}
            </p>
          </div>
          <div className="field">
            <label htmlFor={`${base}-every`}>{t("sources.field.every")}</label>
            <select id={`${base}-every`} value={every} onChange={(e) => setEvery(e.target.value)}>
              {everyOptions.map((n) => (
                <option key={n} value={String(n)}>
                  {tn("sources.every", n)}
                </option>
              ))}
            </select>
          </div>
          {adding && (kind.first_run === "baseline" || kind.first_run === "intake") && (
            <p className="hint" data-first-read="">
              {t(kind.first_run === "intake" ? "sources.first_read_intake" : "sources.first_read_noted")}
            </p>
          )}
          {adding && choices.length > 0 && (
            <div className="field">
              <label htmlFor={`${base}-project`}>{t("sources.field.project")}</label>
              <select id={`${base}-project`} value={project} onChange={(e) => setProject(e.target.value)}>
                <option value="">{t("sources.field.no_project")}</option>
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {accountList !== null && (
            <div className="field">
              <label htmlFor={`${base}-account`}>{t("sources.field.account")}</label>
              <select
                id={`${base}-account`}
                value={accountChosen}
                aria-describedby={`${base}-account-hint`}
                onChange={(e) => setAccount(e.target.value)}
              >
                {accountChosen === "" && <option value="">{t("sources.field.choose_account")}</option>}
                {accountChoices.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
              <p className="hint" id={`${base}-account-hint`}>
                {t("sources.field.account_hint")}
              </p>
            </div>
          )}
          {(authors.data?.length ?? 0) > 0 && (
            <div className="field">
              <label htmlFor={`${base}-author`}>{t("sources.field.author")}</label>
              <select
                id={`${base}-author`}
                value={author}
                aria-describedby={`${base}-author-hint`}
                onChange={(e) => setAuthor(e.target.value)}
              >
                <option value="">{t("sources.field.no_author")}</option>
                {(authors.data ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.kind === "you" ? t("sources.field.author_you", { name: a.name }) : a.name}
                  </option>
                ))}
              </select>
              <p className="hint" id={`${base}-author-hint`}>
                {t("sources.field.author_hint")}
              </p>
            </div>
          )}
          {waitingForSettings && <p className="hint">{t("loading")}</p>}
          {items.length > 0 && (
            <fieldset className="details">
              <legend>{t("sources.details")}</legend>
              <ItemFields items={items} edits={edits} onEdit={(key, draft) => setEdits((all) => ({ ...all, [key]: draft }))} disabled={busy} idPrefix={`${base}-`} secret={secret} />
            </fieldset>
          )}
        </>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      <RefreshedLines lines={refreshed.lines} time={refreshed.time} />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!ready}>
          {t(busy ? "sources.saving" : adding ? "sources.save_add" : "sources.save_change")}
        </button>
      </div>
    </form>
  );
}

function AutoClosed() {
  const { t } = useWords();
  const closed = useQuery({ queryKey: ["auto-closed"], queryFn: api.autoClosed });
  return (
    <section className="panel-section" aria-labelledby="auto-closed-title">
      <div className="heading">
        <h3 id="auto-closed-title">{t("sources.closed.title")}</h3>
      </div>
      <p className="hint">{t("sources.closed.intro")}</p>
      {closed.isPending ? (
        <Skeleton />
      ) : closed.isError ? (
        <p className="empty">
          {t("sources.closed.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void closed.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : closed.data.length === 0 ? (
        <p className="empty">{t("sources.closed.empty")}</p>
      ) : (
        <ul className="queue">
          {closed.data.map((item) => (
            <ClosedRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ClosedRow(props: { item: Closed }) {
  const { t } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const { item } = props;
  const titleId = `closed-${item.id}`;
  const lookCloser = async () => {
    setBusy(true);
    await act(
      () => api.closerLook(item.id, item.version),
      () => ({ message: t("sources.closed.toast", { title: item.title }) }),
    );
    setBusy(false);
  };
  const facts = [item.source, when(item.created_at)].filter(Boolean);
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-done">{t(`sources.closed.change.${item.change}`)}</span>
        <div className="text">
          <strong id={titleId}>{item.title}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          <span className="sub">{t("sources.closed.why", { reason: item.reason })}</span>
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            disabled={busy}
            aria-label={t("sources.closed.look_named", { title: item.title })}
            onClick={() => void lookCloser()}
          >
            {t("sources.closed.look")}
          </button>
        </div>
      </div>
    </li>
  );
}

/** Every close nobody has seen: a rule's, the sorting's, the assistant's own drops and closes, with what, when, by whom
 * and why, and the share of all closes they are. Looks right marks a rule's or the assistant's close as seen; set-aside
 * mail is reviewed in its folder above. */
function SilentCloses() {
  const { t } = useWords();
  const found = useQuery({ queryKey: ["silent-closes"], queryFn: api.silentCloses });
  return (
    <section className="panel-section" aria-labelledby="silent-closes-title">
      <div className="heading">
        <h3 id="silent-closes-title">{t("sources.silent.title")}</h3>
      </div>
      <p className="hint">{t("sources.silent.intro")}</p>
      {found.isPending ? (
        <Skeleton />
      ) : found.isError ? (
        <p className="empty">
          {t("sources.silent.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void found.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : (
        <>
          {found.data.measure.total > 0 ? (
            <p className="hint" data-testid="silent-measure">
              {found.data.measure.silent === 0
                ? t("sources.silent.measure_none", { days: found.data.measure.days })
                : t("sources.silent.measure", {
                    silent: found.data.measure.silent,
                    total: found.data.measure.total,
                    days: found.data.measure.days,
                  })}
            </p>
          ) : null}
          {found.data.closes.length === 0 ? (
            <p className="empty">{t("sources.silent.empty")}</p>
          ) : (
            <ul className="queue">
              {found.data.closes.map((item) => (
                <SilentCloseRow key={item.ref} item={item} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function SilentCloseRow(props: { item: SilentClose }) {
  const { t } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const { item } = props;
  const titleId = `silent-${item.ref}`;
  const seen = async () => {
    setBusy(true);
    await act(
      () => api.closeSeen(item.ref),
      () => ({ message: t("sources.silent.toast", { title: item.title }) }),
    );
    setBusy(false);
  };
  const by = item.rule ? t("sources.silent.by_rule", { rule: item.rule }) : t("sources.silent.by_assistant");
  const facts = [by, when(item.when)].filter(Boolean);
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-done">{t(`sources.silent.how.${item.how}`)}</span>
        <div className="text">
          <strong id={titleId}>{item.title}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          {item.why ? <span className="sub">{t("sources.silent.why", { reason: item.why })}</span> : null}
          {item.kind === "set_aside" ? <span className="sub">{t("sources.silent.in_folder")}</span> : null}
        </div>
        {item.kind === "set_aside" ? null : (
          <div className="acts">
            <button
              type="button"
              className="btn primary"
              data-key="primary"
              disabled={busy}
              aria-label={t("sources.silent.seen_named", { title: item.title })}
              onClick={() => void seen()}
            >
              {t("sources.silent.seen")}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
