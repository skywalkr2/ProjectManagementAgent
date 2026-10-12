import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IconButton } from "./IconButton";
import { MenuButton, type MenuGroup } from "./MenuButton";

function menu(groups: MenuGroup[]) {
  render(<MenuButton groups={groups} trigger={<IconButton icon="more" label="Open the menu" tooltip={false} />} />);
}

test("a menu opens from its button and runs the chosen entry, then closes", async () => {
  const user = userEvent.setup();
  const run = vi.fn();
  menu([{ id: "a", entries: [{ id: "one", label: "First", run }, { id: "two", label: "Second" }] }]);
  await user.click(screen.getByRole("button", { name: "Open the menu" }));
  expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["First", "Second"]);
  await user.click(screen.getByRole("menuitem", { name: "First" }));
  expect(run).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
});

test("it opens and moves by keyboard, and Escape closes it with focus back on the button", async () => {
  const user = userEvent.setup();
  const run = vi.fn();
  menu([{ id: "a", entries: [{ id: "one", label: "First" }, { id: "two", label: "Second", run }] }]);
  const button = screen.getByRole("button", { name: "Open the menu" });
  button.focus();
  await user.keyboard("{Enter}");
  await user.keyboard("{ArrowDown}{Enter}");
  expect(run).toHaveBeenCalledTimes(1);
  await user.click(button);
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  await waitFor(() => expect(button).toHaveFocus());
});

test("a disabled entry says why, and does nothing", async () => {
  const user = userEvent.setup();
  const run = vi.fn();
  menu([{ id: "a", entries: [{ id: "one", label: "Undo", run, disabled: true, reason: "Nothing to undo yet." }] }]);
  await user.click(screen.getByRole("button", { name: "Open the menu" }));
  const item = screen.getByRole("menuitem", { name: /Undo/ });
  expect(item).toHaveAttribute("aria-disabled", "true");
  expect(item).toHaveAccessibleDescription("Nothing to undo yet.");
  await user.click(item);
  expect(run).not.toHaveBeenCalled();
});

test("groups are divided, a group that picks a value checks it, and a title names the group", async () => {
  const user = userEvent.setup();
  menu([
    { id: "a", entries: [{ id: "x", label: "Plain" }] },
    { id: "b", title: "Theme", selected: "dark", entries: [{ id: "light", label: "Light" }, { id: "dark", label: "Dark" }] },
  ]);
  await user.click(screen.getByRole("button", { name: "Open the menu" }));
  expect(screen.getByRole("separator")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
  expect(screen.getByRole("menuitemradio", { name: "Dark" })).toBeChecked();
  expect(screen.getByRole("menuitemradio", { name: "Light" })).not.toBeChecked();
});

test("a link entry opens its address in a new tab", async () => {
  const user = userEvent.setup();
  menu([{ id: "a", entries: [{ id: "doc", label: "Read the guide", href: "docs/guide" }] }]);
  await user.click(screen.getByRole("button", { name: "Open the menu" }));
  const item = screen.getByRole("menuitem", { name: "Read the guide" });
  expect(item).toHaveAttribute("href", "docs/guide");
  expect(item).toHaveAttribute("target", "_blank");
  expect(item).toHaveAttribute("rel", "noopener noreferrer");
});

test("with no entries there is no menu at all", () => {
  menu([{ id: "a", entries: [] }]);
  expect(screen.queryByRole("button")).toBeNull();
});
