// A repeat said back in the person's words: the server reads the typed phrase into a shape (kind and values), and every
// word of the sentence comes from the wording sheet. Weekdays, months and ordinals arrive as English keys.
import { useEffect, useState } from "react";
import { api, type S } from "./api";
import { useWords } from "./wording";

type Say = (key: string, vars?: Record<string, string | number>) => string;
export type Shape = S["RepeatShapeView"];

const list = (t: Say, items: string[]): string =>
  items.length <= 1
    ? (items[0] ?? "")
    : items.length === 2
      ? t("repeat.join.two", { a: items[0], b: items[1] })
      : t("repeat.join.many", { rest: items.slice(0, -1).join(", "), last: items[items.length - 1] });

const suffixOf = (n: number): string => (n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th");

/** A day of the month with its ending, "1st": the ending is in the wording sheet. */
export const dayOfMonth = (t: Say, n: number): string => t("repeat.day", { n, suffix: t(`repeat.suffix.${suffixOf(n)}`) });

/** The sentence for a shape, without its start: "Every Monday and Thursday". */
export function saidShape(t: Say, shape: Shape): string {
  const every = (key: string, vars: Record<string, string | number>) => {
    const n = shape.interval ?? 1;
    return t(`repeat.said.${key}.${n === 1 ? "one" : n === 2 ? "two" : "other"}`, { n, ...vars });
  };
  const weekday = (name?: string | null) => t(`repeat.weekday.${name}`);
  const said = ((): string => {
    switch (shape.kind) {
      case "daily":
        return every("daily", {});
      case "weekdays":
        return t("repeat.said.weekdays");
      case "weekly":
        return every("weekly", { weekday: weekday(shape.weekday) });
      case "weekly_days":
        return every("weekly_days", { weekdays: list(t, (shape.weekdays ?? []).map(weekday)) });
      case "monthly_day":
        return every("monthly_day", { day: dayOfMonth(t, shape.day ?? 1) });
      case "monthly_days":
        return every("monthly_days", { days: list(t, (shape.days ?? []).map((d) => dayOfMonth(t, d))) });
      case "monthly_last_day":
        return every("monthly_last_day", {});
      case "monthly_nth":
        return t("repeat.said.monthly_nth", { ordinal: t(`repeat.ordinal.${shape.ordinal}`), weekday: weekday(shape.weekday) });
      case "monthly_nths":
        return t("repeat.said.monthly_nths", {
          ordinals: list(t, (shape.ordinals ?? []).map((o) => t(`repeat.ordinal.${o}`))),
          weekday: weekday(shape.weekday),
        });
      case "monthly_weekday":
        return t("repeat.said.monthly_weekday", { position: t(`repeat.ordinal.${shape.position}`) });
      case "yearly":
        return t("repeat.said.yearly", { month: t(`repeat.month.${shape.month}`), day: shape.day ?? 1 });
      default:
        return t("repeat.said.yearly_nth", {
          month: t(`repeat.month.${shape.month}`),
          ordinal: t(`repeat.ordinal.${shape.ordinal}`),
          weekday: weekday(shape.weekday),
        });
    }
  })();
  // A day past the 28th falls on a shorter month's last day: the sentence says so.
  const clamped = (shape.kind === "monthly_day" && (shape.day ?? 0) > 28) || (shape.kind === "yearly" && shape.month === "february" && shape.day === 29);
  return clamped ? t("repeat.clamped", { said }) : said;
}

const startFormat = new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric" });

/** The whole sentence: "Every Monday and Thursday, starting November 2". */
export function saidRepeat(t: Say, shape: Shape, start: string): string {
  const [y, m, d] = start.slice(0, 10).split("-").map(Number);
  return t("repeat.starting", { said: saidShape(t, shape), date: startFormat.format(new Date(y, m - 1, d)) });
}

/** What the words typed so far are read as, asked of the server once typing pauses; nothing while the words are empty. */
export function useRepeatCheck(phrase: string, start: string | null): S["RepeatCheckView"] | null {
  const [found, setFound] = useState<{ asked: string; view: S["RepeatCheckView"] } | null>(null);
  const words = phrase.trim();
  const key = `${words}|${start ?? ""}`;
  useEffect(() => {
    if (!words) return;
    let current = true;
    const timer = setTimeout(() => {
      api
        .checkRepeat({ phrase: words, ...(start ? { start } : {}) })
        .then((view) => current && setFound({ asked: key, view }))
        .catch(() => current && setFound(null));
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [words, start, key]);
  return words && found?.asked === key ? found.view : null;
}

/** The sentence for a stored repeat on a row or a page. */
export function useSaid() {
  const { t } = useWords();
  return (repeat: S["RepeatView"]) => saidRepeat(t, repeat.shape, repeat.start);
}
