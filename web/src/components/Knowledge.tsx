// Knowledge (design 7.18): everything the assistant has learned and the standing rules it follows, by kind, with where each
// piece came from, what it reaches and how much it was used. One primary action per row (Keep a proposal, Narrow an
// active entry); the rest is in the row's menu. Every act is at once, with an undo toast.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useKnowledgeActs } from "../lib/knowledge-acts";
import {
  FILTERS,
  KINDS,
  counts,
  inFilter,
  itemsOf,
  reachWords,
  usedWords,
  type Filter,
  type Item,
  type Kind,
} from "../lib/knowledge";
import { useReachNames } from "../lib/reach";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { LoadFailed } from "../ui/LoadFailed";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { SegmentedControl } from "../ui/SegmentedControl";
import { Skeleton } from "../ui/Skeleton";
import { NarrowForm } from "./NarrowForm";
import { OriginLink } from "./Origin";
import { RowMenu, type MenuAction } from "./RowMenu";
import styles from "./Knowledge.module.css";

export function Knowledge(props: { onOpenReview: () => void }) {
  const words = useWords();
  const { t, tn } = words;
  const entries = useQuery({ queryKey: ["knowledge"], queryFn: api.knowledge });
  const rules = useQuery({ queryKey: ["knowledge", "rules"], queryFn: api.knowledgeRules });
  const review = useQuery({ queryKey: ["knowledge", "rules", "review"], queryFn: api.ruleReview });
  const reach = useReachNames();
  const [chosen, setChosen] = useState<Filter | null>(null);
  const [kind, setKind] = useState<Kind | "all">("all");
  const kindId = useId();
  const list = useRef<HTMLUListElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [acted, setActed] = useState(0);
  // After an act the row it was on usually leaves the list; keyboard focus moves to what is now first.
  useEffect(() => {
    if (acted === 0) return;
    (list.current?.querySelector<HTMLElement>("[data-row]") ?? heading.current)?.focus();
  }, [acted]);

  const all = useMemo(() => (entries.data && rules.data ? itemsOf(entries.data, rules.data) : []), [entries.data, rules.data]);
  const ofKind = all.filter((i) => kind === "all" || i.kind === kind);
  const number = counts(ofKind);
  // Open on what waits for the person; with nothing waiting, on what is active.
  const filter: Filter = chosen ?? (number.proposed > 0 ? "proposed" : "active");
  const shown = ofKind.filter((i) => inFilter(i, filter));
  const now = new Date();
  const flagged = review.data ? review.data.flagged.length : 0;
  const moved = review.data?.moved ?? 0;
  const failed = entries.isError || rules.isError;

  return (
    <section className="panel-section" aria-labelledby="knowledge-title">
      <div className="heading">
        <h1 id="knowledge-title" ref={heading} tabIndex={-1}>
          {t("knowledge.title")}
        </h1>
      </div>
      <p className={styles.intro}>{t("knowledge.intro")}</p>
      {(flagged > 0 || moved > 0) && (
        <div className={styles.review}>
          <p>{flagged > 0 ? tn("knowledge.review", flagged) : t("knowledge.review.moved")}</p>
          <Button size="sm" onClick={props.onOpenReview}>
            {t("knowledge.review.open")}
          </Button>
        </div>
      )}
      <div className={styles.controls}>
        <SegmentedControl
          label={t("knowledge.filter.label")}
          value={filter}
          onChange={setChosen}
          options={FILTERS.map((f) => ({
            value: f,
            // A filter with nothing under it is only its name: no "(0)".
            label: number[f] > 0 ? t("knowledge.filter.count", { label: t(`knowledge.filter.${f}`), n: number[f] }) : t(`knowledge.filter.${f}`),
          }))}
        />
        <div className={styles.kind}>
          <label htmlFor={kindId}>{t("knowledge.kind.label")}</label>
          <select id={kindId} value={kind} onChange={(e) => setKind(e.target.value as Kind | "all")}>
            <option value="all">{t("knowledge.kind.all")}</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`knowledge.kinds.${k}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
      {failed ? (
        <LoadFailed
          message={t("knowledge.load_failed")}
          onRetry={() => {
            void entries.refetch();
            void rules.refetch();
          }}
        />
      ) : entries.isPending || rules.isPending ? (
        <Skeleton />
      ) : shown.length === 0 ? (
        <p className="empty">{t(`knowledge.empty.${filter}`)}</p>
      ) : (
        <ul ref={list} className={styles.list} aria-label={t("knowledge.list_label")}>
          {shown.map((item) => (
            <KnowledgeRow
              key={item.id}
              item={item}
              now={now}
              words={words}
              reach={reachWords(item.scope, reach.names, words)}
              projects={reach.projectList}
              onActed={() => setActed((n) => n + 1)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function KnowledgeRow(props: {
  item: Item;
  now: Date;
  words: ReturnType<typeof useWords>;
  reach: string;
  projects: S["ProjectView"][];
  onActed: () => void;
}) {
  const { t } = props.words;
  const { item } = props;
  const acts = useKnowledgeActs();
  const [narrowing, setNarrowing] = useState(false);
  const [editing, setEditing] = useState(false);
  const narrowButton = useRef<HTMLButtonElement>(null);
  const done = async (run: Promise<unknown>) => {
    await run;
    props.onActed();
  };
  const meta = [
    item.status === "proposed" || item.status === "active" ? "" : t(`knowledge.status.${item.status}`),
    t(`knowledge.from.${item.learnedFrom}`),
    item.untrusted ? t("knowledge.outside") : "",
    item.enforced ? t("knowledge.enforced") : "",
    props.reach,
    usedWords(item, props.now, props.words),
  ].filter(Boolean);
  const menu: MenuAction[] =
    item.status === "proposed"
      ? [
          { id: "edit", label: t("knowledge.edit"), run: () => setEditing(true) },
          { id: "just", label: t("knowledge.just_this_time"), run: () => void done(acts.justThisTime(item)) },
          { id: "discard", label: t("knowledge.discard"), run: () => void done(acts.discard(item)) },
        ]
      : item.status === "active"
        ? [{ id: "retire", label: t("knowledge.retire"), run: () => void done(acts.retire(item)) }]
        : [];
  const primary =
    item.status === "proposed" ? (
      <Button variant="primary" size="sm" data-key="primary" aria-label={t("knowledge.keep_named", { text: item.text })} onClick={() => void done(acts.keep(item))}>
        {t("knowledge.keep")}
      </Button>
    ) : item.status === "active" ? (
      <Button
        ref={narrowButton}
        size="sm"
        data-key="primary"
        aria-label={t("knowledge.narrow_named", { text: item.text })}
        aria-expanded={narrowing}
        onClick={() => setNarrowing(true)}
      >
        {t("knowledge.narrow")}
      </Button>
    ) : null;
  const extra = narrowing || editing || item.origin;
  const closeNarrow = () => {
    setNarrowing(false);
    narrowButton.current?.focus();
  };
  return (
    <Row
      pill={<Pill>{t(`knowledge.kind.${item.kind}`)}</Pill>}
      title={item.text}
      meta={meta.join(" · ")}
      primary={primary}
      menu={<RowMenu label={item.text} actions={menu} />}
    >
      {extra && (
        <>
          {narrowing && (
            <NarrowForm
              scope={item.scope}
              projects={props.projects}
              onCancel={closeNarrow}
              onSave={(scope) => {
                setNarrowing(false);
                void done(acts.narrow(item, scope));
              }}
            />
          )}
          <OriginLink origin={item.origin} />
          {editing && (
            <EditDrawer
              item={item}
              words={props.words}
              onClose={() => setEditing(false)}
              onKeep={(text) => {
                setEditing(false);
                void done(acts.keep(item, { text }));
              }}
            />
          )}
        </>
      )}
    </Row>
  );
}

/** Edit the wording of a proposal and keep it in one step; what is kept is the person's own wording. */
function EditDrawer(props: { item: Item; words: ReturnType<typeof useWords>; onClose: () => void; onKeep: (text: string) => void }) {
  const { t } = props.words;
  const [text, setText] = useState(props.item.text);
  const field = useId();
  const clean = text.trim();
  return (
    <Drawer
      open
      title={t("knowledge.edit.title")}
      onClose={props.onClose}
      dirty={text !== props.item.text}
      footer={
        <>
          <Button variant="primary" disabled={!clean} onClick={() => props.onKeep(clean)}>
            {t("knowledge.edit.keep")}
          </Button>
          <Button onClick={props.onClose}>{t("action.cancel")}</Button>
        </>
      }
    >
      <div className={styles.edit}>
        <label htmlFor={field}>{t("knowledge.edit.text")}</label>
        <textarea id={field} className="short" value={text} autoFocus onChange={(e) => setText(e.target.value)} />
        <p className="hint">{t("knowledge.edit.note")}</p>
      </div>
    </Drawer>
  );
}
