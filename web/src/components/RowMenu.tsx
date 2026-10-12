// The "…" menu on a row: every action other than the row's one primary action.
import { IconButton } from "../ui/IconButton";
import { MenuButton, type MenuEntry } from "../ui/MenuButton";
import { useWords } from "../lib/wording";

export type MenuAction = MenuEntry;

export function RowMenu(props: { label: string; actions: MenuAction[]; buttonId?: string }) {
  const { t } = useWords();
  if (!props.actions.length) return null;
  return (
    <MenuButton
      groups={[{ id: "actions", entries: props.actions }]}
      trigger={<IconButton id={props.buttonId} icon="more" size="sm" label={t("menu.more", { what: props.label })} tooltip={false} />}
    />
  );
}
