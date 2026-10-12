import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "./lib/api";
import { fakeApi, renderApp } from "./test-utils";
import { App } from "./App";

const rc = (extra: Partial<S["RuntimeConfig"]> = {}): S["RuntimeConfig"] => ({
  api_base: "api",
  assistant_name: "Helper",
  base_path: "",
  demo: false,
  feedback_to: "feedback@example.com",
  narrow_below_px: 640,
  logo: false,
  theme: "system",
  density: "comfortable",
  pm: null,
  shortcuts: { undo: "u", hand_in: "n", help: "?", ask: "/" },
  toast_seconds: 0,
  version: "9.8.7",
  wording: {},
  workspace_name: "Workspace",
  ...extra,
});

test("the footer says the version and opens Send feedback, and focus comes back to it", async () => {
  fakeApi({ "GET panels": () => [], "GET asks": () => [] });
  renderApp(<App rc={rc()} />);
  const user = userEvent.setup();
  expect(screen.getByText("Version 9.8.7")).toBeInTheDocument();
  const button = screen.getByRole("button", { name: "Send feedback" });
  await user.click(button);
  const dialog = screen.getByRole("dialog", { name: "Send feedback" });
  await user.type(screen.getByLabelText("What happened, or what would help?"), "Hello");
  expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Hello\n\nApp version: 9.8.7\nScreen: Today");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(dialog).not.toBeInTheDocument());
  await waitFor(() => expect(button).toHaveFocus());
});

test("the Ask key comes from the configured shortcuts", async () => {
  fakeApi({ "GET panels": () => [], "GET asks": () => [] });
  renderApp(<App rc={rc({ shortcuts: { undo: "u", hand_in: "n", help: "?", ask: "g" } })} />);
  const user = userEvent.setup();
  await user.keyboard("/");
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.keyboard("g");
  expect(await screen.findByRole("dialog", { name: "Ask Helper" })).toBeInTheDocument();
});

const today = {
  "GET panels": () => [],
  "GET asks": () => [],
  "GET today/agenda": () => [],
  "GET today/todo": () => [],
  "GET today/arrived": () => ({ items: [], left_out: 0 }),
  "GET watch": () => [],
  "GET watch/kinds": () => [
    { name: "demo/feed", label: "A feed", plugin: "demo", items: [] },
    { name: "folder", label: "A folder", plugin: null, items: [] },
  ],
  "GET projects": () => [],
};

test("Connect on Today's empty card opens Sources with the add form open, and only that time", async () => {
  fakeApi(today);
  renderApp(<App rc={rc()} />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Connect a calendar" }));
  expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
  expect(await screen.findByRole("form", { name: "Add a source" })).toBeInTheDocument();
  // Going away and coming back by the views doesn't open it again.
  await user.click(screen.getByRole("button", { name: "Workspace, go to Today" }));
  expect(await screen.findByRole("button", { name: "Connect a mailbox" })).toBeInTheDocument();
  await user.click(within(screen.getByRole("navigation", { name: "Views" })).getByRole("button", { name: "Sources" }));
  expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Add a source" })).toBeNull();
});

test("the workspace name goes to Today from any screen", async () => {
  fakeApi(today);
  renderApp(<App rc={rc()} />);
  const user = userEvent.setup();
  await user.click(within(screen.getByRole("navigation", { name: "Views" })).getByRole("button", { name: "Sources" }));
  expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Workspace, go to Today" }));
  expect(await screen.findByRole("heading", { name: "Agenda" })).toBeInTheDocument();
});
