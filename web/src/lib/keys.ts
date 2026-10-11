// Keyboard shortcuts for the review loop. Keys come from config/ui.yaml; they never fire while typing.
//
// Rows are elements marked data-row. The current row is the one holding focus; j/k move it. Other keys are sent to
// the current row as a "rowkey" event, which the row (or the row around it) handles.
import { useEffect } from "react";

export type RowKey = "primary" | "send_back" | "copy" | "edit" | "toggle";
export const ROW_EVENT = "rowkey";

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-row]"));
}

function currentRow(): HTMLElement | null {
  const active = document.activeElement;
  return active instanceof HTMLElement ? active.closest<HTMLElement>("[data-row]") : null;
}

function move(step: number): void {
  const all = rows();
  if (!all.length) return;
  const here = currentRow();
  const index = here ? all.indexOf(here) : -1;
  const target = all[Math.max(0, Math.min(all.length - 1, index + step))];
  target.focus();
}

export function sendRowKey(key: RowKey): boolean {
  const row = currentRow();
  if (!row) return false;
  const unhandled = row.dispatchEvent(new CustomEvent(ROW_EVENT, { detail: key, bubbles: true, cancelable: true }));
  if (unhandled) {
    // A row without its own handler: press its marked button for this key, if it has one.
    row.querySelector<HTMLButtonElement>(`[data-key="${key}"]:not(:disabled)`)?.click();
  }
  return true;
}

export interface GlobalHandlers {
  undo: () => void;
  hand_in: () => void;
  ask: () => void;
  help: () => void;
}

export function useShortcuts(keys: Record<string, string>, handlers: GlobalHandlers): void {
  useEffect(() => {
    const byKey = new Map(Object.entries(keys).map(([action, key]) => [key, action]));
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return;
      if (document.querySelector("[data-modal-open]")) return;
      if (event.key === "Enter" && event.target instanceof HTMLElement && event.target.hasAttribute("data-row")) {
        event.preventDefault();
        sendRowKey("toggle");
        return;
      }
      const action = byKey.get(event.key);
      if (!action) return;
      switch (action) {
        case "next":
          move(1);
          break;
        case "previous":
          move(-1);
          break;
        case "primary":
        case "send_back":
        case "copy":
        case "edit":
          sendRowKey(action);
          break;
        case "undo":
          handlers.undo();
          break;
        case "hand_in":
          handlers.hand_in();
          break;
        case "ask":
          handlers.ask();
          break;
        case "help":
          handlers.help();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [keys, handlers]);
}

/** Let a row element handle keys sent to it. Return true from a handler when it handled the key. */
export function useRowKeys(
  ref: React.RefObject<HTMLElement | null>,
  handlers: Partial<Record<RowKey, () => void>>,
): void {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onRowKey = (event: Event) => {
      const key = (event as CustomEvent<RowKey>).detail;
      const handler = handlers[key];
      if (handler) {
        event.preventDefault();
        event.stopPropagation();
        handler();
      }
    };
    el.addEventListener(ROW_EVENT, onRowKey);
    return () => el.removeEventListener(ROW_EVENT, onRowKey);
  }, [ref, handlers]);
}
