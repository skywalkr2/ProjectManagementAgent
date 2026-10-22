// Which messages to send this browser has shown (design 7.13): Copy on a line copies at once when the person has already
// seen that exact message, and shows it first when it is new or has changed. A message is known by who it is for and a
// hash of its exact text, so any change to the words makes it new again. This is a convenience of one browser, so every
// read and write copes with storage being blocked: the line then shows the message first, as it does for a new one.

const KEY = "seen-messages";
/** How many messages are remembered; the oldest are forgotten first. */
const KEEP = 300;

/** A short fingerprint of the exact text (FNV-1a over its UTF-16 units, with its length), enough to tell one message from another. */
export function messageHash(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${h.toString(16)}.${text.length}`;
}

const entry = (person: string, message: string) => `${person}:${messageHash(message)}`;

function read(): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** Whether this exact message to this person has been shown here before. */
export function hasSeenMessage(person: string, message: string): boolean {
  return message.trim() !== "" && read().includes(entry(person, message));
}

/** Remembers that this exact message to this person was shown. */
export function markMessageSeen(person: string, message: string): void {
  if (message.trim() === "") return;
  const key = entry(person, message);
  const seen = read();
  if (seen.at(-1) === key) return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify([...seen.filter((x) => x !== key), key].slice(-KEEP)));
  } catch {
    // Storage can be blocked; the message is then shown first each time.
  }
}
