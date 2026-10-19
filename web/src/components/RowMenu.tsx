// The "…" menu on a row: every action other than the row's one primary action.
import { IconButton } from "../ui/IconButton";
import { MenuButton, type MenuEntry, type MenuGroup } from "../ui/MenuButton";
import { useWords } from "../lib/wording";

export type MenuAction = MenuEntry;

/** `groups` are further titled groups of choices after the actions (the snooze choices of a reminder). */
export function RowMenu(props: { label: string; actions: MenuAction[]; groups?: MenuGroup[]; buttonId?: string }) {
  const { t } = useWords();
  const groups = (props.groups ?? []).filter((g) => g.entries.length > 0);
  if (!props.actions.length && !groups.length) return null;
  return (
    <MenuButton
      groups={[{ id: "actions", entries: props.actions }, ...groups]}
      trigger={<IconButton id={props.buttonId} icon="more" size="sm" label={t("menu.more", { what: props.label })} tooltip={false} />}
    />
  );
}
