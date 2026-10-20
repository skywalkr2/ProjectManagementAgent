// Copy (design 7.5): the one place the app puts text on the clipboard. A message goes as its formatted version and its plain
// text together, so mail and documents paste the formatting and chat pastes clean text; the formatted version is made from
// the very text on screen and escapes every piece of it, so what is pasted is what was shown. "Copy as plain text" puts the
// plain text alone. A browser with no rich clipboard gets the plain text, and a refusal is told to the caller, which selects
// the text for a copy by hand.

/** What reached the clipboard: formatted and plain together, the plain text alone, or nothing (the browser refused). */
export type CopyResult = "formatted" | "plain" | "blocked";

/** Text made safe to sit inside HTML: every character that could start a tag or end an attribute is written as an entity. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const ADDRESS = /https?:\/\/[^\s<>"']+/gi;
/** What may trail an address in running text without belonging to it. */
const TRAILING = /[.,;:!?)\]]+$/;

/** One line, escaped, with each web address a link. The address and the words of a link are both escaped; an address with
 * another scheme is plain text. */
function line(text: string): string {
  let out = "";
  let at = 0;
  for (const found of text.matchAll(ADDRESS)) {
    const start = found.index ?? 0;
    const trail = TRAILING.exec(found[0])?.[0] ?? "";
    const address = found[0].slice(0, found[0].length - trail.length);
    out += escapeHtml(text.slice(at, start));
    out += `<a href="${escapeHtml(address)}">${escapeHtml(address)}</a>${escapeHtml(trail)}`;
    at = start + found[0].length;
  }
  return out + escapeHtml(text.slice(at));
}

/** A message as HTML for mail and documents: a paragraph for each run of lines, a line break inside one, web addresses as
 * links. Nothing but those few tags is ever written; every piece of the text is escaped. */
export function messageHtml(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.replace(/^\n+|\n+$/g, ""))
    .filter((paragraph) => paragraph.trim() !== "")
    .map((paragraph) => `<p>${paragraph.split("\n").map(line).join("<br>")}</p>`)
    .join("");
}

async function writeText(text: string): Promise<CopyResult> {
  try {
    await navigator.clipboard.writeText(text);
    return "plain";
  } catch {
    return "blocked";
  }
}

/** Put `html` and `text` on the clipboard together, as one item with both kinds, so the place pasted into takes what it
 * understands. Falls back to the plain text when the browser cannot hold both or refuses to. */
export async function copyBoth(text: string, html: string): Promise<CopyResult> {
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        }),
      ]);
      return "formatted";
    } catch {
      // The browser refused the rich copy: the plain text still goes.
    }
  }
  return writeText(text);
}

/** Copy a message: formatted and plain together. */
export function copyMessage(text: string): Promise<CopyResult> {
  return copyBoth(text, messageHtml(text));
}

/** Copy as plain text: only the text, wherever it is pasted. Also what a secret or a command line is copied with. */
export function copyPlain(text: string): Promise<CopyResult> {
  return writeText(text);
}
