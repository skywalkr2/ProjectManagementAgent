import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ASK_KEY, useShortcuts, withAskKey } from "./keys";

const SHORTCUTS = { undo: "u", hand_in: "n", help: "?" };

test("the Ask box has its usual key unless one is configured or the key is taken", () => {
  expect(withAskKey(SHORTCUTS)).toEqual({ ...SHORTCUTS, ask: ASK_KEY });
  expect(withAskKey({ ...SHORTCUTS, ask: "g" }).ask).toBe("g");
  expect(withAskKey({ ...SHORTCUTS, edit: ASK_KEY })).toEqual({ ...SHORTCUTS, edit: ASK_KEY });
});

function Harness(props: { keys: Record<string, string>; ask: () => void }) {
  useShortcuts(props.keys, { undo: () => {}, hand_in: () => {}, help: () => {}, ask: props.ask });
  return <input aria-label="Typing" />;
}

test("the Ask key opens the box, and never while typing or with a dialog open", async () => {
  const user = userEvent.setup();
  const ask = vi.fn();
  render(<Harness keys={withAskKey(SHORTCUTS)} ask={ask} />);
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
  render(<Harness keys={withAskKey({ ...SHORTCUTS, ask: "g" })} ask={ask} />);
  await user.keyboard("/");
  expect(ask).not.toHaveBeenCalled();
  await user.keyboard("g");
  expect(ask).toHaveBeenCalledTimes(1);
});
