// Any record's page: its ordinary fields as a list of labelled values, each long text with its versions and working
// copies, and what the plugins offer on it (design 5.3, 7.2). Nothing here knows what kind of record it is.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { ApiError, api, type S } from "../lib/api";
import { resolveOffers, usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { problemText } from "../lib/problem";
import { changedFields, editableFields, initialDraft, type Draft } from "../lib/record-edit";
import { inReadingOrder, readable, readableTail, useDetailLines, useFieldLabel, useValueLines } from "../lib/records";
import { reconcile, type Refreshed } from "../lib/refreshed";
import { time } from "../lib/dates";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { useChangeThis, useQuestionMenu, type ChangeKind } from "./ChangeThis";
import { FactSource } from "./FactSource";
import { FiledLine } from "./Filed";
import { LearnedLines } from "./Learned";
import { OriginLink } from "./Origin";
import { PersonDrawer } from "./PersonForm";
import { PersonPicker } from "./PersonPicker";
import { AgendaSection } from "./AgendaList";
import { Attendees } from "./Attendees";
import { useInvitationActs } from "./InvitationActs";
import { useMessageActs } from "./MessageActs";
import { ProjectKnows } from "./ProjectKnows";
import { PromiseWhy } from "./PromiseWhy";
import { ProjectDrawer } from "./ProjectForm";
import { ProjectPicker } from "./ProjectPicker";
import { RecordActivity } from "./RecordActivity";
import { RefreshedLines } from "./RefreshedLines";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeLink, domainOf } from "./SafeText";
import { StancePicker } from "./StancePicker";
import { TextSection } from "./TextSection";
import { useTextReview } from "./TextReview";
import { ValueSelect } from "./ValueSelect";
import { Skeleton } from "../ui/Skeleton";
import { useFocusAfterRender } from "../lib/focus-after-render";

