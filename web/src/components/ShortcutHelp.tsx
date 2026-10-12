// The list of keyboard shortcuts, from the configured keys.
import { Heading } from "react-aria-components";
import { Button } from "../ui/Button";
import { useWords } from "../lib/wording";
import { ModalPanel } from "./ModalPanel";
import styles from "./ShortcutHelp.module.css";

const ORDER = ["next", "previous", "primary", "send_back", "copy", "edit", "undo", "hand_in", "ask", "help"];

export function ShortcutHelp(props: { open: boolean; onClose: () => void; keys: Record<string, string> }) {
  const { t } = useWords();
  if (!props.open) return null;
  return (
    <ModalPanel titleId="help-title" onClose={props.onClose} dismissable>
      <Heading slot="title" id="help-title" className={styles.title}>
        {t("help.title")}
      </Heading>
      <dl className={styles.list}>
        {ORDER.filter((a) => props.keys[a]).map((action) => (
          <div key={action} className={styles.row}>
            <dt>
              <kbd>{props.keys[action]}</kbd>
            </dt>
            <dd>{t(`help.${action}`)}</dd>
          </div>
        ))}
        <div className={styles.row}>
          <dt>
            <kbd>{t("help.enter_key")}</kbd>
          </dt>
          <dd>{t("help.toggle")}</dd>
        </div>
        <div className={styles.row}>
          <dt>
            <kbd>{t("help.escape_key")}</kbd>
          </dt>
          <dd>{t("help.escape")}</dd>
        </div>
      </dl>
      <div className={styles.end}>
        <Button variant="primary" onClick={props.onClose} autoFocus>
          {t("action.close")}
        </Button>
      </div>
    </ModalPanel>
  );
}
