import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Drawer } from "./Drawer";

function Demo(props: { dirty?: boolean; onClosed?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open drawer
      </button>
      <Drawer
        open={open}
        title="Add a person"
        dirty={props.dirty}
        onClose={() => {
          setOpen(false);
          props.onClosed?.();
        }}
        footer={<button type="button">Save</button>}
      >
        <label>
          Name
          <input />
        </label>
      </Drawer>
    </>
  );
}

test("a drawer opens from its button, shows its footer, and Esc closes it with focus back on the button", async () => {
  const user = userEvent.setup();
  const onClosed = vi.fn();
  render(<Demo onClosed={onClosed} />);
  const opener = screen.getByRole("button", { name: "Open drawer" });
  await user.click(opener);
  const dialog = await screen.findByRole("dialog", { name: "Add a person" });
  expect(dialog).toContainElement(screen.getByRole("button", { name: "Save" }));
  await user.keyboard("{Escape}");
  await waitFor(() => expect(dialog).not.toBeInTheDocument());
  expect(onClosed).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(opener).toHaveFocus());
});

test("with unsaved text, Esc asks first and Keep editing leaves the drawer open", async () => {
  const user = userEvent.setup();
  const onClosed = vi.fn();
  render(<Demo dirty onClosed={onClosed} />);
  await user.click(screen.getByRole("button", { name: "Open drawer" }));
  await screen.findByRole("dialog", { name: "Add a person" });
  await user.keyboard("{Escape}");
  expect(await screen.findByRole("alert")).toHaveTextContent("Discard");
  expect(onClosed).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(screen.getByRole("dialog", { name: "Add a person" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
});

test("with unsaved text, Discard closes it and returns focus to the opener", async () => {
  const user = userEvent.setup();
  const onClosed = vi.fn();
  render(<Demo dirty onClosed={onClosed} />);
  const opener = screen.getByRole("button", { name: "Open drawer" });
  await user.click(opener);
  await screen.findByRole("dialog", { name: "Add a person" });
  await user.keyboard("{Escape}");
  await user.click(await screen.findByRole("button", { name: "Discard" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(onClosed).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(opener).toHaveFocus());
});

test("the close button follows the same guard", async () => {
  const user = userEvent.setup();
  render(<Demo dirty />);
  await user.click(screen.getByRole("button", { name: "Open drawer" }));
  await screen.findByRole("dialog", { name: "Add a person" });
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

test("a drawer opened over another is named by its own title", async () => {
  const user = userEvent.setup();
  function Two() {
    const [inner, setInner] = useState(false);
    return (
      <Drawer open title="Add a project" onClose={() => undefined}>
        <button type="button" onClick={() => setInner(true)}>
          Add an owner
        </button>
        {inner && (
          <Drawer open title="Add a person" onClose={() => setInner(false)}>
            <input aria-label="Full name" />
          </Drawer>
        )}
      </Drawer>
    );
  }
  render(<Two />);
  await user.click(screen.getByRole("button", { name: "Add an owner" }));
  expect(await screen.findByRole("dialog", { name: "Add a person" })).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "Add a project", hidden: true })).toBeInTheDocument();
});

test("a drawer opens with the cursor in its first field, or on its heading when it has none", async () => {
  const user = userEvent.setup();
  const { unmount } = render(<Demo />);
  await user.click(screen.getByRole("button", { name: "Open drawer" }));
  await waitFor(() => expect(screen.getByLabelText("Name")).toHaveFocus());
  unmount();
  render(
    <Drawer open title="What this means" onClose={() => undefined}>
      <p>Words only.</p>
      <button type="button">Got it</button>
    </Drawer>,
  );
  await waitFor(() => expect(screen.getByRole("heading", { name: "What this means" })).toHaveFocus());
});
