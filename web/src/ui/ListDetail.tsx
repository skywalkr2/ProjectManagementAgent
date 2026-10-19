// A list and the detail of the row chosen (design 7.13): from 1024px the detail is a pane beside the list, which keeps its
// place; below that it opens as a drawer. `detail` is null while no row is chosen.
import type { ReactNode } from "react";
import { useMediaQuery } from "../lib/media";
import { useWords } from "../lib/wording";
import { Drawer } from "./Drawer";
import { IconButton } from "./IconButton";
import styles from "./ListDetail.module.css";

export function ListDetail(props: { children: ReactNode; detail: ReactNode | null; title: string; onClose: () => void }) {
  const { t } = useWords();
  const beside = useMediaQuery("(min-width: 1024px)");
  const open = props.detail !== null;
  return (
    <div className={[styles.split, open && beside ? styles.open : ""].filter(Boolean).join(" ")}>
      <div className={styles.main}>{props.children}</div>
      {open &&
        (beside ? (
          <aside className={styles.pane} aria-label={props.title} data-detail-pane="">
            <div className={styles.head}>
              <h2 className={styles.title}>{props.title}</h2>
              <IconButton icon="close" label={t("action.close")} onPress={props.onClose} />
            </div>
            <div className={styles.body}>{props.detail}</div>
          </aside>
        ) : (
          <Drawer open title={props.title} onClose={props.onClose}>
            <div className={styles.body}>{props.detail}</div>
          </Drawer>
        ))}
    </div>
  );
}
