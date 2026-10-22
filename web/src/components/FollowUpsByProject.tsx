// Follow-ups grouped by project (design 7.5, 7.13): the same open questions and to-dos as the groups by person, one line per
// project; choosing it shows that project's items in the detail, with who each is with and where it stands. An item's button
// goes to that person's group, where Copy, Mark sent and Record reply are.
import { useRef } from "react";
import type { S } from "../lib/api";
import { useRowKeys } from "../lib/keys";
import { useListChoice, type ListChoice } from "../lib/list-choice";
import { useWords } from "../lib/wording";
import { ListDetail } from "../ui/ListDetail";
import { OriginLink } from "./Origin";

type Section = S["FollowupSection"];

interface Item {
  id: string;
  title: string;
  /** Who it is with: the person's id and name, and whether that is the person themselves. */
  person: string;
  name: string;
  mine: boolean;
  /** Where it stands, from the sheet. */
  state: string;
  kind: "question" | "action";
  origin?: S["FollowupQuestion"]["origin"];
}

type Words = ReturnType<typeof useWords>;

function waiting(days: number | null, chase: boolean, w: Words): string {
  if (days === null) return w.t("followups.by_project.to_send");
  return w.tn(chase ? "followups.waiting_pill.chase" : "followups.waiting_pill", days);
}

function itemsOf(section: Section, w: Words): Array<[string, Item]> {
  const base = { person: section.person, name: section.name, mine: section.is_pm };
  const out: Array<[string, Item]> = [];
  for (const q of section.questions) {
    const state = section.is_pm ? w.t("followups.by_project.yours") : q.status === "sent" ? waiting(q.waiting_days ?? 0, q.chase_due, w) : waiting(null, false, w);
    out.push([q.project_name ?? "", { ...base, id: q.id, title: q.title, state, kind: "question", origin: q.origin }]);
  }
  for (const q of section.later ?? []) {
    out.push([q.project_name ?? "", { ...base, id: q.id, title: q.title, state: w.t("followups.by_project.later"), kind: "question", origin: q.origin }]);
  }
  for (const a of section.actions) {
    const state = section.is_pm ? w.t("followups.by_project.yours") : waiting(a.told_days, a.chase_due, w);
    out.push([a.project_name ?? "", { ...base, id: a.id, title: a.text, state, kind: "action", origin: a.origin }]);
  }
  return out;
}

/** The projects with their items: by name, the items with no project last; within one, the person's own first, then by person. */
export function groupByProject(sections: Section[], w: Words, compact = false): Array<{ project: string; items: Item[] }> {
  const groups = new Map<string, Item[]>();
  for (const s of sections) {
    if (compact && s.is_pm) continue;
    for (const [project, item] of itemsOf(s, w)) groups.set(project, [...(groups.get(project) ?? []), item]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)))
    .map(([project, items]) => ({
      project,
      items: [...items].sort((a, b) => Number(b.mine) - Number(a.mine) || a.name.localeCompare(b.name) || a.title.localeCompare(b.title)),
    }));
}

type Group = { project: string; items: Item[] };

/** The width the list needs beside the pane: a project's name and how many are open. */
const BY_PROJECT_FIT = 420;

export function FollowUpsByProject(props: { sections: Section[]; compact: boolean; beside?: boolean; onOpenPerson: (person: string) => void }) {
  const words = useWords();
  const { t } = words;
  const groups = groupByProject(props.sections, words, props.compact);
  const keyOf = (g: Group) => g.project || "none";
  const choice = useListChoice({ keys: groups.map(keyOf), beside: !!props.beside });
  const selected = groups.find((g) => keyOf(g) === choice.chosen) ?? null;
  const title = (g: Group) => g.project || t("followups.by_project.none");
  return (
    <ListDetail
      title={selected ? title(selected) : ""}
      onClose={choice.close}
      fit={BY_PROJECT_FIT}
      detail={selected ? <ProjectItems group={selected} onOpenPerson={props.onOpenPerson} /> : null}
    >
      <ol className="queue" aria-label={t("followups.by_project.list")}>
        {groups.map((g) => (
          <ProjectLine key={keyOf(g)} group={g} id={keyOf(g)} title={title(g)} choice={choice} />
        ))}
      </ol>
    </ListDetail>
  );
}

function ProjectLine(props: { group: Group; id: string; title: string; choice: ListChoice }) {
  const { tn } = useWords();
  const { choice } = props;
  const ref = useRef<HTMLLIElement>(null);
  useRowKeys(ref, { toggle: () => choice.enter(props.id) });
  return (
    <li className="line" ref={ref} aria-label={props.title} data-project-group={props.group.project} {...choice.rowProps(props.id)}>
      <div className="row single">
        <button type="button" className="expander text" aria-expanded={choice.chosen === props.id} onClick={() => choice.choose(props.id)}>
          <strong>{props.title}</strong>
          <span className="sub">{tn("followups.by_project.count", props.group.items.length)}</span>
        </button>
      </div>
    </li>
  );
}

/** A project's items, each with who it is with and the button that goes to that person's group. */
function ProjectItems(props: { group: Group; onOpenPerson: (person: string) => void }) {
  const { t } = useWords();
  return (
    <ul className="children">
      {props.group.items.map((item) => (
        <li key={item.id} className="child" data-row tabIndex={-1}>
          <div>
            <div className="what">{t(item.kind === "question" ? "followups.question" : "followups.by_project.to_do")}</div>
            <div className="title">{item.title}</div>
            <div className="meta">{[item.mine ? t("followups.you") : item.name, item.state].filter(Boolean).join(" · ")}</div>
            <OriginLink origin={item.origin} />
          </div>
          <div className="acts">
            <button type="button" className="btn" aria-label={t("followups.by_project.open_named", { name: item.mine ? t("followups.you") : item.name })} onClick={() => props.onOpenPerson(item.person)}>
              {t("followups.by_project.open")}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
