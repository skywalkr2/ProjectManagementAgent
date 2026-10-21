import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi, renderApp } from "../test-utils";
import { BottomBar } from "./BottomBar";

function show(handlers: Partial<Record<"onHandIn" | "onAsk" | "onHelp" | "onFeedback" | "onOpenGuide", () => void>> = {}) {
  fakeApi({ "GET panels": () => [], "GET changes": () => [], "GET followups": () => [] });
  const noop = () => undefined;
  renderApp(
    <BottomBar
      current="today"
      version="9.8.7"
      onHandIn={handlers.onHandIn ?? noop}
      onAsk={handlers.onAsk ?? noop}
      onHelp={handlers.onHelp ?? noop}
      onFeedback={handlers.onFeedback ?? noop}
      onOpenGuide={handlers.onOpenGuide ?? noop}
    />,
  );
}

test("the bar has Today, Work, a plus for handing something in, Ask and More", () => {
  show();
  const bar = screen.getByRole("navigation", { name: "Views" });
  expect(within(bar).getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");
  expect(within(bar).getByRole("button", { name: "Work" })).toBeInTheDocument();
  expect(within(bar).getByRole("button", { name: "Hand something in" })).toBeInTheDocument();
  expect(within(bar).getByRole("button", { name: "Ask" })).toBeInTheDocument();
  expect(within(bar).getByRole("button", { name: "More" })).toBeInTheDocument();
});

test("the plus and Ask run the same actions as the header's", async () => {
  const user = userEvent.setup();
  const onHandIn = vi.fn();
  const onAsk = vi.fn();
  show({ onHandIn, onAsk });
  await user.click(screen.getByRole("button", { name: "Hand something in" }));
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(onHandIn).toHaveBeenCalledTimes(1);
  expect(onAsk).toHaveBeenCalledTimes(1);
});

test("Work opens a sheet with its views, as links", async () => {
  const user = userEvent.setup();
  show();
  await user.click(screen.getByRole("button", { name: "Work" }));
  const sheet = await screen.findByRole("dialog", { name: "Work" });
  expect(within(sheet).getAllByRole("link").map((a) => a.textContent)).toEqual(["What changed", "Follow-ups", "To-dos and questions", "Waiting to go out", "Stages"]);
  expect(within(sheet).getByRole("link", { name: "Stages" })).toHaveAttribute("href", expect.stringMatching(/#work\/stages$/));
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("More lists Records, Connections, Add-ons and Settings, the help items, and this device's theme and density", async () => {
  const user = userEvent.setup();
  const onHelp = vi.fn();
  show({ onHelp });
  await user.click(screen.getByRole("button", { name: "More" }));
  const sheet = await screen.findByRole("dialog", { name: "More" });
  expect(within(sheet).getAllByRole("link").map((a) => a.textContent)).toEqual(["Projects", "People", "Files", "Knowledge", "Connections", "Add-ons", "Settings"]);
  expect(within(sheet).getByRole("button", { name: "Show keyboard shortcuts" })).toBeInTheDocument();
  expect(within(sheet).getByRole("button", { name: "Setup guide" })).toBeInTheDocument();
  expect(within(sheet).getByRole("button", { name: "Write feedback" })).toBeInTheDocument();
  expect(within(sheet).getByText("Version 9.8.7")).toBeInTheDocument();
  expect(within(sheet).getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
  expect(within(sheet).getByRole("radiogroup", { name: "Spacing" })).toBeInTheDocument();
  await user.click(within(sheet).getByRole("button", { name: "Show keyboard shortcuts" }));
  await waitFor(() => expect(onHelp).toHaveBeenCalledTimes(1));
});
