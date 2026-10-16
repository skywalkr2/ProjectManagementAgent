// What Today's queue holds, counted and grouped in one place so the heading, the menu's count and the rows agree
// (design 7.7): the lines the engine ranks, the lines running plugins add, and the stage tasks waiting for a go. A line
// folded away (the week) is not counted.
import { useQuery } from "@tanstack/react-query";
import { api, type S } from "./api";
import { useStageToday } from "../components/StageToday";

export type QueueLine = S["QueueLineView"];
export type QueueGroupName = QueueLine["group"];

/** The groups in the order the engine ranks them (6.15); the screen never ranks. */
export const GROUPS: readonly QueueGroupName[] = ["decide", "risk", "review", "send"];

export function useQueue() {
  return useQuery({ queryKey: ["today", "queue"], queryFn: api.todayQueue });
}

/** How many lines need the person: the queue's, the plugins' and the stages'. Null until the queue has answered, so the
 * menu shows no number rather than a wrong one. */
export function useTodayCount(): number | null {
  const queue = useQueue();
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
