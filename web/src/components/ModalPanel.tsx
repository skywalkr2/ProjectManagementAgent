// A modal dialog: labelled by its heading, focus kept inside, Escape closes. The marker attribute pauses the row
// shortcuts while it is open. Where focus goes on close is up to the caller (see restoreFocus).
import type { ReactNode } from "react";
import { Dialog, Modal, ModalOverlay } from "react-aria-components";

export function ModalPanel(props: { titleId: string; onClose: () => void; children: ReactNode }) {
  return (
    <ModalOverlay isOpen onOpenChange={(open) => !open && props.onClose()} className="help">
      <Modal className="panel dialog-panel" data-modal-open>
        <Dialog aria-labelledby={props.titleId} className="help-dialog">
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
