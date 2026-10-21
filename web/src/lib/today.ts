// What Today's queue holds, counted and grouped in one place so the heading, the menu's count and the rows agree
// (design 7.7): the lines the engine ranks, the lines running plugins add, and the stage tasks waiting for a go. A line
// folded away (the week) is not counted.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "./api";
import { onSide, type SideChoice } from "./sides";
import { useStageToday } from "../components/StageToday";

export type QueueLine = S["QueueLineView"];
export type QueueGroupName = QueueLine["group"];

/** The groups in the order the engine ranks them (6.15); the screen never ranks. */
export const GROUPS: readonly QueueGroupName[] = ["decide", "risk", "review", "send"];

/** The kinds of line whose words are a count ("3 things need you"): with a count of zero there is nothing to say, so the
 * line is not shown. */
const COUNTED: ReadonlySet<QueueLine["kind"]> = new Set([
  "first_go",
  "catch_up_go",
  "intake_go",
  "intake_review",
  "restart",
  "paused",
  "borrow",
  "offline",
  "overdue",
  "review",
  "learned",
  "catch_up",
  "send",
  "nudge",
  "stale",
  "unfiled",
  "moved",
  "since_yesterday",
  "away",
]);

/** Whether a line has something to count: a line that counts things and holds none is left out. */
export const hasSomething = (line: QueueLine): boolean => !COUNTED.has(line.kind) || line.count > 0;

/** The queue's lines; with a side picked, only that side's and the lines that belong to neither (the app's own). */
export function useQueue(side: SideChoice = "all") {
  return useQuery({
    queryKey: ["today", "queue"],
    queryFn: api.todayQueue,
    select: (lines) => lines.filter((line) => hasSomething(line) && onSide(line.side, side)),
  });
}

/** How many lines need the person: the queue's, the plugins' and the stages'. Null until the queue has answered, so the
 * menu shows no number rather than a wrong one. */
export function useTodayCount(side: SideChoice = "all"): number | null {
  const queue = useQueue(side);
  const plugins = useQuery({ queryKey: ["plugin-today"], queryFn: api.pluginToday });
  const stage = useStageToday();
  if (!queue.data) return null;
  return queue.data.length + (plugins.data?.length ?? 0) + stage.count;
}

/** The lines of one group, in the engine's order. */
export function inGroup(lines: QueueLine[], group: QueueGroupName): QueueLine[] {
  return lines.filter((line) => line.group === group);
}

/** Whether the lines name more than one project, which is when a row names its own. */
export function mixesProjects(lines: QueueLine[]): boolean {
  return new Set(lines.map((line) => line.project).filter(Boolean)).size > 1;
}

// The line the inspector showed last, for the rest of the session: returning to Today (or a live refresh) opens the same
// line, and when it is gone, the line now in its place.
let remembered: { key: string; index: number } | null = null;

export function rememberLine(key: string, index: number): void {
  remembered = { key, index };
}

export function recallLine(): { key: string; index: number } | null {
  return remembered;
}

/** Forgets the remembered line, so the inspector starts on the first one. */
export function forgetLine(): void {
  remembered = null;
}
