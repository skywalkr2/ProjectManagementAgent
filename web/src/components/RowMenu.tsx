// The "…" menu on a row: every action other than the row's one primary action.
import { Button, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";
import { useWords } from "../lib/wording";

export interface MenuAction {
  id: string;
  label: string;
  run?: () => void;
  /** An address to open in a new tab instead of running something (only for an address the caller has checked). */
  href?: string;
}

export function RowMenu(props: { label: string; actions: MenuAction[] }) {
  const { t } = useWords();
  if (!props.actions.length) return null;
  return (
    <MenuTrigger>
      <Button className="btn more" aria-label={t("menu.more", { what: props.label })}>
        •••
      </Button>
      <Popover placement="bottom end" className="menu-popover">
        <Menu
          className="menu"
          onAction={(key) => props.actions.find((a) => a.id === key)?.run?.()}
          items={props.actions}
        >
          {(item) => (
            <MenuItem
              id={item.id}
              className="menu-item"
              href={item.href}
              target={item.href ? "_blank" : undefined}
              rel={item.href ? "noopener noreferrer" : undefined}
            >
              {item.label}
            </MenuItem>
          )}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
