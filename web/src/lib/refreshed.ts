// After a save was refused because what the form showed had changed meanwhile: which fields the person never touched
// take the saved value, which of those changed underneath them (so a second Save is an informed one), and which of the
// person's own are kept and marked.
import type { S } from "./api";
import { time } from "./dates";
import { formatValue, labelForKey, type Item } from "./settings";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Has = (key: string) => boolean;

/** One field that took the value saved now: what it is called, what it says now. */
export type Refreshed = { label: string; value: string };

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** The settings the person did not touch whose saved value is not the one the form was showing. */
export function refreshedSettings(before: Item[], after: Item[], touched: (key: string) => boolean, t: T, has: Has): Refreshed[] {
  const was = new Map(before.map((i) => [i.key, i.value]));
  return after
    .filter((i) => was.has(i.key) && !touched(i.key) && !same(was.get(i.key), i.value))
    .map((i) => ({ label: labelForKey(i.key, after, t, has), value: formatValue(i.value, t) }));
}

/** Whether a setting the person did touch has a different saved value now than when the form opened. */
export const changedUnderneath = (before: Item[], after: Item[], key: string): boolean =>
  !same(before.find((i) => i.key === key)?.value, after.find((i) => i.key === key)?.value);

/** The time the files changed, for the line: "9:14 AM", or empty when it is not known. */
export function changedTime(view: Pick<S["SettingsView"], "changed_at"> | undefined | null): string {
  const when = view?.changed_at ? new Date(view.changed_at) : null;
  return when && !Number.isNaN(when.getTime()) ? time(when) : "";
}

/** A form's own fields after a refusal: a field the person did not touch takes the value saved now (and is listed when
 * that is not what it showed), a field they changed is kept as typed (and is listed as kept when the saved value moved).
 * `opened` is what the form showed when it opened, `typed` what it holds, `now` what is saved now. */
export function reconcile<V>(
  opened: Record<string, V>,
  typed: Record<string, V>,
  now: Record<string, V>,
): { next: Record<string, V>; refreshed: string[]; kept: string[] } {
  const next: Record<string, V> = {};
  const refreshed: string[] = [];
  const kept: string[] = [];
  for (const key of new Set([...Object.keys(opened), ...Object.keys(typed), ...Object.keys(now)])) {
    const untouched = same(typed[key], opened[key]);
    if (untouched) {
      if (key in now) next[key] = now[key];
      if (!same(opened[key], now[key])) refreshed.push(key);
    } else {
      next[key] = typed[key];
      if (!same(opened[key], now[key])) kept.push(key);
    }
  }
  return { next, refreshed, kept };
}
