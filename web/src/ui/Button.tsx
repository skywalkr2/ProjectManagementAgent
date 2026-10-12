// The one button (design 7.12): primary for the likeliest next step of a row or region, secondary for the other visible
// actions, ghost for toolbars, danger for irreversible confirms only. A disabled button says why (`reason`), under it
// and wired to it for screen readers; it is never shown by opacity alone.
import { useId, type ButtonHTMLAttributes, type ReactNode, type Ref } from "react";
import { Icon, type IconName } from "./Icon";
import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "md" | "sm";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** A leading icon. */
  icon?: IconName;
  /** A spinner replaces the icon; the label stays and the button does nothing until it is done. */
  loading?: boolean;
  /** Why the button is disabled, shown under it. Ignored while it is enabled. */
  reason?: string;
  children: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

export function Button(props: ButtonProps) {
  const { variant = "secondary", size = "md", icon, loading, reason, disabled, className, children, onClick, ref, ...rest } = props;
  const hintId = useId();
  const hint = disabled && reason ? reason : null;
  const classes = [styles.btn, styles[variant], size === "sm" ? styles.sm : "", loading ? styles.loading : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  const button = (
    <button
      type="button"
      {...rest}
      ref={ref}
      className={classes}
      disabled={disabled}
      aria-busy={loading || undefined}
      aria-describedby={[rest["aria-describedby"], hint ? hintId : null].filter(Boolean).join(" ") || undefined}
      onClick={loading ? undefined : onClick}
      data-variant={variant}
    >
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
  if (!hint) return button;
  return (
    <span className={styles.wrap}>
      {button}
      <p id={hintId} className={styles.reason}>
        {hint}
      </p>
    </span>
  );
}
