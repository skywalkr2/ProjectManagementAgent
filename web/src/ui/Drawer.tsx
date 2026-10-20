// A drawer from the right (design 7.12, 7.13): for forms and hand-in, so the list stays visible. It has a sticky footer for
// its actions, closes with Esc, and when it holds unsaved text (`dirty`) Esc or a click outside asks first instead of
// losing it. Focus returns to what opened it when it closes.
import { useId, useState, type ReactNode } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useCursorRef } from "../lib/cursor";
import { useWords } from "../lib/wording";
import { Button } from "./Button";
import { IconButton } from "./IconButton";
import styles from "./Drawer.module.css";

export function Drawer(props: {
  open: boolean;
  title: string;
  onClose: () => void;
  /** Unsaved text: closing then asks "keep editing or discard". */
  dirty?: boolean;
  /** The actions, pinned to the bottom. */
  footer?: ReactNode;
  /** About 640px instead of the detail width. */
  wide?: boolean;
  children: ReactNode;
}) {
  const { t } = useWords();
  const [guarding, setGuarding] = useState(false);
  // Each drawer has its own heading id, so one opened over another is named by its own title.
  const titleId = useId();
  // The cursor starts in the drawer's first field, or on its heading when it has none (design 7.0).
  const cursor = useCursorRef(titleId);
  const close = () => {
    setGuarding(false);
    props.onClose();
  };
  const attempt = () => {
    if (props.dirty) setGuarding(true);
    else close();
  };
  return (
    <ModalOverlay
      isOpen={props.open}
      onOpenChange={(open) => {
        if (!open) attempt();
      }}
      isDismissable
      className={styles.overlay}
    >
      <Modal className={[styles.modal, props.wide ? styles.wide : ""].filter(Boolean).join(" ")} data-modal-open="">
        <Dialog ref={cursor} className={styles.dialog} aria-labelledby={titleId}>
          <div className={styles.head}>
            <Heading slot="title" id={titleId} className={styles.title}>
              {props.title}
            </Heading>
            <IconButton icon="close" label={t("action.close")} onPress={attempt} />
          </div>
          <div className={styles.body}>{props.children}</div>
          {(props.footer || guarding) && (
            <div className={styles.footer}>
              {guarding ? (
                <>
                  <p className={styles.guard} role="alert">
                    {t("drawer.discard_ask")}
                  </p>
                  <Button onClick={() => setGuarding(false)} autoFocus>
                    {t("drawer.keep_editing")}
                  </Button>
                  <Button variant="danger" onClick={close}>
                    {t("drawer.discard")}
                  </Button>
                </>
              ) : (
                props.footer
              )}
            </div>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
