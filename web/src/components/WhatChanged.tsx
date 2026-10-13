// What changed (design 7.3): one row per thing handed in, with what the assistant did nested inside it.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { dayAndTime, day } from "../lib/dates";
import { firstGoOf, useFirstGoSorting } from "../lib/first-go";
import { useRowKeys } from "../lib/keys";
import { showRow, useReveal } from "../lib/reveal";
import { useEstimate } from "../lib/money";
import { useSetAside } from "../lib/set-aside";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { AskChooser } from "./AskChooser";
import { FirstGoRow } from "./FirstGoRow";
import { RowMenu, type MenuAction } from "./RowMenu";
import { Highlighted } from "./SafeText";
import { StageTodayRows, useStageToday } from "./StageToday";
import { useOwnRequests } from "./HandIn";

type Filter = "attention" | "done" | "all";
const ATTENTION = new Set(["queued", "running", "review", "needs_you"]);

/** Still in progress, waiting for review, or holding something until the PM answers. */
export function needsAttention(c: S["ChangeItem"]): boolean {
  return ATTENTION.has(c.state) || !!c.changeset?.ops.some((o) => o.ask?.status === "open");
}

/** `compact` is for a narrow column on Today: the heading sits one level down. `onOpenGuide` opens the setup guide at a
 * step, for a stopped line whose way on is a step of the guide. */
