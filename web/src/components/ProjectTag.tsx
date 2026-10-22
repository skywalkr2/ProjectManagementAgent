// An action's project as a small tag, with the project it is part of when there is one ("Parent › Project"). Shared by
// every list that shows an action, so the same row reads the same everywhere (design 7.5, 7.7).
import { useWords } from "../lib/wording";
import styles from "./ProjectTag.module.css";

export function ProjectTag(props: { name: string; parent: string | null | undefined; className?: string }) {
  const { t } = useWords();
  if (!props.name) return null;
  return <span className={props.className ?? styles.project}>{props.parent ? t("open.project_in", { parent: props.parent, project: props.name }) : props.name}</span>;
}
