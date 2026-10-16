// A menu (design 7.12): a surface with a floating shadow, 36px items with an optional icon, a separator between groups,
// a disabled item that says why, and groups that choose one value (a checked item). Built on the React Aria menu, so it
// is keyboard and screen-reader complete. The trigger is any React Aria button (an IconButton, a StatusChip).
import { Fragment, type ReactNode } from "react";
import { Header, Menu, MenuItem, MenuSection, MenuTrigger, Popover, Separator, Text } from "react-aria-components";
import { Icon, type IconName } from "./Icon";
import styles from "./MenuButton.module.css";

export interface MenuEntry {
  id: string;
  label: string;
  icon?: IconName;
  run?: () => void;
  /** An address to open in a new tab instead of running something (only for an address the caller has checked). */
  href?: string;
  /** The entry can't be used now; `reason` says why, under its label. */
  disabled?: boolean;
  reason?: string;
  /** A line under the label that says what the entry does or costs, shown whether or not the entry can be used. */
  note?: string;
}

export interface MenuGroup {
  id: string;
  /** A small heading over the group. */
  title?: string;
  entries: MenuEntry[];
  /** The one chosen entry's id, for a group that picks a value (theme, density); it shows a check. */
  selected?: string;
}

export function MenuButton(props: { trigger: ReactNode; groups: MenuGroup[]; placement?: "bottom end" | "bottom start" | "top end" | "top start" }) {
  const groups = props.groups.filter((g) => g.entries.length);
  if (!groups.length) return null;
  const find = (key: unknown) => groups.flatMap((g) => g.entries).find((e) => e.id === key);
  return (
    <MenuTrigger>
      {props.trigger}
      <Popover placement={props.placement ?? "bottom end"} className={styles.popover}>
        <Menu className={styles.menu} onAction={(key) => find(key)?.run?.()}>
          {groups.map((group, index) => (
            <Fragment key={group.id}>
              {index > 0 && <Separator className={styles.sep} />}
              <MenuSection
                className={styles.group}
                aria-label={group.title ?? group.id}
                selectionMode={group.selected !== undefined ? "single" : "none"}
                selectedKeys={group.selected !== undefined ? [group.selected] : undefined}
              >
                {group.title && <Header className={styles.header}>{group.title}</Header>}
                {group.entries.map((entry) => (
                  <MenuItem
                    key={entry.id}
                    id={entry.id}
                    className={styles.item}
                    isDisabled={entry.disabled}
                    textValue={entry.label}
                    href={entry.href}
                    target={entry.href ? "_blank" : undefined}
                    rel={entry.href ? "noopener noreferrer" : undefined}
                  >
                    {({ isSelected }) => (
                      <>
                        {entry.icon && (
                          <span className={styles.lead}>
                            <Icon name={entry.icon} size={16} />
                          </span>
                        )}
                        <Text slot="label" className={entry.icon ? styles.label : styles.bare}>
                          {entry.label}
                        </Text>
                        {isSelected && (
                          <span className={styles.tick}>
                            <Icon name="check" size={16} />
                          </span>
                        )}
                        {(entry.disabled && entry.reason ? entry.reason : entry.note) && (
                          <Text slot="description" className={styles.reason}>
                            {entry.disabled && entry.reason ? entry.reason : entry.note}
                          </Text>
                        )}
                      </>
                    )}
                  </MenuItem>
                ))}
              </MenuSection>
            </Fragment>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
