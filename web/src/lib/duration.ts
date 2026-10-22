// A length of time in words from the wording sheet: "45 minutes", "2 hours", "1 hour 30 minutes".
type T = (key: string, vars?: Record<string, string | number>) => string;
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

export function durationWords(minutes: number, tn: Tn): string {
  const whole = Math.max(0, Math.round(minutes));
  const hours = Math.floor(whole / 60);
  const rest = whole % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(tn("time.hours", hours, { n: hours }));
  if (rest > 0 || hours === 0) parts.push(tn("time.minutes", rest, { n: rest }));
  return parts.join(" ");
}

/** The common sizes of a to-do, in minutes, for the pick list; any other length is typed. */
export const EFFORT_SIZES: readonly number[] = [15, 30, 45, 60, 90, 120, 180, 240, 480];

export type { T, Tn };
