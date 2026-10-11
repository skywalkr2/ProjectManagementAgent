// Lines the enabled plugins add to Today (design 7.7): one row each, with the one thing to do from it as the primary
// action. The whole section is absent when no plugin has anything to say.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { day } from "../lib/dates";
import { usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { useWords } from "../lib/wording";
import { SafeText } from "./SafeText";

/** `compact` is for a narrow column on Today: the heading sits one level down. */
export function PluginToday(props: { compact?: boolean }) {
  const Heading = props.compact ? "h3" : "h2";
  const { t } = useWords();
  const lines = useQuery({ queryKey: ["plugin-today"], queryFn: api.pluginToday });
  const { run, review } = usePluginRun();
  if (!lines.data || lines.data.length === 0) return null;
  return (
    <section className={props.compact ? "panel-section compact" : "panel-section"} aria-labelledby="plugin-today-title">
      <div className="heading">
        <Heading id="plugin-today-title">{t("today.plugins.title")}</Heading>
      </div>
      <ul className="queue">
        {lines.data.map((line) => (
          <TodayRow key={`${line.plugin}:${line.id}`} line={line} run={run} />
        ))}
      </ul>
      {review}
    </section>
  );
}

function waiting(line: S["TodayLineView"], t: ReturnType<typeof useWords>["t"]): string {
  const until = line.until ? (/^\d{4}-\d{2}-\d{2}/.test(line.until) ? day(line.until) : line.until) : "";
  const why = line.why?.trim() ?? "";
  if (why && until) return t("today.plugins.waiting_until", { why, until });
  if (why) return t("today.plugins.waiting", { why });
  if (until) return t("today.plugins.until", { until });
  return "";
}

function TodayRow(props: { line: S["TodayLineView"]; run: (offer: Offer, target: S["RecordReference"] | null) => void }) {
  const { t } = useWords();
  const { line } = props;
  const about = line.about ?? null;
  const isAction = line.action_is === "action";
  const isTask = line.action_is === "task";
  const actions = usePluginActions(about?.kind, about?.id, !!line.action && isAction);
  const tasks = useTaskKinds(about?.kind, about?.id, !!line.action && isTask);
  const found = (isAction ? actions.data : tasks.data)?.find((x) => x.name === line.action);
  const label = found?.label ?? t("today.plugins.go");
  const wait = waiting(line, t);
  const titleId = `today-${line.plugin}-${line.id}`.replace(/[^A-Za-z0-9_-]/g, "-");
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className={line.action && line.action_is ? "row pair" : "row single"}>
        <div className="text">
          <div id={titleId} className="name">
            <SafeText text={line.text} />
          </div>
          {wait && <span className="sub">{wait}</span>}
        </div>
        {line.action && line.action_is && (
          <div className="acts">
            <button
              type="button"
              className="btn primary"
              data-key="primary"
              onClick={() => props.run({ name: line.action!, label, is: line.action_is!, on: about?.kind ?? null }, about)}
            >
              {label}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
