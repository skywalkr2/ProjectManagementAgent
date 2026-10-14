// The rules review (design 6.22, 7.18): the standing rules the assistant was given and never showed applying, with how often
// each was given, how large what every run is sent is against its budget, and Keep, Narrow or Retire on each.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { useKnowledgeActs } from "../lib/knowledge-acts";
import { reachWords } from "../lib/knowledge";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { LoadFailed } from "../ui/LoadFailed";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { Skeleton } from "../ui/Skeleton";
import { useReachNames } from "./Knowledge";
import { NarrowForm } from "./NarrowForm";
import { RowMenu } from "./RowMenu";
import styles from "./Knowledge.module.css";

export function RuleReview(props: { onBack: () => void }) {
  const words = useWords();
  const { t, tn } = words;
  const review = useQuery({ queryKey: ["knowledge", "rules", "review"], queryFn: api.ruleReview });
  const reach = useReachNames();
  const list = useRef<HTMLUListElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [acted, setActed] = useState(0);
  // After an act the row it was on leaves the list; keyboard focus moves to what is now first.
  useEffect(() => {
    if (acted === 0) return;
    (list.current?.querySelector<HTMLElement>("[data-row]") ?? heading.current)?.focus();
  }, [acted]);
  const found = review.data;
  return (
    <section className="panel-section" aria-labelledby="rules-review-title">
      <div className="heading">
        <h1 id="rules-review-title" ref={heading} tabIndex={-1}>
          {t("rules_review.title")}
        </h1>
      </div>
      <p className={styles.back}>
        <Button size="sm" variant="ghost" onClick={props.onBack}>
          {t("rules_review.back")}
        </Button>
      </p>
      {review.isError ? (
        <LoadFailed message={t("rules_review.load_failed")} onRetry={() => void review.refetch()} />
      ) : !found ? (
        <Skeleton />
      ) : (
        <>
          <p className={styles.intro}>{t("rules_review.intro", { days: found.days })}</p>
          <div className={styles.sizes}>
            <p>{t("rules_review.size", { size: found.stable_chars, budget: found.stable_budget })}</p>
            {found.moved > 0 && <p>{tn("rules_review.moved", found.moved)}</p>}
          </div>
          {found.flagged.length === 0 ? (
            <p className="empty">{t("rules_review.empty")}</p>
          ) : (
            <ul ref={list} className={styles.list} aria-label={t("rules_review.list_label")}>
              {found.flagged.map((rule) => (
                <ReviewRow
                  key={rule.id}
                  rule={rule}
                  words={words}
                  reach={reachWords(rule.applies_to, reach.names, words)}
                  projects={reach.projectList}
                  onActed={() => setActed((n) => n + 1)}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function ReviewRow(props: {
  rule: S["RuleReviewRule"];
  words: ReturnType<typeof useWords>;
  reach: string;
  projects: S["ProjectView"][];
  onActed: () => void;
}) {
  const { t, tn } = props.words;
  const { rule } = props;
  const acts = useKnowledgeActs();
  const [narrowing, setNarrowing] = useState(false);
  const text = rule.text || rule.name;
  const done = async (run: Promise<unknown>) => {
    await run;
    props.onActed();
  };
  return (
    <Row
      pill={<Pill>{t("knowledge.kind.rule")}</Pill>}
      title={text}
      meta={[tn("rules_review.counts", rule.present), props.reach].join(" · ")}
      primary={
        <Button variant="primary" size="sm" data-key="primary" aria-label={t("knowledge.keep_named", { text })} onClick={() => void done(acts.keepRule(rule))}>
          {t("knowledge.keep")}
        </Button>
      }
      menu={
        <RowMenu
          label={text}
          actions={[
            { id: "narrow", label: t("knowledge.narrow"), run: () => setNarrowing(true) },
            { id: "retire", label: t("knowledge.retire"), run: () => void done(acts.retire(rule)) },
          ]}
        />
      }
    >
      {narrowing && (
        <NarrowForm
          scope={rule.applies_to}
          projects={props.projects}
          onCancel={() => setNarrowing(false)}
          onSave={(scope) => {
            setNarrowing(false);
            void done(acts.narrow(rule, scope));
          }}
        />
      )}
    </Row>
  );
}
