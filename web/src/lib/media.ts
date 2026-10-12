// Reacting to the window's width. The phone layout follows the workspace's setting (`narrow_below_px`, and the page's
// `data-narrow` attribute the styles key off); other widths use media queries directly.
import { useEffect, useState } from "react";

function matches(query: string): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

/** Whether a media query matches now, kept up to date. */
export function useMediaQuery(query: string): boolean {
  const [on, setOn] = useState(() => matches(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const apply = () => setOn(list.matches);
    apply();
    list.addEventListener("change", apply);
    return () => list.removeEventListener("change", apply);
  }, [query]);
  return on;
}

/** True below the configured width: the sidebar gives way to the bottom bar. Sets `data-narrow` on the page. */
export function useNarrow(px: number): boolean {
  const narrow = useMediaQuery(`(max-width: ${px - 1}px)`);
  useEffect(() => {
    document.documentElement.toggleAttribute("data-narrow", narrow);
  }, [narrow]);
  return narrow;
}
