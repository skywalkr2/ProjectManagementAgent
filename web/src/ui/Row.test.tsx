import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { Row } from "./Row";

test("a row has a pill column, a title, a meta line, then the primary action and the menu", () => {
  render(
    <ul>
      <Row
        pill={<span>Decision</span>}
        title="Make 1 decision"
        meta="From an email"
        primary={<button type="button">Answer</button>}
        menu={<button type="button">More</button>}
      />
    </ul>,
  );
  const row = screen.getByRole("listitem");
  expect(row).toHaveAttribute("data-row");
  expect(within(row).getByText("Make 1 decision")).toBeInTheDocument();
  expect(within(row).getByText("From an email")).toBeInTheDocument();
  const buttons = within(row).getAllByRole("button");
  // The menu is the last thing on the row.
  expect(buttons.map((b) => b.textContent)).toEqual(["Answer", "More"]);
});

test("a row can take focus from the keyboard loop, and says when it is selected", () => {
  const { rerender } = render(
    <ul>
      <Row title="One" />
    </ul>,
  );
  const row = screen.getByRole("listitem");
  row.focus();
  expect(row).toHaveFocus();
  expect(row).not.toHaveAttribute("aria-current");
  rerender(
    <ul>
      <Row title="One" selected />
    </ul>,
  );
  expect(screen.getByRole("listitem")).toHaveAttribute("aria-current", "true");
  expect(screen.getByRole("listitem")).toHaveAttribute("data-selected");
});

test("expanded content sits under the row", () => {
  render(
    <ul>
      <Row title="One">
        <p>Item inside</p>
      </Row>
    </ul>,
  );
  expect(within(screen.getByRole("listitem")).getByText("Item inside")).toBeInTheDocument();
});

test("a row can be a plain block outside a list", () => {
  render(<Row as="div" title="Alone" />);
  expect(screen.queryByRole("listitem")).toBeNull();
  expect(screen.getByText("Alone").closest("[data-row]")?.tagName).toBe("DIV");
});
