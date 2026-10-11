// Settings (design 7.9): every setting the config schemas describe, as a form. Basic settings come first and the rest
// sit behind a toggle; the search looks at all of them. A save sends only what changed, reads it back and offers Undo.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { problemText } from "../lib/problem";
import {
  fileName,
  formatValue,
  fromDraft,
  groupItems,
  groupLabel,
  isOff,
  labelOf,
  depthOf,
  switchOf,
  toDraft,
  type Draft,
  type Group,
  type Item,
} from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { FolderPicker, useFolderListing } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";
import { SignIns } from "./SignIns";

type Edits = Record<string, Draft>;

export function Settings(props: { onOpenGuide: () => void; onOpenAddons: () => void }) {
  const { t, tn, has } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [more, setMore] = useState(false);
  const [query, setQuery] = useState("");
  const [edits, setEdits] = useState<Edits>({});
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const searchId = useId();
  const listId = useId();

  const groups = groupItems(settings.data?.items ?? [], { more, query }, t, has);
  const shown = groups.reduce((n, g) => n + g.items.length, 0);

  const everything = settings.data?.items ?? [];
  const canList = useFolderListing(everything.some((i) => i.picker === "folder"));

  const edit = (key: string, draft: Draft) => setEdits((all) => ({ ...all, [key]: draft }));

  // The keys of a group that were changed on screen, with what each would send; `bad` lists any that can't be sent.
  const pending = (group: Group) => {
    const changes: Record<string, unknown> = {};
    const bad: string[] = [];
    for (const item of group.items) {
      if (!(item.key in edits) || item.locked || !item.editable || item.type === "other") continue;
      if (edits[item.key] === toDraft(item)) continue;
      const parsed = fromDraft(item, edits[item.key]);
      if (parsed.ok) changes[item.key] = parsed.value;
      else bad.push(item.key);
    }
    return { changes, bad };
  };

  const submit = async (group: string, changes: Record<string, unknown>, reset: string[]) => {
    if (!settings.data) return false;
    setBusy(group);
    setProblems((all) => ({ ...all, [group]: "" }));
    try {
      const saved = await api.saveSettings({ changes, reset, fingerprint: settings.data.fingerprint });
      setEdits((all) => {
        const next = { ...all };
        for (const key of [...Object.keys(changes), ...reset]) delete next[key];
        return next;
      });
      await afterSave(saved);
      return true;
    } catch (err) {
      // A changed file means the form is out of date: show what the server said and load it again, keeping what was typed.
      if (err instanceof ApiError && err.status === 409) void client.invalidateQueries({ queryKey: ["settings"] });
      const text = err instanceof ApiError && err.detail ? err.detail : problemText(err, t);
      setProblems((all) => ({ ...all, [group]: text }));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const reset = async (group: string, item: Item) => {
    if (await submit(group, {}, [item.key])) document.getElementById(`setting-${item.key}`)?.focus();
  };

  return (
    <section className="panel-section" aria-labelledby="settings-title">
      <div className="heading">
        <h2 id="settings-title">{t("settings.title")}</h2>
        <div className="acts">
          <button type="button" className="btn" onClick={props.onOpenAddons}>
            {t("settings.open_addons")}
          </button>
          <button type="button" className="btn" onClick={props.onOpenGuide}>
            {t("settings.open_guide")}
          </button>
        </div>
      </div>
      <p className="hint">{t("settings.intro")}</p>
      <div className="settings-tools">
        <div className="field">
          <label htmlFor={searchId}>{t("settings.search")}</label>
          <input id={searchId} type="search" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
        </div>
        {!query.trim() && (
          <button type="button" className="btn" aria-expanded={more} aria-controls={listId} onClick={() => setMore(!more)}>
            {t(more ? "settings.fewer" : "settings.more")}
          </button>
        )}
      </div>
      <p className="hint" role="status">
        {settings.data ? (shown ? tn("settings.shown", shown) : t("settings.none_match")) : ""}
      </p>
      <div id={listId} className="settings-groups">
        {settings.isPending ? (
          <p className="empty">{t("loading")}</p>
        ) : settings.isError ? (
          <p className="empty">{t("settings.failed")}</p>
        ) : (
          groups.map((group) => {
            const { changes, bad } = pending(group);
            const count = Object.keys(changes).length;
            const titleId = `settings-group-${group.group}`;
            return (
              <form
                key={group.group}
                className="panel settings-group"
                aria-labelledby={titleId}
                onSubmit={(e) => {
                  e.preventDefault();
                  if (count && !bad.length) void submit(group.group, changes, []);
                }}
              >
                <h3 id={titleId}>{groupLabel(group.group, t, has)}</h3>
                {group.items.map((item) => {
                  const gate = switchOf(item, everything);
                  return (
                    <SettingRow
                      key={item.key}
                      item={item}
                      draft={item.key in edits ? edits[item.key] : toDraft(item)}
                      onChange={(draft) => edit(item.key, draft)}
                      onReset={() => void reset(group.group, item)}
                      disabled={busy !== null}
                      depth={depthOf(item, everything)}
                      gate={gate && isOff(gate, edits) ? gate : null}
                      canList={canList}
                    />
                  );
                })}
                {problems[group.group] && (
                  <p className="problem-note" role="alert">
                    {problems[group.group]}
                  </p>
                )}
                <div className="row-end">
                  <button type="submit" className="btn primary" disabled={busy !== null || count === 0 || bad.length > 0}>
                    {t("settings.save")}
                    <span className="sr"> {groupLabel(group.group, t, has)}</span>
                  </button>
                </div>
              </form>
            );
          })
        )}
      </div>
      <SignIns />
    </section>
  );
}

function SettingRow(props: {
  item: Item;
  draft: Draft;
  onChange: (draft: Draft) => void;
  onReset: () => void;
  disabled: boolean;
  depth: number;
  /** The switch this setting depends on, when it is off. */
  gate: Item | null;
  canList: boolean;
}) {
  const { t, has } = useWords();
  const [picking, setPicking] = useState(false);
  const chooser = useRef<HTMLButtonElement>(null);
  const { item, draft } = props;
  const id = `setting-${item.key}`;
  const label = labelOf(item, t, has);
  const readOnly = item.type === "other" || (!item.locked && !item.editable);
  const note = item.locked
    ? t(item.source === "env" ? "settings.locked_env" : "settings.locked_flag")
    : readOnly
      ? t("settings.changed_in", { file: fileName(item) })
      : null;
  const hint = label !== item.description ? item.description : null;
  const parsed = !readOnly && !item.locked && draft !== toDraft(item) ? fromDraft(item, draft) : null;
  const invalid = parsed && !parsed.ok ? t(`settings.invalid.${parsed.problem}`) : null;
  const waiting = props.gate ? t(props.gate.type === "yes_no" ? "settings.needs_on" : "settings.needs_value", { label: labelOf(props.gate, t, has) }) : null;
  const describedBy = [hint && `${id}-hint`, waiting && `${id}-waiting`, item.type === "list" && `${id}-list`, invalid && `${id}-bad`, note && `${id}-note`, `${id}-default`]
    .filter(Boolean)
    .join(" ");
  const off = item.locked || props.disabled || props.gate !== null;
  const option = (o: string) => (has(`settings.option.${item.key}.${o}`) ? t(`settings.option.${item.key}.${o}`) : o);

  let control;
  if (readOnly) {
    control = (
      <p className="setting-value" id={id}>
        {formatValue(item.value, t)}
      </p>
    );
  } else if (item.type === "yes_no") {
    control = (
      <input
        id={id}
        type="checkbox"
        checked={draft === true}
        disabled={off}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.checked)}
      />
    );
  } else if (item.type === "choice") {
    control = (
      <select id={id} value={String(draft)} disabled={off} aria-describedby={describedBy} onChange={(e) => props.onChange(e.target.value)}>
        {(item.options ?? []).map((o) => (
          <option key={o} value={o}>
            {option(o)}
          </option>
        ))}
      </select>
    );
  } else if (item.type === "list") {
    control = (
      <textarea
        id={id}
        className="short"
        value={String(draft)}
        disabled={off}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
  } else {
    const input = (
      <input
        id={id}
        type="text"
        inputMode={item.type === "text" ? undefined : "decimal"}
        value={String(draft)}
        disabled={off}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
    // A folder can be picked from a list where the app can list folders; otherwise it is typed, with no fuss.
    control =
      item.picker === "folder" && props.canList ? (
        <div className="inline-field">
          {input}
          <button type="button" className="btn primary" ref={chooser} disabled={off} onClick={() => setPicking(true)}>
            {t("settings.choose_folder")}
            <span className="sr"> {label}</span>
          </button>
          {String(draft) !== "" && (
            <button type="button" className="btn quiet" disabled={off} onClick={() => props.onChange("")}>
              {t("settings.clear_value")}
              <span className="sr"> {label}</span>
            </button>
          )}
        </div>
      ) : (
        input
      );
  }

  const checkbox = item.type === "yes_no" && !readOnly;
  return (
    <div
      className={`setting${props.depth ? " dependent" : ""}${props.gate ? " waiting" : ""}`}
      data-key={item.key}
      style={props.depth ? { marginInlineStart: `${Math.min(props.depth, 3) * 20}px` } : undefined}
    >
      {checkbox ? (
        <label className="check-line" htmlFor={id}>
          {control}
          <span>{label}</span>
        </label>
      ) : readOnly ? (
        <span className="setting-label">{label}</span>
      ) : (
        <label className="setting-label" htmlFor={id}>
          {label}
        </label>
      )}
      {checkbox ? null : control}
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {waiting && (
        <p className="hint" id={`${id}-waiting`}>
          {waiting}
        </p>
      )}
      {item.type === "list" && !readOnly && (
        <p className="hint" id={`${id}-list`}>
          {t("settings.list_hint")}
        </p>
      )}
      {invalid && (
        <p className="problem-note" id={`${id}-bad`}>
          {invalid}
        </p>
      )}
      {note && (
        <p className="hint" id={`${id}-note`}>
          {note}
        </p>
      )}
      <div className="setting-foot">
        {item.type !== "other" && (
          <p className="hint" id={`${id}-default`}>
            {t("settings.default", { value: formatValue(item.default, t) })}
          </p>
        )}
        {item.source === "file" && item.editable && !item.locked && (
          <button
            type="button"
            className="btn quiet small"
            disabled={props.disabled}
            aria-label={t("settings.back_to_default_named", { label })}
            onClick={props.onReset}
          >
            {t("settings.back_to_default")}
          </button>
        )}
      </div>
      {picking && (
        <FolderPicker
          start={String(draft) || undefined}
          onClose={() => {
            setPicking(false);
            restoreFocus(() => chooser.current);
          }}
          onPick={(picked) => {
            setPicking(false);
            props.onChange(picked);
            restoreFocus(() => chooser.current);
          }}
        />
      )}
    </div>
  );
}
