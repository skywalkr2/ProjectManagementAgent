// The phone's review mode (design 7.1): a Work list opens one item at a time, the item in full with its evidence and
// source, then Looks good, Send back and Next as full-width buttons at the bottom, so a review is finished with no sideways
// scrolling and no menu. The buttons press the item's own actions (the same ones its keys use), so what they do and what
// they record is what the row's own buttons do. When an item leaves the list (it was approved) the next one takes its place.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { sendKeyTo } from "../lib/keys";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import styles from "./ReviewMode.module.css";

export function ReviewMode<T extends { id: string }>(props: {
  items: T[];
  /** The item in full, as its list row shows it opened. */
  render: (item: T) => ReactNode;
  /** Whether Send back can be used on the item. */
  canSendBack: (item: T) => boolean;
  onClose: () => void;
}) {
  const { t } = useWords();
  const { items } = props;
  const [currentId, setCurrentId] = useState<string | null>(items[0]?.id ?? null);
  const lastIndex = useRef(0);
  const body = useRef<HTMLOListElement>(null);
  // Where the person is follows the item, so a list that changes under them (another item arrives, this one is approved)
  // keeps them on it, or moves them to the one that took its place.
  const found = currentId === null ? -1 : items.findIndex((i) => i.id === currentId);
  const index = found >= 0 ? found : Math.min(lastIndex.current, Math.max(0, items.length - 1));
  const item: T | undefined = items[index];
  useEffect(() => {
    lastIndex.current = index;
    if (item && item.id !== currentId) setCurrentId(item.id);
  }, [index, item, currentId]);

  // The cursor starts on the item, so the keys work and a screen reader hears it.
  useEffect(() => {
    body.current?.querySelector<HTMLElement>("[data-row]")?.focus({ preventScroll: true });
  }, [item?.id]);

  if (!item) {
    return (
      <section className={styles.done} aria-labelledby="review-done">
        <h2 id="review-done" className={styles.heading}>
          {t("review.done")}
        </h2>
        <Button variant="primary" onClick={props.onClose}>
          {t("review.back")}
        </Button>
      </section>
    );
  }
  const press = (key: "primary" | "send_back") => {
    const row = body.current?.querySelector<HTMLElement>("[data-row]");
    if (row) sendKeyTo(row, key);
  };
  return (
    <section className={styles.mode} aria-labelledby="review-title">
      <div className={styles.top}>
        <h2 id="review-title" className={styles.heading} tabIndex={-1}>
          {t("review.progress", { n: index + 1, total: items.length })}
        </h2>
        <Button variant="ghost" size="sm" onClick={props.onClose}>
          {t("review.back")}
        </Button>
      </div>
      <ol className={styles.item} ref={body}>
        {props.render(item)}
      </ol>
      <div className={styles.bar} role="group" aria-label={t("review.actions")}>
        <Button disabled={!props.canSendBack(item)} onClick={() => press("send_back")}>
          {t("review.send_back")}
        </Button>
        <Button variant="primary" onClick={() => press("primary")}>
          {t("review.looks_good")}
        </Button>
        <Button disabled={items.length < 2} onClick={() => setCurrentId(items[(index + 1) % items.length].id)}>
          {t("review.next")}
        </Button>
      </div>
    </section>
  );
}
