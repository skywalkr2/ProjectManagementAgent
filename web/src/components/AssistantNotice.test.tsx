import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { AssistantNotice } from "./AssistantNotice";

function status(ai: S["AiState"]): S["Status"] {
  return {
    backup: { configured: false, last_success: null, age_hours: null, needs_attention: false, last_error: null },
    ai,
    requests: { queued: 0, running: 0, review: 0, needs_you: 0 },
    version: 1,
    restart_needed: null,
  };
}

test("nothing shows when the assistant is working", async () => {
  const calls = fakeApi({ "GET status": () => status({ state: "ok", detail: null }) });
  const { container } = renderApp(<AssistantNotice />);
  await vi.waitFor(() => expect(calls.some((c) => c.route === "GET status")).toBe(true));
  expect(container.querySelector(".notice")).toBeNull();
});

test("an assistant with no account says so and what to do", async () => {
  fakeApi({ "GET status": () => status({ state: "not_set_up", detail: null }) });
  renderApp(<AssistantNotice />);
  expect(await screen.findByText("The assistant isn't set up yet")).toBeInTheDocument();
  expect(screen.getByText(/cockpit ai test/)).toBeInTheDocument();
});

test("an untested connection asks for the connection test", async () => {
  fakeApi({ "GET status": () => status({ state: "untested", detail: null }) });
  renderApp(<AssistantNotice />);
  expect(await screen.findByText("The assistant's connection hasn't been tested")).toBeInTheDocument();
  expect(screen.getByText("Run the connection test: cockpit ai test")).toBeInTheDocument();
});

test("a failing account shows the provider's own reason and never a model name", async () => {
  fakeApi({ "GET status": () => status({ state: "failing", detail: "auth: User not found" }) });
  renderApp(<AssistantNotice />);
  expect(await screen.findByText("The assistant can't use its AI account")).toBeInTheDocument();
  expect(screen.getByText("The account said: auth: User not found")).toBeInTheDocument();
  expect(
    screen.getByText("Check the account in your AI settings, then run the connection test: cockpit ai test"),
  ).toBeInTheDocument();
  expect(screen.getByText(/Needs attention/)).toBeInTheDocument(); // not colour alone
});

test("a failing account without a reason still says so", async () => {
  fakeApi({ "GET status": () => status({ state: "failing", detail: null }) });
  renderApp(<AssistantNotice />);
  expect(await screen.findByText("The account didn't work and gave no reason.")).toBeInTheDocument();
});
