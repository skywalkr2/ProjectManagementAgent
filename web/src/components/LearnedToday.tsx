// Today's lines for what the assistant learned (design 7.7, 7.18): one Review line for what it learned from inputs and
// from corrections the person has already left, and one for the catch-up list. Each opens its list: a row per thing,
// tagged by where it came from, with Keep as its one primary action and Just this time, Edit and Discard in its menu.
// Keep all is offered only for glossary terms that carry the words they came from.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { ProposalEvidence, ProposalForms, ReachPicker, useProposal, type Proposal } from "./Learned";
import { RowMenu, type MenuAction } from "./RowMenu";
import styles from "./Learned.module.css";

type List = "daily" | "catch_up";

/** The kinds of queue line this draws: what was learned, and the catch-up list. */
export function isLearned(line: S["QueueLineView"]): boolean {
  return line.kind === "learned" || line.kind === "catch_up";
}

/** One learned line of the Today queue. The counts come from the queue; the list loads when it is opened. */
export function LearnedLine(props: { line: S["QueueLineView"] }) {
  const { t, tn } = useWords();
  const { line } = props;
  const [open, setOpen] = useState(false);
  const list: List = line.kind === "learned" ? "daily" : "catch_up";
  const origins = line.origins ?? {};
  const sub = [
    line.kind === "learned" && origins.input ? tn("learned.today.from_inputs", origins.input) : "",
    line.kind === "learned" && origins.correction ? tn("learned.today.from_corrections", origins.correction) : "",
    line.kind === "learned" && line.expired ? tn("learned.today.expired", line.expired) : "",
    line.kind === "catch_up" && line.left_out ? tn("learned.today.left_out", line.left_out) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <section className={styles.todayLine} aria-label={t("learned.today.label")} data-queue-line={line.kind} data-row="" tabIndex={-1}>
      <Pill tone="need">{t("learned.today.label")}</Pill>
      <div className={styles.todayBody}>
        <p className={styles.todayText}>{line.kind === "learned" ? tn("learned.today.review", line.count) : tn("learned.today.catch_up", line.count)}</p>
        {sub && <p className={styles.todaySub}>{sub}</p>}
      </div>
      <div className={styles.todayActs}>
        <Button size="sm" variant="primary" data-key="primary" onClick={() => setOpen(true)}>
          {t("learned.today.open")}
        </Button>
      </div>
      {open && <ReviewDrawer list={list} onClose={() => setOpen(false)} />}
    </section>
  );
}

/** The glossary terms a list holds that carry the words they came from: the only ones kept together. */
export function keptTogether(rows: Proposal[]): Proposal[] {
  return rows.filter((p) => p.kind === "glossary_entry" && !!p.evidence?.quote);
}

function ReviewDrawer(props: { list: List; onClose: () => void }) {
  const { t, tn } = useWords();
  const daily = props.list === "daily";
  const proposals = useQuery({ queryKey: ["proposals"], queryFn: api.proposals, enabled: daily });
  const catchUp = useQuery({ queryKey: ["catch-up"], queryFn: api.catchUp, enabled: !daily });
  const found = daily ? proposals : catchUp;
  const rows = (daily ? proposals.data?.proposals : catchUp.data?.proposals) ?? [];
  const terms = keptTogether(rows);
  const summary = daily
    ? [
        proposals.data?.origins.input ? tn("learned.today.from_inputs", proposals.data.origins.input) : "",
        proposals.data?.origins.correction ? tn("learned.today.from_corrections", proposals.data.origins.correction) : "",
        proposals.data?.expired ? tn("learned.today.expired", proposals.data.expired) : "",
      ]
    : [
        catchUp.data?.waiting ? tn("learned.catch_up.waiting", catchUp.data.waiting) : "",
        catchUp.data?.left_out ? tn("learned.catch_up.left_out", catchUp.data.left_out, { most: catchUp.data.most }) : "",
      ];
  return (
    <Drawer open title={daily ? t("learned.review.title") : t("learned.catch_up.title")} onClose={props.onClose} wide>
      <div className={styles.review}>
        {summary.some(Boolean) && <p className={styles.summary}>{summary.filter(Boolean).join(" · ")}</p>}
        {terms.length > 0 && <KeepAll terms={terms} />}
        {found.isPending ? (
          <Skeleton />
        ) : found.isError ? (
          <p className={styles.empty}>
            {t("learned.load_failed")}{" "}
            <Button size="sm" onClick={() => void found.refetch()}>
              {t("action.try_again")}
            </Button>
          </p>
        ) : rows.length === 0 ? (
          <p className={styles.empty}>{t("learned.review.empty")}</p>
        ) : (
          <>
            <ul className={styles.list} aria-label={daily ? t("learned.review.title") : t("learned.catch_up.title")}>
              {rows.map((p) => (
                <ProposalRow key={p.id} p={p} />
              ))}
            </ul>
            <p className={styles.summary}>{t("learned.review.one_at_a_time")}</p>
          </>
        )}
      </div>
    </Drawer>
  );
}

/** Keeps every glossary term shown with the words it came from, each with its own Undo behind one toast. */
function KeepAll(props: { terms: Proposal[] }) {
  const { t, tn } = useWords();
  const act = useAct();
  const client = useQueryClient();
  const count = props.terms.length;
  const run = () =>
    void act(
      async () => {
        const done: string[] = [];
        try {
          for (const p of props.terms) done.push((await api.keepKnowledge(p.id, { read_version: p.version })).changeset);
        } finally {
          if (done.length) await client.invalidateQueries();
        }
        return done;
      },
      (done) => ({
        message: tn("toast.learned_kept_all", done.length),
        undo: async () => {
          for (const cs of done) await api.undo(cs);
        },
      }),
    );
  return (
    <div>
      <Button variant="primary" onClick={run}>
        {tn("learned.keep_all", count)}
      </Button>
      <p className={styles.summary}>{t("learned.keep_all_hint")}</p>
    </div>
  );
}

function ProposalRow(props: { p: Proposal }) {
  const { t, tn } = useWords();
  const { p } = props;
  const state = useProposal(p);
  const menu: MenuAction[] = [
    { id: "just-this-time", label: t("learned.just_this_time"), run: () => void state.justThisTime() },
    { id: "edit", label: t("learned.edit"), run: () => state.setEditing(true) },
    { id: "discard", label: t("learned.discard"), run: () => state.setDiscarding(true) },
  ];
  const meta = [state.reachNow, p.expires_at ? t("learned.expires", { date: day(p.expires_at) }) : ""].filter(Boolean).join(" · ");
  return (
    <Row
      data-learned={p.id}
      pill={<Pill>{t(`learned.from.${p.came_from}`)}</Pill>}
      title={p.text}
      meta={meta}
      oneLine
      primary={
        <Button size="sm" variant="primary" onClick={() => void state.keep()}>
          {t("learned.keep")}
        </Button>
      }
      menu={<RowMenu label={p.text} actions={menu} />}
    >
      <div className={styles.detail}>
        {!state.editing && <ReachPicker choices={state.choices} value={state.chosen} onChange={state.setChosen} words={state.words} said={state.reachSaid} />}
        {!state.editing && <ProposalEvidence p={p} />}
        {p.just_this_time_before > 0 && <p className={styles.summary}>{tn("learned.said_just_this_time", p.just_this_time_before)}</p>}
        <ProposalForms p={p} state={state} />
      </div>
    </Row>
  );
}
