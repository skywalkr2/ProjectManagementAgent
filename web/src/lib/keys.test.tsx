import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useShortcuts } from "./keys";

const SHORTCUTS = { undo: "u", hand_in: "n", help: "?", ask: "/" };

function Harness(props: { keys: Record<string, string>; ask: () => void }) {
  useShortcuts(props.keys, { undo: () => {}, hand_in: () => {}, help: () => {}, ask: props.ask });
  return <input aria-label="Typing" />;
}

test("the Ask key opens the box, and never while typing or with a dialog open", async () => {
  const user = userEvent.setup();
  const ask = vi.fn();
  render(<Harness keys={SHORTCUTS} ask={ask} />);
  await user.keyboard("/");
  expect(ask).toHaveBeenCalledTimes(1);
  await user.click(screen.getByLabelText("Typing"));
  await user.keyboard("/");
  expect(ask).toHaveBeenCalledTimes(1);
  await user.click(document.body);
  const dialog = document.createElement("div");
  dialog.setAttribute("data-modal-open", "");
  document.body.append(dialog);
  await user.keyboard("/");
  expect(ask).toHaveBeenCalledTimes(1);
  dialog.remove();
});

test("a configured key for Ask is used instead of the usual one", async () => {
  const user = userEvent.setup();
  const ask = vi.fn();
  render(<Harness keys={{ ...SHORTCUTS, ask: "g" }} ask={ask} />);
  await user.keyboard("/");
  expect(ask).not.toHaveBeenCalled();
  await user.keyboard("g");
  expect(ask).toHaveBeenCalledTimes(1);
});

test("on a row the arrow keys walk the rows as j and k do, and in a field they are left alone", async () => {
  const user = userEvent.setup();
  render(
    <>
      <Harness keys={{ ...SHORTCUTS, next: "j", previous: "k" }} ask={() => {}} />
      <div data-row="" tabIndex={-1} aria-label="first" />
      <div data-row="" tabIndex={-1} aria-label="second" />
    </>,
  );
  const [first, second] = [screen.getByLabelText("first"), screen.getByLabelText("second")];
  first.focus();
  await user.keyboard("{ArrowDown}");
  expect(second).toHaveFocus();
  await user.keyboard("{ArrowUp}");
  expect(first).toHaveFocus();
  // In a field, the arrow keys stay the field's.
  await user.click(screen.getByLabelText("Typing"));
  await user.keyboard("{ArrowDown}");
  expect(screen.getByLabelText("Typing")).toHaveFocus();
});

test("Shift+N runs the show-new action, and never while typing", async () => {
  const user = userEvent.setup();
  const show_new = vi.fn();
  function Probe() {
    useShortcuts({ ...SHORTCUTS, show_new: "N" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined, show_new });
    return <input aria-label="field" />;
  }
  render(<Probe />);
  await user.keyboard("{Shift>}N{/Shift}");
  expect(show_new).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("textbox"));
  await user.keyboard("{Shift>}N{/Shift}");
  expect(show_new).toHaveBeenCalledTimes(1);
});

test("the move key goes to the row that has the cursor, and only when it is configured", async () => {
  const user = userEvent.setup();
  const moved = vi.fn();
  function Row() {
    return (
      <div data-testid="row" data-row tabIndex={-1} onKeyDownCapture={undefined} ref={(el) => el?.addEventListener("rowkey", (e) => moved((e as CustomEvent).detail))}>
        a card
      </div>
    );
  }
  const { rerender } = render(
    <>
      <Harness keys={{ ...SHORTCUTS, move: "m" }} ask={() => {}} />
      <Row />
    </>,
  );
  screen.getByTestId("row").focus();
  await user.keyboard("m");
  expect(moved).toHaveBeenCalledWith("move");
  moved.mockClear();
  rerender(
    <>
      <Harness keys={SHORTCUTS} ask={() => {}} />
      <Row />
    </>,
  );
  screen.getByTestId("row").focus();
  await user.keyboard("m");
  expect(moved).not.toHaveBeenCalled();
});
