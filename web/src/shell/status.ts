// The status chip's one state (design 7.1): the worst thing going on, so the header says one word. In order: offline,
// a restart to finish, a backup needed, spend near a limit, otherwise live.
import type { S } from "../lib/api";
import type { LiveState } from "../lib/live";

export type StatusKind = "connecting" | "offline" | "restart" | "restarting" | "backup" | "spend" | "live";

export function worstState(input: {
  live: LiveState;
  status: S["Status"] | undefined;
  /** The restart notice's phase (lib/restart): asking, waiting, stuck, refused, done or idle. */
  restartPhase: string;
}): StatusKind {
  if (input.live === "offline") return "offline";
  if (input.restartPhase === "waiting") return "restarting";
  if (["asking", "stuck", "refused"].includes(input.restartPhase) || input.status?.restart_needed) return "restart";
  if (input.status?.backup.needs_attention) return "backup";
  if (input.status?.spend.warn) return "spend";
  if (input.live === "connecting") return "connecting";
  return "live";
}

/** Everything but "live" and "connecting" is something the person may want to act on. */
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