export function RecordPage(props: { kind: string; id: string; onBack: () => void }) {
  const { t } = useWords();
  const { kind, id } = props;
  const record = useQuery({ queryKey: ["record", kind, id], queryFn: () => api.record(kind, id) });
  const fields = useQuery({ queryKey: ["kind", kind], queryFn: () => api.kindView(kind) });
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  // What is open with the record, what was finished and what happened to it; a record the page can't be read for shows none.
  const page = useQuery({ queryKey: ["record-page", kind, id], queryFn: () => api.recordPage(kind, id) });
  const lines = useValueLines();
  const { open, dialog } = useTextReview();
  // "Change this" sits in a menu beside the record's own actions, for the kinds of record it can be asked for.
  const change = useChangeThis({ kind: kind as ChangeKind, id });
  // A question also has its own menu: reword it, ask someone else, drop it, or say it was already sent.
  const questionFields = record.data?.fields;
  const questionMenu = useQuestionMenu(
    { id, title: String(questionFields?.title ?? ""), text: String(questionFields?.text ?? "") },
    { canMarkSent: questionFields?.status === "open" },
  );
  const menu = [...(kind === "question" ? questionMenu.entries : []), change.entry];
  // A saved message can be replied to, forwarded or filed: each drafts an act that opens in Waiting to go out.
  const message = useMessageActs(id, String(record.data?.fields.title ?? ""), kind === "source");
  // An invitation on a calendar entry can be answered the same way.
  const invite = useInvitationActs(id, kind === "event" && record.data?.fields.invitation === true);
  const [editing, setEditing] = useState(false);
  // A person and a project are edited in the same drawer as on their own screens.
  const drawer = kind === "person" ? (people.data ?? []).find((p) => p.id === id) : kind === "project" ? (projects.data ?? []).find((p) => p.id === id) : undefined;
  const editButton = useRef<HTMLButtonElement>(null);
  const focusAfterRender = useFocusAfterRender();
  const stopEditing = () => {
    setEditing(false);
    focusAfterRender(() => editButton.current);
  };

  const info = new Map((fields.data?.fields ?? []).map((f) => [f.name, f]));
  // Every id the page can name: the people and projects on file, and whatever the server resolved for this record (an
  // organization, a team, anything a field refers to). An id is never shown.
  const names = new Map<string, string>([
    ...(people.data ?? []).map((p) => [p.id, p.name] as [string, string]),
    ...(projects.data ?? []).map((p) => [p.id, p.name] as [string, string]),
    ...(page.data?.details ?? []).flatMap((d) => (d.refs ?? []).filter((r) => r.name).map((r) => [r.id, r.name] as [string, string])),
  ]);
  const shown = (name: string, value: unknown): string[] =>
    lines(value).map((line) => (info.get(name)?.refers_to && names.has(line) ? names.get(line)! : line));
  const detailLines = useDetailLines();
  const labelOf = useFieldLabel();

  const data = record.data;
  const offered = editableFields(fields.data?.fields ?? []);
  const rows = data
    ? inReadingOrder(
        Object.entries(data.fields)
          // The id of the input an item came from is shown as its "Where it came from" link instead.
          .filter(([name]) => name !== "id" && name !== "filed_by" && !(name === "source" && data.origin) && !(kind === "person" && name === "stance"))
          // A calendar entry's people are a list of their own below; its internal key, flags and answer aren't details.
          .filter(([name, value]) => !(kind === "event" && (CALENDAR_LISTED.has(name) || (name === "cancelled" && value !== true))))
          .map(([name, value]) => ({ name, lines: detailLines(name, value, info.get(name), names) }))
          .filter((row) => row.lines.length > 0),
      )
    : [];
  // The record's name, never its id: the page says it (a person is named by their full name).
  const heading = data ? (page.data?.name || shown("title", data.fields.title)[0] || shown("name", data.fields.name)[0] || data.id) : id;

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
          <h1 id="record-title">{heading}</h1>
        </div>
        {data && (
          <div className="acts">
            <Offers kind={kind} id={id} />
            {message.options && (
              <button type="button" className="btn primary" onClick={() => message.ask("reply")}>
                {t("acts.reply")}
              </button>
            )}
            {message.options && <RowMenu label={heading} actions={message.menu(["reply"])} />}
            {invite.buttons}
            {CHANGEABLE.has(kind) && <RowMenu label={heading} actions={menu} />}
          </div>
        )}
      </div>
      {data && kind === "question" && questionMenu.form}
      {data && message.form}
      {data && invite.form}
      {data && CHANGEABLE.has(kind) && change.form}
      {data && page.data?.filed && <FiledLine kind={kind} id={id} filed={page.data.filed} />}
      {data && kind === "fact" && page.data?.fact_source && <FactSource source={page.data.fact_source} fact={id} version={data.version} />}
      {data && <LearnedLines records={[id]} />}
      {record.isPending && <Skeleton />}
      {record.isError && (
        <p className="empty">
          {t("record.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void record.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      )}
      {data && (
        <div className="record-grid">
          <div className="record-main">
          {kind === "action" && <PromiseWhy action={id} quiet omitOrigin />}
          {kind === "event" && <AgendaSection items={page.data?.agenda ?? []} id="record-agenda" />}
          {kind === "event" && <Attendees fields={data.fields} names={names} />}
          {page.data && <RecordActivity page={page.data} />}
          {kind === "project" && <ProjectKnows id={id} />}
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
          </div>
          <aside className="record-side">
          <OriginLink origin={data.origin} />
          <section aria-labelledby="record-details">
            <div className="heading">
              <h3 id="record-details">{t("record.details")}</h3>
              {(drawer || offered.length > 0) && !editing && (
                <button type="button" className="btn" ref={editButton} onClick={() => setEditing(true)}>
                  {t("record.edit")}
                </button>
              )}
            </div>
            {editing && drawer && kind === "person" && <PersonDrawer person={drawer as S["PersonView"]} onClose={stopEditing} />}
            {editing && drawer && kind === "project" && <ProjectDrawer project={drawer as S["ProjectView"]} onClose={stopEditing} />}
            {editing && !drawer ? (
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
                    <dt>{labelOf(row.name)}</dt>
                    <dd>
                      {row.lines.map((line, i) => (
                        <div key={i}>{typeof line === "string" ? line : <SafeLink label={line.label || domainOf(line.url) || line.url} url={line.url} />}</div>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          {kind === "person" && (
            <StancePicker person={id} version={data.version} stance={data.fields.stance} trackOnly={data.fields.track_only === true} />
          )}
          </aside>
        </div>
      )}
      {dialog}
    </section>
  );
}

/** The fields of a calendar entry the page shows in its own way (its people and its answer), or not at all (its key). */
const CALENDAR_LISTED = new Set<string>(["key", "attendees", "organizer", "invitation", "response", "agenda"]);

/** The kinds of record a change can be asked for. */
const CHANGEABLE = new Set<string>(["action", "question", "event", "fact"]);

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
  // What the form showed when it opened, or when a refused save last refreshed it: the untouched fields are the ones
  // still equal to it.
  const [shown, setShown] = useState<Draft>(draft);
  const [refreshed, setRefreshed] = useState<{ lines: Refreshed[]; time: string }>({ lines: [], time: "" });
  const lines = useValueLines();
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
      const stale = err instanceof ApiError && err.status === 409;
      setError({ text: problemText(err, t), stale });
      if (stale) {
        // Fields the person didn't touch take what is saved now and are listed; the ones they changed are kept.
        try {
          const now = await client.fetchQuery({ queryKey: ["record", props.kind, record.id], queryFn: () => api.record(props.kind, record.id), staleTime: 0 });
          const saved = initialDraft(fields, now.fields);
          const out = reconcile(shown, draft, saved);
          setDraft(out.next as Draft);
          setShown(saved);
          const at = now.changed_at ? new Date(now.changed_at) : null;
          setRefreshed({
            lines: out.refreshed.map((name) => ({ label: readable(name), value: lines(now.fields[name]).join(", ") || t("settings.empty") })),
            time: at && !Number.isNaN(at.getTime()) ? time(at) : "",
          });
        } catch {
          // Without the current record the form can't be refreshed; the next look at the page finds the cause.
        }
      }
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
      <RefreshedLines lines={refreshed.lines} time={refreshed.time} />
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
    return <PersonPicker label={label} value={text} onChange={props.onChange} suggested={[]} people={people} autoFocus={props.autoFocus} />;
  }
  if (f.value_list) {
    return (
      <ValueSelect
        id={id}
        list={f.value_list}
        label={label}
        value={text}
        onChange={props.onChange}
        note={f.description || undefined}
        required={required}
        autoFocus={props.autoFocus}
      />
    );
  }
  let control;
  if (f.type === "reference" && f.refers_to === "project") {
    // A project can be added from here: the form opens in place and the new project is the one picked.
    return (
      <>
        <ProjectPicker id={id} label={label} value={text} onChange={props.onChange} empty={required ? "" : t("record.none")} required={required} describedBy={help} autoFocus={props.autoFocus} />
        {note}
      </>
    );
  }
  if (f.type === "choice") {
    const options = (f.options ?? []).map((o) => ({ value: o, label: o }));
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
