// What changed (design 7.3): one row per thing handed in, with what the assistant did nested inside it.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { dayAndTime, day } from "../lib/dates";
import { firstGoOf, useFirstGoSorting } from "../lib/first-go";
import { useRowKeys } from "../lib/keys";
import { useFieldLabel } from "../lib/records";
import { useHeldAnswers } from "../lib/held-answers";
import { heldTold, titleWords } from "../lib/queue-words";
import { useIsNarrow, useMediaQuery } from "../lib/media";
import { useListChoice, type ListChoice } from "../lib/list-choice";
import { showRow, useReveal } from "../lib/reveal";
import { recordView, viewHref } from "../lib/views";
import { useEstimate, useSpent } from "../lib/money";
import { useSetAside } from "../lib/set-aside";
import { useAfterSave } from "../lib/settings-save";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { ListDetail } from "../ui/ListDetail";
import { AskChooser } from "./AskChooser";
import { ProjectProposalRow } from "./NextSteps";
import { Because } from "./Because";
import { LearnedLines } from "./Learned";
import { FirstGoRow } from "./FirstGoRow";
import { useChangeThis, type ChangeKind } from "./ChangeThis";
import { PromiseWhy } from "./PromiseWhy";
import { RowMenu, type MenuAction } from "./RowMenu";
import { Highlighted } from "./SafeText";
import { StageTodayRows, useStageToday } from "./StageToday";
import { useOwnRequests } from "./HandIn";
import { ReviewMode } from "./ReviewMode";

