import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
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
