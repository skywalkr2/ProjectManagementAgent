// The one confirm on the way out (design 7.1): a send says what it will do ("Send this message to <person> now?") and goes only on
// the person's word. The content it sends is the one on the screen behind it.
import { useId } from "react";
import { Heading } from "react-aria-components";
import { recipientNames, type Act } from "../lib/acts";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { ModalPanel } from "./ModalPanel";

export function ConfirmSend(props: { act: Act; again?: boolean; onGo: () => void; onCancel: () => void }) {
  const { t } = useWords();
  const titleId = useId();
  const { act } = props;
  const title = t(`outgoing.confirm.${props.again ? "again." : ""}${act.kind}`, {
    names: recipientNames(act, t),
    calendar: act.calendar ?? "",
    folder: act.folder ?? "",
  });
  return (
    <ModalPanel titleId={titleId} onClose={props.onCancel}>
      <Heading slot="title" id={titleId}>
        {title}
      </Heading>
      <p>{t("outgoing.confirm.text")}</p>
      <div className="row-end">
        <Button onClick={props.onCancel}>{t("action.cancel")}</Button>
        <Button variant="primary" onClick={props.onGo}>
          {t("outgoing.confirm.go")}
        </Button>
      </div>
    </ModalPanel>
  );
}
