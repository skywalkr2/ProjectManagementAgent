// The Personal / business filter on Today and Follow-ups (design 6.32): shown only to a person who has set a business, and
// remembered on this browser as the theme is. Lines and rows carry the side their project is on; one on neither side (the
// app's own lines, a row filed under no project) shows under every choice.
import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { api } from "./api";
import { useWords } from "./wording";

export type Side = "personal" | "business";
export type SideChoice = "all" | Side;

const KEY = "cockpit:side-filter";
const isChoice = (v: unknown): v is SideChoice => v === "all" || v === "personal" || v === "business";

// What was picked when this browser won't keep it: it then lasts until the page is closed.
let session: SideChoice = "all";
const listeners = new Set<() => void>();

function stored(): SideChoice {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (isChoice(saved)) return saved;
  } catch {
    // Storage can be blocked.
  }
  return session;
}

/** Remembers the pick on this browser and tells every screen that shows it. */
export function setSideChoice(choice: SideChoice): void {
  session = choice;
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {
    // Storage can be blocked; the pick then lasts until the page is closed.
  }
  for (const listener of listeners) listener();
}

function useStoredChoice(): SideChoice {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    stored,
  );
}

/** Whether a line or row shows under a choice: everything under "all", and what is on that side or on none. */
export const onSide = (side: Side | null | undefined, choice: SideChoice): boolean => choice === "all" || !side || side === choice;

export interface SideFilter {
  /** Whether the person has a business, so the filter is offered at all. */
  offered: boolean;
  /** The business's name, for its option. */
  business: string | null;
  /** The pick in force: always "all" while there is no business, whatever was remembered. */
  choice: SideChoice;
  /** The pick in the person's words ("Personal", or the business's name); empty for "all". */
  named: string;
  set: (choice: SideChoice) => void;
}

/** The filter's state: whether it is offered, what is picked and what the pick is called. */
export function useSideFilter(): SideFilter {
  const { t } = useWords();
  const state = useQuery({ queryKey: ["business"], queryFn: api.business });
  const picked = useStoredChoice();
  const offered = state.data?.business === true;
  const business = offered ? (state.data?.name ?? null) : null;
  const choice = offered ? picked : "all";
  const named = choice === "personal" ? t("sides.filter.personal") : choice === "business" ? (business ?? "") : "";
  return { offered, business, choice, named, set: setSideChoice };
}
