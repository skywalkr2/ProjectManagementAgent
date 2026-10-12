import { act, renderHook } from "@testing-library/react";
import { applyBrand, applyDensity, applyTheme, brandTokens, contrast, initAppearance, parseHex, setDensity, setTheme, useAppearance } from "./theme";

const root = () => document.documentElement;

afterEach(() => {
  root().removeAttribute("style");
  root().removeAttribute("data-theme");
  root().removeAttribute("data-density");
  window.localStorage.clear();
  vi.restoreAllMocks();
});

test("contrast follows the WCAG ratio", () => {
  expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
  expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  expect(contrast("#3446b5", "#ffffff")).toBeGreaterThan(7);
  // The order doesn't matter, and something that isn't a color has no contrast.
  expect(contrast("#ffffff", "#3446b5")).toBeCloseTo(contrast("#3446b5", "#ffffff"), 5);
  expect(contrast("nope", "#ffffff")).toBe(0);
});

test("only #rrggbb is a brand color", () => {
  expect(parseHex("#3446B5")).toEqual([52, 70, 181]);
  expect(parseHex("3446b5")).toBeNull();
  expect(parseHex("#fff")).toBeNull();
  expect(brandTokens("blue")).toBeNull();
});

test("the brand shades are derived from the color", () => {
  const tokens = brandTokens("#3446b5")!;
  expect(tokens["--brand-600"]).toBe("#3446b5");
  // Hover is darker; the soft tint is nearly white; the dark-mode shades are lighter and the deep tint is dark.
  expect(contrast(tokens["--brand-700"], "#ffffff")).toBeGreaterThan(contrast("#3446b5", "#ffffff"));
  expect(contrast(tokens["--brand-50"], "#ffffff")).toBeLessThan(1.3);
  expect(contrast(tokens["--brand-300"], "#171a20")).toBeGreaterThan(4.5);
  expect(contrast(tokens["--brand-200"], "#171a20")).toBeGreaterThan(contrast(tokens["--brand-300"], "#171a20"));
  expect(contrast(tokens["--brand-900"], "#ffffff")).toBeGreaterThan(10);
  // White text on this color is readable, so the text on the accent isn't touched.
  expect(tokens["--text-on-accent"]).toBeUndefined();
  for (const value of Object.values(tokens)) expect(value).toMatch(/^#[0-9a-f]{6}$/);
});

test("the link shade reads on the surface and on the soft tint, even for a pale brand color", () => {
  for (const color of ["#3446b5", "#2e7d32", "#c2185b", "#f2b65c", "#ffd54f"]) {
    const tokens = brandTokens(color)!;
    expect(contrast(tokens["--brand-650"], "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(tokens["--brand-650"], tokens["--brand-50"])).toBeGreaterThanOrEqual(4.5);
  }
});

test("white on a pale brand color is replaced by near-black", () => {
  const tokens = brandTokens("#f2b65c")!;
  expect(contrast("#ffffff", "#f2b65c")).toBeLessThan(4.5);
  expect(tokens["--text-on-accent"]).toBe("#14171f");
  expect(contrast(tokens["--text-on-accent"], "#f2b65c")).toBeGreaterThan(4.5);
});

test("applyBrand sets the primitives on the page and clears them again", () => {
  applyBrand("#2e7d32");
  expect(root().style.getPropertyValue("--brand-600")).toBe("#2e7d32");
  expect(root().style.getPropertyValue("--brand-700")).not.toBe("");
  applyBrand(null);
  expect(root().style.getPropertyValue("--brand-600")).toBe("");
  applyBrand("not a color");
  expect(root().style.getPropertyValue("--brand-600")).toBe("");
});

test("system theme has no attribute, and comfortable density has none either", () => {
  applyTheme("dark");
  expect(root()).toHaveAttribute("data-theme", "dark");
  applyTheme("system");
  expect(root()).not.toHaveAttribute("data-theme");
  applyDensity("compact");
  expect(root()).toHaveAttribute("data-density", "compact");
  applyDensity("comfortable");
  expect(root()).not.toHaveAttribute("data-density");
});

test("this device's choice wins over the workspace's, and the workspace's applies when there is none", () => {
  initAppearance({ brand_color: null, theme: "dark", density: "compact" });
  expect(root()).toHaveAttribute("data-theme", "dark");
  expect(root()).toHaveAttribute("data-density", "compact");
  window.localStorage.setItem("cockpit:theme", "light");
  window.localStorage.setItem("cockpit:density", "comfortable");
  initAppearance({ brand_color: null, theme: "dark", density: "compact" });
  expect(root()).toHaveAttribute("data-theme", "light");
  expect(root()).not.toHaveAttribute("data-density");
});

test("a saved value that isn't one of the choices is ignored", () => {
  window.localStorage.setItem("cockpit:theme", "neon");
  initAppearance({ brand_color: null, theme: "light", density: "comfortable" });
  expect(root()).toHaveAttribute("data-theme", "light");
});

test("choices are remembered on this device and reach whoever is watching", () => {
  initAppearance({ brand_color: null, theme: "system", density: "comfortable" });
  const { result } = renderHook(() => useAppearance());
  expect(result.current).toEqual({ theme: "system", density: "comfortable" });
  act(() => setTheme("dark"));
  act(() => setDensity("compact"));
  expect(result.current).toEqual({ theme: "dark", density: "compact" });
  expect(window.localStorage.getItem("cockpit:theme")).toBe("dark");
  expect(window.localStorage.getItem("cockpit:density")).toBe("compact");
  expect(root()).toHaveAttribute("data-theme", "dark");
});

test("blocked storage never breaks the page", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => initAppearance({ brand_color: null, theme: "light", density: "comfortable" })).not.toThrow();
  expect(root()).toHaveAttribute("data-theme", "light");
  expect(() => setTheme("dark")).not.toThrow();
  expect(root()).toHaveAttribute("data-theme", "dark");
});
