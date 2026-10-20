// The words of the Today lines that ask a question about a held item or about what to check after something moved (design 7.6,
// 7.7). The title is the item as a question with the item named in quotes; the primary button names what it does, and the
// other answer is as specific, so nobody has to read the title again to know what they are agreeing to.
import type { S } from "./api";
import { day } from "./dates";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Tn = (key: string, n: number, vars?: Record<string, string | number>) => string;

const first = (name: string | null | undefined) => (name ?? "").trim().split(/\s+/)[0] ?? "";

/** The owners of an ending in the words of a line: their names in the owner format, or "someone" when none is named. */
export function endingWho(held: S["HeldAsk"], t: T): string {
  const owners = held.owners ?? [];
  return owners.length > 0 ? owners.join(", ") : t("queue.held.e.someone");
}

/** The day a move is to: the day when it is known, else the words the input used for it ("next Tuesday"), without the word
 * that joined them to the sentence ("by October 30" reads as "October 30" after "to"). */
function moveWhen(held: S["HeldAsk"], t: T): string {
  if (held.value) return day(held.value);
  const words = (held.due_words ?? "").replace(/^(by|on|before|until|for|at)\s+/i, "").trim();
  return words || t("queue.held.e.new_date");
}

/** A held line's title: the item as a question, named in quotes (design 7.6). */
export function heldTitle(held: S["HeldAsk"], t: T): string {
  const item = held.item;
  switch (held.ask) {
    case "ending":
      return t("queue.held.e.ending", { who: endingWho(held, t), item });
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
    case "move":
      return t("queue.held.q.move", { item, when: moveWhen(held, t) });
    case "part":
      return t("queue.held.q.part", { item });
    default:
      return item;
  }
}

/** The two answers to a held line, each naming its result: the first applies the held change, the other leaves things as
 * they were. The line and the inspector use the same words. */
export function heldAnswers(held: S["HeldAsk"], t: T): { primary: string; other: string } {
  switch (held.ask) {
    case "ending":
      return { primary: t("queue.held.e.ending_done", { who: endingWho(held, t) }), other: t("queue.held.e.not_yet") };
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
    case "move":
      return { primary: t("queue.held.a.move"), other: held.from_value ? t("queue.held.k.date", { date: day(held.from_value) }) : t("queue.held.k.move") };
    case "part":
      return { primary: t("queue.held.a.part"), other: t("queue.held.k.part") };
    default:
      return { primary: t("queue.held.a.close"), other: t("queue.held.k.close") };
  }
}

/** What the line says under its question: the words it rests on, and who said them. Nothing else; the rest is in the
 * inspector (design 7.6). */
export function heldMeta(held: S["HeldAsk"], t: T): string {
  return [held.quote ? t("queue.held.quote", { quote: held.quote }) : "", held.reporter ? t("queue.held.e.said_by", { name: held.reporter }) : ""].filter(Boolean).join(" · ");
}

/** Who a drop would leave out of the loop, in bold on the line's inspector where it leads: the names, then "were told on
 * Sat, Oct 10". Empty when nobody was told. */
export function heldTold(held: S["HeldAsk"], t: T): string {
  const told = held.told ?? [];
  if (held.ask !== "drop" || told.length === 0) return "";
  return held.told_on ? t("queue.held.told_on", { names: told.join(", "), date: day(held.told_on) }) : t("queue.held.told", { names: told.join(", ") });
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

/** An item's title by the title rule ("Email from <person> · <topic>"), the same words on Today and in What changed;
 * nothing when the item has none. With no topic the title says so, never a piece of the input's first sentence. Work the
 * app started is named by its kind of task and what it is about ("Filing notes · Launch reading"); `has` tells which
 * kinds of task the wording sheet names, and the others read as the assistant's work. */
export function titleWords(title: S["ItemTitle"] | null | undefined, t: T, has?: (key: string) => boolean): string {
  if (!title) return "";
  if (title.kind === "task") {
    const named = !title.task ? "" : has?.(`task.${title.task}`) === false ? t("task.other") : t(`task.${title.task}`);
    const head = named ? named.charAt(0).toUpperCase() + named.slice(1) : t("queue.title.task");
    const about = title.subject || title.topic;
    return about ? t("queue.title.with_topic", { head, topic: about }) : head;
  }
  const who = title.person_name ?? title.sender ?? t("queue.title.someone");
  const head = t(`queue.title.${title.kind}`, { who });
  // With no topic worth showing, the title is the kind and who it came from, never a cut-off sentence.
  return title.topic ? t("queue.title.with_topic", { head, topic: title.topic }) : head;
}
