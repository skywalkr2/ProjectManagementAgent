import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { PluginToday } from "./PluginToday";

function line(extra: Partial<S["TodayLineView"]> = {}): S["TodayLineView"] {
  return { plugin: "demo", id: "L-1", text: "Chapter 3 is ready to look at", about: null, action: null, action_is: null, why: "", until: null, ...extra };
}

const about = { kind: "demo/chapter", id: "CH-3" };
const on = `kind=${encodeURIComponent(about.kind)}&id=${about.id}`;

const proposal = (): S["ActionProposalView"] => ({
  token: "tok-1",
  action: "demo/check",
  summary: "Check chapter 3",
  ops: [{ op: "note", label: "Note: checked" }],
  files: [],
  previews: [],
  choices: [],
  notes: [],
  expires_at: "2026-10-09T15:00:00Z",
});

test("nothing shows when no plugin has a line", async () => {
  const calls = fakeApi({ "GET plugin-today": () => [] });
  renderApp(<PluginToday />);
  await waitFor(() => expect(calls.length).toBe(1));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(screen.queryByRole("region", { name: "More for today" })).toBeNull();
  expect(screen.queryByRole("heading")).toBeNull();
});

test("one row per line, text as plain text, with why and until said as waiting", async () => {
  fakeApi({
    "GET plugin-today": () => [
      line({ text: "Review <b>this</b>", why: "The author is away", until: "2026-10-20" }),
      line({ id: "L-2", text: "Second line", why: "Needs a reader" }),
      line({ id: "L-3", text: "Third line" }),
    ],
  });
  renderApp(<PluginToday />);
  const section = await screen.findByRole("region", { name: "More for today" });
  const rows = within(section).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Review <b>this</b>");
  expect(rows[0].querySelector("b")).toBeNull();
  expect(rows[0]).toHaveTextContent(/Waiting: The author is away · until/);
  expect(rows[1]).toHaveTextContent("Waiting: Needs a reader");
  expect(rows[2]).not.toHaveTextContent("Waiting");
  expect(within(section).queryAllByRole("button")).toHaveLength(0);
});

test("a person action opens its review for the line's record, labelled from what the record offers", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET plugin-today": () => [line({ about, action: "demo/check", action_is: "action" })],
    [`GET plugin-actions?${on}`]: () => [{ name: "demo/check", label: "Check the chapter", on: about.kind }],
    "POST plugin-actions/demo/check/preview": () => proposal(),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Check the chapter" }));
  await screen.findByRole("dialog", { name: "Check chapter 3" });
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/check/preview")?.body).toEqual({ target: about, choices: {} });
});

test("a kind of work starts at once with a toast", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET plugin-today": () => [line({ about, action: "demo/read-through", action_is: "task" })],
    [`GET task-kinds?${on}`]: () => [{ name: "demo/read-through", label: "Read it through", on: about.kind }],
    "POST task-kinds/demo/read-through/start": () => ({ request: "REQ-1" }),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Read it through" }));
  expect(await screen.findByText("Started: Read it through")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST task-kinds/demo/read-through/start")?.body).toEqual({ about, note: "" });
});

test("a line about the whole workspace looks its action up there, and falls back to a plain label", async () => {
  fakeApi({
    "GET plugin-today": () => [
      line({ action: "demo/tidy", action_is: "action" }),
      line({ id: "L-2", text: "Other", action: "demo/unknown", action_is: "task" }),
    ],
    "GET plugin-actions": () => [{ name: "demo/tidy", label: "Tidy up", on: null }],
    "GET task-kinds": () => [],
  });
  renderApp(<PluginToday />);
  expect(await screen.findByRole("button", { name: "Tidy up" })).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Open" })).toBeInTheDocument();
});
