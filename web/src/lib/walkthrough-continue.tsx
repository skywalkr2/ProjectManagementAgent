// The walkthrough's one primary button (design 7.8): every screen ends with the same Continue. A screen that has something to
// save says so through `useContinue`: what Continue does (save, then move on), whether it can be pressed yet and, when it
// can't, why in words. A screen with nothing to save leaves Continue as a plain move to the next screen. Outside the
// walkthrough (the setup list) there is no slot, and a screen shows a button of its own.
import { createContext, useContext, useEffect, useRef } from "react";

export interface ContinueSpec {
  /** Saves what the screen holds. Returning false keeps the person on the screen (it has said why itself). */
  run: () => Promise<boolean | void>;
  /** The button's words when they aren't "Continue" (the backup screen's own verb). */
  label?: string;
  /** Continue can't be pressed yet. */
  disabled?: boolean;
  /** What is missing, said under the button while it is disabled. */
  why?: string;
}

export type ContinueSlot = (spec: ContinueSpec | null) => void;

const Slot = createContext<ContinueSlot | null>(null);
export const ContinueSlotProvider = Slot.Provider;

/** Whether the screen is inside the walkthrough, which then owns its Continue button. */
export function useHasContinueSlot(): boolean {
  return useContext(Slot) !== null;
}

/** Tells the walkthrough what its Continue does on this screen; cleared when the screen goes. Passing null leaves Continue
 * as a plain move on. */
export function useContinue(spec: ContinueSpec | null): void {
  const slot = useContext(Slot);
  const latest = useRef(spec);
  latest.current = spec;
  useEffect(() => {
    if (!slot) return;
    slot(latest.current);
  });
  useEffect(() => () => slot?.(null), [slot]);
}