/** The width the list needs beside the pane: a state, a title with one line under it, the primary and the menu. */
const CHANGES_FIT = 480;

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
  const { t, tn, has } = useWords();
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
  const [picked, setPicked] = useState<{ id: string; n: number } | null>(null);
  const [wanted, setWanted] = useState<string | null>(null);
  // A Today line for what a newly added source's intake found: the list narrows to that source's intake until it is cleared.
  const [intake, setIntake] = useState<string | null>(null);
  const watched = useQuery({ queryKey: ["watch"], queryFn: api.watchSources, enabled: intake !== null });
  useReveal("intake", (source) => {
    setFilter("all");
    setIntake(source);
    return true;
  });
  const openChangeset = (changeset: string): boolean => {
    const all = latest.current;
    const item = all?.find((c) => c.changeset?.id === changeset);
    if (!all || !item) return false;
    setFilter("all");
    setShown((prev) => new Set([...(prev ?? all.map((c) => c.id)), item.id]));
    setRevealed({ id: item.id, n: Date.now() });
    // The change is chosen, so its detail shows it in full (once the list shows it).
    setPicked({ id: item.id, n: Date.now() });
    return true;
  };
  useReveal("changeset", (changeset) => {
    // Opened from another screen before the list has loaded: it opens the row once it has.
    if (!latest.current) {
      setWanted(changeset);
      return true;
    }
    return openChangeset(changeset);
  });
  useEffect(() => {
    if (wanted && changes.data) {
      openChangeset(wanted);
      setWanted(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, changes.data]);

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
      (intake !== null ? c.intake === intake : shown?.has(c.id)) &&
      !waitingGo.has(c.id) &&
      !(firstLine && c.first_go) &&
      (filter === "all" || (filter === "attention") === needsAttention(c)),
  );
  const stageRows = (filter === "attention" ? stageToday.count : 0) + (firstLine ? 1 : 0);
  const filters: Filter[] = ["attention", "done", "all"];
  // On a phone the items waiting for a look can be gone through one at a time (design 7.1).
  const phone = useIsNarrow() && !props.compact;
  const [reviewing, setReviewing] = useState(false);
  const reviewable = rows.filter((c) => c.state === "review" && !!c.changeset);
  // A list with nothing in it has nothing to hold still: what arrives shows at once, so the first results after a first go are
  // one list, never "5 new · Show" over an empty one.
  useEffect(() => {
    if (changes.data && waiting.length > 0 && rows.length === 0 && stageRows === 0) setShown(new Set(changes.data.map((c) => c.id)));
  }, [changes.data, waiting.length, rows.length, stageRows]);

  // The list | detail choice (design 7.13): beside the list the first change is chosen as the list opens, or the first one
  // holding a question for the person; below 1024px the detail is a drawer that opens when a change is chosen.
  const beside = useMediaQuery("(min-width: 1024px)") && !props.compact;
  const asking = rows.find((c) => !!c.changeset?.ops.some((o) => o.ask?.status === "open"));
  const choice = useListChoice({ keys: rows.map((c) => c.id), beside, first: asking?.id ?? null, reset: `${filter}|${intake ?? ""}` });
  useEffect(() => {
    if (picked) choice.choose(picked.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked]);
  const selected = rows.find((c) => c.id === choice.chosen) ?? null;
  const [want, setWant] = useState<(ChangeWant & { id: string }) | null>(null);
  useEffect(() => setWant(null), [choice.chosen]);
  const asked = (id: string) => (what: ChangeWant["what"]) => {
    setWant({ id, what, n: Date.now() });
    choice.choose(id);
  };

  return (
    <section className={props.compact ? "panel-section compact" : "panel-section"} aria-labelledby="changes-title">
      <div className="heading">
        <Heading id="changes-title">{t("changes.title")}</Heading>
        {!props.compact && (
          <a className="btn" href={viewHref("work/since")}>
            {t("changes.since")}
          </a>
        )}
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
      {intake !== null && (
        <p className="hint" data-intake-filter="">
          {t("changes.intake.title", { source: watched.data?.find((w) => w.id === intake)?.label ?? intake })}{" "}
          <button type="button" className="btn" onClick={() => setIntake(null)}>
            {t("changes.intake.show_all")}
          </button>
        </p>
      )}
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
      ) : reviewing && phone ? (
        <ReviewMode
          items={reviewable}
          render={(item) => <ChangeRow key={item.id} item={item} reveal={0} onOpenGuide={props.onOpenGuide} open />}
          canSendBack={(item) => item.state === "review" && !!item.changeset}
          onClose={() => setReviewing(false)}
        />
      ) : rows.length === 0 && stageRows === 0 ? (
        <p className="empty">{t(filter === "attention" ? "changes.empty_attention" : "changes.empty")}</p>
      ) : (
        <ListDetail
          title={selected ? changeTitle(selected, t, has) : ""}
          onClose={choice.close}
          fit={CHANGES_FIT}
          detail={
            selected ? (
              <ol className="queue detail-queue">
                <ChangeRow
                  key={selected.id}
                  item={selected}
                  pane
                  reveal={0}
                  want={want?.id === selected.id ? want : null}
                  onOpenGuide={props.onOpenGuide}
                />
              </ol>
            ) : null
          }
        >
          <ol className="queue">
            {phone && reviewable.length > 0 && (
              <li className="review-start">
                <button type="button" className="btn primary" onClick={() => setReviewing(true)}>
                  {t("review.start")}
                </button>
              </li>
            )}
            {firstLine && <FirstGoRow first={first} />}
            {filter === "attention" && <StageTodayRows today={stageToday} />}
            {rows.map((item) => (
              <ChangeListRow
                key={item.id}
                item={item}
                choice={choice}
                reveal={revealed?.id === item.id ? revealed.n : 0}
                onWant={asked(item.id)}
                onOpenGuide={props.onOpenGuide}
              />
            ))}
          </ol>
        </ListDetail>
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

/** What a change is called: by the rule Today uses ("Email from <person> · <topic>"), never by the first line of what came in;
 * the stored title is only the way back when the rule has nothing to say. Once the assistant has done something with what the
 * person typed, their words are shown as their note and never as the title; until then (waiting, or stopped) they are all that
 * says what the change is. */
export function changeTitle(item: S["ChangeItem"], t: T, has: (key: string) => boolean): string {
  return titleWords(item.title, t, has) || item.source_title || (item.changeset ? "" : firstLine(item.note)) || t("changes.untitled");
}

/** What a change asks the screen to open in its detail: the note to send it back with, or the choice of another account. */
export interface ChangeWant {
  what: "sendback" | "choose";
  n: number;
}

/** The one primary action of a change and the rest in its menu, the same on its list row and in its detail. `startSendBack`
 * and `startChoosing` open the form each needs, wherever that is shown. */
function useChangeActions(item: S["ChangeItem"], hooks: { onOpenGuide?: (step: string) => void; startSendBack: () => void; startChoosing: () => void }) {
  const { t, tn, has } = useWords();
  const act = useAct();
  const afterSave = useAfterSave();
  const { setAside: moveToFolder } = useSetAside();
  const gated = waitsForGo(item);
  const cs = item.changeset;
  const live = cs ? cs.ops.filter((o) => o.status === "applied" || o.status === "held") : [];
  const title = changeTitle(item, t, has);

  const looksGood = () =>
    cs &&
    act(
      () => api.looksGood(cs.id),
      () => ({ message: t("toast.looks_good"), many: (n) => tn("toast.looks_good_many", n), undo: () => api.reopen(cs.id) }),
    );
  const undoAll = () =>
    cs &&
    act(
      () => api.undo(cs.id),
      (report) => ({ message: undoMessage(report, t, tn) }),
    );
  const retry = () => void act(() => api.retry(item.id), () => ({ message: t("toast.retrying") }));

  // A stop with a cause the screen can clear offers that one action in place of Try again, which could not work.
  const cause = item.state === "needs_you" || item.state === "failed" ? item.cause : null;
  const allowing = cause?.kind === "data_level" && cause.account && cause.level ? { account: cause.account, level: cause.level } : null;
  const naming = cause?.kind === "no_person" && hooks.onOpenGuide ? hooks.onOpenGuide : null;
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
    primary = item.refused ? { label: t("changes.send_other"), run: hooks.startChoosing } : { label: t("action.try_again"), run: retry };

  const menu: MenuAction[] = [];
  if (item.refused && (item.state === "needs_you" || item.state === "failed"))
    menu.push({ id: "retry", label: t("action.try_again"), run: retry });
  if (cs && item.state === "review") menu.push({ id: "sendback", label: t("changes.send_back"), run: hooks.startSendBack });
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
  return { gated, cs, title, primary, menu, canSendBack: !!cs && item.state === "review" };
}

/** What a change's list row says under its title: the estimate while it waits for the go, else what was done. */
function useChangeSub(item: S["ChangeItem"]): string {
  const { t, tn } = useWords();
  const estimate = useEstimate();
  return waitsForGo(item) ? (estimate(item.estimate_usd) ?? t("changes.sub.go_waiting", { when: dayAndTime(item.created_at) })) : subLine(item, t, tn);
}

/** One change as a line of the list (design 7.13): its state, its title, what was done in one line, its one primary and the
 * rest in the menu. Choosing it shows the whole change in the detail beside the list. */
function ChangeListRow(props: { item: S["ChangeItem"]; choice: ListChoice; reveal: number; onWant: (what: ChangeWant["what"]) => void; onOpenGuide?: (step: string) => void }) {
  const { t } = useWords();
  const { item, choice } = props;
  const ref = useRef<HTMLLIElement>(null);
  const { gated, cs, title, primary, menu, canSendBack } = useChangeActions(item, {
    onOpenGuide: props.onOpenGuide,
    startSendBack: () => props.onWant("sendback"),
    startChoosing: () => props.onWant("choose"),
  });
  const sub = useChangeSub(item);
  useEffect(() => {
    if (props.reveal) showRow(ref.current);
  }, [props.reveal]);
  useRowKeys(ref, {
    toggle: () => choice.enter(item.id),
    primary: primary?.run,
    send_back: canSendBack ? () => props.onWant("sendback") : undefined,
  });
  return (
    <li className="line" ref={ref} aria-labelledby={`t-${item.id}`} data-changeset={cs?.id} {...choice.rowProps(item.id)}>
      <div className="row">
        <span className={`kind ${PILL[item.state]}`}>
          {t(item.dismissed ? "changes.state.dismissed" : gated ? "changes.state.cost_go" : `changes.state.${item.state}`)}
        </span>
        <button type="button" className="expander text" aria-expanded={choice.chosen === item.id} onClick={() => choice.choose(item.id)}>
          <strong id={`t-${item.id}`}>{title}</strong>
          <span className="sub">{sub}</span>
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
      <OnTheRow item={item} />
    </li>
  );
}

/** What the list row keeps in view without the change being chosen: what is being learned from it, and the drafts and files
 * it made. */
function OnTheRow(props: { item: S["ChangeItem"] }) {
  const { item } = props;
  const cs = item.changeset;
  return (
    <>
      <div className="learned-inset">
        <LearnedLines changesets={[cs?.id, item.redoes]} />
      </div>
      {cs && (cs.made ?? []).length > 0 && <MadeLinks made={cs.made ?? []} />}
    </>
  );
}

/** One change in full: what the assistant did, nested, with the buttons for it. `open` shows it expanded from the start (the
 * Today inspector), `sendBack` starts with the note to send it back with, and `pane` is the detail beside the list, where the
 * title is the pane's own heading and `want` is what the list row asked to have opened. */
export function ChangeRow(props: { item: S["ChangeItem"]; reveal: number; onOpenGuide?: (step: string) => void; open?: boolean; sendBack?: boolean; pane?: boolean; want?: ChangeWant | null }) {
  const { t, tn } = useWords();
  const spentLine = useSpent();
  const { item } = props;
  const cs = item.changeset;
  // Every row that holds a question for the person starts open, whatever state its request is in, so none sits closed.
  const asks = !!cs?.ops.some((o) => o.ask?.status === "open");
  const gated = waitsForGo(item);
  const [open, setOpen] = useState(!!props.open || !!props.pane || !!props.sendBack || !!props.want || asks || item.state === "review" || (item.state === "needs_you" && !gated));
  const [sendingBack, setSendingBack] = useState(!!props.sendBack || props.want?.what === "sendback");
  const [choosing, setChoosing] = useState(props.want?.what === "choose");
  const ref = useRef<HTMLLIElement>(null);
  const { title, primary, menu, canSendBack } = useChangeActions(item, {
    onOpenGuide: props.onOpenGuide,
    startSendBack: () => {
      setOpen(true);
      setSendingBack(true);
    },
    startChoosing: () => {
      setOpen(true);
      setChoosing(true);
    },
  });
  const sub = useChangeSub(item);
  useEffect(() => {
    if (!props.reveal) return;
    setOpen(true);
    showRow(ref.current);
  }, [props.reveal]);
  // What the list row asked for (its menu's Send back, or Send to another account) opens here, in the detail.
  const wantedN = props.want?.n;
  useEffect(() => {
    if (!props.want) return;
    setOpen(true);
    if (props.want.what === "sendback") setSendingBack(true);
    else setChoosing(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedN]);

  useRowKeys(ref, {
    toggle: props.pane ? undefined : () => setOpen((v) => !v),
    primary: primary?.run,
    send_back: canSendBack ? () => {
      setOpen(true);
      setSendingBack(true);
    } : undefined,
  });

  const actions = (
    <div className="acts">
      {primary && (
        <button type="button" className="btn primary" onClick={primary.run}>
          {primary.label}
        </button>
      )}
      <RowMenu label={title} actions={menu} />
    </div>
  );
  const pill = (
    <span className={`kind ${PILL[item.state]}`}>
      {t(item.dismissed ? "changes.state.dismissed" : gated ? "changes.state.cost_go" : `changes.state.${item.state}`)}
    </span>
  );
  return (
    <li className={props.pane ? "line in-pane" : "line"} data-row tabIndex={-1} ref={ref} aria-labelledby={props.pane ? undefined : `t-${item.id}`} data-changeset={cs?.id}>
      {props.pane ? (
        <div className="detail-top">
          <div className="detail-state">
            {pill}
            <span className="sub">{sub}</span>
          </div>
          {actions}
        </div>
      ) : (
        <div className="row">
          {pill}
          <button type="button" className="expander text" aria-expanded={open} aria-controls={`b-${item.id}`} onClick={() => setOpen(!open)}>
            <strong id={`t-${item.id}`}>{title}</strong>
            <span className="sub">{sub}</span>
          </button>
          {actions}
        </div>
      )}
      {(cs?.second_opinion || item.follows_summary) && (
        <div className={props.pane ? "detail-notes" : "text row-notes"}>
          {cs?.second_opinion && <span className="sub second-opinion">{t(`changes.second.${cs.second_opinion}`)}</span>}
          {item.follows_summary && <span className="sub">{t("changes.follows", { summary: item.follows_summary })}</span>}
        </div>
      )}
      {!props.pane && <OnTheRow item={item} />}
      {open && (
        <div className="body" id={`b-${item.id}`}>
          {item.note && (
            <div className="your-note">
              <span className="what">{t("changes.your_note")}</span>
              <p>{item.note}</p>
            </div>
          )}
          {item.waiting && item.state !== "review" && <p className="hint">{item.waiting}</p>}
          {(item.state === "review" || item.state === "done") && spentLine(item.spent_usd, item.range_usd) && (
            <p className="hint">{spentLine(item.spent_usd, item.range_usd)}</p>
          )}
          {cs && cs.summary.trim() && (
            <div className="assistant-summary">
              <span className="what">{t("changes.summary_label")}</span>
              <p>{cs.summary}</p>
            </div>
          )}
          {cs && <Because cs={cs} />}
          {cs && cs.ops.length === 0 && !cs.summary.trim() && <p className="hint">{t("changes.nothing_done")}</p>}
          {cs && cs.ops.length > 0 && (
            <ul className="children" aria-label={tn("changes.did", cs.ops.length)}>
              {cs.ops.map((op) =>
                op.op === "project.add" && op.status === "held" ? (
                  <ProjectProposalRow key={op.index} op={op} changeset={cs.id} />
                ) : (
                  <OpRow key={op.index} op={op} cs={cs} source={item.source} />
                ),
              )}
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

/** The drafts and files a change made, one link each, shown without opening the change's details. A draft opens on the
 * record it is for, where it waits for review; a file opens in the files list. */
function MadeLinks(props: { made: S["MadeView"][] }) {
  const { t } = useWords();
  return (
    <ul className="made plain-list" aria-label={t("changes.made")}>
      {props.made.map((m) => (
        <li key={`${m.kind}-${m.id}`}>
          <span className="what">{t("changes.made")}</span>{" "}
          <a href={viewHref(m.kind === "file" ? "records/files" : recordView(m.record.kind, m.record.id))}>
            {t(`changes.made.${m.kind}`, { label: m.label })}
          </a>
        </li>
      ))}
    </ul>
  );
}

type T = (key: string, vars?: Record<string, string | number>) => string;
type TN = (key: string, n: number, vars?: Record<string, string | number>) => string;

// What each kind of op did, in the words the screens use for it (the same grouping Today's review lines use).
const DID: Record<string, string> = {
  "action.add": "actions_added",
  "action.close": "actions_closed",
  "question.add": "questions",
  note: "notes",
  fact: "recorded",
  "event.add": "recorded",
  "event.set": "recorded",
  "series.add": "recorded",
  "series.link": "recorded",
  "agenda.add": "recorded",
  "record.set": "recorded",
  "record.log": "recorded",
  "person.add": "people",
  "project.add": "projects",
  "text.draft": "drafts",
  "report.draft": "drafts",
  "text.propose": "drafts",
};
const DID_ORDER = ["actions_added", "actions_closed", "questions", "notes", "recorded", "people", "projects", "drafts"];

/** What the changes did, said as what they were: "Added 3 to-dos, Filed 1 note". Ops of a kind with no words here are
 * counted as "did N things", so nothing is left out. */
function didText(ops: S["OpView"][], t: T, tn: TN): string {
  const counts = new Map<string, number>();
  let other = 0;
  for (const op of ops) {
    const group = DID[op.op];
    if (group) counts.set(group, (counts.get(group) ?? 0) + 1);
    else other += 1;
  }
  const said = DID_ORDER.filter((g) => counts.has(g)).map((g) => tn(`changes.did_what.${g}`, counts.get(g)!));
  if (other) said.push(tn("changes.did", other));
  return said.join(t("changes.did_what.join"));
}

function subLine(item: S["ChangeItem"], t: T, tn: TN): string {
  const when = dayAndTime(item.created_at);
  if (item.state === "queued" || item.state === "running") return t("changes.sub.waiting", { when });
  if (item.dismissed) return t("changes.sub.dismissed", { when });
  if (item.state === "needs_you" || item.state === "failed") return t("changes.sub.stopped", { when });
  const ops = item.changeset?.ops ?? [];
  const held = ops.filter((o) => o.status === "held" || o.ask?.status === "open").length;
  const did = ops.length ? didText(ops, t, tn) : t("changes.did_nothing");
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

/** The kinds of item a review card's row can be changed as (the kinds the change route takes). */
const CHANGEABLE: ChangeKind[] = ["action", "question", "decision", "event", "fact"];

/** The ops about a promise: the row shows why it exists and how it ended, beside the words the op rests on. */
const PROMISE_OPS = new Set(["action.add", "action.close", "action.drop", "action.move", "action.part", "action.news"]);

export function OpRow(props: { op: S["OpView"]; cs: S["ChangesetView"]; source: string | null }) {
  const { t, tn, has } = useWords();
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
  // A held change the line on Today asks as a question has the same two answers here, in the same words.
  const heldWords = useHeldAnswers(cs.id, op.index, op.status === "held" && !ask ? op.held : null);
  const told = op.held ? heldTold(op.held, t) : "";

  // Each item the assistant made can be changed on its own, without sending the others back.
  const changeKind = op.record && CHANGEABLE.includes(op.record.kind as ChangeKind) ? (op.record.kind as ChangeKind) : null;
  const change = useChangeThis({ kind: changeKind ?? "action", id: op.record?.id ?? "" }, () => ref.current?.focus());
  const menu: MenuAction[] = [];
  if (op.status === "applied") menu.push({ id: "undo", label: t("op.undo_this"), run: () => void undoThis() });
  if (changeKind && op.status === "applied") menu.push(change.entry);
  if (op.evidence && props.source)
    menu.push({ id: "source", label: t(showSource ? "op.hide_source" : "op.show_source"), run: () => setShowSource((v) => !v) });

  if (heldWords) for (const extra of heldWords.menu) menu.push(extra);
  useRowKeys(ref, { primary: op.status === "held" && !ask ? (heldWords ? heldWords.primary.run : () => void release()) : undefined });

  const labelOf = useFieldLabel();
  const meta = metaLine(op, t, labelOf);
  return (
    <li className="child" data-row tabIndex={-1} ref={ref}>
      <div>
        {heldWords && told && (
          <div className="reason">
            <strong>{told}</strong>
          </div>
        )}
        <div className="what">
          {opLabel(op, t, has)}
          {pill && <span className={`pill ${pill}`}>{t(`op.status.${pillKey}`)}</span>}
        </div>
        <div className="title">{op.title}</div>
        {meta && <div className="meta">{meta}</div>}
        {op.reason && op.status !== "applied" && <div className="reason">{op.reason}</div>}
      </div>
      <div className="acts">
        {heldWords ? (
          <>
            {heldWords.other && (
              <button type="button" className="btn" onClick={heldWords.other.run}>
                {heldWords.other.label}
              </button>
            )}
            <button type="button" className="btn primary" onClick={heldWords.primary.run}>
              {heldWords.primary.label}
            </button>
          </>
        ) : (
          op.status === "held" &&
          !ask && (
            <button type="button" className="btn primary" onClick={() => void release()}>
              {t("op.do_anyway")}
            </button>
          )
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
      {op.record?.kind === "action" && PROMISE_OPS.has(op.op) && op.status !== "undone" && (
        <div className="full">
          <PromiseWhy action={op.record.id} quiet omitQuote line />
        </div>
      )}
      {changeKind && change.form}
      {ask && (
        <div className="full">
          <AskChooser ask={ask} fold={{ changeset: cs.id, index: op.index }} />
        </div>
      )}
    </li>
  );
}

/** What the assistant did, in words; a filed note also says where it went. */
function opLabel(op: S["OpView"], t: T, has: (key: string) => boolean): string {
  // Before it is decided an op is only what would happen ("Would close a to-do"); done is said once it is.
  const word = op.status === "held" && has(`op.would.${op.op}`) ? "op.would" : "op";
  if (op.op === "note") return op.meta.project ? t(`${word}.note.under`, { project: op.meta.project }) : t(`${word}.note.none`);
  return t(`${word}.${op.op}`);
}

/** A value an op sets, as words: a date as elsewhere in the app, never as it is stored. */
function setValue(value: unknown): string {
  const text = String(value ?? "");
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? day(text) : text;
}

function metaLine(op: S["OpView"], t: T, labelOf: (name: string) => string): string {
  const bits: string[] = [];
  const m = op.meta;
  if (m.owners?.length) bits.push(m.owners.join(", "));
  if (m.to_send) bits.push(t("action.to_send"));
  if (m.to) bits.push(t("op.meta.to", { name: m.to }));
  if (m.due) bits.push(t("op.meta.due", { date: day(m.due) }));
  if (m.project && op.op !== "note") bits.push(m.project);
  if (m.field) bits.push(t("op.meta.set", { field: labelOf(m.field), value: setValue(m.value) }));
  if (m.role) bits.push(t("op.meta.role", { role: t(`role.${m.role}`) }));
  if (m.stance) bits.push(t("op.meta.stance", { stance: t(`stance.${m.stance}`) }));
  return bits.join(" · ");
}

export function SourcePanel(props: { id: string; quote: string }) {
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
  // Starting again from nothing is the usual choice; keeping what it did and changing it from there is the other.
  const [undoFirst, setUndoFirst] = useState(true);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => area.current?.focus(), []);
  return (
    <form
      className="sendback"
      onSubmit={(e) => {
        e.preventDefault();
        void act(
          () => api.sendBack(props.cs, note, undoFirst),
          () => ({ message: t("toast.sent_back") }),
        ).then(props.onDone);
      }}
    >
      <label className="hint" htmlFor={`sb-${props.cs}`}>
        {t("changes.send_back_label")}
      </label>
      <textarea id={`sb-${props.cs}`} ref={area} value={note} onChange={(e) => setNote(e.target.value)} required />
      <label className="check-line">
        <input type="checkbox" checked={undoFirst} onChange={(e) => setUndoFirst(e.target.checked)} />
        {t("changes.send_back_undo")}
      </label>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onDone}>
          {t("action.cancel")}
        </button>
        <Button variant="primary" type="submit" disabled={!note.trim()} reason={t("changes.send_back_needs_note")}>
          {t("changes.send_back_go")}
        </Button>
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
