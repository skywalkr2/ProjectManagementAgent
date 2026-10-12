/** What the person typed where a key is kept, as the reference the server takes. A bare name is the name of a variable in
 * the app's environment; anything that already says where (a scheme and a colon) goes as it is. */
export function asReference(typed: string): string {
  const text = typed.trim();
  return text === "" || text.includes(":") ? text : `env:${text}`;
}
