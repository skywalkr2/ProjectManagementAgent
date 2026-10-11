// Any record's page: its ordinary fields as a list of labelled values, each long text with its versions and working
// copies, and what the plugins offer on it (design 5.3, 7.2). Nothing here knows what kind of record it is.
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../lib/api";
import { resolveOffers, usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { readable, readableTail, useValueLines } from "../lib/records";
import { useWords } from "../lib/wording";
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

  const info = new Map((fields.data?.fields ?? []).map((f) => [f.name, f]));
  const names = new Map<string, string>([
    ...(people.data ?? []).map((p) => [p.id, p.name] as [string, string]),
    ...(projects.data ?? []).map((p) => [p.id, p.name] as [string, string]),
  ]);
  // A field that holds the id of a person or a project shows that one's name.
  const shown = (name: string, value: unknown): string[] =>
    lines(value).map((line) => (info.get(name)?.refers_to && names.has(line) ? names.get(line)! : line));

  const data = record.data;
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
            <h3 id="record-details">{t("record.details")}</h3>
            {rows.length === 0 ? (
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
