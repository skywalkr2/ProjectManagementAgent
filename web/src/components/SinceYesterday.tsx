// What changed since yesterday (design 6.32, 6.35): one row for each thing the assistant or a rule did on its own, newest first,
// in the assistant's own words with the quote it rested on and who said it. A close nobody has seen says so in words.
// Open (the record) is the row's one action; Undo is in its menu. Opening the list is what marks it seen, as drawn: the
// line on Today goes until something new happens. The list is kept as it was drawn while the screen is open.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day, dayAndTime } from "../lib/dates";
import { viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { LoadFailed } from "../ui/LoadFailed";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { RowMenu, type MenuAction } from "./RowMenu";

type Entry = S["SinceEntryView"];
type T = (key: string, vars?: Record<string, string | number>) => string;

/** The acts that close something, whose unseen ones are marked. */
const CLOSES = new Set<Entry["act"]>(["closed", "dropped", "set_aside"]);

/** The reason in the assistant's voice: who said what it rested on, or the rule that did it. */
export function whyWords(e: Entry, t: T): string {
  switch (e.because) {
    case "replied":
      return t("since.why.replied", { day: e.day ? day(e.day) : "" });
    case "meeting":
      return t("since.why.meeting");
    case "rule":
      return e.reason ? t("since.why.rule", { reason: e.reason }) : t("since.why.nothing");
    case "sorting":
      return e.reason ? t("since.why.sorting", { reason: e.reason }) : t("since.why.nothing");
    default:
      if (e.quote) {
        if (e.by_you) return t("since.why.said_you", { quote: e.quote });
        return e.said_by_name ? t("since.why.said", { name: e.said_by_name, quote: e.quote }) : t("since.why.said_unknown", { quote: e.quote });
      }
      return e.reason ? t("since.why.reason", { reason: e.reason }) : t("since.why.nothing");
  }
}

/** The act and its reason as one sentence: "Closed “Send the floor plan”: Ana said “it went out this morning”". */
export function sentence(e: Entry, t: T): string {
  const key = e.act === "moved" && !e.day ? "since.act.moved_undated" : `since.act.${e.act}`;
  return t(key, { title: e.title, why: whyWords(e, t), day: e.day ? day(e.day) : "" });
}

type Drawn = { status: "loading" } | { status: "failed" } | { status: "ready"; asOf: string; entries: Entry[] };

export function SinceYesterday(props: { onOpenRecord: (kind: string, id: string) => void }) {
  const { t } = useWords();
  const client = useQueryClient();
  const heading = useRef<HTMLHeadingElement>(null);
  const [drawn, setDrawn] = useState<Drawn>({ status: "loading" });
  const [gone, setGone] = useState<ReadonlySet<string>>(new Set());
  const load = useCallback(async () => {
    setDrawn({ status: "loading" });
    try {
      const body = await api.sinceYesterday();
      setDrawn({ status: "ready", asOf: body.as_of, entries: body.entries });
      // Opening the list is what marks it seen, as it was drawn; a failure here only leaves Today's line where it was.
      if (body.entries.length > 0) {
        await api.sinceSeen(body.as_of).catch(() => undefined);
        await client.invalidateQueries({ queryKey: ["today"] });
      }
    } catch {
      setDrawn({ status: "failed" });
    }
  }, [client]);
  useEffect(() => {
    void load();
  }, [load]);
  // A screen with no field puts the cursor on its heading.
  useEffect(() => heading.current?.focus(), []);
  const entries = drawn.status === "ready" ? drawn.entries.filter((e) => !gone.has(e.ref)) : [];
  return (
    <section className="panel-section" aria-labelledby="since-title">
      <div className="heading">
        <h1 id="since-title" ref={heading} tabIndex={-1}>
          {t("since.title")}
        </h1>
        <a className="btn" href={viewHref("work/changed")}>
          {t("since.back")}
        </a>
      </div>
      <p className="hint">{t("since.intro")}</p>
      {drawn.status === "loading" ? (
        <div aria-busy="true" aria-label={t("since.loading")}>
          <Skeleton />
        </div>
      ) : drawn.status === "failed" ? (
        <LoadFailed message={t("since.load_failed")} onRetry={() => void load()} />
      ) : entries.length === 0 ? (
        <p className="empty">{t("since.empty")}</p>
      ) : (
        <ul className="queue" aria-label={t("since.list_label")}>
          {entries.map((e) => (
            <EntryRow key={e.ref} entry={e} onOpenRecord={props.onOpenRecord} onGone={() => setGone((g) => new Set([...g, e.ref]))} />
          ))}
        </ul>
      )}
    </section>
  );
}

function EntryRow(props: { entry: Entry; onOpenRecord: (kind: string, id: string) => void; onGone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const { entry: e } = props;
  const text = sentence(e, t);
  const unseen = !e.seen && CLOSES.has(e.act);
  const undone = async (run: () => Promise<unknown>, done: string) => {
    const result = await act(run, () => ({ message: t(done, { title: e.title }) }));
    if (result !== undefined) props.onGone();
  };
  const menu: MenuAction[] = [];
  if (e.undo === "changeset" && e.changeset && e.op != null) {
    const cs = e.changeset;
    const op = e.op;
    menu.push({
      id: "undo",
      label: t("since.undo"),
      run: () =>
        void act(
          () => api.undo(cs, [op]),
          (report) => ({ message: report.restored.includes(op) ? t("since.undone", { title: e.title }) : t("since.undo_failed") }),
        ).then((report) => report?.restored.includes(op) && props.onGone()),
    });
  } else if (e.undo === "closer_look" && e.request && e.version != null) {
    const request = e.request;
    const version = e.version;
    menu.push({ id: "closer-look", label: t("since.closer_look"), run: () => void undone(() => api.closerLook(request, version), "since.closer_look_done") });
  } else if (e.undo === "set_aside" && e.snapshot && e.version != null) {
    const snapshot = e.snapshot;
    const version = e.version;
    menu.push({ id: "is-work", label: t("since.is_work"), run: () => void undone(() => api.isWork(snapshot, version), "since.is_work_done") });
  }
  const record = e.record;
  return (
    <Row
      as="li"
      title={text}
      meta={
        <>
          {dayAndTime(e.when)}
          {e.detail ? ` · ${e.detail}` : ""}
          {unseen && (
            <>
              {" · "}
              <strong>{t("since.unseen_close")}</strong>
            </>
          )}
        </>
      }
      data-since-entry={e.ref}
      data-unseen={unseen ? "" : undefined}
      primary={
        record ? (
          <Button size="sm" variant="primary" data-key="primary" aria-label={t("since.open_named", { title: e.title })} onClick={() => props.onOpenRecord(record.kind, record.id)}>
            {t("since.open")}
          </Button>
        ) : undefined
      }
      menu={menu.length > 0 ? <RowMenu label={e.title} actions={menu} /> : undefined}
    />
  );
}
