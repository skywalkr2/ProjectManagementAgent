// The build's stylelint rules (design 7.11): raw colors only in the token file, spacing, sizes and radii from tokens,
// no uppercase, and no opacity on a disabled state.
import { join } from "node:path";
import stylelint from "stylelint";

const root = join(__dirname, "..", "..");

async function problems(code: string, codeFilename = "src/x.css"): Promise<string[]> {
  const result = await stylelint.lint({
    code,
    codeFilename: `${root}/${codeFilename}`,
    configFile: `${root}/.stylelintrc.json`,
    cwd: root,
  });
  return result.results.flatMap((r) => r.warnings.map((w) => w.rule));
}

test("tokens are fine, and so are zero, auto, inherit and percentages", async () => {
  expect(
    await problems(
      ".a { padding: 0 var(--space-3); margin: var(--space-1) auto; gap: calc(var(--space-1) * 2); font-size: var(--text-sm); border-radius: var(--radius-md); margin-block: 50%; padding-bottom: calc(var(--space-4) + env(safe-area-inset-bottom, 0px)); color: var(--text); background: transparent; border-color: currentcolor; border: 1px solid var(--border); }",
    ),
  ).toEqual([]);
});

test("raw colors are refused outside the token file and allowed in it", async () => {
  expect(await problems(".a { color: #fff; }")).toEqual(["color-no-hex"]);
  expect(await problems(".a { background: rgb(1 2 3); }")).toEqual(["function-disallowed-list"]);
  expect(await problems(".a { color: red; }")).toEqual(["color-named"]);
  expect(await problems(":root { --x: #fff; --y: rgb(0 0 0 / 0.5); }", "src/theme/tokens.css")).toEqual([]);
});

test("sizes, spacing and radii must come from tokens", async () => {
  expect(await problems(".a { font-size: 13px; }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { padding: 0 12px; }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { margin-left: 1rem; }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { gap: 8px 4px; }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { border-radius: 4px; }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { padding: calc(var(--x) + 3px); }")).toEqual(["cockpit/token-values"]);
  expect(await problems(".a { font-size: larger; }")).toEqual(["cockpit/token-values"]);
});

test("uppercase text is refused", async () => {
  expect(await problems(".a { text-transform: uppercase; }")).toEqual(["declaration-property-value-disallowed-list"]);
  expect(await problems(".a { text-transform: none; }")).toEqual([]);
});

test("a disabled state is never shown by opacity", async () => {
  expect(await problems(".a:disabled { opacity: 0.5; }")).toEqual(["cockpit/no-opacity-when-disabled"]);
  expect(await problems('.a[aria-disabled="true"] { opacity: 0.5; }')).toEqual(["cockpit/no-opacity-when-disabled"]);
  expect(await problems(".a[data-disabled] { opacity: 0.5; }")).toEqual(["cockpit/no-opacity-when-disabled"]);
  expect(await problems(".a[disabled] { opacity: 0.5; }")).toEqual(["cockpit/no-opacity-when-disabled"]);
  expect(await problems(".a:not(:disabled) { opacity: 0.5; }")).toEqual([]);
  expect(await problems(".a:hover { opacity: 0.5; }")).toEqual([]);
});

test("a font weight is one of the weight tokens, never a number or a word, and never with a fallback number", async () => {
  expect(await problems(".a { font-weight: var(--weight-regular); }")).toEqual([]);
  expect(await problems(".a { font-weight: var(--weight-medium); }")).toEqual([]);
  expect(await problems(".a { font-weight: var(--weight-semibold); }")).toEqual([]);
  expect(await problems(".a { font-weight: inherit; }")).toEqual([]);
  expect(await problems(".a { font-weight: 700; }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: 600; }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: bold; }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: bolder; }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: normal; }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: var(--weight-regular, 400); }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font-weight: var(--bold); }")).toEqual(["cockpit/weight-tokens"]);
});

test("the font shorthand can't carry a weight number or word either", async () => {
  expect(await problems(".a { font: inherit; }")).toEqual([]);
  expect(await problems(".a { font: var(--weight-semibold) var(--text-sm)/var(--lh-sm) var(--font-ui); }")).toEqual([]);
  expect(await problems(".a { font: 700 var(--text-sm) var(--font-ui); }")).toEqual(["cockpit/weight-tokens"]);
  expect(await problems(".a { font: bold var(--text-sm) var(--font-ui); }")).toEqual(["cockpit/weight-tokens"]);
});

test("the weight rule holds for the whole stylesheet set: no weight outside the tokens anywhere in src", async () => {
  const { globSync, readFileSync } = await import("node:fs");
  const files = globSync("src/**/*.css", { cwd: root }).filter((f: string) => f !== "src/theme/tokens.css");
  const found: string[] = [];
  for (const file of files) {
    const bad = (await problems(readFileSync(join(root, file), "utf8"), file)).filter((r) => r === "cockpit/weight-tokens");
    if (bad.length) found.push(file);
  }
  expect(found).toEqual([]);
});

test("the elements a browser makes bold by itself (700) take the semibold token in the base styles", async () => {
  const { readFileSync } = await import("node:fs");
  const base = readFileSync(join(root, "src/styles.css"), "utf8");
  const rule = base.match(/(^|\n)([^{}\n]*\bstrong\b[^{}\n]*)\{([^}]*)\}/);
  expect(rule?.[3]).toContain("font-weight: var(--weight-semibold)");
  for (const element of ["b", "th", "h6", "optgroup"]) expect(rule?.[2]).toMatch(new RegExp(`(^|[ ,])${element}([ ,]|$)`));
});
