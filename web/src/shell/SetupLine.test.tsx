import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp, setupStep as step, setupView } from "../test-utils";
import { SetupLine } from "./SetupLine";

const CORE = ["workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons"];

function api(steps: S["SetupStepView"][], finished = false) {
  return fakeApi({ "GET setup": () => setupView(steps, { finished }) });
}

const open = () => {
  const onOpenGuide = vi.fn();
  renderApp(<SetupLine workspace="Test" onOpenGuide={onOpenGuide} />);
  return { onOpenGuide };
};

beforeEach(() => window.localStorage.clear());

test("it is one row: how far along, a progress bar, the next step and a button to continue", async () => {
  api([step("workspace", { done: true }), step("people", { skipped: true }), step("ai"), step("backup")]);
  open();
  const line = await screen.findByRole("region", { name: "Setup" });
  expect(line).toHaveTextContent("Setup 2 of 4");
  expect(line).toHaveTextContent("Next: Add an AI account and test it");
  const bar = screen.getByRole("progressbar", { name: "Setup progress" });
  expect(bar).toHaveAttribute("aria-valuenow", "2");
  expect(bar).toHaveAttribute("aria-valuemax", "4");
});

test("a brand new workspace starts at zero and names the first step", async () => {
  api(CORE.map((id) => step(id)));
  open();
  const line = await screen.findByRole("region", { name: "Setup" });
  expect(line).toHaveTextContent("Setup 0 of 5");
  expect(line).toHaveTextContent("Next: Name the workspace and say who you are");
});

test("Continue setup opens the guide at the next step", async () => {
  const user = userEvent.setup();
  api([step("workspace", { done: true }), step("ai"), step("backup")]);
  const { onOpenGuide } = open();
  await user.click(await screen.findByRole("button", { name: "Continue setup" }));
  expect(onOpenGuide).toHaveBeenLastCalledWith("ai");
});

test("the optional extras and an add-on's own steps are neither counted nor named", async () => {
  api([step("ai"), step("template"), step("plugin/tidy", { label: "Connect the tidy-up tool", plugin: "plugin" })]);
  open();
  const line = await screen.findByRole("region", { name: "Setup" });
  expect(line).toHaveTextContent("Setup 0 of 1");
  expect(line).toHaveTextContent("Next: Add an AI account and test it");
  expect(screen.queryByText(/tidy-up/)).toBeNull();
});

test("once every step is done or skipped the line is gone", async () => {
  const calls = api([step("workspace", { done: true }), step("people", { skipped: true }), step("template")], true);
  open();
  await vi.waitFor(() => expect(calls.filter((c) => c.route === "GET setup").length).toBeGreaterThan(0));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("region", { name: "Setup" })).toBeNull();
});

test("hiding the line is remembered in this browser", async () => {
  const user = userEvent.setup();
  api([step("ai")]);
  open();
  await user.click(await screen.findByRole("button", { name: "More actions for setup" }));
  await user.click(screen.getByRole("menuitem", { name: "Hide" }));
  expect(screen.queryByRole("region", { name: "Setup" })).toBeNull();
  document.body.innerHTML = "";
  api([step("ai")]);
  open();
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("region", { name: "Setup" })).toBeNull();
});

test("a browser that blocks storage still shows the line", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  api([step("ai")]);
  open();
  expect(await screen.findByRole("region", { name: "Setup" })).toBeInTheDocument();
  vi.restoreAllMocks();
});
