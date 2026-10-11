// Lines the enabled plugins add to Today (design 7.7): one row each, with the one thing to do from it as the primary
// action. The whole section is absent when no plugin has anything to say.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useEstimate } from "../lib/money";
import { usePluginActions, useTaskKinds, type Offer } from "../lib/plugin-actions";
import { usePluginRun } from "../lib/plugin-run";
import { reveal } from "../lib/reveal";
import { sameItem, useMove, useStageRecords } from "../lib/stages";
import { recordView, toHash } from "../lib/views";
import { useWords } from "../lib/wording";
import { SafeText } from "./SafeText";

/** `compact` is for a narrow column on Today: the heading sits one level down. */
export function PluginToday(props: { compact?: boolean; onOpenRecord?: (kind: string, id: string) => void }) {
  const Heading = props.compact ? "h3" : "h2";
  const { t } = useWords();
  const lines = useQuery({ queryKey: ["plugin-today"], queryFn: api.pluginToday });
  const { run, review } = usePluginRun();
  // Opening a record's page: the app's own way when it is given, else the address it keeps the screen in.
  const open = (kind: string, id: string) => {
    if (props.onOpenRecord) props.onOpenRecord(kind, id);
    else window.location.hash = toHash(recordView(kind, id));
  };
  if (!lines.data || lines.data.length === 0) return null;
  return (
    <section className={props.compact ? "panel-section compact" : "panel-section"} aria-labelledby="plugin-today-title">
      <div className="heading">
        <Heading id="plugin-today-title">{t("today.plugins.title")}</Heading>
      </div>
      <ul className="queue">
        {lines.data.map((line) => (
          <TodayRow key={`${line.plugin}:${line.id}`} line={line} run={run} open={open} />
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

type Open = (kind: string, id: string) => void;
type Run = (offer: Offer, target: S["RecordReference"] | null) => void;

function TodayRow(props: { line: S["TodayLineView"]; run: Run; open: Open }) {
  const { t } = useWords();
  const { line } = props;
  const about = line.about ?? null;
  const isAction = line.action_is === "action";
  const isTask = line.action_is === "task";
  const isCore = line.action_is === "core" && !!line.action && !!about;
  const runnable = !!line.action && (isAction || isTask);
  const actions = usePluginActions(about?.kind, about?.id, !!line.action && isAction);
  const tasks = useTaskKinds(about?.kind, about?.id, !!line.action && isTask);
  const found = (isAction ? actions.data : tasks.data)?.find((x) => x.name === line.action);
  const label = found?.label ?? t("today.plugins.go");
  const wait = waiting(line, t);
  const titleId = `today-${line.plugin}-${line.id}`.replace(/[^A-Za-z0-9_-]/g, "-");
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className={runnable || isCore ? "row pair" : "row single"}>
        <div className="text">
          <div id={titleId} className="name">
            <SafeText text={line.text} />
          </div>
          {wait && <span className="sub">{wait}</span>}
        </div>
        {isCore && (
          <div className="acts">
            <CoreAction action={line.action!} about={about!} describedBy={titleId} open={props.open} />
          </div>
        )}
        {runnable && (
          <div className="acts">
            <button
              type="button"
              className="btn primary"
              data-key="primary"
              onClick={() => props.run({ name: line.action!, label, is: isAction ? "action" : "task", on: about?.kind ?? null }, about)}
            >
              {label}
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

/** The core's own actions on a line's record, each wired to what the app does for it elsewhere. */
function CoreAction(props: { action: string; about: S["RecordReference"]; describedBy: string; open: Open }) {
  const { action, about } = props;
  if (action === "go") return <GoButton about={about} describedBy={props.describedBy} open={props.open} />;
  if (action === "move-stage") return <MoveButton about={about} describedBy={props.describedBy} open={props.open} />;
  if (action === "review" && about.kind === "changeset")
    return (
      <PrimaryButton
        word="today.plugins.review"
        describedBy={props.describedBy}
        // The answer's own review is in What changed; a changeset that isn't listed there has no page of its own.
        onClick={() => {
          if (!reveal("changeset", about.id)) props.open(about.kind, about.id);
        }}
      />
    );
  if (action === "answer")
    return (
      <PrimaryButton
        word="today.plugins.answer"
        describedBy={props.describedBy}
        onClick={() => {
          if (!reveal("question", about.id)) props.open(about.kind, about.id);
        }}
      />
    );
  // "open", and a review of a record's own draft: the record's page, where its text is reviewed.
  return (
    <PrimaryButton
      word={action === "review" ? "today.plugins.review" : "today.plugins.open"}
      describedBy={props.describedBy}
      onClick={() => props.open(about.kind, about.id)}
    />
  );
}

function PrimaryButton(props: { word: string; describedBy: string; disabled?: boolean; onClick: () => void }) {
  const { t } = useWords();
  return (
    <button
      type="button"
      className="btn primary"
      data-key="primary"
      disabled={props.disabled}
      aria-describedby={props.describedBy}
      onClick={props.onClick}
    >
      {t(props.word)}
    </button>
  );
}

/** Give the go to a queued run: the same call as the Go on a run held back for its cost, with the estimate beside it. */
function GoButton(props: { about: S["RecordReference"]; describedBy: string; open: Open }) {
  const { t } = useWords();
  const act = useAct();
  const estimate = useEstimate();
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  const request = changes.data?.find((c) => c.id === props.about.id);
  if (changes.isPending) return <PrimaryButton word="today.plugins.give_go" describedBy={props.describedBy} disabled onClick={() => undefined} />;
  // Not waiting for a go any more (given elsewhere, or gone): nothing to give it to, so the record is what's left to open.
  if (!request || request.approval !== "required" || request.state !== "needs_you")
    return <PrimaryButton word="today.plugins.open" describedBy={props.describedBy} onClick={() => props.open(props.about.kind, props.about.id)} />;
  const cost = estimate(request.estimate_usd);
  return (
    <>
      {cost && <span className="hint">{cost}</span>}
      <PrimaryButton
        word="today.plugins.give_go"
        describedBy={props.describedBy}
        onClick={() => void act(() => api.stageGo(request.id, request.version), () => ({ message: t("toast.go") }))}
      />
    </>
  );
}

/** Move a record to its next stage: the same call as the stages screen, with its Undo; a refusal is said on the row. */
function MoveButton(props: { about: S["RecordReference"]; describedBy: string; open: Open }) {
  const records = useStageRecords();
  const { error, busy, move } = useMove();
  const view = records.data?.find((v) => sameItem(v.record, props.about));
  const next = view?.next;
  if (!view || !next || !view.ready)
    return <PrimaryButton word="today.plugins.open" describedBy={props.describedBy} onClick={() => props.open(props.about.kind, props.about.id)} />;
  return (
    <>
      <PrimaryButton word="today.plugins.move_on" describedBy={props.describedBy} disabled={busy} onClick={() => void move(view, next)} />
      {error && (
        <p className="problem-note" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
