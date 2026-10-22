// Today's lines for what went wrong on the way out or can't be told (design 6.12, 7.7): one line for each act that failed
// ("Sign in to <account> again", or the reason), that may or may not have gone out ("Check the Sent folder for the message to
// <person>", with It was sent and Send it again), or whose yes no longer covers it ("Look again at the message to <person>: <what
// changed>"). Each starts with the verb and opens the act in Waiting to go out. A line goes when the act does.
import { useId, useState } from "react";
import { actPhrase, changedWords, useOutgoing, type Act, type ActLine } from "../lib/acts";
import { revealOrKeep } from "../lib/reveal";
import type { View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Row } from "../ui/Row";
import { ConfirmSend } from "./ConfirmSend";
import { RowMenu, type MenuAction } from "./RowMenu";
import { SafeText } from "./SafeText";

/** Opens the act in Waiting to go out, where the screen is asked for it as it opens. */
export function openAct(act: Act, onView?: (view: View) => void): void {
  if (onView) onView("work/outgoing");
  revealOrKeep("act", act.id);
}

export function ActTodayRows(props: { lines: ActLine[]; onView?: (view: View) => void }) {
  return (
    <>
      {props.lines.map(({ act }) => (
        <ActTodayRow key={act.id} act={act} onView={props.onView} />
      ))}
    </>
  );
}

function ActTodayRow(props: { act: Act; onView?: (view: View) => void }) {
  const { t } = useWords();
  const out = useOutgoing();
  const [again, setAgain] = useState(false);
  const titleId = useId();
  const { act } = props;
  const what = actPhrase(act, t);
  const open = () => openAct(act, props.onView);

  let title: string;
  let primary: { label: string; run: () => void };
  const menu: MenuAction[] = [];
  if (act.status === "uncertain") {
    title = t(`outgoing.today.uncertain.${act.kind}`, { what });
    primary = { label: t("outgoing.uncertain.sent"), run: () => void out.markSent(act) };
    menu.push({ id: "again", label: t("outgoing.uncertain.again"), run: () => setAgain(true) });
    menu.push({ id: "open", label: t("outgoing.today.open"), run: open });
  } else if (act.status === "stale") {
    title = t("outgoing.today.stale", { what, changed: changedWords(act, t) });
    primary = { label: t("outgoing.look_again"), run: open };
  } else {
    // A withdrawn sign-in says which account to sign in to again, in the channel's own words.
    const reason = act.failure?.reason ?? "";
    title = act.failure?.kind === "auth" && reason ? reason : t("outgoing.today.failed", { what, reason: reason || t("outgoing.toast.no_reason") });
    primary = { label: t("outgoing.today.open"), run: open };
  }

  return (
    <Row
      aria-labelledby={titleId}
      title={
        <span id={titleId}>
          <SafeText text={title} />
        </span>
      }
      oneLine
      primary={
        <Button size="sm" variant="primary" data-key="primary" aria-describedby={titleId} onClick={primary.run}>
          {primary.label}
        </Button>
      }
      menu={menu.length > 0 ? <RowMenu label={title} actions={menu} /> : undefined}
    >
      {again && (
        <ConfirmSend
          act={act}
          again
          onCancel={() => setAgain(false)}
          onGo={() => {
            setAgain(false);
            void out.sendAgain(act);
          }}
        />
      )}
    </Row>
  );
}
