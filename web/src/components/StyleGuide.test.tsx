import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp } from "../test-utils";
import { StyleGuide } from "./StyleGuide";

afterEach(() => document.documentElement.removeAttribute("data-theme"));

test("every shared component has a section, in its states", () => {
  renderApp(<StyleGuide />);
  expect(screen.getByRole("heading", { level: 1, name: "Style guide" })).toBeInTheDocument();
  for (const name of ["Type scale", "Color roles", "Buttons", "Pills and the status chip", "Rows", "Segmented control", "Empty, loading and failed", "Drawer, dialog, menu and toast", "Form controls", "Evidence", "Icons"]) {
    expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
  }
  // Disabled with a reason, loading, failed, empty and skeleton states are all there.
  expect(screen.getAllByText("Pick a person first.").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("button", { busy: true }).length).toBeGreaterThan(0);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load people.");
  expect(screen.getByRole("status", { name: "Loading…" })).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("Nothing waiting to go out. Drafts appear here for your approval.")).toBeInTheDocument();
});

test("the colors are named by their roles", () => {
  renderApp(<StyleGuide />);
  for (const token of ["--canvas", "--surface", "--surface-sunk", "--accent", "--accent-soft", "--warn-soft", "--danger-soft", "--ok-soft", "--mark"]) {
    expect(screen.getByText(token)).toBeInTheDocument();
  }
});

test("the page's own toggle shows light and dark without changing what the device remembers", async () => {
  const user = userEvent.setup();
  renderApp(<StyleGuide />);
  const theme = screen.getByRole("radiogroup", { name: "Show the page in" });
  await user.click(within(theme).getByRole("radio", { name: "Dark" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  await user.click(within(theme).getByRole("radio", { name: "Light" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "light");
  expect(window.localStorage.getItem("cockpit:theme")).toBeNull();
});

test("the drawer, the dialog and the toast open from their buttons", async () => {
  const user = userEvent.setup();
  renderApp(<StyleGuide />);
  await user.click(screen.getByRole("button", { name: "Open a drawer" }));
  expect(await screen.findByRole("dialog", { name: "Add a person" })).toBeInTheDocument();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await user.click(screen.getByRole("button", { name: "Open a dialog" }));
  expect(await screen.findByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await user.click(screen.getByRole("button", { name: "Show a toast" }));
  expect(await screen.findByText("Marked as sent to Sample Person")).toBeInTheDocument();
});
