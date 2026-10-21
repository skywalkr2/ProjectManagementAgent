// Focus that waits for the render that draws its target. A state change that shows an element (a form opening, a button
// coming back when a form closes) can't focus it on the next frame: on a slow machine that frame comes before the render,
// the element isn't there yet, and the focus is lost. This keeps the request until a render has drawn the element.
import { useEffect, useRef } from "react";

type Find = () => HTMLElement | null | undefined;

/** Returns `focusAfterRender(find)`: after the next render that makes `find()` return an element, that element is focused. */
export function useFocusAfterRender(): (find: Find) => void {
  const pending = useRef<Find | null>(null);
  useEffect(() => {
    const target = pending.current?.();
    if (!target) return;
    pending.current = null;
    target.focus();
  });
  return (find: Find) => {
    pending.current = find;
  };
}
