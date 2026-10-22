import { render } from "@testing-library/react";
import { vi } from "vitest";
import { fakeApi } from "../test-utils";
import { useReviewTime } from "./review-time";

function Screen(props: { on?: boolean }) {
  useReviewTime("changes", props.on);
  return <p>A screen</p>;
}

afterEach(() => {
  vi.useRealTimers();
});

function visibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

test("leaving a screen records the seconds it was open and in view, once", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-20T09:00:00Z"));
  const calls = fakeApi({ "POST quality/review-time": () => ({ seconds: 42 }) });
  const { unmount } = render(<Screen />);
  vi.setSystemTime(new Date("2026-10-20T09:00:42Z"));
  unmount();
  expect(calls.filter((c) => c.route === "POST quality/review-time").map((c) => c.body)).toEqual([{ screen: "changes", seconds: 42 }]);
});

test("time with the window out of view is not counted, and a visit of under a second says nothing", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-20T09:00:00Z"));
  const calls = fakeApi({ "POST quality/review-time": () => ({ seconds: 10 }) });
  const { unmount } = render(<Screen />);
  vi.setSystemTime(new Date("2026-10-20T09:00:10Z"));
  visibility("hidden");
  vi.setSystemTime(new Date("2026-10-20T09:30:10Z"));
  visibility("visible");
  vi.setSystemTime(new Date("2026-10-20T09:30:10.400Z"));
  unmount();
  expect(calls.filter((c) => c.route === "POST quality/review-time").map((c) => c.body)).toEqual([{ screen: "changes", seconds: 10 }]);
  const quick = fakeApi({ "POST quality/review-time": () => ({ seconds: 0 }) });
  const second = render(<Screen />);
  second.unmount();
  expect(quick.filter((c) => c.route === "POST quality/review-time")).toEqual([]);
});

test("a screen that is switched off counts nothing", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-20T09:00:00Z"));
  const calls = fakeApi({});
  const { unmount } = render(<Screen on={false} />);
  vi.setSystemTime(new Date("2026-10-20T09:05:00Z"));
  unmount();
  expect(calls).toEqual([]);
});
