// What is to be taken up at a meeting (design 7.14): each item is the words it is there under, linking to the action,
// question or note it came from, with who put it there and when. Record display only: an item is listed, never changed
// from here. Shown on a meeting's page, on its series' page and under its row in Today's agenda.
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";

type Line = S["AgendaLine"];

/** The items as rows under an "Agenda" heading; nothing at all when there are none. */
export function AgendaSection(props: { items: Line[]; id: string }) {
  const { t } = useWords();
  if (props.items.length === 0) return null;
  return (
    <section aria-labelledby={props.id} className="record-section">
      <div className="heading">
        <h3 id={props.id}>{t("agenda.heading")}</h3>
      </div>
      <ul className="queue">
        {props.items.map((item) => (
          <Row
            key={`${item.kind}:${item.id}`}
            pill={<Pill tone="neutral">{t(`agenda.kind.${item.kind}`)}</Pill>}
            title={<a href={viewHref(recordView(item.kind, item.id))}>{item.text}</a>}
            meta={item.added_by_name ? t("agenda.put_by", { name: item.added_by_name, day: day(item.added_at) }) : t("agenda.put_by_assistant", { day: day(item.added_at) })}
          />
        ))}
      </ul>
    </section>
  );
}

/** The items as a short list under a Today agenda row, each a link; nothing when there are none. */
export function AgendaItems(props: { items: Line[] }) {
  const { t } = useWords();
  if (props.items.length === 0) return null;
  return (
    <ul className="tb-agenda" aria-label={t("agenda.heading")}>
      {props.items.map((item) => (
        <li key={`${item.kind}:${item.id}`}>
          <a href={viewHref(recordView(item.kind, item.id))}>{item.text}</a>
        </li>
      ))}
    </ul>
  );
}
