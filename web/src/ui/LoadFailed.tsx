// A failed load, inline where it happened (design 7.12): what couldn't be loaded, Try again, and the raw detail behind
// "Details". Errors are never toasts.
import { useWords } from "../lib/wording";
import { Button } from "./Button";
import { Icon } from "./Icon";
import styles from "./LoadFailed.module.css";

export function LoadFailed(props: { message: string; onRetry: () => void; detail?: string | null }) {
  const { t } = useWords();
  return (
    <div className={styles.failed} role="alert">
      <div className={styles.line}>
        <p className={styles.message}>
          <Icon name="alert" size={16} />
          {props.message}
        </p>
        <Button size="sm" icon="refresh" onClick={props.onRetry}>
          {t("action.try_again")}
        </Button>
      </div>
      {props.detail && (
        <details className={styles.details}>
          <summary>{t("action.details")}</summary>
          <p className={styles.detail}>{props.detail}</p>
        </details>
      )}
    </div>
  );
}
