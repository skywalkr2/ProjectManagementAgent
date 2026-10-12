// The sidebar (design 7.1, 7.13): Today with its count, then Work, then Records, then Sources, Add-ons and Settings at the
// bottom. Every entry is a real link, so it can be bookmarked, opened in a new tab and reached with Back. It is 232px with
// labels from 1280px and a 64px icon rail (a tooltip per icon) below that; the person can collapse or pin it at any
// width, remembered on this device.
import { useState } from "react";
import { Link } from "react-aria-components";
import { useMediaQuery } from "../lib/media";
import { viewHref, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { Tooltip } from "../ui/Tooltip";
import { useNav, type NavEntry } from "./nav";
import styles from "./Sidebar.module.css";

const KEY = "cockpit:sidebar";

function saved(): "collapsed" | "expanded" | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "collapsed" || v === "expanded" ? v : null;
  } catch {
    return null;
  }
}

/** Whether the sidebar shows labels: the person's choice for this device, or else by width (labels from 1280px). */
export function useSidebarMode(): { expanded: boolean; toggle: () => void } {
  const wide = useMediaQuery("(min-width: 1280px)");
  const [pref, setPref] = useState(saved);
  const expanded = pref ? pref === "expanded" : wide;
  const toggle = () => {
    const next = expanded ? "collapsed" : "expanded";
    setPref(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // Storage can be blocked; the choice then lasts until the page closes.
    }
  };
  return { expanded, toggle };
}

function Entry(props: { entry: NavEntry; current: View; rail: boolean; sub?: boolean }) {
  const { entry } = props;
  const link = (
    <Link
      href={viewHref(entry.view)}
      className={[styles.entry, props.sub ? styles.sub : ""].filter(Boolean).join(" ")}
      aria-current={props.current === entry.view ? "page" : undefined}
      data-view={entry.view}
    >
      {entry.icon ? <Icon name={entry.icon} /> : <span className={styles.glyph} aria-hidden="true">{entry.glyph}</span>}
      <span className={styles.label}>{entry.label}</span>
      {entry.count ? <span className={styles.count}>{entry.count}</span> : null}
    </Link>
  );
  return props.rail ? <Tooltip text={entry.label} placement="right">{link}</Tooltip> : link;
}

export function Sidebar(props: { current: View; expanded: boolean; onToggle: () => void }) {
  const { t } = useWords();
  const nav = useNav();
  const rail = !props.expanded;
  const entry = (e: NavEntry, sub = false) => <Entry key={e.view} entry={e} current={props.current} rail={rail} sub={sub && !rail} />;
  const builtIn = 4;
  return (
    <nav className={[styles.side, rail ? styles.rail : ""].filter(Boolean).join(" ")} aria-label={t("nav.label")}>
      <div className={styles.group}>{entry(nav.today)}</div>
      <div className={styles.group} role="group" aria-labelledby="nav-work">
        <span id="nav-work" className={styles.title}>
          {t("nav.work")}
        </span>
        {nav.work.map((e, i) => entry(e, i >= builtIn))}
      </div>
      <div className={styles.group} role="group" aria-labelledby="nav-records">
        <span id="nav-records" className={styles.title}>
          {t("nav.records")}
        </span>
        {nav.records.map((e, i) => entry(e, i >= 3))}
      </div>
      <div className={styles.bottom}>
        {nav.bottom.map((e) => entry(e))}
        <div className={styles.toggle}>
          <IconButton
            icon="panel-left"
            label={t(props.expanded ? "nav.collapse" : "nav.expand")}
            onPress={props.onToggle}
            data-sidebar-toggle=""
          />
        </div>
      </div>
    </nav>
  );
}
