// What was settled of a move's questions in this session (design 7.7). The questions after one move are one group on Today;
// as each is answered it leaves the group, and the group of the last two becomes an ordinary row. The toast for the last
// one is the move's, not a question's, so which move a question came after, and how many it had, is kept here.

const progress = new Map<string, { total: number; done: Set<string> }>();

/** The group for a move is on screen with `total` questions. Seen again, it keeps its first count. */
export function seeMove(request: string, total: number): void {
  if (total > 1 && !progress.has(request)) progress.set(request, { total, done: new Set() });
}

/** A question of the move was answered. True when it was the last of the group the person saw, which settles the move. */
export function settleMove(request: string, question: string): boolean {
  const found = progress.get(request);
  if (!found) return false;
  found.done.add(question);
  if (found.done.size < found.total) return false;
  progress.delete(request);
  return true;
}

/** Forget what was seen (a new session of the screen, or a test). */
export function forgetMoves(): void {
  progress.clear();
}
