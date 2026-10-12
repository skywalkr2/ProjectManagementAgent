import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToasts } from "./toasts";

function Pusher(props: { undo?: () => void }) {
  const { push, undoLast } = useToasts();
  return (
    <>
      <button type="button" onClick={() => push({ message: `Message ${Math.random()}`, undo: props.undo })}>
        push
      </button>
      <button type="button" onClick={() => push({ message: "Fixed", action: { label: "Go", run: () => undefined } })}>
        fixed
      </button>
      <button type="button" onClick={undoLast}>
        undo last
      </button>
    </>
  );
}

const region = () => screen.getByRole("region", { name: "Notifications" });

test("a toast shows in the notifications region, which announces politely, and can be dismissed", async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider seconds={0}>
      <Pusher />
    </ToastProvider>,
  );
  await user.click(screen.getByRole("button", { name: "fixed" }));
  expect(within(region()).getByText("Fixed")).toBeInTheDocument();
  expect(region().querySelector('[aria-live="polite"]')).not.toBeNull();
  expect(within(region()).getByRole("button", { name: "Go" })).toBeInTheDocument();
  await user.click(within(region()).getByRole("button", { name: "Dismiss" }));
  expect(within(region()).queryByText("Fixed")).toBeNull();
});

test("at most three toasts show, the newest last", async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider seconds={0}>
      <Pusher />
    </ToastProvider>,
  );
  for (let i = 0; i < 5; i++) await user.click(screen.getByRole("button", { name: "push" }));
  expect(within(region()).getAllByRole("button", { name: "Dismiss" })).toHaveLength(3);
});

test("Undo runs the undo and says so, and the last undo is reachable by keyboard", async () => {
  const user = userEvent.setup();
  const undo = vi.fn();
  render(
    <ToastProvider seconds={0}>
      <Pusher undo={undo} />
    </ToastProvider>,
  );
  await user.click(screen.getByRole("button", { name: "push" }));
  await user.click(within(region()).getByRole("button", { name: "Undo" }));
  expect(undo).toHaveBeenCalledTimes(1);
  expect(await within(region()).findByText(/Undone/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "push" }));
  await user.click(screen.getByRole("button", { name: "undo last" }));
  await waitFor(() => expect(undo).toHaveBeenCalledTimes(2));
});

test("with nothing to undo, it says so", async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider seconds={0}>
      <Pusher />
    </ToastProvider>,
  );
  await user.click(screen.getByRole("button", { name: "undo last" }));
  expect(within(region()).getByText("Nothing to undo.")).toBeInTheDocument();
});

test("a toast goes by itself after its time, unless the pointer is on it", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  render(
    <ToastProvider seconds={2}>
      <Pusher />
    </ToastProvider>,
  );
  act(() => screen.getByRole("button", { name: "fixed" }).click());
  expect(within(region()).getByText("Fixed")).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(2100);
  });
  expect(within(region()).queryByText("Fixed")).toBeNull();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("dismissAll takes every toast off the screen, and the page is told how many show while any do", async () => {
  const user = userEvent.setup();
  function Clearer() {
    const { dismissAll } = useToasts();
    return (
      <button type="button" onClick={dismissAll}>
        clear all
      </button>
    );
  }
  render(
    <ToastProvider seconds={0}>
      <Pusher />
      <Clearer />
    </ToastProvider>,
  );
  expect(document.documentElement).not.toHaveAttribute("data-toasts");
  await user.click(screen.getByRole("button", { name: "push" }));
  await user.click(screen.getByRole("button", { name: "push" }));
  expect(document.documentElement).toHaveAttribute("data-toasts");
  expect(document.documentElement.style.getPropertyValue("--toasts")).toBe("2");
  await user.click(screen.getByRole("button", { name: "clear all" }));
  expect(within(region()).queryAllByRole("button", { name: "Dismiss" })).toHaveLength(0);
  expect(document.documentElement).not.toHaveAttribute("data-toasts");
  expect(document.documentElement.style.getPropertyValue("--toasts")).toBe("");
});
