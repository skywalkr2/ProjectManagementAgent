// A group of the Today queue (design 7.7): a small heading and its rows, in a list. The groups come in rank order and
// nothing nests inside a row beyond its items.
import type { ReactNode } from "react";
import styles from "./Today.module.css";

export function QueueGroup(props: { id: string; title: string; children: ReactNode }) {
  return (
    <section className={styles.group} aria-labelledby={props.id}>
      <h3 id={props.id} className={styles.groupHead}>
        {props.title}
      </h3>
      <ul className={styles.list}>{props.children}</ul>
    </section>
  );
}
