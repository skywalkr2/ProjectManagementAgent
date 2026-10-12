// One line-icon set, drawn inline so nothing is fetched at run time (design 7.12). Icons use the text color, a 1.8
// stroke and an 18px box by default. An icon is decoration unless it has a label; icons never carry status alone.
import type { ReactNode } from "react";

const SHAPES = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  inbox: <path d="M3 13l3-8h12l3 8v6H3z M3 13h5l1 3h6l1-3h5" />,
  send: <path d="M22 2L11 13 M22 2l-7 20-4-9-9-4z" />,
  upload: <path d="M12 3v12 M7 8l5-5 5 5 M4 15v5h16v-5" />,
  layers: <path d="M12 3l9 5-9 5-9-5z M3 13l9 5 9-5" />,
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5 M16 4.5a3.5 3.5 0 0 1 0 7 M18 14.5c2 .6 3.2 2.5 3.6 5.5" />
    </>
  ),
  folder: <path d="M3 6h6l2 2h10v11H3z" />,
  rss: (
    <>
      <path d="M4 11a9 9 0 0 1 9 9 M4 4a16 16 0 0 1 16 16" />
      <circle cx="5" cy="19" r="1" />
    </>
  ),
  puzzle: <path d="M10 3h4v3a2 2 0 1 0 4 0V3h3v7h-3a2 2 0 1 0 0 4h3v7h-7v-3a2 2 0 1 0-4 0v3H3v-7h3a2 2 0 1 0 0-4H3V3z" />,
  gear: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </>
  ),
  plus: <path d="M12 5v14 M5 12h14" />,
  more: (
    <>
      <circle cx="5" cy="12" r="1.2" />
      <circle cx="12" cy="12" r="1.2" />
      <circle cx="19" cy="12" r="1.2" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14 M12 17h.01" />
    </>
  ),
  chevron: <path d="M9 6l6 6-6 6" />,
  "chevron-down": <path d="M6 9l6 6 6-6" />,
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  close: <path d="M6 6l12 12 M18 6L6 18" />,
  alert: <path d="M12 3l10 18H2z M12 10v5 M12 18h.01" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  refresh: <path d="M20 11a8 8 0 0 0-14.5-4.2 M4 5v4h4 M4 13a8 8 0 0 0 14.5 4.2 M20 19v-4h-4" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4" />
    </>
  ),
  moon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
  monitor: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8 M12 16v4" />
    </>
  ),
  menu: <path d="M4 6h16 M4 12h16 M4 18h16" />,
  "panel-left": (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof SHAPES;
export const ICON_NAMES = Object.keys(SHAPES) as IconName[];

export function Icon(props: {
  name: IconName;
  /** Pixels; 18 in navigation and buttons, 16 in meta lines. */
  size?: number;
  /** An accessible name. Without one the icon is decoration and is hidden from screen readers. */
  label?: string;
  className?: string;
}) {
  const size = props.size ?? 18;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={props.className}
      focusable="false"
      data-icon={props.name}
      {...(props.label ? { role: "img", "aria-label": props.label } : { "aria-hidden": true })}
    >
      {SHAPES[props.name]}
    </svg>
  );
}
