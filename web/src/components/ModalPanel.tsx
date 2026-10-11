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

/** Put focus back on the control that opened a dialog, once the dialog has gone. */
export function restoreFocus(target: () => HTMLElement | null | undefined): void {
  window.setTimeout(() => target()?.focus(), 0);
}
