// What is going on with a record (design 7.14): what is open with it, what has been finished and by whom, and what happened to
// it, newest first. It reads the record's page from the server, which resolves every name; nothing here knows what kind of
// record it is. Finished work is credited to the one who did it, with who said it was done, so a nudge is never completion.
import type { ReactNode } from "react";
import { type S } from "../lib/api";
import { day, monthDay } from "../lib/dates";
import { forMeeting } from "../lib/meetings";
import { useFieldLabel } from "../lib/records";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { OriginLink, hasOrigin } from "./Origin";

type Page = S["RecordPageView"];

function Section(props: { id: string; title: string; count?: number; children: ReactNode }) {
  return (
    <section aria-labelledby={props.id} className="record-section">
      <div className="heading">
        <h3 id={props.id}>{props.title}</h3>
        {props.count ? <span className="hint">{props.count}</span> : null}
      </div>
      {props.children}
    </section>
  );
}

/** "for Thursday's print sync", linking to the series' page; nothing for an item that is on no series. */
export function MeetingLabel(props: { series?: string | null; title?: string | null; on?: string | null }) {
  const { t } = useWords();
  if (!props.series || !props.title) return null;
  return <a href={viewHref(recordView("series", props.series))}>{forMeeting(t, props.title, props.on)}</a>;
}

const joined = (parts: ReactNode[]): ReactNode =>
  parts
    .filter(Boolean)
    .flatMap((part, i) => (i === 0 ? [part] : [" · ", part]))
    .map((part, i) => <span key={i}>{part}</span>);

export function RecordActivity(props: { page: Page }) {
  const { t, tn, has } = useWords();
  const { page } = props;
  const labelOf = useFieldLabel();
  // What the change was, in a word, from the op that made it; one the sheet has no word for is just a change.
  const verb = (op: string) => (has(`record.op.${op.split("#")[0]}`) ? t(`record.op.${op.split("#")[0]}`) : t("record.op.other"));
  // A change with a word of its own (added, closed, asked) says that word; any other says which field changed, by its label.
  const did = (e: Page["activity"][number]) => {
    const own = e.op.split("#")[0];
    const plain = own !== "record.edit" && has(`record.op.${own}`);
    return !plain && e.field ? t("record.did_field", { field: labelOf(e.field).toLocaleLowerCase() }) : verb(e.op);
  };
  const completed = page.completed_actions ?? [];
  const open = page.open_actions.length + page.open_questions.length;
  return (
    <div className="record-activity">
      {open > 0 && (
        <Section id="record-open" title={t("record.open_with", { name: page.name })} count={open}>
          <ul className="queue">
            {page.open_actions.map((a) => (
              <Row
                key={a.id}
                pill={<Pill tone="neutral">{t("unfiled.kind.action")}</Pill>}
                title={<a href={viewHref(recordView("action", a.id))}>{a.text}</a>}
                meta={joined([
                  (a.owners ?? []).join(", "),
                  a.due && t("op.meta.due", { date: day(a.due) }),
                  page.kind !== "project" && a.project_name,
                  a.series && a.series_title && <MeetingLabel key="m" series={a.series} title={a.series_title} on={a.meeting_on} />,
                  hasOrigin(a.origin) && <OriginLink key="o" origin={a.origin} />,
                ])}
              />
            ))}
            {page.open_questions.map((q) => (
              <Row
                key={q.id}
                pill={<Pill tone="neutral">{t("unfiled.kind.question")}</Pill>}
                title={<a href={viewHref(recordView("question", q.id))}>{q.title}</a>}
                meta={joined([
                  q.to_name && t("record.asked_of", { name: q.to_name }),
                  q.series && q.series_title && <MeetingLabel key="m" series={q.series} title={q.series_title} on={q.meeting_on} />,
                  hasOrigin(q.origin) && <OriginLink key="o" origin={q.origin} />,
                ])}
              />
            ))}
          </ul>
        </Section>
      )}
      {completed.length > 0 && (
        <Section id="record-completed" title={t("record.completed")} count={completed.length}>
          <ul className="queue">
            {completed.map((c) => (
              <Row
                key={c.id}
                pill={<Pill tone="ok">{t("record.done")}</Pill>}
                title={<a href={viewHref(recordView("action", c.id))}>{c.text}</a>}
                meta={joined([
                  (c.done_by ?? []).length ? t("record.done_by", { names: (c.done_by ?? []).join(", ") }) : t("record.closed"),
                  c.reported_by && t("record.reported_by", { name: c.reported_by }),
                  c.done_on && monthDay(c.done_on),
                  page.kind !== "project" && c.project_name,
                ])}
              />
            ))}
          </ul>
        </Section>
      )}
      {page.activity.length > 0 && (
        <Section id="record-activity" title={t("record.activity")}>
          <ol className="timeline">
            {page.activity.map((e, i) => (
              <li key={`${e.at}-${e.id}-${e.op}-${i}`}>
                <span className="when">{monthDay(e.at)}</span>{" "}
                <span>{t("record.did", { who: e.by_assistant ? t("record.by_assistant") : t("record.by_you"), what: did(e) })}</span>{" "}
                <strong>{e.name}</strong>
              </li>
            ))}
          </ol>
        </Section>
      )}
      {open === 0 && completed.length === 0 && page.activity.length === 0 && <p className="hint">{t("record.nothing_yet")}</p>}
      <span className="sr">{tn("record.items_count", open)}</span>
    </div>
  );
}
