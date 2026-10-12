import { act, renderHook } from "@testing-library/react";
import { useMediaQuery, useNarrow } from "./media";

function stubMedia() {
  const listeners = new Set<() => void>();
  const state = { matches: false };
  vi.stubGlobal("matchMedia", () => ({
    get matches() {
      return state.matches;
    },
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  }));
  return {
    set(matches: boolean) {
      state.matches = matches;
      for (const fn of listeners) fn();
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-narrow");
});

test("a media query is followed as the window changes", () => {
  const media = stubMedia();
  const { result } = renderHook(() => useMediaQuery("(min-width: 1280px)"));
  expect(result.current).toBe(false);
  act(() => media.set(true));
  expect(result.current).toBe(true);
});

test("without matchMedia a query simply doesn't match", () => {
  vi.stubGlobal("matchMedia", undefined);
  const { result } = renderHook(() => useMediaQuery("(min-width: 1280px)"));
  expect(result.current).toBe(false);
});

test("below the configured width the page is marked narrow, and the mark follows the window", () => {
  const media = stubMedia();
  const { result } = renderHook(() => useNarrow(640));
  expect(result.current).toBe(false);
  expect(document.documentElement).not.toHaveAttribute("data-narrow");
  act(() => media.set(true));
  expect(result.current).toBe(true);
  expect(document.documentElement).toHaveAttribute("data-narrow");
});
