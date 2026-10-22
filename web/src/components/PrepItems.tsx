// The open things with a person, as rows (design 7.14): what the person promised them, what they promised the person, what
// they asked and what was asked of them, each as one row with its day, how long it has been quiet and the exact words it was
// made from. Shown in a meeting's prep and on a person's page. Record display only: a row links to nothing it changes.
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";

export type OpenItem = S["OpenItemView"];

/** One kind of item under its heading; nothing at all when there are none. */
export function PrepItems(props: { kind: OpenItem["kind"]; items: OpenItem[]; name: string; heading?: boolean }) {
  const { t, tn } = useWords();
  if (props.items.length === 0) return null;
  return (
    <div data-items={props.kind}>
      {props.heading !== false && <h4>{t(`meeting.items.${props.kind}`, { name: props.name })}</h4>}
      <ul className="queue">
        {props.items.map((item) => (
          <Row
            key={`${item.record}:${item.id}`}
            pill={item.quiet > 0 ? <Pill tone="neutral">{tn("meeting.items.quiet", item.quiet)}</Pill> : undefined}
            title={item.text}
            meta={[item.due ? t("meeting.items.due", { date: day(item.due) }) : "", item.quote ? t("meeting.items.quote", { quote: item.quote }) : ""].filter(Boolean).join(" · ") || undefined}
          />
        ))}
      </ul>
    </div>
  );
}

export const ITEM_KINDS = ["promised_to", "promised_by", "asked_by", "asked_of"] as const;
