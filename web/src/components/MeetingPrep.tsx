// Prep for a calendar entry (design 6.32, 7.14): for each known person coming, what is open between them and the person (the
// promises both ways, questions, replies owed), when they were last in touch and what the last entry with them left open;
// a prep note the assistant drafts when asked (a draft on the page, held for the person's go); and, once the entry has ended,
// the box for what happened at it. All of it is worked out by rules on the server; nothing here changes a record.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { OutsideTag } from "../ui/OutsideTag";
import { CaptureForm } from "./CaptureForm";
import { ITEM_KINDS, PrepItems } from "./PrepItems";

type Person = S["PersonPrepView"];

/** "Last in touch: mail from them on Oct 18", and the subject when it is mail, marked as from outside. */
export function TouchLine(props: { touch: NonNullable<Person["last_in_touch"]> }) {
  const { t } = useWords();
  const { touch } = props;
  return (
    <p className="hint" data-touch={touch.kind}>
      {t(`meeting.touch.${touch.kind}`, { date: day(touch.on) })}
      {touch.subject && (
        <>
          {" · "}
          <span>{touch.subject}</span> {touch.untrusted && <OutsideTag />}
        </>
      )}
    </p>
  );
}

function PersonBlock(props: { person: Person }) {
  const { t, tn } = useWords();
  const { person } = props;
  const nothing = person.promised_to.length + person.promised_by.length + person.asked_by.length + person.asked_of.length === 0;
  return (
    <section className="record-section" data-person={person.person} aria-label={person.name}>
      <div className="heading">
        <h3>
          <a href={viewHref(recordView("person", person.person))}>{person.name}</a>
        </h3>
      </div>
      {person.last_in_touch ? <TouchLine touch={person.last_in_touch} /> : <p className="hint">{t("meeting.touch.none")}</p>}
      {nothing && <p className="hint">{t("meeting.prep.nothing_open", { name: person.name })}</p>}
      {ITEM_KINDS.map((kind) => (
        <PrepItems key={kind} kind={kind} items={person[kind]} name={person.name} />
      ))}
      {person.more > 0 && <p className="hint">{tn("meeting.prep.more", person.more)}</p>}
      {person.left_open && person.left_open.items.length > 0 && (
        <div data-items="left_open">
          <h4>
            {t("meeting.prep.left_open", { title: person.left_open.title, date: day(person.left_open.on) })} {person.left_open.untrusted && <OutsideTag />}
          </h4>
          <PrepItems kind="left_open" items={person.left_open.items} name={person.name} heading={false} />
        </div>
      )}
    </section>
  );
}

function PrepNote(props: { entry: string; note: S["PrepNoteView"] }) {
  const { t } = useWords();
  const act = useAct();
  const { note } = props;
  if (note.state === "none" || note.state === "kept")
    return (
      <p>
        <button type="button" className="btn" onClick={() => void act(() => api.askPrepNote(props.entry), () => ({ message: t("meeting.note.asked") }))}>
          {t(note.state === "kept" ? "meeting.note.again" : "meeting.note.ask")}
        </button>
      </p>
    );
  return <p className="hint">{t(`meeting.note.${note.state}`)}</p>;
}

export function MeetingPrep(props: { entry: string; title: string }) {
  const { t, tn } = useWords();
  const found = useQuery({ queryKey: ["meeting-prep", props.entry], queryFn: () => api.meetingPrep(props.entry) });
  const [capturing, setCapturing] = useState(false);
  const prep = found.data;
  if (!prep) return null;
  const strangers = prep.coming.filter((g) => !g.person);
  return (
    <section aria-labelledby="meeting-prep" className="record-section" data-meeting-prep={prep.event}>
      <div className="heading">
        <h3 id="meeting-prep">{t("meeting.prep.heading")}</h3>
      </div>
      {prep.coming.length === 0 && <p className="hint">{t("meeting.prep.alone")}</p>}
      {prep.people.map((p) => (
        <PersonBlock key={p.person} person={p} />
      ))}
      {strangers.length > 0 && (
        <p className="hint">{tn("meeting.prep.unknown", strangers.length, { names: strangers.map((g) => g.name || g.address || "").join(", ") })}</p>
      )}
      {prep.coming.length > 0 && <PrepNote entry={prep.event} note={prep.note} />}
      {prep.over && prep.captured_at && <p className="hint">{t("meeting.capture.done", { date: day(prep.captured_at) })}</p>}
      {prep.over && !prep.captured_at && !capturing && (
        <p>
          <button type="button" className="btn" onClick={() => setCapturing(true)}>
            {t("meeting.capture.open")}
          </button>
        </p>
      )}
      {capturing && <CaptureForm event={prep.event} title={props.title} onClose={() => setCapturing(false)} />}
    </section>
  );
}
