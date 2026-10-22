// Today's line for reminders that can't go the way the person chose (design 6.12): their standing yes has gone stale (the
// wording changed, the account may no longer act, their own address changed), so reminders wait for them until they look
// again. It starts with the verb, says what changed, and opens Settings where the choice is made.
import { useId } from "react";
import { staleLine, useReminderWhere } from "../lib/reminder-where";
import { settingsView, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Row } from "../ui/Row";
import { SafeText } from "./SafeText";

export function ReminderWhereRow(props: { onView?: (view: View) => void }) {
  const { t } = useWords();
  const view = useReminderWhere();
  const titleId = useId();
  const title = staleLine(view.data, t);
  if (!title) return null;
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
        <Button size="sm" variant="primary" data-key="primary" aria-describedby={titleId} onClick={() => props.onView?.(settingsView("today"))}>
          {t("reminders.where.stale.open")}
        </Button>
      }
    />
  );
}
