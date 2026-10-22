// The brief (design 6.32): a card at the top of Today with the morning brief, the evening wrap-up or the Monday briefing,
// whichever is due. Built by rules on the server, so every line here is a kind and its values worded from the sheet. A
// line that waits for the person's yes opens Today's own line; the rest open their record. The card closes for the day,
// which is remembered in this browser only and is no signal of anything. The Monday form also holds the week's goals
// (kept as confirmed) and the message to whoever the person reports to.
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { copyMessage } from "../lib/copy";
import { day, wallTime } from "../lib/dates";
import { durationWords } from "../lib/duration";
import { chooseFilters } from "../lib/open-items";
import type { View } from "../lib/views";
import { useMoney } from "../lib/money";
import { reveal } from "../lib/reveal";
import { useToasts } from "../lib/toasts";
import { useQueue, type QueueLine } from "../lib/today";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { useLineTitle } from "./TodayQueue";
import styles from "./BriefCard.module.css";

type Brief = S["BriefView"];
type Line = S["BriefLineView"];
type Form = NonNullable<Brief["form"]>;
type T = ReturnType<typeof useWords>["t"];
type Tn = ReturnType<typeof useWords>["tn"];

const KEY = "brief-closed";

/** Whether the card for a form was closed for this day in this browser. A browser that blocks storage shows it every time. */
function closedFor(workspace: string, form: string, on: string): boolean {
  try {
    return window.localStorage.getItem(`${KEY}:${workspace}:${form}:${on}`) === "1";
  } catch {
    return false;
  }
}

function closeFor(workspace: string, form: string, on: string) {
  try {
    window.localStorage.setItem(`${KEY}:${workspace}:${form}:${on}`, "1");
  } catch {
    // Storage can be blocked; the card then comes back, which is harmless.
  }
}

export function useBrief(form: Form | null) {
  return useQuery({ queryKey: ["brief", form], queryFn: () => api.brief(form ?? undefined) });
}

const clock = (at: string | null | undefined) => (at ? wallTime(`T${at}`) : "");

function heading(key: string, t: T): string {
  switch (key) {
    case "changed":
      return t("brief.section.changed");
    case "risk":
      return t("brief.section.risk");
    case "yes":
      return t("brief.section.yes");
    case "done":
      return t("brief.section.done");
    case "moved":
      return t("brief.section.moved");
    case "waiting":
      return t("brief.section.waiting");
    case "yours":
      return t("brief.section.yours");
    case "owed":
      return t("brief.section.owed");
    case "send":
      return t("brief.section.send");
    case "chase":
      return t("brief.section.chase");
    default:
      return t("brief.section.decide");
  }
}

function invitation(line: Line, t: T): string {
  const vars = { name: line.person_name ?? "", text: line.text ?? "", date: day(line.day), time: clock(line.at), from: [day(line.from_day), clock(line.from_at)].filter(Boolean).join(" "), place: line.detail ?? "" };
  switch (line.change) {
    case "new":
      return line.person_name ? t(line.at ? "brief.line.invitation.new_at" : "brief.line.invitation.new", vars) : t(line.at ? "brief.line.invitation.new_unnamed_at" : "brief.line.invitation.new_unnamed", vars);
    case "cancelled":
      return t("brief.line.invitation.cancelled", vars);
    case "restored":
      return t("brief.line.invitation.restored", vars);
    case "moved":
      return t(line.at ? "brief.line.invitation.moved_at" : "brief.line.invitation.moved", vars);
    case "now_timed":
      return t("brief.line.invitation.now_timed", vars);
    case "now_all_day":
      return t("brief.line.invitation.now_all_day", vars);
    case "end_changed":
      return t("brief.line.invitation.end_changed", vars);
    case "location_changed":
      return t("brief.line.invitation.location_changed", vars);
    case "location_removed":
      return t("brief.line.invitation.location_removed", vars);
    case "title_changed":
      return t("brief.line.invitation.title_changed", vars);
    default:
      return t("brief.line.invitation.organizer_changed", { ...vars, name: line.detail ?? line.person_name ?? "" });
  }
}

/** What a line says. A line that waits for the person's yes is titled as Today's own line is, so the two never disagree. */
function useLineWords(): (line: Line, queue: QueueLine | undefined) => string {
  const { t, tn } = useWords();
  const title = useLineTitle();
  return (line, queue) => lineWords(line, queue, t, tn, title);
}

