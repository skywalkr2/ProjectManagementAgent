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
