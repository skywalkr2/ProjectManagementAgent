// Who is asked to a calendar entry kept from a calendar (design 7.14): who invited, each person asked with their answer,
// and the person's own answer when they were invited. A person the workspace knows links to their page.
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";

type Someone = { address?: string | null; name?: string | null; person?: string | null; response?: string | null };

const isSomeone = (value: unknown): value is Someone => typeof value === "object" && value !== null;

export function Attendees(props: { fields: Record<string, unknown>; names: Map<string, string> }) {
  const { t, has } = useWords();
  const asked = (Array.isArray(props.fields.attendees) ? props.fields.attendees : []).filter(isSomeone);
  const organizer = isSomeone(props.fields.organizer) ? props.fields.organizer : null;
  if (asked.length === 0 && organizer === null) return null;
  const invited = props.fields.invitation === true;
  const own = typeof props.fields.response === "string" ? props.fields.response : null;
  const answer = (response: string) => (has(`record.response.${response}`) ? t(`record.response.${response}`) : response);
  const nameOf = (who: Someone) => (who.person ? props.names.get(who.person) : undefined) || who.name || who.address || "";
  const shown = (who: Someone) =>
    who.person ? <a href={viewHref(recordView("person", who.person))}>{nameOf(who)}</a> : <span>{nameOf(who)}</span>;
  return (
    <section aria-labelledby="record-attendees" className="attendees">
      <h3 id="record-attendees">{t("record.attendees")}</h3>
      {organizer && (
        <p className="hint">
          {t(invited ? "record.invited_by" : "record.organized_by")} {shown(organizer)}
        </p>
      )}
      {invited && own && <p className="hint">{t("record.your_answer", { answer: answer(own) })}</p>}
      {asked.length > 0 && (
        <ul className="attendee-list">
          {asked.map((who, i) => (
            <li key={`${who.address ?? who.name ?? ""}:${i}`}>
              {shown(who)}
              {who.address && nameOf(who) !== who.address && <span className="sub"> · {who.address}</span>}
              {who.response && <span className="sub"> · {answer(who.response)}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
