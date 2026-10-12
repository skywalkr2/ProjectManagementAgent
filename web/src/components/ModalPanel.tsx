// A modal dialog (design 7.12): labelled by its heading, focus kept inside, Escape closes. The marker attribute pauses the
// row shortcuts while it is open. Where focus goes on close is up to the caller (see restoreFocus).
import type { ReactNode } from "react";
import { Dialog, Modal, ModalOverlay } from "react-aria-components";
import styles from "./ModalPanel.module.css";

export function ModalPanel(props: { titleId: string; onClose: () => void; /** A click outside closes it too. */ dismissable?: boolean; children: ReactNode }) {
  return (
    <ModalOverlay isOpen onOpenChange={(open) => !open && props.onClose()} isDismissable={props.dismissable} className={styles.overlay}>
      <Modal className={`${styles.modal} dialog-panel`} data-modal-open>
        <Dialog aria-labelledby={props.titleId} className={`${styles.dialog} help-dialog`}>
          {props.children}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

/** Put focus back on the control that opened a dialog, once the dialog has gone. While a dialog is open the rest of the
 * page is inert, and that is lifted a moment after the dialog leaves, so this waits (a frame at a time, about a second
 * at most) until the control can take focus. */
export function restoreFocus(target: () => HTMLElement | null | undefined, frames = 60): void {
  const attempt = (left: number) => {
    const el = target();
    const blocked = !el || !!document.querySelector("[data-modal-open]") || !!el.closest("[inert], [aria-hidden=true]");
    if (blocked && left > 0) {
      window.requestAnimationFrame(() => attempt(left - 1));
      return;
    }
    el?.focus();
  };
  window.requestAnimationFrame(() => attempt(frames));
}
