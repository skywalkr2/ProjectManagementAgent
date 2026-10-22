// What the assistant knows about a project (design 7.18), on the project's page: where its inputs come from and the last
// one from each, its facts with who they rest on and when (answer 29: the source label, "Inferred" and Confirm it), the
// glossary terms used there, who answers what, and what is still unknown with the question asked for it. It reads, and the
// one thing it changes is a fact the person confirms. Every row is one thing; a section with nothing says so in words.
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, type S } from "../lib/api";
import { monthDay } from "../lib/dates";
import { recordView, viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { LoadFailed } from "../ui/LoadFailed";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { FactSource } from "./FactSource";
import { OriginLink } from "./Origin";

/** The ways an input arrives that the sheet has a word for; any other is "another input". */
const KINDS = ["pasted", "email", "calendar", "change", "note", "task"];
const FIELDS = ["status", "phase", "target", "owner", "summary"] as const;

function Part(props: { id: string; title: string; empty: string; count: number; children: ReactNode }) {
  return (
    <section aria-labelledby={props.id} className="record-section">
      <div className="heading">
        <h3 id={props.id}>{props.title}</h3>
        {props.count > 0 && <span className="hint">{props.count}</span>}
      </div>
      {props.count === 0 ? <p className="empty">{props.empty}</p> : <ul className="queue">{props.children}</ul>}
    </section>
  );
}

/** Which accounts may read the project's material, and whether reading it sends anything away from this computer (design
 * 6.32). It says so in words, and each account says where it runs, so nothing rests on a color. */
function Reading(props: { reading: S["ProjectReading"]; area: boolean }) {
  const { t } = useWords();
  const { reading } = props;
  const names = reading.readers.map((r) => r.name).join(", ");
  const summary = reading.state === "none" ? t("knows.reading.none") : t(reading.state === "local" ? "knows.reading.local" : "knows.reading.away", { names });
  return (
    <section aria-labelledby="knows-reading" className="record-section" data-reading={reading.state}>
      <div className="heading">
        <h3 id="knows-reading">{t("knows.reading")}</h3>
      </div>
      {props.area && <p className="hint">{t("knows.area")}</p>}
      <p>{summary}</p>
      {reading.levels.length > 0 && <p className="hint">{t("knows.reading.levels", { levels: reading.levels.join(", ") })}</p>}
      {reading.readers.length > 0 && (
        <ul className="queue">
          {reading.readers.map((r) => (
            <Row key={r.account} title={r.name} meta={t(r.leaves ? "knows.reading.sent_away" : "knows.reading.on_this_computer")} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Sources(props: { rows: S["KnowsSource"][] }) {
  const { t, tn } = useWords();
  return (
    <Part id="knows-sources" title={t("knows.sources")} empty={t("knows.sources.empty")} count={props.rows.length}>
      {props.rows.map((s) => (
        <Row
          key={s.key}
          title={s.label ?? t(`knows.kind.${s.kind && KINDS.includes(s.kind) ? s.kind : "other"}`)}
          meta={t("knows.source.meta", { inputs: tn("knows.source.inputs", s.inputs), day: monthDay(s.last.received_at) })}
        >
          <OriginLink origin={{ kind: "source", source: s.last.id }} label={s.last.title} />
        </Row>
      ))}
    </Part>
  );
}

function Facts(props: { rows: S["KnowsFact"][] }) {
  const { t } = useWords();
  return (
    <Part id="knows-facts" title={t("knows.facts")} empty={t("knows.facts.empty")} count={props.rows.length}>
      {props.rows.map((f) => (
        <Row
          key={f.id}
          pill={f.key ? <Pill tone="neutral">{t("knows.key")}</Pill> : undefined}
          title={<a href={viewHref(recordView("fact", f.id))}>{f.text}</a>}
          meta={<FactSource inline source={f.source} fact={f.id} version={f.version} />}
        />
      ))}
    </Part>
  );
}

function Terms(props: { rows: S["KnowsTerm"][] }) {
  const { t } = useWords();
  return (
    <Part id="knows-terms" title={t("knows.terms")} empty={t("knows.terms.empty")} count={props.rows.length}>
      {props.rows.map((x) => (
        <Row
          key={x.id}
          pill={<Pill tone={x.confidence === "unknown" ? "warn" : "neutral"}>{t(`knows.confidence.${x.confidence}`)}</Pill>}
          title={x.term}
          meta={x.confidence === "unknown" ? undefined : x.meaning}
        />
      ))}
    </Part>
  );
}

function Routing(props: { rows: S["KnowsRouting"][] }) {
  const { t } = useWords();
  return (
    <Part id="knows-routing" title={t("knows.routing")} empty={t("knows.routing.empty")} count={props.rows.length}>
      {props.rows.map((r) => (
        <Row
          key={r.id}
          title={r.topic}
          meta={[t(r.negative ? "knows.routing.not" : "knows.routing.answers", { who: r.who }), r.look_up && t("knows.routing.look_up", { where: r.look_up })]
            .filter(Boolean)
            .join(" · ")}
        />
      ))}
    </Part>
  );
}

function Unknown(props: { rows: S["KnowsUnknown"][] }) {
  const { t } = useWords();
  return (
    <Part id="knows-unknown" title={t("knows.unknown")} empty={t("knows.unknown.empty")} count={props.rows.length}>
      {props.rows.map((u) => {
        const q = u.question;
        const field = u.field && FIELDS.includes(u.field) ? u.field : null;
        return (
          <Row
            key={u.entry ?? u.field ?? u.term}
            title={u.kind === "term" ? t("knows.unknown.term", { term: u.term ?? "" }) : field ? t(`knows.unknown.${field}`) : ""}
            meta={
              q ? (
                <>
                  {t("knows.unknown.asked", { name: q.to_name })}: <a href={viewHref(recordView("question", q.id))}>{q.title}</a>
                </>
              ) : (
                t("knows.unknown.nobody")
              )
            }
          />
        );
      })}
    </Part>
  );
}

export function ProjectKnows(props: { id: string }) {
  const { t } = useWords();
  const knows = useQuery({ queryKey: ["project-knows", props.id], queryFn: () => api.projectKnows(props.id) });
  const data = knows.data;
  return (
    <section aria-labelledby="knows-title" className="record-section" data-project-knows="">
      <div className="heading">
        <h2 id="knows-title">{t("knows.title")}</h2>
      </div>
      {knows.isPending && <Skeleton />}
      {knows.isError && <LoadFailed message={t("knows.load_failed")} onRetry={() => void knows.refetch()} />}
      {data && (
        <>
          <Reading reading={data.reading} area={data.area} />
          <Sources rows={data.sources} />
          <Facts rows={data.facts} />
          <Terms rows={data.terms} />
          <Routing rows={data.routing} />
          <Unknown rows={data.unknown} />
        </>
      )}
    </section>
  );
}
