// Target sizes (design 7.11, WCAG 2.5.8; finding 3.8, check C52): an icon-only button is at least 32px square (24px is the floor),
// an inline text button is at least 24px tall, and a checkbox or radio has a hit area of at least 24px, by padding its label.
// Styles are not computed under jsdom, so these read the stylesheets; the browser check in e2e/a11y.spec.ts measures the result.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..");
const read = (file: string) => readFileSync(join(root, file), "utf8");
const rule = (css: string, selector: string): string => {
  const at = css.split("\n").find((line) => line.trimStart().startsWith(`${selector} {`) || line.trimStart().startsWith(`${selector}{`));
  return at ?? "";
};

test("the target tokens are 24px for the floor and 32px for an icon button", () => {
  const tokens = read("theme/tokens.css");
  expect(tokens).toMatch(/--target-min:\s*24px/);
  expect(tokens).toMatch(/--target-icon:\s*32px/);
});

test("an icon-only button is never narrower or shorter than the icon target, and a row can't squeeze it", () => {
  const css = read("ui/Button.module.css");
  const icon = rule(css, ".icon-only");
  expect(icon).toMatch(/min-width:\s*var\(--target-icon\)/);
  expect(icon).toMatch(/min-height:\s*var\(--target-icon\)/);
  expect(icon).toMatch(/flex:\s*none/);
  expect(rule(css, ".icon-only.sm")).toMatch(/min-width:\s*var\(--target-icon\)/);
});

test("every button is at least 24px each way, and so is an inline text button", () => {
  const css = read("styles.css");
  const buttons = css.split("\n").find((line) => /^button\b[^{]*\{/.test(line) && line.includes("min-height") && line.includes("--target-min")) ?? "";
  expect(buttons).toMatch(/min-width:\s*var\(--target-min\)/);
  expect(rule(css, ".link-button")).toMatch(/min-height:\s*var\(--target-min\)/);
});

test("a checkbox or radio has a hit area of at least 24px: its label is padded to that, and the box itself reaches out to it", () => {
  const css = read("styles.css");
  const label = css.split("\n").find((line) => line.includes('label:has(> input[type="checkbox"])')) ?? "";
  expect(label).toMatch(/min-height:\s*var\(--target-min\)/);
  expect(css).toMatch(/input\[type="checkbox"\]::before,\s*input\[type="radio"\]::before\s*\{[^}]*inset:\s*calc\(-1 \* var\(--space-1\)\)/);
});
