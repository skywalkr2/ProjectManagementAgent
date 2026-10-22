// Where reminders reach the person when the app isn't open (design 6.12): the choices, the words for a standing yes that
// has gone stale, and the exact reminder as it will go. The words are the sheet's.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "./api";

export type ReminderWhere = S["ReminderWhereView"];
export type Where = ReminderWhere["where"];
type T = (key: string, vars?: Record<string, string | number>) => string;

export const useReminderWhere = () => useQuery({ queryKey: ["reminder-where"], queryFn: api.reminderWhere });

/** Where a reminder that needs an account goes, in the words the line uses ("your calendar", "your mail"). */
export const whereWords = (form: "calendar" | "mail", t: T): string => t(`reminders.where.line.${form}`);

/** What changed since the person said yes, in words, from the reasons the engine gives. */
export function changeWords(reasons: string[], t: T): string {
  const words = reasons.map((r) => t(`reminders.where.change.${r}`));
  return new Intl.ListFormat(undefined, { style: "long", type: "conjunction" }).format(words);
}

/** The line for Today when the yes (or the chosen account) can't work now, or null when nothing needs looking at. */
export function staleLine(view: ReminderWhere | undefined, t: T): string | null {
  const stale = view?.stale ?? [];
  if (!view || stale.length === 0) return null;
  const form = view.standing?.form ?? (view.where === "calendar" || view.where === "mail" ? view.where : null);
  if (!form) return null;
  return t("reminders.where.stale", { where: whereWords(form, t), changed: changeWords(stale, t) });
}