function lineWords(line: Line, queue: QueueLine | undefined, t: T, tn: Tn, title: (q: QueueLine) => string): string {
  const name = line.person_name ?? "";
  const text = line.text ?? "";
  const date = day(line.day);
  switch (line.kind) {
    case "closed":
      return name ? t("brief.line.closed", { name, text }) : t("brief.line.closed_rule", { text });
    case "moved":
      if (line.change === "meeting") return t("brief.line.moved_meeting", { text, date });
      return name ? t("brief.line.moved", { name, text, date }) : t("brief.line.moved_unnamed", { text, date });
    case "moved_ahead":
      return t("brief.line.moved_ahead", { text, date });
    case "news":
      if (line.detail) return name ? t("brief.line.news", { name, text, detail: line.detail }) : t("brief.line.news_unnamed", { text, detail: line.detail });
      return name ? t("brief.line.news_bare", { name, text }) : t("brief.line.news_bare_unnamed", { text });
    case "invitation":
      return invitation(line, t);
    case "own_due":
      if (line.state === "today") return t(line.at ? "brief.line.own_due.today_at" : "brief.line.own_due.today", { text, time: clock(line.at) });
      return tn("brief.line.own_due.overdue", line.days ?? 0, { text });
    case "owed_late":
      return tn("brief.line.owed_late", line.days ?? 0, { name, text });
    case "clash":     {
      const vars = { text, other: line.other ?? "", date, time: clock(line.at) };
      return line.state === "travel" ? tn("brief.line.clash.travel", line.minutes ?? 0, vars) : tn("brief.line.clash", line.minutes ?? 0, vars);
    }
    case "capacity":
      return t("brief.line.capacity", { needed: durationWords(line.needed_minutes ?? 0, tn), free: durationWords(line.minutes ?? 0, tn) });
    case "digest":
      return line.change === "escalate" ? t("brief.line.digest.escalate", { name, text }) : tn(`brief.line.digest.${line.change}`, line.count ?? 1);
    case "yes":
      if (line.change === "reminder_offer") return t("brief.line.reminder_offer", { text, date, time: clock(line.at) });
      return queue ? title(queue) : text || t("brief.line.yes");
    case "done":
      return line.you ? t("brief.line.done_you", { text }) : name ? t("brief.line.done_them", { name, text }) : t("brief.line.done_anyone", { text });
    case "carried":
      return t("brief.line.carried", { text });
    case "waiting":
      return line.day ? t("brief.line.waiting_due", { name, text, date }) : t("brief.line.waiting", { name, text });
    case "waiting_answer":
      return t("brief.line.waiting_answer", { name, text });
    case "week_promise": {
      const late = line.state === "overdue";
      if (line.you) return t(late ? "brief.line.week.overdue" : "brief.line.week.due", { text, date });
      return t(late ? "brief.line.week.owed_overdue" : "brief.line.week.owed", { name, text, date });
    }
    case "send_question":
      return t("brief.line.send_question", { name, text });
    case "chase_answer":
      return t("brief.line.chase_answer", { name, text });
    case "decision":
      return t("brief.line.decision", { text });
    default:
      return text;
  }
}

/** Where a suggestion that waited for the brief is dealt with, since its line isn't on Today. */
const DIGEST_VIEW: Record<string, View> = { stale: "work/open", unfiled: "records/projects", escalate: "work/followups", learned: "records/knowledge", catch_up: "records/knowledge" };

function LineRow(props: { line: Line; queue: QueueLine | undefined; onOpenRecord: (kind: string, id: string) => void; onOpenView?: (view: View) => void }) {
  const { t } = useWords();
  const act = useAct();
  const words = useLineWords();
  const { line } = props;
  const offer = line.kind === "yes" && line.change === "reminder_offer" && line.link && line.when ? { action: line.link.id, at: line.when } : null;
  const remind = () => {
    if (!offer) return;
    void act(
      () => api.remind(offer.action, { at: offer.at }),
      (result) => ({ message: t("brief.remind.saved", { text: line.text ?? "" }), undo: () => api.undo(result.changeset) }),
    );
  };
  const view = line.kind === "digest" && line.change ? DIGEST_VIEW[line.change] : undefined;
  const open = () => {
    if (view && props.onOpenView) {
      if (line.change === "stale") chooseFilters({ state: "stale" });
      props.onOpenView(view);
      return;
    }
    if (line.queue && reveal("line", line.queue)) return;
    if (line.link) props.onOpenRecord(line.link.kind, line.link.id);
  };
  const opens = !offer && (Boolean(line.queue) || Boolean(line.link) || Boolean(view && props.onOpenView));
  const meta = [line.kind === "own_due" && line.person_name ? t("brief.line.own_due.for", { name: line.person_name }) : "", line.kind === "week_promise" && line.you && line.person_name ? t("brief.line.week.to", { name: line.person_name }) : "", line.ready ? t("brief.ready") : ""].filter(Boolean);
  return (
    <li className={styles.line} data-kind={line.kind}>
      <span className={styles.what}>{words(line, props.queue)}</span>
      {meta.length > 0 && <span className={styles.meta}>{meta.join(" · ")}</span>}
      {offer && (
        <Button size="sm" className={styles.open} onClick={remind}>
          {t("brief.remind")}
        </Button>
      )}
      {opens && (
        <Button size="sm" className={styles.open} onClick={open}>
          {t("brief.open")}
        </Button>
      )}
    </li>
  );
}

