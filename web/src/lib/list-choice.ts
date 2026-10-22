// Which row of a list | detail view is chosen (design 7.13): the row whose detail the pane shows. From 1024px, where the pane
// stands beside the list, the first row is chosen when the list opens (or the one `first` names), the choice follows the
// cursor as Up and Down move it, Enter on a row moves the cursor into its detail, and Escape closes the pane and puts the
// cursor back on the row. Below that the detail is a drawer, which opens only when the person asks for it. When the chosen
// row leaves the list (it was approved, sent, dismissed), the row that takes its place is chosen, or none if the list is empty.
import { useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent } from "react";

const INTERACTIVE = "a, button, input, select, textarea, label, [role='menuitem'], [role='dialog']";

/** The list row of a key, if it is on screen. */
export function choiceRow(key: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-choice]")).find((el) => el.dataset.choice === key);
}

export interface ListChoice {
  chosen: string | null;
  choose: (key: string) => void;
  close: () => void;
  /** The attributes of a list row: the cursor stops on it, a click chooses it, Enter moves into its detail. */
  rowProps: (key: string) => {
    "data-row": string;
    "data-choice": string;
    "aria-current": "true" | undefined;
    tabIndex: number;
    onClick: (event: MouseEvent<HTMLElement>) => void;
    onFocus: (event: FocusEvent<HTMLElement>) => void;
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  };
  /** Chooses the row and moves the cursor into its detail (Enter on the row). */
  enter: (key: string) => void;
}

/** `keys` are the rows now listed, in order. `first` is the row to choose when the list opens (the first by default).
 * `reset` changes when the list becomes another list (a filter, a grouping): the choice starts over. */
export function useListChoice(args: { keys: string[]; beside: boolean; first?: string | null; reset?: string }): ListChoice {
  const { keys, beside, reset } = args;
  const [chosen, setChosen] = useState<string | null>(null);
  const [back, setBack] = useState<{ key: string; n: number } | null>(null);
  const [into, setInto] = useState(0);
  // Whether the person (or a link) has chosen or closed anything since the list began; until then the first row is chosen.
  const touched = useRef(false);
  const lastIndex = useRef(0);
  const chosenNow = useRef<string | null>(null);
  chosenNow.current = chosen;
  const first = args.first && keys.includes(args.first) ? args.first : (keys[0] ?? null);

  useEffect(() => {
    touched.current = false;
    setChosen(null);
  }, [reset]);

  useEffect(() => {
    if (beside && !touched.current && chosen === null && first !== null) {
      touched.current = true;
      setChosen(first);
    }
  }, [beside, chosen, first]);

  // The chosen row left the list: its neighbor is chosen in its place (beside the list), or the detail closes.
  useEffect(() => {
    if (chosen === null) return;
    const at = keys.indexOf(chosen);
    if (at >= 0) {
      lastIndex.current = at;
      return;
    }
    // A list left with nothing in it starts over: what arrives next is chosen as the first.
    if (keys.length === 0) touched.current = false;
    setChosen(beside && keys.length > 0 ? keys[Math.min(lastIndex.current, keys.length - 1)] : null);
  }, [chosen, keys, beside]);

  const choose = useCallback((key: string) => {
    touched.current = true;
    setChosen(key);
  }, []);
  const close = useCallback(() => {
    touched.current = true;
    const was = chosenNow.current;
    if (was !== null) setBack((b) => ({ key: was, n: (b?.n ?? 0) + 1 }));
    setChosen(null);
  }, []);
  const enter = useCallback((key: string) => {
    touched.current = true;
    setChosen(key);
    setInto((n) => n + 1);
  }, []);

  // The cursor goes back to the row whose detail was closed, once the pane (or drawer) has gone.
  useEffect(() => {
    if (!back) return;
    const row = choiceRow(back.key);
    row?.focus({ preventScroll: true });
    // A drawer gives focus back to where it was opened from as it closes; the row has the last word.
    const frame = window.requestAnimationFrame(() => {
      if (row && document.activeElement !== row) row.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [back]);

  // Enter moves the cursor into the pane's detail, where its keys and buttons are.
  useEffect(() => {
    if (!into) return;
    const target = document.querySelector<HTMLElement>("[data-detail-pane] [data-row]") ?? document.querySelector<HTMLElement>("[data-detail-pane] button");
    target?.focus({ preventScroll: true });
  }, [into]);

  const rowProps = useCallback<ListChoice["rowProps"]>(
    (key) => ({
      "data-row": "",
      "data-choice": key,
      "aria-current": chosen === key ? "true" : undefined,
      tabIndex: -1,
      onClick: (event) => {
        if ((event.target as HTMLElement).closest(INTERACTIVE)) return;
        choose(key);
      },
      // The cursor arriving on the row itself (Up and Down) moves the choice with it while a pane stands beside the list.
      onFocus: (event) => {
        if (event.target === event.currentTarget && beside && chosen !== null && chosen !== key) choose(key);
      },
      onKeyDown: (event) => {
        if (event.key === "Escape" && !event.defaultPrevented && event.target === event.currentTarget && chosen !== null) {
          event.stopPropagation();
          close();
        }
      },
    }),
    [chosen, beside, choose, close],
  );
  return useMemo(() => ({ chosen, choose, close, rowProps, enter }), [chosen, choose, close, rowProps, enter]);
}
