import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { ICON_NAMES, Icon } from "./Icon";

test("an icon is hidden from screen readers unless it has a label", () => {
  const { container, rerender } = render(<Icon name="home" />);
  const svg = container.querySelector("svg")!;
  expect(svg).toHaveAttribute("aria-hidden", "true");
  expect(svg).toHaveAttribute("width", "18");
  expect(svg).toHaveAttribute("stroke", "currentColor");
  rerender(<Icon name="home" label="Today" size={16} />);
  expect(screen.getByRole("img", { name: "Today" })).toHaveAttribute("width", "16");
});

test("the set has every icon the app needs, each with something to draw", () => {
  const needed = [
    "home", "inbox", "send", "upload", "layers", "grid", "users", "folder", "rss", "puzzle", "gear", "search", "plus", "more",
    "help", "chevron", "chat", "close", "alert", "check", "refresh", "sun", "moon", "monitor", "menu", "panel-left",
  ];
  expect(ICON_NAMES).toEqual(expect.arrayContaining(needed));
  for (const name of ICON_NAMES) {
    const { container, unmount } = render(<Icon name={name} />);
    expect(container.querySelector("path, circle, rect")).not.toBeNull();
    unmount();
  }
});
