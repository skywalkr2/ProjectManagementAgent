import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SegmentedControl } from "./SegmentedControl";

function Demo(props: { onChange?: (v: string) => void }) {
  const [value, setValue] = useState("send");
  return (
    <SegmentedControl
      label="Show"
      value={value}
      onChange={(v) => {
        setValue(v);
        props.onChange?.(v);
      }}
      options={[
        { value: "send", label: "To send" },
        { value: "waiting", label: "Waiting on them" },
      ]}
    />
  );
}

test("one option is selected, and choosing another changes it", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<Demo onChange={onChange} />);
  const group = screen.getByRole("radiogroup", { name: "Show" });
  expect(group).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "To send" })).toBeChecked();
  await user.click(screen.getByRole("radio", { name: "Waiting on them" }));
  expect(onChange).toHaveBeenCalledWith("waiting");
  expect(screen.getByRole("radio", { name: "Waiting on them" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "To send" })).not.toBeChecked();
});

test("choosing the selected option again keeps it selected", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<Demo onChange={onChange} />);
  await user.click(screen.getByRole("radio", { name: "To send" }));
  expect(screen.getByRole("radio", { name: "To send" })).toBeChecked();
});

test("the arrow keys move between options and space chooses", async () => {
  const user = userEvent.setup();
  render(<Demo />);
  await user.tab();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("radio", { name: "Waiting on them" })).toHaveFocus();
  await user.keyboard(" ");
  expect(screen.getByRole("radio", { name: "Waiting on them" })).toBeChecked();
});
