// An icon-only button: the label is required (it is the accessible name and the tooltip). Built on the React Aria button
// so it can open a menu or a popover as their trigger.
import { Button as AriaButton, type ButtonProps as AriaButtonProps } from "react-aria-components";
import { Icon, type IconName } from "./Icon";
import { Tooltip } from "./Tooltip";
import styles from "./Button.module.css";

export interface IconButtonProps extends Omit<AriaButtonProps, "children" | "className" | "aria-label"> {
  icon: IconName;
  /** Required: what the button does, in words. */
  label: string;
  size?: "md" | "sm";
  variant?: "ghost" | "secondary";
  /** Show the tooltip; turn off where the label is also visible beside it. */
  tooltip?: boolean;
  className?: string;
  iconSize?: number;
}

export function IconButton(props: IconButtonProps) {
  const { icon, label, size = "md", variant = "ghost", tooltip = true, className, iconSize, ...rest } = props;
  const classes = [styles.btn, styles[variant], styles["icon-only"], size === "sm" ? styles.sm : "", className ?? ""].filter(Boolean).join(" ");
  const button = (
    <AriaButton {...rest} className={classes} aria-label={label}>
      <Icon name={icon} size={iconSize} />
    </AriaButton>
  );
  return tooltip ? <Tooltip text={label}>{button}</Tooltip> : button;
}
