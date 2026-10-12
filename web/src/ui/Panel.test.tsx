import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { Panel } from "./Panel";

test("a panel is a region named by its heading, with its count and actions", () => {
  render(
    <Panel title="Needs you" count={8} actions={<button type="button">Filter</button>}>
      <p>Body</p>
    </Panel>,
  );
  const region = screen.getByRole("region", { name: "Needs you" });
  expect(region).toHaveTextContent("8");
  expect(screen.getByRole("heading", { level: 2, name: "Needs you" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Filter" })).toBeInTheDocument();
  expect(screen.getByText("Body")).toBeInTheDocument();
});

test("a rail pane can use a smaller heading level, and an empty count shows nothing", () => {
  render(<Panel title="Agenda" level={3} count="" small />);
  expect(screen.getByRole("heading", { level: 3, name: "Agenda" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Agenda" })).not.toHaveTextContent(/\d/);
});
