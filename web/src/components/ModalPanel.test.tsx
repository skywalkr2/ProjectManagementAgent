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
