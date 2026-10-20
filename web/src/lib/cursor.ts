// Where the cursor starts when a dialog or drawer opens (design 7.0, "the cursor starts where you type"): in its first
// field, or on its heading when it has none. A field that was given the cursor already (autofocus, a chosen button)
// keeps it. Content that loads after the dialog opened can bring a field later; until the person moves the cursor
// themselves the first field that appears takes it from the heading.

import { useCallback, useRef } from "react";

const FIELDS = "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])";
/** How long a field that arrives late may still take the cursor. */
const WAIT_MS = 3000;

const usable = (el: HTMLElement) => !el.closest("[hidden], [inert], [aria-hidden=true]");

/** The first field inside a dialog that a person could type in or choose from now. */
export function firstField(root: HTMLElement): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>(FIELDS)).find(usable) ?? null;
}

/** Starts the cursor in `root`: its first field, else the heading with id `titleId`. Returns a function that stops
 * watching for late fields. */
export function startCursor(root: HTMLElement, titleId?: string): () => void {
  const heading = () => (titleId ? document.getElementById(titleId) : null);
  const mine = (el: Element | null) => !!el && root.contains(el);
  // The cursor is where the person or the dialog's own autofocus put it, rather than on the dialog or its heading.
  const claimed = () => {
    const at = document.activeElement;
    return mine(at) && at !== root && at !== heading();
  };
  const place = () => {
    const field = firstField(root);
    if (field) {
      field.focus({ preventScroll: true });
      return true;
    }
    const title = heading();
    if (title) {
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
    }
    return false;
  };

  let stopped = false;
  let observer: MutationObserver | undefined;
  let timer: number | undefined;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    observer?.disconnect();
    window.clearTimeout(timer);
    root.removeEventListener("focusin", moved);
  };
  // The person moving the cursor to a control (not the dialog or its heading) ends the wait.
  const moved = (e: FocusEvent) => {
    if (e.target !== root && e.target !== heading()) stop();
  };

  const frame = window.requestAnimationFrame(() => {
    if (stopped) return;
    if (claimed()) {
      stop();
      return;
    }
    if (place()) {
      stop();
      return;
    }
    root.addEventListener("focusin", moved);
    observer = new MutationObserver(() => {
      if (stopped || claimed()) return;
      if (firstField(root)) {
        place();
        stop();
      }
    });
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "disabled"] });
    timer = window.setTimeout(stop, WAIT_MS);
  });
  return () => {
    window.cancelAnimationFrame(frame);
    stop();
  };
}

/** A ref for a dialog's element that starts the cursor in it when it appears (see `startCursor`). */
export function useCursorRef(titleId: string) {
  const stop = useRef<(() => void) | undefined>(undefined);
  return useCallback(
    (node: HTMLElement | null) => {
      stop.current?.();
      stop.current = node ? startCursor(node, titleId) : undefined;
    },
    [titleId],
  );
}
