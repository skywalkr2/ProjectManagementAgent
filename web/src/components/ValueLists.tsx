// Lists in Settings: the choices dropdowns offer, one block per list. A value can be added, renamed (everywhere it is
// held) or stopped being offered, and a value that is no longer offered can be offered again. Every change acts at once
// with Undo.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { offers, useListChange, useValueLists, type ValueList } from "../lib/lists";
import { readable, readableTail } from "../lib/records";
import { useWords } from "../lib/wording";
import { Pill } from "../ui/Pill";
import { RowMenu, type MenuAction } from "./RowMenu";

const slug = (name: string) => name.replace(/[^A-Za-z0-9_-]/g, "-");

type Tone = S["ListSuggestionView"]["tone"];
type Meaning = NonNullable<S["ListSuggestionView"]["meaning"]>;
const TONES: Tone[] = ["ok", "warn", "danger", "neutral"];
const MEANINGS: Meaning[] = ["not_started", "open", "at_risk", "blocked", "done"];

/** `level` 2 makes the heading the heading of a section of its own, which takes the cursor when the section opens. */
export function ValueLists(props: { level?: 2 | 3 }) {
  const { t } = useWords();
  const lists = useValueLists();
  // Nothing is shown until the lists have loaded; a failure says so quietly.
  if (lists.isPending) return null;
  if (lists.isError) return <p className="hint">{t("lists.load_failed")}</p>;
  if (lists.data.length === 0) return null;
  const Heading = props.level === 2 ? "h2" : "h3";
  return (
    <section className="panel-section" aria-labelledby="lists-title">
      <div className="heading">
        <Heading id="lists-title" {...(props.level === 2 ? { tabIndex: -1, "data-section-heading": "" } : {})}>
          {t("lists.title")}
        </Heading>
      </div>
      <p className="hint">{t("lists.intro")}</p>
      <ul className="queue">
        {lists.data.map((list) => (
          <ListBlock key={list.name} list={list} />
        ))}
      </ul>
    </section>
  );
}

/** Where a list is used, in plain words: the wording sheet names the core's fields; another add-on's field is named
 * from its kind and field. */
function useUsedBy(list: ValueList): string {
  const { t, has } = useWords();
  const fields = list.used_by.map((use) => {
    if (has(`lists.used.${use}`)) return t(`lists.used.${use}`);
    const dot = use.lastIndexOf(".");
    return t("lists.used.other", { kind: readableTail(use.slice(0, dot)), field: readable(use.slice(dot + 1)).toLowerCase() });
  });
  return fields.length ? t("lists.used_by", { fields: fields.join(", ") }) : "";
}

