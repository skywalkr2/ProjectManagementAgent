import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { App } from "../App";
import { DemoStrip } from "./DemoStrip";

const rc = (extra: Partial<S["RuntimeConfig"]> = {}): S["RuntimeConfig"] => ({
  api_base: "api",
  assistant_name: "Helper",
  base_path: "",
  demo: false,
  feedback_to: null,
  narrow_below_px: 640,
  pm: null,
  shortcuts: { undo: "u", hand_in: "n", help: "?", ask: "/" },
  toast_seconds: 0,
  version: "9.8.7",
  wording: {},
  workspace_name: "Workspace",
  ...extra,
});

test("the strip is a labelled landmark with the word Demo and the sentence", () => {
  renderApp(<DemoStrip />);
  const strip = screen.getByRole("complementary", { name: "Demo workspace" });
  expect(strip).toHaveTextContent("Demo");
  expect(strip).toHaveTextContent("Everything here is made up. Nothing you do here reaches anyone.");
  expect(screen.queryByRole("button")).toBeNull();
});

test("every screen shows the strip when the workspace is a demo", () => {
  fakeApi({});
  renderApp(<App rc={rc({ demo: true })} />);
  expect(screen.getByRole("complementary", { name: "Demo workspace" })).toBeInTheDocument();
});

test("no strip when the workspace is not a demo", () => {
  fakeApi({});
  renderApp(<App rc={rc({ demo: false })} />);
  expect(screen.queryByRole("complementary", { name: "Demo workspace" })).toBeNull();
});
