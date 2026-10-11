// Drafting an email for the person to send themselves: a mail link with the subject and body encoded, and the plain
// text to copy. The app sends nothing; the link only opens the person's own mail program.

/** The longest mail link offered. Longer links are cut off or refused by some browsers and mail programs. */
export const MAIL_LINK_MAX = 1800;

/** The text that goes on the clipboard: the subject, a blank line, then the body. */
export function mailText(subject: string, body: string): string {
  return `${subject}\n\n${body}`;
}

/** A mail link to the address with the subject and body filled in, or null when there is no address or the link
 * would be longer than the limit. Line breaks are written the way mail links define them. */
export function mailtoLink(to: string | null | undefined, subject: string, body: string): string | null {
  const address = (to ?? "").trim();
  if (!address) return null;
  const lines = (text: string) => encodeURIComponent(text.replace(/\r?\n/g, "\r\n"));
  const link = `mailto:${encodeURIComponent(address).replace(/%40/g, "@")}?subject=${lines(subject)}&body=${lines(body)}`;
  return link.length > MAIL_LINK_MAX ? null : link;
}

/** True when an address was given but its link is too long to offer: the person copies the message instead. */
export function tooLongForLink(to: string | null | undefined, subject: string, body: string): boolean {
  return !!(to ?? "").trim() && mailtoLink(to, subject, body) === null;
}
