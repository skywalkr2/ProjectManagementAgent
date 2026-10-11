// Settings (design 7.9): every setting the config schemas describe, as a form. Basic settings come first and the rest
// sit behind a toggle; the search looks at all of them. A save sends only what changed, reads it back and offers Undo.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, ApiError } from "../lib/api";
import { problemText } from "../lib/problem";
import { fromDraft, groupItems, groupLabel, isOff, depthOf, switchOf, toDraft, type Draft, type Group, type Item } from "../lib/settings";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { AiAccounts } from "./AiAccounts";
import { DataForms } from "./DataForms";
import { useFolderListing } from "./FolderPicker";
import { SettingRow } from "./SettingRow";
import { SignIns } from "./SignIns";
import { ValueLists } from "./ValueLists";

type Edits = Record<string, Draft>;

export function Settings(props: {
  onOpenGuide: () => void;
  onOpenAddons: () => void;
  onChooseSource: (plugin: string | null) => void;
}) {
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
      <DataForms />
      <AiAccounts />
      <ValueLists />
      <SignIns onOpenAddons={props.onOpenAddons} onChooseSource={props.onChooseSource} />
    </section>
  );
}
