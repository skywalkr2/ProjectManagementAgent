// Sources: the places the assistant keeps reading, one row each with how often it reads and how the last read went,
// and under them what a rule set aside without the assistant reading it, with a way to hand any of it in after all.
// A source is added from a kind (the app's own or an add-on's) with a form built from that kind's settings; a row's menu
// reads it now, changes it, turns it off or on, and removes it, each with Undo. Sources are taken in without a restart.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText as when } from "../lib/dates";
import { problemText } from "../lib/problem";
import { projectChoices } from "../lib/project-choices";
import { addonLabel, formValues, nest, prefill, type Draft } from "../lib/settings";
import { useAfterSave, useFreshFingerprint } from "../lib/settings-save";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { RowMenu, type MenuAction } from "./RowMenu";
import { restoreFocus } from "./ModalPanel";
import { ItemFields } from "./SettingRow";

type Source = S["WatchSourceView"];
type Closed = S["AutoClosedView"];
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
      return last.new + last.changed + last.removed === 0
        ? t("sources.last.nothing")
        : t("sources.last.counts", { new: last.new, changed: last.changed, gone: last.removed });
    case "baseline":
      return t("sources.last.baseline");
    case "offline":
      return t("sources.last.offline");
    default:
      return t("sources.last.failed");
  }
}

/** Why a source can't be read, while its last read failed. */
export function problemOf(source: Source, t: T): string | null {
  if (source.last?.outcome !== "failed") return null;
  return source.problem || source.last.error || t("sources.problem_generic");
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
        <h2 id="sources-title">{t("sources.title")}</h2>
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
        <p className="empty">{t("loading")}</p>
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
      <AutoClosed />
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
  const { t, tn } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const save = useSourceSave();
  const [busy, setBusy] = useState(false);
  const { source } = props;
  const titleId = `source-${source.id}`;
  const menuId = `${titleId}-menu`;
  const problem = problemOf(source, t);
  const lastWhen = source.last ? when(source.last.started_at) : "";
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
      (fresh) => ({ message: t("sources.read_toast", { label: fresh.label, result: problemOf(fresh, t) ?? lastReadText(fresh, t) }) }),
    );
    setBusy(false);
  };
  const turn = (enabled: boolean) =>
    void save(
      (fingerprint) => api.changeSource(source.id, { enabled, fingerprint }),
      t(enabled ? "sources.turned_on_toast" : "sources.turned_off_toast", { label: source.label }),
    );
  const remove = () =>
    void save((fingerprint) => api.removeSource(source.id, fingerprint), t("sources.removed_toast", { label: source.label }));

  const actions: MenuAction[] = [
    { id: "read", label: t("sources.read_now"), run: () => void readNow(), disabled: !source.enabled || busy },
    { id: "change", label: t("sources.change"), run: props.onChange },
    { id: "power", label: t(source.enabled ? "sources.turn_off" : "sources.turn_on"), run: () => turn(!source.enabled) },
    { id: "remove", label: t("sources.remove"), run: remove },
  ];

  const facts = [source.connector_label || t("sources.kind_none"), tn("sources.items", source.items)];
  const schedule = [
    source.enabled ? tn("sources.read_every", source.every_minutes) : t("sources.off"),
    source.last ? t("sources.last_read", { when: lastWhen }) : t("sources.never"),
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
          {problem && (
            <p className="problem-note" role={props.alert ? "alert" : undefined}>
              {problem}
            </p>
          )}
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

type Mode = { type: "add"; plugin: string | null } | { type: "change"; source: Source };

/** The form for adding a source or changing one: the kind (adding only), a name, how often, a project (adding only)
 * and the settings that kind takes, as the Settings screen shows them. */
function SourceForm(props: { mode: Mode; kinds: Kind[] | undefined; kindsFailed: boolean; onClose: () => void }) {
  const { t, tn, has } = useWords();
  const afterSave = useAfterSave();
  const fingerprint = useFreshFingerprint();
  const client = useQueryClient();
  const base = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const { mode } = props;
  const adding = mode.type === "add";
  const source = mode.type === "change" ? mode.source : null;

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: !adding });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: adding });

  const available = (props.kinds ?? []).filter((k) => mode.type !== "add" || !mode.plugin || k.plugin === mode.plugin);
  const [picked, setPicked] = useState<string | null>(null);
  const chosen = source ? source.connector : (picked ?? (available.length === 1 ? available[0].name : ""));
  const kind = (props.kinds ?? []).find((k) => k.name === chosen);

  const [label, setLabel] = useState(source?.label ?? "");
  const [every, setEvery] = useState(String(source?.every_minutes ?? 60));
  const [project, setProject] = useState("");
  const [edits, setEdits] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    heading.current?.focus();
    heading.current?.scrollIntoView?.({ block: "nearest" });
  }, []);

  // A source's own settings are read from the saved settings; without them only its name, schedule and on/off can change.
  const stored = (() => {
    if (!source || !settings.data) return undefined;
    const list = settings.data.items.find((i) => i.key === "watch.sources")?.value;
    if (!Array.isArray(list)) return undefined;
    const mine = list.find((entry) => typeof entry === "object" && entry !== null && (entry as { id?: unknown }).id === source.id);
    return mine ? ((mine as { settings?: unknown }).settings ?? {}) : undefined;
  })();
  const waitingForSettings = !adding && settings.isPending;
  const items = kind && !waitingForSettings && (adding || stored !== undefined) ? (adding ? kind.items : prefill(kind.items, stored)) : [];
  const { values, bad } = formValues(items, edits);

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
  const ready = kind !== undefined && !busy && bad.length === 0;

  const submit = async () => {
    if (!ready || !kind) return;
    setBusy(true);
    setProblem("");
    try {
      const fp = await fingerprint();
      const minutes = Number(every);
      const name = label.trim();
      if (mode.type === "add") {
        const saved = await api.addSource({
          connector: kind.name,
          label: name,
          every_minutes: minutes,
          project: project || null,
          settings: nest(values),
          fingerprint: fp,
        });
        await afterSave(saved, { message: t("sources.added_toast", { label: name || kind.label, every: tn("sources.every", minutes) }) });
      } else {
        const saved = await api.changeSource(mode.source.id, {
          ...(name ? { label: name } : {}),
          every_minutes: minutes,
          ...(items.length > 0 ? { settings: nest(values) } : {}),
          fingerprint: fp,
        });
        await afterSave(saved, { message: t("sources.changed_toast", { label: name || mode.source.label }) });
      }
      props.onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      setProblem(err instanceof ApiError && err.detail ? err.detail : problemText(err, t));
      setBusy(false);
    }
  };

  const titleId = `${base}-title`;
  return (
    <form
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
          {waitingForSettings && <p className="hint">{t("loading")}</p>}
          {items.length > 0 && (
            <fieldset className="details">
              <legend>{t("sources.details")}</legend>
              <ItemFields items={items} edits={edits} onEdit={(key, draft) => setEdits((all) => ({ ...all, [key]: draft }))} disabled={busy} idPrefix={`${base}-`} />
            </fieldset>
          )}
        </>
      )}
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
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
        <p className="empty">{t("loading")}</p>
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
