import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "./EmptyState";
import { LoadFailed } from "./LoadFailed";
import { Skeleton } from "./Skeleton";

test("an empty state is one sentence and one button that does the next step", async () => {
  const user = userEvent.setup();
  const run = vi.fn();
  render(<EmptyState text="Nothing waiting to go out." action={{ label: "Hand something in", onClick: run }} />);
  expect(screen.getByText("Nothing waiting to go out.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Hand something in" }));
  expect(run).toHaveBeenCalledTimes(1);
});

test("an empty state without a next step has no button, and a rail one is a single line", () => {
  const { container } = render(<EmptyState inline text="Not connected" />);
  expect(screen.queryByRole("button")).toBeNull();
  expect(container.querySelector("svg")).toBeNull();
});

test("a failed load says what failed, offers Try again and keeps the raw detail behind Details", async () => {
  const user = userEvent.setup();
  const retry = vi.fn();
  render(<LoadFailed message="Couldn't load people." onRetry={retry} detail="HTTP 500: boom" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load people.");
  const detail = screen.getByText("HTTP 500: boom");
  expect(detail).not.toBeVisible();
  await user.click(screen.getByText("Details"));
  expect(detail).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

test("a failed load without a detail has no Details", () => {
  render(<LoadFailed message="Couldn't load people." onRetry={() => {}} />);
  expect(screen.queryByText("Details")).toBeNull();
});

test("skeleton rows mark their region busy and say nothing visible", () => {
  const { container } = render(<Skeleton rows={4} />);
  const region = screen.getByRole("status", { name: "Loading…" });
  expect(region).toHaveAttribute("aria-busy", "true");
  expect(container.querySelectorAll("[data-skeleton] > div")).toHaveLength(4);
  expect(region.textContent).toBe("");
});
