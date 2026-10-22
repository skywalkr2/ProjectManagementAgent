// The sweep shared by the view tests: what no screen of the app says, checked on the rendered page.
import { expect } from "vitest";

const ID = /\b[A-Z]{2,5}-\d+\b/;
const ISO_DATE = /\d{4}-\d{2}-\d{2}/;
const EMPTY_DOT = /·\s*·|·\s*$|^\s*·/m;

/** What no screen of the app says. `choices` are the stored words of choice fields, which a label stands in for. */
export function sweep(root: HTMLElement, choices: string[] = []) {
  const text = root.textContent ?? "";
  expect(text.match(ID)?.[0] ?? null, "an id of the app's own").toBeNull();
  expect(text.match(ISO_DATE)?.[0] ?? null, "a date as it is stored").toBeNull();
  for (const piece of root.querySelectorAll("li, .detail, .meta, .sub, dd, td, p")) {
    // Lines of text only: a piece that holds other pieces is looked at through them.
    if (piece.querySelector("li, .detail, .meta, .sub, dd, td, p")) continue;
    const own = (piece.textContent ?? "").trim();
    expect(own, `an empty separator in "${own}"`).not.toMatch(EMPTY_DOT);
    expect(choices, `a stored word on its own line: "${own}"`).not.toContain(own);
  }
}
