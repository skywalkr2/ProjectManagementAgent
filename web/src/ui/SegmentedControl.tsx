// The one segmented control, for two to four filters (design 7.12). Tabs are for switching panes inside a record, and
// neither is ever the main navigation.
import { ToggleButton, ToggleButtonGroup } from "react-aria-components";
import styles from "./SegmentedControl.module.css";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
}

export function SegmentedControl<T extends string>(props: {
  /** Names the group for screen readers. */
  label: string;
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <ToggleButtonGroup
      aria-label={props.label}
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={[props.value]}
      onSelectionChange={(keys) => {
        const next = [...keys][0];
        if (next !== undefined) props.onChange(String(next) as T);
      }}
      className={[styles.track, props.className ?? ""].filter(Boolean).join(" ")}
    >
      {props.options.map((o) => (
        <ToggleButton key={o.value} id={o.value} className={styles.segment}>
          {o.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