export function WhatChanged(props: { compact?: boolean; onOpenGuide?: (step: string) => void }) {
  const Heading = props.compact ? "h3" : "h1";
  const { t, tn } = useWords();
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  const own = useOwnRequests();
  const stageToday = useStageToday();
  const [filter, setFilter] = useState<Filter>("attention");
  const [shown, setShown] = useState<Set<string> | null>(null);
  const [announce, setAnnounce] = useState("");
  // A Today line asking for an answer to be looked at: the row (by request) opens, whatever the filter.
  const [revealed, setRevealed] = useState<{ id: string; n: number } | null>(null);
  const latest = useRef(changes.data);
  latest.current = changes.data;
  useReveal("changeset", (changeset) => {
    const item = latest.current?.find((c) => c.changeset?.id === changeset);
    if (!item) return false;
    setFilter("all");
    setShown((prev) => new Set([...(prev ?? []), item.id]));
    setRevealed({ id: item.id, n: Date.now() });
    return true;
  });

  // Rows that arrive while the PM is reading wait behind "N new · Show" instead of moving the list,
  // except the PM's own hand-ins, which they expect to see.
  useEffect(() => {
    if (!changes.data) return;
    const ids = changes.data.map((c) => c.id);
    setShown((prev) => {
      if (prev === null) return new Set(ids);
      const add = ids.filter((id) => !prev.has(id) && own.has(id));
      return add.length ? new Set([...prev, ...add]) : prev;
    });
  }, [changes.data, own]);

  const waiting = useMemo(
    () => (changes.data && shown ? changes.data.filter((c) => !shown.has(c.id)) : []),
    [changes.data, shown],
  );
  useEffect(() => {
    if (waiting.length) setAnnounce(tn("changes.new_arrived", waiting.length));
  }, [waiting.length, tn]);

  // A stage task waiting for the go has its own row below; its plain request row would only offer a retry.
  // Runs waiting for the first go are one line together while the list shows what needs attention.
  const waitingGo = new Set(stageToday.waiting.map((w) => w.request.id));
  const sorting = useFirstGoSorting(firstGoOf(changes.data).count > 0);
  const first = firstGoOf(changes.data, sorting);
  const firstLine = filter === "attention" && first.count > 0;
  const rows = (changes.data ?? []).filter(
    (c) =>
      shown?.has(c.id) &&
      !waitingGo.has(c.id) &&
      !(firstLine && c.first_go) &&
      (filter === "all" || (filter === "attention") === needsAttention(c)),
  );
  const stageRows = (filter === "attention" ? stageToday.count : 0) + (firstLine ? 1 : 0);
  const filters: Filter[] = ["attention", "done", "all"];

  return (
    <section className={props.compact ? "panel-section compact" : "panel-section"} aria-labelledby="changes-title">
      <div className="heading">
        <Heading id="changes-title">{t("changes.title")}</Heading>
        <div className="filters" role="group" aria-label={t("changes.filter")}>
          {filters.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`changes.filter.${f}`)}
            </button>
          ))}
        </div>
      </div>
      <p className="sr" aria-live="polite">
        {announce}
      </p>
      {waiting.length > 0 && (
        <button
          type="button"
          className="newbar"
          onClick={() => setShown(new Set([...(shown ?? []), ...waiting.map((c) => c.id)]))}
        >
          {tn("changes.show_new", waiting.length)}
        </button>
      )}
      {changes.isPending ? (
        <Skeleton />
      ) : changes.isError ? (
        <p className="empty">
          {t("changes.load_failed")}{" "}
          <button type="button" className="btn" onClick={() => void changes.refetch()}>
            {t("action.try_again")}
          </button>
        </p>
      ) : rows.length === 0 && stageRows === 0 ? (
        <p className="empty">{t(filter === "attention" ? "changes.empty_attention" : "changes.empty")}</p>
      ) : (
        <ol className="queue">
          {firstLine && <FirstGoRow first={first} />}
          {filter === "attention" && <StageTodayRows today={stageToday} />}
          {rows.map((item) => (
            <ChangeRow
              key={item.id}
              item={item}
              reveal={revealed?.id === item.id ? revealed.n : 0}
              onOpenGuide={props.onOpenGuide}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

function Skeleton() {
  const { t } = useWords();
  return (
    <ol className="queue" aria-busy="true" aria-label={t("loading")}>
      {[0, 1, 2].map((i) => (
        <li key={i} className="line skeleton" aria-hidden="true">
          <div className="row">
            <span className="kind" />
            <span className="bar" />
          </div>
        </li>
      ))}
    </ol>
  );
}

const PILL: Record<S["ChangeItem"]["state"], string> = {
  queued: "k-wait",
  running: "k-wait",
  review: "k-review",
  needs_you: "k-held",
  done: "k-done",
  failed: "k-risk",
};

/** A run held back because its estimate is above the amount to confirm (stage tasks have their own go row). */
export function waitsForGo(c: S["ChangeItem"]): boolean {
  return c.approval === "required" && !c.stage_task && c.state === "needs_you" && !c.dismissed;
}

function ChangeRow(props: { item: S["ChangeItem"]; reveal: number; onOpenGuide?: (step: string) => void }) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const estimate = useEstimate();
  const { setAside: moveToFolder } = useSetAside();
  const { item } = props;
  const gated = waitsForGo(item);
  const cs = item.changeset;
  const [open, setOpen] = useState(item.state === "review" || (item.state === "needs_you" && !gated));
  const [sendingBack, setSendingBack] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  const title = item.source_title || firstLine(item.note) || t("changes.untitled");
  const live = cs ? cs.ops.filter((o) => o.status === "applied" || o.status === "held") : [];
  useEffect(() => {
    if (!props.reveal) return;
    setOpen(true);
    showRow(ref.current);
  }, [props.reveal]);

  const looksGood = () =>
    cs &&
    act(
      () => api.looksGood(cs.id),
      () => ({ message: t("toast.looks_good"), undo: () => api.reopen(cs.id) }),
    );
  const undoAll = () =>
    cs &&
    act(
      () => api.undo(cs.id),
      (report) => ({ message: undoMessage(report, t, tn) }),
    );
  const startSendBack = () => {
    setOpen(true);
    setSendingBack(true);
  };

  const retry = () => void act(() => api.retry(item.id), () => ({ message: t("toast.retrying") }));

  // A stop with a cause the screen can clear offers that one action in place of Try again, which could not work.
  const cause = item.state === "needs_you" || item.state === "failed" ? item.cause : null;
  const allowing = cause?.kind === "data_level" && cause.account && cause.level ? { account: cause.account, level: cause.level } : null;
  const naming = cause?.kind === "no_person" && props.onOpenGuide ? props.onOpenGuide : null;
  const levelWord = (level: string) => (has(`changes.level.${level}`) ? t(`changes.level.${level}`) : level);
  const allow = async () => {
    if (!allowing) return;
    const done = await act(() => api.allowData(item.id));
    if (done) await afterSave(done.saved, { message: t("toast.allowed_data", { account: done.account, level: levelWord(done.level) }) });
  };

  const dismiss = () =>
    void act(
      () => api.dismiss(item.id, item.version),
      (result) => ({ message: t("toast.dismissed"), undo: () => api.undismiss(item.id, result.version) }),
    );

  let primary: { label: string; run: () => void } | null = null;
  if (item.state === "review" && cs) primary = { label: t("changes.looks_good"), run: () => void looksGood() };
  if (gated)
    primary = {
      label: t("changes.go"),
      run: () => void act(() => api.stageGo(item.id, item.version), () => ({ message: t("toast.go") })),
    };
  else if (allowing)
    primary = { label: t("changes.allow_data", { account: allowing.account, level: levelWord(allowing.level) }), run: () => void allow() };
  else if (naming) primary = { label: t("changes.say_who"), run: () => naming("workspace") };
  else if (item.state === "needs_you" || item.state === "failed")
    primary = item.refused
      ? {
          label: t("changes.send_other"),
          run: () => {
            setOpen(true);
            setChoosing(true);
          },
        }
      : { label: t("action.try_again"), run: retry };

  const menu: MenuAction[] = [];
  if (item.refused && (item.state === "needs_you" || item.state === "failed"))
    menu.push({ id: "retry", label: t("action.try_again"), run: retry });
  if (cs && item.state === "review") menu.push({ id: "sendback", label: t("changes.send_back"), run: startSendBack });
  if (item.state === "needs_you" || item.state === "failed") menu.push({ id: "dismiss", label: t("changes.dismiss"), run: dismiss });
  if (cs && item.state === "done") {
    menu.push({
      id: "reopen",
      label: t("changes.reopen"),
      run: () => void act(() => api.reopen(cs.id), () => ({ message: t("toast.reopened"), undo: () => api.looksGood(cs.id) })),
    });
  }
  if (cs && live.length) menu.push({ id: "undoall", label: t("changes.undo_all"), run: () => void undoAll() });
  if (item.mail_item) {
    const mail = { id: item.mail_item, title };
    menu.push(
      { id: "aside-personal", label: t("setaside.menu_personal"), run: () => void moveToFolder(mail, "personal") },
      { id: "aside-sales", label: t("setaside.menu_sales"), run: () => void moveToFolder(mail, "sales") },
    );
  }

  useRowKeys(ref, {
    toggle: () => setOpen((v) => !v),
    primary: primary?.run,
    send_back: cs && item.state === "review" ? startSendBack : undefined,
  });

  return (
    <li className="line" data-row tabIndex={-1} ref={ref} aria-labelledby={`t-${item.id}`} data-changeset={cs?.id}>
      <div className="row">
        <span className={`kind ${PILL[item.state]}`}>
          {t(item.dismissed ? "changes.state.dismissed" : gated ? "changes.state.cost_go" : `changes.state.${item.state}`)}
        </span>
        <button
          type="button"
          className="expander text"
          aria-expanded={open}
          aria-controls={`b-${item.id}`}
          onClick={() => setOpen(!open)}
        >
          <strong id={`t-${item.id}`}>{title}</strong>
          <span className="sub">{gated ? (estimate(item.estimate_usd) ?? t("changes.sub.go_waiting", { when: dayAndTime(item.created_at) })) : subLine(item, t, tn)}</span>
          {cs?.second_opinion && <span className="sub second-opinion">{t(`changes.second.${cs.second_opinion}`)}</span>}
          {item.follows_summary && <span className="sub">{t("changes.follows", { summary: item.follows_summary })}</span>}
        </button>
        <div className="acts">
          {primary && (
            <button type="button" className="btn primary" onClick={primary.run}>
              {primary.label}
            </button>
          )}
          <RowMenu label={title} actions={menu} />
        </div>
      </div>
      {open && (
        <div className="body" id={`b-${item.id}`}>
          {item.note && (
            <div className="your-note">
              <span className="what">{t("changes.your_note")}</span>
              <p>{item.note}</p>
            </div>
          )}
          {item.waiting && item.state !== "review" && <p className="hint">{item.waiting}</p>}
          {cs && cs.summary.trim() && (
            <div className="assistant-summary">
              <span className="what">{t("changes.summary_label")}</span>
              <p>{cs.summary}</p>
            </div>
          )}
          {cs && cs.ops.length === 0 && !cs.summary.trim() && <p className="hint">{t("changes.nothing_done")}</p>}
          {cs && cs.ops.length > 0 && (
            <ul className="children" aria-label={tn("changes.did", cs.ops.length)}>
              {cs.ops.map((op) => (
                <OpRow key={op.index} op={op} cs={cs} source={item.source} />
              ))}
            </ul>
          )}
          {sendingBack && cs && <SendBackForm cs={cs.id} onDone={() => setSendingBack(false)} />}
          {choosing && <AccountChooser request={item.id} onDone={() => setChoosing(false)} />}
        </div>
      )}
    </li>
  );
}

function firstLine(text: string | null): string {
  return (text ?? "").split("\n").find((l) => l.trim())?.trim() ?? "";
}

type T = (key: string, vars?: Record<string, string | number>) => string;
type TN = (key: string, n: number, vars?: Record<string, string | number>) => string;

function subLine(item: S["ChangeItem"], t: T, tn: TN): string {
  const when = dayAndTime(item.created_at);
  if (item.state === "queued" || item.state === "running") return t("changes.sub.waiting", { when });
  if (item.dismissed) return t("changes.sub.dismissed", { when });
  if (item.state === "needs_you" || item.state === "failed") return t("changes.sub.stopped", { when });
  const ops = item.changeset?.ops ?? [];
  const held = ops.filter((o) => o.status === "held" || o.ask?.status === "open").length;
  const did = ops.length ? tn("changes.did", ops.length) : t("changes.did_nothing");
  return held ? t("changes.sub.held", { did, held: tn("changes.held", held), when }) : t("changes.sub.did", { did, when });
}

function undoMessage(report: S["UndoReport"], t: T, tn: TN): string {
  const restored = report.restored.length;
  const skipped = report.skipped.length;
  if (!restored && !skipped) return t("toast.nothing_undone");
  return skipped ? t("toast.undo_partial", { skipped: tn("toast.skipped", skipped) }) : t("toast.undone_items");
}

const OP_PILL: Record<S["OpView"]["status"], string | null> = {
  applied: null,
  held: "k-held",
  refused: "k-risk",
  undone: "k-done",
};

function OpRow(props: { op: S["OpView"]; cs: S["ChangesetView"]; source: string | null }) {
  const { t, tn } = useWords();
  const act = useAct();
  const { op, cs } = props;
  const ref = useRef<HTMLLIElement>(null);
  const [showSource, setShowSource] = useState(false);
  const ask = op.ask && op.ask.status === "open" ? op.ask : null;
  const needsOwner = op.meta.action_status === "held";
  const pillKey = needsOwner && ask ? "owner" : op.status;
  const pill = needsOwner && ask ? "k-held" : OP_PILL[op.status];

  const release = () =>
    act(
      () => api.release(cs.id, op.index),
      () => ({ message: t("toast.released"), undo: () => api.undo(cs.id, [op.index]) }),
    );
  const undoThis = () =>
    act(
      () => api.undo(cs.id, [op.index]),
      (report) => ({ message: undoMessage(report, t, tn) }),
    );

  const menu: MenuAction[] = [];
  if (op.status === "applied") menu.push({ id: "undo", label: t("op.undo_this"), run: () => void undoThis() });
  if (op.evidence && props.source)
    menu.push({ id: "source", label: t(showSource ? "op.hide_source" : "op.show_source"), run: () => setShowSource((v) => !v) });

  useRowKeys(ref, { primary: op.status === "held" && !ask ? () => void release() : undefined });

  const meta = metaLine(op, t);
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        <div className="what">
          {opLabel(op, t)}
          {pill && <span className={`pill ${pill}`}>{t(`op.status.${pillKey}`)}</span>}
        </div>
        <div className="title">{op.title}</div>
        {meta && <div className="meta">{meta}</div>}
        {op.reason && op.status !== "applied" && <div className="reason">{op.reason}</div>}
      </div>
      <div className="acts">
        {op.status === "held" && !ask && (
          <button type="button" className="btn primary" onClick={() => void release()}>
            {t("op.do_anyway")}
          </button>
        )}
        <RowMenu label={op.title} actions={menu} />
      </div>
      {op.evidence && (
        <div className="because">
          {t("op.because")} <q>{op.evidence.quote}</q>{" "}
          {props.source && (
            <button type="button" aria-expanded={showSource} onClick={() => setShowSource(!showSource)}>
              {t(showSource ? "op.hide_source" : "op.show_source")}
            </button>
          )}
        </div>
      )}
      {showSource && op.evidence && props.source && <SourcePanel id={props.source} quote={op.evidence.quote} />}
      {ask && (
        <div className="full">
          <AskChooser ask={ask} />
        </div>
      )}
    </li>
  );
}

/** What the assistant did, in words; a filed note also says where it went. */
function opLabel(op: S["OpView"], t: T): string {
  if (op.op === "note") return op.meta.project ? t("op.note.under", { project: op.meta.project }) : t("op.note.none");
  return t(`op.${op.op}`);
}

function metaLine(op: S["OpView"], t: T): string {
  const bits: string[] = [];
  const m = op.meta;
  if (m.owners?.length) bits.push(m.owners.join(", "));
  if (m.to) bits.push(t("op.meta.to", { name: m.to }));
  if (m.due) bits.push(t("op.meta.due", { date: day(m.due) }));
  if (m.project && op.op !== "note") bits.push(m.project);
  if (m.field) bits.push(t("op.meta.set", { field: m.field, value: String(m.value ?? "") }));
  return bits.join(" · ");
}

function SourcePanel(props: { id: string; quote: string }) {
  const { t } = useWords();
  const source = useQuery({ queryKey: ["source", props.id], queryFn: () => api.source(props.id) });
  if (source.isPending) return <div className="source">{t("loading")}</div>;
  if (source.isError || !source.data) return <div className="source">{t("source.missing")}</div>;
  const s = source.data;
  return (
    <div className="source">
      <div className="src">
        {s.title} · {dayAndTime(s.received_at)}
        {s.trust === "untrusted" && <span className="tag">{t("source.outside")}</span>}
      </div>
      {s.text ? <Highlighted text={s.text} quote={props.quote} /> : <p className="hint">{t("source.not_kept")}</p>}
    </div>
  );
}

function SendBackForm(props: { cs: string; onDone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const [note, setNote] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => area.current?.focus(), []);
  return (
    <form
      className="sendback"
      onSubmit={(e) => {
        e.preventDefault();
        void act(
          () => api.sendBack(props.cs, note),
          () => ({ message: t("toast.sent_back") }),
        ).then(props.onDone);
      }}
    >
      <label className="hint" htmlFor={`sb-${props.cs}`}>
        {t("changes.send_back_label")}
      </label>
      <textarea id={`sb-${props.cs}`} ref={area} value={note} onChange={(e) => setNote(e.target.value)} required />
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <button type="submit" className="btn primary" disabled={!note.trim()}>
          {t("changes.send_back_go")}
        </button>
      </div>
    </form>
  );
}

/** Where a request that an account declined can go instead: the other accounts that may take its material. */
function AccountChooser(props: { request: string; onDone: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const accounts = useQuery({
    queryKey: ["request-accounts", props.request],
    queryFn: () => api.requestAccounts(props.request),
    gcTime: 0,
  });
  const box = useRef<HTMLDivElement>(null);
  const ready = !accounts.isPending;
  useEffect(() => {
    if (ready) box.current?.querySelector<HTMLElement>("button")?.focus();
  }, [ready]);
  const choose = (account: S["AccountChoice"]) =>
    void act(
      () => api.retry(props.request, account.use),
      () => ({ message: t("toast.sent_other", { account: account.label }) }),
    ).then((done) => {
      if (done) props.onDone();
    });
  const list = accounts.data ?? [];
  return (
    <div className="sendback" role="group" aria-labelledby={`ac-${props.request}`} ref={box}>
      <p className="hint" id={`ac-${props.request}`}>
        {t(ready && list.length === 0 ? "changes.no_accounts" : "changes.choose_account")}
      </p>
      {accounts.isPending && <p className="hint">{t("loading")}</p>}
      {accounts.isError && <p className="problem-note">{t("changes.accounts_failed")}</p>}
      {list.length > 0 && (
        <ul className="plain-list account-list">
          {list.map((a) => (
            <li key={a.use}>
              <button type="button" className="btn" onClick={() => choose(a)}>
                {a.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
      </div>
    </div>
  );
}
