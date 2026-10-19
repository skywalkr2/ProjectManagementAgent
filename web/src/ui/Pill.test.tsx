import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { Pill } from "./Pill";
import { StatusChip } from "./StatusChip";

test("a pill is a word with a tone, neutral by default", () => {
  const { rerender } = render(<Pill>Review</Pill>);
  expect(screen.getByText("Review")).toHaveAttribute("data-tone", "neutral");
  for (const tone of ["need", "warn", "danger", "ok"] as const) {
    rerender(<Pill tone={tone}>Word</Pill>);
    expect(screen.getByText("Word")).toHaveAttribute("data-tone", tone);
  }
});

test("a status chip says its state in words, with a dot that is only decoration", () => {
  const { container } = render(<StatusChip tone="warn">Backup needed</StatusChip>);
  const chip = screen.getByRole("button", { name: "Backup needed" });
  expect(chip).toHaveAttribute("data-tone", "warn");
  expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
});

test("the inferred tag is a dashed outline with an approximate sign, and a screen reader hears what it means", () => {
  const { container } = render(
    <Pill inferred describedAs="Inferred by the assistant, not stated">
      Inferred
    </Pill>,
  );
  const tag = container.querySelector("[data-inferred]")!;
  expect(tag).toHaveTextContent("≈");
  expect(screen.getByText("Inferred by the assistant, not stated")).toHaveClass("sr");
  // The visible word is hidden from the reader so it isn't read twice.
  expect(screen.getByText("Inferred", { selector: "[aria-hidden=true]" })).toBeInTheDocument();
  expect(tag.className).toMatch(/inferred/);
});
