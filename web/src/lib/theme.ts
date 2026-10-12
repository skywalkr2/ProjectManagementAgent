// Branding and appearance (design 7.12). The workspace's brand color becomes the brand primitives of the token file, with
// the hover, soft and dark-mode shades derived from it and the text on the accent switched to near-black when white
// would fall below 4.5:1. The theme and the density come from this device's choice, or else from the workspace.
import { useSyncExternalStore } from "react";
import type { S } from "./api";

export type Theme = "system" | "light" | "dark";
export type Density = "comfortable" | "compact";

type Rgb = [number, number, number];
type Oklch = { l: number; c: number; h: number };

// ---------------------------------------------------------------- Color math

/** `#rrggbb` as three 0-255 channels, or null when the text is not that. */
export function parseHex(text: string): Rgb | null {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(text.trim());
  if (!m) return null;
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

const hex2 = (n: number) => Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, "0");
export const toHex = ([r, g, b]: Rgb): string => `#${hex2(r)}${hex2(g)}${hex2(b)}`;

const toLinear = (v: number) => {
  const c = v / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const fromLinear = (c: number) => 255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/** WCAG relative luminance of a color. */
function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG contrast ratio of two `#rrggbb` colors (1 to 21); 0 when either is not a color. */
export function contrast(a: string, b: string): number {
  const x = parseHex(a);
  const y = parseHex(b);
  if (!x || !y) return 0;
  const [hi, lo] = [luminance(x), luminance(y)].sort((p, q) => q - p);
  return (hi + 0.05) / (lo + 0.05);
}

function toOklch(rgb: Rgb): Oklch {
  const [r, g, b] = rgb.map(toLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { l: L, c: Math.hypot(A, B), h: Math.atan2(B, A) };
}

/** The linear sRGB of an OKLCH color, which may lie outside 0..1 when the color is out of gamut. */
function linearOf({ l, c, h }: Oklch): Rgb {
  const A = c * Math.cos(h);
  const B = c * Math.sin(h);
  const l_ = (l + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m_ = (l - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s_ = (l - 0.0894841775 * A - 1.291485548 * B) ** 3;
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
}

/** An OKLCH color as sRGB, lowering its chroma until it fits the gamut so a lightened color keeps its hue. */
function fromOklch(color: Oklch): Rgb {
  const l = Math.min(1, Math.max(0, color.l));
  let c = color.c;
  for (let i = 0; i < 24; i++) {
    const lin = linearOf({ l, c, h: color.h });
    if (lin.every((v) => v >= -0.0005 && v <= 1.0005)) return lin.map((v) => fromLinear(Math.min(1, Math.max(0, v)))) as Rgb;
    c *= 0.9;
  }
  const grey = fromLinear(Math.min(1, Math.max(0, linearOf({ l, c: 0, h: 0 })[0])));
  return [grey, grey, grey];
}

const mix = (a: Rgb, b: Rgb, amount: number): Rgb => [0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * amount) as Rgb;
const WHITE: Rgb = [255, 255, 255];
const NEAR_BLACK = "#14171f";

/** The brand primitives for a color: the color itself (600), hover (700), the link shade (650), the light tint (50) and
 * the dark-mode shades (300, 200 and the deep tint 900); plus the text on the accent when white would not be readable. */
export function brandTokens(color: string): Record<string, string> | null {
  const rgb = parseHex(color);
  if (!rgb) return null;
  const base = toOklch(rgb);
  const darker = (factor: number) => toHex(fromOklch({ ...base, l: base.l * factor }));
  const tint = mix(WHITE, rgb, 0.08);
  // The link shade has to read on both the surface and the soft tint, so it darkens until it does.
  let link = darker(0.93);
  for (let f = 0.93; f > 0.2 && Math.min(contrast(link, "#ffffff"), contrast(link, toHex(tint))) < 4.5; f -= 0.04) {
    link = darker(f);
  }
  const lighter = Math.min(base.l + 0.35, 0.86);
  const calm = { ...base, c: base.c * 0.85 };
  const tokens: Record<string, string> = {
    "--brand-600": toHex(rgb),
    "--brand-700": darker(0.85),
    "--brand-650": link,
    "--brand-50": toHex(tint),
    "--brand-300": toHex(fromOklch({ ...calm, l: lighter })),
    "--brand-200": toHex(fromOklch({ ...calm, l: Math.min(lighter + 0.06, 0.92) })),
    "--brand-900": toHex(fromOklch({ l: 0.3, c: Math.min(base.c * 0.45, 0.09), h: base.h })),
  };
  if (contrast("#ffffff", toHex(rgb)) < 4.5) tokens["--text-on-accent"] = NEAR_BLACK;
  return tokens;
}

const BRAND_NAMES = ["--brand-600", "--brand-700", "--brand-650", "--brand-50", "--brand-300", "--brand-200", "--brand-900", "--text-on-accent"];

/** Sets the brand primitives on the page, or clears them when there is no (valid) brand color. */
export function applyBrand(color: string | null | undefined, root: HTMLElement = document.documentElement): void {
  for (const name of BRAND_NAMES) root.style.removeProperty(name);
  const tokens = color ? brandTokens(color) : null;
  if (!tokens) return;
  for (const [name, value] of Object.entries(tokens)) root.style.setProperty(name, value);
}

// ---------------------------------------------------------------- This device's choices

const THEME_KEY = "cockpit:theme";
const DENSITY_KEY = "cockpit:density";

const isTheme = (v: unknown): v is Theme => v === "system" || v === "light" || v === "dark";
const isDensity = (v: unknown): v is Density => v === "comfortable" || v === "compact";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be blocked; the choice then lasts until the page is closed.
  }
}

/** Sets or removes the page's `data-theme`; "system" leaves the choice to the operating system. */
export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Sets or removes the page's `data-density`; comfortable is the default and has no attribute. */
export function applyDensity(density: Density, root: HTMLElement = document.documentElement): void {
  if (density === "compact") root.setAttribute("data-density", "compact");
  else root.removeAttribute("data-density");
}

interface Appearance {
  theme: Theme;
  density: Density;
}

let current: Appearance = { theme: "system", density: "comfortable" };
const listeners = new Set<() => void>();

function publish(next: Appearance): void {
  current = next;
  for (const listener of listeners) listener();
}

/** Applies the brand color and the appearance at start-up: this device's choice first, then the workspace's. Call it
 * before the first render so the page never flashes the wrong theme. */
export function initAppearance(rc: Pick<S["RuntimeConfig"], "brand_color" | "theme" | "density">): Appearance {
  applyBrand(rc.brand_color);
  const savedTheme = read(THEME_KEY);
  const savedDensity = read(DENSITY_KEY);
  const theme = isTheme(savedTheme) ? savedTheme : isTheme(rc.theme) ? rc.theme : "system";
  const density = isDensity(savedDensity) ? savedDensity : isDensity(rc.density) ? rc.density : "comfortable";
  applyTheme(theme);
  applyDensity(density);
  publish({ theme, density });
  return current;
}

/** Remembers a theme for this device and applies it. */
export function setTheme(theme: Theme): void {
  write(THEME_KEY, theme);
  applyTheme(theme);
  publish({ ...current, theme });
}

/** Remembers a density for this device and applies it. */
export function setDensity(density: Density): void {
  write(DENSITY_KEY, density);
  applyDensity(density);
  publish({ ...current, density });
}

/** The theme and density now showing, updated when either changes. */
export function useAppearance(): Appearance {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
