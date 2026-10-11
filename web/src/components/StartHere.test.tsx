import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { StartHere } from "./StartHere";

const step = (id: string, extra: Partial<S["SetupStepView"]> = {}): S["SetupStepView"] => ({
  id,
  done: false,
  skipped: false,
  label: "",
  explanation: "",
  action: null,
  plugin: null,
  ...extra,
});

const CORE = ["workspace", "template", "ai", "backup", "people", "first_note", "addons"];

function api(steps: S["SetupStepView"][], finished = false) {
  return fakeApi({ "GET setup": () => ({ steps, finished, local: true }) });
}

const open = () => {
  const onOpenGuide = vi.fn();
  renderApp(<StartHere workspace="Test" onOpenGuide={onOpenGuide} />);
  return { onOpenGuide };
};

beforeEach(() => window.localStorage.clear());

test("a new workspace lists every step still to do, each saying in words that it is not done", async () => {
  api(CORE.map((id) => step(id)));
  open();
  const steps = within(await screen.findByRole("list")).getAllByRole("listitem");
  expect(steps).toHaveLength(CORE.length);
  for (const item of steps) expect(item).toHaveTextContent("Not done yet");
  expect(steps[0]).toHaveTextContent("Name the workspace and say who you are");
  expect(steps[2]).toHaveTextContent("Add an AI account and test it");
  expect(steps[steps.length - 1]).toHaveTextContent("Turn on your add-ons");
});

test("the add-ons step opens the guide at its own step", async () => {
  const user = userEvent.setup();
  api([step("addons")]);
  const { onOpenGuide } = open();
  await user.click(await screen.findByRole("button", { name: "Set up: Turn on your add-ons" }));
  expect(onOpenGuide).toHaveBeenLastCalledWith("addons");
});

test("steps that are done or skipped are not listed", async () => {
  api([step("workspace", { done: true }), step("template", { skipped: true }), step("ai"), step("backup")]);
  open();
  const steps = within(await screen.findByRole("list")).getAllByRole("listitem");
  expect(steps.map((s) => s.getAttribute("data-step"))).toEqual(["ai", "backup"]);
});

test("a plugin's step shows its own words", async () => {
  api([step("plugin/tidy", { label: "Connect the tidy-up tool", plugin: "plugin" })]);
  open();
  expect(await screen.findByText("Connect the tidy-up tool")).toBeInTheDocument();
});

test("each button opens the guide at its own step", async () => {
  const user = userEvent.setup();
  api([step("ai"), step("backup")]);
  const { onOpenGuide } = open();
  await user.click(await screen.findByRole("button", { name: "Set up: Choose a backup folder" }));
  expect(onOpenGuide).toHaveBeenLastCalledWith("backup");
  await user.click(screen.getByRole("button", { name: "Set up: Add an AI account and test it" }));
  expect(onOpenGuide).toHaveBeenLastCalledWith("ai");
});

test("once every step is done or skipped the card is gone", async () => {
  const calls = api([step("workspace", { done: true }), step("template", { skipped: true })], true);
  open();
  await vi.waitFor(() => expect(calls.filter((c) => c.route === "GET setup").length).toBeGreaterThan(0));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
});

test("hiding the card is remembered in this browser", async () => {
  const user = userEvent.setup();
  api([step("ai")]);
  open();
  await user.click(await screen.findByRole("button", { name: "Hide this" }));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
  document.body.innerHTML = "";
  api([step("ai")]);
  open();
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("heading", { name: "Start here" })).not.toBeInTheDocument();
});

test("a browser that blocks storage still shows the card", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  api([step("ai")]);
  open();
  expect(await screen.findByRole("heading", { name: "Start here" })).toBeInTheDocument();
  vi.restoreAllMocks();
});
