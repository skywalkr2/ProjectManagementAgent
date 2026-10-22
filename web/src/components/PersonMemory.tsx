// What to remember about a person (design 6.32, 7.14), on their page: when you were last in touch, what is open between you
// both ways, how they like to be reached, their dates and what matters to them. Each part comes from the records by rules and
// carries the words it rests on; a part with nothing in it is left out. Record display only.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import { TouchLine } from "./MeetingPrep";
import { ITEM_KINDS, PrepItems } from "./PrepItems";

export function PersonMemory(props: { person: string }) {
  const { t } = useWords();
  const found = useQuery({ queryKey: ["person-memory", props.person], queryFn: () => api.personMemory(props.person) });
  const memory = found.data;
  if (!memory) return null;
  const kept = Object.entries(memory.reach.kept ?? {});
  const empty = !memory.last_in_touch && kept.length === 0 && memory.dates.length === 0 && memory.matters.length === 0 && ITEM_KINDS.every((k) => memory[k].length === 0);
  return (
    <section aria-labelledby="person-memory" className="record-section" data-person-memory={memory.person}>
      <div className="heading">
        <h3 id="person-memory">{t("memory.heading")}</h3>
      </div>
      {empty && <p className="hint">{t("memory.empty", { name: memory.name })}</p>}
      {memory.last_in_touch ? <TouchLine touch={memory.last_in_touch} /> : !empty && <p className="hint">{t("meeting.touch.none")}</p>}
      {ITEM_KINDS.map((kind) => (
        <PrepItems key={kind} kind={kind} items={memory[kind]} name={memory.name} />
      ))}
      {kept.length > 0 && (
        <div data-memory="reach">
          <h4>{t("memory.reach")}</h4>
          <ul className="attendee-list">
            {kept.map(([channel, address]) => (
              <li key={channel}>
                <span>{address}</span>
                <span className="sub"> · {channel}</span>
                {memory.reach.replies_on === channel && <span className="sub"> · {t("memory.reach.replies")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {memory.dates.length > 0 && (
        <div data-memory="dates">
          <h4>{t("memory.dates")}</h4>
          <ul className="attendee-list">
            {memory.dates.map((d) => (
              <li key={d.fact}>
                <span>{d.text}</span>
                {d.on && <span className="sub"> · {t(d.yearly ? "memory.dates.next_yearly" : "memory.dates.on", { date: day(d.on) })}</span>}
                {d.quote && d.quote !== d.text && <span className="sub"> · {t("meeting.items.quote", { quote: d.quote })}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {memory.matters.length > 0 && (
        <div data-memory="matters">
          <h4>{t("memory.matters")}</h4>
          <ul className="attendee-list">
            {memory.matters.map((k) => (
              <li key={k.fact}>
                <span>{k.text}</span>
                {k.as_of && <span className="sub"> · {t("memory.matters.as_of", { date: day(k.as_of) })}</span>}
                {k.quote && k.quote !== k.text && <span className="sub"> · {t("meeting.items.quote", { quote: k.quote })}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
