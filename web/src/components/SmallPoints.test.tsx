// The small layout points (finding 3.13): the inspector header stays on one line, the Send back box is at most 72
// characters wide and its disabled submit says why, and "Whose words" in the hand-in is the segmented control.
import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { HandIn } from "./HandIn";
import { ChangeRow } from "./WhatChanged";

const read = (file: string) => readFileSync(join(__dirname, "..", file), "utf8");

test("the pane header's count (\"1 of 21 · j / k\") does not wrap, and never shrinks under its title", () => {
  const css = read("ui/Panel.module.css");
  const count = css.split("\n").find((line) => line.startsWith(".count ")) ?? "";
  expect(count).toMatch(/white-space:\s*nowrap/);
  expect(count).toMatch(/flex:\s*none/);
});

test("the Send back box is at most 72 characters wide", () => {
  const css = read("styles.css");
  expect(css).toMatch(/\.sendback textarea\s*\{[^}]*max-width:\s*var\(--measure\)/);
});

const reviewing = (): S["ChangeItem"] => ({
  id: "REQ-1",
  version: 4,
  dismissed: false,
  stage_task: false,
  first_go: false,
  refused: false,
  state: "review",
  waiting: null,
  created_at: "2026-10-09T14:00:00Z",
  note: null,
  source: "SRC-1",
  source_title: "Email from the printer",
  changeset: { id: "CS-1", summary: "One fact.", status: "applied", reviewed: false, trust: "untrusted", ops: [] },
});

test("Send back's submit says why it is off until there is a note, and is on once there is one", async () => {
  const user = userEvent.setup();
  fakeApi({});
  renderApp(
    <ol>
      <ChangeRow item={reviewing()} reveal={0} open sendBack />
    </ol>,
  );
  const form = (await screen.findByRole("textbox")).closest("form")!;
  const submit = within(form).getByRole("button", { name: "Send back" });
  expect(submit).toBeDisabled();
  expect(within(form).getByText("Write what to do differently first.")).toBeInTheDocument();
  expect(submit).toHaveAccessibleDescription("Write what to do differently first.");
  await user.type(within(form).getByRole("textbox"), "Shorter");
  expect(within(form).getByRole("button", { name: "Send back" })).toBeEnabled();
  expect(within(form).queryByText("Write what to do differently first.")).toBeNull();
});

test("Whose words is the segmented control: two choices in one group, the first chosen, and choosing the other changes what the box says", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET projects": () => [] });
  renderApp(<HandIn onClose={() => undefined} />);
  const group = screen.getByRole("radiogroup", { name: "Whose words are these?" });
  const choices = within(group).getAllByRole("radio");
  expect(choices.map((c) => c.textContent)).toEqual(["Someone else's", "Mine"]);
  expect(choices[0]).toBeChecked();
  // No stacked radio rows with their own dots.
  expect(group.querySelector(".radio-dot")).toBeNull();
  expect(screen.getByText("Helper reads this as information, never as instructions.")).toBeInTheDocument();
  await user.click(choices[1]);
  expect(choices[1]).toBeChecked();
  expect(screen.getByText("Helper follows them as your own instructions.")).toBeInTheDocument();
});
