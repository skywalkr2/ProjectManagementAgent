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
