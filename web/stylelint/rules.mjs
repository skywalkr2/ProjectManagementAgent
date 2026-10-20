// Local stylelint rules for the design tokens (design 7.11, 7.12).
//
// cockpit/token-values: font sizes, gaps, paddings, margins and radii come from the token scale (a var(--…)), or are 0, auto,
//   inherit, initial, unset or a percentage. Inside calc(), min(), max() and clamp() the same holds, and a bare multiplier is fine.
// cockpit/no-opacity-when-disabled: a rule that styles a disabled state never uses opacity; a disabled control gets the
//   sunken fill, the subtle text color and a border instead.
// cockpit/weight-tokens: a font weight is one of the weight tokens (var(--weight-regular), -medium or -semibold, with no
//   fallback number), or inherit, initial, unset or revert. No number, no bold or normal, in font-weight or in the font shorthand.
import stylelint from "stylelint";
import valueParser from "postcss-value-parser";

const { createPlugin, utils } = stylelint;

const TOKEN_PROPERTIES =
  /^(font-size|gap|row-gap|column-gap|grid-gap|padding(-[a-z]+)*|margin(-[a-z]+)*|border-radius|border-(top|bottom|start|end)-(left|right|start|end)-radius)$/;
const KEYWORDS = new Set(["0", "auto", "inherit", "initial", "unset"]);
const MATH = new Set(["calc", "min", "max", "clamp"]);

/** The first part of a value that is not from the scale, or null when every part is. */
function offender(nodes, insideMath) {
  for (const node of nodes) {
    if (node.type === "word") {
      const text = node.value;
      if (KEYWORDS.has(text.toLowerCase())) continue;
      if (/^-?\d*\.?\d+%$/.test(text)) continue;
      if (insideMath && (/^[+\-*/]$/.test(text) || /^-?\d*\.?\d+$/.test(text))) continue;
      return text;
    }
    if (node.type === "function") {
      const name = node.value.toLowerCase();
      if (name === "var" || name === "env") continue;
      if (MATH.has(name)) {
        const inner = offender(node.nodes, true);
        if (inner) return inner;
        continue;
      }
      return `${node.value}(…)`;
    }
  }
  return null;
}

const tokenValues = "cockpit/token-values";
const tokenMessages = utils.ruleMessages(tokenValues, {
  rejected: (prop, value) => `Use a token (var(--…)) for ${prop}, not "${value}"`,
});

const noOpacity = "cockpit/no-opacity-when-disabled";
const opacityMessages = utils.ruleMessages(noOpacity, {
  rejected: "A disabled state is shown by the sunken fill, subtle text and a border, never by opacity",
});

const weightTokens = "cockpit/weight-tokens";
const weightMessages = utils.ruleMessages(weightTokens, {
  rejected: (value) => `Use a weight token (var(--weight-regular), var(--weight-medium) or var(--weight-semibold)), not "${value}"`,
});
const WEIGHT_TOKEN = /^--weight-(regular|medium|semibold)$/;
const WEIGHT_KEYWORDS = new Set(["inherit", "initial", "unset", "revert"]);

/** The first weight in a value that is not a token, or null. In the font shorthand only a number or a bold word counts. */
function weightOffender(nodes, shorthand) {
  for (const node of nodes) {
    if (node.type === "function" && node.value.toLowerCase() === "var") {
      const names = node.nodes.filter((n) => n.type === "word");
      const hasFallback = node.nodes.some((n) => n.type === "div");
      const name = names[0]?.value ?? "";
      if (WEIGHT_TOKEN.test(name) && !hasFallback) continue;
      if (shorthand && !/weight|bold/i.test(name)) continue;
      return `var(${name}${hasFallback ? ", …" : ""})`;
    }
    if (node.type !== "word") {
      if (node.type === "function" && !shorthand) return `${node.value}(…)`;
      continue;
    }
    const text = node.value.toLowerCase();
    if (WEIGHT_KEYWORDS.has(text)) continue;
    if (shorthand) {
      if (/^(bold|bolder|lighter|[1-9]00)$/.test(text)) return node.value;
      continue;
    }
    return node.value;
  }
  return null;
}

const DISABLED = /:disabled|\[disabled|\[aria-disabled|\[data-disabled/;

export default [
  createPlugin(tokenValues, (enabled) => (root, result) => {
    if (!utils.validateOptions(result, tokenValues, { actual: enabled })) return;
    root.walkDecls((decl) => {
      if (!TOKEN_PROPERTIES.test(decl.prop)) return;
      const bad = offender(valueParser(decl.value).nodes, false);
      if (bad) utils.report({ ruleName: tokenValues, result, node: decl, message: tokenMessages.rejected(decl.prop, bad) });
    });
  }),
  createPlugin(weightTokens, (enabled) => (root, result) => {
    if (!utils.validateOptions(result, weightTokens, { actual: enabled })) return;
    root.walkDecls(/^(font-weight|font)$/i, (decl) => {
      const bad = weightOffender(valueParser(decl.value).nodes, decl.prop.toLowerCase() === "font");
      if (bad) utils.report({ ruleName: weightTokens, result, node: decl, message: weightMessages.rejected(bad) });
    });
  }),
  createPlugin(noOpacity, (enabled) => (root, result) => {
    if (!utils.validateOptions(result, noOpacity, { actual: enabled })) return;
    root.walkRules((rule) => {
      // ":not(:disabled)" styles the enabled state, so it is set aside before looking.
      const selector = rule.selector.replace(/:not\([^)]*\)/g, "");
      if (!DISABLED.test(selector)) return;
      rule.walkDecls("opacity", (decl) => {
        utils.report({ ruleName: noOpacity, result, node: decl, message: opacityMessages.rejected });
      });
    });
  }),
];
