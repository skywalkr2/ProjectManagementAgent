// Settings (design 7.9): sections down the side, the open section's settings in the middle with their help beside each
// one. A change is saved as it is made (a choice when it changes, a box when the cursor leaves it or Enter is pressed),
// with a toast that reads it back and offers Undo; there is no Save button. Each save carries the fingerprint of the
// settings as the screen last knew them, so a change made elsewhere meanwhile is refused in plain words and what was
// typed stays.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type MouseEvent } from "react";
import { api, ApiError, type S } from "../lib/api";
import { useValueLists } from "../lib/lists";
import { problemText } from "../lib/problem";
import { addonLabel, fromDraft, groupLabel, isOff, depthOf, matches, switchOf, toDraft, type Draft, type Item } from "../lib/settings";
import { navSections, sectionItems, sectionOfItem, topics } from "../lib/settings-sections";
import { knownFingerprint, rememberFingerprint, useAfterSave } from "../lib/settings-save";
import { settingsView, viewHref, type SettingsSection } from "../lib/views";
import { useWords } from "../lib/wording";
import { AiAccounts } from "./AiAccounts";
import { DataForms } from "./DataForms";
import { useFolderListing } from "./FolderPicker";
import { SettingRow } from "./SettingRow";
import { ValueLists } from "./ValueLists";
import { Drawer } from "../ui/Drawer";
import { Skeleton } from "../ui/Skeleton";
import { WelcomeAi } from "./WelcomeAi";
import { restoreFocus } from "./ModalPanel";

type Edits = Record<string, Draft>;

const FIRST_FIELD = "input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled])";

