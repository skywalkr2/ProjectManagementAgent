// A tooltip that repeats what is already reachable another way (design 7.6): the label of an icon-only control.
import type { ReactNode } from "react";
import { Tooltip as AriaTooltip, TooltipTrigger } from "react-aria-components";
import styles from "./Tooltip.module.css";

export function Tooltip(props: { text: string; placement?: "top" | "bottom" | "left" | "right"; children: ReactNode }) {
  return (
    <TooltipTrigger delay={400} closeDelay={0}>
      {props.children}
      <AriaTooltip className={styles.tip} placement={props.placement ?? "bottom"} offset={6}>
        {props.text}
      </AriaTooltip>
    </TooltipTrigger>
  );
}
