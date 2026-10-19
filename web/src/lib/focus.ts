// Where the cursor goes when a form opens (design 7.0): in its first main field. A drawer takes focus itself as it opens, so
// the field is focused a frame later; a screen with no field puts the cursor on its heading instead.
import { useEffect, useRef } from "react";

/** A ref for a form's container: its first field has the cursor once the container is on screen. */
export function useFirstField<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() =>
      ref.current?.querySelector<HTMLElement>("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea")?.focus(),
    );
    return () => window.cancelAnimationFrame(frame);
  }, []);
  return ref;
}