export function Settings(props: {
  /** Opens the setup guide, at the step named when one is. */
  onOpenGuide: (step?: string) => void;
  onOpenAddons: () => void;
  onChooseSource: (plugin: string | null) => void;
  /** Opens the Sources screen, which the section list links to. */
  onOpenSources?: () => void;
  /** Opens the Knowledge screen, where the standing rules are kept and reviewed. */
  onOpenKnowledge?: () => void;
  /** Opens the grid of what each AI account can do. */
  onOpenCompare?: () => void;
  /** The section the address names; the first when it names none. */
  section?: SettingsSection | null;
  /** Called with the section the person chose, to put it in the address; without it the screen keeps the choice itself. */
  onSection?: (section: SettingsSection) => void;
  /** A moment (a counter) when something else asks for the form that adds an AI account to open, and its acknowledgment. */
  addAccount?: number | null;
  onAddAccountOpened?: () => void;
}) {
  const { t, tn, has } = useWords();
  const client = useQueryClient();
  const afterSave = useAfterSave();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const setup = useQuery({ queryKey: ["setup"], queryFn: api.setup });
  // What decides which sections are listed, and when a section that loads its own content is ready to take the cursor.
  const lists = useValueLists();
  const forms = useQuery({ queryKey: ["data-forms"], queryFn: api.dataForms });
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  // The form that adds an AI account opens here, as a drawer, so the person never leaves Settings for it.
  const [adding, setAdding] = useState(false);
  const [addDirty, setAddDirty] = useState(false);
  const addButton = useRef<HTMLElement | null>(null);
  const requested = props.addAccount;
  const acknowledge = props.onAddAccountOpened;
  useEffect(() => {
    if (requested == null) return;
    setAdding(true);
    acknowledge?.();
  }, [requested, acknowledge]);
  const [chosen, setChosen] = useState<SettingsSection>("you");
  const [more, setMore] = useState<Record<string, boolean>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [edits, setEdits] = useState<Edits>({});
  const [problems, setProblems] = useState<Record<string, string>>({});
  const searchId = useId();
  const content = useRef<HTMLDivElement>(null);

  const everything = settings.data?.items ?? [];
  const canList = useFolderListing(everything.some((i) => i.picker === "folder"));
  const listed = navSections(everything, { lists: (lists.data?.length ?? 0) > 0, files: (forms.data?.length ?? 0) > 0 });
  const wanted = props.section ?? chosen;
  const loaded = settings.isSuccess && !lists.isPending && !forms.isPending;
  // An address naming a section that has nothing to show (an add-on turned off) opens the first one.
  const section: SettingsSection = !loaded || listed.includes(wanted) ? wanted : "you";
  const label = (s: SettingsSection) => (s.startsWith("addon/") ? addonLabel(s.slice("addon/".length), t, has) : t(`settings.section.${s}`));

  const choose = (next: SettingsSection) => {
    setQuery("");
    if (props.onSection) props.onSection(next);
    else setChosen(next);
  };
  const follow = (e: MouseEvent, run: () => void) => {
    // A plain click moves within the app; a modified one (a new tab) keeps its link.
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    run();
  };

  // The cursor goes to the section's first field when it opens, or to its heading where its content is a list.
  const settled = settings.isSuccess && (section === "ai" ? !accounts.isPending : section === "lists" ? !lists.isPending : section === "files" ? !forms.isPending : true);
  useEffect(() => {
    if (!settled) return;
    const root = content.current;
    if (!root) return;
    const field = root.querySelector<HTMLElement>(FIRST_FIELD);
    const heading = root.querySelector<HTMLElement>("[data-section-heading]");
    const target = section === "ai" || section === "lists" || section === "files" ? heading : (field ?? heading);
    target?.focus({ preventScroll: true });
    // Only when a section opens: a save must not move the cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, settled]);

  // The fingerprint to save against is the one the screen loaded with and what each save answered with. A background
  // reload doesn't replace it, so a change made elsewhere is refused instead of being written over; after the refusal
  // the next load does, since the person has been told to look again.
  const adopt = useRef(true);
  useEffect(() => {
    if (!settings.data || settings.isFetching || !adopt.current) return;
    adopt.current = false;
    rememberFingerprint(client, settings.data.fingerprint);
  }, [client, settings.data, settings.isFetching]);

  const draftOf = (item: Item): Draft => (item.key in edits ? edits[item.key] : toDraft(item));
  const edit = (key: string, draft: Draft) => {
    setEdits((all) => ({ ...all, [key]: draft }));
    setProblems((all) => (all[key] ? { ...all, [key]: "" } : all));
  };

  // Saves go one at a time, each on the fingerprint the one before answered with.
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const enqueue = (run: () => Promise<void>) => {
    chain.current = chain.current.then(run, run);
  };
  const drop = (key: string, sent?: Draft) =>
    setEdits((all) => {
      if (!(key in all) || (sent !== undefined && all[key] !== sent)) return all;
      const next = { ...all };
      delete next[key];
      return next;
    });
  const save = async (key: string, body: { changes?: Record<string, unknown>; reset?: string[] }, sent?: Draft) => {
    const view = client.getQueryData<S["SettingsView"]>(["settings"]);
    const fingerprint = knownFingerprint(client, view?.fingerprint);
    if (!view || !fingerprint) return;
    setProblems((all) => ({ ...all, [key]: "" }));
    try {
      const saved = await api.saveSettings({ changes: body.changes ?? {}, reset: body.reset ?? [], fingerprint });
      rememberFingerprint(client, saved.fingerprint);
      // What the screen shows is what was saved, at once, before the reload comes back.
      client.setQueryData<S["SettingsView"]>(["settings"], (now) =>
        now && {
          fingerprint: saved.fingerprint,
          items: now.items.map((item) => {
            const change = saved.changes.find((c) => c.key === item.key);
            return change ? { ...item, value: change.after, source: change.is_default ? "default" : "file" } : item;
          }),
        },
      );
      drop(key, sent);
      await afterSave(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Out of date: load again, keeping what was typed, and say so on the row.
        adopt.current = true;
        void client.invalidateQueries({ queryKey: ["settings"] });
        setProblems((all) => ({ ...all, [key]: t("settings.changed_since_opened") }));
        return;
      }
      setProblems((all) => ({ ...all, [key]: err instanceof ApiError && err.detail ? err.detail : problemText(err, t) }));
    }
  };

  const commit = (item: Item, draft: Draft) => {
    if (item.locked || !item.editable || item.type === "other") return;
    const parsed = fromDraft(item, draft);
    if (!parsed.ok) return;
    enqueue(async () => {
      // What is saved now, so a repeat (Enter, then the cursor leaving) or an edit put back as it was sends nothing.
      const now = client.getQueryData<S["SettingsView"]>(["settings"])?.items.find((i) => i.key === item.key) ?? item;
      const saved = fromDraft(now, toDraft(now));
      if (saved.ok && JSON.stringify(saved.value) === JSON.stringify(parsed.value)) {
        drop(item.key, draft);
        return;
      }
      await save(item.key, { changes: { [item.key]: parsed.value } }, draft);
    });
  };

  const reset = (item: Item) => {
    drop(item.key);
    enqueue(async () => {
      await save(item.key, { reset: [item.key] });
      document.getElementById(`setting-${item.key}`)?.focus();
    });
  };

  const row = (item: Item) => {
    const gate = switchOf(item, everything);
    return (
      <SettingRow
        key={item.key}
        item={item}
        draft={draftOf(item)}
        onChange={(draft) => edit(item.key, draft)}
        commit={(draft) => commit(item, draft)}
        onReset={() => reset(item)}
        problem={problems[item.key]}
        beside
        disabled={false}
        depth={depthOf(item, everything)}
        gate={gate && isOff(gate, edits) ? gate : null}
        canList={canList}
      />
    );
  };

  /** The settings of one group, under its heading when there is a heading to show. */
  const group = (name: string, items: Item[], heading: boolean) => {
    const titleId = `settings-group-${name.replace(/[^A-Za-z0-9_-]/g, "-")}`;
    return (
      <div key={name} className="settings-group" role="group" aria-labelledby={heading ? titleId : undefined}>
        {heading && <h3 id={titleId}>{groupLabel(name, t, has)}</h3>}
        {name === "rules" && props.onOpenKnowledge && (
          <p className="hint">
            {t("settings.rules_link")}{" "}
            <button type="button" className="link-button" onClick={props.onOpenKnowledge}>
              {t("settings.rules_open")}
            </button>
          </p>
        )}
        {items.map(row)}
      </div>
    );
  };

  /** A section of settings: its basic ones, and the rest behind More settings (a section with no basic one shows all). */
  const form = (id: SettingsSection) => {
    const all = sectionItems(everything, id);
    const hasBasic = all.some((i) => i.basic);
    const extra = hasBasic && all.some((i) => !i.basic);
    const shown = !hasBasic || more[id] ? all : all.filter((i) => i.basic);
    const byTopic = topics(shown);
    const headings = byTopic.length > 1 || id === "ai";
    const listId = `settings-more-${id.replace(/[^A-Za-z0-9_-]/g, "-")}`;
    return (
      <>
        <div id={listId} className="settings-groups">
          {byTopic.map((topic) => group(topic.group, topic.items, headings))}
        </div>
        {extra && (
          <div className="row-end">
            <button type="button" className="btn" aria-expanded={!!more[id]} aria-controls={listId} onClick={() => setMore({ ...more, [id]: !more[id] })}>
              {t(more[id] ? "settings.fewer" : "settings.more")}
            </button>
          </div>
        )}
      </>
    );
  };

  /** Advanced: the settings no other section holds, by topic, each topic closed until it is opened. */
  const advanced = () =>
    topics(sectionItems(everything, "advanced")).map((topic) => {
      const key = `advanced:${topic.group}`;
      const id = `settings-topic-${topic.group.replace(/[^A-Za-z0-9_-]/g, "-")}`;
      return (
        <div key={topic.group} className="settings-topic">
          <h3 id={`${id}-title`}>
            <button type="button" className="topic-toggle" aria-expanded={!!open[key]} aria-controls={id} onClick={() => setOpen({ ...open, [key]: !open[key] })}>
              {groupLabel(topic.group, t, has)}
            </button>
          </h3>
          <div id={id} hidden={!open[key]} role="group" aria-labelledby={`${id}-title`}>
            {open[key] && group(topic.group, topic.items, false)}
          </div>
        </div>
      );
    });

  const heading = (id: SettingsSection) => (
    <h2 id={`settings-section-${id.replace(/[^A-Za-z0-9_-]/g, "-")}`} tabIndex={-1} data-section-heading="">
      {label(id)}
    </h2>
  );

  const found = query.trim() ? everything.filter((item) => matches(item, query, t, has)) : [];
  const results = () => {
    if (!found.length) return <p className="empty">{t("settings.none_match")}</p>;
    return listed
      .map((id) => ({ id, items: found.filter((i) => sectionOfItem(i) === id) }))
      .filter((s) => s.items.length > 0)
      .map((s) => (
        <section key={s.id} className="settings-results" aria-label={label(s.id)}>
          <h3>{label(s.id)}</h3>
          {s.items.map(row)}
        </section>
      ));
  };

  const body = () => {
    if (section === "ai") {
      return (
        <>
          <AiAccounts
            level={2}
            local={setup.data?.local}
            onAdd={() => {
              addButton.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
              setAdding(true);
            }}
            onCompare={props.onOpenCompare}
          />
          {form("ai")}
        </>
      );
    }
    if (section === "lists") return <ValueLists level={2} />;
    if (section === "files") return <DataForms level={2} />;
    if (section === "advanced") {
      return (
        <>
          {heading("advanced")}
          <p className="hint">{t("settings.advanced_intro")}</p>
          <div className="settings-topics">{advanced()}</div>
        </>
      );
    }
    return (
      <>
        {heading(section)}
        {form(section)}
      </>
    );
  };

  return (
    <section className="panel-section settings-screen" aria-labelledby="settings-title">
      <div className="heading">
        <h1 id="settings-title">{t("settings.title")}</h1>
        <div className="acts">
          <button type="button" className="btn" onClick={props.onOpenAddons}>
            {t("settings.open_addons")}
          </button>
          <button type="button" className="btn" onClick={() => props.onOpenGuide()}>
            {t("settings.open_guide")}
          </button>
        </div>
      </div>
      <p className="hint">{t("settings.intro")}</p>
      <div className="settings-layout">
        <div className="settings-side">
          <div className="field">
            <label htmlFor={searchId}>{t("settings.search")}</label>
            <input id={searchId} type="search" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
          </div>
          <nav aria-label={t("settings.sections")}>
            <ul className="settings-nav">
              {listed.flatMap((id) => [
                <li key={id}>
                  <a
                    href={viewHref(settingsView(id))}
                    aria-current={!query.trim() && id === section ? "page" : undefined}
                    onClick={(e) => follow(e, () => choose(id))}
                  >
                    {label(id)}
                  </a>
                </li>,
                // Sources is a screen of its own; the list only leads to it.
                ...(id === "ai"
                  ? [
                      <li key="sources">
                        <a href={viewHref("sources")} onClick={(e) => props.onOpenSources && follow(e, props.onOpenSources)}>
                          {t("settings.section.sources")}
                        </a>
                      </li>,
                    ]
                  : []),
              ])}
            </ul>
          </nav>
        </div>
        <div className="settings-content" ref={content}>
          {query.trim() && (
            <p className="hint" role="status">
              {found.length ? tn("settings.shown", found.length) : ""}
            </p>
          )}
          {settings.isPending ? (
            <Skeleton />
          ) : settings.isError ? (
            <p className="empty">{t("settings.failed")}</p>
          ) : query.trim() ? (
            results()
          ) : (
            body()
          )}
        </div>
      </div>
      <Drawer
        open={adding}
        title={t("ai_add.title")}
        dirty={addDirty}
        wide
        onClose={() => {
          setAdding(false);
          setAddDirty(false);
          restoreFocus(() => addButton.current);
        }}
      >
        {adding && setup.data && (
          <WelcomeAi
            local={setup.data.local}
            done
            drawer={{
              onAdded: () => {
                setAdding(false);
                setAddDirty(false);
                restoreFocus(() => addButton.current);
              },
              onCancel: () => {
                setAdding(false);
                setAddDirty(false);
                restoreFocus(() => addButton.current);
              },
              onDirty: setAddDirty,
            }}
          />
        )}
      </Drawer>
    </section>
  );
}
