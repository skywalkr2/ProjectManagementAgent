import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ModalPanel, restoreFocus } from "./ModalPanel";

function Demo() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" id="opener" onClick={() => setOpen(true)}>
        Open
      </button>
      {open && (
        <ModalPanel
          titleId="t"
          onClose={() => {
            setOpen(false);
            restoreFocus(() => document.getElementById("opener"));
          }}
        >
          <h2 id="t">Short question</h2>
          <button type="button">Yes</button>
        </ModalPanel>
      )}
    </>
  );
}

test("a dialog is labelled by its heading, Esc closes it and focus returns to what opened it", async () => {
  const user = userEvent.setup();
  render(<Demo />);
  await user.click(screen.getByRole("button", { name: "Open" }));
  const dialog = await screen.findByRole("dialog", { name: "Short question" });
  expect(dialog.closest("[data-modal-open]")).not.toBeNull();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Open" })).toHaveFocus());
});

test("a dialog opens with the cursor in its first field, or on its heading when it has none", async () => {
  const { unmount } = render(
    <ModalPanel titleId="a" onClose={() => undefined}>
      <h2 id="a">Rename it</h2>
      <button type="button">Help</button>
      <label>
        New name
        <input />
      </label>
    </ModalPanel>,
  );
  await waitFor(() => expect(screen.getByLabelText("New name")).toHaveFocus());
  unmount();
  render(
    <ModalPanel titleId="b" onClose={() => undefined}>
      <h2 id="b">Short question</h2>
      <button type="button">Yes</button>
    </ModalPanel>,
  );
  await waitFor(() => expect(screen.getByRole("heading", { name: "Short question" })).toHaveFocus());
});
