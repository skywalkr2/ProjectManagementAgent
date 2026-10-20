import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test-utils";
import { WaitingToGoOut } from "./WaitingToGoOut";

// Waiting to go out (design 7.4): where what is ready to leave waits for the person's approval. The sending itself is not built,
// so the screen is its empty state, designed: what will wait here, how things leave today, and the way to what changed.

test("the screen says what waits here and that nothing goes without the person's approval", () => {
  renderApp(<WaitingToGoOut onView={() => undefined} />);
  expect(screen.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeInTheDocument();
  expect(screen.getByText(/Nothing is sent, published or posted without your approval/)).toBeInTheDocument();
});

test("with nothing waiting it says so and shows how a message leaves today", () => {
  renderApp(<WaitingToGoOut onView={() => undefined} />);
  expect(screen.getByText("Nothing is waiting to go out.")).toBeInTheDocument();
  expect(screen.getByText(/copy a message in Follow-ups, send it yourself/i)).toBeInTheDocument();
});

test("its one button goes to what changed, and a link goes to Follow-ups", async () => {
  const user = userEvent.setup();
  const onView = vi.fn();
  renderApp(<WaitingToGoOut onView={onView} />);
  await user.click(screen.getByRole("button", { name: "See what changed" }));
  expect(onView).toHaveBeenLastCalledWith("work/changed");
  await user.click(screen.getByRole("button", { name: "Open Follow-ups" }));
  expect(onView).toHaveBeenLastCalledWith("work/followups");
});