/** The goals for the week: the proposed or confirmed ones, and a small form to set them (the cursor in the first field). */
function Goals(props: { goals: NonNullable<Brief["goals"]> }) {
  const { t } = useWords();
  const act = useAct();
  const { goals } = props;
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<string[]>([]);
  const [problem, setProblem] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  const shown = goals.confirmed ? goals.goals : goals.proposed;
  const id = useId();
  const keep = async (list: string[]) => {
    const kept = await act(
      () => api.putGoals({ goals: list }),
      (result) => ({ message: t("brief.goals.saved"), undo: () => api.putGoals({ goals: result.previous }) }),
    );
    if (kept) setEditing(false);
  };
  const edit = () => {
    const start = shown.length > 0 ? shown : [""];
    setRows(start);
    setProblem(false);
    setEditing(true);
    window.setTimeout(() => first.current?.focus(), 0);
  };
  const save = () => {
    const list = rows.map((r) => r.trim()).filter(Boolean);
    if (list.length < goals.fewest) {
      setProblem(true);
      return;
    }
    void keep(list);
  };
  return (
    <div className={styles.block} data-block="goals">
      <h3 className={styles.sub}>{t("brief.goals.title")}</h3>
      {editing ? (
        <form
          className={styles.form}
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <p className="hint">{t("brief.goals.count", { fewest: goals.fewest, most: goals.most })}</p>
          <ul className={styles.rows}>
            {rows.map((row, n) => (
              <li key={n} className={styles.goalRow}>
                <label htmlFor={`${id}-${n}`} className="sr">
                  {t("brief.goals.field", { n: n + 1 })}
                </label>
                <input
                  id={`${id}-${n}`}
                  ref={n === 0 ? first : undefined}
                  type="text"
                  value={row}
                  maxLength={200}
                  placeholder={t("brief.goals.field", { n: n + 1 })}
                  onChange={(e) => setRows(rows.map((r, i) => (i === n ? e.target.value : r)))}
                />
                <Button type="button" onClick={() => setRows(rows.filter((_, i) => i !== n))}>
                  {t("brief.goals.drop", { n: n + 1 })}
                </Button>
              </li>
            ))}
          </ul>
          {problem && (
            <p className="hint" role="alert">
              {t("brief.goals.too_few", { fewest: goals.fewest })}
            </p>
          )}
          <div className={styles.actions}>
            {rows.length < goals.most && (
              <Button type="button" onClick={() => setRows([...rows, ""])}>
                {t("brief.goals.add")}
              </Button>
            )}
            <Button type="submit" variant="primary">
              {t("brief.goals.save")}
            </Button>
            <Button type="button" onClick={() => setEditing(false)}>
              {t("brief.goals.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <>
          {shown.length > 0 ? (
            <>
              <p className="hint">{goals.confirmed ? t("brief.goals.confirmed") : t("brief.goals.proposed")}</p>
              <ol className={styles.goalList}>
                {shown.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ol>
            </>
          ) : (
            <p className="hint">{t("brief.goals.none")}</p>
          )}
          <div className={styles.actions}>
            {!goals.confirmed && shown.length >= goals.fewest && (
              <Button variant="primary" onClick={() => void keep(shown)}>
                {t("brief.goals.use")}
              </Button>
            )}
            <Button onClick={edit}>{shown.length > 0 ? t("brief.goals.change") : t("brief.goals.set")}</Button>
          </div>
        </>
      )}
    </div>
  );
}

/** The message to whoever the person reports to: ask for it, see where it stands, read the draft, copy it. */
function Message(props: { message: NonNullable<Brief["message"]> }) {
  const { t } = useWords();
  const act = useAct();
  const money = useMoney();
  const { push } = useToasts();
  const { message } = props;
  const names = message.to.map((p) => p.name).join(", ");
  const copy = async (text: string, accept: boolean) => {
    if ((await copyMessage(text)) === "blocked") {
      push({ message: t("brief.message.copy_blocked") });
      return;
    }
    if (accept) await act(() => api.briefMessageCopied(), () => ({ message: t("brief.message.copied") }));
    else push({ message: t("brief.message.copied") });
  };
  let body: ReactNode;
  switch (message.state) {
    case "none":
      body = (
        <Button onClick={() => void act(() => api.askBriefMessage({}), () => ({ message: t("brief.message.asked") }))}>{t("brief.message.ask")}</Button>
      );
      break;
    case "working":
      body = <p className="hint">{t("brief.message.working")}</p>;
      break;
    case "needs_go":
      body = <p className="hint">{message.estimate_usd != null ? t("brief.message.needs_go_cost", { cost: money(message.estimate_usd) }) : t("brief.message.needs_go")}</p>;
      break;
    default:
      body = (
        <>
          <p className="hint">{message.state === "draft" ? t("brief.message.draft") : t("brief.message.kept")}</p>
          <p className={styles.message} data-message={message.state}>
            {message.text}
          </p>
          <div className={styles.actions}>
            <Button variant="primary" onClick={() => void copy(message.text ?? "", message.state === "draft")}>
              {t("brief.message.copy")}
            </Button>
          </div>
        </>
      );
  }
  return (
    <div className={styles.block} data-block="message">
      <h3 className={styles.sub}>{t("brief.message.title", { names })}</h3>
      <p className="hint">{t("brief.message.hint")}</p>
      {body}
    </div>
  );
}

export function BriefCard(props: { workspace: string; onOpenRecord: (kind: string, id: string) => void; onOpenView?: (view: View) => void }) {
  const { t, tn } = useWords();
  const [asked, setAsked] = useState<Form | null>(null);
  const [, shut] = useState(0);
  const found = useBrief(asked);
  const queue = useQueue();
  const id = useId();
  const data = found.data;
  if (!data || data.form === null) return null;
  const form = data.form;
  if (closedFor(props.workspace, form, data.day)) return null;
  const byKey = new Map((queue.data ?? []).map((line) => [line.key, line]));
  const others = data.forms.filter((f) => f !== form);
  const title = form === "morning" ? t("brief.title.morning") : form === "evening" ? t("brief.title.evening") : t("brief.title.monday");
  const showWords = (f: Form) => (f === "morning" ? t("brief.show.morning") : f === "evening" ? t("brief.show.evening") : t("brief.show.monday"));
  const quiet = form === "morning" ? t("brief.quiet.morning") : form === "evening" ? t("brief.quiet.evening") : t("brief.quiet.monday");
  return (
    <section className={styles.card} aria-labelledby={`${id}-head`} data-brief={form}>
      <div className={styles.head}>
        <h2 id={`${id}-head`} className={styles.title}>
          {title}
        </h2>
        <div className={styles.headActions}>
          {others.map((f) => (
            <Button key={f} onClick={() => setAsked(f)}>
              {showWords(f)}
            </Button>
          ))}
          <Button
            onClick={() => {
              closeFor(props.workspace, form, data.day);
              shut((n) => n + 1);
            }}
          >
            {t("brief.close")}
          </Button>
        </div>
      </div>
      {data.message && <Message message={data.message} />}
      {data.sections.map((section) => (
        <div key={section.key} className={styles.section} data-section={section.key}>
          <h3 className={styles.sub}>{heading(section.key, t)}</h3>
          <ul className={styles.lines}>
            {section.lines.map((line) => (
              <LineRow key={line.key} line={line} queue={line.queue ? byKey.get(line.queue) : undefined} onOpenRecord={props.onOpenRecord} onOpenView={props.onOpenView} />
            ))}
          </ul>
          {section.more > 0 && <p className="hint">{tn("brief.more", section.more)}</p>}
        </div>
      ))}
      {data.quiet && <p className={styles.quiet}>{quiet}</p>}
      {data.on_today > 0 && <p className="hint">{tn("brief.on_today", data.on_today)}</p>}
      {data.goals && <Goals goals={data.goals} />}
    </section>
  );
}
