// Any record's page: its ordinary fields as a list of labelled values, each long text with its versions and working
// copies, and what the plugins offer on it (design 5.3, 7.2). Nothing here knows what kind of record it is.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { ApiError, api, type S } from "../lib/api";
import { resolveOffers, usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { problemText } from "../lib/problem";
import { changedFields, editableFields, initialDraft, type Draft } from "../lib/record-edit";
import { readable, readableTail, useValueLines } from "../lib/records";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";
import { RowMenu, type MenuAction } from "./RowMenu";
import { TextSection } from "./TextSection";
import { useTextReview } from "./TextReview";

export function RecordPage(props: { kind: string; id: string; onBack: () => void }) {
  const { t } = useWords();
  const { kind, id } = props;
  const record = useQuery({ queryKey: ["record", kind, id], queryFn: () => api.record(kind, id) });
  const fields = useQuery({ queryKey: ["kind", kind], queryFn: () => api.kindView(kind) });
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const lines = useValueLines();
  const { open, dialog } = useTextReview();
  const [editing, setEditing] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const stopEditing = () => {
    setEditing(false);
    window.requestAnimationFrame(() => editButton.current?.focus());
  };

  const info = new Map((fields.data?.fields ?? []).map((f) => [f.name, f]));
  const names = new Map<string, string>([
    ...(people.data ?? []).map((p) => [p.id, p.name] as [string, string]),
    ...(projects.data ?? []).map((p) => [p.id, p.name] as [string, string]),
  ]);
  // A field that holds the id of a person or a project shows that one's name.
  const shown = (name: string, value: unknown): string[] =>
    lines(value).map((line) => (info.get(name)?.refers_to && names.has(line) ? names.get(line)! : line));

  const data = record.data;
  const offered = editableFields(fields.data?.fields ?? []);
  const rows = data
    ? Object.entries(data.fields)
        .filter(([name]) => name !== "id")
        .map(([name, value]) => ({ name, lines: shown(name, value) }))
        .filter((row) => row.lines.length > 0)
    : [];
  const heading = data ? (shown("title", data.fields.title)[0] ?? shown("name", data.fields.name)[0] ?? data.id) : id;

  return (
    <section className="panel-section record-page" aria-labelledby="record-title">
      <div>
        <button type="button" className="btn quiet small" onClick={props.onBack}>
          {t("record.back")}
        </button>
      </div>
      <div className="heading">
        <div>
          <span className="kind k-review">{readableTail(kind)}</span>
          <h2 id="record-title">{heading}</h2>
        </div>
        {data && <Offers kind={kind} id={id} />}
      </div>
      {record.isPending && <p className="empty">{t("loading")}</p>}
      {record.isError && (
        <p className="empty">
          {t("record.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void record.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      )}
      {data && (
        <>
          <section aria-labelledby="record-details">
            <div className="heading">
              <h3 id="record-details">{t("record.details")}</h3>
              {offered.length > 0 && !editing && (
                <button type="button" className="btn" ref={editButton} onClick={() => setEditing(true)}>
                  {t("record.edit")}
                </button>
              )}
            </div>
            {editing ? (
              <DetailsForm
                kind={kind}
                record={data}
                fields={offered}
                people={people.data ?? []}
                projects={projects.data ?? []}
                onDone={stopEditing}
              />
            ) : rows.length === 0 ? (
              <p className="hint">{t("record.no_details")}</p>
            ) : (
              <dl className="details-list">
                {rows.map((row) => (
                  <div key={row.name} className="detail">
                    <dt>{readable(row.name)}</dt>
                    <dd>
                      {row.lines.map((line, i) => (
                        <div key={i}>{line}</div>
                      ))}
                      {info.get(row.name)?.description && <span className="hint">{info.get(row.name)!.description}</span>}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          {data.long_text.map((field) => (
            <TextSection
              key={field}
              kind={kind}
              id={id}
              field={field}
              help={info.get(field)?.description || undefined}
              onReview={open}
            />
          ))}
        </>
      )}
      {dialog}
    </section>
  );
}

/** What the plugins offer on this record: the first thing is the primary button and the rest are in its menu. */
function Offers(props: { kind: string; id: string }) {
  const { t } = useWords();
  const actions = usePluginActions(props.kind, props.id);
  const tasks = useTaskKinds(props.kind, props.id);
  const { run, review } = usePluginRun();
  const box = useRef<HTMLDivElement>(null);
  const names = [...(actions.data ?? []).map((a) => a.name), ...(tasks.data ?? []).map((k) => k.name)];
  const offers: Offer[] = resolveOffers(names, actions.data ?? [], tasks.data ?? []);
  if (offers.length === 0) return review;
  const target = { kind: props.kind, id: props.id };
  const [primary, ...rest] = offers;
  const menu: MenuAction[] = rest.map((o) => ({
    id: o.name,
    label: o.label,
    run: () => run(o, target, () => box.current?.querySelector<HTMLElement>("button.more")),
  }));
  return (
    <div className="acts" ref={box} role="group" aria-label={t("record.actions")}>
      <button
        type="button"
        className="btn primary"
        data-key="primary"
        onClick={(e) => {
          const button = e.currentTarget;
          run(primary, target, () => button);
        }}
      >
        {primary.label}
      </button>
      <RowMenu label={t("record.actions")} actions={menu} />
      {review}
    </div>
  );
}

/** The record's ordinary fields as a form. Save sends only what changed, with the version the person was looking at,
 * and offers Undo; a refusal is shown here and the form stays open with what was typed. */
function DetailsForm(props: {
  kind: string;
  record: S["GenericRecordView"];
  fields: S["FieldView"][];
  people: S["PersonView"][];
  projects: S["ProjectView"][];
  onDone: () => void;
}) {
  const { t } = useWords();
  const client = useQueryClient();
  const { push } = useToasts();
  const base = useId();
  const { record, fields } = props;
  const [draft, setDraft] = useState<Draft>(() => initialDraft(fields, record.fields));
  const [error, setError] = useState<{ text: string; stale: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const changed = changedFields(fields, record.fields, draft);
  const dirty = Object.keys(changed).length > 0;
  const set = (name: string, value: string | boolean) => setDraft((d) => ({ ...d, [name]: value }));

  const save = async () => {
    if (!dirty) return;
    setSaving(true);
    setError(null);
    try {
      const done = await api.editRecord({ kind: props.kind, id: record.id, fields: changed, read_version: record.version });
      await client.invalidateQueries();
      push({
        message: t("record.saved"),
        undo: async () => {
          const report = await api.undo(done.changeset);
          await client.invalidateQueries();
          if (!report.restored.length) throw new Error("not undone");
        },
      });
      props.onDone();
    } catch (err) {
      setError({ text: problemText(err, t), stale: err instanceof ApiError && err.status === 409 });
      setSaving(false);
    }
  };

  return (
    <form
      className="panel setup-form"
      aria-label={t("record.edit")}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") props.onDone();
      }}
    >
      {fields.map((f, i) => (
        <DetailInput
          key={f.name}
          id={`${base}-${f.name}`}
          field={f}
          value={draft[f.name]}
          onChange={(v) => set(f.name, v)}
          people={props.people}
          projects={props.projects}
          autoFocus={i === 0}
        />
      ))}
      {error && (
        <div className="problem-note" role="alert">
          <p>{error.text}</p>
          {error.stale && <p>{t("record.edit_stale")}</p>}
        </div>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!dirty || saving}>
          {t("record.save")}
        </button>
      </div>
    </form>
  );
}

function DetailInput(props: {
  id: string;
  field: S["FieldView"];
  value: string | boolean;
  onChange: (value: string | boolean) => void;
  people: S["PersonView"][];
  projects: S["ProjectView"][];
  autoFocus: boolean;
}) {
  const { t } = useWords();
  const { field: f, id, value } = props;
  const label = readable(f.name);
  const text = String(value);
  const required = f.required === true;
  const help = f.description ? `${id}-help` : undefined;
  const note = f.description ? (
    <span id={help} className="hint">
      {f.description}
    </span>
  ) : null;

  if (f.type === "yes_no") {
    return (
      <div className="field">
        <label className="check-line" htmlFor={id}>
          <input id={id} type="checkbox" checked={value === true} aria-describedby={help} autoFocus={props.autoFocus} onChange={(e) => props.onChange(e.target.checked)} />
          <span>{label}</span>
        </label>
        {note}
      </div>
    );
  }
  if (f.type === "reference" && f.refers_to === "person") {
    // The person who is picked stays pickable even after they have left.
    const people = props.people.filter((p) => p.status === "active" || p.id === text);
    return <PersonPicker label={label} value={text} onChange={props.onChange} suggested={[]} people={people} />;
  }
  let control;
  if (f.type === "choice" || (f.type === "reference" && f.refers_to === "project")) {
    const options =
      f.type === "choice"
        ? (f.options ?? []).map((o) => ({ value: o, label: o }))
        : props.projects.map((p) => ({ value: p.id, label: p.name }));
    control = (
      <select id={id} value={text} required={required} aria-describedby={help} autoFocus={props.autoFocus} onChange={(e) => props.onChange(e.target.value)}>
        {!required && <option value="">{t("record.none")}</option>}
        {required && text === "" && <option value="" />}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  } else if (f.type === "list") {
    control = <textarea id={id} className="short" value={text} aria-describedby={help} autoFocus={props.autoFocus} onChange={(e) => props.onChange(e.target.value)} />;
  } else {
    const type = f.type === "number" ? "number" : f.type === "date" ? "date" : "text";
    control = (
      <input
        id={id}
        type={type}
        step={f.type === "number" ? "any" : undefined}
        value={text}
        required={required}
        aria-describedby={help}
        autoFocus={props.autoFocus}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
  }
  return (
    <div className="field">
      <label htmlFor={id}>
        {label} {f.type === "list" && <span className="hint">{t("record.list_hint")}</span>}
      </label>
      {control}
      {note}
    </div>
  );
}
