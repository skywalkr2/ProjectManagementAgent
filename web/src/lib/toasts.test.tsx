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
      <button type="button" onClick={() => push({ message: "Fixed", action: { label: "Start", run: () => undefined } })}>
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
  expect(within(region()).getByRole("button", { name: "Start" })).toBeInTheDocument();
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

function Same(props: { undo?: () => void; many?: (n: number) => string }) {
  const { push } = useToasts();
  return (
    <button type="button" onClick={() => push({ message: "Reviewed and filed.", undo: props.undo, many: props.many })}>
      same
    </button>
  );
}

test("the same message pushed again is one toast with a count, and its Undo takes back the newest one", async () => {
  const user = userEvent.setup();
  const undo = vi.fn();
  render(
    <ToastProvider seconds={0}>
      <Same undo={undo} many={(n) => `Filed ${n} reviews`} />
    </ToastProvider>,
  );
  for (let i = 0; i < 3; i++) await user.click(screen.getByRole("button", { name: "same" }));
  expect(within(region()).getAllByRole("button", { name: "Dismiss" })).toHaveLength(1);
  expect(within(region()).getByText("Filed 3 reviews")).toBeInTheDocument();
  await user.click(within(region()).getByRole("button", { name: "Undo last" }));
  expect(undo).toHaveBeenCalledTimes(1);
  expect(within(region()).getByText("Filed 2 reviews")).toBeInTheDocument();
});

test("a repeated message without its own wording says how many times", async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider seconds={0}>
      <Same />
    </ToastProvider>,
  );
  await user.click(screen.getByRole("button", { name: "same" }));
  await user.click(screen.getByRole("button", { name: "same" }));
  expect(within(region()).getByText("Reviewed and filed. (2 times)")).toBeInTheDocument();
});

test("reduced motion does not keep a toast longer: it goes after its time like any other", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined }));
  render(
    <ToastProvider seconds={2}>
      <Pusher />
    </ToastProvider>,
  );
  act(() => screen.getByRole("button", { name: "fixed" }).click());
  act(() => {
    vi.advanceTimersByTime(2100);
  });
  expect(within(region()).queryByText("Fixed")).toBeNull();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("a toast waits while the pointer or the cursor is on it, and goes once both have left", async () => {
  vi.useFakeTimers();
  render(
    <ToastProvider seconds={2}>
      <Pusher />
    </ToastProvider>,
  );
  act(() => screen.getByRole("button", { name: "fixed" }).click());
  const toast = within(region()).getByText("Fixed").parentElement!;
  act(() => {
    toast.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  });
  act(() => {
    vi.advanceTimersByTime(5000);
  });
  expect(within(region()).getByText("Fixed")).toBeInTheDocument();
  act(() => {
    toast.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
  });
  act(() => {
    vi.advanceTimersByTime(2100);
  });
  expect(within(region()).queryByText("Fixed")).toBeNull();
  vi.useRealTimers();
});

test("F6 moves the cursor to the newest toast, and Escape puts it away and gives the cursor back", async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider seconds={0}>
      <Pusher />
    </ToastProvider>,
  );
  const opener = screen.getByRole("button", { name: "fixed" });
  await user.click(opener);
  opener.focus();
  await user.keyboard("{F6}");
  expect(region().contains(document.activeElement)).toBe(true);
  await user.keyboard("{Escape}");
  expect(within(region()).queryByText("Fixed")).toBeNull();
  expect(opener).toHaveFocus();
});
