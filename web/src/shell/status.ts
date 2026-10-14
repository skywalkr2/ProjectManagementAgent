// The status chip's one state (design 7.1): the worst thing going on, so the header says one word. In order: offline,
// work waiting for the network, a restart to finish, a backup needed, spend near a limit, otherwise live.
import type { S } from "../lib/api";
import type { LiveState } from "../lib/live";

export type StatusKind = "connecting" | "offline" | "network" | "restart" | "restarting" | "backup" | "spend" | "live";

export function worstState(input: {
  live: LiveState;
  status: S["Status"] | undefined;
  /** The restart notice's phase (lib/restart): asking, waiting, stuck, refused, done or idle. */
  restartPhase: string;
}): StatusKind {
  if (input.live === "offline") return "offline";
  if (input.status?.network_wait) return "network";
  if (input.restartPhase === "waiting") return "restarting";
  if (["asking", "stuck", "refused"].includes(input.restartPhase) || input.status?.restart_needed) return "restart";
  if (input.status?.backup.needs_attention) return "backup";
  if (input.status?.spend.warn) return "spend";
  if (input.live === "connecting") return "connecting";
  return "live";
}

/** What the assistant's own line says, worst first: a failing account or run (bad), then the states the chip knows that
 * hold work up (warn), otherwise fine. */
export type AliveKind = "fine" | "failing" | "run_failed" | "network" | "restarting" | "restart" | "paused" | "not_set_up";
export type AliveTone = "ok" | "warn" | "bad";

export function aliveState(input: { status: S["Status"]; restartPhase: string }): { kind: AliveKind; tone: AliveTone } {
  const { status } = input;
  if (status.ai.state === "failing") return { kind: "failing", tone: "bad" };
  if (status.assistant.last_run_failed) return { kind: "run_failed", tone: "bad" };
  if (status.network_wait) return { kind: "network", tone: "warn" };
  if (input.restartPhase === "waiting") return { kind: "restarting", tone: "warn" };
  if (["asking", "stuck", "refused"].includes(input.restartPhase) || status.restart_needed) return { kind: "restart", tone: "warn" };
  if (status.assistant.paused.length) return { kind: "paused", tone: "warn" };
  if (status.ai.state === "not_set_up") return { kind: "not_set_up", tone: "warn" };
  return { kind: "fine", tone: "ok" };
}

/** Everything but "live"and "connecting" is something the person may want to act on. */
export const isWarn = (kind: StatusKind): boolean => kind !== "live" && kind !== "connecting";

/** Up to two capital letters from a name, for a monogram or an avatar. */
export function initials(name: string): string {
  const words = name
    .trim()
    .split(/[\s·,-]+/)
    .filter((w) => /\p{L}/u.test(w));
  const letters = words.length > 1 ? [words[0], words[words.length - 1]] : words;
  return letters
    .map((w) => ([...w].find((c) => /\p{L}/u.test(c)) ?? "").toUpperCase())
    .join("")
    .slice(0, 2);
}