function ListBlock(props: { list: ValueList }) {
  const { t } = useWords();
  const change = useListChange();
  const { list } = props;
  const base = `list-${slug(list.name)}`;
  const used = useUsedBy(list);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [newValue, setNewValue] = useState("");
  const [chosenTone, setChosenTone] = useState<Tone | null>(null);
  const [chosenMeaning, setChosenMeaning] = useState<Meaning | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [problem, setProblem] = useState("");
  // What the typed value suggests: its tone, and on a status list its meaning. The person can change either.
  const typed = newValue.trim();
  const suggestion = useQuery({
    queryKey: ["list-suggestion", list.name, typed],
    queryFn: () => api.listSuggestion(list.name, typed),
    enabled: !!typed,
    retry: false,
  });
  const tone: Tone = chosenTone ?? suggestion.data?.tone ?? "neutral";
  const meaning: Meaning | null = list.status ? (chosenMeaning ?? suggestion.data?.meaning ?? "open") : null;

  // After a change the row that held focus may be gone, so focus goes to the list's own name.
  const settle = () => window.requestAnimationFrame(() => document.getElementById(`${base}-name`)?.focus());

  const run = async (go: () => Promise<S["Applied"]>, message: string) => {
    setProblem("");
    const failed = await change(go, message);
    setProblem(failed);
    return !failed;
  };

  const add = async (value: string, message: string, meant?: Parameters<typeof api.listAdd>[2]) => {
    const ok = await run(() => api.listAdd(list.name, value, meant), message);
    if (ok) settle();
    return ok;
  };

  return (
    <li className="line">
      <div className="row">
        <div className="text">
          <strong id={`${base}-name`} tabIndex={-1}>
            {list.label}
          </strong>
          {used && <span className="sub">{used}</span>}
        </div>
      </div>
      <div className="body">
        {list.values.length === 0 ? (
          <p className="hint">{t("lists.no_values")}</p>
        ) : (
          <ul className="list-values" aria-label={t("lists.values_of", { list: list.label })}>
            {list.values.map((value) => (
              <li key={value}>
                {renaming === value ? (
                  <RenameField
                    id={`${base}-rename`}
                    value={value}
                    onCancel={() => {
                      setRenaming(null);
                      setProblem("");
                    }}
                    onSave={async (to) => {
                      if (to === value) {
                        setRenaming(null);
                        return;
                      }
                      if (await run(() => api.listRename(list.name, value, to), t("lists.renamed_toast", { value, to }))) {
                        setRenaming(null);
                        settle();
                      }
                    }}
                  />
                ) : (
                  <>
                    <span className="list-value">{value}</span>
                    <Meant list={list} value={value} />
                    <RowMenu
                      label={t("lists.value_menu", { value, list: list.label })}
                      actions={
                        [
                          { id: "rename", label: t("lists.rename"), run: () => setRenaming(value) },
                          {
                            id: "stop",
                            label: t("lists.stop"),
                            run: () =>
                              void run(() => api.listRetire(list.name, value), t("lists.stopped_toast", { value, list: list.label })).then(
                                (ok) => ok && settle(),
                              ),
                          },
                        ] satisfies MenuAction[]
                      }
                    />
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        <form
          className="inline-field"
          onSubmit={(e) => {
            e.preventDefault();
            const value = newValue.trim();
            if (!value) return;
            const existing = offers(list.values, value);
            if (existing) {
              setProblem("");
              setNewValue("");
              return;
            }
            // A value on a status list is asked for its meaning with its tone; elsewhere a tone is sent only when chosen.
            const meant = list.status ? { tone, meaning: meaning ?? undefined } : chosenTone ? { tone: chosenTone } : undefined;
            void add(value, t("lists.added_toast", { value, list: list.label }), meant).then((ok) => {
              if (!ok) return;
              setNewValue("");
              setChosenTone(null);
              setChosenMeaning(null);
            });
          }}
        >
          <label className="sr" htmlFor={`${base}-add`}>
            {t("lists.add_to", { list: list.label })}
          </label>
          <input
            id={`${base}-add`}
            type="text"
            value={newValue}
            autoComplete="off"
            placeholder={t("lists.add_placeholder")}
            onChange={(e) => setNewValue(e.target.value)}
          />
          {typed && list.status && (
            <>
              <label htmlFor={`${base}-meaning`}>{t("lists.meaning_label")}</label>
              <select id={`${base}-meaning`} value={meaning ?? "open"} onChange={(e) => setChosenMeaning(e.target.value as Meaning)}>
                {MEANINGS.map((m) => (
                  <option key={m} value={m}>
                    {t(`lists.meaning.${m}`)}
                  </option>
                ))}
              </select>
            </>
          )}
          {typed && (
            <>
              <label htmlFor={`${base}-tone`}>{t("lists.tone_label")}</label>
              <select id={`${base}-tone`} value={tone} onChange={(e) => setChosenTone(e.target.value as Tone)}>
                {TONES.map((x) => (
                  <option key={x} value={x}>
                    {t(`lists.tone.${x}`)}
                  </option>
                ))}
              </select>
            </>
          )}
          <button type="submit" className="btn" disabled={!newValue.trim()}>
            {t("lists.add")} <span className="sr">{t("lists.add_for", { list: list.label })}</span>
          </button>
        </form>
        {typed && suggestion.data && chosenTone === null && chosenMeaning === null && <p className="hint">{t("lists.suggested")}</p>}
        {problem && (
          <p className="problem-note" role="alert">
            {problem}
          </p>
        )}
        {list.retired.length > 0 && (
          <div className="list-retired">
            <button
              type="button"
              className="btn quiet small"
              aria-expanded={showRetired}
              aria-controls={`${base}-retired`}
              onClick={() => setShowRetired((v) => !v)}
            >
              {t("lists.retired", { n: list.retired.length })}
            </button>
            {showRetired && (
              <div id={`${base}-retired`}>
                <p className="hint">{t("lists.retired_hint")}</p>
                <ul className="list-values">
                  {list.retired.map((value) => (
                    <li key={value}>
                      <span className="list-value">{value}</span>
                      <button
                        type="button"
                        className="btn small"
                        onClick={() => void add(value, t("lists.again_toast", { value, list: list.label }))}
                      >
                        {t("lists.offer_again")} <span className="sr">{value}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

/** A value's name being changed in place: Enter saves, Escape leaves it as it was. */
function RenameField(props: { id: string; value: string; onSave: (to: string) => void; onCancel: () => void }) {
  const { t } = useWords();
  const [text, setText] = useState(props.value);
  const to = text.trim();
  return (
    <form
      className="inline-field"
      onSubmit={(e) => {
        e.preventDefault();
        if (to) props.onSave(to);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onCancel();
      }}
    >
      <label className="sr" htmlFor={props.id}>
        {t("lists.rename_label", { value: props.value })}
      </label>
      <input id={props.id} type="text" value={text} autoFocus autoComplete="off" onChange={(e) => setText(e.target.value)} />
      <button type="submit" className="btn primary" disabled={!to}>
        {t("lists.rename_save")}
      </button>
      <button type="button" className="btn quiet" onClick={props.onCancel}>
        {t("action.cancel")}
      </button>
    </form>
  );
}

/** How a value looks and, on a status list, what it counts as: a small label whose words say it, so the color is never all
 * there is. A value with neither says nothing. */
function Meant(props: { list: ValueList; value: string }) {
  const { t } = useWords();
  const tone = props.list.tones?.[props.value] ?? "neutral";
  const meaning = props.list.meanings?.[props.value];
  if (!meaning && tone === "neutral") return null;
  return <Pill tone={tone}>{meaning ? t("lists.means", { meaning: t(`lists.meaning.${meaning}`) }) : t(`lists.tone.${tone}`)}</Pill>;
}
