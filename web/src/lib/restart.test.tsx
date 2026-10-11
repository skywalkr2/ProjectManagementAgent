import "@testing-library/jest-dom/vitest";
import { act, render, screen } from "@testing-library/react";
import { WordingProvider } from "./wording";
import { RestartNotice, RestartProvider, useRestart } from "./restart";

function Starter() {
  const { begin } = useRestart();
  return (
    <button type="button" onClick={begin}>
      begin
    </button>
  );
}

function tree(hellos: number, seconds?: number) {
  return (
    <WordingProvider>
      <RestartProvider hellos={hellos} seconds={seconds}>
        <Starter />
        <RestartNotice />
      </RestartProvider>
    </WordingProvider>
  );
}

const SAYS = "Restarting to use the new settings…";

test("the live region is always there, and says nothing until a restart begins", () => {
  render(tree(1));
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

test("the notice stays until the event stream says hello again", () => {
  const { rerender } = render(tree(1));
  act(() => screen.getByRole("button", { name: "begin" }).click());
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  rerender(tree(1));
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  rerender(tree(2));
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

test("it gives up after a while when no restart came", () => {
  vi.useFakeTimers();
  render(tree(1, 5));
  act(() => screen.getByRole("button", { name: "begin" }).click());
  expect(screen.getByRole("status")).toHaveTextContent(SAYS);
  act(() => {
    vi.advanceTimersByTime(5001);
  });
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
  vi.useRealTimers();
});
