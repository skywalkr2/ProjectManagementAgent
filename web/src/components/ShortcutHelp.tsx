// The list of keyboard shortcuts, from the configured keys.
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useWords } from "../lib/wording";

const ORDER = ["next", "previous", "primary", "send_back", "copy", "edit", "undo", "hand_in", "ask", "help"];

export function ShortcutHelp(props: { open: boolean; onClose: () => void; keys: Record<string, string> }) {
  const { t } = useWords();
  return (
    <ModalOverlay isOpen={props.open} onOpenChange={(open) => !open && props.onClose()} isDismissable className="help">
      <Modal className="panel help-panel" data-modal-open>
        <Dialog aria-labelledby="help-title" className="help-dialog">
          <Heading slot="title" id="help-title">
            {t("help.title")}
          </Heading>
          <dl>
            {ORDER.filter((a) => props.keys[a]).map((action) => (
              <div key={action} className="help-row">
                <dt>
                  <kbd>{props.keys[action]}</kbd>
                </dt>
                <dd>{t(`help.${action}`)}</dd>
              </div>
            ))}
            <div className="help-row">
              <dt>
                <kbd>{t("help.enter_key")}</kbd>
              </dt>
              <dd>{t("help.toggle")}</dd>
            </div>
            <div className="help-row">
              <dt>
                <kbd>{t("help.escape_key")}</kbd>
              </dt>
              <dd>{t("help.escape")}</dd>
            </div>
          </dl>
          <div className="row-end">
            <button type="button" className="btn primary" onClick={props.onClose} autoFocus>
              {t("action.close")}
            </button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
