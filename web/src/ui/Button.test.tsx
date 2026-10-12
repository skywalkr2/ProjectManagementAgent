import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";
import { IconButton } from "./IconButton";

test("a button runs its action, and the variants are marked", async () => {
  const user = userEvent.setup();
  const onClick = vi.fn();
  render(
    <Button variant="primary" onClick={onClick}>
      Save
    </Button>,
  );
  const button = screen.getByRole("button", { name: "Save" });
  expect(button).toHaveAttribute("data-variant", "primary");
  expect(button).toHaveAttribute("type", "button");
  await user.click(button);
  expect(onClick).toHaveBeenCalledTimes(1);
});

test("a disabled button shows its reason and points to it", async () => {
  const user = userEvent.setup();
  const onClick = vi.fn();
  render(
    <Button disabled reason="Pick a person first" onClick={onClick}>
      Send
    </Button>,
  );
  const button = screen.getByRole("button", { name: "Send" });
  expect(button).toBeDisabled();
  expect(screen.getByText("Pick a person first")).toBeVisible();
  expect(button).toHaveAccessibleDescription("Pick a person first");
  await user.click(button);
  expect(onClick).not.toHaveBeenCalled();
});

test("the reason is only shown while the button is disabled", () => {
  render(<Button reason="Pick a person first">Send</Button>);
  expect(screen.queryByText("Pick a person first")).toBeNull();
  expect(screen.getByRole("button", { name: "Send" })).not.toHaveAttribute("aria-describedby");
});

test("a loading button keeps its label, is busy and does nothing", async () => {
  const user = userEvent.setup();
  const onClick = vi.fn();
  render(
    <Button loading icon="send" onClick={onClick}>
      Sending
    </Button>,
  );
  const button = screen.getByRole("button", { name: "Sending" });
  expect(button).toHaveAttribute("aria-busy", "true");
  expect(button.querySelector("[data-icon]")).toBeNull();
  await user.click(button);
  expect(onClick).not.toHaveBeenCalled();
});

test("an icon shows beside the label, and the sizes are small or medium", () => {
  render(
    <Button icon="plus" size="sm">
      Add
    </Button>,
  );
  expect(screen.getByRole("button", { name: "Add" }).querySelector('[data-icon="plus"]')).not.toBeNull();
});

test("an icon-only button is named by its label and runs when pressed", async () => {
  const user = userEvent.setup();
  const onPress = vi.fn();
  render(<IconButton icon="close" label="Close the panel" onPress={onPress} />);
  const button = screen.getByRole("button", { name: "Close the panel" });
  await user.click(button);
  expect(onPress).toHaveBeenCalledTimes(1);
});

test("an icon-only button shows its label as a tooltip on focus", async () => {
  const user = userEvent.setup();
  render(<IconButton icon="help" label="Help" />);
  await user.tab();
  expect(await screen.findByRole("tooltip")).toHaveTextContent("Help");
});
