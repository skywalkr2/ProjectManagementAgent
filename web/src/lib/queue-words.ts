// The words of the Today lines that ask a question about a held item or about what to check after something moved (design 7.6,
// 7.7). The title is the item as a question with the item named in quotes; the primary button names what it does, and the
// other answer is as specific, so nobody has to read the title again to know what they are agreeing to.
import type { S } from "./api";
import { day } from "./dates";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

const first = (name: string | null | undefined) => (name ?? "").trim().split(/\s+/)[0] ?? "";

/** An ending of an action read from an input: the line says what the input says happened, and the person keeps it, asks
 * for it later, or changes the action. Questions and every other hold keep their own words. */
export function isEnding(held: S["HeldAsk"]): boolean {
  return !!held.record && (held.ask === "close" || held.ask === "drop" || held.ask === "move" || held.ask === "part" || held.ask === "ending");
}

/** The owners of an ending in the words of a line: their names in the owner format, or "someone" when none is named. */
export function endingWho(held: S["HeldAsk"], t: T): string {
  const owners = held.owners ?? [];
  return owners.length > 0 ? owners.join(", ") : t("queue.held.e.someone");
}

function endingTitle(held: S["HeldAsk"], t: T): string {
  const item = held.item;
  const who = endingWho(held, t);
  switch (held.ask) {
    case "ending":
      return t("queue.held.e.ending", { who, item });
    case "drop":
      return t("queue.held.e.drop", { item });
    case "move":
      return t("queue.held.e.move", { item, when: held.due_words || (held.value ? day(held.value) : t("queue.held.e.new_date")) });
    case "part":
      return t("queue.held.e.part", { who, delivered: held.delivered ?? "", left: held.left ?? "" });
    default:
      return t("queue.held.e.close", { who, item });
  }
}

export function heldTitle(held: S["HeldAsk"], t: T): string {
  const item = held.item;
  if (isEnding(held)) return endingTitle(held, t);
  switch (held.ask) {
    case "close":
      return t("queue.held.q.close", { item });
    case "date":
      return t("queue.held.q.date", { item, date: held.value ? day(held.value) : "" });
    case "owner":
      return t("queue.held.q.owner", { item, name: held.to_name ?? "" });
    case "routing":
      return t("queue.held.q.routing", { item, name: held.to_name ?? "" });
    case "drop":
      return t("queue.held.q.drop", { item });
    default:
      return item;
  }
}

export function heldAnswers(held: S["HeldAsk"], t: T): { primary: string; other: string } {
  if (held.ask === "ending" && isEnding(held)) return { primary: t("queue.held.e.ending_done", { who: endingWho(held, t) }), other: t("queue.held.e.not_yet") };
  if (isEnding(held)) return { primary: t("queue.held.e.keep"), other: t("queue.held.e.not_yet") };
  switch (held.ask) {
    case "close":
      return { primary: t("queue.held.a.close"), other: t("queue.held.k.close") };
    case "date":
      return {
        primary: t("queue.held.a.date", { date: held.value ? day(held.value) : "" }),
        other: held.from_value ? t("queue.held.k.date", { date: day(held.from_value) }) : t("queue.held.k.same"),
      };
    case "owner":
      return {
        primary: t("queue.held.a.owner", { name: first(held.to_name) }),
        other: held.from_value ? t("queue.held.k.owner", { name: first(held.from_value) }) : t("queue.held.k.same"),
      };
    case "routing":
      return {
        primary: t("queue.held.a.routing", { name: first(held.to_name) }),
        other: held.from_value ? t("queue.held.k.routing", { name: first(held.from_value) }) : t("queue.held.k.same"),
      };
    case "drop":
      return { primary: t("queue.held.a.drop"), other: t("queue.held.k.drop") };
    default:
      return { primary: t("queue.held.e.keep"), other: t("queue.held.e.not_yet") };
  }
}

/** "Print sync moved to Thu, Oct 22 · 2 things to check": the move's own name and the day it moved to, "moved earlier" when
 * the day is before where it was, since earlier moves are the risky ones. */
export function moveTitle(line: S["QueueLineView"], t: T, tn: Tn): string {
  const after = line.after_move;
  const checks = tn("queue.moved.checks", line.count);
  if (!after) return checks;
  const head = after.replaced
    ? t("queue.moved.replaced", { title: after.title })
    : t(after.earlier ? "queue.moved.earlier" : "queue.moved", { title: after.title, date: after.to ? day(after.to) : "" });
  return `${head} · ${checks}`;
}

/** What a single question came after, for its meta line: "because Print sync moved to Thu, Oct 22". */
export function afterMove(line: S["QueueLineView"], t: T): string {
  const after = line.after_move;
  if (!after) return "";
  return after.replaced
    ? t("queue.moved.because_replaced", { title: after.title })
    : t("queue.moved.because", { title: after.title, date: after.to ? day(after.to) : "" });
}
