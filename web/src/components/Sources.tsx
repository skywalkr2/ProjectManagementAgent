// Sources: the places the assistant keeps reading, one row each with how the last read went, and under them what a
// rule set aside without the assistant reading it, with a way to hand any of it in after all. Where sources are
// listed is the workspace's configuration; this screen shows them and reads one on request.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { whenText as when } from "../lib/dates";
import { useWords } from "../lib/wording";

type Source = S["WatchSourceView"];
type Closed = S["AutoClosedView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** How the last read went, in words. A failed read says it failed here; its reason is shown beside it. */
export function lastReadText(source: Source, t: T): string {
  const last = source.last;
  if (!last) return t("sources.never");
  switch (last.outcome) {
    case "ok":
      return last.new + last.changed + last.removed === 0
        ? t("sources.last.nothing")
        : t("sources.last.counts", { new: last.new, changed: last.changed, gone: last.removed });
    case "baseline":
      return t("sources.last.baseline");
    case "offline":
      return t("sources.last.offline");
    default:
      return t("sources.last.failed");
  }
}

/** Why a source can't be read, while its last read failed. */
export function problemOf(source: Source, t: T): string | null {
  if (source.last?.outcome !== "failed") return null;
  return source.problem || source.last.error || t("sources.problem_generic");
}

export function Sources(props: { onAsk: (question?: string) => void }) {
  const { t } = useWords();
  const sources = useQuery({ queryKey: ["watch"], queryFn: api.watchSources });
  // Only a failure already there when the screen opened is announced at once; later refreshes don't repeat it.
  const [announce, setAnnounce] = useState<Set<string> | null>(null);
  if (sources.data && announce === null) {
    setAnnounce(new Set(sources.data.filter((s) => s.failures >= 1).map((s) => s.id)));
  }
  return (
    <section className="panel-section" aria-labelledby="sources-title">
      <div className="heading">
        <h2 id="sources-title">{t("sources.title")}</h2>
      </div>
      <p className="hint">{t("sources.intro")}</p>
      {sources.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : sources.isError ? (
        <p className="empty">
          {t("sources.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void sources.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : sources.data.length === 0 ? (
        <div className="empty">
          <p>{t("sources.empty")}</p>
          <p>
            <button type="button" className="btn" onClick={() => props.onAsk(t("sources.ask_text"))}>
              {t("sources.empty_ask")}
            </button>
          </p>
        </div>
      ) : (
        <ul className="queue">
          {sources.data.map((source) => (
            <SourceRow key={source.id} source={source} alert={announce?.has(source.id) ?? false} />
          ))}
        </ul>
      )}
      <AutoClosed />
    </section>
  );
}

function SourceRow(props: { source: Source; alert: boolean }) {
  const { t, tn } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { source } = props;
  const titleId = `source-${source.id}`;
  const problem = problemOf(source, t);
  const lastWhen = source.last ? when(source.last.started_at) : "";
  const lastWords = lastReadText(source, t);

  const readNow = async () => {
    setBusy(true);
    await act(
      async () => {
        const fresh = await api.readSource(source.id);
        // Show what the read found at once, without waiting for the list to be fetched again.
        client.setQueryData<Source[]>(["watch"], (all) => all?.map((s) => (s.id === fresh.id ? fresh : s)));
        return fresh;
      },
      (fresh) => ({ message: t("sources.read_toast", { label: fresh.label, result: problemOf(fresh, t) ?? lastReadText(fresh, t) }) }),
    );
    setBusy(false);
  };

  const facts = [
    source.connector_label || t("sources.kind_none"),
    source.enabled ? tn("sources.every", source.every_minutes) : t("sources.off"),
    tn("sources.items", source.items),
  ];
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row pair">
        <div className="text">
          <strong id={titleId}>{source.label}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          <span className="sub">
            {source.last ? t("sources.last", { when: lastWhen, what: lastWords }) : lastWords}
            {source.failures > 1 ? ` · ${t("sources.failures", { n: source.failures })}` : ""}
          </span>
          {problem && (
            <p className="problem-note" role={props.alert ? "alert" : undefined}>
              {problem}
            </p>
          )}
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            disabled={!source.enabled || busy}
            aria-label={t("sources.read_now_named", { label: source.label })}
            onClick={() => void readNow()}
          >
            {t(busy ? "sources.reading" : "sources.read_now")}
          </button>
        </div>
      </div>
    </li>
  );
}

function AutoClosed() {
  const { t } = useWords();
  const closed = useQuery({ queryKey: ["auto-closed"], queryFn: api.autoClosed });
  return (
    <section className="panel-section" aria-labelledby="auto-closed-title">
      <div className="heading">
        <h3 id="auto-closed-title">{t("sources.closed.title")}</h3>
      </div>
      <p className="hint">{t("sources.closed.intro")}</p>
      {closed.isPending ? (
        <p className="empty">{t("loading")}</p>
      ) : closed.isError ? (
        <p className="empty">
          {t("sources.closed.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void closed.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : closed.data.length === 0 ? (
        <p className="empty">{t("sources.closed.empty")}</p>
      ) : (
        <ul className="queue">
          {closed.data.map((item) => (
            <ClosedRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ClosedRow(props: { item: Closed }) {
  const { t } = useWords();
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const { item } = props;
  const titleId = `closed-${item.id}`;
  const lookCloser = async () => {
    setBusy(true);
    await act(
      () => api.closerLook(item.id, item.version),
      () => ({ message: t("sources.closed.toast", { title: item.title }) }),
    );
    setBusy(false);
  };
  const facts = [item.source, when(item.created_at)].filter(Boolean);
  return (
    <li className="line" data-row tabIndex={-1} aria-labelledby={titleId}>
      <div className="row">
        <span className="kind k-done">{t(`sources.closed.change.${item.change}`)}</span>
        <div className="text">
          <strong id={titleId}>{item.title}</strong>
          <span className="sub">{facts.join(" · ")}</span>
          <span className="sub">{t("sources.closed.why", { reason: item.reason })}</span>
        </div>
        <div className="acts">
          <button
            type="button"
            className="btn primary"
            data-key="primary"
            disabled={busy}
            aria-label={t("sources.closed.look_named", { title: item.title })}
            onClick={() => void lookCloser()}
          >
            {t("sources.closed.look")}
          </button>
        </div>
      </div>
    </li>
  );
}
