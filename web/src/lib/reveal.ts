// Pointing at a row on another part of the same screen: a Today line asks for the assistant's answer to be looked at,
// or a question to be answered, and the list that holds it opens that row. The list says it handled the request; when
// none does (its row isn't on this screen), the caller does something else.
import { useEffect, useRef } from "react";

export type Revealable = "changeset" | "question";
const EVENT = "reveal-row";

/** Ask whichever list holds this item to open it. True when one did. */
export function reveal(type: Revealable, id: string): boolean {
  const event = new CustomEvent(EVENT, { detail: { type, id }, cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

/** Answer requests for one kind of item: `handle` opens the row and returns true, or returns false when it has no such row. */
export function useReveal(type: Revealable, handle: (id: string) => boolean): void {
  const latest = useRef(handle);
  latest.current = handle;
  useEffect(() => {
    const onReveal = (event: Event) => {
      const detail = (event as CustomEvent<{ type: Revealable; id: string }>).detail;
      if (detail?.type === type && !event.defaultPrevented && latest.current(detail.id)) event.preventDefault();
    };
    window.addEventListener(EVENT, onReveal);
    return () => window.removeEventListener(EVENT, onReveal);
  }, [type]);
}

/** Bring a row into view and give it focus. */
export function showRow(row: HTMLElement | null, focusInside = false): void {
  if (!row) return;
  row.scrollIntoView?.({ block: "nearest" });
  const inner = focusInside ? row.querySelector<HTMLElement>("textarea, input, select, button") : null;
  (inner ?? row).focus();
}
