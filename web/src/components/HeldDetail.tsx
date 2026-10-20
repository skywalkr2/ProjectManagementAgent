// What a held line opens (design 7.6, 7.7): the one decision it asks and nothing of the change it came from: the question,
// the words it rests on and who said them, where it came from, why it waits, and the same answers the line has. The change's
// own card, with its Looks good, stays on What changed; a held op that isn't shaped as a question is shown as its own row.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { useHeldAnswers } from "../lib/held-answers";
import { heldTitle, heldTold, titleWords } from "../lib/queue-words";
import type { QueueLine } from "../lib/today";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import styles from "./HeldDetail.module.css";
import { OpRow, SourcePanel } from "./WhatChanged";

export function HeldDetail(props: { line: QueueLine }) {
  const { line } = props;
  const { t, has } = useWords();
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  const answers = useHeldAnswers(line.changeset ?? "", line.op ?? 0, line.held ?? null);
  const [showSource, setShowSource] = useState(false);
  const ask = line.held;
  const item = changes.data?.find((c) => c.id === line.request);
  const op = item?.changeset?.ops.find((o) => o.index === line.op);

  if (!ask || !answers) {
    // A hold that isn't a question with two answers: its own row, with its label and why it waits, and nothing around it.
    if (changes.isPending) return <Skeleton />;
    if (!item?.changeset || !op) return <p className="hint">{t("queue.detail.gone")}</p>;
    return (
      <ul className="children">
        <OpRow op={op} cs={item.changeset} source={item.source} />
      </ul>
    );
  }
  const told = heldTold(ask, t);
  const source = item?.source ?? null;
  const from = titleWords(line.title, t, has);
  const buttons = [
    ...(answers.other ? [{ id: "other", ...answers.other, primary: false }] : []),
    { id: "primary", ...answers.primary, primary: true },
    ...answers.menu.map((m) => ({ ...m, primary: false })),
  ];
  return (
    <section className={styles.held} aria-label={heldTitle(ask, t)}>
      <p className={styles.question}>{heldTitle(ask, t)}</p>
      <dl className={styles.facts}>
        {ask.quote && (
          <div className={styles.fact}>
            <dt>{t("queue.held.detail.said")}</dt>
            <dd>
              {t("queue.held.quote", { quote: ask.quote })}
              {ask.reporter ? ` · ${t("queue.held.e.said_by", { name: ask.reporter })}` : ""}
            </dd>
          </div>
        )}
        {told && (
          <div className={styles.fact}>
            <dd>
              <strong>{told}</strong>
            </dd>
          </div>
        )}
        {from && (
          <div className={styles.fact}>
            <dt>{t("queue.held.detail.source")}</dt>
            <dd>
              {from}
              {source && ask.quote && (
                <>
                  {" "}
                  <button type="button" className="link-button" aria-expanded={showSource} onClick={() => setShowSource(!showSource)}>
                    {t(showSource ? "op.hide_source" : "op.show_source")}
                  </button>
                </>
              )}
            </dd>
          </div>
        )}
        {line.waiting && (
          <div className={styles.fact}>
            <dt>{t("queue.held.detail.reason")}</dt>
            <dd>{line.waiting}</dd>
          </div>
        )}
      </dl>
      {showSource && source && ask.quote && <SourcePanel id={source} quote={ask.quote} />}
      <div className={styles.answers}>
        {buttons.map((b) => (
          <Button key={b.id} size="sm" variant={b.primary ? "primary" : "secondary"} onClick={b.run}>
            {b.label}
          </Button>
        ))}
      </div>
    </section>
  );
}
